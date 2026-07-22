#!/usr/bin/env python3
"""Finalize the narrow metadata state required for Batch-87 D0 closure.

This script does not alter architecture substance. It:

- ratifies B87-D0-A4.2 as an approved architecture baseline;
- records that its effective closure condition has been satisfied;
- verifies that the closure decision exists and is accepted;
- verifies that D0-ISSUE-001 is closed;
- supports idempotent check and diff-preview modes.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


A42_PATH = Path(
    "docs/architecture/"
    "B87-D0-A4.2-CONTROLLED-GOVERNANCE-RESILIENCE-EVIDENCE-ISOLATION.md"
)
ISSUE_REGISTER_PATH = Path(
    "docs/architecture/B87-D0-ARCHITECTURE-ISSUE-REGISTER.md"
)
CLOSURE_DECISION_PATH = Path(
    "docs/architecture/B87-D0-CLOSURE-DECISION.md"
)

PENDING_STATUS = "**Status:** Pending validation and closure acceptance"
APPROVED_STATUS = "**Status:** Approved architecture baseline"

PENDING_EFFECTIVE_CONDITION = (
    "**Effective condition:** Becomes an approved architecture baseline upon "
    "successful D0 closure validation and Nolan–Byte acceptance"
)
SATISFIED_EFFECTIVE_CONDITION = (
    "**Effective condition:** Satisfied by B87-D0 closure decision accepted "
    "2026-07-22"
)


@dataclass(frozen=True)
class Change:
    path: Path
    before: str
    after: str

    @property
    def changed(self) -> bool:
        return self.before != self.after


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError(f"Unable to locate repository root from {start}")


def normalise_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_required(repo_root: Path, path: Path) -> str:
    try:
        return normalise_newlines(
            (repo_root / path).read_text(encoding="utf-8-sig")
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required closure file is missing: {path}") from exc


def replace_metadata_line(
    text: str,
    pending: str,
    approved: str,
    label: str,
) -> str:
    """Replace one metadata line and canonicalise its trailing whitespace.

    Markdown source files may use two trailing spaces for a hard line break.
    Closure metadata must not retain those spaces because ``git diff --check``
    correctly reports trailing whitespace on newly changed lines.
    """

    lines = text.splitlines()
    pending_indexes = [
        index for index, line in enumerate(lines) if line.rstrip(" \t") == pending
    ]
    approved_indexes = [
        index for index, line in enumerate(lines) if line.rstrip(" \t") == approved
    ]

    if pending_indexes and approved_indexes:
        raise RuntimeError(
            f"{label} contains both pending and approved forms; manual review required."
        )

    if len(pending_indexes) > 1 or len(approved_indexes) > 1:
        raise RuntimeError(
            f"{label}: expected one metadata line; found "
            f"{len(pending_indexes)} pending and {len(approved_indexes)} approved."
        )

    if pending_indexes:
        lines[pending_indexes[0]] = approved
    elif approved_indexes:
        # Canonicalise an already-finalised line by removing trailing spaces.
        lines[approved_indexes[0]] = approved
    else:
        raise RuntimeError(
            f"{label}: expected exactly one pending or approved value; found none."
        )

    return "\n".join(lines) + "\n"


def verify_closure_inputs(issue_register: str, closure_decision: str) -> None:
    required_issue_literals = [
        "## D0-ISSUE-001 — Controlled testing and defensive-bias risk",
        "**Status:** Closed",
        "**Closed on:** 2026-07-22",
        "**Closure decision:** B87-D0 — Architecture Closure Decision",
    ]
    for literal in required_issue_literals:
        if literal not in issue_register:
            raise RuntimeError(
                f"Issue register is not closure-ready; missing: {literal}"
            )

    required_decision_literals = [
        "# B87-D0 — Architecture Closure Decision",
        "**Status:** Accepted and closed",
        "**Decision date:** 2026-07-22",
        "**Next authorised slice:** B87-I1 — Persistence Kernel",
        "model behavioural efficacy: not yet validated",
    ]
    for literal in required_decision_literals:
        if literal not in closure_decision:
            raise RuntimeError(
                f"Closure decision is not acceptance-ready; missing: {literal}"
            )


def prepare_change(repo_root: Path) -> Change:
    a42 = read_required(repo_root, A42_PATH)
    issue_register = read_required(repo_root, ISSUE_REGISTER_PATH)
    closure_decision = read_required(repo_root, CLOSURE_DECISION_PATH)

    verify_closure_inputs(issue_register, closure_decision)

    after = replace_metadata_line(
        a42,
        PENDING_STATUS,
        APPROVED_STATUS,
        "A4.2 status",
    )
    after = replace_metadata_line(
        after,
        PENDING_EFFECTIVE_CONDITION,
        SATISFIED_EFFECTIVE_CONDITION,
        "A4.2 effective condition",
    )

    if "**Resolves:** D0-ISSUE-001" not in after:
        raise RuntimeError("A4.2 no longer identifies D0-ISSUE-001 as resolved.")

    return Change(
        path=A42_PATH,
        before=a42.rstrip("\n") + "\n",
        after=after.rstrip("\n") + "\n",
    )


def unified_diff(change: Change) -> str:
    return "".join(
        difflib.unified_diff(
            change.before.splitlines(keepends=True),
            change.after.splitlines(keepends=True),
            fromfile=str(change.path),
            tofile=str(change.path),
        )
    )


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 1 when finalisation is still required.",
    )
    parser.add_argument(
        "--show-diff",
        action="store_true",
        help="Print the proposed narrow metadata diff.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = (
        args.repo_root.resolve()
        if args.repo_root
        else find_repo_root(Path.cwd())
    )

    try:
        change = prepare_change(repo_root)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.show_diff and change.changed:
        print(unified_diff(change), end="")

    if not change.changed:
        print("PASS: D0 closure metadata is already finalised.")
        return 0

    if args.check:
        print(f"D0 closure finalisation is required: {change.path}")
        return 1

    path = repo_root / change.path
    path.write_text(change.after, encoding="utf-8", newline="\n")

    print(f"UPDATED: {change.path}")
    print("D0 closure metadata finalised.")
    print(
        "Run scripts/validate_d0_architecture.py --require-closed next."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
