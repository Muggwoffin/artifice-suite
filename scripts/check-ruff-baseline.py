# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Ruff baseline gate: fail CI only on NEW violations.

The tree carries a pre-existing ruff backlog (731 violations when the baseline
was first generated).  A hard `ruff check` gate would be red forever, so this
script instead compares the current violation multiset — keyed by
``<file>|<code>`` — against a committed baseline and fails only when a new
(file, code) pair appears or an existing count increases.  Reductions are
always allowed.

    uv run python scripts/check-ruff-baseline.py            # check (CI gate)
    uv run python scripts/check-ruff-baseline.py --generate # refresh baseline

NOTE: `ruff check` exits 1 when it finds violations, so a non-zero return code
is EXPECTED here and must not be treated as a fatal error.  Only a JSON parse
failure or an unexpected return code (not 0/1) is a real failure.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "scripts" / "ruff-baseline.json"
RUFF_CMD = ["uv", "run", "ruff", "check", ".", "--output-format=json"]


def _normalise_filename(filename: str) -> str:
    """Return a repo-relative Ruff filename when possible."""
    path = Path(filename)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _run_ruff() -> list[dict]:
    """Run ruff, returning parsed JSON.  Accepts exit codes 0 and 1 (both mean
    "ruff ran fine"; 1 merely means violations exist)."""
    result = subprocess.run(
        RUFF_CMD, capture_output=True, text=True, cwd=REPO_ROOT
    )
    if result.returncode not in (0, 1):
        print(
            f"ruff exited {result.returncode} (unexpected); stderr:\n{result.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"Could not parse ruff JSON output: {exc}", file=sys.stderr)
        sys.exit(1)


def _counts(violations: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for violation in violations:
        # ruff's JSON schema uses `filename`, not `file`.
        key = f"{_normalise_filename(violation['filename'])}|{violation['code']}"
        counts[key] += 1
    return dict(counts)


def generate_baseline() -> None:
    """Snapshot the current tree's violations into the committed baseline."""
    counts = _counts(_run_ruff())
    baseline = {
        "_generated": datetime.now().isoformat(timespec="seconds"),
        "violations": counts,
    }
    BASELINE_PATH.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    print(f"Generated baseline with {len(counts)} (file|code) entries at {BASELINE_PATH}")
    for key, count in sorted(counts.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {key}: {count}")


def check_baseline() -> None:
    """Compare current violations against the committed baseline."""
    if not BASELINE_PATH.exists():
        print(
            f"No baseline at {BASELINE_PATH}; run with --generate first.",
            file=sys.stderr,
        )
        sys.exit(1)
    baseline = json.loads(BASELINE_PATH.read_text())
    current = _counts(_run_ruff())

    new = {k: v for k, v in current.items() if k not in baseline["violations"]}
    increased = {
        k: (baseline["violations"][k], v)
        for k, v in current.items()
        if k in baseline["violations"] and v > baseline["violations"][k]
    }

    if not new and not increased:
        print("baseline OK — no new ruff violations")
        sys.exit(0)

    print(
        f"{len(new) + len(increased)} new/increased violations vs baseline",
        file=sys.stderr,
    )
    if new:
        print("New violations:", file=sys.stderr)
        for key, count in sorted(new.items()):
            print(f"  {key}: {count}", file=sys.stderr)
    if increased:
        print("Increased violations:", file=sys.stderr)
        for key, (before, after) in sorted(increased.items()):
            print(f"  {key}: {before} → {after}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--generate":
        generate_baseline()
    else:
        check_baseline()


if __name__ == "__main__":
    main()
