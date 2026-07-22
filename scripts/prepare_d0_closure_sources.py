#!/usr/bin/env python3
"""Prepare the Batch-87 D0 source documents for final closure validation.

The script performs narrow, idempotent edits:

- normalises Markdown heading hierarchy to one H1 per architecture document;
- adds the A4.2 discoverability reference to A2;
- adds the A4.2 discoverability reference to A3;
- ratifies A3.1 as an approved architecture baseline.

It does not approve A4.2, close D0-ISSUE-001, create the closure decision, or
implement runtime code. Those remain Nolan–Byte acceptance actions after
validation.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


A2_PATH = Path("docs/architecture/B87-D0-A2-MEMORY-CONTRACTS-AND-TAXONOMY.md")
A3_PATH = Path("docs/architecture/B87-D0-A3-PERSISTENCE-AND-PROTOCOL-ARCHITECTURE.md")
A31_PATH = Path("docs/architecture/B87-D0-A3.1-BYTE-PERSPECTIVE-HOW-WORK-GETS-DONE.md")
A41_PATH = Path("docs/architecture/B87-D0-A4.1-CONTROLLED-GOVERNANCE-RESILIENCE-TESTING.md")

A3_ANCHOR = "## 34. Acceptance Criteria"
A42_REFERENCE = "B87-D0-A4.2"

A2_SECTION = """## 31.1. Controlled Governance Resilience Evidence

Raw Controlled Governance Resilience evidence is governed by:

> **B87-D0-A4.2 — Controlled Governance Resilience Evidence Isolation**

This evidence is classified as restricted and evaluation-only.

It is prohibited from:

- ordinary memory;
- ordinary developmental retrieval;
- identity;
- training during B87-S1.

A4.2 supplies the narrower governing rule where a general A2 evidence,
evaluation, retrieval, identity, or training contract would otherwise permit
broader treatment.

---

"""

A3_SECTION = """## 33.1. Controlled Governance Resilience Persistence

Persistence and runtime treatment of Controlled Governance Resilience evidence
is governed by:

> **B87-D0-A4.2 — Controlled Governance Resilience Evidence Isolation**

A4.2 defines the required:

- dedicated persistence mapping;
- immutable eligibility restrictions;
- ordinary-retrieval exclusion;
- explicit evaluation-only retrieval path;
- context-manifest enforcement;
- recovery-context isolation;
- identity-link rejection;
- training-export exclusion;
- audit requirements;
- deterministic isolation tests.

Where a general A3 persistence, retrieval, context, or audit rule would permit
broader handling, A4.2 supplies the narrower rule for this evidence class.

---

