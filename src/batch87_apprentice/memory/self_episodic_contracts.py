"""Immutable factual self-model contracts for B87-I3-C1."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, TypeAlias

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc
from batch87_apprentice.persistence.contracts import RecordEnvelope

from .contracts import MEMORY_RECORD_POLICIES

SELF_MODEL_RECORD_FAMILY = "self_model"
SELF_EPISODIC_MEMORY_DOMAIN = "self_episodic"

EVALUATION_KINDS = frozenset(
    {"capability_evaluation", "maturity_evaluation"}
)
EVALUATION_ANCHOR_STATES = frozenset(
    {"registered", "claimed", "invalid", "retired"}
)
EVALUATION_ANCHOR_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "registered": frozenset({"claimed", "invalid", "retired"}),
    "claimed": frozenset({"invalid", "retired"}),
    "invalid": frozenset({"retired"}),
    "retired": frozenset(),
}
DEVELOPMENTAL_POLICY_KINDS = frozenset(
    {"capability_stability", "maturity_progression"}
)
DEVELOPMENTAL_POLICY_STATUSES = frozenset(
    {"approved", "revoked", "retired"}
)
RUNTIME_ATTESTATION_ENVIRONMENTS = frozenset(
    {"production", "synthetic_validation"}
)
TRUSTED_RUNTIME_ATTESTOR_STATUSES = frozenset(
    {"active", "revoked", "retired"}
)
CAPABILITY_OBSERVATION_TYPES = frozenset({"strength", "weakness", "unknown"})
CAPABILITY_STABILITIES = (
    "unconfirmed",
    "emerging",
    "repeated",
    "stable",
)
MATURITY_STAGES = (
    "uninitialised",
    "oriented",
    "apprentice-observer",
    "apprentice-analyst",
    "apprentice-proposer",
    "supervised-specialist",
    "maturity-review-eligible",
)
B87_S1_ACTIVE_MATURITY_STAGES = frozenset(MATURITY_STAGES[:4])
FACTUAL_SELF_PAYLOAD_TABLES: Mapping[str, str] = {
    "runtime_identity": "runtime_identities",
    "capability_observation": "capability_observations",
    "maturity_state": "maturity_states",
}

_REQUIRED_CAPABILITY_STABILITY_RULES = frozenset(
    {"emerging", "repeated", "stable"}
)
_PLACEHOLDER_SUBSTRATE_VALUES = frozenset(
    {
        "unknown",
        "none",
        "null",
        "n/a",
        "na",
        "placeholder",
        "planned",
        "future",
        "previous",
        "tbd",
        "unset",
        "not_applicable",
        "not-applicable",
    }
)


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be non-empty text")
    return value


def _identifier(value: str, field: str) -> str:
    return validate_identifier(value, field=field)


def _optional_identifier(value: str | None, field: str) -> str | None:
    if value is not None:
        _identifier(value, field)
    return value


def _enum(value: str, accepted: frozenset[str], field: str) -> str:
    if value not in accepted:
        raise ValidationError(f"{field} has an unsupported value: {value!r}")
    return value


def _identifiers(values: Sequence[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(
        values, Sequence
    ):
        raise ValidationError(f"{field} must be an ordered sequence")
    result = tuple(values)
    if not result:
        raise ValidationError(f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise ValidationError(f"{field} must not contain duplicates")
    for index, value in enumerate(result):
        _identifier(value, f"{field}[{index}]")
    return result


def _strings(
    values: Sequence[str],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(
        values, Sequence
    ):
        raise ValidationError(f"{field} must be an ordered sequence")
    result = tuple(values)
    if not allow_empty and not result:
        raise ValidationError(f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise ValidationError(f"{field} must not contain duplicates")
    for index, value in enumerate(result):
        _text(value, f"{field}[{index}]")
    return result


def _canonical_object(value: Mapping[str, Any], field: str) -> str:
    if not isinstance(value, Mapping) or not value:
        raise ValidationError(f"{field} must be a non-empty JSON object")
    canonical = canonical_json_text(dict(value))
    parsed = parse_json(canonical)
    if not isinstance(parsed, dict) or not parsed:
        raise ValidationError(f"{field} must be a non-empty JSON object")
    return canonical


def _positive_integer(value: Any, field: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError(f"{field} must be an integer >= {minimum}")
    return value


def _substrate_text(value: str, field: str) -> str:
    _text(value, field)
    if value.strip().casefold() in _PLACEHOLDER_SUBSTRATE_VALUES:
        raise ValidationError(f"{field} cannot be a placeholder value")
    return value


def capability_policy_configuration(
    configuration: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the exact configurable C1 capability-policy shape."""

    if set(configuration) != {
        "allow_registered_for_unconfirmed",
        "stability_requirements",
    }:
        raise ValidationError(
            "capability policy configuration has unsupported or missing fields"
        )
    allow_registered = configuration["allow_registered_for_unconfirmed"]
    if not isinstance(allow_registered, bool):
        raise ValidationError(
            "allow_registered_for_unconfirmed must be boolean"
        )
    requirements = configuration["stability_requirements"]
    if not isinstance(requirements, Mapping) or set(requirements) != (
        _REQUIRED_CAPABILITY_STABILITY_RULES
    ):
        raise ValidationError(
            "capability policy must define emerging, repeated, and stable"
        )
    normalized: dict[str, dict[str, int]] = {}
    for stability in ("emerging", "repeated", "stable"):
        rule = requirements[stability]
        if not isinstance(rule, Mapping) or set(rule) != {
            "minimum_claimed_evaluations",
            "minimum_sample_size",
        }:
            raise ValidationError(
                f"{stability} stability requirement has an invalid shape"
            )
        minimum_claimed = _positive_integer(
            rule["minimum_claimed_evaluations"],
            f"{stability}.minimum_claimed_evaluations",
            minimum=2,
        )
        minimum_sample = _positive_integer(
            rule["minimum_sample_size"],
            f"{stability}.minimum_sample_size",
        )
        normalized[stability] = {
            "minimum_claimed_evaluations": minimum_claimed,
            "minimum_sample_size": minimum_sample,
        }
    return {
        "allow_registered_for_unconfirmed": allow_registered,
        "stability_requirements": normalized,
    }


