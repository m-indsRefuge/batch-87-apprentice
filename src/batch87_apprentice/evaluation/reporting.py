"""Deterministic blinded report generation from stored PRE-I5 evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import IntegrityInspectionError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.persistence.config import DatabaseConfig

from .contracts import (
    EvaluationReport,
    REPORT_PROTOCOL,
    REPORT_PROTOCOL_VERSION,
)
from .store import EvaluationStore


_IDENTITY_FIELDS = frozenset(
    {
        "artifact_format",
        "candidate_content_hash",
        "candidate_hash",
        "candidate_id",
        "candidate_to_blind_mapping",
        "model_family",
        "model_revision",
        "quantization",
    }
)
_NON_IDENTIFYING_GENERIC_VALUES = frozenset({"", "none", "synthetic", "unknown"})


def _assert_identity_safe(
    value: object,
    *,
    candidate_records: tuple[dict[str, Any], ...],
) -> None:
    """Fail closed if a blinded projection contains known candidate identity."""

    identifying_values: set[str] = set()
    for record in candidate_records:
        candidate = record["value"]
        identifying_values.update(
            {
                record["content_hash"],
                candidate["candidate_id"],
                candidate["model_family"],
                candidate["model_revision"],
            }
        )
        for field in ("quantization", "artifact_format"):
            candidate_value = candidate[field]
            if (
                isinstance(candidate_value, str)
                and candidate_value.lower() not in _NON_IDENTIFYING_GENERIC_VALUES
            ):
                identifying_values.add(candidate_value)

    def inspect(item: object) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                if key.lower() in _IDENTITY_FIELDS:
                    raise IntegrityInspectionError(
                        "blinded report contains an identity-bearing field"
                    )
                inspect(nested)
        elif isinstance(item, list):
            for nested in item:
                inspect(nested)
        elif isinstance(item, str) and any(
            identity in item for identity in identifying_values
        ):
            raise IntegrityInspectionError(
                "blinded report contains candidate identity"
            )

    inspect(value)


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
        condition_outcomes: dict[str, dict[str, Counter[str]]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        condition_scores: dict[
            str, dict[str, dict[str, list[float]]]
        ] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

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
                latency_ms = None
            else:
                result_value = result_record["value"]
                outcome = result_value["outcome"]
                result_hash = result_record["content_hash"]
                evidence_status = "recorded"
                scores = result_value["scores"]
                critical_failures = result_value["critical_failures"]
                latency_ms = result_value["runtime_observed"]["latency_ms"]
                if outcome == "completed":
                    for score in scores:
                        completed_scores[blind_id][score["dimension"]].append(
                            float(score["score"])
                        )
                        condition_scores[blind_id][run["condition_label"]][
                            score["dimension"]
                        ].append(float(score["score"]))
            outcomes_by_candidate[blind_id][outcome] += 1
            condition_outcomes[blind_id][run["condition_label"]][outcome] += 1
            report_runs.append(
                {
                    "blinded_candidate_id": blind_id,
                    "condition_id": run["condition_id"],
                    "condition_label": run["condition_label"],
                    "critical_failures": critical_failures,
                    "critical_invalidation": outcome
                    in {"critical_failure", "invalid"},
                    "evidence_status": evidence_status,
                    "fixture_id": run["fixture_id"],
                    "latency_ms": latency_ms,
                    "metadata_projection": "identity_bearing_metadata_omitted",
                    "numeric_scores": scores,
                    "outcome": outcome,
                    "repetition_index": run["repetition_index"],
                    "result_hash": result_hash,
                    "run_hash": stored["content_hash"],
                    "run_id": run["run_id"],
                    "run_ordinal": run["run_ordinal"],
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

        condition_comparisons = []
        for blind_id in sorted(outcomes_by_candidate):
            summaries: dict[str, dict[str, Any]] = {}
            for label in ("enabled", "withheld"):
                counts = condition_outcomes[blind_id][label]
                means = {
                    dimension: sum(values) / len(values)
                    for dimension, values in sorted(
                        condition_scores[blind_id][label].items()
                    )
                }
                summaries[label] = {
                    "completed_score_means": means,
                    "missing_evidence_count": counts["missing_evidence"],
                    "outcome_counts": {
                        key: counts[key] for key in sorted(counts)
                    },
                    "recorded_result_count": sum(
                        count
                        for outcome, count in counts.items()
                        if outcome != "missing_evidence"
                    ),
                }
            shared_dimensions = sorted(
                set(summaries["enabled"]["completed_score_means"])
                & set(summaries["withheld"]["completed_score_means"])
            )
            condition_comparisons.append(
                {
                    "blinded_candidate_id": blind_id,
                    "enabled": summaries["enabled"],
                    "enabled_minus_withheld_score_means": {
                        dimension: (
                            summaries["enabled"]["completed_score_means"][dimension]
                            - summaries["withheld"]["completed_score_means"][dimension]
                        )
                        for dimension in shared_dimensions
                    },
                    "withheld": summaries["withheld"],
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
            "campaign_status": campaign_status,
            "candidate_summaries": candidate_summaries,
            "condition_comparisons": condition_comparisons,
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
        candidate_records = tuple(
            self._store.reconstruct_candidate(binding["candidate_id"])
            for binding in reconstruction["candidate_bindings"]
        )
        _assert_identity_safe(value, candidate_records=candidate_records)
        value["blinding"] = "preserved"
        value["blinding_validation"] = {
            "identity_leak_check": "passed",
            "raw_metadata_projection": "omitted",
        }
        canonical = canonical_json_text(value)
        return EvaluationReport(
            canonical_json=canonical,
            content_hash=sha256_canonical_json(value),
        )
