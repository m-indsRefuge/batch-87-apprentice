from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from batch87_apprentice.common.errors import ConflictError, ValidationError
from batch87_apprentice.memory import (
    ActiveUncertaintyPayload,
    TypedSourceReference,
    UncertaintyResolution,
)
from tests.support.i2_fixtures import EARLIER, LATER, NOW, evidence, uid
from tests.support.i3c_fixtures import register_evaluation
from tests.support.i3c3_fixtures import (
    approved_lesson_components,
    create_active_analysis_task,
    create_candidate,
    create_source_bundle,
    review_candidate,
)
from tests.support.i3d_fixtures import (
    I3DHarness,
    build_i3d_harness,
    context_item,
    create_other_project_task_evidence,
    create_uncertainty,
    source_hash,
    uncertainty_components,
)
from tests.support.sql_probe import SqlProbe


@pytest.fixture
def harness(tmp_path: Path) -> I3DHarness:
    return build_i3d_harness(tmp_path, base=930_000)


def resolution(
    harness: I3DHarness,
    *,
    base: int,
    uncertainty_record_id: str,
    source: TypedSourceReference | None = None,
    resolved_at: str = NOW,
    source_content_hash: str | None = None,
) -> UncertaintyResolution:
    if source is None:
        source = TypedSourceReference(evidence_id=harness.task_evidence_id)
    return UncertaintyResolution(
        resolution_id=uid(base),
        uncertainty_record_id=uncertainty_record_id,
        task_id=harness.task_id,
        session_id=harness.session_id,
        project_scope_id=harness.project_scope_id,
        source=source,
        source_content_hash=(
            source_hash(harness, source)
            if source_content_hash is None
            else source_content_hash
        ),
        resolved_at=resolved_at,
        created_by_principal="operator",
    )


def finalized_context(harness: I3DHarness, *, base: int) -> None:
    harness.persistence.session_task_memory.add_context_item(
        context_item(harness, base=base)
    )
    harness.persistence.session_task_memory.finalize_context(
        harness.task_id,
        finalization_id=uid(base + 1),
        finalized_at=NOW,
        finalized_by_principal="operator",
    )


