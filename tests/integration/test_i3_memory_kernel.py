from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ConflictError, NotFoundError, ValidationError
from batch87_apprentice.memory import (
    EligibilityContext,
    MemoryApprovalGrant,
    MemoryIntegrityInspector,
    MemoryKernel,
    MemoryRelationshipGrant,
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


def create_candidate_memory_type(
    harness,
    *,
    base: int,
    record_family: str,
    record_type: str,
    agent_write_policy: str,
) -> tuple[str, str]:
    record_id = uid(base + 1)
    source = EvidenceItem.inline_text(
        evidence_id=uid(base),
        evidence_kind="human_statement",
        content=f"Deterministic source for {record_family}/{record_type}.",
        captured_at=NOW,
        sensitivity_class="internal",
        privacy_class="none",
        captured_by_entity=harness.operator_id,
    )
    harness.persistence.evidence.create(source)
    envelope = replace(
        _candidate_envelope(harness, record_id),
        record_family=record_family,
        record_type=record_type,
        agent_write_policy=agent_write_policy,
    )
    _insert_memory_envelope(harness, envelope)
    harness.persistence.evidence.link(
        EvidenceLink(
            record_id=record_id,
            evidence_id=source.evidence_id,
            relationship="derived_from",
            explanation="Typed candidate remains separate from source evidence.",
        )
    )
    return record_id, source.evidence_id


def register_memory_authority(
    harness,
    *,
    base: int,
    authority_class: str = "nolan_byte_approved",
    project_scope_id: str | None = None,
    **authority_overrides: object,
) -> tuple[str, str]:
    approval_evidence = evidence(
        base,
        captured_by_entity=harness.operator_id,
        content="Exact scoped memory-governance approval evidence.",
    )
    approval_authority = authority(
        harness,
        base + 1,
        evidence_ids=(approval_evidence.evidence_id,),
        authority_class=authority_class,
        permissions=("observe",),
        project_scope_id=project_scope_id,
        **authority_overrides,
    )
    harness.runtime.register_authority(
        approval_authority,
        evidence_items=(approval_evidence,),
    )
    return approval_authority.authority_record_id, approval_evidence.evidence_id


def register_approval_grant(
    harness,
    memory: MemoryKernel,
    record_id: str,
    *,
    base: int,
    target_status: str = "approved",
    authority_class: str = "nolan_byte_approved",
    project_scope_id: str | None = None,
    expires_at: str | None = None,
    single_use: bool = True,
    **authority_overrides: object,
) -> str:
    authority_id, evidence_id = register_memory_authority(
        harness,
        base=base,
        authority_class=authority_class,
        project_scope_id=project_scope_id,
        **authority_overrides,
    )
    grant_id = uid(base + 2)
    memory.register_approval_grant(
        MemoryApprovalGrant(
            grant_id=grant_id,
            record_id=record_id,
            target_status=target_status,
            project_scope_id=(
                harness.project_scope_id
                if project_scope_id is None
                else project_scope_id
            ),
            authority_record_id=authority_id,
            approved_by_entity_id=harness.operator_id,
            approved_at=NOW,
            expires_at=expires_at,
            single_use=single_use,
            evidence_id=evidence_id,
        )
    )
    return grant_id


def register_relationship_grant(
    harness,
    memory: MemoryKernel,
    *,
    base: int,
    relationship_id: str,
    relationship_type: str,
    source_record_id: str,
    target_record_id: str,
    authority_class: str = "nolan_approved",
    project_scope_id: str | None = None,
    expires_at: str | None = None,
) -> str:
    authority_id, evidence_id = register_memory_authority(
        harness,
        base=base,
        authority_class=authority_class,
        project_scope_id=project_scope_id,
    )
    grant_id = uid(base + 2)
    memory.register_relationship_grant(
        MemoryRelationshipGrant(
            grant_id=grant_id,
            relationship_id=relationship_id,
            relationship_type=relationship_type,
            source_record_id=source_record_id,
            target_record_id=target_record_id,
            project_scope_id=(
                harness.project_scope_id
                if project_scope_id is None
                else project_scope_id
            ),
            authority_record_id=authority_id,
            approved_by_entity_id=harness.operator_id,
            approved_at=NOW,
            expires_at=expires_at,
            evidence_id=evidence_id,
        )
    )
    return grant_id


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
        assert count == 10


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

    approval_grant_id = register_approval_grant(
        harness,
        memory,
        record_id,
        base=81_002,
    )
    memory.transition_approval(
        record_id,
        transition_id=uid(81_005),
        to_status="approved",
        reason_code="exact_memory_approval_grant",
        changed_at=NOW,
        changed_by_entity_id=harness.operator_id,
        approval_grant_id=approval_grant_id,
    )
    memory.transition_lifecycle(
        record_id,
        transition_id=uid(81_006),
        to_state="approved",
        reason_code="approval_recorded",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    memory.transition_lifecycle(
        record_id,
        transition_id=uid(81_007),
        to_state="active",
        reason_code="activation_gate_passed",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )

    decision = memory.assess_eligibility(
        record_id,
        EligibilityContext(
            assessment_id=uid(81_008),
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

    with pytest.raises(ValidationError, match="exact relationship grant"):
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

    relationship_id = uid(86_302)
    relationship_grant_id = register_relationship_grant(
        harness,
        memory,
        base=86_300,
        relationship_id=relationship_id,
        relationship_type="supersedes",
        source_record_id=second_id,
        target_record_id=first_id,
    )
    governed_digest = memory.link_records(
        RecordRelationship(
            relationship_id=relationship_id,
            source_record_id=second_id,
            target_record_id=first_id,
            relationship_type="supersedes",
            created_at=NOW,
            created_by_principal="operator",
            relationship_grant_id=relationship_grant_id,
            explanation="Exact Nolan-authorised same-project supersession.",
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
    authority_id, _ = register_memory_authority(harness, base=87_200)
    unrelated = evidence(
        87_202,
        captured_by_entity=harness.operator_id,
        content="Valid evidence, but not linked to the approval authority.",
    )
    harness.persistence.evidence.create(unrelated)

    with pytest.raises(ValidationError, match="linked to the supplied authority"):
        memory.register_approval_grant(
            MemoryApprovalGrant(
                grant_id=uid(87_203),
                record_id=record_id,
                target_status="approved",
                project_scope_id=harness.project_scope_id,
                authority_record_id=authority_id,
                approved_by_entity_id=harness.operator_id,
                approved_at=NOW,
                evidence_id=unrelated.evidence_id,
            )
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
    authority_id, evidence_id = register_memory_authority(
        harness,
        base=90_200,
        authority_class="nolan_byte_approved",
        **authority_overrides,
    )

    with pytest.raises(ValidationError, match="inactive, out of scope, or type-insufficient"):
        memory.register_approval_grant(
            MemoryApprovalGrant(
                grant_id=uid(90_202),
                record_id=record_id,
                target_status="approved",
                project_scope_id=harness.project_scope_id,
                authority_record_id=authority_id,
                approved_by_entity_id=harness.operator_id,
                approved_at=NOW,
                evidence_id=evidence_id,
            )
        )

def test_generic_observe_authority_cannot_directly_approve_memory(tmp_path) -> None:
    harness = build_harness(tmp_path)
    record_id, _ = create_candidate_memory(harness, base=91_000)
    memory = MemoryKernel(harness.config)
    memory.register_initial_state(
        record_id,
        lifecycle_transition_id=uid(91_100),
        approval_transition_id=uid(91_101),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    authority_id, _ = register_memory_authority(
        harness,
        base=91_200,
        authority_class="nolan_byte_approved",
    )

    with pytest.raises(NotFoundError, match="approval grant not found"):
        memory.transition_approval(
            record_id,
            transition_id=uid(91_202),
            to_status="approved",
            reason_code="generic_observe_authority_attempt",
            changed_at=NOW,
            changed_by_entity_id=harness.operator_id,
            approval_grant_id=authority_id,
        )


def test_project_policy_cannot_approve_architecture_decision(tmp_path) -> None:
    harness = build_harness(tmp_path)
    record_id, _ = create_candidate_memory_type(
        harness,
        base=92_000,
        record_family="construct_memory",
        record_type="architecture_decision",
        agent_write_policy="prohibited",
    )
    memory = MemoryKernel(harness.config)
    authority_id, evidence_id = register_memory_authority(
        harness,
        base=92_100,
        authority_class="approved_project_policy",
    )

    with pytest.raises(ValidationError, match="type-insufficient"):
        memory.register_approval_grant(
            MemoryApprovalGrant(
                grant_id=uid(92_102),
                record_id=record_id,
                target_status="approved",
                project_scope_id=harness.project_scope_id,
                authority_record_id=authority_id,
                approved_by_entity_id=harness.operator_id,
                approved_at=NOW,
                evidence_id=evidence_id,
            )
        )


@pytest.mark.parametrize(
    ("record_family", "record_type", "agent_write_policy"),
    (
        ("construct_memory", "construct_doctrine", "prohibited"),
        ("episodic_memory", "approved_lesson", "prohibited"),
    ),
)
def test_validated_system_evidence_cannot_approve_nolan_governed_memory(
    tmp_path,
    record_family: str,
    record_type: str,
    agent_write_policy: str,
) -> None:
    harness = build_harness(tmp_path)
    record_id, _ = create_candidate_memory_type(
        harness,
        base=93_000,
        record_family=record_family,
        record_type=record_type,
        agent_write_policy=agent_write_policy,
    )
    memory = MemoryKernel(harness.config)
    authority_id, evidence_id = register_memory_authority(
        harness,
        base=93_100,
        authority_class="validated_system_evidence",
    )

    with pytest.raises(ValidationError, match="type-insufficient"):
        memory.register_approval_grant(
            MemoryApprovalGrant(
                grant_id=uid(93_102),
                record_id=record_id,
                target_status="approved",
                project_scope_id=harness.project_scope_id,
                authority_record_id=authority_id,
                approved_by_entity_id=harness.operator_id,
                approved_at=NOW,
                evidence_id=evidence_id,
            )
        )


def test_approval_grant_is_bound_to_one_exact_record(tmp_path) -> None:
    harness = build_harness(tmp_path)
    first_id, _ = create_candidate_memory(harness, base=94_000)
    second_id, _ = create_candidate_memory(harness, base=94_100)
    memory = MemoryKernel(harness.config)
    for offset, record_id in enumerate((first_id, second_id)):
        memory.register_initial_state(
            record_id,
            lifecycle_transition_id=uid(94_200 + offset * 2),
            approval_transition_id=uid(94_201 + offset * 2),
            changed_at=NOW,
            changed_by_principal="codex_development_harness",
            changed_by_entity_id=harness.participant_id,
            reason_code="candidate_registered",
        )
    grant_id = register_approval_grant(
        harness,
        memory,
        first_id,
        base=94_300,
    )

    with pytest.raises(ValidationError, match="exact transition"):
        memory.transition_approval(
            second_id,
            transition_id=uid(94_303),
            to_status="approved",
            reason_code="wrong_record_attempt",
            changed_at=NOW,
            changed_by_entity_id=harness.operator_id,
            approval_grant_id=grant_id,
        )


def test_expired_approval_grant_fails_closed(tmp_path) -> None:
    harness = build_harness(tmp_path)
    record_id, _ = create_candidate_memory(harness, base=95_000)
    memory = MemoryKernel(harness.config)
    memory.register_initial_state(
        record_id,
        lifecycle_transition_id=uid(95_100),
        approval_transition_id=uid(95_101),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    authority_id, evidence_id = register_memory_authority(
        harness,
        base=95_200,
        authority_class="nolan_byte_approved",
    )
    grant = MemoryApprovalGrant(
        grant_id=uid(95_202),
        record_id=record_id,
        target_status="approved",
        project_scope_id=harness.project_scope_id,
        authority_record_id=authority_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=EARLIER,
        expires_at=EARLIER,
        evidence_id=evidence_id,
    )
    memory.register_approval_grant(grant)

    with pytest.raises(ValidationError, match="exact transition"):
        memory.transition_approval(
            record_id,
            transition_id=uid(95_203),
            to_status="approved",
            reason_code="expired_grant_attempt",
            changed_at=NOW,
            changed_by_entity_id=harness.operator_id,
            approval_grant_id=grant.grant_id,
        )


def test_single_use_approval_grant_consumption_is_append_only(tmp_path) -> None:
    harness = build_harness(tmp_path)
    record_id, _ = create_candidate_memory(harness, base=96_000)
    memory = MemoryKernel(harness.config)
    memory.register_initial_state(
        record_id,
        lifecycle_transition_id=uid(96_100),
        approval_transition_id=uid(96_101),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    grant_id = register_approval_grant(
        harness,
        memory,
        record_id,
        base=96_200,
    )
    transition_id = uid(96_203)
    memory.transition_approval(
        record_id,
        transition_id=transition_id,
        to_status="approved",
        reason_code="consume_exact_grant",
        changed_at=NOW,
        changed_by_entity_id=harness.operator_id,
        approval_grant_id=grant_id,
    )
    consumed = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT consumed_at, consumed_by_transition_id
            FROM memory_approval_grants WHERE grant_id = ?
            """,
            (grant_id,),
        ).fetchone()
    )
    assert consumed["consumed_at"] == NOW
    assert consumed["consumed_by_transition_id"] == transition_id

    with pytest.raises(ConflictError):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                UPDATE memory_approval_grants
                SET consumed_at = ?, consumed_by_transition_id = ?
                WHERE grant_id = ?
                """,
                (NOW, uid(96_204), grant_id),
            )
        )


def test_revoked_approval_authority_invalidates_unconsumed_grant(tmp_path) -> None:
    harness = build_harness(tmp_path)
    record_id, _ = create_candidate_memory(harness, base=97_000)
    memory = MemoryKernel(harness.config)
    memory.register_initial_state(
        record_id,
        lifecycle_transition_id=uid(97_100),
        approval_transition_id=uid(97_101),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    authority_id, evidence_id = register_memory_authority(
        harness,
        base=97_200,
        authority_class="nolan_byte_approved",
    )
    grant = MemoryApprovalGrant(
        grant_id=uid(97_202),
        record_id=record_id,
        target_status="approved",
        project_scope_id=harness.project_scope_id,
        authority_record_id=authority_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        evidence_id=evidence_id,
    )
    memory.register_approval_grant(grant)
    harness.runtime.revoke_authority(
        authority_id,
        revoked_by_entity_id=harness.operator_id,
        reason="Operator revoked memory approval authority.",
        provenance_json=canonical_json_text({"source": "repair fixture"}),
    )

    with pytest.raises(ValidationError, match="revoked"):
        memory.transition_approval(
            record_id,
            transition_id=uid(97_203),
            to_status="approved",
            reason_code="revoked_grant_attempt",
            changed_at=NOW,
            changed_by_entity_id=harness.operator_id,
            approval_grant_id=grant.grant_id,
        )


def test_wrong_scope_authority_cannot_create_approval_grant(tmp_path) -> None:
    harness = build_harness(tmp_path)
    record_id, _ = create_candidate_memory(harness, base=98_000)
    memory = MemoryKernel(harness.config)
    approval_evidence = evidence(
        98_100,
        captured_by_entity=harness.operator_id,
        content="Wrong-project approval evidence.",
    )
    approval_authority = authority(
        harness,
        98_101,
        evidence_ids=(approval_evidence.evidence_id,),
        authority_class="nolan_byte_approved",
        permissions=("observe",),
        project_scope_id=harness.other_project_scope_id,
        scope_id=harness.other_project_scope_id,
    )
    harness.runtime.register_authority(
        approval_authority,
        evidence_items=(approval_evidence,),
    )

    with pytest.raises(ValidationError, match="out of scope"):
        memory.register_approval_grant(
            MemoryApprovalGrant(
                grant_id=uid(98_102),
                record_id=record_id,
                target_status="approved",
                project_scope_id=harness.project_scope_id,
                authority_record_id=approval_authority.authority_record_id,
                approved_by_entity_id=harness.operator_id,
                approved_at=NOW,
                evidence_id=approval_evidence.evidence_id,
            )
        )


def test_authority_bearing_relationship_rejects_non_nolan_grant(tmp_path) -> None:
    harness = build_harness(tmp_path)
    first_id, _ = create_candidate_memory(harness, base=99_000)
    second_id, _ = create_candidate_memory(harness, base=99_100)
    memory = MemoryKernel(harness.config)
    relationship_id = uid(99_200)
    authority_id, evidence_id = register_memory_authority(
        harness,
        base=99_300,
        authority_class="approved_project_policy",
    )

    with pytest.raises(ValidationError, match="type-insufficient"):
        memory.register_relationship_grant(
            MemoryRelationshipGrant(
                grant_id=uid(99_302),
                relationship_id=relationship_id,
                relationship_type="supersedes",
                source_record_id=second_id,
                target_record_id=first_id,
                project_scope_id=harness.project_scope_id,
                authority_record_id=authority_id,
                approved_by_entity_id=harness.operator_id,
                approved_at=NOW,
                evidence_id=evidence_id,
            )
        )



def test_lesson_candidate_exclusion_is_reconstructable_and_approved_lesson_is_eligible(
    tmp_path,
) -> None:
    harness = build_harness(tmp_path)
    task_id = create_active_task(harness, base=100_000)
    memory = MemoryKernel(harness.config)

    candidate_id, _ = create_candidate_memory_type(
        harness,
        base=100_100,
        record_family="episodic_memory",
        record_type="lesson_candidate",
        agent_write_policy="candidate_only",
    )
    memory.register_initial_state(
        candidate_id,
        lifecycle_transition_id=uid(100_300),
        approval_transition_id=uid(100_301),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    memory.transition_lifecycle(
        candidate_id,
        transition_id=uid(100_302),
        to_state="reviewed",
        reason_code="provenance_review_complete",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )

    with pytest.raises(ValidationError, match="cannot be approved in place"):
        register_approval_grant(
            harness,
            memory,
            candidate_id,
            base=100_400,
        )

    candidate_decision = memory.assess_eligibility(
        candidate_id,
        EligibilityContext(
            assessment_id=uid(100_600),
            task_id=task_id,
            task_project_scope_id=harness.project_scope_id,
            requested_domain="self_episodic",
            evaluated_at=NOW,
            allowed_sensitivity_classes=("public", "internal"),
            allowed_privacy_classes=("none",),
        ),
    )
    assert candidate_decision.eligible is False
    assert candidate_decision.reason_codes[0] == "ordinary_retrieval_prohibited"
    assert "lifecycle_not_active" in candidate_decision.reason_codes
    assert "approval_not_eligible" in candidate_decision.reason_codes

    candidate_reconstruction = memory.reconstruct(candidate_id)
    candidate_assessment = candidate_reconstruction["eligibility_assessments"][0]
    assert candidate_assessment["eligible"] == 0
    assert candidate_assessment["reason_codes"][0] == "ordinary_retrieval_prohibited"
    assert candidate_assessment["decision_hash"] == candidate_decision.decision_hash

    approved_lesson_id, _ = create_candidate_memory_type(
        harness,
        base=100_200,
        record_family="episodic_memory",
        record_type="approved_lesson",
        agent_write_policy="prohibited",
    )
    memory.register_initial_state(
        approved_lesson_id,
        lifecycle_transition_id=uid(100_310),
        approval_transition_id=uid(100_311),
        changed_at=NOW,
        changed_by_principal="codex_development_harness",
        changed_by_entity_id=harness.participant_id,
        reason_code="candidate_registered",
    )
    memory.transition_lifecycle(
        approved_lesson_id,
        transition_id=uid(100_312),
        to_state="reviewed",
        reason_code="provenance_review_complete",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    approved_grant_id = register_approval_grant(
        harness,
        memory,
        approved_lesson_id,
        base=100_410,
    )
    memory.transition_approval(
        approved_lesson_id,
        transition_id=uid(100_413),
        to_status="approved",
        reason_code="exact_memory_approval_grant",
        changed_at=NOW,
        changed_by_entity_id=harness.operator_id,
        approval_grant_id=approved_grant_id,
    )
    memory.transition_lifecycle(
        approved_lesson_id,
        transition_id=uid(100_510),
        to_state="approved",
        reason_code="approval_recorded",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    memory.transition_lifecycle(
        approved_lesson_id,
        transition_id=uid(100_511),
        to_state="active",
        reason_code="activation_gate_passed",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )

    approved_decision = memory.assess_eligibility(
        approved_lesson_id,
        EligibilityContext(
            assessment_id=uid(100_601),
            task_id=task_id,
            task_project_scope_id=harness.project_scope_id,
            requested_domain="self_episodic",
            evaluated_at=NOW,
            allowed_sensitivity_classes=("public", "internal"),
            allowed_privacy_classes=("none",),
        ),
    )
    assert approved_decision.eligible is True
    assert approved_decision.reason_codes == ()
    assert MemoryIntegrityInspector(harness.config).inspect().ok is True
