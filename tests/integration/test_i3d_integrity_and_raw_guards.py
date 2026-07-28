from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import ConflictError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.memory import (
    TaskContextFinalization,
    TypedSourceReference,
    UncertaintyResolution,
)
from batch87_apprentice.persistence.contracts import Entity
from batch87_apprentice.persistence.task_runtime_store import TaskRuntimeStore
from tests.support.i2_fixtures import EARLIER, LATER, NOW, task, uid
from tests.support.i3d_fixtures import (
    I3DHarness,
    active_rule_source,
    build_i3d_harness,
    context_item,
    create_other_project_task_evidence,
    create_uncertainty,
    create_unbound_active_rule_source,
    source_hash,
    uncertainty_components,
)
from tests.support.sql_probe import SqlProbe


JUST_BEFORE_LATER = "2026-07-24T11:59:59.999999Z"


@pytest.fixture
def harness(tmp_path: Path) -> I3DHarness:
    return build_i3d_harness(tmp_path, base=940_000)


def finalized_context(harness: I3DHarness, *, base: int = 941_000):
    item = context_item(harness, base=base)
    harness.persistence.session_task_memory.add_context_item(item)
    harness.persistence.session_task_memory.finalize_context(
        harness.task_id,
        finalization_id=uid(base + 1),
        finalized_at=NOW,
        finalized_by_principal="operator",
    )
    return item


def resolve(
    harness: I3DHarness,
    uncertainty_record_id: str,
    *,
    base: int,
) -> UncertaintyResolution:
    source = TypedSourceReference(evidence_id=harness.task_evidence_id)
    value = UncertaintyResolution(
        resolution_id=uid(base),
        uncertainty_record_id=uncertainty_record_id,
        task_id=harness.task_id,
        session_id=harness.session_id,
        project_scope_id=harness.project_scope_id,
        source=source,
        source_content_hash=source_hash(harness, source),
        resolved_at=NOW,
        created_by_principal="operator",
    )
    harness.persistence.session_task_memory.resolve_uncertainty(value)
    return value


def codes(harness: I3DHarness) -> set[str]:
    return {
        item.code
        for item in harness.persistence.session_task_integrity.inspect().findings
    }


def assert_dedicated_and_top_level_code(
    harness: I3DHarness,
    code: str,
) -> None:
    dedicated = harness.persistence.session_task_integrity.inspect()
    top = harness.persistence.integrity.inspect()
    assert code in {finding.code for finding in dedicated.findings}
    assert "session_task_" + code.lower().replace("-", "_") in {
        finding.code for finding in top.findings
    }


def rehash_transaction(
    connection: sqlite3.Connection,
    task_id: str,
) -> str:
    row = connection.execute(
        """
        SELECT transaction_record.*, task.contract_hash,
               decision.content_hash AS decision_hash,
               stop.content_hash AS stop_hash
        FROM governed_runtime_transactions AS transaction_record
        JOIN tasks AS task ON task.task_id = transaction_record.task_id
        JOIN governance_decisions AS decision
          ON decision.transaction_id = transaction_record.transaction_id
        LEFT JOIN task_stop_events AS stop
          ON stop.transaction_id = transaction_record.transaction_id
        WHERE transaction_record.task_id = ?
        """,
        (task_id,),
    ).fetchone()
    assert row is not None
    value = {
        "completed_at": row["completed_at"],
        "decision_hash": row["decision_hash"],
        "execution_principal": row["execution_principal"],
        "runtime_instance_id": row["runtime_instance_id"],
        "started_at": row["started_at"],
        "status": row["status"],
        "stop_hash": row["stop_hash"],
        "structured_failures": parse_json(row["structured_failure_json"]),
        "task_contract_hash": row["contract_hash"],
        "task_id": row["task_id"],
        "transaction_id": row["transaction_id"],
    }
    connection.execute(
        """
        UPDATE governed_runtime_transactions
        SET content_hash = ?
        WHERE transaction_id = ?
        """,
        (sha256_canonical_json(value), row["transaction_id"]),
    )
    return row["transaction_id"]


def rehash_decision(
    connection: sqlite3.Connection,
    task_id: str,
    **canonical_updates: object,
) -> str:
    row = connection.execute(
        """
        SELECT governance_decision_id, canonical_json
        FROM governance_decisions
        WHERE task_id = ?
        """,
        (task_id,),
    ).fetchone()
    assert row is not None
    value = parse_json(row["canonical_json"])
    assert isinstance(value, dict)
    value.update(canonical_updates)
    canonical = canonical_json_text(value)
    connection.execute(
        """
        UPDATE governance_decisions
        SET canonical_json = ?, content_hash = ?
        WHERE governance_decision_id = ?
        """,
        (
            canonical,
            sha256_canonical_json(value),
            row["governance_decision_id"],
        ),
    )
    return row["governance_decision_id"]


def assert_propagated_i2_findings(
    harness: I3DHarness,
    *,
    task_id: str,
    session_id: str,
    expected: set[tuple[str, str]],
) -> dict[str, object]:
    top = harness.persistence.integrity.inspect()
    dedicated = harness.persistence.session_task_integrity.inspect()
    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        task_id,
        mode="active",
        evaluated_at=NOW,
    )["value"]
    session = harness.persistence.session_task_memory.reconstruct_session_memory(
        session_id
    )["value"]

    assert expected <= {
        (finding.code, finding.object_id or "")
        for finding in top.findings
    }
    dedicated_i2 = {
        (finding.code, finding.object_id or "")
        for finding in dedicated.findings
        if finding.source == "i2"
        and finding.task_id == task_id
        and finding.session_id == session_id
    }
    task_i2 = {
        (finding["code"], finding["object_id"] or "")
        for finding in projection["integrity"][
            "authoritative_i2_integrity_findings"
        ]
    }
    assert expected <= dedicated_i2
    assert expected <= task_i2
    assert all(
        set(finding) == {
            "code",
            "detail",
            "object_id",
            "session_id",
            "severity",
            "source",
            "table",
            "task_id",
        }
        and finding["severity"] == "error"
        and finding["task_id"] == task_id
        and finding["session_id"] == session_id
        and not finding["code"].startswith("I3D-")
        for finding in projection["integrity"][
            "authoritative_i2_integrity_findings"
        ]
    )
    assert not projection["integrity"]["valid"]
    assert not projection["context_ready"]
    assert not session["integrity"]["valid"]
    assert task_id in session["integrity"]["summary"]["affected_task_ids"]
    assert "authoritative_i2_integrity_findings" in session[
        "integrity"
    ]["summary"]["reason_categories"]
    assert "session_scoped_i3d_findings" not in session[
        "integrity"
    ]["summary"]["reason_categories"]
    return projection


def create_extra_entity(harness: I3DHarness, *, number: int) -> str:
    entity_id = uid(number)
    harness.persistence.entities.create(
        Entity(
            entity_id=entity_id,
            entity_kind="system",
            canonical_name=f"Uncontracted participant {number}",
            description="Deterministic I3-D participant-boundary fixture.",
            status="active",
            created_at=NOW,
        )
    )
    return entity_id


