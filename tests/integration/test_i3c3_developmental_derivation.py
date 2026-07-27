from __future__ import annotations

from dataclasses import replace
import pytest

from batch87_apprentice.common.errors import ConflictError, ValidationError
from batch87_apprentice.memory import EligibilityContext
from tests.support.i2_fixtures import EARLIER, LATER, NOW, uid
from tests.support.i3c3_fixtures import (
    approved_lesson_components,
    build_c3_harness,
    candidate_components,
    create_active_analysis_task,
    create_approved_lesson,
    create_candidate,
    create_source_bundle,
    review_candidate,
)
from tests.support.sql_probe import SqlProbe


def _candidate_fixture(tmp_path):
    harness = build_c3_harness(tmp_path)
    task_id = create_active_analysis_task(harness, base=820_000)
    _, (_, episode), (_, correction) = create_source_bundle(
        harness,
        base=821_000,
    )
    return harness, task_id, episode, correction


def test_apprentice_origin_candidate_is_created_only_candidate_pending(
    tmp_path,
) -> None:
    harness, task_id, episode, correction = _candidate_fixture(tmp_path)
    envelope, payload = create_candidate(
        harness,
        base=822_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )

    rebuilt = harness.persistence.developmental_derivation.reconstruct(
        payload.record_id
    )
    assert rebuilt["integrity_ok"]
    assert rebuilt["payload"] == payload.canonical_content()
    assert rebuilt["envelope"]["lifecycle_state"] == "candidate"
    assert rebuilt["envelope"]["approval_status"] == "pending"
    assert rebuilt["envelope"]["agent_write_policy"] == "candidate_only"
    assert rebuilt["stored_content_hash"] == rebuilt["expected_content_hash"]
    history = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT changed_by_principal, changed_by_entity_id
            FROM memory_record_lifecycle_transitions
            WHERE record_id = ? AND sequence_number = 0
            """,
            (payload.record_id,),
        ).fetchone()
    )
    assert tuple(history) == ("codex_development_harness", None)
    assert envelope.created_by_entity_id == harness.agent_id


def test_candidate_is_excluded_from_ordinary_retrieval_before_and_after_review(
    tmp_path,
) -> None:
    harness, task_id, episode, correction = _candidate_fixture(tmp_path)
    _, payload = create_candidate(
        harness,
        base=823_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    context = EligibilityContext(
        assessment_id=uid(823_010),
        task_id=task_id,
        task_project_scope_id=harness.project_scope_id,
        requested_domain="self_episodic",
        evaluated_at=NOW,
        allowed_sensitivity_classes=("internal",),
        allowed_privacy_classes=("none",),
    )

    before = harness.memory.assess_eligibility(payload.record_id, context)
    review_candidate(
        harness,
        candidate_id=payload.record_id,
        transition_id=uid(823_011),
    )
    after = harness.memory.assess_eligibility(
        payload.record_id,
        replace(context, assessment_id=uid(823_012)),
    )

    assert not before.eligible
    assert not after.eligible
    assert "ordinary_retrieval_prohibited" in before.reason_codes
    assert "ordinary_retrieval_prohibited" in after.reason_codes
    rebuilt = harness.persistence.developmental_derivation.reconstruct(
        payload.record_id
    )
    assert rebuilt["envelope"]["record_type"] == "lesson_candidate"
    assert rebuilt["envelope"]["lifecycle_state"] == "reviewed"
    assert rebuilt["envelope"]["approval_status"] == "pending"


@pytest.mark.parametrize(
    "principal",
    ["apprentice", "experimental_harness", "model"],
)
def test_candidate_rejects_non_infrastructure_creation_principal(
    tmp_path,
    principal: str,
) -> None:
    harness, task_id, episode, correction = _candidate_fixture(tmp_path)
    envelope, payload = candidate_components(
        harness,
        base=824_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    with pytest.raises(ValidationError, match="creation principal"):
        harness.persistence.developmental_derivation.create_lesson_candidate(
            envelope,
            payload,
            lifecycle_transition_id=uid(824_001),
            approval_transition_id=uid(824_002),
            changed_by_principal=principal,
        )


def test_candidate_rejects_missing_or_inactive_governed_analysis_task(
    tmp_path,
) -> None:
    harness, task_id, episode, correction = _candidate_fixture(tmp_path)
    harness.runtime.transition_task(
        task_id,
        to_status="completed",
        reason_code="fixture_completed_before_derivation",
    )
    envelope, payload = candidate_components(
        harness,
        base=825_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )

    with pytest.raises(ValidationError, match="active governed analysis task"):
        harness.persistence.developmental_derivation.create_lesson_candidate(
            envelope,
            payload,
            lifecycle_transition_id=uid(825_001),
            approval_transition_id=uid(825_002),
            changed_by_principal="codex_development_harness",
        )


def test_candidate_rejects_creation_before_governed_task_start(tmp_path) -> None:
    harness, task_id, episode, correction = _candidate_fixture(tmp_path)
    envelope, payload = candidate_components(
        harness,
        base=825_050,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )

    with pytest.raises(ValidationError, match="active governed analysis task"):
        harness.persistence.developmental_derivation.create_lesson_candidate(
            replace(envelope, created_at=EARLIER),
            payload,
            lifecycle_transition_id=uid(825_051),
            approval_transition_id=uid(825_052),
            changed_by_principal="codex_development_harness",
        )


def test_candidate_integrity_remains_clean_after_task_stops(tmp_path) -> None:
    harness, task_id, episode, correction = _candidate_fixture(tmp_path)
    _, payload = create_candidate(
        harness,
        base=825_060,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )

    def stop_after_creation(connection) -> None:
        transaction_id = connection.execute(
            """
            SELECT transaction_id
            FROM governed_runtime_transactions
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()[0]
        sequence_number = connection.execute(
            """
            SELECT MAX(sequence_number) + 1
            FROM task_state_transitions
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO task_state_transitions (
                transition_id, task_id, sequence_number, from_status,
                to_status, reason_code, changed_at, changed_by, transaction_id
            ) VALUES (?, ?, ?, 'active', 'stopped',
                      'fixture_stop_after_candidate', ?,
                      'governance_kernel', ?)
            """,
            (
                uid(825_063),
                task_id,
                sequence_number,
                LATER,
                transaction_id,
            ),
        )
        connection.execute(
            """
            UPDATE tasks
            SET status = 'stopped', completed_at = ?
            WHERE task_id = ?
            """,
            (LATER, task_id),
        )

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("tasks_stop_requires_event",),
        stop_after_creation,
    )

    report = harness.persistence.developmental_derivation_integrity.inspect()
    candidate_findings = tuple(
        finding
        for finding in report.findings
        if finding.record_id == payload.record_id
    )
    assert candidate_findings == ()


