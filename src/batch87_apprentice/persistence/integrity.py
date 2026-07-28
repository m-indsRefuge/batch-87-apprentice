"""Read-only integrity inspection for the implemented B87-I1 schema."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import (
    IntegrityInspectionError,
    MigrationError,
    ValidationError,
)
from batch87_apprentice.common.hashing import (
    sha256_bytes,
    sha256_canonical_json,
)

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
class TaskRuntimeIntegrityFinding:
    """An accepted I2 integrity finding with exact task/session attribution."""

    code: str
    severity: str
    table: str
    object_id: str | None
    task_id: str | None
    session_id: str | None
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
        self._inspect_task_runtime(connection, findings)
        self._inspect_construct_memory(connection, findings)
        self._inspect_self_episodic_memory(connection, findings)
        self._inspect_episode_correction_memory(connection, findings)
        self._inspect_developmental_derivation(connection, findings)
        self._inspect_session_task_memory(connection, findings)

    @staticmethod
    def _inspect_construct_memory(
        connection: sqlite3.Connection,
        findings: list[IntegrityFinding],
    ) -> None:
        from batch87_apprentice.memory.construct_integrity import (
            ConstructIntegrityInspector,
        )

        report = ConstructIntegrityInspector._inspect_connection(connection)
        for finding in report.findings:
            _finding(
                findings,
                severity=finding.severity,
                code="construct_memory_" + finding.code.lower().replace("-", "_"),
                table="construct_memory",
                object_id=finding.record_id,
                detail=finding.detail,
            )

    @staticmethod
    def _inspect_self_episodic_memory(
        connection: sqlite3.Connection,
        findings: list[IntegrityFinding],
    ) -> None:
        from batch87_apprentice.memory.self_episodic_integrity import (
            SelfEpisodicIntegrityInspector,
        )

        report = SelfEpisodicIntegrityInspector._inspect_connection(connection)
        for finding in report.findings:
            _finding(
                findings,
                severity=finding.severity,
                code="self_episodic_" + finding.code.lower().replace("-", "_"),
                table=finding.table,
                object_id=finding.record_id,
                detail=finding.detail,
            )

    @staticmethod
    def _inspect_episode_correction_memory(
        connection: sqlite3.Connection,
        findings: list[IntegrityFinding],
    ) -> None:
        from batch87_apprentice.memory.episode_correction_integrity import (
            EpisodeCorrectionIntegrityInspector,
        )

        report = EpisodeCorrectionIntegrityInspector._inspect_connection(connection)
        for finding in report.findings:
            _finding(
                findings,
                severity=finding.severity,
                code="episode_correction_" + finding.code.lower().replace("-", "_"),
                table="episode_correction_ledger",
                object_id=finding.record_id,
                detail=finding.detail,
            )

    @staticmethod
    def _inspect_developmental_derivation(
        connection: sqlite3.Connection,
        findings: list[IntegrityFinding],
    ) -> None:
        from batch87_apprentice.memory.developmental_derivation_integrity import (
            DevelopmentalDerivationIntegrityInspector,
        )

        report = DevelopmentalDerivationIntegrityInspector._inspect_connection(
            connection
        )
        for finding in report.findings:
            _finding(
                findings,
                severity=finding.severity,
                code=(
                    "developmental_derivation_"
                    + finding.code.lower().replace("-", "_")
                ),
                table=finding.table,
                object_id=finding.record_id,
                detail=finding.detail,
            )

    @staticmethod
    def _inspect_session_task_memory(
        connection: sqlite3.Connection,
        findings: list[IntegrityFinding],
    ) -> None:
        from batch87_apprentice.memory.session_task_integrity import (
            SessionTaskIntegrityInspector,
        )

        report = SessionTaskIntegrityInspector._inspect_connection(connection)
        for finding in report.findings:
            if finding.source == "i2":
                continue
            _finding(
                findings,
                severity=finding.severity,
                code="session_task_" + finding.code.lower().replace("-", "_"),
                table=finding.table,
                object_id=finding.object_id,
                detail=finding.detail,
            )

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
        from batch87_apprentice.memory.construct_contracts import (
            CONSTRUCT_PAYLOAD_TABLES,
            construct_memory_content_hash,
            payload_from_database,
        )
        from batch87_apprentice.memory.self_episodic_contracts import (
            FACTUAL_SELF_PAYLOAD_TABLES,
            factual_self_content_hash,
            payload_from_database as factual_self_payload_from_database,
        )
        from batch87_apprentice.memory.episode_correction_contracts import (
            C2_PAYLOAD_TABLES,
            correction_content_hash,
            correction_from_database,
            episode_content_hash,
            episode_from_database,
        )
        from batch87_apprentice.memory.developmental_derivation_contracts import (
            C3_PAYLOAD_TABLES,
            developmental_content_hash,
        )
        from batch87_apprentice.memory.developmental_derivation_repository import (
            DevelopmentalDerivationRepository,
        )
        from batch87_apprentice.memory.session_task_contracts import (
            ActiveUncertaintyPayload,
            active_uncertainty_content_hash,
        )

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
                elif row["record_type"] in CONSTRUCT_PAYLOAD_TABLES:
                    construct_row = connection.execute(
                        f"""
                        SELECT * FROM {CONSTRUCT_PAYLOAD_TABLES[row['record_type']]}
                        WHERE record_id = ?
                        """,
                        (record_id,),
                    ).fetchone()
                    if construct_row is None:
                        expected = record_content_hash(envelope)
                    else:
                        construct_payload = payload_from_database(
                            row["record_type"],
                            dict(construct_row),
                        )
                        expected = construct_memory_content_hash(
                            envelope,
                            construct_payload,
                        )
                elif (
                    row["record_family"] == "self_model"
                    and row["record_type"] in FACTUAL_SELF_PAYLOAD_TABLES
                ):
                    factual_row = connection.execute(
                        f"""
                        SELECT *
                        FROM {FACTUAL_SELF_PAYLOAD_TABLES[row['record_type']]}
                        WHERE record_id = ?
                        """,
                        (record_id,),
                    ).fetchone()
                    if factual_row is None:
                        expected = record_content_hash(envelope)
                    else:
                        evaluation_ids: tuple[str, ...] = ()
                        if row["record_type"] == "capability_observation":
                            evaluation_ids = tuple(
                                item["evaluation_record_id"]
                                for item in connection.execute(
                                    """
                                    SELECT evaluation_record_id
                                    FROM capability_observation_evaluations
                                    WHERE record_id = ?
                                    ORDER BY evaluation_order
                                    """,
                                    (record_id,),
                                )
                            )
                        elif row["record_type"] == "maturity_state":
                            evaluation_ids = tuple(
                                item["evaluation_record_id"]
                                for item in connection.execute(
                                    """
                                    SELECT evaluation_record_id
                                    FROM maturity_state_basis_evaluations
                                    WHERE record_id = ?
                                    ORDER BY evaluation_order
                                    """,
                                    (record_id,),
                                )
                            )
                        factual_payload = factual_self_payload_from_database(
                            row["record_type"],
                            dict(factual_row),
                            evaluation_record_ids=evaluation_ids,
                        )
                        expected = factual_self_content_hash(
                            envelope,
                            factual_payload,
                        )
                elif (
                    row["record_family"] == "episodic_memory"
                    and row["record_type"] in C2_PAYLOAD_TABLES
                    and connection.execute(
                        """
                        SELECT 1 FROM sqlite_master
                        WHERE type = 'table' AND name = ?
                        """,
                        (C2_PAYLOAD_TABLES[row["record_type"]],),
                    ).fetchone()
                    is not None
                ):
                    c2_row = connection.execute(
                        f"""
                        SELECT * FROM {C2_PAYLOAD_TABLES[row['record_type']]}
                        WHERE record_id = ?
                        """,
                        (record_id,),
                    ).fetchone()
                    if c2_row is None:
                        expected = record_content_hash(envelope)
                    elif row["record_type"] == "episode":
                        inputs = tuple(
                            item["evidence_id"]
                            for item in connection.execute(
                                """
                                SELECT evidence_id FROM episode_input_evidence
                                WHERE record_id = ? ORDER BY evidence_order
                                """,
                                (record_id,),
                            )
                        )
                        outputs = tuple(
                            item["evidence_id"]
                            for item in connection.execute(
                                """
                                SELECT evidence_id FROM episode_output_evidence
                                WHERE record_id = ? ORDER BY evidence_order
                                """,
                                (record_id,),
                            )
                        )
                        evaluations = tuple(
                            item["evaluation_record_id"]
                            for item in connection.execute(
                                """
                                SELECT evaluation_record_id
                                FROM episode_evaluation_anchors
                                WHERE record_id = ? ORDER BY evaluation_order
                                """,
                                (record_id,),
                            )
                        )
                        c2_payload = episode_from_database(
                            dict(c2_row),
                            input_evidence_ids=inputs,
                            output_evidence_ids=outputs,
                            evaluation_record_ids=evaluations,
                        )
                        expected = episode_content_hash(envelope, c2_payload)
                    else:
                        support = tuple(
                            item["evidence_id"]
                            for item in connection.execute(
                                """
                                SELECT evidence_id
                                FROM correction_supporting_evidence
                                WHERE record_id = ? ORDER BY evidence_order
                                """,
                                (record_id,),
                            )
                        )
                        c2_payload = correction_from_database(dict(c2_row))
                        expected = correction_content_hash(
                            envelope,
                            c2_payload,
                            support,
                        )
                elif (
                    row["record_family"] == "episodic_memory"
                    and row["record_type"] in C3_PAYLOAD_TABLES
                    and connection.execute(
                        """
                        SELECT 1 FROM sqlite_master
                        WHERE type = 'table' AND name = ?
                        """,
                        (C3_PAYLOAD_TABLES[row["record_type"]],),
                    ).fetchone()
                    is not None
                ):
                    c3_row = connection.execute(
                        f"""
                        SELECT 1 FROM {C3_PAYLOAD_TABLES[row['record_type']]}
                        WHERE record_id = ?
                        """,
                        (record_id,),
                    ).fetchone()
                    if c3_row is None:
                        expected = record_content_hash(envelope)
                    else:
                        c3_payload = (
                            DevelopmentalDerivationRepository
                            ._payload_from_connection(connection, row)
                        )
                        expected = developmental_content_hash(
                            envelope,
                            c3_payload,
                        )
                elif (
                    row["record_family"] == "session_task_memory"
                    and row["record_type"] == "active_uncertainty"
                    and connection.execute(
                        """
                        SELECT 1 FROM sqlite_master
                        WHERE type = 'table' AND name = 'active_uncertainties'
                        """
                    ).fetchone()
                    is not None
                ):
                    uncertainty_row = connection.execute(
                        """
                        SELECT * FROM active_uncertainties
                        WHERE record_id = ?
                        """,
                        (record_id,),
                    ).fetchone()
                    if uncertainty_row is None:
                        expected = record_content_hash(envelope)
                    else:
                        uncertainty = ActiveUncertaintyPayload(
                            record_id=uncertainty_row["record_id"],
                            task_id=uncertainty_row["task_id"],
                            session_id=uncertainty_row["session_id"],
                            project_scope_id=uncertainty_row["project_scope_id"],
                            uncertainty_statement=uncertainty_row[
                                "uncertainty_statement"
                            ],
                            impact=uncertainty_row["impact"],
                            resolution_required=bool(
                                uncertainty_row["resolution_required"]
                            ),
                            created_at=uncertainty_row["created_at"],
                            created_by_principal=uncertainty_row[
                                "created_by_principal"
                            ],
                        )
                        expected = active_uncertainty_content_hash(
                            envelope,
                            uncertainty,
                        )
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

    @staticmethod
    def _inspect_task_runtime(
        connection: sqlite3.Connection,
        findings: list[IntegrityFinding],
    ) -> None:
        """Expose the shared I2 projection through the accepted top-level shape."""

        seen: set[tuple[str, str, str, str | None, str]] = set()
        for finding in inspect_task_runtime_integrity(connection):
            identity = (
                finding.severity,
                finding.code,
                finding.table,
                finding.object_id,
                finding.detail,
            )
            if identity in seen:
                continue
            seen.add(identity)
            _finding(
                findings,
                severity=finding.severity,
                code=finding.code,
                table=finding.table,
                object_id=finding.object_id,
                detail=finding.detail,
            )

    @staticmethod
    def _inspect_task_runtime_raw(
        connection: sqlite3.Connection,
        findings: list[IntegrityFinding],
    ) -> None:
        """Verify canonical I2 records and complete governed transactions."""

        table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'governed_runtime_transactions'
            """
        ).fetchone()
        if table_exists is None:
            return

        canonical_tables = (
            (
                "permission_profiles",
                "permission_profile_id",
                "canonical_json",
                "content_hash",
            ),
            ("sessions", "session_id", "canonical_json", "content_hash"),
            (
                "operation_definitions",
                "operation_name",
                "canonical_json",
                "content_hash",
            ),
            (
                "authority_records",
                "authority_record_id",
                "canonical_json",
                "content_hash",
            ),
            (
                "authority_revocations",
                "authority_record_id",
                "canonical_json",
                "content_hash",
            ),
            (
                "human_approvals",
                "human_approval_id",
                "canonical_json",
                "content_hash",
            ),
            (
                "tasks",
                "task_id",
                "canonical_contract_json",
                "contract_hash",
            ),
            (
                "governance_decisions",
                "governance_decision_id",
                "canonical_json",
                "content_hash",
            ),
            (
                "task_stop_events",
                "stop_event_id",
                "canonical_json",
                "content_hash",
            ),
        )
        for table, id_column, json_column, hash_column in canonical_tables:
            for row in connection.execute(
                f"""
                SELECT {id_column}, {json_column}, {hash_column}
                FROM {table}
                ORDER BY {id_column}
                """
            ):
                object_id = row[id_column]
                try:
                    value = parse_json(row[json_column])
                    if (
                        not isinstance(value, dict)
                        or canonical_json_text(value) != row[json_column]
                    ):
                        raise ValidationError(
                            "stored value is not a canonical JSON object"
                        )
                    if row[hash_column] != sha256_canonical_json(value):
                        _finding(
                            findings,
                            severity="error",
                            code="task_runtime_hash_mismatch",
                            table=table,
                            object_id=object_id,
                            detail=(
                                f"{hash_column} differs from canonical "
                                f"{json_column}"
                            ),
                        )
                except ValidationError as exc:
                    _finding(
                        findings,
                        severity="error",
                        code="task_runtime_canonical_json_invalid",
                        table=table,
                        object_id=object_id,
                        detail=str(exc),
                    )

        for row in connection.execute(
            "SELECT * FROM governance_rules ORDER BY governance_rule_id"
        ):
            rule_value = {
                "configuration": parse_json(row["configuration_json"]),
                "description": row["description"],
                "governance_rule_id": row["governance_rule_id"],
                "kind": row["rule_kind"],
                "name": row["rule_name"],
                "version": row["rule_version"],
            }
            if row["content_hash"] != sha256_canonical_json(rule_value):
                _finding(
                    findings,
                    severity="error",
                    code="governance_rule_hash_mismatch",
                    table="governance_rules",
                    object_id=row["governance_rule_id"],
                    detail="stored digest differs from canonical rule content",
                )

        for row in connection.execute(
            """
            SELECT session.session_id, session.created_by_entity_id,
                   participant.role
            FROM sessions AS session
            LEFT JOIN session_participants AS participant
              ON participant.session_id = session.session_id
             AND participant.entity_id = session.created_by_entity_id
            ORDER BY session.session_id
            """
        ):
            if row["role"] != "operator":
                _finding(
                    findings,
                    severity="error",
                    code="session_operator_missing",
                    table="sessions",
                    object_id=row["session_id"],
                    detail="session creator is not preserved as operator participant",
                )

        for session_row in connection.execute(
            "SELECT session_id, session_status FROM sessions ORDER BY session_id"
        ):
            transitions = tuple(
                connection.execute(
                    """
                    SELECT sequence_number, from_status, to_status
                    FROM session_state_transitions
                    WHERE session_id = ?
                    ORDER BY sequence_number
                    """,
                    (session_row["session_id"],),
                )
            )
            valid = bool(transitions)
            previous: str | None = None
            for index, transition in enumerate(transitions):
                if (
                    transition["sequence_number"] != index
                    or transition["from_status"] != previous
                    or (index == 0 and transition["to_status"] != "open")
                    or (
                        index > 0
                        and (previous, transition["to_status"])
                        not in {
                            ("open", "paused"), ("open", "closed"),
                            ("open", "aborted"), ("paused", "open"),
                            ("paused", "closed"), ("paused", "aborted"),
                        }
                    )
                ):
                    valid = False
                    break
                previous = transition["to_status"]
            if not valid or previous != session_row["session_status"]:
                _finding(
                    findings, severity="error",
                    code="session_transition_history_invalid",
                    table="session_state_transitions",
                    object_id=session_row["session_id"],
                    detail="session transition history is not contiguous or does not match current status",
                )

        for row in connection.execute(
            """
            SELECT authority_record_id, evidence_ids_json
            FROM authority_records
            ORDER BY authority_record_id
            """
        ):
            declared = tuple(parse_json(row["evidence_ids_json"]))
            linked = tuple(
                (
                    evidence["evidence_id"],
                    evidence["evidence_order"],
                )
                for evidence in connection.execute(
                    """
                    SELECT evidence_id, evidence_order
                    FROM authority_record_evidence
                    WHERE authority_record_id = ?
                    ORDER BY evidence_order
                    """,
                    (row["authority_record_id"],),
                )
            )
            if tuple(evidence_id for evidence_id, _ in linked) != declared or tuple(
                order for _, order in linked
            ) != tuple(range(len(declared))):
                _finding(
                    findings,
                    severity="error",
                    code="authority_evidence_relationship_invalid",
                    table="authority_record_evidence",
                    object_id=row["authority_record_id"],
                    detail="linked evidence differs from the canonical authority order",
                )

        for row in connection.execute(
            "SELECT human_approval_id, evidence_ids_json, single_use, consumed_at, consumed_by_task_id, consumed_by_decision_id FROM human_approvals ORDER BY human_approval_id"
        ):
            declared = tuple(parse_json(row["evidence_ids_json"]))
            linked = tuple(
                (item["evidence_id"], item["evidence_order"])
                for item in connection.execute(
                    "SELECT evidence_id, evidence_order FROM human_approval_evidence WHERE human_approval_id = ? ORDER BY evidence_order",
                    (row["human_approval_id"],),
                )
            )
            if (
                tuple(item_id for item_id, _ in linked) != declared
                or tuple(order for _, order in linked) != tuple(range(len(declared)))
            ):
                _finding(
                    findings, severity="error",
                    code="human_approval_evidence_relationship_invalid",
                    table="human_approval_evidence",
                    object_id=row["human_approval_id"],
                    detail="linked evidence differs from canonical human approval order",
                )
            consumed_fields = (
                row["consumed_at"], row["consumed_by_task_id"],
                row["consumed_by_decision_id"],
            )
            if (
                (row["single_use"] == 0 and any(value is not None for value in consumed_fields))
                or (row["single_use"] == 1 and any(value is not None for value in consumed_fields) and not all(value is not None for value in consumed_fields))
            ):
                _finding(
                    findings, severity="error",
                    code="human_approval_consumption_invalid",
                    table="human_approvals",
                    object_id=row["human_approval_id"],
                    detail="human approval consumption fields are inconsistent",
                )

        transactions = connection.execute(
            """
            SELECT transaction_record.*, task.status AS task_status,
                   task.contract_hash, decision.governance_decision_id,
                   decision.decision, decision.content_hash AS decision_hash,
                   decision.task_contract_hash, decision.permission_profile_id,
                   decision.permission_profile_hash,
                   decision.runtime_execution_principal,
                   decision.governing_rule_ids_json,
                   decision.evidence_ids_json,
                   decision.authority_assessments_json,
                   decision.human_approval_assessments_json,
                   decision.evidence_assessments_json,
                   decision.requested_operation,
                   decision.operation_definition_hash,
                   profile.content_hash AS stored_profile_hash,
                   stop.stop_event_id, stop.content_hash AS stop_hash
            FROM governed_runtime_transactions AS transaction_record
            LEFT JOIN tasks AS task ON task.task_id = transaction_record.task_id
            LEFT JOIN governance_decisions AS decision
              ON decision.transaction_id = transaction_record.transaction_id
            LEFT JOIN permission_profiles AS profile
              ON profile.permission_profile_id = decision.permission_profile_id
            LEFT JOIN task_stop_events AS stop
              ON stop.transaction_id = transaction_record.transaction_id
            ORDER BY transaction_record.transaction_id
            """
        )
        for row in transactions:
            transaction_id = row["transaction_id"]
            if (
                row["task_status"] is None
                or row["governance_decision_id"] is None
                or row["status"] == "in_progress"
            ):
                _finding(
                    findings,
                    severity="error",
                    code="task_runtime_transaction_incomplete",
                    table="governed_runtime_transactions",
                    object_id=transaction_id,
                    detail="transaction lacks a final task or governance decision",
                )
                continue

            state_valid = (
                row["status"] == "committed"
                and row["task_status"] in {"active", "completed", "failed"}
                and row["decision"] == "allow"
                and row["stop_event_id"] is None
            ) or (
                row["status"] == "stopped"
                and row["task_status"] == "stopped"
                and row["decision"] != "allow"
                and row["stop_event_id"] is not None
            )
            if not state_valid:
                _finding(
                    findings,
                    severity="error",
                    code="task_runtime_state_inconsistent",
                    table="governed_runtime_transactions",
                    object_id=transaction_id,
                    detail="transaction, task, decision, and stop states disagree",
                )

            transitions = tuple(
                connection.execute(
                    """
                    SELECT sequence_number, from_status, to_status
                    FROM task_state_transitions
                    WHERE task_id = ?
                    ORDER BY sequence_number
                    """,
                    (row["task_id"],),
                )
            )
            expected_terminal = row["task_status"]
            valid_transitions = bool(transitions)
            previous: str | None = None
            allowed_task_transitions = {
                (None, "pending"),
                ("pending", "active"), ("pending", "stopped"),
                ("pending", "failed"), ("active", "completed"),
                ("active", "stopped"), ("active", "failed"),
            }
            for index, transition in enumerate(transitions):
                pair = (transition["from_status"], transition["to_status"])
                if (
                    transition["sequence_number"] != index
                    or transition["from_status"] != previous
                    or pair not in allowed_task_transitions
                ):
                    valid_transitions = False
                    break
                previous = transition["to_status"]
            if not valid_transitions or previous != expected_terminal:
                _finding(
                    findings, severity="error",
                    code="task_transition_history_invalid",
                    table="task_state_transitions", object_id=row["task_id"],
                    detail="task transition history is not contiguous or does not match current status",
                )

            if (
                row["contract_hash"] != row["task_contract_hash"]
                or row["permission_profile_hash"] != row["stored_profile_hash"]
                or row["execution_principal"]
                != row["runtime_execution_principal"]
            ):
                _finding(
                    findings,
                    severity="error",
                    code="task_runtime_input_hash_mismatch",
                    table="governance_decisions",
                    object_id=row["governance_decision_id"],
                    detail="decision input hash does not match its persisted input",
                )

            operation = connection.execute(
                "SELECT content_hash FROM operation_definitions WHERE operation_name = ?",
                (row["requested_operation"],),
            ).fetchone()
            operation_valid = (
                operation is not None
                and operation["content_hash"] == row["operation_definition_hash"]
            ) or (
                operation is None
                and row["decision"] == "stop"
                and row["operation_definition_hash"] == "0" * 64
            )
            if not operation_valid:
                _finding(
                    findings, severity="error",
                    code="decision_operation_definition_invalid",
                    table="governance_decisions",
                    object_id=row["governance_decision_id"],
                    detail="decision operation definition is missing or hash-mismatched",
                )

            authority_relationships = [
                {
                    "applicable": item["validation_status"] == "applicable",
                    "authority_class": item["authority_class"],
                    "claimed_authority_id": item["claimed_authority_id"],
                    "resolved_record_hash": item["content_hash"],
                    "result_code": item["validation_status"],
                }
                for item in connection.execute(
                    """
                    SELECT rel.*, authority.authority_class, authority.content_hash
                    FROM governance_decision_authority_inputs AS rel
                    LEFT JOIN authority_records AS authority
                      ON authority.authority_record_id = rel.resolved_authority_record_id
                    WHERE rel.governance_decision_id = ? ORDER BY rel.input_order
                    """,
                    (row["governance_decision_id"],),
                )
            ]
            if authority_relationships != parse_json(row["authority_assessments_json"]):
                _finding(
                    findings, severity="error",
                    code="decision_authority_relationship_invalid",
                    table="governance_decision_authority_inputs",
                    object_id=row["governance_decision_id"],
                    detail="authority relationships differ from canonical assessments",
                )

            approval_relationships = [
                {
                    "applicable": item["validation_status"] == "applicable",
                    "claimed_human_approval_id": item["claimed_human_approval_id"],
                    "consumed": bool(item["consumed"]),
                    "resolved_record_hash": item["content_hash"],
                    "selected": bool(item["selected"]),
                    "result_code": item["validation_status"],
                }
                for item in connection.execute(
                    """
                    SELECT rel.*, approval.content_hash
                    FROM governance_decision_human_approvals AS rel
                    LEFT JOIN human_approvals AS approval
                      ON approval.human_approval_id = rel.resolved_human_approval_id
                    WHERE rel.governance_decision_id = ? ORDER BY rel.input_order
                    """,
                    (row["governance_decision_id"],),
                )
            ]
            if approval_relationships != parse_json(row["human_approval_assessments_json"]):
                _finding(
                    findings, severity="error",
                    code="decision_human_approval_relationship_invalid",
                    table="governance_decision_human_approvals",
                    object_id=row["governance_decision_id"],
                    detail="human approval relationships differ from canonical assessments",
                )

            evidence_relationships = [
                {
                    "available": item["validation_status"] == "available",
                    "input_kind": item["input_kind"],
                    "required_evidence_id": item["required_evidence_id"],
                }
                for item in connection.execute(
                    "SELECT * FROM governance_decision_evidence WHERE governance_decision_id = ? ORDER BY input_order",
                    (row["governance_decision_id"],),
                )
            ]
            if evidence_relationships != parse_json(row["evidence_assessments_json"]):
                _finding(
                    findings, severity="error",
                    code="decision_evidence_assessment_relationship_invalid",
                    table="governance_decision_evidence",
                    object_id=row["governance_decision_id"],
                    detail="evidence relationships differ from canonical assessments",
                )

            linked_rules = [
                rule["governance_rule_id"]
                for rule in connection.execute(
                    """
                    SELECT governance_rule_id
                    FROM governance_decision_rules
                    WHERE governance_decision_id = ?
                    ORDER BY rule_order
                    """,
                    (row["governance_decision_id"],),
                )
            ]
            if linked_rules != parse_json(row["governing_rule_ids_json"]):
                _finding(
                    findings,
                    severity="error",
                    code="decision_rule_relationship_invalid",
                    table="governance_decision_rules",
                    object_id=row["governance_decision_id"],
                    detail="decision rule links differ from canonical rule identifiers",
                )

            resolved_evidence = tuple(
                dict.fromkeys(
                    evidence["resolved_evidence_id"]
                    for evidence in connection.execute(
                        """
                        SELECT resolved_evidence_id
                        FROM governance_decision_evidence
                        WHERE governance_decision_id = ?
                          AND resolved_evidence_id IS NOT NULL
                        ORDER BY input_order
                        """,
                        (row["governance_decision_id"],),
                    )
                )
            )
            if list(resolved_evidence) != parse_json(row["evidence_ids_json"]):
                _finding(
                    findings,
                    severity="error",
                    code="decision_evidence_relationship_invalid",
                    table="governance_decision_evidence",
                    object_id=row["governance_decision_id"],
                    detail="decision evidence links differ from canonical evidence identifiers",
                )

            structured_failures = parse_json(row["structured_failure_json"])
            transaction_value = {
                "completed_at": row["completed_at"],
                "decision_hash": row["decision_hash"],
                "execution_principal": row["execution_principal"],
                "runtime_instance_id": row["runtime_instance_id"],
                "started_at": row["started_at"],
                "status": row["status"],
                "stop_hash": row["stop_hash"],
                "structured_failures": structured_failures,
                "task_contract_hash": row["contract_hash"],
                "task_id": row["task_id"],
                "transaction_id": transaction_id,
            }
            if row["content_hash"] != sha256_canonical_json(transaction_value):
                _finding(
                    findings,
                    severity="error",
                    code="task_runtime_transaction_hash_mismatch",
                    table="governed_runtime_transactions",
                    object_id=transaction_id,
                    detail="transaction digest differs from canonical reconstruction",
                )


