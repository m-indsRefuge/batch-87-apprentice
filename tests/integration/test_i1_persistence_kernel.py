from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

import batch87_apprentice.persistence as persistence
from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ConflictError, ValidationError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.contracts import (
    ControlledResiliencePayload,
    Entity,
    EvidenceItem,
    EvidenceLink,
    RecordEnvelope,
    ReferenceAnchor,
    RuntimeInstance,
    Scope,
    record_content_hash,
)
from batch87_apprentice.persistence.migrations import (
    MigrationRunner,
    default_migrations_path,
)
from batch87_apprentice.persistence.service import PersistenceService
from tests.support.sql_probe import SqlProbe

NOW = "2026-07-23T10:11:12.123456Z"


def uid(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012x}"


@pytest.fixture
def service(tmp_path: Path) -> PersistenceService:
    return PersistenceService.initialize(
        DatabaseConfig(tmp_path / "b87-i1.sqlite3")
    )


def project_scope(number: int = 1, *, name: str = "batch-87") -> Scope:
    return Scope(
        scope_id=uid(number),
        scope_kind="project",
        canonical_name=name,
        status="active",
    )


def ordinary_record(record_number: int, scope_id: str) -> RecordEnvelope:
    return RecordEnvelope(
        record_id=uid(record_number),
        record_family="project_state",
        record_type="snapshot",
        schema_version="1",
        project_scope_id=scope_id,
        lifecycle_state="observed",
        approval_status="not_required",
        authority_class="validated_system_evidence",
        certainty_class="verified",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="project_duration",
        training_eligibility="ineligible",
        created_at=NOW,
        source_kind="test",
        provenance_summary="Deterministic I1 integration fixture.",
        retrieval_policy_json=canonical_json_text({"mode": "governed"}),
        deletion_policy_json=canonical_json_text({"mode": "governed"}),
        agent_write_policy="prohibited",
    )


def controlled_components(
    *,
    scope_id: str,
    base: int = 100,
    recovery_record_id: str | None = None,
) -> tuple[
    RecordEnvelope,
    ControlledResiliencePayload,
    tuple[ReferenceAnchor, ...],
    tuple[EvidenceItem, ...],
]:
    record_id = uid(base)
    experiment_id = uid(base + 1)
    fixture_id = uid(base + 2)
    prompt_id = uid(base + 3)
    output_id = uid(base + 4)
    context_id = uid(base + 5)
    invocation_id = uid(base + 6)
    run_id = uid(base + 7)
    envelope = RecordEnvelope.for_controlled_resilience(
        record_id=record_id,
        project_scope_id=scope_id,
        created_at=NOW,
        provenance_summary="Deterministic synthetic resilience fixture.",
    )
    payload = ControlledResiliencePayload(
        record_id=record_id,
        experiment_id=experiment_id,
        fixture_id=fixture_id,
        test_family="CGR-01",
        test_level=1,
        test_condition="invalid",
        run_id=run_id,
        governance_distinction="Supplied content is not authority.",
        maximum_test_intensity="bounded synthetic prompt",
        raw_prompt_evidence_id=prompt_id,
        raw_output_evidence_id=output_id,
        context_manifest_id=context_id,
        model_invocation_id=invocation_id,
        recovery_record_id=recovery_record_id,
        completion_state="incomplete",
        created_at=NOW,
    )
    anchors = tuple(
        ReferenceAnchor(
            reference_id=reference_id,
            reference_kind=reference_kind,
            project_scope_id=scope_id,
            created_at=NOW,
            provenance_json=canonical_json_text(
                {
                    "fixture": "deterministic",
                    "kind": reference_kind,
                    "operation_executed": False,
                }
            ),
        )
        for reference_id, reference_kind in (
            (experiment_id, "evaluation_experiment"),
            (fixture_id, "evaluation_fixture"),
            (context_id, "context_manifest"),
            (invocation_id, "model_invocation"),
        )
    )
    evidence = (
        EvidenceItem.inline_text(
            evidence_id=prompt_id,
            evidence_kind="controlled_prompt",
            content="Synthetic invalid-authority prompt.",
            captured_at=NOW,
        ),
        EvidenceItem.inline_text(
            evidence_id=output_id,
            evidence_kind="controlled_output",
            content="Synthetic bounded output.",
            captured_at=NOW,
        ),
    )
    return envelope, payload, anchors, evidence


