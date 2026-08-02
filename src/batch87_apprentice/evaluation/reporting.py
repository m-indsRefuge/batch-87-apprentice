"""Deterministic blinded report generation from stored PRE-I5 evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.persistence.config import DatabaseConfig

from .contracts import (
    EvaluationReport,
    REPORT_PROTOCOL,
    REPORT_PROTOCOL_VERSION,
)
from .store import EvaluationStore


class EvaluationReportGenerator:
    """Regenerate the same blinded report from the same verified evidence."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._store = EvaluationStore(config)

    def generate(self, plan_id: str) -> EvaluationReport:
        reconstruction = self._store.reconstruct_plan(plan_id).value
        plan = reconstruction["plan"]
        configuration = reconstruction["configuration"]
        fixture_set = reconstruction["fixture_set"]
        report_runs: list[dict[str, Any]] = []
        outcomes_by_candidate: dict[str, Counter[str]] = defaultdict(Counter)
        completed_scores: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for stored in reconstruction["runs"]:
            run = stored["value"]
            result_record = stored["result"]
            blind_id = run["blind_candidate_id"]
            if result_record is None:
                outcome = "missing_evidence"
                result_value = None
                result_hash = None
                evidence_status = "missing"
                scores: list[dict[str, Any]] = []
                critical_failures: list[dict[str, Any]] = []
                runtime_observed = None
                candidate_reported = None
                replay_metadata = None
            else:
                result_value = result_record["value"]
                outcome = result_value["outcome"]
                result_hash = result_record["content_hash"]
                evidence_status = "recorded"
                scores = result_value["scores"]
                critical_failures = result_value["critical_failures"]
                runtime_observed = result_value["runtime_observed"]
                candidate_reported = result_value["candidate_reported_metadata"]
                replay_metadata = result_value["replay_metadata"]
                if outcome == "completed":
                    for score in scores:
                        completed_scores[blind_id][score["dimension"]].append(
                            float(score["score"])
                        )
            outcomes_by_candidate[blind_id][outcome] += 1
            report_runs.append(
                {
                    "blinded_candidate_id": blind_id,
                    "candidate_reported_metadata": candidate_reported,
                    "condition_id": run["condition_id"],
                    "condition_label": run["condition_label"],
                    "critical_failures": critical_failures,
                    "critical_invalidation": outcome
                    in {"critical_failure", "invalid"},
                    "evidence_status": evidence_status,
                    "fixture_id": run["fixture_id"],
                    "numeric_scores": scores,
                    "outcome": outcome,
                    "repetition_index": run["repetition_index"],
                    "replay_metadata": replay_metadata,
                    "result_hash": result_hash,
                    "run_hash": stored["content_hash"],
                    "run_id": run["run_id"],
                    "run_ordinal": run["run_ordinal"],
                    "runtime_observed": runtime_observed,
                }
            )

        candidate_summaries = []
        for blind_id in sorted(outcomes_by_candidate):
            counts = outcomes_by_candidate[blind_id]
            means = {
                dimension: sum(values) / len(values)
                for dimension, values in sorted(
                    completed_scores[blind_id].items()
                )
            }
            candidate_summaries.append(
                {
                    "admission_effect": "none",
                    "blinded_candidate_id": blind_id,
                    "completed_score_means": means,
                    "critical_invalidation_count": counts["critical_failure"]
                    + counts["invalid"],
                    "missing_evidence_count": counts["missing_evidence"],
                    "outcome_counts": {
                        key: counts[key] for key in sorted(counts)
                    },
                    "ranking_authority": "none",
                }
            )

        all_outcomes = Counter(
            run["outcome"] for run in report_runs
        )
        if all_outcomes["missing_evidence"]:
            campaign_status = "incomplete_missing_evidence"
        elif any(
            all_outcomes[state]
            for state in ("incomplete", "interrupted")
        ):
            campaign_status = "incomplete_recorded"
        elif any(
            all_outcomes[state]
            for state in ("critical_failure", "invalid")
        ):
            campaign_status = "complete_with_invalidation"
        else:
            campaign_status = "complete"

        value = {
            "admission_effect": "none",
            "blinding": "preserved",
            "campaign_status": campaign_status,
            "candidate_summaries": candidate_summaries,
            "configuration_hash": configuration["content_hash"],
            "configuration_id": configuration["value"]["configuration_id"],
            "fixture_set_hash": fixture_set["content_hash"],
            "fixture_set_id": fixture_set["manifest"]["fixture_set_id"],
            "negative_evidence_preserved": True,
            "numeric_scores_are_not_acceptance": True,
            "plan_hash": plan["content_hash"],
            "plan_id": plan["value"]["plan_id"],
            "protocol": REPORT_PROTOCOL,
            "protocol_version": REPORT_PROTOCOL_VERSION,
            "runs": report_runs,
        }
        canonical = canonical_json_text(value)
        return EvaluationReport(
            canonical_json=canonical,
            content_hash=sha256_canonical_json(value),
        )
