from __future__ import annotations

from dataclasses import replace

import pytest

import batch87_apprentice.persistence.contracts as persistence_contracts
import tests.support.sql_probe as sql_probe_support

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ConflictError, ValidationError
from batch87_apprentice.persistence.contracts import (
    EvidenceItem,
    EvidenceLink,
    RecordEnvelope,
)
from tests.integration.test_i1_persistence_kernel import ordinary_record
from tests.support.i2_fixtures import EARLIER, NOW, uid
from tests.support.i3c_fixtures import register_evaluation
from tests.support.i3c2_fixtures import (
    C2Harness,
    activate_record,
    build_c2_harness,
    c2_evidence,
    claimed_evaluation,
    create_episode,
    create_terminal_task,
    episode_components,
)
from tests.support.sql_probe import SqlProbe


@pytest.fixture
def harness(tmp_path) -> C2Harness:
    return build_c2_harness(tmp_path)


def count(probe: SqlProbe, table: str) -> int:
    return probe.read(
        lambda connection: int(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        )
    )


def test_completed_episode_reconstructs_exact_ordered_lineage(
    harness: C2Harness,
) -> None:
    task_id = create_terminal_task(harness, base=600_000, status="completed")
    anchor = claimed_evaluation(harness, base=600_100)
    envelope, payload, _ = create_episode(
        harness,
        base=600_200,
        task_id=task_id,
        evaluation_record_ids=(anchor.evaluation_record_id,),
    )

    rebuilt = harness.persistence.episode_correction_ledger.reconstruct_episode(
        payload.record_id
    )

    assert rebuilt["record"]["project_scope_id"] == harness.project_scope_id
    assert rebuilt["payload"] == payload.canonical_content()
    assert rebuilt["input_evidence_ids"] == payload.input_evidence_ids
    assert rebuilt["output_evidence_ids"] == payload.output_evidence_ids
    assert rebuilt["evaluation_record_ids"] == payload.evaluation_record_ids
    assert {
        (item["evidence_id"], item["relationship"])
        for item in rebuilt["evidence_links"]
    } == {
        (payload.input_evidence_ids[0], "derived_from"),
        (payload.output_evidence_ids[0], "produced_as"),
    }
    assert rebuilt["canonical_json"] == payload.canonical_json
    assert rebuilt["content_hash"] == rebuilt["recomputed_content_hash"]
    assert rebuilt["integrity"]["valid"]
    assert envelope.approval_status == "pending"
    assert envelope.lifecycle_state == "observed"


def test_episode_activates_only_through_existing_external_approval(
    harness: C2Harness,
) -> None:
    task_id = create_terminal_task(harness, base=600_400, status="completed")
    _, payload, _ = create_episode(
        harness,
        base=600_500,
        task_id=task_id,
    )
    activate_record(
        harness,
        record_id=payload.record_id,
        base=600_600,
        starts_observed=True,
    )
    rebuilt = harness.persistence.episode_correction_ledger.reconstruct_episode(
        payload.record_id
    )
    assert rebuilt["record"]["approval_status"] == "approved"
    assert rebuilt["record"]["lifecycle_state"] == "active"
    assert rebuilt["integrity"]["valid"]


@pytest.mark.parametrize(
    ("task_status", "outcome"),
    (
        ("completed", "completed"),
        ("failed", "failed"),
        ("failed", "partial"),
        ("stopped", "stopped"),
        ("stopped", "partial"),
        ("stopped", "rejected"),
    ),
)
def test_terminal_task_outcome_matrix_is_exact(
    tmp_path,
    task_status: str,
    outcome: str,
) -> None:
    harness = build_c2_harness(tmp_path)
    task_id = create_terminal_task(
        harness,
        base=601_000,
        status=task_status,
    )
    _, payload, _ = create_episode(
        harness,
        base=601_100,
        task_id=task_id,
        outcome=outcome,
    )
    assert (
        harness.persistence.episode_correction_ledger.reconstruct_episode(
            payload.record_id
        )["payload"]["outcome"]
        == outcome
    )