def other_task_transaction(
    harness: I3DHarness,
    *,
    base: int,
) -> tuple[str, str]:
    create_other_project_task_evidence(harness, base=base)
    row = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT task.task_id, transaction_record.transaction_id
            FROM tasks AS task
            JOIN governed_runtime_transactions AS transaction_record
              ON transaction_record.task_id = task.task_id
            WHERE task.task_id <> ?
            ORDER BY task.task_id DESC
            LIMIT 1
            """,
            (harness.task_id,),
        ).fetchone()
    )
    assert row is not None
    return row["task_id"], row["transaction_id"]


def create_timed_context_and_uncertainty(
    harness: I3DHarness,
    *,
    base: int,
    timestamp: str,
) -> None:
    item = replace(
        context_item(harness, base=base),
        created_at=timestamp,
    )
    harness.persistence.session_task_memory.add_context_item(item)
    harness.persistence.session_task_memory.finalize_context(
        harness.task_id,
        finalization_id=uid(base + 1),
        finalized_at=timestamp,
        finalized_by_principal="operator",
    )
    envelope, payload = uncertainty_components(harness, base=base + 10)
    envelope = replace(envelope, created_at=timestamp)
    payload = replace(payload, created_at=timestamp)
    harness.persistence.session_task_memory.create_uncertainty(
        envelope,
        payload,
        lifecycle_transition_id=uid(base + 11),
        approval_transition_id=uid(base + 12),
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )


def apply_terminal_transition(
    harness: I3DHarness,
    *,
    terminal_kind: str,
    base: int,
    timestamp: str = LATER,
) -> None:
    store = TaskRuntimeStore(harness.config)
    if terminal_kind == "task":
        store.transition_task(
            task_id=harness.task_id,
            to_status="completed",
            transition_id=uid(base),
            changed_at=timestamp,
            reason_code="exact_terminal_fixture",
        )
    else:
        store.transition_session(
            session_id=harness.session_id,
            to_status="closed",
            transition_id=uid(base),
            changed_at=timestamp,
            changed_by_principal="codex_development_harness",
            reason_code="exact_terminal_fixture",
        )


def test_dedicated_and_top_level_integrity_are_clean_for_valid_data(
    harness: I3DHarness,
) -> None:
    finalized_context(harness)
    _, uncertainty = create_uncertainty(
        harness,
        base=941_100,
        impact="high",
    )
    resolve(harness, uncertainty.record_id, base=941_103)

    assert harness.persistence.session_task_integrity.inspect().ok
    assert harness.persistence.integrity.inspect().ok
    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
        evaluated_at=NOW,
    )["value"]
    assert projection["integrity"]["valid"]
    assert projection["context_ready"]
    assert projection["integrity"][
        "authoritative_i2_integrity_findings"
    ] == []


def test_committed_transaction_state_inconsistency_propagates_with_history(
    harness: I3DHarness,
) -> None:
    item = finalized_context(harness, base=950_000)
    _, uncertainty = create_uncertainty(
        harness,
        base=950_010,
        impact="high",
    )
    before = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
        evaluated_at=NOW,
    )["value"]
    transaction_id = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT transaction_id
            FROM governed_runtime_transactions
            WHERE task_id = ?
            """,
            (harness.task_id,),
        ).fetchone()["transaction_id"]
    )

    def corrupt(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE governed_runtime_transactions
            SET status = 'stopped'
            WHERE task_id = ?
            """,
            (harness.task_id,),
        )
        assert rehash_transaction(connection, harness.task_id) == transaction_id

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (
            "governed_runtime_transaction_finalise",
            "governed_runtime_transactions_no_second_update",
        ),
        corrupt,
    )

    projection = assert_propagated_i2_findings(
        harness,
        task_id=harness.task_id,
        session_id=harness.session_id,
        expected={
            ("task_runtime_state_inconsistent", transaction_id),
        },
    )
    assert projection["integrity"]["authoritative_i2_verified"]
    assert projection["integrity"]["i2_reconstruction_error"] is None
    assert [
        value["context_item_id"]
        for value in projection["context"]["items"]
    ] == [item.context_item_id]
    assert projection["context"]["finalization"] == before["context"][
        "finalization"
    ]
    assert [
        value["uncertainty"]["record_id"]
        for value in projection["uncertainties"]["history"]
    ] == [uncertainty.record_id]
    assert projection["authoritative_i2"]["transitions"] == before[
        "authoritative_i2"
    ]["transitions"]


def test_stopped_transaction_changed_to_committed_propagates(
    harness: I3DHarness,
) -> None:
    authority_id = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT claimed_authority_id
            FROM governance_decision_authority_inputs
            WHERE governance_decision_id = (
                SELECT governance_decision_id
                FROM governance_decisions
                WHERE task_id = ?
            )
            ORDER BY input_order
            LIMIT 1
            """,
            (harness.task_id,),
        ).fetchone()["claimed_authority_id"]
    )
    stopped_contract = task(
        harness.c3.c2.c1.i2,
        950_100,
        authority_ids=(authority_id,),
        action_class="execute",
        objective="Exercise deterministic stopped transaction projection.",
    )
    result = harness.runtime.evaluate(stopped_contract)
    assert result.task_status == "stopped"
    assert result.stop_event is not None
    transaction_id = result.decision.transaction_id

    def corrupt(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE governed_runtime_transactions
            SET status = 'committed'
            WHERE task_id = ?
            """,
            (stopped_contract.task_id,),
        )
        assert (
            rehash_transaction(connection, stopped_contract.task_id)
            == transaction_id
        )

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (
            "governed_runtime_transaction_finalise",
            "governed_runtime_transactions_no_second_update",
        ),
        corrupt,
    )

    projection = assert_propagated_i2_findings(
        harness,
        task_id=stopped_contract.task_id,
        session_id=harness.session_id,
        expected={
            ("task_runtime_state_inconsistent", transaction_id),
        },
    )
    assert projection["authoritative_i2"]["task_status"] == "stopped"
    assert projection["authoritative_i2"]["stop_event"] is not None
    assert projection["authoritative_i2"]["transitions"]


def test_stop_event_hash_finding_uses_stopped_task_attribution(
    harness: I3DHarness,
) -> None:
    authority_id = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT claimed_authority_id
            FROM governance_decision_authority_inputs
            WHERE governance_decision_id = (
                SELECT governance_decision_id
                FROM governance_decisions
                WHERE task_id = ?
            )
            ORDER BY input_order
            LIMIT 1
            """,
            (harness.task_id,),
        ).fetchone()["claimed_authority_id"]
    )
    stopped_contract = task(
        harness.c3.c2.c1.i2,
        950_150,
        authority_ids=(authority_id,),
        action_class="execute",
        objective="Exercise exact stop-event integrity attribution.",
    )
    result = harness.runtime.evaluate(stopped_contract)
    assert result.task_status == "stopped"
    assert result.stop_event is not None
    stop_event_id = result.stop_event.stop_event_id

    def corrupt(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE task_stop_events
            SET content_hash = ?
            WHERE stop_event_id = ?
            """,
            ("c" * 64, stop_event_id),
        )
        rehash_transaction(connection, stopped_contract.task_id)

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (
            "task_stop_events_immutable",
            "governed_runtime_transaction_finalise",
            "governed_runtime_transactions_no_second_update",
        ),
        corrupt,
    )

    assert_propagated_i2_findings(
        harness,
        task_id=stopped_contract.task_id,
        session_id=harness.session_id,
        expected={
            ("task_runtime_hash_mismatch", stop_event_id),
        },
    )


def test_decision_state_inconsistency_propagates_after_hash_recomputation(
    harness: I3DHarness,
) -> None:
    finalized_context(harness, base=950_200)
    identifiers = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT decision.governance_decision_id,
                   transaction_record.transaction_id
            FROM governance_decisions AS decision
            JOIN governed_runtime_transactions AS transaction_record
              ON transaction_record.transaction_id = decision.transaction_id
            WHERE decision.task_id = ?
            """,
            (harness.task_id,),
        ).fetchone()
    )

    def corrupt(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE governance_decisions
            SET decision = 'deny'
            WHERE task_id = ?
            """,
            (harness.task_id,),
        )
        assert (
            rehash_decision(
                connection,
                harness.task_id,
                outcome="deny",
            )
            == identifiers["governance_decision_id"]
        )
        assert (
            rehash_transaction(connection, harness.task_id)
            == identifiers["transaction_id"]
        )

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (
            "governance_decisions_immutable",
            "governed_runtime_transaction_finalise",
            "governed_runtime_transactions_no_second_update",
        ),
        corrupt,
    )

    projection = assert_propagated_i2_findings(
        harness,
        task_id=harness.task_id,
        session_id=harness.session_id,
        expected={
            (
                "task_runtime_state_inconsistent",
                identifiers["transaction_id"],
            ),
        },
    )
    assert projection["integrity"]["authoritative_i2_verified"]
    assert projection["integrity"]["i2_reconstruction_error"] is None


@pytest.mark.parametrize(
    ("record_kind", "table", "id_column", "trigger"),
    (
        (
            "permission_profile",
            "permission_profiles",
            "permission_profile_id",
            "permission_profiles_immutable",
        ),
        (
            "operation_definition",
            "operation_definitions",
            "operation_name",
            "operation_definitions_immutable",
        ),
    ),
)
def test_global_i2_record_corruption_is_attributed_through_exact_decision(
    harness: I3DHarness,
    record_kind: str,
    table: str,
    id_column: str,
    trigger: str,
) -> None:
    finalized_context(harness, base=950_250)
    row = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            f"""
            SELECT decision.governance_decision_id,
                   record.{id_column} AS object_id
            FROM governance_decisions AS decision
            JOIN {table} AS record ON record.{id_column} = {
                "decision.permission_profile_id"
                if record_kind == "permission_profile"
                else "decision.requested_operation"
            }
            WHERE decision.task_id = ?
            """,
            (harness.task_id,),
        ).fetchone()
    )
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (trigger,),
        lambda connection: connection.execute(
            f"""
            UPDATE {table}
            SET content_hash = ?
            WHERE {id_column} = ?
            """,
            ("d" * 64, row["object_id"]),
        ),
    )
    secondary_code = (
        "task_runtime_input_hash_mismatch"
        if record_kind == "permission_profile"
        else "decision_operation_definition_invalid"
    )

    assert_propagated_i2_findings(
        harness,
        task_id=harness.task_id,
        session_id=harness.session_id,
        expected={
            ("task_runtime_hash_mismatch", row["object_id"]),
            (secondary_code, row["governance_decision_id"]),
        },
    )


@pytest.mark.parametrize(
    "corruption",
    (
        "task_contract_hash",
        "execution_principal",
        "permission_profile_hash",
    ),
)
def test_decision_input_inconsistency_propagates_after_hash_recomputation(
    harness: I3DHarness,
    corruption: str,
) -> None:
    finalized_context(harness, base=950_300)
    decision_id = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT governance_decision_id
            FROM governance_decisions
            WHERE task_id = ?
            """,
            (harness.task_id,),
        ).fetchone()["governance_decision_id"]
    )
    triggers = [
        "governed_runtime_transaction_finalise",
        "governed_runtime_transactions_no_second_update",
    ]

    def corrupt(connection: sqlite3.Connection) -> None:
        if corruption == "task_contract_hash":
            connection.execute(
                """
                UPDATE governance_decisions
                SET task_contract_hash = ?
                WHERE task_id = ?
                """,
                ("a" * 64, harness.task_id),
            )
            rehash_decision(
                connection,
                harness.task_id,
                task_contract_hash="a" * 64,
            )
        elif corruption == "permission_profile_hash":
            connection.execute(
                """
                UPDATE governance_decisions
                SET permission_profile_hash = ?
                WHERE task_id = ?
                """,
                ("b" * 64, harness.task_id),
            )
            rehash_decision(
                connection,
                harness.task_id,
                permission_profile_hash="b" * 64,
            )
        else:
            connection.execute(
                """
                UPDATE governed_runtime_transactions
                SET execution_principal = 'operator'
                WHERE task_id = ?
                """,
                (harness.task_id,),
            )
        rehash_transaction(connection, harness.task_id)

    if corruption in {"task_contract_hash", "permission_profile_hash"}:
        triggers.append("governance_decisions_immutable")
    else:
        triggers.append("governed_runtime_transactions_core_immutable")
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        tuple(triggers),
        corrupt,
    )

    projection = assert_propagated_i2_findings(
        harness,
        task_id=harness.task_id,
        session_id=harness.session_id,
        expected={
            ("task_runtime_input_hash_mismatch", decision_id),
        },
    )
    assert projection["integrity"]["authoritative_i2_verified"]
    assert projection["integrity"]["i2_reconstruction_error"] is None


