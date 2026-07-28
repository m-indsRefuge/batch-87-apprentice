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
from tests.unit.test_i3c2_migrations import copy_migrations, names, rows

C3_TABLES = {
    "lesson_candidates",
    "lesson_candidate_source_episodes",
    "lesson_candidate_source_corrections",
    "lesson_candidate_limitations",
    "approved_lessons",
    "approved_lesson_source_episodes",
    "approved_lesson_source_corrections",
    "approved_lesson_application_conditions",
    "approved_lesson_non_application_conditions",
    "approved_lesson_transfer_tests",
    "failure_patterns",
    "failure_pattern_episodes",
    "success_patterns",
    "success_pattern_episodes",
    "success_pattern_transfer_scopes",
}

ACCEPTED_MIGRATION_HASHES = {
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
    "0008_episode_correction_ledger.sql": (
        "6bcf5cd844937bf25c3381895977983999e539e52f947b20e7498ef2b4a482b5"
    ),
}


def test_fresh_database_applies_exactly_through_0009(tmp_path: Path) -> None:
    migration_directory = tmp_path / "migrations"
    copy_migrations(migration_directory, through=9)
    config = DatabaseConfig(tmp_path / "fresh.sqlite3")
    migrations = MigrationRunner(config, migration_directory).apply_all()

    assert [item.version for item in migrations] == list(range(1, 10))
    assert migrations[-1].filename == "0009_developmental_derivation.sql"
    assert C3_TABLES <= names(config.path, "table")
    assert all(rows(config.path, table) == () for table in C3_TABLES)
    assert rows(config.path, "memory_approval_grants") == ()
    assert rows(config.path, "memory_relationship_grants") == ()
    stored = rows(config.path, "schema_migrations")[-1]
    assert stored[0] == "0009"
    assert stored[2] == migrations[-1].sha256


def test_0009_adds_only_c3_schema_to_exact_0008(tmp_path: Path) -> None:
    migration_directory = tmp_path / "migrations"
    copy_migrations(migration_directory, through=8)
    config = DatabaseConfig(tmp_path / "upgrade.sqlite3")
    runner = MigrationRunner(config, migration_directory)
    assert [item.version for item in runner.apply_all()] == list(range(1, 9))
    before_tables = names(config.path, "table")
    before_registry = rows(config.path, "memory_record_types")
    before_authorities = rows(
        config.path,
        "memory_record_approval_authorities",
    )
    before_history = rows(config.path, "schema_migrations")

    source = default_migrations_path() / "0009_developmental_derivation.sql"
    (migration_directory / source.name).write_bytes(source.read_bytes())
    assert [item.version for item in runner.apply_all()] == list(range(1, 10))

    assert names(config.path, "table") - before_tables == C3_TABLES
    assert rows(config.path, "memory_record_types") == before_registry
    assert (
        rows(config.path, "memory_record_approval_authorities")
        == before_authorities
    )
    assert rows(config.path, "schema_migrations")[:8] == before_history
    assert {
        "lesson_candidates_insert_guard",
        "approved_lessons_insert_guard",
        "failure_patterns_insert_guard",
        "success_patterns_insert_guard",
        "developmental_initial_finalization_guard",
        "developmental_evidence_link_insert_guard",
        "developmental_evidence_link_update_guard",
        "developmental_evidence_link_delete_guard",
        "approved_as_exact_endpoints_guard",
        "approved_as_retarget_guard",
        "approved_lesson_activation_guard",
        "developmental_records_identity_guard",
        "approved_lesson_transfer_test_guard",
    } <= names(config.path, "trigger")


def test_failed_0009_rolls_back_all_schema_objects(tmp_path: Path) -> None:
    migration_directory = tmp_path / "migrations"
    copy_migrations(migration_directory, through=8)
    config = DatabaseConfig(tmp_path / "rollback.sqlite3")
    runner = MigrationRunner(config, migration_directory)
    runner.apply_all()
    before_tables = names(config.path, "table")
    before_triggers = names(config.path, "trigger")
    before_indexes = names(config.path, "index")
    source = default_migrations_path() / "0009_developmental_derivation.sql"
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
    ] == [f"{version:04d}" for version in range(1, 9)]


def test_accepted_migrations_0001_through_0008_are_byte_identical() -> None:
    for filename, expected_hash in ACCEPTED_MIGRATION_HASHES.items():
        assert sha256_bytes(
            (default_migrations_path() / filename).read_bytes()
        ) == expected_hash


def test_0009_contains_no_i4_or_registry_expansion() -> None:
    migration = (
        default_migrations_path() / "0009_developmental_derivation.sql"
    ).read_text(encoding="utf-8").lower()
    for prohibited in (
        "insert into memory_record_types",
        "insert into memory_record_approval_authorities",
        "embedding",
        "semantic_search",
        "context_manifest",
        "model_provider",
        "soul.md",
    ):
        assert prohibited not in migration


def test_0009_schema_passes_sqlite_integrity_checks(tmp_path: Path) -> None:
    config = DatabaseConfig(tmp_path / "integrity.sqlite3")
    MigrationRunner(config).apply_all()
    connection = sqlite3.connect(config.path)
    try:
        assert tuple(connection.execute("PRAGMA integrity_check")) == (("ok",),)
        assert tuple(connection.execute("PRAGMA foreign_key_check")) == ()
    finally:
        connection.close()
