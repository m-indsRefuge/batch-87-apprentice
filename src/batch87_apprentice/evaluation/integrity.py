"""Read-only integrity inspection for B87-PRE-I5 evaluation evidence."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from batch87_apprentice.common.errors import IntegrityInspectionError
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .store import EvaluationStore


@dataclass(frozen=True, slots=True)
class EvaluationIntegrityFinding:
    severity: str
    code: str
    object_id: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class EvaluationIntegrityReport:
    database_path: str
    candidate_count: int
    configuration_count: int
    fixture_set_count: int
    plan_count: int
    run_count: int
    result_count: int
    findings: tuple[EvaluationIntegrityFinding, ...]

    @property
    def ok(self) -> bool:
        return all(finding.severity != "error" for finding in self.findings)


class EvaluationIntegrityInspector:
    """Verify registries, parent hashes, transitions, and exact reconstruction."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._kernel = PersistenceKernel(config)
        self._store = EvaluationStore(config)

    def inspect(self) -> EvaluationIntegrityReport:
        try:
            inventory = self._kernel.read(self._inventory)
        except Exception as exc:
            raise IntegrityInspectionError(
                "evaluation integrity inventory failed"
            ) from exc
        findings = list(inventory["findings"])

        for candidate_id in inventory["candidate_ids"]:
            try:
                self._store.reconstruct_candidate(candidate_id)
            except Exception as exc:
                findings.append(
                    EvaluationIntegrityFinding(
                        severity="error",
                        code="candidate_reconstruction_invalid",
                        object_id=candidate_id,
                        detail=str(exc),
                    )
                )
        for configuration_id in inventory["configuration_ids"]:
            try:
                self._store.reconstruct_configuration(configuration_id)
            except Exception as exc:
                findings.append(
                    EvaluationIntegrityFinding(
                        severity="error",
                        code="configuration_reconstruction_invalid",
                        object_id=configuration_id,
                        detail=str(exc),
                    )
                )
        for fixture_set_id, fixture_set_version in inventory["fixture_sets"]:
            try:
                self._store.reconstruct_fixture_set(
                    fixture_set_id, fixture_set_version
                )
            except Exception as exc:
                findings.append(
                    EvaluationIntegrityFinding(
                        severity="error",
                        code="fixture_set_reconstruction_invalid",
                        object_id=fixture_set_id,
                        detail=str(exc),
                    )
                )
        for plan_id in inventory["plan_ids"]:
            try:
                self._store.reconstruct_plan(plan_id)
            except Exception as exc:
                findings.append(
                    EvaluationIntegrityFinding(
                        severity="error",
                        code="plan_reconstruction_invalid",
                        object_id=plan_id,
                        detail=str(exc),
                    )
                )

        ordered = tuple(
            sorted(
                findings,
                key=lambda finding: (
                    finding.severity,
                    finding.code,
                    finding.object_id or "",
                    finding.detail,
                ),
            )
        )
        return EvaluationIntegrityReport(
            database_path=str(self._kernel.config.path),
            candidate_count=len(inventory["candidate_ids"]),
            configuration_count=len(inventory["configuration_ids"]),
            fixture_set_count=len(inventory["fixture_sets"]),
            plan_count=len(inventory["plan_ids"]),
            run_count=inventory["run_count"],
            result_count=inventory["result_count"],
            findings=ordered,
        )

    @staticmethod
    def _inventory(connection: sqlite3.Connection) -> dict[str, object]:
        connection.execute("BEGIN")
        findings: list[EvaluationIntegrityFinding] = []
        integrity_rows = tuple(
            tuple(row) for row in connection.execute("PRAGMA integrity_check")
        )
        if integrity_rows != (("ok",),):
            findings.append(
                EvaluationIntegrityFinding(
                    severity="error",
                    code="sqlite_integrity_invalid",
                    object_id=None,
                    detail=str(integrity_rows),
                )
            )
        for row in connection.execute("PRAGMA foreign_key_check"):
            findings.append(
                EvaluationIntegrityFinding(
                    severity="error",
                    code="foreign_key_invalid",
                    object_id=str(row[1]) if row[1] is not None else None,
                    detail=str(tuple(row)),
                )
            )
        return {
            "candidate_ids": tuple(
                row[0]
                for row in connection.execute(
                    "SELECT candidate_id FROM evaluation_candidates ORDER BY candidate_id"
                )
            ),
            "configuration_ids": tuple(
                row[0]
                for row in connection.execute(
                    """
                    SELECT configuration_id FROM evaluation_configurations
                    ORDER BY configuration_id
                    """
                )
            ),
            "fixture_sets": tuple(
                (row[0], row[1])
                for row in connection.execute(
                    """
                    SELECT fixture_set_id, fixture_set_version
                    FROM evaluation_fixture_sets
                    ORDER BY fixture_set_id, fixture_set_version
                    """
                )
            ),
            "plan_ids": tuple(
                row[0]
                for row in connection.execute(
                    "SELECT plan_id FROM evaluation_plans ORDER BY plan_id"
                )
            ),
            "run_count": connection.execute(
                "SELECT COUNT(*) FROM evaluation_runs"
            ).fetchone()[0],
            "result_count": connection.execute(
                "SELECT COUNT(*) FROM evaluation_results"
            ).fetchone()[0],
            "findings": tuple(findings),
        }