@pytest.mark.parametrize(
    ("relationship", "expected_codes"),
    (
        (
            "authority",
            {"decision_authority_relationship_invalid"},
        ),
        (
            "human_approval",
            {"decision_human_approval_relationship_invalid"},
        ),
        (
            "evidence",
            {
                "decision_evidence_assessment_relationship_invalid",
                "decision_evidence_relationship_invalid",
            },
        ),
        (
            "rule",
            {"decision_rule_relationship_invalid"},
        ),
    ),
)
def test_decision_relationship_findings_propagate_without_invented_codes(
    harness: I3DHarness,
    relationship: str,
    expected_codes: set[str],
) -> None:
    finalized_context(harness, base=950_400)
    decision_id = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT governance_decision_id
            FROM governance_decisions
            WHERE task_id = ?
            """,
            (harness.task_id,),
        ).fetchone()["governance_decision_id"]
    )
    triggers = [
        "governance_decisions_immutable",
        "governed_runtime_transaction_finalise",
        "governed_runtime_transactions_no_second_update",
    ]
    if relationship != "human_approval":
        triggers.append(
            {
                "authority":
                    "governance_decision_authority_inputs_no_delete",
                "evidence": "governance_decision_evidence_no_delete",
                "rule": "governance_decision_rules_no_delete",
            }[relationship]
        )

    def corrupt(connection: sqlite3.Connection) -> None:
        if relationship == "authority":
            connection.execute(
                """
                DELETE FROM governance_decision_authority_inputs
                WHERE governance_decision_id = ?
                """,
                (decision_id,),
            )
        elif relationship == "human_approval":
            connection.execute(
                """
                INSERT INTO governance_decision_human_approvals (
                    governance_decision_id, input_order,
                    claimed_human_approval_id,
                    resolved_human_approval_id, validation_status,
                    selected, consumed
                ) VALUES (?, 0, ?, NULL, 'missing_human_approval', 0, 0)
                """,
                (decision_id, uid(950_450)),
            )
        elif relationship == "evidence":
            connection.execute(
                """
                DELETE FROM governance_decision_evidence
                WHERE governance_decision_id = ?
                """,
                (decision_id,),
            )
        else:
            connection.execute(
                """
                DELETE FROM governance_decision_rules
                WHERE governance_decision_id = ?
                """,
                (decision_id,),
            )
        assert rehash_decision(connection, harness.task_id) == decision_id
        rehash_transaction(connection, harness.task_id)

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        tuple(triggers),
        corrupt,
    )

    projection = assert_propagated_i2_findings(
        harness,
        task_id=harness.task_id,
        session_id=harness.session_id,
        expected={(code, decision_id) for code in expected_codes},
    )
    propagated_codes = {
        finding["code"]
        for finding in projection["integrity"][
            "authoritative_i2_integrity_findings"
        ]
    }
    assert expected_codes <= propagated_codes
    assert "task_runtime_hash_mismatch" not in propagated_codes
    assert "task_runtime_transaction_hash_mismatch" not in propagated_codes


def test_task_attribution_isolated_across_tasks_and_sessions(
    harness: I3DHarness,
) -> None:
    finalized_context(harness, base=950_500)
    other_evidence_id = create_other_project_task_evidence(
        harness,
        base=950_510,
    )
    other = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT decision.task_id, decision.session_id,
                   decision.project_scope_id
            FROM governance_decisions AS decision
            JOIN governance_decision_evidence AS decision_evidence
              ON decision_evidence.governance_decision_id =
                 decision.governance_decision_id
            WHERE decision_evidence.resolved_evidence_id = ?
              AND decision.task_id <> ?
            """,
            (other_evidence_id, harness.task_id),
        ).fetchone()
    )
    other_source = TypedSourceReference(evidence_id=other_evidence_id)
    other_item = context_item(
        harness,
        base=950_520,
        source=other_source,
        task_id=other["task_id"],
        session_id=other["session_id"],
        project_scope_id=other["project_scope_id"],
        content_hash=source_hash(harness, other_source),
    )
    harness.persistence.session_task_memory.add_context_item(other_item)
    harness.persistence.session_task_memory.finalize_context(
        other["task_id"],
        finalization_id=uid(950_521),
        finalized_at=NOW,
        finalized_by_principal="operator",
    )
    other_before = (
        harness.persistence.session_task_memory.reconstruct_task_memory(
            other["task_id"],
            mode="active",
            evaluated_at=NOW,
        )["value"]
    )
    assert other_before["integrity"]["valid"]
    assert other_before["context_ready"]
    transaction_id = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT transaction_id
            FROM governed_runtime_transactions
            WHERE task_id = ?
            """,
            (harness.task_id,),
        ).fetchone()["transaction_id"]
    )

    def corrupt(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE governed_runtime_transactions
            SET status = 'stopped'
            WHERE task_id = ?
            """,
            (harness.task_id,),
        )
        rehash_transaction(connection, harness.task_id)

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (
            "governed_runtime_transaction_finalise",
            "governed_runtime_transactions_no_second_update",
        ),
        corrupt,
    )

    assert_propagated_i2_findings(
        harness,
        task_id=harness.task_id,
        session_id=harness.session_id,
        expected={
            ("task_runtime_state_inconsistent", transaction_id),
        },
    )
    other_after = (
        harness.persistence.session_task_memory.reconstruct_task_memory(
            other["task_id"],
            mode="active",
            evaluated_at=NOW,
        )["value"]
    )
    other_session = (
        harness.persistence.session_task_memory.reconstruct_session_memory(
            other["session_id"]
        )["value"]
    )
    main_session = (
        harness.persistence.session_task_memory.reconstruct_session_memory(
            harness.session_id
        )["value"]
    )
    assert other_after["integrity"]["valid"]
    assert other_after["context_ready"]
    assert other_after["integrity"][
        "authoritative_i2_integrity_findings"
    ] == []
    assert other_session["integrity"]["valid"]
    assert other_session["integrity"]["summary"]["affected_task_ids"] == []
    assert not main_session["integrity"]["valid"]
    assert main_session["integrity"]["summary"]["affected_task_ids"] == [
        harness.task_id
    ]


