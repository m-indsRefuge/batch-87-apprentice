from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from batch87_apprentice.common.errors import ConflictError, ValidationError
from batch87_apprentice.memory import TypedSourceReference
from batch87_apprentice.persistence.service import PersistenceService
from tests.support.i2_fixtures import NOW, uid
from tests.support.i3c3_fixtures import (
    create_active_analysis_task,
    create_approved_lesson,
    create_candidate,
    create_source_bundle,
    review_candidate,
)
from tests.support.i3d_fixtures import (
    I3DHarness,
    active_rule_source,
    build_i3d_harness,
    context_item,
    create_other_project_task_evidence,
    create_unbound_active_rule_source,
    source_hash,
)
from tests.support.sql_probe import SqlProbe


@pytest.fixture
def harness(tmp_path: Path) -> I3DHarness:
    return build_i3d_harness(tmp_path)


def finalize_one(harness: I3DHarness, *, base: int = 920_000) -> None:
    harness.persistence.session_task_memory.add_context_item(
        context_item(harness, base=base)
    )
    harness.persistence.session_task_memory.finalize_context(
        harness.task_id,
        finalization_id=uid(base + 1),
        finalized_at=NOW,
        finalized_by_principal="codex_development_harness",
    )


def lesson_sources(harness: I3DHarness, *, base: int):
    _, episode_bundle, correction_bundle = create_source_bundle(
        harness.c3,
        base=base,
    )
    episode, _ = episode_bundle
    correction, _ = correction_bundle
    candidate_task_id = create_active_analysis_task(
        harness.c3,
        base=base + 1_000,
    )
    _, candidate = create_candidate(
        harness.c3,
        base=base + 2_000,
        task_id=candidate_task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    review_candidate(
        harness.c3,
        candidate_id=candidate.record_id,
        transition_id=uid(base + 2_003),
    )
    _, approved = create_approved_lesson(
        harness.c3,
        base=base + 3_000,
        candidate=candidate,
    )
    return candidate, approved


def test_i3d_adds_no_duplicate_i2_authority_tables(
    harness: I3DHarness,
) -> None:
    names = SqlProbe(harness.config).read(
        lambda connection: {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    )
    assert {
        "sessions",
        "tasks",
        "task_state_transitions",
        "task_stop_events",
        "governance_decisions",
        "governed_runtime_transactions",
    } <= names
    assert not {
        "session_memory_sessions",
        "session_task_tasks",
        "task_memory_status",
        "context_manifests",
    } & names


def test_task_projection_reflects_exact_i2_state_and_is_read_only(
    harness: I3DHarness,
) -> None:
    finalize_one(harness)
    before = harness.runtime.reconstruct(harness.task_id).value
    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )
    after = harness.runtime.reconstruct(harness.task_id).value

    assert projection["integrity_verified"]
    assert projection["value"]["authority_source"] == "B87-I2"
    assert projection["value"]["authoritative_i2"] == before == after
    assert projection["value"]["context_ready"]
    assert projection["value"]["context"]["items"][0]["task_id"] == (
        harness.task_id
    )


def test_session_projection_contains_contract_history_participants_and_tasks(
    harness: I3DHarness,
) -> None:
    finalize_one(harness)
    projection = (
        harness.persistence.session_task_memory.reconstruct_session_memory(
            harness.session_id
        )
    )

    assert projection["integrity_verified"]
    value = projection["value"]
    assert value["integrity"]["summary"] == {
        "affected_task_ids": [],
        "reason_categories": [],
        "tasks": [],
    }
    assert value["authority_source"] == "B87-I2"
    assert value["session"]["session_id"] == harness.session_id
    assert value["retention_disposition"] == "retain_restricted"
    assert value["transitions"][0]["to_status"] == "open"
    assert {item["entity_id"] for item in value["participants"]} >= {
        harness.operator_id,
        harness.c3.c2.c1.i2.participant_id,
    }
    assert harness.task_id in {
        item["authoritative_i2"]["task"]["task_id"] for item in value["tasks"]
    }


@pytest.mark.parametrize(
    "corruption",
    (
        "task_contract",
        "governance_decision",
        "permission_profile",
        "runtime_transaction",
    ),
)
def test_session_projection_aggregates_contained_task_integrity_failures(
    harness: I3DHarness,
    corruption: str,
) -> None:
    finalize_one(harness, base=920_100)
    before = (
        harness.persistence.session_task_memory.reconstruct_session_memory(
            harness.session_id
        )
    )
    assert before["integrity_verified"]

    if corruption == "task_contract":
        triggers = ("tasks_core_immutable",)
        statement = "UPDATE tasks SET contract_hash = ? WHERE task_id = ?"
        parameters = ("0" * 64, harness.task_id)
    elif corruption == "governance_decision":
        triggers = ("governance_decisions_immutable",)
        statement = (
            "UPDATE governance_decisions SET content_hash = ? "
            "WHERE task_id = ?"
        )
        parameters = ("0" * 64, harness.task_id)
    elif corruption == "permission_profile":
        triggers = ("permission_profiles_immutable",)
        statement = """
            UPDATE permission_profiles
            SET content_hash = ?
            WHERE permission_profile_id = (
                SELECT permission_profile_id
                FROM governance_decisions
                WHERE task_id = ?
            )
        """
        parameters = ("0" * 64, harness.task_id)
    else:
        triggers = (
            "governed_runtime_transaction_finalise",
            "governed_runtime_transactions_no_second_update",
        )
        statement = """
            UPDATE governed_runtime_transactions
            SET content_hash = ?
            WHERE task_id = ?
        """
        parameters = ("0" * 64, harness.task_id)
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        triggers,
        lambda connection: connection.execute(statement, parameters),
    )

    task_projection = (
        harness.persistence.session_task_memory.reconstruct_task_memory(
            harness.task_id
        )
    )
    session_projection = (
        harness.persistence.session_task_memory.reconstruct_session_memory(
            harness.session_id
        )
    )
    session_value = session_projection["value"]
    nested = next(
        item
        for item in session_value["tasks"]
        if item["authoritative_i2"]["task"]["task_id"] == harness.task_id
    )
    task_summary = next(
        item
        for item in session_value["integrity"]["summary"]["tasks"]
        if item["task_id"] == harness.task_id
    )

    assert not task_projection["integrity_verified"]
    assert not task_projection["value"]["integrity"]["valid"]
    assert not task_projection["value"]["integrity"][
        "authoritative_i2_verified"
    ]
    assert task_projection["value"]["integrity"][
        "i2_reconstruction_error"
    ] is not None
    assert not session_projection["integrity_verified"]
    assert not session_value["integrity"]["valid"]
    assert session_value["integrity"]["findings"] == []
    assert harness.task_id in session_value["integrity"]["summary"][
        "affected_task_ids"
    ]
    expected_reasons = [
        "task_integrity_invalid",
        "authoritative_i2_integrity_findings",
        "authoritative_i2_unverified",
        "i2_reconstruction_error",
    ]
    if corruption == "task_contract":
        expected_reasons.append("task_scoped_i3d_findings")
    assert task_summary["reason_categories"] == expected_reasons
    assert nested == task_projection["value"]


