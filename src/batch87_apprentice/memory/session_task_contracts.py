"""Deterministic contracts for B87-I3-D session and task memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc
from batch87_apprentice.persistence.contracts import RecordEnvelope


CONTEXT_KINDS = frozenset(
    {
        "constitution",
        "policy",
        "construct_memory",
        "approved_lesson",
        "evidence",
        "session_instruction",
    }
)
CONTEXT_SOURCE_KINDS = frozenset(
    {"memory_record", "evidence", "governance_rule"}
)
UNCERTAINTY_IMPACTS = frozenset({"low", "medium", "high", "blocking"})
SESSION_TASK_CREATION_PRINCIPALS = frozenset(
    {"operator", "codex_development_harness"}
)
TASK_MEMORY_MODES = frozenset({"active", "historical"})
TASK_MEMORY_REASON_ORDER = (
    "wrong_task",
    "wrong_session",
    "wrong_project",
    "task_not_active",
    "session_not_open",
    "historical_mode_required",
    "context_not_finalized",
    "source_missing",
    "source_not_task_bound",
    "source_hash_mismatch",
    "source_integrity_invalid",
    "source_not_active",
    "source_not_approved",
    "source_superseded",
    "source_revoked",
    "source_deleted",
    "lesson_candidate_prohibited",
    "controlled_resilience_prohibited",
    "sensitivity_denied",
    "privacy_denied",
)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be non-empty")
    return value


def _enum(value: object, accepted: frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in accepted:
        raise ValidationError(f"{field} is invalid")
    return value


def _sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValidationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _principal(value: object, field: str) -> str:
    return _enum(value, SESSION_TASK_CREATION_PRINCIPALS, field)


@dataclass(frozen=True, slots=True)
class TypedSourceReference:
    """One database-enforceable source identity with no polymorphic text key."""

    memory_record_id: str | None = None
    evidence_id: str | None = None
    governance_rule_id: str | None = None

    def __post_init__(self) -> None:
        supplied = tuple(
            value
            for value in (
                self.memory_record_id,
                self.evidence_id,
                self.governance_rule_id,
            )
            if value is not None
        )
        if len(supplied) != 1:
            raise ValidationError("typed source requires exactly one identifier")
        for field in (
            "memory_record_id",
            "evidence_id",
            "governance_rule_id",
        ):
            value = getattr(self, field)
            if value is not None:
                validate_identifier(value, field=field)

    @property
    def source_kind(self) -> str:
        if self.memory_record_id is not None:
            return "memory_record"
        if self.evidence_id is not None:
            return "evidence"
        return "governance_rule"

    @property
    def source_id(self) -> str:
        return (
            self.memory_record_id
            or self.evidence_id
            or self.governance_rule_id
            or ""
        )

    def canonical_value(self) -> dict[str, str]:
        return {
            "source_kind": self.source_kind,
            {
                "memory_record": "memory_record_id",
                "evidence": "evidence_id",
                "governance_rule": "governance_rule_id",
            }[self.source_kind]: self.source_id,
        }


@dataclass(frozen=True, slots=True)
class TaskContextItem:
    context_item_id: str
    task_id: str
    session_id: str
    project_scope_id: str
    context_kind: str
    source: TypedSourceReference
    injection_order: int
    required: bool
    content_hash: str
    created_at: str
    created_by_principal: str

    def __post_init__(self) -> None:
        for field in (
            "context_item_id",
            "task_id",
            "session_id",
            "project_scope_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        _enum(self.context_kind, CONTEXT_KINDS, "context_kind")
        if not isinstance(self.source, TypedSourceReference):
            raise ValidationError("source must be a TypedSourceReference")
        expected_source = {
            "constitution": "governance_rule",
            "policy": "governance_rule",
            "construct_memory": "memory_record",
            "approved_lesson": "memory_record",
            "evidence": "evidence",
            "session_instruction": "evidence",
        }[self.context_kind]
        if self.source.source_kind != expected_source:
            raise ValidationError(
                f"{self.context_kind} requires source_kind={expected_source!r}"
            )
        if (
            not isinstance(self.injection_order, int)
            or isinstance(self.injection_order, bool)
            or self.injection_order < 0
        ):
            raise ValidationError("injection_order must be a non-negative integer")
        if not isinstance(self.required, bool):
            raise ValidationError("required must be boolean")
        _sha256(self.content_hash, "content_hash")
        parse_canonical_utc(self.created_at, field="created_at")
        _principal(self.created_by_principal, "created_by_principal")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "content_hash": self.content_hash,
            "context_item_id": self.context_item_id,
            "context_kind": self.context_kind,
            "created_at": self.created_at,
            "created_by_principal": self.created_by_principal,
            "injection_order": self.injection_order,
            "project_scope_id": self.project_scope_id,
            "required": self.required,
            "session_id": self.session_id,
            "source": self.source.canonical_value(),
            "task_id": self.task_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def canonical_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class TaskContextFinalization:
    finalization_id: str
    task_id: str
    session_id: str
    project_scope_id: str
    ordered_item_ids: tuple[str, ...]
    ordered_item_hashes: tuple[str, ...]
    finalized_at: str
    finalized_by_principal: str

    def __post_init__(self) -> None:
        for field in (
            "finalization_id",
            "task_id",
            "session_id",
            "project_scope_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        if not self.ordered_item_ids:
            raise ValidationError("finalized task context cannot be empty")
        if len(set(self.ordered_item_ids)) != len(self.ordered_item_ids):
            raise ValidationError("ordered_item_ids cannot contain duplicates")
        for item_id in self.ordered_item_ids:
            validate_identifier(item_id, field="ordered_item_id")
        if len(self.ordered_item_hashes) != len(self.ordered_item_ids):
            raise ValidationError("ordered item identifiers and hashes differ")
        for digest in self.ordered_item_hashes:
            _sha256(digest, "ordered_item_hash")
        parse_canonical_utc(self.finalized_at, field="finalized_at")
        _principal(self.finalized_by_principal, "finalized_by_principal")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "finalization_id": self.finalization_id,
            "finalized_at": self.finalized_at,
            "finalized_by_principal": self.finalized_by_principal,
            "ordered_items": [
                {"canonical_hash": digest, "context_item_id": item_id}
                for item_id, digest in zip(
                    self.ordered_item_ids,
                    self.ordered_item_hashes,
                    strict=True,
                )
            ],
            "project_scope_id": self.project_scope_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class ActiveUncertaintyPayload:
    record_id: str
    task_id: str
    session_id: str
    project_scope_id: str
    uncertainty_statement: str
    impact: str
    resolution_required: bool
    created_at: str
    created_by_principal: str

    RECORD_TYPE = "active_uncertainty"

    def __post_init__(self) -> None:
        for field in (
            "record_id",
            "task_id",
            "session_id",
            "project_scope_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        _text(self.uncertainty_statement, "uncertainty_statement")
        _enum(self.impact, UNCERTAINTY_IMPACTS, "impact")
        if not isinstance(self.resolution_required, bool):
            raise ValidationError("resolution_required must be boolean")
        if self.impact == "blocking" and not self.resolution_required:
            raise ValidationError("blocking uncertainty requires resolution")
        parse_canonical_utc(self.created_at, field="created_at")
        _principal(self.created_by_principal, "created_by_principal")

    def canonical_content(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "created_by_principal": self.created_by_principal,
            "impact": self.impact,
            "project_scope_id": self.project_scope_id,
            "record_id": self.record_id,
            "resolution_required": self.resolution_required,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "uncertainty_statement": self.uncertainty_statement,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_content())


def validate_active_uncertainty_pair(
    envelope: RecordEnvelope,
    payload: ActiveUncertaintyPayload,
    *,
    for_creation: bool = True,
) -> None:
    if not isinstance(payload, ActiveUncertaintyPayload):
        raise TypeError("payload must be an ActiveUncertaintyPayload")
    if envelope.record_id != payload.record_id:
        raise ValidationError("uncertainty payload and envelope identifiers differ")
    if (
        envelope.record_family != "session_task_memory"
        or envelope.record_type != payload.RECORD_TYPE
    ):
        raise ValidationError("active uncertainty requires its registered record type")
    if (
        envelope.task_id != payload.task_id
        or envelope.session_id != payload.session_id
        or envelope.project_scope_id != payload.project_scope_id
    ):
        raise ValidationError(
            "uncertainty envelope must exactly match task, session and project"
        )
    if envelope.created_at != payload.created_at:
        raise ValidationError("uncertainty creation timestamps must match")
    if envelope.agent_write_policy != "candidate_only":
        raise ValidationError("active uncertainty requires candidate_only policy")
    if envelope.integrity_status != "valid":
        raise ValidationError("active uncertainty requires valid integrity")
    if envelope.sensitivity_class not in {"public", "internal"}:
        raise ValidationError(
            "active uncertainty ordinary memory must be public or internal"
        )
    if envelope.privacy_class != "none":
        raise ValidationError("active uncertainty requires privacy_class='none'")
    if envelope.training_eligibility == "approved":
        raise ValidationError("uncertainty cannot be training-approved at creation")
    if for_creation and (
        envelope.lifecycle_state != "observed"
        or envelope.approval_status != "not_required"
    ):
        raise ValidationError(
            "active uncertainty must begin observed and approval-not-required"
        )


def active_uncertainty_content_hash(
    envelope: RecordEnvelope,
    payload: ActiveUncertaintyPayload,
) -> str:
    validate_active_uncertainty_pair(envelope, payload, for_creation=False)
    return sha256_canonical_json(
        {
            "envelope": envelope.hash_material(),
            "payload": payload.canonical_content(),
            "payload_type": payload.RECORD_TYPE,
        }
    )


@dataclass(frozen=True, slots=True)
class UncertaintyResolution:
    resolution_id: str
    uncertainty_record_id: str
    task_id: str
    session_id: str
    project_scope_id: str
    source: TypedSourceReference
    source_content_hash: str
    resolved_at: str
    created_by_principal: str

    def __post_init__(self) -> None:
        for field in (
            "resolution_id",
            "uncertainty_record_id",
            "task_id",
            "session_id",
            "project_scope_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        if not isinstance(self.source, TypedSourceReference):
            raise ValidationError("source must be a TypedSourceReference")
        if self.source.source_kind == "governance_rule":
            raise ValidationError(
                "uncertainty resolution requires evidence or a governed record"
            )
        _sha256(self.source_content_hash, "source_content_hash")
        parse_canonical_utc(self.resolved_at, field="resolved_at")
        _principal(self.created_by_principal, "created_by_principal")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "created_by_principal": self.created_by_principal,
            "project_scope_id": self.project_scope_id,
            "resolution_id": self.resolution_id,
            "resolved_at": self.resolved_at,
            "session_id": self.session_id,
            "source": self.source.canonical_value(),
            "source_content_hash": self.source_content_hash,
            "task_id": self.task_id,
            "uncertainty_record_id": self.uncertainty_record_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class TaskMemoryEligibilityDecision:
    context_item_id: str
    task_id: str
    mode: str
    eligible: bool
    reason_codes: tuple[str, ...]
    evaluated_at: str
    decision_hash: str

    def __post_init__(self) -> None:
        validate_identifier(self.context_item_id, field="context_item_id")
        validate_identifier(self.task_id, field="task_id")
        _enum(self.mode, TASK_MEMORY_MODES, "mode")
        parse_canonical_utc(self.evaluated_at, field="evaluated_at")
        unknown = set(self.reason_codes) - set(TASK_MEMORY_REASON_ORDER)
        if unknown:
            raise ValidationError(
                f"unknown task-memory eligibility reasons: {sorted(unknown)!r}"
            )
        if self.eligible == bool(self.reason_codes):
            raise ValidationError(
                "eligibility and task-memory exclusion reasons conflict"
            )
        _sha256(self.decision_hash, "decision_hash")
