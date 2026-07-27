from __future__ import annotations

from dataclasses import replace

import pytest

import batch87_apprentice.persistence.contracts as persistence_contracts
import tests.support.sql_probe as sql_probe_support

from batch87_apprentice.common.errors import ConflictError, ValidationError
from batch87_apprentice.memory import (
    MemoryRelationshipGrant,
    RecordRelationship,
)
from batch87_apprentice.persistence.contracts import EvidenceItem, EvidenceLink
from tests.integration.test_i1_persistence_kernel import ordinary_record
from tests.support.i2_fixtures import NOW, uid
from tests.support.i3c2_fixtures import (
    C2Harness,
    activate_record,
    add_corrects_relationship,
    approve_memory_record,
    build_c2_harness,
    correction_components,
    create_correction,
    create_episode,
    create_terminal_task,
)
from tests.support.i3c_fixtures import register_nolan_byte_authority
from tests.support.sql_probe import SqlProbe


@pytest.fixture
def harness(tmp_path) -> C2Harness:
    return build_c2_harness(tmp_path)


def target_episode(
    harness: C2Harness,
    *,
    base: int,
):
    task_id = create_terminal_task(harness, base=base, status="completed")
    return create_episode(harness, base=base + 100, task_id=task_id)


def test_correction_accepts_exact_target_and_reconstructs_exact_links(
    harness: C2Harness,
) -> None:
    _, episode, _ = target_episode(harness, base=620_000)
    envelope, correction, support = create_correction(
        harness,
        base=620_300,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )

    rebuilt = harness.persistence.episode_correction_ledger.reconstruct_correction(
        correction.record_id
    )

    assert rebuilt["payload"] == correction.canonical_content()
    assert rebuilt["supporting_evidence_ids"] == (
        support[0].evidence_id,
    )
    assert {
        (item["evidence_id"], item["relationship"])
        for item in rebuilt["evidence_links"]
    } == {
        (episode.output_evidence_ids[0], "derived_from"),
        (support[0].evidence_id, "supports"),
    }
    assert rebuilt["content_hash"] == rebuilt["recomputed_content_hash"]
    assert rebuilt["integrity"]["valid"]
    assert envelope.lifecycle_state == "reviewed"
    assert envelope.approval_status == "pending"


def test_non_output_and_cross_project_targets_are_rejected(
    harness: C2Harness,
) -> None:
    _, episode, _ = target_episode(harness, base=621_000)
    for base, target_evidence, project_scope in (
        (621_300, episode.input_evidence_ids[0], harness.project_scope_id),
        (
            621_400,
            episode.output_evidence_ids[0],
            harness.c1.i2.other_project_scope_id,
        ),
    ):
        envelope, payload, support = correction_components(
            harness,
            base=base,
            target_episode_id=episode.record_id,
            target_output_evidence_id=target_evidence,
            project_scope_id=project_scope,
        )
        with pytest.raises(ValidationError, match="target"):
            harness.persistence.episode_correction_ledger.create_correction(
                envelope,
                payload,
                supporting_evidence_ids=(support[0].evidence_id,),
                lifecycle_transition_id=uid(base + 30),
                approval_transition_id=uid(base + 31),
                changed_by_principal="operator",
                changed_by_entity_id=harness.operator_id,
                evidence_items=support,
            )