def test_later_i2_transitions_appear_without_rewriting_i3d_history(
    harness: I3DHarness,
) -> None:
    finalize_one(harness)
    context_before = SqlProbe(harness.config).read(
        lambda connection: tuple(
            connection.execute(
                "SELECT * FROM task_context_items WHERE task_id = ?",
                (harness.task_id,),
            )
        )
    )
    harness.runtime.transition_task(
        harness.task_id,
        to_status="completed",
        reason_code="i3d_projection_completed",
    )
    harness.runtime.transition_session(
        harness.session_id,
        to_status="closed",
        reason_code="i3d_session_closed",
    )

    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id
    )
    context_after = SqlProbe(harness.config).read(
        lambda connection: tuple(
            connection.execute(
                "SELECT * FROM task_context_items WHERE task_id = ?",
                (harness.task_id,),
            )
        )
    )
    assert projection["value"]["authoritative_i2"]["task_status"] == "completed"
    assert projection["value"]["authoritative_i2"]["session"]["status"] == "closed"
    assert projection["value"]["context"]["items"]
    assert not projection["value"]["context_ready"]
    assert context_after == context_before


def test_file_reopen_reconstructs_identical_canonical_projection(
    harness: I3DHarness,
) -> None:
    finalize_one(harness)
    first = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )
    reopened = PersistenceService(harness.config)
    second = reopened.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )

    assert second["canonical_json"] == first["canonical_json"]
    assert second["content_hash"] == first["content_hash"]


