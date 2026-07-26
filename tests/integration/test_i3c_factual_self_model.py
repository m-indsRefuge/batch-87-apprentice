from __future__ import annotations

from pathlib import Path
import sqlite3
from dataclasses import replace
import os
import subprocess
import sys

import pytest

from batch87_apprentice.common.errors import (
    ConflictError,
    IntegrityInspectionError,
    ValidationError,
)
from batch87_apprentice.governance.contracts import (
    active_b87_s1_permission_profile,
)
from batch87_apprentice.memory import (
    RuntimeSubstrateAttestation,
    TrustedRuntimeAttestor,
)
from batch87_apprentice.persistence.contracts import (
    Entity,
    EvidenceItem,
    RuntimeInstance,
    Scope,
)
from batch87_apprentice.persistence.service import PersistenceService
from tests.support.i2_fixtures import NOW, authority, evidence, task, uid
from tests.support.i3c_fixtures import (
    approval_grant,
    build_c1_harness,
    capability_components,
    create_capability_policy,
    create_maturity_policy,
    maturity_components,
    ingest_runtime_attestation,
    register_evaluation,
    register_nolan_byte_authority,
    register_trusted_runtime_attestor,
    runtime_identity_components,
    supersession_components,
)


def persist_runtime_identity(
    harness,
    envelope,
    payload,
    links,
    *,
    base: int,
):
    return harness.persistence.self_episodic_memory.create_runtime_identity(
        envelope,
        payload,
        initial_lifecycle_transition_id=uid(base + 2),
        initial_approval_transition_id=uid(base + 3),
        reviewed_transition_id=uid(base + 4),
        approved_transition_id=uid(base + 5),
        active_transition_id=uid(base + 6),
        evidence_links=links,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )


def create_runtime_identity(
    harness,
    *,
    base: int = 210_000,
    trusted: TrustedRuntimeAttestor | None = None,
):
    if trusted is None:
        trusted, _, _ = register_trusted_runtime_attestor(
            harness,
            base=base + 20,
        )
    envelope, payload, attestation, evidence_item, links = (
        runtime_identity_components(
            harness,
            base=base,
            trusted_attestor=trusted,
        )
    )
    ingest_runtime_attestation(harness, attestation, evidence_item)
    digest = persist_runtime_identity(
        harness,
        envelope,
        payload,
        links,
        base=base,
    )
    return envelope, payload, digest, trusted


