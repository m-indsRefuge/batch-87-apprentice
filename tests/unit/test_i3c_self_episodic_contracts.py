from __future__ import annotations

from dataclasses import replace

import pytest

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.memory import (
    B87_S1_ACTIVE_MATURITY_STAGES,
    FACTUAL_SELF_PAYLOAD_TYPES,
    MATURITY_STAGES,
    CapabilityObservationPayload,
    DevelopmentalPolicyVersion,
    EvaluationReferenceAnchor,
    MaturityStatePayload,
    RuntimeIdentityPayload,
    RuntimeSubstrateAttestation,
    TrustedRuntimeAttestor,
    factual_self_content_hash,
    validate_factual_self_pair,
)
from batch87_apprentice.memory.contracts import MEMORY_RECORD_POLICIES
from batch87_apprentice.persistence.contracts import RecordEnvelope

NOW = "2026-07-26T10:00:00.000000Z"
LATER = "2026-07-26T11:00:00.000000Z"


def uid(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012d}"


def envelope(
    payload: RuntimeIdentityPayload
    | CapabilityObservationPayload
    | MaturityStatePayload,
    *,
    lifecycle_state: str,
    approval_status: str,
    authority_class: str,
    source_kind: str,
    agent_write_policy: str,
) -> RecordEnvelope:
    return RecordEnvelope(
        record_id=payload.record_id,
        record_family="self_model",
        record_type=payload.RECORD_TYPE,
        schema_version="1.0.0",
        lifecycle_state=lifecycle_state,
        approval_status=approval_status,
        authority_class=authority_class,
        certainty_class="verified",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="project_duration",
        training_eligibility="ineligible",
        created_at=NOW,
        source_kind=source_kind,
        provenance_summary="Exact governed C1 fixture.",
        retrieval_policy_json=canonical_json_text(
            {"retrieval_mode": "ordinary"}
        ),
        deletion_policy_json=canonical_json_text(
            {"deletion_mode": "governed"}
        ),
        agent_write_policy=agent_write_policy,
        project_scope_id=uid(1),
        subject_entity_id=(
            payload.agent_entity_id
            if isinstance(payload, (RuntimeIdentityPayload, MaturityStatePayload))
            else uid(2)
        ),
        created_by_runtime_id=(
            payload.runtime_instance_id
            if isinstance(payload, RuntimeIdentityPayload)
            else None
        ),
    )


def capability_policy(
    *,
    minimum: int = 2,
) -> DevelopmentalPolicyVersion:
    return DevelopmentalPolicyVersion(
        developmental_policy_id=uid(10),
        policy_kind="capability_stability",
        version="fixture-1",
        project_scope_id=uid(1),
        configuration={
            "allow_registered_for_unconfirmed": False,
            "stability_requirements": {
                stability: {
                    "minimum_claimed_evaluations": minimum,
                    "minimum_sample_size": minimum,
                }
                for stability in ("emerging", "repeated", "stable")
            },
        },
        authority_record_id=uid(11),
        approval_evidence_id=uid(12),
        approved_by_entity_id=uid(13),
        approved_at=NOW,
        effective_from=NOW,
    )


def test_contract_registry_has_only_three_c1_payloads_and_no_permission_memory() -> None:
    assert set(FACTUAL_SELF_PAYLOAD_TYPES) == {
        "runtime_identity",
        "capability_observation",
        "maturity_state",
    }
    assert ("self_model", "permission_profile") not in MEMORY_RECORD_POLICIES
    assert MEMORY_RECORD_POLICIES[("self_model", "runtime_identity")] == (
        "self_episodic",
        "not_required",
        "prohibited",
    )


def test_evaluation_anchor_and_policy_hash_exact_canonical_truth() -> None:
    anchor = EvaluationReferenceAnchor(
        evaluation_record_id=uid(20),
        evaluation_kind="capability_evaluation",
        project_scope_id=uid(1),
        provenance_evidence_id=uid(21),
        registered_at=NOW,
        provenance_summary="Externally supplied evaluation identity.",
    )
    policy = capability_policy(minimum=7)

    assert anchor.canonical_json == canonical_json_text(anchor.canonical_value())
    assert len(anchor.content_hash) == 64
    assert policy.configuration["stability_requirements"]["stable"] == {
        "minimum_claimed_evaluations": 7,
        "minimum_sample_size": 7,
    }
    assert len(policy.content_hash) == 64
    with pytest.raises(ValidationError, match="begin registered"):
        replace(anchor, state="claimed")
    with pytest.raises(ValidationError, match="integer >= 2"):
        capability_policy(minimum=1)


