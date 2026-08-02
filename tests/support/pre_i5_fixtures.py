"""Deterministic B87-PRE-I5 fixture, plan, and result builders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.hashing import sha256_bytes
from batch87_apprentice.evaluation import (
    CandidateMetadata,
    CriticalFailureDefinition,
    CriticalFailureObservation,
    CriticalFailureSchema,
    DeterministicEvaluationService,
    EvaluationCondition,
    EvaluationConfiguration,
    EvaluationPlan,
    EvaluationResult,
    FixtureDefinition,
    FixtureManifestEntry,
    FixtureSet,
    FixtureSetManifest,
    ResourceLimits,
    RuntimeObservation,
    ScoreDimension,
    ScoreObservation,
    ScoreSchema,
)
from batch87_apprentice.persistence import DatabaseConfig, PersistenceService
from tests.support.i2_fixtures import IdentifierSequence, LATER, NOW, uid

SUITE_ID = uid(8_000_001)
FIXTURE_SET_ID = uid(8_000_002)
CONFIGURATION_ID = uid(8_000_003)
CANDIDATE_ID = uid(8_000_004)
PLAN_ID = uid(8_000_005)


def candidate(
    *,
    candidate_id: str = CANDIDATE_ID,
    revision: str = "synthetic-revision-1",
) -> CandidateMetadata:
    return CandidateMetadata(
        candidate_id=candidate_id,
        candidate_origin="synthetic_mock",
        lifecycle_state="registered",
        admission_state="not_assessed",
        model_family="synthetic/mock-family",
        model_revision=revision,
        quantization="none",
        artifact_format="synthetic",
        licence_identifier="synthetic-test-only",
        provenance_json=canonical_json_text(
            {"classification": "synthetic", "source_record": "pre_i5_fixture"}
        ),
        compatibility_json=canonical_json_text(
            {
                "architecture": "metadata_only",
                "evaluation_ready": False,
                "model_execution": False,
            }
        ),
        registered_at=NOW,
    )


def fixture_definition(number: int, *, expected_score: int) -> FixtureDefinition:
    return FixtureDefinition(
        fixture_id=uid(number),
        fixture_version="1.0.0",
        evaluation_suite_id=SUITE_ID,
        evaluation_suite_version="1.0.0",
        fixture_set_id=FIXTURE_SET_ID,
        fixture_set_version="1.0.0",
        sensitivity="restricted_synthetic",
        provenance_json=canonical_json_text(
            {"classification": "synthetic", "source_record": f"fixture_{number}"}
        ),
        payload_json=canonical_json_text(
            {
                "expected_score": expected_score,
                "fixture_kind": "deterministic_mock",
                "synthetic_result_only": True,
            }
        ),
    )


def fixture_set() -> FixtureSet:
    definitions = (
        fixture_definition(8_000_101, expected_score=4),
        fixture_definition(8_000_102, expected_score=3),
    )
    entries = tuple(
        FixtureManifestEntry(
            fixture_id=definition.fixture_id,
            source_name=f"fixture_{index:02d}.json",
            ordinal=index,
            content_hash=sha256_bytes(definition.canonical_bytes),
        )
        for index, definition in enumerate(definitions)
    )
    manifest = FixtureSetManifest(
        fixture_set_id=FIXTURE_SET_ID,
        fixture_set_version="1.0.0",
        evaluation_suite_id=SUITE_ID,
        evaluation_suite_version="1.0.0",
        entries=entries,
        provenance_json=canonical_json_text(
            {"classification": "synthetic", "source_record": "pre_i5_manifest"}
        ),
        registered_at=NOW,
    )
    from batch87_apprentice.evaluation.contracts import DiscoveredFixture

    return FixtureSet(
        manifest=manifest,
        fixtures=tuple(
            DiscoveredFixture(
                definition=definition,
                entry=entry,
                exact_bytes=definition.canonical_bytes,
            )
            for definition, entry in zip(definitions, entries, strict=True)
        ),
    )


def write_fixture_set(root: Path, value: FixtureSet | None = None) -> FixtureSet:
    discovered = fixture_set() if value is None else value
    root.mkdir(parents=True, exist_ok=True)
    for fixture in discovered.fixtures:
        target = root / fixture.entry.source_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(fixture.exact_bytes)
    return discovered


def configuration(
    manifest: FixtureSetManifest,
    *,
    repetitions: int = 2,
) -> EvaluationConfiguration:
    return EvaluationConfiguration(
        configuration_id=CONFIGURATION_ID,
        configuration_version="1.0.0",
        evaluation_suite_id=manifest.evaluation_suite_id,
        evaluation_suite_version=manifest.evaluation_suite_version,
        fixture_set_id=manifest.fixture_set_id,
        fixture_set_version=manifest.fixture_set_version,
        fixture_set_hash=manifest.content_hash,
        timeout_ms=5_000,
        repetitions=repetitions,
        conditions=(
            EvaluationCondition(
                condition_id=uid(8_000_201),
                name="memory_enabled",
                label="enabled",
                ordinal=0,
                ablation_metadata_json=canonical_json_text(
                    {"memory_available": True}
                ),
            ),
            EvaluationCondition(
                condition_id=uid(8_000_202),
                name="memory_withheld",
                label="withheld",
                ordinal=1,
                ablation_metadata_json=canonical_json_text(
                    {"memory_available": False}
                ),
            ),
            EvaluationCondition(
                condition_id=uid(8_000_203),
                name="over_transfer_control",
                label="over_transfer",
                ordinal=2,
                ablation_metadata_json=canonical_json_text(
                    {"scope_relation": "unrelated"}
                ),
            ),
        ),
        resource_limits=ResourceLimits(
            cpu_threads=2,
            memory_limit_mb=512,
            accelerator_required=False,
        ),
        score_schema=ScoreSchema(
            schema_id="b87_core_scores",
            schema_version="1.0.0",
            dimensions=(
                ScoreDimension(
                    name="accuracy",
                    description="Agreement with recorded synthetic evidence.",
                ),
                ScoreDimension(
                    name="evidence_discipline",
                    description="Separation of evidence and inference.",
                ),
            ),
        ),
        critical_failure_schema=CriticalFailureSchema(
            schema_id="b87_critical_failures",
            schema_version="1.0.0",
            definitions=(
                CriticalFailureDefinition(
                    code="fabricated_authority",
                    description="The observed output fabricated authority.",
                ),
                CriticalFailureDefinition(
                    code="cross_project_contamination",
                    description="The observed output crossed project scope.",
                ),
            ),
        ),
        registered_at=NOW,
    )


def result_for_run(
    run,
    *,
    number: int,
    outcome: str | None = None,
    critical_code: str | None = None,
) -> EvaluationResult:
    selected_outcome = (
        "withheld" if run.condition_label == "withheld" else "completed"
    ) if outcome is None else outcome
    scores = ()
    if selected_outcome in {"completed", "incomplete", "interrupted"}:
        score = 3 if run.condition_label == "over_transfer" else 4
        scores = (
            ScoreObservation(
                dimension="accuracy",
                score=score,
                rationale="Deterministic synthetic observation.",
                evidence_refs=("synthetic_fixture",),
            ),
            ScoreObservation(
                dimension="evidence_discipline",
                score=score,
                rationale="Deterministic synthetic observation.",
                evidence_refs=("synthetic_fixture",),
            ),
        )
    critical = ()
    if selected_outcome == "critical_failure":
        critical = (
            CriticalFailureObservation(
                code=critical_code or "fabricated_authority",
                rationale="Synthetic negative-control evidence.",
                evidence_refs=("synthetic_negative_control",),
            ),
        )
    return EvaluationResult(
        result_id=uid(number),
        run_id=run.run_id,
        outcome=selected_outcome,
        evidence_origin="synthetic_mock",
        scores=scores,
        critical_failures=critical,
        runtime_observed=RuntimeObservation(
            latency_ms=None if selected_outcome == "withheld" else 10,
            hardware_metadata_json=canonical_json_text(
                {
                    "cpu_architecture": "synthetic",
                    "runtime_label": "deterministic_mock",
                }
            ),
        ),
        candidate_reported_metadata_json=canonical_json_text(
            {"classification": "candidate_reported", "synthetic": True}
        ),
        replay_metadata_json=canonical_json_text(
            {"replay_protocol": "pre_i5_mock_v1", "synthetic": True}
        ),
        observed_at=LATER,
    )


@dataclass(frozen=True, slots=True)
class PreI5Harness:
    config: DatabaseConfig
    service: DeterministicEvaluationService
    candidate: CandidateMetadata
    fixtures: FixtureSet
    configuration: EvaluationConfiguration
    plan: EvaluationPlan


def build_harness(tmp_path: Path, *, repetitions: int = 2) -> PreI5Harness:
    config = DatabaseConfig(tmp_path / "pre-i5.sqlite3")
    PersistenceService.initialize(config)
    sequence = IdentifierSequence(8_100_000)
    service = DeterministicEvaluationService(
        config,
        clock=lambda: NOW,
        identifier_factory=sequence,
    )
    candidate_value = candidate()
    fixtures_value = fixture_set()
    configuration_value = configuration(
        fixtures_value.manifest,
        repetitions=repetitions,
    )
    service.register_candidate(candidate_value)
    service.register_fixture_set(fixtures_value)
    service.register_configuration(configuration_value)
    plan = service.schedule(
        plan_id=PLAN_ID,
        plan_version="1.0.0",
        configuration=configuration_value,
        fixture_set=fixtures_value,
        candidates=(candidate_value,),
    )
    return PreI5Harness(
        config=config,
        service=service,
        candidate=candidate_value,
        fixtures=fixtures_value,
        configuration=configuration_value,
        plan=plan,
    )


def complete_mock_campaign(harness: PreI5Harness, *, base: int = 8_200_000):
    results = tuple(
        result_for_run(run, number=base + index)
        for index, run in enumerate(harness.plan.runs)
    )
    report = harness.service.record_mock_campaign(harness.plan, results)
    return results, report
