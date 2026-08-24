#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

#
# install.sh --- standalone installer for artifice-transcribe.
#
# Detects GPU hardware, prompts for the heavy ASR pack, and creates a
# desktop shortcut (Linux .desktop file or macOS .command file).  Downloads
# and verifies the uv installer with a pinned SHA256 checksum before
# executing it --- never pipes a remote script directly into a shell.
#
# The uv installer URL and checksum are version-pinned; they change only when
# UV_VERSION is deliberately bumped.  See the uv-bootstrap section below.
#
# Usage:
#   bash install.sh        (double-click the .command file on macOS)
#

set -euo pipefail

# --- helpers ------------------------------------------------------------------

die() { printf '\nERROR: %s\n' "$*" >&2; printf '\nPress Enter to exit.\n' >&2; read -r; exit 1; }
info() { printf '  %s\n' "$*"; }
banner() { printf '\n--- %s ---\n' "$*"; }

# --- pre-flight validation ----------------------------------------------------
#
# This section runs before any network activity.  It mirrors the app-name
# validation pattern from the original multi-app install.sh / install.ps1,
# where all inputs were checked ahead of the uv bootstrap so a simple typo
# never triggered a persistent machine change.

# Check for a working Internet connection.
if ! curl -fsSL --connect-timeout 5 --max-time 10 https://astral.sh/ >/dev/null 2>&1; then
    die "No network connection to https://astral.sh.  Check your internet connection and try again."
fi

# --- ensure uv is available (pinned checksum verification) --------------------
#
# The uv installer is fetched from a version-pinned URL, so its bytes are
# immutable and the checksum below changes only when UV_VERSION is bumped.
# When bumping, change UV_VERSION and EXPECTED_HASH together and re-verify
# the hash against the pinned release before committing.

UV_VERSION="0.12.5"
UV_INSTALLER_URL="https://astral.sh/uv/${UV_VERSION}/install.sh"
EXPECTED_HASH="504511fbbbd811aeaba6738abc79408956b6c7da0ca35437b3dcc24a41efc111"

if ! command -v uv &>/dev/null; then
    banner "Installing uv (Python package manager)"

    uv_installer="$(mktemp /tmp/uv-install.XXXXXX.sh)"
    # Ensure cleanup on any exit path.
    trap 'rm -f "$uv_installer"' EXIT

    info "Downloading uv installer ..."
    if ! curl -fsSL "$UV_INSTALLER_URL" -o "$uv_installer"; then
        rm -f "$uv_installer"
        die "Failed to download uv installer from $UV_INSTALLER_URL"
    fi

    info "Verifying checksum ..."
    actual_hash=$(sha256sum "$uv_installer" | awk '{print $1}')

    if [ "$actual_hash" != "$EXPECTED_HASH" ]; then
        rm -f "$uv_installer"
        die "SHA256 checksum MISMATCH for the uv installer.
  Expected: $EXPECTED_HASH
  Actual:   $actual_hash

This could mean the upstream installer has changed or the download was
tampered with.  The installer was NOT executed.

If you are the maintainer:
  1. Verify the new checksum against a trusted source.
  2. Update the EXPECTED_HASH constant in this script.
  3. Re-run this installer."
    fi

    info "Checksum verified.  Running installer ..."
    sh "$uv_installer" || {
        rm -f "$uv_installer"
        die "uv installer exited with a non-zero status.  uv was not installed."
    }

    rm -f "$uv_installer"

    # uv installs itself to ~/.local/bin (honouring XDG_BIN_HOME), not
    # ~/.cargo/bin --- that path is a legacy of uv's old cargo-based
    # installer.  The profile update only takes effect in new sessions, so
    # prepend both directories now for the current one: the modern location
    # first, ~/.cargo/bin retained as a fallback for older existing installs.
    export PATH="${XDG_BIN_HOME:-$HOME/.local/bin}:$HOME/.cargo/bin:$PATH"

    # Final check: did uv actually show up?
    if ! command -v uv &>/dev/null; then
        die "uv was installed but is not on PATH.  Try restarting your terminal and running this script again."
    fi
fi

info "uv $(uv --version 2>&1) found."

# --- hardware probe -----------------------------------------------------------

banner "Probing hardware"

nvidia_available=false
apple_silicon=false

if command -v nvidia-smi &>/dev/null; then
    nvidia_available=true
    info "NVIDIA GPU detected (nvidia-smi found)."
else
    info "No NVIDIA GPU detected (nvidia-smi not found)."
fi

