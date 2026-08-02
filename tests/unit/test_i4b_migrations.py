from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from batch87_apprentice.common.errors import MigrationHistoryError
from batch87_apprentice.common.hashing import sha256_bytes
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.migrations import MigrationRunner
from batch87_apprentice.persistence.service import PersistenceService
from tests.support.i4b_fixtures import build_i4b_harness

I4B_TABLES = {
    "model_invocations",
    "model_invocation_state_transitions",
    "model_raw_outputs",
    "model_outputs",
}
I4B_INDEXES = {
    "model_invocations_task_status",
    "model_invocations_context",
    "model_invocations_one_incomplete_per_task_context",
}
I4B_TRIGGERS = {
    "model_invocations_validate_bindings",
    "model_invocation_transitions_validate_current_state",
    "model_invocations_status_requires_transition",
    "model_invocations_core_immutable",
    "model_invocations_terminal_immutable",
    "model_invocations_projection_update_requires_transition",
    "model_invocations_validate_terminal_projection",
    "model_raw_outputs_validate_capture",
    "model_outputs_validate_binding",
    "governed_reference_anchor_ownerless_claim",
    "model_invocation_state_transitions_immutable",
    "model_invocation_state_transitions_no_delete",
    "model_raw_outputs_immutable",
    "model_raw_outputs_no_delete",
    "model_outputs_immutable",
    "model_outputs_no_delete",
    "model_invocations_no_delete",
}
PROTECTED_MIGRATION_HASHES = {
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
    "0009_developmental_derivation.sql": (
        "cb75c40c4399ef8289a6b4cfc02941868b5d4db6b1d0f23c3184e4c96db364e4"
    ),
    "0010_session_task_memory.sql": (
        "5848a296c20446f3e2210ab29e145a62f4f8dd690fe4d31701b8da327bbd290e"
    ),
    "0011_retrieval_context.sql": (
        "44b2e682ae2d3bc888fd1871437cea062cef94c8d34519158b1d955e3f4b64bd"
    ),
}


def names(path: Path, object_type: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = ?
                """,
                (object_type,),
            )
        }
    finally:
        connection.close()


def test_i4b_migration_is_single_ordered_additive_step(tmp_path: Path) -> None:
    config = DatabaseConfig(tmp_path / "fresh.sqlite3")
    runner = MigrationRunner(config)
    migrations = runner.apply_all()
    connection = sqlite3.connect(config.path)
    try:
        first_ledger = connection.execute(
            """
            SELECT migration_id, filename, content_hash, applied_at,
                   application_build
            FROM schema_migrations
            ORDER BY migration_id
            """
        ).fetchall()
    finally:
        connection.close()
    runner.apply_all()
    connection = sqlite3.connect(config.path)
    try:
        repeated_ledger = connection.execute(
            """
            SELECT migration_id, filename, content_hash, applied_at,
                   application_build
            FROM schema_migrations
            ORDER BY migration_id
            """
        ).fetchall()
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchall()
    finally:
        connection.close()

    assert [migration.version for migration in migrations[:12]] == list(range(1, 13))
    assert migrations[11].filename == "0012_model_invocation_bridge.sql"
    assert repeated_ledger == first_ledger
    assert foreign_keys == []
    assert integrity == [("ok",)]
    assert I4B_TABLES <= names(config.path, "table")
    assert I4B_INDEXES <= names(config.path, "index")
    assert I4B_TRIGGERS <= names(config.path, "trigger")


def test_upgrade_from_0011_preserves_accepted_seed_and_ledger_rows(
    tmp_path: Path,
) -> None:
    source = Path(__file__).resolve().parents[2] / "src" / (
        "batch87_apprentice"
    ) / "persistence" / "sql"
    pre_i4b = tmp_path / "pre_i4b_migrations"
    pre_i4b.mkdir()
    for path in sorted(source.glob("*.sql"))[:11]:
        shutil.copy2(path, pre_i4b / path.name)
    config = DatabaseConfig(tmp_path / "upgrade.sqlite3")
    MigrationRunner(config, migrations_path=pre_i4b).apply_all()
    connection = sqlite3.connect(config.path)
    try:
        seed_before = {
            table: connection.execute(
                f"SELECT * FROM {table} ORDER BY 1"  # noqa: S608
            ).fetchall()
            for table in (
                "memory_domains",
                "memory_record_types",
                "memory_record_approval_authorities",
            )
        }
        ledger_before = connection.execute(
            """
            SELECT migration_id, filename, content_hash, applied_at,
                   application_build
            FROM schema_migrations
            ORDER BY migration_id
            """
        ).fetchall()
    finally:
        connection.close()

    MigrationRunner(config).apply_all()
    connection = sqlite3.connect(config.path)
    try:
        seed_after = {
            table: connection.execute(
                f"SELECT * FROM {table} ORDER BY 1"  # noqa: S608
            ).fetchall()
            for table in seed_before
        }
        ledger_after = connection.execute(
            """
            SELECT migration_id, filename, content_hash, applied_at,
                   application_build
            FROM schema_migrations
            ORDER BY migration_id
            """
        ).fetchall()
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchall()
    finally:
        connection.close()

    assert seed_after == seed_before
    assert ledger_after[:11] == ledger_before
    assert ledger_after[11][0:2] == (
        "0012",
        "0012_model_invocation_bridge.sql",
    )
    assert foreign_keys == []
    assert integrity == [("ok",)]



def _database_snapshot(
    connection: sqlite3.Connection,
    tables: tuple[str, ...],
) -> dict[str, tuple[tuple[object, ...], ...]]:
    return {
        table: tuple(
            connection.execute(
                f"SELECT * FROM {table} ORDER BY rowid"  # noqa: S608
            ).fetchall()
        )
        for table in tables
    }


def test_populated_i1_through_i4a_upgrade_preserves_rows_and_reconstruction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Path(__file__).resolve().parents[2] / "src" / (
        "batch87_apprentice"
    ) / "persistence" / "sql"
    pre_i4b = tmp_path / "populated_pre_i4b_migrations"
    pre_i4b.mkdir()
    for path in sorted(source.glob("*.sql"))[:11]:
        shutil.copy2(path, pre_i4b / path.name)

    original_initialize = PersistenceService.initialize.__func__

    def initialize_through_i4a(cls, config, *, migrations_path=None):
        return original_initialize(cls, config, migrations_path=pre_i4b)

    with monkeypatch.context() as scoped:
        scoped.setattr(
            PersistenceService,
            "initialize",
            classmethod(initialize_through_i4a),
        )
        harness = build_i4b_harness(
            tmp_path / "populated_fixture",
            base=6_200_000,
        )

    config = harness.config
    connection = sqlite3.connect(config.path)
    try:
        preexisting_tables = tuple(
            row[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                  AND name <> 'schema_migrations'
                ORDER BY name
                """
            )
        )
        rows_before = _database_snapshot(connection, preexisting_tables)
        ledger_before = tuple(
            connection.execute(
                """
                SELECT migration_id, filename, content_hash, applied_at,
                       application_build
                FROM schema_migrations
                ORDER BY migration_id
                """
            ).fetchall()
        )
    finally:
        connection.close()

    reconstructions_before = {
        "task": harness.i4a.runtime.reconstruct(harness.task_id).value,
        "task_memory": (
            harness.i4a.persistence.session_task_memory.reconstruct_task_memory(
                harness.task_id,
                mode="active",
                evaluated_at="2026-07-30T00:00:01.000000Z",
            )
        ),
        "context": (
            harness.i4a.persistence.retrieval_context.reconstruct_context_package(
                harness.context_package_id
            )
        ),
    }

    MigrationRunner(config).apply_all()

    connection = sqlite3.connect(config.path)
    try:
        rows_after = _database_snapshot(connection, preexisting_tables)
        ledger_after = tuple(
            connection.execute(
                """
                SELECT migration_id, filename, content_hash, applied_at,
                       application_build
                FROM schema_migrations
                ORDER BY migration_id
                """
            ).fetchall()
        )
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchall()
    finally:
        connection.close()

    reopened = PersistenceService(config)
    reconstructions_after = {
        "task": harness.i4a.runtime.reconstruct(harness.task_id).value,
        "task_memory": reopened.session_task_memory.reconstruct_task_memory(
            harness.task_id,
            mode="active",
            evaluated_at="2026-07-30T00:00:01.000000Z",
        ),
        "context": reopened.retrieval_context.reconstruct_context_package(
            harness.context_package_id
        ),
    }

    assert any(rows_before[table] for table in preexisting_tables)
    assert rows_after == rows_before
    assert reconstructions_after == reconstructions_before
    assert ledger_after[:11] == ledger_before
    assert ledger_after[11][0:2] == (
        "0012",
        "0012_model_invocation_bridge.sql",
    )
    assert foreign_keys == []
    assert integrity == [("ok",)]
    assert I4B_TABLES <= names(config.path, "table")
    assert I4B_INDEXES <= names(config.path, "index")
    assert I4B_TRIGGERS <= names(config.path, "trigger")


