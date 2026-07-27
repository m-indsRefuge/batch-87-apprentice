from __future__ import annotations

from dataclasses import replace

import pytest

from batch87_apprentice.common.errors import ConflictError, ValidationError
from batch87_apprentice.memory import FailurePatternPayload, SuccessPatternPayload
from tests.support.i2_fixtures import uid
from tests.support.i3c2_fixtures import (
    create_episode,
    create_terminal_task,
)
from tests.support.i3c3_fixtures import (
    build_c3_harness,
    candidate_components,
    create_active_analysis_task,
    create_source_bundle,
    failure_pattern_components,
    success_pattern_components,
)
from tests.support.sql_probe import SqlProbe


def _episodes(harness, *, base: int, status: str, outcome: str, count: int = 2):
    result = []
    for index in range(count):
        task_id = create_terminal_task(
            harness.c2,
            base=base + index * 1_000,
            status=status,
        )
        envelope, payload, _ = create_episode(
            harness.c2,
            base=base + index * 1_000 + 100,
            task_id=task_id,
            outcome=outcome,
        )
        result.append((envelope, payload))
    return tuple(result)


def _agent_pattern_components(harness, *, pattern_kind: str, base: int):
    analysis_task = create_active_analysis_task(harness, base=base)
    terminal_status = "failed" if pattern_kind == "failure" else "completed"
    sources = _episodes(
        harness,
        base=base + 100,
        status=terminal_status,
        outcome=terminal_status,
    )
    episode_ids = tuple(item[0].record_id for item in sources)
    if pattern_kind == "failure":
        envelope, payload = failure_pattern_components(
            harness,
            base=base + 2_500,
            episode_ids=episode_ids,
        )
        create = harness.persistence.developmental_derivation.create_failure_pattern
    else:
        envelope, payload = success_pattern_components(
            harness,
            base=base + 2_500,
            episode_ids=episode_ids,
        )
        create = harness.persistence.developmental_derivation.create_success_pattern
    return (
        replace(
            envelope,
            created_by_entity_id=harness.agent_id,
            session_id=harness.session_id,
            task_id=analysis_task,
        ),
        payload,
        create,
    )


def test_repeated_failure_pattern_creation_preserves_exact_frequency(
    tmp_path,
) -> None:
    harness = build_c3_harness(tmp_path)
    sources = _episodes(
        harness,
        base=840_000,
        status="failed",
        outcome="failed",
    )
    envelope, payload = failure_pattern_components(
        harness,
        base=843_000,
        episode_ids=tuple(item[0].record_id for item in sources),
    )

    harness.persistence.developmental_derivation.create_failure_pattern(
        envelope,
        payload,
        lifecycle_transition_id=uid(843_001),
        approval_transition_id=uid(843_002),
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )

    rebuilt = harness.persistence.developmental_derivation.reconstruct(
        payload.record_id
    )
    assert rebuilt["integrity_ok"]
    assert rebuilt["payload"]["frequency"] == 2
    assert rebuilt["payload"]["episode_ids"] == [
        item[0].record_id for item in sources
    ]
    assert rebuilt["envelope"]["lifecycle_state"] == "candidate"
    assert rebuilt["envelope"]["approval_status"] == "pending"


def test_repeated_success_pattern_requires_distinct_completed_tasks(
    tmp_path,
) -> None:
    harness = build_c3_harness(tmp_path)
    sources = _episodes(
        harness,
        base=844_000,
        status="completed",
        outcome="completed",
    )
    envelope, payload = success_pattern_components(
        harness,
        base=847_000,
        episode_ids=tuple(item[0].record_id for item in sources),
    )

    harness.persistence.developmental_derivation.create_success_pattern(
        envelope,
        payload,
        lifecycle_transition_id=uid(847_001),
        approval_transition_id=uid(847_002),
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )

    rebuilt = harness.persistence.developmental_derivation.reconstruct(
        payload.record_id
    )
    assert rebuilt["integrity_ok"]
    assert rebuilt["payload"]["stability"] == "emerging"
    assert rebuilt["payload"]["transfer_scope"] == ["same governed project"]


