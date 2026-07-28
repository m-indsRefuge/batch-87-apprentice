from __future__ import annotations

import pytest

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.memory import (
    ActiveUncertaintyPayload,
    TaskContextFinalization,
    TaskContextItem,
    TypedSourceReference,
    UncertaintyResolution,
    active_uncertainty_content_hash,
    validate_active_uncertainty_pair,
)
from batch87_apprentice.persistence.contracts import RecordEnvelope
from tests.support.i2_fixtures import NOW, uid


HASH = "a" * 64


def uncertainty_pair() -> tuple[RecordEnvelope, ActiveUncertaintyPayload]:
    payload = ActiveUncertaintyPayload(
        record_id=uid(910_000),
        task_id=uid(910_001),
        session_id=uid(910_002),
        project_scope_id=uid(910_003),
        uncertainty_statement="The exact source interpretation is unresolved.",
        impact="blocking",
        resolution_required=True,
        created_at=NOW,
        created_by_principal="operator",
    )
    envelope = RecordEnvelope(
        record_id=payload.record_id,
        record_family="session_task_memory",
        record_type="active_uncertainty",
        schema_version="1.0.0",
        lifecycle_state="observed",
        approval_status="not_required",
        authority_class="nolan_approved",
        certainty_class="unknown",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="project_duration",
        training_eligibility="prohibited",
        created_at=NOW,
        source_kind="human_statement",
        provenance_summary="Explicit deterministic uncertainty.",
        retrieval_policy_json=canonical_json_text(
            {"allowed_project_scope_ids": [payload.project_scope_id]}
        ),
        deletion_policy_json=canonical_json_text(
            {"deletion_mode": "governed"}
        ),
        agent_write_policy="candidate_only",
        project_scope_id=payload.project_scope_id,
        session_id=payload.session_id,
        task_id=payload.task_id,
        created_by_entity_id=uid(910_004),
    )
    return envelope, payload


def test_typed_source_requires_exactly_one_identifier() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        TypedSourceReference()
    with pytest.raises(ValidationError, match="exactly one"):
        TypedSourceReference(
            memory_record_id=uid(1),
            evidence_id=uid(2),
        )


@pytest.mark.parametrize(
    ("context_kind", "source"),
    (
        ("constitution", TypedSourceReference(governance_rule_id=uid(1))),
        ("policy", TypedSourceReference(governance_rule_id=uid(2))),
        ("construct_memory", TypedSourceReference(memory_record_id=uid(3))),
        ("approved_lesson", TypedSourceReference(memory_record_id=uid(4))),
        ("evidence", TypedSourceReference(evidence_id=uid(5))),
        ("session_instruction", TypedSourceReference(evidence_id=uid(6))),
    ),
)
def test_context_kinds_require_explicit_typed_sources(
    context_kind: str,
    source: TypedSourceReference,
) -> None:
    item = TaskContextItem(
        context_item_id=uid(10),
        task_id=uid(11),
        session_id=uid(12),
        project_scope_id=uid(13),
        context_kind=context_kind,
        source=source,
        injection_order=0,
        required=True,
        content_hash=HASH,
        created_at=NOW,
        created_by_principal="codex_development_harness",
    )
    assert item.canonical_value()["source"] == source.canonical_value()
    assert len(item.canonical_hash) == 64


def test_context_rejects_wrong_source_kind_and_unsupported_principal() -> None:
    with pytest.raises(ValidationError, match="requires source_kind"):
        TaskContextItem(
            context_item_id=uid(20),
            task_id=uid(21),
            session_id=uid(22),
            project_scope_id=uid(23),
            context_kind="approved_lesson",
            source=TypedSourceReference(evidence_id=uid(24)),
            injection_order=0,
            required=True,
            content_hash=HASH,
            created_at=NOW,
            created_by_principal="operator",
        )
    with pytest.raises(ValidationError, match="created_by_principal"):
        TaskContextItem(
            context_item_id=uid(25),
            task_id=uid(26),
            session_id=uid(27),
            project_scope_id=uid(28),
            context_kind="evidence",
            source=TypedSourceReference(evidence_id=uid(29)),
            injection_order=0,
            required=True,
            content_hash=HASH,
            created_at=NOW,
            created_by_principal="apprentice",
        )


def test_finalization_preserves_exact_ordered_identifiers_and_hashes() -> None:
    finalization = TaskContextFinalization(
        finalization_id=uid(30),
        task_id=uid(31),
        session_id=uid(32),
        project_scope_id=uid(33),
        ordered_item_ids=(uid(34), uid(35)),
        ordered_item_hashes=("a" * 64, "b" * 64),
        finalized_at=NOW,
        finalized_by_principal="operator",
    )
    assert [item["context_item_id"] for item in finalization.canonical_value()[
        "ordered_items"
    ]] == [uid(34), uid(35)]
    assert len(finalization.content_hash) == 64


def test_blocking_uncertainty_requires_resolution() -> None:
    with pytest.raises(ValidationError, match="requires resolution"):
        ActiveUncertaintyPayload(
            record_id=uid(40),
            task_id=uid(41),
            session_id=uid(42),
            project_scope_id=uid(43),
            uncertainty_statement="Blocking uncertainty.",
            impact="blocking",
            resolution_required=False,
            created_at=NOW,
            created_by_principal="operator",
        )


def test_uncertainty_envelope_binding_and_hash_are_deterministic() -> None:
    envelope, payload = uncertainty_pair()
    validate_active_uncertainty_pair(envelope, payload)
    assert active_uncertainty_content_hash(
        envelope,
        payload,
    ) == active_uncertainty_content_hash(envelope, payload)

    wrong_payload = ActiveUncertaintyPayload(
        record_id=payload.record_id,
        task_id=uid(910_099),
        session_id=payload.session_id,
        project_scope_id=payload.project_scope_id,
        uncertainty_statement=payload.uncertainty_statement,
        impact=payload.impact,
        resolution_required=payload.resolution_required,
        created_at=payload.created_at,
        created_by_principal=payload.created_by_principal,
    )
    with pytest.raises(ValidationError, match="exactly match"):
        validate_active_uncertainty_pair(envelope, wrong_payload)


def test_resolution_rejects_policy_as_an_ambiguous_resolution_source() -> None:
    with pytest.raises(ValidationError, match="evidence or a governed record"):
        UncertaintyResolution(
            resolution_id=uid(50),
            uncertainty_record_id=uid(51),
            task_id=uid(52),
            session_id=uid(53),
            project_scope_id=uid(54),
            source=TypedSourceReference(governance_rule_id=uid(55)),
            source_content_hash=HASH,
            resolved_at=NOW,
            created_by_principal="operator",
        )
