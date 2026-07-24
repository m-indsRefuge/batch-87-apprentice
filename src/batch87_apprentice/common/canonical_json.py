"""Canonical JSON encoding for deterministic hashes and stored payloads."""

from __future__ import annotations

import json
from typing import Any, Never

from .errors import ValidationError


def _reject_non_finite(value: str) -> Never:
    raise ValidationError(f"non-finite JSON number is forbidden: {value}")


def canonical_json_text(value: Any) -> str:
    """Return the single canonical UTF-8 JSON text representation."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError("value is not canonical-JSON serializable") from exc


def canonical_json_bytes(value: Any) -> bytes:
    """Encode canonical JSON as UTF-8 bytes."""

    return canonical_json_text(value).encode("utf-8")


def parse_json(value: str) -> Any:
    """Parse JSON while rejecting non-standard numeric constants."""

    if not isinstance(value, str):
        raise ValidationError("JSON input must be text")
    try:
        return json.loads(value, parse_constant=_reject_non_finite)
    except ValidationError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValidationError("invalid JSON text") from exc
