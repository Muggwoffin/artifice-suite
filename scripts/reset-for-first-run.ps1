<#
.SYNOPSIS
    Return this machine to a genuine first-run state for the Artifice Suite.

.DESCRIPTION
    `uninstall.ps1` removes programs and DELIBERATELY leaves user data behind —
    a researcher who reinstalls keeps their settings and transcripts. That is
    the right default, and it is the wrong one for a pre-release test pass:
    every app's first-run behaviour is gated on state that lives in the data
    directory, not in the program.

    Specifically, the BYOM onboarding screen is gated server-side. `byom.js`
    fetches /api/byom/state and only opens when `configured` is false, and that
    flag is read from the app's config file. Leave the data in place and no app
    will ever show you its first-run flow again.

    This script backs everything up, then removes it.

    WHAT IT DOES NOT NEED TO DO — browser storage.
    The frozen apps call webview.start() without setting `private_mode`, and
    pywebview defaults it to True, so localStorage is never persisted between
    sessions. Theme, hardware tier, column visibility and batch templates are
    already discarded on every launch. There is no WebView2 profile to clear.

.PARAMETER BackupRoot
    Where to copy the data before deleting it. Defaults to a timestamped folder
    on the Desktop. The backup is always taken; there is no way to skip it.

.PARAMETER KeepPrograms
    Remove user data but leave the `uv tool` installs alone. Useful when you are
    only resetting first-run state and not re-testing the install path.

.PARAMETER Force
    Skip the confirmation prompt. Intended for scripted runs; think before using
    it interactively.

.PARAMETER DryRun
    Report what would be backed up and removed, and change nothing.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\reset-for-first-run.ps1 -DryRun

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\reset-for-first-run.ps1
#>

# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later

[CmdletBinding()]
param(
    [string] $BackupRoot,
    [switch] $KeepPrograms,
    [switch] $Force,
    [switch] $DryRun
)

$ErrorActionPreference = 'Stop'

$APPS = @('artifice-ocr', 'artifice-draft', 'artifice-graph', 'artifice-transcribe')

function Write-Banner([string] $Text) {
    Write-Host ''
    Write-Host "--- $Text ---" -ForegroundColor Cyan
}

# ---------------------------------------------------------------------------
# Locate the data directories.
#
# Each app can report its own path via `<app> --data-dir`, which is what
# uninstall.ps1 uses and the only authoritative source — the platformdirs
# location depends on the app author string and could change. Fall back to the
# known defaults when the app is not installed, because the whole point of this
# script is to work on a machine you are about to wipe.
#
# ~/.callosip is included deliberately. artifice-graph migrates that legacy
# directory into its platformdirs location on FIRST ACCESS (config.py,
# _resolve_user_data_dir, move_mode="whole_dir", collision_is_silent=True).
# Delete graph's data but leave .callosip, and graph's next launch silently
# restores the old config, reports configured=true, and skips the BYOM screen —
# a "first run" that quietly is not one.
# ---------------------------------------------------------------------------
function Get-DataDirs {
    $dirs = [ordered]@{}

    foreach ($app in $APPS) {
        $cmd = Get-Command $app -ErrorAction SilentlyContinue
        if ($cmd) {
            # stderr goes to $null, not 2>&1: merging a native command's stderr
            # into the success stream in PowerShell 5.1 wraps each line in an
            # ErrorRecord and sets $? to false even on a clean exit.
            #
            # This probe genuinely fails in the wild. A half-removed `uv tool`
            # install leaves a shim on PATH whose package is gone, so the exe
            # exists, runs, and dies with ModuleNotFoundError — which is exactly
            # the machine this script is meant to clean up. Fall back quietly.
            try {
                $reported = (& $app --data-dir 2>$null | Select-Object -First 1)
                if ($LASTEXITCODE -eq 0 -and $reported) {
                    $dirs[$app] = $reported.Trim()
                    continue
                }
            } catch {
                # Fall through to the default below.
            }
        }
    }

    $defaults = [ordered]@{
        'artifice-ocr'        = Join-Path $env:USERPROFILE '.artifice_ocr'
        'artifice-draft'      = Join-Path $env:USERPROFILE '.artifice_draft'
        'artifice-graph'      = Join-Path $env:LOCALAPPDATA 'ArtificeSuite\artifice-graph'
        'artifice-transcribe' = Join-Path $env:LOCALAPPDATA 'ArtificeSuite\artifice-transcribe'
    }
    foreach ($k in $defaults.Keys) {
        if (-not $dirs.Contains($k)) { $dirs[$k] = $defaults[$k] }
    }

    # Suite-level state that belongs to no single app.
    $dirs['artifice-hub']      = Join-Path $env:LOCALAPPDATA 'ArtificeSuite\artifice-hub'
    $dirs['suite-discovery']   = Join-Path $env:LOCALAPPDATA 'ArtificeSuite\artifice-suite'
    $dirs['legacy-.callosip']  = Join-Path $env:USERPROFILE '.callosip'

    return $dirs
}

$dataDirs = Get-DataDirs

# ---------------------------------------------------------------------------
# Report what exists, and what it costs to lose.
# ---------------------------------------------------------------------------
Write-Banner 'Found'

