"""Opaque identifier generation and validation."""

from __future__ import annotations

from uuid import UUID, uuid4

from .errors import ValidationError

_SUPPORTED_UUID_VERSIONS = frozenset({4, 7})


def generate_identifier() -> str:
    """Generate a canonical lowercase UUIDv4 identifier."""

    return str(uuid4())


def validate_identifier(value: str, *, field: str = "identifier") -> str:
    """Validate a canonical UUIDv4 or UUIDv7 without assigning semantics."""

    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValidationError(f"{field} must be a UUIDv4 or UUIDv7") from exc
    if parsed.version not in _SUPPORTED_UUID_VERSIONS or str(parsed) != value:
        raise ValidationError(f"{field} must be a canonical lowercase UUIDv4 or UUIDv7")
    return value