@pytest.mark.parametrize(
    ("session_status", "outcome"),
    (
        ("closed", "completed"),
        ("aborted", "stopped"),
        ("aborted", "partial"),
    ),
)
def test_taskless_terminal_session_outcome_matrix(
    tmp_path,
    session_status: str,
    outcome: str,
) -> None:
    harness = build_c2_harness(tmp_path)
    harness.runtime.transition_session(
        harness.session_id,
        to_status=session_status,
        reason_code=f"fixture_{session_status}",
    )
    _, payload, _ = create_episode(
        harness,
        base=602_000,
        task_id=None,
        outcome=outcome,
        episode_kind="conversation",
    )
    assert harness.persistence.episode_correction_ledger.reconstruct_episode(
        payload.record_id
    )["integrity"]["valid"]


@pytest.mark.parametrize(
    ("task_status", "outcome"),
    (
        ("completed", "failed"),
        ("failed", "completed"),
        ("stopped", "completed"),
        ("completed", "rejected"),
    ),
)
def test_impossible_task_outcome_is_rejected(
    tmp_path,
    task_status: str,
    outcome: str,
) -> None:
    harness = build_c2_harness(tmp_path)
    task_id = create_terminal_task(
        harness,
        base=603_000,
        status=task_status,
    )
    envelope, payload, items = episode_components(
        harness,
        base=603_100,
        task_id=task_id,
        outcome=outcome,
    )
    with pytest.raises(ValidationError, match="outcome"):
        harness.persistence.episode_correction_ledger.create_episode(
            envelope,
            payload,
            lifecycle_transition_id=uid(603_130),
            approval_transition_id=uid(603_131),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
            evidence_items=items,
        )


def test_active_task_and_open_taskless_session_are_rejected(
    harness: C2Harness,
) -> None:
    active_task = create_terminal_task(harness, base=604_000, status="active")
    for base, task_id, match in (
        (604_100, active_task, "not terminal"),
        (604_200, None, "terminal session"),
    ):
        envelope, payload, items = episode_components(
            harness,
            base=base,
            task_id=task_id,
            outcome="completed",
        )
        with pytest.raises(ValidationError, match=match):
            harness.persistence.episode_correction_ledger.create_episode(
                envelope,
                payload,
                lifecycle_transition_id=uid(base + 30),
                approval_transition_id=uid(base + 31),
                changed_by_principal="operator",
                changed_by_entity_id=harness.operator_id,
                evidence_items=items,
            )


@pytest.mark.parametrize("defect", ("session", "project", "time"))
def test_occurrence_scope_and_terminal_time_fail_closed(
    tmp_path,
    defect: str,
) -> None:
    harness = build_c2_harness(tmp_path)
    task_id = create_terminal_task(harness, base=605_000, status="completed")
    envelope, payload, items = episode_components(
        harness,
        base=605_100,
        task_id=task_id,
        session_id=uid(605_500) if defect == "session" else None,
        project_scope_id=(
            harness.c1.i2.other_project_scope_id if defect == "project" else None
        ),
        created_at=EARLIER if defect == "time" else NOW,
    )
    with pytest.raises(ValidationError):
        harness.persistence.episode_correction_ledger.create_episode(
            envelope,
            payload,
            lifecycle_transition_id=uid(605_130),
            approval_transition_id=uid(605_131),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
            evidence_items=items,
        )


def test_missing_invalid_and_controlled_evidence_are_rejected_atomically(
    harness: C2Harness,
) -> None:
    task_id = create_terminal_task(harness, base=606_000, status="completed")
    missing_envelope, missing_payload, _ = episode_components(
        harness,
        base=606_100,
        task_id=task_id,
    )
    with pytest.raises(ValidationError, match="missing"):
        harness.persistence.episode_correction_ledger.create_episode(
            missing_envelope,
            missing_payload,
            lifecycle_transition_id=uid(606_130),
            approval_transition_id=uid(606_131),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )

    unavailable = EvidenceItem(
        evidence_id=uid(606_210),
        evidence_kind="document",
        storage_kind="repository_reference",
        storage_location="fixture://unavailable",
        captured_at=NOW,
        integrity_status="unavailable",
        redaction_status="none",
        sensitivity_class="internal",
        privacy_class="none",
        content_hash="0" * 64,
    )
    envelope, payload, _ = episode_components(
        harness,
        base=606_200,
        task_id=task_id,
        input_count=0,
        output_count=1,
    )
    payload = replace(
        payload,
        output_evidence_ids=(unavailable.evidence_id,),
    )
    with pytest.raises(ValidationError, match="valid integrity"):
        harness.persistence.episode_correction_ledger.create_episode(
            envelope,
            payload,
            lifecycle_transition_id=uid(606_230),
            approval_transition_id=uid(606_231),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
            evidence_items=(unavailable,),
        )

    controlled = EvidenceItem.inline_text(
        evidence_id=uid(606_310),
        evidence_kind="controlled_output",
        content="Raw controlled output.",
        captured_at=NOW,
        sensitivity_class="internal",
        privacy_class="none",
    )
    envelope, payload, _ = episode_components(
        harness,
        base=606_300,
        task_id=task_id,
        input_count=0,
        output_count=1,
    )
    payload = replace(payload, output_evidence_ids=(controlled.evidence_id,))
    with pytest.raises(ValidationError, match="Controlled Governance"):
        harness.persistence.episode_correction_ledger.create_episode(
            envelope,
            payload,
            lifecycle_transition_id=uid(606_330),
            approval_transition_id=uid(606_331),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
            evidence_items=(controlled,),
        )


