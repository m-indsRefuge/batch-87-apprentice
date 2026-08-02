from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.evaluation import (
    CandidateMetadata,
    EvaluationCondition,
    EvaluationResult,
    FixtureManifestEntry,
    FixtureSetManifest,
    ScoreDimension,
    discover_fixture_set,
)
from batch87_apprentice.evaluation.planning import build_evaluation_plan
from tests.support.i2_fixtures import IdentifierSequence, NOW, uid
from tests.support.pre_i5_fixtures import (
    PLAN_FAMILY_ID,
    PLAN_ID,
    candidate,
    configuration,
    fixture_set,
    result_for_run,
    write_fixture_set,
)


def test_candidate_contract_is_immutable_canonical_and_origin_separate() -> None:
    value = candidate()

    assert value.canonical_json == canonical_json_text(value.canonical_value())
    assert value.candidate_origin == "synthetic_mock"
    assert value.lifecycle_state == "registered"
    assert value.admission_state == "not_assessed"
    with pytest.raises(FrozenInstanceError):
        value.lifecycle_state = "retired"  # type: ignore[misc]
    assert replace(value, model_revision="synthetic-revision-2").content_hash != (
        value.content_hash
    )


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("lifecycle_state", "active"),
        ("admission_state", "accepted"),
        ("admission_state", "activated"),
    ),
)
def test_candidate_cannot_be_accepted_or_activated(
    field: str,
    invalid: str,
) -> None:
    with pytest.raises(ValidationError):
        replace(candidate(), **{field: invalid})


@pytest.mark.parametrize(
    "metadata",
    (
        {"url": "external"},
        {"model_path": "artifact"},
        {"credential": "redacted"},
        {"nested": {"endpoint": "local"}},
        {"source": "https://example.invalid"},
        {"source": "C:/models/candidate"},
    ),
)
def test_candidate_metadata_rejects_live_capability_shapes(metadata: dict) -> None:
    with pytest.raises(ValidationError):
        replace(candidate(), provenance_json=canonical_json_text(metadata))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("model_family", "https://example.invalid/model"),
        ("model_revision", "C:/models/revision"),
        ("quantization", "sk-not-a-real-token"),
        ("licence_identifier", "/private/licence"),
    ),
)
def test_candidate_scalar_metadata_rejects_capability_values(
    field: str,
    value: str,
) -> None:
    with pytest.raises(ValidationError):
        replace(candidate(), **{field: value})


@pytest.mark.parametrize(
    "name",
    (
        "hidden_thought_quality",
        "chain_of_thought_accuracy",
        "sentience",
        "loyalty",
        "self_preservation",
    ),
)
def test_score_schema_rejects_hidden_or_anthropomorphic_dimensions(
    name: str,
) -> None:
    with pytest.raises(ValidationError):
        ScoreDimension(name=name, description="Forbidden dimension.")


def test_score_schema_rejects_forbidden_semantics_in_description() -> None:
    with pytest.raises(ValidationError):
        ScoreDimension(
            name="quality",
            description="Scores hidden reasoning quality.",
        )


def test_configuration_hash_covers_conditions_repetitions_and_resources() -> None:
    fixtures = fixture_set()
    first = configuration(fixtures.manifest)
    changed = replace(first, timeout_ms=first.timeout_ms + 1)
    repeated = replace(first, repetitions=first.repetitions + 1)
    condition_changed = replace(
        first,
        conditions=(
            replace(
                first.conditions[0],
                ablation_metadata_json=canonical_json_text(
                    {"memory_available": False}
                ),
            ),
            *first.conditions[1:],
        ),
    )

    assert first.canonical_json == canonical_json_text(first.canonical_value())
    assert len({first.content_hash, changed.content_hash, repeated.content_hash}) == 3
    assert condition_changed.content_hash != first.content_hash


def test_fixture_discovery_is_exact_ordered_and_hash_verified(tmp_path: Path) -> None:
    expected = write_fixture_set(tmp_path / "fixtures")

    discovered = discover_fixture_set(tmp_path / "fixtures", expected.manifest)

    assert discovered == expected
    assert tuple(item.entry.ordinal for item in discovered.fixtures) == (0, 1)
    assert tuple(item.entry.source_name for item in discovered.fixtures) == (
        "fixture_00.json",
        "fixture_01.json",
    )


def test_fixture_discovery_rejects_missing_unlisted_and_altered_files(
    tmp_path: Path,
) -> None:
    expected = write_fixture_set(tmp_path / "fixtures")
    missing = tmp_path / "fixtures" / expected.fixtures[0].entry.source_name
    missing.unlink()
    with pytest.raises(ValidationError, match="missing"):
        discover_fixture_set(tmp_path / "fixtures", expected.manifest)

    missing.write_bytes(expected.fixtures[0].exact_bytes)
    (tmp_path / "fixtures" / "unlisted.json").write_text("{}", "utf-8")
    with pytest.raises(ValidationError, match="unlisted"):
        discover_fixture_set(tmp_path / "fixtures", expected.manifest)

    (tmp_path / "fixtures" / "unlisted.json").unlink()
    missing.write_bytes(expected.fixtures[0].exact_bytes + b"\n")
    with pytest.raises(ValidationError, match="hash changed"):
        discover_fixture_set(tmp_path / "fixtures", expected.manifest)