def test_top_level_integrity_includes_i3d_findings(
    harness: I3DHarness,
) -> None:
    item = finalized_context(harness)
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("task_context_items_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE task_context_items SET canonical_json = '{}'
            WHERE context_item_id = ?
            """,
            (item.context_item_id,),
        ),
    )
    dedicated = harness.persistence.session_task_integrity.inspect()
    top = harness.persistence.integrity.inspect()

    assert "I3D-CONTEXT-CANONICAL" in {
        finding.code for finding in dedicated.findings
    }
    assert "session_task_i3d_context_canonical" in {
        finding.code for finding in top.findings
    }


@pytest.mark.parametrize(
    ("target", "expected"),
    (
        ("context_canonical", "I3D-CONTEXT-CANONICAL"),
        ("context_hash", "I3D-CONTEXT-CANONICAL"),
        ("ordering", "I3D-CONTEXT-ORDER"),
        ("cross_project", "I3D-CONTEXT-BINDING"),
    ),
)
def test_context_corruption_is_detected(
    harness: I3DHarness,
    target: str,
    expected: str,
) -> None:
    item = finalized_context(harness)
    if target == "context_canonical":
        statement = "UPDATE task_context_items SET canonical_json = '{}' WHERE context_item_id = ?"
        parameters = (item.context_item_id,)
    elif target == "context_hash":
        statement = "UPDATE task_context_items SET canonical_hash = ? WHERE context_item_id = ?"
        parameters = ("b" * 64, item.context_item_id)
    elif target == "ordering":
        statement = "UPDATE task_context_items SET injection_order = 2 WHERE context_item_id = ?"
        parameters = (item.context_item_id,)
    else:
        statement = "UPDATE task_context_items SET project_scope_id = ? WHERE context_item_id = ?"
        parameters = (
            harness.c3.c2.c1.i2.other_project_scope_id,
            item.context_item_id,
        )
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("task_context_items_immutable",),
        lambda connection: connection.execute(statement, parameters),
    )
    assert expected in codes(harness)


def test_missing_typed_context_source_is_detected(
    harness: I3DHarness,
) -> None:
    item = finalized_context(harness)
    connection = sqlite3.connect(harness.config.path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DROP TRIGGER task_context_items_immutable")
        connection.execute(
            """
            UPDATE task_context_items SET source_evidence_id = ?
            WHERE context_item_id = ?
            """,
            (uid(941_299), item.context_item_id),
        )
        connection.commit()
    finally:
        connection.close()
    assert "I3D-CONTEXT-SOURCE" in codes(harness)


def test_unbound_active_rule_corruption_is_ineligible_and_detected(
    harness: I3DHarness,
) -> None:
    bound_source = active_rule_source(harness)
    item = context_item(
        harness,
        base=941_250,
        context_kind="policy",
        source=bound_source,
    )
    harness.persistence.session_task_memory.add_context_item(item)
    finalization_id = uid(941_251)
    harness.persistence.session_task_memory.finalize_context(
        harness.task_id,
        finalization_id=finalization_id,
        finalized_at=NOW,
        finalized_by_principal="operator",
    )

    unbound_source = create_unbound_active_rule_source(
        harness,
        base=941_252,
    )
    corrupted_item = replace(
        item,
        source=unbound_source,
        content_hash=source_hash(harness, unbound_source),
    )
    corrupted_finalization = TaskContextFinalization(
        finalization_id=finalization_id,
        task_id=harness.task_id,
        session_id=harness.session_id,
        project_scope_id=harness.project_scope_id,
        ordered_item_ids=(corrupted_item.context_item_id,),
        ordered_item_hashes=(corrupted_item.canonical_hash,),
        finalized_at=NOW,
        finalized_by_principal="operator",
    )

    def corrupt(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE task_context_items
            SET source_governance_rule_id = ?, content_hash = ?,
                canonical_json = ?, canonical_hash = ?
            WHERE context_item_id = ?
            """,
            (
                unbound_source.governance_rule_id,
                corrupted_item.content_hash,
                corrupted_item.canonical_json,
                corrupted_item.canonical_hash,
                item.context_item_id,
            ),
        )
        connection.execute(
            """
            UPDATE task_context_finalizations
            SET canonical_json = ?, content_hash = ?
            WHERE finalization_id = ?
            """,
            (
                corrupted_finalization.canonical_json,
                corrupted_finalization.content_hash,
                finalization_id,
            ),
        )

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (
            "task_context_items_immutable",
            "task_context_finalizations_immutable",
        ),
        corrupt,
    )

    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
        evaluated_at=NOW,
    )["value"]
    assert not projection["context_ready"]
    assert projection["context"]["items"][0]["eligibility"]["reason_codes"] == [
        "source_not_task_bound"
    ]
    assert "I3D-CONTEXT-SOURCE" in codes(harness)
    assert "session_task_i3d_context_source" in {
        finding.code
        for finding in harness.persistence.integrity.inspect().findings
    }


