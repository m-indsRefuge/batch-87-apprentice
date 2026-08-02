"""Append-only persistence and exact reconstruction for B87-PRE-I5."""

from __future__ import annotations

from collections.abc import Callable
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import canonical_json_text, parse_json
from batch87_apprentice.common.errors import (
    IntegrityInspectionError,
    NotFoundError,
    ValidationError,
)
from batch87_apprentice.common.hashing import sha256_bytes, sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .contracts import (
    CandidateMetadata,
    EVALUATION_CONTRACT_VERSION,
    EvaluationConfiguration,
    EvaluationPlan,
    EvaluationReconstruction,
    EvaluationResult,
    EvaluationRunStateTransition,
    FixtureSet,
)


def _json_array(values: tuple[object, ...], method: str = "canonical_value") -> str:
    return canonical_json_text([getattr(value, method)() for value in values])


def _verified_object(text: object, digest: object, label: str) -> dict[str, Any]:
    if not isinstance(text, str) or not isinstance(digest, str):
        raise IntegrityInspectionError(f"{label} canonical data is malformed")
    try:
        value = parse_json(text)
    except ValidationError as exc:
        raise IntegrityInspectionError(f"{label} canonical JSON is invalid") from exc
    if not isinstance(value, dict) or canonical_json_text(value) != text:
        raise IntegrityInspectionError(f"{label} canonical JSON is not canonical")
    if sha256_canonical_json(value) != digest:
        raise IntegrityInspectionError(f"{label} content hash mismatch")
    return value


