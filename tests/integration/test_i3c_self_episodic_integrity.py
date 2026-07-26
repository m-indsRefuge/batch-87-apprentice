from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.persistence.service import PersistenceService
from tests.integration.test_i3c_factual_self_model import create_runtime_identity
from tests.support.i2_fixtures import uid
from tests.support.i3c_fixtures import (
    build_c1_harness,
    capability_components,
    create_capability_policy,
    register_evaluation,
    register_trusted_runtime_attestor,
)
from tests.support.sql_probe import SqlProbe


def finding_codes(report) -> set[str]:
    return {finding.code for finding in report.findings}


def create_capability_candidate(harness, *, base: int):
    anchor = register_evaluation(
        harness,
        base=base,
        evaluation_kind="capability_evaluation",
    )
    envelope, payload, source, links = capability_components(
        harness,
        base=base + 100,
        evaluation_record_ids=(anchor.evaluation_record_id,),
    )
    harness.persistence.self_episodic_memory.create_capability_observation(
        envelope,
        payload,
        lifecycle_transition_id=uid(base + 102),
        approval_transition_id=uid(base + 103),
        evidence_items=(source,),
        evidence_links=links,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    return anchor, payload


def test_valid_factual_self_state_is_clean_after_file_backed_reopen(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    _, payload, _, _ = create_runtime_identity(harness, base=220_000)

    assert harness.persistence.self_episodic_integrity.inspect().ok
    assert harness.persistence.integrity.inspect().ok

    reopened = PersistenceService(harness.config)
    reconstructed = reopened.self_episodic_memory.reconstruct(payload.record_id)
    assert reconstructed["integrity"]["valid"]
    assert reopened.self_episodic_integrity.inspect().ok
    assert reopened.integrity.inspect().ok


def test_envelope_and_payload_hash_corruption_are_detected_independently(
    tmp_path: Path,
) -> None:
    envelope_harness = build_c1_harness(
        tmp_path / "envelope",
        identifier_start=320_000,
    )
    _, envelope_payload, _, _ = create_runtime_identity(
        envelope_harness,
        base=221_000,
    )
    SqlProbe(envelope_harness.config).corrupt_after_dropping_triggers(
        ("factual_self_records_core_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE records
            SET provenance_summary = 'corrupted envelope provenance'
            WHERE record_id = ?
            """,
            (envelope_payload.record_id,),
        ),
    )
    envelope_codes = finding_codes(
        envelope_harness.persistence.self_episodic_integrity.inspect()
    )
    assert "C1-COMBINED-HASH-MISMATCH" in envelope_codes

    payload_harness = build_c1_harness(
        tmp_path / "payload",
        identifier_start=321_000,
    )
    _, payload, _, _ = create_runtime_identity(
        payload_harness,
        base=221_100,
    )
    SqlProbe(payload_harness.config).corrupt_after_dropping_triggers(
        ("runtime_identities_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE runtime_identities
            SET base_model = 'corrupted/model'
            WHERE record_id = ?
            """,
            (payload.record_id,),
        ),
    )
    payload_report = payload_harness.persistence.self_episodic_integrity.inspect()
    payload_codes = finding_codes(payload_report)
    assert "C1-COMBINED-HASH-MISMATCH" in payload_codes
    assert "C1-RUNTIME-SUBSTRATE-MISMATCH" in payload_codes
    global_codes = finding_codes(payload_harness.persistence.integrity.inspect())
    assert "self_episodic_c1_combined_hash_mismatch" in global_codes
    assert "self_episodic_c1_runtime_substrate_mismatch" in global_codes


def test_trusted_attestor_registry_and_approval_drift_are_detected(
    tmp_path: Path,
) -> None:
    hash_harness = build_c1_harness(
        tmp_path / "hash",
        identifier_start=324_000,
    )
    _, _, _, trusted = create_runtime_identity(
        hash_harness,
        base=221_200,
    )
    SqlProbe(hash_harness.config).corrupt_after_dropping_triggers(
        ("trusted_runtime_attestors_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE trusted_runtime_attestors
            SET content_hash = ?
            WHERE trusted_attestor_id = ?
            """,
            ("0" * 64, trusted.trusted_attestor_id),
        ),
    )
    hash_codes = finding_codes(
        hash_harness.persistence.self_episodic_integrity.inspect()
    )
    assert "C1-TRUSTED-ATTESTOR-REGISTRY-DRIFT" in hash_codes

    approval_harness = build_c1_harness(
        tmp_path / "approval",
        identifier_start=325_000,
    )
    _, payload, _, trusted = create_runtime_identity(
        approval_harness,
        base=221_300,
    )
    SqlProbe(approval_harness.config).corrupt_after_dropping_triggers(
        ("trusted_runtime_attestors_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE trusted_runtime_attestors
            SET approval_evidence_id = ?
            WHERE trusted_attestor_id = ?
            """,
            (
                payload.substrate_attestation_evidence_id,
                trusted.trusted_attestor_id,
            ),
        ),
    )
    approval_codes = finding_codes(
        approval_harness.persistence.self_episodic_integrity.inspect()
    )
    assert "C1-TRUSTED-ATTESTOR-APPROVAL-INVALID" in approval_codes


def test_attestation_support_evidence_and_context_corruption_are_detected(
    tmp_path: Path,
) -> None:
    context_harness = build_c1_harness(
        tmp_path / "context",
        identifier_start=326_000,
    )
    _, context_payload, _, _ = create_runtime_identity(
        context_harness,
        base=221_400,
    )
    SqlProbe(context_harness.config).corrupt_after_dropping_triggers(
        (
            "runtime_substrate_attestations_immutable",
            "runtime_identities_immutable",
        ),
        lambda connection: (
            connection.execute(
                """
                UPDATE runtime_substrate_attestations
                SET context_limit = 'malformed'
                WHERE substrate_attestation_evidence_id = ?
                """,
                (context_payload.substrate_attestation_evidence_id,),
            ),
            connection.execute(
                """
                UPDATE runtime_identities
                SET context_limit = 'malformed'
                WHERE record_id = ?
                """,
                (context_payload.record_id,),
            ),
        ),
    )
    context_codes = finding_codes(
        context_harness.persistence.self_episodic_integrity.inspect()
    )
    assert "C1-RUNTIME-CONTEXT-LIMIT-INVALID" in context_codes
    assert "C1-RUNTIME-ATTESTATION-CONTENT-MISMATCH" in context_codes
    with pytest.raises(ValidationError, match="integer >= 1"):
        context_harness.persistence.self_episodic_memory.reconstruct(
            context_payload.record_id
        )

    evidence_harness = build_c1_harness(
        tmp_path / "evidence",
        identifier_start=327_000,
    )
    _, evidence_payload, _, _ = create_runtime_identity(
        evidence_harness,
        base=221_500,
    )
    SqlProbe(evidence_harness.config).corrupt_after_dropping_triggers(
        (
            "runtime_attestation_evidence_immutable",
            "evidence_core_immutable",
        ),
        lambda connection: connection.execute(
            """
            UPDATE evidence_items
            SET content_hash = ?
            WHERE evidence_id = ?
            """,
            (
                "0" * 64,
                evidence_payload.substrate_attestation_evidence_id,
            ),
        ),
    )
    evidence_codes = finding_codes(
        evidence_harness.persistence.self_episodic_integrity.inspect()
    )
    assert "C1-RUNTIME-ATTESTATION-EVIDENCE-MISMATCH" in evidence_codes


@pytest.mark.parametrize(
    "corruption",
    ("missing", "wrong_relationship", "wrong_evidence", "additional"),
)
def test_runtime_identity_evidence_link_corruption_is_detected_independently(
    tmp_path: Path,
    corruption: str,
) -> None:
    harness = build_c1_harness(
        tmp_path / corruption,
        identifier_start=327_500,
    )
    _, payload, _, trusted = create_runtime_identity(
        harness,
        base=221_550,
    )

    if corruption == "missing":
        triggers = ("runtime_identity_evidence_links_no_delete",)

        def corrupt(connection):
            connection.execute(
                "DELETE FROM record_evidence_links WHERE record_id = ?",
                (payload.record_id,),
            )
    elif corruption == "wrong_relationship":
        triggers = ("runtime_identity_evidence_links_immutable",)

        def corrupt(connection):
            connection.execute(
                """
                UPDATE record_evidence_links
                SET relationship = 'contextualises'
                WHERE record_id = ?
                """,
                (payload.record_id,),
            )
    elif corruption == "wrong_evidence":
        triggers = ("runtime_identity_evidence_links_immutable",)

        def corrupt(connection):
            connection.execute(
                """
                UPDATE record_evidence_links
                SET evidence_id = ?
                WHERE record_id = ?
                """,
                (trusted.approval_evidence_id, payload.record_id),
            )
    else:
        triggers = ("runtime_identity_evidence_link_contract_guard",)

        def corrupt(connection):
            connection.execute(
                """
                INSERT INTO record_evidence_links (
                    record_id, evidence_id, relationship, explanation
                ) VALUES (?, ?, 'supports', 'corrupted additional link')
                """,
                (payload.record_id, trusted.approval_evidence_id),
            )

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        triggers,
        corrupt,
    )
    codes = finding_codes(
        harness.persistence.self_episodic_integrity.inspect()
    )
    assert "C1-RUNTIME-ATTESTATION-EVIDENCE-MISMATCH" in codes


def test_missing_support_and_revoked_attestor_bound_to_identity_are_detected(
    tmp_path: Path,
) -> None:
    missing_harness = build_c1_harness(
        tmp_path / "missing-support",
        identifier_start=328_000,
    )
    _, missing_payload, _, _ = create_runtime_identity(
        missing_harness,
        base=221_600,
    )
    connection = sqlite3.connect(missing_harness.config.path)
    try:
        connection.execute(
            "DROP TRIGGER runtime_substrate_attestations_no_delete"
        )
        connection.execute(
            """
            DELETE FROM runtime_substrate_attestations
            WHERE substrate_attestation_evidence_id = ?
            """,
            (missing_payload.substrate_attestation_evidence_id,),
        )
        connection.commit()
    finally:
        connection.close()
    missing_codes = finding_codes(
        missing_harness.persistence.self_episodic_integrity.inspect()
    )
    assert "C1-RUNTIME-ATTESTATION-SUPPORT-MISSING" in missing_codes

    revoked_harness = build_c1_harness(
        tmp_path / "revoked",
        identifier_start=329_000,
    )
    _, _, _, trusted = create_runtime_identity(
        revoked_harness,
        base=221_700,
    )
    register_trusted_runtime_attestor(
        revoked_harness,
        base=221_730,
        status="revoked",
        supersedes_trusted_attestor_id=trusted.trusted_attestor_id,
    )
    revoked_codes = finding_codes(
        revoked_harness.persistence.self_episodic_integrity.inspect()
    )
    assert "C1-RUNTIME-ATTESTOR-INVALID" in revoked_codes
    assert "C1-RUNTIME-ATTESTATION-PARENT-MISMATCH" in revoked_codes


def test_missing_payload_and_capability_lineage_corruption_are_detected(
    tmp_path: Path,
) -> None:
    payload_harness = build_c1_harness(
        tmp_path / "missing",
        identifier_start=322_000,
    )
    _, runtime_payload, _, _ = create_runtime_identity(
        payload_harness,
        base=222_000,
    )
    SqlProbe(payload_harness.config).corrupt_after_dropping_triggers(
        ("runtime_identities_no_delete",),
        lambda connection: connection.execute(
            "DELETE FROM runtime_identities WHERE record_id = ?",
            (runtime_payload.record_id,),
        ),
    )
    missing_codes = finding_codes(
        payload_harness.persistence.self_episodic_integrity.inspect()
    )
    assert "C1-PAYLOAD-CARDINALITY-INVALID" in missing_codes
    assert "C1-PAYLOAD-OR-ENVELOPE-INVALID" in missing_codes

    lineage_harness = build_c1_harness(
        tmp_path / "lineage",
        identifier_start=323_000,
    )
    _, capability_payload = create_capability_candidate(
        lineage_harness,
        base=222_100,
    )
    SqlProbe(lineage_harness.config).corrupt_after_dropping_triggers(
        ("capability_observation_evaluations_no_delete",),
        lambda connection: connection.execute(
            """
            DELETE FROM capability_observation_evaluations
            WHERE record_id = ?
            """,
            (capability_payload.record_id,),
        ),
    )
    lineage_codes = finding_codes(
        lineage_harness.persistence.self_episodic_integrity.inspect()
    )
    assert "C1-CAPABILITY-LINEAGE-MISMATCH" in lineage_codes
    assert "C1-PAYLOAD-OR-ENVELOPE-INVALID" in lineage_codes


def test_anchor_history_and_noncanonical_policy_corruption_are_detected(
    tmp_path: Path,
) -> None:
    harness = build_c1_harness(tmp_path)
    anchor, _ = create_capability_candidate(harness, base=223_000)
    policy, _, _ = create_capability_policy(harness, base=223_200)
    probe = SqlProbe(harness.config)

    probe.corrupt_after_dropping_triggers(
        ("governed_evaluation_anchor_history_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE governed_evaluation_anchor_state_history
            SET content_hash = ?
            WHERE evaluation_record_id = ? AND sequence_number = 1
            """,
            ("0" * 64, anchor.evaluation_record_id),
        ),
    )
    probe.corrupt_after_dropping_triggers(
        ("developmental_policy_versions_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE developmental_policy_versions
            SET configuration_json =
                '{ "allow_registered_for_unconfirmed": false, "stability_requirements": {} }'
            WHERE developmental_policy_id = ?
            """,
            (policy.developmental_policy_id,),
        ),
    )

    local_codes = finding_codes(
        harness.persistence.self_episodic_integrity.inspect()
    )
    assert "C1-EVALUATION-ANCHOR-HISTORY-MISMATCH" in local_codes
    assert "C1-DEVELOPMENTAL-POLICY-INVALID" in local_codes
    global_codes = finding_codes(harness.persistence.integrity.inspect())
    assert "self_episodic_c1_evaluation_anchor_history_mismatch" in global_codes
    assert "self_episodic_c1_developmental_policy_invalid" in global_codes