def task_bound_memory_source(
    harness: I3DHarness,
    *,
    base: int,
) -> TypedSourceReference:
    _, episode_bundle, correction_bundle = create_source_bundle(
        harness.c3,
        base=base,
    )
    episode, _ = episode_bundle
    correction, _ = correction_bundle
    candidate_task_id = create_active_analysis_task(
        harness.c3,
        base=base + 1_000,
    )
    _, candidate = create_candidate(
        harness.c3,
        base=base + 2_000,
        task_id=candidate_task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    review_candidate(
        harness.c3,
        candidate_id=candidate.record_id,
        transition_id=uid(base + 2_003),
    )
    transfer = register_evaluation(
        harness.c3.c2.c1,
        base=base + 3_040,
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
        harness.c3,
        base=base + 3_000,
        candidate=candidate,
        transfer_test_id=transfer.evaluation_record_id,
    )
    task_bound_envelope = replace(
        envelope,
        task_id=harness.task_id,
        session_id=harness.session_id,
    )
    harness.persistence.developmental_derivation.create_approved_lesson(
        task_bound_envelope,
        payload,
        initial_lifecycle_transition_id=uid(base + 3_004),
        initial_approval_transition_id=uid(base + 3_005),
        approval_transition_id=uid(base + 3_006),
        approved_lifecycle_transition_id=uid(base + 3_007),
        active_lifecycle_transition_id=uid(base + 3_008),
        approval_grant=approval_grant,
        relationship_grant=relationship_grant,
        relationship=relationship,
    )
    return TypedSourceReference(memory_record_id=payload.record_id)


def test_valid_uncertainty_is_exactly_task_session_project_bound(
    harness: I3DHarness,
) -> None:
    envelope, payload = create_uncertainty(
        harness,
        base=931_000,
        impact="high",
    )
    row = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            "SELECT * FROM active_uncertainties WHERE record_id = ?",
            (payload.record_id,),
        ).fetchone()
    )
    assert row["task_id"] == harness.task_id == envelope.task_id
    assert row["session_id"] == harness.session_id == envelope.session_id
    assert row["project_scope_id"] == (
        harness.project_scope_id
    ) == envelope.project_scope_id
    assert row["resolution_required"] == 1
    assert harness.persistence.session_task_integrity.inspect().ok


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("task_id", uid(931_101)),
        ("session_id", uid(931_102)),
        ("project_scope_id", uid(931_103)),
    ),
)
def test_wrong_task_session_or_project_uncertainty_fails(
    harness: I3DHarness,
    field: str,
    value: str,
) -> None:
    envelope, payload = uncertainty_components(
        harness,
        base=931_110,
        **{field: value},
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.create_uncertainty(
            envelope,
            payload,
            lifecycle_transition_id=uid(931_111),
            approval_transition_id=uid(931_112),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )


def test_uncertainty_creation_after_task_termination_fails(
    harness: I3DHarness,
) -> None:
    harness.runtime.transition_task(
        harness.task_id,
        to_status="completed",
        reason_code="task_complete",
    )
    envelope, payload = uncertainty_components(harness, base=931_200)
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.create_uncertainty(
            envelope,
            payload,
            lifecycle_transition_id=uid(931_201),
            approval_transition_id=uid(931_202),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )


def test_original_uncertainty_is_immutable(
    harness: I3DHarness,
) -> None:
    _, payload = create_uncertainty(harness, base=931_300)
    probe = SqlProbe(harness.config)
    with pytest.raises(ConflictError, match="integrity constraint"):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE active_uncertainties
                SET uncertainty_statement = 'rewritten'
                WHERE record_id = ?
                """,
                (payload.record_id,),
            )
        )
    with pytest.raises(ConflictError, match="integrity constraint"):
        probe.write(
            lambda connection: connection.execute(
                "DELETE FROM active_uncertainties WHERE record_id = ?",
                (payload.record_id,),
            )
        )


def test_resolution_is_append_only_and_cannot_predate_uncertainty(
    harness: I3DHarness,
) -> None:
    _, payload = create_uncertainty(harness, base=931_400)
    early = resolution(
        harness,
        base=931_403,
        uncertainty_record_id=payload.record_id,
        resolved_at=EARLIER,
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.resolve_uncertainty(early)

    accepted = resolution(
        harness,
        base=931_404,
        uncertainty_record_id=payload.record_id,
    )
    harness.persistence.session_task_memory.resolve_uncertainty(accepted)
    probe = SqlProbe(harness.config)
    with pytest.raises(ConflictError, match="integrity constraint"):
        probe.write(
            lambda connection: connection.execute(
                """
                UPDATE uncertainty_resolutions SET resolved_at = ?
                WHERE resolution_id = ?
                """,
                (EARLIER, accepted.resolution_id),
            )
        )
    with pytest.raises(ConflictError, match="integrity constraint"):
        probe.write(
            lambda connection: connection.execute(
                "DELETE FROM uncertainty_resolutions WHERE resolution_id = ?",
                (accepted.resolution_id,),
            )
        )


def test_missing_or_unbound_resolution_source_fails(
    harness: I3DHarness,
) -> None:
    _, payload = create_uncertainty(harness, base=931_500)
    missing = TypedSourceReference(evidence_id=uid(931_503))
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.resolve_uncertainty(
            resolution(
                harness,
                base=931_504,
                uncertainty_record_id=payload.record_id,
                source=missing,
                source_content_hash="a" * 64,
            )
        )

    unbound_item = evidence(
        931_506,
        content="Valid evidence that is not bound to this governed task.",
        captured_by_entity=harness.operator_id,
    )
    harness.persistence.evidence.create(unbound_item)
    unbound = TypedSourceReference(evidence_id=unbound_item.evidence_id)
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.resolve_uncertainty(
            resolution(
                harness,
                base=931_505,
                uncertainty_record_id=payload.record_id,
                source=unbound,
            )
        )


def test_cross_project_resolution_source_fails(
    harness: I3DHarness,
) -> None:
    _, payload = create_uncertainty(harness, base=931_550)
    evidence_id = create_other_project_task_evidence(
        harness,
        base=931_560,
    )
    source = TypedSourceReference(evidence_id=evidence_id)
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.resolve_uncertainty(
            resolution(
                harness,
                base=931_564,
                uncertainty_record_id=payload.record_id,
                source=source,
            )
        )


def test_uncertainty_can_be_resolved_at_most_once(
    harness: I3DHarness,
) -> None:
    _, payload = create_uncertainty(harness, base=931_600)
    first = resolution(
        harness,
        base=931_603,
        uncertainty_record_id=payload.record_id,
    )
    harness.persistence.session_task_memory.resolve_uncertainty(first)
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.resolve_uncertainty(
            resolution(
                harness,
                base=931_604,
                uncertainty_record_id=payload.record_id,
            )
        )


def test_resolved_uncertainty_leaves_active_set_but_remains_in_history(
    harness: I3DHarness,
) -> None:
    _, payload = create_uncertainty(
        harness,
        base=931_700,
        impact="blocking",
    )
    accepted = resolution(
        harness,
        base=931_703,
        uncertainty_record_id=payload.record_id,
    )
    harness.persistence.session_task_memory.resolve_uncertainty(accepted)
    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id
    )["value"]

    assert projection["uncertainties"]["active"] == []
    assert projection["uncertainties"]["resolved"][0]["uncertainty"][
        "record_id"
    ] == payload.record_id
    assert projection["uncertainties"]["history"][0]["resolution"][
        "resolution_id"
    ] == accepted.resolution_id


def test_unresolved_blocking_uncertainty_blocks_context_readiness(
    harness: I3DHarness,
) -> None:
    finalized_context(harness, base=931_800)
    _, payload = create_uncertainty(
        harness,
        base=931_810,
        impact="blocking",
    )
    before = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )["value"]
    assert not before["context_ready"]

    harness.persistence.session_task_memory.resolve_uncertainty(
        resolution(
            harness,
            base=931_813,
            uncertainty_record_id=payload.record_id,
        )
    )
    after = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )["value"]
    assert after["context_ready"]


@pytest.mark.parametrize(
    ("invalidation", "expected_reason"),
    (
        ("revoked", "source_revoked"),
        ("deleted", "source_deleted"),
        ("integrity_mismatch", "source_integrity_invalid"),
    ),
)
def test_invalid_memory_resolution_basis_reactivates_blocking_uncertainty(
    harness: I3DHarness,
    invalidation: str,
    expected_reason: str,
) -> None:
    finalized_context(harness, base=932_100)
    source = task_bound_memory_source(harness, base=950_000)
    _, payload = create_uncertainty(
        harness,
        base=954_000,
        impact="blocking",
    )
    unresolved = (
        harness.persistence.session_task_memory.reconstruct_task_memory(
            harness.task_id,
            mode="active",
        )["value"]
    )
    assert not unresolved["context_ready"]
    assert [item["record_id"] for item in unresolved["uncertainties"]["active"]] == [
        payload.record_id
    ]

    accepted = resolution(
        harness,
        base=954_003,
        uncertainty_record_id=payload.record_id,
        source=source,
    )
    harness.persistence.session_task_memory.resolve_uncertainty(accepted)
    resolved = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )["value"]
    assert resolved["context_ready"]
    assert resolved["uncertainties"]["active"] == []
    assert resolved["uncertainties"]["history"][0]["resolution"]["effective"]

    if invalidation == "integrity_mismatch":
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                UPDATE records SET integrity_status = 'mismatch'
                WHERE record_id = ?
                """,
                (source.memory_record_id,),
            )
        )
    else:
        harness.c3.memory.transition_lifecycle(
            source.memory_record_id or "",
            transition_id=uid(954_010),
            to_state=invalidation,
            reason_code=f"resolution_source_{invalidation}",
            changed_at=LATER,
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )

    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )["value"]
    history_resolution = projection["uncertainties"]["history"][0][
        "resolution"
    ]
    dedicated_codes = {
        finding.code
        for finding in harness.persistence.session_task_integrity.inspect().findings
    }
    top_codes = {
        finding.code
        for finding in harness.persistence.integrity.inspect().findings
    }

    assert not projection["context_ready"]
    assert [item["record_id"] for item in projection["uncertainties"]["active"]] == [
        payload.record_id
    ]
    assert history_resolution["resolution_id"] == accepted.resolution_id
    assert not history_resolution["effective"]
    assert expected_reason in history_resolution["ineffective_reasons"]
    assert "I3D-RESOLUTION-SOURCE" in dedicated_codes
    assert "session_task_i3d_resolution_source" in top_codes


