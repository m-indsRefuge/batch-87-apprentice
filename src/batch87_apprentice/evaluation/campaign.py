"""Synthetic-only PRE-I5 mock campaign orchestration."""

from __future__ import annotations

from collections.abc import Callable

from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.identifiers import generate_identifier
from batch87_apprentice.common.timestamps import canonical_utc_now
from batch87_apprentice.persistence.config import DatabaseConfig

from .contracts import (
    CandidateMetadata,
    EvaluationConfiguration,
    EvaluationPlan,
    EvaluationReport,
    EvaluationReconstruction,
    EvaluationResult,
    FixtureSet,
)
from .planning import build_evaluation_plan
from .reporting import EvaluationReportGenerator
from .store import EvaluationStore


class DeterministicEvaluationService:
    """Public non-model service for registries, planning, evidence, and replay."""

    def __init__(
        self,
        config: DatabaseConfig,
        *,
        clock: Callable[[], str] = canonical_utc_now,
        identifier_factory: Callable[[], str] = generate_identifier,
    ) -> None:
        self._store = EvaluationStore(config)
        self._reports = EvaluationReportGenerator(config)
        self._clock = clock
        self._identifier_factory = identifier_factory

    def register_candidate(self, candidate: CandidateMetadata) -> str:
        return self._store.register_candidate(candidate)

    def register_fixture_set(self, fixture_set: FixtureSet) -> str:
        return self._store.register_fixture_set(fixture_set)

    def register_configuration(
        self, configuration: EvaluationConfiguration
    ) -> str:
        return self._store.register_configuration(configuration)

    def schedule(
        self,
        *,
        plan_id: str,
        plan_family_id: str,
        plan_version: str,
        configuration: EvaluationConfiguration,
        fixture_set: FixtureSet,
        candidates: tuple[CandidateMetadata, ...],
    ) -> EvaluationPlan:
        plan = build_evaluation_plan(
            plan_id=plan_id,
            plan_family_id=plan_family_id,
            plan_version=plan_version,
            configuration=configuration,
            fixture_set=fixture_set,
            candidates=candidates,
            identifier_factory=self._identifier_factory,
            clock=self._clock,
        )
        transition_ids = tuple(
            self._identifier_factory() for _ in plan.runs
        )
        self._store.register_plan(
            plan,
            initial_transition_ids=transition_ids,
        )
        return plan

    def record_result(self, result: EvaluationResult) -> str:
        return self._store.record_result(
            result,
            terminal_transition_id=self._identifier_factory(),
        )

    def record_mock_campaign(
        self,
        plan: EvaluationPlan,
        results: tuple[EvaluationResult, ...],
    ) -> EvaluationReport:
        """Persist one complete synthetic campaign; never call a provider."""

        run_ids = tuple(run.run_id for run in plan.runs)
        result_run_ids = tuple(result.run_id for result in results)
        if len(set(result_run_ids)) != len(result_run_ids):
            raise ValidationError("mock campaign result identities are duplicated")
        if set(result_run_ids) != set(run_ids):
            raise ValidationError("mock campaign requires exactly one result per run")
        if any(result.evidence_origin != "synthetic_mock" for result in results):
            raise ValidationError("mock campaign accepts synthetic result evidence only")
        ordered = {result.run_id: result for result in results}
        for run_id in run_ids:
            self.record_result(ordered[run_id])
        return self.report(plan.plan_id)

    def reconstruct(self, plan_id: str) -> EvaluationReconstruction:
        return self._store.reconstruct_plan(plan_id)

    def report(self, plan_id: str) -> EvaluationReport:
        return self._reports.generate(plan_id)
