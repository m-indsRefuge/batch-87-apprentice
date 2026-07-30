"""Deterministic B87-I3-C1 fixtures over accepted I2 persistence truth."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.memory import (
    CapabilityObservationPayload,
    DevelopmentalPolicyVersion,
    EvaluationReferenceAnchor,
    MaturityStatePayload,
    MemoryApprovalGrant,
    MemoryRelationshipGrant,
    RecordRelationship,
    RuntimeIdentityPayload,
    RuntimeSubstrateAttestation,
    TrustedRuntimeAttestor,
)
from batch87_apprentice.persistence.contracts import (
    Entity,
    EvidenceItem,
    EvidenceLink,
    RecordEnvelope,
)
from tests.support.i2_fixtures import (
    I2Harness,
    NOW,
    authority,
    build_harness,
    evidence,
    uid,
)


@dataclass(frozen=True, slots=True)
class C1Harness:
    i2: I2Harness
    agent_id: str

    @property
    def config(self):
        return self.i2.config

    @property
    def persistence(self):
        return self.i2.persistence

    @property
    def runtime(self):
        return self.i2.runtime

    @property
    def operator_id(self) -> str:
        return self.i2.operator_id

    @property
    def runtime_id(self) -> str:
        return self.i2.runtime_id

    @property
    def project_scope_id(self) -> str:
        return self.i2.project_scope_id


def build_c1_harness(
    tmp_path: Path,
    *,
    identifier_start: int = 300_000,
) -> C1Harness:
    i2 = build_harness(tmp_path, identifier_start=identifier_start)
    agent_id = uid(200_000)
    i2.persistence.entities.create(
        Entity(
            entity_id=agent_id,
            entity_kind="agent",
            canonical_name="B87-S1 Apprentice",
            description="Deterministic factual-self subject.",
            status="active",
            created_at=NOW,
        )
    )
    return C1Harness(i2=i2, agent_id=agent_id)


def register_nolan_byte_authority(
    harness: C1Harness,
    *,
    base: int,
    content: str,
) -> tuple[object, EvidenceItem]:
    approval_evidence = evidence(
        base,
        content=content,
        captured_by_entity=harness.operator_id,
    )
    approval_authority = authority(
        harness.i2,
        base + 1,
        evidence_ids=(approval_evidence.evidence_id,),
        authority_class="nolan_byte_approved",
        issuer_entity_id=harness.operator_id,
    )
    harness.runtime.register_authority(
        approval_authority,
        evidence_items=(approval_evidence,),
    )
    return approval_authority, approval_evidence


def register_trusted_runtime_attestor(
    harness: C1Harness,
    *,
    base: int,
    attestation_environment: str = "production",
    attestor_entity_id: str | None = None,
    effective_from: str = NOW,
    effective_until: str | None = None,
    status: str = "active",
    supersedes_trusted_attestor_id: str | None = None,
) -> tuple[TrustedRuntimeAttestor, object, EvidenceItem]:
    approval_authority, approval_evidence = register_nolan_byte_authority(
        harness,
        base=base,
        content=(
            "Exact Nolan-Byte trusted runtime-attestor registration approval."
        ),
    )
    trusted = TrustedRuntimeAttestor(
        trusted_attestor_id=uid(base + 2),
        attestor_entity_id=(
            attestor_entity_id or harness.i2.participant_id
        ),
        project_scope_id=harness.project_scope_id,
        attestation_environment=attestation_environment,
        authority_record_id=approval_authority.authority_record_id,
        approval_evidence_id=approval_evidence.evidence_id,
        registered_by_principal="operator",
        registered_by_entity_id=harness.operator_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        effective_from=effective_from,
        effective_until=effective_until,
        status=status,
        supersedes_trusted_attestor_id=supersedes_trusted_attestor_id,
    )
    harness.persistence.self_episodic_memory.register_trusted_runtime_attestor(
        trusted,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    return trusted, approval_authority, approval_evidence


def create_capability_policy(
    harness: C1Harness,
    *,
    base: int,
    minimum_claimed: int = 2,
    minimum_sample: int = 2,
    allow_registered_for_unconfirmed: bool = False,
) -> tuple[DevelopmentalPolicyVersion, object, EvidenceItem]:
    approval_authority, approval_evidence = register_nolan_byte_authority(
        harness,
        base=base,
        content="Exact Nolan-Byte capability-stability policy approval.",
    )
    policy = DevelopmentalPolicyVersion(
        developmental_policy_id=uid(base + 2),
        policy_kind="capability_stability",
        version=f"capability-{base}",
        project_scope_id=harness.project_scope_id,
        configuration={
            "allow_registered_for_unconfirmed": (
                allow_registered_for_unconfirmed
            ),
            "stability_requirements": {
                stability: {
                    "minimum_claimed_evaluations": minimum_claimed,
                    "minimum_sample_size": minimum_sample,
                }
                for stability in ("emerging", "repeated", "stable")
            },
        },
        authority_record_id=approval_authority.authority_record_id,
        approval_evidence_id=approval_evidence.evidence_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        effective_from=NOW,
    )
    harness.persistence.self_episodic_memory.create_developmental_policy_version(
        policy,
        changed_by_principal="codex_development_harness",
    )
    return policy, approval_authority, approval_evidence


def create_maturity_policy(
    harness: C1Harness,
    *,
    base: int,
    transitions: tuple[dict[str, object], ...] | None = None,
) -> tuple[DevelopmentalPolicyVersion, object, EvidenceItem]:
    approval_authority, approval_evidence = register_nolan_byte_authority(
        harness,
        base=base,
        content="Exact Nolan-Byte maturity-progression policy approval.",
    )
    if transitions is None:
        transitions = (
            {
                "from_stage": None,
                "to_stage": "uninitialised",
                "minimum_claimed_evaluations": 1,
            },
            {
                "from_stage": "uninitialised",
                "to_stage": "oriented",
                "minimum_claimed_evaluations": 1,
            },
            {
                "from_stage": "oriented",
                "to_stage": "apprentice-observer",
                "minimum_claimed_evaluations": 2,
            },
            {
                "from_stage": "apprentice-observer",
                "to_stage": "apprentice-analyst",
                "minimum_claimed_evaluations": 2,
            },
        )
    policy = DevelopmentalPolicyVersion(
        developmental_policy_id=uid(base + 2),
        policy_kind="maturity_progression",
        version=f"maturity-{base}",
        project_scope_id=harness.project_scope_id,
        configuration={"stage_transitions": transitions},
        authority_record_id=approval_authority.authority_record_id,
        approval_evidence_id=approval_evidence.evidence_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        effective_from=NOW,
    )
    harness.persistence.self_episodic_memory.create_developmental_policy_version(
        policy,
        changed_by_principal="codex_development_harness",
    )
    return policy, approval_authority, approval_evidence


def register_evaluation(
    harness: C1Harness,
    *,
    base: int,
    evaluation_kind: str,
    claimed: bool = True,
    project_scope_id: str | None = None,
    evidence_kind: str = "test_report",
) -> EvaluationReferenceAnchor:
    provenance = evidence(
        base,
        content="Externally verified evaluation reference evidence.",
        captured_by_entity=harness.operator_id,
        evidence_kind=evidence_kind,
    )
    anchor = EvaluationReferenceAnchor(
        evaluation_record_id=uid(base + 1),
        evaluation_kind=evaluation_kind,
        project_scope_id=project_scope_id or harness.project_scope_id,
        provenance_evidence_id=provenance.evidence_id,
        registered_at=NOW,
        provenance_summary="Narrow typed reference; no result implied.",
    )
    harness.persistence.self_episodic_memory.register_evaluation_anchor(
        anchor,
        initial_transition_id=uid(base + 2),
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
        reason_code="evaluation_reference_registered",
        evidence_items=(provenance,),
    )
    if claimed:
        harness.persistence.self_episodic_memory.transition_evaluation_anchor(
            anchor.evaluation_record_id,
            transition_id=uid(base + 3),
            to_state="claimed",
            changed_at=NOW,
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
            transition_evidence_id=provenance.evidence_id,
            reason_code="external_evaluation_occurrence_verified",
        )
    return anchor


def runtime_identity_components(
    harness: C1Harness,
    *,
    base: int,
    trusted_attestor: TrustedRuntimeAttestor,
    runtime_instance_id: str | None = None,
    supersedes_record_id: str | None = None,
    context_limit: int = 8192,
    base_model: str = "fixture/model",
    model_revision: str | None = None,
    runtime_provider: str = "deterministic-local",
) -> tuple[
    RecordEnvelope,
    RuntimeIdentityPayload,
    RuntimeSubstrateAttestation,
    EvidenceItem,
    tuple[EvidenceLink, ...],
]:
    runtime_id = runtime_instance_id or harness.runtime_id
    payload = RuntimeIdentityPayload(
        record_id=uid(base),
        agent_entity_id=harness.agent_id,
        base_model=base_model,
        model_revision=(
            f"fixture-revision-{base}"
            if model_revision is None
            else model_revision
        ),
        runtime_provider=runtime_provider,
        quantisation="q4_k_m",
        context_limit=context_limit,
        active_adapter=None,
        runtime_started_at=NOW,
        runtime_instance_id=runtime_id,
        substrate_attestor_entity_id=trusted_attestor.attestor_entity_id,
        substrate_attestation_evidence_id=uid(base + 1),
    )
    attestation_contract = RuntimeSubstrateAttestation(
        substrate_attestation_evidence_id=(
            payload.substrate_attestation_evidence_id
        ),
        trusted_attestor_id=trusted_attestor.trusted_attestor_id,
        attestor_entity_id=trusted_attestor.attestor_entity_id,
        project_scope_id=harness.project_scope_id,
        agent_entity_id=payload.agent_entity_id,
        runtime_instance_id=payload.runtime_instance_id,
        attestation_environment=trusted_attestor.attestation_environment,
        base_model=payload.base_model,
        model_revision=payload.model_revision,
        runtime_provider=payload.runtime_provider,
        quantisation=payload.quantisation,
        context_limit=payload.context_limit,
        active_adapter=payload.active_adapter,
        runtime_started_at=payload.runtime_started_at,
        captured_at=NOW,
        changed_by_principal=(
            "validated_system"
            if trusted_attestor.attestation_environment == "production"
            else "codex_development_harness"
        ),
        changed_by_entity_id=trusted_attestor.attestor_entity_id,
    )
    attestation = EvidenceItem.inline_text(
        evidence_id=payload.substrate_attestation_evidence_id,
        evidence_kind="system_event",
        content=attestation_contract.canonical_json,
        captured_at=NOW,
        sensitivity_class="internal",
        privacy_class="none",
        captured_by_entity=trusted_attestor.attestor_entity_id,
    )
    envelope = RecordEnvelope(
        record_id=payload.record_id,
        record_family="self_model",
        record_type="runtime_identity",
        schema_version="1.0.0",
        lifecycle_state="observed",
        approval_status="not_required",
        authority_class="validated_system_evidence",
        certainty_class="verified",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="project_duration",
        training_eligibility="prohibited",
        created_at=NOW,
        source_kind="runtime_event",
        provenance_summary="Exact runtime substrate attestation.",
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
        created_by_runtime_id=runtime_id,
        supersedes_record_id=supersedes_record_id,
    )
    links = (
        EvidenceLink(
            record_id=payload.record_id,
            evidence_id=attestation.evidence_id,
            relationship="supports",
            explanation="Exact running substrate attestation.",
        ),
    )
    return envelope, payload, attestation_contract, attestation, links


def ingest_runtime_attestation(
    harness: C1Harness,
    attestation: RuntimeSubstrateAttestation,
    evidence_item: EvidenceItem,
) -> str:
    return (
        harness.persistence.self_episodic_memory
        .ingest_runtime_substrate_attestation(
            attestation,
            evidence_item,
            changed_by_principal=attestation.changed_by_principal,
            changed_by_entity_id=attestation.changed_by_entity_id,
        )
    )


def capability_components(
    harness: C1Harness,
    *,
    base: int,
    evaluation_record_ids: tuple[str, ...],
    stability: str = "unconfirmed",
    developmental_policy_id: str | None = None,
    supersedes_record_id: str | None = None,
    proposed_by_apprentice: bool = False,
) -> tuple[
    RecordEnvelope,
    CapabilityObservationPayload,
    EvidenceItem,
    tuple[EvidenceLink, ...],
]:
    payload = CapabilityObservationPayload(
        record_id=uid(base),
        capability_name="governed factual reconstruction",
        observation_type="strength",
        evidence_summary="Exact evaluation lineage and non-model evidence.",
        sample_size=len(evaluation_record_ids),
        evaluation_record_ids=evaluation_record_ids,
        stability=stability,
        developmental_policy_id=developmental_policy_id,
    )
    source = evidence(
        base + 1,
        content="Non-model capability observation evidence.",
        captured_by_entity=harness.operator_id,
        evidence_kind="test_report",
    )
    envelope = RecordEnvelope(
        record_id=payload.record_id,
        record_family="self_model",
        record_type="capability_observation",
        schema_version="1.0.0",
        lifecycle_state="candidate",
        approval_status="pending",
        authority_class=(
            "agent_proposal"
            if proposed_by_apprentice
            else "validated_system_evidence"
        ),
        certainty_class="strongly_supported",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="project_duration",
        training_eligibility="ineligible",
        created_at=NOW,
        source_kind="derived_record",
        provenance_summary="Governed capability observation candidate.",
        retrieval_policy_json=canonical_json_text(
            {"retrieval_mode": "ordinary"}
        ),
        deletion_policy_json=canonical_json_text(
            {"deletion_mode": "governed"}
        ),
        agent_write_policy="candidate_only",
        project_scope_id=harness.project_scope_id,
        subject_entity_id=harness.agent_id,
        created_by_entity_id=(
            harness.agent_id
            if proposed_by_apprentice
            else harness.operator_id
        ),
        supersedes_record_id=supersedes_record_id,
    )
    links = (
        EvidenceLink(
            record_id=payload.record_id,
            evidence_id=source.evidence_id,
            relationship="evaluated_against",
            explanation="Evidence remains separate from interpretation.",
        ),
    )
    return envelope, payload, source, links


def maturity_components(
    harness: C1Harness,
    *,
    base: int,
    stage: str,
    basis: tuple[str, ...],
    developmental_policy_id: str,
    supersedes_record_id: str | None = None,
) -> tuple[
    RecordEnvelope,
    MaturityStatePayload,
    EvidenceItem,
    tuple[EvidenceLink, ...],
]:
    payload = MaturityStatePayload(
        record_id=uid(base),
        stage=stage,
        entered_at=NOW,
        basis=basis,
        restrictions=("Observe and Analyse only.",),
        next_gate="Exact Nolan-Byte developmental review.",
        agent_entity_id=harness.agent_id,
        developmental_policy_id=developmental_policy_id,
    )
    source = evidence(
        base + 1,
        content="Exact maturity-basis evidence.",
        captured_by_entity=harness.operator_id,
        evidence_kind="test_report",
    )
    envelope = RecordEnvelope(
        record_id=payload.record_id,
        record_family="self_model",
        record_type="maturity_state",
        schema_version="1.0.0",
        lifecycle_state="reviewed",
        approval_status="pending",
        authority_class="validated_system_evidence",
        certainty_class="verified",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="project_duration",
        training_eligibility="ineligible",
        created_at=NOW,
        source_kind="derived_record",
        provenance_summary="Externally governed maturity state.",
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
        supersedes_record_id=supersedes_record_id,
    )
    links = (
        EvidenceLink(
            record_id=payload.record_id,
            evidence_id=source.evidence_id,
            relationship="evaluated_against",
            explanation="Claimed maturity basis remains external evidence.",
        ),
    )
    return envelope, payload, source, links


def approval_grant(
    harness: C1Harness,
    *,
    record_id: str,
    authority_record,
    approval_evidence: EvidenceItem,
    base: int,
) -> MemoryApprovalGrant:
    return MemoryApprovalGrant(
        grant_id=uid(base),
        record_id=record_id,
        target_status="approved",
        project_scope_id=harness.project_scope_id,
        authority_record_id=authority_record.authority_record_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        evidence_id=approval_evidence.evidence_id,
    )


def supersession_components(
    harness: C1Harness,
    *,
    source_record_id: str,
    target_record_id: str,
    authority_record,
    approval_evidence: EvidenceItem,
    base: int,
) -> tuple[MemoryRelationshipGrant, RecordRelationship]:
    relationship_id = uid(base)
    grant = MemoryRelationshipGrant(
        grant_id=uid(base + 1),
        relationship_id=relationship_id,
        relationship_type="supersedes",
        source_record_id=source_record_id,
        target_record_id=target_record_id,
        project_scope_id=harness.project_scope_id,
        authority_record_id=authority_record.authority_record_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        evidence_id=approval_evidence.evidence_id,
    )
    relationship = RecordRelationship(
        relationship_id=relationship_id,
        source_record_id=source_record_id,
        target_record_id=target_record_id,
        relationship_type="supersedes",
        created_at=NOW,
        created_by_principal="operator",
        relationship_grant_id=grant.grant_id,
        explanation="Exact governed C1 factual-state replacement.",
    )
    return grant, relationship
