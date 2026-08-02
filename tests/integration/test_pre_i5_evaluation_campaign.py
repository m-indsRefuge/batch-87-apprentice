from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import (
    ConflictError,
    IntegrityInspectionError,
    ValidationError,
)
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.evaluation import (
    DeterministicEvaluationService,
    ScoreObservation,
)
from batch87_apprentice.evaluation.store import EvaluationStore
from batch87_apprentice.persistence import PersistenceService
from tests.support.pre_i5_fixtures import (
    build_harness,
    candidate,
    complete_mock_campaign,
    result_for_run,
)
from tests.support.sql_probe import SqlProbe

ROOT = Path(__file__).resolve().parents[2]


def _count(config, table: str) -> int:
    return SqlProbe(config).read(
        lambda connection: connection.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]
    )


def test_mock_campaign_reconstructs_every_condition_and_replays_identically(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)
    results, report = complete_mock_campaign(harness)

    reconstructed = harness.service.reconstruct(harness.plan.plan_id)
    replayed = DeterministicEvaluationService(harness.config).report(
        harness.plan.plan_id
    )

    assert len(harness.plan.runs) == 12
    assert len(results) == len(harness.plan.runs)
    assert {run.condition_label for run in harness.plan.runs} == {
        "enabled",
        "withheld",
        "over_transfer",
    }
    assert [
        stored["value"]["run_ordinal"]
        for stored in reconstructed.value["runs"]
    ] == list(range(12))
    assert all(
        stored["result"] is not None
        and len(stored["transitions"]) == 2
        for stored in reconstructed.value["runs"]
    )
    assert replayed.canonical_json == report.canonical_json
    assert replayed.content_hash == report.content_hash
    assert report.value["campaign_status"] == "complete"
    assert harness.candidate.candidate_id not in report.canonical_json
    assert report.value["blinding"] == "preserved"
    assert all(
        summary["admission_effect"] == "none"
        and summary["ranking_authority"] == "none"
        for summary in report.value["candidate_summaries"]
    )


def test_complete_campaign_reconstructs_in_a_fresh_python_process(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)
    _, report = complete_mock_campaign(harness)
    expected_reconstruction = harness.service.reconstruct(harness.plan.plan_id)
    script = (
        "from pathlib import Path;"
        "from batch87_apprentice.persistence import DatabaseConfig;"
        "from batch87_apprentice.evaluation import DeterministicEvaluationService;"
        f"s=DeterministicEvaluationService(DatabaseConfig(Path({str(harness.config.path)!r})));"
        f"print(s.reconstruct({harness.plan.plan_id!r}).content_hash);"
        f"print(s.report({harness.plan.plan_id!r}).content_hash)"
    )

    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.splitlines() == [
        expected_reconstruction.content_hash,
        report.content_hash,
    ]


def test_partial_campaign_preserves_missing_and_critical_negative_evidence(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)
    run = next(
        item for item in harness.plan.runs if item.condition_label == "enabled"
    )
    harness.service.record_result(
        result_for_run(
            run,
            number=8_300_001,
            outcome="critical_failure",
            critical_code="fabricated_authority",
        )
    )

    report = harness.service.report(harness.plan.plan_id)
    observed = next(item for item in report.value["runs"] if item["run_id"] == run.run_id)

    assert report.value["campaign_status"] == "incomplete_missing_evidence"
    assert report.value["negative_evidence_preserved"] is True
    assert observed["evidence_status"] == "recorded"
    assert observed["critical_invalidation"] is True
    assert observed["numeric_scores"] == []
    assert observed["critical_failures"][0]["code"] == "fabricated_authority"
    assert sum(
        item["evidence_status"] == "missing" for item in report.value["runs"]
    ) == len(harness.plan.runs) - 1


def test_duplicate_and_conflicting_registry_identities_fail_closed(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)

    with pytest.raises(ConflictError):
        harness.service.register_candidate(harness.candidate)
    with pytest.raises(ConflictError):
        harness.service.register_candidate(
            candidate(
                candidate_id=harness.candidate.candidate_id,
                revision="conflicting-revision",
            )
        )
    with pytest.raises(ConflictError):
        harness.service.register_configuration(harness.configuration)
    with pytest.raises(ConflictError):
        harness.service.register_configuration(
            replace(harness.configuration, timeout_ms=9_999)
        )

    assert _count(harness.config, "evaluation_candidates") == 1
    assert _count(harness.config, "evaluation_configurations") == 1


def test_duplicate_and_contradictory_results_fail_closed(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)
    enabled = next(
        run for run in harness.plan.runs if run.condition_label == "enabled"
    )
    withheld = next(
        run for run in harness.plan.runs if run.condition_label == "withheld"
    )
    first = result_for_run(enabled, number=8_300_010)
    harness.service.record_result(first)

    with pytest.raises(ConflictError):
        harness.service.record_result(first)
    with pytest.raises(ConflictError):
        harness.service.record_result(
            result_for_run(enabled, number=8_300_011, outcome="invalid")
        )
    with pytest.raises(ValidationError, match="withheld run"):
        harness.service.record_result(
            result_for_run(withheld, number=8_300_012, outcome="completed")
        )
    unknown_score = replace(
        result_for_run(
            next(
                run
                for run in harness.plan.runs
                if run.condition_label == "over_transfer"
            ),
            number=8_300_013,
        ),
        scores=(
            ScoreObservation(
                dimension="unregistered_dimension",
                score=4,
                rationale="Synthetic contradiction fixture.",
                evidence_refs=("synthetic_fixture",),
            ),
        ),
    )
    with pytest.raises(ValidationError, match="unknown score dimension"):
        harness.service.record_result(unknown_score)

    assert _count(harness.config, "evaluation_results") == 1


