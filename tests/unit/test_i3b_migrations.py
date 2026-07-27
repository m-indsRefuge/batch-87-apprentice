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
}
I3B_TABLES = {
    "construct_relationship_type_policies",
    "construct_entities",
    "construct_relationships",
    "architecture_decisions",
    "project_states",
    "construct_doctrines",
    "terminology_definitions",
    "preference_records",
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


def test_fresh_database_applies_exact_order_and_ledger_hash(tmp_path: Path) -> None:
    config = DatabaseConfig(tmp_path / "fresh.sqlite3")
    runner = MigrationRunner(config)

    migrations = runner.apply_all()

    assert [migration.version for migration in migrations] == list(range(1, 9))
    assert migrations[5].filename == "0006_construct_relational_memory.sql"
    assert I3B_TABLES <= table_names(config.path)
    connection = sqlite3.connect(config.path)
    try:
        ledger_hash = connection.execute(
            """
            SELECT content_hash FROM schema_migrations
            WHERE migration_id = '0006'
            """
        ).fetchone()[0]
    finally:
        connection.close()
    assert ledger_hash == migrations[5].sha256


def test_exact_0005_database_upgrades_additively_to_0006(tmp_path: Path) -> None:
    migration_directory = tmp_path / "migrations"
    copy_migrations(migration_directory, through=5)
    config = DatabaseConfig(tmp_path / "upgrade.sqlite3")
    runner = MigrationRunner(config, migration_directory)
    assert [item.version for item in runner.apply_all()] == [1, 2, 3, 4, 5]
    before = table_names(config.path)

    source = default_migrations_path() / "0006_construct_relational_memory.sql"
    (migration_directory / source.name).write_bytes(source.read_bytes())
    assert [item.version for item in runner.apply_all()] == [1, 2, 3, 4, 5, 6]

    after = table_names(config.path)
    assert after - before == I3B_TABLES


def test_0006_failure_rolls_back_all_i3b_schema_and_ledger(tmp_path: Path) -> None:
    migration_directory = tmp_path / "migrations"
    copy_migrations(migration_directory, through=5)
    config = DatabaseConfig(tmp_path / "rollback.sqlite3")
    runner = MigrationRunner(config, migration_directory)
    runner.apply_all()
    source = default_migrations_path() / "0006_construct_relational_memory.sql"
    broken = source.read_text(encoding="utf-8") + "\nTHIS IS NOT SQL;\n"
    (migration_directory / source.name).write_text(
        broken,
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(MigrationError, match="failed to apply"):
        runner.apply_all()

    assert not (I3B_TABLES & table_names(config.path))
    connection = sqlite3.connect(config.path)
    try:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
            )
        ]
    finally:
        connection.close()
    assert versions == ["0001", "0002", "0003", "0004", "0005"]


def test_accepted_migrations_0001_through_0005_remain_byte_identical() -> None:
    for filename, expected_hash in EXPECTED_ACCEPTED_HASHES.items():
        assert sha256_bytes((default_migrations_path() / filename).read_bytes()) == (
            expected_hash
        )



def test_relationship_policy_registry_rejects_post_seed_insert(tmp_path: Path) -> None:
    config = DatabaseConfig(tmp_path / "registry.sqlite3")
    MigrationRunner(config).apply_all()
    connection = sqlite3.connect(config.path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="authorised migration"):
            connection.execute(
                """
                INSERT INTO construct_relationship_type_policies (
                    relationship_type, authority_bearing,
                    self_reference_permitted, bidirectional_permitted,
                    required_approval_authority_class, status
                ) VALUES ('invented_relation', 0, 0, 0,
                          'nolan_byte_approved', 'active')
                """
            )
    finally:
        connection.close()
