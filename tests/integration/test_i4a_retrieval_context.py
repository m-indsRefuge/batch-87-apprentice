from __future__ import annotations

from dataclasses import replace
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.common.errors import (
    ConflictError,
    IntegrityInspectionError,
    NotFoundError,
    ValidationError,
)
from batch87_apprentice.context import (
    CONTEXT_SECTIONS,
    ContextIntegrityInspector,
    ContextRetrievalService,
    DeterministicFallbackRanker,
    RankedCandidate,
    RetrievalRequest,
    StructuredContextPackage,
    build_authoritative_authority_section,
    build_authoritative_task_section,
)
from batch87_apprentice.context.retrieval import _SafeSourceMaterializer
from batch87_apprentice.memory import MemoryKernel
from batch87_apprentice.persistence import PersistenceService
from batch87_apprentice.runtime import GovernedTaskRuntime
from tests.support.i2_fixtures import (
    LATER,
    NOW,
    IdentifierSequence,
    evidence,
    uid,
)
from tests.support.i3d_fixtures import (
    I3DHarness,
    active_rule_source,
    context_item,
    create_uncertainty,
)
from tests.support.i4a_fixtures import (
    InjectExcludedAssembler,
    SubstituteAuthoritativeSectionAssembler,
    SubstituteMaterializedAssembler,
    build_i4a_harness,
    create_active_approved_lesson,
    create_active_construct_memory,
    create_controlled_bundle,
    create_model_output_evidence,
    create_noninline_evidence,
    finalize_items,
    memory_context_item,
    ordinary_evidence_item,
    request_for,
    retrieval_service,
)
from tests.support.sql_probe import SqlProbe


@pytest.fixture
def harness(tmp_path: Path) -> I3DHarness:
    return build_i4a_harness(tmp_path)


def basic_attempt(
    harness: I3DHarness,
    *,
    item_number: int = 1_600_000,
    finalization_number: int = 1_600_001,
    request_number: int = 1_600_002,
    identifier_start: int = 1_610_000,
):
    item = ordinary_evidence_item(harness, number=item_number)
    finalization_id = finalize_items(
        harness,
        (item,),
        finalization_number=finalization_number,
    )
    request = request_for(
        harness,
        finalization_id=finalization_id,
        number=request_number,
    )
    service = retrieval_service(
        harness,
        identifier_start=identifier_start,
    )
    return service, request, service.assemble(request)


def independent_materializations(result) -> dict[str, str]:
    return {
        entry.retrieval_manifest_entry_id: entry.entry_json
        for entry in result.context_package.ordered_entries
        if entry.retrieval_manifest_entry_id is not None
    }


def corrupt_task_evidence_binding(
    harness: I3DHarness,
    corruption: str,
    *,
    base: int,
) -> None:
    if corruption == "required_mismatch":
        triggers = ("governance_decision_evidence_immutable",)

        def corrupt(connection) -> None:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(
                """
                UPDATE governance_decision_evidence
                SET required_evidence_id = ?
                WHERE governance_decision_id = (
                    SELECT governance_decision_id
                    FROM governance_decisions
                    WHERE task_id = ?
                )
                  AND resolved_evidence_id = ?
                """,
                (uid(base), harness.task_id, harness.task_evidence_id),
            )

    elif corruption == "resolved_mismatch":
        substitute = evidence(
            base,
            captured_by_entity=harness.operator_id,
            content="Evidence that is not the task's required evidence.",
        )
        harness.persistence.evidence.create(substitute)
        triggers = ("governance_decision_evidence_immutable",)

        def corrupt(connection) -> None:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(
                """
                UPDATE governance_decision_evidence
                SET resolved_evidence_id = ?
                WHERE governance_decision_id = (
                    SELECT governance_decision_id
                    FROM governance_decisions
                    WHERE task_id = ?
                )
                  AND required_evidence_id = ?
                """,
                (
                    substitute.evidence_id,
                    harness.task_id,
                    harness.task_evidence_id,
                ),
            )

    elif corruption == "unavailable":
        triggers = ("governance_decision_evidence_immutable",)

        def corrupt(connection) -> None:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(
                """
                UPDATE governance_decision_evidence
                SET validation_status = 'missing'
                WHERE governance_decision_id = (
                    SELECT governance_decision_id
                    FROM governance_decisions
                    WHERE task_id = ?
                )
                  AND required_evidence_id = ?
                  AND resolved_evidence_id = ?
                """,
                (
                    harness.task_id,
                    harness.task_evidence_id,
                    harness.task_evidence_id,
                ),
            )

    elif corruption == "decision_project":
        triggers = ("governance_decisions_immutable",)

        def corrupt(connection) -> None:
            connection.execute(
                """
                UPDATE governance_decisions
                SET project_scope_id = ?
                WHERE task_id = ?
                """,
                (
                    harness.c3.c2.c1.i2.other_project_scope_id,
                    harness.task_id,
                ),
            )

    else:
        raise ValueError(f"unsupported evidence binding corruption: {corruption}")

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        triggers,
        corrupt,
    )


def corrupt_memory_payload(
    harness: I3DHarness,
    *,
    memory_kind: str,
    record_id: str,
) -> None:
    table, trigger, column = {
        "construct_memory": (
            "construct_doctrines",
            "construct_doctrines_immutable",
            "doctrine_statement",
        ),
        "approved_lesson": (
            "approved_lessons",
            "approved_lessons_immutable",
            "lesson_statement",
        ),
    }[memory_kind]
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (trigger,),
        lambda connection: connection.execute(
            f"UPDATE {table} SET {column} = {column} || ' corrupted' "  # noqa: S608
            "WHERE record_id = ?",
            (record_id,),
        ),
    )


def retrieval_row_counts(harness: I3DHarness) -> dict[str, int]:
    tables = (
        "retrieval_requests",
        "retrieval_manifests",
        "retrieval_manifest_entries",
        "context_packages",
        "ordered_context_manifest_entries",
        "context_contamination_findings",
        "context_recovery_relationships",
    )
    return SqlProbe(harness.config).read(
        lambda connection: {
            table: connection.execute(
                f"SELECT count(*) FROM {table}"  # noqa: S608
            ).fetchone()[0]
            for table in tables
        }
    )


def expected_authoritative_sections(result) -> tuple[dict, dict]:
    projection = parse_json(
        result.retrieval_manifest.task_memory_projection_json
    )
    authoritative_i2 = projection["authoritative_i2"]
    active_uncertainties = tuple(projection["uncertainties"]["active"])
    return (
        build_authoritative_task_section(
            authoritative_i2,
            active_uncertainties,
        ),
        build_authoritative_authority_section(authoritative_i2),
    )


def corrupt_authoritative_section(
    harness: I3DHarness,
    result,
    *,
    section: str,
    recompute_local_hashes: bool,
) -> None:
    sections = parse_json(result.context_package.sections_json)
    if section == "task":
        sections["task"]["objective"] += " Raw SQL semantic corruption."
    else:
        sections["authority"]["governance_decision"]["outcome"] = (
            "raw_sql_corruption"
        )
    entry = next(
        ordered
        for ordered in result.context_package.ordered_entries
        if ordered.section == section
    )
    changed_json = canonical_json_text(sections[section])
    if not recompute_local_hashes:
        SqlProbe(harness.config).corrupt_after_dropping_triggers(
            ("ordered_context_entries_immutable",),
            lambda connection: connection.execute(
                """
                UPDATE ordered_context_manifest_entries
                SET entry_canonical_json = ?
                WHERE ordered_entry_id = ?
                """,
                (changed_json, entry.ordered_entry_id),
            ),
        )
        return

    changed_hash = sha256_canonical_json(sections[section])
    changed_entry = replace(
        entry,
        source_content_hash=changed_hash,
        entry_json=changed_json,
    )
    changed_entries = tuple(
        changed_entry
        if ordered.ordered_entry_id == entry.ordered_entry_id
        else ordered
        for ordered in result.context_package.ordered_entries
    )
    changed_package = replace(
        result.context_package,
        authoritative_task_hash=(
            changed_hash
            if section == "task"
            else result.context_package.authoritative_task_hash
        ),
        authoritative_authority_hash=(
            changed_hash
            if section == "authority"
            else result.context_package.authoritative_authority_hash
        ),
        sections_json=canonical_json_text(sections),
        ordered_entries=changed_entries,
    )

    def corrupt(connection) -> None:
        connection.execute(
            """
            UPDATE ordered_context_manifest_entries
            SET source_content_hash = ?,
                entry_canonical_json = ?,
                entry_canonical_hash = ?,
                canonical_json = ?,
                content_hash = ?
            WHERE ordered_entry_id = ?
            """,
            (
                changed_entry.source_content_hash,
                changed_entry.entry_json,
                changed_entry.entry_canonical_hash,
                changed_entry.canonical_json,
                changed_entry.content_hash,
                changed_entry.ordered_entry_id,
            ),
        )
        connection.execute(
            """
            UPDATE context_packages
            SET authoritative_task_hash = ?,
                authoritative_authority_hash = ?,
                sections_json = ?,
                canonical_json = ?,
                content_hash = ?
            WHERE context_package_id = ?
            """,
            (
                changed_package.authoritative_task_hash,
                changed_package.authoritative_authority_hash,
                changed_package.sections_json,
                changed_package.canonical_json,
                changed_package.content_hash,
                changed_package.context_package_id,
            ),
        )

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (
            "ordered_context_entries_immutable",
            "context_packages_immutable",
        ),
        corrupt,
    )


