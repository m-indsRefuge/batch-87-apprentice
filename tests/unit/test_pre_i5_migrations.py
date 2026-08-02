from __future__ import annotations

from pathlib import Path
import shutil
import sqlite3

import pytest

from batch87_apprentice.common.errors import MigrationError, MigrationHistoryError
from batch87_apprentice.persistence import DatabaseConfig, MigrationRunner, PersistenceService
from tests.support.i4b_fixtures import bridge_for, build_i4b_harness, invocation_spec

PRE_I5_TABLES = {
    "evaluation_candidates",
    "evaluation_fixture_sets",
    "evaluation_fixtures",
    "evaluation_configurations",
    "evaluation_plans",
    "evaluation_plan_candidates",
    "evaluation_runs",
    "evaluation_results",
    "evaluation_run_state_transitions",
}
PRE_I5_INDEXES = {
    "evaluation_candidates_origin_state",
    "evaluation_configurations_suite",
    "evaluation_fixtures_set_order",
    "evaluation_runs_plan_order",
    "evaluation_runs_condition",
    "evaluation_runs_blinded_candidate",
    "evaluation_results_outcome",
}
PRE_I5_TRIGGERS = {
    "evaluation_results_validate_run",
    "evaluation_run_transitions_validate",
    "evaluation_candidates_immutable",
    "evaluation_candidates_no_delete",
    "evaluation_fixture_sets_immutable",
    "evaluation_fixture_sets_no_delete",
    "evaluation_fixtures_immutable",
    "evaluation_fixtures_no_delete",
    "evaluation_configurations_immutable",
    "evaluation_configurations_no_delete",
    "evaluation_plans_immutable",
    "evaluation_plans_no_delete",
    "evaluation_plan_candidates_immutable",
    "evaluation_plan_candidates_no_delete",
    "evaluation_runs_immutable",
    "evaluation_runs_no_delete",
    "evaluation_results_immutable",
    "evaluation_results_no_delete",
    "evaluation_run_state_transitions_immutable",
    "evaluation_run_state_transitions_no_delete",
}
PROTECTED_MIGRATION_HASHES = {
    "0001_system_entities_records.sql": "4b17bba385254cc532785e2dfed08e27ffbc5b1c4537c22447982cb24a053f77",
    "0002_evidence.sql": "d266b07159f002f5a068d7e8ca0314c5a5e2e9a829639ac1f961941e3c629134",
    "0003_controlled_resilience.sql": "982872f104192f243d8ab676ab448daa004d40be9de560efd065fbabb2c19a28",
    "0004_governed_task_runtime.sql": "54f2d1e10d7ffdcee4e64e6746b883b2f1d366da3d78ac656e631f71a1527a70",
    "0005_memory_domains.sql": "5f4ab60ad85020873951985c298ecbad41cb5e05d6c4f93119e0564159f2ee16",
    "0006_construct_relational_memory.sql": "322cbcb0b67fb25a7de68ba4f29d1b349f3f79ac96cbc2de7d51155d57f81fdf",
    "0007_self_episodic_memory.sql": "17812d04e60cf5f3f9451e2515179b79dbb264a253c359d439d71c8e79a057ca",
    "0008_episode_correction_ledger.sql": "6bcf5cd844937bf25c3381895977983999e539e52f947b20e7498ef2b4a482b5",
    "0009_developmental_derivation.sql": "cb75c40c4399ef8289a6b4cfc02941868b5d4db6b1d0f23c3184e4c96db364e4",
    "0010_session_task_memory.sql": "5848a296c20446f3e2210ab29e145a62f4f8dd690fe4d31701b8da327bbd290e",
    "0011_retrieval_context.sql": "44b2e682ae2d3bc888fd1871437cea062cef94c8d34519158b1d955e3f4b64bd",
    "0012_model_invocation_bridge.sql": "f6efc631505209e6ec28092fd8d951312cecb33ddb836843c3c2268e17e04fd2",
}


def _source() -> Path:
    return Path(__file__).resolve().parents[2] / "src" / (
        "batch87_apprentice"
    ) / "persistence" / "sql"


def _objects(path: Path, kind: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = ?", (kind,)
            )
        }
    finally:
        connection.close()