@pytest.mark.parametrize("pattern_kind", ["failure", "success"])
def test_agent_created_pattern_requires_exact_active_analysis_task(
    tmp_path,
    pattern_kind: str,
) -> None:
    harness = build_c3_harness(tmp_path)
    analysis_task = create_active_analysis_task(harness, base=847_100)
    terminal_status = "failed" if pattern_kind == "failure" else "completed"
    sources = _episodes(
        harness,
        base=847_200,
        status=terminal_status,
        outcome=terminal_status,
    )
    episode_ids = tuple(item[0].record_id for item in sources)
    if pattern_kind == "failure":
        envelope, payload = failure_pattern_components(
            harness,
            base=847_500,
            episode_ids=episode_ids,
        )
        create = harness.persistence.developmental_derivation.create_failure_pattern
    else:
        envelope, payload = success_pattern_components(
            harness,
            base=847_500,
            episode_ids=episode_ids,
        )
        create = harness.persistence.developmental_derivation.create_success_pattern
    agent_envelope = replace(
        envelope,
        created_by_entity_id=harness.agent_id,
        session_id=harness.session_id,
    )

    with pytest.raises(
        ValidationError,
        match="requires task|active governed analysis task",
    ):
        create(
            agent_envelope,
            payload,
            lifecycle_transition_id=uid(847_501),
            approval_transition_id=uid(847_502),
            changed_by_principal="codex_development_harness",
        )

    create(
        replace(agent_envelope, task_id=analysis_task),
        payload,
        lifecycle_transition_id=uid(847_503),
        approval_transition_id=uid(847_504),
        changed_by_principal="codex_development_harness",
    )
    report = harness.persistence.developmental_derivation_integrity.inspect()
    assert tuple(
        finding
        for finding in report.findings
        if finding.record_id == payload.record_id
    ) == ()


@pytest.mark.parametrize("pattern_kind", ["failure", "success"])
def test_agent_pattern_historical_integrity_survives_creator_archival(
    tmp_path,
    pattern_kind: str,
) -> None:
    harness = build_c3_harness(tmp_path)
    envelope, payload, create = _agent_pattern_components(
        harness,
        pattern_kind=pattern_kind,
        base=872_000,
    )
    create(
        envelope,
        payload,
        lifecycle_transition_id=uid(874_501),
        approval_transition_id=uid(874_502),
        changed_by_principal="codex_development_harness",
    )
    SqlProbe(harness.config).write(
        lambda connection: connection.execute(
            "UPDATE entities SET status = 'archived' WHERE entity_id = ?",
            (harness.agent_id,),
        )
    )

    report = harness.persistence.developmental_derivation_integrity.inspect()
    assert tuple(
        finding
        for finding in report.findings
        if finding.record_id == payload.record_id
    ) == ()


@pytest.mark.parametrize("pattern_kind", ["failure", "success"])
def test_inactive_agent_cannot_create_new_agent_pattern(
    tmp_path,
    pattern_kind: str,
) -> None:
    harness = build_c3_harness(tmp_path)
    envelope, payload, create = _agent_pattern_components(
        harness,
        pattern_kind=pattern_kind,
        base=875_000,
    )
    SqlProbe(harness.config).write(
        lambda connection: connection.execute(
            "UPDATE entities SET status = 'inactive' WHERE entity_id = ?",
            (harness.agent_id,),
        )
    )

    with pytest.raises(ValidationError, match="active governed analysis task"):
        create(
            envelope,
            payload,
            lifecycle_transition_id=uid(877_501),
            approval_transition_id=uid(877_502),
            changed_by_principal="codex_development_harness",
        )


