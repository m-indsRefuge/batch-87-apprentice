from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from batch87_apprentice.common.errors import ConflictError, ValidationError
from batch87_apprentice.memory import (
    EpisodeCorrectionIntegrityInspector,
)
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.service import PersistenceService
from tests.support.i2_fixtures import NOW, uid
from tests.support.i3c2_fixtures import (
    add_corrects_relationship,
    build_c2_harness,
    c2_evidence,
    claimed_evaluation,
    create_correction,
    create_episode,
    create_terminal_task,
    episode_components,
)
from tests.support.sql_probe import SqlProbe


def build_records(tmp_path: Path, *, base: int = 640_000):
    harness = build_c2_harness(tmp_path)
    task_id = create_terminal_task(harness, base=base, status="completed")
    anchor = claimed_evaluation(harness, base=base + 100)
    _, episode, _ = create_episode(
        harness,
        base=base + 200,
        task_id=task_id,
        evaluation_record_ids=(anchor.evaluation_record_id,),
    )
    _, correction, _ = create_correction(
        harness,
        base=base + 300,
        target_episode_id=episode.record_id,
        target_output_evidence_id=episode.output_evidence_ids[0],
    )
    return harness, task_id, anchor, episode, correction


def codes(harness) -> set[str]:
    return {
        item.code
        for item in harness.persistence.episode_correction_integrity.inspect().findings
    }


def test_clean_ledgers_are_clean_in_dedicated_and_top_level_reports(
    tmp_path: Path,
) -> None:
    harness, _, _, episode, correction = build_records(tmp_path)
    report = harness.persistence.episode_correction_integrity.inspect()
    assert report.ok
    assert report.findings == ()
    assert harness.persistence.integrity.inspect().ok
    assert harness.persistence.episode_correction_ledger.reconstruct_episode(
        episode.record_id
    )["integrity"]["valid"]
    assert harness.persistence.episode_correction_ledger.reconstruct_correction(
        correction.record_id
    )["integrity"]["valid"]


@pytest.mark.parametrize(
    "lineage_kind",
    ("episode_input", "episode_output", "correction_support"),
)
def test_c2_inline_lineage_content_cannot_be_deleted(
    tmp_path: Path,
    lineage_kind: str,
) -> None:
    harness, _, _, episode, correction = build_records(
        tmp_path,
        base=640_500,
    )
    probe = SqlProbe(harness.config)
    support_id = probe.read(
        lambda connection: connection.execute(
            """
            SELECT evidence_id
            FROM correction_supporting_evidence
            WHERE record_id = ?
            ORDER BY evidence_order
            LIMIT 1
            """,
            (correction.record_id,),
        ).fetchone()[0]
    )
    evidence_id = {
        "episode_input": episode.input_evidence_ids[0],
        "episode_output": episode.output_evidence_ids[0],
        "correction_support": support_id,
    }[lineage_kind]

    with pytest.raises(ConflictError, match="integrity constraint"):
        probe.write(
            lambda connection: connection.execute(
                "DELETE FROM evidence_inline_text WHERE evidence_id = ?",
                (evidence_id,),
            )
        )

    assert probe.read(
        lambda connection: connection.execute(
            """
            SELECT COUNT(*) FROM evidence_inline_text
            WHERE evidence_id = ?
            """,
            (evidence_id,),
        ).fetchone()[0]
    ) == 1


def test_episode_creation_revalidates_exact_persisted_evidence_bytes(
    tmp_path: Path,
) -> None:
    harness = build_c2_harness(tmp_path)
    task_id = create_terminal_task(
        harness,
        base=640_800,
        status="completed",
    )
    envelope, payload, items = episode_components(
        harness,
        base=640_900,
        task_id=task_id,
    )
    for item in items:
        harness.persistence.evidence.create(item)

    probe = SqlProbe(harness.config)
    probe.write(
        lambda connection: connection.execute(
            "DELETE FROM evidence_inline_text WHERE evidence_id = ?",
            (payload.input_evidence_ids[0],),
        )
    )

    with pytest.raises(
        ValidationError,
        match="preserved exact inline bytes",
    ):
        harness.persistence.episode_correction_ledger.create_episode(
            envelope,
            payload,
            lifecycle_transition_id=uid(640_930),
            approval_transition_id=uid(640_931),
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )

    assert probe.read(
        lambda connection: connection.execute(
            "SELECT 1 FROM records WHERE record_id = ?",
            (payload.record_id,),
        ).fetchone()
    ) is None