@pytest.mark.parametrize("terminal_state", ("revoked", "deleted"))
def test_revoked_or_deleted_target_is_rejected(
    tmp_path,
    terminal_state: str,
) -> None:
    harness = build_c2_harness(tmp_path)
    _, episode, _ = target_episode(harness, base=622_000)
    harness.memory.transition_lifecycle(
        episode.record_id,
        transition_id=uid(622_250),
        to_state=terminal_state,
        reason_code=f"fixture_{terminal_state}",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    envelope, payload, support = correction_components(
        harness,
        base=622_300,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )
    with pytest.raises(ValidationError, match="revoked or deleted"):
        harness.persistence.episode_correction_ledger.create_correction(
            envelope,
            payload,
            supporting_evidence_ids=(support[0].evidence_id,),
            lifecycle_transition_id=uid(622_330),
            approval_transition_id=uid(622_331),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
            evidence_items=support,
        )


def test_support_is_required_separate_and_controlled_evidence_is_rejected(
    harness: C2Harness,
) -> None:
    _, episode, _ = target_episode(harness, base=623_000)
    envelope, payload, support = correction_components(
        harness,
        base=623_300,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )
    repository = harness.persistence.episode_correction_ledger
    with pytest.raises(ValidationError, match="must not be empty"):
        repository.create_correction(
            envelope,
            payload,
            supporting_evidence_ids=(),
            lifecycle_transition_id=uid(623_330),
            approval_transition_id=uid(623_331),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )
    with pytest.raises(ValidationError, match="separate"):
        repository.create_correction(
            envelope,
            payload,
            supporting_evidence_ids=(payload.target_output_evidence_id,),
            lifecycle_transition_id=uid(623_332),
            approval_transition_id=uid(623_333),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )

    controlled = EvidenceItem.inline_text(
        evidence_id=uid(623_400),
        evidence_kind="controlled_prompt",
        content="Raw controlled prompt.",
        captured_at=NOW,
        sensitivity_class="internal",
        privacy_class="none",
    )
    with pytest.raises(ValidationError, match="Controlled Governance"):
        repository.create_correction(
            envelope,
            payload,
            supporting_evidence_ids=(controlled.evidence_id,),
            lifecycle_transition_id=uid(623_430),
            approval_transition_id=uid(623_431),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
            evidence_items=(controlled,),
        )
    assert support


def test_issuer_must_be_active_and_approved_evaluator_fails_closed(
    tmp_path,
) -> None:
    inactive_harness = build_c2_harness(tmp_path / "inactive")
    _, episode, _ = target_episode(inactive_harness, base=624_000)
    SqlProbe(inactive_harness.config).write(
        lambda connection: connection.execute(
            "UPDATE entities SET status = 'inactive' WHERE entity_id = ?",
            (inactive_harness.operator_id,),
        )
    )
    envelope, payload, support = correction_components(
        inactive_harness,
        base=624_300,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )
    with pytest.raises(ValidationError, match="active entity"):
        inactive_harness.persistence.episode_correction_ledger.create_correction(
            envelope,
            payload,
            supporting_evidence_ids=(support[0].evidence_id,),
            lifecycle_transition_id=uid(624_330),
            approval_transition_id=uid(624_331),
            changed_by_principal="operator",
            changed_by_entity_id=inactive_harness.operator_id,
            evidence_items=support,
        )

    evaluator_harness = build_c2_harness(tmp_path / "evaluator")
    _, episode, _ = target_episode(evaluator_harness, base=625_000)
    envelope, payload, support = correction_components(
        evaluator_harness,
        base=625_300,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
        issuer_class="approved_evaluator",
    )
    with pytest.raises(ValidationError, match="cannot prove"):
        evaluator_harness.persistence.episode_correction_ledger.create_correction(
            envelope,
            payload,
            supporting_evidence_ids=(support[0].evidence_id,),
            lifecycle_transition_id=uid(625_330),
            approval_transition_id=uid(625_331),
            changed_by_principal="operator",
            changed_by_entity_id=evaluator_harness.operator_id,
            evidence_items=support,
        )


def test_creation_does_not_create_authority_approval_or_later_payloads(
    harness: C2Harness,
) -> None:
    _, episode, _ = target_episode(harness, base=626_000)
    probe = SqlProbe(harness.config)
    before_authority = probe.read(
        lambda connection: connection.execute(
            "SELECT COUNT(*) FROM authority_records"
        ).fetchone()[0]
    )
    _, correction, _ = create_correction(
        harness,
        base=626_300,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )
    assert probe.read(
        lambda connection: connection.execute(
            "SELECT COUNT(*) FROM authority_records"
        ).fetchone()[0]
    ) == before_authority
    assert probe.read(
        lambda connection: connection.execute(
            "SELECT COUNT(*) FROM memory_approval_grants WHERE record_id = ?",
            (correction.record_id,),
        ).fetchone()[0]
    ) == 0
    assert probe.read(
        lambda connection: connection.execute(
            """
            SELECT COUNT(*) FROM records
            WHERE record_type IN (
                'lesson_candidate', 'approved_lesson',
                'failure_pattern', 'success_pattern'
            )
            """
        ).fetchone()[0]
    ) == 0


def test_activation_requires_exact_consumed_corrects_grant_and_rolls_back(
    harness: C2Harness,
) -> None:
    _, episode, _ = target_episode(harness, base=627_000)
    _, correction, _ = create_correction(
        harness,
        base=627_300,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )
    approve_memory_record(harness, record_id=correction.record_id, base=627_400)
    harness.memory.transition_lifecycle(
        correction.record_id,
        transition_id=uid(627_500),
        to_state="approved",
        reason_code="approval_recorded",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    before = harness.persistence.episode_correction_ledger.reconstruct_correction(
        correction.record_id
    )
    with pytest.raises(ConflictError):
        harness.memory.transition_lifecycle(
            correction.record_id,
            transition_id=uid(627_501),
            to_state="active",
            reason_code="premature_activation",
            changed_at=NOW,
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )
    after = harness.persistence.episode_correction_ledger.reconstruct_correction(
        correction.record_id
    )
    assert after["record"]["lifecycle_state"] == "approved"
    assert after["record"] == before["record"]
    add_corrects_relationship(
        harness,
        correction_id=correction.record_id,
        episode_id=episode.record_id,
        base=627_600,
    )
    harness.memory.transition_lifecycle(
        correction.record_id,
        transition_id=uid(627_502),
        to_state="active",
        reason_code="governed_activation",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    assert harness.persistence.episode_correction_ledger.reconstruct_correction(
        correction.record_id
    )["record"]["lifecycle_state"] == "active"


@pytest.mark.parametrize("wrong_kind", ("direction", "target", "duplicate"))
def test_wrong_or_additional_corrects_relationship_is_rejected(
    tmp_path,
    wrong_kind: str,
) -> None:
    harness = build_c2_harness(tmp_path)
    _, episode, _ = target_episode(harness, base=628_000)
    _, correction, _ = create_correction(
        harness,
        base=628_300,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )
    if wrong_kind in {"target", "duplicate"}:
        _, other_episode, _ = target_episode(harness, base=628_500)
    else:
        other_episode = episode
    if wrong_kind == "duplicate":
        add_corrects_relationship(
            harness,
            correction_id=correction.record_id,
            episode_id=episode.record_id,
            base=628_700,
        )
        source_id = correction.record_id
        target_id = episode.record_id
    elif wrong_kind == "direction":
        source_id = episode.record_id
        target_id = correction.record_id
    else:
        source_id = correction.record_id
        target_id = other_episode.record_id
    authority_record, approval_evidence = register_nolan_byte_authority(
        harness.c1,
        base=628_800,
        content="Exact wrong-relationship rejection authority fixture.",
    )
    relationship_id = uid(628_802)
    grant = MemoryRelationshipGrant(
        grant_id=uid(628_803),
        relationship_id=relationship_id,
        relationship_type="corrects",
        source_record_id=source_id,
        target_record_id=target_id,
        project_scope_id=harness.project_scope_id,
        authority_record_id=authority_record.authority_record_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        evidence_id=approval_evidence.evidence_id,
    )
    relationship = RecordRelationship(
        relationship_id=relationship_id,
        source_record_id=source_id,
        target_record_id=target_id,
        relationship_type="corrects",
        created_at=NOW,
        created_by_principal="operator",
        relationship_grant_id=grant.grant_id,
        explanation="Intentionally wrong C2 relationship.",
    )
    harness.memory.register_relationship_grant(grant)
    with pytest.raises((ConflictError, ValidationError)):
        harness.memory.link_records(relationship)


def test_original_episode_and_output_remain_byte_identical_after_correction(
    harness: C2Harness,
) -> None:
    _, episode, _ = target_episode(harness, base=629_000)
    probe = SqlProbe(harness.config)

    def snapshot(connection):
        return (
            tuple(
                connection.execute(
                    "SELECT * FROM records WHERE record_id = ?",
                    (episode.record_id,),
                ).fetchone()
            ),
            tuple(
                connection.execute(
                    "SELECT * FROM episodes WHERE record_id = ?",
                    (episode.record_id,),
                ).fetchone()
            ),
            tuple(
                connection.execute(
                    "SELECT * FROM evidence_items WHERE evidence_id = ?",
                    (episode.output_evidence_ids[0],),
                ).fetchone()
            ),
            tuple(
                connection.execute(
                    "SELECT * FROM evidence_inline_text WHERE evidence_id = ?",
                    (episode.output_evidence_ids[0],),
                ).fetchone()
            ),
        )

    before = probe.read(snapshot)
    _, correction, _ = create_correction(
        harness,
        base=629_300,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )
    add_corrects_relationship(
        harness,
        correction_id=correction.record_id,
        episode_id=episode.record_id,
        base=629_400,
    )
    activate_record(
        harness,
        record_id=correction.record_id,
        base=629_500,
        starts_observed=False,
    )
    assert probe.read(snapshot) == before


@pytest.mark.parametrize(
    "failure_step",
    ("evidence", "record", "payload_and_lineage", "evidence_links", "histories"),
)
def test_injected_correction_failure_rolls_back_every_write(
    tmp_path,
    monkeypatch,
    failure_step: str,
) -> None:
    harness = build_c2_harness(tmp_path)
    _, episode, _ = target_episode(harness, base=630_000)
    envelope, payload, support = correction_components(
        harness,
        base=630_300,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )
    repository = harness.persistence.episode_correction_ledger

    def fail(step, connection) -> None:
        if step == failure_step:
            raise RuntimeError(f"injected-{step}")

    monkeypatch.setattr(repository, "_after_write_step", fail)
    with pytest.raises(RuntimeError, match="injected"):
        repository.create_correction(
            envelope,
            payload,
            supporting_evidence_ids=(support[0].evidence_id,),
            lifecycle_transition_id=uid(630_330),
            approval_transition_id=uid(630_331),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
            evidence_items=support,
        )
    probe = SqlProbe(harness.config)
    assert probe.read(
        lambda connection: connection.execute(
            "SELECT 1 FROM records WHERE record_id = ?",
            (payload.record_id,),
        ).fetchone()
    ) is None
    assert probe.read(
        lambda connection: connection.execute(
            "SELECT 1 FROM evidence_items WHERE evidence_id = ?",
            (support[0].evidence_id,),
        ).fetchone()
    ) is None


def test_apprentice_cannot_create_or_activate_correction(
    harness: C2Harness,
) -> None:
    _, episode, _ = target_episode(harness, base=631_000)
    envelope, payload, support = correction_components(
        harness,
        base=631_300,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )
    with pytest.raises(ValidationError, match="principal"):
        harness.persistence.episode_correction_ledger.create_correction(
            envelope,
            payload,
            supporting_evidence_ids=(support[0].evidence_id,),
            lifecycle_transition_id=uid(631_330),
            approval_transition_id=uid(631_331),
            changed_by_principal="apprentice",
            changed_by_entity_id=harness.agent_id,
            evidence_items=support,
        )
    _, correction, _ = create_correction(
        harness,
        base=631_400,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )
    approve_memory_record(harness, record_id=correction.record_id, base=631_500)
    harness.memory.transition_lifecycle(
        correction.record_id,
        transition_id=uid(631_510),
        to_state="approved",
        reason_code="approval_recorded",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    add_corrects_relationship(
        harness,
        correction_id=correction.record_id,
        episode_id=episode.record_id,
        base=631_600,
    )
    with pytest.raises(ValidationError, match="Apprentice"):
        harness.memory.transition_lifecycle(
            correction.record_id,
            transition_id=uid(631_700),
            to_state="active",
            reason_code="apprentice_activation",
            changed_at=NOW,
            changed_by_principal="apprentice",
            changed_by_entity_id=harness.agent_id,
        )


@pytest.mark.parametrize("active", (False, True))
def test_correction_supporting_lineage_is_sealed_after_initial_state(
    tmp_path,
    active: bool,
) -> None:
    harness = build_c2_harness(tmp_path)
    task_id = create_terminal_task(harness, base=629_000, status="completed")
    _, episode, _ = create_episode(
        harness,
        base=629_100,
        task_id=task_id,
    )
    _, correction, _ = create_correction(
        harness,
        base=629_200,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )
    if active:
        add_corrects_relationship(
            harness,
            correction_id=correction.record_id,
            episode_id=episode.record_id,
            base=629_300,
        )
        activate_record(
            harness,
            record_id=correction.record_id,
            base=629_400,
            starts_observed=False,
        )

    late_support = EvidenceItem.inline_text(
        evidence_id=uid(629_500),
        evidence_kind="human_statement",
        content="Late correction support must be rejected.",
        captured_at=NOW,
        captured_by_entity=harness.operator_id,
        sensitivity_class="internal",
    )
    harness.persistence.evidence.create(late_support)

    with pytest.raises(ConflictError):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                INSERT INTO correction_supporting_evidence (
                    record_id, evidence_id, evidence_order
                ) VALUES (?, ?, 1)
                """,
                (correction.record_id, late_support.evidence_id),
            )
        )

    rebuilt = harness.persistence.episode_correction_ledger.reconstruct_correction(
        correction.record_id
    )
    assert len(rebuilt["supporting_evidence_ids"]) == 1
    assert rebuilt["content_hash"] == rebuilt["recomputed_content_hash"]


def test_correction_payload_cannot_be_inserted_after_initial_state(
    harness: C2Harness,
) -> None:
    task_id = create_terminal_task(harness, base=630_000, status="completed")
    _, episode, _ = create_episode(
        harness,
        base=630_100,
        task_id=task_id,
    )
    envelope, payload, _ = correction_components(
        harness,
        base=630_200,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
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
        lifecycle_transition_id=uid(630_230),
        approval_transition_id=uid(630_231),
        changed_at=envelope.created_at,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
        reason_code="finalized_without_payload_for_guard_test",
    )

    with pytest.raises(ConflictError):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                INSERT INTO corrections (
                    record_id, target_episode_id, target_output_evidence_id,
                    problem_statement, corrected_interpretation,
                    correction_category, issued_by_entity_id, issuer_class,
                    severity, canonical_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.record_id,
                    payload.target_episode_id,
                    payload.target_output_evidence_id,
                    payload.problem_statement,
                    payload.corrected_interpretation,
                    payload.correction_category,
                    payload.issued_by_entity_id,
                    payload.issuer_class,
                    payload.severity,
                    payload.canonical_json,
                ),
            )
        )


def test_ordinary_evidence_link_cannot_be_retargeted_into_correction(
    harness: C2Harness,
) -> None:
    task_id = create_terminal_task(harness, base=631_000, status="completed")
    _, episode, _ = create_episode(
        harness,
        base=631_100,
        task_id=task_id,
    )
    _, correction, _ = create_correction(
        harness,
        base=631_200,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )
    ordinary = ordinary_record(631_300, harness.project_scope_id)
    evidence = EvidenceItem.inline_text(
        evidence_id=uid(631_301),
        evidence_kind="human_statement",
        content="Ordinary correction retargeting fixture.",
        captured_at=NOW,
        captured_by_entity=harness.operator_id,
        sensitivity_class="internal",
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
                (correction.record_id, ordinary.record_id, evidence.evidence_id),
            )
        )
