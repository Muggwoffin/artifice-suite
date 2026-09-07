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
REMOTE_ACTION = re.compile(r"(?<![./\w-])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([^\s\"'#]+)")
FULL_COMMIT = re.compile(r"[0-9a-f]{40}")


def _without_yaml_comments(text: str) -> str:
    """Remove comments while preserving hashes inside quoted YAML scalars."""
    cleaned: list[str] = []
    for line in text.splitlines():
        quote: str | None = None
        escaped = False
        for index, char in enumerate(line):
            if escaped:
                escaped = False
                continue
            if char == "\\" and quote == '"':
                escaped = True
            elif char in {'"', "'"}:
                quote = None if quote == char else (char if quote is None else quote)
            elif char == "#" and quote is None:
                line = line[:index]
                break
        cleaned.append(line)
    return "\n".join(cleaned)


def _has_pull_request_target(text: str) -> bool:
    text = _without_yaml_comments(text)
    return re.search(r"(?<![A-Za-z0-9_-])pull_request_target(?![A-Za-z0-9_-])", text) is not None


def _self_test() -> None:
    assert _has_pull_request_target("on:\n  pull_request_target:\n")
    assert _has_pull_request_target("on: [push, pull_request_target]\n")
    assert _has_pull_request_target("on:\n  - pull_request_target\n")
    assert not _has_pull_request_target("on: pull_request\n# pull_request_target is forbidden\n")


def main() -> int:
    _self_test()
    findings: list[str] = []
    for path in sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml"))):
        text = _without_yaml_comments(path.read_text(encoding="utf-8"))
        if _has_pull_request_target(text):
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
