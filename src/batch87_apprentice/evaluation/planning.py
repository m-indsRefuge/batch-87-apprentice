"""Deterministic blinded evaluation-run planning without model execution."""

from __future__ import annotations

from collections.abc import Callable

from batch87_apprentice.common.canonical_json import canonical_json_text, parse_json
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.common.identifiers import generate_identifier, validate_identifier
from batch87_apprentice.common.timestamps import canonical_utc_now

from .contracts import (
    CandidateBlindBinding,
    CandidateMetadata,
    EvaluationConfiguration,
    EvaluationPlan,
    FixtureSet,
    PlannedRun,
)


def _blind_id(
    plan_id: str,
    configuration_hash: str,
    candidate_id: str,
) -> str:
    digest = sha256_canonical_json(
        {
            "candidate_id": candidate_id,
            "configuration_hash": configuration_hash,
            "plan_id": plan_id,
            "protocol": "b87-pre-i5-blinding-v1",
        }
    )
    return "blind_" + digest[:24]


def build_evaluation_plan(
    *,
    plan_id: str,
    plan_family_id: str,
    plan_version: str,
    configuration: EvaluationConfiguration,
    fixture_set: FixtureSet,
    candidates: tuple[CandidateMetadata, ...],
    identifier_factory: Callable[[], str] = generate_identifier,
    clock: Callable[[], str] = canonical_utc_now,
) -> EvaluationPlan:
    """Create one fully ordered plan from immutable registry inputs."""

    validate_identifier(plan_id, field="plan_id")
    validate_identifier(plan_family_id, field="plan_family_id")
    if not isinstance(configuration, EvaluationConfiguration):
        raise ValidationError("configuration is invalid")
    if not isinstance(fixture_set, FixtureSet):
        raise ValidationError("fixture_set is invalid")
    if not candidates or not all(
        isinstance(candidate, CandidateMetadata) for candidate in candidates
    ):
        raise ValidationError("at least one candidate is required")
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise ValidationError("candidate identities must be unique")
    manifest = fixture_set.manifest
    if (
        configuration.fixture_set_id != manifest.fixture_set_id
        or configuration.fixture_set_version != manifest.fixture_set_version
        or configuration.fixture_set_hash != manifest.content_hash
        or configuration.evaluation_suite_id != manifest.evaluation_suite_id
        or configuration.evaluation_suite_version
        != manifest.evaluation_suite_version
    ):
        raise ValidationError("configuration and fixture-set binding conflict")

    created_at = clock()
    ordered_candidates = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    bindings = tuple(
        CandidateBlindBinding(
            candidate_id=candidate.candidate_id,
            candidate_hash=candidate.content_hash,
            blind_candidate_id=_blind_id(
                plan_id,
                configuration.content_hash,
                candidate.candidate_id,
            ),
        )
        for candidate in ordered_candidates
    )
    fixture_by_id = {
        fixture.definition.fixture_id: fixture for fixture in fixture_set.fixtures
    }
    ordered_fixtures = tuple(
        fixture_by_id[entry.fixture_id] for entry in manifest.entries
    )
    runs: list[PlannedRun] = []
    for binding in bindings:
        for fixture in ordered_fixtures:
            for condition in configuration.conditions:
                for repetition_index in range(configuration.repetitions):
                    run_id = identifier_factory()
                    validate_identifier(run_id, field="run_id")
                    runs.append(
                        PlannedRun(
                            run_id=run_id,
                            plan_id=plan_id,
                            condition_id=condition.condition_id,
                            condition_label=condition.label,
                            blind_candidate_id=binding.blind_candidate_id,
                            fixture_id=fixture.definition.fixture_id,
                            repetition_index=repetition_index,
                            run_ordinal=len(runs),
                            ablation_metadata_json=canonical_json_text(
                                {
                                    "condition": condition.name,
                                    "definition": parse_json(
                                        condition.ablation_metadata_json
                                    ),
                                }
                            ),
                            planned_at=created_at,
                        )
                    )
    if len({run.run_id for run in runs}) != len(runs):
        raise ValidationError("identifier factory produced duplicate run identities")

    return EvaluationPlan(
        plan_id=plan_id,
        plan_family_id=plan_family_id,
        plan_version=plan_version,
        configuration_id=configuration.configuration_id,
        configuration_hash=configuration.content_hash,
        fixture_set_id=manifest.fixture_set_id,
        fixture_set_version=manifest.fixture_set_version,
        fixture_set_hash=manifest.content_hash,
        candidate_bindings=bindings,
        runs=tuple(runs),
        created_at=created_at,
    )
