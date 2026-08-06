# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later

"""PyPI publication-readiness gate for the Artifice Suite.

Builds every publishable distribution and inspects the BUILT ARTIFACT, not the
source tree.  That distinction is the whole point: this repo has shipped (or
nearly shipped) four packaging bugs that no test could reach, because tests run
against ``src/`` while the defect exists only in the wheel.

Checks, per distribution:

  1. The wheel builds at all.
  2. Core metadata is present: Name, Version, Summary, Requires-Python,
     License-Expression (PEP 639).  These are FAIL-level: a missing field
     causes a non-zero exit.
  3. **No workspace path leaks into Requires-Dist.**  Every app depends on
     ``artifice-model-harness`` and friends, which uv resolves from the local
     workspace via ``[tool.uv.sources]``.  If a ``file://`` or path-style
     requirement reaches the published metadata, the package installs on this
     machine and nowhere else.
  4. The README referenced by ``readme =`` is actually embedded, so the PyPI
     project page is not blank.
  5. Declared package data (templates, static assets, fonts) is **noted** in
     the output so a human can confirm presence; absence is not a FAIL.

Description-Content-Type is a **WARN**, not a FAIL: missing it means PyPI may
not render the README as Markdown, but the install will still succeed.

Exits non-zero if any FAIL-level check fails.  Warnings do not gate.

Usage:  uv run python scripts/check-pypi-readiness.py [--no-build]
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from email.parser import Parser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every distribution intended for PyPI.  The three shared packages MUST be
# published before the four apps, because each app declares them by name.
SHARED_PACKAGES = [
    REPO_ROOT / "packages" / "model-harness",
    REPO_ROOT / "packages" / "secure-io",
    REPO_ROOT / "packages" / "shared-ui",
]
APPS = [
    REPO_ROOT / "apps" / "artifice-ocr",
    REPO_ROOT / "apps" / "artifice-draft",
    REPO_ROOT / "apps" / "artifice-graph",
    REPO_ROOT / "apps" / "artifice-transcribe",
]
ALL_DISTS = SHARED_PACKAGES + APPS

# A requirement that points at a filesystem location rather than a name.
# Matches Unix-style paths (file://, @ /…, ../) and Windows-style absolute or
# relative paths (@ C:\…, @ D:/…, ..\).
_PATH_REQUIREMENT = re.compile(
    r"(file://|@\s*/|\.\./|\bfile:|@\s*[A-Za-z]:[/\\]|\.\.[\\/])",
    re.IGNORECASE,
)


class Result:
    def __init__(self, name: str) -> None:
        self.name = name
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def fail(self, msg: str) -> None:
        self.failures.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.info.append(msg)


def build_wheel(dist_dir: Path) -> Path | None:
    """Clean-build a wheel.  build/ is cleared first because setuptools reuses
    whatever it finds there, which resurrects deleted modules into new wheels."""
    for stale in ("build", "dist"):
        target = dist_dir / stale
        if target.exists():
            shutil.rmtree(target)

    proc = subprocess.run(
        ["uv", "run", "--with", "build", "python", "-m", "build", "--wheel"],
        cwd=dist_dir,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-6:]
        print("    build failed:\n      " + "\n      ".join(tail))
        return None

    wheels = sorted((dist_dir / "dist").glob("*.whl"))
    return wheels[0] if wheels else None


def inspect(wheel: Path, dist_dir: Path) -> Result:
    result = Result(dist_dir.name)

    # unzip is not installed in this environment; zipfile is the way in.
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        meta_name = next((n for n in names if n.endswith(".dist-info/METADATA")), None)
        if meta_name is None:
            result.fail("wheel contains no METADATA")
            return result
        metadata = Parser().parsestr(zf.read(meta_name).decode("utf-8"))
        payload = metadata.get_payload()

    name = metadata.get("Name")
    version = metadata.get("Version")
    result.note(f"{name} {version}  ({wheel.name})")

    for field in ("Name", "Version", "Summary", "Requires-Python"):
        if not metadata.get(field):
            result.fail(f"missing {field}")

    # PEP 639.  A License:: classifier alongside a license expression makes
    # setuptools reject the build outright, so its absence is required, not
    # optional.
    if not metadata.get("License-Expression"):
        result.fail("missing License-Expression (PEP 639)")
    if any(c.startswith("License ::") for c in metadata.get_all("Classifier") or []):
        result.fail("License :: classifier present alongside a license expression")

    if not metadata.get("Description-Content-Type"):
        result.warn("no Description-Content-Type — PyPI may not render the README")
    if not payload.strip():
        result.fail("README/long description is empty — PyPI page would be blank")

    # The bug that would break every install from PyPI.
    for req in metadata.get_all("Requires-Dist") or []:
        if _PATH_REQUIREMENT.search(req):
            result.fail(f"path-based requirement leaked into metadata: {req!r}")

    if not (metadata.get_all("Classifier") or []):
        result.warn("no classifiers — the project will be hard to find on PyPI")
    if not metadata.get("Author") and not metadata.get("Author-email"):
        result.warn("no Author/Author-email")
    if not (metadata.get_all("Project-URL") or []):
        result.warn("no Project-URL entries")

    return result


def check_package_data(wheel: Path, result: Result) -> None:
    """Assets outside the installable package are excluded from a wheel and can
    then only be found by a CWD-relative path, which breaks the moment the
    server starts from anywhere else."""
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()

    for suffix, label in ((".html", "templates"), (".css", "stylesheets")):
        if any(n.endswith(suffix) for n in names):
            result.note(f"{label} present in wheel")


def main() -> None:
    build = "--no-build" not in sys.argv

    print("\nPyPI Readiness Report")
    print("=====================")
    print("\nPublish order matters: the three shared packages must land on PyPI")
    print("BEFORE the four apps, because every app declares them by name.\n")

    results: list[Result] = []
    for dist_dir in ALL_DISTS:
        print(f"  building {dist_dir.name} ...")
        if build:
            wheel = build_wheel(dist_dir)
        else:
            wheels = sorted((dist_dir / "dist").glob("*.whl"))
            wheel = wheels[0] if wheels else None

        if wheel is None:
            r = Result(dist_dir.name)
            r.fail("no wheel produced")
            results.append(r)
            continue

        r = inspect(wheel, dist_dir)
        check_package_data(wheel, r)
        results.append(r)

    print("\n" + "-" * 62)
    failed = 0
    for r in results:
        status = "FAIL" if r.failures else ("WARN" if r.warnings else "OK")
        print(f"\n[{status}] {r.name}")
        for line in r.info:
            print(f"    - {line}")
        for line in r.failures:
            print(f"    FAIL: {line}")
        for line in r.warnings:
            print(f"    warn: {line}")
        if r.failures:
            failed += 1

    print("\n" + "-" * 62)
    print(f"\n{len(results)} distributions checked, {failed} with failures")
    print(f"\nStatus: {'FAIL' if failed else 'PASS'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