# Check for Apple Silicon (macOS only).
if [ "$(uname -s)" = "Darwin" ]; then
    if sysctl -n machdep.cpu.brand_string 2>/dev/null | grep -q "Apple"; then
        apple_silicon=true
        info "Apple Silicon detected."
    fi
fi

# --- user prompt: ASR extras --------------------------------------------------

echo ""
echo "artifice-transcribe can install a heavy ASR pack (~7 GB) for speech-to-text"
echo "and speaker diarisation. Without it, the server starts but transcription"
echo "features will be unavailable until the pack is installed."

if [ "$nvidia_available" = true ]; then
    echo ""
    echo "CUDA GPU detected: the [asr-cuda] variant will download GPU-accelerated"
    echo "PyTorch."
elif [ "$apple_silicon" = true ]; then
    echo ""
    echo "Apple Silicon detected: the [asr] variant will download CPU PyTorch"
    echo "(MPS acceleration is available at runtime)."
else
    echo ""
    echo "No CUDA GPU detected: the [asr] variant will download CPU-only PyTorch."
fi

printf '\nInstall the ASR pack now? (y/N) '
read -r answer

# --- install artifice-transcribe ----------------------------------------------

banner "Installing artifice-transcribe"

case "$answer" in
    [Yy]|[Yy][Ee][Ss])
        if [ "$nvidia_available" = true ]; then
            info "GPU (CUDA) install --- this may download ~7 GB"
            uv tool install "artifice-transcribe[asr-cuda]"
        else
            info "CPU install --- this avoids the ~7 GB CUDA runtime"
            uv tool install "artifice-transcribe[asr]"
        fi
        ;;
    *)
        info "Skipping ASR pack.  The server will start but transcription is unavailable."
        if [ "$nvidia_available" = true ]; then
            info "Install later with: uv tool install artifice-transcribe[asr-cuda]"
        else
            info "Install later with: uv tool install artifice-transcribe[asr]"
        fi
        uv tool install artifice-transcribe
        ;;
esac

# --- desktop shortcut ---------------------------------------------------------

banner "Desktop shortcut"

os_type="$(uname -s)"

# Resolve the installed entry-point.  uv tool install places executables in
# the uv tool bin directory (~/.local/bin, or $XDG_BIN_HOME if set), with
# ~/.cargo/bin retained as a fallback for older installs.
entry_point="${XDG_BIN_HOME:-$HOME/.local/bin}/artifice-transcribe"
if [ ! -x "$entry_point" ]; then
    entry_point="$HOME/.cargo/bin/artifice-transcribe"
fi
if [ ! -x "$entry_point" ]; then
    # Fall back to a PATH search.
    entry_point="$(command -v artifice-transcribe 2>/dev/null || true)"
fi

if [ -z "$entry_point" ]; then
    info "WARNING: Could not locate artifice-transcribe entry point."
    info "  Skipping desktop shortcut.  Launch from terminal with: artifice-transcribe"
elif [ "$os_type" = "Linux" ]; then

    # --- Linux: .desktop file -------------------------------------------------
    desktop_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    mkdir -p "$desktop_dir"

    cat > "$desktop_dir/artifice-transcribe.desktop" << DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=Artifice Transcribe
Comment=Speech-to-Text & Diarization
Exec=$entry_point
Terminal=true
Categories=Audio;AudioVideo;
StartupNotify=true
DESKTOP_EOF

    chmod +x "$desktop_dir/artifice-transcribe.desktop"
    info "Created: $desktop_dir/artifice-transcribe.desktop"

    # Attempt to copy to the Desktop as well (XDG Desktop dir).
    desktop_folder="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
    if [ -d "$desktop_folder" ]; then
        cp "$desktop_dir/artifice-transcribe.desktop" "$desktop_folder/"
        info "Copied to: $desktop_folder/artifice-transcribe.desktop"
    fi

elif [ "$os_type" = "Darwin" ]; then

    # --- macOS: .command file on Desktop --------------------------------------
    command_path="$HOME/Desktop/Artifice Transcribe.command"

    cat > "$command_path" << COMMAND_EOF
#!/usr/bin/env bash
# Launch artifice-transcribe
exec "$entry_point"
COMMAND_EOF

    chmod +x "$command_path"
    info "Created: $command_path"
    info "  Double-click it in Finder to launch Artifice Transcribe."

fi

# --- summary ------------------------------------------------------------------

echo ""
echo "==============================================="
echo "  Install complete!"
echo "==============================================="
echo ""
echo "  Launch:  artifice-transcribe"
echo "  Uninstall: uv tool uninstall artifice-transcribe"
echo ""
printf "Press Enter to exit."
read -r
