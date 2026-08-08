# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

<#
.SYNOPSIS
Install artifice-transcribe via uv tool install with hardware-appropriate ASR extras.

.DESCRIPTION
A standalone, double-click installer.  Detects GPU hardware, prompts for the
heavy ASR pack, and creates a Desktop shortcut.  Downloads and verifies the uv
installer with a pinned SHA256 checksum before executing it --- never pipes a
remote script directly into a shell.

The SHA256 constant in this file MUST be updated by the maintainer before every
release.  See the MAINTAINER comment in the uv-bootstrap section.

.EXAMPLE
.\install.ps1
#>
param()

$ErrorActionPreference = "Stop"

# --- internal helpers ---------------------------------------------------------

function Write-Banner {
    param([string]$Message)
    Write-Host ""
    Write-Host "--- $Message ---"
}

function Exit-Install {
    param([string]$Message)
    Write-Error $Message
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# --- pre-flight validation ----------------------------------------------------
#
# This section runs before any network activity.  It mirrors the app-name
# validation pattern from the original multi-app install.sh / install.ps1,
# where all inputs were checked ahead of the uv bootstrap so a simple typo
# never triggered a persistent machine change.

# Check for a working Internet connection by testing https://astral.sh.
# (Test-Connection is an ICMP ping and many networks block it; test the TLS
#  handshake instead.)
try {
    $null = [System.Net.ServicePointManager]::SecurityProtocol -bor `
           [System.Net.SecurityProtocolType]::Tls12
    $req = [System.Net.WebRequest]::Create("https://astral.sh/uv/install.ps1")
    $req.Timeout = 5000
    $req.Method = "HEAD"
    $req.GetResponse().Close()
} catch {
    Exit-Install "No network connection to https://astral.sh.  Check your internet connection and try again."
}

# --- ensure uv is available (pinned checksum verification) --------------------
#
# MAINTAINER: Replace the checksum below with the actual SHA256 of the
# installer BEFORE EVERY RELEASE.  To obtain it:
#
#   Invoke-WebRequest https://astral.sh/uv/install.ps1 -OutFile - | Get-FileHash -Algorithm SHA256
#
# The placeholder value will ALWAYS cause a mismatch, preventing the installer
# from running an unverified script.

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Banner "Installing uv (Python package manager)"

    $ExpectedUvHash = "PLACEHOLDER_SHA256"
    $uvInstallerUrl = "https://astral.sh/uv/install.ps1"
    $uvInstallerPath = Join-Path $env:TEMP "uv-install-$(Get-Random).ps1"

    try {
        Write-Host "  Downloading uv installer ..."
        Invoke-WebRequest -Uri $uvInstallerUrl -OutFile $uvInstallerPath `
            -ErrorAction Stop

        Write-Host "  Verifying checksum ..."
        $actualHash = (Get-FileHash -Path $uvInstallerPath -Algorithm SHA256).Hash

        if ($actualHash -ne $ExpectedUvHash) {
            Remove-Item -Force $uvInstallerPath -ErrorAction SilentlyContinue
            Exit-Install @"
SHA256 checksum MISMATCH for the uv installer.
  Expected: $ExpectedUvHash
  Actual:   $actualHash

This could mean the upstream installer has changed or the download was
tampered with.  The installer was NOT executed.

If you are the maintainer:
  1. Verify the new checksum against a trusted source.
  2. Update the `ExpectedUvHash` constant in this script.
  3. Re-run this installer.
"@
        }

        Write-Host "  Checksum verified.  Running installer ..."
        $proc = Start-Process -FilePath "powershell.exe" `
            -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$uvInstallerPath`"" `
            -Wait -PassThru -NoNewWindow

        if ($proc.ExitCode -ne 0) {
            Remove-Item -Force $uvInstallerPath -ErrorAction SilentlyContinue
            Exit-Install "uv installer exited with code $($proc.ExitCode).  uv was not installed."
        }

        Remove-Item -Force $uvInstallerPath -ErrorAction SilentlyContinue
    } catch {
        Remove-Item -Force $uvInstallerPath -ErrorAction SilentlyContinue
        Exit-Install "Failed to download or verify the uv installer: $_"
    }

    # The uv installer adds ~\.cargo\bin to the user PATH, but that only takes
    # effect in new shell sessions.  Prepend it here so the rest of this
    # script can find uv.
    $cargoBin = "$env:USERPROFILE\.cargo\bin"
    if (Test-Path $cargoBin) {
        $env:PATH = "$cargoBin;$env:PATH"
    }

    # Final check: did uv actually show up?
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Exit-Install "uv was installed but is not on PATH.  Try restarting your terminal and running this script again."
    }
}

Write-Host "  uv $(uv --version 2>&1) found."

# --- hardware probe -----------------------------------------------------------

Write-Banner "Probing hardware"

$nvidiaAvailable = $false
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $nvidiaAvailable = $true
    Write-Host "  NVIDIA GPU detected (nvidia-smi found)."
} else {
    Write-Host "  No NVIDIA GPU detected (nvidia-smi not found)."
}

# --- user prompt: ASR extras --------------------------------------------------

Write-Host ""
Write-Host "artifice-transcribe can install a heavy ASR pack (~7 GB) for speech-to-text"
Write-Host "and speaker diarisation. Without it, the server starts but transcription"
Write-Host "features will be unavailable until the pack is installed."

if ($nvidiaAvailable) {
    Write-Host ""
    Write-Host "CUDA GPU detected: the [asr-cuda] variant will download GPU-accelerated"
    Write-Host "PyTorch."
} else {
    Write-Host ""
    Write-Host "No CUDA GPU detected: the [asr] variant will download CPU-only PyTorch."
}

$answer = Read-Host "`nInstall the ASR pack now? (y/N)"

# --- install artifice-transcribe ----------------------------------------------

Write-Banner "Installing artifice-transcribe"

if ($answer -match '^[Yy]([Ee][Ss])?$') {
    if ($nvidiaAvailable) {
        Write-Host "  GPU (CUDA) install --- this may download ~7 GB"
        uv tool install "artifice-transcribe[asr-cuda]"
    } else {
        Write-Host "  CPU install --- this avoids the ~7 GB CUDA runtime"
        uv tool install "artifice-transcribe[asr]"
    }
} else {
    Write-Host "  Skipping ASR pack.  The server will start but transcription is unavailable."
    Write-Host "  Install later with: uv tool install artifice-transcribe[asr]"
    uv tool install artifice-transcribe
}

if ($LASTEXITCODE -ne 0) {
    Exit-Install "uv tool install failed (exit code $LASTEXITCODE)."
}

# --- desktop shortcut ---------------------------------------------------------

Write-Banner "Desktop shortcut"

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Artifice Transcribe.lnk"

# Resolve the installed entry-point.  uv tool install places executables in
# ~\.cargo\bin by default.  Try that first, then fall back to a PATH search.
$cargoBin = "$env:USERPROFILE\.cargo\bin"
if (Test-Path "$cargoBin\artifice-transcribe.exe") {
    $targetExe = "$cargoBin\artifice-transcribe.exe"
} elseif (Test-Path "$cargoBin\artifice-transcribe.cmd") {
    $targetExe = "$cargoBin\artifice-transcribe.cmd"
} else {
    # uv may have installed to a non-default tool dir; probe it.
    $found = Get-Command artifice-transcribe -CommandType Application -ErrorAction SilentlyContinue
    if ($found) {
        $targetExe = $found.Source
    } else {
        # Re-add cargo bin to PATH in case it was dropped and retry.
        $env:PATH = "$cargoBin;$env:PATH"
        $found = Get-Command artifice-transcribe -CommandType Application -ErrorAction SilentlyContinue
        if ($found) {
            $targetExe = $found.Source
        } else {
            Write-Host "  WARNING: Could not locate artifice-transcribe entry point."
            Write-Host "  Skipping desktop shortcut.  Launch from terminal with: artifice-transcribe"
            $targetExe = $null
        }
    }
}

if ($targetExe) {
    $wshShell = New-Object -ComObject WScript.Shell
    $shortcut = $wshShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $targetExe
    $shortcut.WorkingDirectory = [Environment]::GetFolderPath("UserProfile")
    $shortcut.Description = "Artifice Transcribe --- Speech-to-Text & Diarization"
    $shortcut.Save()

    Write-Host "  Created: $shortcutPath"
}

# --- summary ------------------------------------------------------------------

Write-Host ""
Write-Host "==============================================="
Write-Host "  Install complete!"
Write-Host "==============================================="
Write-Host ""
Write-Host "  Launch:  artifice-transcribe"
Write-Host "  Uninstall: uv tool uninstall artifice-transcribe"
Write-Host ""
Read-Host "Press Enter to exit"
