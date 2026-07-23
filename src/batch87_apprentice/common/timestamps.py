"""Canonical UTC timestamp helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from .errors import ValidationError

_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def canonical_utc_now() -> str:
    """Return the current UTC instant in the canonical RFC 3339 form."""

    return datetime.now(UTC).strftime(_FORMAT)


def parse_canonical_utc(value: str, *, field: str = "timestamp") -> datetime:
    """Require the exact canonical UTC representation used at rest."""

    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text")
    try:
        parsed = datetime.strptime(value, _FORMAT).replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValidationError(
            f"{field} must use YYYY-MM-DDTHH:MM:SS.ffffffZ"
        ) from exc
    if parsed.strftime(_FORMAT) != value:
        raise ValidationError(f"{field} is not a canonical UTC timestamp")
    return parsed
