from __future__ import annotations

from tests.support.i2_fixtures import NOW, uid
from tests.support.i3c_fixtures import register_evaluation
from tests.support.i3c2_fixtures import create_episode, create_terminal_task
from tests.support.i3c3_fixtures import (
    approved_lesson_components,
    build_c3_harness,
    create_active_analysis_task,
    create_candidate,
    create_source_bundle,
    failure_pattern_components,
    review_candidate,
)
from tests.support.sql_probe import SqlProbe


def _candidate(tmp_path, *, base: int = 920_000):
    harness = build_c3_harness(tmp_path)
    task_id = create_active_analysis_task(harness, base=base)
    _, (_, episode), (_, correction) = create_source_bundle(
        harness,
        base=base + 1_000,
    )
    _, candidate = create_candidate(
        harness,
        base=base + 2_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    return harness, candidate


def _approved(tmp_path, *, base: int = 930_000):
    harness, candidate = _candidate(tmp_path, base=base)
    review_candidate(
        harness,
        candidate_id=candidate.record_id,
        transition_id=uid(base + 2_010),
    )
    transfer = register_evaluation(
        harness.c2.c1,
        base=base + 3_000,
        evaluation_kind="capability_evaluation",
        claimed=True,
    )
    components = approved_lesson_components(
        harness,
        base=base + 4_000,
        candidate=candidate,
        transfer_test_id=transfer.evaluation_record_id,
    )
    harness.persistence.developmental_derivation.create_approved_lesson(
        components[0],
        components[1],
        initial_lifecycle_transition_id=uid(base + 4_004),
        initial_approval_transition_id=uid(base + 4_005),
        approval_transition_id=uid(base + 4_006),
        approved_lifecycle_transition_id=uid(base + 4_007),
        active_lifecycle_transition_id=uid(base + 4_008),
        approval_grant=components[2],
        relationship_grant=components[3],
        relationship=components[4],
    )
    return harness, candidate, transfer, components


def _codes(report) -> set[str]:
    return {finding.code for finding in report.findings}


def test_dedicated_and_top_level_integrity_are_clean_for_all_c3_types(
    tmp_path,
) -> None:
    harness, _, _, _ = _approved(tmp_path)
    task_one = create_terminal_task(harness.c2, base=940_000, status="failed")
    task_two = create_terminal_task(harness.c2, base=941_000, status="failed")
    episode_one, _, _ = create_episode(
        harness.c2,
        base=940_100,
        task_id=task_one,
        outcome="failed",
    )
    episode_two, _, _ = create_episode(
        harness.c2,
        base=941_100,
        task_id=task_two,
        outcome="failed",
    )
    envelope, pattern = failure_pattern_components(
        harness,
        base=942_000,
        episode_ids=(episode_one.record_id, episode_two.record_id),
    )
    harness.persistence.developmental_derivation.create_failure_pattern(
        envelope,
        pattern,
        lifecycle_transition_id=uid(942_001),
        approval_transition_id=uid(942_002),
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )

    dedicated = harness.persistence.developmental_derivation_integrity.inspect()
    top_level = harness.persistence.integrity.inspect()
    assert dedicated.ok
    assert dedicated.error_count == 0
    assert top_level.ok
    assert top_level.error_count == 0
    assert top_level.migration_count == 11


def test_inspector_detects_payload_canonical_and_record_hash_corruption(
    tmp_path,
) -> None:
    harness, candidate = _candidate(tmp_path)
    probe = SqlProbe(harness.config)
    probe.corrupt_after_dropping_triggers(
        ("lesson_candidates_immutable",),
        lambda connection: connection.execute(
            "UPDATE lesson_candidates SET canonical_json = '{}' WHERE record_id = ?",
            (candidate.record_id,),
        ),
    )
    probe.corrupt_after_dropping_triggers(
        ("developmental_records_identity_guard",),
        lambda connection: connection.execute(
            "UPDATE records SET content_hash = ? WHERE record_id = ?",
            ("0" * 64, candidate.record_id),
        ),
    )

    codes = _codes(
        harness.persistence.developmental_derivation_integrity.inspect()
    )
    assert "I3C3-CANONICAL-JSON" in codes
    assert "I3C3-CONTENT-HASH" in codes


def test_inspector_detects_order_gap_after_minimum_guard_removal(
    tmp_path,
) -> None:
    harness, candidate = _candidate(tmp_path)
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("lesson_candidate_source_episodes_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE lesson_candidate_source_episodes
            SET source_order = 2 WHERE record_id = ?
            """,
            (candidate.record_id,),
        ),
    )

    report = harness.persistence.developmental_derivation_integrity.inspect()
    assert "I3C3-LINEAGE-ORDER" in _codes(report)


def test_inspector_detects_candidate_boundary_escape(tmp_path) -> None:
    harness, candidate = _candidate(tmp_path)
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("memory_records_approval_requires_transition",),
        lambda connection: connection.execute(
            "UPDATE records SET approval_status = 'approved' WHERE record_id = ?",
            (candidate.record_id,),
        ),
    )

    assert "I3C3-CANDIDATE-ISOLATION" in _codes(
        harness.persistence.developmental_derivation_integrity.inspect()
    )


def test_inspector_detects_approved_as_retarget_and_grant_consumption_tamper(
    tmp_path,
) -> None:
    harness, _, _, components = _approved(tmp_path)
    probe = SqlProbe(harness.config)
    probe.corrupt_after_dropping_triggers(
        ("approved_as_retarget_guard", "record_relationships_immutable"),
        lambda connection: connection.execute(
            """
            UPDATE record_relationships SET source_record_id = ?
            WHERE relationship_id = ?
            """,
            (
                components[1].source_episode_ids[0],
                components[4].relationship_id,
            ),
        ),
    )
    probe.corrupt_after_dropping_triggers(
        ("memory_approval_grants_consumption_guard",),
        lambda connection: connection.execute(
            """
            UPDATE memory_approval_grants
            SET consumed_by_transition_id = (
                SELECT transition_id
                FROM memory_record_approval_transitions
                WHERE record_id = ? AND sequence_number = 0
            )
            WHERE grant_id = ?
            """,
            (components[1].record_id, components[2].grant_id),
        ),
    )

    codes = _codes(
        harness.persistence.developmental_derivation_integrity.inspect()
    )
    assert "I3C3-APPROVED-AS" in codes
    assert "I3C3-APPROVAL-GRANT" in codes


def test_inspector_detects_cross_grant_authority_mismatch(tmp_path) -> None:
    harness, _, _, components = _approved(tmp_path)
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("memory_relationship_grants_core_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE memory_relationship_grants
            SET approved_by_entity_id = ?
            WHERE grant_id = ?
            """,
            (harness.agent_id, components[3].grant_id),
        ),
    )

    codes = _codes(
        harness.persistence.developmental_derivation_integrity.inspect()
    )
    assert "I3C3-GRANT-CONSISTENCY" in codes
    assert "I3C3-GRANT-HASH" in codes