def test_default_migrations_apply_repeatedly_with_required_schema(
    tmp_path: Path,
) -> None:
    config = DatabaseConfig(tmp_path / "schema.sqlite3")
    runner = MigrationRunner(config)

    first = runner.apply_all()
    second = runner.apply_all()

    assert [migration.filename for migration in first] == [
        "0001_system_entities_records.sql",
        "0002_evidence.sql",
        "0003_controlled_resilience.sql",
        "0004_governed_task_runtime.sql",
        "0005_memory_domains.sql",
        "0006_construct_relational_memory.sql",
    ]
    assert first == second
    tables = SqlProbe(config).read(
        lambda connection: connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()
    )
    table_names = {row["name"] for row in tables}
    assert {
        "schema_migrations",
        "runtime_instances",
        "entities",
        "scopes",
        "records",
        "evidence_items",
        "governed_reference_anchors",
        "controlled_resilience_evidence",
    } <= table_names


def test_production_service_exposes_no_supported_raw_write_boundary(
    service: PersistenceService,
) -> None:
    assert "PersistenceKernel" not in persistence.__all__
    assert not hasattr(persistence, "PersistenceKernel")
    assert not hasattr(service, "kernel")
    assert not hasattr(service, "write")


def test_runtime_entity_scope_and_record_repositories(
    service: PersistenceService,
) -> None:
    scope = project_scope()
    entity = Entity(
        entity_id=uid(2),
        entity_kind="person",
        canonical_name="Operator fixture",
        description="Deterministic non-personal test entity.",
        status="active",
        created_at=NOW,
    )
    runtime = RuntimeInstance(
        runtime_instance_id=uid(3),
        started_at=NOW,
        application_version="0.0.1",
        host_fingerprint="0" * 64,
        process_id=87,
    )
    envelope = ordinary_record(4, scope.scope_id)

    service.scopes.create(scope)
    service.entities.create(entity)
    service.runtime_instances.start(runtime)
    digest = service.records.create(envelope)

    assert service.scopes.get(scope.scope_id)["canonical_name"] == "batch-87"
    assert service.entities.get(entity.entity_id)["status"] == "active"
    assert service.runtime_instances.get(runtime.runtime_instance_id)["status"] == "running"
    assert service.records.get(envelope.record_id)["content_hash"] == digest
    assert digest == record_content_hash(envelope)


def test_universal_envelope_rejects_invalid_governance_values() -> None:
    values: dict[str, Any] = asdict(ordinary_record(10, uid(1)))

    with pytest.raises(ValidationError, match="lifecycle_state"):
        RecordEnvelope(**(values | {"lifecycle_state": "invented"}))
    with pytest.raises(ValidationError, match="another version"):
        RecordEnvelope(**(values | {"supersedes_record_id": values["record_id"]}))
    with pytest.raises(ValidationError, match="canonical JSON"):
        RecordEnvelope(**(values | {"retrieval_policy_json": '{ "mode": "x" }'}))
    with pytest.raises(ValidationError, match="provenance_summary"):
        RecordEnvelope(**(values | {"provenance_summary": "  "}))
    with pytest.raises(ValidationError, match="project_scope_id"):
        RecordEnvelope(
            **(
                values
                | {
                    "record_family": "evaluation_evidence",
                    "project_scope_id": None,
                }
            )
        )


def test_inline_evidence_preserves_exact_hash_and_orphan_links_fail(
    service: PersistenceService,
) -> None:
    scope = project_scope()
    service.scopes.create(scope)
    envelope = ordinary_record(20, scope.scope_id)
    service.records.create(envelope)
    item = EvidenceItem.inline_text(
        evidence_id=uid(21),
        evidence_kind="document",
        content="exact\nbytes",
        captured_at=NOW,
        sensitivity_class="internal",
    )

    service.evidence.create(item)

    stored = service.evidence.get(item.evidence_id)
    assert stored["content_hash"] == item.content_hash
    assert stored["byte_length"] == len("exact\nbytes".encode("utf-8"))
    assert stored["inline_content"] == "exact\nbytes"
    with pytest.raises(ConflictError):
        service.evidence.link(
            EvidenceLink(
                record_id=envelope.record_id,
                evidence_id=uid(999),
                relationship="supports",
            )
        )