def test_removed_finalization_guards_expose_detectable_late_lineage(
    tmp_path: Path,
) -> None:
    harness, _, _, episode, correction = build_records(tmp_path, base=641_000)
    late_episode_evidence = c2_evidence(
        641_500,
        content="Deliberate late episode lineage corruption.",
        captured_by_entity=harness.operator_id,
    )
    late_correction_evidence = c2_evidence(
        641_501,
        content="Deliberate late correction lineage corruption.",
        evidence_kind="human_statement",
        captured_by_entity=harness.operator_id,
    )
    harness.persistence.evidence.create(late_episode_evidence)
    harness.persistence.evidence.create(late_correction_evidence)
    probe = SqlProbe(harness.config)

    def corrupt(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO episode_input_evidence (
                record_id, evidence_id, evidence_order
            ) VALUES (?, ?, 1)
            """,
            (episode.record_id, late_episode_evidence.evidence_id),
        )
        connection.execute(
            """
            INSERT INTO record_evidence_links (
                record_id, evidence_id, relationship, explanation
            ) VALUES (?, ?, 'derived_from', ?)
            """,
            (
                episode.record_id,
                late_episode_evidence.evidence_id,
                "Deliberate test-only late episode lineage.",
            ),
        )
        connection.execute(
            """
            INSERT INTO correction_supporting_evidence (
                record_id, evidence_id, evidence_order
            ) VALUES (?, ?, 1)
            """,
            (correction.record_id, late_correction_evidence.evidence_id),
        )
        connection.execute(
            """
            INSERT INTO record_evidence_links (
                record_id, evidence_id, relationship, explanation
            ) VALUES (?, ?, 'supports', ?)
            """,
            (
                correction.record_id,
                late_correction_evidence.evidence_id,
                "Deliberate test-only late correction lineage.",
            ),
        )

    probe.corrupt_after_dropping_triggers(
        (
            "c2_episode_input_evidence_finalization_guard",
            "c2_correction_support_finalization_guard",
            "c2_record_evidence_link_finalization_guard",
        ),
        corrupt,
    )

    report = harness.persistence.episode_correction_integrity.inspect()
    findings = {(finding.record_id, finding.code) for finding in report.findings}
    assert (episode.record_id, "I3C2-EPISODE-CONTENT-HASH") in findings
    assert (correction.record_id, "I3C2-CORRECTION-CONTENT-HASH") in findings


@pytest.mark.parametrize(
    ("defect", "expected"),
    (
        ("canonical", "I3C2-EPISODE-CANONICAL-JSON"),
        ("order", "I3C2-LINEAGE-ORDER"),
        ("overlap", "I3C2-EPISODE-EVIDENCE-OVERLAP"),
        ("wrong_link", "I3C2-EVIDENCE-LINK-MISSING"),
        ("invalid_evidence", "I3C2-EVIDENCE-INTEGRITY"),
        ("altered_evidence", "I3C2-EVIDENCE-CONTENT"),
        ("deleted_evidence", "I3C2-EVIDENCE-CONTENT"),
        ("nonterminal", "I3C2-EPISODE-OCCURRENCE"),
        ("envelope_type", "I3C2-MISSING-PAYLOAD"),
        ("active_unapproved", "I3C2-ACTIVE-WITHOUT-APPROVAL"),
    ),
)
def test_episode_corruption_is_detected(
    tmp_path: Path,
    defect: str,
    expected: str,
) -> None:
    harness, task_id, _, episode, _ = build_records(tmp_path)
    probe = SqlProbe(harness.config)
    if defect == "canonical":
        probe.corrupt_after_dropping_triggers(
            ("episodes_immutable",),
            lambda connection: connection.execute(
                "UPDATE episodes SET canonical_json = '{}' WHERE record_id = ?",
                (episode.record_id,),
            ),
        )
    elif defect == "order":
        probe.corrupt_after_dropping_triggers(
            ("episode_input_evidence_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE episode_input_evidence SET evidence_order = 5
                WHERE record_id = ?
                """,
                (episode.record_id,),
            ),
        )
    elif defect == "overlap":
        probe.corrupt_after_dropping_triggers(
            (
                "episode_input_evidence_insert_guard",
                "c2_episode_input_evidence_finalization_guard",
            ),
            lambda connection: connection.execute(
                """
                INSERT INTO episode_input_evidence (
                    record_id, evidence_id, evidence_order
                ) VALUES (?, ?, 1)
                """,
                (episode.record_id, episode.output_evidence_ids[0]),
            ),
        )
    elif defect == "wrong_link":
        probe.corrupt_after_dropping_triggers(
            ("c2_record_evidence_links_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE record_evidence_links SET relationship = 'supports'
                WHERE record_id = ? AND evidence_id = ?
                """,
                (episode.record_id, episode.input_evidence_ids[0]),
            ),
        )
    elif defect == "invalid_evidence":
        probe.corrupt_after_dropping_triggers(
            ("c2_output_evidence_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE evidence_items SET integrity_status = 'mismatch'
                WHERE evidence_id = ?
                """,
                (episode.output_evidence_ids[0],),
            ),
        )
    elif defect == "altered_evidence":
        probe.corrupt_after_dropping_triggers(
            ("evidence_inline_content_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE evidence_inline_text SET content = 'altered bytes'
                WHERE evidence_id = ?
                """,
                (episode.output_evidence_ids[0],),
            ),
        )
    elif defect == "deleted_evidence":
        probe.corrupt_after_dropping_triggers(
            ("c2_inline_evidence_content_no_delete",),
            lambda connection: connection.execute(
                """
                DELETE FROM evidence_inline_text
                WHERE evidence_id = ?
                """,
                (episode.output_evidence_ids[0],),
            ),
        )
    elif defect == "nonterminal":
        probe.corrupt_after_dropping_triggers(
            ("tasks_status_requires_transition",),
            lambda connection: connection.execute(
                """
                UPDATE tasks SET status = 'active', completed_at = NULL
                WHERE task_id = ?
                """,
                (task_id,),
            ),
        )
    elif defect == "envelope_type":
        probe.corrupt_after_dropping_triggers(
            ("c2_records_core_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE records SET record_type = 'correction'
                WHERE record_id = ?
                """,
                (episode.record_id,),
            ),
        )
    else:
        probe.corrupt_after_dropping_triggers(
            (
                "c2_episode_activation_guard",
                "memory_records_activation_guard",
                "memory_records_lifecycle_requires_transition",
            ),
            lambda connection: connection.execute(
                """
                UPDATE records SET lifecycle_state = 'active'
                WHERE record_id = ?
                """,
                (episode.record_id,),
            ),
        )
    assert expected in codes(harness)


