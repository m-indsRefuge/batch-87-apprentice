"""Deterministic B87-I4-A fixtures over accepted I2 and I3-D truth."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.context import (
    CONTEXT_SECTIONS,
    ContextAssembler,
    ContextRetrievalService,
    OrderedContextEntry,
    RetrievalRequest,
)
from batch87_apprentice.memory import (
    ConstructDoctrinePayload,
    MemoryApprovalGrant,
    MemoryKernel,
    TypedSourceReference,
)
from batch87_apprentice.persistence.contracts import (
    ControlledResiliencePayload,
    EvidenceItem,
    EvidenceLink,
    RecordEnvelope,
    ReferenceAnchor,
)
from tests.support.i2_fixtures import (
    NOW,
    IdentifierSequence,
    authority,
    evidence,
    task,
    uid,
)
from tests.support.i3c3_fixtures import (
    create_approved_lesson,
    create_candidate,
    create_source_bundle,
    review_candidate,
)
from tests.support.i3d_fixtures import (
    I3DHarness,
    build_i3d_harness,
    context_item,
    source_hash,
)


def build_i4a_harness(
    tmp_path: Path,
    *,
    base: int = 1_100_000,
) -> I3DHarness:
    return build_i3d_harness(tmp_path, base=base)


def build_task_with_inline_evidence(
    harness: I3DHarness,
    *,
    base: int,
    evidence_kind: str,
    content: str,
    governing_constraints: tuple[str, ...] = (
        "b87_s1_permissions",
        "structured_authority_only",
    ),
    expected_output_schema_id: str = (
        "https://batch87.local/schemas/output/test-analysis"
    ),
    prohibited_actions: tuple[str, ...] | None = None,
    task_type: str = "governed_analysis",
) -> I3DHarness:
    item = EvidenceItem.inline_text(
        evidence_id=uid(base + 1),
        evidence_kind=evidence_kind,
        content=content,
        captured_at=NOW,
        sensitivity_class="internal",
        privacy_class="none",
        captured_by_entity=harness.operator_id,
    )
    i2 = harness.c3.c2.c1.i2
    authority_record = authority(
        i2,
        base + 2,
        evidence_ids=(item.evidence_id,),
        permissions=("analyse",),
    )
    harness.runtime.register_authority(
        authority_record,
        evidence_items=(item,),
    )
    contract = task(
        i2,
        base,
        authority_ids=(authority_record.authority_record_id,),
        required_evidence_ids=(item.evidence_id,),
        action_class="analyse",
        objective="Assemble exact governed context over typed evidence.",
        governing_constraints=governing_constraints,
        expected_output_schema_id=expected_output_schema_id,
        prohibited_actions=prohibited_actions,
        task_type=task_type,
    )
    result = harness.runtime.evaluate(contract)
    assert result.task_status == "active", result
    return I3DHarness(
        c3=harness.c3,
        task_id=contract.task_id,
        task_evidence_id=item.evidence_id,
    )


def retrieval_service(
    harness: I3DHarness,
    *,
    identifier_start: int = 1_500_000,
    ranker: object | None = None,
    assembler: ContextAssembler | None = None,
) -> ContextRetrievalService:
    return ContextRetrievalService(
        harness.config,
        identifier_factory=IdentifierSequence(identifier_start),
        ranker=ranker,
        assembler=assembler,
    )


def request_for(
    harness: I3DHarness,
    *,
    finalization_id: str,
    number: int,
    purpose: str = "Assemble exact governed task context.",
    provenance: Mapping[str, Any] | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    project_scope_id: str | None = None,
) -> RetrievalRequest:
    return RetrievalRequest(
        retrieval_request_id=uid(number),
        contract_version="1.0.0",
        task_id=harness.task_id if task_id is None else task_id,
        session_id=(
            harness.session_id if session_id is None else session_id
        ),
        project_scope_id=(
            harness.project_scope_id
            if project_scope_id is None
            else project_scope_id
        ),
        task_context_finalization_id=finalization_id,
        purpose=purpose,
        requested_sections=CONTEXT_SECTIONS,
        requested_at=NOW,
        requested_by_principal="operator",
        ranking_strategy="deterministic_fallback_v1",
        provenance_json=canonical_json_text(
            provenance or {"source": "deterministic I4-A test fixture"}
        ),
    )


def finalize_items(
    harness: I3DHarness,
    items: tuple[object, ...],
    *,
    finalization_number: int,
) -> str:
    for item in items:
        harness.persistence.session_task_memory.add_context_item(item)
    finalization_id = uid(finalization_number)
    harness.persistence.session_task_memory.finalize_context(
        harness.task_id,
        finalization_id=finalization_id,
        finalized_at=NOW,
        finalized_by_principal="operator",
    )
    return finalization_id


def ordinary_evidence_item(
    harness: I3DHarness,
    *,
    number: int,
    injection_order: int = 0,
    required: bool = True,
    context_kind: str = "evidence",
):
    return context_item(
        harness,
        base=number,
        context_kind=context_kind,
        injection_order=injection_order,
        required=required,
    )


def create_noninline_evidence(
    harness: I3DHarness,
    *,
    number: int,
) -> EvidenceItem:
    item = EvidenceItem(
        evidence_id=uid(number),
        evidence_kind="document",
        storage_kind="local_file",
        storage_location="inert-test-reference.txt",
        captured_at=NOW,
        integrity_status="unavailable",
        redaction_status="none",
        sensitivity_class="internal",
        privacy_class="none",
        media_type="text/plain",
        byte_length=17,
        content_hash="a" * 64,
    )
    harness.persistence.evidence.create(item)
    return item


def create_model_output_evidence(
    harness: I3DHarness,
    *,
    number: int,
) -> EvidenceItem:
    item = EvidenceItem.inline_text(
        evidence_id=uid(number),
        evidence_kind="model_output",
        content="Synthetic model-like output that is not memory or authority.",
        captured_at=NOW,
        sensitivity_class="internal",
        privacy_class="none",
    )
    harness.persistence.evidence.create(item)
    return item


def create_controlled_bundle(
    harness: I3DHarness,
    *,
    base: int,
) -> tuple[ControlledResiliencePayload, tuple[EvidenceItem, ...]]:
    record_id = uid(base)
    experiment_id = uid(base + 1)
    fixture_id = uid(base + 2)
    prompt_id = uid(base + 3)
    output_id = uid(base + 4)
    context_id = uid(base + 5)
    invocation_id = uid(base + 6)
    payload = ControlledResiliencePayload(
        record_id=record_id,
        experiment_id=experiment_id,
        fixture_id=fixture_id,
        test_family="CGR-I4A",
        test_level=1,
        test_condition="invalid",
        run_id=uid(base + 7),
        governance_distinction="Supplied content is not authority.",
        maximum_test_intensity="bounded synthetic prompt",
        raw_prompt_evidence_id=prompt_id,
        raw_output_evidence_id=output_id,
        context_manifest_id=context_id,
        model_invocation_id=invocation_id,
        completion_state="incomplete",
        created_at=NOW,
    )
    envelope = RecordEnvelope.for_controlled_resilience(
        record_id=record_id,
        project_scope_id=harness.project_scope_id,
        created_at=NOW,
        provenance_summary="Deterministic I4-A controlled bundle.",
    )
    anchors = tuple(
        ReferenceAnchor(
            reference_id=identifier,
            reference_kind=kind,
            project_scope_id=harness.project_scope_id,
            created_at=NOW,
            provenance_json=canonical_json_text(
                {
                    "fixture": "deterministic I4-A",
                    "kind": kind,
                    "operation_executed": False,
                }
            ),
        )
        for identifier, kind in (
            (experiment_id, "evaluation_experiment"),
            (fixture_id, "evaluation_fixture"),
            (context_id, "context_manifest"),
            (invocation_id, "model_invocation"),
        )
    )
    items = (
        EvidenceItem.inline_text(
            evidence_id=prompt_id,
            evidence_kind="controlled_prompt",
            content="Synthetic invalid-authority prompt.",
            captured_at=NOW,
        ),
        EvidenceItem.inline_text(
            evidence_id=output_id,
            evidence_kind="controlled_output",
            content="Synthetic bounded output.",
            captured_at=NOW,
        ),
    )
    harness.persistence.controlled_resilience.create(
        envelope,
        payload,
        anchors=anchors,
        evidence_items=items,
    )
    return payload, items


def create_active_construct_memory(
    harness: I3DHarness,
    *,
    base: int,
) -> str:
    payload = ConstructDoctrinePayload(
        record_id=uid(base),
        doctrine_statement="Models propose; Nolan authorises.",
        application_scopes=(harness.project_scope_id,),
        interpretation_notes=(
            "The record is contextual memory, not live permission."
        ),
    )
    envelope = RecordEnvelope(
        record_id=payload.record_id,
        record_family="construct_memory",
        record_type=payload.RECORD_TYPE,
        schema_version="1.0.0",
        lifecycle_state="candidate",
        approval_status="pending",
        authority_class="agent_proposal",
        certainty_class="strongly_supported",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="project_duration",
        training_eligibility="ineligible",
        created_at=NOW,
        source_kind="human_statement",
        provenance_summary="Explicit governed Construct doctrine.",
        retrieval_policy_json=canonical_json_text(
            {
                "allowed_project_scope_ids": [harness.project_scope_id],
                "retrieval_mode": "ordinary",
            }
        ),
        deletion_policy_json=canonical_json_text(
            {"deletion_mode": "governed"}
        ),
        agent_write_policy="prohibited",
        project_scope_id=harness.project_scope_id,
        created_by_entity_id=harness.operator_id,
    )
    source = EvidenceItem.inline_text(
        evidence_id=uid(base + 1),
        evidence_kind="human_statement",
        content="Exact evidence for the governed Construct doctrine.",
        captured_at=NOW,
        sensitivity_class="internal",
        privacy_class="none",
        captured_by_entity=harness.operator_id,
    )
    harness.persistence.construct_memory.create(
        envelope,
        payload,
        lifecycle_transition_id=uid(base + 2),
        approval_transition_id=uid(base + 3),
        evidence_items=(source,),
        evidence_links=(
            EvidenceLink(
                record_id=payload.record_id,
                evidence_id=source.evidence_id,
                relationship="derived_from",
                explanation="Evidence remains separate from memory.",
            ),
        ),
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    memory = MemoryKernel(harness.config)
    memory.transition_lifecycle(
        payload.record_id,
        transition_id=uid(base + 4),
        to_state="reviewed",
        reason_code="construct_review_complete",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    approval_evidence = evidence(
        base + 5,
        captured_by_entity=harness.operator_id,
        content="Exact Nolan approval for I4-A Construct context.",
    )
    i2 = harness.c3.c2.c1.i2
    approval_authority = authority(
        i2,
        base + 6,
        evidence_ids=(approval_evidence.evidence_id,),
        authority_class="nolan_approved",
    )
    harness.runtime.register_authority(
        approval_authority,
        evidence_items=(approval_evidence,),
    )
    grant = MemoryApprovalGrant(
        grant_id=uid(base + 7),
        record_id=payload.record_id,
        target_status="approved",
        project_scope_id=harness.project_scope_id,
        authority_record_id=approval_authority.authority_record_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        evidence_id=approval_evidence.evidence_id,
    )
    memory.register_approval_grant(grant)
    memory.transition_approval(
        payload.record_id,
        transition_id=uid(base + 8),
        to_status="approved",
        reason_code="construct_memory_approved",
        changed_at=NOW,
        changed_by_entity_id=harness.operator_id,
        approval_grant_id=grant.grant_id,
    )
    memory.transition_lifecycle(
        payload.record_id,
        transition_id=uid(base + 9),
        to_state="approved",
        reason_code="construct_approval_recorded",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    memory.transition_lifecycle(
        payload.record_id,
        transition_id=uid(base + 10),
        to_state="active",
        reason_code="construct_activated_for_context",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    return payload.record_id


def create_active_approved_lesson(
    harness: I3DHarness,
    *,
    base: int,
) -> str:
    _, episode_bundle, correction_bundle = create_source_bundle(
        harness.c3,
        base=base,
    )
    episode, _ = episode_bundle
    correction, _ = correction_bundle
    _, candidate = create_candidate(
        harness.c3,
        base=base + 400,
        task_id=harness.task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    review_candidate(
        harness.c3,
        candidate_id=candidate.record_id,
        transition_id=uid(base + 403),
    )
    _, lesson = create_approved_lesson(
        harness.c3,
        base=base + 500,
        candidate=candidate,
    )
    return lesson.record_id


def memory_context_item(
    harness: I3DHarness,
    *,
    number: int,
    record_id: str,
    context_kind: str,
    injection_order: int,
    required: bool,
):
    source = TypedSourceReference(memory_record_id=record_id)
    return context_item(
        harness,
        base=number,
        context_kind=context_kind,
        source=source,
        injection_order=injection_order,
        required=required,
        content_hash=source_hash(harness, source),
    )


class InjectExcludedAssembler(ContextAssembler):
    """Test-only assembler that proves the independent scanner fails closed."""

    def __init__(
        self,
        injected_source: tuple[str, str, str, str] | None = None,
    ) -> None:
        self._injected_source = injected_source

    def assemble(
        self,
        *,
        authoritative_i2: Mapping[str, Any],
        active_uncertainties: tuple[Mapping[str, Any], ...],
        ranked_candidates: tuple[object, ...],
        manifest_entries: Mapping[str, object],
        identifier_factory: Callable[[], str],
    ):
        sections_json, ordered, task_hash, authority_hash = super().assemble(
            authoritative_i2=authoritative_i2,
            active_uncertainties=active_uncertainties,
            ranked_candidates=ranked_candidates,
            manifest_entries=manifest_entries,
            identifier_factory=identifier_factory,
        )
        excluded = next(
            entry
            for entry in manifest_entries.values()
            if entry.disposition == "excluded"
        )
        if self._injected_source is None:
            source_kind = excluded.source_kind
            source_id = excluded.source_id
            source_hash = excluded.source_content_hash
            target_section = excluded.target_section
        else:
            source_kind, source_id, source_hash, target_section = (
                self._injected_source
            )
        sections = parse_json(sections_json)
        material = {
            "classification": "deliberately injected contamination fixture",
            "source_id": source_id,
        }
        section_values = sections[target_section]
        section_values.append(material)
        injected = OrderedContextEntry(
            ordered_entry_id=identifier_factory(),
            section=target_section,
            section_order=CONTEXT_SECTIONS.index(target_section),
            entry_order=len(section_values) - 1,
            source_kind=source_kind,
            source_id=source_id,
            source_content_hash=source_hash,
            retrieval_manifest_entry_id=excluded.entry_id,
            entry_json=canonical_json_text(material),
        )
        combined = tuple(
            sorted(
                (*ordered, injected),
                key=lambda entry: (
                    entry.section_order,
                    entry.entry_order,
                ),
            )
        )
        return (
            canonical_json_text(sections),
            combined,
            task_hash,
            authority_hash,
        )


class SubstituteMaterializedAssembler(ContextAssembler):
    """Replace benign source material while preserving all source metadata."""

    def assemble(
        self,
        *,
        authoritative_i2: Mapping[str, Any],
        active_uncertainties: tuple[Mapping[str, Any], ...],
        ranked_candidates: tuple[object, ...],
        manifest_entries: Mapping[str, object],
        identifier_factory: Callable[[], str],
    ):
        sections_json, ordered, task_hash, authority_hash = super().assemble(
            authoritative_i2=authoritative_i2,
            active_uncertainties=active_uncertainties,
            ranked_candidates=ranked_candidates,
            manifest_entries=manifest_entries,
            identifier_factory=identifier_factory,
        )
        target = next(
            entry
            for entry in ordered
            if entry.retrieval_manifest_entry_id is not None
        )
        substituted_value = parse_json(target.entry_json)
        substituted_value["review_note"] = (
            "benign content substituted after deterministic materialization"
        )
        substituted_json = canonical_json_text(substituted_value)
        substituted_entry = OrderedContextEntry(
            ordered_entry_id=target.ordered_entry_id,
            section=target.section,
            section_order=target.section_order,
            entry_order=target.entry_order,
            source_kind=target.source_kind,
            source_id=target.source_id,
            source_content_hash=target.source_content_hash,
            retrieval_manifest_entry_id=target.retrieval_manifest_entry_id,
            entry_json=substituted_json,
        )
        sections = parse_json(sections_json)
        sections[target.section][target.entry_order] = substituted_value
        substituted_order = tuple(
            substituted_entry
            if entry.ordered_entry_id == target.ordered_entry_id
            else entry
            for entry in ordered
        )
        return (
            canonical_json_text(sections),
            substituted_order,
            task_hash,
            authority_hash,
        )


class SubstituteAuthoritativeSectionAssembler(ContextAssembler):
    """Alter one authoritative semantic field and recompute every self-hash."""

    _MUTATIONS = frozenset(
        {
            "task_objective",
            "task_prohibited_action",
            "task_requested_operation",
            "task_uncertainty",
            "authority_outcome",
            "authority_reason",
            "authority_permission_profile",
            "authority_reference",
        }
    )

    def __init__(self, mutation: str) -> None:
        if mutation not in self._MUTATIONS:
            raise ValueError(f"unsupported authoritative mutation: {mutation}")
        self._mutation = mutation

    def assemble(
        self,
        *,
        authoritative_i2: Mapping[str, Any],
        active_uncertainties: tuple[Mapping[str, Any], ...],
        ranked_candidates: tuple[object, ...],
        manifest_entries: Mapping[str, object],
        identifier_factory: Callable[[], str],
    ):
        sections_json, ordered, task_hash, authority_hash = super().assemble(
            authoritative_i2=authoritative_i2,
            active_uncertainties=active_uncertainties,
            ranked_candidates=ranked_candidates,
            manifest_entries=manifest_entries,
            identifier_factory=identifier_factory,
        )
        sections = parse_json(sections_json)
        if self._mutation == "task_objective":
            sections["task"]["objective"] += " Altered by faulty assembler."
        elif self._mutation == "task_prohibited_action":
            sections["task"]["prohibited_actions"] = sections["task"][
                "prohibited_actions"
            ][:-1]
        elif self._mutation == "task_requested_operation":
            sections["task"]["requested_operation"]["name"] += "_altered"
        elif self._mutation == "task_uncertainty":
            sections["task"]["active_non_blocking_uncertainties"] = []
        elif self._mutation == "authority_outcome":
            sections["authority"]["governance_decision"]["outcome"] = (
                "altered_outcome"
            )
        elif self._mutation == "authority_reason":
            sections["authority"]["governance_decision"]["reasons"] = sections[
                "authority"
            ]["governance_decision"]["reasons"][:-1]
        elif self._mutation == "authority_permission_profile":
            sections["authority"]["permission_profile"] = {
                "classification": "faulty replacement permission profile"
            }
        else:
            sections["authority"]["governing_rule_references"] = sections[
                "authority"
            ]["governing_rule_references"][:-1]

        section = (
            "task" if self._mutation.startswith("task_") else "authority"
        )
        substituted_json = canonical_json_text(sections[section])
        substituted_hash = sha256_canonical_json(sections[section])
        target = next(entry for entry in ordered if entry.section == section)
        substituted_entry = replace(
            target,
            source_content_hash=substituted_hash,
            entry_json=substituted_json,
        )
        substituted_order = tuple(
            substituted_entry
            if entry.ordered_entry_id == target.ordered_entry_id
            else entry
            for entry in ordered
        )
        return (
            canonical_json_text(sections),
            substituted_order,
            substituted_hash if section == "task" else task_hash,
            substituted_hash if section == "authority" else authority_hash,
        )
