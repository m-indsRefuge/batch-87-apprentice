"""Governed persistence and read-only projection for B87-I3-D."""

from __future__ import annotations

from collections.abc import Mapping
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import (
    IntegrityInspectionError,
    NotFoundError,
    ValidationError,
)
from batch87_apprentice.common.hashing import (
    sha256_canonical_json,
)
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.contracts import RecordEnvelope
from batch87_apprentice.persistence.repositories import _insert_record
from batch87_apprentice.persistence.task_runtime_store import TaskRuntimeStore
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .kernel import _insert_initial_memory_state
from .session_task_contracts import (
    TASK_MEMORY_MODES,
    TASK_MEMORY_REASON_ORDER,
    ActiveUncertaintyPayload,
    TaskContextFinalization,
    TaskContextItem,
    TaskMemoryEligibilityDecision,
    TypedSourceReference,
    UncertaintyResolution,
    active_uncertainty_content_hash,
    validate_active_uncertainty_pair,
)


_SESSION_INTEGRITY_REASON_ORDER = (
    "session_scoped_i3d_findings",
    "task_integrity_invalid",
    "authoritative_i2_integrity_findings",
    "authoritative_i2_unverified",
    "i2_reconstruction_error",
    "task_scoped_i3d_findings",
)


def _source_columns(source: TypedSourceReference) -> tuple[str | None, ...]:
    return (
        source.source_kind,
        source.memory_record_id,
        source.evidence_id,
        source.governance_rule_id,
    )


def _source_from_row(row: Mapping[str, Any]) -> TypedSourceReference:
    return TypedSourceReference(
        memory_record_id=row.get("source_memory_record_id"),
        evidence_id=row.get("source_evidence_id"),
        governance_rule_id=row.get("source_governance_rule_id"),
    )


def _record_envelope(row: Mapping[str, Any]) -> RecordEnvelope:
    return RecordEnvelope(
        record_id=row["record_id"],
        record_family=row["record_family"],
        record_type=row["record_type"],
        schema_version=row["schema_version"],
        construct_scope_id=row["construct_scope_id"],
        project_scope_id=row["project_scope_id"],
        subject_entity_id=row["subject_entity_id"],
        session_id=row["session_id"],
        task_id=row["task_id"],
        lifecycle_state=row["lifecycle_state"],
        approval_status=row["approval_status"],
        authority_class=row["authority_class"],
        certainty_class=row["certainty_class"],
        sensitivity_class=row["sensitivity_class"],
        privacy_class=row["privacy_class"],
        retention_class=row["retention_class"],
        training_eligibility=row["training_eligibility"],
        created_at=row["created_at"],
        created_by_entity_id=row["created_by_entity_id"],
        created_by_runtime_id=row["created_by_runtime_id"],
        effective_from=row["effective_from"],
        effective_until=row["effective_until"],
        review_due_at=row["review_due_at"],
        supersedes_record_id=row["supersedes_record_id"],
        superseded_by_record_id=row["superseded_by_record_id"],
        previous_version_id=row["previous_version_id"],
        source_kind=row["source_kind"],
        provenance_summary=row["provenance_summary"],
        retrieval_policy_json=row["retrieval_policy_json"],
        deletion_policy_json=row["deletion_policy_json"],
        agent_write_policy=row["agent_write_policy"],
        integrity_status=row["integrity_status"],
        deleted_at=row["deleted_at"],
        deletion_basis=row["deletion_basis"],
    )


