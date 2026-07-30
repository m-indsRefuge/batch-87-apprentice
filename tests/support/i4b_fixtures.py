"""Deterministic B87-I4-B fixtures over accepted I2/I3/I4-A truth."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.invocation import (
    InferenceConfiguration,
    InvocationBridge,
    InvocationSpec,
    ModelDescriptor,
)
from batch87_apprentice.invocation.schemas import (
    APPRENTICE_RESPONSE_SCHEMA_HASH,
    APPRENTICE_RESPONSE_SCHEMA_ID,
)
from batch87_apprentice.providers import DeterministicMockFixture
from tests.support.i2_fixtures import LATER, NOW, IdentifierSequence, uid
from tests.support.i3c_fixtures import (
    ingest_runtime_attestation,
    register_trusted_runtime_attestor,
    runtime_identity_components,
)
from tests.support.i3d_fixtures import I3DHarness
from tests.support.i4a_fixtures import (
    build_i4a_harness,
    build_task_with_inline_evidence,
    finalize_items,
    ordinary_evidence_item,
    request_for,
    retrieval_service,
)


@dataclass(frozen=True, slots=True)
class I4BHarness:
    i4a: I3DHarness
    context_package_id: str
    context_package_hash: str
    runtime_identity_id: str
    runtime_identity_hash: str
    model_descriptor: ModelDescriptor

    @property
    def config(self):
        return self.i4a.config

    @property
    def task_id(self) -> str:
        return self.i4a.task_id

    @property
    def session_id(self) -> str:
        return self.i4a.session_id

    @property
    def project_scope_id(self) -> str:
        return self.i4a.project_scope_id


def valid_response_bytes(
    task_id: str,
    *,
    status: str = "completed",
    recommendations: tuple[str, ...] = (),
    memory_used: tuple[str, ...] = (),
    evidence_used: tuple[str, ...] = (),
    stop_requested: bool = False,
    stop_reason: str | None = None,
) -> bytes:
    return canonical_json_text(
        {
            "evidence_used": list(evidence_used),
            "inferences": ["The bounded fixture was analysed deterministically."],
            "memory_used": list(memory_used),
            "observations": ["The governed context package was available."],
            "protocol": "batch87.apprentice-response",
            "protocol_version": "1.0.0",
            "recommendations": list(recommendations),
            "status": status,
            "stop_reason": stop_reason,
            "stop_requested": stop_requested,
            "task_id": task_id,
            "uncertainties": [],
        }
    ).encode("utf-8")


def build_i4b_harness(
    tmp_path: Path,
    *,
    base: int = 2_000_000,
    completion_marker: bool = True,
    human_review_required: bool = False,
    recommendations_allowed: bool = False,
    runtime_provider: str = "deterministic_mock",
) -> I4BHarness:
    initial = build_i4a_harness(tmp_path, base=base)
    constraints = [
        "b87_s1_permissions",
        "structured_authority_only",
    ]
    if human_review_required:
        task_type = (
            "i4b_bounded_response_with_recommendations_human_review"
            if recommendations_allowed
            else "i4b_bounded_response_human_review"
        )
    elif completion_marker:
        task_type = (
            "i4b_bounded_response_with_recommendations"
            if recommendations_allowed
            else "i4b_bounded_response"
        )
    else:
        task_type = "governed_analysis"
    i4a = build_task_with_inline_evidence(
        initial,
        base=base + 10_000,
        evidence_kind="document",
        content="Exact governed I4-B context evidence.",
        governing_constraints=tuple(constraints),
        expected_output_schema_id=APPRENTICE_RESPONSE_SCHEMA_ID,
        prohibited_actions=("execute", "autonomous_action", "tool_use"),
        task_type=task_type,
    )
    context_item = ordinary_evidence_item(
        i4a,
        number=base + 20_000,
    )
    finalization_id = finalize_items(
        i4a,
        (context_item,),
        finalization_number=base + 20_010,
    )
    request = request_for(
        i4a,
        finalization_id=finalization_id,
        number=base + 20_020,
    )
    assembled = retrieval_service(
        i4a,
        identifier_start=base + 21_000,
    ).assemble(request)
    assert assembled.accepted
    assert assembled.bridge_context_ready

    c1 = i4a.c3.c2.c1
    trusted, _, _ = register_trusted_runtime_attestor(
        c1,
        base=base + 30_000,
    )
    identity_base = base + 31_000
    envelope, payload, attestation, evidence_item, links = (
        runtime_identity_components(
            c1,
            base=identity_base,
            trusted_attestor=trusted,
            base_model="fixture/i4b-deterministic-mock",
            model_revision="fixture-i4b-revision-1",
            runtime_provider=runtime_provider,
        )
    )
    ingest_runtime_attestation(c1, attestation, evidence_item)
    identity_hash = (
        c1.persistence.self_episodic_memory.create_runtime_identity(
            envelope,
            payload,
            initial_lifecycle_transition_id=uid(identity_base + 2),
            initial_approval_transition_id=uid(identity_base + 3),
            reviewed_transition_id=uid(identity_base + 4),
            approved_transition_id=uid(identity_base + 5),
            active_transition_id=uid(identity_base + 6),
            evidence_links=links,
            changed_by_principal="operator",
            changed_by_entity_id=c1.operator_id,
        )
    )
    descriptor = ModelDescriptor(
        model_name=payload.base_model,
        model_revision=payload.model_revision,
        quantisation=payload.quantisation,
        active_adapter=payload.active_adapter,
        context_limit=payload.context_limit,
    )
    return I4BHarness(
        i4a=i4a,
        context_package_id=assembled.context_package.context_package_id,
        context_package_hash=assembled.context_package.content_hash,
        runtime_identity_id=payload.record_id,
        runtime_identity_hash=identity_hash,
        model_descriptor=descriptor,
    )


def invocation_spec(
    harness: I4BHarness,
    *,
    number: int = 2_100_000,
    provider_id: str = "deterministic_mock",
    retry_of_invocation_id: str | None = None,
) -> InvocationSpec:
    return InvocationSpec(
        model_invocation_id=uid(number),
        task_id=harness.task_id,
        session_id=harness.session_id,
        project_scope_id=harness.project_scope_id,
        context_package_id=harness.context_package_id,
        context_package_hash=harness.context_package_hash,
        runtime_identity_id=harness.runtime_identity_id,
        runtime_identity_hash=harness.runtime_identity_hash,
        provider_id=provider_id,
        model_descriptor=harness.model_descriptor,
        inference_configuration=InferenceConfiguration(
            max_output_tokens=512,
        ),
        output_schema_id=APPRENTICE_RESPONSE_SCHEMA_ID,
        output_schema_hash=APPRENTICE_RESPONSE_SCHEMA_HASH,
        retry_of_invocation_id=retry_of_invocation_id,
    )


def build_additional_i4b_task(
    harness: I4BHarness,
    *,
    base: int,
) -> I4BHarness:
    i4a = build_task_with_inline_evidence(
        harness.i4a,
        base=base,
        evidence_kind="document",
        content="Distinct governed I4-B context evidence.",
        governing_constraints=(
            "b87_s1_permissions",
            "structured_authority_only",
        ),
        expected_output_schema_id=APPRENTICE_RESPONSE_SCHEMA_ID,
        prohibited_actions=("execute", "autonomous_action", "tool_use"),
        task_type="i4b_bounded_response",
    )
    context_item = ordinary_evidence_item(i4a, number=base + 100)
    finalization_id = finalize_items(
        i4a,
        (context_item,),
        finalization_number=base + 110,
    )
    assembled = retrieval_service(
        i4a,
        identifier_start=base + 1_000,
    ).assemble(
        request_for(
            i4a,
            finalization_id=finalization_id,
            number=base + 120,
        )
    )
    assert assembled.accepted
    assert assembled.bridge_context_ready
    return I4BHarness(
        i4a=i4a,
        context_package_id=assembled.context_package.context_package_id,
        context_package_hash=assembled.context_package.content_hash,
        runtime_identity_id=harness.runtime_identity_id,
        runtime_identity_hash=harness.runtime_identity_hash,
        model_descriptor=harness.model_descriptor,
    )


def bridge_for(
    harness: I4BHarness,
    *,
    raw_output: bytes | None = None,
    outcome: str = "output",
    declared_encoding: str | None = "utf-8",
    failure_code: str | None = None,
    identifier_start: int = 2_200_000,
) -> InvocationBridge:
    if raw_output is None and outcome == "output":
        raw_output = valid_response_bytes(harness.task_id)
    fixture = DeterministicMockFixture(
        fixture_id="i4b_fixture",
        raw_output=raw_output,
        declared_encoding=declared_encoding,
        outcome=outcome,
        failure_code=failure_code,
    )
    return InvocationBridge(
        harness.config,
        mock_fixture=fixture,
        clock=lambda: LATER,
        identifier_factory=IdentifierSequence(identifier_start),
    )