def test_result_and_terminal_transition_share_one_commit_boundary(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)
    run = next(
        item for item in harness.plan.runs if item.condition_label == "enabled"
    )
    result = result_for_run(run, number=8_300_020)
    visible_during_transaction: list[int] = []

    def observe(point: str) -> None:
        assert point == "after_result"
        with sqlite3.connect(harness.config.path) as connection:
            visible_during_transaction.append(
                connection.execute(
                    "SELECT COUNT(*) FROM evaluation_results WHERE run_id = ?",
                    (run.run_id,),
                ).fetchone()[0]
            )

    EvaluationStore(harness.config).record_result(
        result,
        terminal_transition_id="00000000-0000-4000-8000-000000830021",
        failure_injector=(
            lambda point: observe(point) if point == "after_result" else None
        ),
    )

    assert visible_during_transaction == [0]
    assert _count(harness.config, "evaluation_results") == 1
    assert SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT COUNT(*) FROM evaluation_run_state_transitions
            WHERE run_id = ? AND sequence = 1
            """,
            (run.run_id,),
        ).fetchone()[0]
    ) == 1


def test_injected_result_failure_rolls_back_result_and_transition(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)
    run = next(
        item for item in harness.plan.runs if item.condition_label == "enabled"
    )

    def fail(point: str) -> None:
        if point == "after_result":
            raise RuntimeError("injected PRE-I5 result failure")

    with pytest.raises(RuntimeError, match="injected PRE-I5 result failure"):
        EvaluationStore(harness.config).record_result(
            result_for_run(run, number=8_300_030),
            terminal_transition_id="00000000-0000-4000-8000-000000830031",
            failure_injector=fail,
        )

    assert _count(harness.config, "evaluation_results") == 0
    assert SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            "SELECT COUNT(*) FROM evaluation_run_state_transitions WHERE run_id = ?",
            (run.run_id,),
        ).fetchone()[0]
    ) == 1


def test_integrity_inspection_covers_sqlite_foreign_keys_and_reconstruction(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)
    complete_mock_campaign(harness)

    report = PersistenceService(harness.config).deterministic_evaluation_integrity.inspect()

    assert report.ok
    assert report.findings == ()
    assert report.candidate_count == 1
    assert report.configuration_count == 1
    assert report.fixture_set_count == 1
    assert report.plan_count == 1
    assert report.run_count == 12
    assert report.result_count == 12
    assert SqlProbe(harness.config).read(
        lambda connection: tuple(
            tuple(row) for row in connection.execute("PRAGMA integrity_check")
        )
    ) == (("ok",),)
    assert SqlProbe(harness.config).read(
        lambda connection: tuple(connection.execute("PRAGMA foreign_key_check"))
    ) == ()


def test_tampered_candidate_projection_is_detected_without_rewriting_evidence(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("evaluation_candidates_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE evaluation_candidates SET model_revision = ?
            WHERE candidate_id = ?
            """,
            ("tampered-revision", harness.candidate.candidate_id),
        ),
    )

    with pytest.raises(IntegrityInspectionError, match="projection drift"):
        harness.service.reconstruct(harness.plan.plan_id)
    report = PersistenceService(harness.config).deterministic_evaluation_integrity.inspect()
    assert not report.ok
    assert any(
        finding.code in {
            "candidate_reconstruction_invalid",
            "plan_reconstruction_invalid",
        }
        for finding in report.findings
    )


def test_coherently_rehashed_contradictory_result_schema_is_detected(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)
    enabled = next(
        run for run in harness.plan.runs if run.condition_label == "enabled"
    )
    harness.service.record_result(result_for_run(enabled, number=8_300_040))

    def contradict(connection: sqlite3.Connection) -> None:
        row = connection.execute(
            "SELECT canonical_json FROM evaluation_results WHERE run_id = ?",
            (enabled.run_id,),
        ).fetchone()
        value = parse_json(row[0])
        value["scores"][0]["dimension"] = "unregistered_dimension"
        connection.execute(
            """
            UPDATE evaluation_results
            SET scores_json = ?, canonical_json = ?, content_hash = ?
            WHERE run_id = ?
            """,
            (
                canonical_json_text(value["scores"]),
                canonical_json_text(value),
                sha256_canonical_json(value),
                enabled.run_id,
            ),
        )

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("evaluation_results_immutable",),
        contradict,
    )

    with pytest.raises(IntegrityInspectionError, match="score schema"):
        harness.service.reconstruct(harness.plan.plan_id)
