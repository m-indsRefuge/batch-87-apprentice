from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FINALIZER_PATH = REPO_ROOT / "scripts" / "finalize_d0_closure.py"


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


finalizer = load_module("finalize_d0_closure", FINALIZER_PATH)


def write_fixture_repo(root: Path) -> None:
    (root / "docs" / "architecture").mkdir(parents=True)

    (root / finalizer.A42_PATH).write_text(
        "\n".join(
            [
                "# B87-D0-A4.2 — Controlled Governance Resilience Evidence Isolation",
                "",
                finalizer.PENDING_STATUS + "  ",
                "**Resolves:** D0-ISSUE-001",
                finalizer.PENDING_EFFECTIVE_CONDITION + "  ",
                "",
            ]
        ),
        encoding="utf-8",
    )

    (root / finalizer.ISSUE_REGISTER_PATH).write_text(
        "\n".join(
            [
                "# B87-D0 — Architecture Issue Register",
                "",
                "## D0-ISSUE-001 — Controlled testing and defensive-bias risk",
                "",
                "**Status:** Closed",
                "**Closed on:** 2026-07-22",
                "**Closure decision:** B87-D0 — Architecture Closure Decision",
                "",
            ]
        ),
        encoding="utf-8",
    )

    (root / finalizer.CLOSURE_DECISION_PATH).write_text(
        "\n".join(
            [
                "# B87-D0 — Architecture Closure Decision",
                "",
                "**Status:** Accepted and closed",
                "**Decision date:** 2026-07-22",
                "**Next authorised slice:** B87-I1 — Persistence Kernel",
                "",
                "model behavioural efficacy: not yet validated",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_prepare_change_ratifies_only_closure_metadata(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)

    change = finalizer.prepare_change(tmp_path)

    assert change.changed
    assert finalizer.APPROVED_STATUS in change.after
    assert finalizer.SATISFIED_EFFECTIVE_CONDITION in change.after
    assert finalizer.PENDING_STATUS not in change.after
    assert finalizer.PENDING_EFFECTIVE_CONDITION not in change.after
    assert "**Resolves:** D0-ISSUE-001" in change.after


def test_prepare_change_removes_trailing_whitespace_from_changed_lines(
    tmp_path: Path,
) -> None:
    write_fixture_repo(tmp_path)

    change = finalizer.prepare_change(tmp_path)
    lines = change.after.splitlines()

    status_line = next(line for line in lines if line.startswith("**Status:**"))
    effective_line = next(
        line for line in lines if line.startswith("**Effective condition:**")
    )

    assert status_line == finalizer.APPROVED_STATUS
    assert effective_line == finalizer.SATISFIED_EFFECTIVE_CONDITION
    assert not status_line.endswith((" ", "\t"))
    assert not effective_line.endswith((" ", "\t"))


def test_prepare_change_is_idempotent_after_write(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)

    first = finalizer.prepare_change(tmp_path)
    (tmp_path / first.path).write_text(first.after, encoding="utf-8")

    second = finalizer.prepare_change(tmp_path)

    assert not second.changed


def test_prepare_change_requires_accepted_closure_decision(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)
    (tmp_path / finalizer.CLOSURE_DECISION_PATH).write_text(
        "# B87-D0 — Architecture Closure Decision\n\n**Status:** Pending\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Closure decision is not acceptance-ready"):
        finalizer.prepare_change(tmp_path)