def maturity_policy_configuration(
    configuration: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact policy-supplied maturity transitions and thresholds."""

    if set(configuration) != {"stage_transitions"}:
        raise ValidationError(
            "maturity policy configuration has unsupported or missing fields"
        )
    transitions = configuration["stage_transitions"]
    if isinstance(transitions, (str, bytes, bytearray)) or not isinstance(
        transitions, Sequence
    ):
        raise ValidationError("stage_transitions must be an ordered sequence")
    if not transitions:
        raise ValidationError("stage_transitions must not be empty")
    normalized: list[dict[str, Any]] = []
    pairs: set[tuple[str | None, str]] = set()
    for index, transition in enumerate(transitions):
        if not isinstance(transition, Mapping) or set(transition) != {
            "from_stage",
            "to_stage",
            "minimum_claimed_evaluations",
        }:
            raise ValidationError(
                f"stage_transitions[{index}] has an invalid shape"
            )
        from_stage = transition["from_stage"]
        to_stage = transition["to_stage"]
        if from_stage is not None and from_stage not in MATURITY_STAGES:
            raise ValidationError(
                f"stage_transitions[{index}].from_stage is unsupported"
            )
        if to_stage not in MATURITY_STAGES:
            raise ValidationError(
                f"stage_transitions[{index}].to_stage is unsupported"
            )
        if from_stage == to_stage:
            raise ValidationError("maturity policy cannot repeat the same stage")
        pair = (from_stage, to_stage)
        if pair in pairs:
            raise ValidationError("maturity policy contains a duplicate transition")
        pairs.add(pair)
        normalized.append(
            {
                "from_stage": from_stage,
                "to_stage": to_stage,
                "minimum_claimed_evaluations": _positive_integer(
                    transition["minimum_claimed_evaluations"],
                    (
                        f"stage_transitions[{index}]"
                        ".minimum_claimed_evaluations"
                    ),
                ),
            }
        )
    return {"stage_transitions": normalized}


def validate_policy_configuration(
    policy_kind: str,
    configuration: Mapping[str, Any],
) -> dict[str, Any]:
    _enum(policy_kind, DEVELOPMENTAL_POLICY_KINDS, "policy_kind")
    if not isinstance(configuration, Mapping):
        raise ValidationError("configuration must be a JSON object")
    if policy_kind == "capability_stability":
        return capability_policy_configuration(configuration)
    return maturity_policy_configuration(configuration)


@dataclass(frozen=True, slots=True)
class EvaluationReferenceAnchor:
    """A narrow pre-I5 typed identity that never asserts an evaluation result."""

    evaluation_record_id: str
    evaluation_kind: str
    project_scope_id: str
    provenance_evidence_id: str
    registered_at: str
    provenance_summary: str
    state: str = "registered"

    def __post_init__(self) -> None:
        _identifier(self.evaluation_record_id, "evaluation_record_id")
        _enum(self.evaluation_kind, EVALUATION_KINDS, "evaluation_kind")
        _identifier(self.project_scope_id, "project_scope_id")
        _identifier(self.provenance_evidence_id, "provenance_evidence_id")
        parse_canonical_utc(self.registered_at, field="registered_at")
        _text(self.provenance_summary, "provenance_summary")
        _enum(self.state, EVALUATION_ANCHOR_STATES, "state")
        if self.state != "registered":
            raise ValidationError("new evaluation anchors must begin registered")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "evaluation_kind": self.evaluation_kind,
            "evaluation_record_id": self.evaluation_record_id,
            "project_scope_id": self.project_scope_id,
            "provenance_evidence_id": self.provenance_evidence_id,
            "provenance_summary": self.provenance_summary,
            "registered_at": self.registered_at,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True, init=False)
class DevelopmentalPolicyVersion:
    """One append-only, externally approved developmental policy version."""

    developmental_policy_id: str
    policy_kind: str
    version: str
    project_scope_id: str
    configuration_json: str
    authority_record_id: str
    approval_evidence_id: str
    approved_by_entity_id: str
    approved_at: str
    effective_from: str
    effective_until: str | None
    status: str

    def __init__(
        self,
        *,
        developmental_policy_id: str,
        policy_kind: str,
        version: str,
        project_scope_id: str,
        configuration: Mapping[str, Any],
        authority_record_id: str,
        approval_evidence_id: str,
        approved_by_entity_id: str,
        approved_at: str,
        effective_from: str,
        effective_until: str | None = None,
        status: str = "approved",
    ) -> None:
        object.__setattr__(
            self,
            "developmental_policy_id",
            _identifier(developmental_policy_id, "developmental_policy_id"),
        )
        object.__setattr__(
            self,
            "policy_kind",
            _enum(policy_kind, DEVELOPMENTAL_POLICY_KINDS, "policy_kind"),
        )
        object.__setattr__(self, "version", _text(version, "version"))
        object.__setattr__(
            self,
            "project_scope_id",
            _identifier(project_scope_id, "project_scope_id"),
        )
        normalized = validate_policy_configuration(policy_kind, configuration)
        object.__setattr__(
            self,
            "configuration_json",
            _canonical_object(normalized, "configuration"),
        )
        object.__setattr__(
            self,
            "authority_record_id",
            _identifier(authority_record_id, "authority_record_id"),
        )
        object.__setattr__(
            self,
            "approval_evidence_id",
            _identifier(approval_evidence_id, "approval_evidence_id"),
        )
        object.__setattr__(
            self,
            "approved_by_entity_id",
            _identifier(approved_by_entity_id, "approved_by_entity_id"),
        )
        parse_canonical_utc(approved_at, field="approved_at")
        parse_canonical_utc(effective_from, field="effective_from")
        if effective_from < approved_at:
            raise ValidationError("policy cannot become effective before approval")
        if effective_until is not None:
            parse_canonical_utc(effective_until, field="effective_until")
            if effective_until < effective_from:
                raise ValidationError(
                    "policy effective_until cannot precede effective_from"
                )
        object.__setattr__(self, "approved_at", approved_at)
        object.__setattr__(self, "effective_from", effective_from)
        object.__setattr__(self, "effective_until", effective_until)
        object.__setattr__(
            self,
            "status",
            _enum(status, DEVELOPMENTAL_POLICY_STATUSES, "status"),
        )

    @property
    def configuration(self) -> dict[str, Any]:
        return parse_json(self.configuration_json)

    def canonical_value(self) -> dict[str, Any]:
        return {
            "approval_evidence_id": self.approval_evidence_id,
            "approved_at": self.approved_at,
            "approved_by_entity_id": self.approved_by_entity_id,
            "authority_record_id": self.authority_record_id,
            "configuration": self.configuration,
            "developmental_policy_id": self.developmental_policy_id,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
            "policy_kind": self.policy_kind,
            "project_scope_id": self.project_scope_id,
            "status": self.status,
            "version": self.version,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())

    def database_values(self) -> dict[str, Any]:
        return {
            "developmental_policy_id": self.developmental_policy_id,
            "policy_kind": self.policy_kind,
            "version": self.version,
            "project_scope_id": self.project_scope_id,
            "configuration_json": self.configuration_json,
            "authority_record_id": self.authority_record_id,
            "approval_evidence_id": self.approval_evidence_id,
            "approved_by_entity_id": self.approved_by_entity_id,
            "approved_at": self.approved_at,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
            "status": self.status,
            "canonical_json": self.canonical_json,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class TrustedRuntimeAttestor:
    """One immutable, externally approved runtime-attestor registry version."""

    trusted_attestor_id: str
    attestor_entity_id: str
    project_scope_id: str
    attestation_environment: str
    authority_record_id: str
    approval_evidence_id: str
    registered_by_principal: str
    registered_by_entity_id: str
    approved_by_entity_id: str
    approved_at: str
    effective_from: str
    effective_until: str | None = None
    status: str = "active"
    supersedes_trusted_attestor_id: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.trusted_attestor_id, "trusted_attestor_id")
        _identifier(self.attestor_entity_id, "attestor_entity_id")
        _identifier(self.project_scope_id, "project_scope_id")
        _enum(
            self.attestation_environment,
            RUNTIME_ATTESTATION_ENVIRONMENTS,
            "attestation_environment",
        )
        _identifier(self.authority_record_id, "authority_record_id")
        _identifier(self.approval_evidence_id, "approval_evidence_id")
        if self.registered_by_principal != "operator":
            raise ValidationError(
                "trusted attestor registration requires operator attribution"
            )
        _identifier(
            self.registered_by_entity_id,
            "registered_by_entity_id",
        )
        _identifier(self.approved_by_entity_id, "approved_by_entity_id")
        parse_canonical_utc(self.approved_at, field="approved_at")
        parse_canonical_utc(self.effective_from, field="effective_from")
        if self.effective_from < self.approved_at:
            raise ValidationError(
                "trusted attestor cannot become effective before approval"
            )
        if self.effective_until is not None:
            parse_canonical_utc(
                self.effective_until,
                field="effective_until",
            )
            if self.effective_until < self.effective_from:
                raise ValidationError(
                    "trusted attestor effective_until cannot precede effective_from"
                )
        _enum(
            self.status,
            TRUSTED_RUNTIME_ATTESTOR_STATUSES,
            "status",
        )
        _optional_identifier(
            self.supersedes_trusted_attestor_id,
            "supersedes_trusted_attestor_id",
        )
        if self.supersedes_trusted_attestor_id == self.trusted_attestor_id:
            raise ValidationError("trusted attestor version cannot supersede itself")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "approval_evidence_id": self.approval_evidence_id,
            "approved_at": self.approved_at,
            "approved_by_entity_id": self.approved_by_entity_id,
            "attestation_environment": self.attestation_environment,
            "attestor_entity_id": self.attestor_entity_id,
            "authority_record_id": self.authority_record_id,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
            "project_scope_id": self.project_scope_id,
            "registered_by_entity_id": self.registered_by_entity_id,
            "registered_by_principal": self.registered_by_principal,
            "status": self.status,
            "supersedes_trusted_attestor_id": (
                self.supersedes_trusted_attestor_id
            ),
            "trusted_attestor_id": self.trusted_attestor_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())

    def database_values(self) -> dict[str, Any]:
        return {
            **self.canonical_value(),
            "canonical_json": self.canonical_json,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class RuntimeSubstrateAttestation:
    """Exact immutable runtime substrate captured by a governed attestor."""

    substrate_attestation_evidence_id: str
    trusted_attestor_id: str
    attestor_entity_id: str
    project_scope_id: str
    agent_entity_id: str
    runtime_instance_id: str
    attestation_environment: str
    base_model: str
    model_revision: str
    runtime_provider: str
    quantisation: str | None
    context_limit: int
    active_adapter: str | None
    runtime_started_at: str
    captured_at: str
    changed_by_principal: str
    changed_by_entity_id: str

    def __post_init__(self) -> None:
        _identifier(
            self.substrate_attestation_evidence_id,
            "substrate_attestation_evidence_id",
        )
        _identifier(self.trusted_attestor_id, "trusted_attestor_id")
        _identifier(self.attestor_entity_id, "attestor_entity_id")
        _identifier(self.project_scope_id, "project_scope_id")
        _identifier(self.agent_entity_id, "agent_entity_id")
        _identifier(self.runtime_instance_id, "runtime_instance_id")
        _enum(
            self.attestation_environment,
            RUNTIME_ATTESTATION_ENVIRONMENTS,
            "attestation_environment",
        )
        _substrate_text(self.base_model, "base_model")
        _substrate_text(self.model_revision, "model_revision")
        _substrate_text(self.runtime_provider, "runtime_provider")
        if self.quantisation is not None:
            _substrate_text(self.quantisation, "quantisation")
        _positive_integer(self.context_limit, "context_limit")
        if self.active_adapter is not None:
            _substrate_text(self.active_adapter, "active_adapter")
        parse_canonical_utc(self.runtime_started_at, field="runtime_started_at")
        parse_canonical_utc(self.captured_at, field="captured_at")
        if self.captured_at < self.runtime_started_at:
            raise ValidationError(
                "runtime substrate cannot be captured before runtime start"
            )
        expected_principal = (
            "validated_system"
            if self.attestation_environment == "production"
            else "codex_development_harness"
        )
        if self.changed_by_principal != expected_principal:
            raise ValidationError(
                f"{self.attestation_environment} attestation requires "
                f"{expected_principal}"
            )
        _identifier(self.changed_by_entity_id, "changed_by_entity_id")
        if self.changed_by_entity_id != self.attestor_entity_id:
            raise ValidationError(
                "changed_by_entity_id must equal the trusted attestor entity"
            )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "active_adapter": self.active_adapter,
            "agent_entity_id": self.agent_entity_id,
            "attestation_environment": self.attestation_environment,
            "attestation_type": "runtime_substrate_attestation",
            "attestor_entity_id": self.attestor_entity_id,
            "base_model": self.base_model,
            "captured_at": self.captured_at,
            "changed_by_entity_id": self.changed_by_entity_id,
            "changed_by_principal": self.changed_by_principal,
            "context_limit": self.context_limit,
            "model_revision": self.model_revision,
            "project_scope_id": self.project_scope_id,
            "quantisation": self.quantisation,
            "runtime_instance_id": self.runtime_instance_id,
            "runtime_provider": self.runtime_provider,
            "runtime_started_at": self.runtime_started_at,
            "substrate_attestation_evidence_id": (
                self.substrate_attestation_evidence_id
            ),
            "trusted_attestor_id": self.trusted_attestor_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())

    def database_values(self) -> dict[str, Any]:
        return {
            **{
                key: value
                for key, value in self.canonical_value().items()
                if key != "attestation_type"
            },
            "canonical_json": self.canonical_json,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class RuntimeIdentityPayload:
    record_id: str
    agent_entity_id: str
    base_model: str
    model_revision: str
    runtime_provider: str
    quantisation: str | None
    context_limit: int
    active_adapter: str | None
    runtime_started_at: str
    runtime_instance_id: str
    substrate_attestor_entity_id: str
    substrate_attestation_evidence_id: str

    RECORD_TYPE: ClassVar[str] = "runtime_identity"
    TABLE: ClassVar[str] = "runtime_identities"

    def __post_init__(self) -> None:
        _identifier(self.record_id, "record_id")
        _identifier(self.agent_entity_id, "agent_entity_id")
        _substrate_text(self.base_model, "base_model")
        _substrate_text(self.model_revision, "model_revision")
        _substrate_text(self.runtime_provider, "runtime_provider")
        if self.quantisation is not None:
            _substrate_text(self.quantisation, "quantisation")
        _positive_integer(self.context_limit, "context_limit")
        if self.active_adapter is not None:
            _substrate_text(self.active_adapter, "active_adapter")
        parse_canonical_utc(self.runtime_started_at, field="runtime_started_at")
        _identifier(self.runtime_instance_id, "runtime_instance_id")
        _identifier(
            self.substrate_attestor_entity_id,
            "substrate_attestor_entity_id",
        )
        _identifier(
            self.substrate_attestation_evidence_id,
            "substrate_attestation_evidence_id",
        )

    def canonical_content(self) -> dict[str, Any]:
        return {
            "active_adapter": self.active_adapter,
            "agent_entity_id": self.agent_entity_id,
            "base_model": self.base_model,
            "context_limit": self.context_limit,
            "model_revision": self.model_revision,
            "quantisation": self.quantisation,
            "record_id": self.record_id,
            "runtime_instance_id": self.runtime_instance_id,
            "runtime_provider": self.runtime_provider,
            "runtime_started_at": self.runtime_started_at,
            "substrate_attestor_entity_id": (
                self.substrate_attestor_entity_id
            ),
            "substrate_attestation_evidence_id": (
                self.substrate_attestation_evidence_id
            ),
        }

    def database_values(self) -> dict[str, Any]:
        return self.canonical_content()


@dataclass(frozen=True, slots=True, init=False)
class CapabilityObservationPayload:
    record_id: str
    capability_name: str
    capability_key: str
    observation_type: str
    evidence_summary: str
    sample_size: int
    evaluation_record_ids: tuple[str, ...]
    stability: str
    developmental_policy_id: str | None

    RECORD_TYPE: ClassVar[str] = "capability_observation"
    TABLE: ClassVar[str] = "capability_observations"

    def __init__(
        self,
        *,
        record_id: str,
        capability_name: str,
        observation_type: str,
        evidence_summary: str,
        sample_size: int,
        evaluation_record_ids: Sequence[str],
        stability: str,
        developmental_policy_id: str | None = None,
    ) -> None:
        object.__setattr__(self, "record_id", _identifier(record_id, "record_id"))
        object.__setattr__(
            self,
            "capability_name",
            _text(capability_name, "capability_name"),
        )
        object.__setattr__(
            self,
            "capability_key",
            capability_name.strip().casefold(),
        )
        object.__setattr__(
            self,
            "observation_type",
            _enum(
                observation_type,
                CAPABILITY_OBSERVATION_TYPES,
                "observation_type",
            ),
        )
        object.__setattr__(
            self,
            "evidence_summary",
            _text(evidence_summary, "evidence_summary"),
        )
        evaluation_ids = _identifiers(
            evaluation_record_ids,
            "evaluation_record_ids",
        )
        size = _positive_integer(sample_size, "sample_size")
        if size != len(evaluation_ids):
            raise ValidationError(
                "sample_size must exactly reconcile with evaluation_record_ids"
            )
        object.__setattr__(self, "sample_size", size)
        object.__setattr__(self, "evaluation_record_ids", evaluation_ids)
        object.__setattr__(
            self,
            "stability",
            _enum(stability, frozenset(CAPABILITY_STABILITIES), "stability"),
        )
        policy_id = _optional_identifier(
            developmental_policy_id,
            "developmental_policy_id",
        )
        if stability != "unconfirmed" and policy_id is None:
            raise ValidationError(
                "emerging, repeated, and stable observations require a policy"
            )
        object.__setattr__(self, "developmental_policy_id", policy_id)

    def canonical_content(self) -> dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "developmental_policy_id": self.developmental_policy_id,
            "evaluation_record_ids": list(self.evaluation_record_ids),
            "evidence_summary": self.evidence_summary,
            "observation_type": self.observation_type,
            "record_id": self.record_id,
            "sample_size": self.sample_size,
            "stability": self.stability,
        }

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "capability_name": self.capability_name,
            "capability_key": self.capability_key,
            "observation_type": self.observation_type,
            "evidence_summary": self.evidence_summary,
            "sample_size": self.sample_size,
            "stability": self.stability,
            "developmental_policy_id": self.developmental_policy_id,
        }


@dataclass(frozen=True, slots=True, init=False)
class MaturityStatePayload:
    record_id: str
    stage: str
    entered_at: str
    basis: tuple[str, ...]
    restrictions_json: str
    next_gate: str
    agent_entity_id: str
    developmental_policy_id: str

    RECORD_TYPE: ClassVar[str] = "maturity_state"
    TABLE: ClassVar[str] = "maturity_states"

    def __init__(
        self,
        *,
        record_id: str,
        stage: str,
        entered_at: str,
        basis: Sequence[str],
        restrictions: Sequence[str],
        next_gate: str,
        agent_entity_id: str,
        developmental_policy_id: str,
    ) -> None:
        object.__setattr__(self, "record_id", _identifier(record_id, "record_id"))
        object.__setattr__(
            self,
            "stage",
            _enum(stage, frozenset(MATURITY_STAGES), "stage"),
        )
        parse_canonical_utc(entered_at, field="entered_at")
        object.__setattr__(self, "entered_at", entered_at)
        object.__setattr__(self, "basis", _identifiers(basis, "basis"))
        normalized_restrictions = _strings(restrictions, "restrictions")
        object.__setattr__(
            self,
            "restrictions_json",
            canonical_json_text(list(normalized_restrictions)),
        )
        object.__setattr__(self, "next_gate", _text(next_gate, "next_gate"))
        object.__setattr__(
            self,
            "agent_entity_id",
            _identifier(agent_entity_id, "agent_entity_id"),
        )
        object.__setattr__(
            self,
            "developmental_policy_id",
            _identifier(
                developmental_policy_id,
                "developmental_policy_id",
            ),
        )

    @property
    def restrictions(self) -> tuple[str, ...]:
        return tuple(parse_json(self.restrictions_json))

    def canonical_content(self) -> dict[str, Any]:
        return {
            "agent_entity_id": self.agent_entity_id,
            "basis": list(self.basis),
            "developmental_policy_id": self.developmental_policy_id,
            "entered_at": self.entered_at,
            "next_gate": self.next_gate,
            "record_id": self.record_id,
            "restrictions": list(self.restrictions),
            "stage": self.stage,
        }

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "stage": self.stage,
            "entered_at": self.entered_at,
            "restrictions_json": self.restrictions_json,
            "next_gate": self.next_gate,
            "agent_entity_id": self.agent_entity_id,
            "developmental_policy_id": self.developmental_policy_id,
        }


FactualSelfPayload: TypeAlias = (
    RuntimeIdentityPayload
    | CapabilityObservationPayload
    | MaturityStatePayload
)
FACTUAL_SELF_PAYLOAD_TYPES: Mapping[str, type[FactualSelfPayload]] = {
    payload_type.RECORD_TYPE: payload_type
    for payload_type in (
        RuntimeIdentityPayload,
        CapabilityObservationPayload,
        MaturityStatePayload,
    )
}


def _validate_factual_self_identity(
    envelope: RecordEnvelope,
    payload: FactualSelfPayload,
) -> None:
    if not isinstance(payload, tuple(FACTUAL_SELF_PAYLOAD_TYPES.values())):
        raise TypeError("payload must be an accepted B87-I3-C1 payload")
    if envelope.record_id != payload.record_id:
        raise ValidationError("payload and envelope record identifiers differ")
    if envelope.record_family != SELF_MODEL_RECORD_FAMILY:
        raise ValidationError("factual self-model record family must be self_model")
    if envelope.record_type != payload.RECORD_TYPE:
        raise ValidationError("payload type does not match the record envelope")
    if envelope.project_scope_id is None:
        raise ValidationError("factual self-model memory requires project_scope_id")
    if envelope.subject_entity_id is None:
        raise ValidationError("factual self-model memory requires an agent subject")
    expected_write_policy = MEMORY_RECORD_POLICIES[
        (envelope.record_family, envelope.record_type)
    ][2]
    if envelope.agent_write_policy != expected_write_policy:
        raise ValidationError("agent_write_policy does not match the I3-A registry")

    if isinstance(payload, RuntimeIdentityPayload):
        if envelope.authority_class != "validated_system_evidence":
            raise ValidationError(
                "runtime identity requires validated_system_evidence authority"
            )
        if envelope.source_kind != "runtime_event":
            raise ValidationError("runtime identity must originate from a runtime event")
        if envelope.subject_entity_id != payload.agent_entity_id:
            raise ValidationError("runtime identity agent differs from envelope subject")
        if envelope.created_by_runtime_id != payload.runtime_instance_id:
            raise ValidationError(
                "runtime identity instance differs from envelope creator runtime"
            )
    elif isinstance(payload, MaturityStatePayload):
        if envelope.subject_entity_id != payload.agent_entity_id:
            raise ValidationError("maturity-state agent differs from envelope subject")


def validate_factual_self_pair(
    envelope: RecordEnvelope,
    payload: FactualSelfPayload,
) -> None:
    _validate_factual_self_identity(envelope, payload)
    if envelope.integrity_status != "valid":
        raise ValidationError("factual self-model memory must begin with valid integrity")
    if isinstance(payload, RuntimeIdentityPayload):
        if envelope.lifecycle_state != "observed":
            raise ValidationError("runtime identity must begin observed")
        if envelope.approval_status != "not_required":
            raise ValidationError("runtime identity approval must be not_required")
    elif isinstance(payload, CapabilityObservationPayload):
        if envelope.lifecycle_state != "candidate":
            raise ValidationError("capability observation must begin candidate")
        if envelope.approval_status != "pending":
            raise ValidationError("capability observation must begin pending")
    else:
        if envelope.lifecycle_state != "reviewed":
            raise ValidationError("maturity state must begin reviewed")
        if envelope.approval_status != "pending":
            raise ValidationError("maturity state must begin pending")


def factual_self_content_hash(
    envelope: RecordEnvelope,
    payload: FactualSelfPayload,
) -> str:
    _validate_factual_self_identity(envelope, payload)
    return sha256_canonical_json(
        {
            "envelope": envelope.hash_material(),
            "payload": payload.canonical_content(),
            "payload_type": payload.RECORD_TYPE,
        }
    )


def payload_from_database(
    record_type: str,
    row: Mapping[str, Any],
    *,
    evaluation_record_ids: Sequence[str] = (),
) -> FactualSelfPayload:
    values = dict(row)
    if record_type == "runtime_identity":
        return RuntimeIdentityPayload(
            **{
                field: values[field]
                for field in RuntimeIdentityPayload.__dataclass_fields__
                if field not in {"RECORD_TYPE", "TABLE"}
            }
        )
    if record_type == "capability_observation":
        return CapabilityObservationPayload(
            record_id=values["record_id"],
            capability_name=values["capability_name"],
            observation_type=values["observation_type"],
            evidence_summary=values["evidence_summary"],
            sample_size=values["sample_size"],
            evaluation_record_ids=evaluation_record_ids,
            stability=values["stability"],
            developmental_policy_id=values["developmental_policy_id"],
        )
    if record_type == "maturity_state":
        return MaturityStatePayload(
            record_id=values["record_id"],
            stage=values["stage"],
            entered_at=values["entered_at"],
            basis=evaluation_record_ids,
            restrictions=parse_json(values["restrictions_json"]),
            next_gate=values["next_gate"],
            agent_entity_id=values["agent_entity_id"],
            developmental_policy_id=values["developmental_policy_id"],
        )
    raise ValidationError(f"unsupported factual self-model type: {record_type!r}")