def _snapshot(
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


def test_pre_i5_migration_is_one_ordered_additive_step_and_idempotent(
    tmp_path: Path,
) -> None:
    config = DatabaseConfig(tmp_path / "fresh.sqlite3")
    runner = MigrationRunner(config)
    migrations = runner.apply_all()
    connection = sqlite3.connect(config.path)
    try:
        first_ledger = tuple(
            connection.execute(
                """
                SELECT migration_id, filename, content_hash, applied_at,
                       application_build
                FROM schema_migrations ORDER BY migration_id
                """
            )
        )
    finally:
        connection.close()

    runner.apply_all()
    connection = sqlite3.connect(config.path)
    try:
        repeated_ledger = tuple(
            connection.execute(
                """
                SELECT migration_id, filename, content_hash, applied_at,
                       application_build
                FROM schema_migrations ORDER BY migration_id
                """
            )
        )
        foreign_keys = tuple(connection.execute("PRAGMA foreign_key_check"))
        integrity = tuple(connection.execute("PRAGMA integrity_check"))
    finally:
        connection.close()

    assert [migration.version for migration in migrations] == list(range(1, 14))
    assert migrations[-1].filename == "0013_deterministic_evaluation.sql"
    assert repeated_ledger == first_ledger
    assert foreign_keys == ()
    assert integrity == (("ok",),)
    assert PRE_I5_TABLES <= _objects(config.path, "table")
    assert PRE_I5_INDEXES <= _objects(config.path, "index")
    assert PRE_I5_TRIGGERS <= _objects(config.path, "trigger")


def test_upgrade_from_populated_0012_preserves_all_prior_bytes_and_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pre_i5 = tmp_path / "migrations-through-0012"
    pre_i5.mkdir()
    for path in sorted(_source().glob("*.sql"))[:12]:
        shutil.copy2(path, pre_i5 / path.name)
    original_initialize = PersistenceService.initialize.__func__

    def initialize_through_i4b(cls, config, *, migrations_path=None):
        return original_initialize(cls, config, migrations_path=pre_i5)

    with monkeypatch.context() as scoped:
        scoped.setattr(
            PersistenceService,
            "initialize",
            classmethod(initialize_through_i4b),
        )
        harness = build_i4b_harness(tmp_path / "populated", base=8_700_000)
    spec = invocation_spec(harness, number=8_750_000)
    before_invocation = bridge_for(
        harness, identifier_start=8_760_000
    ).invoke(spec).value

    connection = sqlite3.connect(harness.config.path)
    try:
        prior_tables = tuple(
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
        before_rows = _snapshot(connection, prior_tables)
        before_ledger = tuple(
            connection.execute(
                "SELECT * FROM schema_migrations ORDER BY migration_id"
            )
        )
    finally:
        connection.close()

    MigrationRunner(harness.config).apply_all()

    connection = sqlite3.connect(harness.config.path)
    try:
        after_rows = _snapshot(connection, prior_tables)
        after_ledger = tuple(
            connection.execute(
                "SELECT * FROM schema_migrations ORDER BY migration_id"
            )
        )
        foreign_keys = tuple(connection.execute("PRAGMA foreign_key_check"))
        integrity = tuple(connection.execute("PRAGMA integrity_check"))
    finally:
        connection.close()
    reopened = bridge_for(harness, identifier_start=8_770_000).reconstruct(
        spec.model_invocation_id
    ).value

    assert before_rows == after_rows
    assert after_ledger[:12] == before_ledger
    assert after_ledger[12][0:2] == (
        "0013",
        "0013_deterministic_evaluation.sql",
    )
    assert reopened == before_invocation
    assert foreign_keys == ()
    assert integrity == (("ok",),)


def test_injected_0013_failure_rolls_back_schema_and_ledger(tmp_path: Path) -> None:
    through_0012 = tmp_path / "through-0012"
    broken = tmp_path / "broken"
    through_0012.mkdir()
    broken.mkdir()
    for path in sorted(_source().glob("*.sql")):
        shutil.copy2(path, broken / path.name)
        if path.name != "0013_deterministic_evaluation.sql":
            shutil.copy2(path, through_0012 / path.name)
    config = DatabaseConfig(tmp_path / "rollback.sqlite3")
    MigrationRunner(config, migrations_path=through_0012).apply_all()
    target = broken / "0013_deterministic_evaluation.sql"
    target.write_bytes(
        target.read_bytes()
        + b"\nCREATE TABLE pre_i5_partial_marker (value TEXT);"
        + b"\nINSERT INTO missing_pre_i5_parent VALUES ('fail');\n"
    )

    with pytest.raises(MigrationError, match="0013"):
        MigrationRunner(config, migrations_path=broken).apply_all()

    connection = sqlite3.connect(config.path)
    try:
        ledger = tuple(
            row[0]
            for row in connection.execute(
                "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
            )
        )
        objects = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()
    assert ledger == tuple(f"{number:04d}" for number in range(1, 13))
    assert not PRE_I5_TABLES & objects
    assert "pre_i5_partial_marker" not in objects


def test_0013_exact_byte_tamper_is_detected(tmp_path: Path) -> None:
    copied = tmp_path / "tampered"
    copied.mkdir()
    for path in sorted(_source().glob("*.sql")):
        shutil.copy2(path, copied / path.name)
    config = DatabaseConfig(tmp_path / "tampered.sqlite3")
    MigrationRunner(config, migrations_path=copied).apply_all()
    target = copied / "0013_deterministic_evaluation.sql"
    target.write_bytes(target.read_bytes() + b"\n")

    with pytest.raises(MigrationHistoryError, match="hash changed"):
        MigrationRunner(config, migrations_path=copied).verify_history()


def test_migrations_0001_through_0012_remain_exactly_unchanged() -> None:
    migrations = MigrationRunner(
        DatabaseConfig(Path("unused-pre-i5-hash-check.sqlite3"))
    ).discover()

    assert {
        migration.filename: migration.sha256 for migration in migrations[:12]
    } == PROTECTED_MIGRATION_HASHES


def test_0013_contains_no_live_provider_model_or_experimental_activation() -> None:
    migration = MigrationRunner(
        DatabaseConfig(Path("unused-pre-i5-content-check.sqlite3"))
    ).discover()[-1]
    lowered = migration.sql.lower()

    assert "create table evaluation_candidates" in lowered
    assert "create table evaluation_results" in lowered
    for prohibited in (
        "http://",
        "https://",
        "api_key",
        "model_path",
        "create table model_weights",
        "validation_v1",
        "experimental laboratory",
    ):
        assert prohibited not in lowered
