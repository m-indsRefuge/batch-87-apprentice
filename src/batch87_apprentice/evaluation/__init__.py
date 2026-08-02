"""B87-PRE-I5 deterministic non-model evaluation infrastructure."""

from .campaign import DeterministicEvaluationService
from .contracts import (
    CandidateMetadata,
    CriticalFailureDefinition,
    CriticalFailureObservation,
    CriticalFailureSchema,
    DiscoveredFixture,
    EvaluationCondition,
    EvaluationConfiguration,
    EvaluationPlan,
    EvaluationReconstruction,
    EvaluationReport,
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
from .fixtures import discover_fixture_set
from .integrity import EvaluationIntegrityInspector, EvaluationIntegrityReport
from .planning import build_evaluation_plan

__all__ = [
    "CandidateMetadata",
    "CriticalFailureDefinition",
    "CriticalFailureObservation",
    "CriticalFailureSchema",
    "DeterministicEvaluationService",
    "DiscoveredFixture",
    "EvaluationCondition",
    "EvaluationConfiguration",
    "EvaluationIntegrityInspector",
    "EvaluationIntegrityReport",
    "EvaluationPlan",
    "EvaluationReconstruction",
    "EvaluationReport",
    "EvaluationResult",
    "FixtureDefinition",
    "FixtureManifestEntry",
    "FixtureSet",
    "FixtureSetManifest",
    "ResourceLimits",
    "RuntimeObservation",
    "ScoreDimension",
    "ScoreObservation",
    "ScoreSchema",
    "build_evaluation_plan",
    "discover_fixture_set",
]
