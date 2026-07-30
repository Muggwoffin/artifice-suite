"""Path validation for web endpoints.

Adopted from ``artifice-graph``'s ``_validate_directory`` model, which the
security auditor confirmed sufficient. The same pattern keeps the tool usable
for its actual workflow — an external drive, a departmental share, several
project folders — while refusing paths that should never be reachable from an
unauthenticated HTTP request.

*Not* lifted to a shared module because graph and transcribe already have their
own copies, and the brief explicitly leaves those apps untouched. A third
independent copy is the correct decision when duplicating two already-proven
implementations.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import HTTPException

# On POSIX systems, pathlib treats ``C:/Windows`` as a relative path and
# ``resolve()`` prepends the current working directory, which would place it
# inside an allowed root. Detect the drive-letter prefix so it is rejected
# rather than silently landing inside cwd.
_WIN_DRIVE = re.compile(r"^[A-Za-z]:")


def _normalise(raw: str, field_name: str) -> str:
    """Normalise a raw path string: strip, replace backslashes, and — on
    POSIX — reject Windows absolute paths before they can be misinterpreted
    as relative.  Raises HTTP 400 on rejection."""
    normalised = raw.replace("\\", "/").strip()
    if not normalised:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name}: path must not be empty",
        )
    if os.name == "posix" and _WIN_DRIVE.match(normalised):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{field_name}: path {normalised!r} is not valid on this "
                f"platform"
            ),
        )
    return normalised


def _build_allowed_roots() -> list[Path]:
    """Return the set of directory roots permitted for user-supplied paths.

    Roots are resolved at call time so ``cwd`` reflects the server process at
    the moment of the check, not import time. The env var provides the escape
    hatch for external drives, network shares, and any other location an
    individual installation needs.
    """
    roots: list[Path] = [
        Path.home(),
        Path("/tmp"),
        Path.cwd(),
    ]
    extra = os.environ.get("ARTIFICE_OCR_ALLOWED_ROOTS", "")
    for raw in extra.split(os.pathsep):
        raw = raw.strip()
        if raw:
            roots.append(Path(raw).expanduser().resolve())
    return roots


def validate_directory(raw: str, field_name: str) -> str:
    """Return *raw* as a normalised path string after checking it resides
    within an allowed root directory.  Raises HTTP 400 on rejection.

    Backslashes are normalised to forward slashes before processing so that a
    Windows-style path supplied from a browser is not misinterpreted as a
    single filename on a POSIX server (pathlib does not treat ``\\`` as a
    separator on POSIX, and ``Path("C:\\Windows").resolve()`` would land
    inside the current working directory instead of being rejected).
    """
    normalised_raw = _normalise(raw, field_name)
    try:
        p = Path(normalised_raw).expanduser().resolve(strict=False)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name}: cannot resolve path {raw!r}",
        ) from None

    allowed = _build_allowed_roots()
    for root in allowed:
        resolved_root = root.resolve()
        try:
            relative = p.relative_to(resolved_root)
            break
        except ValueError:
            continue
    else:
        # Deliberately does NOT name the allowed roots, and echoes the caller's
        # own input rather than the resolved path. Both would disclose server
        # filesystem layout — the roots include Path.home(), so listing them
        # hands the OS username to an unauthenticated caller, and echoing the
        # resolved path leaks it too whenever the input was relative.
        raise HTTPException(
            status_code=400,
            detail=(
                f"{field_name}: path {raw!r} is outside the directories this "
                f"server is permitted to access. The operator can widen them "
                f"with the ARTIFICE_OCR_ALLOWED_ROOTS environment variable."
            ),
        )

    # Home is an allowed root, which would otherwise make configuration and
    # key-material directories nameable as an output directory or scan source.
    # Hidden components are checked *below* the matched root rather than across
    # the whole path, so a project that happens to live under a dotted
    # directory is not rendered unusable by its own parent.
    hidden = [
        part for part in relative.parts
        if part.startswith(".") and part not in (".", "..")
    ]
    if hidden:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{field_name}: path {raw!r} descends into a hidden "
                f"directory ({hidden[0]!r}). Choose a visible directory."
            ),
        )
    return str(p)


def validate_contained(raw: str, container: str, field_name: str) -> str:
    """Return *raw* as a normalised path after checking it resolves within
    *container*.  Raises HTTP 400 on rejection.

    Backslashes are normalised to forward slashes (same rationale as
    ``validate_directory``).
    """
    normalised_raw = _normalise(raw, field_name)
    try:
        p = Path(normalised_raw).expanduser().resolve(strict=True)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name}: cannot resolve path {raw!r}",
        ) from None

    base = Path(container).expanduser().resolve()
    try:
        p.relative_to(base)
    except ValueError:
        # Names neither the resolved path nor the container's absolute path;
        # both disclose server filesystem layout to an unauthenticated caller.
        raise HTTPException(
            status_code=400,
            detail=(
                f"{field_name}: path {raw!r} is not within the permitted "
                f"output directory"
            ),
        ) from None

    return str(p)
