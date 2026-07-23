"""Validated value objects accepted by governed repositories."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_bytes, sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc

LIFECYCLE_STATES = frozenset(
    {
        "observed",
        "candidate",
        "reviewed",
        "approved",
        "active",
        "superseded",
        "revoked",
        "archived",
        "deleted",
    }
)
APPROVAL_STATUSES = frozenset(
    {"not_required", "pending", "approved", "rejected", "withdrawn"}
)
AUTHORITY_CLASSES = frozenset(
    {
        "law_or_external_obligation",
        "nolan_approved",
        "nolan_byte_approved",
        "validated_system_evidence",
        "approved_project_policy",
        "approved_memory",
        "approved_evaluation",
        "agent_proposal",
        "model_inference",
        "external_untrusted",
        "unknown",
    }
)
CERTAINTY_CLASSES = frozenset(
    {"verified", "strongly_supported", "inferred", "speculative", "disputed", "unknown"}
)
SENSITIVITY_CLASSES = frozenset(
    {"public", "internal", "confidential", "restricted", "secret"}
)
PRIVACY_CLASSES = frozenset(
    {
        "none",
        "personal",
        "sensitive_personal",
        "credential",
        "legally_restricted",
        "unknown",
    }
)
RETENTION_CLASSES = frozenset(
    {
        "ephemeral",
        "temporary",
        "project_duration",
        "long_term",
        "permanent_history",
        "legally_governed",
    }
)
TRAINING_ELIGIBILITIES = frozenset(
    {"ineligible", "pending_review", "approved", "prohibited"}
)
SOURCE_KINDS = frozenset(
    {
        "human_statement",
        "project_document",
        "test",
        "runtime_event",
        "model_output",
        "external_source",
        "derived_record",
    }
)
AGENT_WRITE_POLICIES = frozenset(
    {"prohibited", "candidate_only", "externally_approved"}
)
INTEGRITY_STATUSES = frozenset(
    {"valid", "mismatch", "unavailable", "not_applicable"}
)
REFERENCE_KINDS = frozenset(
    {
        "evaluation_experiment",
        "evaluation_fixture",
        "context_manifest",
        "model_invocation",
    }
)
ANCHOR_LIFECYCLE_STATES = frozenset(
    {"registered", "claimed", "invalid", "retired"}
)
TEST_CONDITIONS = frozenset(
    {"invalid", "valid_authority_control", "neutral_control", "recovery"}
)
COMPLETION_STATES = frozenset({"exploratory", "incomplete"})
EVIDENCE_KINDS = frozenset(
    {
        "document",
        "code",
        "log",
        "test_report",
        "human_statement",
        "model_output",
        "system_event",
        "external_source",
        "controlled_prompt",
        "controlled_output",
    }
)
STORAGE_KINDS = frozenset(
    {
        "inline_text",
        "local_file",
        "repository_reference",
        "external_reference",
        "generated_record",
    }
)
EVIDENCE_RELATIONSHIPS = frozenset(
    {
        "derived_from",
        "supports",
        "contradicts",
        "contextualises",
        "does_not_establish",
        "produced_as",
        "evaluated_against",
    }
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")
_MAX_INLINE_EVIDENCE_BYTES = 65_536


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be non-empty text")
    return value


def _enum(value: str, accepted: frozenset[str], field: str) -> str:
    if value not in accepted:
        raise ValidationError(f"{field} has an unsupported value: {value!r}")
    return value


def _token(value: str, field: str) -> str:
    _text(value, field)
    if _TOKEN.fullmatch(value) is None:
        raise ValidationError(f"{field} must be a lowercase token")
    return value


def _identifier_or_none(value: str | None, field: str) -> str | None:
    if value is not None:
        validate_identifier(value, field=field)
    return value


def _timestamp_or_none(value: str | None, field: str) -> str | None:
    if value is not None:
        parse_canonical_utc(value, field=field)
    return value


def _canonical_object(value: str, field: str) -> dict[str, Any]:
    parsed = parse_json(value)
    if not isinstance(parsed, dict):
        raise ValidationError(f"{field} must be a JSON object")
    if canonical_json_text(parsed) != value:
        raise ValidationError(f"{field} must use canonical JSON")
    return parsed


def _sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValidationError(f"{field} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True)
class RuntimeInstance:
    runtime_instance_id: str
    started_at: str
    application_version: str
    status: str = "running"
    stopped_at: str | None = None
    host_fingerprint: str | None = None
    process_id: int | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.runtime_instance_id, field="runtime_instance_id")
        parse_canonical_utc(self.started_at, field="started_at")
        _timestamp_or_none(self.stopped_at, "stopped_at")
        _text(self.application_version, "application_version")
        _enum(self.status, frozenset({"running", "stopped", "failed"}), "status")
        if self.stopped_at is not None and self.stopped_at < self.started_at:
            raise ValidationError("stopped_at cannot precede started_at")
        if self.host_fingerprint is not None:
            _sha256(self.host_fingerprint, "host_fingerprint")
        if self.process_id is not None and self.process_id < 1:
            raise ValidationError("process_id must be positive")


@dataclass(frozen=True, slots=True)
class Entity:
    entity_id: str
    entity_kind: str
    canonical_name: str
    description: str
    status: str
    created_at: str

    def __post_init__(self) -> None:
        validate_identifier(self.entity_id, field="entity_id")
        _enum(
            self.entity_kind,
            frozenset(
                {
                    "person",
                    "agent",
                    "project",
                    "repository",
                    "organisation",
                    "system",
                    "component",
                }
            ),
            "entity_kind",
        )
        _text(self.canonical_name, "canonical_name")
        _text(self.description, "description")
        _enum(self.status, frozenset({"active", "inactive", "archived"}), "status")
        parse_canonical_utc(self.created_at, field="created_at")


@dataclass(frozen=True, slots=True)
class EntityAlias:
    entity_alias_id: str
    entity_id: str
    alias: str
    scope_id: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.entity_alias_id, field="entity_alias_id")
        validate_identifier(self.entity_id, field="entity_id")
        _text(self.alias, "alias")
        _identifier_or_none(self.scope_id, "scope_id")


@dataclass(frozen=True, slots=True)
class Scope:
    scope_id: str
    scope_kind: str
    canonical_name: str
    status: str
    parent_scope_id: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.scope_id, field="scope_id")
        _enum(
            self.scope_kind,
            frozenset(
                {
                    "construct",
                    "project",
                    "repository",
                    "component",
                    "session",
                    "task",
                    "evaluation",
                }
            ),
            "scope_kind",
        )
        _text(self.canonical_name, "canonical_name")
        _enum(self.status, frozenset({"active", "inactive", "archived"}), "status")
        _identifier_or_none(self.parent_scope_id, "parent_scope_id")
        if self.parent_scope_id == self.scope_id:
            raise ValidationError("scope cannot be its own parent")


@dataclass(frozen=True, slots=True)
class RecordEnvelope:
    record_id: str
    record_family: str
    record_type: str
    schema_version: str
    lifecycle_state: str
    approval_status: str
    authority_class: str
    certainty_class: str
    sensitivity_class: str
    privacy_class: str
    retention_class: str
    training_eligibility: str
    created_at: str
    source_kind: str
    provenance_summary: str
    retrieval_policy_json: str
    deletion_policy_json: str
    agent_write_policy: str
    construct_scope_id: str | None = None
    project_scope_id: str | None = None
    subject_entity_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    created_by_entity_id: str | None = None
    created_by_runtime_id: str | None = None
    effective_from: str | None = None
    effective_until: str | None = None
    review_due_at: str | None = None
    supersedes_record_id: str | None = None
    superseded_by_record_id: str | None = None
    previous_version_id: str | None = None
    integrity_status: str = "valid"
    deleted_at: str | None = None
    deletion_basis: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.record_id, field="record_id")
        _token(self.record_family, "record_family")
        _token(self.record_type, "record_type")
        _text(self.schema_version, "schema_version")
        _enum(self.lifecycle_state, LIFECYCLE_STATES, "lifecycle_state")
        _enum(self.approval_status, APPROVAL_STATUSES, "approval_status")
        _enum(self.authority_class, AUTHORITY_CLASSES, "authority_class")
        _enum(self.certainty_class, CERTAINTY_CLASSES, "certainty_class")
        _enum(self.sensitivity_class, SENSITIVITY_CLASSES, "sensitivity_class")
        _enum(self.privacy_class, PRIVACY_CLASSES, "privacy_class")
        _enum(self.retention_class, RETENTION_CLASSES, "retention_class")
        _enum(
            self.training_eligibility,
            TRAINING_ELIGIBILITIES,
            "training_eligibility",
        )
        parse_canonical_utc(self.created_at, field="created_at")
        _enum(self.source_kind, SOURCE_KINDS, "source_kind")
        _text(self.provenance_summary, "provenance_summary")
        _canonical_object(self.retrieval_policy_json, "retrieval_policy_json")
        _canonical_object(self.deletion_policy_json, "deletion_policy_json")
        _enum(
            self.agent_write_policy,
            AGENT_WRITE_POLICIES,
            "agent_write_policy",
        )
        _enum(self.integrity_status, INTEGRITY_STATUSES, "integrity_status")

        identifier_fields = (
            "construct_scope_id",
            "project_scope_id",
            "subject_entity_id",
            "session_id",
            "task_id",
            "created_by_entity_id",
            "created_by_runtime_id",
            "supersedes_record_id",
            "superseded_by_record_id",
            "previous_version_id",
        )
        for field in identifier_fields:
            _identifier_or_none(getattr(self, field), field)
        for field in (
            "effective_from",
            "effective_until",
            "review_due_at",
            "deleted_at",
        ):
            _timestamp_or_none(getattr(self, field), field)

        linked_ids = (
            self.supersedes_record_id,
            self.superseded_by_record_id,
            self.previous_version_id,
        )
        if self.record_id in linked_ids:
            raise ValidationError("record cannot reference itself as another version")
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_from > self.effective_until
        ):
            raise ValidationError("effective_from cannot follow effective_until")
        if self.lifecycle_state == "active" and self.approval_status == "rejected":
            raise ValidationError("a rejected record cannot be active")
        if self.training_eligibility == "approved" and self.privacy_class != "none":
            raise ValidationError("private records cannot be training-approved")
        if self.record_family == "evaluation_evidence" and self.project_scope_id is None:
            raise ValidationError("evaluation evidence requires project_scope_id")
        if self.lifecycle_state == "deleted":
            if self.deleted_at is None or not self.deletion_basis:
                raise ValidationError("deleted records require timestamp and basis")
        elif self.deleted_at is not None:
            raise ValidationError("non-deleted records cannot have deleted_at")

    @classmethod
    def for_controlled_resilience(
        cls,
        *,
        record_id: str,
        project_scope_id: str,
        created_at: str,
        provenance_summary: str,
    ) -> RecordEnvelope:
        """Build the immutable A4.2 classification for an I1 raw run record."""

        return cls(
            record_id=record_id,
            record_family="evaluation_evidence",
            record_type="controlled_governance_resilience_run",
            schema_version="1",
            project_scope_id=project_scope_id,
            lifecycle_state="observed",
            approval_status="not_required",
            authority_class="validated_system_evidence",
            certainty_class="verified",
            sensitivity_class="restricted",
            privacy_class="none",
            retention_class="project_duration",
            training_eligibility="prohibited",
            created_at=created_at,
            source_kind="test",
            provenance_summary=provenance_summary,
            retrieval_policy_json=canonical_json_text(
                {
                    "ordinary_memory_eligibility": "prohibited",
                    "retrieval_mode": "evaluation_only",
                }
            ),
            deletion_policy_json=canonical_json_text(
                {"deletion_mode": "governed"}
            ),
            agent_write_policy="prohibited",
        )

    def hash_material(self) -> dict[str, Any]:
        """Return immutable envelope content, excluding mutable assessment state."""

        return {
            "record_id": self.record_id,
            "record_family": self.record_family,
            "record_type": self.record_type,
            "schema_version": self.schema_version,
            "construct_scope_id": self.construct_scope_id,
            "project_scope_id": self.project_scope_id,
            "subject_entity_id": self.subject_entity_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "authority_class": self.authority_class,
            "certainty_class": self.certainty_class,
            "sensitivity_class": self.sensitivity_class,
            "privacy_class": self.privacy_class,
            "retention_class": self.retention_class,
            "training_eligibility": self.training_eligibility,
            "created_at": self.created_at,
            "created_by_entity_id": self.created_by_entity_id,
            "created_by_runtime_id": self.created_by_runtime_id,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
            "supersedes_record_id": self.supersedes_record_id,
            "previous_version_id": self.previous_version_id,
            "source_kind": self.source_kind,
            "provenance_summary": self.provenance_summary,
            "retrieval_policy": parse_json(self.retrieval_policy_json),
            "deletion_policy": parse_json(self.deletion_policy_json),
            "agent_write_policy": self.agent_write_policy,
        }

    def database_values(self, *, content_hash: str) -> dict[str, Any]:
        _sha256(content_hash, "content_hash")
        values = {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }
        values["content_hash"] = content_hash
        return values


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    evidence_kind: str
    storage_kind: str
    captured_at: str
    integrity_status: str
    redaction_status: str
    sensitivity_class: str
    privacy_class: str
    storage_location: str | None = None
    original_name: str | None = None
    media_type: str | None = None
    byte_length: int | None = None
    content_hash: str | None = None
    captured_by_entity: str | None = None
    inline_content: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.evidence_id, field="evidence_id")
        _enum(self.evidence_kind, EVIDENCE_KINDS, "evidence_kind")
        _enum(self.storage_kind, STORAGE_KINDS, "storage_kind")
        parse_canonical_utc(self.captured_at, field="captured_at")
        _enum(
            self.integrity_status,
            frozenset({"valid", "mismatch", "unavailable"}),
            "integrity_status",
        )
        _enum(
            self.redaction_status,
            frozenset({"none", "partial", "full"}),
            "redaction_status",
        )
        _enum(self.sensitivity_class, SENSITIVITY_CLASSES, "sensitivity_class")
        _enum(self.privacy_class, PRIVACY_CLASSES, "privacy_class")
        _identifier_or_none(self.captured_by_entity, "captured_by_entity")
        if self.byte_length is not None and self.byte_length < 0:
            raise ValidationError("byte_length cannot be negative")

        if self.storage_kind == "inline_text":
            if self.inline_content is None:
                raise ValidationError("inline_text evidence requires inline_content")
            if self.storage_location is not None:
                raise ValidationError("inline_text evidence cannot have a location")
            exact = self.inline_content.encode("utf-8")
            if len(exact) > _MAX_INLINE_EVIDENCE_BYTES:
                raise ValidationError("inline evidence exceeds 65536 UTF-8 bytes")
            derived_hash = sha256_bytes(exact)
            if self.content_hash is not None and self.content_hash != derived_hash:
                raise ValidationError("inline evidence hash does not match exact bytes")
            if self.byte_length is not None and self.byte_length != len(exact):
                raise ValidationError("inline evidence byte_length does not match")
            object.__setattr__(self, "content_hash", derived_hash)
            object.__setattr__(self, "byte_length", len(exact))
        else:
            if self.inline_content is not None:
                raise ValidationError("non-inline evidence cannot carry inline_content")
            if self.storage_kind != "generated_record":
                _text(self.storage_location or "", "storage_location")
            if self.content_hash is None:
                raise ValidationError("non-inline evidence requires content_hash")
            _sha256(self.content_hash, "content_hash")

    @classmethod
    def inline_text(
        cls,
        *,
        evidence_id: str,
        evidence_kind: str,
        content: str,
        captured_at: str,
        sensitivity_class: str = "restricted",
        privacy_class: str = "none",
        captured_by_entity: str | None = None,
    ) -> EvidenceItem:
        return cls(
            evidence_id=evidence_id,
            evidence_kind=evidence_kind,
            storage_kind="inline_text",
            captured_at=captured_at,
            integrity_status="valid",
            redaction_status="none",
            sensitivity_class=sensitivity_class,
            privacy_class=privacy_class,
            captured_by_entity=captured_by_entity,
            media_type="text/plain; charset=utf-8",
            inline_content=content,
        )

    def database_values(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_kind": self.evidence_kind,
            "storage_kind": self.storage_kind,
            "storage_location": self.storage_location,
            "original_name": self.original_name,
            "media_type": self.media_type,
            "byte_length": self.byte_length,
            "content_hash": self.content_hash,
            "captured_at": self.captured_at,
            "captured_by_entity": self.captured_by_entity,
            "integrity_status": self.integrity_status,
            "redaction_status": self.redaction_status,
            "sensitivity_class": self.sensitivity_class,
            "privacy_class": self.privacy_class,
        }


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    record_id: str
    evidence_id: str
    relationship: str
    explanation: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.record_id, field="record_id")
        validate_identifier(self.evidence_id, field="evidence_id")
        _enum(self.relationship, EVIDENCE_RELATIONSHIPS, "relationship")


@dataclass(frozen=True, slots=True)
class ReferenceAnchor:
    reference_id: str
    reference_kind: str
    project_scope_id: str
    created_at: str
    provenance_json: str
    lifecycle_state: str = "registered"
    integrity_status: str = "valid"

    def __post_init__(self) -> None:
        validate_identifier(self.reference_id, field="reference_id")
        _enum(self.reference_kind, REFERENCE_KINDS, "reference_kind")
        validate_identifier(self.project_scope_id, field="project_scope_id")
        parse_canonical_utc(self.created_at, field="created_at")
        _canonical_object(self.provenance_json, "provenance_json")
        _enum(
            self.lifecycle_state,
            ANCHOR_LIFECYCLE_STATES,
            "lifecycle_state",
        )
        _enum(
            self.integrity_status,
            frozenset({"valid", "mismatch", "unavailable"}),
            "integrity_status",
        )

    def hash_material(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "reference_kind": self.reference_kind,
            "project_scope_id": self.project_scope_id,
            "created_at": self.created_at,
            "provenance": parse_json(self.provenance_json),
        }

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.hash_material())


@dataclass(frozen=True, slots=True)
class ControlledResiliencePayload:
    record_id: str
    experiment_id: str
    fixture_id: str
    test_family: str
    test_level: int
    test_condition: str
    run_id: str
    governance_distinction: str
    maximum_test_intensity: str
    raw_prompt_evidence_id: str
    raw_output_evidence_id: str
    context_manifest_id: str
    model_invocation_id: str
    created_at: str
    recovery_record_id: str | None = None
    lesson_derivation_status: str = "not_reviewed"
    completion_state: str = "incomplete"

    def __post_init__(self) -> None:
        for field in (
            "record_id",
            "experiment_id",
            "fixture_id",
            "run_id",
            "raw_prompt_evidence_id",
            "raw_output_evidence_id",
            "context_manifest_id",
            "model_invocation_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        _identifier_or_none(self.recovery_record_id, "recovery_record_id")
        _text(self.test_family, "test_family")
        if not isinstance(self.test_level, int) or isinstance(self.test_level, bool):
            raise ValidationError("test_level must be an integer")
        if self.test_level < 1:
            raise ValidationError("test_level must be positive")
        _enum(self.test_condition, TEST_CONDITIONS, "test_condition")
        _text(self.governance_distinction, "governance_distinction")
        _text(self.maximum_test_intensity, "maximum_test_intensity")
        _enum(
            self.lesson_derivation_status,
            frozenset(
                {
                    "not_reviewed",
                    "prohibited",
                    "candidate_created",
                    "no_lesson_required",
                }
            ),
            "lesson_derivation_status",
        )
        _enum(self.completion_state, COMPLETION_STATES, "completion_state")
        parse_canonical_utc(self.created_at, field="created_at")
        if self.raw_prompt_evidence_id == self.raw_output_evidence_id:
            raise ValidationError("raw prompt and output evidence must differ")
        if self.recovery_record_id == self.record_id:
            raise ValidationError("recovery record must differ from the raw run record")

    def hash_material(self) -> dict[str, Any]:
        return {
            "evaluation_mode": "controlled_governance_resilience",
            "experiment_id": self.experiment_id,
            "experiment_reference_kind": "evaluation_experiment",
            "fixture_id": self.fixture_id,
            "fixture_reference_kind": "evaluation_fixture",
            "test_family": self.test_family,
            "test_level": self.test_level,
            "test_condition": self.test_condition,
            "run_id": self.run_id,
            "governance_distinction": self.governance_distinction,
            "maximum_test_intensity": self.maximum_test_intensity,
            "raw_prompt_evidence_id": self.raw_prompt_evidence_id,
            "raw_output_evidence_id": self.raw_output_evidence_id,
            "context_manifest_id": self.context_manifest_id,
            "context_manifest_reference_kind": "context_manifest",
            "model_invocation_id": self.model_invocation_id,
            "model_invocation_reference_kind": "model_invocation",
            "recovery_record_id": self.recovery_record_id,
            "ordinary_memory_eligibility": "prohibited",
            "identity_eligibility": "prohibited",
            "lesson_derivation_status": self.lesson_derivation_status,
            "completion_state": self.completion_state,
            "created_at": self.created_at,
        }

    def database_values(self) -> dict[str, Any]:
        return self.hash_material() | {"record_id": self.record_id}


def record_content_hash(envelope: RecordEnvelope) -> str:
    return sha256_canonical_json(envelope.hash_material())


def controlled_resilience_content_hash(
    envelope: RecordEnvelope,
    payload: ControlledResiliencePayload,
) -> str:
    return sha256_canonical_json(
        {
            "envelope": envelope.hash_material(),
            "controlled_resilience": payload.hash_material(),
        }
    )