def _task_runtime_task_target(
    connection: sqlite3.Connection,
    task_id: str,
) -> tuple[str, str | None]:
    row = connection.execute(
        "SELECT session_id FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    return task_id, None if row is None else row["session_id"]


def _task_runtime_decision_targets(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[Any, ...],
) -> set[tuple[str, str | None]]:
    return {
        (row["task_id"], row["session_id"])
        for row in connection.execute(query, parameters)
    }


def _task_runtime_finding_targets(
    connection: sqlite3.Connection,
    finding: IntegrityFinding,
) -> set[tuple[str | None, str | None]]:
    """Resolve only authoritative I2 relationships; never infer broad scope."""

    object_id = finding.object_id
    if object_id is None:
        return {(None, None)}

    if finding.table in {"sessions", "session_state_transitions"}:
        return {(None, object_id)}

    if finding.table in {"tasks", "task_state_transitions"}:
        return {_task_runtime_task_target(connection, object_id)}

    if finding.table == "governed_runtime_transactions":
        row = connection.execute(
            """
            SELECT transaction_record.task_id, task.session_id
            FROM governed_runtime_transactions AS transaction_record
            LEFT JOIN tasks AS task
              ON task.task_id = transaction_record.task_id
            WHERE transaction_record.transaction_id = ?
            """,
            (object_id,),
        ).fetchone()
        return (
            {(None, None)}
            if row is None
            else {(row["task_id"], row["session_id"])}
        )

    if finding.table in {
        "governance_decisions",
        "governance_decision_authority_inputs",
        "governance_decision_human_approvals",
        "governance_decision_evidence",
        "governance_decision_rules",
    }:
        targets = _task_runtime_decision_targets(
            connection,
            """
            SELECT task_id, session_id
            FROM governance_decisions
            WHERE governance_decision_id = ?
            """,
            (object_id,),
        )
        return targets or {(None, None)}

    if finding.table == "task_stop_events":
        row = connection.execute(
            """
            SELECT stop.task_id, task.session_id
            FROM task_stop_events AS stop
            LEFT JOIN tasks AS task ON task.task_id = stop.task_id
            WHERE stop.stop_event_id = ?
            """,
            (object_id,),
        ).fetchone()
        return (
            {(None, None)}
            if row is None
            else {(row["task_id"], row["session_id"])}
        )

    if finding.table == "permission_profiles":
        targets = _task_runtime_decision_targets(
            connection,
            """
            SELECT task_id, session_id
            FROM governance_decisions
            WHERE permission_profile_id = ?
            ORDER BY task_id
            """,
            (object_id,),
        )
        return targets or {(None, None)}

    if finding.table == "operation_definitions":
        targets = _task_runtime_decision_targets(
            connection,
            """
            SELECT task_id, session_id
            FROM governance_decisions
            WHERE requested_operation = ?
            ORDER BY task_id
            """,
            (object_id,),
        )
        return targets or {(None, None)}

    if finding.table == "governance_rules":
        targets = _task_runtime_decision_targets(
            connection,
            """
            SELECT decision_record.task_id, decision_record.session_id
            FROM governance_decision_rules AS relationship
            JOIN governance_decisions AS decision_record
              ON decision_record.governance_decision_id =
                 relationship.governance_decision_id
            WHERE relationship.governance_rule_id = ?
            ORDER BY decision_record.task_id
            """,
            (object_id,),
        )
        return targets or {(None, None)}

    if finding.table in {
        "authority_records",
        "authority_revocations",
        "authority_record_evidence",
    }:
        targets = _task_runtime_decision_targets(
            connection,
            """
            SELECT DISTINCT decision_record.task_id, decision_record.session_id
            FROM governance_decision_authority_inputs AS relationship
            JOIN governance_decisions AS decision_record
              ON decision_record.governance_decision_id =
                 relationship.governance_decision_id
            WHERE relationship.claimed_authority_id = ?
               OR relationship.resolved_authority_record_id = ?
            ORDER BY decision_record.task_id
            """,
            (object_id, object_id),
        )
        direct = connection.execute(
            """
            SELECT task_id
            FROM authority_records
            WHERE authority_record_id = ? AND task_id IS NOT NULL
            """,
            (object_id,),
        ).fetchone()
        if direct is not None:
            targets.add(
                _task_runtime_task_target(connection, direct["task_id"])
            )
        return targets or {(None, None)}

    if finding.table in {
        "human_approvals",
        "human_approval_evidence",
    }:
        targets = _task_runtime_decision_targets(
            connection,
            """
            SELECT DISTINCT decision_record.task_id, decision_record.session_id
            FROM governance_decision_human_approvals AS relationship
            JOIN governance_decisions AS decision_record
              ON decision_record.governance_decision_id =
                 relationship.governance_decision_id
            WHERE relationship.claimed_human_approval_id = ?
               OR relationship.resolved_human_approval_id = ?
            ORDER BY decision_record.task_id
            """,
            (object_id, object_id),
        )
        approval = connection.execute(
            """
            SELECT task_id, consumed_by_task_id, consumed_by_decision_id
            FROM human_approvals
            WHERE human_approval_id = ?
            """,
            (object_id,),
        ).fetchone()
        if approval is not None:
            for task_id in (
                approval["task_id"],
                approval["consumed_by_task_id"],
            ):
                if task_id is not None:
                    targets.add(
                        _task_runtime_task_target(connection, task_id)
                    )
            if approval["consumed_by_decision_id"] is not None:
                targets.update(
                    _task_runtime_decision_targets(
                        connection,
                        """
                        SELECT task_id, session_id
                        FROM governance_decisions
                        WHERE governance_decision_id = ?
                        """,
                        (approval["consumed_by_decision_id"],),
                    )
                )
        return targets or {(None, None)}

    return {(None, None)}


def inspect_task_runtime_integrity(
    connection: sqlite3.Connection,
) -> tuple[TaskRuntimeIntegrityFinding, ...]:
    """Return the single accepted I2 integrity result with exact attribution."""

    raw_findings: list[IntegrityFinding] = []
    IntegrityInspector._inspect_task_runtime_raw(connection, raw_findings)
    attributed: set[TaskRuntimeIntegrityFinding] = set()
    for finding in raw_findings:
        for task_id, session_id in _task_runtime_finding_targets(
            connection,
            finding,
        ):
            attributed.add(
                TaskRuntimeIntegrityFinding(
                    code=finding.code,
                    severity=finding.severity,
                    table=finding.table,
                    object_id=finding.object_id,
                    task_id=task_id,
                    session_id=session_id,
                    detail=finding.detail,
                )
            )
    return tuple(
        sorted(
            attributed,
            key=lambda finding: (
                finding.code,
                finding.table,
                finding.object_id or "",
                finding.task_id or "",
                finding.session_id or "",
                finding.detail,
            ),
        )
    )