@pytest.mark.parametrize(
    "corruption",
    ("relationship_deleted", "required_mismatch", "decision_project"),
)
def test_current_evidence_task_binding_loss_is_ineligible_and_detected(
    harness: I3DHarness,
    corruption: str,
) -> None:
    item = finalized_context(harness, base=941_270)

    if corruption == "relationship_deleted":
        triggers = ("governance_decision_evidence_no_delete",)

        def corrupt(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                DELETE FROM governance_decision_evidence
                WHERE governance_decision_id = (
                    SELECT governance_decision_id
                    FROM governance_decisions
                    WHERE task_id = ?
                )
                  AND resolved_evidence_id = ?
                """,
                (harness.task_id, harness.task_evidence_id),
            )

    elif corruption == "required_mismatch":
        triggers = ("governance_decision_evidence_immutable",)

        def corrupt(connection: sqlite3.Connection) -> None:
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
                (uid(941_272), harness.task_id, harness.task_evidence_id),
            )

    else:
        triggers = ("governance_decisions_immutable",)

        def corrupt(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                UPDATE governance_decisions
                SET project_scope_id = ?
                WHERE task_id = ?
                """,
                (
                    harness.c3.c2.c1.i2.other_project_scope_id,
                    harness.task_id,
                ),
            )

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        triggers,
        corrupt,
    )

    eligibility = (
        harness.persistence.session_task_memory.assess_context_item(
            harness.task_id,
            item.context_item_id,
            mode="active",
            evaluated_at=NOW,
        )
    )
    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
        evaluated_at=NOW,
    )["value"]
    dedicated = harness.persistence.session_task_integrity.inspect()
    top = harness.persistence.integrity.inspect()

    assert not eligibility.eligible
    assert eligibility.reason_codes == ("source_not_task_bound",)
    assert not projection["context_ready"]
    assert "I3D-CONTEXT-SOURCE" in {
        finding.code for finding in dedicated.findings
    }
    assert "session_task_i3d_context_source" in {
        finding.code for finding in top.findings
    }


@pytest.mark.parametrize(
    ("target", "expected"),
    (
        ("uncertainty_canonical", "I3D-UNCERTAINTY-CANONICAL"),
        ("record_hash", "I3D-UNCERTAINTY-CANONICAL"),
        ("resolution_hash", "I3D-RESOLUTION-CANONICAL"),
        ("resolution_time", "I3D-RESOLUTION-BINDING"),
    ),
)
def test_uncertainty_and_resolution_corruption_is_detected(
    harness: I3DHarness,
    target: str,
    expected: str,
) -> None:
    _, uncertainty = create_uncertainty(
        harness,
        base=941_300,
        impact="high",
    )
    resolution = resolve(harness, uncertainty.record_id, base=941_303)
    probe = SqlProbe(harness.config)
    if target == "uncertainty_canonical":
        probe.corrupt_after_dropping_triggers(
            ("active_uncertainties_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE active_uncertainties SET canonical_json = '{}'
                WHERE record_id = ?
                """,
                (uncertainty.record_id,),
            ),
        )
    elif target == "record_hash":
        probe.corrupt_after_dropping_triggers(
            ("active_uncertainty_records_immutable",),
            lambda connection: connection.execute(
                "UPDATE records SET content_hash = ? WHERE record_id = ?",
                ("c" * 64, uncertainty.record_id),
            ),
        )
    elif target == "resolution_hash":
        probe.corrupt_after_dropping_triggers(
            ("uncertainty_resolutions_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE uncertainty_resolutions SET content_hash = ?
                WHERE resolution_id = ?
                """,
                ("d" * 64, resolution.resolution_id),
            ),
        )
    else:
        corrupted = UncertaintyResolution(
            resolution_id=resolution.resolution_id,
            uncertainty_record_id=resolution.uncertainty_record_id,
            task_id=resolution.task_id,
            session_id=resolution.session_id,
            project_scope_id=resolution.project_scope_id,
            source=resolution.source,
            source_content_hash=resolution.source_content_hash,
            resolved_at=EARLIER,
            created_by_principal=resolution.created_by_principal,
        )
        probe.corrupt_after_dropping_triggers(
            ("uncertainty_resolutions_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE uncertainty_resolutions
                SET resolved_at = ?, canonical_json = ?, content_hash = ?
                WHERE resolution_id = ?
                """,
                (
                    EARLIER,
                    corrupted.canonical_json,
                    corrupted.content_hash,
                    resolution.resolution_id,
                ),
            ),
        )
    assert expected in codes(harness)


@pytest.mark.parametrize(
    "envelope_field",
    ("task_id", "session_id", "project_scope_id", "created_at"),
)
def test_explicit_envelope_aliases_detect_binding_corruption_and_block_context(
    harness: I3DHarness,
    envelope_field: str,
) -> None:
    finalized_context(harness, base=941_350)
    _, uncertainty = create_uncertainty(
        harness,
        base=941_360,
        impact="blocking",
    )
    resolve(harness, uncertainty.record_id, base=941_363)
    before = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
        evaluated_at=NOW,
    )["value"]
    assert before["context_ready"]

    create_other_project_task_evidence(harness, base=941_370)
    other = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT task_id, session_id, project_scope_id
            FROM tasks
            WHERE task_id <> ?
            ORDER BY task_id
            LIMIT 1
            """,
            (harness.task_id,),
        ).fetchone()
    )
    replacement_value = (
        LATER if envelope_field == "created_at" else other[envelope_field]
    )
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("active_uncertainty_records_immutable",),
        lambda connection: connection.execute(
            f"UPDATE records SET {envelope_field} = ? WHERE record_id = ?",
            (replacement_value, uncertainty.record_id),
        ),
    )

    dedicated = harness.persistence.session_task_integrity.inspect()
    top = harness.persistence.integrity.inspect()
    after = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
        evaluated_at=NOW,
    )["value"]

    assert "I3D-UNCERTAINTY-BINDING" in {
        finding.code for finding in dedicated.findings
    }
    assert "session_task_i3d_uncertainty_binding" in {
        finding.code for finding in top.findings
    }
    assert not after["context_ready"]
    assert after["uncertainties"]["active"] == []
    assert after["uncertainties"]["history"][0]["uncertainty"]["current"] is False