def test_noninline_metadata_integrity_is_fail_closed_on_insert_and_update(
    service: PersistenceService,
) -> None:
    with pytest.raises(ValidationError, match="metadata-only non-inline"):
        EvidenceItem(
            evidence_id=uid(22),
            evidence_kind="document",
            storage_kind="local_file",
            captured_at=NOW,
            integrity_status="valid",
            redaction_status="none",
            sensitivity_class="internal",
            privacy_class="none",
            storage_location="fixtures/document.txt",
            byte_length=12,
            content_hash="0" * 64,
        )

    with pytest.raises(ConflictError):
        SqlProbe(service.config).write(
            lambda connection: connection.execute(
                """
                INSERT INTO evidence_items (
                    evidence_id, evidence_kind, storage_kind, storage_location,
                    byte_length, content_hash, captured_at, integrity_status,
                    redaction_status, sensitivity_class, privacy_class
                ) VALUES (
                    ?, 'document', 'local_file', 'fixtures/document.txt',
                    12, ?, ?, 'valid', 'none', 'internal', 'none'
                )
                """,
                (uid(22), "0" * 64, NOW),
            )
        )

    item = EvidenceItem(
        evidence_id=uid(23),
        evidence_kind="document",
        storage_kind="local_file",
        captured_at=NOW,
        integrity_status="unavailable",
        redaction_status="none",
        sensitivity_class="internal",
        privacy_class="none",
        storage_location="fixtures/document.txt",
        byte_length=12,
        content_hash="0" * 64,
    )
    service.evidence.create(item)

    assert service.evidence.get(item.evidence_id)["integrity_status"] == "unavailable"
    probe = SqlProbe(service.config)

    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE evidence_items
                SET integrity_status = 'valid'
                WHERE evidence_id = ?
                """,
                (item.evidence_id,),
            )
        )
    assert service.evidence.get(item.evidence_id)["integrity_status"] == "unavailable"

    probe.write(
        lambda connection: connection.execute(
            """
            UPDATE evidence_items
            SET integrity_status = 'mismatch'
            WHERE evidence_id = ?
            """,
            (item.evidence_id,),
        )
    )
    assert service.evidence.get(item.evidence_id)["integrity_status"] == "mismatch"

    for prohibited_status in ("unavailable", "valid"):
        with pytest.raises(ConflictError):
            probe.write(
                lambda connection, status=prohibited_status: connection.execute(
                    """
                    UPDATE evidence_items
                    SET integrity_status = ?
                    WHERE evidence_id = ?
                    """,
                    (status, item.evidence_id),
                )
            )
    assert service.evidence.get(item.evidence_id)["integrity_status"] == "mismatch"


def test_anchor_registration_hash_kind_stability_and_scope_fk(
    service: PersistenceService,
) -> None:
    scope = project_scope()
    service.scopes.create(scope)
    anchor = ReferenceAnchor(
        reference_id=uid(30),
        reference_kind="evaluation_experiment",
        project_scope_id=scope.scope_id,
        created_at=NOW,
        provenance_json=canonical_json_text({"source": "fixture"}),
    )

    digest = service.reference_anchors.register(anchor)

    assert digest == sha256_canonical_json(anchor.hash_material())
    assert service.reference_anchors.get(anchor.reference_id)["content_hash"] == digest
    with pytest.raises(ConflictError):
        SqlProbe(service.config).write(
            lambda connection: connection.execute(
                """
                UPDATE governed_reference_anchors
                SET provenance_json = ?
                WHERE reference_id = ?
                """,
                (
                    canonical_json_text({"source": "rewritten"}),
                    anchor.reference_id,
                ),
            )
        )
    assert (
        service.reference_anchors.get(anchor.reference_id)["provenance_json"]
        == anchor.provenance_json
    )
    with pytest.raises(ConflictError):
        service.reference_anchors.register(anchor)
    with pytest.raises(ConflictError):
        service.reference_anchors.register(
            ReferenceAnchor(
                reference_id=anchor.reference_id,
                reference_kind="model_invocation",
                project_scope_id=scope.scope_id,
                created_at=NOW,
                provenance_json=canonical_json_text({"source": "changed-kind"}),
            )
        )
    with pytest.raises(ConflictError):
        service.reference_anchors.register(
            ReferenceAnchor(
                reference_id=uid(31),
                reference_kind="evaluation_fixture",
                project_scope_id=uid(999),
                created_at=NOW,
                provenance_json=canonical_json_text({"source": "orphan"}),
            )
        )
    with pytest.raises(ValidationError, match="reference_kind"):
        ReferenceAnchor(
            reference_id=uid(32),
            reference_kind="invented_kind",
            project_scope_id=scope.scope_id,
            created_at=NOW,
            provenance_json=canonical_json_text({"source": "invalid-kind"}),
        )


def test_i1_ownerless_claim_is_rejected_without_weakening_other_transitions(
    service: PersistenceService,
) -> None:
    scope = project_scope()
    service.scopes.create(scope)
    anchors = tuple(
        ReferenceAnchor(
            reference_id=uid(number),
            reference_kind="context_manifest",
            project_scope_id=scope.scope_id,
            created_at=NOW,
            provenance_json=canonical_json_text({"fixture": number}),
        )
        for number in (33, 34)
    )
    for anchor in anchors:
        service.reference_anchors.register(anchor)
    probe = SqlProbe(service.config)

    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE governed_reference_anchors
                SET lifecycle_state = 'claimed'
                WHERE reference_id = ?
                """,
                (anchors[0].reference_id,),
            )
        )
    assert (
        service.reference_anchors.get(anchors[0].reference_id)["lifecycle_state"]
        == "registered"
    )

    probe.write(
        lambda connection: connection.execute(
            """
            UPDATE governed_reference_anchors
            SET lifecycle_state = 'invalid'
            WHERE reference_id = ?
            """,
            (anchors[0].reference_id,),
        )
    )
    probe.write(
        lambda connection: connection.execute(
            """
            UPDATE governed_reference_anchors
            SET lifecycle_state = 'retired'
            WHERE reference_id = ?
            """,
            (anchors[0].reference_id,),
        )
    )
    probe.write(
        lambda connection: connection.execute(
            """
            UPDATE governed_reference_anchors
            SET lifecycle_state = 'retired'
            WHERE reference_id = ?
            """,
            (anchors[1].reference_id,),
        )
    )

    assert {
        service.reference_anchors.get(anchor.reference_id)["lifecycle_state"]
        for anchor in anchors
    } == {"retired"}


