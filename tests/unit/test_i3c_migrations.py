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

EXPECTED_ACCEPTED_HASHES = {
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
}
C1_TABLES = {
    "governed_evaluation_record_anchors",
    "governed_evaluation_anchor_state_history",
    "developmental_policy_kinds",
    "developmental_policy_versions",
    "trusted_runtime_attestors",
    "runtime_substrate_attestations",
    "runtime_identities",
    "capability_observations",
    "capability_observation_evaluations",
    "maturity_states",
    "maturity_state_basis_evaluations",
}


def copy_migrations(destination: Path, *, through: int) -> None:
    destination.mkdir()
    for source in sorted(default_migrations_path().glob("*.sql"))[:through]:
        (destination / source.name).write_bytes(source.read_bytes())


def table_names(database_path: Path) -> set[str]:
    connection = sqlite3.connect(database_path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()


def rows(database_path: Path, table: str) -> tuple[tuple[object, ...], ...]:
    connection = sqlite3.connect(database_path)
    try:
        return tuple(connection.execute(f"SELECT * FROM {table} ORDER BY 1"))
    finally:
        connection.close()


def test_fresh_database_applies_through_0007_without_active_policy(
    tmp_path: Path,
) -> None:
    config = DatabaseConfig(tmp_path / "fresh.sqlite3")
    migrations = MigrationRunner(config).apply_all()

    assert [migration.version for migration in migrations] == list(range(1, 8))
    assert migrations[-1].filename == "0007_self_episodic_memory.sql"
    assert C1_TABLES <= table_names(config.path)
    assert rows(config.path, "developmental_policy_versions") == ()
    assert rows(config.path, "trusted_runtime_attestors") == ()
    assert rows(config.path, "runtime_substrate_attestations") == ()
    assert rows(config.path, "runtime_identities") == ()
    assert rows(config.path, "developmental_policy_kinds") == (
        ("capability_stability", "active"),
        ("maturity_progression", "active"),
    )
    connection = sqlite3.connect(config.path)
    try:
        ledger_hash = connection.execute(
            """
            SELECT content_hash
            FROM schema_migrations
            WHERE migration_id = '0007'
            """
        ).fetchone()[0]
    finally:
        connection.close()
    assert ledger_hash == migrations[-1].sha256


def test_runtime_context_limit_is_non_null_and_positive_in_0007(
    tmp_path: Path,
) -> None:
    config = DatabaseConfig(tmp_path / "context-limit.sqlite3")
    MigrationRunner(config).apply_all()
    connection = sqlite3.connect(config.path)
    try:
        for table in (
            "runtime_substrate_attestations",
            "runtime_identities",
        ):
            columns = {
                row[1]: row
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            assert columns["context_limit"][2] == "INTEGER"
            assert columns["context_limit"][3] == 1
            create_sql = connection.execute(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table,),
            ).fetchone()[0]
            assert "context_limit > 0" in create_sql
    finally:
        connection.close()


def test_exact_0006_database_upgrades_additively_without_changing_prior_rows(
    tmp_path: Path,
) -> None:
    migration_directory = tmp_path / "migrations"
    copy_migrations(migration_directory, through=6)
    config = DatabaseConfig(tmp_path / "upgrade.sqlite3")
    runner = MigrationRunner(config, migration_directory)
    assert [item.version for item in runner.apply_all()] == list(range(1, 7))

    connection = sqlite3.connect(config.path)
    try:
        connection.execute(
            """
            INSERT INTO entities (
                entity_id, entity_kind, canonical_name, description,
                status, created_at
            ) VALUES (
                '00000000-0000-4000-8000-000000000701',
                'project', 'preserved-project', 'pre-0007 row',
                'active', '2026-07-26T00:00:00.000000Z'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO scopes (
                scope_id, scope_kind, canonical_name, parent_scope_id, status
            ) VALUES (
                '00000000-0000-4000-8000-000000000702',
                'project', 'preserved-scope', NULL, 'active'
            )
            """
        )
        connection.commit()
    finally:
        connection.close()
    before_tables = table_names(config.path)
    before_entities = rows(config.path, "entities")
    before_scopes = rows(config.path, "scopes")
    before_ledger = rows(config.path, "schema_migrations")

    source = default_migrations_path() / "0007_self_episodic_memory.sql"
    (migration_directory / source.name).write_bytes(source.read_bytes())
    assert [item.version for item in runner.apply_all()] == list(range(1, 8))

    assert table_names(config.path) - before_tables == C1_TABLES
    assert rows(config.path, "entities") == before_entities
    assert rows(config.path, "scopes") == before_scopes
    assert rows(config.path, "schema_migrations")[:6] == before_ledger


def test_0007_failure_rolls_back_all_schema_and_ledger(tmp_path: Path) -> None:
    migration_directory = tmp_path / "migrations"
    copy_migrations(migration_directory, through=6)
    config = DatabaseConfig(tmp_path / "rollback.sqlite3")
    runner = MigrationRunner(config, migration_directory)
    runner.apply_all()
    source = default_migrations_path() / "0007_self_episodic_memory.sql"
    broken = source.read_text(encoding="utf-8") + "\nTHIS IS NOT SQL;\n"
    (migration_directory / source.name).write_text(
        broken,
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(MigrationError, match="failed to apply"):
        runner.apply_all()

    assert not (C1_TABLES & table_names(config.path))
    assert [
        row[0] for row in rows(config.path, "schema_migrations")
    ] == [f"{version:04d}" for version in range(1, 7)]


def test_policy_and_memory_registries_reject_post_seed_mutation(
    tmp_path: Path,
) -> None:
    config = DatabaseConfig(tmp_path / "registry.sqlite3")
    MigrationRunner(config).apply_all()
    connection = sqlite3.connect(config.path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="migration-seeded"):
            connection.execute(
                """
                INSERT INTO developmental_policy_kinds (policy_kind, status)
                VALUES ('invented_policy', 'active')
                """
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """
                UPDATE developmental_policy_kinds
                SET status = 'active'
                WHERE policy_kind = 'capability_stability'
                """
            )
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            connection.execute(
                """
                DELETE FROM developmental_policy_kinds
                WHERE policy_kind = 'maturity_progression'
                """
            )
        with pytest.raises(sqlite3.IntegrityError, match="migration-seeded"):
            connection.execute(
                """
                INSERT INTO memory_record_types (
                    record_family, record_type, memory_domain,
                    approval_requirement, agent_write_policy, status
                ) VALUES (
                    'self_model', 'permission_profile', 'self_episodic',
                    'external', 'prohibited', 'active'
                )
                """
            )
    finally:
        connection.close()


def test_migrations_0001_through_0006_remain_byte_identical() -> None:
    for filename, expected_hash in EXPECTED_ACCEPTED_HASHES.items():
        actual = sha256_bytes(
            (default_migrations_path() / filename).read_bytes()
        )
        assert actual == expected_hash
