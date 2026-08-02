"""Deterministic read-only integrity inspection for B87-I4-B."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from batch87_apprentice.common.errors import IntegrityInspectionError
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .store import InvocationStore


@dataclass(frozen=True, slots=True)
class InvocationIntegrityFinding:
    severity: str
    code: str
    model_invocation_id: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class InvocationIntegrityReport:
    database_path: str
    invocation_count: int
    findings: tuple[InvocationIntegrityFinding, ...]

    @property
    def ok(self) -> bool:
        return all(finding.severity != "error" for finding in self.findings)


class InvocationIntegrityInspector:
    """Reconstruct every invocation and verify cross-attempt invariants."""

    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel
        self._store = InvocationStore(kernel.config)

    @staticmethod
    def _inspect_connection(
        connection: sqlite3.Connection,
    ) -> InvocationIntegrityReport:
        findings: list[InvocationIntegrityFinding] = []
        identifiers = tuple(
            row["model_invocation_id"]
            for row in connection.execute(
                """
                SELECT model_invocation_id
                FROM model_invocations
                ORDER BY model_invocation_id
                """
            )
        )
        for identifier in identifiers:
            try:
                InvocationStore._reconstruct_connection(
                    connection,
                    identifier,
                )
            except Exception as exc:
                findings.append(
                    InvocationIntegrityFinding(
                        severity="error",
                        code="invocation_reconstruction_invalid",
                        model_invocation_id=identifier,
                        detail=str(exc),
                    )
                )

        for row in connection.execute(
            """
            SELECT child.model_invocation_id,
                   child.task_id AS child_task_id,
                   child.context_package_id AS child_context_id,
                   parent.task_id AS parent_task_id,
                   parent.context_package_id AS parent_context_id,
                   parent.current_status AS parent_status
            FROM model_invocations AS child
            LEFT JOIN model_invocations AS parent
              ON parent.model_invocation_id = child.retry_of_invocation_id
            WHERE child.retry_of_invocation_id IS NOT NULL
            ORDER BY child.model_invocation_id
            """
        ):
            if (
                row["parent_task_id"] is None
                or row["child_task_id"] != row["parent_task_id"]
                or row["child_context_id"] != row["parent_context_id"]
                or row["parent_status"]
                in {"prepared", "in_progress", "raw_output_captured"}
            ):
                findings.append(
                    InvocationIntegrityFinding(
                        severity="error",
                        code="retry_parent_invalid",
                        model_invocation_id=row["model_invocation_id"],
                        detail=(
                            "retry parent is absent, non-terminal, or belongs "
                            "to a different task/context binding"
                        ),
                    )
                )

        cycle_rows = tuple(
            connection.execute(
                """
                WITH RECURSIVE retry_chain(origin, current, path, cycle) AS (
                    SELECT model_invocation_id, retry_of_invocation_id,
                           model_invocation_id, 0
                    FROM model_invocations
                    WHERE retry_of_invocation_id IS NOT NULL
                    UNION ALL
                    SELECT chain.origin, parent.retry_of_invocation_id,
                           chain.path || ',' || parent.model_invocation_id,
                           instr(chain.path, parent.model_invocation_id) > 0
                    FROM retry_chain AS chain
                    JOIN model_invocations AS parent
                      ON parent.model_invocation_id = chain.current
                    WHERE chain.current IS NOT NULL AND chain.cycle = 0
                )
                SELECT DISTINCT origin
                FROM retry_chain
                WHERE cycle = 1
                ORDER BY origin
                """
            )
        )
        for row in cycle_rows:
            findings.append(
                InvocationIntegrityFinding(
                    severity="error",
                    code="retry_cycle",
                    model_invocation_id=row["origin"],
                    detail="retry relationships contain a cycle",
                )
            )

        ordered = tuple(
            sorted(
                findings,
                key=lambda finding: (
                    finding.severity,
                    finding.code,
                    finding.model_invocation_id or "",
                    finding.detail,
                ),
            )
        )
        return InvocationIntegrityReport(
            database_path="",
            invocation_count=len(identifiers),
            findings=ordered,
        )

    def inspect(self) -> InvocationIntegrityReport:
        try:
            def operation(
                connection: sqlite3.Connection,
            ) -> tuple[InvocationIntegrityReport, tuple[str, ...]]:
                connection.execute("BEGIN")
                identifiers = tuple(
                    row["model_invocation_id"]
                    for row in connection.execute(
                        """
                        SELECT model_invocation_id
                        FROM model_invocations
                        ORDER BY model_invocation_id
                        """
                    )
                )
                return self._inspect_connection(connection), identifiers

            report, identifiers = self._kernel.read(operation)
        except Exception as exc:
            if isinstance(exc, IntegrityInspectionError):
                raise
            raise IntegrityInspectionError(
                "model-invocation integrity inspection failed"
            ) from exc
        findings = list(report.findings)
        failed_identifiers = {
            finding.model_invocation_id
            for finding in findings
            if finding.severity == "error"
        }
        for identifier in identifiers:
            if identifier in failed_identifiers:
                continue
            try:
                self._store.reconstruct(identifier)
            except Exception as exc:
                findings.append(
                    InvocationIntegrityFinding(
                        severity="error",
                        code="invocation_parent_reconstruction_invalid",
                        model_invocation_id=identifier,
                        detail=str(exc),
                    )
                )
        return InvocationIntegrityReport(
            database_path=str(self._kernel.config.path),
            invocation_count=report.invocation_count,
            findings=tuple(
                sorted(
                    findings,
                    key=lambda finding: (
                        finding.severity,
                        finding.code,
                        finding.model_invocation_id or "",
                        finding.detail,
                    ),
                )
            ),
        )