@pytest.mark.parametrize(
    "withdrawn_lifecycle",
    ("archived", "revoked", "deleted"),
)
def test_withdrawn_uncertainty_leaves_active_set_but_preserves_history(
    harness: I3DHarness,
    withdrawn_lifecycle: str,
) -> None:
    finalized_context(harness, base=955_000)
    _, payload = create_uncertainty(
        harness,
        base=955_010,
        impact="blocking",
    )
    before = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )["value"]
    assert not before["context_ready"]

    harness.c3.memory.transition_lifecycle(
        payload.record_id,
        transition_id=uid(955_013),
        to_state=withdrawn_lifecycle,
        reason_code=f"uncertainty_{withdrawn_lifecycle}",
        changed_at=LATER,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    after = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )["value"]

    historical = after["uncertainties"]["history"][0]["uncertainty"]
    session_projection = (
        harness.persistence.session_task_memory.reconstruct_session_memory(
            harness.session_id
        )
    )
    assert after["context_ready"]
    assert after["uncertainties"]["active"] == []
    assert historical["record_id"] == payload.record_id
    assert historical["lifecycle_state"] == withdrawn_lifecycle
    assert historical["current"] is False
    assert historical["inactive_reasons"] == [
        f"lifecycle_{withdrawn_lifecycle}"
    ]
    assert session_projection["integrity_verified"]