def test_valid_context_ready_task_persists_exact_auditable_package(
    harness: I3DHarness,
) -> None:
    projection = None
    item = ordinary_evidence_item(harness, number=1_620_000)
    finalization_id = finalize_items(
        harness,
        (item,),
        finalization_number=1_620_001,
    )
    request = request_for(
        harness,
        finalization_id=finalization_id,
        number=1_620_002,
    )
    projection = harness.persistence.session_task_memory.reconstruct_task_memory(
        harness.task_id,
        mode="active",
        evaluated_at=NOW,
    )

    service = retrieval_service(harness, identifier_start=1_621_000)
    result = service.assemble(request)
    sections = parse_json(result.context_package.sections_json)
    expected_task, expected_authority = expected_authoritative_sections(result)
    authoritative_entries = {
        entry.section: entry
        for entry in result.context_package.ordered_entries
        if entry.section in {"task", "authority"}
    }

    assert result.accepted
    assert result.bridge_context_ready
    assert result.rejection_reasons == ()
    assert result.context_package.status == "accepted"
    assert result.context_package.contamination_status == "clean"
    assert result.retrieval_manifest.status == "accepted"
    assert result.retrieval_manifest.request_hash == request.content_hash
    assert (
        result.retrieval_manifest.task_memory_projection_hash
        == projection["content_hash"]
    )
    assert (
        result.retrieval_manifest.finalization_hash
        == projection["value"]["context"]["finalization"]["content_hash"]
    )
    assert len(result.retrieval_manifest.entries) == 1
    assert result.retrieval_manifest.entries[0].disposition == "included"
    assert result.retrieval_manifest.entries[0].final_rank == 0
    evidence_entry = next(
        entry
        for entry in result.context_package.ordered_entries
        if entry.section == "evidence"
    )
    assert (
        result.retrieval_manifest.entries[0].materialized_content_hash
        == evidence_entry.entry_canonical_hash
    )
    assert (
        result.retrieval_manifest.task_memory_projection_json
        == projection["canonical_json"]
    )
    assert sections["task"]["task_id"] == harness.task_id
    assert sections["task"] == expected_task
    assert sections["authority"] == expected_authority
    assert result.context_package.authoritative_task_hash == (
        sha256_canonical_json(expected_task)
    )
    assert result.context_package.authoritative_authority_hash == (
        sha256_canonical_json(expected_authority)
    )
    assert authoritative_entries["task"].entry_json == canonical_json_text(
        expected_task
    )
    assert authoritative_entries["task"].entry_canonical_hash == (
        result.context_package.authoritative_task_hash
    )
    assert authoritative_entries["task"].source_content_hash == (
        result.context_package.authoritative_task_hash
    )
    assert authoritative_entries["task"].retrieval_manifest_entry_id is None
    assert authoritative_entries["authority"].entry_json == (
        canonical_json_text(expected_authority)
    )
    assert authoritative_entries["authority"].entry_canonical_hash == (
        result.context_package.authoritative_authority_hash
    )
    assert authoritative_entries["authority"].source_content_hash == (
        result.context_package.authoritative_authority_hash
    )
    assert (
        authoritative_entries["authority"].retrieval_manifest_entry_id
        is None
    )
    assert sections["authority"]["authority_classification"] == (
        "authoritative system decision"
    )
    assert sections["authority"]["context_classification"] == (
        "context supplied to a future model"
    )
    assert sections["evidence"][0]["classification"] == {
        "authority": (
            "evidence is not authority unless separately represented by I2"
        ),
        "memory": "evidence is not memory",
    }
    assert sections["memory"] == []
    assert [
        (entry.section, entry.section_order, entry.entry_order)
        for entry in result.context_package.ordered_entries
    ] == [
        ("task", 0, 0),
        ("authority", 1, 0),
        ("evidence", 3, 0),
    ]
    assert tuple(
        section
        for section in CONTEXT_SECTIONS
        if any(
            entry.section == section
            for entry in result.context_package.ordered_entries
        )
    ) == ("task", "authority", "evidence")
    assert result.content_hash
    assert service.reconstruct_retrieval_manifest(
        result.retrieval_manifest.retrieval_manifest_id
    )["content_hash"] == result.retrieval_manifest.content_hash
    assert service.reconstruct_context_package(
        result.context_package.context_package_id
    )["content_hash"] == result.context_package.content_hash
    assert ContextIntegrityInspector(service._kernel).inspect().ok
    assert harness.persistence.integrity.inspect().ok


def test_identical_canonical_inputs_produce_identical_order_and_hashes(
    tmp_path: Path,
) -> None:
    results = []
    for folder in ("one", "two"):
        harness = build_i4a_harness(tmp_path / folder, base=1_630_000)
        _, _, result = basic_attempt(
            harness,
            item_number=1_631_000,
            finalization_number=1_631_001,
            request_number=1_631_002,
            identifier_start=1_632_000,
        )
        results.append(result)

    first, second = results
    assert first.retrieval_manifest.canonical_json == (
        second.retrieval_manifest.canonical_json
    )
    assert first.retrieval_manifest.content_hash == (
        second.retrieval_manifest.content_hash
    )
    assert first.context_package.canonical_json == (
        second.context_package.canonical_json
    )
    assert first.context_package.content_hash == second.context_package.content_hash
    assert first.content_hash == second.content_hash


def test_reopen_and_separate_process_reconstruct_identical_package(
    harness: I3DHarness,
) -> None:
    service, _, result = basic_attempt(harness)
    package_id = result.context_package.context_package_id

    reopened = PersistenceService.initialize(harness.config)
    reconstruction = reopened.retrieval_context.reconstruct_context_package(
        package_id
    )
    assert reconstruction["canonical_json"] == result.context_package.canonical_json
    assert reconstruction["content_hash"] == result.context_package.content_hash

    code = (
        "import json,sys;"
        "from pathlib import Path;"
        "from batch87_apprentice.persistence import DatabaseConfig,PersistenceService;"
        "service=PersistenceService.initialize(DatabaseConfig(Path(sys.argv[1])));"
        "value=service.retrieval_context.reconstruct_context_package(sys.argv[2]);"
        "print(json.dumps({'hash':value['content_hash'],"
        "'canonical':value['canonical_json']},sort_keys=True))"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(Path.cwd() / "src"), str(Path.cwd())]
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(harness.config.path),
            package_id,
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    separate = json.loads(completed.stdout)
    assert separate["hash"] == result.context_package.content_hash
    assert separate["canonical"] == result.context_package.canonical_json
    assert service.reconstruct_context_package(package_id) == reconstruction


def test_current_readiness_is_deterministic_and_read_only_while_active(
    harness: I3DHarness,
) -> None:
    service, _, result = basic_attempt(harness)
    package_id = result.context_package.context_package_id
    before = retrieval_row_counts(harness)

    first = service.assess_context_readiness(package_id, NOW)
    second = service.assess_context_readiness(package_id, NOW)

    assert first == second
    assert first["current_bridge_context_ready"]
    assert first["current_findings"] == []
    assert len(first["decision_hash"]) == 64
    assert retrieval_row_counts(harness) == before


@pytest.mark.parametrize(
    "terminal_state",
    ("task_completed", "session_closed"),
)
def test_historical_reconstruction_survives_normal_terminal_lifecycle(
    harness: I3DHarness,
    terminal_state: str,
) -> None:
    service, _, result = basic_attempt(harness)
    package_id = result.context_package.context_package_id
    expected_task, expected_authority = expected_authoritative_sections(result)
    historical_before = service.reconstruct_context_package(package_id)
    manifest_before = service.reconstruct_retrieval_manifest(
        result.retrieval_manifest.retrieval_manifest_id
    )
    row_counts = retrieval_row_counts(harness)
    terminal_runtime = GovernedTaskRuntime(
        harness.config,
        runtime_instance_id=harness.c3.c2.c1.i2.runtime_id,
        clock=lambda: LATER,
        identifier_factory=IdentifierSequence(1_638_000),
    )
    terminal_runtime.transition_task(
        harness.task_id,
        to_status="completed",
        reason_code="i4a_historical_package_completed",
    )
    if terminal_state == "session_closed":
        terminal_runtime.transition_session(
            harness.session_id,
            to_status="closed",
            reason_code="i4a_historical_package_session_closed",
        )

    historical_after = service.reconstruct_context_package(package_id)
    manifest_after = service.reconstruct_retrieval_manifest(
        result.retrieval_manifest.retrieval_manifest_id
    )
    readiness = service.assess_context_readiness(package_id, LATER)
    readiness_repeat = service.assess_context_readiness(package_id, LATER)
    reason_codes = {
        finding["reason_code"]
        for finding in readiness["current_findings"]
    }

    assert historical_after == historical_before
    assert manifest_after == manifest_before
    assert historical_after["historical_integrity_verified"]
    assert historical_after["historical_status"] == "accepted"
    assert historical_after["value"]["sections"]["task"] == expected_task
    assert historical_after["value"]["sections"]["authority"] == (
        expected_authority
    )
    assert not readiness["current_bridge_context_ready"]
    assert "task_not_active" in reason_codes
    if terminal_state == "session_closed":
        assert "session_not_open" in reason_codes
    else:
        assert "session_not_open" not in reason_codes
    assert readiness_repeat == readiness
    assert retrieval_row_counts(harness) == row_counts

    reopened = PersistenceService.initialize(harness.config).retrieval_context
    assert reopened.reconstruct_context_package(package_id) == historical_before
    assert reopened.assess_context_readiness(package_id, LATER) == readiness
    assert ContextIntegrityInspector(service._kernel).inspect().ok
    assert harness.persistence.integrity.inspect().ok

    if terminal_state == "session_closed":
        code = (
            "import json,sys;"
            "from pathlib import Path;"
            "from batch87_apprentice.persistence import "
            "DatabaseConfig,PersistenceService;"
            "service=PersistenceService.initialize("
            "DatabaseConfig(Path(sys.argv[1]))).retrieval_context;"
            "historical=service.reconstruct_context_package(sys.argv[2]);"
            "readiness=service.assess_context_readiness(sys.argv[2],sys.argv[3]);"
            "print(json.dumps({'historical':historical,'readiness':readiness},"
            "sort_keys=True))"
        )
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(Path.cwd() / "src"), str(Path.cwd())]
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(harness.config.path),
                package_id,
                LATER,
            ],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        separate = json.loads(completed.stdout)
        assert separate["historical"] == historical_before
        assert separate["readiness"] == readiness


