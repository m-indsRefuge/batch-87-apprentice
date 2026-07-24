from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ConflictError, ValidationError
from batch87_apprentice.memory import (
    EligibilityContext,
    MemoryIntegrityInspector,
    MemoryKernel,
    RecordRelationship,
)
from batch87_apprentice.persistence.connection import open_connection
from batch87_apprentice.persistence.contracts import (
    EvidenceItem,
    EvidenceLink,
    RecordEnvelope,
    record_content_hash,
)
from tests.support.i2_fixtures import (
    EARLIER,
    NOW,
    authority,
    build_harness,
    evidence,
    task,
    uid,
)
from tests.support.sql_probe import SqlProbe


def _insert_memory_envelope(harness, envelope: RecordEnvelope) -> None:
    values = envelope.database_values(content_hash=record_content_hash(envelope))
    columns = tuple(values)
    placeholders = ", ".join(f":{column}" for column in columns)
    SqlProbe(harness.config).write(
        lambda connection: connection.execute(
            f"INSERT INTO records ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
    )


def _candidate_envelope(harness, record_id: str) -> RecordEnvelope:
    return RecordEnvelope(
        record_id=record_id,
        record_family="construct_memory",
        record_type="project_state",
        schema_version="1.0.0",
        lifecycle_state="candidate",
        approval_status="pending",
        authority_class="agent_proposal",
        certainty_class="inferred",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="project_duration",
        training_eligibility="ineligible",
        created_at=NOW,
        source_kind="human_statement",
        provenance_summary="Deterministic I3-A candidate fixture.",
        retrieval_policy_json=canonical_json_text(
            {
                "retrieval_mode": "ordinary",
                "allowed_project_scope_ids": [harness.project_scope_id],
            }
        ),
        deletion_policy_json=canonical_json_text(
            {"deletion_mode": "governed"}
        ),
        agent_write_policy="candidate_only",
        project_scope_id=harness.project_scope_id,
        subject_entity_id=harness.participant_id,
        created_by_entity_id=harness.operator_id,
        effective_from=NOW,
    )


def create_active_task(harness, *, base: int = 70_000) -> str:
    authority_evidence = evidence(
        base,
        captured_by_entity=harness.operator_id,
    )
    record = authority(
        harness,
        base + 1,
        evidence_ids=(authority_evidence.evidence_id,),
    )
    harness.runtime.register_authority(
        record,
        evidence_items=(authority_evidence,),
    )
    contract = task(
        harness,
        base + 2,
        authority_ids=(record.authority_record_id,),
        required_evidence_ids=(authority_evidence.evidence_id,),
    )
    result = harness.runtime.evaluate(contract)
    assert result.decision.outcome == "allow"
    return contract.task_id


def create_candidate_memory(harness, *, base: int = 80_000) -> tuple[str, str]:
    memory_evidence = EvidenceItem.inline_text(
        evidence_id=uid(base),
        evidence_kind="human_statement",
        content="Approved project-state source.",
        captured_at=NOW,
        sensitivity_class="internal",
        privacy_class="none",
        captured_by_entity=harness.operator_id,
    )
    harness.persistence.evidence.create(memory_evidence)
    record_id = uid(base + 1)
    envelope = _candidate_envelope(harness, record_id)
    _insert_memory_envelope(harness, envelope)
    harness.persistence.evidence.link(
        EvidenceLink(
            record_id=record_id,
            evidence_id=memory_evidence.evidence_id,
            relationship="derived_from",
            explanation="Candidate project state is derived from human evidence.",
        )
    )
    return record_id, memory_evidence.evidence_id


def register_memory_authority(harness, *, base: int) -> tuple[str, str]:
    approval_evidence = evidence(
        base,
        captured_by_entity=harness.operator_id,
        content="Nolan authorises the scoped memory decision.",
    )
    approval_authority = authority(
        harness,
        base + 1,
        evidence_ids=(approval_evidence.evidence_id,),
        authority_class="nolan_approved",
        permissions=("observe",),
    )
    harness.runtime.register_authority(
        approval_authority,
        evidence_items=(approval_evidence,),
    )
    return approval_authority.authority_record_id, approval_evidence.evidence_id


def test_i3a_migration_installs_exactly_three_domains(tmp_path) -> None:
    harness = build_harness(tmp_path)
    with open_connection(harness.config) as connection:
        domains = tuple(
            row["memory_domain"]
            for row in connection.execute(
                "SELECT memory_domain FROM memory_domains ORDER BY memory_domain"
            )
        )
        assert domains == (
            "construct_relational",
            "self_episodic",
            "session_task",
        )
        count = connection.execute(
            "SELECT COUNT(*) AS value FROM schema_migrations"
        ).fetchone()["value"]
        assert count == 5


def test_memory_state_transitions_and_eligibility_are_reconstructable(tmp_path) -> None:
    harness = build_harness(tmp_path)
    task_id = create_active_task(harness)
    record_id, _ = create_candidate_memory(harness)
    memory = MemoryKernel(harness.config)

    memory.register_initial_state(
        record_id,
        lifecycle_transition_id=uid(81_000),
        approval_transition_id=uid(89_000),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    memory.transition_lifecycle(
        record_id,
        transition_id=uid(81_001),
        to_state="reviewed",
        reason_code="provenance_review_complete",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )

    approval_authority_id, approval_evidence_id = register_memory_authority(
        harness,
        base=81_002,
    )
    memory.transition_approval(
        record_id,
        transition_id=uid(81_004),
        to_status="approved",
        reason_code="nolan_memory_approval",
        changed_at=NOW,
        changed_by_entity_id=harness.operator_id,
        authority_record_id=approval_authority_id,
        approval_evidence_id=approval_evidence_id,
    )
    memory.transition_lifecycle(
        record_id,
        transition_id=uid(81_005),
        to_state="approved",
        reason_code="approval_recorded",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    memory.transition_lifecycle(
        record_id,
        transition_id=uid(81_006),
        to_state="active",
        reason_code="activation_gate_passed",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )

    decision = memory.assess_eligibility(
        record_id,
        EligibilityContext(
            assessment_id=uid(81_007),
            task_id=task_id,
            task_project_scope_id=harness.project_scope_id,
            requested_domain="construct_relational",
            evaluated_at=NOW,
            allowed_sensitivity_classes=("public", "internal"),
            allowed_privacy_classes=("none",),
        ),
    )
    assert decision.eligible is True
    assert decision.reason_codes == ()

    reconstruction = memory.reconstruct(record_id)
    assert reconstruction["memory_domain"] == "construct_relational"
    assert [row["to_state"] for row in reconstruction["lifecycle_transitions"]] == [
        "candidate",
        "reviewed",
        "approved",
        "active",
    ]
    assert [row["to_status"] for row in reconstruction["approval_transitions"]] == [
        "pending",
        "approved",
    ]
    assessment = reconstruction["eligibility_assessments"][0]
    assert assessment["eligible"] == 1
    assert assessment["record_snapshot"]["record_id"] == record_id
    assert assessment["context"]["task_id"] == task_id
    assert assessment["record_snapshot_hash"] == decision.record_snapshot_hash
    assert MemoryIntegrityInspector(harness.config).inspect().ok is True


def test_candidate_cannot_jump_directly_to_active(tmp_path) -> None:
    harness = build_harness(tmp_path)
    record_id, _ = create_candidate_memory(harness)
    memory = MemoryKernel(harness.config)
    memory.register_initial_state(
        record_id,
        lifecycle_transition_id=uid(82_000),
        approval_transition_id=uid(89_000),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    with pytest.raises(ValidationError):
        memory.transition_lifecycle(
            record_id,
            transition_id=uid(82_001),
            to_state="active",
            reason_code="invalid_direct_activation",
            changed_at=NOW,
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )


def test_direct_state_mutation_is_rejected(tmp_path) -> None:
    harness = build_harness(tmp_path)
    record_id, _ = create_candidate_memory(harness)
    memory = MemoryKernel(harness.config)
    memory.register_initial_state(
        record_id,
        lifecycle_transition_id=uid(83_000),
        approval_transition_id=uid(89_000),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    with pytest.raises(ConflictError):
        def mutate(connection: sqlite3.Connection) -> None:
            connection.execute(
                "UPDATE records SET lifecycle_state = 'active' WHERE record_id = ?",
                (record_id,),
            )
        memory._kernel.write(mutate)


def test_memory_transition_history_is_immutable(tmp_path) -> None:
    harness = build_harness(tmp_path)
    record_id, _ = create_candidate_memory(harness)
    memory = MemoryKernel(harness.config)
    transition_id = uid(84_000)
    memory.register_initial_state(
        record_id,
        lifecycle_transition_id=transition_id,
        approval_transition_id=uid(89_000),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    with pytest.raises(ConflictError):
        def mutate(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                UPDATE memory_record_lifecycle_transitions
                SET reason_code = 'rewritten'
                WHERE transition_id = ?
                """,
                (transition_id,),
            )
        memory._kernel.write(mutate)


def test_generic_record_repository_rejects_memory_types(tmp_path) -> None:
    harness = build_harness(tmp_path)
    envelope = _candidate_envelope(harness, uid(85_000))
    with pytest.raises(ValidationError, match="domain repository"):
        harness.persistence.records.create(envelope)


def test_initial_memory_contract_rejects_active_creation(tmp_path) -> None:
    harness = build_harness(tmp_path)
    envelope = replace(
        _candidate_envelope(harness, uid(85_001)),
        lifecycle_state="active",
        approval_status="approved",
        authority_class="approved_memory",
    )
    with pytest.raises(ConflictError):
        _insert_memory_envelope(harness, envelope)


def test_record_relationships_are_typed_and_governed(tmp_path) -> None:
    harness = build_harness(tmp_path)
    first_id, _ = create_candidate_memory(harness, base=86_000)
    second_id, _ = create_candidate_memory(harness, base=86_100)
    memory = MemoryKernel(harness.config)
    memory.register_initial_state(
        first_id,
        lifecycle_transition_id=uid(86_200),
        approval_transition_id=uid(86_201),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    memory.register_initial_state(
        second_id,
        lifecycle_transition_id=uid(86_202),
        approval_transition_id=uid(86_203),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )

    digest = memory.link_records(
        RecordRelationship(
            relationship_id=uid(86_204),
            source_record_id=second_id,
            target_record_id=first_id,
            relationship_type="derived_from",
            created_at=NOW,
            created_by_principal="apprentice",
            explanation="Candidate relationship only; no authority is created.",
        )
    )
    assert len(digest) == 64

    with pytest.raises(ValidationError, match="explicit authority"):
        memory.link_records(
            RecordRelationship(
                relationship_id=uid(86_205),
                source_record_id=second_id,
                target_record_id=first_id,
                relationship_type="supersedes",
                created_at=NOW,
                created_by_principal="operator",
                explanation="A supersession cannot be created without authority.",
            )
        )

    relationship_authority_id, _ = register_memory_authority(
        harness,
        base=86_300,
    )
    governed_digest = memory.link_records(
        RecordRelationship(
            relationship_id=uid(86_302),
            source_record_id=second_id,
            target_record_id=first_id,
            relationship_type="supersedes",
            created_at=NOW,
            created_by_principal="operator",
            authority_record_id=relationship_authority_id,
            explanation="Operator-authorised same-project supersession relationship.",
        )
    )
    assert len(governed_digest) == 64
    assert MemoryIntegrityInspector(harness.config).inspect().ok is True



def test_memory_approval_rejects_evidence_not_linked_to_authority(tmp_path) -> None:
    harness = build_harness(tmp_path)
    record_id, _ = create_candidate_memory(harness, base=87_000)
    memory = MemoryKernel(harness.config)
    memory.register_initial_state(
        record_id,
        lifecycle_transition_id=uid(87_100),
        approval_transition_id=uid(87_101),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    memory.transition_lifecycle(
        record_id,
        transition_id=uid(87_102),
        to_state="reviewed",
        reason_code="review_complete",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    authority_id, _ = register_memory_authority(harness, base=87_200)
    unrelated = evidence(
        87_202,
        captured_by_entity=harness.operator_id,
        content="Valid evidence, but not linked to the approval authority.",
    )
    harness.persistence.evidence.create(unrelated)

    with pytest.raises(ValidationError, match="linked to the supplied authority"):
        memory.transition_approval(
            record_id,
            transition_id=uid(87_203),
            to_status="approved",
            reason_code="invalid_evidence_link",
            changed_at=NOW,
            changed_by_entity_id=harness.operator_id,
            authority_record_id=authority_id,
            approval_evidence_id=unrelated.evidence_id,
        )


def test_eligibility_snapshot_corruption_is_detected_independently(tmp_path) -> None:
    harness = build_harness(tmp_path)
    task_id = create_active_task(harness, base=88_000)
    record_id, _ = create_candidate_memory(harness, base=88_100)
    memory = MemoryKernel(harness.config)
    memory.register_initial_state(
        record_id,
        lifecycle_transition_id=uid(88_200),
        approval_transition_id=uid(88_201),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    # Candidate state is sufficient to create a deterministic exclusion assessment.
    decision = memory.assess_eligibility(
        record_id,
        EligibilityContext(
            assessment_id=uid(88_202),
            task_id=task_id,
            task_project_scope_id=harness.project_scope_id,
            requested_domain="construct_relational",
            evaluated_at=NOW,
            allowed_sensitivity_classes=("public", "internal"),
            allowed_privacy_classes=("none",),
        ),
    )
    assert decision.eligible is False
    assert MemoryIntegrityInspector(harness.config).inspect().ok is True

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("memory_eligibility_assessments_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE memory_eligibility_assessments
            SET record_snapshot_json = ?
            WHERE assessment_id = ?
            """,
            (
                canonical_json_text(
                    {
                        "record_id": record_id,
                        "record_family": "construct_memory",
                        "record_type": "project_state",
                        "project_scope_id": harness.project_scope_id,
                        "lifecycle_state": "active",
                        "approval_status": "approved",
                        "integrity_status": "valid",
                        "sensitivity_class": "internal",
                        "privacy_class": "none",
                        "effective_from": NOW,
                        "effective_until": None,
                        "superseded_by_record_id": None,
                        "retrieval_policy_json": canonical_json_text(
                            {"retrieval_mode": "ordinary"}
                        ),
                    }
                ),
                decision.assessment_id,
            ),
        ),
    )
    report = MemoryIntegrityInspector(harness.config).inspect()
    assert report.ok is False
    assert "I3A-ELIGIBILITY-SNAPSHOT" in {
        finding.code for finding in report.findings
    }


def test_transition_column_corruption_is_detected_against_canonical_record(tmp_path) -> None:
    harness = build_harness(tmp_path)
    record_id, _ = create_candidate_memory(harness, base=89_000)
    memory = MemoryKernel(harness.config)
    transition_id = uid(89_100)
    memory.register_initial_state(
        record_id,
        lifecycle_transition_id=transition_id,
        approval_transition_id=uid(89_101),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("memory_lifecycle_transitions_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE memory_record_lifecycle_transitions
            SET reason_code = 'corrupted_without_rehash'
            WHERE transition_id = ?
            """,
            (transition_id,),
        ),
    )
    report = MemoryIntegrityInspector(harness.config).inspect()
    assert report.ok is False
    assert "I3A-CANONICAL-COLUMN-MISMATCH" in {
        finding.code for finding in report.findings
    }



@pytest.mark.parametrize(
    "authority_overrides",
    (
        {"effect": "deny"},
        {"effective_from": EARLIER, "effective_until": EARLIER},
    ),
)
def test_memory_approval_requires_allowing_current_authority(
    tmp_path,
    authority_overrides: dict[str, object],
) -> None:
    harness = build_harness(tmp_path)
    record_id, _ = create_candidate_memory(harness, base=90_000)
    memory = MemoryKernel(harness.config)
    memory.register_initial_state(
        record_id,
        lifecycle_transition_id=uid(90_100),
        approval_transition_id=uid(90_101),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    memory.transition_lifecycle(
        record_id,
        transition_id=uid(90_102),
        to_state="reviewed",
        reason_code="review_complete",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    approval_evidence = evidence(
        90_200,
        captured_by_entity=harness.operator_id,
        content="Evidence for a deliberately ineligible authority fixture.",
    )
    approval_authority = authority(
        harness,
        90_201,
        evidence_ids=(approval_evidence.evidence_id,),
        authority_class="nolan_approved",
        permissions=("observe",),
        **authority_overrides,
    )
    harness.runtime.register_authority(
        approval_authority,
        evidence_items=(approval_evidence,),
    )

    with pytest.raises(ValidationError, match="inactive or insufficient"):
        memory.transition_approval(
            record_id,
            transition_id=uid(90_202),
            to_status="approved",
            reason_code="invalid_authority",
            changed_at=NOW,
            changed_by_entity_id=harness.operator_id,
            authority_record_id=approval_authority.authority_record_id,
            approval_evidence_id=approval_evidence.evidence_id,
        )