@pytest.mark.parametrize("agent_status", ["inactive", "archived"])
def test_candidate_historical_integrity_ignores_current_agent_lifecycle(
    tmp_path,
    agent_status: str,
) -> None:
    harness, task_id, episode, correction = _candidate_fixture(tmp_path)
    _, payload = create_candidate(
        harness,
        base=825_070,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    SqlProbe(harness.config).write(
        lambda connection: connection.execute(
            "UPDATE entities SET status = ? WHERE entity_id = ?",
            (agent_status, harness.agent_id),
        )
    )

    report = harness.persistence.developmental_derivation_integrity.inspect()
    assert tuple(
        finding
        for finding in report.findings
        if finding.record_id == payload.record_id
    ) == ()


def test_inactive_agent_cannot_create_new_apprentice_candidate(tmp_path) -> None:
    harness, task_id, episode, correction = _candidate_fixture(tmp_path)
    envelope, payload = candidate_components(
        harness,
        base=825_080,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    SqlProbe(harness.config).write(
        lambda connection: connection.execute(
            "UPDATE entities SET status = 'inactive' WHERE entity_id = ?",
            (harness.agent_id,),
        )
    )

    with pytest.raises(ValidationError, match="active governed analysis task"):
        harness.persistence.developmental_derivation.create_lesson_candidate(
            envelope,
            payload,
            lifecycle_transition_id=uid(825_081),
            approval_transition_id=uid(825_082),
            changed_by_principal="codex_development_harness",
        )


def test_candidate_rejects_non_agent_apprentice_proposer(tmp_path) -> None:
    harness, task_id, episode, correction = _candidate_fixture(tmp_path)
    envelope, payload = candidate_components(
        harness,
        base=825_100,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    envelope = replace(
        envelope,
        created_by_entity_id=harness.operator_id,
    )
    payload = replace(
        payload,
        proposer_entity_id=harness.operator_id,
    )

    with pytest.raises(ValidationError, match="active governed analysis task"):
        harness.persistence.developmental_derivation.create_lesson_candidate(
            envelope,
            payload,
            lifecycle_transition_id=uid(825_101),
            approval_transition_id=uid(825_102),
            changed_by_principal="codex_development_harness",
        )


def test_atomic_approved_lesson_preserves_candidate_and_exact_authority(
    tmp_path,
) -> None:
    harness, task_id, episode, correction = _candidate_fixture(tmp_path)
    _, candidate = create_candidate(
        harness,
        base=826_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    candidate_before = harness.persistence.developmental_derivation.reconstruct(
        candidate.record_id
    )
    review_candidate(
        harness,
        candidate_id=candidate.record_id,
        transition_id=uid(826_010),
    )
    _, approved = create_approved_lesson(
        harness,
        base=827_000,
        candidate=candidate,
    )

    candidate_after = harness.persistence.developmental_derivation.reconstruct(
        candidate.record_id
    )
    rebuilt = harness.persistence.developmental_derivation.reconstruct(
        approved.record_id
    )
    assert candidate_after["payload"] == candidate_before["payload"]
    assert (
        candidate_after["stored_content_hash"]
        == candidate_before["stored_content_hash"]
    )
    assert candidate_after["envelope"]["record_type"] == "lesson_candidate"
    assert candidate_after["envelope"]["approval_status"] == "pending"
    assert rebuilt["integrity_ok"]
    assert rebuilt["envelope"]["record_type"] == "approved_lesson"
    assert rebuilt["envelope"]["lifecycle_state"] == "active"
    assert rebuilt["envelope"]["approval_status"] == "approved"
    facts = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT relationship.source_record_id,
                   relationship.target_record_id,
                   relationship.relationship_type,
                   approval.authority_class,
                   approval.consumed_at,
                   relation_grant.authority_class AS relationship_authority,
                   relation_grant.consumed_at AS relationship_consumed_at
            FROM record_relationships AS relationship
            JOIN memory_relationship_grants AS relation_grant
              ON relation_grant.grant_id = relationship.relationship_grant_id
            JOIN memory_approval_grants AS approval
              ON approval.record_id = relationship.target_record_id
            WHERE relationship.target_record_id = ?
            """,
            (approved.record_id,),
        ).fetchone()
    )
    assert facts["source_record_id"] == candidate.record_id
    assert facts["target_record_id"] == approved.record_id
    assert facts["relationship_type"] == "approved_as"
    assert facts["authority_class"] == "nolan_byte_approved"
    assert facts["relationship_authority"] == "nolan_byte_approved"
    assert facts["consumed_at"] is not None
    assert facts["relationship_consumed_at"] is not None


def test_approved_lesson_rejects_reversed_approved_as_direction(tmp_path) -> None:
    harness, task_id, episode, correction = _candidate_fixture(tmp_path)
    _, candidate = create_candidate(
        harness,
        base=828_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    review_candidate(
        harness,
        candidate_id=candidate.record_id,
        transition_id=uid(828_010),
    )
    from tests.support.i3c_fixtures import register_evaluation

    transfer = register_evaluation(
        harness.c2.c1,
        base=829_100,
        evaluation_kind="capability_evaluation",
        claimed=True,
    )
    (
        envelope,
        payload,
        approval_grant,
        relationship_grant,
        relationship,
    ) = approved_lesson_components(
        harness,
        base=829_000,
        candidate=candidate,
        transfer_test_id=transfer.evaluation_record_id,
    )
    reversed_relationship = replace(
        relationship,
        source_record_id=payload.record_id,
        target_record_id=candidate.record_id,
    )

    with pytest.raises(ValidationError, match="exact single-use"):
        harness.persistence.developmental_derivation.create_approved_lesson(
            envelope,
            payload,
            initial_lifecycle_transition_id=uid(829_004),
            initial_approval_transition_id=uid(829_005),
            approval_transition_id=uid(829_006),
            approved_lifecycle_transition_id=uid(829_007),
            active_lifecycle_transition_id=uid(829_008),
            approval_grant=approval_grant,
            relationship_grant=relationship_grant,
            relationship=reversed_relationship,
        )


def test_raw_sql_rejects_candidate_retyping_payload_mutation_and_retargeting(
    tmp_path,
) -> None:
    harness, task_id, episode, correction = _candidate_fixture(tmp_path)
    _, candidate = create_candidate(
        harness,
        base=830_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    review_candidate(
        harness,
        candidate_id=candidate.record_id,
        transition_id=uid(830_010),
    )
    _, approved = create_approved_lesson(
        harness,
        base=831_000,
        candidate=candidate,
    )
    probe = SqlProbe(harness.config)

    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE records SET record_type = 'approved_lesson'
                WHERE record_id = ?
                """,
                (candidate.record_id,),
            )
        )
    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE records SET retrieval_policy_json =
                    '{"retrieval_mode":"ordinary"}'
                WHERE record_id = ?
                """,
                (candidate.record_id,),
            )
        )
    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE lesson_candidates SET lesson_statement = 'changed'
                WHERE record_id = ?
                """,
                (candidate.record_id,),
            )
        )
    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                "DELETE FROM approved_lessons WHERE record_id = ?",
                (approved.record_id,),
            )
        )
    with pytest.raises(ConflictError):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE record_relationships
                SET source_record_id = ?
                WHERE target_record_id = ? AND relationship_type = 'approved_as'
                """,
                (approved.record_id, approved.record_id),
            )
        )
