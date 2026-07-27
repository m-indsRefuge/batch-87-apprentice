"""Deterministic B87-I3-C3 fixtures over accepted C2 truth."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.memory import (
    ApprovedLessonPayload,
    FailurePatternPayload,
    LessonCandidatePayload,
    MemoryApprovalGrant,
    MemoryKernel,
    MemoryRelationshipGrant,
    RecordRelationship,
    SuccessPatternPayload,
)
from batch87_apprentice.persistence.contracts import RecordEnvelope
from tests.support.i2_fixtures import NOW, authority, evidence, task, uid
from tests.support.i3c_fixtures import (
    register_evaluation,
    register_nolan_byte_authority,
)
from tests.support.i3c2_fixtures import (
    C2Harness,
    build_c2_harness,
    create_correction,
    create_episode,
    create_terminal_task,
)


@dataclass(frozen=True, slots=True)
class C3Harness:
    c2: C2Harness

    @property
    def config(self):
        return self.c2.config

    @property
    def persistence(self):
        return self.c2.persistence

    @property
    def runtime(self):
        return self.c2.runtime

    @property
    def memory(self) -> MemoryKernel:
        return self.c2.memory

    @property
    def operator_id(self) -> str:
        return self.c2.operator_id

    @property
    def agent_id(self) -> str:
        return self.c2.agent_id

    @property
    def project_scope_id(self) -> str:
        return self.c2.project_scope_id

    @property
    def session_id(self) -> str:
        return self.c2.session_id


def build_c3_harness(
    tmp_path: Path,
    *,
    identifier_start: int = 700_000,
) -> C3Harness:
    return C3Harness(
        c2=build_c2_harness(
            tmp_path,
            identifier_start=identifier_start,
        )
    )


def create_active_analysis_task(harness: C3Harness, *, base: int) -> str:
    authority_evidence = evidence(
        base + 1,
        content="Exact governed Analyse authority for C3 candidate derivation.",
        captured_by_entity=harness.operator_id,
    )
    authority_record = authority(
        harness.c2.c1.i2,
        base + 2,
        evidence_ids=(authority_evidence.evidence_id,),
        permissions=("analyse",),
    )
    harness.runtime.register_authority(
        authority_record,
        evidence_items=(authority_evidence,),
    )
    contract = task(
        harness.c2.c1.i2,
        base,
        authority_ids=(authority_record.authority_record_id,),
        action_class="analyse",
        objective="Derive one inspect-only developmental candidate.",
    )
    result = harness.runtime.evaluate(contract)
    assert result.task_status == "active"
    return contract.task_id


def candidate_components(
    harness: C3Harness,
    *,
    base: int,
    task_id: str,
    episode_id: str,
    correction_id: str,
    proposed_by: str = "apprentice",
) -> tuple[RecordEnvelope, LessonCandidatePayload]:
    payload = LessonCandidatePayload(
        record_id=uid(base),
        source_episode_ids=(episode_id,),
        source_correction_ids=(correction_id,),
        lesson_statement=(
            "Verify the exact governed source before applying its interpretation."
        ),
        intended_scope="project",
        proposer_entity_id=harness.agent_id,
        proposed_by=proposed_by,
        known_limitations=("Applies only to the governed project boundary.",),
    )
    apprentice = proposed_by == "apprentice"
    envelope = RecordEnvelope(
        record_id=payload.record_id,
        record_family="episodic_memory",
        record_type="lesson_candidate",
        schema_version="1.0.0",
        lifecycle_state="candidate",
        approval_status="pending",
        authority_class="agent_proposal",
        certainty_class="inferred",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="project_duration",
        training_eligibility="prohibited",
        created_at=NOW,
        source_kind="model_output" if apprentice else "human_statement",
        provenance_summary="Explicit proposal over exact reviewed C2 lineage.",
        retrieval_policy_json=canonical_json_text(
            {"retrieval_mode": "inspection_only"}
        ),
        deletion_policy_json=canonical_json_text(
            {"deletion_mode": "governed"}
        ),
        agent_write_policy="candidate_only",
        project_scope_id=harness.project_scope_id,
        subject_entity_id=harness.agent_id,
        session_id=harness.session_id,
        task_id=task_id if apprentice else None,
        created_by_entity_id=(
            harness.agent_id if apprentice else harness.operator_id
        ),
    )
    return envelope, payload


def create_candidate(
    harness: C3Harness,
    *,
    base: int,
    task_id: str,
    episode_id: str,
    correction_id: str,
) -> tuple[RecordEnvelope, LessonCandidatePayload]:
    envelope, payload = candidate_components(
        harness,
        base=base,
        task_id=task_id,
        episode_id=episode_id,
        correction_id=correction_id,
    )
    harness.persistence.developmental_derivation.create_lesson_candidate(
        envelope,
        payload,
        lifecycle_transition_id=uid(base + 1),
        approval_transition_id=uid(base + 2),
        changed_by_principal="codex_development_harness",
    )
    return envelope, payload


def review_candidate(
    harness: C3Harness,
    *,
    candidate_id: str,
    transition_id: str,
) -> None:
    harness.memory.transition_lifecycle(
        candidate_id,
        transition_id=transition_id,
        to_state="reviewed",
        reason_code="operator_candidate_review",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )


def approved_lesson_components(
    harness: C3Harness,
    *,
    base: int,
    candidate: LessonCandidatePayload,
    transfer_test_id: str,
) -> tuple[
    RecordEnvelope,
    ApprovedLessonPayload,
    MemoryApprovalGrant,
    MemoryRelationshipGrant,
    RecordRelationship,
]:
    approval_authority, approval_evidence = register_nolan_byte_authority(
        harness.c2.c1,
        base=base + 20,
        content="Exact Nolan-Byte approval for one C3 lesson and relationship.",
    )
    payload = ApprovedLessonPayload(
        record_id=uid(base),
        candidate_record_id=candidate.record_id,
        lesson_statement=candidate.lesson_statement,
        application_conditions=(
            "The governed source and project scope are unchanged.",
        ),
        non_application_conditions=(
            "The source or project scope cannot be verified.",
        ),
        source_episode_ids=candidate.source_episode_ids,
        source_correction_ids=candidate.source_correction_ids,
        transfer_test_evaluation_ids=(transfer_test_id,),
        stability="new",
    )
    envelope = RecordEnvelope(
        record_id=payload.record_id,
        record_family="episodic_memory",
        record_type="approved_lesson",
        schema_version="1.0.0",
        lifecycle_state="reviewed",
        approval_status="pending",
        authority_class="nolan_byte_approved",
        certainty_class="strongly_supported",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="long_term",
        training_eligibility="prohibited",
        created_at=NOW,
        source_kind="derived_record",
        provenance_summary="Separate externally approved lesson from exact candidate.",
        retrieval_policy_json=canonical_json_text(
            {"retrieval_mode": "ordinary"}
        ),
        deletion_policy_json=canonical_json_text(
            {"deletion_mode": "governed"}
        ),
        agent_write_policy="prohibited",
        project_scope_id=harness.project_scope_id,
        subject_entity_id=harness.agent_id,
        created_by_entity_id=harness.operator_id,
    )
    approval_grant = MemoryApprovalGrant(
        grant_id=uid(base + 1),
        record_id=payload.record_id,
        target_status="approved",
        project_scope_id=harness.project_scope_id,
        authority_record_id=approval_authority.authority_record_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        evidence_id=approval_evidence.evidence_id,
    )
    relationship_id = uid(base + 2)
    relationship_grant = MemoryRelationshipGrant(
        grant_id=uid(base + 3),
        relationship_id=relationship_id,
        relationship_type="approved_as",
        source_record_id=candidate.record_id,
        target_record_id=payload.record_id,
        project_scope_id=harness.project_scope_id,
        authority_record_id=approval_authority.authority_record_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        evidence_id=approval_evidence.evidence_id,
    )
    relationship = RecordRelationship(
        relationship_id=relationship_id,
        source_record_id=candidate.record_id,
        target_record_id=payload.record_id,
        relationship_type="approved_as",
        created_at=NOW,
        created_by_principal="operator",
        relationship_grant_id=relationship_grant.grant_id,
        explanation="Exact candidate approved as this separate lesson.",
    )
    return (
        envelope,
        payload,
        approval_grant,
        relationship_grant,
        relationship,
    )


def create_approved_lesson(
    harness: C3Harness,
    *,
    base: int,
    candidate: LessonCandidatePayload,
) -> tuple[RecordEnvelope, ApprovedLessonPayload]:
    transfer = register_evaluation(
        harness.c2.c1,
        base=base + 40,
        evaluation_kind="capability_evaluation",
        claimed=True,
    )
    (
        envelope,
        payload,
        approval_grant,
        relationship_grant,
        relationship,
    ) = approved_lesson_components(
        harness,
        base=base,
        candidate=candidate,
        transfer_test_id=transfer.evaluation_record_id,
    )
    harness.persistence.developmental_derivation.create_approved_lesson(
        envelope,
        payload,
        initial_lifecycle_transition_id=uid(base + 4),
        initial_approval_transition_id=uid(base + 5),
        approval_transition_id=uid(base + 6),
        approved_lifecycle_transition_id=uid(base + 7),
        active_lifecycle_transition_id=uid(base + 8),
        approval_grant=approval_grant,
        relationship_grant=relationship_grant,
        relationship=relationship,
    )
    return envelope, payload


def create_source_bundle(
    harness: C3Harness,
    *,
    base: int,
) -> tuple[str, object, object]:
    source_task = create_terminal_task(
        harness.c2,
        base=base,
        status="completed",
    )
    episode, episode_payload, _ = create_episode(
        harness.c2,
        base=base + 100,
        task_id=source_task,
        outcome="completed",
    )
    correction, correction_payload, _ = create_correction(
        harness.c2,
        base=base + 200,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode_payload.output_evidence_ids[0],
    )
    return source_task, (episode, episode_payload), (
        correction,
        correction_payload,
    )


def failure_pattern_components(
    harness: C3Harness,
    *,
    base: int,
    episode_ids: tuple[str, ...],
) -> tuple[RecordEnvelope, FailurePatternPayload]:
    payload = FailurePatternPayload(
        record_id=uid(base),
        pattern_name="Repeated governed task failure",
        description="Externally reviewable repetition over exact episode identifiers.",
        episode_ids=episode_ids,
        frequency=len(episode_ids),
        severity="material",
        containment_required=True,
        resolution_status="open",
    )
    envelope = _pattern_envelope(
        harness,
        payload.record_id,
        record_type="failure_pattern",
    )
    return envelope, payload


def success_pattern_components(
    harness: C3Harness,
    *,
    base: int,
    episode_ids: tuple[str, ...],
) -> tuple[RecordEnvelope, SuccessPatternPayload]:
    payload = SuccessPatternPayload(
        record_id=uid(base),
        pattern_name="Repeated governed task success",
        description="Externally reviewable repetition across distinct tasks.",
        episode_ids=episode_ids,
        transfer_scope=("same governed project",),
        stability="emerging",
    )
    envelope = _pattern_envelope(
        harness,
        payload.record_id,
        record_type="success_pattern",
    )
    return envelope, payload


def _pattern_envelope(
    harness: C3Harness,
    record_id: str,
    *,
    record_type: str,
) -> RecordEnvelope:
    return RecordEnvelope(
        record_id=record_id,
        record_family="episodic_memory",
        record_type=record_type,
        schema_version="1.0.0",
        lifecycle_state="candidate",
        approval_status="pending",
        authority_class="agent_proposal",
        certainty_class="inferred",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="project_duration",
        training_eligibility="prohibited",
        created_at=NOW,
        source_kind="derived_record",
        provenance_summary="Exact repeated episode lineage without text inference.",
        retrieval_policy_json=canonical_json_text(
            {"retrieval_mode": "ordinary"}
        ),
        deletion_policy_json=canonical_json_text(
            {"deletion_mode": "governed"}
        ),
        agent_write_policy="candidate_only",
        project_scope_id=harness.project_scope_id,
        subject_entity_id=harness.agent_id,
        created_by_entity_id=harness.operator_id,
    )