@pytest.mark.parametrize(
    "corruption",
    (
        "lifecycle_sequence",
        "lifecycle_canonical",
        "lifecycle_hash",
        "envelope_lifecycle",
        "approval_sequence",
        "approval_hash",
    ),
)
def test_complete_uncertainty_history_corruption_fails_closed(
    harness: I3DHarness,
    corruption: str,
) -> None:
    finalized_context(harness, base=957_000)
    _, payload = create_uncertainty(
        harness,
        base=957_010,
        impact="blocking",
    )
    unresolved = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )["value"]
    assert not unresolved["context_ready"]
    assert [item["record_id"] for item in unresolved["uncertainties"]["active"]] == [
        payload.record_id
    ]

    archive_transition_id = uid(957_013)
    harness.c3.memory.transition_lifecycle(
        payload.record_id,
        transition_id=archive_transition_id,
        to_state="archived",
        reason_code="valid_uncertainty_archive",
        changed_at=LATER,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    archived = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )["value"]
    assert archived["context_ready"]
    assert archived["uncertainties"]["active"] == []
    assert archived["uncertainties"]["history"][0]["uncertainty"][
        "lifecycle_state"
    ] == "archived"

    if corruption == "lifecycle_sequence":
        triggers = ("memory_lifecycle_transitions_immutable",)
        statement = """
            UPDATE memory_record_lifecycle_transitions
            SET sequence_number = 3
            WHERE transition_id = ?
        """
        parameters = (archive_transition_id,)
    elif corruption == "lifecycle_canonical":
        triggers = ("memory_lifecycle_transitions_immutable",)
        statement = """
            UPDATE memory_record_lifecycle_transitions
            SET canonical_json = '{}'
            WHERE transition_id = ?
        """
        parameters = (archive_transition_id,)
    elif corruption == "lifecycle_hash":
        triggers = ("memory_lifecycle_transitions_immutable",)
        statement = """
            UPDATE memory_record_lifecycle_transitions
            SET content_hash = ?
            WHERE transition_id = ?
        """
        parameters = ("0" * 64, archive_transition_id)
    elif corruption == "envelope_lifecycle":
        triggers = ("memory_records_lifecycle_requires_transition",)
        statement = """
            UPDATE records SET lifecycle_state = 'observed'
            WHERE record_id = ?
        """
        parameters = (payload.record_id,)
    elif corruption == "approval_sequence":
        triggers = ("memory_approval_transitions_immutable",)
        statement = """
            UPDATE memory_record_approval_transitions
            SET sequence_number = 2
            WHERE transition_id = ?
        """
        parameters = (uid(957_012),)
    else:
        triggers = ("memory_approval_transitions_immutable",)
        statement = """
            UPDATE memory_record_approval_transitions
            SET content_hash = ?
            WHERE transition_id = ?
        """
        parameters = ("0" * 64, uid(957_012))
    def corrupt_history(connection) -> None:
        if corruption == "approval_sequence":
            connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(statement, parameters)

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        triggers,
        corrupt_history,
    )

    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )["value"]
    session_projection = (
        harness.persistence.session_task_memory.reconstruct_session_memory(
            harness.session_id
        )
    )
    historical = projection["uncertainties"]["history"][0]["uncertainty"]
    dedicated_codes = {
        finding.code
        for finding in harness.persistence.session_task_integrity.inspect().findings
    }
    top_codes = {
        finding.code
        for finding in harness.persistence.integrity.inspect().findings
    }

    assert not projection["context_ready"]
    assert not projection["integrity"]["valid"]
    assert projection["uncertainties"]["active"] == []
    assert historical["record_id"] == payload.record_id
    assert historical["current"] is False
    assert "integrity_finding" in historical["inactive_reasons"]
    assert "I3D-UNCERTAINTY-HISTORY" in dedicated_codes
    assert "session_task_i3d_uncertainty_history" in top_codes
    assert not session_projection["integrity_verified"]
    assert harness.task_id in session_projection["value"]["integrity"]["summary"][
        "affected_task_ids"
    ]


