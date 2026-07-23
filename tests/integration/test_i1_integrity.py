from __future__ import annotations

from pathlib import Path

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.contracts import ReferenceAnchor
from batch87_apprentice.persistence.integrity import IntegrityInspector
from batch87_apprentice.persistence.migrations import (
    MigrationRunner,
    default_migrations_path,
)
from batch87_apprentice.persistence.service import PersistenceService

from .test_i1_persistence_kernel import (
    NOW,
    controlled_components,
    ordinary_record,
    project_scope,
    uid,
)


def test_clean_database_integrity_report_is_error_free(tmp_path: Path) -> None:
    service = PersistenceService.initialize(
        DatabaseConfig(tmp_path / "clean.sqlite3")
    )

    report = service.integrity.inspect()

    assert report.ok
    assert report.migration_count == 3
    assert report.error_count == 0
    assert report.warning_count == 0


def test_unclaimed_anchor_is_visible_without_implying_failure(
    tmp_path: Path,
) -> None:
    service = PersistenceService.initialize(
        DatabaseConfig(tmp_path / "unclaimed.sqlite3")
    )
    scope = project_scope()
    service.scopes.create(scope)
    anchor = ReferenceAnchor(
        reference_id=uid(10),
        reference_kind="evaluation_experiment",
        project_scope_id=scope.scope_id,
        created_at=NOW,
        provenance_json=canonical_json_text({"operation_executed": False}),
    )
    service.reference_anchors.register(anchor)

    report = service.integrity.inspect()

    assert report.ok
    assert report.warning_count == 1
    assert report.findings[0].code == "anchor_unclaimed"


def test_integrity_inspector_exposes_hash_and_lifecycle_mismatches(
    tmp_path: Path,
) -> None:
    service = PersistenceService.initialize(
        DatabaseConfig(tmp_path / "mismatch.sqlite3")
    )
    scope = project_scope()
    service.scopes.create(scope)
    envelope = ordinary_record(20, scope.scope_id)
    service.records.create(envelope)
    invalid_anchor = ReferenceAnchor(
        reference_id=uid(21),
        reference_kind="evaluation_experiment",
        project_scope_id=scope.scope_id,
        created_at=NOW,
        provenance_json=canonical_json_text({"source": "fixture"}),
    )
    service.reference_anchors.register(invalid_anchor)

    def introduce_visible_mismatches(connection) -> None:
        connection.execute(
            "UPDATE records SET content_hash = ? WHERE record_id = ?",
            ("0" * 64, envelope.record_id),
        )
        connection.execute(
            """
            UPDATE governed_reference_anchors
            SET lifecycle_state = 'invalid', integrity_status = 'mismatch'
            WHERE reference_id = ?
            """,
            (invalid_anchor.reference_id,),
        )
        connection.execute(
            """
            INSERT INTO governed_reference_anchors (
                reference_id, reference_kind, project_scope_id, lifecycle_state,
                created_at, provenance_json, content_hash, integrity_status
            ) VALUES (?, 'evaluation_fixture', ?, 'registered', ?, ?, ?, 'valid')
            """,
            (
                uid(22),
                scope.scope_id,
                NOW,
                canonical_json_text({"source": "deliberately mismatched fixture"}),
                "f" * 64,
            ),
        )

    service.kernel.write(introduce_visible_mismatches)

    report = service.integrity.inspect()
    codes = {finding.code for finding in report.findings}
    assert not report.ok
    assert {
        "record_hash_mismatch",
        "anchor_invalid",
        "anchor_integrity_not_valid",
        "anchor_hash_mismatch",
        "anchor_unclaimed",
    } <= codes


def test_controlled_anchor_integrity_failure_remains_auditable(
    tmp_path: Path,
) -> None:
    service = PersistenceService.initialize(
        DatabaseConfig(tmp_path / "controlled-mismatch.sqlite3")
    )
    scope = project_scope()
    service.scopes.create(scope)
    envelope, payload, anchors, evidence = controlled_components(
        scope_id=scope.scope_id,
        base=100,
    )
    service.controlled_resilience.create(
        envelope,
        payload,
        anchors=anchors,
        evidence_items=evidence,
    )
    service.kernel.write(
        lambda connection: connection.execute(
            """
            UPDATE governed_reference_anchors
            SET integrity_status = 'mismatch'
            WHERE reference_id = ?
            """,
            (payload.context_manifest_id,),
        )
    )

    report = service.integrity.inspect()
    codes = {finding.code for finding in report.findings}

    assert not report.ok
    assert "anchor_integrity_not_valid" in codes
    assert "controlled_anchor_invalid" in codes


def test_migration_tampering_is_reported_read_only(tmp_path: Path) -> None:
    migration_directory = tmp_path / "migrations"
    migration_directory.mkdir()
    for source in default_migrations_path().glob("*.sql"):
        (migration_directory / source.name).write_bytes(source.read_bytes())
    config = DatabaseConfig(tmp_path / "migration.sqlite3")
    runner = MigrationRunner(config, migration_directory)
    runner.apply_all()
    migration = migration_directory / "0001_system_entities_records.sql"
    migration.write_bytes(migration.read_bytes() + b"\n")

    report = IntegrityInspector(
        PersistenceService(config).kernel,
        migration_runner=runner,
    ).inspect()

    assert not report.ok
    assert report.migration_count == 0
    assert {finding.code for finding in report.findings} == {
        "migration_history_invalid"
    }