def test_runtime_identity_rejects_placeholders_and_hashes_normalized_bindings() -> None:
    payload = RuntimeIdentityPayload(
        record_id=uid(30),
        agent_entity_id=uid(2),
        base_model="example/model",
        model_revision="sha-abcdef",
        runtime_provider="local-runtime",
        quantisation="q4_k_m",
        context_limit=8192,
        active_adapter=None,
        runtime_started_at=NOW,
        runtime_instance_id=uid(31),
        substrate_attestor_entity_id=uid(33),
        substrate_attestation_evidence_id=uid(32),
    )
    record = envelope(
        payload,
        lifecycle_state="observed",
        approval_status="not_required",
        authority_class="validated_system_evidence",
        source_kind="runtime_event",
        agent_write_policy="prohibited",
    )

    validate_factual_self_pair(record, payload)
    digest = factual_self_content_hash(record, payload)
    assert len(digest) == 64
    assert digest != factual_self_content_hash(
        record,
        replace(payload, context_limit=16384),
    )
    with pytest.raises(ValidationError, match="placeholder"):
        replace(payload, base_model="planned")
    with pytest.raises(ValidationError, match="integer >= 1"):
        replace(payload, context_limit=None)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="integer >= 1"):
        replace(payload, context_limit=0)
    with pytest.raises(ValidationError, match="integer >= 1"):
        replace(payload, context_limit=-1)
    with pytest.raises(TypeError, match="context_limit"):
        RuntimeIdentityPayload(
            record_id=uid(30),
            agent_entity_id=uid(2),
            base_model="example/model",
            model_revision="sha-abcdef",
            runtime_provider="local-runtime",
            quantisation=None,
            active_adapter=None,
            runtime_started_at=NOW,
            runtime_instance_id=uid(31),
            substrate_attestor_entity_id=uid(33),
            substrate_attestation_evidence_id=uid(32),
        )  # type: ignore[call-arg]


def test_runtime_attestor_and_attestation_contracts_hash_exact_governed_truth() -> None:
    trusted = TrustedRuntimeAttestor(
        trusted_attestor_id=uid(60),
        attestor_entity_id=uid(61),
        project_scope_id=uid(1),
        attestation_environment="production",
        authority_record_id=uid(62),
        approval_evidence_id=uid(63),
        registered_by_principal="operator",
        registered_by_entity_id=uid(64),
        approved_by_entity_id=uid(64),
        approved_at=NOW,
        effective_from=NOW,
    )
    attestation = RuntimeSubstrateAttestation(
        substrate_attestation_evidence_id=uid(65),
        trusted_attestor_id=trusted.trusted_attestor_id,
        attestor_entity_id=trusted.attestor_entity_id,
        project_scope_id=trusted.project_scope_id,
        agent_entity_id=uid(2),
        runtime_instance_id=uid(31),
        attestation_environment="production",
        base_model="example/model",
        model_revision="sha-abcdef",
        runtime_provider="local-runtime",
        quantisation=None,
        context_limit=8192,
        active_adapter=None,
        runtime_started_at=NOW,
        captured_at=NOW,
        changed_by_principal="validated_system",
        changed_by_entity_id=trusted.attestor_entity_id,
    )

    assert trusted.canonical_json == canonical_json_text(
        trusted.canonical_value()
    )
    assert attestation.canonical_json == canonical_json_text(
        attestation.canonical_value()
    )
    assert len(trusted.content_hash) == 64
    assert len(attestation.content_hash) == 64
    with pytest.raises(ValidationError, match="validated_system"):
        replace(attestation, changed_by_principal="operator")
    with pytest.raises(ValidationError, match="integer >= 1"):
        replace(attestation, context_limit=0)


