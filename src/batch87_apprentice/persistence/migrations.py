"""Ordered, immutable, hash-verified SQLite migrations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3

from batch87_apprentice import __version__
from batch87_apprentice.common.errors import MigrationError, MigrationHistoryError
from batch87_apprentice.common.hashing import sha256_bytes
from batch87_apprentice.common.timestamps import canonical_utc_now

from .config import DatabaseConfig
from .connection import open_connection, read_connection

_MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]{4})_(?P<name>[a-z0-9_]+)\.sql$")
_TRANSACTION_CONTROL = re.compile(
    r"""
    \b(?:
        BEGIN(?:\s+(?:DEFERRED|IMMEDIATE|EXCLUSIVE))?(?:\s+TRANSACTION)?\s*;
        |COMMIT(?:\s+TRANSACTION)?\s*;
        |ROLLBACK(?:\s+TRANSACTION)?\s*;
        |SAVEPOINT\s+\S+\s*;
        |RELEASE(?:\s+SAVEPOINT)?\s+\S+\s*;
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
_LEDGER_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY CHECK (
        length(migration_id) = 4
        AND migration_id NOT GLOB '*[^0-9]*'
    ),
    filename TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    applied_at TEXT NOT NULL,
    application_build TEXT NOT NULL,
    CHECK (filename GLOB '[0-9][0-9][0-9][0-9]_[a-z0-9_]*.sql')
);
CREATE TRIGGER IF NOT EXISTS schema_migrations_no_update
BEFORE UPDATE ON schema_migrations
BEGIN
    SELECT RAISE(ABORT, 'schema migration history is immutable');
END;
CREATE TRIGGER IF NOT EXISTS schema_migrations_no_delete
BEFORE DELETE ON schema_migrations
BEGIN
    SELECT RAISE(ABORT, 'schema migration history is immutable');
END;
"""


@dataclass(frozen=True, slots=True)
class Migration:
    """One exact migration resource."""

    version: int
    filename: str
    sql: str
    sha256: str


def default_migrations_path() -> Path:
    return Path(__file__).resolve().parent / "sql"


class MigrationRunner:
    """Validate and apply an ordered migration set."""

    def __init__(
        self,
        config: DatabaseConfig,
        migrations_path: Path | None = None,
    ) -> None:
        self.config = config
        self.migrations_path = (
            default_migrations_path()
            if migrations_path is None
            else Path(migrations_path).resolve(strict=False)
        )

    def discover(self) -> tuple[Migration, ...]:
        """Load a contiguous migration sequence from exact UTF-8 bytes."""

        if not self.migrations_path.is_dir():
            raise MigrationError("migration directory does not exist")
        migrations: list[Migration] = []
        for path in sorted(self.migrations_path.glob("*.sql")):
            match = _MIGRATION_NAME.fullmatch(path.name)
            if match is None:
                raise MigrationError(f"invalid migration filename: {path.name}")
            exact_bytes = path.read_bytes()
            try:
                sql = exact_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise MigrationError(f"migration is not UTF-8: {path.name}") from exc
            if _TRANSACTION_CONTROL.search(sql):
                raise MigrationError(
                    f"migration contains transaction control: {path.name}"
                )
            migrations.append(
                Migration(
                    version=int(match.group("version")),
                    filename=path.name,
                    sql=sql,
                    sha256=sha256_bytes(exact_bytes),
                )
            )
        expected = list(range(1, len(migrations) + 1))
        actual = [migration.version for migration in migrations]
        if actual != expected:
            raise MigrationError("migration versions must be contiguous from 0001")
        return tuple(migrations)

    @staticmethod
    def _ensure_ledger(connection: sqlite3.Connection) -> None:
        connection.executescript(_LEDGER_SQL)

    @staticmethod
    def _applied(connection: sqlite3.Connection) -> tuple[sqlite3.Row, ...]:
        return tuple(
            connection.execute(
                """
                SELECT migration_id, filename, content_hash, applied_at,
                       application_build
                FROM schema_migrations
                ORDER BY migration_id
                """
            )
        )

    @staticmethod
    def _verify_rows(
        available: tuple[Migration, ...],
        applied: tuple[sqlite3.Row, ...],
    ) -> None:
        if len(applied) > len(available):
            raise MigrationHistoryError("database migration history is ahead of code")
        for index, row in enumerate(applied):
            expected = available[index]
            if row["migration_id"] != f"{expected.version:04d}":
                raise MigrationHistoryError("database migration history has a gap")
            if row["filename"] != expected.filename:
                raise MigrationHistoryError(
                    f"migration filename changed at version {expected.version:04d}"
                )
            if row["content_hash"] != expected.sha256:
                raise MigrationHistoryError(
                    f"migration hash changed at version {expected.version:04d}"
                )

    def verify_history(self) -> tuple[Migration, ...]:
        """Verify applied history without mutating the database."""

        available = self.discover()
        with read_connection(self.config) as connection:
            try:
                applied = self._applied(connection)
            except sqlite3.Error as exc:
                raise MigrationHistoryError("migration ledger is unavailable") from exc
        self._verify_rows(available, applied)
        return available

    def apply_all(self) -> tuple[Migration, ...]:
        """Apply every pending migration and re-verify immutable history."""

        available = self.discover()
        connection = open_connection(self.config)
        try:
            try:
                self._ensure_ledger(connection)
                applied = self._applied(connection)
            except sqlite3.Error as exc:
                raise MigrationHistoryError(
                    "migration ledger could not be created or read"
                ) from exc
            self._verify_rows(available, applied)
            for migration in available[len(applied) :]:
                try:
                    connection.executescript("BEGIN IMMEDIATE;\n" + migration.sql)
                    connection.execute(
                        """
                        INSERT INTO schema_migrations (
                            migration_id, filename, content_hash, applied_at,
                            application_build
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            f"{migration.version:04d}",
                            migration.filename,
                            migration.sha256,
                            canonical_utc_now(),
                            __version__,
                        ),
                    )
                    connection.commit()
                except sqlite3.Error as exc:
                    if connection.in_transaction:
                        connection.rollback()
                    raise MigrationError(
                        f"failed to apply migration {migration.filename}"
                    ) from exc
        finally:
            connection.close()

        self.verify_history()
        return available
