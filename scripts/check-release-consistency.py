# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later

import argparse
import pathlib
import sys
from collections import defaultdict

try:
    import tomllib
    HAS_TOMLLIB = True
except ImportError:
    HAS_TOMLLIB = False

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

def parse_pyproject(file_path):
    if not HAS_TOMLLIB:
        raise RuntimeError("tomllib not available; cannot parse TOML")
    
    with open(file_path, "rb") as f:
        data = tomllib.load(f)
    
    return data.get("project", {}).get("version", "")


def parse_citation_cff(file_path):
    if HAS_YAML:
        with open(file_path) as f:
            data = yaml.safe_load(f)
        return data.get("version", ""), data.get("date-released")
    else:
        # Fallback regex approach
        import re
        with open(file_path) as f:
            content = f.read()
        
        version_match = re.search(r"^version:\s*([^\n]+)", content, re.MULTILINE)
        if not version_match:
            raise ValueError("Could not find version in CITATION.cff")
        
        version = version_match.group(1).strip("'\" ")
        date_match = re.search(r"^date-released:\s*([^\n]+)", content, re.MULTILINE)
        date_released = date_match.group(1).strip("'\" ") if date_match else None
        
        return version, date_released

def main():
    parser = argparse.ArgumentParser(
        description="Check version consistency across pyproject.toml and CITATION.cff"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--expect-equal", action="store_true", help="Check all versions are equal")
    group.add_argument("--expected", type=str, help="Check all versions equal this value")
    
    args = parser.parse_args()
    
    # Discover pyproject.toml files: the root one, plus every app and package.
    # Scoped on purpose — a blind "**" glob could pick up stray pyproject.toml
    # files inside .venv/, dist/ or build/ trees.
    root_dir = pathlib.Path(__file__).parent.parent
    pyproject_files = [root_dir / "pyproject.toml"]
    pyproject_files += sorted((root_dir / "apps").glob("*/pyproject.toml"))
    pyproject_files += sorted((root_dir / "packages").glob("*/pyproject.toml"))
    
    # Parse pyproject.toml files
    versions = defaultdict(list)
    for file_path in pyproject_files:
        try:
            version = parse_pyproject(file_path)
            versions[version].append(file_path)
        except Exception as e:
            print(f"Error parsing {file_path}: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Parse CITATION.cff
    citation_path = root_dir / "CITATION.cff"
    try:
        citation_version, date_released = parse_citation_cff(citation_path)
        versions[citation_version].append(citation_path)
    except Exception as e:
        print(f"Error parsing {citation_path}: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Print version table
    print("Version consistency report:")
    for version, files in sorted(versions.items()):
        print(f"{version}: {len(files)} files")
        for file_path in sorted(files):
            print(f"  - {file_path}")
    
    # Check conditions
    if args.expect_equal:
        if len(versions) == 1:
            print("All versions are equal")
            sys.exit(0)
        else:
            print("Version mismatch detected", file=sys.stderr)
            sys.exit(1)
    elif args.expected:
        expected_version = args.expected.lstrip("v")
        if len(versions) == 1 and expected_version in versions:
            print(f"All versions match expected {expected_version}")
            sys.exit(0)
        else:
            print(
                f"Version mismatch detected (expected {expected_version})",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        # Default to --expect-equal
        if len(versions) == 1:
            print("All versions are equal")
            sys.exit(0)
        else:
            print("Version mismatch detected", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
