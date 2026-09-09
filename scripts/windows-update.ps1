# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

<#
.SYNOPSIS
    Sync the Windows clone of artifice-suite with the GitHub remote and
    reinstall dependencies.

.DESCRIPTION
    This clone (C:\dev\artifice-suite) is the one used to RUN the apps natively
    on Windows, where pywebview gets a real EdgeWebView2 window. It is separate
    from the WSL clone used for development, so it has to be pulled explicitly.

    Note the remote is named `github`, not `origin`. There is also a `wsl`
    remote pointing at the WSL working copy, which is deliberately NOT used
    here — the GitHub remote is the canonical source.

    Extras are pinned explicitly rather than relying on `--extra all`, because
    `all` carries a bare `artifice-ocr` (no [web,window]); syncing with `all`
    alone would strip pywebview and FastAPI and silently break the OCR desktop
    window that already works.

.PARAMETER Branch
    Branch to sync to. Defaults to main.

.PARAMETER NoSync
    Pull only; skip the uv dependency sync.

.PARAMETER Asr
    Also install the ASR stack (WhisperX, torch, pyannote) for automatic
    transcription. Several GB. Not needed for hand transcription, uploads,
    editing or export.

    You rarely need this switch: if the ASR stack is already installed, it is
    detected and kept automatically. `uv sync` reconciles the environment to
    exactly the extras it is given, so without that detection a routine update
    would silently uninstall a multi-gigabyte stack the user had deliberately
    added.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows-update.ps1
#>
[CmdletBinding()]
param(
    [string]$Branch = "main",
    [switch]$NoSync,
    [switch]$Asr
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "  Artifice Suite - Windows update" -ForegroundColor Cyan
Write-Host "  $repo"
Write-Host ""

Set-Location $repo

# ── Refuse to clobber uncommitted work ────────────────────────────────────
# Only TRACKED modifications block: those are what a checkout or fast-forward
# could overwrite. Untracked files (local launchers, scratch notes, this
# script before it is committed) are safe to leave in place — and in the one
# case where they are not, because the incoming branch adds a file at the same
# path, git refuses the checkout itself with a clear message.
$dirty = git status --porcelain --untracked-files=no
if ($dirty) {
    Write-Host "  Uncommitted changes to tracked files - not touching them:" -ForegroundColor Yellow
    $dirty | ForEach-Object { Write-Host "    $_" }
    Write-Host ""
    Write-Host "  Commit or stash them first, then re-run." -ForegroundColor Yellow
    exit 1
}

# ── Fetch ─────────────────────────────────────────────────────────────────
Write-Host "  Fetching from github..." -ForegroundColor Gray
git fetch github --prune
if ($LASTEXITCODE -ne 0) { Write-Host "  git fetch failed." -ForegroundColor Red; exit 1 }

$before = git rev-parse --short HEAD
$target = git rev-parse --short "github/$Branch"

if ($before -eq $target) {
    Write-Host "  Already up to date at $before ($Branch)." -ForegroundColor Green
} else {
    $behind = git rev-list --count "HEAD..github/$Branch"
    Write-Host "  $behind commit(s) behind github/$Branch. Updating..." -ForegroundColor Gray

    # Ask whether the local branch exists rather than trying the checkout and
    # reacting to failure. Redirecting a native exe's stderr in PowerShell 5.1
    # wraps each line in an ErrorRecord and, under ErrorActionPreference=Stop,
    # aborts the script before any fallback can run — so the "try it and see"
    # shape cannot work here.
    #
    # This matters more than usual because the remote is named `github`, not
    # `origin`: git's DWIM "create a local branch tracking the remote one"
    # only fires for a single remote it can guess, so `git checkout main`
    # fails outright here and the explicit -b path is the normal case.
    git rev-parse --verify --quiet "refs/heads/$Branch" > $null
    $branchExists = ($LASTEXITCODE -eq 0)

    if ($branchExists) {
        git checkout $Branch
    } else {
        Write-Host "  Creating local '$Branch' tracking github/$Branch..." -ForegroundColor Gray
        git checkout -b $Branch --track "github/$Branch"
    }
    if ($LASTEXITCODE -ne 0) { Write-Host "  checkout failed." -ForegroundColor Red; exit 1 }

    # --ff-only: a divergent local branch should stop and be looked at, never
    # be silently merged by a launcher script.
    git merge --ff-only "github/$Branch"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Local '$Branch' has diverged from github/$Branch." -ForegroundColor Red
        Write-Host "  Resolve by hand - refusing to merge automatically." -ForegroundColor Red
        exit 1
    }
    Write-Host "  Updated $before -> $(git rev-parse --short HEAD)" -ForegroundColor Green
}

Write-Host "  Branch: $(git rev-parse --abbrev-ref HEAD)   HEAD: $(git log --oneline -1)"

# ── Dependencies ──────────────────────────────────────────────────────────
if ($NoSync) {
    Write-Host ""
    Write-Host "  -NoSync given; skipping dependency install." -ForegroundColor Gray
    exit 0
}

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    Write-Host "  uv not found on PATH - cannot sync dependencies." -ForegroundColor Red
    Write-Host "  Install from https://docs.astral.sh/uv/ then re-run." -ForegroundColor Red
    exit 1
}

# Is the ASR stack already present? `uv sync` reconciles the environment to
# exactly the extras it is given, so omitting --extra asr on a machine that has
# it would silently uninstall several GB the user chose to add. Detect and
# preserve rather than surprise them.
$asrInstalled = $false
$venvPy = Join-Path $repo ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    & $venvPy -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('whisperx') else 1)" 2>$null
    $asrInstalled = ($LASTEXITCODE -eq 0)
}

$extras = @("--extra", "all", "--extra", "ocr-web", "--extra", "transcribe")

if ($Asr -or $asrInstalled) {
    $extras += @("--extra", "asr")
    if ($asrInstalled -and -not $Asr) {
        Write-Host ""
        Write-Host "  ASR stack detected - keeping it (pass -NoSync to skip entirely)." -ForegroundColor Gray
    } else {
        Write-Host ""
        Write-Host "  Installing the ASR stack. This is a multi-GB download." -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "  Syncing dependencies (no ASR stack - that stays opt-in)..." -ForegroundColor Gray
}

# ocr-web   : artifice-ocr[web,window] - keeps the OCR desktop window working
# transcribe: artifice-transcribe core - FastAPI/SQLAlchemy, no torch
# all       : the remaining apps, so the whole workspace stays importable
uv sync @extras
if ($LASTEXITCODE -ne 0) {
    Write-Host "  uv sync failed." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  Done." -ForegroundColor Green
if ($Asr -or $asrInstalled) {
    Write-Host "  ASR stack is installed - automatic transcription available." -ForegroundColor Gray
} else {
    Write-Host "  ASR (Whisper/pyannote) is not installed. To add it:" -ForegroundColor Gray
    Write-Host "      scripts\windows-update.ps1 -Asr" -ForegroundColor Gray
}
Write-Host ""