class EvaluationStore:
    """Own PRE-I5 registry, plan, transition, result, and replay writes."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._kernel = PersistenceKernel(config)

    def register_candidate(self, candidate: CandidateMetadata) -> str:
        if not isinstance(candidate, CandidateMetadata):
            raise ValidationError("candidate metadata is invalid")

        def operation(connection: sqlite3.Connection) -> str:
            connection.execute(
                """
                INSERT INTO evaluation_candidates (
                    candidate_id, candidate_origin, lifecycle_state,
                    admission_state, model_family, model_revision,
                    quantization, artifact_format, licence_identifier,
                    provenance_json, compatibility_json, registered_at,
                    canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.candidate_id,
                    candidate.candidate_origin,
                    candidate.lifecycle_state,
                    candidate.admission_state,
                    candidate.model_family,
                    candidate.model_revision,
                    candidate.quantization,
                    candidate.artifact_format,
                    candidate.licence_identifier,
                    candidate.provenance_json,
                    candidate.compatibility_json,
                    candidate.registered_at,
                    candidate.canonical_json,
                    candidate.content_hash,
                ),
            )
            return candidate.content_hash

        return self._kernel.write(operation)

    def register_fixture_set(self, fixture_set: FixtureSet) -> str:
        if not isinstance(fixture_set, FixtureSet):
            raise ValidationError("fixture set is invalid")
        manifest = fixture_set.manifest

        def operation(connection: sqlite3.Connection) -> str:
            connection.execute(
                """
                INSERT INTO evaluation_fixture_sets (
                    fixture_set_id, fixture_set_version, evaluation_suite_id,
                    evaluation_suite_version, provenance_json, registered_at,
                    manifest_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest.fixture_set_id,
                    manifest.fixture_set_version,
                    manifest.evaluation_suite_id,
                    manifest.evaluation_suite_version,
                    manifest.provenance_json,
                    manifest.registered_at,
                    manifest.canonical_json,
                    manifest.content_hash,
                ),
            )
            for fixture in fixture_set.fixtures:
                definition = fixture.definition
                entry = fixture.entry
                connection.execute(
                    """
                    INSERT INTO evaluation_fixtures (
                        fixture_id, fixture_version, fixture_set_id,
                        fixture_set_version, fixture_set_hash,
                        evaluation_suite_id, evaluation_suite_version,
                        fixture_ordinal, source_name, sensitivity,
                        provenance_json, fixture_json, byte_length,
                        content_hash, registered_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        definition.fixture_id,
                        definition.fixture_version,
                        definition.fixture_set_id,
                        definition.fixture_set_version,
                        manifest.content_hash,
                        definition.evaluation_suite_id,
                        definition.evaluation_suite_version,
                        entry.ordinal,
                        entry.source_name,
                        definition.sensitivity,
                        definition.provenance_json,
                        fixture.exact_bytes.decode("utf-8"),
                        len(fixture.exact_bytes),
                        entry.content_hash,
                        manifest.registered_at,
                    ),
                )
            return manifest.content_hash

        return self._kernel.write(operation)

    def register_configuration(
        self,
        configuration: EvaluationConfiguration,
    ) -> str:
        if not isinstance(configuration, EvaluationConfiguration):
            raise ValidationError("evaluation configuration is invalid")

        def operation(connection: sqlite3.Connection) -> str:
            connection.execute(
                """
                INSERT INTO evaluation_configurations (
                    configuration_id, configuration_version,
                    evaluation_suite_id, evaluation_suite_version,
                    fixture_set_id, fixture_set_version, fixture_set_hash,
                    timeout_ms, repetitions, conditions_json,
                    resource_limits_json, score_schema_json,
                    critical_failure_schema_json, registered_at,
                    canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    configuration.configuration_id,
                    configuration.configuration_version,
                    configuration.evaluation_suite_id,
                    configuration.evaluation_suite_version,
                    configuration.fixture_set_id,
                    configuration.fixture_set_version,
                    configuration.fixture_set_hash,
                    configuration.timeout_ms,
                    configuration.repetitions,
                    _json_array(configuration.conditions),
                    canonical_json_text(
                        configuration.resource_limits.canonical_value()
                    ),
                    canonical_json_text(configuration.score_schema.canonical_value()),
                    canonical_json_text(
                        configuration.critical_failure_schema.canonical_value()
                    ),
                    configuration.registered_at,
                    configuration.canonical_json,
                    configuration.content_hash,
                ),
            )
            return configuration.content_hash

        return self._kernel.write(operation)

    @staticmethod
    def _configuration_value(
        connection: sqlite3.Connection,
        configuration_id: str,
    ) -> tuple[sqlite3.Row, dict[str, Any]]:
        row = connection.execute(
            "SELECT * FROM evaluation_configurations WHERE configuration_id = ?",
            (configuration_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError("evaluation configuration does not exist")
        value = _verified_object(
            row["canonical_json"], row["content_hash"], "evaluation configuration"
        )
        expected = {
            "configuration_id": row["configuration_id"],
            "configuration_version": row["configuration_version"],
            "evaluation_suite_id": row["evaluation_suite_id"],
            "evaluation_suite_version": row["evaluation_suite_version"],
            "fixture_set_id": row["fixture_set_id"],
            "fixture_set_version": row["fixture_set_version"],
            "fixture_set_hash": row["fixture_set_hash"],
            "timeout_ms": row["timeout_ms"],
            "repetitions": row["repetitions"],
            "registered_at": row["registered_at"],
        }
        if any(value.get(key) != item for key, item in expected.items()):
            raise IntegrityInspectionError("evaluation configuration projection drift")
        for key, column in (
            ("conditions", "conditions_json"),
            ("resource_limits", "resource_limits_json"),
            ("score_schema", "score_schema_json"),
            ("critical_failure_schema", "critical_failure_schema_json"),
        ):
            if canonical_json_text(value.get(key)) != row[column]:
                raise IntegrityInspectionError(
                    f"evaluation configuration {key} projection drift"
                )
        return row, value

    def register_plan(
        self,
        plan: EvaluationPlan,
        *,
        initial_transition_ids: tuple[str, ...],
        failure_injector: Callable[[str], None] | None = None,
    ) -> str:
        if not isinstance(plan, EvaluationPlan):
            raise ValidationError("evaluation plan is invalid")
        if len(initial_transition_ids) != len(plan.runs):
            raise ValidationError("one initial transition identity is required per run")
        for identifier in initial_transition_ids:
            validate_identifier(identifier, field="initial_transition_id")
        if len(set(initial_transition_ids)) != len(initial_transition_ids):
            raise ValidationError("initial transition identities must be unique")

        def inject(point: str) -> None:
            if failure_injector is not None:
                failure_injector(point)

        def operation(connection: sqlite3.Connection) -> str:
            config_row, config_value = self._configuration_value(
                connection, plan.configuration_id
            )
            if config_row["content_hash"] != plan.configuration_hash:
                raise ValidationError("plan configuration hash conflicts")
            fixture_set = connection.execute(
                """
                SELECT * FROM evaluation_fixture_sets
                WHERE fixture_set_id = ? AND fixture_set_version = ?
                """,
                (plan.fixture_set_id, plan.fixture_set_version),
            ).fetchone()
            if fixture_set is None or fixture_set["content_hash"] != plan.fixture_set_hash:
                raise ValidationError("plan fixture-set binding conflicts")
            conditions = {
                item["condition_id"]: item for item in config_value["conditions"]
            }
            fixtures = {
                row["fixture_id"]: row
                for row in connection.execute(
                    """
                    SELECT * FROM evaluation_fixtures
                    WHERE fixture_set_id = ? AND fixture_set_version = ?
                    ORDER BY fixture_ordinal
                    """,
                    (plan.fixture_set_id, plan.fixture_set_version),
                )
            }
            expected_run_count = (
                len(plan.candidate_bindings)
                * len(fixtures)
                * len(conditions)
                * int(config_row["repetitions"])
            )
            if len(plan.runs) != expected_run_count:
                raise ValidationError("evaluation plan run matrix is incomplete")
            for binding in plan.candidate_bindings:
                candidate = connection.execute(
                    """
                    SELECT content_hash FROM evaluation_candidates
                    WHERE candidate_id = ?
                    """,
                    (binding.candidate_id,),
                ).fetchone()
                if candidate is None or candidate["content_hash"] != binding.candidate_hash:
                    raise ValidationError("plan candidate binding conflicts")
            for run in plan.runs:
                condition = conditions.get(run.condition_id)
                if condition is None or condition["label"] != run.condition_label:
                    raise ValidationError("run condition binding conflicts")
                expected_ablation = canonical_json_text(
                    {
                        "condition": condition["name"],
                        "definition": condition["ablation_metadata"],
                    }
                )
                if run.ablation_metadata_json != expected_ablation:
                    raise ValidationError("run ablation binding conflicts")
                if run.fixture_id not in fixtures:
                    raise ValidationError("run fixture binding conflicts")
                if run.repetition_index >= int(config_row["repetitions"]):
                    raise ValidationError("run repetition is outside configuration")

            connection.execute(
                """
                INSERT INTO evaluation_plans (
                    plan_id, plan_version, configuration_id,
                    configuration_hash, fixture_set_id, fixture_set_version,
                    fixture_set_hash, created_at, canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_id,
                    plan.plan_version,
                    plan.configuration_id,
                    plan.configuration_hash,
                    plan.fixture_set_id,
                    plan.fixture_set_version,
                    plan.fixture_set_hash,
                    plan.created_at,
                    plan.canonical_json,
                    plan.content_hash,
                ),
            )
            inject("after_plan")
            for binding in plan.candidate_bindings:
                connection.execute(
                    """
                    INSERT INTO evaluation_plan_candidates (
                        plan_id, plan_hash, candidate_id, candidate_hash,
                        blind_candidate_id
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        plan.plan_id,
                        plan.content_hash,
                        binding.candidate_id,
                        binding.candidate_hash,
                        binding.blind_candidate_id,
                    ),
                )
            inject("after_candidate_bindings")
            for run, transition_id in zip(
                plan.runs, initial_transition_ids, strict=True
            ):
                connection.execute(
                    """
                    INSERT INTO evaluation_runs (
                        run_id, plan_id, plan_hash, condition_id,
                        condition_label, blind_candidate_id, fixture_id,
                        repetition_index, run_ordinal, ablation_metadata_json,
                        planned_at, canonical_json, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.run_id,
                        run.plan_id,
                        plan.content_hash,
                        run.condition_id,
                        run.condition_label,
                        run.blind_candidate_id,
                        run.fixture_id,
                        run.repetition_index,
                        run.run_ordinal,
                        run.ablation_metadata_json,
                        run.planned_at,
                        run.canonical_json,
                        run.content_hash,
                    ),
                )
                transition = EvaluationRunStateTransition(
                    transition_id=transition_id,
                    run_id=run.run_id,
                    sequence=0,
                    from_state=None,
                    to_state="planned",
                    occurred_at=run.planned_at,
                )
                connection.execute(
                    """
                    INSERT INTO evaluation_run_state_transitions (
                        transition_id, run_id, sequence, from_state, to_state,
                        occurred_at, canonical_json, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        transition.transition_id,
                        transition.run_id,
                        transition.sequence,
                        transition.from_state,
                        transition.to_state,
                        transition.occurred_at,
                        transition.canonical_json,
                        transition.content_hash,
                    ),
                )
            inject("after_runs")
            return plan.content_hash

        return self._kernel.write(operation)

    @staticmethod
    def _validate_result_schema(
        run: sqlite3.Row,
        configuration: dict[str, Any],
        result: EvaluationResult,
    ) -> None:
        if run["condition_label"] == "withheld":
            if result.outcome != "withheld":
                raise ValidationError("withheld run requires withheld result")
        elif result.outcome == "withheld":
            raise ValidationError("non-withheld run cannot be withheld")
        dimensions = {
            item["name"]: item for item in configuration["score_schema"]["dimensions"]
        }
        observed = {item.dimension for item in result.scores}
        if not observed <= set(dimensions):
            raise ValidationError("result contains an unknown score dimension")
        if result.outcome == "completed" and observed != set(dimensions):
            raise ValidationError("completed result requires every score dimension")
        for observation in result.scores:
            definition = dimensions[observation.dimension]
            if not definition["minimum"] <= observation.score <= definition["maximum"]:
                raise ValidationError("score is outside its registered schema")
        critical_codes = {
            item["code"]
            for item in configuration["critical_failure_schema"]["definitions"]
        }
        if not {item.code for item in result.critical_failures} <= critical_codes:
            raise ValidationError("result contains an unknown critical failure")

    @staticmethod
    def _validate_reconstructed_result_schema(
        run: sqlite3.Row,
        configuration: dict[str, Any],
        value: dict[str, Any],
    ) -> None:
        expected_fields = {
            "candidate_reported_metadata",
            "contract_version",
            "critical_failures",
            "evidence_origin",
            "observed_at",
            "outcome",
            "replay_metadata",
            "result_id",
            "run_id",
            "runtime_observed",
            "scores",
        }
        if (
            set(value) != expected_fields
            or value.get("contract_version") != EVALUATION_CONTRACT_VERSION
        ):
            raise IntegrityInspectionError("evaluation result shape is invalid")
        scores = value.get("scores")
        failures = value.get("critical_failures")
        if not isinstance(scores, list) or not isinstance(failures, list):
            raise IntegrityInspectionError("evaluation result evidence shape is invalid")
        dimensions = {
            item["name"]: item for item in configuration["score_schema"]["dimensions"]
        }
        observed_dimensions: set[str] = set()
        for score in scores:
            if not isinstance(score, dict) or set(score) != {
                "dimension",
                "evidence_refs",
                "rationale",
                "score",
            }:
                raise IntegrityInspectionError("evaluation score shape is invalid")
            dimension = score.get("dimension")
            numeric = score.get("score")
            evidence_refs = score.get("evidence_refs")
            if (
                not isinstance(dimension, str)
                or dimension not in dimensions
                or dimension in observed_dimensions
                or not isinstance(numeric, (int, float))
                or isinstance(numeric, bool)
                or not dimensions[dimension]["minimum"]
                <= float(numeric)
                <= dimensions[dimension]["maximum"]
                or not isinstance(score.get("rationale"), str)
                or not score["rationale"].strip()
                or not isinstance(evidence_refs, list)
                or not evidence_refs
                or not all(
                    isinstance(reference, str) and reference.strip()
                    for reference in evidence_refs
                )
                or len(evidence_refs) != len(set(evidence_refs))
            ):
                raise IntegrityInspectionError("evaluation score schema is invalid")
            observed_dimensions.add(dimension)
        critical_codes = {
            item["code"]
            for item in configuration["critical_failure_schema"]["definitions"]
        }
        observed_codes: set[str] = set()
        for failure in failures:
            if not isinstance(failure, dict) or set(failure) != {
                "code",
                "evidence_refs",
                "rationale",
            }:
                raise IntegrityInspectionError(
                    "evaluation critical-failure shape is invalid"
                )
            code = failure.get("code")
            evidence_refs = failure.get("evidence_refs")
            if (
                not isinstance(code, str)
                or code not in critical_codes
                or code in observed_codes
                or not isinstance(failure.get("rationale"), str)
                or not failure["rationale"].strip()
                or not isinstance(evidence_refs, list)
                or not evidence_refs
                or not all(
                    isinstance(reference, str) and reference.strip()
                    for reference in evidence_refs
                )
                or len(evidence_refs) != len(set(evidence_refs))
            ):
                raise IntegrityInspectionError(
                    "evaluation critical-failure schema is invalid"
                )
            observed_codes.add(code)
        runtime = value.get("runtime_observed")
        candidate_reported = value.get("candidate_reported_metadata")
        replay_metadata = value.get("replay_metadata")
        if not isinstance(runtime, dict) or set(runtime) != {
            "hardware_metadata",
            "latency_ms",
        }:
            raise IntegrityInspectionError("runtime observation shape is invalid")
        latency = runtime.get("latency_ms")
        if (
            latency is not None
            and (
                not isinstance(latency, int)
                or isinstance(latency, bool)
                or latency < 0
            )
        ):
            raise IntegrityInspectionError("runtime latency is invalid")
        if (
            not isinstance(runtime.get("hardware_metadata"), dict)
            or not isinstance(candidate_reported, dict)
            or not isinstance(replay_metadata, dict)
        ):
            raise IntegrityInspectionError("evaluation result metadata is invalid")
        outcome = value.get("outcome")
        if run["condition_label"] == "withheld":
            if outcome != "withheld":
                raise IntegrityInspectionError("withheld result binding is invalid")
        elif outcome == "withheld":
            raise IntegrityInspectionError("non-withheld result binding is invalid")
        if outcome == "completed" and (
            observed_dimensions != set(dimensions) or failures
        ):
            raise IntegrityInspectionError("completed result schema is invalid")
        if outcome == "critical_failure" and not failures:
            raise IntegrityInspectionError("critical-failure evidence is missing")
        if outcome == "withheld" and (scores or failures):
            raise IntegrityInspectionError("withheld scoring evidence is invalid")

    def record_result(
        self,
        result: EvaluationResult,
        *,
        terminal_transition_id: str,
        failure_injector: Callable[[str], None] | None = None,
    ) -> str:
        if not isinstance(result, EvaluationResult):
            raise ValidationError("evaluation result is invalid")
        validate_identifier(terminal_transition_id, field="terminal_transition_id")

        def inject(point: str) -> None:
            if failure_injector is not None:
                failure_injector(point)

        def operation(connection: sqlite3.Connection) -> str:
            run = connection.execute(
                """
                SELECT run.*, plan.configuration_id
                FROM evaluation_runs AS run
                JOIN evaluation_plans AS plan ON plan.plan_id = run.plan_id
                WHERE run.run_id = ?
                """,
                (result.run_id,),
            ).fetchone()
            if run is None:
                raise NotFoundError("evaluation run does not exist")
            _, configuration = self._configuration_value(
                connection, run["configuration_id"]
            )
            self._validate_result_schema(run, configuration, result)
            connection.execute(
                """
                INSERT INTO evaluation_results (
                    result_id, run_id, run_hash, outcome, evidence_origin,
                    scores_json, critical_failures_json,
                    runtime_observed_json, candidate_reported_metadata_json,
                    replay_metadata_json, observed_at, canonical_json,
                    content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.result_id,
                    result.run_id,
                    run["content_hash"],
                    result.outcome,
                    result.evidence_origin,
                    _json_array(result.scores),
                    _json_array(result.critical_failures),
                    canonical_json_text(result.runtime_observed.canonical_value()),
                    result.candidate_reported_metadata_json,
                    result.replay_metadata_json,
                    result.observed_at,
                    result.canonical_json,
                    result.content_hash,
                ),
            )
            inject("after_result")
            transition = EvaluationRunStateTransition(
                transition_id=terminal_transition_id,
                run_id=result.run_id,
                sequence=1,
                from_state="planned",
                to_state=result.outcome,
                occurred_at=result.observed_at,
            )
            connection.execute(
                """
                INSERT INTO evaluation_run_state_transitions (
                    transition_id, run_id, sequence, from_state, to_state,
                    occurred_at, canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition.transition_id,
                    transition.run_id,
                    transition.sequence,
                    transition.from_state,
                    transition.to_state,
                    transition.occurred_at,
                    transition.canonical_json,
                    transition.content_hash,
                ),
            )
            inject("after_transition")
            return result.content_hash

        return self._kernel.write(operation)

    @staticmethod
    def _candidate_connection(
        connection: sqlite3.Connection,
        candidate_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM evaluation_candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError("evaluation candidate does not exist")
        value = _verified_object(
            row["canonical_json"], row["content_hash"], "evaluation candidate"
        )
        expected = {
            "candidate_id": row["candidate_id"],
            "candidate_origin": row["candidate_origin"],
            "lifecycle_state": row["lifecycle_state"],
            "admission_state": row["admission_state"],
            "model_family": row["model_family"],
            "model_revision": row["model_revision"],
            "quantization": row["quantization"],
            "artifact_format": row["artifact_format"],
            "licence_identifier": row["licence_identifier"],
            "registered_at": row["registered_at"],
        }
        if any(value.get(key) != item for key, item in expected.items()):
            raise IntegrityInspectionError("evaluation candidate projection drift")
        if (
            canonical_json_text(value.get("provenance")) != row["provenance_json"]
            or canonical_json_text(value.get("compatibility"))
            != row["compatibility_json"]
        ):
            raise IntegrityInspectionError("evaluation candidate metadata drift")
        return {"content_hash": row["content_hash"], "value": value}

    @staticmethod
    def _fixture_set_connection(
        connection: sqlite3.Connection,
        fixture_set_id: str,
        fixture_set_version: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT * FROM evaluation_fixture_sets
            WHERE fixture_set_id = ? AND fixture_set_version = ?
            """,
            (fixture_set_id, fixture_set_version),
        ).fetchone()
        if row is None:
            raise NotFoundError("evaluation fixture set does not exist")
        manifest = _verified_object(
            row["manifest_json"], row["content_hash"], "evaluation fixture set"
        )
        expected = {
            "fixture_set_id": row["fixture_set_id"],
            "fixture_set_version": row["fixture_set_version"],
            "evaluation_suite_id": row["evaluation_suite_id"],
            "evaluation_suite_version": row["evaluation_suite_version"],
            "registered_at": row["registered_at"],
        }
        if any(manifest.get(key) != item for key, item in expected.items()):
            raise IntegrityInspectionError("evaluation fixture-set projection drift")
        if canonical_json_text(manifest.get("provenance")) != row["provenance_json"]:
            raise IntegrityInspectionError("evaluation fixture-set provenance drift")

        fixtures = []
        rows = tuple(
            connection.execute(
                """
                SELECT * FROM evaluation_fixtures
                WHERE fixture_set_id = ? AND fixture_set_version = ?
                ORDER BY fixture_ordinal
                """,
                (fixture_set_id, fixture_set_version),
            )
        )
        if len(rows) != len(manifest.get("entries", [])):
            raise IntegrityInspectionError("evaluation fixture-set membership changed")
        for fixture_row, entry in zip(rows, manifest["entries"], strict=True):
            try:
                fixture_value = parse_json(fixture_row["fixture_json"])
            except ValidationError as exc:
                raise IntegrityInspectionError("evaluation fixture JSON is invalid") from exc
            if (
                not isinstance(fixture_value, dict)
                or canonical_json_text(fixture_value) != fixture_row["fixture_json"]
                or sha256_bytes(fixture_row["fixture_json"].encode("utf-8"))
                != fixture_row["content_hash"]
                or len(fixture_row["fixture_json"].encode("utf-8"))
                != fixture_row["byte_length"]
            ):
                raise IntegrityInspectionError("evaluation fixture content mismatch")
            projected = {
                "fixture_id": fixture_row["fixture_id"],
                "fixture_version": fixture_row["fixture_version"],
                "fixture_set_id": fixture_row["fixture_set_id"],
                "fixture_set_version": fixture_row["fixture_set_version"],
                "evaluation_suite_id": fixture_row["evaluation_suite_id"],
                "evaluation_suite_version": fixture_row["evaluation_suite_version"],
                "sensitivity": fixture_row["sensitivity"],
            }
            if any(fixture_value.get(key) != item for key, item in projected.items()):
                raise IntegrityInspectionError("evaluation fixture projection drift")
            if (
                entry.get("fixture_id") != fixture_row["fixture_id"]
                or entry.get("source_name") != fixture_row["source_name"]
                or entry.get("ordinal") != fixture_row["fixture_ordinal"]
                or entry.get("content_hash") != fixture_row["content_hash"]
                or fixture_row["fixture_set_hash"] != row["content_hash"]
            ):
                raise IntegrityInspectionError("evaluation fixture manifest conflict")
            fixtures.append(
                {
                    "byte_length": fixture_row["byte_length"],
                    "content_hash": fixture_row["content_hash"],
                    "definition": fixture_value,
                    "ordinal": fixture_row["fixture_ordinal"],
                    "source_name": fixture_row["source_name"],
                }
            )
        return {
            "content_hash": row["content_hash"],
            "fixtures": fixtures,
            "manifest": manifest,
        }

    @classmethod
    def _result_connection(
        cls,
        connection: sqlite3.Connection,
        run: sqlite3.Row,
        configuration: dict[str, Any],
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM evaluation_results WHERE run_id = ?",
            (run["run_id"],),
        ).fetchone()
        if row is None:
            return None
        value = _verified_object(
            row["canonical_json"], row["content_hash"], "evaluation result"
        )
        expected = {
            "result_id": row["result_id"],
            "run_id": row["run_id"],
            "outcome": row["outcome"],
            "evidence_origin": row["evidence_origin"],
            "observed_at": row["observed_at"],
        }
        if any(value.get(key) != item for key, item in expected.items()):
            raise IntegrityInspectionError("evaluation result projection drift")
        for key, column in (
            ("scores", "scores_json"),
            ("critical_failures", "critical_failures_json"),
            ("runtime_observed", "runtime_observed_json"),
            (
                "candidate_reported_metadata",
                "candidate_reported_metadata_json",
            ),
            ("replay_metadata", "replay_metadata_json"),
        ):
            if canonical_json_text(value.get(key)) != row[column]:
                raise IntegrityInspectionError(f"evaluation result {key} drift")
        if row["run_hash"] != run["content_hash"]:
            raise IntegrityInspectionError("evaluation result run hash conflict")
        cls._validate_reconstructed_result_schema(run, configuration, value)
        return {"content_hash": row["content_hash"], "value": value}

    @classmethod
    def _plan_connection(
        cls,
        connection: sqlite3.Connection,
        plan_id: str,
    ) -> EvaluationReconstruction:
        plan_row = connection.execute(
            "SELECT * FROM evaluation_plans WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        if plan_row is None:
            raise NotFoundError("evaluation plan does not exist")
        plan_value = _verified_object(
            plan_row["canonical_json"], plan_row["content_hash"], "evaluation plan"
        )
        expected_plan = {
            "plan_id": plan_row["plan_id"],
            "plan_version": plan_row["plan_version"],
            "configuration_id": plan_row["configuration_id"],
            "configuration_hash": plan_row["configuration_hash"],
            "fixture_set_id": plan_row["fixture_set_id"],
            "fixture_set_version": plan_row["fixture_set_version"],
            "fixture_set_hash": plan_row["fixture_set_hash"],
            "created_at": plan_row["created_at"],
        }
        if any(plan_value.get(key) != item for key, item in expected_plan.items()):
            raise IntegrityInspectionError("evaluation plan projection drift")
        config_row, configuration = cls._configuration_value(
            connection, plan_row["configuration_id"]
        )
        if config_row["content_hash"] != plan_row["configuration_hash"]:
            raise IntegrityInspectionError("evaluation plan configuration conflict")
        fixture_set = cls._fixture_set_connection(
            connection,
            plan_row["fixture_set_id"],
            plan_row["fixture_set_version"],
        )
        if fixture_set["content_hash"] != plan_row["fixture_set_hash"]:
            raise IntegrityInspectionError("evaluation plan fixture-set conflict")

        binding_rows = tuple(
            connection.execute(
                """
                SELECT * FROM evaluation_plan_candidates
                WHERE plan_id = ? ORDER BY blind_candidate_id
                """,
                (plan_id,),
            )
        )
        bindings = []
        for row in binding_rows:
            candidate = cls._candidate_connection(connection, row["candidate_id"])
            if (
                row["plan_hash"] != plan_row["content_hash"]
                or row["candidate_hash"] != candidate["content_hash"]
            ):
                raise IntegrityInspectionError("evaluation candidate binding conflict")
            bindings.append(
                {
                    "blind_candidate_id": row["blind_candidate_id"],
                    "candidate_hash": row["candidate_hash"],
                    "candidate_id": row["candidate_id"],
                }
            )
        if sorted(
            bindings, key=lambda item: item["candidate_id"]
        ) != plan_value.get("candidate_bindings"):
            raise IntegrityInspectionError("evaluation plan candidate set changed")

        run_rows = tuple(
            connection.execute(
                "SELECT * FROM evaluation_runs WHERE plan_id = ? ORDER BY run_ordinal",
                (plan_id,),
            )
        )
        stored_run_values = []
        runs = []
        condition_by_id = {
            item["condition_id"]: item for item in configuration["conditions"]
        }
        fixture_ids = {
            fixture["definition"]["fixture_id"] for fixture in fixture_set["fixtures"]
        }
        blind_ids = {item["blind_candidate_id"] for item in bindings}
        for run_row in run_rows:
            run_value = _verified_object(
                run_row["canonical_json"],
                run_row["content_hash"],
                "evaluation run",
            )
            expected_run = {
                "run_id": run_row["run_id"],
                "plan_id": run_row["plan_id"],
                "condition_id": run_row["condition_id"],
                "condition_label": run_row["condition_label"],
                "blind_candidate_id": run_row["blind_candidate_id"],
                "fixture_id": run_row["fixture_id"],
                "repetition_index": run_row["repetition_index"],
                "run_ordinal": run_row["run_ordinal"],
                "planned_at": run_row["planned_at"],
            }
            if any(run_value.get(key) != item for key, item in expected_run.items()):
                raise IntegrityInspectionError("evaluation run projection drift")
            if canonical_json_text(run_value.get("ablation_metadata")) != run_row[
                "ablation_metadata_json"
            ]:
                raise IntegrityInspectionError("evaluation run ablation drift")
            condition = condition_by_id.get(run_row["condition_id"])
            expected_ablation = (
                canonical_json_text(
                    {
                        "condition": condition["name"],
                        "definition": condition["ablation_metadata"],
                    }
                )
                if condition is not None
                else None
            )
            if (
                run_row["plan_hash"] != plan_row["content_hash"]
                or run_row["blind_candidate_id"] not in blind_ids
                or run_row["fixture_id"] not in fixture_ids
                or condition is None
                or condition["label"] != run_row["condition_label"]
                or run_row["ablation_metadata_json"] != expected_ablation
                or run_row["repetition_index"] >= configuration["repetitions"]
            ):
                raise IntegrityInspectionError("evaluation run parent conflict")
            transitions = []
            for transition_row in connection.execute(
                """
                SELECT * FROM evaluation_run_state_transitions
                WHERE run_id = ? ORDER BY sequence
                """,
                (run_row["run_id"],),
            ):
                transition_value = _verified_object(
                    transition_row["canonical_json"],
                    transition_row["content_hash"],
                    "evaluation run transition",
                )
                projected = {
                    "transition_id": transition_row["transition_id"],
                    "run_id": transition_row["run_id"],
                    "sequence": transition_row["sequence"],
                    "from_state": transition_row["from_state"],
                    "to_state": transition_row["to_state"],
                    "occurred_at": transition_row["occurred_at"],
                }
                if any(
                    transition_value.get(key) != item
                    for key, item in projected.items()
                ):
                    raise IntegrityInspectionError("evaluation transition projection drift")
                transitions.append(
                    {
                        "content_hash": transition_row["content_hash"],
                        "value": transition_value,
                    }
                )
            if (
                not transitions
                or transitions[0]["value"]["sequence"] != 0
                or transitions[0]["value"]["from_state"] is not None
                or transitions[0]["value"]["to_state"] != "planned"
                or len(transitions) > 2
            ):
                raise IntegrityInspectionError("evaluation transition history is invalid")
            result = cls._result_connection(
                connection, run_row, configuration
            )
            if result is None and len(transitions) != 1:
                raise IntegrityInspectionError("evaluation terminal state lacks result")
            if result is not None and (
                len(transitions) != 2
                or transitions[1]["value"]["sequence"] != 1
                or transitions[1]["value"]["from_state"] != "planned"
                or transitions[1]["value"]["to_state"]
                != result["value"]["outcome"]
            ):
                raise IntegrityInspectionError("evaluation result transition conflict")
            stored_run_values.append(run_value)
            runs.append(
                {
                    "content_hash": run_row["content_hash"],
                    "result": result,
                    "transitions": transitions,
                    "value": run_value,
                }
            )
        if stored_run_values != plan_value.get("runs"):
            raise IntegrityInspectionError("evaluation plan run set changed")

        reconstruction = {
            "candidate_bindings": bindings,
            "configuration": {
                "content_hash": config_row["content_hash"],
                "value": configuration,
            },
            "fixture_set": fixture_set,
            "plan": {
                "content_hash": plan_row["content_hash"],
                "value": plan_value,
            },
            "runs": runs,
        }
        canonical = canonical_json_text(reconstruction)
        return EvaluationReconstruction(
            canonical_json=canonical,
            content_hash=sha256_canonical_json(reconstruction),
        )

    def reconstruct_candidate(self, candidate_id: str) -> dict[str, Any]:
        validate_identifier(candidate_id, field="candidate_id")
        return self._kernel.read(
            lambda connection: self._candidate_connection(connection, candidate_id)
        )

    def reconstruct_configuration(
        self, configuration_id: str
    ) -> dict[str, Any]:
        validate_identifier(configuration_id, field="configuration_id")

        def operation(connection: sqlite3.Connection) -> dict[str, Any]:
            row, value = self._configuration_value(connection, configuration_id)
            fixture_set = self._fixture_set_connection(
                connection, row["fixture_set_id"], row["fixture_set_version"]
            )
            if fixture_set["content_hash"] != row["fixture_set_hash"]:
                raise IntegrityInspectionError(
                    "evaluation configuration fixture-set hash conflict"
                )
            return {
                "content_hash": row["content_hash"],
                "fixture_set_hash": fixture_set["content_hash"],
                "value": value,
            }

        return self._kernel.read(operation)

    def reconstruct_fixture_set(
        self,
        fixture_set_id: str,
        fixture_set_version: str,
    ) -> dict[str, Any]:
        validate_identifier(fixture_set_id, field="fixture_set_id")
        return self._kernel.read(
            lambda connection: self._fixture_set_connection(
                connection, fixture_set_id, fixture_set_version
            )
        )

    def reconstruct_plan(self, plan_id: str) -> EvaluationReconstruction:
        validate_identifier(plan_id, field="plan_id")

        def operation(connection: sqlite3.Connection) -> EvaluationReconstruction:
            connection.execute("BEGIN")
            return self._plan_connection(connection, plan_id)

        return self._kernel.read(operation)

    def plan_identifiers(self) -> tuple[str, ...]:
        return self._kernel.read(
            lambda connection: tuple(
                row["plan_id"]
                for row in connection.execute(
                    "SELECT plan_id FROM evaluation_plans ORDER BY plan_id"
                )
            )
        )
