# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Dependency audit gate for the Artifice Suite.

Supply-chain gate for generated code.  Fails CI when a Python file imports a
package that:

  1. does not exist / is not installed / is not declared / is not locked
     (GHOST import — the hallucinated-package failure mode), or
  2. is installed only transitively and never declared in any pyproject.toml
     (UNDECLARED import — a portability bug that breaks a clean machine), or
  3. is declared but the lockfile does not resolve it (lockfile drift).

Import-name -> distribution-name mapping (PIL->pillow, yaml->PyYAML,
bs4->beautifulsoup4, pyannote->pyannote-audio) is resolved via
`importlib.metadata.packages_distributions()` so a declared dependency is
recognised under its real distribution name.  That only works for packages
that are INSTALLED, so `IMPORT_ROOT_TO_DIST` below covers the ones CI does
not install — see the comment there.

Warnings (exit 0): declared-but-never-imported deps and dynamic imports
(`importlib.import_module("literal")` / `__import__("literal")`).
"""

import ast
import re
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

EXCLUDE_DIRS = {
    ".venv",
    "build",
    "dist",
    ".git",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
}

# Intra-repo packages: never ghost suspects.
WORKSPACE_PACKAGES = {
    "artifice_ocr",
    "artifice_draft",
    "artifice_graph",
    "artifice_transcribe",
    "model_harness",
    "secure_io",
    "shared_ui",
}

# pytest infrastructure, not a real package: `from conftest import ...` works
# because pytest inserts the test directory on sys.path.  Never a ghost.
PYTEST_INTERNAL = {"conftest"}

# Import root -> distribution name, for packages whose import root differs
# from the name they are declared under.
#
# `packages_distributions()` derives this automatically, but ONLY for packages
# installed in the environment running this script.  An optional dependency
# that the lint job does not install therefore has no entry, and the
# not-installed fallback below can only compare the import root against
# distribution names — a comparison that cannot succeed when the two differ.
# The result is a FALSE ghost: correctly declared, correctly locked, reported
# as hallucinated.
#
# `pyannote.audio` is exactly that case.  It is declared under
# artifice-transcribe's `asr` / `asr-cuda` extras, which `--extra all` does
# not pull in (the root `all` extra deliberately omits the ~2 GB ASR stack),
# so CI resolves it in uv.lock but never installs it.
#
# Entries here are NOT exemptions: the mapped distribution still has to appear
# in a pyproject.toml or uv.lock to pass.  This only teaches the fallback the
# name to look for.
IMPORT_ROOT_TO_DIST = {
    "pyannote": "pyannote-audio",
}


def normalize_package_name(name: str) -> str:
    """PEP 503 normalisation: lowercase, runs of [-_.] -> '-'."""
    return re.sub(r"[-_.]+", "-", name).lower()


def normalize_import_name(name: str) -> str:
    """Import-name normalisation: lowercase, dashes/dots -> underscores."""
    return re.sub(r"[-.]+", "_", name).lower()


def split_spec(spec: str) -> str:
    """Return the bare distribution name from a PEP 508 requirement string."""
    name = re.split(r"[<>=~!;\[ ]", spec, maxsplit=1)[0].strip()
    return name


def get_imported_modules(file_path: Path) -> tuple[set[str], set[str]]:
    """Return (imported module roots, dynamic-import literals) for a file."""
    with open(file_path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=str(file_path))

    imported: set[str] = set()
    dynamic: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import — intra-package
            if node.module:
                imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            func = node.func
            is_dynamic = (
                isinstance(func, ast.Name) and func.id in ("__import__", "import_module")
            ) or (isinstance(func, ast.Attribute) and func.attr == "import_module")
            if is_dynamic:
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        dynamic.add(arg.value.split(".")[0])
    return imported, dynamic


def get_declared_dependencies(pyproject_path: Path) -> set[str]:
    """Collect normalised distribution names from a pyproject.toml."""
    with open(pyproject_path, "rb") as fh:
        data = tomllib.load(fh)

    deps: set[str] = set()
    project = data.get("project", {})
    specs = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        specs += list(group)
    for group in data.get("dependency-groups", {}).values():
        for dep in group:
            if isinstance(dep, dict):
                dep = dep.get("include-dist") or dep.get("include-group") or ""
            if isinstance(dep, str) and dep.strip():
                specs.append(dep)
    for spec in specs:
        name = normalize_package_name(split_spec(spec))
        if name:
            deps.add(name)
    return deps


def get_locked_packages(lockfile_path: Path) -> set[str]:
    """Extract normalised package names from uv.lock."""
    packages: set[str] = set()
    with open(lockfile_path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("name = "):
                name = line.split("=", 1)[1].strip().strip('"')
                packages.add(normalize_package_name(name))
    return packages


def main() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    stdlib = set(sys.stdlib_module_names)

    python_files = [
        p for p in root_dir.rglob("*.py") if not any(part in EXCLUDE_DIRS for part in p.parts)
    ]

    imported: set[str] = set()
    dynamic: set[str] = set()
    module_to_files: dict[str, set[str]] = {}
    for file_path in python_files:
        mods, dyn = get_imported_modules(file_path)
        imported.update(mods)
        dynamic.update(dyn)
        for m in mods:
            module_to_files.setdefault(m, set()).add(str(file_path.relative_to(root_dir)))

    third_party = imported - stdlib - WORKSPACE_PACKAGES - PYTEST_INTERNAL

    declared: set[str] = set()
    for pp in root_dir.rglob("pyproject.toml"):
        if not any(part in EXCLUDE_DIRS for part in pp.parts):
            declared.update(get_declared_dependencies(pp))

    lockfile = root_dir / "uv.lock"
    locked = get_locked_packages(lockfile) if lockfile.exists() else set()

    try:
        import_to_dist = packages_distributions()
    except Exception:  # noqa: BLE001
        import_to_dist = {}

    # import-name -> normalised distribution names
    import_to_dists = {
        normalize_import_name(k): {normalize_package_name(d) for d in v}
        for k, v in import_to_dist.items()
    }

    ghost: set[str] = set()
    undeclared: set[str] = set()
    for module in third_party:
        dists = import_to_dists.get(normalize_import_name(module), set())
        if dists:
            # present in env — is it declared under any of its dist names?
            if not any(d in declared for d in dists):
                undeclared.add(module)
        else:
            # Not installed, so packages_distributions() cannot tell us the
            # distribution name.  Try the import root itself, then the known
            # alias — a declared-but-uninstalled dep is not a ghost.
            candidates = {normalize_package_name(module)}
            alias = IMPORT_ROOT_TO_DIST.get(normalize_import_name(module))
            if alias:
                candidates.add(normalize_package_name(alias))
            if not any(c in declared or c in locked for c in candidates):
                # no distribution anywhere: prime hallucinated-package suspect
                ghost.add(module)

    declared_but_not_locked = declared - locked

    # dist -> import names (for the unused-dep warning)
    dist_to_imports: dict[str, set[str]] = {}
    for imp_name, dists in import_to_dists.items():
        for d in dists:
            dist_to_imports.setdefault(d, set()).add(imp_name)
    # Normalise for the comparison: third_party holds raw import roots (e.g.
    # "PIL") while dist_to_imports keys are normalised ("pil").
    third_party_norm = {normalize_import_name(m) for m in third_party}
    declared_but_not_imported = {
        d
        for d in declared
        if d in dist_to_imports
        and d not in {normalize_package_name(w) for w in WORKSPACE_PACKAGES}
        and not any(i in third_party_norm for i in dist_to_imports[d])
    }

    exit_code = 1 if (ghost or undeclared or declared_but_not_locked) else 0

    print("\nDependency Audit Report")
    print("=======================")

    print(f"\nGhost imports (FAIL): {len(ghost)}")
    for module in sorted(ghost):
        print(f"  - {module}")
        for f in sorted(module_to_files.get(module, set())):
            print(f"      {f}")

    print(f"\nUndeclared imports (FAIL): {len(undeclared)}")
    for module in sorted(undeclared):
        print(f"  - {module}")
        for f in sorted(module_to_files.get(module, set())):
            print(f"      {f}")

    print(f"\nDeclared but not in uv.lock (FAIL): {len(declared_but_not_locked)}")
    for module in sorted(declared_but_not_locked):
        print(f"  - {module}")

    print(f"\nDeclared but never imported (WARN): {len(declared_but_not_imported)}")
    for module in sorted(declared_but_not_imported):
        print(f"  - {module}")

    print(f"\nDynamic imports (WARN): {len(dynamic)}")
    for module in sorted(dynamic):
        print(f"  - {module}")

    print(f"\nStatus: {'FAIL' if exit_code else 'PASS'}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