def test_evaluation_anchor_state_drift_is_detected(tmp_path: Path) -> None:
    harness, _, anchor, _, _ = build_records(tmp_path)
    harness.persistence.self_episodic_memory.transition_evaluation_anchor(
        anchor.evaluation_record_id,
        transition_id=uid(641_000),
        to_state="invalid",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
        transition_evidence_id=anchor.provenance_evidence_id,
        reason_code="evaluation_invalidated",
    )
    assert "I3C2-EVALUATION-ANCHOR-INVALID" in codes(harness)


@pytest.mark.parametrize(
    ("defect", "expected"),
    (
        ("canonical", "I3C2-CORRECTION-CANONICAL-JSON"),
        ("support_missing", "I3C2-CORRECTION-SUPPORT-MISSING"),
        ("wrong_link", "I3C2-EVIDENCE-LINK-MISSING"),
        ("issuer_inactive", "I3C2-CORRECTION-ISSUER"),
        ("target_revoked", "I3C2-CORRECTION-TARGET"),
        ("target_evidence", "I3C2-EVIDENCE-INTEGRITY"),
        ("cross_project", "I3C2-CORRECTION-TARGET"),
        ("relationship_direction", "I3C2-CORRECTS-RELATIONSHIP"),
        ("grant_unconsumed", "I3C2-CORRECTS-GRANT"),
        ("active_unapproved", "I3C2-ACTIVE-WITHOUT-APPROVAL"),
    ),
)
def test_correction_corruption_is_detected(
    tmp_path: Path,
    defect: str,
    expected: str,
) -> None:
    harness, _, _, episode, correction = build_records(tmp_path)
    probe = SqlProbe(harness.config)
    if defect in {"relationship_direction", "grant_unconsumed"}:
        relationship = add_corrects_relationship(
            harness,
            correction_id=correction.record_id,
            episode_id=episode.record_id,
            base=642_000,
        )
    if defect == "canonical":
        probe.corrupt_after_dropping_triggers(
            ("corrections_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE corrections SET canonical_json = '{}'
                WHERE record_id = ?
                """,
                (correction.record_id,),
            ),
        )
    elif defect == "support_missing":
        probe.corrupt_after_dropping_triggers(
            ("correction_supporting_evidence_no_delete",),
            lambda connection: connection.execute(
                """
                DELETE FROM correction_supporting_evidence
                WHERE record_id = ?
                """,
                (correction.record_id,),
            ),
        )
    elif defect == "wrong_link":
        probe.corrupt_after_dropping_triggers(
            ("c2_record_evidence_links_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE record_evidence_links SET relationship = 'contextualises'
                WHERE record_id = ? AND relationship = 'supports'
                """,
                (correction.record_id,),
            ),
        )
    elif defect == "issuer_inactive":
        probe.write(
            lambda connection: connection.execute(
                "UPDATE entities SET status = 'inactive' WHERE entity_id = ?",
                (harness.operator_id,),
            )
        )
    elif defect == "target_revoked":
        harness.memory.transition_lifecycle(
            episode.record_id,
            transition_id=uid(642_100),
            to_state="revoked",
            reason_code="target_revoked",
            changed_at=NOW,
            changed_by_principal="operator",
            changed_by_entity_id=harness.operator_id,
        )
    elif defect == "target_evidence":
        probe.corrupt_after_dropping_triggers(
            ("c2_output_evidence_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE evidence_items SET integrity_status = 'mismatch'
                WHERE evidence_id = ?
                """,
                (episode.output_evidence_ids[0],),
            ),
        )
    elif defect == "cross_project":
        probe.corrupt_after_dropping_triggers(
            ("c2_records_core_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE records SET project_scope_id = ?
                WHERE record_id = ?
                """,
                (harness.c1.i2.other_project_scope_id, episode.record_id),
            ),
        )
    elif defect == "relationship_direction":
        probe.corrupt_after_dropping_triggers(
            ("record_relationships_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE record_relationships
                SET source_record_id = ?, target_record_id = ?
                WHERE relationship_id = ?
                """,
                (
                    episode.record_id,
                    correction.record_id,
                    relationship.relationship_id,
                ),
            ),
        )
    elif defect == "grant_unconsumed":
        probe.corrupt_after_dropping_triggers(
            ("memory_relationship_grants_consumption_guard",),
            lambda connection: connection.execute(
                """
                UPDATE memory_relationship_grants
                SET consumed_at = NULL, consumed_by_relationship_id = NULL
                WHERE consumed_by_relationship_id = ?
                """,
                (relationship.relationship_id,),
            ),
        )
    else:
        probe.corrupt_after_dropping_triggers(
            (
                "c2_correction_activation_guard",
                "memory_records_activation_guard",
                "memory_records_lifecycle_requires_transition",
            ),
            lambda connection: connection.execute(
                """
                UPDATE records SET lifecycle_state = 'active'
                WHERE record_id = ?
                """,
                (correction.record_id,),
            ),
        )
    assert expected in codes(harness)


@pytest.mark.parametrize(
    ("defect", "expected"),
    (
        ("missing_episode_payload", "I3C2-MISSING-PAYLOAD"),
        ("orphaned_correction", "I3C2-ORPHANED-PAYLOAD"),
        ("missing_target", "I3C2-CORRECTION-TARGET"),
        ("missing_target_evidence", "I3C2-EVIDENCE-MISSING"),
    ),
)
def test_foreign_key_corruption_is_detected_in_disposable_database(
    tmp_path: Path,
    defect: str,
    expected: str,
) -> None:
    harness, _, _, episode, correction = build_records(tmp_path)
    connection = sqlite3.connect(harness.config.path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        if defect == "missing_episode_payload":
            connection.execute("DROP TRIGGER episodes_no_delete")
            connection.execute(
                "DELETE FROM episodes WHERE record_id = ?",
                (episode.record_id,),
            )
        elif defect == "orphaned_correction":
            connection.execute(
                "DELETE FROM records WHERE record_id = ?",
                (correction.record_id,),
            )
        elif defect == "missing_target":
            connection.execute("DROP TRIGGER corrections_immutable")
            connection.execute(
                """
                UPDATE corrections SET target_episode_id = ?
                WHERE record_id = ?
                """,
                (uid(649_999), correction.record_id),
            )
        else:
            connection.execute("DROP TRIGGER c2_output_evidence_no_delete")
            connection.execute(
                "DELETE FROM evidence_items WHERE evidence_id = ?",
                (episode.output_evidence_ids[0],),
            )
        connection.commit()
    finally:
        connection.close()
    assert expected in codes(harness)


def test_file_reopen_and_separate_process_reconstruct_exact_c2_records(
    tmp_path: Path,
) -> None:
    harness, _, _, episode, correction = build_records(tmp_path)
    reopened = PersistenceService(harness.config)
    assert reopened.episode_correction_ledger.reconstruct_episode(
        episode.record_id
    )["integrity"]["valid"]
    assert reopened.episode_correction_ledger.reconstruct_correction(
        correction.record_id
    )["integrity"]["valid"]

    script = (
        "import json;"
        "from pathlib import Path;"
        "from batch87_apprentice.persistence.config import DatabaseConfig;"
        "from batch87_apprentice.persistence.service import PersistenceService;"
        f"s=PersistenceService(DatabaseConfig(Path({str(harness.config.path)!r})));"
        f"e=s.episode_correction_ledger.reconstruct_episode({episode.record_id!r});"
        f"c=s.episode_correction_ledger.reconstruct_correction({correction.record_id!r});"
        "print(json.dumps({'episode':e['integrity']['valid'],"
        "'correction':c['integrity']['valid'],"
        "'episode_hash':e['content_hash'],"
        "'correction_hash':c['content_hash']},sort_keys=True))"
    )
    repository_root = Path(__file__).resolve().parents[2]
    source_root = repository_root / "src"
    existing_pythonpath = os.environ.get("PYTHONPATH")
    pythonpath_entries = [str(source_root)]
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)

    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(pythonpath_entries),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
    }
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "correction": True,
        "correction_hash": reopened.episode_correction_ledger.reconstruct_correction(
            correction.record_id
        )["content_hash"],
        "episode": True,
        "episode_hash": reopened.episode_correction_ledger.reconstruct_episode(
            episode.record_id
        )["content_hash"],
    }


def test_inspector_is_read_only_and_creates_no_later_phase_records(
    tmp_path: Path,
) -> None:
    harness, _, _, _, _ = build_records(tmp_path)
    probe = SqlProbe(harness.config)
    before = probe.read(
        lambda connection: tuple(
            connection.execute(
                """
                SELECT record_type, COUNT(*) FROM records
                GROUP BY record_type ORDER BY record_type
                """
            )
        )
    )
    report = EpisodeCorrectionIntegrityInspector(harness.config).inspect()
    after = probe.read(
        lambda connection: tuple(
            connection.execute(
                """
                SELECT record_type, COUNT(*) FROM records
                GROUP BY record_type ORDER BY record_type
                """
            )
        )
    )
    assert report.ok
    assert after == before
