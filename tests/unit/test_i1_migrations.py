from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from batch87_apprentice.common.errors import MigrationError, MigrationHistoryError
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.connection import open_connection
from batch87_apprentice.persistence.migrations import MigrationRunner


def _write_migration(directory: Path, name: str, sql: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(sql, encoding="utf-8", newline="\n")
    return path


def test_migrations_apply_once_and_verified_pragmas_hold(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(
        migrations,
        "0001_example.sql",
        "CREATE TABLE example (id INTEGER PRIMARY KEY);\n",
    )
    config = DatabaseConfig(tmp_path / "kernel.sqlite3")
    runner = MigrationRunner(config, migrations)

    first = runner.apply_all()
    second = runner.apply_all()
    connection = open_connection(config)
    try:
        applied = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
        assert applied is not None
        assert applied[0] == 1
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000
    finally:
        connection.close()

    assert first == second


def test_migration_hash_tampering_fails_closed(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    path = _write_migration(
        migrations,
        "0001_example.sql",
        "CREATE TABLE example (id INTEGER PRIMARY KEY);\n",
    )
    runner = MigrationRunner(
        DatabaseConfig(tmp_path / "kernel.sqlite3"),
        migrations,
    )
    runner.apply_all()

    path.write_text(
        "CREATE TABLE example (id INTEGER PRIMARY KEY, changed TEXT);\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(MigrationHistoryError, match="hash changed"):
        runner.verify_history()


def test_database_ahead_of_available_migrations_fails_closed(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(
        migrations,
        "0001_example.sql",
        "CREATE TABLE example (id INTEGER PRIMARY KEY);\n",
    )
    config = DatabaseConfig(tmp_path / "kernel.sqlite3")
    runner = MigrationRunner(config, migrations)
    runner.apply_all()

    connection = open_connection(config)
    try:
        connection.execute(
            """
            INSERT INTO schema_migrations (
                migration_id, filename, content_hash, applied_at,
                application_build
            ) VALUES (
                '0002', '0002_future.sql', ?,
                '2026-07-23T00:00:00.000000Z', 'future'
            )
            """,
            ("0" * 64,),
        )
    finally:
        connection.close()

    with pytest.raises(MigrationHistoryError, match="ahead"):
        runner.verify_history()


def test_failed_migration_rolls_back_schema_and_ledger(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(
        migrations,
        "0001_broken.sql",
        """
        CREATE TABLE should_rollback (id INTEGER PRIMARY KEY);
        THIS IS NOT SQL;
        """,
    )
    config = DatabaseConfig(tmp_path / "kernel.sqlite3")
    runner = MigrationRunner(config, migrations)

    with pytest.raises(MigrationError, match="failed to apply"):
        runner.apply_all()

    connection = sqlite3.connect(config.path)
    try:
        table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'should_rollback'
            """
        ).fetchone()
        applied = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
    finally:
        connection.close()

    assert table is None
    assert applied == (0,)


def test_migration_names_are_contiguous_and_transaction_free(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(migrations, "0002_gap.sql", "SELECT 1;\n")

    with pytest.raises(MigrationError, match="contiguous"):
        MigrationRunner(
            DatabaseConfig(tmp_path / "gap.sqlite3"),
            migrations,
        ).discover()

    (migrations / "0002_gap.sql").unlink()
    _write_migration(migrations, "0001_bad.sql", "BEGIN; SELECT 1;\n")
    with pytest.raises(MigrationError, match="transaction control"):
        MigrationRunner(
            DatabaseConfig(tmp_path / "control.sqlite3"),
            migrations,
        ).discover()


@pytest.mark.parametrize(
    "transaction_sql",
    (
        "BEGIN;",
        "BEGIN DEFERRED;",
        "BEGIN IMMEDIATE;",
        "BEGIN EXCLUSIVE;",
        "BEGIN TRANSACTION;",
        "COMMIT;",
        "COMMIT TRANSACTION;",
        "END;",
        "  eNd \n TRANSACTION ;",
        "ROLLBACK;",
        "ROLLBACK TRANSACTION;",
        "ROLLBACK TO marker;",
        "ROLLBACK TO SAVEPOINT marker;",
        "SAVEPOINT marker;",
        "RELEASE marker;",
        "RELEASE SAVEPOINT marker;",
    ),
)
def test_all_top_level_transaction_control_aliases_fail_discovery(
    tmp_path: Path,
    transaction_sql: str,
) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(
        migrations,
        "0001_transaction_control.sql",
        f"-- leading comment\n{transaction_sql}\n",
    )

    with pytest.raises(MigrationError, match="transaction control"):
        MigrationRunner(
            DatabaseConfig(tmp_path / "control.sqlite3"),
            migrations,
        ).discover()


def test_trigger_begin_end_is_not_mistaken_for_transaction_control(
    tmp_path: Path,
) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(
        migrations,
        "0001_trigger.sql",
        """
        CREATE TABLE source (id INTEGER PRIMARY KEY, value INTEGER NOT NULL);
        CREATE TABLE audit (source_id INTEGER NOT NULL);
        CREATE TRIGGER source_audit
        AFTER INSERT ON source
        BEGIN
            INSERT INTO audit (source_id)
            VALUES (
                CASE WHEN NEW.value > 0 THEN NEW.id ELSE NEW.id END
            );
        END;
        """,
    )

    runner = MigrationRunner(
        DatabaseConfig(tmp_path / "trigger.sqlite3"),
        migrations,
    )

    assert len(runner.discover()) == 1
    assert len(runner.apply_all()) == 1


def test_end_alias_is_rejected_before_any_schema_or_ledger_write(
    tmp_path: Path,
) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(
        migrations,
        "0001_should_never_execute.sql",
        """
        CREATE TABLE should_never_commit (id INTEGER PRIMARY KEY);
        END;
        THIS IS NOT SQL;
        """,
    )
    config = DatabaseConfig(tmp_path / "preflight.sqlite3")

    with pytest.raises(MigrationError, match="transaction control"):
        MigrationRunner(config, migrations).apply_all()

    connection = sqlite3.connect(config.path)
    try:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()

    assert "should_never_commit" not in names
    assert "schema_migrations" not in names


def test_duplicate_migration_identifiers_fail_discovery(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(migrations, "0001_first.sql", "SELECT 1;\n")
    _write_migration(migrations, "0001_second.sql", "SELECT 2;\n")

    with pytest.raises(MigrationError, match="contiguous"):
        MigrationRunner(
            DatabaseConfig(tmp_path / "duplicate.sqlite3"),
            migrations,
        ).discover()