@pytest.mark.parametrize(
    "corruption",
    ("session_id", "project_scope_id", "task_id", "finalized_at"),
)
def test_finalization_binding_and_live_state_corruption_is_detected(
    harness: I3DHarness,
    corruption: str,
) -> None:
    item = finalized_context(harness, base=942_000)
    create_other_project_task_evidence(harness, base=942_010)
    other = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT task_id, session_id, project_scope_id
            FROM tasks
            WHERE project_scope_id = ?
            ORDER BY task_id
            LIMIT 1
            """,
            (harness.c3.c2.c1.i2.other_project_scope_id,),
        ).fetchone()
    )
    values = {
        "task_id": harness.task_id,
        "session_id": harness.session_id,
        "project_scope_id": harness.project_scope_id,
        "finalized_at": NOW,
    }
    values[corruption] = (
        EARLIER if corruption == "finalized_at" else other[corruption]
    )
    corrupted = TaskContextFinalization(
        finalization_id=uid(942_001),
        task_id=values["task_id"],
        session_id=values["session_id"],
        project_scope_id=values["project_scope_id"],
        ordered_item_ids=(item.context_item_id,),
        ordered_item_hashes=(item.canonical_hash,),
        finalized_at=values["finalized_at"],
        finalized_by_principal="operator",
    )
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("task_context_finalizations_immutable",),
        lambda connection: connection.execute(
            f"""
            UPDATE task_context_finalizations
            SET {corruption} = ?, canonical_json = ?, content_hash = ?
            WHERE finalization_id = ?
            """,
            (
                values[corruption],
                corrupted.canonical_json,
                corrupted.content_hash,
                corrupted.finalization_id,
            ),
        ),
    )
    stored = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT canonical_json, content_hash
            FROM task_context_finalizations
            WHERE finalization_id = ?
            """,
            (corrupted.finalization_id,),
        ).fetchone()
    )

    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
        evaluated_at=NOW,
    )["value"]
    dedicated = harness.persistence.session_task_integrity.inspect()
    top = harness.persistence.integrity.inspect()

    assert not projection["context_ready"]
    assert stored["canonical_json"] == corrupted.canonical_json
    assert stored["content_hash"] == corrupted.content_hash
    assert "I3D-CONTEXT-FINALIZATION-BINDING" in {
        finding.code for finding in dedicated.findings
    }
    assert "session_task_i3d_context_finalization_binding" in {
        finding.code for finding in top.findings
    }


def test_raw_sql_context_insert_cannot_bypass_terminal_task_guard(
    harness: I3DHarness,
) -> None:
    item = context_item(harness, base=941_400)
    harness.runtime.transition_task(
        harness.task_id,
        to_status="completed",
        reason_code="task_complete",
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
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.context_item_id,
                    item.task_id,
                    item.session_id,
                    item.project_scope_id,
                    item.context_kind,
                    item.source.source_kind,
                    item.source.evidence_id,
                    item.injection_order,
                    int(item.required),
                    item.content_hash,
                    item.created_at,
                    item.created_by_principal,
                    item.canonical_json,
                    item.canonical_hash,
                ),
            )
        )


def test_raw_sql_uncertainty_payload_cannot_bypass_envelope_guard(
    harness: I3DHarness,
) -> None:
    _, payload = uncertainty_components(harness, base=941_500)
    with pytest.raises(ConflictError, match="integrity constraint"):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                INSERT INTO active_uncertainties (
                    record_id, task_id, session_id, project_scope_id,
                    uncertainty_statement, impact, resolution_required,
                    created_at, created_by_principal, canonical_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.record_id,
                    payload.task_id,
                    payload.session_id,
                    payload.project_scope_id,
                    payload.uncertainty_statement,
                    payload.impact,
                    int(payload.resolution_required),
                    payload.created_at,
                    payload.created_by_principal,
                    payload.canonical_json,
                ),
            )
        )


def test_raw_sql_gapped_finalization_is_rejected(
    harness: I3DHarness,
) -> None:
    item = context_item(harness, base=941_600, injection_order=1)
    harness.persistence.session_task_memory.add_context_item(item)
    with pytest.raises(ConflictError, match="integrity constraint"):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                INSERT INTO task_context_finalizations (
                    finalization_id, task_id, session_id, project_scope_id,
                    item_count, finalized_at, finalized_by_principal,
                    canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, 1, ?, 'operator', '{}', ?)
                """,
                (
                    uid(941_601),
                    harness.task_id,
                    harness.session_id,
                    harness.project_scope_id,
                    NOW,
                    "a" * 64,
                ),
            )
        )


def test_uncontracted_session_participant_is_rejected_at_sql_boundary(
    harness: I3DHarness,
) -> None:
    entity_id = create_extra_entity(harness, number=949_001)

    with pytest.raises(ConflictError, match="integrity constraint"):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                INSERT INTO session_participants (session_id, entity_id, role)
                VALUES (?, ?, 'participant')
                """,
                (harness.session_id, entity_id),
            )
        )


@pytest.mark.parametrize(
    "corruption",
    (
        "missing_participant",
        "missing_creator",
        "extra_participant",
        "creator_role",
        "participant_role",
    ),
)
def test_authoritative_session_participant_corruption_propagates_without_losing_history(
    harness: I3DHarness,
    corruption: str,
) -> None:
    finalized_context(harness, base=949_100)
    create_uncertainty(harness, base=949_110)
    probe = SqlProbe(harness.config)

    if corruption in {"missing_participant", "missing_creator"}:
        probe.corrupt_after_dropping_triggers(
            ("session_participants_no_delete",),
            lambda connection: connection.execute(
                """
                DELETE FROM session_participants
                WHERE session_id = ?
                  AND (
                      (? = 'missing_creator' AND entity_id = ?)
                      OR
                      (? = 'missing_participant' AND entity_id <> ?)
                  )
                """,
                (
                    harness.session_id,
                    corruption,
                    harness.operator_id,
                    corruption,
                    harness.operator_id,
                ),
            ),
        )
    elif corruption == "extra_participant":
        entity_id = create_extra_entity(harness, number=949_120)
        probe.corrupt_after_dropping_triggers(
            ("session_participants_contract_guard",),
            lambda connection: connection.execute(
                """
                INSERT INTO session_participants (session_id, entity_id, role)
                VALUES (?, ?, 'participant')
                """,
                (harness.session_id, entity_id),
            ),
        )
    elif corruption == "creator_role":
        probe.corrupt_after_dropping_triggers(
            ("session_participants_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE session_participants SET role = 'participant'
                WHERE session_id = ? AND entity_id = ?
                """,
                (harness.session_id, harness.operator_id),
            ),
        )
    else:
        probe.corrupt_after_dropping_triggers(
            ("session_participants_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE session_participants SET role = 'operator'
                WHERE session_id = ? AND entity_id <> ?
                """,
                (harness.session_id, harness.operator_id),
            ),
        )

    assert_dedicated_and_top_level_code(
        harness,
        "I3D-I2-SESSION-PARTICIPANTS",
    )
    task = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
        evaluated_at=NOW,
    )["value"]
    session = harness.persistence.session_task_memory.reconstruct_session_memory(
        harness.session_id
    )["value"]

    assert not task["integrity"]["valid"]
    assert not task["context_ready"]
    assert len(task["context"]["items"]) == 1
    assert task["context"]["finalization"] is not None
    assert len(task["uncertainties"]["history"]) == 1
    assert session["transitions"]
    assert not session["integrity"]["valid"]
    expected_codes = {"I3D-I2-SESSION-PARTICIPANTS"}
    if corruption in {"missing_creator", "creator_role"}:
        expected_codes.add("session_operator_missing")
    assert {
        finding["code"] for finding in session["integrity"]["findings"]
    } == expected_codes
    assert "session_scoped_i3d_findings" in session["integrity"]["summary"][
        "reason_categories"
    ]
    assert "task_scoped_i3d_findings" not in session["integrity"]["summary"][
        "reason_categories"
    ]