"""


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


def _collect_headings(lines: list[str]) -> list[tuple[int, int]]:
    inside_fence = False
    fence_marker: str | None = None
    headings: list[tuple[int, int]] = []

    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not inside_fence:
                inside_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                inside_fence = False
                fence_marker = None
            continue

        if inside_fence or not line.startswith("#"):
            continue

        prefix = line.split(" ", 1)[0]
        if 1 <= len(prefix) <= 6 and set(prefix) == {"#"}:
            headings.append((index, len(prefix)))

    return headings


def _set_heading_level(line: str, level: int) -> str:
    if not 1 <= level <= 6:
        raise RuntimeError(f"Invalid target heading level: H{level}")
    _, separator, title = line.partition(" ")
    if not separator:
        raise RuntimeError(f"Malformed heading: {line!r}")
    return f"{'#' * level} {title}"


def normalise_heading_hierarchy(text: str) -> str:
    """Ensure one H1 and remove heading jumps outside fenced code blocks.

    The function supports the two legacy layouts in the D0 corpus:

    - documents whose major sections were additional H1 headings;
    - documents whose major sections begin at H3/H4 beneath one H1 title.
    """

    lines = normalise_newlines(text).splitlines()
    if not lines or not lines[0].startswith("# "):
        raise RuntimeError("The first line must be the approved H1 title.")

    headings = _collect_headings(lines)
    if not headings or headings[0] != (0, 1):
        raise RuntimeError("The approved H1 title must be the first heading.")

    output = list(lines)
    following = headings[1:]
    if not following:
        return "\n".join(output).rstrip("\n") + "\n"

    if any(level == 1 for _, level in following):
        shift = 1
    else:
        minimum_level = min(level for _, level in following)
        shift = -(minimum_level - 2) if minimum_level > 2 else 0

    shifted: list[tuple[int, int]] = [(0, 1)]
    for index, level in following:
        target = level + shift
        if not 2 <= target <= 6:
            raise RuntimeError(
                f"Cannot safely normalise heading at line {index + 1}: H{level} -> H{target}."
            )
        shifted.append((index, target))

    previous_level = 1
    repaired: list[tuple[int, int]] = [(0, 1)]
    for index, level in shifted[1:]:
        target = min(level, previous_level + 1)
        if target < 2:
            target = 2
        repaired.append((index, target))
        previous_level = target

    for index, level in repaired[1:]:
        output[index] = _set_heading_level(output[index], level)

    result = "\n".join(output).rstrip("\n") + "\n"
    final_headings = _collect_headings(result.splitlines())
    h1_count = sum(1 for _, level in final_headings if level == 1)
    if h1_count != 1:
        raise RuntimeError(f"Heading normalisation produced {h1_count} H1 headings.")

    previous_level = 0
    for index, level in final_headings:
        if previous_level and level > previous_level + 1:
            raise RuntimeError(
                f"Heading jump remains at line {index + 1}: H{previous_level} -> H{level}."
            )
        previous_level = level

    return result


def insert_before_anchor(text: str, *, anchor: str, section: str, label: str) -> str:
    if A42_REFERENCE in text:
        return text

    occurrences = text.count(anchor)
    if occurrences != 1:
        raise RuntimeError(
            f"{label}: expected exactly one anchor {anchor!r}; found {occurrences}."
        )

    return text.replace(anchor, section + anchor, 1)


def ratify_a31(text: str) -> str:
    proposed = "**Status:** Proposed baseline for Nolan approval"
    approved = "**Status:** Approved architecture baseline"

    if approved in text:
        return text
    if proposed not in text:
        raise RuntimeError("A3.1 has an unrecognised status; manual review required.")
    return text.replace(proposed, approved, 1)


def prepare_changes(repo_root: Path) -> list[Change]:
    paths = [A2_PATH, A3_PATH, A31_PATH, A41_PATH]
    contents: dict[Path, str] = {}

    for relative_path in paths:
        path = repo_root / relative_path
        try:
            contents[relative_path] = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError as exc:
            raise RuntimeError(f"Required document is missing: {relative_path}") from exc

    a2_after = normalise_heading_hierarchy(contents[A2_PATH])
    a2_after = insert_before_anchor(
        a2_after,
        anchor="## 32. Implementation Boundary",
        section=A2_SECTION,
        label="A2",
    )

    a3_after = normalise_heading_hierarchy(contents[A3_PATH])
    a3_after = insert_before_anchor(
        a3_after,
        anchor=A3_ANCHOR,
        section=A3_SECTION,
        label="A3",
    )

    a31_after = ratify_a31(normalise_heading_hierarchy(contents[A31_PATH]))
    a41_after = normalise_heading_hierarchy(contents[A41_PATH])

    return [
        Change(A2_PATH, normalise_newlines(contents[A2_PATH]), a2_after),
        Change(A3_PATH, normalise_newlines(contents[A3_PATH]), a3_after),
        Change(A31_PATH, normalise_newlines(contents[A31_PATH]), a31_after),
        Change(A41_PATH, normalise_newlines(contents[A41_PATH]), a41_after),
    ]


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
        help="Do not write; exit 1 when source preparation changes are required.",
    )
    parser.add_argument(
        "--show-diff",
        action="store_true",
        help="Print the proposed unified diff.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root(Path.cwd())

    try:
        changes = prepare_changes(repo_root)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    pending = [change for change in changes if change.changed]

    if args.show_diff:
        for change in pending:
            print(unified_diff(change), end="")

    if not pending:
        print("PASS: D0 source documents are already prepared for closure validation.")
        return 0

    if args.check:
        print("D0 source preparation is required:")
        for change in pending:
            print(f"  - {change.path}")
        return 1

    for change in pending:
        path = repo_root / change.path
        path.write_text(change.after, encoding="utf-8", newline="\n")
        print(f"UPDATED: {change.path}")

    print("D0 source preparation completed.")
    print("Run scripts/validate_d0_architecture.py next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
