from __future__ import annotations

import inspect

import pytest

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.memory import (
    ArchitectureDecisionPayload,
    ConstructDoctrinePayload,
    ConstructEntityPayload,
    ConstructMemoryRepository,
    ConstructRelationshipPayload,
    MemoryApprovalGrant,
    MemoryKernel,
    MemoryRelationshipGrant,
    RecordRelationship,
    PreferenceRecordPayload,
    ProjectStatePayload,
    TerminologyDefinitionPayload,
)
from batch87_apprentice.persistence.contracts import (
    Entity,
    EvidenceItem,
    EvidenceLink,
    RecordEnvelope,
)
from batch87_apprentice.persistence.service import PersistenceService
from tests.support.i2_fixtures import (
    NOW,
    authority,
    build_harness,
    evidence,
    uid,
)
from tests.support.sql_probe import SqlProbe

PROJECT_ENTITY_ID = uid(130_000)


def add_project_entity(harness) -> None:
    harness.persistence.entities.create(
        Entity(
            entity_id=PROJECT_ENTITY_ID,
            entity_kind="project",
            canonical_name="Batch-87 Apprentice",
            description="Deterministic project entity for I3-B.",
            status="active",
            created_at=NOW,
        )
    )


def payload_subject(payload) -> str | None:
    if isinstance(payload, ConstructEntityPayload):
        return payload.entity_id
    if isinstance(payload, ConstructRelationshipPayload):
        return payload.subject_entity_id
    if isinstance(payload, ProjectStatePayload):
        return payload.project_id
    if isinstance(payload, PreferenceRecordPayload):
        return payload.preference_subject_id
    return None


def envelope_for(
    harness,
    payload,
    *,
    supersedes_record_id: str | None = None,
) -> RecordEnvelope:
    prohibited = {"architecture_decision", "construct_doctrine"}
    return RecordEnvelope(
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
        provenance_summary=f"Explicit evidence for {payload.RECORD_TYPE}.",
        retrieval_policy_json=canonical_json_text(
            {
                "retrieval_mode": "ordinary",
                "allowed_project_scope_ids": [harness.project_scope_id],
            }
        ),
        deletion_policy_json=canonical_json_text({"deletion_mode": "governed"}),
        agent_write_policy=(
            "prohibited"
            if payload.RECORD_TYPE in prohibited
            else "candidate_only"
        ),
        project_scope_id=harness.project_scope_id,
        subject_entity_id=payload_subject(payload),
        created_by_entity_id=harness.operator_id,
        supersedes_record_id=supersedes_record_id,
    )


def create_payload(
    harness,
    payload,
    *,
    base: int,
    evidence_kind: str = "human_statement",
    supersedes_record_id: str | None = None,
) -> str:
    source = EvidenceItem.inline_text(
        evidence_id=uid(base),
        evidence_kind=evidence_kind,
        content=f"Exact source for {payload.RECORD_TYPE}.",
        captured_at=NOW,
        sensitivity_class="internal",
        privacy_class="none",
        captured_by_entity=harness.operator_id,
    )
    return harness.persistence.construct_memory.create(
        envelope_for(
            harness,
            payload,
            supersedes_record_id=supersedes_record_id,
        ),
        payload,
        lifecycle_transition_id=uid(base + 1),
        approval_transition_id=uid(base + 2),
        evidence_items=(source,),
        evidence_links=(
            EvidenceLink(
                record_id=payload.record_id,
                evidence_id=source.evidence_id,
                relationship="derived_from",
                explanation="Evidence remains separate from Construct memory.",
            ),
        ),
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )


def all_payloads(harness) -> tuple[object, ...]:
    return (
        ConstructEntityPayload(
            uid(131_000),
            harness.operator_id,
            "Nolan is the final human authority.",
        ),
        ConstructRelationshipPayload(
            uid(132_000),
            harness.operator_id,
            "participates_in",
            PROJECT_ENTITY_ID,
            "Nolan participates in Batch-87.",
        ),
        ArchitectureDecisionPayload(
            record_id=uid(133_000),
            decision_statement="Use governed direct SQLite persistence.",
            decision_scope=harness.project_scope_id,
            rationale="The accepted architecture requires explicit transactions.",
            alternatives=[{"name": "ORM", "status": "not_selected"}],
            consequences=["Foreign keys remain explicit"],
            decision_status="accepted",
        ),
        ProjectStatePayload(
            record_id=uid(134_000),
            project_id=PROJECT_ENTITY_ID,
            state_type="phase",
            state_value={"phase": "I3-B", "status": "implementation"},
            observed_at=NOW,
        ),
        ConstructDoctrinePayload(
            record_id=uid(135_000),
            doctrine_statement="Models propose; Nolan authorises.",
            application_scopes=(
                harness.project_scope_id,
                harness.nested_scope_id,
            ),
            interpretation_notes="No model output creates authority.",
        ),
        TerminologyDefinitionPayload(
            record_id=uid(136_000),
            term="Construct memory",
            definition="Governed architecture, doctrine, state, and relationships.",
            definition_scope_id=harness.project_scope_id,
            deprecated_aliases=("world model",),
        ),
        PreferenceRecordPayload(
            record_id=uid(137_000),
            preference_subject_id=harness.operator_id,
            preference_category="engineering_reports",
            preference_statement="Return validation evidence.",
            context_constraints=({"project_scope_id": harness.project_scope_id},),
        ),
    )


