# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

<#
.SYNOPSIS
Remove one or more Artifice apps, leaving user data in place.

.DESCRIPTION
For each app, the script:
  1. Reads the app's user-data directory (via its own --data-dir command)
     BEFORE the app is removed.
  2. Runs `uv tool uninstall <app>`
  3. Prints a prominent disclosure: the program is removed, your data is
     still on disk, and it may contain an API key.

It does NOT delete your data and does NOT ask interactively.

.PARAMETER Apps
One or more app names: artifice-ocr, artifice-draft, artifice-graph,
artifice-transcribe.

.EXAMPLE
.\scripts\uninstall.ps1 artifice-ocr
#>

param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Apps
)

$ErrorActionPreference = "Stop"

$ValidApps = @("artifice-ocr", "artifice-draft", "artifice-graph", "artifice-transcribe")

if (-not $Apps -or $Apps.Count -eq 0) {
    Write-Error "No app specified. Usage: .\scripts\uninstall.ps1 <app> [<app> ...]"
    exit 1
}

# ----- ensure uv is available -----

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is not installed. Nothing to uninstall."
    exit 1
}

# ----- helper: map app name to its data-dir command -----

function Get-DataDirCommand {
    param([string]$App)
    return @($App, "--data-dir")
}

# ----- uninstall each app -----

foreach ($app in $Apps) {
    if ($app -notin $ValidApps) {
        Write-Error "Unknown app: $app"
        exit 1
    }

    # --- Step 1: read the data directory BEFORE removing the program ---
    $dataDir = $null
    $entryCmd = Get-DataDirCommand $app
    try {
        $result = & $entryCmd[0] $entryCmd[1] 2>$null
        if ($result) {
            $dataDir = $result.Trim()
        }
    }
    catch {
        # Could not read — app may not be installed
    }

    # --- Step 2: remove the program ---
    $toolList = uv tool list 2>$null | Out-String
    if ($toolList -match "^$app ") {
        Write-Host ""
        $uninstallOutput = uv tool uninstall $app 2>&1
        Write-Host "Removed: $uninstallOutput"
    }
    else {
        Write-Host ""
        Write-Host "$app is not installed -- nothing to remove."
    }

    # --- Step 3: disclosure ---
    if ($dataDir) {
        Write-Host @"

------------------------------------------------------------
  Your data has been LEFT IN PLACE

  Location: $dataDir

  This directory was NOT deleted by the uninstaller.
  It may contain your API key, settings, and project data.

  If you wish to delete it, run:
      Remove-Item -Recurse -Force "$dataDir"

  Be certain before you do.
------------------------------------------------------------

"@
    }
    else {
        Write-Host @"

------------------------------------------------------------
  NOTE: The data directory could not be read (the app was
  not installed, or --data-dir failed).  If you previously
  used $app, your data may still be on disk.
  Check manually -- typical paths:
    artifice-ocr         ~\.artifice_ocr\
    artifice-draft       ~\.artifice_draft\
    artifice-graph       platformdirs("artifice-graph", "ArtificeSuite")
    artifice-transcribe  platformdirs("artifice-transcribe",
                         "ArtificeSuite")
------------------------------------------------------------

"@
    }
}
