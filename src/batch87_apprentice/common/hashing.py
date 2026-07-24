"""SHA-256 helpers with explicit byte boundaries."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from .canonical_json import canonical_json_bytes
from .errors import ValidationError


def sha256_bytes(value: bytes) -> str:
    """Hash exact bytes and return a lowercase hexadecimal digest."""

    if not isinstance(value, bytes):
        raise ValidationError("SHA-256 input must be bytes")
    return hashlib.sha256(value).hexdigest()


def sha256_canonical_json(value: Any) -> str:
    """Hash the canonical JSON representation of a value."""

    return sha256_bytes(canonical_json_bytes(value))


def hashes_match(expected: str, actual: str) -> bool:
    """Compare SHA-256 digests without timing-sensitive equality."""

    if not isinstance(expected, str) or not isinstance(actual, str):
        return False
    return hmac.compare_digest(expected, actual)
