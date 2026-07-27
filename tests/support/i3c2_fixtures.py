"""Deterministic B87-I3-C2 fixtures over accepted I2/C1 truth."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.memory import (
    CorrectionPayload,
    EpisodePayload,
    MemoryApprovalGrant,
    MemoryKernel,
    MemoryRelationshipGrant,
    RecordRelationship,
)
from batch87_apprentice.persistence.contracts import EvidenceItem, RecordEnvelope
from tests.support.i2_fixtures import NOW, authority, evidence, task, uid
from tests.support.i3c_fixtures import (
    C1Harness,
    build_c1_harness,
    register_evaluation,
    register_nolan_byte_authority,
)


@dataclass(frozen=True, slots=True)
class C2Harness:
    c1: C1Harness

    @property
    def config(self):
        return self.c1.config

    @property
    def persistence(self):
        return self.c1.persistence

    @property
    def runtime(self):
        return self.c1.runtime

    @property
    def memory(self) -> MemoryKernel:
        return MemoryKernel(self.config)

    @property
    def operator_id(self) -> str:
        return self.c1.operator_id

    @property
    def agent_id(self) -> str:
        return self.c1.agent_id

    @property
    def project_scope_id(self) -> str:
        return self.c1.project_scope_id

    @property
    def session_id(self) -> str:
        return self.c1.i2.session_id


def build_c2_harness(
    tmp_path: Path,
    *,
    identifier_start: int = 500_000,
) -> C2Harness:
    return C2Harness(
        c1=build_c1_harness(
            tmp_path,
            identifier_start=identifier_start,
        )
    )


def c2_evidence(
    number: int,
    *,
    content: str,
    evidence_kind: str = "test_report",
    captured_by_entity: str | None = None,
) -> EvidenceItem:
    return EvidenceItem.inline_text(
        evidence_id=uid(number),
        evidence_kind=evidence_kind,
        content=content,
        captured_at=NOW,
        sensitivity_class="internal",
        privacy_class="none",
        captured_by_entity=captured_by_entity,
    )


def create_terminal_task(
    harness: C2Harness,
    *,
    base: int,
    status: str = "completed",
) -> str:
    if status == "stopped":
        contract = task(
            harness.c1.i2,
            base,
            authority_ids=(),
        )
        result = harness.runtime.evaluate(contract)
        assert result.task_status == "stopped"
        return contract.task_id
    authority_evidence = evidence(
        base + 1,
        captured_by_entity=harness.operator_id,
    )
    authority_record = authority(
        harness.c1.i2,
        base + 2,
        evidence_ids=(authority_evidence.evidence_id,),
    )
    harness.runtime.register_authority(
        authority_record,
        evidence_items=(authority_evidence,),
    )
    contract = task(
        harness.c1.i2,
        base,
        authority_ids=(authority_record.authority_record_id,),
    )
    result = harness.runtime.evaluate(contract)
    assert result.task_status == "active"
    if status == "active":
        return contract.task_id
    if status not in {"completed", "failed"}:
        raise ValueError("status must be active, completed, stopped, or failed")
    harness.runtime.transition_task(
        contract.task_id,
        to_status=status,
        reason_code=f"fixture_{status}",
    )
    return contract.task_id


def episode_components(
    harness: C2Harness,
    *,
    base: int,
    task_id: str | None,
    outcome: str = "completed",
    episode_kind: str = "task",
    input_count: int = 1,
    output_count: int = 1,
    evaluation_record_ids: tuple[str, ...] = (),
    project_scope_id: str | None = None,
    session_id: str | None = None,
    created_at: str = NOW,
) -> tuple[RecordEnvelope, EpisodePayload, tuple[EvidenceItem, ...]]:
    input_items = tuple(
        c2_evidence(
            base + 10 + index,
            content=f"Exact episode input {index}.",
            captured_by_entity=harness.operator_id,
        )
        for index in range(input_count)
    )
    output_items = tuple(
        c2_evidence(
            base + 20 + index,
            content=f"Exact episode output {index}.",
            evidence_kind="model_output",
            captured_by_entity=harness.operator_id,
        )
        for index in range(output_count)
    )
    payload = EpisodePayload(
        record_id=uid(base),
        episode_kind=episode_kind,
        summary="Exact governed occurrence without inferred lesson.",
        outcome=outcome,
        input_evidence_ids=tuple(item.evidence_id for item in input_items),
        output_evidence_ids=tuple(item.evidence_id for item in output_items),
        evaluation_record_ids=evaluation_record_ids,
    )
    envelope = RecordEnvelope(
        record_id=payload.record_id,
        record_family="episodic_memory",
        record_type="episode",
        schema_version="1.0.0",
        lifecycle_state="observed",
        approval_status="pending",
        authority_class="validated_system_evidence",
        certainty_class="verified",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="project_duration",
        training_eligibility="prohibited",
        created_at=created_at,
        source_kind="runtime_event",
        provenance_summary="Exact terminal governed occurrence.",
        retrieval_policy_json=canonical_json_text(
            {"retrieval_mode": "ordinary"}
        ),
        deletion_policy_json=canonical_json_text(
            {"deletion_mode": "governed"}
        ),
        agent_write_policy="prohibited",
        project_scope_id=project_scope_id or harness.project_scope_id,
        subject_entity_id=harness.agent_id,
        session_id=session_id or harness.session_id,
        task_id=task_id,
        created_by_entity_id=harness.operator_id,
        effective_from=created_at,
    )
    return envelope, payload, (*input_items, *output_items)


def create_episode(
    harness: C2Harness,
    *,
    base: int,
    task_id: str | None,
    outcome: str = "completed",
    episode_kind: str = "task",
    evaluation_record_ids: tuple[str, ...] = (),
) -> tuple[RecordEnvelope, EpisodePayload, tuple[EvidenceItem, ...]]:
    envelope, payload, items = episode_components(
        harness,
        base=base,
        task_id=task_id,
        outcome=outcome,
        episode_kind=episode_kind,
        evaluation_record_ids=evaluation_record_ids,
    )
    harness.persistence.episode_correction_ledger.create_episode(
        envelope,
        payload,
        lifecycle_transition_id=uid(base + 30),
        approval_transition_id=uid(base + 31),
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
        evidence_items=items,
    )
    return envelope, payload, items


def correction_components(
    harness: C2Harness,
    *,
    base: int,
    target_episode_id: str,
    target_output_evidence_id: str,
    project_scope_id: str | None = None,
    issued_by_entity_id: str | None = None,
    issuer_class: str = "nolan",
) -> tuple[RecordEnvelope, CorrectionPayload, tuple[EvidenceItem, ...]]:
    support = (
        c2_evidence(
            base + 10,
            content="Exact independent correction support.",
            evidence_kind="human_statement",
            captured_by_entity=harness.operator_id,
        ),
    )
    payload = CorrectionPayload(
        record_id=uid(base),
        target_episode_id=target_episode_id,
        target_output_evidence_id=target_output_evidence_id,
        problem_statement="The exact output contains a material interpretation error.",
        corrected_interpretation="The evidence supports this bounded interpretation.",
        correction_category="interpretation_error",
        issued_by_entity_id=issued_by_entity_id or harness.operator_id,
        issuer_class=issuer_class,
        severity="material",
    )
    envelope = RecordEnvelope(
        record_id=payload.record_id,
        record_family="episodic_memory",
        record_type="correction",
        schema_version="1.0.0",
        lifecycle_state="reviewed",
        approval_status="pending",
        authority_class="nolan_approved",
        certainty_class="verified",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="permanent_history",
        training_eligibility="prohibited",
        created_at=NOW,
        source_kind="human_statement",
        provenance_summary="Exact correction attribution; no lesson implied.",
        retrieval_policy_json=canonical_json_text(
            {"retrieval_mode": "ordinary"}
        ),
        deletion_policy_json=canonical_json_text(
            {"deletion_mode": "governed"}
        ),
        agent_write_policy="prohibited",
        project_scope_id=project_scope_id or harness.project_scope_id,
        subject_entity_id=harness.agent_id,
        created_by_entity_id=harness.operator_id,
    )
    return envelope, payload, support


def create_correction(
    harness: C2Harness,
    *,
    base: int,
    target_episode_id: str,
    target_output_evidence_id: str,
) -> tuple[RecordEnvelope, CorrectionPayload, tuple[EvidenceItem, ...]]:
    envelope, payload, support = correction_components(
        harness,
        base=base,
        target_episode_id=target_episode_id,
        target_output_evidence_id=target_output_evidence_id,
    )
    harness.persistence.episode_correction_ledger.create_correction(
        envelope,
        payload,
        supporting_evidence_ids=tuple(item.evidence_id for item in support),
        lifecycle_transition_id=uid(base + 30),
        approval_transition_id=uid(base + 31),
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
        evidence_items=support,
    )
    return envelope, payload, support


def approve_memory_record(
    harness: C2Harness,
    *,
    record_id: str,
    base: int,
) -> tuple[object, EvidenceItem]:
    approval_authority, approval_evidence = register_nolan_byte_authority(
        harness.c1,
        base=base,
        content="Exact Nolan-Byte C2 memory approval.",
    )
    memory = harness.memory
    grant = MemoryApprovalGrant(
        grant_id=uid(base + 2),
        record_id=record_id,
        target_status="approved",
        project_scope_id=harness.project_scope_id,
        authority_record_id=approval_authority.authority_record_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        evidence_id=approval_evidence.evidence_id,
    )
    memory.register_approval_grant(grant)
    memory.transition_approval(
        record_id,
        transition_id=uid(base + 3),
        to_status="approved",
        reason_code="operator_c2_approval",
        changed_at=NOW,
        changed_by_entity_id=harness.operator_id,
        approval_grant_id=grant.grant_id,
    )
    return approval_authority, approval_evidence


def add_corrects_relationship(
    harness: C2Harness,
    *,
    correction_id: str,
    episode_id: str,
    base: int,
) -> RecordRelationship:
    authority_record, approval_evidence = register_nolan_byte_authority(
        harness.c1,
        base=base,
        content="Exact Nolan-Byte corrects relationship approval.",
    )
    relationship_id = uid(base + 2)
    grant = MemoryRelationshipGrant(
        grant_id=uid(base + 3),
        relationship_id=relationship_id,
        relationship_type="corrects",
        source_record_id=correction_id,
        target_record_id=episode_id,
        project_scope_id=harness.project_scope_id,
        authority_record_id=authority_record.authority_record_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        evidence_id=approval_evidence.evidence_id,
    )
    relationship = RecordRelationship(
        relationship_id=relationship_id,
        source_record_id=correction_id,
        target_record_id=episode_id,
        relationship_type="corrects",
        created_at=NOW,
        created_by_principal="operator",
        relationship_grant_id=grant.grant_id,
        explanation="Exact governed correction target.",
    )
    memory = harness.memory
    memory.register_relationship_grant(grant)
    memory.link_records(relationship)
    return relationship


def activate_record(
    harness: C2Harness,
    *,
    record_id: str,
    base: int,
    starts_observed: bool,
) -> None:
    memory = harness.memory
    if starts_observed:
        memory.transition_lifecycle(
            record_id,
            transition_id=uid(base),
            to_state="reviewed",
            reason_code="operator_review",
            changed_at=NOW,
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )
    approve_memory_record(harness, record_id=record_id, base=base + 10)
    memory.transition_lifecycle(
        record_id,
        transition_id=uid(base + 1),
        to_state="approved",
        reason_code="external_approval_recorded",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    memory.transition_lifecycle(
        record_id,
        transition_id=uid(base + 2),
        to_state="active",
        reason_code="operator_activation",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )


def claimed_evaluation(harness: C2Harness, *, base: int):
    return register_evaluation(
        harness.c1,
        base=base,
        evaluation_kind="capability_evaluation",
        claimed=True,
    )