@pytest.mark.parametrize("mismatch", ("task", "project"))
def test_evidence_materialization_requires_exact_task_and_project(
    harness: I3DHarness,
    mismatch: str,
) -> None:
    task_id = harness.task_id if mismatch != "task" else uid(1_639_000)
    project_scope_id = (
        harness.project_scope_id
        if mismatch != "project"
        else harness.c3.c2.c1.i2.other_project_scope_id
    )

    status, reasons, materialized_json = SqlProbe(harness.config).read(
        lambda connection: _SafeSourceMaterializer().materialize(
            connection,
            source_kind="evidence",
            source_id=harness.task_evidence_id,
            context_kind="evidence",
            task_id=task_id,
            project_scope_id=project_scope_id,
            mode="active",
            evaluated_at=NOW,
        )
    )
    snapshot = SqlProbe(harness.config).read(
        lambda connection: ContextRetrievalService._source_snapshot_by_identity(
            connection,
            source_kind="evidence",
            source_id=harness.task_evidence_id,
            task_id=task_id,
            project_scope_id=project_scope_id,
        )
    )

    assert status == "invalid"
    assert reasons == ("source_not_task_bound",)
    assert materialized_json is None
    assert snapshot is not None
    assert snapshot["task_bound"] is False


@pytest.mark.parametrize(
    "corruption",
    (
        "required_mismatch",
        "resolved_mismatch",
        "unavailable",
        "decision_project",
    ),
)
def test_exact_evidence_binding_loss_blocks_initial_i4a_attempt(
    harness: I3DHarness,
    corruption: str,
) -> None:
    item = ordinary_evidence_item(harness, number=1_639_100)
    finalization_id = finalize_items(
        harness,
        (item,),
        finalization_number=1_639_101,
    )
    corrupt_task_evidence_binding(
        harness,
        corruption,
        base=1_639_200,
    )

    eligibility = (
        harness.persistence.session_task_memory.assess_context_item(
            harness.task_id,
            item.context_item_id,
            mode="active",
            evaluated_at=NOW,
        )
    )
    status, reasons, materialized_json = SqlProbe(harness.config).read(
        lambda connection: _SafeSourceMaterializer().materialize(
            connection,
            source_kind="evidence",
            source_id=harness.task_evidence_id,
            context_kind="evidence",
            task_id=harness.task_id,
            project_scope_id=harness.project_scope_id,
            mode="active",
            evaluated_at=NOW,
        )
    )

    assert not eligibility.eligible
    assert "source_not_task_bound" in eligibility.reason_codes
    assert status == "invalid"
    assert reasons == ("source_not_task_bound",)
    assert materialized_json is None
    with pytest.raises(IntegrityInspectionError):
        retrieval_service(harness).assemble(
            request_for(
                harness,
                finalization_id=finalization_id,
                number=1_639_102,
            )
        )
    assert retrieval_row_counts(harness) == {
        "retrieval_requests": 0,
        "retrieval_manifests": 0,
        "retrieval_manifest_entries": 0,
        "context_packages": 0,
        "ordered_context_manifest_entries": 0,
        "context_contamination_findings": 0,
        "context_recovery_relationships": 0,
    }


@pytest.mark.parametrize(
    "corruption",
    (
        "required_mismatch",
        "resolved_mismatch",
        "unavailable",
        "decision_project",
    ),
)
def test_persisted_evidence_binding_loss_is_detected_by_every_i4a_consumer(
    harness: I3DHarness,
    corruption: str,
) -> None:
    service, _, result = basic_attempt(harness)
    manifest_entry = result.retrieval_manifest.entries[0]
    corrupt_task_evidence_binding(
        harness,
        corruption,
        base=1_639_300,
    )

    snapshot = SqlProbe(harness.config).read(
        lambda connection: dict(
            ContextRetrievalService._source_snapshot_by_identity(
                connection,
                source_kind=manifest_entry.source_kind,
                source_id=manifest_entry.source_id,
                task_id=harness.task_id,
                project_scope_id=harness.project_scope_id,
            )
            or {}
        )
    )
    status, reasons, materialized_json = SqlProbe(harness.config).read(
        lambda connection: _SafeSourceMaterializer().materialize(
            connection,
            source_kind=manifest_entry.source_kind,
            source_id=manifest_entry.source_id,
            context_kind="evidence",
            task_id=harness.task_id,
            project_scope_id=harness.project_scope_id,
            mode="active",
            evaluated_at=NOW,
        )
    )
    contamination = service._contamination.inspect(
        sections_json=result.context_package.sections_json,
        ordered_entries=result.context_package.ordered_entries,
        authoritative_task_hash=(
            result.context_package.authoritative_task_hash
        ),
        authoritative_authority_hash=(
            result.context_package.authoritative_authority_hash
        ),
        task_memory_projection_json=(
            result.retrieval_manifest.task_memory_projection_json
        ),
        manifest_entries=result.retrieval_manifest.entries,
        independent_materializations=independent_materializations(result),
        source_snapshots={
            (manifest_entry.source_kind, manifest_entry.source_id): snapshot
        },
        task_id=harness.task_id,
        project_scope_id=harness.project_scope_id,
        identifier_factory=IdentifierSequence(1_639_400),
    )

    assert snapshot["task_bound"] is False
    assert status == "invalid"
    assert reasons == ("source_not_task_bound",)
    assert materialized_json is None
    assert "source_not_task_bound" in {
        finding.reason_code for finding in contamination
    }
    with pytest.raises(IntegrityInspectionError):
        service.reconstruct_retrieval_manifest(
            result.retrieval_manifest.retrieval_manifest_id
        )
    with pytest.raises(IntegrityInspectionError):
        service.reconstruct_context_package(
            result.context_package.context_package_id
        )
    report = ContextIntegrityInspector(service._kernel).inspect()
    assert not report.ok
    assert "I4A-CONTEXT-RECONSTRUCTION" in {
        finding.code for finding in report.findings
    }
    assert not harness.persistence.integrity.inspect().ok


