from __future__ import annotations

from dataclasses import replace

import pytest

from batch87_apprentice.common.errors import ConflictError, ValidationError
from batch87_apprentice.memory import ApprovedLessonPayload
from tests.support.i2_fixtures import authority, evidence, uid
from tests.support.i3c_fixtures import register_evaluation
from tests.support.i3c3_fixtures import (
    approved_lesson_components,
    build_c3_harness,
    create_active_analysis_task,
    create_candidate,
    create_source_bundle,
    review_candidate,
)
from tests.support.sql_probe import SqlProbe


def _reviewed_candidate(tmp_path, *, base: int = 880_000):
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
    review_candidate(
        harness,
        candidate_id=candidate.record_id,
        transition_id=uid(base + 2_010),
    )
    return harness, candidate


def _call_atomic(
    harness,
    *,
    base: int,
    envelope,
    payload,
    approval_grant,
    relationship_grant,
    relationship,
):
    return harness.persistence.developmental_derivation.create_approved_lesson(
        envelope,
        payload,
        initial_lifecycle_transition_id=uid(base + 4),
        initial_approval_transition_id=uid(base + 5),
        approval_transition_id=uid(base + 6),
        approved_lifecycle_transition_id=uid(base + 7),
        active_lifecycle_transition_id=uid(base + 8),
        approval_grant=approval_grant,
        relationship_grant=relationship_grant,
        relationship=relationship,
    )


@pytest.mark.parametrize("anchor_case", ["missing", "unclaimed", "cross_project"])
def test_approved_lesson_requires_claimed_same_project_transfer_test(
    tmp_path,
    anchor_case: str,
) -> None:
    harness, candidate = _reviewed_candidate(tmp_path)
    if anchor_case == "missing":
        transfer_id = uid(883_900)
    else:
        transfer = register_evaluation(
            harness.c2.c1,
            base=883_000,
            evaluation_kind="capability_evaluation",
            claimed=anchor_case != "unclaimed",
            project_scope_id=(
                harness.c2.c1.i2.other_project_scope_id
                if anchor_case == "cross_project"
                else harness.project_scope_id
            ),
        )
        transfer_id = transfer.evaluation_record_id
    components = approved_lesson_components(
        harness,
        base=884_000,
        candidate=candidate,
        transfer_test_id=transfer_id,
    )

    with pytest.raises(ValidationError, match="transfer test"):
        _call_atomic(
            harness,
            base=884_000,
            envelope=components[0],
            payload=components[1],
            approval_grant=components[2],
            relationship_grant=components[3],
            relationship=components[4],
        )
    assert SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            "SELECT 1 FROM records WHERE record_id = ?",
            (components[1].record_id,),
        ).fetchone()
    ) is None


@pytest.mark.parametrize(
    "removal_step",
    ["evidence_links", "approved_as_relationship"],
)
def test_approved_lesson_requires_exact_support_at_finalization_and_activation(
    tmp_path,
    monkeypatch,
    removal_step: str,
) -> None:
    harness, candidate = _reviewed_candidate(tmp_path, base=884_100)
    transfer = register_evaluation(
        harness.c2.c1,
        base=884_500,
        evaluation_kind="capability_evaluation",
        claimed=True,
    )
    components = approved_lesson_components(
        harness,
        base=884_600,
        candidate=candidate,
        transfer_test_id=transfer.evaluation_record_id,
    )
    repository = harness.persistence.developmental_derivation

    def remove_exact_support(step, connection) -> None:
        if step != removal_step:
            return
        connection.execute(
            "DROP TRIGGER developmental_evidence_link_delete_guard"
        )
        connection.execute(
            """
            DELETE FROM record_evidence_links
            WHERE record_id = ? AND evidence_id = ?
              AND relationship = 'supports'
            """,
            (components[1].record_id, components[2].evidence_id),
        )

    monkeypatch.setattr(repository, "_after_write_step", remove_exact_support)
    with pytest.raises(ConflictError, match="integrity constraint"):
        _call_atomic(
            harness,
            base=884_600,
            envelope=components[0],
            payload=components[1],
            approval_grant=components[2],
            relationship_grant=components[3],
            relationship=components[4],
        )

    assert SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            "SELECT 1 FROM records WHERE record_id = ?",
            (components[1].record_id,),
        ).fetchone()
    ) is None