def test_fixture_manifest_rejects_duplicate_identity_order_source_and_hash() -> None:
    valid = fixture_set().manifest
    first = valid.entries[0]
    builders = (
        lambda: replace(valid, entries=(first, replace(first, ordinal=1))),
        lambda: replace(
            valid,
            entries=(first, replace(valid.entries[1], source_name=first.source_name)),
        ),
        lambda: replace(
            valid,
            entries=(first, replace(valid.entries[1], content_hash=first.content_hash)),
        ),
        lambda: replace(valid, entries=tuple(reversed(valid.entries))),
    )
    for build in builders:
        with pytest.raises(ValidationError):
            build()


def test_fixture_manifest_rejects_unsafe_source_name() -> None:
    entry = fixture_set().manifest.entries[0]
    with pytest.raises(ValidationError):
        replace(entry, source_name="../fixture.json")
    with pytest.raises(ValidationError):
        FixtureManifestEntry(
            fixture_id=uid(8_009_001),
            source_name="fixture.txt",
            ordinal=0,
            content_hash=entry.content_hash,
        )


def test_plan_generation_is_reproducible_blinded_and_ordinal() -> None:
    fixtures = fixture_set()
    config = configuration(fixtures.manifest, repetitions=2)
    kwargs = {
        "plan_id": PLAN_ID,
        "plan_family_id": PLAN_FAMILY_ID,
        "plan_version": "1.0.0",
        "configuration": config,
        "fixture_set": fixtures,
        "candidates": (candidate(),),
        "clock": lambda: NOW,
    }
    first = build_evaluation_plan(
        **kwargs,
        identifier_factory=IdentifierSequence(8_300_000),
    )
    second = build_evaluation_plan(
        **kwargs,
        identifier_factory=IdentifierSequence(8_300_000),
    )

    assert first == second
    assert first.content_hash == second.content_hash
    assert len(first.runs) == 12
    assert tuple(run.run_ordinal for run in first.runs) == tuple(range(12))
    assert candidate().candidate_id not in tuple(
        run.blind_candidate_id for run in first.runs
    )
    assert all(
        run.blind_candidate_id.startswith("blind_") for run in first.runs
    )
    assert {run.condition_label for run in first.runs} == {
        "enabled",
        "withheld",
        "over_transfer",
    }


def test_result_contract_separates_runtime_and_candidate_metadata() -> None:
    fixtures = fixture_set()
    config = configuration(fixtures.manifest, repetitions=1)
    plan = build_evaluation_plan(
        plan_id=PLAN_ID,
        plan_family_id=PLAN_FAMILY_ID,
        plan_version="1.0.0",
        configuration=config,
        fixture_set=fixtures,
        candidates=(candidate(),),
        identifier_factory=IdentifierSequence(8_400_000),
        clock=lambda: NOW,
    )
    result = result_for_run(plan.runs[0], number=8_400_100)
    value = result.canonical_value()

    assert value["runtime_observed"]["latency_ms"] == 10
    assert value["candidate_reported_metadata"]["classification"] == (
        "candidate_reported"
    )
    assert "candidate_reported_metadata" not in value["runtime_observed"]


def test_outcome_shapes_fail_closed_independently_of_condition() -> None:
    fixtures = fixture_set()
    config = configuration(fixtures.manifest, repetitions=1)
    plan = build_evaluation_plan(
        plan_id=PLAN_ID,
        plan_family_id=PLAN_FAMILY_ID,
        plan_version="1.0.0",
        configuration=config,
        fixture_set=fixtures,
        candidates=(candidate(),),
        identifier_factory=IdentifierSequence(8_500_000),
        clock=lambda: NOW,
    )
    enabled = next(run for run in plan.runs if run.condition_label == "enabled")
    completed = result_for_run(enabled, number=8_500_100)
    with pytest.raises(ValidationError):
        replace(completed, outcome="critical_failure")
    with pytest.raises(ValidationError):
        replace(completed, outcome="withheld")


def test_condition_labels_are_closed() -> None:
    value = configuration(fixture_set().manifest).conditions[0]
    with pytest.raises(ValidationError):
        replace(value, label="candidate_accepted")
    with pytest.raises(ValidationError):
        EvaluationCondition(
            condition_id=uid(8_600_001),
            name="live_execution",
            label="enabled",
            ordinal=0,
            ablation_metadata_json=canonical_json_text(
                {"provider_configuration": "forbidden"}
            ),
        )