def test_separate_process_reconstructs_exact_task_and_session_projections(
    harness: I3DHarness,
) -> None:
    finalize_one(harness)
    task = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )
    session = (
        harness.persistence.session_task_memory.reconstruct_session_memory(
            harness.session_id
        )
    )
    script = (
        "import json,sys;"
        "from pathlib import Path;"
        "from batch87_apprentice.persistence.config import DatabaseConfig;"
        "from batch87_apprentice.persistence.service import PersistenceService;"
        "s=PersistenceService(DatabaseConfig(Path(sys.argv[1])));"
        "t=s.session_task_memory.reconstruct_task_memory("
        "sys.argv[2],mode='active');"
        "m=s.session_task_memory.reconstruct_session_memory(sys.argv[3]);"
        "print(json.dumps({'task_hash':t['content_hash'],"
        "'session_hash':m['content_hash']},sort_keys=True))"
    )
    repository_root = Path(__file__).resolve().parents[2]
    source_root = repository_root / "src"
    pythonpath_entries = [str(source_root)]
    if os.environ.get("PYTHONPATH"):
        pythonpath_entries.append(os.environ["PYTHONPATH"])
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(pythonpath_entries),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(harness.config.path),
            harness.task_id,
            harness.session_id,
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "session_hash": session["content_hash"],
        "task_hash": task["content_hash"],
    }


def test_valid_context_item_is_exactly_task_session_project_bound(
    harness: I3DHarness,
) -> None:
    item = context_item(harness, base=921_000)
    digest = harness.persistence.session_task_memory.add_context_item(item)
    row = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            "SELECT * FROM task_context_items WHERE context_item_id = ?",
            (item.context_item_id,),
        ).fetchone()
    )
    assert digest == item.canonical_hash
    assert row["task_id"] == harness.task_id
    assert row["session_id"] == harness.session_id
    assert row["project_scope_id"] == harness.project_scope_id
    assert row["source_evidence_id"] == harness.task_evidence_id


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("task_id", uid(921_101)),
        ("session_id", uid(921_102)),
        ("project_scope_id", uid(921_103)),
    ),
)
def test_wrong_task_session_or_project_context_binding_fails(
    harness: I3DHarness,
    field: str,
    value: str,
) -> None:
    arguments = {field: value}
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            context_item(
                harness,
                base=921_110,
                **arguments,
            )
        )


def test_missing_or_hash_mismatched_context_source_fails(
    harness: I3DHarness,
) -> None:
    missing = TypedSourceReference(evidence_id=uid(921_200))
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            context_item(
                harness,
                base=921_201,
                source=missing,
                content_hash="a" * 64,
            )
        )
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            context_item(
                harness,
                base=921_202,
                content_hash="b" * 64,
            )
        )


def test_cross_project_governed_evidence_source_fails(
    harness: I3DHarness,
) -> None:
    evidence_id = create_other_project_task_evidence(
        harness,
        base=921_250,
    )
    source = TypedSourceReference(evidence_id=evidence_id)
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            context_item(
                harness,
                base=921_254,
                source=source,
            )
        )


