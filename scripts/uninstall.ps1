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

# ----- helper: run a native command without its stderr aborting the script -----

# Windows PowerShell 5.1 wraps every stderr line from a native executable in an
# ErrorRecord (NativeCommandError).  Under `$ErrorActionPreference = "Stop"`
# that record is TERMINATING, so a program which merely reports progress on
# stderr kills the script even when it exited 0.
#
# uv does exactly that: `uv tool uninstall` writes "Uninstalled 2 executables:
# ..." to stderr, and `uv tool list` writes "No tools installed" there too.
# Measured on native Windows 11: the uninstaller aborted at the `uv tool
# uninstall` line, exited 1 after a SUCCESSFUL removal, and never reached the
# data-disclosure block below — which is the one thing this script exists to
# print.  The `$app is not installed` branch was unreachable for the same
# reason.
#
# Restoring the preference only around the native call keeps `Stop` semantics
# for the rest of the script.
# stderr is DISCARDED rather than merged.  Merging it with 2>&1 still produces
# ErrorRecords, which render as a PowerShell error blob and would be captured
# into the message we print back to the user.  uv's own wording is not needed
# here — success is determined by $LASTEXITCODE, and this script prints its
# own summary.
function Invoke-NativeStdout {
    param([scriptblock]$Command)

    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        return (& $Command 2>$null | Out-String)
    }
    finally {
        $ErrorActionPreference = $previous
    }
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
    $toolList = Invoke-NativeStdout { uv tool list }
    if ($toolList -match "(?m)^$([regex]::Escape($app))\s") {
        Write-Host ""
        Invoke-NativeStdout { uv tool uninstall $app } | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Error "uv tool uninstall failed for $app (exit $LASTEXITCODE)"
            exit 1
        }
        Write-Host "Removed: $app"
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

# Exit explicitly.  Without this the script's status is whatever $LASTEXITCODE
# a preceding native call happened to leave behind, which made a successful
# uninstall report failure to any caller that checks.
exit 0