def test_migration_guard_rejects_included_evidence_without_exact_binding(
    harness: I3DHarness,
) -> None:
    service, _, result = basic_attempt(harness)
    corrupt_task_evidence_binding(
        harness,
        "required_mismatch",
        base=1_639_500,
    )
    request = replace(
        result.retrieval_request,
        retrieval_request_id=uid(1_639_501),
    )
    manifest_id = uid(1_639_502)
    entry = replace(
        result.retrieval_manifest.entries[0],
        entry_id=uid(1_639_503),
    )
    manifest = replace(
        result.retrieval_manifest,
        retrieval_manifest_id=manifest_id,
        retrieval_request_id=request.retrieval_request_id,
        request_hash=request.content_hash,
        entries=(entry,),
    )

    def persist(connection) -> None:
        service._persist_request(connection, request)
        service._persist_manifest(connection, manifest)

    with pytest.raises(ConflictError, match="integrity constraint"):
        service._kernel.write(persist)

    assert SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT count(*) FROM retrieval_requests
            WHERE retrieval_request_id = ?
            """,
            (request.retrieval_request_id,),
        ).fetchone()[0]
    ) == 0


@pytest.mark.parametrize(
    "mismatch",
    ["task", "session", "project", "finalization"],
)
def test_request_binding_mismatch_fails_closed(
    harness: I3DHarness,
    mismatch: str,
) -> None:
    finalization_id = finalize_items(
        harness,
        (ordinary_evidence_item(harness, number=1_640_000),),
        finalization_number=1_640_001,
    )
    overrides = {
        "task_id": uid(1_649_000) if mismatch == "task" else None,
        "session_id": uid(1_649_000) if mismatch == "session" else None,
        "project_scope_id": (
            uid(1_649_000) if mismatch == "project" else None
        ),
    }
    if mismatch == "finalization":
        finalization_id = uid(1_649_001)
    request = request_for(
        harness,
        finalization_id=finalization_id,
        number=1_640_002,
        **overrides,
    )

    with pytest.raises((ValidationError, NotFoundError)):
        retrieval_service(harness).assemble(request)

    assert SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            "SELECT count(*) FROM retrieval_requests"
        ).fetchone()[0]
    ) == 0


def test_non_active_task_fails_before_persistence(harness: I3DHarness) -> None:
    finalization_id = finalize_items(
        harness,
        (ordinary_evidence_item(harness, number=1_650_000),),
        finalization_number=1_650_001,
    )
    harness.runtime.transition_task(
        harness.task_id,
        to_status="completed",
        reason_code="i4a_fixture_completed",
    )

    with pytest.raises((ValidationError, IntegrityInspectionError)):
        retrieval_service(harness).assemble(
            request_for(
                harness,
                finalization_id=finalization_id,
                number=1_650_002,
            )
        )


def test_closed_session_fails_before_persistence(harness: I3DHarness) -> None:
    finalization_id = finalize_items(
        harness,
        (ordinary_evidence_item(harness, number=1_651_000),),
        finalization_number=1_651_001,
    )
    harness.runtime.transition_session(
        harness.session_id,
        to_status="closed",
        reason_code="i4a_fixture_closed",
    )

    with pytest.raises((ValidationError, IntegrityInspectionError)):
        retrieval_service(harness).assemble(
            request_for(
                harness,
                finalization_id=finalization_id,
                number=1_651_002,
            )
        )


def test_blocking_uncertainty_fails_before_persistence(
    harness: I3DHarness,
) -> None:
    finalization_id = finalize_items(
        harness,
        (ordinary_evidence_item(harness, number=1_652_000),),
        finalization_number=1_652_001,
    )
    create_uncertainty(harness, base=1_652_100, impact="blocking")

    with pytest.raises(ValidationError, match="blocking uncertainty"):
        retrieval_service(harness).assemble(
            request_for(
                harness,
                finalization_id=finalization_id,
                number=1_652_002,
            )
        )


@pytest.mark.parametrize(
    ("trigger", "table", "identifier_column", "corrupt_column"),
    [
        ("tasks_core_immutable", "tasks", "task_id", "contract_hash"),
        (
            "task_context_items_immutable",
            "task_context_items",
            "context_item_id",
            "canonical_json",
        ),
    ],
)
def test_authoritative_i2_or_i3d_integrity_failure_blocks_retrieval(
    harness: I3DHarness,
    trigger: str,
    table: str,
    identifier_column: str,
    corrupt_column: str,
) -> None:
    item = ordinary_evidence_item(harness, number=1_653_000)
    finalization_id = finalize_items(
        harness,
        (item,),
        finalization_number=1_653_001,
    )
    identifier = (
        harness.task_id if table == "tasks" else item.context_item_id
    )
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (trigger,),
        lambda connection: connection.execute(
            f"UPDATE {table} SET {corrupt_column} = ? "  # noqa: S608
            f"WHERE {identifier_column} = ?",  # noqa: S608
            (
                "f" * 64 if corrupt_column == "contract_hash" else "{}",
                identifier,
            ),
        ),
    )

    with pytest.raises(IntegrityInspectionError):
        retrieval_service(harness).assemble(
            request_for(
                harness,
                finalization_id=finalization_id,
                number=1_653_002,
            )
        )


def test_conflicting_request_identity_reuse_fails(harness: I3DHarness) -> None:
    service, request, result = basic_attempt(harness)
    assert result.accepted
    conflicting = RetrievalRequest(
        retrieval_request_id=request.retrieval_request_id,
        contract_version=request.contract_version,
        task_id=request.task_id,
        session_id=request.session_id,
        project_scope_id=request.project_scope_id,
        task_context_finalization_id=request.task_context_finalization_id,
        purpose="Different immutable retrieval purpose.",
        requested_sections=request.requested_sections,
        requested_at=request.requested_at,
        requested_by_principal=request.requested_by_principal,
        ranking_strategy=request.ranking_strategy,
        provenance_json=request.provenance_json,
    )

    with pytest.raises(ConflictError, match="conflicts"):
        service.assemble(conflicting)


class RecordingRanker:
    strategy = "deterministic_fallback_v1"

    def __init__(self) -> None:
        self.received = ()

    def rank(self, request, eligible_candidates):
        self.received = eligible_candidates
        return DeterministicFallbackRanker().rank(
            request,
            eligible_candidates,
        )


def test_eligibility_and_materialization_complete_before_ranking(
    harness: I3DHarness,
) -> None:
    construct_id = create_active_construct_memory(
        harness,
        base=1_660_000,
    )
    items = (
        ordinary_evidence_item(
            harness,
            number=1_660_010,
            injection_order=0,
            required=True,
        ),
        memory_context_item(
            harness,
            number=1_660_011,
            record_id=construct_id,
            context_kind="construct_memory",
            injection_order=1,
            required=False,
        ),
    )
    finalization_id = finalize_items(
        harness,
        items,
        finalization_number=1_660_012,
    )
    MemoryKernel(harness.config).transition_lifecycle(
        construct_id,
        transition_id=uid(1_660_014),
        to_state="revoked",
        reason_code="construct_revoked_before_retrieval",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    ranker = RecordingRanker()
    service = retrieval_service(
        harness,
        identifier_start=1_661_000,
        ranker=ranker,
    )

    result = service.assemble(
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_660_013,
        )
    )

    assert result.accepted
    assert len(ranker.received) == 1
    assert all(candidate.includable for candidate in ranker.received)
    excluded = result.retrieval_manifest.entries[1]
    assert excluded.disposition == "excluded"
    assert excluded.final_rank is None
    assert "source_not_active" in excluded.eligibility_reasons
    assert "source_revoked" in excluded.eligibility_reasons
    assert excluded.materialization_status == "not_attempted"
    assert len(result.retrieval_manifest.entries) == len(items)


def test_noninline_and_model_output_evidence_fail_safe_materialization(
    harness: I3DHarness,
) -> None:
    noninline = create_noninline_evidence(harness, number=1_670_000)
    model_output = create_model_output_evidence(
        harness,
        number=1_670_001,
    )
    materializer = _SafeSourceMaterializer()

    noninline_result, model_result = SqlProbe(harness.config).read(
        lambda connection: (
            materializer.materialize(
                connection,
                source_kind="evidence",
                source_id=noninline.evidence_id,
                context_kind="evidence",
                task_id=harness.task_id,
                project_scope_id=harness.project_scope_id,
            ),
            materializer.materialize(
                connection,
                source_kind="evidence",
                source_id=model_output.evidence_id,
                context_kind="evidence",
                task_id=harness.task_id,
                project_scope_id=harness.project_scope_id,
            ),
        )
    )

    assert noninline_result == (
        "unavailable",
        ("content_unavailable",),
        None,
    )
    assert model_result == (
        "prohibited",
        ("model_output_prohibited",),
        None,
    )


class ProhibitingMaterializer:
    def materialize(self, *args, **kwargs):
        return "prohibited", ("test_source_prohibited",), None


@pytest.mark.parametrize("required", [False, True])
def test_materialization_exclusion_is_preserved_and_requiredness_controls_status(
    harness: I3DHarness,
    required: bool,
) -> None:
    item = ordinary_evidence_item(
        harness,
        number=1_675_000,
        required=required,
    )
    finalization_id = finalize_items(
        harness,
        (item,),
        finalization_number=1_675_001,
    )
    service = retrieval_service(
        harness,
        identifier_start=1_676_000,
    )
    service._materializer = ProhibitingMaterializer()

    result = service.assemble(
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_675_002,
        )
    )

    assert result.accepted is (not required)
    assert result.retrieval_manifest.entries[0].disposition == "excluded"
    assert result.retrieval_manifest.entries[0].materialization_reasons == (
        "test_source_prohibited",
    )
    assert parse_json(result.context_package.sections_json)["evidence"] == []
    if required:
        assert result.context_package.status == "rejected_required_source"
        assert not result.bridge_context_ready


def test_governance_evidence_construct_and_approved_lesson_materialize_safely(
    harness: I3DHarness,
) -> None:
    construct_id = create_active_construct_memory(
        harness,
        base=1_680_000,
    )
    lesson_id = create_active_approved_lesson(
        harness,
        base=1_690_000,
    )
    rule_source = active_rule_source(harness)
    items = (
        context_item(
            harness,
            base=1_699_000,
            context_kind="policy",
            source=rule_source,
            injection_order=0,
            required=True,
        ),
        ordinary_evidence_item(
            harness,
            number=1_699_001,
            injection_order=1,
            required=True,
        ),
        memory_context_item(
            harness,
            number=1_699_002,
            record_id=construct_id,
            context_kind="construct_memory",
            injection_order=2,
            required=False,
        ),
        memory_context_item(
            harness,
            number=1_699_003,
            record_id=lesson_id,
            context_kind="approved_lesson",
            injection_order=3,
            required=False,
        ),
    )
    finalization_id = finalize_items(
        harness,
        items,
        finalization_number=1_699_004,
    )

    result = retrieval_service(
        harness,
        identifier_start=1_700_000,
    ).assemble(
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_699_005,
        )
    )
    sections = parse_json(result.context_package.sections_json)

    assert result.accepted
    assert len(sections["policy"]) == 1
    assert sections["policy"][0]["task_decision_relationships"]
    assert len(sections["evidence"]) == 1
    assert len(sections["memory"]) == 2
    assert {
        entry["classification"]["context_role"]
        for entry in sections["memory"]
    } == {"contextual memory", "approved contextual lesson"}
    assert all(
        entry["classification"]["authority"] == "not authority"
        for entry in sections["memory"]
    )
    serialized = result.context_package.sections_json
    for prohibited in (
        "storage_location",
        "retrieval_policy",
        "deletion_policy",
        "database_connection",
        "repository_handle",
        "credential_handle",
        "raw_sql_handle",
    ):
        assert prohibited not in serialized


@pytest.mark.parametrize(
    "memory_kind",
    ("construct_memory", "approved_lesson"),
)
def test_selected_memory_payload_corruption_blocks_initial_materialization(
    harness: I3DHarness,
    memory_kind: str,
) -> None:
    record_id = (
        create_active_construct_memory(harness, base=1_705_000)
        if memory_kind == "construct_memory"
        else create_active_approved_lesson(harness, base=1_705_000)
    )
    item = memory_context_item(
        harness,
        number=1_707_000,
        record_id=record_id,
        context_kind=memory_kind,
        injection_order=0,
        required=True,
    )
    finalization_id = finalize_items(
        harness,
        (item,),
        finalization_number=1_707_001,
    )
    corrupt_memory_payload(
        harness,
        memory_kind=memory_kind,
        record_id=record_id,
    )

    result = retrieval_service(
        harness,
        identifier_start=1_707_100,
    ).assemble(
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_707_002,
        )
    )
    entry = result.retrieval_manifest.entries[0]

    assert not result.accepted
    assert result.context_package.status == "rejected_required_source"
    assert entry.disposition == "excluded"
    assert entry.materialization_status == "invalid"
    assert entry.materialization_reasons == ("source_integrity_invalid",)
    assert entry.materialized_content_hash is None
    assert parse_json(result.context_package.sections_json)["memory"] == []


@pytest.mark.parametrize(
    "memory_kind",
    ("construct_memory", "approved_lesson"),
)
def test_selected_memory_payload_corruption_is_detected_after_persistence(
    harness: I3DHarness,
    memory_kind: str,
) -> None:
    record_id = (
        create_active_construct_memory(harness, base=1_708_000)
        if memory_kind == "construct_memory"
        else create_active_approved_lesson(harness, base=1_708_000)
    )
    finalization_id = finalize_items(
        harness,
        (
            memory_context_item(
                harness,
                number=1_709_000,
                record_id=record_id,
                context_kind=memory_kind,
                injection_order=0,
                required=True,
            ),
        ),
        finalization_number=1_709_001,
    )
    service = retrieval_service(
        harness,
        identifier_start=1_709_100,
    )
    result = service.assemble(
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_709_002,
        )
    )
    assert result.accepted
    corrupt_memory_payload(
        harness,
        memory_kind=memory_kind,
        record_id=record_id,
    )

    with pytest.raises(IntegrityInspectionError):
        service.reconstruct_context_package(
            result.context_package.context_package_id
        )
    readiness = service.assess_context_readiness(
        result.context_package.context_package_id,
        NOW,
    )
    assert not readiness["current_bridge_context_ready"]
    assert "source_integrity_invalid" in {
        finding["reason_code"]
        for finding in readiness["current_findings"]
    }
    report = ContextIntegrityInspector(service._kernel).inspect()
    assert not report.ok
    assert "I4A-SELECTED-SOURCE-INTEGRITY" in {
        finding.code for finding in report.findings
    }
    assert not harness.persistence.integrity.inspect().ok


@pytest.mark.parametrize(
    "memory_kind",
    ("construct_memory", "approved_lesson"),
)
def test_later_memory_revocation_changes_readiness_not_historical_integrity(
    harness: I3DHarness,
    memory_kind: str,
) -> None:
    record_id = (
        create_active_construct_memory(harness, base=1_710_000)
        if memory_kind == "construct_memory"
        else create_active_approved_lesson(harness, base=1_710_000)
    )
    finalization_id = finalize_items(
        harness,
        (
            memory_context_item(
                harness,
                number=1_711_000,
                record_id=record_id,
                context_kind=memory_kind,
                injection_order=0,
                required=True,
            ),
        ),
        finalization_number=1_711_001,
    )
    service = retrieval_service(
        harness,
        identifier_start=1_711_100,
    )
    result = service.assemble(
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_711_002,
        )
    )
    historical_before = service.reconstruct_context_package(
        result.context_package.context_package_id
    )
    MemoryKernel(harness.config).transition_lifecycle(
        record_id,
        transition_id=uid(1_711_003),
        to_state="revoked",
        reason_code="i4a_source_revoked_after_context_assembly",
        changed_at=LATER,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )

    historical_after = service.reconstruct_context_package(
        result.context_package.context_package_id
    )
    readiness = service.assess_context_readiness(
        result.context_package.context_package_id,
        LATER,
    )

    assert historical_after == historical_before
    assert historical_after["historical_integrity_verified"]
    assert not readiness["current_bridge_context_ready"]
    assert "source_revoked" in {
        finding["reason_code"]
        for finding in readiness["current_findings"]
    }
    assert ContextIntegrityInspector(service._kernel).inspect().ok
    assert harness.persistence.integrity.inspect().ok


@pytest.mark.parametrize(
    "memory_kind",
    ("construct_memory", "approved_lesson"),
)
def test_unrelated_memory_payload_corruption_is_isolated(
    harness: I3DHarness,
    memory_kind: str,
) -> None:
    create_memory = (
        create_active_construct_memory
        if memory_kind == "construct_memory"
        else create_active_approved_lesson
    )
    selected_id = create_memory(harness, base=1_712_000)
    unrelated_id = create_memory(harness, base=1_722_000)
    corrupt_memory_payload(
        harness,
        memory_kind=memory_kind,
        record_id=unrelated_id,
    )
    finalization_id = finalize_items(
        harness,
        (
            memory_context_item(
                harness,
                number=1_726_000,
                record_id=selected_id,
                context_kind=memory_kind,
                injection_order=0,
                required=True,
            ),
        ),
        finalization_number=1_726_001,
    )
    service = retrieval_service(
        harness,
        identifier_start=1_726_100,
    )
    result = service.assemble(
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_726_002,
        )
    )

    assert result.accepted
    assert service.reconstruct_context_package(
        result.context_package.context_package_id
    )["historical_integrity_verified"]
    readiness = service.assess_context_readiness(
        result.context_package.context_package_id,
        NOW,
    )
    assert readiness["current_bridge_context_ready"]
    assert readiness["current_findings"] == []
    assert ContextIntegrityInspector(service._kernel).inspect().ok
    assert not harness.persistence.integrity.inspect().ok


def test_active_nonblocking_uncertainty_is_structured_in_task_section(
    harness: I3DHarness,
) -> None:
    create_uncertainty(harness, base=1_710_000, impact="medium")
    service, _, result = basic_attempt(
        harness,
        item_number=1_710_010,
        finalization_number=1_710_011,
        request_number=1_710_012,
        identifier_start=1_711_000,
    )

    uncertainties = parse_json(result.context_package.sections_json)[
        "task"
    ]["active_non_blocking_uncertainties"]
    assert len(uncertainties) == 1
    assert uncertainties[0]["impact"] == "medium"
    assert service.reconstruct_context_package(
        result.context_package.context_package_id
    )["integrity_verified"]


def test_structural_capability_detection_is_not_keyword_censorship(
    harness: I3DHarness,
) -> None:
    service, _, result = basic_attempt(harness)
    package = result.context_package
    sections = parse_json(package.sections_json)
    sections["task"]["objective"] = (
        "Discuss SQL, filesystem and network architecture as inert text."
    )
    clean = service._contamination.inspect(
        sections_json=canonical_json_text(sections),
        ordered_entries=package.ordered_entries,
        authoritative_task_hash=package.authoritative_task_hash,
        authoritative_authority_hash=package.authoritative_authority_hash,
        task_memory_projection_json=(
            result.retrieval_manifest.task_memory_projection_json
        ),
        manifest_entries=result.retrieval_manifest.entries,
        independent_materializations=independent_materializations(result),
        source_snapshots={},
        task_id=harness.task_id,
        project_scope_id=harness.project_scope_id,
        identifier_factory=IdentifierSequence(1_720_000),
    )
    assert {
        finding.reason_code for finding in clean
    } == {
        "authoritative_task_content_mismatch",
        "untracked_material",
        "source_missing",
    }

    sections["task"]["database_connection"] = {"opaque": "capability"}
    findings = service._contamination.inspect(
        sections_json=canonical_json_text(sections),
        ordered_entries=package.ordered_entries,
        authoritative_task_hash=package.authoritative_task_hash,
        authoritative_authority_hash=package.authoritative_authority_hash,
        task_memory_projection_json=(
            result.retrieval_manifest.task_memory_projection_json
        ),
        manifest_entries=result.retrieval_manifest.entries,
        independent_materializations=independent_materializations(result),
        source_snapshots={},
        task_id=harness.task_id,
        project_scope_id=harness.project_scope_id,
        identifier_factory=IdentifierSequence(1_720_100),
    )
    assert "executable_capability_exposed" in {
        finding.reason_code for finding in findings
    }


@pytest.mark.parametrize(
    ("snapshot_change", "expected_code"),
    [
        ({"evidence_kind": "controlled_prompt"}, "controlled_prompt"),
        ({"evidence_kind": "controlled_output"}, "controlled_output"),
        ({"evidence_kind": "model_output"}, "model_output_evidence"),
        (
            {"controlled_resilience": 1},
            "controlled_resilience_evidence",
        ),
        ({"content_hash": "f" * 64}, "source_hash_drift"),
    ],
)
def test_contamination_scanner_detects_evidence_classification_and_hash_drift(
    harness: I3DHarness,
    snapshot_change: dict[str, object],
    expected_code: str,
) -> None:
    service, _, result = basic_attempt(harness)
    manifest_entry = result.retrieval_manifest.entries[0]
    snapshot = SqlProbe(harness.config).read(
        lambda connection: dict(
            ContextRetrievalService._source_snapshot_by_identity(
                connection,
                source_kind=manifest_entry.source_kind,
                source_id=manifest_entry.source_id,
                task_id=harness.task_id,
                project_scope_id=harness.project_scope_id,
            )
            or {}
        )
    )
    snapshot.update(snapshot_change)

    findings = service._contamination.inspect(
        sections_json=result.context_package.sections_json,
        ordered_entries=result.context_package.ordered_entries,
        authoritative_task_hash=(
            result.context_package.authoritative_task_hash
        ),
        authoritative_authority_hash=(
            result.context_package.authoritative_authority_hash
        ),
        task_memory_projection_json=(
            result.retrieval_manifest.task_memory_projection_json
        ),
        manifest_entries=result.retrieval_manifest.entries,
        independent_materializations=independent_materializations(result),
        source_snapshots={
            (manifest_entry.source_kind, manifest_entry.source_id): snapshot
        },
        task_id=harness.task_id,
        project_scope_id=harness.project_scope_id,
        identifier_factory=IdentifierSequence(1_725_000),
    )

    assert expected_code in {
        finding.reason_code for finding in findings
    }


@pytest.mark.parametrize(
    ("snapshot_change", "expected_code"),
    [
        ({"lifecycle_state": "revoked"}, "source_revoked"),
        ({"lifecycle_state": "deleted"}, "source_deleted"),
        ({"integrity_status": "mismatch"}, "source_integrity_invalid"),
        ({"task_id": uid(1_726_000)}, "cross_task_source"),
        ({"project_scope_id": uid(1_726_001)}, "cross_project_source"),
        (
            {
                "record_family": "episodic_memory",
                "record_type": "lesson_candidate",
            },
            "lesson_candidate_as_approved",
        ),
    ],
)
def test_contamination_scanner_detects_invalid_memory_classification(
    harness: I3DHarness,
    snapshot_change: dict[str, object],
    expected_code: str,
) -> None:
    construct_id = create_active_construct_memory(
        harness,
        base=1_727_000,
    )
    finalization_id = finalize_items(
        harness,
        (
            memory_context_item(
                harness,
                number=1_727_020,
                record_id=construct_id,
                context_kind="construct_memory",
                injection_order=0,
                required=True,
            ),
        ),
        finalization_number=1_727_021,
    )
    service = retrieval_service(
        harness,
        identifier_start=1_727_100,
    )
    result = service.assemble(
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_727_022,
        )
    )
    manifest_entry = result.retrieval_manifest.entries[0]
    snapshot = SqlProbe(harness.config).read(
        lambda connection: dict(
            connection.execute(
                "SELECT * FROM records WHERE record_id = ?",
                (construct_id,),
            ).fetchone()
        )
    )
    snapshot.update(snapshot_change)

    findings = service._contamination.inspect(
        sections_json=result.context_package.sections_json,
        ordered_entries=result.context_package.ordered_entries,
        authoritative_task_hash=(
            result.context_package.authoritative_task_hash
        ),
        authoritative_authority_hash=(
            result.context_package.authoritative_authority_hash
        ),
        task_memory_projection_json=(
            result.retrieval_manifest.task_memory_projection_json
        ),
        manifest_entries=result.retrieval_manifest.entries,
        independent_materializations=independent_materializations(result),
        source_snapshots={
            (manifest_entry.source_kind, manifest_entry.source_id): snapshot
        },
        task_id=harness.task_id,
        project_scope_id=harness.project_scope_id,
        identifier_factory=IdentifierSequence(1_727_200),
    )

    assert expected_code in {
        finding.reason_code for finding in findings
    }


def test_benign_materialized_content_substitution_is_rejected_and_preserved(
    harness: I3DHarness,
) -> None:
    item = ordinary_evidence_item(harness, number=1_729_000)
    finalization_id = finalize_items(
        harness,
        (item,),
        finalization_number=1_729_001,
    )
    service = retrieval_service(
        harness,
        identifier_start=1_729_100,
        assembler=SubstituteMaterializedAssembler(),
    )
    result = service.assemble(
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_729_002,
        )
    )
    manifest_entry = result.retrieval_manifest.entries[0]
    ordered_entry = next(
        entry
        for entry in result.context_package.ordered_entries
        if entry.retrieval_manifest_entry_id == manifest_entry.entry_id
    )

    assert not result.accepted
    assert not result.bridge_context_ready
    assert result.context_package.status == "rejected_contamination"
    assert manifest_entry.source_id == ordered_entry.source_id
    assert (
        manifest_entry.source_content_hash
        == ordered_entry.source_content_hash
    )
    assert (
        manifest_entry.materialized_content_hash
        != ordered_entry.entry_canonical_hash
    )
    assert {
        finding.reason_code
        for finding in result.context_package.contamination_findings
    } == {"materialized_content_mismatch"}
    reconstruction = service.reconstruct_context_package(
        result.context_package.context_package_id
    )
    assert reconstruction["historical_integrity_verified"]
    report = ContextIntegrityInspector(service._kernel).inspect()
    matching = [
        finding
        for finding in report.findings
        if finding.code == "I4A-MATERIALIZED-CONTENT-MISMATCH"
    ]
    assert len(matching) == 1
    assert matching[0].severity == "warning"
    assert report.ok


def test_controlled_contamination_is_preserved_then_cleanly_recovered(
    harness: I3DHarness,
) -> None:
    payload, controlled = create_controlled_bundle(
        harness,
        base=1_730_000,
    )
    prompt = controlled[0]
    construct_id = create_active_construct_memory(
        harness,
        base=1_728_000,
    )
    items = (
        ordinary_evidence_item(
            harness,
            number=1_730_010,
            injection_order=0,
            required=True,
        ),
        memory_context_item(
            harness,
            number=1_730_011,
            record_id=construct_id,
            context_kind="construct_memory",
            injection_order=1,
            required=False,
        ),
    )
    finalization_id = finalize_items(
        harness,
        items,
        finalization_number=1_730_012,
    )
    MemoryKernel(harness.config).transition_lifecycle(
        construct_id,
        transition_id=uid(1_730_015),
        to_state="revoked",
        reason_code="construct_revoked_before_contamination_fixture",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    contaminated_service = retrieval_service(
        harness,
        identifier_start=1_731_000,
        assembler=InjectExcludedAssembler(
            (
                "evidence",
                prompt.evidence_id,
                prompt.content_hash or "",
                "evidence",
            )
        ),
    )
    rejected = contaminated_service.assemble(
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_730_013,
        )
    )

    assert not rejected.accepted
    assert not rejected.bridge_context_ready
    assert rejected.context_package.status == "rejected_contamination"
    codes = {
        finding.reason_code
        for finding in rejected.context_package.contamination_findings
    }
    assert {
        "controlled_prompt",
        "controlled_resilience_evidence",
        "untracked_material",
    }.issubset(codes)
    reconstructed_rejected = contaminated_service.reconstruct_context_package(
        rejected.context_package.context_package_id
    )
    assert (
        reconstructed_rejected["content_hash"]
        == rejected.context_package.content_hash
    )

    recovery_service = retrieval_service(
        harness,
        identifier_start=1_732_000,
    )
    recovered = recovery_service.recover(
        rejected.context_package.context_package_id,
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_730_014,
            provenance={
                "recovery_of": rejected.context_package.context_package_id
            },
        ),
    )
    relationship = SqlProbe(harness.config).read(
        lambda connection: dict(
            connection.execute(
                """
                SELECT * FROM context_recovery_relationships
                WHERE recovery_context_package_id = ?
                """,
                (recovered.context_package.context_package_id,),
            ).fetchone()
        )
    )
    exclusions = set(parse_json(relationship["excluded_source_ids_json"]))
    recovered_task, recovered_authority = expected_authoritative_sections(
        recovered
    )
    recovered_sections = parse_json(
        recovered.context_package.sections_json
    )
    recovered_readiness = recovery_service.assess_context_readiness(
        recovered.context_package.context_package_id,
        NOW,
    )

    assert recovered.accepted
    assert recovered.bridge_context_ready
    assert recovered_sections["task"] == recovered_task
    assert recovered_sections["authority"] == recovered_authority
    assert recovered.context_package.authoritative_task_hash == (
        sha256_canonical_json(recovered_task)
    )
    assert recovered.context_package.authoritative_authority_hash == (
        sha256_canonical_json(recovered_authority)
    )
    assert recovered_readiness["current_bridge_context_ready"]
    assert recovered_readiness["current_findings"] == []
    assert recovered.context_package.recovery_of_context_package_id == (
        rejected.context_package.context_package_id
    )
    assert (
        recovered.context_package.recovery_relationship_hash
        == relationship["content_hash"]
    )
    assert {
        payload.record_id,
        payload.raw_prompt_evidence_id,
        payload.raw_output_evidence_id,
    }.issubset(exclusions)
    assert parse_json(relationship["preserved_findings_json"]) == [
        finding.canonical_value()
        for finding in rejected.context_package.contamination_findings
    ]
    assert recovered.retrieval_manifest.entries[1].disposition == "excluded"
    assert "source_revoked" in (
        recovered.retrieval_manifest.entries[1].eligibility_reasons
    )
    assert rejected.context_package.canonical_json == (
        reconstructed_rejected["canonical_json"]
    )
    assert recovery_service.reconstruct_context_package(
        recovered.context_package.context_package_id
    )["content_hash"] == recovered.context_package.content_hash
    assert ContextIntegrityInspector(recovery_service._kernel).inspect().ok


def test_raw_controlled_record_is_detected_and_recovery_excludes_bundle(
    harness: I3DHarness,
) -> None:
    payload, _ = create_controlled_bundle(
        harness,
        base=1_735_000,
    )
    controlled_record_hash = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            "SELECT content_hash FROM records WHERE record_id = ?",
            (payload.record_id,),
        ).fetchone()["content_hash"]
    )
    construct_id = create_active_construct_memory(
        harness,
        base=1_736_000,
    )
    items = (
        ordinary_evidence_item(
            harness,
            number=1_736_010,
            injection_order=0,
            required=True,
        ),
        memory_context_item(
            harness,
            number=1_736_011,
            record_id=construct_id,
            context_kind="construct_memory",
            injection_order=1,
            required=False,
        ),
    )
    finalization_id = finalize_items(
        harness,
        items,
        finalization_number=1_736_012,
    )
    MemoryKernel(harness.config).transition_lifecycle(
        construct_id,
        transition_id=uid(1_736_013),
        to_state="revoked",
        reason_code="construct_revoked_before_raw_record_fixture",
        changed_at=NOW,
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    contaminated_service = retrieval_service(
        harness,
        identifier_start=1_737_000,
        assembler=InjectExcludedAssembler(
            (
                "memory_record",
                payload.record_id,
                controlled_record_hash,
                "memory",
            )
        ),
    )
    rejected = contaminated_service.assemble(
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_736_014,
        )
    )

    assert rejected.context_package.status == "rejected_contamination"
    assert "controlled_resilience_record" in {
        finding.reason_code
        for finding in rejected.context_package.contamination_findings
    }

    recovery_service = retrieval_service(
        harness,
        identifier_start=1_738_000,
    )
    recovered = recovery_service.recover(
        rejected.context_package.context_package_id,
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_736_015,
        ),
    )
    relationship = SqlProbe(harness.config).read(
        lambda connection: dict(
            connection.execute(
                """
                SELECT * FROM context_recovery_relationships
                WHERE recovery_context_package_id = ?
                """,
                (recovered.context_package.context_package_id,),
            ).fetchone()
        )
    )
    exclusions = set(parse_json(relationship["excluded_source_ids_json"]))

    assert recovered.accepted
    assert {
        payload.record_id,
        payload.raw_prompt_evidence_id,
        payload.raw_output_evidence_id,
    }.issubset(exclusions)
    assert parse_json(relationship["preserved_findings_json"]) == [
        finding.canonical_value()
        for finding in rejected.context_package.contamination_findings
    ]
    assert ContextIntegrityInspector(recovery_service._kernel).inspect().ok


def test_required_contaminated_source_recovery_remains_rejected(
    harness: I3DHarness,
) -> None:
    item = ordinary_evidence_item(
        harness,
        number=1_740_010,
        required=True,
    )
    finalization_id = finalize_items(
        harness,
        (item,),
        finalization_number=1_740_011,
    )
    contaminated_service = retrieval_service(
        harness,
        identifier_start=1_741_000,
        assembler=InjectExcludedAssembler(),
    )
    contaminated_service._materializer = ProhibitingMaterializer()
    contaminated = contaminated_service.assemble(
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_740_012,
        )
    )
    assert contaminated.context_package.status == "rejected_contamination"
    assert "excluded_source_present" in {
        finding.reason_code
        for finding in contaminated.context_package.contamination_findings
    }

    recovery = retrieval_service(
        harness,
        identifier_start=1_742_000,
    ).recover(
        contaminated.context_package.context_package_id,
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_740_013,
        ),
    )

    assert not recovery.accepted
    assert recovery.context_package.status == "rejected_required_source"
    assert not recovery.bridge_context_ready
    assert recovery.retrieval_manifest.entries[0].disposition == "excluded"


@pytest.mark.parametrize(
    ("trigger", "table", "id_column", "value_column", "value", "code"),
    [
        (
            "retrieval_requests_immutable",
            "retrieval_requests",
            "retrieval_request_id",
            "content_hash",
            "f" * 64,
            "I4A-REQUEST-HASH",
        ),
        (
            "retrieval_manifests_immutable",
            "retrieval_manifests",
            "retrieval_manifest_id",
            "content_hash",
            "e" * 64,
            "I4A-MANIFEST-HASH",
        ),
        (
            "retrieval_manifests_immutable",
            "retrieval_manifests",
            "retrieval_manifest_id",
            "task_memory_projection_json",
            "{}",
            "I4A-MANIFEST-RECONSTRUCTION",
        ),
        (
            "context_packages_immutable",
            "context_packages",
            "context_package_id",
            "content_hash",
            "d" * 64,
            "I4A-CONTEXT-HASH",
        ),
        (
            "retrieval_manifest_entries_immutable",
            "retrieval_manifest_entries",
            "entry_id",
            "final_rank",
            7,
            "I4A-RANK-ORDER",
        ),
        (
            "ordered_context_entries_immutable",
            "ordered_context_manifest_entries",
            "ordered_entry_id",
            "entry_order",
            7,
            "I4A-SECTION-ORDER",
        ),
    ],
)
def test_raw_sql_corruption_is_detected_by_dedicated_and_top_level_integrity(
    harness: I3DHarness,
    trigger: str,
    table: str,
    id_column: str,
    value_column: str,
    value: object,
    code: str,
) -> None:
    service, _, result = basic_attempt(harness)
    identifiers = {
        "retrieval_requests": result.retrieval_request.retrieval_request_id,
        "retrieval_manifests":
            result.retrieval_manifest.retrieval_manifest_id,
        "context_packages": result.context_package.context_package_id,
        "retrieval_manifest_entries":
            result.retrieval_manifest.entries[0].entry_id,
        "ordered_context_manifest_entries": next(
            entry.ordered_entry_id
            for entry in result.context_package.ordered_entries
            if entry.section == "evidence"
        ),
    }
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (trigger,),
        lambda connection: connection.execute(
            f"UPDATE {table} SET {value_column} = ? "  # noqa: S608
            f"WHERE {id_column} = ?",  # noqa: S608
            (value, identifiers[table]),
        ),
    )

    report = ContextIntegrityInspector(service._kernel).inspect()
    assert not report.ok
    assert code in {finding.code for finding in report.findings}
    assert not harness.persistence.integrity.inspect().ok
    with pytest.raises((IntegrityInspectionError, ValidationError)):
        service.reconstruct_context_package(
            result.context_package.context_package_id
        )


@pytest.mark.parametrize(
    ("mutation", "section", "reason_code", "integrity_code"),
    [
        (
            "task_objective",
            "task",
            "authoritative_task_content_mismatch",
            "I4A-AUTHORITATIVE-TASK-CONTENT-MISMATCH",
        ),
        (
            "task_prohibited_action",
            "task",
            "authoritative_task_content_mismatch",
            "I4A-AUTHORITATIVE-TASK-CONTENT-MISMATCH",
        ),
        (
            "task_requested_operation",
            "task",
            "authoritative_task_content_mismatch",
            "I4A-AUTHORITATIVE-TASK-CONTENT-MISMATCH",
        ),
        (
            "task_uncertainty",
            "task",
            "authoritative_task_content_mismatch",
            "I4A-AUTHORITATIVE-TASK-CONTENT-MISMATCH",
        ),
        (
            "authority_outcome",
            "authority",
            "authoritative_authority_content_mismatch",
            "I4A-AUTHORITATIVE-AUTHORITY-CONTENT-MISMATCH",
        ),
        (
            "authority_reason",
            "authority",
            "authoritative_authority_content_mismatch",
            "I4A-AUTHORITATIVE-AUTHORITY-CONTENT-MISMATCH",
        ),
        (
            "authority_permission_profile",
            "authority",
            "authoritative_authority_content_mismatch",
            "I4A-AUTHORITATIVE-AUTHORITY-CONTENT-MISMATCH",
        ),
        (
            "authority_reference",
            "authority",
            "authoritative_authority_content_mismatch",
            "I4A-AUTHORITATIVE-AUTHORITY-CONTENT-MISMATCH",
        ),
    ],
)
def test_faulty_authoritative_assembler_is_rejected_and_exactly_preserved(
    harness: I3DHarness,
    mutation: str,
    section: str,
    reason_code: str,
    integrity_code: str,
) -> None:
    create_uncertainty(harness, base=1_760_000, impact="medium")
    item = ordinary_evidence_item(harness, number=1_760_010)
    finalization_id = finalize_items(
        harness,
        (item,),
        finalization_number=1_760_011,
    )
    service = retrieval_service(
        harness,
        identifier_start=1_761_000,
        assembler=SubstituteAuthoritativeSectionAssembler(mutation),
    )
    result = service.assemble(
        request_for(
            harness,
            finalization_id=finalization_id,
            number=1_760_012,
        )
    )
    expected_task, expected_authority = expected_authoritative_sections(result)
    expected = (
        expected_task if section == "task" else expected_authority
    )
    expected_hash = sha256_canonical_json(expected)
    sections = parse_json(result.context_package.sections_json)
    authoritative_entry = next(
        entry
        for entry in result.context_package.ordered_entries
        if entry.section == section
    )
    package_hash = (
        result.context_package.authoritative_task_hash
        if section == "task"
        else result.context_package.authoritative_authority_hash
    )

    assert not result.accepted
    assert not result.bridge_context_ready
    assert result.context_package.status == "rejected_contamination"
    assert result.context_package.contamination_status == "contaminated"
    assert result.rejection_reasons == (reason_code,)
    assert sections[section] != expected
    assert package_hash != expected_hash
    assert package_hash == sha256_canonical_json(sections[section])
    assert authoritative_entry.entry_canonical_hash == package_hash
    assert authoritative_entry.source_content_hash == package_hash
    assert authoritative_entry.retrieval_manifest_entry_id is None
    assert len(result.context_package.contamination_findings) == 1
    finding = result.context_package.contamination_findings[0]
    assert finding.reason_code == reason_code
    assert f"expected_hash={expected_hash}" in finding.detail
    assert f"package_hash={package_hash}" in finding.detail

    reconstruction = service.reconstruct_context_package(
        result.context_package.context_package_id
    )
    readiness = service.assess_context_readiness(
        result.context_package.context_package_id,
        NOW,
    )
    assert reconstruction["historical_integrity_verified"]
    assert reconstruction["historical_status"] == "rejected_contamination"
    assert not readiness["current_bridge_context_ready"]
    assert reason_code in {
        readiness_finding["reason_code"]
        for readiness_finding in readiness["current_findings"]
    }

    reopened = PersistenceService.initialize(harness.config).retrieval_context
    assert reopened.reconstruct_context_package(
        result.context_package.context_package_id
    ) == reconstruction
    assert reopened.assess_context_readiness(
        result.context_package.context_package_id,
        NOW,
    ) == readiness

    report = ContextIntegrityInspector(service._kernel).inspect()
    exact = [
        report_finding
        for report_finding in report.findings
        if report_finding.code == integrity_code
    ]
    assert len(exact) == 1
    assert exact[0].severity == "warning"
    assert exact[0].detail == finding.detail
    assert report.ok
    top_level = harness.persistence.integrity.inspect()
    assert top_level.ok
    assert (
        "retrieval_context_" + integrity_code.lower().replace("-", "_")
    ) in {top_finding.code for top_finding in top_level.findings}


@pytest.mark.parametrize(
    ("section", "integrity_code"),
    [
        ("task", "I4A-AUTHORITATIVE-TASK-CONTENT-MISMATCH"),
        ("authority", "I4A-AUTHORITATIVE-AUTHORITY-CONTENT-MISMATCH"),
    ],
)
def test_raw_sql_authoritative_content_corruption_is_detected(
    harness: I3DHarness,
    section: str,
    integrity_code: str,
) -> None:
    service, _, result = basic_attempt(harness)
    corrupt_authoritative_section(
        harness,
        result,
        section=section,
        recompute_local_hashes=False,
    )

    report = ContextIntegrityInspector(service._kernel).inspect()
    assert not report.ok
    assert integrity_code in {finding.code for finding in report.findings}
    top_level = harness.persistence.integrity.inspect()
    assert not top_level.ok
    assert (
        "retrieval_context_" + integrity_code.lower().replace("-", "_")
    ) in {finding.code for finding in top_level.findings}
    with pytest.raises((IntegrityInspectionError, ValidationError)):
        service.reconstruct_context_package(
            result.context_package.context_package_id
        )


@pytest.mark.parametrize(
    ("section", "reason_code", "integrity_code"),
    [
        (
            "task",
            "authoritative_task_content_mismatch",
            "I4A-AUTHORITATIVE-TASK-CONTENT-MISMATCH",
        ),
        (
            "authority",
            "authoritative_authority_content_mismatch",
            "I4A-AUTHORITATIVE-AUTHORITY-CONTENT-MISMATCH",
        ),
    ],
)
def test_recomputed_local_hashes_cannot_hide_authoritative_sql_corruption(
    harness: I3DHarness,
    section: str,
    reason_code: str,
    integrity_code: str,
) -> None:
    service, _, result = basic_attempt(harness)
    package_id = result.context_package.context_package_id
    corrupt_authoritative_section(
        harness,
        result,
        section=section,
        recompute_local_hashes=True,
    )

    with pytest.raises(
        IntegrityInspectionError,
        match="historical authoritative section binding",
    ):
        service.reconstruct_context_package(package_id)
    readiness = service.assess_context_readiness(package_id, NOW)
    assert not readiness["current_bridge_context_ready"]
    assert reason_code in {
        finding["reason_code"] for finding in readiness["current_findings"]
    }
    report = ContextIntegrityInspector(service._kernel).inspect()
    assert not report.ok
    matching = [
        finding
        for finding in report.findings
        if finding.code == integrity_code
    ]
    assert len(matching) == 1
    assert matching[0].severity == "error"
    top_level = harness.persistence.integrity.inspect()
    assert not top_level.ok
    assert (
        "retrieval_context_" + integrity_code.lower().replace("-", "_")
    ) in {finding.code for finding in top_level.findings}

    reopened = PersistenceService.initialize(harness.config).retrieval_context
    with pytest.raises(IntegrityInspectionError):
        reopened.reconstruct_context_package(package_id)
    assert reopened.assess_context_readiness(package_id, NOW) == readiness

    code = """