def test_authoritative_session_column_drift_invalidates_session_and_task(
    harness: I3DHarness,
) -> None:
    finalized_context(harness, base=949_200)
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("sessions_core_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE sessions SET session_purpose = 'relational drift'
            WHERE session_id = ?
            """,
            (harness.session_id,),
        ),
    )

    assert_dedicated_and_top_level_code(
        harness,
        "I3D-I2-SESSION-CANONICAL",
    )
    task = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
        evaluated_at=NOW,
    )["value"]
    session = harness.persistence.session_task_memory.reconstruct_session_memory(
        harness.session_id
    )["value"]

    assert not task["integrity"]["valid"]
    assert not task["context_ready"]
    assert not session["integrity"]["valid"]
    assert "session_scoped_i3d_findings" in session["integrity"]["summary"][
        "reason_categories"
    ]
    assert "task_scoped_i3d_findings" not in session["integrity"]["summary"][
        "reason_categories"
    ]


def test_malformed_session_contract_fails_closed_without_losing_projection(
    harness: I3DHarness,
) -> None:
    finalized_context(harness, base=949_250)
    SqlProbe(harness.config).write(
        lambda connection: connection.execute(
            """
            UPDATE sessions SET canonical_json = '{}'
            WHERE session_id = ?
            """,
            (harness.session_id,),
        )
    )

    assert_dedicated_and_top_level_code(
        harness,
        "I3D-I2-SESSION-CANONICAL",
    )
    task = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id
    )["value"]
    session = harness.persistence.session_task_memory.reconstruct_session_memory(
        harness.session_id
    )["value"]
    assert not task["integrity"]["valid"]
    assert not task["context_ready"]
    assert len(task["context"]["items"]) == 1
    assert not session["integrity"]["valid"]
    assert session["session"]["session_id"] == harness.session_id
    assert session["transitions"]


@pytest.mark.parametrize(
    "corruption",
    ("sequence", "timestamp", "status", "closed_at"),
)
def test_authoritative_session_history_corruption_is_detected_and_propagated(
    harness: I3DHarness,
    corruption: str,
) -> None:
    finalized_context(harness, base=949_300)
    store = TaskRuntimeStore(harness.config)
    probe = SqlProbe(harness.config)

    if corruption == "sequence":
        probe.corrupt_after_dropping_triggers(
            ("session_state_transitions_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE session_state_transitions SET sequence_number = 2
                WHERE session_id = ? AND sequence_number = 0
                """,
                (harness.session_id,),
            ),
        )
    elif corruption == "timestamp":
        store.transition_session(
            session_id=harness.session_id,
            to_status="paused",
            transition_id=uid(949_310),
            changed_at=LATER,
            changed_by_principal="codex_development_harness",
            reason_code="pause_for_timestamp_fixture",
        )
        probe.corrupt_after_dropping_triggers(
            ("session_state_transitions_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE session_state_transitions SET changed_at = ?
                WHERE session_id = ? AND sequence_number = 1
                """,
                (EARLIER, harness.session_id),
            ),
        )
    elif corruption == "status":
        probe.corrupt_after_dropping_triggers(
            ("sessions_status_requires_transition",),
            lambda connection: connection.execute(
                """
                UPDATE sessions SET session_status = 'paused'
                WHERE session_id = ?
                """,
                (harness.session_id,),
            ),
        )
    else:
        store.transition_session(
            session_id=harness.session_id,
            to_status="closed",
            transition_id=uid(949_320),
            changed_at=LATER,
            changed_by_principal="codex_development_harness",
            reason_code="close_for_timestamp_fixture",
        )
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE sessions SET closed_at = ?
                WHERE session_id = ?
                """,
                (NOW, harness.session_id),
            )
        )

    assert_dedicated_and_top_level_code(
        harness,
        "I3D-I2-SESSION-HISTORY",
    )
    task = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id
    )["value"]
    session = harness.persistence.session_task_memory.reconstruct_session_memory(
        harness.session_id
    )["value"]
    assert not task["integrity"]["valid"]
    assert not task["context_ready"]
    assert not session["integrity"]["valid"]
    assert session["transitions"]


def test_session_and_task_transition_timestamp_regressions_are_rejected(
    harness: I3DHarness,
) -> None:
    transaction_id = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT transaction_id
            FROM governed_runtime_transactions
            WHERE task_id = ?
            """,
            (harness.task_id,),
        ).fetchone()["transaction_id"]
    )

    with pytest.raises(ConflictError, match="integrity constraint"):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                INSERT INTO session_state_transitions (
                    transition_id, session_id, sequence_number, from_status,
                    to_status, reason_code, changed_at, changed_by_principal
                ) VALUES (?, ?, 1, 'open', 'paused', 'timestamp_regression',
                          ?, 'codex_development_harness')
                """,
                (uid(949_400), harness.session_id, EARLIER),
            )
        )

    with pytest.raises(ConflictError, match="integrity constraint"):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                INSERT INTO task_state_transitions (
                    transition_id, task_id, sequence_number, from_status,
                    to_status, reason_code, changed_at, changed_by,
                    transaction_id
                ) VALUES (?, ?, 2, 'active', 'completed',
                          'timestamp_regression', ?, 'governance_kernel', ?)
                """,
                (
                    uid(949_401),
                    harness.task_id,
                    EARLIER,
                    transaction_id,
                ),
            )
        )


def test_authoritative_task_column_drift_is_task_scoped_only(
    harness: I3DHarness,
) -> None:
    finalized_context(harness, base=949_500)
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("tasks_core_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE tasks SET objective = 'relational task drift'
            WHERE task_id = ?
            """,
            (harness.task_id,),
        ),
    )

    assert_dedicated_and_top_level_code(
        harness,
        "I3D-I2-TASK-CANONICAL",
    )
    task = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
        evaluated_at=NOW,
    )["value"]
    session = harness.persistence.session_task_memory.reconstruct_session_memory(
        harness.session_id
    )["value"]

    assert not task["integrity"]["valid"]
    assert not task["context_ready"]
    assert {
        finding["task_id"] for finding in task["integrity"]["findings"]
    } == {harness.task_id}
    assert session["integrity"]["findings"] == []
    categories = session["integrity"]["summary"]["reason_categories"]
    assert "task_scoped_i3d_findings" in categories
    assert "session_scoped_i3d_findings" not in categories