class SessionTaskMemoryRepository:
    """Own I3-D writes and deterministic projections without I2 mutation."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._kernel = PersistenceKernel(config)
        self._task_runtime = TaskRuntimeStore(config)

    def add_context_item(self, item: TaskContextItem) -> str:
        if not isinstance(item, TaskContextItem):
            raise TypeError("item must be a TaskContextItem")

        def operation(connection: sqlite3.Connection) -> None:
            source_kind, memory_id, evidence_id, rule_id = _source_columns(
                item.source
            )
            connection.execute(
                """
                INSERT INTO task_context_items (
                    context_item_id, task_id, session_id, project_scope_id,
                    context_kind, source_kind, source_memory_record_id,
                    source_evidence_id, source_governance_rule_id,
                    injection_order, required, content_hash, created_at,
                    created_by_principal, canonical_json, canonical_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.context_item_id,
                    item.task_id,
                    item.session_id,
                    item.project_scope_id,
                    item.context_kind,
                    source_kind,
                    memory_id,
                    evidence_id,
                    rule_id,
                    item.injection_order,
                    int(item.required),
                    item.content_hash,
                    item.created_at,
                    item.created_by_principal,
                    item.canonical_json,
                    item.canonical_hash,
                ),
            )

        self._kernel.write(operation)
        return item.canonical_hash

    def finalize_context(
        self,
        task_id: str,
        *,
        finalization_id: str,
        finalized_at: str,
        finalized_by_principal: str,
    ) -> str:
        validate_identifier(task_id, field="task_id")
        validate_identifier(finalization_id, field="finalization_id")
        parse_canonical_utc(finalized_at, field="finalized_at")

        def operation(connection: sqlite3.Connection) -> str:
            task = connection.execute(
                """
                SELECT task.task_id, task.session_id, task.project_scope_id
                FROM tasks AS task
                WHERE task.task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if task is None:
                raise NotFoundError(f"task not found: {task_id}")
            items = tuple(
                connection.execute(
                    """
                    SELECT context_item_id, injection_order, canonical_hash
                    FROM task_context_items
                    WHERE task_id = ?
                    ORDER BY injection_order
                    """,
                    (task_id,),
                )
            )
            if tuple(row["injection_order"] for row in items) != tuple(
                range(len(items))
            ):
                raise ValidationError(
                    "task context cannot finalize with a gapped order"
                )
            finalization = TaskContextFinalization(
                finalization_id=finalization_id,
                task_id=task_id,
                session_id=task["session_id"],
                project_scope_id=task["project_scope_id"],
                ordered_item_ids=tuple(
                    row["context_item_id"] for row in items
                ),
                ordered_item_hashes=tuple(
                    row["canonical_hash"] for row in items
                ),
                finalized_at=finalized_at,
                finalized_by_principal=finalized_by_principal,
            )
            connection.execute(
                """
                INSERT INTO task_context_finalizations (
                    finalization_id, task_id, session_id, project_scope_id,
                    item_count, finalized_at, finalized_by_principal,
                    canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finalization.finalization_id,
                    finalization.task_id,
                    finalization.session_id,
                    finalization.project_scope_id,
                    len(finalization.ordered_item_ids),
                    finalization.finalized_at,
                    finalization.finalized_by_principal,
                    finalization.canonical_json,
                    finalization.content_hash,
                ),
            )
            return finalization.content_hash

        return self._kernel.write(operation)

    def create_uncertainty(
        self,
        envelope: RecordEnvelope,
        payload: ActiveUncertaintyPayload,
        *,
        lifecycle_transition_id: str,
        approval_transition_id: str,
        changed_by_principal: str,
        changed_by_entity_id: str,
        reason_code: str = "task_uncertainty_observed",
    ) -> str:
        validate_active_uncertainty_pair(envelope, payload)
        if changed_by_principal != payload.created_by_principal:
            raise ValidationError(
                "uncertainty creator and lifecycle principal must match"
            )
        if envelope.created_by_entity_id != changed_by_entity_id:
            raise ValidationError(
                "uncertainty creator identity must match the envelope"
            )
        digest = active_uncertainty_content_hash(envelope, payload)

        def operation(connection: sqlite3.Connection) -> None:
            _insert_record(connection, envelope, content_hash=digest)
            connection.execute(
                """
                INSERT INTO active_uncertainties (
                    record_id, task_id, session_id, project_scope_id,
                    uncertainty_statement, impact, resolution_required,
                    created_at, created_by_principal, canonical_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.record_id,
                    payload.task_id,
                    payload.session_id,
                    payload.project_scope_id,
                    payload.uncertainty_statement,
                    payload.impact,
                    int(payload.resolution_required),
                    payload.created_at,
                    payload.created_by_principal,
                    payload.canonical_json,
                ),
            )
            _insert_initial_memory_state(
                connection,
                payload.record_id,
                lifecycle_transition_id=lifecycle_transition_id,
                approval_transition_id=approval_transition_id,
                changed_at=payload.created_at,
                changed_by_principal=changed_by_principal,
                changed_by_entity_id=changed_by_entity_id,
                reason_code=reason_code,
            )

        self._kernel.write(operation)
        return digest

    def resolve_uncertainty(self, resolution: UncertaintyResolution) -> str:
        if not isinstance(resolution, UncertaintyResolution):
            raise TypeError("resolution must be an UncertaintyResolution")

        def operation(connection: sqlite3.Connection) -> None:
            _, memory_id, evidence_id, _ = _source_columns(resolution.source)
            connection.execute(
                """
                INSERT INTO uncertainty_resolutions (
                    resolution_id, uncertainty_record_id, task_id, session_id,
                    project_scope_id, source_kind, source_memory_record_id,
                    source_evidence_id, source_content_hash, resolved_at,
                    created_by_principal, canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolution.resolution_id,
                    resolution.uncertainty_record_id,
                    resolution.task_id,
                    resolution.session_id,
                    resolution.project_scope_id,
                    resolution.source.source_kind,
                    memory_id,
                    evidence_id,
                    resolution.source_content_hash,
                    resolution.resolved_at,
                    resolution.created_by_principal,
                    resolution.canonical_json,
                    resolution.content_hash,
                ),
            )

        self._kernel.write(operation)
        return resolution.content_hash

    @staticmethod
    def _context_source_snapshot(
        connection: sqlite3.Connection,
        item: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        source_kind = item["source_kind"]
        if source_kind == "memory_record":
            row = connection.execute(
                "SELECT * FROM records WHERE record_id = ?",
                (item["source_memory_record_id"],),
            ).fetchone()
            return None if row is None else dict(row)
        if source_kind == "evidence":
            row = connection.execute(
                """
                SELECT evidence.*,
                       CASE WHEN controlled.record_id IS NULL THEN 0 ELSE 1 END
                           AS controlled_resilience,
                       CASE WHEN EXISTS (
                           SELECT 1
                           FROM governance_decision_evidence AS evidence_input
                           JOIN governance_decisions AS decision_record
                             ON decision_record.governance_decision_id =
                                evidence_input.governance_decision_id
                           WHERE evidence_input.required_evidence_id =
                                 evidence.evidence_id
                             AND evidence_input.resolved_evidence_id =
                                 evidence.evidence_id
                             AND evidence_input.validation_status = 'available'
                             AND decision_record.task_id = ?
                             AND decision_record.project_scope_id = ?
                       ) THEN 1 ELSE 0 END AS task_bound
                FROM evidence_items AS evidence
                LEFT JOIN controlled_resilience_evidence AS controlled
                  ON controlled.raw_prompt_evidence_id = evidence.evidence_id
                  OR controlled.raw_output_evidence_id = evidence.evidence_id
                WHERE evidence.evidence_id = ?
                """,
                (
                    item["task_id"],
                    item["project_scope_id"],
                    item["source_evidence_id"],
                ),
            ).fetchone()
            return None if row is None else dict(row)
        row = connection.execute(
            """
            SELECT rule.*,
                   CASE WHEN EXISTS (
                       SELECT 1
                       FROM governance_decision_rules AS decision_rule
                       JOIN governance_decisions AS decision_record
                         ON decision_record.governance_decision_id =
                            decision_rule.governance_decision_id
                       WHERE decision_rule.governance_rule_id =
                             rule.governance_rule_id
                         AND decision_record.task_id = ?
                         AND decision_record.project_scope_id = ?
                   ) THEN 1 ELSE 0 END AS task_bound
            FROM governance_rules AS rule
            WHERE rule.governance_rule_id = ?
            """,
            (
                item["task_id"],
                item["project_scope_id"],
                item["source_governance_rule_id"],
            ),
        ).fetchone()
        return None if row is None else dict(row)

    @classmethod
    def _eligibility_from_connection(
        cls,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        context_item_id: str,
        mode: str,
        evaluated_at: str,
    ) -> TaskMemoryEligibilityDecision:
        if mode not in TASK_MEMORY_MODES:
            raise ValidationError("task-memory mode is invalid")
        parse_canonical_utc(evaluated_at, field="evaluated_at")
        row = connection.execute(
            """
            SELECT item.*, task.status AS task_status,
                   task.session_id AS authoritative_session_id,
                   task.project_scope_id AS authoritative_project_scope_id,
                   session_record.session_status
            FROM task_context_items AS item
            JOIN tasks AS task ON task.task_id = ?
            JOIN sessions AS session_record
              ON session_record.session_id = task.session_id
            WHERE item.context_item_id = ?
            """,
            (task_id, context_item_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"context item not found: {context_item_id}")
        item = dict(row)
        reasons: set[str] = set()
        if item["task_id"] != task_id:
            reasons.add("wrong_task")
        if item["session_id"] != item["authoritative_session_id"]:
            reasons.add("wrong_session")
        if item["project_scope_id"] != item["authoritative_project_scope_id"]:
            reasons.add("wrong_project")
        if mode == "active":
            if item["task_status"] != "active":
                reasons.add("task_not_active")
                reasons.add("historical_mode_required")
            if item["session_status"] not in {"open", "paused"}:
                reasons.add("session_not_open")
                reasons.add("historical_mode_required")
        finalized = connection.execute(
            "SELECT 1 FROM task_context_finalizations WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if finalized is None:
            reasons.add("context_not_finalized")

        source = cls._context_source_snapshot(connection, item)
        if source is None:
            reasons.add("source_missing")
        elif source.get("content_hash") != item["content_hash"]:
            reasons.add("source_hash_mismatch")

        if source is not None and item["source_kind"] == "memory_record":
            if source["integrity_status"] not in {"valid", "not_applicable"}:
                reasons.add("source_integrity_invalid")
            lifecycle = source["lifecycle_state"]
            if lifecycle != "active":
                reasons.add("source_not_active")
            if source["approval_status"] not in {"approved", "not_required"}:
                reasons.add("source_not_approved")
            if lifecycle == "superseded" or source["superseded_by_record_id"]:
                reasons.add("source_superseded")
            if lifecycle == "revoked":
                reasons.add("source_revoked")
            if lifecycle == "deleted":
                reasons.add("source_deleted")
            if (
                source["record_family"] == "episodic_memory"
                and source["record_type"] == "lesson_candidate"
            ):
                reasons.add("lesson_candidate_prohibited")
            if source["sensitivity_class"] not in {"public", "internal"}:
                reasons.add("sensitivity_denied")
            if source["privacy_class"] != "none":
                reasons.add("privacy_denied")
        elif source is not None and item["source_kind"] == "evidence":
            if not source["task_bound"]:
                reasons.add("source_not_task_bound")
            if source["integrity_status"] != "valid":
                reasons.add("source_integrity_invalid")
            if (
                source["evidence_kind"]
                in {"controlled_prompt", "controlled_output"}
                or source["controlled_resilience"]
            ):
                reasons.add("controlled_resilience_prohibited")
            if source["sensitivity_class"] == "secret":
                reasons.add("sensitivity_denied")
            if source["privacy_class"] != "none":
                reasons.add("privacy_denied")
        elif source is not None:
            if not source["task_bound"]:
                reasons.add("source_not_task_bound")
            if source["status"] != "active":
                reasons.add("source_not_active")

        ordered = tuple(
            reason for reason in TASK_MEMORY_REASON_ORDER if reason in reasons
        )
        material = {
            "context_item_id": context_item_id,
            "eligible": not ordered,
            "evaluated_at": evaluated_at,
            "mode": mode,
            "reason_codes": list(ordered),
            "task_id": task_id,
        }
        return TaskMemoryEligibilityDecision(
            context_item_id=context_item_id,
            task_id=task_id,
            mode=mode,
            eligible=not ordered,
            reason_codes=ordered,
            evaluated_at=evaluated_at,
            decision_hash=sha256_canonical_json(material),
        )

    def assess_context_item(
        self,
        task_id: str,
        context_item_id: str,
        *,
        mode: str,
        evaluated_at: str,
    ) -> TaskMemoryEligibilityDecision:
        validate_identifier(task_id, field="task_id")
        validate_identifier(context_item_id, field="context_item_id")
        return self._kernel.read(
            lambda connection: self._eligibility_from_connection(
                connection,
                task_id=task_id,
                context_item_id=context_item_id,
                mode=mode,
                evaluated_at=evaluated_at,
            )
        )

    @staticmethod
    def _context_value(
        connection: sqlite3.Connection,
        task_id: str,
        *,
        mode: str,
        evaluated_at: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        items: list[dict[str, Any]] = []
        for row in connection.execute(
            """
            SELECT * FROM task_context_items
            WHERE task_id = ? ORDER BY injection_order
            """,
            (task_id,),
        ):
            item = dict(row)
            item["required"] = bool(item["required"])
            item["source"] = _source_from_row(item).canonical_value()
            eligibility = (
                SessionTaskMemoryRepository._eligibility_from_connection(
                    connection,
                    task_id=task_id,
                    context_item_id=item["context_item_id"],
                    mode=mode,
                    evaluated_at=evaluated_at,
                )
            )
            item["eligibility"] = {
                "decision_hash": eligibility.decision_hash,
                "eligible": eligibility.eligible,
                "evaluated_at": eligibility.evaluated_at,
                "mode": eligibility.mode,
                "reason_codes": list(eligibility.reason_codes),
            }
            for column in (
                "source_memory_record_id",
                "source_evidence_id",
                "source_governance_rule_id",
            ):
                item.pop(column)
            items.append(item)
        finalization_row = connection.execute(
            """
            SELECT * FROM task_context_finalizations
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        finalization = (
            None if finalization_row is None else dict(finalization_row)
        )
        return items, finalization

    @staticmethod
    def _uncertainty_value(
        connection: sqlite3.Connection,
        task_id: str,
        *,
        integrity_findings: tuple[Any, ...] = (),
    ) -> dict[str, list[dict[str, Any]]]:
        from .session_task_integrity import _resolution_effectiveness

        history: list[dict[str, Any]] = []
        active: list[dict[str, Any]] = []
        resolved: list[dict[str, Any]] = []
        invalid_uncertainty_ids = {
            finding.object_id
            for finding in integrity_findings
            if finding.code.startswith("I3D-UNCERTAINTY-")
            and finding.object_id is not None
        }
        for row in connection.execute(
            """
            SELECT uncertainty.*, record.content_hash AS record_content_hash,
                   record.task_id AS envelope_task_id,
                   record.session_id AS envelope_session_id,
                   record.project_scope_id AS envelope_project_scope_id,
                   record.created_at AS envelope_created_at,
                   record.lifecycle_state AS record_lifecycle_state,
                   record.integrity_status AS record_integrity_status,
                   resolution.resolution_id, resolution.source_kind,
                   resolution.uncertainty_record_id
                       AS resolution_uncertainty_record_id,
                   resolution.task_id AS resolution_task_id,
                   resolution.session_id AS resolution_session_id,
                   resolution.project_scope_id AS resolution_project_scope_id,
                   resolution.source_memory_record_id,
                   resolution.source_evidence_id,
                   resolution.source_content_hash, resolution.resolved_at,
                   resolution.created_by_principal
                       AS resolution_created_by_principal,
                   resolution.canonical_json AS resolution_canonical_json,
                   resolution.content_hash AS resolution_content_hash
            FROM active_uncertainties AS uncertainty
            JOIN records AS record ON record.record_id = uncertainty.record_id
            LEFT JOIN uncertainty_resolutions AS resolution
              ON resolution.uncertainty_record_id = uncertainty.record_id
            WHERE uncertainty.task_id = ?
            ORDER BY uncertainty.created_at, uncertainty.record_id
            """,
            (task_id,),
        ):
            uncertainty = {
                "canonical_json": row["canonical_json"],
                "created_at": row["created_at"],
                "created_by_principal": row["created_by_principal"],
                "impact": row["impact"],
                "integrity_status": row["record_integrity_status"],
                "lifecycle_state": row["record_lifecycle_state"],
                "project_scope_id": row["project_scope_id"],
                "record_content_hash": row["record_content_hash"],
                "record_id": row["record_id"],
                "resolution_required": bool(row["resolution_required"]),
                "session_id": row["session_id"],
                "task_id": row["task_id"],
                "uncertainty_statement": row["uncertainty_statement"],
            }
            inactive_reasons: list[str] = []
            if row["record_lifecycle_state"] in {
                "superseded",
                "revoked",
                "archived",
                "deleted",
            }:
                inactive_reasons.append(
                    "lifecycle_" + row["record_lifecycle_state"]
                )
            if row["record_integrity_status"] != "valid":
                inactive_reasons.append("integrity_status_invalid")
            if (
                row["envelope_task_id"] != row["task_id"]
                or row["envelope_session_id"] != row["session_id"]
                or row["envelope_project_scope_id"]
                != row["project_scope_id"]
                or row["envelope_created_at"] != row["created_at"]
            ):
                inactive_reasons.append("envelope_binding_invalid")
            if row["record_id"] in invalid_uncertainty_ids:
                inactive_reasons.append("integrity_finding")
            current = not inactive_reasons
            uncertainty["current"] = current
            uncertainty["inactive_reasons"] = inactive_reasons

            resolution: dict[str, Any] | None = None
            if row["resolution_id"] is not None:
                resolution_row = {
                    "canonical_json": row["resolution_canonical_json"],
                    "content_hash": row["resolution_content_hash"],
                    "created_by_principal":
                        row["resolution_created_by_principal"],
                    "project_scope_id": row["resolution_project_scope_id"],
                    "resolution_id": row["resolution_id"],
                    "resolved_at": row["resolved_at"],
                    "session_id": row["resolution_session_id"],
                    "source_content_hash": row["source_content_hash"],
                    "source_evidence_id": row["source_evidence_id"],
                    "source_kind": row["source_kind"],
                    "source_memory_record_id":
                        row["source_memory_record_id"],
                    "task_id": row["resolution_task_id"],
                    "uncertainty_record_id":
                        row["resolution_uncertainty_record_id"],
                }
                assessment = _resolution_effectiveness(
                    connection,
                    resolution_row,
                    {
                        "created_at": row["created_at"],
                        "project_scope_id": row["project_scope_id"],
                        "record_id": row["record_id"],
                        "session_id": row["session_id"],
                        "task_id": row["task_id"],
                    },
                )
                source_value = {
                    "source_kind": row["source_kind"],
                    (
                        "memory_record_id"
                        if row["source_kind"] == "memory_record"
                        else "evidence_id"
                    ): (
                        row["source_memory_record_id"]
                        if row["source_kind"] == "memory_record"
                        else row["source_evidence_id"]
                    ),
                }
                resolution = {
                    "canonical_json": row["resolution_canonical_json"],
                    "content_hash": row["resolution_content_hash"],
                    "created_by_principal":
                        row["resolution_created_by_principal"],
                    "effective": assessment.effective,
                    "ineffective_reasons": list(assessment.reason_codes),
                    "resolution_id": row["resolution_id"],
                    "resolved_at": row["resolved_at"],
                    "source": source_value,
                    "source_content_hash": row["source_content_hash"],
                }
            entry = {
                "current": current,
                "resolution": resolution,
                "uncertainty": uncertainty,
            }
            history.append(entry)
            if current and (
                resolution is None or not resolution["effective"]
            ):
                active.append(uncertainty)
            elif current:
                resolved.append(entry)
        return {"active": active, "history": history, "resolved": resolved}

    def reconstruct_task_memory(
        self,
        task_id: str,
        *,
        mode: str = "historical",
        evaluated_at: str | None = None,
    ) -> Mapping[str, Any]:
        validate_identifier(task_id, field="task_id")
        if mode not in TASK_MEMORY_MODES:
            raise ValidationError("task-memory mode is invalid")
        i2_reconstruction_error: str | None = None

        def blocked_authoritative(error: str) -> Mapping[str, Any]:
            def blocked_projection(
                connection: sqlite3.Connection,
            ) -> Mapping[str, Any]:
                row = connection.execute(
                    """
                    SELECT task.task_id, task.session_id,
                           task.project_scope_id, task.effective_at,
                           task.status AS task_status,
                           session_record.session_status,
                           session_record.active_project_scope
                    FROM tasks AS task
                    LEFT JOIN sessions AS session_record
                      ON session_record.session_id = task.session_id
                    WHERE task.task_id = ?
                    """,
                    (task_id,),
                ).fetchone()
                if row is None:
                    raise NotFoundError(f"task not found: {task_id}")
                return {
                    "integrity_error": error,
                    "projection_kind": "integrity_blocked_task_runtime",
                    "session": {
                        "active_project_scope":
                            row["active_project_scope"],
                        "session_id": row["session_id"],
                        "status": row["session_status"],
                    },
                    "task": {
                        "effective_at": row["effective_at"],
                        "project_scope_id": row["project_scope_id"],
                        "session_id": row["session_id"],
                        "task_id": row["task_id"],
                    },
                    "task_status": row["task_status"],
                }

            return {
                "integrity_verified": False,
                "value": self._kernel.read(blocked_projection),
            }

        try:
            authoritative = self._task_runtime.reconstruct(task_id)
        except (
            IntegrityInspectionError,
            ValidationError,
            KeyError,
            TypeError,
        ) as exc:
            i2_reconstruction_error = str(exc)
            authoritative = blocked_authoritative(i2_reconstruction_error)

        try:
            authoritative_value = authoritative["value"]
            authoritative_task = authoritative_value["task"]
            authoritative_session = authoritative_value["session"]
            if (
                not isinstance(authoritative_task, Mapping)
                or not isinstance(authoritative_session, Mapping)
            ):
                raise TypeError("authoritative task/session is not an object")
            for field in ("effective_at", "session_id", "task_id"):
                if field not in authoritative_task:
                    raise KeyError(f"task.{field}")
            for field in ("session_id", "status"):
                if field not in authoritative_session:
                    raise KeyError(f"session.{field}")
            if evaluated_at is None:
                parse_canonical_utc(
                    authoritative_task["effective_at"],
                    field="task effective_at",
                )
        except (KeyError, TypeError, ValidationError) as exc:
            i2_reconstruction_error = (
                "authoritative I2 projection is unusable: " + str(exc)
            )
            authoritative = blocked_authoritative(i2_reconstruction_error)

        i2_value = authoritative["value"]
        if evaluated_at is None:
            evaluated_at = i2_value["task"]["effective_at"]
        parse_canonical_utc(evaluated_at, field="evaluated_at")
        from .session_task_integrity import SessionTaskIntegrityInspector

        def operation(connection: sqlite3.Connection) -> dict[str, Any]:
            integrity_report = SessionTaskIntegrityInspector._inspect_connection(
                connection
            )
            task_session_id = i2_value["task"]["session_id"]
            context_items, finalization = self._context_value(
                connection,
                task_id,
                mode=mode,
                evaluated_at=evaluated_at or "",
            )
            uncertainties = self._uncertainty_value(
                connection,
                task_id,
                integrity_findings=integrity_report.findings,
            )
            active_blocking = any(
                item["impact"] == "blocking"
                for item in uncertainties["active"]
            )
            required_ineligible = any(
                item["required"] and not item["eligibility"]["eligible"]
                for item in context_items
            )
            integrity_findings = [
                {
                    "code": finding.code,
                    "detail": finding.detail,
                    "object_id": finding.object_id,
                    "session_id": finding.session_id,
                    "severity": finding.severity,
                    "source": finding.source,
                    "table": finding.table,
                    "task_id": finding.task_id,
                }
                for finding in integrity_report.findings
                if finding.task_id == task_id
                or (
                    finding.task_id is None
                    and finding.session_id == task_session_id
                )
            ]
            current_context_ready = (
                i2_reconstruction_error is None
                and authoritative["integrity_verified"]
                and i2_value["task_status"] == "active"
                and i2_value["session"]["status"] in {"open", "paused"}
                and finalization is not None
                and not active_blocking
                and not required_ineligible
                and not integrity_findings
            )
            return {
                "authority_source": "B87-I2",
                "authoritative_i2": i2_value,
                "context": {
                    "finalization": finalization,
                    "items": context_items,
                },
                "context_ready": current_context_ready,
                "integrity": {
                    "authoritative_i2_integrity_findings": [
                        finding
                        for finding in integrity_findings
                        if finding["source"] == "i2"
                    ],
                    "authoritative_i2_verified":
                        authoritative["integrity_verified"],
                    "findings": integrity_findings,
                    "i2_reconstruction_error": i2_reconstruction_error,
                    "valid": (
                        i2_reconstruction_error is None
                        and authoritative["integrity_verified"]
                        and not integrity_findings
                    ),
                },
                "mode": mode,
                "projection_kind": "task_memory",
                "uncertainties": uncertainties,
            }

        value = self._kernel.read(operation)
        canonical = canonical_json_text(value)
        return {
            "canonical_json": canonical,
            "content_hash": sha256_canonical_json(value),
            "integrity_verified": bool(value["integrity"]["valid"]),
            "value": value,
        }

    def reconstruct_session_memory(
        self,
        session_id: str,
    ) -> Mapping[str, Any]:
        validate_identifier(session_id, field="session_id")
        from .session_task_integrity import SessionTaskIntegrityInspector

        def session_operation(
            connection: sqlite3.Connection,
        ) -> tuple[
            dict[str, Any],
            list[dict[str, Any]],
            list[dict[str, Any]],
            list[str],
            list[dict[str, Any]],
        ]:
            session = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if session is None:
                raise NotFoundError(f"session not found: {session_id}")
            participants = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT participant.entity_id, participant.role,
                           entity.entity_kind, entity.canonical_name
                    FROM session_participants AS participant
                    JOIN entities AS entity
                      ON entity.entity_id = participant.entity_id
                    WHERE participant.session_id = ?
                    ORDER BY participant.entity_id
                    """,
                    (session_id,),
                )
            ]
            relational_session = {
                "closed_at": session["closed_at"],
                "contract_version": session["contract_version"],
                "created_by_entity_id": session["created_by_entity_id"],
                "opened_at": session["opened_at"],
                "participant_entity_ids": [
                    item["entity_id"] for item in participants
                ],
                "project_scope_id": session["active_project_scope"],
                "purpose": session["session_purpose"],
                "retention_disposition": session["retention_disposition"],
                "session_id": session["session_id"],
                "status": session["session_status"],
            }
            try:
                stored_session = parse_json(session["canonical_json"])
            except ValidationError:
                stored_session = None
            canonical_session = (
                dict(stored_session)
                if isinstance(stored_session, Mapping)
                and set(relational_session) <= set(stored_session)
                else relational_session
            )
            transitions = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM session_state_transitions
                    WHERE session_id = ? ORDER BY sequence_number
                    """,
                    (session_id,),
                )
            ]
            task_ids = [
                row["task_id"]
                for row in connection.execute(
                    """
                    SELECT task_id FROM tasks
                    WHERE session_id = ? ORDER BY created_at, task_id
                    """,
                    (session_id,),
                )
            ]
            integrity_findings = [
                {
                    "code": finding.code,
                    "detail": finding.detail,
                    "object_id": finding.object_id,
                    "session_id": finding.session_id,
                    "severity": finding.severity,
                    "source": finding.source,
                    "table": finding.table,
                    "task_id": finding.task_id,
                }
                for finding in SessionTaskIntegrityInspector._inspect_connection(
                    connection
                ).findings
                if finding.session_id == session_id
                and finding.task_id is None
            ]
            return (
                canonical_session,
                participants,
                transitions,
                task_ids,
                integrity_findings,
            )

        (
            session,
            participants,
            transitions,
            task_ids,
            integrity_findings,
        ) = self._kernel.read(session_operation)
        tasks = [
            self.reconstruct_task_memory(task_id, mode="historical")["value"]
            for task_id in task_ids
        ]
        task_integrity_failures: list[dict[str, Any]] = []
        session_reason_categories: set[str] = set()
        if any(
            finding["source"] == "i3d"
            for finding in integrity_findings
        ):
            session_reason_categories.add("session_scoped_i3d_findings")
        if any(
            finding["source"] == "i2"
            for finding in integrity_findings
        ):
            session_reason_categories.add(
                "authoritative_i2_integrity_findings"
            )
        for task in tasks:
            task_integrity = task["integrity"]
            task_reason_categories: set[str] = set()
            if not task_integrity["valid"]:
                task_reason_categories.add("task_integrity_invalid")
            if not task_integrity["authoritative_i2_verified"]:
                task_reason_categories.add("authoritative_i2_unverified")
            if task_integrity["i2_reconstruction_error"] is not None:
                task_reason_categories.add("i2_reconstruction_error")
            if any(
                finding["source"] == "i2"
                and finding["task_id"] is not None
                for finding in task_integrity[
                    "authoritative_i2_integrity_findings"
                ]
            ):
                task_reason_categories.add(
                    "authoritative_i2_integrity_findings"
                )
            if any(
                finding["source"] == "i3d"
                and finding["task_id"] is not None
                for finding in task_integrity["findings"]
            ):
                task_reason_categories.add("task_scoped_i3d_findings")
            if task_reason_categories:
                ordered_reasons = [
                    reason
                    for reason in _SESSION_INTEGRITY_REASON_ORDER
                    if reason in task_reason_categories
                ]
                task_integrity_failures.append(
                    {
                        "reason_categories": ordered_reasons,
                        "task_id": task["authoritative_i2"]["task"]["task_id"],
                    }
                )
                session_reason_categories.update(task_reason_categories)
        task_integrity_failures.sort(key=lambda item: item["task_id"])
        integrity_summary = {
            "affected_task_ids": [
                item["task_id"] for item in task_integrity_failures
            ],
            "reason_categories": [
                reason
                for reason in _SESSION_INTEGRITY_REASON_ORDER
                if reason in session_reason_categories
            ],
            "tasks": task_integrity_failures,
        }
        value = {
            "authority_source": "B87-I2",
            "context_summary": {
                "active_blocking_uncertainty_count": sum(
                    1
                    for task in tasks
                    for item in task["uncertainties"]["active"]
                    if item["impact"] == "blocking"
                ),
                "context_item_count": sum(
                    len(task["context"]["items"]) for task in tasks
                ),
                "task_count": len(tasks),
            },
            "integrity": {
                "findings": integrity_findings,
                "summary": integrity_summary,
                "valid": (
                    not integrity_findings
                    and not task_integrity_failures
                ),
            },
            "participants": participants,
            "projection_kind": "session_memory",
            "retention_disposition": session["retention_disposition"],
            "session": session,
            "tasks": tasks,
            "transitions": transitions,
        }
        canonical = canonical_json_text(value)
        return {
            "canonical_json": canonical,
            "content_hash": sha256_canonical_json(value),
            "integrity_verified": bool(value["integrity"]["valid"]),
            "value": value,
        }
