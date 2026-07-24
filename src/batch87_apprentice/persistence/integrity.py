"""Read-only integrity inspection for the implemented B87-I1 schema."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import parse_json
from batch87_apprentice.common.errors import (
    IntegrityInspectionError,
    MigrationError,
    ValidationError,
)
from batch87_apprentice.common.hashing import sha256_bytes

from .contracts import (
    ControlledResiliencePayload,
    RecordEnvelope,
    ReferenceAnchor,
    controlled_resilience_content_hash,
    record_content_hash,
)
from .migrations import MigrationRunner
from .transactions import PersistenceKernel


@dataclass(frozen=True, slots=True)
class IntegrityFinding:
    severity: str
    code: str
    table: str
    object_id: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    database_path: str
    migration_count: int
    findings: tuple[IntegrityFinding, ...]

    @property
    def ok(self) -> bool:
        return all(finding.severity != "error" for finding in self.findings)

    @property
    def error_count(self) -> int:
        return sum(finding.severity == "error" for finding in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(finding.severity == "warning" for finding in self.findings)


def _finding(
    findings: list[IntegrityFinding],
    *,
    severity: str,
    code: str,
    table: str,
    object_id: str | None,
    detail: str,
) -> None:
    findings.append(
        IntegrityFinding(
            severity=severity,
            code=code,
            table=table,
            object_id=object_id,
            detail=detail,
        )
    )


def _envelope_from_row(row: sqlite3.Row) -> RecordEnvelope:
    fields = RecordEnvelope.__dataclass_fields__
    return RecordEnvelope(**{field: row[field] for field in fields})


def _payload_from_row(row: sqlite3.Row) -> ControlledResiliencePayload:
    fields = ControlledResiliencePayload.__dataclass_fields__
    return ControlledResiliencePayload(**{field: row[field] for field in fields})


class IntegrityInspector:
    """Inspect migrations, SQLite structure, hashes, and I1 classifications."""

    def __init__(
        self,
        kernel: PersistenceKernel,
        *,
        migration_runner: MigrationRunner | None = None,
    ) -> None:
        self._kernel = kernel
        self._migration_runner = migration_runner or MigrationRunner(kernel.config)

    def inspect(self) -> IntegrityReport:
        findings: list[IntegrityFinding] = []
        migration_count = 0
        try:
            migrations = self._migration_runner.verify_history()
            migration_count = len(migrations)
        except MigrationError as exc:
            _finding(
                findings,
                severity="error",
                code="migration_history_invalid",
                table="schema_migrations",
                object_id=None,
                detail=str(exc),
            )

        try:
            self._kernel.read(
                lambda connection: self._inspect_connection(connection, findings)
            )
        except Exception as exc:
            if isinstance(exc, IntegrityInspectionError):
                raise
            raise IntegrityInspectionError(
                "read-only database integrity inspection failed"
            ) from exc

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
        return IntegrityReport(
            database_path=str(self._kernel.config.path),
            migration_count=migration_count,
            findings=ordered,
        )

    def _inspect_connection(
        self,
        connection: sqlite3.Connection,
        findings: list[IntegrityFinding],
    ) -> None:
        self._inspect_sqlite(connection, findings)
        self._inspect_evidence(connection, findings)
        self._inspect_anchors(connection, findings)
        self._inspect_records(connection, findings)
        self._inspect_controlled_classification(connection, findings)

    @staticmethod
    def _inspect_sqlite(
        connection: sqlite3.Connection,
        findings: list[IntegrityFinding],
    ) -> None:
        results = tuple(connection.execute("PRAGMA integrity_check"))
        for row in results:
            if row[0] != "ok":
                _finding(
                    findings,
                    severity="error",
                    code="sqlite_integrity_failure",
                    table="sqlite",
                    object_id=None,
                    detail=str(row[0]),
                )
        for row in connection.execute("PRAGMA foreign_key_check"):
            _finding(
                findings,
                severity="error",
                code="foreign_key_violation",
                table=str(row["table"]),
                object_id=str(row["rowid"]),
                detail=f"parent={row['parent']}; foreign_key={row['fkid']}",
            )

    @staticmethod
    def _inspect_evidence(
        connection: sqlite3.Connection,
        findings: list[IntegrityFinding],
    ) -> None:
        inline_ids: set[str] = set()
        for row in connection.execute(
            """
            SELECT item.evidence_id, item.content_hash, item.byte_length,
                   item.storage_kind, item.integrity_status,
                   inline.content, inline.encoding
            FROM evidence_items AS item
            JOIN evidence_inline_text AS inline
              ON inline.evidence_id = item.evidence_id
            ORDER BY item.evidence_id
            """
        ):
            evidence_id = row["evidence_id"]
            inline_ids.add(evidence_id)
            exact = row["content"].encode("utf-8")
            if row["storage_kind"] != "inline_text" or row["encoding"] != "utf-8":
                _finding(
                    findings,
                    severity="error",
                    code="inline_evidence_storage_invalid",
                    table="evidence_inline_text",
                    object_id=evidence_id,
                    detail="inline row has incompatible storage metadata",
                )
            if row["content_hash"] != sha256_bytes(exact):
                _finding(
                    findings,
                    severity="error",
                    code="evidence_hash_mismatch",
                    table="evidence_items",
                    object_id=evidence_id,
                    detail="stored digest differs from exact inline UTF-8 bytes",
                )
            if row["byte_length"] != len(exact):
                _finding(
                    findings,
                    severity="error",
                    code="evidence_length_mismatch",
                    table="evidence_items",
                    object_id=evidence_id,
                    detail="stored byte length differs from exact inline UTF-8 bytes",
                )

        for row in connection.execute(
            """
            SELECT evidence_id, storage_kind, integrity_status
            FROM evidence_items
            ORDER BY evidence_id
            """
        ):
            evidence_id = row["evidence_id"]
            if row["storage_kind"] == "inline_text" and evidence_id not in inline_ids:
                _finding(
                    findings,
                    severity="error",
                    code="inline_evidence_content_missing",
                    table="evidence_items",
                    object_id=evidence_id,
                    detail="inline_text metadata has no inline content row",
                )
            if (
                row["storage_kind"] != "inline_text"
                and row["integrity_status"] == "valid"
            ):
                _finding(
                    findings,
                    severity="error",
                    code="noninline_evidence_false_validity",
                    table="evidence_items",
                    object_id=evidence_id,
                    detail=(
                        "metadata-only evidence claims verified integrity without "
                        "independently verified exact bytes"
                    ),
                )
            if row["integrity_status"] != "valid":
                _finding(
                    findings,
                    severity=(
                        "error"
                        if row["integrity_status"] == "mismatch"
                        else "warning"
                    ),
                    code="evidence_integrity_not_valid",
                    table="evidence_items",
                    object_id=evidence_id,
                    detail=f"integrity_status={row['integrity_status']}",
                )

    @staticmethod
    def _inspect_anchors(
        connection: sqlite3.Connection,
        findings: list[IntegrityFinding],
    ) -> None:
        for row in connection.execute(
            "SELECT * FROM governed_reference_anchors ORDER BY reference_id"
        ):
            reference_id = row["reference_id"]
            try:
                anchor = ReferenceAnchor(
                    reference_id=reference_id,
                    reference_kind=row["reference_kind"],
                    project_scope_id=row["project_scope_id"],
                    lifecycle_state=row["lifecycle_state"],
                    created_at=row["created_at"],
                    provenance_json=row["provenance_json"],
                    integrity_status=row["integrity_status"],
                )
                if row["content_hash"] != anchor.content_hash:
                    _finding(
                        findings,
                        severity="error",
                        code="anchor_hash_mismatch",
                        table="governed_reference_anchors",
                        object_id=reference_id,
                        detail="stored digest differs from canonical anchor content",
                    )
            except ValidationError as exc:
                _finding(
                    findings,
                    severity="error",
                    code="anchor_contract_invalid",
                    table="governed_reference_anchors",
                    object_id=reference_id,
                    detail=str(exc),
                )
            if row["lifecycle_state"] == "registered":
                _finding(
                    findings,
                    severity="warning",
                    code="anchor_unclaimed",
                    table="governed_reference_anchors",
                    object_id=reference_id,
                    detail="typed identity exists but no later operational owner has claimed it",
                )
            elif row["lifecycle_state"] == "claimed":
                _finding(
                    findings,
                    severity="error",
                    code="anchor_ownerless_claimed",
                    table="governed_reference_anchors",
                    object_id=reference_id,
                    detail="I1 has no operational owner table that can justify claimed state",
                )
            elif row["lifecycle_state"] == "invalid":
                _finding(
                    findings,
                    severity="error",
                    code="anchor_invalid",
                    table="governed_reference_anchors",
                    object_id=reference_id,
                    detail="anchor lifecycle is explicitly invalid",
                )
            elif row["lifecycle_state"] == "retired":
                _finding(
                    findings,
                    severity="warning",
                    code="anchor_retired",
                    table="governed_reference_anchors",
                    object_id=reference_id,
                    detail="anchor lifecycle is retired",
                )
            if row["integrity_status"] != "valid":
                _finding(
                    findings,
                    severity=(
                        "error"
                        if row["integrity_status"] == "mismatch"
                        else "warning"
                    ),
                    code="anchor_integrity_not_valid",
                    table="governed_reference_anchors",
                    object_id=reference_id,
                    detail=f"integrity_status={row['integrity_status']}",
                )

    @staticmethod
    def _inspect_records(
        connection: sqlite3.Connection,
        findings: list[IntegrityFinding],
    ) -> None:
        payloads = {
            row["record_id"]: row
            for row in connection.execute(
                "SELECT * FROM controlled_resilience_evidence"
            )
        }
        for row in connection.execute("SELECT * FROM records ORDER BY record_id"):
            record_id = row["record_id"]
            try:
                envelope = _envelope_from_row(row)
                if record_id in payloads:
                    payload = _payload_from_row(payloads[record_id])
                    expected = controlled_resilience_content_hash(envelope, payload)
                else:
                    expected = record_content_hash(envelope)
                if row["content_hash"] != expected:
                    _finding(
                        findings,
                        severity="error",
                        code="record_hash_mismatch",
                        table="records",
                        object_id=record_id,
                        detail="stored digest differs from canonical record content",
                    )
            except ValidationError as exc:
                _finding(
                    findings,
                    severity="error",
                    code="record_contract_invalid",
                    table="records",
                    object_id=record_id,
                    detail=str(exc),
                )
            if row["integrity_status"] == "mismatch":
                _finding(
                    findings,
                    severity="error",
                    code="record_integrity_mismatch",
                    table="records",
                    object_id=record_id,
                    detail="record is explicitly marked mismatched",
                )
            elif row["integrity_status"] == "unavailable":
                _finding(
                    findings,
                    severity="warning",
                    code="record_integrity_unavailable",
                    table="records",
                    object_id=record_id,
                    detail="record integrity is unavailable",
                )

    @staticmethod
    def _inspect_controlled_classification(
        connection: sqlite3.Connection,
        findings: list[IntegrityFinding],
    ) -> None:
        for row in connection.execute(
            """
            SELECT payload.*, record.record_family, record.record_type,
                   record.project_scope_id, record.lifecycle_state,
                   record.sensitivity_class, record.training_eligibility,
                   record.retrieval_policy_json
            FROM controlled_resilience_evidence AS payload
            JOIN records AS record ON record.record_id = payload.record_id
            ORDER BY payload.record_id
            """
        ):
            record_id = row["record_id"]
            try:
                retrieval_policy = parse_json(row["retrieval_policy_json"])
            except ValidationError:
                retrieval_policy = {}
            invalid = (
                row["record_family"] != "evaluation_evidence"
                or row["record_type"] != "controlled_governance_resilience_run"
                or row["project_scope_id"] is None
                or row["lifecycle_state"]
                not in {"observed", "reviewed", "approved", "archived"}
                or row["sensitivity_class"] != "restricted"
                or row["training_eligibility"] != "prohibited"
                or row["ordinary_memory_eligibility"] != "prohibited"
                or row["identity_eligibility"] != "prohibited"
                or retrieval_policy.get("ordinary_memory_eligibility")
                != "prohibited"
                or retrieval_policy.get("retrieval_mode") != "evaluation_only"
                or row["completion_state"] not in {"exploratory", "incomplete"}
            )
            if invalid:
                _finding(
                    findings,
                    severity="error",
                    code="controlled_classification_invalid",
                    table="controlled_resilience_evidence",
                    object_id=record_id,
                    detail="raw resilience classification or completion boundary is invalid",
                )

            for id_column, expected_kind in (
                ("experiment_id", "evaluation_experiment"),
                ("fixture_id", "evaluation_fixture"),
                ("context_manifest_id", "context_manifest"),
                ("model_invocation_id", "model_invocation"),
            ):
                anchor = connection.execute(
                    """
                    SELECT reference_kind, project_scope_id, lifecycle_state,
                           integrity_status
                    FROM governed_reference_anchors
                    WHERE reference_id = ?
                    """,
                    (row[id_column],),
                ).fetchone()
                if (
                    anchor is None
                    or anchor["reference_kind"] != expected_kind
                    or anchor["project_scope_id"] != row["project_scope_id"]
                    or anchor["lifecycle_state"] != "registered"
                    or anchor["integrity_status"] != "valid"
                ):
                    _finding(
                        findings,
                        severity="error",
                        code="controlled_anchor_invalid",
                        table="controlled_resilience_evidence",
                        object_id=record_id,
                        detail=f"{id_column} does not resolve to a valid in-scope {expected_kind}",
                    )

            if row["recovery_record_id"] is not None:
                recovery = connection.execute(
                    """
                    SELECT project_scope_id
                    FROM records
                    WHERE record_id = ?
                    """,
                    (row["recovery_record_id"],),
                ).fetchone()
                if (
                    recovery is None
                    or recovery["project_scope_id"] != row["project_scope_id"]
                ):
                    _finding(
                        findings,
                        severity="error",
                        code="controlled_recovery_invalid",
                        table="controlled_resilience_evidence",
                        object_id=record_id,
                        detail="recovery record is missing or outside project scope",
                    )

            evidence = {
                evidence_row["evidence_id"]: evidence_row
                for evidence_row in connection.execute(
                    """
                    SELECT evidence_id, evidence_kind, sensitivity_class,
                           integrity_status
                    FROM evidence_items
                    WHERE evidence_id IN (?, ?)
                    """,
                    (
                        row["raw_prompt_evidence_id"],
                        row["raw_output_evidence_id"],
                    ),
                )
            }
            for evidence_id, expected_kind in (
                (row["raw_prompt_evidence_id"], "controlled_prompt"),
                (row["raw_output_evidence_id"], "controlled_output"),
            ):
                evidence_row = evidence.get(evidence_id)
                if (
                    evidence_row is None
                    or evidence_row["evidence_kind"] != expected_kind
                    or evidence_row["sensitivity_class"] != "restricted"
                    or evidence_row["integrity_status"] != "valid"
                ):
                    _finding(
                        findings,
                        severity="error",
                        code="controlled_evidence_invalid",
                        table="controlled_resilience_evidence",
                        object_id=record_id,
                        detail=f"{expected_kind} is missing or has weakened integrity",
                    )

            links = tuple(
                connection.execute(
                    """
                    SELECT record_id, evidence_id, relationship
                    FROM record_evidence_links
                    WHERE evidence_id IN (?, ?)
                    """,
                    (
                        row["raw_prompt_evidence_id"],
                        row["raw_output_evidence_id"],
                    ),
                )
            )
            prompt_links = tuple(
                link
                for link in links
                if link["record_id"] == record_id
                and link["evidence_id"] == row["raw_prompt_evidence_id"]
                and link["relationship"] == "evaluated_against"
            )
            output_links = tuple(
                link
                for link in links
                if link["record_id"] == record_id
                and link["evidence_id"] == row["raw_output_evidence_id"]
                and link["relationship"] == "produced_as"
            )
            for kind, mandatory_links in (
                ("prompt", prompt_links),
                ("output", output_links),
            ):
                if not mandatory_links:
                    _finding(
                        findings,
                        severity="error",
                        code=f"controlled_{kind}_link_missing",
                        table="record_evidence_links",
                        object_id=record_id,
                        detail=f"mandatory controlled {kind} relationship is absent",
                    )
                elif len(mandatory_links) > 1:
                    _finding(
                        findings,
                        severity="error",
                        code=f"controlled_{kind}_link_duplicate",
                        table="record_evidence_links",
                        object_id=record_id,
                        detail=f"mandatory controlled {kind} relationship is duplicated",
                    )

            for link in links:
                if link["evidence_id"] == row["raw_prompt_evidence_id"]:
                    if link["record_id"] != record_id:
                        code = "controlled_evidence_link_contamination"
                        detail = "raw controlled prompt is linked to another record"
                    elif link["relationship"] not in {
                        "evaluated_against",
                        "does_not_establish",
                    }:
                        code = "controlled_prompt_link_invalid"
                        detail = "raw controlled prompt relationship is invalid"
                    else:
                        continue
                elif link["evidence_id"] == row["raw_output_evidence_id"]:
                    if link["record_id"] != record_id:
                        code = "controlled_evidence_link_contamination"
                        detail = "raw controlled output is linked to another record"
                    elif link["relationship"] not in {
                        "produced_as",
                        "does_not_establish",
                    }:
                        code = "controlled_output_link_invalid"
                        detail = "raw controlled output relationship is invalid"
                    else:
                        continue
                else:
                    continue
                _finding(
                    findings,
                    severity="error",
                    code=code,
                    table="record_evidence_links",
                    object_id=record_id,
                    detail=detail,
                )