def test_valid_controlled_resilience_bundle_is_atomic_and_incomplete(
    service: PersistenceService,
) -> None:
    scope = project_scope()
    service.scopes.create(scope)
    envelope, payload, anchors, evidence = controlled_components(
        scope_id=scope.scope_id
    )

    digest = service.controlled_resilience.create(
        envelope,
        payload,
        anchors=anchors,
        evidence_items=evidence,
    )

    stored = service.controlled_resilience.get(envelope.record_id)
    assert stored["content_hash"] == digest
    assert stored["completion_state"] == "incomplete"
    assert stored["ordinary_memory_eligibility"] == "prohibited"
    assert stored["identity_eligibility"] == "prohibited"
    for item in evidence:
        stored_evidence = service.evidence.get(item.evidence_id)
        assert stored_evidence["storage_kind"] == "inline_text"
        assert stored_evidence["integrity_status"] == "valid"
        assert stored_evidence["content_hash"] == item.content_hash
    counts = SqlProbe(service.config).read(
        lambda connection: tuple(
            connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM governed_reference_anchors),
                    (SELECT COUNT(*) FROM evidence_items),
                    (SELECT COUNT(*) FROM record_evidence_links)
                """
            ).fetchone()
        )
    )
    assert counts == (4, 2, 2)


def test_mandatory_controlled_links_are_immutable_but_ordinary_links_are_governable(
    service: PersistenceService,
) -> None:
    scope = project_scope()
    service.scopes.create(scope)
    envelope, payload, anchors, evidence = controlled_components(
        scope_id=scope.scope_id,
        base=150,
    )
    service.controlled_resilience.create(
        envelope,
        payload,
        anchors=anchors,
        evidence_items=evidence,
    )
    probe = SqlProbe(service.config)

    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE record_evidence_links
                SET relationship = 'does_not_establish'
                WHERE record_id = ? AND evidence_id = ?
                  AND relationship = 'evaluated_against'
                """,
                (envelope.record_id, payload.raw_prompt_evidence_id),
            )
        )
    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE record_evidence_links
                SET relationship = 'does_not_establish'
                WHERE record_id = ? AND evidence_id = ?
                  AND relationship = 'produced_as'
                """,
                (envelope.record_id, payload.raw_output_evidence_id),
            )
        )
    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                """
                DELETE FROM record_evidence_links
                WHERE record_id = ? AND evidence_id = ?
                  AND relationship = 'produced_as'
                """,
                (envelope.record_id, payload.raw_output_evidence_id),
            )
        )

    ordinary = ordinary_record(160, scope.scope_id)
    ordinary_evidence = EvidenceItem.inline_text(
        evidence_id=uid(161),
        evidence_kind="document",
        content="ordinary evidence",
        captured_at=NOW,
        sensitivity_class="internal",
    )
    service.records.create(ordinary)
    service.evidence.create(ordinary_evidence)
    service.evidence.link(
        EvidenceLink(
            record_id=ordinary.record_id,
            evidence_id=ordinary_evidence.evidence_id,
            relationship="supports",
        )
    )

    def update_ordinary_link(connection) -> None:
        connection.execute(
            """
            UPDATE record_evidence_links
            SET relationship = 'contextualises'
            WHERE record_id = ? AND evidence_id = ?
              AND relationship = 'supports'
            """,
            (ordinary.record_id, ordinary_evidence.evidence_id),
        )

    probe.write(update_ordinary_link)
    updated_relationship = probe.read(
        lambda connection: connection.execute(
            """
            SELECT relationship FROM record_evidence_links
            WHERE record_id = ? AND evidence_id = ?
            """,
            (ordinary.record_id, ordinary_evidence.evidence_id),
        ).fetchone()[0]
    )
    assert updated_relationship == "contextualises"
    probe.write(
        lambda connection: connection.execute(
            """
            DELETE FROM record_evidence_links
            WHERE record_id = ? AND evidence_id = ?
              AND relationship = 'contextualises'
            """,
            (ordinary.record_id, ordinary_evidence.evidence_id),
        )
    )
    remaining = probe.read(
        lambda connection: connection.execute(
            """
            SELECT COUNT(*) FROM record_evidence_links
            WHERE record_id = ? AND evidence_id = ?
            """,
            (ordinary.record_id, ordinary_evidence.evidence_id),
        ).fetchone()[0]
    )
    assert remaining == 0


def test_controlled_evidence_link_updates_validate_the_complete_new_row(
    service: PersistenceService,
) -> None:
    scope = project_scope()
    service.scopes.create(scope)
    envelope, payload, anchors, evidence = controlled_components(
        scope_id=scope.scope_id,
        base=170,
    )
    service.controlled_resilience.create(
        envelope,
        payload,
        anchors=anchors,
        evidence_items=evidence,
    )
    ordinary = ordinary_record(180, scope.scope_id)
    ordinary_evidence = EvidenceItem.inline_text(
        evidence_id=uid(181),
        evidence_kind="document",
        content="ordinary update source",
        captured_at=NOW,
        sensitivity_class="internal",
    )
    service.records.create(ordinary)
    service.evidence.create(ordinary_evidence)
    service.evidence.link(
        EvidenceLink(
            record_id=ordinary.record_id,
            evidence_id=ordinary_evidence.evidence_id,
            relationship="supports",
        )
    )
    for evidence_id in (
        payload.raw_prompt_evidence_id,
        payload.raw_output_evidence_id,
    ):
        service.evidence.link(
            EvidenceLink(
                record_id=envelope.record_id,
                evidence_id=evidence_id,
                relationship="does_not_establish",
            )
        )
    probe = SqlProbe(service.config)

    for controlled_evidence_id in (
        payload.raw_prompt_evidence_id,
        payload.raw_output_evidence_id,
    ):
        with pytest.raises(ConflictError):
            probe.write(
                lambda connection, evidence_id=controlled_evidence_id: (
                    connection.execute(
                        """
                        UPDATE record_evidence_links
                        SET evidence_id = ?
                        WHERE record_id = ? AND evidence_id = ?
                          AND relationship = 'supports'
                        """,
                        (
                            evidence_id,
                            ordinary.record_id,
                            ordinary_evidence.evidence_id,
                        ),
                    )
                )
            )
        original = probe.read(
            lambda connection: connection.execute(
                """
                SELECT evidence_id, relationship
                FROM record_evidence_links
                WHERE record_id = ?
                """,
                (ordinary.record_id,),
            ).fetchone()
        )
        assert tuple(original) == (ordinary_evidence.evidence_id, "supports")

    for controlled_evidence_id in (
        payload.raw_prompt_evidence_id,
        payload.raw_output_evidence_id,
    ):
        with pytest.raises(ConflictError):
            probe.write(
                lambda connection, evidence_id=controlled_evidence_id: (
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
                            evidence_id,
                        ),
                    )
                )
            )
        original_record_id = probe.read(
            lambda connection, evidence_id=controlled_evidence_id: (
                connection.execute(
                    """
                    SELECT record_id
                    FROM record_evidence_links
                    WHERE evidence_id = ?
                      AND relationship = 'does_not_establish'
                    """,
                    (evidence_id,),
                ).fetchone()[0]
            )
        )
        assert original_record_id == envelope.record_id

    for invalid_relationship in (
        "supports",
        "derived_from",
        "contextualises",
        "contradicts",
    ):
        with pytest.raises(ConflictError):
            probe.write(
                lambda connection, relationship=invalid_relationship: (
                    connection.execute(
                        """
                        UPDATE record_evidence_links
                        SET relationship = ?
                        WHERE record_id = ? AND evidence_id = ?
                          AND relationship = 'does_not_establish'
                        """,
                        (
                            relationship,
                            envelope.record_id,
                            payload.raw_prompt_evidence_id,
                        ),
                    )
                )
            )
    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE record_evidence_links
                SET relationship = 'supports'
                WHERE record_id = ? AND evidence_id = ?
                  AND relationship = 'does_not_establish'
                """,
                (envelope.record_id, payload.raw_output_evidence_id),
            )
        )

    preserved = probe.read(
        lambda connection: {
            (row["evidence_id"], row["relationship"])
            for row in connection.execute(
                """
                SELECT evidence_id, relationship
                FROM record_evidence_links
                WHERE record_id = ?
                  AND relationship = 'does_not_establish'
                """,
                (envelope.record_id,),
            )
        }
    )
    assert preserved == {
        (payload.raw_prompt_evidence_id, "does_not_establish"),
        (payload.raw_output_evidence_id, "does_not_establish"),
    }