def test_capability_lineage_is_ordered_exact_and_higher_stability_needs_policy() -> None:
    evaluation_ids = (uid(40), uid(41))
    payload = CapabilityObservationPayload(
        record_id=uid(42),
        capability_name="Deterministic reconstruction",
        observation_type="strength",
        evidence_summary="Two exact evaluation references.",
        sample_size=2,
        evaluation_record_ids=evaluation_ids,
        stability="emerging",
        developmental_policy_id=uid(10),
    )
    record = envelope(
        payload,
        lifecycle_state="candidate",
        approval_status="pending",
        authority_class="agent_proposal",
        source_kind="derived_record",
        agent_write_policy="candidate_only",
    )

    validate_factual_self_pair(record, payload)
    assert payload.canonical_content()["evaluation_record_ids"] == list(
        evaluation_ids
    )
    assert factual_self_content_hash(record, payload) != factual_self_content_hash(
        record,
        CapabilityObservationPayload(
            record_id=payload.record_id,
            capability_name=payload.capability_name,
            observation_type=payload.observation_type,
            evidence_summary=payload.evidence_summary,
            sample_size=payload.sample_size,
            evaluation_record_ids=tuple(reversed(evaluation_ids)),
            stability=payload.stability,
            developmental_policy_id=payload.developmental_policy_id,
        ),
    )
    with pytest.raises(ValidationError, match="exactly reconcile"):
        CapabilityObservationPayload(
            record_id=uid(43),
            capability_name="Mismatch",
            observation_type="unknown",
            evidence_summary="Mismatch.",
            sample_size=3,
            evaluation_record_ids=evaluation_ids,
            stability="unconfirmed",
        )
    with pytest.raises(ValidationError, match="require a policy"):
        CapabilityObservationPayload(
            record_id=uid(44),
            capability_name="No policy",
            observation_type="strength",
            evidence_summary="No policy.",
            sample_size=2,
            evaluation_record_ids=evaluation_ids,
            stability="stable",
        )


def test_maturity_recognizes_future_names_but_b87_s1_allowlist_is_narrow() -> None:
    policy = DevelopmentalPolicyVersion(
        developmental_policy_id=uid(50),
        policy_kind="maturity_progression",
        version="fixture-1",
        project_scope_id=uid(1),
        configuration={
            "stage_transitions": [
                {
                    "from_stage": None,
                    "to_stage": "uninitialised",
                    "minimum_claimed_evaluations": 1,
                },
                {
                    "from_stage": "uninitialised",
                    "to_stage": "oriented",
                    "minimum_claimed_evaluations": 4,
                },
            ]
        },
        authority_record_id=uid(51),
        approval_evidence_id=uid(52),
        approved_by_entity_id=uid(13),
        approved_at=NOW,
        effective_from=LATER,
    )
    payload = MaturityStatePayload(
        record_id=uid(53),
        stage="apprentice-proposer",
        entered_at=LATER,
        basis=(uid(54),),
        restrictions=("Observe and Analyse only.",),
        next_gate="Nolan-Byte review",
        agent_entity_id=uid(2),
        developmental_policy_id=policy.developmental_policy_id,
    )

    assert payload.stage in MATURITY_STAGES
    assert payload.stage not in B87_S1_ACTIVE_MATURITY_STAGES
    assert policy.configuration["stage_transitions"][1][
        "minimum_claimed_evaluations"
    ] == 4


def test_combined_hash_is_stable_across_mutable_lifecycle_and_approval_state() -> None:
    payload = CapabilityObservationPayload(
        record_id=uid(60),
        capability_name="Lifecycle-independent truth",
        observation_type="unknown",
        evidence_summary="One claimed evaluation.",
        sample_size=1,
        evaluation_record_ids=(uid(61),),
        stability="unconfirmed",
    )
    initial = envelope(
        payload,
        lifecycle_state="candidate",
        approval_status="pending",
        authority_class="agent_proposal",
        source_kind="derived_record",
        agent_write_policy="candidate_only",
    )
    active = replace(
        initial,
        lifecycle_state="active",
        approval_status="approved",
    )

    assert factual_self_content_hash(initial, payload) == (
        factual_self_content_hash(active, payload)
    )