@pytest.mark.parametrize("pattern_kind", ["failure", "success"])
def test_agent_pattern_creator_kind_mutation_remains_integrity_invalid(
    tmp_path,
    pattern_kind: str,
) -> None:
    harness = build_c3_harness(tmp_path)
    envelope, payload, create = _agent_pattern_components(
        harness,
        pattern_kind=pattern_kind,
        base=878_000,
    )
    create(
        envelope,
        payload,
        lifecycle_transition_id=uid(880_501),
        approval_transition_id=uid(880_502),
        changed_by_principal="codex_development_harness",
    )
    SqlProbe(harness.config).write(
        lambda connection: connection.execute(
            "UPDATE entities SET entity_kind = 'system' WHERE entity_id = ?",
            (harness.agent_id,),
        )
    )

    report = harness.persistence.developmental_derivation_integrity.inspect()
    assert "I3C3-APPRENTICE-TASK" in {
        finding.code
        for finding in report.findings
        if finding.record_id == payload.record_id
    }


@pytest.mark.parametrize("pattern_kind", ["failure", "success"])
def test_operator_pattern_without_apprentice_task_is_not_agent_origin(
    tmp_path,
    pattern_kind: str,
) -> None:
    harness = build_c3_harness(tmp_path)
    terminal_status = "failed" if pattern_kind == "failure" else "completed"
    sources = _episodes(
        harness,
        base=847_600,
        status=terminal_status,
        outcome=terminal_status,
    )
    episode_ids = tuple(item[0].record_id for item in sources)
    if pattern_kind == "failure":
        envelope, payload = failure_pattern_components(
            harness,
            base=847_900,
            episode_ids=episode_ids,
        )
        create = harness.persistence.developmental_derivation.create_failure_pattern
    else:
        envelope, payload = success_pattern_components(
            harness,
            base=847_900,
            episode_ids=episode_ids,
        )
        create = harness.persistence.developmental_derivation.create_success_pattern

    create(
        envelope,
        payload,
        lifecycle_transition_id=uid(847_901),
        approval_transition_id=uid(847_902),
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )

    report = harness.persistence.developmental_derivation_integrity.inspect()
    assert tuple(
        finding
        for finding in report.findings
        if finding.record_id == payload.record_id
    ) == ()


def test_success_pattern_rejects_non_completed_or_same_task_occurrences(
    tmp_path,
) -> None:
    harness = build_c3_harness(tmp_path)
    failed_sources = _episodes(
        harness,
        base=848_000,
        status="failed",
        outcome="failed",
    )
    envelope, payload = success_pattern_components(
        harness,
        base=851_000,
        episode_ids=tuple(item[0].record_id for item in failed_sources),
    )
    with pytest.raises(ValidationError, match="completed episodes"):
        harness.persistence.developmental_derivation.create_success_pattern(
            envelope,
            payload,
            lifecycle_transition_id=uid(851_001),
            approval_transition_id=uid(851_002),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )

    task_id = create_terminal_task(
        harness.c2,
        base=852_000,
        status="completed",
    )
    episode_one, _, _ = create_episode(
        harness.c2,
        base=852_100,
        task_id=task_id,
        outcome="completed",
    )
    episode_two, _, _ = create_episode(
        harness.c2,
        base=852_200,
        task_id=task_id,
        outcome="completed",
    )
    envelope, payload = success_pattern_components(
        harness,
        base=852_300,
        episode_ids=(episode_one.record_id, episode_two.record_id),
    )
    with pytest.raises(ValidationError, match="distinct tasks"):
        harness.persistence.developmental_derivation.create_success_pattern(
            envelope,
            payload,
            lifecycle_transition_id=uid(852_301),
            approval_transition_id=uid(852_302),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )


@pytest.mark.parametrize("record_kind", ["failure", "success"])
def test_one_episode_and_duplicate_patterns_are_rejected_by_contract(
    record_kind: str,
) -> None:
    arguments = {
        "record_id": uid(853_000),
        "pattern_name": "Pattern",
        "description": "Externally reviewable pattern.",
        "episode_ids": (uid(1),),
    }
    with pytest.raises(ValidationError, match="multiple"):
        if record_kind == "failure":
            FailurePatternPayload(
                **arguments,
                frequency=1,
                severity="material",
                containment_required=True,
                resolution_status="open",
            )
        else:
            SuccessPatternPayload(
                **arguments,
                transfer_scope=("scope",),
                stability="emerging",
            )
    with pytest.raises(ValidationError, match="duplicates"):
        if record_kind == "failure":
            FailurePatternPayload(
                **{
                    **arguments,
                    "episode_ids": (uid(1), uid(1)),
                },
                frequency=2,
                severity="material",
                containment_required=True,
                resolution_status="open",
            )
        else:
            SuccessPatternPayload(
                **{
                    **arguments,
                    "episode_ids": (uid(1), uid(1)),
                },
                transfer_scope=("scope",),
                stability="emerging",
            )


def test_candidate_rejects_missing_invalid_revoked_and_cross_project_sources(
    tmp_path,
) -> None:
    harness = build_c3_harness(tmp_path)
    task_id = create_active_analysis_task(harness, base=854_000)
    _, (_, episode), (_, correction) = create_source_bundle(
        harness,
        base=855_000,
    )
    envelope, payload = candidate_components(
        harness,
        base=856_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    repository = harness.persistence.developmental_derivation

    with pytest.raises(ValidationError, match="missing"):
        repository.create_lesson_candidate(
            envelope,
            replace(payload, source_episode_ids=(uid(999_999),)),
            lifecycle_transition_id=uid(856_001),
            approval_transition_id=uid(856_002),
            changed_by_principal="codex_development_harness",
        )

    probe = SqlProbe(harness.config)
    probe.write(
        lambda connection: connection.execute(
            "UPDATE records SET integrity_status = 'mismatch' WHERE record_id = ?",
            (episode.record_id,),
        )
    )
    with pytest.raises(ValidationError, match="invalid"):
        repository.create_lesson_candidate(
            envelope,
            payload,
            lifecycle_transition_id=uid(856_003),
            approval_transition_id=uid(856_004),
            changed_by_principal="codex_development_harness",
        )
    probe.write(
        lambda connection: connection.execute(
            "UPDATE records SET integrity_status = 'valid' WHERE record_id = ?",
            (episode.record_id,),
        )
    )
    probe.corrupt_after_dropping_triggers(
        ("memory_records_lifecycle_requires_transition",),
        lambda connection: connection.execute(
            "UPDATE records SET lifecycle_state = 'revoked' WHERE record_id = ?",
            (episode.record_id,),
        ),
    )
    with pytest.raises(ValidationError, match="revoked"):
        repository.create_lesson_candidate(
            envelope,
            payload,
            lifecycle_transition_id=uid(856_005),
            approval_transition_id=uid(856_006),
            changed_by_principal="codex_development_harness",
        )

    cross_root = tmp_path / "cross_project"
    cross_root.mkdir()
    second = build_c3_harness(cross_root)
    second_task = create_active_analysis_task(second, base=857_000)
    _, (_, second_episode), (_, second_correction) = create_source_bundle(
        second,
        base=858_000,
    )
    second_envelope, second_payload = candidate_components(
        second,
        base=859_000,
        task_id=second_task,
        episode_id=second_episode.record_id,
        correction_id=second_correction.record_id,
    )
    SqlProbe(second.config).corrupt_after_dropping_triggers(
        ("c2_records_core_immutable",),
        lambda connection: connection.execute(
            "UPDATE records SET project_scope_id = ? WHERE record_id = ?",
            (
                second.c2.c1.i2.other_project_scope_id,
                second_episode.record_id,
            ),
        ),
    )
    with pytest.raises(ValidationError, match="out of scope"):
        second.persistence.developmental_derivation.create_lesson_candidate(
            second_envelope,
            second_payload,
            lifecycle_transition_id=uid(859_001),
            approval_transition_id=uid(859_002),
            changed_by_principal="codex_development_harness",
        )


def test_candidate_rejects_correction_not_targeting_supplied_episode(
    tmp_path,
) -> None:
    harness = build_c3_harness(tmp_path)
    task_id = create_active_analysis_task(harness, base=860_000)
    _, (_, source_episode), _ = create_source_bundle(
        harness,
        base=861_000,
    )
    _, _, (_, other_correction) = create_source_bundle(
        harness,
        base=862_000,
    )
    envelope, payload = candidate_components(
        harness,
        base=863_000,
        task_id=task_id,
        episode_id=source_episode.record_id,
        correction_id=other_correction.record_id,
    )

    with pytest.raises(ValidationError, match="does not target"):
        harness.persistence.developmental_derivation.create_lesson_candidate(
            envelope,
            payload,
            lifecycle_transition_id=uid(863_001),
            approval_transition_id=uid(863_002),
            changed_by_principal="codex_development_harness",
        )


def test_raw_controlled_evidence_shape_is_rejected_before_derivation(
    tmp_path,
) -> None:
    harness = build_c3_harness(tmp_path)
    task_id = create_active_analysis_task(harness, base=864_000)
    _, (_, episode), (_, correction) = create_source_bundle(
        harness,
        base=865_000,
    )
    envelope, payload = candidate_components(
        harness,
        base=866_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    evidence_id = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT evidence_id FROM record_evidence_links
            WHERE record_id = ? ORDER BY evidence_id LIMIT 1
            """,
            (episode.record_id,),
        ).fetchone()[0]
    )
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("evidence_core_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE evidence_items SET evidence_kind = 'controlled_prompt'
            WHERE evidence_id = ?
            """,
            (evidence_id,),
        ),
    )

    with pytest.raises(ValidationError, match="controlled"):
        harness.persistence.developmental_derivation.create_lesson_candidate(
            envelope,
            payload,
            lifecycle_transition_id=uid(866_001),
            approval_transition_id=uid(866_002),
            changed_by_principal="codex_development_harness",
        )