def test_evidence_bound_only_to_another_same_project_task_fails(
    harness: I3DHarness,
) -> None:
    other_task_id = create_active_analysis_task(
        harness.c3,
        base=921_270,
    )
    other_evidence_id = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT relationship.resolved_evidence_id
            FROM governance_decision_evidence AS relationship
            JOIN governance_decisions AS decision_record
              ON decision_record.governance_decision_id =
                 relationship.governance_decision_id
            WHERE decision_record.task_id = ?
              AND relationship.validation_status = 'available'
              AND relationship.required_evidence_id =
                  relationship.resolved_evidence_id
            ORDER BY relationship.input_order
            LIMIT 1
            """,
            (other_task_id,),
        ).fetchone()[0]
    )
    source = TypedSourceReference(evidence_id=other_evidence_id)

    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            context_item(
                harness,
                base=921_273,
                source=source,
            )
        )


def test_evidence_resolved_without_matching_required_fails_sql_guard(
    harness: I3DHarness,
) -> None:
    def corrupt_relationship(connection) -> None:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            """
            UPDATE governance_decision_evidence
            SET required_evidence_id = ?
            WHERE governance_decision_id = (
                SELECT governance_decision_id
                FROM governance_decisions
                WHERE task_id = ?
            )
              AND resolved_evidence_id = ?
            """,
            (uid(921_280), harness.task_id, harness.task_evidence_id),
        )

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("governance_decision_evidence_immutable",),
        corrupt_relationship,
    )

    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            context_item(harness, base=921_281)
        )


def test_integrity_invalid_evidence_source_fails(
    harness: I3DHarness,
) -> None:
    SqlProbe(harness.config).write(
        lambda connection: connection.execute(
            """
            UPDATE evidence_items SET integrity_status = 'mismatch'
            WHERE evidence_id = ?
            """,
            (harness.task_evidence_id,),
        )
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            context_item(harness, base=921_300)
        )


def test_active_approved_lesson_succeeds_and_candidate_fails(
    harness: I3DHarness,
) -> None:
    candidate, approved = lesson_sources(harness, base=922_000)
    candidate_source = TypedSourceReference(
        memory_record_id=candidate.record_id
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            context_item(
                harness,
                base=922_100,
                context_kind="approved_lesson",
                source=candidate_source,
            )
        )

    approved_source = TypedSourceReference(
        memory_record_id=approved.record_id
    )
    item = context_item(
        harness,
        base=922_101,
        context_kind="approved_lesson",
        source=approved_source,
    )
    assert harness.persistence.session_task_memory.add_context_item(
        item
    ) == item.canonical_hash


def test_revoked_or_deleted_approved_lesson_source_fails(
    harness: I3DHarness,
) -> None:
    _, approved = lesson_sources(harness, base=923_000)
    harness.c3.memory.transition_lifecycle(
        approved.record_id,
        transition_id=uid(926_100),
        to_state="revoked",
        reason_code="lesson_revoked",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    source = TypedSourceReference(memory_record_id=approved.record_id)
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            context_item(
                harness,
                base=926_101,
                context_kind="approved_lesson",
                source=source,
            )
        )
    harness.c3.memory.transition_lifecycle(
        approved.record_id,
        transition_id=uid(926_102),
        to_state="deleted",
        reason_code="lesson_deleted",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            context_item(
                harness,
                base=926_103,
                context_kind="approved_lesson",
                source=source,
            )
        )


def test_controlled_prompt_or_output_cannot_enter_ordinary_context(
    harness: I3DHarness,
) -> None:
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("evidence_core_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE evidence_items SET evidence_kind = 'controlled_prompt'
            WHERE evidence_id = ?
            """,
            (harness.task_evidence_id,),
        ),
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            context_item(harness, base=927_000)
        )


def test_policy_context_uses_explicit_active_governance_rule(
    harness: I3DHarness,
) -> None:
    source = active_rule_source(harness)
    item = context_item(
        harness,
        base=927_100,
        context_kind="policy",
        source=source,
    )
    harness.persistence.session_task_memory.add_context_item(item)
    harness.persistence.session_task_memory.finalize_context(
        harness.task_id,
        finalization_id=uid(927_101),
        finalized_at=NOW,
        finalized_by_principal="operator",
    )
    decision = harness.persistence.session_task_memory.assess_context_item(
        harness.task_id,
        item.context_item_id,
        mode="active",
        evaluated_at=NOW,
    )
    assert decision.eligible
    assert decision.reason_codes == ()
    assert source_hash(harness, source) == item.content_hash


def test_active_rule_not_recorded_for_task_fails_repository_and_raw_sql(
    harness: I3DHarness,
) -> None:
    source = create_unbound_active_rule_source(harness, base=927_120)
    repository_item = context_item(
        harness,
        base=927_121,
        context_kind="policy",
        source=source,
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            repository_item
        )

    raw_item = context_item(
        harness,
        base=927_122,
        context_kind="policy",
        source=source,
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                INSERT INTO task_context_items (
                    context_item_id, task_id, session_id, project_scope_id,
                    context_kind, source_kind, source_memory_record_id,
                    source_evidence_id, source_governance_rule_id,
                    injection_order, required, content_hash, created_at,
                    created_by_principal, canonical_json, canonical_hash
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    raw_item.context_item_id,
                    raw_item.task_id,
                    raw_item.session_id,
                    raw_item.project_scope_id,
                    raw_item.context_kind,
                    raw_item.source.source_kind,
                    raw_item.source.governance_rule_id,
                    raw_item.injection_order,
                    int(raw_item.required),
                    raw_item.content_hash,
                    raw_item.created_at,
                    raw_item.created_by_principal,
                    raw_item.canonical_json,
                    raw_item.canonical_hash,
                ),
            )
        )