def test_inspector_detects_late_transfer_anchor_invalidation(tmp_path) -> None:
    harness, _, transfer, components = _approved(tmp_path)
    provenance_id = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT provenance_evidence_id
            FROM governed_evaluation_record_anchors
            WHERE evaluation_record_id = ?
            """,
            (transfer.evaluation_record_id,),
        ).fetchone()[0]
    )
    harness.persistence.self_episodic_memory.transition_evaluation_anchor(
        transfer.evaluation_record_id,
        transition_id=uid(999_901),
        to_state="invalid",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
        transition_evidence_id=provenance_id,
        reason_code="transfer_test_later_invalidated",
    )

    report = harness.persistence.developmental_derivation_integrity.inspect()
    assert "I3C3-TRANSFER-TEST" in _codes(report)
    assert any(
        finding.record_id == components[1].record_id
        for finding in report.findings
    )


def test_inspector_detects_evidence_link_loss_and_controlled_contamination(
    tmp_path,
) -> None:
    harness, candidate = _candidate(tmp_path)
    probe = SqlProbe(harness.config)
    links = probe.read(
        lambda connection: tuple(
            connection.execute(
                """
                SELECT evidence_id, relationship
                FROM record_evidence_links
                WHERE record_id = ?
                ORDER BY evidence_id, relationship
                """,
                (candidate.record_id,),
            )
        )
    )
    probe.corrupt_after_dropping_triggers(
        ("developmental_evidence_link_delete_guard",),
        lambda connection: connection.execute(
            """
            DELETE FROM record_evidence_links
            WHERE record_id = ? AND evidence_id = ? AND relationship = ?
            """,
            (
                candidate.record_id,
                links[0]["evidence_id"],
                links[0]["relationship"],
            ),
        ),
    )
    probe.corrupt_after_dropping_triggers(
        ("evidence_core_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE evidence_items SET evidence_kind = 'controlled_output'
            WHERE evidence_id = ?
            """,
            (links[-1]["evidence_id"],),
        ),
    )

    codes = _codes(
        harness.persistence.developmental_derivation_integrity.inspect()
    )
    assert "I3C3-EVIDENCE-COMPLETENESS" in codes
    assert "I3C3-CGR-CONTAMINATION" in codes