def test_integrity_invalid_uncertainty_is_not_presented_as_valid_active_state(
    harness: I3DHarness,
) -> None:
    finalized_context(harness, base=955_100)
    _, payload = create_uncertainty(
        harness,
        base=955_110,
        impact="blocking",
    )
    SqlProbe(harness.config).write(
        lambda connection: connection.execute(
            """
            UPDATE records SET integrity_status = 'mismatch'
            WHERE record_id = ?
            """,
            (payload.record_id,),
        )
    )

    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )["value"]
    historical = projection["uncertainties"]["history"][0]["uncertainty"]

    assert not projection["context_ready"]
    assert projection["uncertainties"]["active"] == []
    assert historical["record_id"] == payload.record_id
    assert historical["current"] is False
    assert "integrity_status_invalid" in historical["inactive_reasons"]
    assert "I3D-UNCERTAINTY-CANONICAL" in {
        finding.code
        for finding in harness.persistence.session_task_integrity.inspect().findings
    }


def test_later_archive_preserves_valid_memory_resolution_history(
    harness: I3DHarness,
) -> None:
    finalized_context(harness, base=956_000)
    source = task_bound_memory_source(harness, base=960_000)
    _, payload = create_uncertainty(
        harness,
        base=964_000,
        impact="blocking",
    )
    accepted = resolution(
        harness,
        base=964_003,
        uncertainty_record_id=payload.record_id,
        source=source,
    )
    harness.persistence.session_task_memory.resolve_uncertainty(accepted)
    harness.c3.memory.transition_lifecycle(
        source.memory_record_id or "",
        transition_id=uid(964_004),
        to_state="archived",
        reason_code="ordinary_source_archive",
        changed_at=LATER,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )

    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )["value"]
    historical_resolution = projection["uncertainties"]["history"][0][
        "resolution"
    ]
    assert projection["context_ready"]
    assert projection["uncertainties"]["active"] == []
    assert historical_resolution["resolution_id"] == accepted.resolution_id
    assert historical_resolution["effective"]
    assert historical_resolution["ineffective_reasons"] == []
    assert harness.persistence.session_task_integrity.inspect().ok


