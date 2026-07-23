"""SQLite connection creation with fail-closed pragma verification."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import sqlite3

from batch87_apprentice.common.errors import (
    ConfigurationError,
    ConnectionVerificationError,
)

from .config import DatabaseConfig

_SYNCHRONOUS_FULL = 2


def _scalar(connection: sqlite3.Connection, statement: str) -> object:
    row = connection.execute(statement).fetchone()
    if row is None:
        raise ConnectionVerificationError(f"pragma returned no value: {statement}")
    return row[0]


def verify_connection(connection: sqlite3.Connection, config: DatabaseConfig) -> None:
    """Prove the safety-critical SQLite settings on an open connection."""

    checks = {
        "foreign_keys": int(_scalar(connection, "PRAGMA foreign_keys")) == 1,
        "journal_mode": str(_scalar(connection, "PRAGMA journal_mode")).lower() == "wal",
        "synchronous": int(_scalar(connection, "PRAGMA synchronous"))
        == _SYNCHRONOUS_FULL,
        "busy_timeout": int(_scalar(connection, "PRAGMA busy_timeout"))
        == config.busy_timeout_ms,
    }
    failed = [name for name, valid in checks.items() if not valid]
    if failed:
        raise ConnectionVerificationError(
            "SQLite pragma verification failed: " + ", ".join(failed)
        )


def open_connection(
    config: DatabaseConfig,
    *,
    read_only: bool = False,
) -> sqlite3.Connection:
    """Open and verify a governed SQLite connection."""

    if read_only and not config.path.is_file():
        raise ConfigurationError("read-only database does not exist")
    if not read_only:
        config.path.parent.mkdir(parents=True, exist_ok=True)

    target: str
    use_uri = read_only
    if read_only:
        target = f"{config.path.as_uri()}?mode=ro"
    else:
        target = str(config.path)

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            target,
            timeout=config.busy_timeout_ms / 1_000,
            isolation_level=None,
            uri=use_uri,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {config.busy_timeout_ms}")
        if read_only:
            connection.execute("PRAGMA query_only = ON")
        else:
            journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
            if journal_mode is None or str(journal_mode[0]).lower() != "wal":
                raise ConnectionVerificationError("SQLite refused WAL journal mode")
            connection.execute("PRAGMA synchronous = FULL")
        verify_connection(connection, config)
        return connection
    except sqlite3.Error as exc:
        if connection is not None:
            connection.close()
        raise ConnectionVerificationError("could not configure SQLite connection") from exc
    except Exception:
        if connection is not None:
            connection.close()
        raise


@contextmanager
def read_connection(config: DatabaseConfig) -> Iterator[sqlite3.Connection]:
    """Yield a verified query-only connection."""

    connection = open_connection(config, read_only=True)
    try:
        yield connection
    finally:
        connection.close()
