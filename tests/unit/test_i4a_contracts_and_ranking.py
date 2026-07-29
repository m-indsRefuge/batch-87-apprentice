from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.context import (
    CONTEXT_SECTIONS,
    DeterministicFallbackRanker,
    RetrievalCandidate,
    RetrievalRequest,
)
from tests.support.i2_fixtures import NOW, uid


def request(*, provenance: dict | None = None) -> RetrievalRequest:
    return RetrievalRequest(
        retrieval_request_id=uid(1_800_000),
        contract_version="1.0.0",
        task_id=uid(1_800_001),
        session_id=uid(1_800_002),
        project_scope_id=uid(1_800_003),
        task_context_finalization_id=uid(1_800_004),
        purpose="Assemble exact governed context.",
        requested_sections=CONTEXT_SECTIONS,
        requested_at=NOW,
        requested_by_principal="operator",
        ranking_strategy="deterministic_fallback_v1",
        provenance_json=canonical_json_text(
            provenance or {"source": "deterministic unit fixture"}
        ),
    )


def candidate(
    number: int,
    *,
    required: bool,
    order: int,
    section: str,
    source_kind: str,
) -> RetrievalCandidate:
    context_kind = {
        "policy": "policy",
        "evidence": "evidence",
        "memory": "construct_memory",
    }[section]
    return RetrievalCandidate(
        context_item_id=uid(number),
        context_kind=context_kind,
        source_kind=source_kind,
        source_id=uid(number + 100),
        source_content_hash=f"{number % 16:x}" * 64,
        required=required,
        injection_order=order,
        target_section=section,
        eligibility_status="eligible",
        eligibility_reasons=(),
        eligibility_decision_hash=f"{(number + 1) % 16:x}" * 64,
        materialization_status="materialized",
        materialization_reasons=(),
        materialized_json=canonical_json_text(
            {"context_item_id": uid(number)}
        ),
    )


def test_retrieval_request_is_immutable_canonical_and_deterministic() -> None:
    first = request()
    second = request()

    assert first == second
    assert first.canonical_json == second.canonical_json
    assert first.content_hash == second.content_hash
    assert tuple(first.canonical_value()["requested_sections"]) == CONTEXT_SECTIONS
    with pytest.raises(FrozenInstanceError):
        first.purpose = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract_version", "2.0.0"),
        ("task_id", "not-a-uuid"),
        ("session_id", "not-a-uuid"),
        ("project_scope_id", "not-a-uuid"),
        ("task_context_finalization_id", "not-a-uuid"),
        ("purpose", ""),
        ("requested_sections", ("task", "authority")),
        ("requested_at", "2026-07-23"),
        ("requested_by_principal", "apprentice"),
        ("ranking_strategy", "semantic_model"),
        ("provenance_json", "[]"),
    ],
)
def test_retrieval_request_rejects_invalid_contract_fields(
    field: str,
    value: object,
) -> None:
    values = {
        name: getattr(request(), name)
        for name in RetrievalRequest.__dataclass_fields__
    }
    values[field] = value

    with pytest.raises(ValidationError):
        RetrievalRequest(**values)


@pytest.mark.parametrize(
    "prohibited_key",
    [
        "provider",
        "provider_name",
        "model",
        "model_name",
        "inference_settings",
        "tool_definitions",
        "raw_sql",
        "filesystem_path",
        "network_destination",
        "credentials",
        "prompt_role",
        "executable_code",
    ],
)
def test_retrieval_request_rejects_structural_provider_or_capability_fields(
    prohibited_key: str,
) -> None:
    with pytest.raises(ValidationError):
        request(provenance={"nested": {prohibited_key: "forbidden"}})


def test_request_mapping_requires_exact_known_fields() -> None:
    value = request().canonical_value()
    value["unexpected"] = True

    with pytest.raises(ValidationError, match="unsupported"):
        RetrievalRequest.from_mapping(value)

    value.pop("unexpected")
    value.pop("purpose")
    with pytest.raises(ValidationError, match="missing"):
        RetrievalRequest.from_mapping(value)


def test_fallback_ranker_is_deterministic_and_records_components() -> None:
    inputs = (
        candidate(
            1_810_000,
            required=False,
            order=0,
            section="memory",
            source_kind="memory_record",
        ),
        candidate(
            1_810_001,
            required=True,
            order=1,
            section="evidence",
            source_kind="evidence",
        ),
        candidate(
            1_810_002,
            required=False,
            order=2,
            section="policy",
            source_kind="governance_rule",
        ),
        candidate(
            1_810_003,
            required=True,
            order=3,
            section="policy",
            source_kind="governance_rule",
        ),
    )
    ranker = DeterministicFallbackRanker()

    first = ranker.rank(request(), inputs)
    second = ranker.rank(request(), inputs)

    assert first == second
    assert [entry.final_rank for entry in first] == [0, 1, 2, 3]
    assert [entry.candidate.injection_order for entry in first[:2]] == [1, 3]
    assert [entry.candidate.target_section for entry in first[2:]] == [
        "policy",
        "memory",
    ]
    assert all(entry.components.stable_tiebreak for entry in first)
    assert all("no semantic relevance is claimed" in entry.explanation for entry in first)
    assert canonical_json_text(
        [entry.canonical_value() for entry in first]
    ) == canonical_json_text(
        [entry.canonical_value() for entry in second]
    )


def test_fallback_ranker_preserves_required_finalized_relative_order() -> None:
    inputs = (
        candidate(
            1_820_000,
            required=True,
            order=0,
            section="memory",
            source_kind="memory_record",
        ),
        candidate(
            1_820_001,
            required=True,
            order=1,
            section="policy",
            source_kind="governance_rule",
        ),
        candidate(
            1_820_002,
            required=True,
            order=2,
            section="evidence",
            source_kind="evidence",
        ),
    )

    ranked = DeterministicFallbackRanker().rank(request(), inputs)

    assert [entry.candidate.injection_order for entry in ranked] == [0, 1, 2]


def test_fallback_ranker_accepts_only_immutable_includable_candidates() -> None:
    valid = candidate(
        1_830_000,
        required=False,
        order=0,
        section="evidence",
        source_kind="evidence",
    )
    ineligible = RetrievalCandidate(
        context_item_id=uid(1_830_001),
        context_kind="evidence",
        source_kind="evidence",
        source_id=uid(1_830_101),
        source_content_hash="a" * 64,
        required=False,
        injection_order=1,
        target_section="evidence",
        eligibility_status="ineligible",
        eligibility_reasons=("source_not_task_bound",),
        eligibility_decision_hash="b" * 64,
        materialization_status="not_attempted",
        materialization_reasons=(),
        materialized_json=None,
    )
    ranker = DeterministicFallbackRanker()

    with pytest.raises(TypeError):
        ranker.rank(request(), [valid])  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="eligible materialized"):
        ranker.rank(request(), (valid, ineligible))
    with pytest.raises(ValidationError, match="duplicate"):
        ranker.rank(request(), (valid, valid))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_content_hash", "bad"),
        ("target_section", "task"),
        ("eligibility_status", "unknown"),
        ("materialization_status", "unknown"),
        ("injection_order", -1),
        ("required", 1),
    ],
)
def test_retrieval_candidate_rejects_invalid_structural_state(
    field: str,
    value: object,
) -> None:
    valid = candidate(
        1_840_000,
        required=False,
        order=0,
        section="evidence",
        source_kind="evidence",
    )
    values = {
        name: getattr(valid, name)
        for name in RetrievalCandidate.__dataclass_fields__
    }
    values[field] = value

    with pytest.raises(ValidationError):
        RetrievalCandidate(**values)
