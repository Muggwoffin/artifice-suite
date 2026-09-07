#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Reject mutable third-party Actions and unsafe privileged PR triggers."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"
REMOTE_ACTION = re.compile(r"^\s*-?\s*uses:\s*([^./\s][^\s@]+)@([^\s#]+)", re.MULTILINE)
FULL_COMMIT = re.compile(r"[0-9a-f]{40}")


def main() -> int:
    findings: list[str] = []
    for path in sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml"))):
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\s*pull_request_target\s*:", text, re.MULTILINE):
            findings.append(f"{path.relative_to(REPO)}: pull_request_target is forbidden")
        for match in REMOTE_ACTION.finditer(text):
            action, revision = match.groups()
            if not FULL_COMMIT.fullmatch(revision):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    f"{path.relative_to(REPO)}:{line}: {action}@{revision} is mutable; "
                    "pin it to a full commit SHA"
                )

    if findings:
        print(f"workflow-security: {len(findings)} violation(s)")
        print("\n".join(findings))
        return 1
    print("workflow-security: all third-party actions use immutable commits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
