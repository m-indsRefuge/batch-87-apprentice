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


I3D_TABLES = {
    "task_context_items",
    "task_context_finalizations",
    "active_uncertainties",
    "uncertainty_resolutions",
}
I3D_INDEXES = {
    "task_context_items_task_order",
    "task_context_items_memory_source",
    "task_context_items_evidence_source",
    "active_uncertainties_task",
    "uncertainty_resolutions_task",
}
I3D_TRIGGERS = {
    "task_context_items_insert_guard",
    "task_context_finalizations_insert_guard",
    "active_uncertainties_insert_guard",
    "active_uncertainty_initial_history_guard",
    "uncertainty_resolutions_insert_guard",
    "task_context_items_immutable",
    "task_context_items_no_delete",
    "task_context_finalizations_immutable",
    "task_context_finalizations_no_delete",
    "active_uncertainties_immutable",
    "active_uncertainty_records_immutable",
    "active_uncertainties_no_delete",
    "uncertainty_resolutions_immutable",
    "uncertainty_resolutions_no_delete",
    "session_participants_contract_guard",
    "session_state_transitions_monotonic_time_guard",
    "task_state_transitions_monotonic_time_guard",
    "task_state_transitions_transaction_guard",
}
ACCEPTED_MIGRATION_HASHES = {
    "0001_system_entities_records.sql":
        "4b17bba385254cc532785e2dfed08e27ffbc5b1c4537c22447982cb24a053f77",
    "0002_evidence.sql":
        "d266b07159f002f5a068d7e8ca0314c5a5e2e9a829639ac1f961941e3c629134",
    "0003_controlled_resilience.sql":
        "982872f104192f243d8ab676ab448daa004d40be9de560efd065fbabb2c19a28",
    "0004_governed_task_runtime.sql":
        "54f2d1e10d7ffdcee4e64e6746b883b2f1d366da3d78ac656e631f71a1527a70",
    "0005_memory_domains.sql":
        "5f4ab60ad85020873951985c298ecbad41cb5e05d6c4f93119e0564159f2ee16",
    "0006_construct_relational_memory.sql":
        "322cbcb0b67fb25a7de68ba4f29d1b349f3f79ac96cbc2de7d51155d57f81fdf",
    "0007_self_episodic_memory.sql":
        "17812d04e60cf5f3f9451e2515179b79dbb264a253c359d439d71c8e79a057ca",
    "0008_episode_correction_ledger.sql":
        "6bcf5cd844937bf25c3381895977983999e539e52f947b20e7498ef2b4a482b5",
    "0009_developmental_derivation.sql":
        "cb75c40c4399ef8289a6b4cfc02941868b5d4db6b1d0f23c3184e4c96db364e4",
}


def test_fresh_database_applies_current_migrations_additively(
    tmp_path: Path,
) -> None:
    config = DatabaseConfig(tmp_path / "fresh.sqlite3")
    migrations = MigrationRunner(config).apply_all()

    assert [item.version for item in migrations] == list(range(1, 13))
    assert migrations[-1].filename == "0012_model_invocation_bridge.sql"
    assert I3D_TABLES <= names(config.path, "table")
    assert I3D_INDEXES <= names(config.path, "index")
    assert I3D_TRIGGERS <= names(config.path, "trigger")
    assert all(rows(config.path, table) == () for table in I3D_TABLES)


def test_0010_is_additive_over_exact_0009(tmp_path: Path) -> None:
    migration_directory = tmp_path / "migrations"
    copy_migrations(migration_directory, through=9)
    config = DatabaseConfig(tmp_path / "upgrade.sqlite3")
    runner = MigrationRunner(config, migration_directory)
    runner.apply_all()
    before_tables = names(config.path, "table")
    before_history = rows(config.path, "schema_migrations")
    before_sessions = rows(config.path, "sessions")
    before_tasks = rows(config.path, "tasks")

    source = default_migrations_path() / "0010_session_task_memory.sql"
    (migration_directory / source.name).write_bytes(source.read_bytes())
    migrations = runner.apply_all()

    assert [item.version for item in migrations] == list(range(1, 11))
    assert names(config.path, "table") - before_tables == I3D_TABLES
    assert rows(config.path, "schema_migrations")[:9] == before_history
    assert rows(config.path, "sessions") == before_sessions
    assert rows(config.path, "tasks") == before_tasks


def test_failed_0010_rolls_back_all_schema_objects(tmp_path: Path) -> None:
    migration_directory = tmp_path / "migrations"
    copy_migrations(migration_directory, through=9)
    config = DatabaseConfig(tmp_path / "rollback.sqlite3")
    runner = MigrationRunner(config, migration_directory)
    runner.apply_all()
    before_tables = names(config.path, "table")
    before_indexes = names(config.path, "index")
    before_triggers = names(config.path, "trigger")
    source = default_migrations_path() / "0010_session_task_memory.sql"
    (migration_directory / source.name).write_text(
        source.read_text(encoding="utf-8") + "\nTHIS IS NOT SQL;\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(MigrationError, match="failed to apply"):
        runner.apply_all()

    assert names(config.path, "table") == before_tables
    assert names(config.path, "index") == before_indexes
    assert names(config.path, "trigger") == before_triggers
    assert [
        row[0] for row in rows(config.path, "schema_migrations")
    ] == [f"{version:04d}" for version in range(1, 10)]


def test_accepted_migrations_0001_through_0009_are_byte_identical() -> None:
    for filename, expected_hash in ACCEPTED_MIGRATION_HASHES.items():
        assert sha256_bytes(
            (default_migrations_path() / filename).read_bytes()
        ) == expected_hash


def test_0010_contains_no_i4_or_model_integration() -> None:
    migration = (
        default_migrations_path() / "0010_session_task_memory.sql"
    ).read_text(encoding="utf-8").lower()
    for prohibited in (
        "context_manifests",
        "retrieval_requests",
        "model_invocations",
        "model_provider",
        "embedding",
        "semantic_search",
        "token_budget",
        "prompt_template",
        "soul.md",
    ):
        assert prohibited not in migration


def test_0010_schema_passes_sqlite_integrity_checks(tmp_path: Path) -> None:
    config = DatabaseConfig(tmp_path / "integrity.sqlite3")
    MigrationRunner(config).apply_all()
    connection = sqlite3.connect(config.path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert tuple(connection.execute("PRAGMA integrity_check")) == (("ok",),)
        assert tuple(connection.execute("PRAGMA foreign_key_check")) == ()
    finally:
        connection.close()