def test_runtime_identity_requires_exact_attestation_and_reconstructs_after_reopen(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    bad_trusted, _, _ = register_trusted_runtime_attestor(
        harness,
        base=210_140,
    )
    (
        bad_envelope,
        bad_payload,
        bad_attestation,
        bad_evidence,
        bad_links,
    ) = runtime_identity_components(
        harness,
        base=210_100,
        trusted_attestor=bad_trusted,
    )
    ingest_runtime_attestation(harness, bad_attestation, bad_evidence)
    bad_payload = type(bad_payload)(
        **{
            field: (
                "wrong/revision"
                if field == "model_revision"
                else getattr(bad_payload, field)
            )
            for field in bad_payload.__dataclass_fields__
            if field not in {"RECORD_TYPE", "TABLE"}
        }
    )
    with pytest.raises(ValidationError, match="does not exactly match"):
        harness.persistence.self_episodic_memory.create_runtime_identity(
            bad_envelope,
            bad_payload,
            initial_lifecycle_transition_id=uid(210_102),
            initial_approval_transition_id=uid(210_103),
            reviewed_transition_id=uid(210_104),
            approved_transition_id=uid(210_105),
            active_transition_id=uid(210_106),
            evidence_links=bad_links,
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )

    envelope, payload, digest, _ = create_runtime_identity(
        harness,
        trusted=bad_trusted,
    )
    reconstructed = harness.persistence.self_episodic_memory.reconstruct(
        payload.record_id,
        permission_profile=active_b87_s1_permission_profile(),
        permission_effective_at=NOW,
    )
    reopened = PersistenceService(harness.config)
    after_reopen = reopened.self_episodic_memory.reconstruct(payload.record_id)

    assert reconstructed["memory_domain"] == "self_episodic"
    assert reconstructed["payload"] == payload.canonical_content()
    assert reconstructed["record"]["lifecycle_state"] == "active"
    assert reconstructed["record"]["approval_status"] == "not_required"
    assert reconstructed["content_hash"] == digest
    assert reconstructed["content_hash"] == reconstructed[
        "recomputed_content_hash"
    ]
    assert reconstructed["permission_profile_projection"]["applicable"]
    assert reconstructed["runtime_instance"]["status"] == "running"
    assert reconstructed["runtime_substrate_attestation"][
        "context_limit"
    ] == payload.context_limit
    assert reconstructed["trusted_runtime_attestor"][
        "attestor_entity_id"
    ] == payload.substrate_attestor_entity_id
    assert reconstructed["integrity"]["valid"]
    assert after_reopen["payload"] == reconstructed["payload"]
    assert after_reopen["recomputed_content_hash"] == digest


def test_runtime_identity_evidence_link_is_exact_and_immutable(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    _, payload, _, trusted = create_runtime_identity(
        harness,
        base=210_200,
    )
    connection = sqlite3.connect(harness.config.path)
    try:
        links = connection.execute(
            """
            SELECT evidence_id, relationship
            FROM record_evidence_links
            WHERE record_id = ?
            ORDER BY evidence_id, relationship
            """,
            (payload.record_id,),
        ).fetchall()
        assert links == [
            (payload.substrate_attestation_evidence_id, "supports")
        ]

        with pytest.raises(sqlite3.IntegrityError, match="exactly one supporting"):
            connection.execute(
                """
                INSERT INTO record_evidence_links (
                    record_id, evidence_id, relationship, explanation
                ) VALUES (?, ?, 'contradicts', 'invalid semantic duplicate')
                """,
                (
                    payload.record_id,
                    payload.substrate_attestation_evidence_id,
                ),
            )
        with pytest.raises(sqlite3.IntegrityError, match="exactly one supporting"):
            connection.execute(
                """
                INSERT INTO record_evidence_links (
                    record_id, evidence_id, relationship, explanation
                ) VALUES (?, ?, 'supports', 'invalid additional evidence')
                """,
                (payload.record_id, trusted.approval_evidence_id),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """
                UPDATE record_evidence_links
                SET relationship = 'contextualises'
                WHERE record_id = ?
                """,
                (payload.record_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            connection.execute(
                """
                DELETE FROM record_evidence_links
                WHERE record_id = ?
                """,
                (payload.record_id,),
            )
    finally:
        connection.close()


def test_runtime_identity_reconstructs_exactly_in_a_separate_process(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    _, payload, digest, _ = create_runtime_identity(
        harness,
        base=210_250,
    )
    script = """
import sys
from pathlib import Path
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.service import PersistenceService

result = PersistenceService(DatabaseConfig(Path(sys.argv[1]))).self_episodic_memory.reconstruct(sys.argv[2])
assert result["content_hash"] == sys.argv[3]
assert result["recomputed_content_hash"] == sys.argv[3]
assert result["payload"]["context_limit"] > 0
assert result["runtime_substrate_attestation"]["attestation_environment"] == "production"
assert result["trusted_runtime_attestor"]["status"] == "active"
assert result["integrity"]["valid"]
print(result["content_hash"])
"""
    environment = os.environ.copy()
    source_path = str(Path(__file__).resolve().parents[2] / "src")
    environment["PYTHONPATH"] = (
        source_path
        if not environment.get("PYTHONPATH")
        else source_path + os.pathsep + environment["PYTHONPATH"]
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(harness.config.path),
            payload.record_id,
            digest,
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == digest


def test_runtime_identity_fails_closed_without_registry_or_dedicated_support(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    unregistered = TrustedRuntimeAttestor(
        trusted_attestor_id=uid(210_300),
        attestor_entity_id=harness.i2.participant_id,
        project_scope_id=harness.project_scope_id,
        attestation_environment="production",
        authority_record_id=uid(210_301),
        approval_evidence_id=uid(210_302),
        registered_by_principal="operator",
        registered_by_entity_id=harness.operator_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        effective_from=NOW,
    )
    envelope, payload, attestation, evidence_item, links = (
        runtime_identity_components(
            harness,
            base=210_310,
            trusted_attestor=unregistered,
        )
    )
    connection = sqlite3.connect(harness.config.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM trusted_runtime_attestors"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM runtime_substrate_attestations"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM runtime_identities"
        ).fetchone()[0] == 0
    finally:
        connection.close()

    with pytest.raises(ValidationError, match="pre-existing dedicated"):
        persist_runtime_identity(
            harness,
            envelope,
            payload,
            links,
            base=210_310,
        )
    with pytest.raises(TypeError, match="evidence_items"):
        harness.persistence.self_episodic_memory.create_runtime_identity(
            envelope,
            payload,
            initial_lifecycle_transition_id=uid(210_312),
            initial_approval_transition_id=uid(210_313),
            reviewed_transition_id=uid(210_314),
            approved_transition_id=uid(210_315),
            active_transition_id=uid(210_316),
            evidence_items=(evidence_item,),  # type: ignore[call-arg]
            evidence_links=links,
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )

    harness.persistence.evidence.create(evidence_item)
    with pytest.raises(ValidationError, match="pre-existing dedicated"):
        persist_runtime_identity(
            harness,
            envelope,
            payload,
            links,
            base=210_310,
        )


def test_attestation_ingestion_enforces_principal_captor_and_no_identity_side_effect(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    trusted, _, _ = register_trusted_runtime_attestor(
        harness,
        base=210_400,
    )
    envelope, payload, attestation, evidence_item, links = (
        runtime_identity_components(
            harness,
            base=210_410,
            trusted_attestor=trusted,
        )
    )
    repository = harness.persistence.self_episodic_memory

    for principal in ("operator", "codex_development_harness"):
        with pytest.raises(ValidationError, match="attribution"):
            repository.ingest_runtime_substrate_attestation(
                attestation,
                evidence_item,
                changed_by_principal=principal,
                changed_by_entity_id=trusted.attestor_entity_id,
            )
    with pytest.raises(ValidationError, match="attribution"):
        repository.ingest_runtime_substrate_attestation(
            attestation,
            evidence_item,
            changed_by_principal="validated_system",
            changed_by_entity_id=harness.operator_id,
        )
    wrong_captor = EvidenceItem.inline_text(
        evidence_id=evidence_item.evidence_id,
        evidence_kind="system_event",
        content=attestation.canonical_json,
        captured_at=NOW,
        sensitivity_class="internal",
        privacy_class="none",
        captured_by_entity=harness.operator_id,
    )
    with pytest.raises(ValidationError, match="does not exactly match"):
        repository.ingest_runtime_substrate_attestation(
            attestation,
            wrong_captor,
            changed_by_principal="validated_system",
            changed_by_entity_id=trusted.attestor_entity_id,
        )
    _, _, generic_attestation, generic_evidence, _ = (
        runtime_identity_components(
            harness,
            base=210_430,
            trusted_attestor=trusted,
        )
    )
    harness.persistence.evidence.create(generic_evidence)
    with pytest.raises(ValidationError, match="cannot be adopted"):
        repository.ingest_runtime_substrate_attestation(
            generic_attestation,
            generic_evidence,
            changed_by_principal="validated_system",
            changed_by_entity_id=trusted.attestor_entity_id,
        )

    assert ingest_runtime_attestation(
        harness,
        attestation,
        evidence_item,
    ) == attestation.content_hash
    assert ingest_runtime_attestation(
        harness,
        attestation,
        evidence_item,
    ) == attestation.content_hash
    connection = sqlite3.connect(harness.config.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM runtime_substrate_attestations"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM runtime_identities"
        ).fetchone()[0] == 0
    finally:
        connection.close()

    mismatched_payload = replace(payload, context_limit=4096)
    with pytest.raises(ValidationError, match="does not exactly match"):
        persist_runtime_identity(
            harness,
            envelope,
            mismatched_payload,
            links,
            base=210_410,
        )


def test_attestation_ingestion_is_atomic_when_support_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build_c1_harness(tmp_path)
    trusted, _, _ = register_trusted_runtime_attestor(
        harness,
        base=210_450,
    )
    _, _, attestation, evidence_item, _ = runtime_identity_components(
        harness,
        base=210_460,
        trusted_attestor=trusted,
    )
    repository = harness.persistence.self_episodic_memory

    def fail_after_evidence(step: str) -> None:
        if step == "runtime_attestation.evidence":
            raise RuntimeError("injected attestation support failure")

    monkeypatch.setattr(repository, "_after_write_step", fail_after_evidence)
    with pytest.raises(RuntimeError, match="injected"):
        ingest_runtime_attestation(harness, attestation, evidence_item)

    connection = sqlite3.connect(harness.config.path)
    try:
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM evidence_items
            WHERE evidence_id = ?
            """,
            (evidence_item.evidence_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM runtime_substrate_attestations
            WHERE substrate_attestation_evidence_id = ?
            """,
            (evidence_item.evidence_id,),
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_synthetic_attestation_is_distinct_and_cannot_activate_identity(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    synthetic, _, _ = register_trusted_runtime_attestor(
        harness,
        base=210_500,
        attestation_environment="synthetic_validation",
    )
    envelope, payload, attestation, evidence_item, links = (
        runtime_identity_components(
            harness,
            base=210_510,
            trusted_attestor=synthetic,
        )
    )
    assert attestation.changed_by_principal == "codex_development_harness"
    ingest_runtime_attestation(harness, attestation, evidence_item)

    with pytest.raises(ValidationError, match="production"):
        persist_runtime_identity(
            harness,
            envelope,
            payload,
            links,
            base=210_510,
        )
    connection = sqlite3.connect(harness.config.path)
    try:
        environments = tuple(
            row[0]
            for row in connection.execute(
                """
                SELECT attestation_environment
                FROM runtime_substrate_attestations
                """
            )
        )
        assert environments == ("synthetic_validation",)
        assert connection.execute(
            "SELECT COUNT(*) FROM runtime_identities"
        ).fetchone()[0] == 0
    finally:
        connection.close()


@pytest.mark.parametrize("terminal_status", ("revoked", "retired"))
def test_attestor_history_is_immutable_and_terminal_replacement_fails_closed(
    tmp_path: Path,
    terminal_status: str,
) -> None:
    harness = build_c1_harness(tmp_path)
    trusted, _, _ = register_trusted_runtime_attestor(
        harness,
        base=210_600,
    )
    register_trusted_runtime_attestor(
        harness,
        base=210_610,
        status=terminal_status,
        supersedes_trusted_attestor_id=trusted.trusted_attestor_id,
    )
    _, _, attestation, evidence_item, _ = runtime_identity_components(
        harness,
        base=210_620,
        trusted_attestor=trusted,
    )
    with pytest.raises(ValidationError, match="replaced, revoked, or retired"):
        ingest_runtime_attestation(harness, attestation, evidence_item)

    connection = sqlite3.connect(harness.config.path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """
                UPDATE trusted_runtime_attestors
                SET status = 'active'
                WHERE trusted_attestor_id = ?
                """,
                (trusted.trusted_attestor_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            connection.execute(
                """
                DELETE FROM trusted_runtime_attestors
                WHERE trusted_attestor_id = ?
                """,
                (trusted.trusted_attestor_id,),
            )
    finally:
        connection.close()


def test_attestor_registration_rejects_wrong_principal_kind_and_model_approval(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    approval_authority, approval_evidence = register_nolan_byte_authority(
        harness,
        base=210_700,
        content="Exact trusted-attestor approval.",
    )
    trusted = TrustedRuntimeAttestor(
        trusted_attestor_id=uid(210_702),
        attestor_entity_id=harness.i2.participant_id,
        project_scope_id=harness.project_scope_id,
        attestation_environment="production",
        authority_record_id=approval_authority.authority_record_id,
        approval_evidence_id=approval_evidence.evidence_id,
        registered_by_principal="operator",
        registered_by_entity_id=harness.operator_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=NOW,
        effective_from=NOW,
    )
    repository = harness.persistence.self_episodic_memory
    with pytest.raises(ValidationError, match="attribution"):
        repository.register_trusted_runtime_attestor(
            trusted,
            changed_by_principal="codex_development_harness",
            changed_by_entity_id=harness.operator_id,
        )
    with pytest.raises(ValidationError, match="system or component"):
        repository.register_trusted_runtime_attestor(
            replace(
                trusted,
                trusted_attestor_id=uid(210_703),
                attestor_entity_id=harness.operator_id,
            ),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )
    inactive_attestor_id = uid(210_704)
    harness.persistence.entities.create(
        Entity(
            entity_id=inactive_attestor_id,
            entity_kind="system",
            canonical_name="Inactive attestor",
            description="Must never be trusted.",
            status="inactive",
            created_at=NOW,
        )
    )
    with pytest.raises(ValidationError, match="active system"):
        repository.register_trusted_runtime_attestor(
            replace(
                trusted,
                trusted_attestor_id=uid(210_705),
                attestor_entity_id=inactive_attestor_id,
            ),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )
    wrong_project_id = uid(210_706)
    harness.persistence.scopes.create(
        Scope(
            scope_id=wrong_project_id,
            scope_kind="project",
            canonical_name="Wrong project",
            status="active",
        )
    )
    with pytest.raises(ValidationError):
        repository.register_trusted_runtime_attestor(
            replace(
                trusted,
                trusted_attestor_id=uid(210_707),
                project_scope_id=wrong_project_id,
            ),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )

    model_evidence = evidence(
        210_710,
        content="Model output cannot approve a trusted runtime attestor.",
        captured_by_entity=harness.operator_id,
        evidence_kind="model_output",
    )
    model_authority = authority(
        harness.i2,
        210_711,
        evidence_ids=(model_evidence.evidence_id,),
        authority_class="nolan_byte_approved",
        issuer_entity_id=harness.operator_id,
    )
    with pytest.raises(ValidationError, match="valid non-model"):
        harness.runtime.register_authority(
            model_authority,
            evidence_items=(model_evidence,),
        )


def test_expired_attestor_and_stopped_runtime_are_rejected(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    trusted, _, _ = register_trusted_runtime_attestor(
        harness,
        base=210_800,
        effective_until=NOW,
    )
    envelope, payload, attestation, evidence_item, links = (
        runtime_identity_components(
            harness,
            base=210_810,
            trusted_attestor=trusted,
        )
    )
    ingest_runtime_attestation(harness, attestation, evidence_item)
    later_envelope = replace(
        envelope,
        created_at="2026-07-23T13:00:00.000000Z",
    )
    with pytest.raises(ValidationError, match="expired"):
        persist_runtime_identity(
            harness,
            later_envelope,
            payload,
            links,
            base=210_810,
        )

    harness.persistence.runtime_instances.stop(
        harness.runtime_id,
        stopped_at="2026-07-23T13:00:00.000000Z",
    )
    with pytest.raises(ValidationError, match="running runtime"):
        persist_runtime_identity(
            harness,
            envelope,
            payload,
            links,
            base=210_810,
        )


def test_runtime_replacement_is_exact_and_failure_leaves_prior_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build_c1_harness(tmp_path)
    _, prior_payload, _, trusted = create_runtime_identity(
        harness,
        base=211_000,
    )
    replacement_runtime_id = uid(211_100)
    harness.persistence.runtime_instances.start(
        RuntimeInstance(
            runtime_instance_id=replacement_runtime_id,
            started_at=NOW,
            application_version="b87-i3c1-test",
        )
    )
    (
        envelope,
        payload,
        attestation,
        attestation_evidence,
        links,
    ) = runtime_identity_components(
        harness,
        base=211_110,
        trusted_attestor=trusted,
        runtime_instance_id=replacement_runtime_id,
        supersedes_record_id=prior_payload.record_id,
    )
    ingest_runtime_attestation(
        harness,
        attestation,
        attestation_evidence,
    )
    authority_record, approval_evidence = register_nolan_byte_authority(
        harness,
        base=211_200,
        content="Exact runtime-identity replacement approval.",
    )
    grant, relationship = supersession_components(
        harness,
        source_record_id=payload.record_id,
        target_record_id=prior_payload.record_id,
        authority_record=authority_record,
        approval_evidence=approval_evidence,
        base=211_210,
    )
    repository = harness.persistence.self_episodic_memory
    original_step = repository._after_write_step

    def fail_before_old_state_changes(step: str) -> None:
        if step == "runtime_identity.supersession.consume":
            raise RuntimeError("injected runtime replacement failure")

    monkeypatch.setattr(repository, "_after_write_step", fail_before_old_state_changes)
    with pytest.raises(RuntimeError, match="injected"):
        repository.replace_runtime_identity(
            envelope,
            payload,
            initial_lifecycle_transition_id=uid(211_120),
            initial_approval_transition_id=uid(211_121),
            reviewed_transition_id=uid(211_122),
            approved_transition_id=uid(211_123),
            prior_superseded_transition_id=uid(211_124),
            active_transition_id=uid(211_125),
            relationship_grant=grant,
            relationship=relationship,
            evidence_links=links,
            changed_by_entity_id=harness.operator_id,
        )
    monkeypatch.setattr(repository, "_after_write_step", original_step)

    connection = sqlite3.connect(harness.config.path)
    try:
        prior_state = connection.execute(
            "SELECT lifecycle_state FROM records WHERE record_id = ?",
            (prior_payload.record_id,),
        ).fetchone()[0]
        replacement_count = connection.execute(
            "SELECT COUNT(*) FROM records WHERE record_id = ?",
            (payload.record_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    assert prior_state == "active"
    assert replacement_count == 0

    repository.replace_runtime_identity(
        envelope,
        payload,
        initial_lifecycle_transition_id=uid(211_120),
        initial_approval_transition_id=uid(211_121),
        reviewed_transition_id=uid(211_122),
        approved_transition_id=uid(211_123),
        prior_superseded_transition_id=uid(211_124),
        active_transition_id=uid(211_125),
        relationship_grant=grant,
        relationship=relationship,
        evidence_links=links,
        changed_by_entity_id=harness.operator_id,
    )
    prior = repository.reconstruct(prior_payload.record_id)
    current = repository.reconstruct(payload.record_id)
    assert prior["record"]["lifecycle_state"] == "superseded"
    assert prior["record"]["superseded_by_record_id"] == payload.record_id
    assert current["record"]["lifecycle_state"] == "active"


def test_capability_candidate_activation_enforces_approval_and_model_boundary(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    anchor = register_evaluation(
        harness,
        base=212_000,
        evaluation_kind="capability_evaluation",
    )
    envelope, payload, source, links = capability_components(
        harness,
        base=212_100,
        evaluation_record_ids=(anchor.evaluation_record_id,),
        proposed_by_apprentice=True,
    )
    repository = harness.persistence.self_episodic_memory
    repository.create_capability_observation(
        envelope,
        payload,
        lifecycle_transition_id=uid(212_102),
        approval_transition_id=uid(212_103),
        evidence_items=(source,),
        evidence_links=links,
        changed_by_principal="codex_development_harness",
    )
    authority_record, approval_evidence = register_nolan_byte_authority(
        harness,
        base=212_200,
        content="Exact Nolan-Byte capability approval.",
    )
    grant = approval_grant(
        harness,
        record_id=payload.record_id,
        authority_record=authority_record,
        approval_evidence=approval_evidence,
        base=212_210,
    )

    with pytest.raises(ValidationError, match="active person"):
        repository.activate_capability_observation(
            payload.record_id,
            reviewed_transition_id=uid(212_220),
            approval_grant=grant,
            approval_transition_id=uid(212_221),
            approved_transition_id=uid(212_222),
            active_transition_id=uid(212_223),
            changed_at=NOW,
            changed_by_entity_id=harness.agent_id,
        )
    repository.activate_capability_observation(
        payload.record_id,
        reviewed_transition_id=uid(212_220),
        approval_grant=grant,
        approval_transition_id=uid(212_221),
        approved_transition_id=uid(212_222),
        active_transition_id=uid(212_223),
        changed_at=NOW,
        changed_by_entity_id=harness.operator_id,
    )

    reconstructed = repository.reconstruct(payload.record_id)
    assert reconstructed["record"]["approval_status"] == "approved"
    assert reconstructed["record"]["lifecycle_state"] == "active"
    assert reconstructed["evaluation_anchors"][0]["anchor"][
        "current_state"
    ] == "claimed"
    assert reconstructed["integrity"]["valid"]


def test_higher_capability_stability_requires_multiple_claimed_policy_basis(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    policy, authority_record, approval_evidence = create_capability_policy(
        harness,
        base=213_000,
        minimum_claimed=2,
        minimum_sample=2,
    )
    one_anchor = register_evaluation(
        harness,
        base=213_100,
        evaluation_kind="capability_evaluation",
    )
    envelope, payload, source, links = capability_components(
        harness,
        base=213_200,
        evaluation_record_ids=(one_anchor.evaluation_record_id,),
        stability="emerging",
        developmental_policy_id=policy.developmental_policy_id,
    )
    repository = harness.persistence.self_episodic_memory
    repository.create_capability_observation(
        envelope,
        payload,
        lifecycle_transition_id=uid(213_202),
        approval_transition_id=uid(213_203),
        evidence_items=(source,),
        evidence_links=links,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    grant = approval_grant(
        harness,
        record_id=payload.record_id,
        authority_record=authority_record,
        approval_evidence=approval_evidence,
        base=213_210,
    )
    with pytest.raises(ValidationError, match="one isolated"):
        repository.activate_capability_observation(
            payload.record_id,
            reviewed_transition_id=uid(213_220),
            approval_grant=grant,
            approval_transition_id=uid(213_221),
            approved_transition_id=uid(213_222),
            active_transition_id=uid(213_223),
            changed_at=NOW,
            changed_by_entity_id=harness.operator_id,
        )
    assert repository.reconstruct(payload.record_id)["record"][
        "lifecycle_state"
    ] == "candidate"


def test_maturity_progression_never_changes_i2_permission_projection(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    policy, authority_record, approval_evidence = create_maturity_policy(
        harness,
        base=214_000,
    )
    anchor = register_evaluation(
        harness,
        base=214_100,
        evaluation_kind="maturity_evaluation",
    )
    before = harness.persistence.permission_profile_projection.current_runtime(
        active_b87_s1_permission_profile(),
        effective_at=NOW,
    )
    envelope, payload, source, links = maturity_components(
        harness,
        base=214_200,
        stage="uninitialised",
        basis=(anchor.evaluation_record_id,),
        developmental_policy_id=policy.developmental_policy_id,
    )
    repository = harness.persistence.self_episodic_memory
    repository.create_maturity_state(
        envelope,
        payload,
        lifecycle_transition_id=uid(214_202),
        approval_transition_id=uid(214_203),
        evidence_items=(source,),
        evidence_links=links,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    grant = approval_grant(
        harness,
        record_id=payload.record_id,
        authority_record=authority_record,
        approval_evidence=approval_evidence,
        base=214_210,
    )
    repository.activate_maturity_state(
        payload.record_id,
        approval_grant=grant,
        approval_transition_id=uid(214_220),
        approved_transition_id=uid(214_221),
        active_transition_id=uid(214_222),
        changed_at=NOW,
        changed_by_entity_id=harness.operator_id,
    )
    after = harness.persistence.permission_profile_projection.current_runtime(
        active_b87_s1_permission_profile(),
        effective_at=NOW,
    )

    assert before == after
    assert repository.reconstruct(payload.record_id)["record"][
        "lifecycle_state"
    ] == "active"
    connection = sqlite3.connect(harness.config.path)
    try:
        profile_count = connection.execute(
            "SELECT COUNT(*) FROM permission_profiles"
        ).fetchone()[0]
        permission_memory_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM memory_record_types
            WHERE record_type = 'permission_profile'
            """
        ).fetchone()[0]
    finally:
        connection.close()
    assert profile_count == 1
    assert permission_memory_count == 0


def test_prohibited_maturity_stage_and_self_promotion_fail_closed(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    policy, authority_record, approval_evidence = create_maturity_policy(
        harness,
        base=215_000,
        transitions=(
            {
                "from_stage": None,
                "to_stage": "apprentice-proposer",
                "minimum_claimed_evaluations": 1,
            },
        ),
    )
    anchor = register_evaluation(
        harness,
        base=215_100,
        evaluation_kind="maturity_evaluation",
    )
    envelope, payload, source, links = maturity_components(
        harness,
        base=215_200,
        stage="apprentice-proposer",
        basis=(anchor.evaluation_record_id,),
        developmental_policy_id=policy.developmental_policy_id,
    )
    repository = harness.persistence.self_episodic_memory
    with pytest.raises(ValidationError, match="unsupported"):
        repository.create_maturity_state(
            envelope,
            payload,
            lifecycle_transition_id=uid(215_202),
            approval_transition_id=uid(215_203),
            evidence_items=(source,),
            evidence_links=links,
            changed_by_principal="apprentice",
            changed_by_entity_id=harness.agent_id,
        )
    repository.create_maturity_state(
        envelope,
        payload,
        lifecycle_transition_id=uid(215_202),
        approval_transition_id=uid(215_203),
        evidence_items=(source,),
        evidence_links=links,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    grant = approval_grant(
        harness,
        record_id=payload.record_id,
        authority_record=authority_record,
        approval_evidence=approval_evidence,
        base=215_210,
    )
    with pytest.raises(ValidationError, match="prohibited during B87-S1"):
        repository.activate_maturity_state(
            payload.record_id,
            approval_grant=grant,
            approval_transition_id=uid(215_220),
            approved_transition_id=uid(215_221),
            active_transition_id=uid(215_222),
            changed_at=NOW,
            changed_by_entity_id=harness.operator_id,
        )


def test_permission_projection_current_and_historical_preserve_i2_stop_state(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    current = harness.persistence.permission_profile_projection.current_runtime(
        active_b87_s1_permission_profile(),
        effective_at=NOW,
    )
    contract = task(
        harness.i2,
        216_000,
        authority_ids=(uid(216_001),),
    )
    result = harness.runtime.evaluate(contract)
    historical = (
        harness.persistence.permission_profile_projection.historical_task(
            contract.task_id
        )
    )
    direct = harness.runtime.reconstruct(contract.task_id)

    assert current["permission_profile"]["allowed_action_classes"] == [
        "observe",
        "analyse",
    ]
    assert result.decision.outcome == "stop"
    assert historical["decision_outcome"] == "stop"
    assert historical["stop_event"] is not None
    assert historical["authority_inputs"][0]["validation_status"] == (
        "missing_authority"
    )
    assert historical["historical_reconstruction"]["canonical_json"] == (
        direct.canonical_json
    )

    connection = sqlite3.connect(harness.config.path)
    try:
        connection.execute("DROP TRIGGER permission_profiles_immutable")
        connection.execute(
            """
            UPDATE permission_profiles
            SET content_hash = ?
            """,
            ("0" * 64,),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(IntegrityInspectionError, match="hash mismatches"):
        harness.persistence.permission_profile_projection.current_runtime(
            active_b87_s1_permission_profile(),
            effective_at=NOW,
        )