def approve_to_lifecycle_approved(harness, payload, *, base: int) -> MemoryKernel:
    memory = MemoryKernel(harness.config)
    memory.transition_lifecycle(
        payload.record_id,
        transition_id=uid(base),
        to_state="reviewed",
        reason_code="construct_review_complete",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    authority_class = (
        "nolan_approved"
        if payload.RECORD_TYPE in {
            "architecture_decision",
            "construct_doctrine",
            "preference_record",
        }
        else "nolan_byte_approved"
    )
    approval_evidence = evidence(
        base + 1,
        captured_by_entity=harness.operator_id,
        content=f"Exact {authority_class} Construct-memory approval.",
    )
    authority_record = authority(
        harness,
        base + 2,
        evidence_ids=(approval_evidence.evidence_id,),
        authority_class=authority_class,
    )
    harness.runtime.register_authority(
        authority_record,
        evidence_items=(approval_evidence,),
    )
    grant = MemoryApprovalGrant(
        grant_id=uid(base + 3),
        record_id=payload.record_id,
        target_status="approved",
        project_scope_id=harness.project_scope_id,
        authority_record_id=authority_record.authority_record_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        evidence_id=approval_evidence.evidence_id,
    )
    memory.register_approval_grant(grant)
    memory.transition_approval(
        payload.record_id,
        transition_id=uid(base + 4),
        to_status="approved",
        reason_code="construct_memory_approved",
        changed_at=NOW,
        changed_by_entity_id=harness.operator_id,
        approval_grant_id=grant.grant_id,
    )
    memory.transition_lifecycle(
        payload.record_id,
        transition_id=uid(base + 5),
        to_state="approved",
        reason_code="construct_approval_recorded",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    return memory


def link_governed_supersession(
    harness,
    *,
    memory: MemoryKernel,
    source_record_id: str,
    target_record_id: str,
    base: int,
) -> None:
    approval_evidence = evidence(
        base,
        captured_by_entity=harness.operator_id,
        content="Exact Nolan-approved supersession relationship evidence.",
    )
    authority_record = authority(
        harness,
        base + 1,
        evidence_ids=(approval_evidence.evidence_id,),
        authority_class="nolan_approved",
    )
    harness.runtime.register_authority(
        authority_record,
        evidence_items=(approval_evidence,),
    )
    relationship_id = uid(base + 2)
    grant = MemoryRelationshipGrant(
        grant_id=uid(base + 3),
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
    memory.register_relationship_grant(grant)
    memory.link_records(
        RecordRelationship(
            relationship_id=relationship_id,
            source_record_id=source_record_id,
            target_record_id=target_record_id,
            relationship_type="supersedes",
            created_at=NOW,
            created_by_principal="operator",
            relationship_grant_id=grant.grant_id,
            explanation="Exact governed replacement relationship.",
        )
    )


def test_all_seven_types_create_atomically_and_reconstruct_after_reopen(
    tmp_path,
) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    payloads = all_payloads(harness)

    for index, payload in enumerate(payloads):
        digest = create_payload(harness, payload, base=140_000 + index * 10)
        assert len(digest) == 64

    first_reconstruction = {
        payload.record_id: harness.persistence.construct_memory.reconstruct(
            payload.record_id
        )
        for payload in payloads
    }
    reopened = PersistenceService.initialize(harness.config)
    second_reconstruction = {
        payload.record_id: reopened.construct_memory.reconstruct(payload.record_id)
        for payload in payloads
    }

    assert second_reconstruction == first_reconstruction
    for payload in payloads:
        audit = second_reconstruction[payload.record_id]
        assert audit["payload_type"] == payload.RECORD_TYPE
        assert audit["payload"] == payload.canonical_content()
        assert len(audit["evidence"]) == 1
        assert len(audit["lifecycle_transitions"]) == 1
        assert len(audit["approval_transitions"]) == 1
        assert audit["approval_grants"] == []
        assert audit["content_hash"] == audit["recomputed_content_hash"]
        assert audit["integrity"]["valid"] is True
        assert audit["integrity"]["findings"] == []
    entity_relationships = second_reconstruction[payloads[0].record_id][
        "construct_relationships"
    ]
    assert len(entity_relationships) == 1
    assert reopened.integrity.inspect().ok is True
    assert reopened.construct_integrity.inspect().ok is True
    assert "SqlProbe" not in inspect.getsource(ConstructMemoryRepository)


def test_failure_after_evidence_insertion_rolls_back_every_creation_row(
    tmp_path,
) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    payload = ProjectStatePayload(
        record_id=uid(150_000),
        project_id=PROJECT_ENTITY_ID,
        state_type="milestone",
        state_value={"name": "atomicity"},
        observed_at=NOW,
    )
    source = evidence(
        150_001,
        captured_by_entity=harness.operator_id,
        content="Evidence inserted before the forced history failure.",
    )

    with pytest.raises(ValidationError, match="lifecycle_transition_id"):
        harness.persistence.construct_memory.create(
            envelope_for(harness, payload),
            payload,
            lifecycle_transition_id="not-a-uuid",
            approval_transition_id=uid(150_002),
            evidence_items=(source,),
            evidence_links=(
                EvidenceLink(
                    payload.record_id,
                    source.evidence_id,
                    "supports",
                    "Must roll back with the transaction.",
                ),
            ),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )

    counts = SqlProbe(harness.config).read(
        lambda connection: {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE "
                + (
                    "evidence_id = ?"
                    if table == "evidence_items"
                    else "record_id = ?"
                ),
                (
                    source.evidence_id
                    if table == "evidence_items"
                    else payload.record_id,
                ),
            ).fetchone()[0]
            for table in (
                "evidence_items",
                "records",
                "project_states",
                "record_evidence_links",
                "memory_record_lifecycle_transitions",
                "memory_record_approval_transitions",
            )
        }
    )
    assert set(counts.values()) == {0}
    assert not hasattr(harness.persistence.construct_memory, "approve")
    assert not hasattr(harness.persistence.construct_memory, "activate")


def test_missing_evidence_and_direct_truth_creation_fail_before_persistence(
    tmp_path,
) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    payload = ProjectStatePayload(
        record_id=uid(150_100),
        project_id=PROJECT_ENTITY_ID,
        state_type="priority",
        state_value={"priority": "governed memory"},
        observed_at=NOW,
    )
    record = envelope_for(harness, payload)
    with pytest.raises(ValidationError, match="explicit linked evidence"):
        harness.persistence.construct_memory.create(
            record,
            payload,
            lifecycle_transition_id=uid(150_101),
            approval_transition_id=uid(150_102),
            evidence_links=(),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )
    with pytest.raises(ValidationError, match="I3-A initial state"):
        harness.persistence.construct_memory.create(
            RecordEnvelope(
                **{
                    **{
                        field: getattr(record, field)
                        for field in RecordEnvelope.__dataclass_fields__
                    },
                    "lifecycle_state": "active",
                    "approval_status": "approved",
                }
            ),
            payload,
            lifecycle_transition_id=uid(150_103),
            approval_transition_id=uid(150_104),
            evidence_links=(),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )
    assert SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            "SELECT COUNT(*) FROM records WHERE record_id = ?",
            (payload.record_id,),
        ).fetchone()[0]
    ) == 0


