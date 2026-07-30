"""Pure deterministic decoding, parsing, validation, and task semantics."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_canonical_json

from .contracts import OutputProcessingResult, ValidationIssue
from .schemas import validate_apprentice_response

_RESPONSE_SUFFICIENT_TASK_TYPES = frozenset(
    {
        "i4b_bounded_response",
        "i4b_bounded_response_with_recommendations",
    }
)
_HUMAN_REVIEW_TASK_TYPES = frozenset(
    {
        "i4b_bounded_response_human_review",
        "i4b_bounded_response_with_recommendations_human_review",
    }
)
_RECOMMENDATION_TASK_TYPES = frozenset(
    {
        "i4b_bounded_response_with_recommendations",
        "i4b_bounded_response_with_recommendations_human_review",
    }
)
_CAPABILITY_REQUEST = re.compile(
    r"\b(?:access|call|connect|delete|execute|invoke|open|query|read|run|send|"
    r"use|write)\b.{0,48}\b(?:api|callback|command|communication|credential|"
    r"database|email|endpoint|executable|file|filesystem|function|message|"
    r"network|password|process|repository|shell|socket|sql|token|tool)\b",
    re.IGNORECASE | re.DOTALL,
)
_PATH_CAPABILITY_REQUEST = re.compile(
    r"\b(?:delete|open|read|write)\b.{0,32}"
    r"(?:[a-zA-Z]:[\\/]|\\\\[a-zA-Z0-9._-]+[\\/]|/[a-zA-Z0-9._-]+(?:/|\b))",
    re.IGNORECASE | re.DOTALL,
)
_NETWORK_CAPABILITY_REQUEST = re.compile(
    r"\b(?:access|call|connect|open|query|read|send|use|write)\b.{0,48}"
    r"(?:https?://|wss?://)",
    re.IGNORECASE | re.DOTALL,
)
_SQL_STATEMENT = re.compile(
    r"\b(?:alter\s+table|attach\s+database|create\s+(?:index|table|trigger|view)|"
    r"delete\s+from|detach\s+database|drop\s+(?:index|table|trigger|view)|"
    r"insert\s+into|pragma\b|reindex\b|replace\s+into|select\b.+\bfrom|"
    r"update\b.+\bset|vacuum\b)\b",
    re.IGNORECASE | re.DOTALL,
)


def _issue(path: str, code: str, detail: str) -> ValidationIssue:
    return ValidationIssue(path=path, code=code, detail=detail)


def _semantic_errors(
    value: Mapping[str, Any],
    *,
    task_id: str,
    task_section: Mapping[str, Any],
    allowed_memory_ids: frozenset[str],
    allowed_evidence_ids: frozenset[str],
) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    if value["task_id"] != task_id:
        issues.append(
            _issue(
                "$.task_id",
                "task_binding_mismatch",
                "response task_id differs from the invocation task",
            )
        )
    if value["stop_requested"] and not (
        isinstance(value["stop_reason"], str)
        and value["stop_reason"].strip()
    ):
        issues.append(
            _issue(
                "$.stop_reason",
                "stop_reason_required",
                "a requested stop requires a non-empty stop reason",
            )
        )
    if value["stop_requested"]:
        issues.append(
            _issue(
                "$.stop_requested",
                "stop_request_not_permitted",
                "a successful I4-B version 1.0 response must not request a stop",
            )
        )
    if not value["stop_requested"] and value["stop_reason"] is not None:
        issues.append(
            _issue(
                "$.stop_reason",
                "unexpected_stop_reason",
                "stop_reason must be null when no stop is requested",
            )
        )
    for index, identifier in enumerate(value["memory_used"]):
        if identifier not in allowed_memory_ids:
            issues.append(
                _issue(
                    f"$.memory_used[{index}]",
                    "unbound_memory_reference",
                    "response references memory absent from the exact context",
                )
            )
    for index, identifier in enumerate(value["evidence_used"]):
        if identifier not in allowed_evidence_ids:
            issues.append(
                _issue(
                    f"$.evidence_used[{index}]",
                    "unbound_evidence_reference",
                    "response references evidence absent from the exact context",
                )
            )
    prohibited = task_section.get("prohibited_actions", [])
    recommendation_prohibited = (
        isinstance(prohibited, list)
        and any(
            isinstance(item, str) and "recommend" in item.lower()
            for item in prohibited
        )
    )
    if value["recommendations"] and (
        task_section.get("task_type") not in _RECOMMENDATION_TASK_TYPES
        or recommendation_prohibited
    ):
        issues.append(
            _issue(
                "$.recommendations",
                "recommendations_not_authorized",
                "the deterministic task contract does not permit recommendations",
            )
        )
    for field in (
        "observations",
        "inferences",
        "uncertainties",
        "recommendations",
    ):
        for index, text in enumerate(value[field]):
            if (
                _CAPABILITY_REQUEST.search(text)
                or _PATH_CAPABILITY_REQUEST.search(text)
                or _NETWORK_CAPABILITY_REQUEST.search(text)
                or _SQL_STATEMENT.search(text)
                or "sk-" in text.lower()
                or "bearer " in text.lower()
            ):
                issues.append(
                    _issue(
                        f"$.{field}[{index}]",
                        "prohibited_capability_request",
                        "response contains a prohibited capability or credential request",
                    )
                )
    return tuple(sorted(set(issues)))


def process_raw_output(
    raw_bytes: bytes,
    *,
    declared_encoding: str,
    task_id: str,
    task_section: Mapping[str, Any],
    allowed_memory_ids: frozenset[str],
    allowed_evidence_ids: frozenset[str],
) -> OutputProcessingResult:
    """Process preserved bytes as total deterministic data, never exceptions."""

    if not isinstance(raw_bytes, bytes):
        raise TypeError("raw_bytes must be immutable bytes")
    if not isinstance(declared_encoding, str) or not declared_encoding:
        raise ValidationError("declared_encoding must be non-empty text")
    try:
        decoded = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return OutputProcessingResult(
            utf8_decode_status="undecodable",
            decoded_text=None,
            decode_errors=(
                _issue(
                    "$",
                    "invalid_utf8",
                    "raw provider output is not valid UTF-8",
                ),
            ),
            parse_status="not_attempted",
            parse_errors=(),
            parsed_canonical_json=None,
            parsed_output_hash=None,
            schema_status="not_attempted",
            schema_errors=(),
            semantic_status="not_attempted",
            semantic_errors=(),
        )

    try:
        parsed = parse_json(decoded)
    except ValidationError:
        return OutputProcessingResult(
            utf8_decode_status="decoded",
            decoded_text=decoded,
            decode_errors=(),
            parse_status="malformed_json",
            parse_errors=(
                _issue(
                    "$",
                    "malformed_json",
                    "decoded provider output is not valid strict JSON",
                ),
            ),
            parsed_canonical_json=None,
            parsed_output_hash=None,
            schema_status="not_attempted",
            schema_errors=(),
            semantic_status="not_attempted",
            semantic_errors=(),
        )

    parsed_json = canonical_json_text(parsed)
    schema_errors = list(validate_apprentice_response(parsed))
    if declared_encoding != "utf-8":
        schema_errors.append(
            _issue(
                "$",
                "unsupported_declared_encoding",
                "I4-B provider output must declare utf-8 exactly",
            )
        )
    ordered_schema_errors = tuple(sorted(set(schema_errors)))
    if ordered_schema_errors:
        return OutputProcessingResult(
            utf8_decode_status="decoded",
            decoded_text=decoded,
            decode_errors=(),
            parse_status="parsed",
            parse_errors=(),
            parsed_canonical_json=parsed_json,
            parsed_output_hash=sha256_canonical_json(parsed),
            schema_status="invalid",
            schema_errors=ordered_schema_errors,
            semantic_status="not_attempted",
            semantic_errors=(),
        )

    semantic_errors = _semantic_errors(
        parsed,
        task_id=task_id,
        task_section=task_section,
        allowed_memory_ids=allowed_memory_ids,
        allowed_evidence_ids=allowed_evidence_ids,
    )
    return OutputProcessingResult(
        utf8_decode_status="decoded",
        decoded_text=decoded,
        decode_errors=(),
        parse_status="parsed",
        parse_errors=(),
        parsed_canonical_json=parsed_json,
        parsed_output_hash=sha256_canonical_json(parsed),
        schema_status="valid",
        schema_errors=(),
        semantic_status="invalid" if semantic_errors else "valid",
        semantic_errors=semantic_errors,
    )


def task_completion_disposition(
    *,
    task_section: Mapping[str, Any],
    response_value: Mapping[str, Any],
) -> str:
    """Return the bounded I2 disposition; never infer truth or approval."""

    task_type = task_section.get("task_type")
    if task_type in _HUMAN_REVIEW_TASK_TYPES:
        return "deferred_human_review"
    if (
        task_type in _RESPONSE_SUFFICIENT_TASK_TYPES
        and response_value.get("status") == "completed"
    ):
        return "completed"
    return "not_applicable"