def test_duplicate_order_and_gapped_final_order_fail(
    harness: I3DHarness,
) -> None:
    harness.persistence.session_task_memory.add_context_item(
        context_item(harness, base=928_000, injection_order=0)
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            context_item(harness, base=928_001, injection_order=0)
        )

    harness.persistence.session_task_memory.add_context_item(
        context_item(harness, base=928_200, injection_order=2)
    )
    with pytest.raises(ValidationError, match="gapped order"):
        harness.persistence.session_task_memory.finalize_context(
            harness.task_id,
            finalization_id=uid(928_201),
            finalized_at=NOW,
            finalized_by_principal="operator",
        )


def test_finalized_context_rejects_update_delete_and_late_items(
    harness: I3DHarness,
) -> None:
    item = context_item(harness, base=929_000)
    harness.persistence.session_task_memory.add_context_item(item)
    harness.persistence.session_task_memory.finalize_context(
        harness.task_id,
        finalization_id=uid(929_001),
        finalized_at=NOW,
        finalized_by_principal="operator",
    )
    probe = SqlProbe(harness.config)
    with pytest.raises(ConflictError, match="integrity constraint"):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE task_context_items SET required = 0
                WHERE context_item_id = ?
                """,
                (item.context_item_id,),
            )
        )
    with pytest.raises(ConflictError, match="integrity constraint"):
        probe.write(
            lambda connection: connection.execute(
                "DELETE FROM task_context_items WHERE context_item_id = ?",
                (item.context_item_id,),
            )
        )
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.add_context_item(
            context_item(harness, base=929_002, injection_order=1)
        )


def test_new_context_after_terminal_task_or_closed_session_fails(
    tmp_path: Path,
) -> None:
    terminal = build_i3d_harness(tmp_path / "terminal", base=929_100)
    terminal.runtime.transition_task(
        terminal.task_id,
        to_status="completed",
        reason_code="task_complete",
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        terminal.persistence.session_task_memory.add_context_item(
            context_item(terminal, base=929_200)
        )

    closed = build_i3d_harness(tmp_path / "closed", base=929_300)
    closed.runtime.transition_session(
        closed.session_id,
        to_status="closed",
        reason_code="session_closed",
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        closed.persistence.session_task_memory.add_context_item(
            context_item(closed, base=929_400)
        )


def test_active_and_historical_eligibility_have_auditable_reason_codes(
    harness: I3DHarness,
) -> None:
    item = context_item(harness, base=929_500)
    harness.persistence.session_task_memory.add_context_item(item)
    harness.persistence.session_task_memory.finalize_context(
        harness.task_id,
        finalization_id=uid(929_501),
        finalized_at=NOW,
        finalized_by_principal="operator",
    )
    active = harness.persistence.session_task_memory.assess_context_item(
        harness.task_id,
        item.context_item_id,
        mode="active",
        evaluated_at=NOW,
    )
    assert active.eligible
    assert active.reason_codes == ()

    harness.runtime.transition_task(
        harness.task_id,
        to_status="completed",
        reason_code="task_complete",
    )
    harness.runtime.transition_session(
        harness.session_id,
        to_status="closed",
        reason_code="session_closed",
    )
    stale_active = harness.persistence.session_task_memory.assess_context_item(
        harness.task_id,
        item.context_item_id,
        mode="active",
        evaluated_at=NOW,
    )
    historical = harness.persistence.session_task_memory.assess_context_item(
        harness.task_id,
        item.context_item_id,
        mode="historical",
        evaluated_at=NOW,
    )

    assert not stale_active.eligible
    assert stale_active.reason_codes == (
        "task_not_active",
        "session_not_open",
        "historical_mode_required",
    )
    assert historical.eligible
    assert historical.reason_codes == ()