def test_malformed_task_contract_fails_closed_without_losing_history(
    harness: I3DHarness,
) -> None:
    finalized_context(harness, base=949_550)
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("tasks_core_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE tasks SET canonical_contract_json = '{}'
            WHERE task_id = ?
            """,
            (harness.task_id,),
        ),
    )

    assert_dedicated_and_top_level_code(
        harness,
        "I3D-I2-TASK-CANONICAL",
    )
    task = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id
    )["value"]
    session = harness.persistence.session_task_memory.reconstruct_session_memory(
        harness.session_id
    )["value"]
    assert not task["integrity"]["valid"]
    assert not task["context_ready"]
    assert len(task["context"]["items"]) == 1
    assert task["context"]["finalization"] is not None
    assert not session["integrity"]["valid"]
    assert harness.task_id in session["integrity"]["summary"][
        "affected_task_ids"
    ]


@pytest.mark.parametrize(
    "corruption",
    ("sequence", "timestamp", "status", "started_at", "completed_at"),
)
def test_authoritative_task_history_corruption_is_detected_and_aggregated(
    harness: I3DHarness,
    corruption: str,
) -> None:
    finalized_context(harness, base=949_600)
    probe = SqlProbe(harness.config)
    store = TaskRuntimeStore(harness.config)

    if corruption == "sequence":
        probe.corrupt_after_dropping_triggers(
            ("task_transitions_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE task_state_transitions SET sequence_number = 3
                WHERE task_id = ? AND sequence_number = 1
                """,
                (harness.task_id,),
            ),
        )
    elif corruption == "timestamp":
        probe.corrupt_after_dropping_triggers(
            ("task_transitions_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE task_state_transitions SET changed_at = ?
                WHERE task_id = ? AND sequence_number = 1
                """,
                (EARLIER, harness.task_id),
            ),
        )
    elif corruption == "status":
        probe.corrupt_after_dropping_triggers(
            ("tasks_status_requires_transition",),
            lambda connection: connection.execute(
                """
                UPDATE tasks
                SET status = 'pending', started_at = NULL
                WHERE task_id = ?
                """,
                (harness.task_id,),
            ),
        )
    elif corruption == "started_at":
        probe.write(
            lambda connection: connection.execute(
                "UPDATE tasks SET started_at = ? WHERE task_id = ?",
                (LATER, harness.task_id),
            )
        )
    else:
        store.transition_task(
            task_id=harness.task_id,
            to_status="completed",
            transition_id=uid(949_610),
            changed_at=LATER,
            reason_code="complete_for_timestamp_fixture",
        )
        probe.write(
            lambda connection: connection.execute(
                "UPDATE tasks SET completed_at = ? WHERE task_id = ?",
                (NOW, harness.task_id),
            )
        )

    assert_dedicated_and_top_level_code(
        harness,
        "I3D-I2-TASK-HISTORY",
    )
    task = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id
    )["value"]
    session = harness.persistence.session_task_memory.reconstruct_session_memory(
        harness.session_id
    )["value"]
    assert not task["integrity"]["valid"]
    assert not task["context_ready"]
    assert not session["integrity"]["valid"]
    assert harness.task_id in session["integrity"]["summary"][
        "affected_task_ids"
    ]
    assert "task_scoped_i3d_findings" in session["integrity"]["summary"][
        "reason_categories"
    ]


def test_other_task_transaction_is_rejected_and_corruption_is_detected(
    harness: I3DHarness,
) -> None:
    finalized_context(harness, base=949_700)
    _, other_transaction_id = other_task_transaction(
        harness,
        base=949_710,
    )

    with pytest.raises(ConflictError, match="integrity constraint"):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                INSERT INTO task_state_transitions (
                    transition_id, task_id, sequence_number, from_status,
                    to_status, reason_code, changed_at, changed_by,
                    transaction_id
                ) VALUES (?, ?, 2, 'active', 'completed',
                          'wrong_transaction', ?, 'governance_kernel', ?)
                """,
                (
                    uid(949_720),
                    harness.task_id,
                    LATER,
                    other_transaction_id,
                ),
            )
        )

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("task_transitions_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE task_state_transitions SET transaction_id = ?
            WHERE task_id = ? AND sequence_number = 1
            """,
            (other_transaction_id, harness.task_id),
        ),
    )

    assert_dedicated_and_top_level_code(
        harness,
        "I3D-I2-TASK-TRANSACTION",
    )
    task = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id
    )["value"]
    session = harness.persistence.session_task_memory.reconstruct_session_memory(
        harness.session_id
    )["value"]
    assert not task["integrity"]["valid"]
    assert not task["context_ready"]
    assert not session["integrity"]["valid"]
    assert harness.task_id in session["integrity"]["summary"][
        "affected_task_ids"
    ]


@pytest.mark.parametrize("terminal_kind", ("task", "session"))
def test_exact_terminal_timestamp_is_not_historically_live(
    harness: I3DHarness,
    terminal_kind: str,
) -> None:
    create_timed_context_and_uncertainty(
        harness,
        base=949_800,
        timestamp=LATER,
    )
    apply_terminal_transition(
        harness,
        terminal_kind=terminal_kind,
        base=949_820,
    )

    expected = {
        "I3D-CONTEXT-CREATION-STATE",
        "I3D-CONTEXT-FINALIZATION-BINDING",
        "I3D-UNCERTAINTY-CREATION-STATE",
    }
    dedicated = harness.persistence.session_task_integrity.inspect()
    top = harness.persistence.integrity.inspect()
    dedicated_codes = {finding.code for finding in dedicated.findings}
    top_codes = {finding.code for finding in top.findings}
    assert expected <= dedicated_codes
    assert {
        "session_task_" + code.lower().replace("-", "_")
        for code in expected
    } <= top_codes

    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
        evaluated_at=LATER,
    )["value"]
    assert not projection["context_ready"]
    assert len(projection["context"]["items"]) == 1
    assert projection["context"]["finalization"] is not None
    assert len(projection["uncertainties"]["history"]) == 1


@pytest.mark.parametrize("terminal_kind", ("task", "session"))
def test_just_before_terminal_timestamp_remains_historically_live(
    harness: I3DHarness,
    terminal_kind: str,
) -> None:
    create_timed_context_and_uncertainty(
        harness,
        base=949_900,
        timestamp=JUST_BEFORE_LATER,
    )
    apply_terminal_transition(
        harness,
        terminal_kind=terminal_kind,
        base=949_920,
    )

    prohibited = {
        "I3D-CONTEXT-CREATION-STATE",
        "I3D-CONTEXT-FINALIZATION-BINDING",
        "I3D-UNCERTAINTY-CREATION-STATE",
    }
    dedicated = harness.persistence.session_task_integrity.inspect()
    top = harness.persistence.integrity.inspect()
    dedicated_codes = {finding.code for finding in dedicated.findings}
    top_codes = {finding.code for finding in top.findings}
    assert not (prohibited & dedicated_codes)
    assert not (
        {
            "session_task_" + code.lower().replace("-", "_")
            for code in prohibited
        }
        & top_codes
    )
