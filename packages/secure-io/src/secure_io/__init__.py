# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Write JSON files with OS-appropriate access controls.

``write_private_json(path, data)`` persists *data* as JSON so that only the
current user can read the file.

- **POSIX**: uses ``os.open(..., 0o600)``, which creates the file with
  restricted permissions atomically — the file is never world-readable.
- **Windows**: creates the file empty, applies an ACL via ``icacls``, verifies
  the ACL, and only then writes the contents.  The file exists empty and
  unprotected between creation and the ACL call, but no secret is exposed
  because the file is still empty during that window.

``restrict_to_current_user(path)`` applies the same restriction to an
**existing** file, which closes the live-defect window for installations that
already have unprotected files on disk.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def write_private_json(path: Path, data: object) -> None:
    """Persist *data* as JSON at *path*, restricting access to the current user.

    The secret never touches an unprotected file:
    - POSIX: mode 0600 is set atomically at creation time via ``os.open(..., 0o600)``.
    - Windows: the file is created empty, the ACL is applied and verified, and
      only then are the contents written.
    """
    if sys.platform == "win32":
        _write_private_json_windows(path, data)
    else:
        _write_private_json_posix(path, data)


def restrict_to_current_user(path: Path) -> None:
    """Restrict *path* so that only the current user can read or write it.

    POSIX: ``os.chmod(path, 0o600)``.
    Windows: strip inherited ACEs and grant the current user's SID read+write.
    """
    if sys.platform == "win32":
        _restrict_windows(path)
    else:
        os.chmod(path, 0o600)
        if not is_restricted(path):
            raise PermissionError(
                f"Failed to restrict permissions on {path}: "
                f"st_mode is {oct(path.stat().st_mode & 0o777)}"
            )


def is_restricted(path: Path) -> bool:
    """Return ``True`` if *path* is readable/writable only by the current user.

    POSIX: checks ``st_mode & 0o777 == 0o600``.
    Windows: verifies via ``icacls`` that the ACL grants the current user
    read+write access and no other accounts appear.
    """
    if not path.exists():
        return False
    if sys.platform == "win32":
        return _is_restricted_windows(path)
    else:
        return (path.stat().st_mode & 0o777) == 0o600


# ---------------------------------------------------------------------------
# POSIX implementation
# ---------------------------------------------------------------------------


def _write_private_json_posix(path: Path, data: object) -> None:
    """Create the file with mode 0600, then write atomically."""
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Windows implementation
# ---------------------------------------------------------------------------


def _write_private_json_windows(path: Path, data: object) -> None:
    """Create empty file, apply ACL, verify, then write.

    The file exists empty and unprotected between its creation and the ACL
    application — no secret is exposed during that window because the file is
    still empty.
    """
    # Create an empty file first.
    fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
    os.close(fd)
    try:
        _restrict_windows(path)
    except Exception:
        # If we cannot protect the file, remove the empty file we created
        # and fail loudly.  Silently writing a plaintext secret is exactly
        # the bug being fixed here, so a hard failure is the intended
        # trade-off.  (A filesystem without ACL support, such as exFAT,
        # will hit this.)
        with contextlib.suppress(OSError):
            path.unlink()
        raise
    _write_json(path, data)


def _restrict_windows(path: Path) -> None:
    """Apply a restrictive ACL to *path* on Windows.

    Uses ``icacls`` (ships with Windows) to strip inherited ACEs and grant
    the current user read+write access.  The user is addressed by SID, not
    username, so the ACL works on non-English Windows installs.
    """
    sid = _get_current_user_sid()
    _run_icacls(
        path,
        [
            "/inheritance:r",
            "/grant:r",
            f"*{sid}:(R,W)",
        ],
    )
    # Verify the ACL took effect before returning.
    if not _is_restricted_windows(path):
        raise PermissionError(
            f"Failed to verify ACL on {path} — the file may still be unprotected"
        )


def _is_restricted_windows(path: Path) -> bool:
    """Check the ACL on *path* using ``icacls``.

    Returns ``True`` when:
    - The ACL contains no inherited entries (no ``(I)`` markers).
    - Exactly one explicit ACE exists.
    - That ACE grants both Read and Write access.
    """
    try:
        result = subprocess.run(
            ["icacls", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    output = result.stdout
    # Inherited ACEs carry an ``(I)`` marker.  We stripped inheritance, so
    # none should remain.
    if "(I)" in output:
        return False
    # Count explicit ACEs — patterns like ``:(R,W)`` or ``:(F)``.
    ace_matches = re.findall(r":\(([A-Z,]+)\)", output)
    if len(ace_matches) != 1:
        return False
    perms = ace_matches[0]
    return "R" in perms and "W" in perms


def _get_current_user_sid() -> str:
    """Return the current user's SID string (``S-1-5-...``).

    Uses ``whoami /user``, which is built into every supported Windows version.
    """
    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        check=True,
    )
    # Output format:  "DOMAIN\\username","S-1-5-21-..."
    parts = result.stdout.strip().rsplit(",", 1)
    if len(parts) < 2:
        raise RuntimeError(f"Unexpected whoami output: {result.stdout!r}")
    sid = parts[-1].strip().strip('"')
    if not sid.startswith("S-1-"):
        raise RuntimeError(f"Unexpected SID format from whoami: {sid!r}")
    return sid


def _run_icacls(path: Path, args: list[str]) -> None:
    """Run ``icacls`` with *args* and raise on failure."""
    subprocess.run(
        ["icacls", str(path)] + args,
        capture_output=True,
        text=True,
        check=True,
    )


def _write_json(path: Path, data: object) -> None:
    """Write *data* as JSON to *path* (no permission handling)."""
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