import json
import sys
from pathlib import Path
from batch87_apprentice.context import ContextIntegrityInspector
from batch87_apprentice.persistence import DatabaseConfig, PersistenceService

persistence = PersistenceService.initialize(DatabaseConfig(Path(sys.argv[1])))
service = persistence.retrieval_context
try:
    service.reconstruct_context_package(sys.argv[2])
except Exception as exc:
    reconstruction_error = type(exc).__name__
else:
    reconstruction_error = None
readiness = service.assess_context_readiness(sys.argv[2], sys.argv[3])
report = ContextIntegrityInspector(service._kernel).inspect()
print(json.dumps({
    "codes": [finding.code for finding in report.findings],
    "readiness": readiness,
    "reconstruction_error": reconstruction_error,
}, sort_keys=True))
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(Path.cwd() / "src"), str(Path.cwd())]
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(harness.config.path),
            package_id,
            NOW,
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    separate = json.loads(completed.stdout)
    assert separate["reconstruction_error"] == "IntegrityInspectionError"
    assert separate["readiness"] == readiness
    assert integrity_code in separate["codes"]


@pytest.mark.parametrize(
    ("section", "violation"),
    [
        ("task", "source_identity"),
        ("task", "entry_hash"),
        ("authority", "source_identity"),
        ("authority", "entry_hash"),
    ],
)
def test_sql_guard_rejects_noncanonical_authoritative_entry_binding(
    harness: I3DHarness,
    section: str,
    violation: str,
) -> None:
    service, _, result = basic_attempt(harness)
    original = next(
        entry
        for entry in result.context_package.ordered_entries
        if entry.section == section
    )
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("ordered_context_entries_no_delete",),
        lambda connection: connection.execute(
            """
            DELETE FROM ordered_context_manifest_entries
            WHERE ordered_entry_id = ?
            """,
            (original.ordered_entry_id,),
        ),
    )
    changed = replace(
        original,
        ordered_entry_id=uid(1_799_000),
    )
    if violation == "source_identity":
        changed = replace(changed, source_id=uid(1_799_001))
    else:
        value = parse_json(changed.entry_json)
        if section == "task":
            value["objective"] += " SQL guard substitution."
        else:
            value["governance_decision"]["outcome"] = (
                "sql_guard_substitution"
            )
        changed = replace(
            changed,
            entry_json=canonical_json_text(value),
        )

    def insert(connection) -> None:
        connection.execute(
            """
            INSERT INTO ordered_context_manifest_entries (
                ordered_entry_id, context_package_id, section,
                section_order, entry_order, source_kind, source_id,
                source_content_hash, retrieval_manifest_entry_id,
                entry_canonical_json, entry_canonical_hash,
                canonical_json, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                changed.ordered_entry_id,
                result.context_package.context_package_id,
                changed.section,
                changed.section_order,
                changed.entry_order,
                changed.source_kind,
                changed.source_id,
                changed.source_content_hash,
                changed.retrieval_manifest_entry_id,
                changed.entry_json,
                changed.entry_canonical_hash,
                changed.canonical_json,
                changed.content_hash,
            ),
        )

    with pytest.raises(ConflictError, match="integrity constraint"):
        service._kernel.write(insert)
    assert SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT count(*)
            FROM ordered_context_manifest_entries
            WHERE context_package_id = ? AND section = ?
            """,
            (result.context_package.context_package_id, section),
        ).fetchone()[0]
    ) == 0


def test_public_boundary_exposes_no_provider_invocation_or_raw_database_handle() -> None:
    source = inspect.getsource(ContextRetrievalService)
    public_methods = {
        name
        for name, value in inspect.getmembers(
            ContextRetrievalService,
            predicate=inspect.isfunction,
        )
        if not name.startswith("_")
    }

    assert public_methods == {
        "assemble",
        "assess_context_readiness",
        "recover",
        "reconstruct_context_package",
        "reconstruct_retrieval_manifest",
    }
    assert "run_model" not in source
    assert "def invoke" not in source
    assert "sqlite3.Connection" not in {
        str(inspect.signature(getattr(ContextRetrievalService, name)))
        for name in public_methods
    }
    assert not hasattr(StructuredContextPackage, "invoke")