def test_post_finalization_lineage_and_evidence_appends_are_rejected(
    tmp_path,
) -> None:
    harness = build_c3_harness(tmp_path)
    sources = _episodes(
        harness,
        base=867_000,
        status="failed",
        outcome="failed",
        count=3,
    )
    envelope, payload = failure_pattern_components(
        harness,
        base=871_000,
        episode_ids=(sources[0][0].record_id, sources[1][0].record_id),
    )
    harness.persistence.developmental_derivation.create_failure_pattern(
        envelope,
        payload,
        lifecycle_transition_id=uid(871_001),
        approval_transition_id=uid(871_002),
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    probe = SqlProbe(harness.config)
    with pytest.raises(ConflictError, match="integrity constraint"):
        probe.write(
            lambda connection: connection.execute(
                """
                INSERT INTO failure_pattern_episodes (
                    record_id, episode_id, episode_order
                ) VALUES (?, ?, 2)
                """,
                (payload.record_id, sources[2][0].record_id),
            )
        )
    extra_evidence = probe.read(
        lambda connection: connection.execute(
            """
            SELECT evidence_id FROM record_evidence_links
            WHERE record_id = ? ORDER BY evidence_id LIMIT 1
            """,
            (sources[2][0].record_id,),
        ).fetchone()[0]
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        probe.write(
            lambda connection: connection.execute(
                """
                INSERT INTO record_evidence_links (
                    record_id, evidence_id, relationship, explanation
                ) VALUES (?, ?, 'derived_from', 'late')
                """,
                (payload.record_id, extra_evidence),
            )
        )