$present = [ordered]@{}
foreach ($name in $dataDirs.Keys) {
    $path = $dataDirs[$name]
    if (Test-Path -LiteralPath $path) {
        $files = @(Get-ChildItem -LiteralPath $path -Recurse -File -ErrorAction SilentlyContinue)
        $bytes = ($files | Measure-Object -Property Length -Sum).Sum
        if ($null -eq $bytes) { $bytes = 0 }
        $present[$name] = $path
        '{0,-20} {1,-58} {2,4} files {3,9:N0} KB' -f $name, $path, $files.Count, ($bytes / 1KB)
    } else {
        '{0,-20} {1,-58} absent' -f $name, $path
    }
}

if ($present.Count -eq 0) {
    Write-Host ''
    Write-Host 'Nothing to remove — this machine is already in a first-run state.' -ForegroundColor Green
    exit 0
}

Write-Host ''
Write-Host 'These directories hold your API keys, settings and project data.' -ForegroundColor Yellow
Write-Host 'Everything listed will be copied to the backup before it is removed.' -ForegroundColor Yellow

# ---------------------------------------------------------------------------
# Confirm.
# ---------------------------------------------------------------------------
if ($DryRun) {
    Write-Host ''
    Write-Host 'DryRun: nothing was changed.' -ForegroundColor Green
    exit 0
}

if (-not $BackupRoot) {
    $stamp = Get-Date -Format 'yyyy-MM-dd-HHmmss'
    $BackupRoot = Join-Path ([Environment]::GetFolderPath('Desktop')) "artifice-backup-$stamp"
}

Write-Host ''
Write-Host "Backup destination: $BackupRoot"

if (-not $Force) {
    $answer = Read-Host 'Back up and remove the directories listed above? (yes/no)'
    if ($answer -ne 'yes') {
        Write-Host 'Aborted. Nothing was changed.' -ForegroundColor Yellow
        exit 1
    }
}

# ---------------------------------------------------------------------------
# Back up first. A failure here must abort before anything is deleted.
# ---------------------------------------------------------------------------
Write-Banner 'Backing up'

if (-not (Test-Path -LiteralPath $BackupRoot)) {
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
}

foreach ($name in $present.Keys) {
    $src  = $present[$name]
    $dest = Join-Path $BackupRoot $name
    Copy-Item -LiteralPath $src -Destination $dest -Recurse -Force
    Write-Host "  copied  $src  ->  $dest"
}

# Verify the backup is non-empty before destroying the source. A silent
# zero-file copy would turn this script into an unrecoverable delete.
$backedUp = @(Get-ChildItem -LiteralPath $BackupRoot -Recurse -File -ErrorAction SilentlyContinue)
if ($backedUp.Count -eq 0) {
    Write-Error "Backup produced no files at $BackupRoot. Refusing to delete anything."
    exit 1
}
Write-Host ("  verified {0} files in the backup" -f $backedUp.Count) -ForegroundColor Green

# ---------------------------------------------------------------------------
# Remove the data.
# ---------------------------------------------------------------------------
Write-Banner 'Removing user data'

foreach ($name in $present.Keys) {
    $path = $present[$name]
    Remove-Item -LiteralPath $path -Recurse -Force -Confirm:$false
    Write-Host "  removed  $path"
}

# The ArtificeSuite parent is left only if it still holds something we do not
# own; otherwise clear it so the tree looks untouched.
$suiteRoot = Join-Path $env:LOCALAPPDATA 'ArtificeSuite'
if (Test-Path -LiteralPath $suiteRoot) {
    $left = @(Get-ChildItem -LiteralPath $suiteRoot -Recurse -File -ErrorAction SilentlyContinue)
    if ($left.Count -eq 0) {
        Remove-Item -LiteralPath $suiteRoot -Recurse -Force -Confirm:$false
        Write-Host "  removed  $suiteRoot (now empty)"
    } else {
        Write-Host "  kept     $suiteRoot ($($left.Count) unrelated files remain)"
    }
}

# ---------------------------------------------------------------------------
# Remove the programs.
# ---------------------------------------------------------------------------
if (-not $KeepPrograms) {
    Write-Banner 'Uninstalling programs'
    foreach ($app in $APPS) {
        $cmd = Get-Command $app -ErrorAction SilentlyContinue
        if (-not $cmd) { Write-Host "  not installed  $app"; continue }
        # No 2>&1 on a native exe: in PowerShell 5.1 that wraps each stderr line
        # in an ErrorRecord and sets $? to false even on a clean exit.
        & uv tool uninstall $app | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  uninstalled    $app"
        } else {
            Write-Host "  FAILED         $app (uv exit $LASTEXITCODE)" -ForegroundColor Yellow
        }
    }
} else {
    Write-Banner 'Programs left installed (-KeepPrograms)'
}

# ---------------------------------------------------------------------------
# Report.
# ---------------------------------------------------------------------------
Write-Banner 'Done'
Write-Host "Backup: $BackupRoot" -ForegroundColor Green
Write-Host ''
Write-Host 'Launch the Hub — it should now behave as a first run: the BYOM screen'
Write-Host 'should open by itself, because /api/byom/state now reports configured=false.'
Write-Host ''
Write-Host 'Note: Ollama and its models are untouched. That is deliberate — the model'
Write-Host 'gate check needs you to control which models are present, not to have none.'