def test_cross_project_evidence_is_rejected(
    harness: C2Harness,
) -> None:
    task_id = create_terminal_task(harness, base=606_500, status="completed")
    cross_project_item = c2_evidence(
        606_510,
        content="Evidence already scoped to another project.",
        captured_by_entity=harness.operator_id,
    )
    harness.persistence.evidence.create(cross_project_item)
    marker = RecordEnvelope(
        record_id=uid(606_511),
        record_family="audit_record",
        record_type="project_marker",
        schema_version="1.0.0",
        lifecycle_state="observed",
        approval_status="not_required",
        authority_class="validated_system_evidence",
        certainty_class="verified",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="temporary",
        training_eligibility="prohibited",
        created_at=NOW,
        source_kind="test",
        provenance_summary="Exact cross-project test marker.",
        retrieval_policy_json=canonical_json_text({"mode": "none"}),
        deletion_policy_json=canonical_json_text({"mode": "governed"}),
        agent_write_policy="prohibited",
        project_scope_id=harness.c1.i2.other_project_scope_id,
        created_by_entity_id=harness.operator_id,
    )
    harness.persistence.records.create(marker)
    harness.persistence.evidence.link(
        EvidenceLink(
            record_id=marker.record_id,
            evidence_id=cross_project_item.evidence_id,
            relationship="supports",
            explanation="Legitimate other-project evidence use.",
        )
    )
    envelope, payload, _ = episode_components(
        harness,
        base=606_520,
        task_id=task_id,
        input_count=1,
        output_count=0,
    )
    payload = replace(
        payload,
        input_evidence_ids=(cross_project_item.evidence_id,),
    )
    with pytest.raises(ValidationError, match="another project"):
        harness.persistence.episode_correction_ledger.create_episode(
            envelope,
            payload,
            lifecycle_transition_id=uid(606_550),
            approval_transition_id=uid(606_551),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )


def test_claimed_anchor_is_accepted_and_other_states_fail_closed(
    tmp_path,
) -> None:
    for index, state in enumerate(("registered", "invalid", "retired", "missing")):
        harness = build_c2_harness(
            tmp_path / state,
            identifier_start=610_000 + index * 1_000,
        )
        task_id = create_terminal_task(
            harness,
            base=607_000 + index * 1_000,
            status="completed",
        )
        if state == "missing":
            evaluation_id = uid(607_900 + index)
        else:
            anchor = register_evaluation(
                harness.c1,
                base=607_100 + index * 1_000,
                evaluation_kind="capability_evaluation",
                claimed=state != "registered",
            )
            evaluation_id = anchor.evaluation_record_id
            if state in {"invalid", "retired"}:
                harness.persistence.self_episodic_memory.transition_evaluation_anchor(
                    evaluation_id,
                    transition_id=uid(607_110 + index * 1_000),
                    to_state="invalid",
                    changed_at=NOW,
                    changed_by_principal="operator",
                    changed_by_entity_id=harness.operator_id,
                    transition_evidence_id=anchor.provenance_evidence_id,
                    reason_code="fixture_invalid",
                )
            if state == "retired":
                harness.persistence.self_episodic_memory.transition_evaluation_anchor(
                    evaluation_id,
                    transition_id=uid(607_111 + index * 1_000),
                    to_state="retired",
                    changed_at=NOW,
                    changed_by_principal="operator",
                    changed_by_entity_id=harness.operator_id,
                    transition_evidence_id=anchor.provenance_evidence_id,
                    reason_code="fixture_retired",
                )
        envelope, payload, items = episode_components(
            harness,
            base=607_500 + index * 1_000,
            task_id=task_id,
            evaluation_record_ids=(evaluation_id,),
        )
        with pytest.raises(ValidationError, match="anchor"):
            harness.persistence.episode_correction_ledger.create_episode(
                envelope,
                payload,
                lifecycle_transition_id=uid(607_530 + index * 1_000),
                approval_transition_id=uid(607_531 + index * 1_000),
                changed_by_principal="operator",
                changed_by_entity_id=harness.operator_id,
                evidence_items=items,
            )


