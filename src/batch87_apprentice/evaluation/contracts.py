"""Immutable canonical contracts for B87-PRE-I5 deterministic evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from pathlib import PurePosixPath
import re
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_bytes,
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_bytes, sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc

EVALUATION_CONTRACT_VERSION = "1.0.0"
REPORT_PROTOCOL = "batch87.deterministic-evaluation-report"
REPORT_PROTOCOL_VERSION = "1.0.0"

CANDIDATE_ORIGINS = frozenset(
    {"operator_supplied", "public_metadata", "synthetic_mock"}
)
CANDIDATE_LIFECYCLE_STATES = frozenset(
    {"registered", "withheld", "ineligible", "retired"}
)
ADMISSION_STATES = frozenset(
    {"not_assessed", "evaluation_pending", "not_admitted", "ineligible"}
)
SENSITIVITY_CLASSES = frozenset(
    {"public", "internal", "restricted_synthetic"}
)
CONDITION_LABELS = frozenset({"enabled", "withheld", "over_transfer"})
RESULT_OUTCOMES = frozenset(
    {
        "completed",
        "critical_failure",
        "incomplete",
        "invalid",
        "interrupted",
    }
)
RUN_STATES = RESULT_OUTCOMES | {"planned"}

_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_BLIND_ID = re.compile(r"^blind_[0-9a-f]{24}$")
_FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "bearer_token",
        "callback",
        "command",
        "credential",
        "credentials",
        "endpoint",
        "environment_variable",
        "executable",
        "executable_path",
        "function",
        "host",
        "model_path",
        "password",
        "port",
        "provider_configuration",
        "secret",
        "socket",
        "token",
        "tool",
        "tools",
        "url",
    }
)
_FORBIDDEN_SCORE_FRAGMENTS = (
    "anthropomorphic",
    "chain_of_thought",
    "consciousness",
    "hidden_reasoning",
    "hidden_thought",
    "loyalty",
    "self_preservation",
    "sentience",
)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be non-empty text")
    return value


def _token(value: object, field: str) -> str:
    text = _text(value, field)
    if _TOKEN.fullmatch(text) is None:
        raise ValidationError(f"{field} must be a lowercase token")
    return text


def _version(value: object, field: str) -> str:
    text = _text(value, field)
    if _VERSION.fullmatch(text) is None:
        raise ValidationError(f"{field} must be a numeric semantic version")
    return text


def _sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValidationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
    ):
        raise ValidationError(f"{field} must be an integer >= {minimum}")
    return value


def _canonical_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be canonical JSON text")
    parsed = parse_json(value)
    if not isinstance(parsed, dict) or canonical_json_text(parsed) != value:
        raise ValidationError(f"{field} must be a canonical JSON object")
    return parsed


def _safe_metadata_value(value: object, path: str) -> None:
    if callable(value):
        raise ValidationError(f"{path} contains an executable capability")
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValidationError(f"{path} contains a non-text field")
            child = f"{path}.{key}"
            if key.lower() in _FORBIDDEN_METADATA_KEYS:
                raise ValidationError(f"{child} is a prohibited capability field")
            _safe_metadata_value(nested, child)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _safe_metadata_value(nested, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        if (
            "://" in value
            or lowered.startswith(("sk-", "bearer ", "api_key="))
            or value.startswith(("/", "\\"))
            or re.match(r"^[a-zA-Z]:[\\/]", value)
        ):
            raise ValidationError(
                f"{path} contains a prohibited endpoint, path, or secret"
            )


def _safe_canonical_object(value: object, field: str) -> dict[str, Any]:
    parsed = _canonical_object(value, field)
    _safe_metadata_value(parsed, field)
    return parsed


def _unique(values: tuple[str, ...], field: str) -> None:
    if len(values) != len(set(values)):
        raise ValidationError(f"{field} must not contain duplicates")


def _reject_forbidden_evaluation_text(value: str) -> None:
    normalized = value.lower().replace("-", " ").replace("_", " ")
    fragments = tuple(
        fragment.replace("_", " ") for fragment in _FORBIDDEN_SCORE_FRAGMENTS
    )
    if any(fragment in normalized for fragment in fragments):
        raise ValidationError(
            "anthropomorphic or hidden-state evaluation is forbidden"
        )


@dataclass(frozen=True, slots=True)
class CandidateMetadata:
    """Write-once candidate facts; registration never means admission."""

    candidate_id: str
    candidate_origin: str
    lifecycle_state: str
    admission_state: str
    model_family: str
    model_revision: str
    quantization: str | None
    artifact_format: str
    licence_identifier: str
    provenance_json: str
    compatibility_json: str
    registered_at: str
    contract_version: str = EVALUATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != EVALUATION_CONTRACT_VERSION:
            raise ValidationError("candidate contract version is invalid")
        validate_identifier(self.candidate_id, field="candidate_id")
        if self.candidate_origin not in CANDIDATE_ORIGINS:
            raise ValidationError("candidate_origin is invalid")
        if self.lifecycle_state not in CANDIDATE_LIFECYCLE_STATES:
            raise ValidationError("candidate lifecycle state is invalid")
        if self.admission_state not in ADMISSION_STATES:
            raise ValidationError("candidate admission state is invalid")
        _safe_metadata_value(
            _text(self.model_family, "model_family"), "model_family"
        )
        _safe_metadata_value(
            _text(self.model_revision, "model_revision"), "model_revision"
        )
        if self.quantization is not None:
            _safe_metadata_value(
                _text(self.quantization, "quantization"), "quantization"
            )
        _token(self.artifact_format, "artifact_format")
        _safe_metadata_value(
            _text(self.licence_identifier, "licence_identifier"),
            "licence_identifier",
        )
        _safe_canonical_object(self.provenance_json, "provenance_json")
        _safe_canonical_object(self.compatibility_json, "compatibility_json")
        parse_canonical_utc(self.registered_at, field="registered_at")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "admission_state": self.admission_state,
            "artifact_format": self.artifact_format,
            "candidate_id": self.candidate_id,
            "candidate_origin": self.candidate_origin,
            "compatibility": _canonical_object(
                self.compatibility_json, "compatibility_json"
            ),
            "contract_version": self.contract_version,
            "licence_identifier": self.licence_identifier,
            "lifecycle_state": self.lifecycle_state,
            "model_family": self.model_family,
            "model_revision": self.model_revision,
            "provenance": _canonical_object(self.provenance_json, "provenance_json"),
            "quantization": self.quantization,
            "registered_at": self.registered_at,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class ScoreDimension:
    name: str
    description: str
    minimum: int = 0
    maximum: int = 4

    def __post_init__(self) -> None:
        _token(self.name, "score dimension name")
        _text(self.description, "score dimension description")
        _reject_forbidden_evaluation_text(self.name)
        _reject_forbidden_evaluation_text(self.description)
        _integer(self.minimum, "score minimum")
        _integer(self.maximum, "score maximum")
        if self.minimum != 0 or self.maximum != 4:
            raise ValidationError("B87-S1 score dimensions must use the 0..4 scale")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "maximum": self.maximum,
            "minimum": self.minimum,
            "name": self.name,
        }


@dataclass(frozen=True, slots=True)
class ScoreSchema:
    schema_id: str
    schema_version: str
    dimensions: tuple[ScoreDimension, ...]

    def __post_init__(self) -> None:
        _token(self.schema_id, "score_schema_id")
        _version(self.schema_version, "score_schema_version")
        if not self.dimensions:
            raise ValidationError("score schema requires at least one dimension")
        if not all(isinstance(item, ScoreDimension) for item in self.dimensions):
            raise ValidationError("score schema dimensions are invalid")
        _unique(tuple(item.name for item in self.dimensions), "score dimensions")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "dimensions": [item.canonical_value() for item in self.dimensions],
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class CriticalFailureDefinition:
    code: str
    description: str

    def __post_init__(self) -> None:
        _token(self.code, "critical failure code")
        _text(self.description, "critical failure description")
        _reject_forbidden_evaluation_text(self.code)
        _reject_forbidden_evaluation_text(self.description)

    def canonical_value(self) -> dict[str, str]:
        return {"code": self.code, "description": self.description}


@dataclass(frozen=True, slots=True)
class CriticalFailureSchema:
    schema_id: str
    schema_version: str
    definitions: tuple[CriticalFailureDefinition, ...]

    def __post_init__(self) -> None:
        _token(self.schema_id, "critical_failure_schema_id")
        _version(self.schema_version, "critical_failure_schema_version")
        if not self.definitions:
            raise ValidationError("critical failure schema requires definitions")
        if not all(
            isinstance(item, CriticalFailureDefinition) for item in self.definitions
        ):
            raise ValidationError("critical failure definitions are invalid")
        _unique(
            tuple(item.code for item in self.definitions),
            "critical failure definitions",
        )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "definitions": [item.canonical_value() for item in self.definitions],
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    cpu_threads: int
    memory_limit_mb: int
    accelerator_required: bool = False

    def __post_init__(self) -> None:
        _integer(self.cpu_threads, "cpu_threads", minimum=1)
        _integer(self.memory_limit_mb, "memory_limit_mb", minimum=1)
        if not isinstance(self.accelerator_required, bool):
            raise ValidationError("accelerator_required must be boolean")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "accelerator_required": self.accelerator_required,
            "cpu_threads": self.cpu_threads,
            "memory_limit_mb": self.memory_limit_mb,
        }


@dataclass(frozen=True, slots=True)
class EvaluationCondition:
    condition_id: str
    name: str
    label: str
    ordinal: int
    ablation_metadata_json: str

    def __post_init__(self) -> None:
        validate_identifier(self.condition_id, field="condition_id")
        _token(self.name, "condition name")
        if self.label not in CONDITION_LABELS:
            raise ValidationError("condition label is invalid")
        _integer(self.ordinal, "condition ordinal")
        _safe_canonical_object(
            self.ablation_metadata_json, "ablation_metadata_json"
        )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "ablation_metadata": _canonical_object(
                self.ablation_metadata_json, "ablation_metadata_json"
            ),
            "condition_id": self.condition_id,
            "label": self.label,
            "name": self.name,
            "ordinal": self.ordinal,
        }


@dataclass(frozen=True, slots=True)
class EvaluationConfiguration:
    configuration_id: str
    configuration_family_id: str
    configuration_version: str
    evaluation_suite_id: str
    evaluation_suite_version: str
    fixture_set_id: str
    fixture_set_version: str
    fixture_set_hash: str
    timeout_ms: int
    repetitions: int
    conditions: tuple[EvaluationCondition, ...]
    resource_limits: ResourceLimits
    score_schema: ScoreSchema
    critical_failure_schema: CriticalFailureSchema
    registered_at: str
    contract_version: str = EVALUATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != EVALUATION_CONTRACT_VERSION:
            raise ValidationError("evaluation configuration version is invalid")
        for field in (
            "configuration_id",
            "configuration_family_id",
            "evaluation_suite_id",
            "fixture_set_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        _version(self.configuration_version, "configuration_version")
        _version(self.evaluation_suite_version, "evaluation_suite_version")
        _version(self.fixture_set_version, "fixture_set_version")
        _sha256(self.fixture_set_hash, "fixture_set_hash")
        _integer(self.timeout_ms, "timeout_ms", minimum=1)
        _integer(self.repetitions, "repetitions", minimum=1)
        if not self.conditions:
            raise ValidationError("evaluation configuration requires conditions")
        if not all(isinstance(item, EvaluationCondition) for item in self.conditions):
            raise ValidationError("evaluation conditions are invalid")
        condition_ids = tuple(item.condition_id for item in self.conditions)
        condition_names = tuple(item.name for item in self.conditions)
        _unique(condition_ids, "condition identifiers")
        _unique(condition_names, "condition names")
        if tuple(item.ordinal for item in self.conditions) != tuple(
            range(len(self.conditions))
        ):
            raise ValidationError("condition ordinals must be contiguous from zero")
        if not isinstance(self.resource_limits, ResourceLimits):
            raise ValidationError("resource_limits are invalid")
        if not isinstance(self.score_schema, ScoreSchema):
            raise ValidationError("score_schema is invalid")
        if not isinstance(self.critical_failure_schema, CriticalFailureSchema):
            raise ValidationError("critical_failure_schema is invalid")
        parse_canonical_utc(self.registered_at, field="registered_at")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "conditions": [item.canonical_value() for item in self.conditions],
            "configuration_family_id": self.configuration_family_id,
            "configuration_id": self.configuration_id,
            "configuration_version": self.configuration_version,
            "contract_version": self.contract_version,
            "critical_failure_schema": self.critical_failure_schema.canonical_value(),
            "evaluation_suite_id": self.evaluation_suite_id,
            "evaluation_suite_version": self.evaluation_suite_version,
            "fixture_set_hash": self.fixture_set_hash,
            "fixture_set_id": self.fixture_set_id,
            "fixture_set_version": self.fixture_set_version,
            "registered_at": self.registered_at,
            "repetitions": self.repetitions,
            "resource_limits": self.resource_limits.canonical_value(),
            "score_schema": self.score_schema.canonical_value(),
            "timeout_ms": self.timeout_ms,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class FixtureDefinition:
    fixture_id: str
    fixture_family_id: str
    fixture_version: str
    evaluation_suite_id: str
    evaluation_suite_version: str
    fixture_set_id: str
    fixture_set_version: str
    sensitivity: str
    provenance_json: str
    payload_json: str
    contract_version: str = EVALUATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != EVALUATION_CONTRACT_VERSION:
            raise ValidationError("fixture contract version is invalid")
        for field in (
            "fixture_id",
            "fixture_family_id",
            "evaluation_suite_id",
            "fixture_set_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        _version(self.fixture_version, "fixture_version")
        _version(self.evaluation_suite_version, "evaluation_suite_version")
        _version(self.fixture_set_version, "fixture_set_version")
        if self.sensitivity not in SENSITIVITY_CLASSES:
            raise ValidationError("fixture sensitivity is invalid")
        _safe_canonical_object(self.provenance_json, "fixture provenance")
        _canonical_object(self.payload_json, "fixture payload")

    @classmethod
    def from_mapping(cls, value: object) -> FixtureDefinition:
        if not isinstance(value, Mapping):
            raise ValidationError("fixture document must be an object")
        expected = {
            "contract_version",
            "evaluation_suite_id",
            "evaluation_suite_version",
            "fixture_family_id",
            "fixture_id",
            "fixture_set_id",
            "fixture_set_version",
            "fixture_version",
            "payload",
            "provenance",
            "sensitivity",
        }
        if set(value) != expected:
            raise ValidationError("fixture document fields are invalid")
        return cls(
            fixture_id=value["fixture_id"],
            fixture_family_id=value["fixture_family_id"],
            fixture_version=value["fixture_version"],
            evaluation_suite_id=value["evaluation_suite_id"],
            evaluation_suite_version=value["evaluation_suite_version"],
            fixture_set_id=value["fixture_set_id"],
            fixture_set_version=value["fixture_set_version"],
            sensitivity=value["sensitivity"],
            provenance_json=canonical_json_text(value["provenance"]),
            payload_json=canonical_json_text(value["payload"]),
            contract_version=value["contract_version"],
        )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "evaluation_suite_id": self.evaluation_suite_id,
            "evaluation_suite_version": self.evaluation_suite_version,
            "fixture_family_id": self.fixture_family_id,
            "fixture_id": self.fixture_id,
            "fixture_set_id": self.fixture_set_id,
            "fixture_set_version": self.fixture_set_version,
            "fixture_version": self.fixture_version,
            "payload": _canonical_object(self.payload_json, "fixture payload"),
            "provenance": _canonical_object(
                self.provenance_json, "fixture provenance"
            ),
            "sensitivity": self.sensitivity,
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_value())


@dataclass(frozen=True, slots=True)
class FixtureManifestEntry:
    fixture_id: str
    source_name: str
    ordinal: int
    content_hash: str

    def __post_init__(self) -> None:
        validate_identifier(self.fixture_id, field="fixture_id")
        source = _text(self.source_name, "fixture source_name")
        path = PurePosixPath(source)
        if (
            path.is_absolute()
            or "\\" in source
            or ".." in path.parts
            or path.suffix != ".json"
            or str(path) != source
        ):
            raise ValidationError("fixture source_name must be a safe relative JSON path")
        _integer(self.ordinal, "fixture ordinal")
        _sha256(self.content_hash, "fixture content_hash")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "content_hash": self.content_hash,
            "fixture_id": self.fixture_id,
            "ordinal": self.ordinal,
            "source_name": self.source_name,
        }


@dataclass(frozen=True, slots=True)
class FixtureSetManifest:
    fixture_set_id: str
    fixture_set_version: str
    evaluation_suite_id: str
    evaluation_suite_version: str
    entries: tuple[FixtureManifestEntry, ...]
    provenance_json: str
    registered_at: str
    contract_version: str = EVALUATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != EVALUATION_CONTRACT_VERSION:
            raise ValidationError("fixture-set contract version is invalid")
        for field in ("fixture_set_id", "evaluation_suite_id"):
            validate_identifier(getattr(self, field), field=field)
        _version(self.fixture_set_version, "fixture_set_version")
        _version(self.evaluation_suite_version, "evaluation_suite_version")
        if not self.entries:
            raise ValidationError("fixture set must contain at least one fixture")
        if not all(isinstance(item, FixtureManifestEntry) for item in self.entries):
            raise ValidationError("fixture manifest entries are invalid")
        _unique(tuple(item.fixture_id for item in self.entries), "fixture identifiers")
        _unique(tuple(item.source_name for item in self.entries), "fixture sources")
        _unique(tuple(item.content_hash for item in self.entries), "fixture hashes")
        if tuple(item.ordinal for item in self.entries) != tuple(range(len(self.entries))):
            raise ValidationError("fixture ordinals must be contiguous from zero")
        _safe_canonical_object(self.provenance_json, "fixture-set provenance")
        parse_canonical_utc(self.registered_at, field="registered_at")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "entries": [item.canonical_value() for item in self.entries],
            "evaluation_suite_id": self.evaluation_suite_id,
            "evaluation_suite_version": self.evaluation_suite_version,
            "fixture_set_id": self.fixture_set_id,
            "fixture_set_version": self.fixture_set_version,
            "provenance": _canonical_object(
                self.provenance_json, "fixture-set provenance"
            ),
            "registered_at": self.registered_at,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class DiscoveredFixture:
    definition: FixtureDefinition
    entry: FixtureManifestEntry
    exact_bytes: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.definition, FixtureDefinition):
            raise ValidationError("discovered fixture definition is invalid")
        if not isinstance(self.entry, FixtureManifestEntry):
            raise ValidationError("discovered fixture manifest entry is invalid")
        if not isinstance(self.exact_bytes, bytes):
            raise ValidationError("fixture exact bytes are invalid")
        if self.definition.fixture_id != self.entry.fixture_id:
            raise ValidationError("fixture identity conflicts with manifest")
        if self.exact_bytes != self.definition.canonical_bytes:
            raise ValidationError("fixture bytes must be exact canonical UTF-8 JSON")
        if sha256_bytes(self.exact_bytes) != self.entry.content_hash:
            raise ValidationError("fixture content differs from manifest")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "content_hash": self.entry.content_hash,
            "definition": self.definition.canonical_value(),
            "ordinal": self.entry.ordinal,
            "source_name": self.entry.source_name,
        }


@dataclass(frozen=True, slots=True)
class FixtureSet:
    manifest: FixtureSetManifest
    fixtures: tuple[DiscoveredFixture, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, FixtureSetManifest):
            raise ValidationError("fixture-set manifest is invalid")
        if not all(isinstance(item, DiscoveredFixture) for item in self.fixtures):
            raise ValidationError("fixture-set entries are invalid")
        if tuple(item.entry for item in self.fixtures) != self.manifest.entries:
            raise ValidationError("discovered fixtures do not exactly match manifest")
        for fixture in self.fixtures:
            definition = fixture.definition
            if (
                definition.fixture_set_id != self.manifest.fixture_set_id
                or definition.fixture_set_version != self.manifest.fixture_set_version
                or definition.evaluation_suite_id
                != self.manifest.evaluation_suite_id
                or definition.evaluation_suite_version
                != self.manifest.evaluation_suite_version
            ):
                raise ValidationError("fixture suite or set membership conflicts")


@dataclass(frozen=True, slots=True)
class CandidateBlindBinding:
    candidate_id: str
    candidate_hash: str
    blind_candidate_id: str

    def __post_init__(self) -> None:
        validate_identifier(self.candidate_id, field="candidate_id")
        _sha256(self.candidate_hash, "candidate_hash")
        if _BLIND_ID.fullmatch(self.blind_candidate_id) is None:
            raise ValidationError("blind_candidate_id is invalid")

    def canonical_value(self) -> dict[str, str]:
        return {
            "blind_candidate_id": self.blind_candidate_id,
            "candidate_hash": self.candidate_hash,
            "candidate_id": self.candidate_id,
        }


@dataclass(frozen=True, slots=True)
class PlannedRun:
    run_id: str
    plan_id: str
    condition_id: str
    condition_label: str
    blind_candidate_id: str
    fixture_id: str
    repetition_index: int
    run_ordinal: int
    ablation_metadata_json: str
    planned_at: str

    def __post_init__(self) -> None:
        for field in ("run_id", "plan_id", "condition_id", "fixture_id"):
            validate_identifier(getattr(self, field), field=field)
        if _BLIND_ID.fullmatch(self.blind_candidate_id) is None:
            raise ValidationError("blind_candidate_id is invalid")
        if self.condition_label not in CONDITION_LABELS:
            raise ValidationError("condition_label is invalid")
        _integer(self.repetition_index, "repetition_index")
        _integer(self.run_ordinal, "run_ordinal")
        _safe_canonical_object(
            self.ablation_metadata_json, "run ablation metadata"
        )
        parse_canonical_utc(self.planned_at, field="planned_at")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "ablation_metadata": _canonical_object(
                self.ablation_metadata_json, "run ablation metadata"
            ),
            "blind_candidate_id": self.blind_candidate_id,
            "condition_id": self.condition_id,
            "condition_label": self.condition_label,
            "fixture_id": self.fixture_id,
            "plan_id": self.plan_id,
            "planned_at": self.planned_at,
            "repetition_index": self.repetition_index,
            "run_id": self.run_id,
            "run_ordinal": self.run_ordinal,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class EvaluationPlan:
    plan_id: str
    plan_family_id: str
    plan_version: str
    configuration_id: str
    configuration_hash: str
    fixture_set_id: str
    fixture_set_version: str
    fixture_set_hash: str
    candidate_bindings: tuple[CandidateBlindBinding, ...]
    runs: tuple[PlannedRun, ...]
    created_at: str
    contract_version: str = EVALUATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != EVALUATION_CONTRACT_VERSION:
            raise ValidationError("evaluation plan contract version is invalid")
        for field in (
            "plan_id",
            "plan_family_id",
            "configuration_id",
            "fixture_set_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        _version(self.plan_version, "plan_version")
        _version(self.fixture_set_version, "fixture_set_version")
        _sha256(self.configuration_hash, "configuration_hash")
        _sha256(self.fixture_set_hash, "fixture_set_hash")
        if not self.candidate_bindings:
            raise ValidationError("evaluation plan requires candidate bindings")
        if not all(
            isinstance(item, CandidateBlindBinding)
            for item in self.candidate_bindings
        ):
            raise ValidationError("candidate bindings are invalid")
        _unique(
            tuple(item.candidate_id for item in self.candidate_bindings),
            "candidate bindings",
        )
        _unique(
            tuple(item.blind_candidate_id for item in self.candidate_bindings),
            "blind candidate bindings",
        )
        if not self.runs or not all(isinstance(item, PlannedRun) for item in self.runs):
            raise ValidationError("evaluation plan requires planned runs")
        _unique(tuple(item.run_id for item in self.runs), "run identifiers")
        if tuple(item.run_ordinal for item in self.runs) != tuple(range(len(self.runs))):
            raise ValidationError("run ordinals must be contiguous from zero")
        blind_ids = {item.blind_candidate_id for item in self.candidate_bindings}
        if any(
            item.plan_id != self.plan_id
            or item.blind_candidate_id not in blind_ids
            for item in self.runs
        ):
            raise ValidationError("planned run binding is invalid")
        parse_canonical_utc(self.created_at, field="created_at")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "candidate_bindings": [
                item.canonical_value() for item in self.candidate_bindings
            ],
            "configuration_hash": self.configuration_hash,
            "configuration_id": self.configuration_id,
            "contract_version": self.contract_version,
            "created_at": self.created_at,
            "fixture_set_hash": self.fixture_set_hash,
            "fixture_set_id": self.fixture_set_id,
            "fixture_set_version": self.fixture_set_version,
            "plan_family_id": self.plan_family_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "runs": [item.canonical_value() for item in self.runs],
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class ScoreObservation:
    dimension: str
    score: float
    rationale: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _token(self.dimension, "score dimension")
        _reject_forbidden_evaluation_text(self.dimension)
        if (
            not isinstance(self.score, (int, float))
            or isinstance(self.score, bool)
            or not math.isfinite(float(self.score))
            or not 0 <= float(self.score) <= 4
        ):
            raise ValidationError("score must be finite and within 0..4")
        _text(self.rationale, "score rationale")
        _reject_forbidden_evaluation_text(self.rationale)
        if not self.evidence_refs:
            raise ValidationError("score requires evidence references")
        for reference in self.evidence_refs:
            _text(reference, "score evidence reference")
        _unique(self.evidence_refs, "score evidence references")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "evidence_refs": list(self.evidence_refs),
            "rationale": self.rationale,
            "score": float(self.score),
        }


@dataclass(frozen=True, slots=True)
class CriticalFailureObservation:
    code: str
    rationale: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _token(self.code, "critical failure code")
        _text(self.rationale, "critical failure rationale")
        _reject_forbidden_evaluation_text(self.code)
        _reject_forbidden_evaluation_text(self.rationale)
        if not self.evidence_refs:
            raise ValidationError("critical failure requires evidence references")
        for reference in self.evidence_refs:
            _text(reference, "critical failure evidence reference")
        _unique(self.evidence_refs, "critical failure evidence references")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "evidence_refs": list(self.evidence_refs),
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class RuntimeObservation:
    latency_ms: int | None
    hardware_metadata_json: str

    def __post_init__(self) -> None:
        if self.latency_ms is not None:
            _integer(self.latency_ms, "latency_ms")
        _safe_canonical_object(
            self.hardware_metadata_json, "runtime hardware metadata"
        )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "hardware_metadata": _canonical_object(
                self.hardware_metadata_json, "runtime hardware metadata"
            ),
            "latency_ms": self.latency_ms,
        }


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    result_id: str
    run_id: str
    outcome: str
    evidence_origin: str
    scores: tuple[ScoreObservation, ...]
    critical_failures: tuple[CriticalFailureObservation, ...]
    runtime_observed: RuntimeObservation
    candidate_reported_metadata_json: str
    replay_metadata_json: str
    observed_at: str
    contract_version: str = EVALUATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != EVALUATION_CONTRACT_VERSION:
            raise ValidationError("evaluation result contract version is invalid")
        validate_identifier(self.result_id, field="result_id")
        validate_identifier(self.run_id, field="run_id")
        if self.outcome not in RESULT_OUTCOMES:
            raise ValidationError("evaluation outcome is invalid")
        if self.evidence_origin not in {"synthetic_mock", "recorded_observation"}:
            raise ValidationError("evaluation evidence origin is invalid")
        if not all(isinstance(item, ScoreObservation) for item in self.scores):
            raise ValidationError("score observations are invalid")
        if not all(
            isinstance(item, CriticalFailureObservation)
            for item in self.critical_failures
        ):
            raise ValidationError("critical failure observations are invalid")
        _unique(tuple(item.dimension for item in self.scores), "result scores")
        _unique(
            tuple(item.code for item in self.critical_failures),
            "result critical failures",
        )
        if self.outcome == "completed" and self.critical_failures:
            raise ValidationError("completed result cannot contain critical failures")
        if self.outcome == "critical_failure" and not self.critical_failures:
            raise ValidationError("critical-failure result requires failure evidence")
        if not isinstance(self.runtime_observed, RuntimeObservation):
            raise ValidationError("runtime observation is invalid")
        _safe_canonical_object(
            self.candidate_reported_metadata_json,
            "candidate-reported metadata",
        )
        _safe_canonical_object(self.replay_metadata_json, "replay metadata")
        parse_canonical_utc(self.observed_at, field="observed_at")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "candidate_reported_metadata": _canonical_object(
                self.candidate_reported_metadata_json,
                "candidate-reported metadata",
            ),
            "contract_version": self.contract_version,
            "critical_failures": [
                item.canonical_value() for item in self.critical_failures
            ],
            "evidence_origin": self.evidence_origin,
            "observed_at": self.observed_at,
            "outcome": self.outcome,
            "replay_metadata": _canonical_object(
                self.replay_metadata_json, "replay metadata"
            ),
            "result_id": self.result_id,
            "run_id": self.run_id,
            "runtime_observed": self.runtime_observed.canonical_value(),
            "scores": [item.canonical_value() for item in self.scores],
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class EvaluationRunStateTransition:
    transition_id: str
    run_id: str
    sequence: int
    from_state: str | None
    to_state: str
    occurred_at: str

    def __post_init__(self) -> None:
        validate_identifier(self.transition_id, field="transition_id")
        validate_identifier(self.run_id, field="run_id")
        _integer(self.sequence, "transition sequence")
        if self.from_state is not None and self.from_state not in RUN_STATES:
            raise ValidationError("transition from_state is invalid")
        if self.to_state not in RUN_STATES:
            raise ValidationError("transition to_state is invalid")
        if self.sequence == 0:
            if self.from_state is not None or self.to_state != "planned":
                raise ValidationError("initial run transition must enter planned")
        elif (
            self.sequence != 1
            or self.from_state != "planned"
            or self.to_state not in RESULT_OUTCOMES
        ):
            raise ValidationError("run terminal transition is invalid")
        parse_canonical_utc(self.occurred_at, field="occurred_at")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "from_state": self.from_state,
            "occurred_at": self.occurred_at,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "to_state": self.to_state,
            "transition_id": self.transition_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class EvaluationReconstruction:
    canonical_json: str
    content_hash: str

    def __post_init__(self) -> None:
        value = _canonical_object(self.canonical_json, "reconstruction")
        _sha256(self.content_hash, "reconstruction content_hash")
        if sha256_canonical_json(value) != self.content_hash:
            raise ValidationError("reconstruction hash does not match content")

    @property
    def value(self) -> dict[str, Any]:
        return _canonical_object(self.canonical_json, "reconstruction")


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    canonical_json: str
    content_hash: str

    def __post_init__(self) -> None:
        value = _canonical_object(self.canonical_json, "evaluation report")
        _sha256(self.content_hash, "evaluation report content_hash")
        if value.get("protocol") != REPORT_PROTOCOL:
            raise ValidationError("evaluation report protocol is invalid")
        if value.get("protocol_version") != REPORT_PROTOCOL_VERSION:
            raise ValidationError("evaluation report protocol version is invalid")
        if sha256_canonical_json(value) != self.content_hash:
            raise ValidationError("evaluation report hash does not match content")

    @property
    def value(self) -> dict[str, Any]:
        return _canonical_object(self.canonical_json, "evaluation report")
