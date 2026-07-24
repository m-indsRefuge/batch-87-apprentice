from __future__ import annotations

from datetime import UTC
import hashlib
from pathlib import Path
from uuid import uuid1, uuid4

import pytest

from batch87_apprentice.common.canonical_json import (
    canonical_json_bytes,
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import ConfigurationError, ValidationError
from batch87_apprentice.common.hashing import sha256_bytes, sha256_canonical_json
from batch87_apprentice.common.identifiers import (
    generate_identifier,
    validate_identifier,
)
from batch87_apprentice.common.timestamps import (
    canonical_utc_now,
    parse_canonical_utc,
)
from batch87_apprentice.persistence.config import (
    DATABASE_PATH_ENV,
    DEFAULT_DATABASE_RELATIVE_PATH,
    DatabaseConfig,
    repository_root,
    resolve_database_config,
)


def test_canonical_json_is_sorted_compact_utf8_and_round_trips() -> None:
    value = {"z": [True, None, "café"], "a": {"b": 2, "a": 1}}

    text = canonical_json_text(value)

    assert text == '{"a":{"a":1,"b":2},"z":[true,null,"café"]}'
    assert canonical_json_bytes(value) == text.encode("utf-8")
    assert parse_json(text) == value


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValidationError):
        canonical_json_text({"value": value})


def test_sha256_hashes_exact_bytes_and_canonical_json() -> None:
    exact = b"batch-87"

    assert sha256_bytes(exact) == hashlib.sha256(exact).hexdigest()
    assert sha256_canonical_json({"b": 2, "a": 1}) == sha256_bytes(
        b'{"a":1,"b":2}'
    )


def test_identifiers_are_canonical_uuid4_or_uuid7() -> None:
    generated = generate_identifier()

    assert validate_identifier(generated) == generated
    with pytest.raises(ValidationError):
        validate_identifier(str(uuid1()))
    with pytest.raises(ValidationError):
        validate_identifier(str(uuid4()).upper())


def test_timestamps_are_exact_canonical_utc() -> None:
    value = canonical_utc_now()

    assert parse_canonical_utc(value).tzinfo is UTC
    with pytest.raises(ValidationError):
        parse_canonical_utc("2026-07-23T12:00:00Z")
    with pytest.raises(ValidationError):
        parse_canonical_utc("2026-07-23T12:00:00.000000+00:00")


def test_database_config_is_file_backed_and_resolves_precedence(
    tmp_path: Path,
) -> None:
    environment_path = tmp_path / "environment.sqlite3"
    explicit_path = tmp_path / "explicit.sqlite3"

    from_environment = resolve_database_config(
        environ={DATABASE_PATH_ENV: str(environment_path)}
    )
    explicit = resolve_database_config(
        explicit_path,
        environ={DATABASE_PATH_ENV: str(environment_path)},
    )
    default = resolve_database_config(environ={})

    assert from_environment.path == environment_path.resolve()
    assert explicit.path == explicit_path.resolve()
    assert default.path == (repository_root() / DEFAULT_DATABASE_RELATIVE_PATH)
    with pytest.raises(ConfigurationError):
        DatabaseConfig(Path(":memory:"))
