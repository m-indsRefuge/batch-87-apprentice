from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.memory import (
    CORRECTION_ISSUER_CLASSES,
    CORRECTION_SEVERITIES,
    EPISODE_KINDS,
    EPISODE_OUTCOMES,
    CorrectionPayload,
    EpisodePayload,
    correction_content_hash,
    episode_content_hash,
    validate_episode_pair,
)
from batch87_apprentice.memory.episode_correction_contracts import (
    correction_from_database,
    episode_from_database,
)
from batch87_apprentice.persistence.contracts import RecordEnvelope
from tests.support.i2_fixtures import NOW, uid


def envelope(record_id: str, record_type: str) -> RecordEnvelope:
    return RecordEnvelope(
        record_id=record_id,
        record_family="episodic_memory",
        record_type=record_type,
        schema_version="1.0.0",
        lifecycle_state="observed" if record_type == "episode" else "reviewed",
        approval_status="pending",
        authority_class="validated_system_evidence",
        certainty_class="verified",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="project_duration",
        training_eligibility="prohibited",
        created_at=NOW,
        source_kind="runtime_event",
        provenance_summary="Exact C2 fixture.",
        retrieval_policy_json=canonical_json_text({"mode": "ordinary"}),
        deletion_policy_json=canonical_json_text({"mode": "governed"}),
        agent_write_policy="prohibited",
        project_scope_id=uid(1),
        session_id=uid(2) if record_type == "episode" else None,
    )


def episode(**overrides) -> EpisodePayload:
    values = {
        "record_id": uid(100),
        "episode_kind": "task",
        "summary": "Exact occurrence.",
        "outcome": "completed",
        "input_evidence_ids": (uid(101), uid(102)),
        "output_evidence_ids": (uid(103),),
        "evaluation_record_ids": (uid(104), uid(105)),
    }
    values.update(overrides)
    return EpisodePayload(**values)


def correction(**overrides) -> CorrectionPayload:
    values = {
        "record_id": uid(200),
        "target_episode_id": uid(201),
        "target_output_evidence_id": uid(202),
        "problem_statement": "Exact problem.",
        "corrected_interpretation": "Exact corrected interpretation.",
        "correction_category": "interpretation_error",
        "issued_by_entity_id": uid(203),
        "issuer_class": "nolan",
        "severity": "material",
    }
    values.update(overrides)
    return CorrectionPayload(**values)


def test_exact_c2_enums_are_closed() -> None:
    assert EPISODE_KINDS == {
        "task",
        "conversation",
        "evaluation",
        "failure",
        "correction",
        "experiment",
    }
    assert EPISODE_OUTCOMES == {
        "completed",
        "partial",
        "failed",
        "stopped",
        "rejected",
    }
    assert CORRECTION_ISSUER_CLASSES == {
        "nolan",
        "byte",
        "nolan_byte",
        "approved_evaluator",
    }
    assert CORRECTION_SEVERITIES == {"minor", "material", "critical"}


@pytest.mark.parametrize(
    ("factory", "field"),
    ((episode, "summary"), (correction, "problem_statement")),
)
def test_payloads_are_frozen(factory, field: str) -> None:
    payload = factory()
    with pytest.raises((FrozenInstanceError, AttributeError)):
        setattr(payload, field, "changed")


def test_episode_preserves_order_and_hashes_it_deterministically() -> None:
    payload = episode()
    record = envelope(payload.record_id, "episode")
    assert episode_content_hash(record, payload) == episode_content_hash(record, payload)
    reordered = episode(
        input_evidence_ids=tuple(reversed(payload.input_evidence_ids))
    )
    assert episode_content_hash(record, payload) != episode_content_hash(
        record,
        reordered,
    )


def test_correction_hash_covers_ordered_support_and_target_issuer_lineage() -> None:
    payload = correction()
    record = envelope(payload.record_id, "correction")
    support = (uid(210), uid(211))
    digest = correction_content_hash(record, payload, support)
    assert digest == correction_content_hash(record, payload, support)
    assert digest != correction_content_hash(record, payload, tuple(reversed(support)))
    assert digest != correction_content_hash(
        record,
        replace(payload, issued_by_entity_id=uid(212)),
        support,
    )


@pytest.mark.parametrize(
    "overrides",
    (
        {"input_evidence_ids": (uid(101), uid(101))},
        {"output_evidence_ids": (uid(101),), "input_evidence_ids": (uid(101),)},
        {"input_evidence_ids": (), "output_evidence_ids": ()},
        {"outcome": "unknown"},
        {"episode_kind": "lesson"},
        {"summary": "  "},
        {"record_id": "not-an-identifier"},
    ),
)
def test_episode_rejects_malformed_contract(overrides) -> None:
    with pytest.raises(ValidationError):
        episode(**overrides)


@pytest.mark.parametrize(
    "overrides",
    (
        {"issuer_class": "model"},
        {"severity": "catastrophic"},
        {"problem_statement": ""},
        {"corrected_interpretation": " "},
        {"correction_category": ""},
        {"issued_by_entity_id": "invalid"},
    ),
)
def test_correction_rejects_malformed_contract(overrides) -> None:
    with pytest.raises(ValidationError):
        correction(**overrides)


def test_payloads_have_no_optional_mandatory_fields() -> None:
    with pytest.raises(TypeError):
        EpisodePayload(
            record_id=uid(300),
            episode_kind="task",
            summary="Missing outcome and lineage.",
        )
    with pytest.raises(TypeError):
        CorrectionPayload(
            record_id=uid(301),
            target_episode_id=uid(302),
            target_output_evidence_id=uid(303),
        )


def test_exact_database_round_trip_preserves_episode_order() -> None:
    payload = episode()
    rebuilt = episode_from_database(
        payload.database_values(),
        input_evidence_ids=payload.input_evidence_ids,
        output_evidence_ids=payload.output_evidence_ids,
        evaluation_record_ids=payload.evaluation_record_ids,
    )
    assert rebuilt == payload
    assert rebuilt.canonical_json == payload.canonical_json


def test_exact_database_round_trip_preserves_correction() -> None:
    payload = correction()
    rebuilt = correction_from_database(payload.database_values())
    assert rebuilt == payload
    assert rebuilt.canonical_json == payload.canonical_json


@pytest.mark.parametrize(
    "changes",
    (
        {"record_family": "construct_memory"},
        {"record_type": "correction"},
        {"project_scope_id": None},
        {"session_id": None},
        {"lifecycle_state": "active"},
        {"approval_status": "approved"},
        {"agent_write_policy": "candidate_only"},
        {"sensitivity_class": "restricted"},
        {"privacy_class": "personal"},
        {"training_eligibility": "approved"},
    ),
)
def test_episode_pair_fails_closed_on_envelope_boundary(changes) -> None:
    payload = episode()
    record = replace(envelope(payload.record_id, "episode"), **changes)
    with pytest.raises(ValidationError):
        validate_episode_pair(record, payload)


def test_correction_support_requires_separate_nonempty_ordered_ids() -> None:
    payload = correction()
    record = envelope(payload.record_id, "correction")
    with pytest.raises(ValidationError):
        correction_content_hash(record, payload, ())
    with pytest.raises(ValidationError):
        correction_content_hash(record, payload, (uid(210), uid(210)))
    with pytest.raises(ValidationError):
        correction_content_hash(
            record,
            payload,
            (payload.target_output_evidence_id,),
        )
