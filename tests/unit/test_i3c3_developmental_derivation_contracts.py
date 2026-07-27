from __future__ import annotations

from dataclasses import replace

import pytest

from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.memory import (
    ApprovedLessonPayload,
    FailurePatternPayload,
    LessonCandidatePayload,
    SuccessPatternPayload,
    developmental_content_hash,
    validate_developmental_pair,
)
from tests.support.i2_fixtures import uid
from tests.support.i3c3_fixtures import (
    build_c3_harness,
    candidate_components,
    create_active_analysis_task,
    create_source_bundle,
    failure_pattern_components,
    success_pattern_components,
)


def test_all_four_payloads_have_exact_canonical_serialization(tmp_path) -> None:
    harness = build_c3_harness(tmp_path)
    analysis_task = create_active_analysis_task(harness, base=800_000)
    _, (_, episode), (_, correction) = create_source_bundle(
        harness,
        base=801_000,
    )
    envelope, candidate = candidate_components(
        harness,
        base=802_000,
        task_id=analysis_task,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    approved = ApprovedLessonPayload(
        record_id=uid(802_100),
        candidate_record_id=candidate.record_id,
        lesson_statement=candidate.lesson_statement,
        application_conditions=("Condition A",),
        non_application_conditions=("Condition B",),
        source_episode_ids=candidate.source_episode_ids,
        source_correction_ids=candidate.source_correction_ids,
        transfer_test_evaluation_ids=(uid(802_101),),
        stability="new",
    )
    _, failure = failure_pattern_components(
        harness,
        base=802_200,
        episode_ids=(uid(1), uid(2)),
    )
    _, success = success_pattern_components(
        harness,
        base=802_300,
        episode_ids=(uid(3), uid(4)),
    )

    assert candidate.canonical_json == (
        '{"intended_scope":"project","known_limitations":'
        '["Applies only to the governed project boundary."],'
        '"lesson_statement":"Verify the exact governed source before applying '
        'its interpretation.","proposed_by":"apprentice",'
        f'"proposer_entity_id":"{harness.agent_id}",'
        f'"record_id":"{candidate.record_id}",'
        f'"source_correction_ids":["{correction.record_id}"],'
        f'"source_episode_ids":["{episode.record_id}"]'
        "}"
    )
    assert approved.canonical_content()["approved_by"] == "nolan-byte"
    assert failure.canonical_content()["frequency"] == 2
    assert success.canonical_content()["transfer_scope"] == [
        "same governed project"
    ]
    assert candidate.canonical_json == candidate.canonical_json
    assert envelope.record_id == candidate.record_id


def test_developmental_hash_is_deterministic_and_payload_sensitive(tmp_path) -> None:
    harness = build_c3_harness(tmp_path)
    task_id = create_active_analysis_task(harness, base=803_000)
    _, (_, episode), (_, correction) = create_source_bundle(
        harness,
        base=804_000,
    )
    envelope, payload = candidate_components(
        harness,
        base=805_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )
    changed = LessonCandidatePayload(
        **{
            **payload.canonical_content(),
            "known_limitations": ("A different exact limitation.",),
        }
    )

    assert developmental_content_hash(
        envelope,
        payload,
    ) == developmental_content_hash(envelope, payload)
    assert developmental_content_hash(
        envelope,
        payload,
    ) != developmental_content_hash(envelope, changed)


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (
            lambda: LessonCandidatePayload(
                record_id=uid(806_000),
                source_episode_ids=(uid(1), uid(1)),
                source_correction_ids=(),
                lesson_statement="Bounded lesson.",
                intended_scope="project",
                proposer_entity_id=uid(2),
                proposed_by="apprentice",
                known_limitations=(),
            ),
            "duplicates",
        ),
        (
            lambda: ApprovedLessonPayload(
                record_id=uid(806_001),
                candidate_record_id=uid(806_002),
                lesson_statement="Bounded lesson.",
                application_conditions=("same",),
                non_application_conditions=("same",),
                source_episode_ids=(uid(1),),
                source_correction_ids=(uid(2),),
                transfer_test_evaluation_ids=(uid(3),),
                stability="new",
            ),
            "disjoint",
        ),
        (
            lambda: FailurePatternPayload(
                record_id=uid(806_003),
                pattern_name="Pattern",
                description="Description",
                episode_ids=(uid(1), uid(2)),
                frequency=3,
                severity="material",
                containment_required=True,
                resolution_status="open",
            ),
            "frequency",
        ),
        (
            lambda: SuccessPatternPayload(
                record_id=uid(806_004),
                pattern_name="Pattern",
                description="Description",
                episode_ids=(uid(1),),
                transfer_scope=("scope",),
                stability="emerging",
            ),
            "multiple",
        ),
    ],
)
def test_payload_contracts_reject_ambiguous_or_non_repeated_values(
    factory,
    match: str,
) -> None:
    with pytest.raises(ValidationError, match=match):
        factory()


def test_pair_validation_enforces_exact_type_and_candidate_policy(tmp_path) -> None:
    harness = build_c3_harness(tmp_path)
    task_id = create_active_analysis_task(harness, base=807_000)
    _, (_, episode), (_, correction) = create_source_bundle(
        harness,
        base=808_000,
    )
    envelope, payload = candidate_components(
        harness,
        base=809_000,
        task_id=task_id,
        episode_id=episode.record_id,
        correction_id=correction.record_id,
    )

    validate_developmental_pair(envelope, payload)
    with pytest.raises(ValidationError, match="candidate_only"):
        validate_developmental_pair(
            replace(envelope, agent_write_policy="prohibited"),
            payload,
        )
    with pytest.raises(ValidationError, match="type"):
        validate_developmental_pair(
            replace(envelope, record_type="failure_pattern"),
            payload,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("proposed_by", "model"),
        ("intended_scope", "global"),
    ],
)
def test_lesson_candidate_rejects_invalid_proposer_or_scope(
    field: str,
    value: str,
) -> None:
    arguments = {
        "record_id": uid(810_000),
        "source_episode_ids": (uid(1),),
        "source_correction_ids": (),
        "lesson_statement": "Bounded lesson.",
        "intended_scope": "project",
        "proposer_entity_id": uid(2),
        "proposed_by": "apprentice",
        "known_limitations": (),
    }
    arguments[field] = value
    with pytest.raises(ValidationError, match=field):
        LessonCandidatePayload(**arguments)
