from __future__ import annotations

from dataclasses import replace

import pytest

from batch87_apprentice.common.errors import ConflictError
from batch87_apprentice.memory import developmental_content_hash
from batch87_apprentice.memory.kernel import _insert_initial_memory_state
from batch87_apprentice.persistence.repositories import _insert_record, _insert_values
from batch87_apprentice.protocols.task_contracts import SessionContract
from tests.support.i2_fixtures import NOW, uid
from tests.support.i3c_fixtures import register_evaluation
from tests.support.i3c2_fixtures import create_episode, create_terminal_task
from tests.support.i3c3_fixtures import (
    approved_lesson_components,
    build_c3_harness,
    candidate_components,
    create_active_analysis_task,
    create_candidate,
    create_source_bundle,
    failure_pattern_components,
    review_candidate,
    success_pattern_components,
)
from tests.support.sql_probe import SqlProbe


def test_raw_sql_single_episode_pattern_cannot_finalize(tmp_path) -> None:
    harness = build_c3_harness(tmp_path)
    first_task = create_terminal_task(
        harness.c2,
        base=960_000,
        status="failed",
    )
    second_task = create_terminal_task(
        harness.c2,
        base=961_000,
        status="failed",
    )
    first, _, _ = create_episode(
        harness.c2,
        base=960_100,
        task_id=first_task,
        outcome="failed",
    )
    second, _, _ = create_episode(
        harness.c2,
        base=961_100,
        task_id=second_task,
        outcome="failed",
    )
    envelope, payload = failure_pattern_components(
        harness,
        base=962_000,
        episode_ids=(first.record_id, second.record_id),
    )
    probe = SqlProbe(harness.config)
    evidence_id = probe.read(
        lambda connection: connection.execute(
            """
            SELECT evidence_id FROM record_evidence_links
            WHERE record_id = ? ORDER BY evidence_id LIMIT 1
            """,
            (first.record_id,),
        ).fetchone()[0]
    )

    def incomplete_pattern(connection):
        _insert_record(
            connection,
            envelope,
            content_hash=developmental_content_hash(envelope, payload),
        )
        _insert_values(connection, payload.TABLE, payload.database_values())
        connection.execute(
            """
            INSERT INTO failure_pattern_episodes (
                record_id, episode_id, episode_order
            ) VALUES (?, ?, 0)
            """,
            (payload.record_id, first.record_id),
        )
        connection.execute(
            """
            INSERT INTO record_evidence_links (
                record_id, evidence_id, relationship, explanation
            ) VALUES (?, ?, 'derived_from', 'exact source evidence')
            """,
            (payload.record_id, evidence_id),
        )
        connection.execute(
            """
            INSERT INTO memory_record_lifecycle_transitions (
                transition_id, record_id, sequence_number, from_state, to_state,
                reason_code, changed_at, changed_by_principal,
                changed_by_entity_id, canonical_json, content_hash
            ) VALUES (?, ?, 0, NULL, 'candidate', 'raw_finalization_probe',
                      ?, 'operator', ?, '{}', ?)
            """,
            (
                uid(962_001),
                payload.record_id,
                NOW,
                harness.operator_id,
                "0" * 64,
            ),
        )

    with pytest.raises(ConflictError, match="integrity constraint"):
        probe.write(incomplete_pattern)
    assert probe.read(
        lambda connection: connection.execute(
            "SELECT 1 FROM records WHERE record_id = ?",
            (payload.record_id,),
        ).fetchone()
    ) is None