def test_transfer_provenance_invalidated_before_activation_blocks_lesson(
    tmp_path,
    monkeypatch,
) -> None:
    harness, candidate = _reviewed_candidate(tmp_path, base=884_700)
    transfer = register_evaluation(
        harness.c2.c1,
        base=885_000,
        evaluation_kind="capability_evaluation",
        claimed=True,
    )
    components = approved_lesson_components(
        harness,
        base=885_100,
        candidate=candidate,
        transfer_test_id=transfer.evaluation_record_id,
    )
    repository = harness.persistence.developmental_derivation

    def invalidate_before_activation(step, connection) -> None:
        if step != "approved_as_relationship":
            return
        connection.execute("DROP TRIGGER evidence_core_immutable")
        connection.execute(
            """
            UPDATE evidence_items
            SET integrity_status = 'mismatch'
            WHERE evidence_id = ?
            """,
            (transfer.provenance_evidence_id,),
        )

    monkeypatch.setattr(
        repository,
        "_after_write_step",
        invalidate_before_activation,
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        _call_atomic(
            harness,
            base=885_100,
            envelope=components[0],
            payload=components[1],
            approval_grant=components[2],
            relationship_grant=components[3],
            relationship=components[4],
        )

    probe = SqlProbe(harness.config)
    record, provenance_status = probe.read(
        lambda connection: (
            connection.execute(
                "SELECT 1 FROM records WHERE record_id = ?",
                (components[1].record_id,),
            ).fetchone(),
            connection.execute(
                """
                SELECT integrity_status
                FROM evidence_items
                WHERE evidence_id = ?
                """,
                (transfer.provenance_evidence_id,),
            ).fetchone()[0],
        )
    )
    assert record is None
    assert provenance_status == "valid"


def test_approved_lesson_rejects_non_nolan_byte_authority(tmp_path) -> None:
    harness, candidate = _reviewed_candidate(tmp_path)
    transfer = register_evaluation(
        harness.c2.c1,
        base=885_000,
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
        base=886_000,
        candidate=candidate,
        transfer_test_id=transfer.evaluation_record_id,
    )
    authority_evidence = evidence(
        886_100,
        content="Nolan-only evidence cannot approve a C3 lesson.",
        captured_by_entity=harness.operator_id,
    )
    authority_record = authority(
        harness.c2.c1.i2,
        886_101,
        authority_class="nolan_approved",
        issuer_entity_id=harness.operator_id,
        evidence_ids=(authority_evidence.evidence_id,),
    )
    harness.runtime.register_authority(
        authority_record,
        evidence_items=(authority_evidence,),
    )
    approval_grant = replace(
        approval_grant,
        authority_record_id=authority_record.authority_record_id,
        evidence_id=authority_evidence.evidence_id,
    )
    relationship_grant = replace(
        relationship_grant,
        authority_record_id=authority_record.authority_record_id,
        evidence_id=authority_evidence.evidence_id,
    )

    with pytest.raises(ValidationError, match="type-insufficient"):
        _call_atomic(
            harness,
            base=886_000,
            envelope=envelope,
            payload=payload,
            approval_grant=approval_grant,
            relationship_grant=relationship_grant,
            relationship=relationship,
        )


def test_approved_lesson_rejects_sources_not_supported_by_candidate(
    tmp_path,
) -> None:
    harness, candidate = _reviewed_candidate(tmp_path)
    _, (_, other_episode), (_, other_correction) = create_source_bundle(
        harness,
        base=887_000,
    )
    transfer = register_evaluation(
        harness.c2.c1,
        base=888_000,
        evaluation_kind="capability_evaluation",
        claimed=True,
    )
    components = approved_lesson_components(
        harness,
        base=889_000,
        candidate=candidate,
        transfer_test_id=transfer.evaluation_record_id,
    )
    payload = ApprovedLessonPayload(
        record_id=components[1].record_id,
        candidate_record_id=candidate.record_id,
        lesson_statement=candidate.lesson_statement,
        application_conditions=components[1].application_conditions,
        non_application_conditions=components[1].non_application_conditions,
        source_episode_ids=(
            *candidate.source_episode_ids,
            other_episode.record_id,
        ),
        source_correction_ids=(
            *candidate.source_correction_ids,
            other_correction.record_id,
        ),
        transfer_test_evaluation_ids=(transfer.evaluation_record_id,),
        stability="new",
    )

    with pytest.raises(ValidationError, match="unsupported sources"):
        _call_atomic(
            harness,
            base=889_000,
            envelope=components[0],
            payload=payload,
            approval_grant=components[2],
            relationship_grant=components[3],
            relationship=components[4],
        )


@pytest.mark.parametrize(
    "failure_step",
    [
        "validated_candidate",
        "record",
        "payload_and_lineage",
        "approval_grant",
        "relationship_grant",
        "evidence_links",
        "histories",
        "approval_transition",
        "approved_state",
        "approved_as_relationship",
        "active_state",
    ],
)
def test_approved_lesson_rolls_back_every_injected_write_boundary(
    tmp_path,
    monkeypatch,
    failure_step: str,
) -> None:
    harness, candidate = _reviewed_candidate(tmp_path, base=890_000)
    transfer = register_evaluation(
        harness.c2.c1,
        base=893_000,
        evaluation_kind="capability_evaluation",
        claimed=True,
    )
    components = approved_lesson_components(
        harness,
        base=894_000,
        candidate=candidate,
        transfer_test_id=transfer.evaluation_record_id,
    )
    repository = harness.persistence.developmental_derivation

    def fail(step, connection) -> None:
        if step == failure_step:
            raise RuntimeError(f"injected-{step}")

    monkeypatch.setattr(repository, "_after_write_step", fail)
    with pytest.raises(RuntimeError, match="injected"):
        _call_atomic(
            harness,
            base=894_000,
            envelope=components[0],
            payload=components[1],
            approval_grant=components[2],
            relationship_grant=components[3],
            relationship=components[4],
        )

    probe = SqlProbe(harness.config)
    counts = probe.read(
        lambda connection: {
            "record": connection.execute(
                "SELECT COUNT(*) FROM records WHERE record_id = ?",
                (components[1].record_id,),
            ).fetchone()[0],
            "payload": connection.execute(
                "SELECT COUNT(*) FROM approved_lessons WHERE record_id = ?",
                (components[1].record_id,),
            ).fetchone()[0],
            "approval_grant": connection.execute(
                "SELECT COUNT(*) FROM memory_approval_grants WHERE grant_id = ?",
                (components[2].grant_id,),
            ).fetchone()[0],
            "relationship_grant": connection.execute(
                "SELECT COUNT(*) FROM memory_relationship_grants WHERE grant_id = ?",
                (components[3].grant_id,),
            ).fetchone()[0],
            "relationship": connection.execute(
                "SELECT COUNT(*) FROM record_relationships WHERE relationship_id = ?",
                (components[4].relationship_id,),
            ).fetchone()[0],
            "evidence_links": connection.execute(
                "SELECT COUNT(*) FROM record_evidence_links WHERE record_id = ?",
                (components[1].record_id,),
            ).fetchone()[0],
            "histories": connection.execute(
                """
                SELECT (
                    SELECT COUNT(*) FROM memory_record_lifecycle_transitions
                    WHERE record_id = ?
                ) + (
                    SELECT COUNT(*) FROM memory_record_approval_transitions
                    WHERE record_id = ?
                )
                """,
                (components[1].record_id, components[1].record_id),
            ).fetchone()[0],
        }
    )
    assert counts == {
        "record": 0,
        "payload": 0,
        "approval_grant": 0,
        "relationship_grant": 0,
        "relationship": 0,
        "evidence_links": 0,
        "histories": 0,
    }
    candidate_row = probe.read(
        lambda connection: connection.execute(
            """
            SELECT record_type, lifecycle_state, approval_status
            FROM records WHERE record_id = ?
            """,
            (candidate.record_id,),
        ).fetchone()
    )
    assert tuple(candidate_row) == ("lesson_candidate", "reviewed", "pending")


def test_atomic_approval_does_not_mutate_unrelated_developmental_authority(
    tmp_path,
) -> None:
    harness, candidate = _reviewed_candidate(tmp_path, base=900_000)
    transfer = register_evaluation(
        harness.c2.c1,
        base=903_000,
        evaluation_kind="capability_evaluation",
        claimed=True,
    )
    components = approved_lesson_components(
        harness,
        base=904_000,
        candidate=candidate,
        transfer_test_id=transfer.evaluation_record_id,
    )
    probe = SqlProbe(harness.config)
    before = probe.read(
        lambda connection: (
            tuple(connection.execute("SELECT * FROM capability_observations")),
            tuple(connection.execute("SELECT * FROM maturity_states")),
            tuple(connection.execute("SELECT * FROM permission_profiles")),
        )
    )

    _call_atomic(
        harness,
        base=904_000,
        envelope=components[0],
        payload=components[1],
        approval_grant=components[2],
        relationship_grant=components[3],
        relationship=components[4],
    )

    after = probe.read(
        lambda connection: (
            tuple(connection.execute("SELECT * FROM capability_observations")),
            tuple(connection.execute("SELECT * FROM maturity_states")),
            tuple(connection.execute("SELECT * FROM permission_profiles")),
        )
    )
    assert after == before