@pytest.mark.parametrize(
    "failure_step",
    ("evidence", "record", "payload_and_lineage", "evidence_links", "histories"),
)
def test_injected_episode_failure_rolls_back_every_write(
    tmp_path,
    monkeypatch,
    failure_step: str,
) -> None:
    harness = build_c2_harness(tmp_path)
    task_id = create_terminal_task(harness, base=608_000, status="completed")
    envelope, payload, items = episode_components(
        harness,
        base=608_100,
        task_id=task_id,
    )
    repository = harness.persistence.episode_correction_ledger

    def fail(step, connection) -> None:
        if step == failure_step:
            raise RuntimeError(f"injected-{step}")

    monkeypatch.setattr(repository, "_after_write_step", fail)
    with pytest.raises(RuntimeError, match="injected"):
        repository.create_episode(
            envelope,
            payload,
            lifecycle_transition_id=uid(608_130),
            approval_transition_id=uid(608_131),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
            evidence_items=items,
        )
    probe = SqlProbe(harness.config)
    assert probe.read(
        lambda connection: connection.execute(
            "SELECT 1 FROM records WHERE record_id = ?",
            (payload.record_id,),
        ).fetchone()
    ) is None
    for item in items:
        assert probe.read(
            lambda connection, evidence_id=item.evidence_id: connection.execute(
                "SELECT 1 FROM evidence_items WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
        ) is None


def test_apprentice_creation_and_unrelated_self_tables_are_unchanged(
    harness: C2Harness,
) -> None:
    task_id = create_terminal_task(harness, base=609_000, status="completed")
    envelope, payload, items = episode_components(
        harness,
        base=609_100,
        task_id=task_id,
    )
    probe = SqlProbe(harness.config)
    before = tuple(
        count(probe, table)
        for table in (
            "capability_observations",
            "maturity_states",
            "developmental_policy_versions",
        )
    )
    with pytest.raises(ValidationError, match="principal"):
        harness.persistence.episode_correction_ledger.create_episode(
            envelope,
            payload,
            lifecycle_transition_id=uid(609_130),
            approval_transition_id=uid(609_131),
            changed_by_principal="apprentice",
            changed_by_entity_id=harness.agent_id,
            evidence_items=items,
        )
    create_episode(
        harness,
        base=609_200,
        task_id=task_id,
    )
    after = tuple(
        count(probe, table)
        for table in (
            "capability_observations",
            "maturity_states",
            "developmental_policy_versions",
        )
    )
    assert after == before


@pytest.mark.parametrize("active", (False, True))
def test_episode_lineage_is_sealed_after_initial_state(
    tmp_path,
    active: bool,
) -> None:
    harness = build_c2_harness(tmp_path)
    task_id = create_terminal_task(harness, base=612_000, status="completed")
    initial_anchor = claimed_evaluation(harness, base=612_100)
    _, payload, _ = create_episode(
        harness,
        base=612_200,
        task_id=task_id,
        evaluation_record_ids=(initial_anchor.evaluation_record_id,),
    )
    if active:
        activate_record(
            harness,
            record_id=payload.record_id,
            base=612_300,
            starts_observed=True,
        )

    late_evidence = c2_evidence(
        612_400,
        content="Late episode lineage must be rejected.",
        captured_by_entity=harness.operator_id,
    )
    harness.persistence.evidence.create(late_evidence)
    late_anchor = claimed_evaluation(harness, base=612_500)
    probe = SqlProbe(harness.config)

    attempts = (
        lambda connection: connection.execute(
            """
            INSERT INTO episode_input_evidence (
                record_id, evidence_id, evidence_order
            ) VALUES (?, ?, 1)
            """,
            (payload.record_id, late_evidence.evidence_id),
        ),
        lambda connection: connection.execute(
            """
            INSERT INTO episode_output_evidence (
                record_id, evidence_id, evidence_order
            ) VALUES (?, ?, 1)
            """,
            (payload.record_id, late_evidence.evidence_id),
        ),
        lambda connection: connection.execute(
            """
            INSERT INTO episode_evaluation_anchors (
                record_id, evaluation_record_id, evaluation_order
            ) VALUES (?, ?, 1)
            """,
            (payload.record_id, late_anchor.evaluation_record_id),
        ),
    )
    for attempt in attempts:
        with pytest.raises(ConflictError):
            probe.write(attempt)

    rebuilt = harness.persistence.episode_correction_ledger.reconstruct_episode(
        payload.record_id
    )
    assert rebuilt["input_evidence_ids"] == payload.input_evidence_ids
    assert rebuilt["output_evidence_ids"] == payload.output_evidence_ids
    assert rebuilt["evaluation_record_ids"] == payload.evaluation_record_ids
    assert rebuilt["content_hash"] == rebuilt["recomputed_content_hash"]


def test_episode_payload_cannot_be_inserted_after_initial_state(
    harness: C2Harness,
) -> None:
    task_id = create_terminal_task(harness, base=613_000, status="completed")
    envelope, payload, _ = episode_components(
        harness,
        base=613_100,
        task_id=task_id,
    )
    values = envelope.database_values(
        content_hash=persistence_contracts.record_content_hash(envelope)
    )
    columns = tuple(values)
    placeholders = ", ".join(f":{column}" for column in columns)
    sql_probe_support.SqlProbe(harness.config).write(
        lambda connection: connection.execute(
            (
                f"INSERT INTO records ({', '.join(columns)}) "
                f"VALUES ({placeholders})"
            ),
            values,
        )
    )
    harness.memory.register_initial_state(
        envelope.record_id,
        lifecycle_transition_id=uid(613_130),
        approval_transition_id=uid(613_131),
        changed_at=envelope.created_at,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
        reason_code="finalized_without_payload_for_guard_test",
    )

    with pytest.raises(ConflictError):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                INSERT INTO episodes (
                    record_id, episode_kind, summary, outcome, canonical_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload.record_id,
                    payload.episode_kind,
                    payload.summary,
                    payload.outcome,
                    payload.canonical_json,
                ),
            )
        )


