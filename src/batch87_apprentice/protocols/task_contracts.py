"""Explicit, versioned protocol contracts for the B87-I2 task boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc

TASK_CONTRACT_VERSION = "1.0.0"
TASK_CONTRACT_SCHEMA_ID = (
    "https://batch87.local/schemas/protocols/task-contract/1.0.0"
)
SESSION_CONTRACT_VERSION = "1.0.0"

EXECUTION_PRINCIPALS = frozenset(
    {
        "apprentice",
        "operator",
        "codex_development_harness",
        "experimental_harness",
    }
)
ACTION_CLASSES = frozenset(
    {"observe", "analyse", "propose", "execute", "ambiguous"}
)
AUTHORITY_GRANT_CLASSES = frozenset(
    {"observe", "analyse", "propose", "execute"}
)
SESSION_STATUSES = frozenset({"open", "paused", "closed", "aborted"})
RETENTION_DISPOSITIONS = frozenset(
    {"delete", "archive_summary", "retain_restricted"}
)
POLICY_VIOLATION_CODES = frozenset(
    {"context_policy_violation", "integrity_violation"}
)

_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")
_TASK_FIELDS = frozenset(
    {
        "contract_version",
        "task_id",
        "session_id",
        "project_scope_id",
        "requested_scope_id",
        "objective",
        "task_type",
        "requested_operation",
        "requesting_principal",
        "authority_grant",
        "claimed_authority_ids",
        "claimed_human_approval_ids",
        "effective_at",
        "governing_constraints",
        "required_evidence_ids",
        "allowed_sources",
        "prohibited_actions",
        "expected_output_schema_id",
        "stop_conditions",
        "provenance",
    }
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


def _enum(value: object, accepted: frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in accepted:
        raise ValidationError(f"{field} has an unsupported value: {value!r}")
    return value


def _string_tuple(
    value: object,
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValidationError(f"{field} must be an immutable tuple of text values")
    result = tuple(_text(item, f"{field} item") for item in value)
    if not allow_empty and not result:
        raise ValidationError(f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise ValidationError(f"{field} must not contain duplicates")
    return result


def _identifier_tuple(
    value: object,
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    result = _string_tuple(value, field, allow_empty=allow_empty)
    for item in result:
        validate_identifier(item, field=f"{field} item")
    return result


def _mapping_string_tuple(
    value: object,
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be a JSON array")
    return _string_tuple(tuple(value), field, allow_empty=allow_empty)


def _mapping_identifier_tuple(
    value: object,
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    return _identifier_tuple(
        _mapping_string_tuple(value, field, allow_empty=allow_empty),
        field,
        allow_empty=allow_empty,
    )


def _canonical_object_text(value: object, field: str) -> str:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{field} must be an object")
    return canonical_json_text(dict(value))


@dataclass(frozen=True, slots=True)
class RequestedOperation:
    """A caller-supplied operation classification, never a semantic guess."""

    name: str
    action_class: str
    autonomous: bool = False

    def __post_init__(self) -> None:
        _token(self.name, "requested_operation.name")
        _enum(
            self.action_class,
            ACTION_CLASSES,
            "requested_operation.action_class",
        )
        if not isinstance(self.autonomous, bool):
            raise ValidationError("requested_operation.autonomous must be boolean")
        if self.autonomous and self.action_class != "execute":
            raise ValidationError(
                "autonomous operations must use action_class='execute'"
            )

    @classmethod
    def from_mapping(cls, value: object) -> RequestedOperation:
        if not isinstance(value, Mapping):
            raise ValidationError("requested_operation must be an object")
        if set(value) != {"name", "action_class", "autonomous"}:
            raise ValidationError(
                "requested_operation has missing or unsupported fields"
            )
        return cls(
            name=value["name"],
            action_class=value["action_class"],
            autonomous=value["autonomous"],
        )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "action_class": self.action_class,
            "autonomous": self.autonomous,
            "name": self.name,
        }

    @property
    def permission_class(self) -> str:
        return "execute" if self.autonomous else self.action_class


@dataclass(frozen=True, slots=True)
class SessionContract:
    """The explicit persisted identity and scope of one bounded session."""

    session_id: str
    purpose: str
    project_scope_id: str
    opened_at: str
    created_by_entity_id: str
    participant_entity_ids: tuple[str, ...]
    status: str = "open"
    retention_disposition: str = "retain_restricted"
    closed_at: str | None = None
    contract_version: str = SESSION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != SESSION_CONTRACT_VERSION:
            raise ValidationError(
                f"unsupported session contract version: {self.contract_version!r}"
            )
        validate_identifier(self.session_id, field="session_id")
        validate_identifier(self.project_scope_id, field="project_scope_id")
        validate_identifier(
            self.created_by_entity_id,
            field="created_by_entity_id",
        )
        _text(self.purpose, "purpose")
        parse_canonical_utc(self.opened_at, field="opened_at")
        _enum(self.status, SESSION_STATUSES, "session status")
        if self.closed_at is not None:
            parse_canonical_utc(self.closed_at, field="closed_at")
            if self.closed_at < self.opened_at:
                raise ValidationError("closed_at cannot precede opened_at")
        if self.status in {"closed", "aborted"} and self.closed_at is None:
            raise ValidationError("terminal sessions require closed_at")
        if self.status in {"open", "paused"} and self.closed_at is not None:
            raise ValidationError("non-terminal sessions cannot have closed_at")
        _enum(
            self.retention_disposition,
            RETENTION_DISPOSITIONS,
            "retention_disposition",
        )
        participants = _identifier_tuple(
            self.participant_entity_ids,
            "participant_entity_ids",
            allow_empty=False,
        )
        if self.created_by_entity_id not in participants:
            raise ValidationError(
                "session creator must be an explicit participant"
            )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "closed_at": self.closed_at,
            "created_by_entity_id": self.created_by_entity_id,
            "opened_at": self.opened_at,
            "participant_entity_ids": list(self.participant_entity_ids),
            "project_scope_id": self.project_scope_id,
            "purpose": self.purpose,
            "retention_disposition": self.retention_disposition,
            "session_id": self.session_id,
            "status": self.status,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class TaskContract:
    """The complete deterministic input to one governed I2 task decision."""

    contract_version: str
    task_id: str
    session_id: str
    project_scope_id: str
    requested_scope_id: str
    objective: str
    task_type: str
    requested_operation: RequestedOperation
    requesting_principal: str
    authority_grant: tuple[str, ...]
    claimed_authority_ids: tuple[str, ...]
    claimed_human_approval_ids: tuple[str, ...]
    effective_at: str
    governing_constraints: tuple[str, ...]
    required_evidence_ids: tuple[str, ...]
    allowed_sources: tuple[str, ...]
    prohibited_actions: tuple[str, ...]
    expected_output_schema_id: str
    stop_conditions: tuple[str, ...]
    provenance_json: str

    def __post_init__(self) -> None:
        if self.contract_version != TASK_CONTRACT_VERSION:
            raise ValidationError(
                f"unsupported task contract version: {self.contract_version!r}"
            )
        for field in (
            "task_id",
            "session_id",
            "project_scope_id",
            "requested_scope_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        _text(self.objective, "objective")
        _token(self.task_type, "task_type")
        if not isinstance(self.requested_operation, RequestedOperation):
            raise ValidationError(
                "requested_operation must be a RequestedOperation"
            )
        _enum(
            self.requesting_principal,
            EXECUTION_PRINCIPALS,
            "requesting_principal",
        )
        grants = _string_tuple(
            self.authority_grant,
            "authority_grant",
            allow_empty=True,
        )
        for grant in grants:
            _enum(grant, AUTHORITY_GRANT_CLASSES, "authority_grant item")
        _identifier_tuple(
            self.claimed_authority_ids,
            "claimed_authority_ids",
            allow_empty=True,
        )
        _identifier_tuple(
            self.claimed_human_approval_ids,
            "claimed_human_approval_ids",
            allow_empty=True,
        )
        parse_canonical_utc(self.effective_at, field="effective_at")
        _string_tuple(
            self.governing_constraints,
            "governing_constraints",
            allow_empty=False,
        )
        _identifier_tuple(
            self.required_evidence_ids,
            "required_evidence_ids",
            allow_empty=True,
        )
        _string_tuple(self.allowed_sources, "allowed_sources", allow_empty=True)
        _string_tuple(
            self.prohibited_actions,
            "prohibited_actions",
            allow_empty=False,
        )
        _text(self.expected_output_schema_id, "expected_output_schema_id")
        _string_tuple(
            self.stop_conditions,
            "stop_conditions",
            allow_empty=False,
        )
        provenance = parse_json(self.provenance_json)
        if (
            not isinstance(provenance, dict)
            or not provenance
            or canonical_json_text(provenance) != self.provenance_json
        ):
            raise ValidationError(
                "provenance_json must be a non-empty canonical JSON object"
            )

    @classmethod
    def from_mapping(cls, value: object) -> TaskContract:
        """Validate an untrusted JSON-shaped value without model interpretation."""

        if not isinstance(value, Mapping):
            raise ValidationError("task contract must be an object")
        fields = set(value)
        missing = sorted(_TASK_FIELDS - fields)
        unsupported = sorted(fields - _TASK_FIELDS)
        if missing or unsupported:
            details: list[str] = []
            if missing:
                details.append("missing=" + ",".join(missing))
            if unsupported:
                details.append("unsupported=" + ",".join(unsupported))
            raise ValidationError(
                "task contract fields are invalid: " + "; ".join(details)
            )
        return cls(
            contract_version=value["contract_version"],
            task_id=value["task_id"],
            session_id=value["session_id"],
            project_scope_id=value["project_scope_id"],
            requested_scope_id=value["requested_scope_id"],
            objective=value["objective"],
            task_type=value["task_type"],
            requested_operation=RequestedOperation.from_mapping(
                value["requested_operation"]
            ),
            requesting_principal=value["requesting_principal"],
            authority_grant=_mapping_string_tuple(
                value["authority_grant"],
                "authority_grant",
            ),
            claimed_authority_ids=_mapping_identifier_tuple(
                value["claimed_authority_ids"],
                "claimed_authority_ids",
            ),
            claimed_human_approval_ids=_mapping_identifier_tuple(
                value["claimed_human_approval_ids"],
                "claimed_human_approval_ids",
            ),
            effective_at=value["effective_at"],
            governing_constraints=_mapping_string_tuple(
                value["governing_constraints"],
                "governing_constraints",
                allow_empty=False,
            ),
            required_evidence_ids=_mapping_identifier_tuple(
                value["required_evidence_ids"],
                "required_evidence_ids",
            ),
            allowed_sources=_mapping_string_tuple(
                value["allowed_sources"],
                "allowed_sources",
            ),
            prohibited_actions=_mapping_string_tuple(
                value["prohibited_actions"],
                "prohibited_actions",
                allow_empty=False,
            ),
            expected_output_schema_id=value["expected_output_schema_id"],
            stop_conditions=_mapping_string_tuple(
                value["stop_conditions"],
                "stop_conditions",
                allow_empty=False,
            ),
            provenance_json=_canonical_object_text(
                value["provenance"],
                "provenance",
            ),
        )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "allowed_sources": list(self.allowed_sources),
            "authority_grant": list(self.authority_grant),
            "claimed_authority_ids": list(self.claimed_authority_ids),
            "claimed_human_approval_ids": list(
                self.claimed_human_approval_ids
            ),
            "contract_version": self.contract_version,
            "effective_at": self.effective_at,
            "expected_output_schema_id": self.expected_output_schema_id,
            "governing_constraints": list(self.governing_constraints),
            "objective": self.objective,
            "prohibited_actions": list(self.prohibited_actions),
            "project_scope_id": self.project_scope_id,
            "provenance": parse_json(self.provenance_json),
            "requested_operation": self.requested_operation.canonical_value(),
            "requested_scope_id": self.requested_scope_id,
            "requesting_principal": self.requesting_principal,
            "required_evidence_ids": list(self.required_evidence_ids),
            "session_id": self.session_id,
            "stop_conditions": list(self.stop_conditions),
            "task_id": self.task_id,
            "task_type": self.task_type,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    """An observable deterministic policy signal supplied to I2."""

    code: str
    source: str
    detail: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _enum(self.code, POLICY_VIOLATION_CODES, "policy violation code")
        _token(self.source, "policy violation source")
        _text(self.detail, "policy violation detail")
        _identifier_tuple(
            self.evidence_ids,
            "policy violation evidence_ids",
            allow_empty=True,
        )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "detail": self.detail,
            "evidence_ids": list(self.evidence_ids),
            "source": self.source,
        }