def test_raw_sql_cross_project_source_insertion_is_rejected(tmp_path) -> None:
    harness = build_c3_harness(tmp_path)
    analysis_task = create_active_analysis_task(harness, base=963_000)
    _, (_, episode), (_, correction) = create_source_bundle(
        harness,
        base=964_000,
    )
    envelope, payload = candidate_components(
        harness,
        base=965_000,
        task_id=analysis_task,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
        proposed_by="evaluator",
    )
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("c2_records_core_immutable",),
        lambda connection: connection.execute(
            "UPDATE records SET project_scope_id = ? WHERE record_id = ?",
            (harness.c2.c1.i2.other_project_scope_id, episode.record_id),
        ),
    )

    def cross_project_lineage(connection):
        _insert_record(
            connection,
            envelope,
            content_hash=developmental_content_hash(envelope, payload),
        )
        _insert_values(connection, payload.TABLE, payload.database_values())
        connection.execute(
            """
            INSERT INTO lesson_candidate_source_episodes (
                record_id, episode_id, source_order
            ) VALUES (?, ?, 0)
            """,
            (payload.record_id, episode.record_id),
        )

    with pytest.raises(ConflictError, match="integrity constraint"):
        SqlProbe(harness.config).write(cross_project_lineage)


def test_raw_sql_rejects_apprentice_candidate_bound_to_wrong_session(
    tmp_path,
) -> None:
    harness = build_c3_harness(tmp_path)
    task_id = create_active_analysis_task(harness, base=965_100)
    _, (_, episode), (_, correction) = create_source_bundle(
        harness,
        base=965_200,
    )
    alternate_session_id = uid(965_300)
    harness.runtime.open_session(
        SessionContract(
            session_id=alternate_session_id,
            purpose="Valid alternate session for exact binding rejection.",
            project_scope_id=harness.project_scope_id,
            opened_at=NOW,
            created_by_entity_id=harness.operator_id,
            participant_entity_ids=(harness.operator_id, harness.agent_id),
        )
    )
    envelope, payload = candidate_components(
        harness,
        base=965_400,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    wrong_session_envelope = replace(
        envelope,
        session_id=alternate_session_id,
    )

    def wrong_session_candidate(connection) -> None:
        _insert_record(
            connection,
            wrong_session_envelope,
            content_hash=developmental_content_hash(
                wrong_session_envelope,
                payload,
            ),
        )
        _insert_values(connection, payload.TABLE, payload.database_values())

    with pytest.raises(ConflictError, match="integrity constraint"):
        SqlProbe(harness.config).write(wrong_session_candidate)


def test_raw_sql_candidate_subset_source_evidence_cannot_finalize(tmp_path) -> None:
    harness = build_c3_harness(tmp_path)
    task_id = create_active_analysis_task(harness, base=965_500)
    _, (_, episode), (_, correction) = create_source_bundle(
        harness,
        base=965_600,
    )
    envelope, payload = candidate_components(
        harness,
        base=965_700,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    probe = SqlProbe(harness.config)
    source_evidence = probe.read(
        lambda connection: tuple(
            row[0]
            for row in connection.execute(
                """
                SELECT DISTINCT evidence_id
                FROM record_evidence_links
                WHERE record_id IN (?, ?)
                ORDER BY evidence_id
                """,
                (episode.record_id, correction.record_id),
            )
        )
    )
    assert len(source_evidence) > 1

    def subset_candidate(connection) -> None:
        _insert_record(
            connection,
            envelope,
            content_hash=developmental_content_hash(envelope, payload),
        )
        _insert_values(connection, payload.TABLE, payload.database_values())
        connection.execute(
            """
            INSERT INTO lesson_candidate_source_episodes (
                record_id, episode_id, source_order
            ) VALUES (?, ?, 0)
            """,
            (payload.record_id, episode.record_id),
        )
        connection.execute(
            """
            INSERT INTO lesson_candidate_source_corrections (
                record_id, correction_id, source_order
            ) VALUES (?, ?, 0)
            """,
            (payload.record_id, correction.record_id),
        )
        connection.execute(
            """
            INSERT INTO lesson_candidate_limitations (
                record_id, limitation_order, limitation
            ) VALUES (?, 0, ?)
            """,
            (payload.record_id, payload.known_limitations[0]),
        )
        connection.execute(
            """
            INSERT INTO record_evidence_links (
                record_id, evidence_id, relationship, explanation
            ) VALUES (?, ?, 'derived_from', 'incomplete exact source set')
            """,
            (payload.record_id, source_evidence[0]),
        )
        _insert_initial_memory_state(
            connection,
            payload.record_id,
            lifecycle_transition_id=uid(965_701),
            approval_transition_id=uid(965_702),
            changed_at=NOW,
            changed_by_principal="codex_development_harness",
            reason_code="raw_candidate_subset_probe",
        )

    with pytest.raises(ConflictError, match="integrity constraint"):
        probe.write(subset_candidate)


def test_raw_sql_pattern_subset_source_evidence_cannot_finalize(tmp_path) -> None:
    harness = build_c3_harness(tmp_path)
    first_task = create_terminal_task(
        harness.c2,
        base=965_800,
        status="failed",
    )
    second_task = create_terminal_task(
        harness.c2,
        base=965_900,
        status="failed",
    )
    first, _, _ = create_episode(
        harness.c2,
        base=966_000,
        task_id=first_task,
        outcome="failed",
    )
    second, _, _ = create_episode(
        harness.c2,
        base=966_100,
        task_id=second_task,
        outcome="failed",
    )
    envelope, payload = failure_pattern_components(
        harness,
        base=966_200,
        episode_ids=(first.record_id, second.record_id),
    )
    probe = SqlProbe(harness.config)
    source_evidence = probe.read(
        lambda connection: tuple(
            row[0]
            for row in connection.execute(
                """
                SELECT DISTINCT evidence_id
                FROM record_evidence_links
                WHERE record_id IN (?, ?)
                ORDER BY evidence_id
                """,
                (first.record_id, second.record_id),
            )
        )
    )
    assert len(source_evidence) > 1

    def subset_pattern(connection) -> None:
        _insert_record(
            connection,
            envelope,
            content_hash=developmental_content_hash(envelope, payload),
        )
        _insert_values(connection, payload.TABLE, payload.database_values())
        connection.executemany(
            """
            INSERT INTO failure_pattern_episodes (
                record_id, episode_id, episode_order
            ) VALUES (?, ?, ?)
            """,
            (
                (payload.record_id, first.record_id, 0),
                (payload.record_id, second.record_id, 1),
            ),
        )
        connection.execute(
            """
            INSERT INTO record_evidence_links (
                record_id, evidence_id, relationship, explanation
            ) VALUES (?, ?, 'derived_from', 'incomplete exact source set')
            """,
            (payload.record_id, source_evidence[0]),
        )
        _insert_initial_memory_state(
            connection,
            payload.record_id,
            lifecycle_transition_id=uid(966_201),
            approval_transition_id=uid(966_202),
            changed_at=NOW,
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
            reason_code="raw_pattern_subset_probe",
        )

    with pytest.raises(ConflictError, match="integrity constraint"):
        probe.write(subset_pattern)


@pytest.mark.parametrize("pattern_kind", ["failure", "success"])
def test_raw_sql_agent_pattern_without_governed_task_is_rejected(
    tmp_path,
    pattern_kind: str,
) -> None:
    harness = build_c3_harness(tmp_path)
    terminal_status = "failed" if pattern_kind == "failure" else "completed"
    outcome = terminal_status
    episodes = []
    for index in range(2):
        task_id = create_terminal_task(
            harness.c2,
            base=966_300 + index * 200,
            status=terminal_status,
        )
        episode, _, _ = create_episode(
            harness.c2,
            base=966_400 + index * 200,
            task_id=task_id,
            outcome=outcome,
        )
        episodes.append(episode.record_id)
    if pattern_kind == "failure":
        envelope, payload = failure_pattern_components(
            harness,
            base=966_800,
            episode_ids=tuple(episodes),
        )
    else:
        envelope, payload = success_pattern_components(
            harness,
            base=966_800,
            episode_ids=tuple(episodes),
        )
    agent_envelope = replace(
        envelope,
        created_by_entity_id=harness.agent_id,
        session_id=harness.session_id,
        task_id=None,
    )

    def unbound_agent_pattern(connection) -> None:
        _insert_record(
            connection,
            agent_envelope,
            content_hash=developmental_content_hash(agent_envelope, payload),
        )
        _insert_values(connection, payload.TABLE, payload.database_values())

    with pytest.raises(ConflictError, match="integrity constraint"):
        SqlProbe(harness.config).write(unbound_agent_pattern)


def test_finalized_lineage_and_evidence_links_reject_update_and_delete(
    tmp_path,
) -> None:
    harness = build_c3_harness(tmp_path)
    task_id = create_active_analysis_task(harness, base=966_000)
    _, (_, episode), (_, correction) = create_source_bundle(
        harness,
        base=967_000,
    )
    _, candidate = create_candidate(
        harness,
        base=968_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    probe = SqlProbe(harness.config)
    evidence_id = probe.read(
        lambda connection: connection.execute(
            """
            SELECT evidence_id FROM record_evidence_links
            WHERE record_id = ? ORDER BY evidence_id LIMIT 1
            """,
            (candidate.record_id,),
        ).fetchone()[0]
    )

    operations = (
        lambda connection: connection.execute(
            """
            UPDATE lesson_candidate_source_episodes SET source_order = 2
            WHERE record_id = ?
            """,
            (candidate.record_id,),
        ),
        lambda connection: connection.execute(
            """
            DELETE FROM lesson_candidate_source_corrections
            WHERE record_id = ?
            """,
            (candidate.record_id,),
        ),
        lambda connection: connection.execute(
            """
            UPDATE record_evidence_links SET explanation = 'changed'
            WHERE record_id = ? AND evidence_id = ?
            """,
            (candidate.record_id, evidence_id),
        ),
        lambda connection: connection.execute(
            """
            DELETE FROM record_evidence_links
            WHERE record_id = ? AND evidence_id = ?
            """,
            (candidate.record_id, evidence_id),
        ),
    )
    for operation in operations:
        with pytest.raises(ConflictError, match="integrity constraint"):
            probe.write(operation)


def test_transfer_tests_cannot_be_inserted_after_lesson_finalization(
    tmp_path,
) -> None:
    harness = build_c3_harness(tmp_path)
    task_id = create_active_analysis_task(harness, base=969_000)
    _, (_, episode), (_, correction) = create_source_bundle(
        harness,
        base=970_000,
    )
    _, candidate = create_candidate(
        harness,
        base=971_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    review_candidate(
        harness,
        candidate_id=candidate.record_id,
        transition_id=uid(971_010),
    )
    first = register_evaluation(
        harness.c2.c1,
        base=972_000,
        evaluation_kind="capability_evaluation",
        claimed=True,
    )
    second = register_evaluation(
        harness.c2.c1,
        base=972_100,
        evaluation_kind="capability_evaluation",
        claimed=True,
    )
    components = approved_lesson_components(
        harness,
        base=973_000,
        candidate=candidate,
        transfer_test_id=first.evaluation_record_id,
    )
    harness.persistence.developmental_derivation.create_approved_lesson(
        components[0],
        components[1],
        initial_lifecycle_transition_id=uid(973_004),
        initial_approval_transition_id=uid(973_005),
        approval_transition_id=uid(973_006),
        approved_lifecycle_transition_id=uid(973_007),
        active_lifecycle_transition_id=uid(973_008),
        approval_grant=components[2],
        relationship_grant=components[3],
        relationship=components[4],
    )

    with pytest.raises(ConflictError, match="integrity constraint"):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                INSERT INTO approved_lesson_transfer_tests (
                    record_id, evaluation_record_id, transfer_order
                ) VALUES (?, ?, 1)
                """,
                (components[1].record_id, second.evaluation_record_id),
            )
        )