def test_i4b_migration_ledger_detects_exact_byte_tampering(
    tmp_path: Path,
) -> None:
    source = Path(__file__).resolve().parents[2] / "src" / (
        "batch87_apprentice"
    ) / "persistence" / "sql"
    copied = tmp_path / "tampered_migrations"
    copied.mkdir()
    for path in sorted(source.glob("*.sql")):
        shutil.copy2(path, copied / path.name)
    config = DatabaseConfig(tmp_path / "tampered.sqlite3")
    MigrationRunner(config, migrations_path=copied).apply_all()
    target = copied / "0012_model_invocation_bridge.sql"
    target.write_bytes(target.read_bytes() + b"\n")

    with pytest.raises(MigrationHistoryError, match="hash changed"):
        MigrationRunner(config, migrations_path=copied).verify_history()


def test_pre_i4b_migration_bytes_remain_exactly_unchanged() -> None:
    migrations = MigrationRunner(
        DatabaseConfig(Path("unused-i4b-hash-check.sqlite3"))
    ).discover()

    assert {
        migration.filename: migration.sha256
        for migration in migrations[:11]
    } == PROTECTED_MIGRATION_HASHES


def test_i4b_migration_contains_no_runtime_or_experimental_activation() -> None:
    migration = MigrationRunner(
        DatabaseConfig(Path("unused-i4b-content-check.sqlite3"))
    ).discover()[11]
    lowered = migration.sql.lower()

    assert "create table model_invocations" in lowered
    assert "create table model_raw_outputs" in lowered
    assert "create table model_outputs" in lowered
    for prohibited in (
        "http://",
        "https://",
        "api_key",
        "model server",
        "experimental laboratory",
        "validation_v1",
    ):
        assert prohibited not in lowered


def test_schema_registry_binds_exact_local_bytes() -> None:
    root = Path(__file__).resolve().parents[2]
    registry = json.loads((root / "schemas" / "registry.json").read_text("utf-8"))
    entries = {entry["id"]: entry for entry in registry["schemas"]}

    assert len(entries) == 3
    for entry in entries.values():
        exact = (root / "schemas" / entry["path"]).read_bytes()
        assert entry["content_hash"] == sha256_bytes(exact)
        assert entry["status"] == "active"
