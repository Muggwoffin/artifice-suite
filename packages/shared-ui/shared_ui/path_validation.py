# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Library-level path validation.

Core ruleset for validating that a user-supplied path resides within permitted
directories.  Raises ``ValueError`` — no web-framework dependency — so it is
usable from the CLI, background threads, and the web layer alike.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

# On POSIX systems, pathlib treats ``C:/Windows`` as a relative path and
# ``resolve()`` prepends the current working directory, which would place it
# inside an allowed root. Detect the drive-letter prefix so it is rejected
# rather than silently landing inside cwd.
_WIN_DRIVE = re.compile(r"^[A-Za-z]:")


class PathValidationError(ValueError):
    """A user-supplied path failed validation, with a safe public message.

    ``public_message`` is set from a string literal at each raise site — it
    is never derived from a wrapped third-party exception — so a caller can
    read it directly instead of calling ``str(e)``/``repr(e)``, which
    CodeQL's stack-trace-exposure query treats as an information leak
    regardless of whether the message is actually sensitive. Subclasses
    ``ValueError`` so existing ``except ValueError`` call sites keep working
    unchanged.
    """

    def __init__(self, public_message: str) -> None:
        self.public_message = public_message
        super().__init__(public_message)


class OutsideAllowedRootsError(PathValidationError):
    """The path resolved outside every allowed root.

    Split out from :class:`PathValidationError` because at least one caller
    (the OCR web layer) needs to react specifically to this case — e.g. to
    add an app-specific hint about the allowed-roots env var — without
    string-matching the message text.
    """


def normalise_path(raw: str, field_name: str) -> str:
    """Normalise a raw path string: strip, replace backslashes, and — on
    POSIX — reject Windows absolute paths before they can be misinterpreted
    as relative.  Raises :class:`PathValidationError` on rejection."""
    normalised = raw.replace("\\", "/").strip()
    if not normalised:
        raise PathValidationError(f"{field_name}: path must not be empty")
    if os.name == "posix" and _WIN_DRIVE.match(normalised):
        raise PathValidationError(
            f"{field_name}: path {normalised!r} is not valid on this platform"
        )
    return normalised


def build_allowed_roots(env_var: str) -> list[Path]:
    """Return the set of directory roots permitted for user-supplied paths.

    Roots are resolved at call time so ``cwd`` reflects the server process at
    the moment of the check, not import time. The env var provides the escape
    hatch for external drives, network shares, and any other location an
    individual installation needs.
    """
    roots: list[Path] = [
        Path.home(),
        Path(tempfile.gettempdir()),
        Path("/tmp"),
        Path.cwd(),
    ]
    extra = os.environ.get(env_var, "")
    for raw in extra.split(os.pathsep):
        raw = raw.strip()
        if raw:
            roots.append(Path(raw).expanduser().resolve())
    return roots


def validate_path(raw: str, field_name: str, *, allowed_roots_env_var: str) -> str:
    """Return *raw* as a normalised path string after checking it resides
    within an allowed root directory.  Raises ``ValueError`` on rejection.

    Backslashes are normalised to forward slashes before processing so that a
    Windows-style path supplied from outside the web layer is not
    misinterpreted as a single filename on a POSIX server.
    """
    normalised_raw = normalise_path(raw, field_name)
    try:
        p = Path(normalised_raw).expanduser().resolve(strict=False)
    except Exception:
        raise PathValidationError(f"{field_name}: cannot resolve path {raw!r}") from None

    allowed = build_allowed_roots(allowed_roots_env_var)
    for root in allowed:
        resolved_root = root.resolve()
        try:
            relative = p.relative_to(resolved_root)
            break
        except ValueError:
            continue
    else:
        # Does NOT name the allowed roots; they include Path.home().
        raise OutsideAllowedRootsError(
            f"{field_name}: path {raw!r} is outside the directories this "
            f"server is permitted to access"
        )

    # Hidden components are checked *below* the matched root rather than across
    # the whole path, so a project that happens to live under a dotted
    # directory is not rendered unusable by its own parent.
    hidden = [part for part in relative.parts if part.startswith(".") and part not in (".", "..")]
    if hidden:
        raise PathValidationError(
            f"{field_name}: path {raw!r} descends into a hidden "
            f"directory ({hidden[0]!r}). Choose a visible directory."
        )
    return str(p)
