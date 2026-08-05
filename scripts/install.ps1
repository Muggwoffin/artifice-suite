# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

<#
.SYNOPSIS
Install one or more Artifice apps via uv tool install.

.DESCRIPTION
The repository must already be cloned and this script must be run from the
repo root (the workspace root). Nothing is published to any index, so an
editable install from the local workspace is the only supported path.

.PARAMETER Apps
One or more app names: artifice-ocr, artifice-draft, artifice-graph,
artifice-transcribe.

.PARAMETER Cuda
Use CUDA torch backend for artifice-transcribe (default: CPU).

.PARAMETER List
List available apps and exit.

.EXAMPLE
.\scripts\install.ps1 artifice-ocr artifice-draft

.EXAMPLE
.\scripts\install.ps1 artifice-transcribe -Cuda
#>

param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Apps,

    [switch]$Cuda,

    [switch]$List
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $RepoRoot

$ValidApps = @("artifice-ocr", "artifice-draft", "artifice-graph", "artifice-transcribe")

if ($List) {
    Write-Host "Available apps:"
    Write-Host "  artifice-ocr         OCR pipeline (Tropy integration, PDF export)"
    Write-Host "  artifice-draft       Copy editing with tracked changes"
    Write-Host "  artifice-graph       Knowledge graph + Obsidian export"
    Write-Host "  artifice-transcribe  Speech-to-text + diarization"
    Write-Host ""
    Write-Host "For artifice-transcribe, add -Cuda for GPU support (default: CPU)."
    exit 0
}

if (-not $Apps -or $Apps.Count -eq 0) {
    Write-Error "No app specified. Usage: .\scripts\install.ps1 <app> [<app> ...]  (or -List)"
    exit 1
}

# ----- ensure uv is available -----

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "-- Installing uv --"
    Write-Host "uv is not installed. Downloading the official installer..."
    powershell -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Error "uv was installed but is still not on PATH. Add ~\.local\bin to your PATH and re-run."
        exit 1
    }
    Write-Host "  uv $(uv --version) installed"
}

# ----- install each app -----

$Installed = @()

foreach ($app in $Apps) {
    if ($app -notin $ValidApps) {
        Write-Error "Unknown app: $app (use -List to see available apps)"
        exit 1
    }

    $AppDir = "apps\$app"
    if (-not (Test-Path $AppDir)) {
        Write-Error "App directory not found: $AppDir"
        exit 1
    }

    Write-Host ""
    Write-Host "-- Installing $app --"

    if ($app -eq "artifice-transcribe") {
        if ($Cuda) {
            Write-Host "  GPU (CUDA) install -- this may download ~7 GB"
            uv tool install --editable "./${AppDir}[asr-cuda]" `
                --torch-backend auto
            if ($LASTEXITCODE -ne 0) {
                Write-Error "uv tool install failed for $app (CUDA)"
                exit 1
            }
        }
        else {
            Write-Host "  CPU install -- this avoids the ~7 GB CUDA runtime"
            uv tool install --editable "./${AppDir}[asr]" `
                --torch-backend cpu
            if ($LASTEXITCODE -ne 0) {
                Write-Error "uv tool install failed for $app (CPU)"
                exit 1
            }
        }
    }
    else {
        uv tool install --editable "./$AppDir"
        if ($LASTEXITCODE -ne 0) {
            Write-Error "uv tool install failed for $app"
            exit 1
        }
    }

    $Installed += $app
}

# ----- summary -----

Write-Host ""
Write-Host "-- Install complete --"

# Map of app -> data-dir command for the summary
$DataCommands = @{
    "artifice-ocr"        = "artifice-ocr --data-dir"
    "artifice-draft"      = "artifice-draft --data-dir"
    "artifice-graph"      = "artifice-graph --data-dir"
    "artifice-transcribe" = "artifice-transcribe --data-dir"
}

foreach ($app in $Installed) {
    switch ($app) {
        "artifice-ocr" {
            Write-Host "  artifice-ocr           CLI + pipeline"
            Write-Host "  artifice-ocr-web       Web UI server"
        }
        "artifice-draft" {
            Write-Host "  artifice-draft         CLI mode"
        }
        "artifice-graph" {
            Write-Host "  artifice-graph          CLI + pipeline"
            Write-Host "  artifice-graph-web      Web UI server"
        }
        "artifice-transcribe" {
            Write-Host "  artifice-transcribe     FastAPI server (port 8000)"
        }
    }

    # Print data directory
    $cmd = $DataCommands[$app]
    try {
        $dataDir = & $cmd.Split(" ")[0] $cmd.Split(" ")[1..99] 2>$null
        if ($dataDir) {
            Write-Host "  Data: $dataDir"
        }
    }
    catch {
        # data-dir failed — skip
    }
    Write-Host ""
}

Write-Host "Uninstall with: .\scripts\uninstall.ps1 <app> [<app> ...]"