def test_invalid_scope_and_model_only_preference_fail_without_partial_rows(
    tmp_path,
) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    doctrine = ConstructDoctrinePayload(
        record_id=uid(151_000),
        doctrine_statement="Invalid fixture must fail.",
        application_scopes=(uid(151_001),),
        interpretation_notes="The referenced scope does not exist.",
    )
    with pytest.raises(ValidationError, match="application scope"):
        create_payload(harness, doctrine, base=151_010)

    preference = PreferenceRecordPayload(
        record_id=uid(151_100),
        preference_subject_id=harness.operator_id,
        preference_category="invalid_inference",
        preference_statement="Model-only inference is insufficient.",
    )
    with pytest.raises(ValidationError, match="model inference alone"):
        create_payload(
            harness,
            preference,
            base=151_110,
            evidence_kind="model_output",
        )

    assert SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT COUNT(*) FROM records
            WHERE record_id IN (?, ?)
            """,
            (doctrine.record_id, preference.record_id),
        ).fetchone()[0]
    ) == 0


@pytest.mark.parametrize(
    "authority_class",
    (
        "nolan_byte_approved",
        "approved_project_policy",
        "validated_system_evidence",
    ),
)
def test_authority_relationship_rejects_every_non_nolan_floor(
    tmp_path,
    authority_class: str,
) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    payload = ConstructRelationshipPayload(
        uid(152_000),
        harness.operator_id,
        "has_final_authority_over",
        PROJECT_ENTITY_ID,
        "The type policy, not this wording, determines authority.",
    )
    create_payload(harness, payload, base=152_010)
    approval_evidence = evidence(
        152_020,
        captured_by_entity=harness.operator_id,
        content=f"Insufficient {authority_class} approval evidence.",
    )
    authority_record = authority(
        harness,
        152_021,
        evidence_ids=(approval_evidence.evidence_id,),
        authority_class=authority_class,
    )
    harness.runtime.register_authority(
        authority_record,
        evidence_items=(approval_evidence,),
    )

    with pytest.raises(ValidationError, match="type-insufficient"):
        MemoryKernel(harness.config).register_approval_grant(
            MemoryApprovalGrant(
                grant_id=uid(152_022),
                record_id=payload.record_id,
                target_status="approved",
                project_scope_id=harness.project_scope_id,
                authority_record_id=authority_record.authority_record_id,
                approved_by_entity_id=harness.operator_id,
                approved_at=NOW,
                evidence_id=approval_evidence.evidence_id,
            )
        )


def test_nolan_authority_approves_authority_relationship_and_nonauthority_uses_i3a(
    tmp_path,
) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    memory = MemoryKernel(harness.config)
    authority_payload = ConstructRelationshipPayload(
        uid(153_000),
        harness.operator_id,
        "has_final_authority_over",
        PROJECT_ENTITY_ID,
        "Final authority is encoded by the registered type.",
    )
    ordinary_payload = ConstructRelationshipPayload(
        uid(153_100),
        harness.participant_id,
        "draws_curriculum_from",
        PROJECT_ENTITY_ID,
        "This wording cannot convert a non-authority type into authority.",
    )
    create_payload(harness, authority_payload, base=153_010)
    create_payload(harness, ordinary_payload, base=153_110)

    for base, payload, authority_class in (
        (153_020, authority_payload, "nolan_approved"),
        (153_120, ordinary_payload, "nolan_byte_approved"),
    ):
        approval_evidence = evidence(
            base,
            captured_by_entity=harness.operator_id,
            content=f"Exact {authority_class} evidence.",
        )
        authority_record = authority(
            harness,
            base + 1,
            evidence_ids=(approval_evidence.evidence_id,),
            authority_class=authority_class,
        )
        harness.runtime.register_authority(
            authority_record,
            evidence_items=(approval_evidence,),
        )
        grant = MemoryApprovalGrant(
            grant_id=uid(base + 2),
            record_id=payload.record_id,
            target_status="approved",
            project_scope_id=harness.project_scope_id,
            authority_record_id=authority_record.authority_record_id,
            approved_by_entity_id=harness.operator_id,
            approved_at=NOW,
            evidence_id=approval_evidence.evidence_id,
        )
        memory.register_approval_grant(grant)
        memory.transition_approval(
            payload.record_id,
            transition_id=uid(base + 3),
            to_status="approved",
            reason_code="operator_approved_relationship",
            changed_at=NOW,
            changed_by_entity_id=harness.operator_id,
            approval_grant_id=grant.grant_id,
        )

    assert harness.persistence.construct_integrity.inspect().ok is True
    assert MemoryKernel(harness.config).reconstruct(authority_payload.record_id)[
        "approval_transitions"
    ][-1]["to_status"] == "approved"



def test_construct_creation_requires_explicit_consistent_principal(tmp_path) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    payload = ProjectStatePayload(
        record_id=uid(154_000),
        project_id=PROJECT_ENTITY_ID,
        state_type="phase",
        state_value={"phase": "I3-B"},
        observed_at=NOW,
    )
    source = evidence(
        154_010,
        captured_by_entity=harness.operator_id,
        content="Exact explicit-principal source.",
    )
    kwargs = {
        "lifecycle_transition_id": uid(154_011),
        "approval_transition_id": uid(154_012),
        "evidence_items": (source,),
        "evidence_links": (
            EvidenceLink(
                payload.record_id,
                source.evidence_id,
                "supports",
                "Explicit attribution fixture.",
            ),
        ),
    }
    with pytest.raises(TypeError, match="changed_by_principal"):
        harness.persistence.construct_memory.create(
            envelope_for(harness, payload),
            payload,
            **kwargs,
        )
    with pytest.raises(ValidationError, match="requires changed_by_entity_id"):
        harness.persistence.construct_memory.create(
            envelope_for(harness, payload),
            payload,
            changed_by_principal="operator",
            **kwargs,
        )
    with pytest.raises(ValidationError, match="cannot claim a human entity"):
        harness.persistence.construct_memory.create(
            envelope_for(harness, payload),
            payload,
            changed_by_principal="codex_development_harness",
            changed_by_entity_id=harness.operator_id,
            **kwargs,
        )


def test_project_state_replacement_requires_governed_ordered_supersession(
    tmp_path,
) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    old = ProjectStatePayload(
        record_id=uid(155_000),
        project_id=PROJECT_ENTITY_ID,
        state_type="phase",
        state_value={"phase": "I3-A"},
        observed_at=NOW,
    )
    create_payload(harness, old, base=155_010)
    memory = approve_to_lifecycle_approved(harness, old, base=155_020)
    memory.transition_lifecycle(
        old.record_id,
        transition_id=uid(155_026),
        to_state="active",
        reason_code="initial_project_state_activated",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )

    replacement = ProjectStatePayload(
        record_id=uid(155_100),
        project_id=PROJECT_ENTITY_ID,
        state_type="phase",
        state_value={"phase": "I3-B"},
        observed_at=NOW,
    )
    create_payload(
        harness,
        replacement,
        base=155_110,
        supersedes_record_id=old.record_id,
    )
    approve_to_lifecycle_approved(harness, replacement, base=155_120)

    with pytest.raises(ValidationError, match="existing active project state"):
        memory.transition_lifecycle(
            replacement.record_id,
            transition_id=uid(155_126),
            to_state="active",
            reason_code="invalid_early_activation",
            changed_at=NOW,
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )
    with pytest.raises(ValidationError, match="governed, type-matching replacement"):
        memory.transition_lifecycle(
            old.record_id,
            transition_id=uid(155_127),
            to_state="superseded",
            reason_code="invalid_unrelated_supersession",
            changed_at=NOW,
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )

    link_governed_supersession(
        harness,
        memory=memory,
        source_record_id=replacement.record_id,
        target_record_id=old.record_id,
        base=155_130,
    )
    memory.transition_lifecycle(
        old.record_id,
        transition_id=uid(155_136),
        to_state="superseded",
        reason_code="governed_project_state_replacement",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    memory.transition_lifecycle(
        replacement.record_id,
        transition_id=uid(155_137),
        to_state="active",
        reason_code="replacement_project_state_activated",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    assert harness.persistence.construct_integrity.inspect().ok is True


def test_terminology_replacement_requires_prior_term_to_be_superseded(
    tmp_path,
) -> None:
    harness = build_harness(tmp_path)
    old = TerminologyDefinitionPayload(
        record_id=uid(156_000),
        term="Straße",
        definition="Original governed definition.",
        definition_scope_id=harness.project_scope_id,
    )
    create_payload(harness, old, base=156_010)
    memory = approve_to_lifecycle_approved(harness, old, base=156_020)
    memory.transition_lifecycle(
        old.record_id,
        transition_id=uid(156_026),
        to_state="active",
        reason_code="initial_term_activated",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    replacement = TerminologyDefinitionPayload(
        record_id=uid(156_100),
        term="STRASSE",
        definition="Replacement governed definition.",
        definition_scope_id=harness.project_scope_id,
    )
    create_payload(
        harness,
        replacement,
        base=156_110,
        supersedes_record_id=old.record_id,
    )
    approve_to_lifecycle_approved(harness, replacement, base=156_120)
    link_governed_supersession(
        harness,
        memory=memory,
        source_record_id=replacement.record_id,
        target_record_id=old.record_id,
        base=156_130,
    )
    with pytest.raises(ValidationError, match="existing active terminology"):
        memory.transition_lifecycle(
            replacement.record_id,
            transition_id=uid(156_136),
            to_state="active",
            reason_code="invalid_parallel_term",
            changed_at=NOW,
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )
    memory.transition_lifecycle(
        old.record_id,
        transition_id=uid(156_137),
        to_state="superseded",
        reason_code="governed_term_replacement",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    memory.transition_lifecycle(
        replacement.record_id,
        transition_id=uid(156_138),
        to_state="active",
        reason_code="replacement_term_activated",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    assert harness.persistence.construct_integrity.inspect().ok is True