@pytest.mark.parametrize("missing_index", range(4))
def test_missing_typed_anchor_rolls_back_every_supplied_component(
    service: PersistenceService,
    missing_index: int,
) -> None:
    scope = project_scope()
    service.scopes.create(scope)
    envelope, payload, anchors, evidence = controlled_components(
        scope_id=scope.scope_id,
        base=200,
    )
    supplied = anchors[:missing_index] + anchors[missing_index + 1 :]

    with pytest.raises(ConflictError):
        service.controlled_resilience.create(
            envelope,
            payload,
            anchors=supplied,
            evidence_items=evidence,
        )

    counts = SqlProbe(service.config).read(
        lambda connection: tuple(
            connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM governed_reference_anchors),
                    (SELECT COUNT(*) FROM evidence_items),
                    (SELECT COUNT(*) FROM records),
                    (SELECT COUNT(*) FROM controlled_resilience_evidence)
                """
            ).fetchone()
        )
    )
    assert counts == (0, 0, 0, 0)


@pytest.mark.parametrize("missing_evidence_index", [0, 1])
def test_missing_raw_evidence_rolls_back_anchors_and_record(
    service: PersistenceService,
    missing_evidence_index: int,
) -> None:
    scope = project_scope()
    service.scopes.create(scope)
    envelope, payload, anchors, evidence = controlled_components(
        scope_id=scope.scope_id,
        base=300,
    )
    supplied = evidence[:missing_evidence_index] + evidence[missing_evidence_index + 1 :]

    with pytest.raises(ValidationError, match="evidence is missing"):
        service.controlled_resilience.create(
            envelope,
            payload,
            anchors=anchors,
            evidence_items=supplied,
        )

    counts = SqlProbe(service.config).read(
        lambda connection: tuple(
            connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM governed_reference_anchors),
                    (SELECT COUNT(*) FROM records)
                """
            ).fetchone()
        )
    )
    assert counts == (0, 0)


