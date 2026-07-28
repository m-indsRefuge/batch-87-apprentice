from __future__ import annotations

from pathlib import Path

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.contracts import (
    EvidenceItem,
    EvidenceLink,
    ReferenceAnchor,
)
from batch87_apprentice.persistence.migrations import (
    MigrationRunner,
    default_migrations_path,
)
from batch87_apprentice.persistence.service import PersistenceService
from tests.support.sql_probe import SqlProbe

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
    assert report.migration_count == 10
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


def test_ownerless_claimed_anchor_is_an_integrity_error(tmp_path: Path) -> None:
    service = PersistenceService.initialize(
        DatabaseConfig(tmp_path / "ownerless-claimed.sqlite3")
    )
    scope = project_scope()
    service.scopes.create(scope)
    anchor = ReferenceAnchor(
        reference_id=uid(11),
        reference_kind="context_manifest",
        project_scope_id=scope.scope_id,
        created_at=NOW,
        provenance_json=canonical_json_text({"operation_executed": False}),
    )
    service.reference_anchors.register(anchor)
    SqlProbe(service.config).corrupt_after_dropping_triggers(
        ("governed_reference_anchor_ownerless_claim",),
        lambda connection: connection.execute(
            """
            UPDATE governed_reference_anchors
            SET lifecycle_state = 'claimed'
            WHERE reference_id = ?
            """,
            (anchor.reference_id,),
        ),
    )

    report = service.integrity.inspect()

    assert not report.ok
    assert "anchor_ownerless_claimed" in {
        finding.code for finding in report.findings
    }


def test_noninline_metadata_is_audited_as_unavailable(tmp_path: Path) -> None:
    service = PersistenceService.initialize(
        DatabaseConfig(tmp_path / "noninline-unavailable.sqlite3")
    )
    item = EvidenceItem(
        evidence_id=uid(12),
        evidence_kind="document",
        storage_kind="repository_reference",
        captured_at=NOW,
        integrity_status="unavailable",
        redaction_status="none",
        sensitivity_class="internal",
        privacy_class="none",
        storage_location="docs/governance.md",
        byte_length=87,
        content_hash="0" * 64,
    )
    service.evidence.create(item)

    report = service.integrity.inspect()

    assert report.ok
    assert report.warning_count == 1
    assert report.findings[0].code == "evidence_integrity_not_valid"


def test_noninline_false_validity_is_reported_after_test_only_corruption(
    tmp_path: Path,
) -> None:
    service = PersistenceService.initialize(
        DatabaseConfig(tmp_path / "noninline-false-validity.sqlite3")
    )
    item = EvidenceItem(
        evidence_id=uid(13),
        evidence_kind="document",
        storage_kind="repository_reference",
        captured_at=NOW,
        integrity_status="unavailable",
        redaction_status="none",
        sensitivity_class="internal",
        privacy_class="none",
        storage_location="docs/governance.md",
        byte_length=87,
        content_hash="0" * 64,
    )
    service.evidence.create(item)
    SqlProbe(service.config).corrupt_after_dropping_triggers(
        ("evidence_noninline_integrity_transition_guard",),
        lambda connection: connection.execute(
            """
            UPDATE evidence_items
            SET integrity_status = 'valid'
            WHERE evidence_id = ?
            """,
            (item.evidence_id,),
        ),
    )

    report = service.integrity.inspect()
    finding = next(
        finding
        for finding in report.findings
        if finding.code == "noninline_evidence_false_validity"
    )

    assert not report.ok
    assert finding.severity == "error"
    assert finding.object_id == item.evidence_id
    assert "without independently verified exact bytes" in finding.detail


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

    SqlProbe(service.config).write(introduce_visible_mismatches)

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
    SqlProbe(service.config).write(
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


def test_controlled_link_corruption_is_reported_by_role(tmp_path: Path) -> None:
    service = PersistenceService.initialize(
        DatabaseConfig(tmp_path / "controlled-link-corruption.sqlite3")
    )
    scope = project_scope()
    service.scopes.create(scope)
    envelope, payload, anchors, evidence = controlled_components(
        scope_id=scope.scope_id,
        base=130,
    )
    service.controlled_resilience.create(
        envelope,
        payload,
        anchors=anchors,
        evidence_items=evidence,
    )
    ordinary = ordinary_record(140, scope.scope_id)
    service.records.create(ordinary)
    service.evidence.link(
        EvidenceLink(
            record_id=envelope.record_id,
            evidence_id=payload.raw_prompt_evidence_id,
            relationship="does_not_establish",
        )
    )

    def corrupt_links(connection) -> None:
        connection.execute(
            """
            DELETE FROM record_evidence_links
            WHERE record_id = ? AND evidence_id = ?
              AND relationship = 'evaluated_against'
            """,
            (envelope.record_id, payload.raw_prompt_evidence_id),
        )
        connection.execute(
            """
            UPDATE record_evidence_links
            SET relationship = 'supports'
            WHERE record_id = ? AND evidence_id = ?
              AND relationship = 'produced_as'
            """,
            (envelope.record_id, payload.raw_output_evidence_id),
        )
        connection.execute(
            """
            UPDATE record_evidence_links
            SET record_id = ?
            WHERE record_id = ? AND evidence_id = ?
              AND relationship = 'does_not_establish'
            """,
            (
                ordinary.record_id,
                envelope.record_id,
                payload.raw_prompt_evidence_id,
            ),
        )

    SqlProbe(service.config).corrupt_after_dropping_triggers(
        (
            "controlled_resilience_mandatory_link_no_delete",
            "controlled_resilience_mandatory_link_no_update",
            "controlled_resilience_evidence_link_update_isolation",
        ),
        corrupt_links,
    )

    report = service.integrity.inspect()
    codes = {finding.code for finding in report.findings}

    assert not report.ok
    assert {
        "controlled_prompt_link_missing",
        "controlled_output_link_missing",
        "controlled_output_link_invalid",
        "controlled_evidence_link_contamination",
    } <= codes


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

    report = SqlProbe(config).inspect(migration_runner=runner)

    assert not report.ok
    assert report.migration_count == 0
    assert {finding.code for finding in report.findings} == {
        "migration_history_invalid"
    }