def test_evidence_integrity_invalidation_makes_resolution_ineffective(
    harness: I3DHarness,
) -> None:
    finalized_context(harness, base=965_000)
    _, payload = create_uncertainty(
        harness,
        base=965_010,
        impact="blocking",
    )
    accepted = resolution(
        harness,
        base=965_013,
        uncertainty_record_id=payload.record_id,
    )
    harness.persistence.session_task_memory.resolve_uncertainty(accepted)
    SqlProbe(harness.config).write(
        lambda connection: connection.execute(
            """
            UPDATE evidence_items SET integrity_status = 'mismatch'
            WHERE evidence_id = ?
            """,
            (harness.task_evidence_id,),
        )
    )

    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )["value"]
    historical_resolution = projection["uncertainties"]["history"][0][
        "resolution"
    ]
    assert not projection["context_ready"]
    assert [item["record_id"] for item in projection["uncertainties"]["active"]] == [
        payload.record_id
    ]
    assert historical_resolution["resolution_id"] == accepted.resolution_id
    assert not historical_resolution["effective"]
    assert "source_integrity_invalid" in historical_resolution[
        "ineffective_reasons"
    ]
    assert "I3D-RESOLUTION-SOURCE" in {
        finding.code
        for finding in harness.persistence.session_task_integrity.inspect().findings
    }
    assert "session_task_i3d_resolution_source" in {
        finding.code
        for finding in harness.persistence.integrity.inspect().findings
    }


def test_loss_of_exact_task_decision_evidence_relationship_is_detected(
    harness: I3DHarness,
) -> None:
    finalized_context(harness, base=966_000)
    _, payload = create_uncertainty(
        harness,
        base=966_010,
        impact="blocking",
    )
    accepted = resolution(
        harness,
        base=966_013,
        uncertainty_record_id=payload.record_id,
    )
    harness.persistence.session_task_memory.resolve_uncertainty(accepted)
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("governance_decision_evidence_no_delete",),
        lambda connection: connection.execute(
            """
            DELETE FROM governance_decision_evidence
            WHERE governance_decision_id = (
                SELECT governance_decision_id
                FROM governance_decisions
                WHERE task_id = ?
            )
              AND required_evidence_id = ?
              AND resolved_evidence_id = ?
              AND validation_status = 'available'
            """,
            (
                harness.task_id,
                harness.task_evidence_id,
                harness.task_evidence_id,
            ),
        ),
    )

    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
    )["value"]
    historical_resolution = projection["uncertainties"]["history"][0][
        "resolution"
    ]
    dedicated_codes = {
        finding.code
        for finding in harness.persistence.session_task_integrity.inspect().findings
    }
    top_codes = {
        finding.code
        for finding in harness.persistence.integrity.inspect().findings
    }
    assert not projection["context_ready"]
    assert [item["record_id"] for item in projection["uncertainties"]["active"]] == [
        payload.record_id
    ]
    assert historical_resolution["resolution_id"] == accepted.resolution_id
    assert not historical_resolution["effective"]
    assert "source_not_task_bound" in historical_resolution[
        "ineffective_reasons"
    ]
    assert "I3D-RESOLUTION-SOURCE" in dedicated_codes
    assert "session_task_i3d_resolution_source" in top_codes


def test_creator_attribution_and_allowed_principals_are_enforced(
    harness: I3DHarness,
) -> None:
    with pytest.raises(ValidationError, match="created_by_principal"):
        ActiveUncertaintyPayload(
            record_id=uid(931_900),
            task_id=harness.task_id,
            session_id=harness.session_id,
            project_scope_id=harness.project_scope_id,
            uncertainty_statement="Invalid model-authored uncertainty.",
            impact="medium",
            resolution_required=False,
            created_at=NOW,
            created_by_principal="apprentice",
        )

    envelope, payload = uncertainty_components(harness, base=931_910)
    wrong_creator = replace(
        envelope,
        created_by_entity_id=harness.c3.c2.c1.i2.participant_id,
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.create_uncertainty(
            wrong_creator,
            payload,
            lifecycle_transition_id=uid(931_911),
            approval_transition_id=uid(931_912),
            changed_by_principal="operator",
            changed_by_entity_id=harness.c3.c2.c1.i2.participant_id,
        )


def test_resolution_from_controlled_evidence_fails(
    harness: I3DHarness,
) -> None:
    _, payload = create_uncertainty(harness, base=932_000)
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("evidence_core_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE evidence_items SET evidence_kind = 'controlled_output'
            WHERE evidence_id = ?
            """,
            (harness.task_evidence_id,),
        ),
    )
    with pytest.raises(ConflictError, match="integrity constraint"):
        harness.persistence.session_task_memory.resolve_uncertainty(
            resolution(
                harness,
                base=932_003,
                uncertainty_record_id=payload.record_id,
            )
        )