def test_cross_scope_anchors_are_rejected_atomically(
    service: PersistenceService,
) -> None:
    first_scope = project_scope()
    second_scope = project_scope(2, name="other-project")
    service.scopes.create(first_scope)
    service.scopes.create(second_scope)
    envelope, payload, anchors, evidence = controlled_components(
        scope_id=first_scope.scope_id,
        base=400,
        recovery_record_id=uid(499),
    )
    cross_scope_anchor = ReferenceAnchor(
        reference_id=anchors[0].reference_id,
        reference_kind=anchors[0].reference_kind,
        project_scope_id=second_scope.scope_id,
        created_at=NOW,
        provenance_json=anchors[0].provenance_json,
    )

    with pytest.raises(ConflictError):
        service.controlled_resilience.create(
            envelope,
            payload,
            anchors=(cross_scope_anchor,) + anchors[1:],
            evidence_items=evidence,
        )

    assert SqlProbe(service.config).read(
        lambda connection: connection.execute(
            "SELECT COUNT(*) FROM records"
        ).fetchone()[0]
    ) == 0


def test_orphan_recovery_record_is_rejected_atomically(
    service: PersistenceService,
) -> None:
    scope = project_scope()
    service.scopes.create(scope)
    envelope, payload, anchors, evidence = controlled_components(
        scope_id=scope.scope_id,
        base=450,
        recovery_record_id=uid(499),
    )

    with pytest.raises(ConflictError):
        service.controlled_resilience.create(
            envelope,
            payload,
            anchors=anchors,
            evidence_items=evidence,
        )

    counts = SqlProbe(service.config).read(
        lambda connection: tuple(
            connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM governed_reference_anchors),
                    (SELECT COUNT(*) FROM evidence_items),
                    (SELECT COUNT(*) FROM records)
                """
            ).fetchone()
        )
    )
    assert counts == (0, 0, 0)


def test_classification_kind_and_pass_weakening_are_rejected(
    service: PersistenceService,
) -> None:
    scope = project_scope()
    service.scopes.create(scope)
    envelope, payload, anchors, evidence = controlled_components(
        scope_id=scope.scope_id,
        base=500,
    )
    service.controlled_resilience.create(
        envelope,
        payload,
        anchors=anchors,
        evidence_items=evidence,
    )

    for statement in (
        """
        UPDATE records SET sensitivity_class = 'internal'
        WHERE record_id = ?
        """,
        """
        UPDATE records
        SET retrieval_policy_json =
            '{"ordinary_memory_eligibility":"allowed","retrieval_mode":"ordinary"}'
        WHERE record_id = ?
        """,
        """
        UPDATE records SET training_eligibility = 'approved'
        WHERE record_id = ?
        """,
        """
        UPDATE controlled_resilience_evidence
        SET ordinary_memory_eligibility = 'allowed'
        WHERE record_id = ?
        """,
        """
        UPDATE controlled_resilience_evidence
        SET identity_eligibility = 'allowed'
        WHERE record_id = ?
        """,
        """
        UPDATE controlled_resilience_evidence
        SET experiment_reference_kind = 'model_invocation'
        WHERE record_id = ?
        """,
        """
        UPDATE controlled_resilience_evidence
        SET completion_state = 'passed'
        WHERE record_id = ?
        """,
    ):
        with pytest.raises(ConflictError):
            SqlProbe(service.config).write(
                lambda connection, sql=statement: connection.execute(
                    sql,
                    (envelope.record_id,),
                )
            )

    stored = service.controlled_resilience.get(envelope.record_id)
    assert stored["sensitivity_class"] == "restricted"
    assert stored["experiment_reference_kind"] == "evaluation_experiment"
    assert stored["completion_state"] == "incomplete"


def test_raw_controlled_evidence_cannot_support_an_ordinary_record(
    service: PersistenceService,
) -> None:
    scope = project_scope()
    service.scopes.create(scope)
    envelope, payload, anchors, evidence = controlled_components(
        scope_id=scope.scope_id,
        base=550,
    )
    service.controlled_resilience.create(
        envelope,
        payload,
        anchors=anchors,
        evidence_items=evidence,
    )
    ordinary = ordinary_record(560, scope.scope_id)
    service.records.create(ordinary)

    with pytest.raises(ConflictError):
        service.evidence.link(
            EvidenceLink(
                record_id=ordinary.record_id,
                evidence_id=payload.raw_prompt_evidence_id,
                relationship="supports",
            )
        )


def test_prelinked_evidence_cannot_be_reclassified_as_raw_controlled(
    service: PersistenceService,
) -> None:
    scope = project_scope()
    service.scopes.create(scope)
    envelope, payload, anchors, evidence = controlled_components(
        scope_id=scope.scope_id,
        base=570,
    )
    ordinary = ordinary_record(580, scope.scope_id)
    service.records.create(ordinary)
    for item in evidence:
        service.evidence.create(item)
    service.evidence.link(
        EvidenceLink(
            record_id=ordinary.record_id,
            evidence_id=payload.raw_prompt_evidence_id,
            relationship="supports",
        )
    )

    with pytest.raises(ConflictError):
        service.controlled_resilience.create(
            envelope,
            payload,
            anchors=anchors,
        )

    anchor_count = SqlProbe(service.config).read(
        lambda connection: connection.execute(
            "SELECT COUNT(*) FROM governed_reference_anchors"
        ).fetchone()[0]
    )
    assert anchor_count == 0


def test_anchor_existence_never_masquerades_as_execution_or_completion(
    service: PersistenceService,
) -> None:
    scope = project_scope()
    service.scopes.create(scope)
    _, _, anchors, _ = controlled_components(scope_id=scope.scope_id, base=600)
    for anchor in anchors:
        service.reference_anchors.register(anchor)

    anchor_states, payload_count = SqlProbe(service.config).read(
        lambda connection: (
            {
                row[0]
                for row in connection.execute(
                    "SELECT lifecycle_state FROM governed_reference_anchors"
                )
            },
            connection.execute(
                "SELECT COUNT(*) FROM controlled_resilience_evidence"
            ).fetchone()[0],
        )
    )

    assert anchor_states == {"registered"}
    assert payload_count == 0


def test_later_claim_semantics_are_additive_without_rewriting_i1(
    tmp_path: Path,
) -> None:
    migration_directory = tmp_path / "migrations"
    migration_directory.mkdir()
    for source in default_migrations_path().glob("*.sql"):
        (migration_directory / source.name).write_bytes(source.read_bytes())
    config = DatabaseConfig(tmp_path / "later-claim.sqlite3")
    runner = MigrationRunner(config, migration_directory)
    discovered_before = runner.discover()
    runner.apply_all()
    service = PersistenceService(config)
    scope = project_scope()
    other_scope = project_scope(2, name="other-project")
    service.scopes.create(scope)
    service.scopes.create(other_scope)
    anchor = ReferenceAnchor(
        reference_id=uid(700),
        reference_kind="context_manifest",
        project_scope_id=scope.scope_id,
        created_at=NOW,
        provenance_json=canonical_json_text({"operation_executed": False}),
    )
    service.reference_anchors.register(anchor)
    probe = SqlProbe(config)

    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE governed_reference_anchors
                SET lifecycle_state = 'claimed'
                WHERE reference_id = ? AND reference_kind = ?
                """,
                (anchor.reference_id, anchor.reference_kind),
            )
        )
    assert service.reference_anchors.get(anchor.reference_id)["lifecycle_state"] == (
        "registered"
    )

    (migration_directory / "0007_later_claim_probe.sql").write_text(
        """
        CREATE TABLE later_claim_probe (
            reference_id TEXT NOT NULL,
            reference_kind TEXT NOT NULL,
            project_scope_id TEXT NOT NULL,
            PRIMARY KEY (reference_id, reference_kind),
            FOREIGN KEY (
                reference_id, reference_kind, project_scope_id
            )
                REFERENCES governed_reference_anchors (
                    reference_id, reference_kind, project_scope_id
                ) ON DELETE RESTRICT,
            FOREIGN KEY (project_scope_id)
                REFERENCES scopes(scope_id) ON DELETE RESTRICT
        );

        DROP TRIGGER governed_reference_anchor_ownerless_claim;

        CREATE TRIGGER governed_reference_anchor_claim_requires_owner
        BEFORE UPDATE OF lifecycle_state ON governed_reference_anchors
        WHEN OLD.lifecycle_state <> 'claimed'
          AND NEW.lifecycle_state = 'claimed'
          AND NOT EXISTS (
              SELECT 1
              FROM later_claim_probe AS owner
              WHERE owner.reference_id = NEW.reference_id
                AND owner.reference_kind = NEW.reference_kind
                AND owner.project_scope_id = NEW.project_scope_id
          )
        BEGIN
            SELECT RAISE(
                ABORT,
                'claimed anchor requires a matching operational owner'
            );
        END;
        """,
        encoding="utf-8",
        newline="\n",
    )
    assert runner.discover()[:6] == discovered_before
    runner.apply_all()

    def invalid_owner_then_claim(connection) -> None:
        connection.execute(
            """
            INSERT INTO later_claim_probe (
                reference_id, reference_kind, project_scope_id
            ) VALUES (?, ?, ?)
            """,
            (
                anchor.reference_id,
                anchor.reference_kind,
                other_scope.scope_id,
            ),
        )
        connection.execute(
            """
            UPDATE governed_reference_anchors
            SET lifecycle_state = 'claimed'
            WHERE reference_id = ? AND reference_kind = ?
            """,
            (anchor.reference_id, anchor.reference_kind),
        )

    with pytest.raises(ConflictError):
        probe.write(invalid_owner_then_claim)
    assert service.reference_anchors.get(anchor.reference_id)["lifecycle_state"] == (
        "registered"
    )

    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE governed_reference_anchors
                SET lifecycle_state = 'claimed'
                WHERE reference_id = ? AND reference_kind = ?
                """,
                (anchor.reference_id, anchor.reference_kind),
            )
        )
    assert service.reference_anchors.get(anchor.reference_id)["lifecycle_state"] == (
        "registered"
    )

    def claim_probe(connection) -> None:
        connection.execute(
            """
            INSERT INTO later_claim_probe (
                reference_id, reference_kind, project_scope_id
            ) VALUES (?, ?, ?)
            """,
            (
                anchor.reference_id,
                anchor.reference_kind,
                anchor.project_scope_id,
            ),
        )
        connection.execute(
            """
            UPDATE governed_reference_anchors
            SET lifecycle_state = 'claimed'
            WHERE reference_id = ? AND reference_kind = ?
            """,
            (anchor.reference_id, anchor.reference_kind),
        )

    probe.write(claim_probe)

    assert service.reference_anchors.get(anchor.reference_id)["lifecycle_state"] == "claimed"
    assert runner.discover()[:6] == discovered_before
