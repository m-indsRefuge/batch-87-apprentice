from __future__ import annotations

from dataclasses import replace

import pytest

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.memory import (
    ArchitectureDecisionPayload,
    ConstructDoctrinePayload,
    ConstructEntityPayload,
    ConstructRelationshipPayload,
    PreferenceRecordPayload,
    ProjectStatePayload,
    TerminologyDefinitionPayload,
    construct_memory_content_hash,
    normalize_construct_term,
)
from batch87_apprentice.persistence.contracts import (
    RecordEnvelope,
    record_content_hash,
)
from tests.support.i2_fixtures import NOW, uid


def envelope(
    record_type: str,
    *,
    record_id: str = uid(110_000),
    subject_entity_id: str | None = None,
    agent_write_policy: str = "candidate_only",
) -> RecordEnvelope:
    return RecordEnvelope(
        record_id=record_id,
        record_family="construct_memory",
        record_type=record_type,
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
        provenance_summary="Deterministic I3-B contract fixture.",
        retrieval_policy_json=canonical_json_text({"retrieval_mode": "ordinary"}),
        deletion_policy_json=canonical_json_text({"deletion_mode": "governed"}),
        agent_write_policy=agent_write_policy,
        project_scope_id=uid(110_001),
        subject_entity_id=subject_entity_id,
        created_by_entity_id=uid(110_002),
    )


def valid_payloads() -> tuple[object, ...]:
    return (
        ConstructEntityPayload(uid(111_000), uid(111_001), "Known person."),
        ConstructRelationshipPayload(
            uid(112_000),
            uid(112_001),
            "participates_in",
            uid(112_002),
            "Participation is explicitly evidenced.",
        ),
        ArchitectureDecisionPayload(
            record_id=uid(113_000),
            decision_statement="Use direct SQLite access.",
            decision_scope=uid(113_001),
            rationale="The accepted baseline requires it.",
            alternatives=[{"name": "ORM", "accepted": False}],
            consequences=["Explicit transactions"],
            decision_status="accepted",
        ),
        ProjectStatePayload(
            record_id=uid(114_000),
            project_id=uid(114_001),
            state_type="phase",
            state_value={"name": "I3-B", "status": "implementation"},
            observed_at=NOW,
        ),
        ConstructDoctrinePayload(
            record_id=uid(115_000),
            doctrine_statement="Models propose; authority remains external.",
            application_scopes=[uid(115_001)],
            interpretation_notes="Apply literally during B87-S1.",
        ),
        TerminologyDefinitionPayload(
            record_id=uid(116_000),
            term="Construct memory",
            definition="Governed architectural and relational memory.",
            definition_scope_id=uid(116_001),
            deprecated_aliases=["world model"],
        ),
        PreferenceRecordPayload(
            record_id=uid(117_000),
            preference_subject_id=uid(117_001),
            preference_category="communication",
            preference_statement="Return evidence, not confidence.",
            context_constraints=[{"project": "Batch-87"}],
        ),
    )


@pytest.mark.parametrize("payload", valid_payloads())
def test_all_seven_payloads_expose_deterministic_canonical_and_database_values(
    payload,
) -> None:
    assert payload.database_values()["record_id"] == payload.record_id
    assert payload.canonical_content()["record_id"] == payload.record_id
    assert payload.RECORD_TYPE
    assert payload.TABLE


def test_structured_values_are_canonical_before_hashing() -> None:
    first = ProjectStatePayload(
        record_id=uid(118_000),
        project_id=uid(118_001),
        state_type="milestone",
        state_value={"z": 1, "a": {"y": 2, "b": 3}},
        observed_at=NOW,
    )
    second = ProjectStatePayload(
        record_id=first.record_id,
        project_id=first.project_id,
        state_type=first.state_type,
        state_value={"a": {"b": 3, "y": 2}, "z": 1},
        observed_at=NOW,
    )
    record = envelope(
        "project_state",
        record_id=first.record_id,
        subject_entity_id=first.project_id,
    )

    assert first.state_value_json == second.state_value_json
    assert construct_memory_content_hash(record, first) == (
        construct_memory_content_hash(record, second)
    )


def test_term_comparison_is_trimmed_unicode_casefolded_and_deterministic() -> None:
    assert normalize_construct_term("  Straße  ") == "strasse"
    assert normalize_construct_term("STRASSE") == "strasse"


def test_combined_hash_covers_payload_type_payload_and_envelope() -> None:
    payload = ConstructEntityPayload(uid(119_000), uid(119_001), "First description.")
    record = envelope(
        "construct_entity",
        record_id=payload.record_id,
        subject_entity_id=payload.entity_id,
    )
    changed_payload = ConstructEntityPayload(
        payload.record_id,
        payload.entity_id,
        "Changed description.",
    )
    changed_record = replace(record, provenance_summary="Changed provenance.")

    digest = construct_memory_content_hash(record, payload)
    assert digest != record_content_hash(record)
    assert digest != construct_memory_content_hash(record, changed_payload)
    assert digest != construct_memory_content_hash(changed_record, payload)


def test_contracts_fail_closed_for_invalid_values_and_pair_mismatch() -> None:
    with pytest.raises(ValidationError, match="unsupported Construct relationship"):
        ConstructRelationshipPayload(
            uid(120_000),
            uid(120_001),
            "invented_authority",
            uid(120_002),
            "Unsupported.",
        )
    with pytest.raises(ValidationError, match="self-reference"):
        ConstructRelationshipPayload(
            uid(120_003),
            uid(120_004),
            "participates_in",
            uid(120_004),
            "Invalid self-link.",
        )
    with pytest.raises(ValidationError, match="bidirectional"):
        ConstructRelationshipPayload(
            uid(120_005),
            uid(120_006),
            "draws_curriculum_from",
            uid(120_007),
            "Invalid reverse authority implication.",
            True,
        )
    with pytest.raises(ValidationError, match="unsupported value"):
        ProjectStatePayload(
            record_id=uid(120_008),
            project_id=uid(120_009),
            state_type="truth",
            state_value={},
            observed_at=NOW,
        )
    with pytest.raises(ValidationError, match="object or array"):
        ProjectStatePayload(
            record_id=uid(120_010),
            project_id=uid(120_011),
            state_type="phase",
            state_value=1,
            observed_at=NOW,
        )
    with pytest.raises(ValidationError, match="YYYY-MM-DD"):
        ProjectStatePayload(
            record_id=uid(120_012),
            project_id=uid(120_013),
            state_type="phase",
            state_value={},
            observed_at="2026-07-25",
        )
    with pytest.raises(ValidationError, match="exceptions must remain empty"):
        ConstructDoctrinePayload(
            record_id=uid(120_014),
            doctrine_statement="No exceptions.",
            application_scopes=[uid(120_015)],
            interpretation_notes="Literal.",
            exceptions=["invented"],
        )
    with pytest.raises(ValidationError, match="non-empty"):
        ConstructEntityPayload(uid(120_016), uid(120_017), " ")

    payload = ConstructEntityPayload(uid(120_018), uid(120_019), "Known.")
    with pytest.raises(ValidationError, match="payload type"):
        construct_memory_content_hash(
            envelope(
                "project_state",
                record_id=payload.record_id,
                subject_entity_id=payload.entity_id,
            ),
            payload,
        )
