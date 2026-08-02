"""Closed protocol-schema registry and deterministic response validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.identifiers import validate_identifier

from .contracts import (
    APPRENTICE_RESPONSE_PROTOCOL,
    APPRENTICE_RESPONSE_PROTOCOL_VERSION,
    ValidationIssue,
)

MODEL_INPUT_SCHEMA_ID = (
    "https://batch87.local/schemas/protocols/model-input/1.0.0"
)
MODEL_INPUT_SCHEMA_HASH = (
    "d3eecaaa715c7f9c83550bc0a4b3c1c76fa43bafbd760582c11a96c57e0a7656"
)
APPRENTICE_RESPONSE_SCHEMA_ID = (
    "https://batch87.local/schemas/protocols/apprentice-response/1.0.0"
)
APPRENTICE_RESPONSE_SCHEMA_HASH = (
    "52a262ffee70fcdeeacf8a20639f8d52fcc7b666e1ec4ec86e400e682bba4a91"
)

_RESPONSE_FIELDS = frozenset(
    {
        "evidence_used",
        "inferences",
        "memory_used",
        "observations",
        "protocol",
        "protocol_version",
        "recommendations",
        "status",
        "stop_reason",
        "stop_requested",
        "task_id",
        "uncertainties",
    }
)
_TEXT_ARRAY_FIELDS = (
    "inferences",
    "observations",
    "recommendations",
    "uncertainties",
)
_IDENTIFIER_ARRAY_FIELDS = ("evidence_used", "memory_used")


@dataclass(frozen=True, slots=True)
class RegisteredSchema:
    schema_id: str
    content_hash: str
    version: str
    purpose: str


_SCHEMAS = {
    MODEL_INPUT_SCHEMA_ID: RegisteredSchema(
        schema_id=MODEL_INPUT_SCHEMA_ID,
        content_hash=MODEL_INPUT_SCHEMA_HASH,
        version="1.0.0",
        purpose="model_input",
    ),
    APPRENTICE_RESPONSE_SCHEMA_ID: RegisteredSchema(
        schema_id=APPRENTICE_RESPONSE_SCHEMA_ID,
        content_hash=APPRENTICE_RESPONSE_SCHEMA_HASH,
        version="1.0.0",
        purpose="apprentice_response",
    ),
}


def resolve_schema(schema_id: str, content_hash: str) -> RegisteredSchema:
    """Resolve one exact repository-owned schema identity and hash."""

    if not isinstance(schema_id, str) or not isinstance(content_hash, str):
        raise ValidationError("schema identity and hash must be text")
    schema = _SCHEMAS.get(schema_id)
    if schema is None or schema.content_hash != content_hash:
        raise ValidationError("schema identity or content hash is not registered")
    return schema


def resolve_response_schema(
    schema_id: str,
    content_hash: str,
) -> RegisteredSchema:
    schema = resolve_schema(schema_id, content_hash)
    if schema.purpose != "apprentice_response":
        raise ValidationError("output schema is not an apprentice response schema")
    return schema


def _issue(path: str, code: str, detail: str) -> ValidationIssue:
    return ValidationIssue(path=path, code=code, detail=detail)


def _validate_text_array(
    value: Mapping[str, Any],
    field: str,
) -> list[ValidationIssue]:
    candidate = value.get(field)
    path = f"$.{field}"
    if not isinstance(candidate, list):
        return [_issue(path, "invalid_type", f"{field} must be an array")]
    issues: list[ValidationIssue] = []
    for index, item in enumerate(candidate):
        if not isinstance(item, str) or not item.strip():
            issues.append(
                _issue(
                    f"{path}[{index}]",
                    "invalid_text",
                    f"{field} entries must be non-empty text",
                )
            )
    return issues


def _validate_identifier_array(
    value: Mapping[str, Any],
    field: str,
) -> list[ValidationIssue]:
    candidate = value.get(field)
    path = f"$.{field}"
    if not isinstance(candidate, list):
        return [_issue(path, "invalid_type", f"{field} must be an array")]
    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    for index, item in enumerate(candidate):
        try:
            validate_identifier(item, field=field)
        except ValidationError:
            issues.append(
                _issue(
                    f"{path}[{index}]",
                    "invalid_identifier",
                    f"{field} entries must be canonical UUIDv4 or UUIDv7 values",
                )
            )
            continue
        if item in seen:
            issues.append(
                _issue(
                    f"{path}[{index}]",
                    "duplicate_identifier",
                    f"{field} entries must be unique",
                )
            )
        seen.add(item)
    return issues


def validate_apprentice_response(value: object) -> tuple[ValidationIssue, ...]:
    """Validate the exact closed response shape without repair or coercion."""

    if not isinstance(value, Mapping):
        return (
            _issue("$", "invalid_type", "response must be a JSON object"),
        )
    issues: list[ValidationIssue] = []
    actual = set(value)
    for field in sorted(_RESPONSE_FIELDS - actual):
        issues.append(
            _issue(
                f"$.{field}",
                "missing_field",
                f"required response field is missing: {field}",
            )
        )
    for field in sorted(actual - _RESPONSE_FIELDS):
        issues.append(
            _issue(
                f"$.{field}",
                "unknown_field",
                f"response field is not permitted: {field}",
            )
        )

    if "protocol" in value and value["protocol"] != APPRENTICE_RESPONSE_PROTOCOL:
        issues.append(
            _issue(
                "$.protocol",
                "invalid_constant",
                "response protocol is not batch87.apprentice-response",
            )
        )
    if (
        "protocol_version" in value
        and value["protocol_version"] != APPRENTICE_RESPONSE_PROTOCOL_VERSION
    ):
        issues.append(
            _issue(
                "$.protocol_version",
                "invalid_constant",
                "response protocol version is not 1.0.0",
            )
        )
    if "task_id" in value:
        try:
            validate_identifier(value["task_id"], field="task_id")
        except ValidationError:
            issues.append(
                _issue(
                    "$.task_id",
                    "invalid_identifier",
                    "task_id must be a canonical UUIDv4 or UUIDv7",
                )
            )
    if "status" in value:
        if not isinstance(value["status"], str):
            issues.append(
                _issue(
                    "$.status",
                    "invalid_type",
                    "status must be text",
                )
            )
        elif value["status"] not in {
            "completed",
            "partial",
            "unable",
        }:
            issues.append(
                _issue(
                    "$.status",
                    "invalid_enum",
                    "status must be completed, partial, or unable",
                )
            )
    if "stop_requested" in value and not isinstance(
        value["stop_requested"],
        bool,
    ):
        issues.append(
            _issue(
                "$.stop_requested",
                "invalid_type",
                "stop_requested must be boolean",
            )
        )
    if "stop_reason" in value and not (
        value["stop_reason"] is None
        or isinstance(value["stop_reason"], str)
    ):
        issues.append(
            _issue(
                "$.stop_reason",
                "invalid_type",
                "stop_reason must be text or null",
            )
        )
    for field in _TEXT_ARRAY_FIELDS:
        if field in value:
            issues.extend(_validate_text_array(value, field))
    for field in _IDENTIFIER_ARRAY_FIELDS:
        if field in value:
            issues.extend(_validate_identifier_array(value, field))
    return tuple(sorted(set(issues)))