def test_inspector_detects_pattern_frequency_and_active_without_approval(
    tmp_path,
) -> None:
    harness = build_c3_harness(tmp_path)
    task_one = create_terminal_task(harness.c2, base=950_000, status="failed")
    task_two = create_terminal_task(harness.c2, base=951_000, status="failed")
    episode_one, _, _ = create_episode(
        harness.c2,
        base=950_100,
        task_id=task_one,
        outcome="failed",
    )
    episode_two, _, _ = create_episode(
        harness.c2,
        base=951_100,
        task_id=task_two,
        outcome="failed",
    )
    envelope, pattern = failure_pattern_components(
        harness,
        base=952_000,
        episode_ids=(episode_one.record_id, episode_two.record_id),
    )
    harness.persistence.developmental_derivation.create_failure_pattern(
        envelope,
        pattern,
        lifecycle_transition_id=uid(952_001),
        approval_transition_id=uid(952_002),
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    probe = SqlProbe(harness.config)
    probe.corrupt_after_dropping_triggers(
        ("failure_patterns_immutable",),
        lambda connection: connection.execute(
            "UPDATE failure_patterns SET frequency = 3 WHERE record_id = ?",
            (pattern.record_id,),
        ),
    )
    probe.corrupt_after_dropping_triggers(
        (
            "memory_records_lifecycle_requires_transition",
            "memory_records_activation_guard",
        ),
        lambda connection: connection.execute(
            "UPDATE records SET lifecycle_state = 'active' WHERE record_id = ?",
            (pattern.record_id,),
        ),
    )

    codes = _codes(
        harness.persistence.developmental_derivation_integrity.inspect()
    )
    assert "I3C3-PAYLOAD-RECONSTRUCTION" in codes
    assert "I3C3-ACTIVE-WITHOUT-APPROVAL" in codes


def test_top_level_report_includes_dedicated_c3_corruption(tmp_path) -> None:
    harness, candidate = _candidate(tmp_path)
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("lesson_candidates_immutable",),
        lambda connection: connection.execute(
            "UPDATE lesson_candidates SET canonical_json = '{}' WHERE record_id = ?",
            (candidate.record_id,),
        ),
    )

    report = harness.persistence.integrity.inspect()
    assert not report.ok
    assert any(
        finding.code
        == "developmental_derivation_i3c3_canonical_json"
        and finding.object_id == candidate.record_id
        for finding in report.findings
    )
