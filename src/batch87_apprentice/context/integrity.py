"""Dedicated read-only integrity inspection for persisted B87-I4-A context."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import IntegrityInspectionError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .assembly import (
    _authoritative_binding_mismatch_specs,
    build_authoritative_authority_section,
    build_authoritative_task_section,
)
from .contracts import OrderedContextEntry


@dataclass(frozen=True, slots=True)
class ContextIntegrityFinding:
    code: str
    severity: str
    table: str
    object_id: str | None
    task_id: str | None
    retrieval_request_id: str | None
    retrieval_manifest_id: str | None
    context_package_id: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class ContextIntegrityReport:
    findings: tuple[ContextIntegrityFinding, ...]

    @property
    def ok(self) -> bool:
        return not any(
            finding.severity == "error" for finding in self.findings
        )


def _add(
    findings: set[ContextIntegrityFinding],
    *,
    code: str,
    table: str,
    detail: str,
    object_id: str | None = None,
    task_id: str | None = None,
    retrieval_request_id: str | None = None,
    retrieval_manifest_id: str | None = None,
    context_package_id: str | None = None,
    severity: str = "error",
) -> None:
    findings.add(
        ContextIntegrityFinding(
            code=code,
            severity=severity,
            table=table,
            object_id=object_id,
            task_id=task_id,
            retrieval_request_id=retrieval_request_id,
            retrieval_manifest_id=retrieval_manifest_id,
            context_package_id=context_package_id,
            detail=detail,
        )
    )


def _canonical_hash_check(
    findings: set[ContextIntegrityFinding],
    *,
    table: str,
    row: sqlite3.Row,
    identifier_column: str,
    code_prefix: str,
    task_id: str | None = None,
    retrieval_request_id: str | None = None,
    retrieval_manifest_id: str | None = None,
    context_package_id: str | None = None,
) -> None:
    object_id = row[identifier_column]
    try:
        value = parse_json(row["canonical_json"])
        canonical = canonical_json_text(value)
    except Exception:
        _add(
            findings,
            code=f"{code_prefix}-CANONICAL",
            table=table,
            object_id=object_id,
            task_id=task_id,
            retrieval_request_id=retrieval_request_id,
            retrieval_manifest_id=retrieval_manifest_id,
            context_package_id=context_package_id,
            detail="stored canonical JSON is malformed",
        )
        return
    if not isinstance(value, dict) or canonical != row["canonical_json"]:
        _add(
            findings,
            code=f"{code_prefix}-CANONICAL",
            table=table,
            object_id=object_id,
            task_id=task_id,
            retrieval_request_id=retrieval_request_id,
            retrieval_manifest_id=retrieval_manifest_id,
            context_package_id=context_package_id,
            detail="stored JSON is not the canonical object representation",
        )
    if row["content_hash"] != sha256_canonical_json(value):
        _add(
            findings,
            code=f"{code_prefix}-HASH",
            table=table,
            object_id=object_id,
            task_id=task_id,
            retrieval_request_id=retrieval_request_id,
            retrieval_manifest_id=retrieval_manifest_id,
            context_package_id=context_package_id,
            detail="stored hash differs from canonical JSON",
        )


class ContextIntegrityInspector:
    """Verify I4-A records, normalized relationships and live source state."""

    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel

    def inspect(self) -> ContextIntegrityReport:
        try:
            return self._kernel.read(self._inspect_connection)
        except IntegrityInspectionError:
            raise
        except Exception as exc:
            raise IntegrityInspectionError(
                "I4-A context integrity inspection failed"
            ) from exc

    @staticmethod
    def _inspect_connection(
        connection: sqlite3.Connection,
    ) -> ContextIntegrityReport:
        from .retrieval import ContextRetrievalService

        findings: set[ContextIntegrityFinding] = set()

        request_rows = list(
            connection.execute(
                "SELECT * FROM retrieval_requests ORDER BY retrieval_request_id"
            )
        )
        for row in request_rows:
            request_id = row["retrieval_request_id"]
            _canonical_hash_check(
                findings,
                table="retrieval_requests",
                row=row,
                identifier_column="retrieval_request_id",
                code_prefix="I4A-REQUEST",
                task_id=row["task_id"],
                retrieval_request_id=request_id,
            )
            try:
                ContextRetrievalService._load_request(connection, request_id)
            except Exception as exc:
                _add(
                    findings,
                    code="I4A-REQUEST-CANONICAL",
                    table="retrieval_requests",
                    object_id=request_id,
                    task_id=row["task_id"],
                    retrieval_request_id=request_id,
                    detail=f"request cannot be reconstructed: {exc}",
                )
            binding = connection.execute(
                """
                SELECT 1
                FROM tasks AS task
                JOIN sessions AS session_record
                  ON session_record.session_id = task.session_id
                JOIN task_context_finalizations AS finalization
                  ON finalization.finalization_id =
                     ? AND finalization.task_id = task.task_id
                WHERE task.task_id = ?
                  AND task.session_id = ?
                  AND task.project_scope_id = ?
                  AND finalization.session_id = ?
                  AND finalization.project_scope_id = ?
                """,
                (
                    row["task_context_finalization_id"],
                    row["task_id"],
                    row["session_id"],
                    row["project_scope_id"],
                    row["session_id"],
                    row["project_scope_id"],
                ),
            ).fetchone()
            if binding is None:
                _add(
                    findings,
                    code="I4A-REQUEST-BINDING",
                    table="retrieval_requests",
                    object_id=request_id,
                    task_id=row["task_id"],
                    retrieval_request_id=request_id,
                    detail=(
                        "request parent task, session, project or finalization "
                        "binding is missing or inconsistent"
                    ),
                )

        manifest_rows = list(
            connection.execute(
                "SELECT * FROM retrieval_manifests "
                "ORDER BY retrieval_manifest_id"
            )
        )
        for row in manifest_rows:
            manifest_id = row["retrieval_manifest_id"]
            request_id = row["retrieval_request_id"]
            _canonical_hash_check(
                findings,
                table="retrieval_manifests",
                row=row,
                identifier_column="retrieval_manifest_id",
                code_prefix="I4A-MANIFEST",
                task_id=row["task_id"],
                retrieval_request_id=request_id,
                retrieval_manifest_id=manifest_id,
            )
            try:
                manifest = ContextRetrievalService._load_manifest(
                    connection,
                    manifest_id,
                )
                request = ContextRetrievalService._load_request(
                    connection,
                    request_id,
                )
                ContextRetrievalService._verify_manifest_relationships(
                    connection,
                    request,
                    manifest,
                )
            except Exception as exc:
                _add(
                    findings,
                    code="I4A-MANIFEST-RECONSTRUCTION",
                    table="retrieval_manifests",
                    object_id=manifest_id,
                    task_id=row["task_id"],
                    retrieval_request_id=request_id,
                    retrieval_manifest_id=manifest_id,
                    detail=f"manifest cannot be reconstructed: {exc}",
                )

            entry_rows = list(
                connection.execute(
                    """
                    SELECT entry.*, item.injection_order
                    FROM retrieval_manifest_entries AS entry
                    LEFT JOIN task_context_items AS item
                      ON item.context_item_id = entry.context_item_id
                    WHERE entry.retrieval_manifest_id = ?
                    ORDER BY item.injection_order, entry.entry_id
                    """,
                    (manifest_id,),
                )
            )
            for entry_row in entry_rows:
                _canonical_hash_check(
                    findings,
                    table="retrieval_manifest_entries",
                    row=entry_row,
                    identifier_column="entry_id",
                    code_prefix="I4A-MANIFEST-ENTRY",
                    task_id=row["task_id"],
                    retrieval_request_id=request_id,
                    retrieval_manifest_id=manifest_id,
                )
            finalized_ids = [
                item["context_item_id"]
                for item in connection.execute(
                    """
                    SELECT context_item_id
                    FROM task_context_items
                    WHERE task_id = ?
                    ORDER BY injection_order
                    """,
                    (row["task_id"],),
                )
            ]
            entry_ids = [
                entry["context_item_id"] for entry in entry_rows
            ]
            if entry_ids != finalized_ids or len(entry_ids) != len(set(entry_ids)):
                _add(
                    findings,
                    code="I4A-CANDIDATE-ACCOUNTING",
                    table="retrieval_manifest_entries",
                    object_id=manifest_id,
                    task_id=row["task_id"],
                    retrieval_request_id=request_id,
                    retrieval_manifest_id=manifest_id,
                    detail=(
                        "manifest candidate set omits, duplicates or adds a "
                        "finalized I3-D context item"
                    ),
                )
            included_invalid = [
                entry["entry_id"]
                for entry in entry_rows
                if entry["disposition"] == "included"
                and (
                    entry["eligibility_status"] != "eligible"
                    or entry["materialization_status"] != "materialized"
                    or entry["materialized_content_hash"] is None
                    or entry["final_rank"] is None
                )
            ]
            if included_invalid:
                _add(
                    findings,
                    code="I4A-INCLUDED-INELIGIBLE",
                    table="retrieval_manifest_entries",
                    object_id=included_invalid[0],
                    task_id=row["task_id"],
                    retrieval_request_id=request_id,
                    retrieval_manifest_id=manifest_id,
                    detail="included entry lacks eligibility, materialization or rank",
                )
            ranks = sorted(
                entry["final_rank"]
                for entry in entry_rows
                if entry["final_rank"] is not None
            )
            if ranks != list(range(len(ranks))):
                _add(
                    findings,
                    code="I4A-RANK-ORDER",
                    table="retrieval_manifest_entries",
                    object_id=manifest_id,
                    task_id=row["task_id"],
                    retrieval_request_id=request_id,
                    retrieval_manifest_id=manifest_id,
                    detail="included final ranks are not contiguous",
                )

        package_rows = list(
            connection.execute(
                "SELECT * FROM context_packages ORDER BY context_package_id"
            )
        )
        for row in package_rows:
            package_id = row["context_package_id"]
            request_id = row["retrieval_request_id"]
            manifest_id = row["retrieval_manifest_id"]
            _canonical_hash_check(
                findings,
                table="context_packages",
                row=row,
                identifier_column="context_package_id",
                code_prefix="I4A-CONTEXT",
                task_id=row["task_id"],
                retrieval_request_id=request_id,
                retrieval_manifest_id=manifest_id,
                context_package_id=package_id,
            )
            try:
                package = ContextRetrievalService._load_package(
                    connection,
                    package_id,
                )
                manifest = ContextRetrievalService._load_manifest(
                    connection,
                    manifest_id,
                )
                request = ContextRetrievalService._load_request(
                    connection,
                    request_id,
                )
                ContextRetrievalService._verify_manifest_relationships(
                    connection,
                    request,
                    manifest,
                )
                ContextRetrievalService._verify_package_relationships(
                    connection,
                    request,
                    manifest,
                    package,
                )
                ContextRetrievalService._verify_historical_projection(
                    connection,
                    request=request,
                    manifest=manifest,
                )
            except Exception as exc:
                _add(
                    findings,
                    code="I4A-CONTEXT-RECONSTRUCTION",
                    table="context_packages",
                    object_id=package_id,
                    task_id=row["task_id"],
                    retrieval_request_id=request_id,
                    retrieval_manifest_id=manifest_id,
                    context_package_id=package_id,
                    detail=f"context package cannot be reconstructed: {exc}",
                )
                package = None
                manifest = None
                request = None
            if package is not None and manifest is not None and request is not None:
                verifier = ContextRetrievalService.__new__(
                    ContextRetrievalService
                )
                from .retrieval import _SafeSourceMaterializer

                verifier._materializer = _SafeSourceMaterializer()
                binding_findings = verifier._materialization_binding_findings(
                    connection,
                    request=request,
                    manifest=manifest,
                    package=package,
                    mode="historical",
                    evaluated_at=request.requested_at,
                )
                preserved = verifier._preserved_rejection_covers(
                    package,
                    binding_findings,
                )
                for binding_finding in binding_findings:
                    _add(
                        findings,
                        code=(
                            "I4A-MATERIALIZED-CONTENT-MISMATCH"
                            if binding_finding.reason_code
                            == "materialized_content_mismatch"
                            else "I4A-SELECTED-SOURCE-INTEGRITY"
                        ),
                        table="ordered_context_manifest_entries",
                        object_id=binding_finding.source_id,
                        task_id=row["task_id"],
                        retrieval_request_id=request_id,
                        retrieval_manifest_id=manifest_id,
                        context_package_id=package_id,
                        detail=binding_finding.detail,
                        severity="warning" if preserved else "error",
                    )

            ordered_rows = list(
                connection.execute(
                    """
                    SELECT * FROM ordered_context_manifest_entries
                    WHERE context_package_id = ?
                    ORDER BY section_order, entry_order
                    """,
                    (package_id,),
                )
            )
            for ordered_row in ordered_rows:
                _canonical_hash_check(
                    findings,
                    table="ordered_context_manifest_entries",
                    row=ordered_row,
                    identifier_column="ordered_entry_id",
                    code_prefix="I4A-ORDERED-ENTRY",
                    task_id=row["task_id"],
                    retrieval_request_id=request_id,
                    retrieval_manifest_id=manifest_id,
                    context_package_id=package_id,
                )
                try:
                    entry_value = parse_json(
                        ordered_row["entry_canonical_json"]
                    )
                    if (
                        not isinstance(entry_value, dict)
                        or canonical_json_text(entry_value)
                        != ordered_row["entry_canonical_json"]
                        or sha256_canonical_json(entry_value)
                        != ordered_row["entry_canonical_hash"]
                    ):
                        raise ValueError
                except Exception:
                    _add(
                        findings,
                        code="I4A-ORDERED-ENTRY-HASH",
                        table="ordered_context_manifest_entries",
                        object_id=ordered_row["ordered_entry_id"],
                        task_id=row["task_id"],
                        retrieval_request_id=request_id,
                        retrieval_manifest_id=manifest_id,
                        context_package_id=package_id,
                        detail=(
                            "ordered entry content is malformed or its hash "
                            "does not match"
                        ),
                    )
            ContextIntegrityInspector._inspect_authoritative_sections(
                connection,
                findings,
                package_row=row,
                ordered_rows=ordered_rows,
            )
            for section_order in range(5):
                positions = [
                    ordered_row["entry_order"]
                    for ordered_row in ordered_rows
                    if ordered_row["section_order"] == section_order
                ]
                if positions != list(range(len(positions))):
                    _add(
                        findings,
                        code="I4A-SECTION-ORDER",
                        table="ordered_context_manifest_entries",
                        object_id=package_id,
                        task_id=row["task_id"],
                        retrieval_request_id=request_id,
                        retrieval_manifest_id=manifest_id,
                        context_package_id=package_id,
                        detail="context entry order is not contiguous by section",
                    )
                    break
            excluded_present = connection.execute(
                """
                SELECT ordered.ordered_entry_id
                FROM ordered_context_manifest_entries AS ordered
                JOIN retrieval_manifest_entries AS entry
                  ON entry.entry_id = ordered.retrieval_manifest_entry_id
                WHERE ordered.context_package_id = ?
                  AND entry.disposition = 'excluded'
                LIMIT 1
                """,
                (package_id,),
            ).fetchone()
            if excluded_present is not None:
                _add(
                    findings,
                    code=(
                        "I4A-REJECTED-EXCLUDED-SOURCE-PRESERVED"
                        if row["status"] == "rejected_contamination"
                        else "I4A-EXCLUDED-SOURCE-PRESENT"
                    ),
                    table="ordered_context_manifest_entries",
                    object_id=excluded_present["ordered_entry_id"],
                    task_id=row["task_id"],
                    retrieval_request_id=request_id,
                    retrieval_manifest_id=manifest_id,
                    context_package_id=package_id,
                    detail=(
                        "an excluded retrieval source appears in the preserved "
                        "attempted context"
                    ),
                    severity=(
                        "warning"
                        if row["status"] == "rejected_contamination"
                        else "error"
                    ),
                )
            finding_count = connection.execute(
                """
                SELECT count(*) AS total
                FROM context_contamination_findings
                WHERE context_package_id = ?
                """,
                (package_id,),
            ).fetchone()["total"]
            if row["status"] == "accepted" and finding_count:
                _add(
                    findings,
                    code="I4A-ACCEPTED-CONTAMINATION",
                    table="context_packages",
                    object_id=package_id,
                    task_id=row["task_id"],
                    retrieval_request_id=request_id,
                    retrieval_manifest_id=manifest_id,
                    context_package_id=package_id,
                    detail="accepted context has contamination findings",
                )
            if (
                row["status"] == "rejected_contamination"
                and not finding_count
            ):
                _add(
                    findings,
                    code="I4A-REJECTED-FINDINGS-MISSING",
                    table="context_packages",
                    object_id=package_id,
                    task_id=row["task_id"],
                    retrieval_request_id=request_id,
                    retrieval_manifest_id=manifest_id,
                    context_package_id=package_id,
                    detail="contamination rejection has no preserved findings",
                )

        ContextIntegrityInspector._inspect_source_hashes(
            connection,
            findings,
        )
        ContextIntegrityInspector._inspect_recoveries(
            connection,
            findings,
        )
        ordered = tuple(
            sorted(
                findings,
                key=lambda finding: (
                    finding.severity,
                    finding.code,
                    finding.table,
                    finding.object_id or "",
                    finding.detail,
                ),
            )
        )
        return ContextIntegrityReport(findings=ordered)

    @staticmethod
    def _inspect_authoritative_sections(
        connection: sqlite3.Connection,
        findings: set[ContextIntegrityFinding],
        *,
        package_row: sqlite3.Row,
        ordered_rows: list[sqlite3.Row],
    ) -> None:
        """Bind raw authoritative rows to canonical attempt-time projection."""

        projection_row = connection.execute(
            """
            SELECT task_memory_projection_json, task_memory_projection_hash
            FROM retrieval_manifests
            WHERE retrieval_manifest_id = ?
            """,
            (package_row["retrieval_manifest_id"],),
        ).fetchone()
        if projection_row is None:
            return
        try:
            projection = parse_json(
                projection_row["task_memory_projection_json"]
            )
            if (
                not isinstance(projection, Mapping)
                or canonical_json_text(projection)
                != projection_row["task_memory_projection_json"]
                or sha256_canonical_json(projection)
                != projection_row["task_memory_projection_hash"]
            ):
                return
            authoritative_i2 = projection["authoritative_i2"]
            uncertainty_projection = projection["uncertainties"]
            if not isinstance(authoritative_i2, Mapping) or not isinstance(
                uncertainty_projection,
                Mapping,
            ):
                return
            active = uncertainty_projection["active"]
            if not isinstance(active, list) or any(
                not isinstance(uncertainty, Mapping)
                for uncertainty in active
            ):
                return
            expected_task = build_authoritative_task_section(
                authoritative_i2,
                tuple(active),
            )
            expected_authority = build_authoritative_authority_section(
                authoritative_i2
            )
            task = authoritative_i2["task"]
            decision = authoritative_i2["decision"]
            if not isinstance(task, Mapping) or not isinstance(
                decision,
                Mapping,
            ):
                return
        except Exception:
            return

        ordered_entries: list[OrderedContextEntry] = []
        stored_entry_hashes: dict[str, str] = {}
        for ordered_row in ordered_rows:
            try:
                entry = OrderedContextEntry(
                    ordered_entry_id=ordered_row["ordered_entry_id"],
                    section=ordered_row["section"],
                    section_order=ordered_row["section_order"],
                    entry_order=ordered_row["entry_order"],
                    source_kind=ordered_row["source_kind"],
                    source_id=ordered_row["source_id"],
                    source_content_hash=ordered_row["source_content_hash"],
                    retrieval_manifest_entry_id=ordered_row[
                        "retrieval_manifest_entry_id"
                    ],
                    entry_json=ordered_row["entry_canonical_json"],
                )
            except Exception:
                continue
            ordered_entries.append(entry)
            stored_entry_hashes[entry.ordered_entry_id] = ordered_row[
                "entry_canonical_hash"
            ]

        specs = _authoritative_binding_mismatch_specs(
            sections_json=package_row["sections_json"],
            ordered_entries=tuple(ordered_entries),
            authoritative_task_hash=package_row["authoritative_task_hash"],
            authoritative_authority_hash=package_row[
                "authoritative_authority_hash"
            ],
            expected_task=expected_task,
            expected_authority=expected_authority,
            expected_task_id=task["task_id"],
            expected_authority_id=decision["governance_decision_id"],
            stored_entry_hashes=stored_entry_hashes,
        )
        if not specs:
            return
        preserved = {
            (
                finding["reason_code"],
                finding["source_kind"],
                finding["source_id"],
                finding["detail"],
            )
            for finding in connection.execute(
                """
                SELECT reason_code, source_kind, source_id, detail
                FROM context_contamination_findings
                WHERE context_package_id = ?
                """,
                (package_row["context_package_id"],),
            )
        }
        codes = {
            "authoritative_task_content_mismatch":
                "I4A-AUTHORITATIVE-TASK-CONTENT-MISMATCH",
            "authoritative_authority_content_mismatch":
                "I4A-AUTHORITATIVE-AUTHORITY-CONTENT-MISMATCH",
        }
        for reason_code, source_kind, source_id, detail in specs:
            exact_finding = (
                reason_code,
                source_kind,
                source_id,
                detail,
            ) in preserved
            deliberately_rejected = (
                package_row["status"] == "rejected_contamination"
                and package_row["contamination_status"] == "contaminated"
                and exact_finding
            )
            matching_row = next(
                (
                    ordered_row
                    for ordered_row in ordered_rows
                    if ordered_row["section"]
                    == (
                        "task"
                        if reason_code
                        == "authoritative_task_content_mismatch"
                        else "authority"
                    )
                    or ordered_row["source_kind"] == source_kind
                ),
                None,
            )
            _add(
                findings,
                code=codes[reason_code],
                table="ordered_context_manifest_entries",
                object_id=(
                    package_row["context_package_id"]
                    if matching_row is None
                    else matching_row["ordered_entry_id"]
                ),
                task_id=package_row["task_id"],
                retrieval_request_id=package_row["retrieval_request_id"],
                retrieval_manifest_id=package_row["retrieval_manifest_id"],
                context_package_id=package_row["context_package_id"],
                detail=detail,
                severity="warning" if deliberately_rejected else "error",
            )

    @staticmethod
    def _inspect_source_hashes(
        connection: sqlite3.Connection,
        findings: set[ContextIntegrityFinding],
    ) -> None:
        rows = connection.execute(
            """
            SELECT entry.entry_id, entry.source_kind, entry.source_id,
                   entry.source_content_hash, manifest.task_id,
                   manifest.retrieval_request_id,
                   manifest.retrieval_manifest_id,
                   package.context_package_id,
                   CASE entry.source_kind
                       WHEN 'memory_record' THEN memory.content_hash
                       WHEN 'evidence' THEN evidence.content_hash
                       WHEN 'governance_rule' THEN rule.content_hash
                   END AS current_hash
            FROM retrieval_manifest_entries AS entry
            JOIN retrieval_manifests AS manifest
              ON manifest.retrieval_manifest_id =
                 entry.retrieval_manifest_id
            LEFT JOIN context_packages AS package
              ON package.retrieval_manifest_id =
                 manifest.retrieval_manifest_id
            LEFT JOIN records AS memory
              ON entry.source_kind = 'memory_record'
             AND memory.record_id = entry.source_id
            LEFT JOIN evidence_items AS evidence
              ON entry.source_kind = 'evidence'
             AND evidence.evidence_id = entry.source_id
            LEFT JOIN governance_rules AS rule
              ON entry.source_kind = 'governance_rule'
             AND rule.governance_rule_id = entry.source_id
            ORDER BY entry.entry_id
            """
        )
        for row in rows:
            if row["current_hash"] != row["source_content_hash"]:
                _add(
                    findings,
                    code="I4A-SOURCE-HASH-DRIFT",
                    table="retrieval_manifest_entries",
                    object_id=row["entry_id"],
                    task_id=row["task_id"],
                    retrieval_request_id=row["retrieval_request_id"],
                    retrieval_manifest_id=row["retrieval_manifest_id"],
                    context_package_id=row["context_package_id"],
                    detail=(
                        f"{row['source_kind']} source is missing or its "
                        "content hash has drifted"
                    ),
                )

    @staticmethod
    def _inspect_recoveries(
        connection: sqlite3.Connection,
        findings: set[ContextIntegrityFinding],
    ) -> None:
        from .contracts import RecoveryRelationship

        relationships = list(
            connection.execute(
                """
                SELECT relationship.*, recovery.task_id,
                       recovery.session_id, recovery.project_scope_id,
                       recovery.task_context_finalization_id,
                       recovery.recovery_of_context_package_id,
                       recovery.recovery_relationship_hash,
                       rejected.task_id AS rejected_task_id,
                       rejected.session_id AS rejected_session_id,
                       rejected.project_scope_id AS rejected_project_scope_id,
                       rejected.task_context_finalization_id
                           AS rejected_finalization_id,
                       rejected.status AS rejected_status,
                       recovery.retrieval_request_id,
                       recovery.retrieval_manifest_id
                FROM context_recovery_relationships AS relationship
                LEFT JOIN context_packages AS recovery
                  ON recovery.context_package_id =
                     relationship.recovery_context_package_id
                LEFT JOIN context_packages AS rejected
                  ON rejected.context_package_id =
                     relationship.rejected_context_package_id
                ORDER BY relationship.recovery_context_package_id
                """
            )
        )
        for row in relationships:
            package_id = row["recovery_context_package_id"]
            try:
                excluded = parse_json(row["excluded_source_ids_json"])
                relationship = RecoveryRelationship(
                    recovery_context_package_id=package_id,
                    rejected_context_package_id=row[
                        "rejected_context_package_id"
                    ],
                    recovery_reason=row["recovery_reason"],
                    excluded_source_ids=tuple(excluded),
                    preserved_findings_json=row[
                        "preserved_findings_json"
                    ],
                    created_at=row["created_at"],
                )
                if (
                    relationship.canonical_json != row["canonical_json"]
                    or relationship.content_hash != row["content_hash"]
                    or row["recovery_relationship_hash"]
                    != relationship.content_hash
                ):
                    raise ValueError
            except Exception:
                _add(
                    findings,
                    code="I4A-RECOVERY-CANONICAL",
                    table="context_recovery_relationships",
                    object_id=package_id,
                    task_id=row["task_id"],
                    retrieval_request_id=row["retrieval_request_id"],
                    retrieval_manifest_id=row["retrieval_manifest_id"],
                    context_package_id=package_id,
                    detail="recovery relationship is malformed or hash-invalid",
                )
                continue
            if (
                row["recovery_of_context_package_id"]
                != row["rejected_context_package_id"]
                or row["rejected_status"] != "rejected_contamination"
                or row["task_id"] != row["rejected_task_id"]
                or row["session_id"] != row["rejected_session_id"]
                or row["project_scope_id"]
                != row["rejected_project_scope_id"]
                or row["task_context_finalization_id"]
                != row["rejected_finalization_id"]
            ):
                _add(
                    findings,
                    code="I4A-RECOVERY-BINDING",
                    table="context_recovery_relationships",
                    object_id=package_id,
                    task_id=row["task_id"],
                    retrieval_request_id=row["retrieval_request_id"],
                    retrieval_manifest_id=row["retrieval_manifest_id"],
                    context_package_id=package_id,
                    detail=(
                        "recovery linkage, task, session, project or "
                        "finalization differs from the rejected package"
                    ),
                )
            placeholders = ",".join("?" for _ in relationship.excluded_source_ids)
            reappearing = connection.execute(
                f"""
                SELECT entry.source_id
                FROM retrieval_manifest_entries AS entry
                WHERE entry.retrieval_manifest_id = ?
                  AND entry.disposition = 'included'
                  AND entry.source_id IN ({placeholders})
                LIMIT 1
                """,  # noqa: S608
                (
                    row["retrieval_manifest_id"],
                    *relationship.excluded_source_ids,
                ),
            ).fetchone()
            if reappearing is not None:
                _add(
                    findings,
                    code="I4A-RECOVERY-CONTAMINATED-SOURCE",
                    table="context_recovery_relationships",
                    object_id=package_id,
                    task_id=row["task_id"],
                    retrieval_request_id=row["retrieval_request_id"],
                    retrieval_manifest_id=row["retrieval_manifest_id"],
                    context_package_id=package_id,
                    detail="an explicitly excluded contaminated source reappears",
                )