def test_ordinary_evidence_link_cannot_be_retargeted_into_episode(
    harness: C2Harness,
) -> None:
    task_id = create_terminal_task(harness, base=614_000, status="completed")
    _, payload, _ = create_episode(
        harness,
        base=614_100,
        task_id=task_id,
    )
    ordinary = ordinary_record(614_200, harness.project_scope_id)
    evidence = c2_evidence(
        614_201,
        content="Ordinary evidence link retargeting fixture.",
        captured_by_entity=harness.operator_id,
    )
    harness.persistence.records.create(ordinary)
    harness.persistence.evidence.create(evidence)
    harness.persistence.evidence.link(
        EvidenceLink(
            record_id=ordinary.record_id,
            evidence_id=evidence.evidence_id,
            relationship="supports",
        )
    )

    with pytest.raises(ConflictError):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                UPDATE record_evidence_links
                SET record_id = ?
                WHERE record_id = ? AND evidence_id = ?
                  AND relationship = 'supports'
                """,
                (payload.record_id, ordinary.record_id, evidence.evidence_id),
            )
        )



def test_episode_evidence_link_is_independently_sealed_after_finalization(
    harness: C2Harness,
) -> None:
    task_id = create_terminal_task(harness, base=615_000, status="completed")
    _, payload, _ = create_episode(
        harness,
        base=615_100,
        task_id=task_id,
    )
    late_evidence = c2_evidence(
        615_200,
        content="Independent evidence-link finalization fixture.",
        captured_by_entity=harness.operator_id,
    )
    harness.persistence.evidence.create(late_evidence)
    probe = SqlProbe(harness.config)
    probe.corrupt_after_dropping_triggers(
        ("c2_episode_input_evidence_finalization_guard",),
        lambda connection: connection.execute(
            """
            INSERT INTO episode_input_evidence (
                record_id, evidence_id, evidence_order
            ) VALUES (?, ?, 1)
            """,
            (payload.record_id, late_evidence.evidence_id),
        ),
    )

    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                """
                INSERT INTO record_evidence_links (
                    record_id, evidence_id, relationship, explanation
                ) VALUES (?, ?, 'derived_from', ?)
                """,
                (
                    payload.record_id,
                    late_evidence.evidence_id,
                    "Late C2 link must remain sealed independently.",
                ),
            )
        )
