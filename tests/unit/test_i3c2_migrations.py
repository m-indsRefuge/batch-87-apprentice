from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from batch87_apprentice.common.errors import MigrationError
from batch87_apprentice.common.hashing import sha256_bytes
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.migrations import (
    MigrationRunner,
    default_migrations_path,
)

C2_TABLES = {
    "episodes",
    "episode_input_evidence",
    "episode_output_evidence",
    "episode_evaluation_anchors",
    "corrections",
    "correction_supporting_evidence",
}
ACCEPTED_HASHES = {
    "0001_system_entities_records.sql": (
        "4b17bba385254cc532785e2dfed08e27ffbc5b1c4537c22447982cb24a053f77"
    ),
    "0002_evidence.sql": (
        "d266b07159f002f5a068d7e8ca0314c5a5e2e9a829639ac1f961941e3c629134"
    ),
    "0003_controlled_resilience.sql": (
        "982872f104192f243d8ab676ab448daa004d40be9de560efd065fbabb2c19a28"
    ),
    "0004_governed_task_runtime.sql": (
        "54f2d1e10d7ffdcee4e64e6746b883b2f1d366da3d78ac656e631f71a1527a70"
    ),
    "0005_memory_domains.sql": (
        "5f4ab60ad85020873951985c298ecbad41cb5e05d6c4f93119e0564159f2ee16"
    ),
    "0006_construct_relational_memory.sql": (
        "322cbcb0b67fb25a7de68ba4f29d1b349f3f79ac96cbc2de7d51155d57f81fdf"
    ),
    "0007_self_episodic_memory.sql": (
        "17812d04e60cf5f3f9451e2515179b79dbb264a253c359d439d71c8e79a057ca"
    ),
}


def copy_migrations(destination: Path, *, through: int) -> None:
    destination.mkdir()
    for source in sorted(default_migrations_path().glob("*.sql"))[:through]:
        (destination / source.name).write_bytes(source.read_bytes())


def names(path: Path, object_type: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = ?",
                (object_type,),
            )
        }
    finally:
        connection.close()


def rows(path: Path, table: str) -> tuple[tuple[object, ...], ...]:
    connection = sqlite3.connect(path)
    try:
        return tuple(connection.execute(f"SELECT * FROM {table} ORDER BY 1"))
    finally:
        connection.close()


def test_fresh_database_applies_exactly_through_0008(tmp_path: Path) -> None:
    config = DatabaseConfig(tmp_path / "fresh.sqlite3")
    migrations = MigrationRunner(config).apply_all()

    assert [item.version for item in migrations] == list(range(1, 9))
    assert migrations[-1].filename == "0008_episode_correction_ledger.sql"
    assert C2_TABLES <= names(config.path, "table")
    for table in C2_TABLES:
        assert rows(config.path, table) == ()
    assert rows(config.path, "memory_approval_grants") == ()
    assert rows(config.path, "memory_relationship_grants") == ()
    assert rows(config.path, "record_relationships") == ()
    connection = sqlite3.connect(config.path)
    try:
        stored = connection.execute(
            """
            SELECT content_hash FROM schema_migrations
            WHERE migration_id = '0008'
            """
        ).fetchone()[0]
    finally:
        connection.close()
    assert stored == migrations[-1].sha256


def test_0008_adds_only_c2_tables_and_guards_to_exact_0007(
    tmp_path: Path,
) -> None:
    migration_directory = tmp_path / "migrations"
    copy_migrations(migration_directory, through=7)
    config = DatabaseConfig(tmp_path / "upgrade.sqlite3")
    runner = MigrationRunner(config, migration_directory)
    assert [item.version for item in runner.apply_all()] == list(range(1, 8))
    before_tables = names(config.path, "table")
    before_rows = {
        "memory_record_types": rows(config.path, "memory_record_types"),
        "memory_record_approval_authorities": rows(
            config.path,
            "memory_record_approval_authorities",
        ),
        "schema_migrations": rows(config.path, "schema_migrations"),
    }

    source = default_migrations_path() / "0008_episode_correction_ledger.sql"
    (migration_directory / source.name).write_bytes(source.read_bytes())
    assert [item.version for item in runner.apply_all()] == list(range(1, 9))

    assert names(config.path, "table") - before_tables == C2_TABLES
    assert rows(config.path, "memory_record_types") == before_rows[
        "memory_record_types"
    ]
    assert rows(config.path, "memory_record_approval_authorities") == before_rows[
        "memory_record_approval_authorities"
    ]
    assert rows(config.path, "schema_migrations")[:7] == before_rows[
        "schema_migrations"
    ]
    trigger_names = names(config.path, "trigger")
    assert {
        "episodes_insert_guard",
        "corrections_insert_guard",
        "c2_episode_activation_guard",
        "c2_correction_activation_guard",
        "c2_corrects_relationship_insert_guard",
        "c2_record_evidence_link_insert_guard",
        "c2_episode_payload_finalization_guard",
        "c2_correction_payload_finalization_guard",
        "c2_episode_input_evidence_finalization_guard",
        "c2_episode_output_evidence_finalization_guard",
        "c2_episode_evaluation_anchor_finalization_guard",
        "c2_correction_support_finalization_guard",
        "c2_record_evidence_link_finalization_guard",
        "c2_inline_evidence_content_no_delete",
    } <= trigger_names


def test_failed_0008_rolls_back_schema_guards_and_ledger(tmp_path: Path) -> None:
    migration_directory = tmp_path / "migrations"
    copy_migrations(migration_directory, through=7)
    config = DatabaseConfig(tmp_path / "rollback.sqlite3")
    runner = MigrationRunner(config, migration_directory)
    runner.apply_all()
    before_tables = names(config.path, "table")
    before_triggers = names(config.path, "trigger")
    before_indexes = names(config.path, "index")
    source = default_migrations_path() / "0008_episode_correction_ledger.sql"
    (migration_directory / source.name).write_text(
        source.read_text(encoding="utf-8") + "\nTHIS IS NOT SQL;\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(MigrationError, match="failed to apply"):
        runner.apply_all()

    assert names(config.path, "table") == before_tables
    assert names(config.path, "trigger") == before_triggers
    assert names(config.path, "index") == before_indexes
    assert [
        row[0] for row in rows(config.path, "schema_migrations")
    ] == [f"{version:04d}" for version in range(1, 8)]


def test_accepted_migrations_0001_through_0007_are_byte_identical() -> None:
    for filename, expected_hash in ACCEPTED_HASHES.items():
        assert sha256_bytes(
            (default_migrations_path() / filename).read_bytes()
        ) == expected_hash


def test_0008_contains_no_lesson_or_pattern_payload_objects() -> None:
    migration = (
        default_migrations_path() / "0008_episode_correction_ledger.sql"
    ).read_text(encoding="utf-8")
    for prohibited in (
        "CREATE TABLE lesson",
        "CREATE TABLE failure_pattern",
        "CREATE TABLE success_pattern",
        "INSERT INTO memory_record_types",
        "INSERT INTO memory_record_approval_authorities",
    ):
        assert prohibited not in migration
