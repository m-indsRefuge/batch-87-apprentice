"""Read-only integrity inspection for B87-I3-D session and task memory."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import canonical_json_text, parse_json
from batch87_apprentice.common.hashing import hashes_match, sha256_canonical_json
from batch87_apprentice.common.timestamps import parse_canonical_utc
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.contracts import RecordEnvelope
from batch87_apprentice.persistence.transactions import PersistenceKernel
from batch87_apprentice.protocols import SessionContract, TaskContract

from .contracts import validate_approval_transition, validate_lifecycle_transition
from .session_task_contracts import (
    ActiveUncertaintyPayload,
    TaskContextFinalization,
    TaskContextItem,
    TypedSourceReference,
    UncertaintyResolution,
    active_uncertainty_content_hash,
)
from .session_task_repository import _source_from_row


_RESOLUTION_INEFFECTIVE_REASON_ORDER = (
    "resolution_canonical_invalid",
    "resolution_binding_invalid",
    "uncertainty_not_current_at_resolution",
    "source_missing",
    "source_wrong_task",
    "source_wrong_project",
    "source_hash_mismatch",
    "source_integrity_invalid",
    "source_not_task_bound",
    "controlled_resilience_prohibited",
    "source_history_invalid",
    "source_not_active_at_resolution",
    "source_not_approved_at_resolution",
    "source_approval_invalid",
    "source_supersession_invalid",
    "source_revoked",
    "source_deleted",
)

_SESSION_CONTRACT_FIELDS = frozenset(
    {
        "closed_at",
        "contract_version",
        "created_by_entity_id",
        "opened_at",
        "participant_entity_ids",
        "project_scope_id",
        "purpose",
        "retention_disposition",
        "session_id",
        "status",
    }
)
_SESSION_TRANSITIONS = frozenset(
    {
        (None, "open"),
        ("open", "paused"),
        ("open", "closed"),
        ("open", "aborted"),
        ("paused", "open"),
        ("paused", "closed"),
        ("paused", "aborted"),
    }
)
_TASK_TRANSITIONS = frozenset(
    {
        (None, "pending"),
        ("pending", "active"),
        ("pending", "stopped"),
        ("pending", "failed"),
        ("active", "completed"),
        ("active", "stopped"),
        ("active", "failed"),
    }
)
_SESSION_TERMINAL_STATES = frozenset({"closed", "aborted"})
_TASK_TERMINAL_STATES = frozenset({"completed", "stopped", "failed"})


@dataclass(frozen=True, slots=True)
class _TransitionHistory:
    state_at: str | None
    latest_state: str | None
    valid: bool


@dataclass(frozen=True, slots=True)
class _ResolutionEffectiveness:
    effective: bool
    reason_codes: tuple[str, ...]


def _transition_history(
    connection: sqlite3.Connection,
    *,
    record_id: str,
    effective_at: str | None,
    history_kind: str,
) -> _TransitionHistory:
    if history_kind == "lifecycle":
        table = "memory_record_lifecycle_transitions"
        from_column = "from_state"
        to_column = "to_state"
        extra_columns = ("changed_by_entity_id",)
    elif history_kind == "approval":
        table = "memory_record_approval_transitions"
        from_column = "from_status"
        to_column = "to_status"
        extra_columns = (
            "changed_by_entity_id",
            "approval_grant_id",
            "authority_record_id",
            "approval_evidence_id",
        )
    else:
        raise ValueError("unknown transition history kind")

    rows = tuple(
        connection.execute(
            f"""
            SELECT * FROM {table}
            WHERE record_id = ?
            ORDER BY sequence_number
            """,
            (record_id,),
        )
    )
    valid = bool(rows)
    previous: str | None = None
    previous_changed_at: str | None = None
    state_at: str | None = None
    for expected_sequence, row in enumerate(rows):
        try:
            parse_canonical_utc(row["changed_at"], field="changed_at")
            if (
                row["sequence_number"] != expected_sequence
                or row[from_column] != previous
                or (
                    previous_changed_at is not None
                    and row["changed_at"] < previous_changed_at
                )
            ):
                raise ValueError("transition history is not contiguous")
            if expected_sequence == 0:
                accepted_initial = (
                    {"observed", "candidate", "reviewed"}
                    if history_kind == "lifecycle"
                    else {"pending", "not_required"}
                )
                if row[from_column] is not None or row[to_column] not in accepted_initial:
                    raise ValueError("transition history has an invalid initial state")
            elif history_kind == "lifecycle":
                validate_lifecycle_transition(previous or "", row[to_column])
            else:
                validate_approval_transition(previous or "", row[to_column])

            material: dict[str, Any] = {
                "transition_id": row["transition_id"],
                "record_id": row["record_id"],
                "sequence_number": row["sequence_number"],
                from_column: row[from_column],
                to_column: row[to_column],
                "reason_code": row["reason_code"],
                "changed_at": row["changed_at"],
                "changed_by_principal": row["changed_by_principal"],
            }
            material.update({column: row[column] for column in extra_columns})
            parsed = parse_json(row["canonical_json"])
            if (
                canonical_json_text(parsed) != row["canonical_json"]
                or parsed != material
                or sha256_canonical_json(material) != row["content_hash"]
            ):
                raise ValueError("transition canonical content differs")
        except Exception:
            valid = False
        if effective_at is None or row["changed_at"] <= effective_at:
            state_at = row[to_column]
        previous = row[to_column]
        previous_changed_at = row["changed_at"]

    return _TransitionHistory(
        state_at=state_at,
        latest_state=previous,
        valid=valid,
    )


def _supersession_is_valid(
    connection: sqlite3.Connection,
    source: Mapping[str, Any],
) -> bool:
    record_id = source["record_id"]
    supersedes_id = source["supersedes_record_id"]
    if supersedes_id is not None:
        prior_link = connection.execute(
            """
            SELECT 1
            FROM record_relationships
            WHERE source_record_id = ?
              AND target_record_id = ?
              AND relationship_type = 'supersedes'
              AND relationship_grant_id IS NOT NULL
            """,
            (record_id, supersedes_id),
        ).fetchone()
        if prior_link is None:
            return False

    was_superseded = connection.execute(
        """
        SELECT 1
        FROM memory_record_lifecycle_transitions
        WHERE record_id = ? AND to_state = 'superseded'
        """,
        (record_id,),
    ).fetchone()
    replacement_id = source["superseded_by_record_id"]
    if was_superseded is None:
        return replacement_id is None
    if replacement_id is None:
        return False
    return (
        connection.execute(
            """
            SELECT 1
            FROM record_relationships AS relationship
            JOIN records AS replacement
              ON replacement.record_id = relationship.source_record_id
            WHERE relationship.source_record_id = ?
              AND relationship.target_record_id = ?
              AND relationship.relationship_type = 'supersedes'
              AND relationship.relationship_grant_id IS NOT NULL
              AND replacement.record_family = ?
              AND replacement.record_type = ?
              AND replacement.project_scope_id = ?
              AND replacement.supersedes_record_id = ?
            """,
            (
                replacement_id,
                record_id,
                source["record_family"],
                source["record_type"],
                source["project_scope_id"],
                record_id,
            ),
        ).fetchone()
        is not None
    )


def _resolution_effectiveness(
    connection: sqlite3.Connection,
    resolution_row: Mapping[str, Any],
    uncertainty_row: Mapping[str, Any],
) -> _ResolutionEffectiveness:
    reasons: set[str] = set()
    source: TypedSourceReference | None = None
    try:
        source = TypedSourceReference(
            memory_record_id=resolution_row["source_memory_record_id"],
            evidence_id=resolution_row["source_evidence_id"],
        )
        resolution = UncertaintyResolution(
            resolution_id=resolution_row["resolution_id"],
            uncertainty_record_id=resolution_row["uncertainty_record_id"],
            task_id=resolution_row["task_id"],
            session_id=resolution_row["session_id"],
            project_scope_id=resolution_row["project_scope_id"],
            source=source,
            source_content_hash=resolution_row["source_content_hash"],
            resolved_at=resolution_row["resolved_at"],
            created_by_principal=resolution_row["created_by_principal"],
        )
        parsed = parse_json(resolution_row["canonical_json"])
        if (
            canonical_json_text(parsed) != resolution_row["canonical_json"]
            or parsed != resolution.canonical_value()
            or resolution.content_hash != resolution_row["content_hash"]
        ):
            raise ValueError("resolution canonical content differs")
    except Exception:
        reasons.add("resolution_canonical_invalid")

    if (
        uncertainty_row["record_id"] != resolution_row["uncertainty_record_id"]
        or uncertainty_row["task_id"] != resolution_row["task_id"]
        or uncertainty_row["session_id"] != resolution_row["session_id"]
        or uncertainty_row["project_scope_id"]
        != resolution_row["project_scope_id"]
        or resolution_row["resolved_at"] < uncertainty_row["created_at"]
    ):
        reasons.add("resolution_binding_invalid")

    uncertainty_record = connection.execute(
        """
        SELECT * FROM records
        WHERE record_id = ?
        """,
        (resolution_row["uncertainty_record_id"],),
    ).fetchone()
    if uncertainty_record is None:
        reasons.add("resolution_binding_invalid")
    else:
        lifecycle = _transition_history(
            connection,
            record_id=uncertainty_record["record_id"],
            effective_at=resolution_row["resolved_at"],
            history_kind="lifecycle",
        )
        if (
            not lifecycle.valid
            or lifecycle.latest_state != uncertainty_record["lifecycle_state"]
            or lifecycle.state_at
            in {"superseded", "revoked", "archived", "deleted", None}
        ):
            reasons.add("uncertainty_not_current_at_resolution")

    if source is not None and source.source_kind == "memory_record":
        source_row = connection.execute(
            "SELECT * FROM records WHERE record_id = ?",
            (source.memory_record_id,),
        ).fetchone()
        if source_row is None:
            reasons.add("source_missing")
        else:
            source_value = dict(source_row)
            if source_value["task_id"] != resolution_row["task_id"]:
                reasons.add("source_wrong_task")
            if (
                source_value["project_scope_id"]
                != resolution_row["project_scope_id"]
            ):
                reasons.add("source_wrong_project")
            if (
                source_value["content_hash"]
                != resolution_row["source_content_hash"]
            ):
                reasons.add("source_hash_mismatch")
            if source_value["integrity_status"] not in {
                "valid",
                "not_applicable",
            }:
                reasons.add("source_integrity_invalid")

            lifecycle = _transition_history(
                connection,
                record_id=source_value["record_id"],
                effective_at=resolution_row["resolved_at"],
                history_kind="lifecycle",
            )
            approval = _transition_history(
                connection,
                record_id=source_value["record_id"],
                effective_at=resolution_row["resolved_at"],
                history_kind="approval",
            )
            if (
                not lifecycle.valid
                or not approval.valid
                or lifecycle.latest_state != source_value["lifecycle_state"]
                or approval.latest_state != source_value["approval_status"]
            ):
                reasons.add("source_history_invalid")
            if lifecycle.state_at != "active":
                reasons.add("source_not_active_at_resolution")
            if approval.state_at not in {"approved", "not_required"}:
                reasons.add("source_not_approved_at_resolution")
            if source_value["approval_status"] in {"rejected", "withdrawn"}:
                reasons.add("source_approval_invalid")
            if not _supersession_is_valid(connection, source_value):
                reasons.add("source_supersession_invalid")
            if connection.execute(
                """
                SELECT 1 FROM memory_record_lifecycle_transitions
                WHERE record_id = ? AND to_state = 'revoked'
                """,
                (source_value["record_id"],),
            ).fetchone() is not None:
                reasons.add("source_revoked")
            if connection.execute(
                """
                SELECT 1 FROM memory_record_lifecycle_transitions
                WHERE record_id = ? AND to_state = 'deleted'
                """,
                (source_value["record_id"],),
            ).fetchone() is not None:
                reasons.add("source_deleted")
    elif source is not None:
        source_row = connection.execute(
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
                resolution_row["task_id"],
                resolution_row["project_scope_id"],
                source.evidence_id,
            ),
        ).fetchone()
        if source_row is None:
            reasons.add("source_missing")
        else:
            if source_row["content_hash"] != resolution_row["source_content_hash"]:
                reasons.add("source_hash_mismatch")
            if source_row["integrity_status"] != "valid":
                reasons.add("source_integrity_invalid")
            if not source_row["task_bound"]:
                reasons.add("source_not_task_bound")
            if (
                source_row["evidence_kind"]
                in {"controlled_prompt", "controlled_output"}
                or source_row["controlled_resilience"]
            ):
                reasons.add("controlled_resilience_prohibited")

    ordered = tuple(
        reason
        for reason in _RESOLUTION_INEFFECTIVE_REASON_ORDER
        if reason in reasons
    )
    return _ResolutionEffectiveness(
        effective=not ordered,
        reason_codes=ordered,
    )


def _uncertainty_envelope(row: Mapping[str, Any]) -> RecordEnvelope:
    return RecordEnvelope(
        record_id=row["envelope_record_id"],
        record_family=row["envelope_record_family"],
        record_type=row["envelope_record_type"],
        schema_version=row["envelope_schema_version"],
        construct_scope_id=row["envelope_construct_scope_id"],
        project_scope_id=row["envelope_project_scope_id"],
        subject_entity_id=row["envelope_subject_entity_id"],
        session_id=row["envelope_session_id"],
        task_id=row["envelope_task_id"],
        lifecycle_state=row["envelope_lifecycle_state"],
        approval_status=row["envelope_approval_status"],
        authority_class=row["envelope_authority_class"],
        certainty_class=row["envelope_certainty_class"],
        sensitivity_class=row["envelope_sensitivity_class"],
        privacy_class=row["envelope_privacy_class"],
        retention_class=row["envelope_retention_class"],
        training_eligibility=row["envelope_training_eligibility"],
        created_at=row["envelope_created_at"],
        created_by_entity_id=row["envelope_created_by_entity_id"],
        created_by_runtime_id=row["envelope_created_by_runtime_id"],
        effective_from=row["envelope_effective_from"],
        effective_until=row["envelope_effective_until"],
        review_due_at=row["envelope_review_due_at"],
        supersedes_record_id=row["envelope_supersedes_record_id"],
        superseded_by_record_id=row["envelope_superseded_by_record_id"],
        previous_version_id=row["envelope_previous_version_id"],
        source_kind=row["envelope_source_kind"],
        provenance_summary=row["envelope_provenance_summary"],
        retrieval_policy_json=row["envelope_retrieval_policy_json"],
        deletion_policy_json=row["envelope_deletion_policy_json"],
        agent_write_policy=row["envelope_agent_write_policy"],
        integrity_status=row["envelope_integrity_status"],
        deleted_at=row["envelope_deleted_at"],
        deletion_basis=row["envelope_deletion_basis"],
    )


@dataclass(frozen=True, slots=True)
class SessionTaskIntegrityFinding:
    code: str
    severity: str
    object_id: str | None
    task_id: str | None
    session_id: str | None
    table: str
    detail: str
    source: str = "i3d"


@dataclass(frozen=True, slots=True)
class SessionTaskIntegrityReport:
    findings: tuple[SessionTaskIntegrityFinding, ...]

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.findings)


class SessionTaskIntegrityInspector:
    """Detect I3-D corruption without treating later I2 closure as corruption."""

    def __init__(
        self,
        kernel_or_config: PersistenceKernel | DatabaseConfig,
    ) -> None:
        self._kernel = (
            kernel_or_config
            if isinstance(kernel_or_config, PersistenceKernel)
            else PersistenceKernel(kernel_or_config)
        )

    @staticmethod
    def _finding(
        findings: list[SessionTaskIntegrityFinding],
        code: str,
        *,
        object_id: str | None,
        task_id: str | None,
        session_id: str | None,
        table: str,
        detail: str,
        severity: str = "error",
        source: str = "i3d",
    ) -> None:
        findings.append(
            SessionTaskIntegrityFinding(
                code=code,
                severity=severity,
                object_id=object_id,
                task_id=task_id,
                session_id=session_id,
                table=table,
                detail=detail,
                source=source,
            )
        )

    @classmethod
    def _inspect_existing_i2_runtime(
        cls,
        connection: sqlite3.Connection,
        findings: list[SessionTaskIntegrityFinding],
    ) -> None:
        from batch87_apprentice.persistence.integrity import (
            inspect_task_runtime_integrity,
        )

        for finding in inspect_task_runtime_integrity(connection):
            cls._finding(
                findings,
                finding.code,
                object_id=finding.object_id,
                task_id=finding.task_id,
                session_id=finding.session_id,
                table=finding.table,
                detail=finding.detail,
                severity=finding.severity,
                source="i2",
            )

    @staticmethod
    def _session_contract(value: object) -> SessionContract:
        if not isinstance(value, Mapping):
            raise ValueError("canonical session contract is not an object")
        if set(value) != _SESSION_CONTRACT_FIELDS:
            raise ValueError("canonical session contract fields differ")
        participants = value["participant_entity_ids"]
        if not isinstance(participants, list):
            raise ValueError("canonical session participants are not an array")
        return SessionContract(
            session_id=value["session_id"],
            purpose=value["purpose"],
            project_scope_id=value["project_scope_id"],
            opened_at=value["opened_at"],
            created_by_entity_id=value["created_by_entity_id"],
            participant_entity_ids=tuple(participants),
            status=value["status"],
            retention_disposition=value["retention_disposition"],
            closed_at=value["closed_at"],
            contract_version=value["contract_version"],
        )

    @classmethod
    def _inspect_i2_sessions(
        cls,
        connection: sqlite3.Connection,
        findings: list[SessionTaskIntegrityFinding],
    ) -> None:
        for row in connection.execute(
            "SELECT * FROM sessions ORDER BY session_id"
        ):
            session_id = row["session_id"]
            contract: SessionContract | None = None
            canonical_participant_ids: tuple[object, ...] | None = None
            canonical_reasons: set[str] = set()
            try:
                parsed = parse_json(row["canonical_json"])
                if (
                    isinstance(parsed, Mapping)
                    and isinstance(parsed.get("participant_entity_ids"), list)
                ):
                    canonical_participant_ids = tuple(
                        parsed["participant_entity_ids"]
                    )
                contract = cls._session_contract(parsed)
                if (
                    canonical_json_text(parsed) != row["canonical_json"]
                    or contract.canonical_json != row["canonical_json"]
                ):
                    canonical_reasons.add("canonical_json_differs")
                if not hashes_match(row["content_hash"], contract.content_hash):
                    canonical_reasons.add("content_hash_differs")
                relational_values = {
                    "closed_at": row["closed_at"],
                    "contract_version": row["contract_version"],
                    "created_by_entity_id": row["created_by_entity_id"],
                    "opened_at": row["opened_at"],
                    "project_scope_id": row["active_project_scope"],
                    "purpose": row["session_purpose"],
                    "retention_disposition": row["retention_disposition"],
                    "session_id": row["session_id"],
                    "status": row["session_status"],
                }
                canonical_values = contract.canonical_value()
                for field, actual in relational_values.items():
                    if canonical_values[field] != actual:
                        canonical_reasons.add(f"{field}_differs")
            except (KeyError, TypeError, ValueError) as exc:
                canonical_reasons.add(
                    "contract_invalid:" + exc.__class__.__name__
                )

            if canonical_reasons:
                cls._finding(
                    findings,
                    "I3D-I2-SESSION-CANONICAL",
                    object_id=session_id,
                    task_id=None,
                    session_id=session_id,
                    table="sessions",
                    detail=(
                        "authoritative session contract differs: "
                        + ",".join(sorted(canonical_reasons))
                    ),
                )

            participant_rows = tuple(
                connection.execute(
                    """
                    SELECT entity_id, role
                    FROM session_participants
                    WHERE session_id = ?
                    ORDER BY entity_id
                    """,
                    (session_id,),
                )
            )
            participant_reasons: set[str] = set()
            actual_ids = tuple(item["entity_id"] for item in participant_rows)
            if len(actual_ids) != len(set(actual_ids)):
                participant_reasons.add("duplicate_participant")
            participant_roles = {
                item["entity_id"]: item["role"] for item in participant_rows
            }
            creator_id = row["created_by_entity_id"]
            if creator_id not in participant_roles:
                participant_reasons.add("creator_missing")
            elif participant_roles[creator_id] != "operator":
                participant_reasons.add("creator_role_invalid")
            if any(
                item["entity_id"] != creator_id
                and item["role"] != "participant"
                for item in participant_rows
            ):
                participant_reasons.add("participant_role_invalid")
            if canonical_participant_ids is not None:
                expected_ids = canonical_participant_ids
                if not all(isinstance(item, str) for item in expected_ids):
                    participant_reasons.add(
                        "canonical_participant_id_invalid"
                    )
                else:
                    if len(expected_ids) != len(set(expected_ids)):
                        participant_reasons.add(
                            "canonical_duplicate_participant"
                        )
                    if set(actual_ids) != set(expected_ids):
                        participant_reasons.add("participant_set_differs")
            if participant_reasons:
                cls._finding(
                    findings,
                    "I3D-I2-SESSION-PARTICIPANTS",
                    object_id=session_id,
                    task_id=None,
                    session_id=session_id,
                    table="session_participants",
                    detail=(
                        "authoritative session participants differ: "
                        + ",".join(sorted(participant_reasons))
                    ),
                )

            transitions = tuple(
                connection.execute(
                    """
                    SELECT *
                    FROM session_state_transitions
                    WHERE session_id = ?
                    ORDER BY sequence_number, transition_id
                    """,
                    (session_id,),
                )
            )
            history_reasons: set[str] = set()
            previous_state: str | None = None
            previous_changed_at: Any | None = None
            terminal_seen = False
            if not transitions:
                history_reasons.add("history_missing")
            for expected_sequence, transition in enumerate(transitions):
                sequence = transition["sequence_number"]
                if sequence != expected_sequence:
                    history_reasons.add("sequence_not_contiguous")
                pair = (
                    transition["from_status"],
                    transition["to_status"],
                )
                if pair not in _SESSION_TRANSITIONS:
                    history_reasons.add("transition_not_permitted")
                if transition["from_status"] != previous_state:
                    history_reasons.add("from_status_differs")
                if terminal_seen:
                    history_reasons.add("transition_after_terminal")
                try:
                    changed_at = parse_canonical_utc(
                        transition["changed_at"],
                        field="session transition changed_at",
                    )
                    if (
                        previous_changed_at is not None
                        and changed_at < previous_changed_at
                    ):
                        history_reasons.add("timestamp_regressed")
                    previous_changed_at = changed_at
                except (TypeError, ValueError):
                    history_reasons.add("timestamp_not_canonical")
                if expected_sequence == 0:
                    if pair != (None, "open"):
                        history_reasons.add("initial_transition_invalid")
                    if transition["changed_at"] != row["opened_at"]:
                        history_reasons.add("opened_at_differs")
                    if (
                        contract is not None
                        and transition["changed_at"] != contract.opened_at
                    ):
                        history_reasons.add("canonical_opened_at_differs")
                previous_state = transition["to_status"]
                terminal_seen = previous_state in _SESSION_TERMINAL_STATES

            if previous_state != row["session_status"]:
                history_reasons.add("latest_status_differs")
            if contract is not None and previous_state != contract.status:
                history_reasons.add("canonical_status_differs")
            if row["session_status"] in {"open", "paused"}:
                if row["closed_at"] is not None:
                    history_reasons.add("nonterminal_closed_at_present")
            elif row["session_status"] in _SESSION_TERMINAL_STATES:
                terminal_at = (
                    transitions[-1]["changed_at"] if transitions else None
                )
                if row["closed_at"] != terminal_at:
                    history_reasons.add("terminal_closed_at_differs")
                if (
                    contract is not None
                    and contract.closed_at != terminal_at
                ):
                    history_reasons.add(
                        "canonical_terminal_closed_at_differs"
                    )
            if history_reasons:
                cls._finding(
                    findings,
                    "I3D-I2-SESSION-HISTORY",
                    object_id=session_id,
                    task_id=None,
                    session_id=session_id,
                    table="session_state_transitions",
                    detail=(
                        "authoritative session history differs: "
                        + ",".join(sorted(history_reasons))
                    ),
                )

    @classmethod
    def _inspect_i2_tasks(
        cls,
        connection: sqlite3.Connection,
        findings: list[SessionTaskIntegrityFinding],
    ) -> None:
        for row in connection.execute("SELECT * FROM tasks ORDER BY task_id"):
            task_id = row["task_id"]
            session_id = row["session_id"]
            contract: TaskContract | None = None
            canonical_reasons: set[str] = set()
            try:
                parsed = parse_json(row["canonical_contract_json"])
                contract = TaskContract.from_mapping(parsed)
                if (
                    canonical_json_text(parsed)
                    != row["canonical_contract_json"]
                    or contract.canonical_json
                    != row["canonical_contract_json"]
                ):
                    canonical_reasons.add("canonical_json_differs")
                if not hashes_match(row["contract_hash"], contract.content_hash):
                    canonical_reasons.add("contract_hash_differs")
                expected_columns: dict[str, object] = {
                    "task_id": contract.task_id,
                    "session_id": contract.session_id,
                    "contract_version": contract.contract_version,
                    "objective": contract.objective,
                    "task_type": contract.task_type,
                    "project_scope_id": contract.project_scope_id,
                    "requested_scope_id": contract.requested_scope_id,
                    "requested_operation": contract.requested_operation.name,
                    "requested_action_class":
                        contract.requested_operation.action_class,
                    "operation_autonomous":
                        int(contract.requested_operation.autonomous),
                    "requesting_principal": contract.requesting_principal,
                    "authority_grant_json": canonical_json_text(
                        list(contract.authority_grant)
                    ),
                    "claimed_authority_ids_json": canonical_json_text(
                        list(contract.claimed_authority_ids)
                    ),
                    "claimed_human_approval_ids_json": canonical_json_text(
                        list(contract.claimed_human_approval_ids)
                    ),
                    "allowed_sources_json": canonical_json_text(
                        list(contract.allowed_sources)
                    ),
                    "prohibited_actions_json": canonical_json_text(
                        list(contract.prohibited_actions)
                    ),
                    "expected_output_schema_id":
                        contract.expected_output_schema_id,
                    "stop_conditions_json": canonical_json_text(
                        list(contract.stop_conditions)
                    ),
                    "governing_constraints_json": canonical_json_text(
                        list(contract.governing_constraints)
                    ),
                    "required_evidence_ids_json": canonical_json_text(
                        list(contract.required_evidence_ids)
                    ),
                    "effective_at": contract.effective_at,
                    "provenance_json": contract.provenance_json,
                }
                for column, expected in expected_columns.items():
                    if row[column] != expected:
                        canonical_reasons.add(f"{column}_differs")
            except (KeyError, TypeError, ValueError) as exc:
                canonical_reasons.add(
                    "contract_invalid:" + exc.__class__.__name__
                )
            if canonical_reasons:
                cls._finding(
                    findings,
                    "I3D-I2-TASK-CANONICAL",
                    object_id=task_id,
                    task_id=task_id,
                    session_id=session_id,
                    table="tasks",
                    detail=(
                        "authoritative task contract differs: "
                        + ",".join(sorted(canonical_reasons))
                    ),
                )

            transactions = tuple(
                connection.execute(
                    """
                    SELECT transaction_id, task_id
                    FROM governed_runtime_transactions
                    WHERE task_id = ?
                    ORDER BY transaction_id
                    """,
                    (task_id,),
                )
            )
            expected_transaction_id = (
                transactions[0]["transaction_id"]
                if len(transactions) == 1
                else None
            )
            transaction_reasons: set[str] = set()
            if len(transactions) != 1:
                transaction_reasons.add("governed_transaction_not_exact")

            transitions = tuple(
                connection.execute(
                    """
                    SELECT *
                    FROM task_state_transitions
                    WHERE task_id = ?
                    ORDER BY sequence_number, transition_id
                    """,
                    (task_id,),
                )
            )
            history_reasons: set[str] = set()
            previous_state: str | None = None
            previous_changed_at: Any | None = None
            terminal_seen = False
            active_timestamps: list[str] = []
            terminal_timestamps: list[str] = []
            if not transitions:
                history_reasons.add("history_missing")
            for expected_sequence, transition in enumerate(transitions):
                if transition["sequence_number"] != expected_sequence:
                    history_reasons.add("sequence_not_contiguous")
                pair = (
                    transition["from_status"],
                    transition["to_status"],
                )
                if pair not in _TASK_TRANSITIONS:
                    history_reasons.add("transition_not_permitted")
                if transition["from_status"] != previous_state:
                    history_reasons.add("from_status_differs")
                if terminal_seen:
                    history_reasons.add("transition_after_terminal")
                try:
                    changed_at = parse_canonical_utc(
                        transition["changed_at"],
                        field="task transition changed_at",
                    )
                    if (
                        previous_changed_at is not None
                        and changed_at < previous_changed_at
                    ):
                        history_reasons.add("timestamp_regressed")
                    previous_changed_at = changed_at
                except (TypeError, ValueError):
                    history_reasons.add("timestamp_not_canonical")
                if expected_sequence == 0:
                    if pair != (None, "pending"):
                        history_reasons.add("initial_transition_invalid")
                    if transition["changed_at"] != row["created_at"]:
                        history_reasons.add("created_at_differs")
                if transition["to_status"] == "active":
                    active_timestamps.append(transition["changed_at"])
                if transition["to_status"] in _TASK_TERMINAL_STATES:
                    terminal_timestamps.append(transition["changed_at"])
                if (
                    expected_transaction_id is None
                    or transition["transaction_id"]
                    != expected_transaction_id
                ):
                    transaction_reasons.add("transaction_id_differs")
                transaction_owner = connection.execute(
                    """
                    SELECT task_id
                    FROM governed_runtime_transactions
                    WHERE transaction_id = ?
                    """,
                    (transition["transaction_id"],),
                ).fetchone()
                if (
                    transaction_owner is None
                    or transaction_owner["task_id"] != task_id
                ):
                    transaction_reasons.add("transaction_task_differs")
                previous_state = transition["to_status"]
                terminal_seen = previous_state in _TASK_TERMINAL_STATES

            if previous_state != row["status"]:
                history_reasons.add("latest_status_differs")
            if len(active_timestamps) > 1:
                history_reasons.add("multiple_active_transitions")
            expected_started_at = (
                active_timestamps[0] if active_timestamps else None
            )
            if row["started_at"] != expected_started_at:
                history_reasons.add("started_at_differs")
            if len(terminal_timestamps) > 1:
                history_reasons.add("multiple_terminal_transitions")
            expected_completed_at = (
                terminal_timestamps[-1] if terminal_timestamps else None
            )
            if row["completed_at"] != expected_completed_at:
                history_reasons.add("completed_at_differs")
            if history_reasons:
                cls._finding(
                    findings,
                    "I3D-I2-TASK-HISTORY",
                    object_id=task_id,
                    task_id=task_id,
                    session_id=session_id,
                    table="task_state_transitions",
                    detail=(
                        "authoritative task history differs: "
                        + ",".join(sorted(history_reasons))
                    ),
                )
            if transaction_reasons:
                cls._finding(
                    findings,
                    "I3D-I2-TASK-TRANSACTION",
                    object_id=task_id,
                    task_id=task_id,
                    session_id=session_id,
                    table="task_state_transitions",
                    detail=(
                        "authoritative task transaction differs: "
                        + ",".join(sorted(transaction_reasons))
                    ),
                )

    @staticmethod
    def _was_live_at(
        connection: sqlite3.Connection,
        *,
        task_id: str,
        session_id: str,
        timestamp: str,
    ) -> bool:
        task_active = connection.execute(
            """
            SELECT 1 FROM task_state_transitions
            WHERE task_id = ? AND to_status = 'active' AND changed_at <= ?
            """,
            (task_id, timestamp),
        ).fetchone()
        task_terminal = connection.execute(
            """
            SELECT 1 FROM task_state_transitions
            WHERE task_id = ?
              AND to_status IN ('completed', 'stopped', 'failed')
              AND changed_at <= ?
            """,
            (task_id, timestamp),
        ).fetchone()
        session_open = connection.execute(
            """
            SELECT 1 FROM session_state_transitions
            WHERE session_id = ? AND to_status = 'open' AND changed_at <= ?
            """,
            (session_id, timestamp),
        ).fetchone()
        session_terminal = connection.execute(
            """
            SELECT 1 FROM session_state_transitions
            WHERE session_id = ?
              AND to_status IN ('closed', 'aborted')
              AND changed_at <= ?
            """,
            (session_id, timestamp),
        ).fetchone()
        return (
            task_active is not None
            and task_terminal is None
            and session_open is not None
            and session_terminal is None
        )

    @classmethod
    def _inspect_context(
        cls,
        connection: sqlite3.Connection,
        findings: list[SessionTaskIntegrityFinding],
    ) -> None:
        rows = tuple(
            connection.execute(
                """
                SELECT item.*, task.session_id AS authoritative_session_id,
                       task.project_scope_id AS authoritative_project_scope_id,
                       session_record.active_project_scope
                           AS session_project_scope_id
                FROM task_context_items AS item
                LEFT JOIN tasks AS task ON task.task_id = item.task_id
                LEFT JOIN sessions AS session_record
                  ON session_record.session_id = item.session_id
                ORDER BY item.task_id, item.injection_order
                """
            )
        )
        by_task: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            by_task.setdefault(row["task_id"], []).append(row)
            identifier = row["context_item_id"]
            try:
                source = _source_from_row(dict(row))
                item = TaskContextItem(
                    context_item_id=identifier,
                    task_id=row["task_id"],
                    session_id=row["session_id"],
                    project_scope_id=row["project_scope_id"],
                    context_kind=row["context_kind"],
                    source=source,
                    injection_order=row["injection_order"],
                    required=bool(row["required"]),
                    content_hash=row["content_hash"],
                    created_at=row["created_at"],
                    created_by_principal=row["created_by_principal"],
                )
                parsed = parse_json(row["canonical_json"])
                if (
                    canonical_json_text(parsed) != row["canonical_json"]
                    or parsed != item.canonical_value()
                ):
                    raise ValueError("canonical content differs from columns")
                if item.canonical_hash != row["canonical_hash"]:
                    raise ValueError("canonical hash differs")
            except Exception as exc:
                cls._finding(
                    findings,
                    "I3D-CONTEXT-CANONICAL",
                    object_id=identifier,
                    task_id=row["task_id"],
                    session_id=row["session_id"],
                    table="task_context_items",
                    detail=f"context canonical integrity failed: {exc}",
                )
            if (
                row["authoritative_session_id"] != row["session_id"]
                or row["authoritative_project_scope_id"]
                != row["project_scope_id"]
                or row["session_project_scope_id"] != row["project_scope_id"]
            ):
                cls._finding(
                    findings,
                    "I3D-CONTEXT-BINDING",
                    object_id=identifier,
                    task_id=row["task_id"],
                    session_id=row["session_id"],
                    table="task_context_items",
                    detail="context task, session and project binding differs",
                )
            if not cls._was_live_at(
                connection,
                task_id=row["task_id"],
                session_id=row["session_id"],
                timestamp=row["created_at"],
            ):
                cls._finding(
                    findings,
                    "I3D-CONTEXT-CREATION-STATE",
                    object_id=identifier,
                    task_id=row["task_id"],
                    session_id=row["session_id"],
                    table="task_context_items",
                    detail="context item was not created during a live task/session",
                )
            source_hash: str | None = None
            source_valid = True
            if row["source_kind"] == "memory_record":
                source_row = connection.execute(
                    """
                    SELECT record_family, record_type, project_scope_id,
                           content_hash
                    FROM records WHERE record_id = ?
                    """,
                    (row["source_memory_record_id"],),
                ).fetchone()
                source_valid = source_row is not None
                if source_row is not None:
                    source_hash = source_row["content_hash"]
                    source_valid = (
                        source_row["project_scope_id"] == row["project_scope_id"]
                        and (
                            (
                                row["context_kind"] == "construct_memory"
                                and source_row["record_family"]
                                == "construct_memory"
                            )
                            or (
                                row["context_kind"] == "approved_lesson"
                                and source_row["record_family"]
                                == "episodic_memory"
                                and source_row["record_type"]
                                == "approved_lesson"
                            )
                        )
                    )
            elif row["source_kind"] == "evidence":
                source_row = connection.execute(
                    """
                    SELECT evidence.content_hash, evidence.evidence_kind,
                           controlled.record_id AS controlled_record_id,
                           CASE WHEN EXISTS (
                               SELECT 1
                               FROM governance_decision_evidence
                                    AS evidence_input
                               JOIN governance_decisions AS decision_record
                                 ON decision_record.governance_decision_id =
                                    evidence_input.governance_decision_id
                               WHERE evidence_input.required_evidence_id =
                                     evidence.evidence_id
                                 AND evidence_input.resolved_evidence_id =
                                     evidence.evidence_id
                                 AND evidence_input.validation_status =
                                     'available'
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
                        row["task_id"],
                        row["project_scope_id"],
                        row["source_evidence_id"],
                    ),
                ).fetchone()
                source_valid = source_row is not None
                if source_row is not None:
                    source_hash = source_row["content_hash"]
                    source_valid = (
                        source_row["evidence_kind"]
                        not in {"controlled_prompt", "controlled_output"}
                        and source_row["controlled_record_id"] is None
                        and bool(source_row["task_bound"])
                    )
            else:
                source_row = connection.execute(
                    """
                    SELECT rule.content_hash, rule.status,
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
                        row["task_id"],
                        row["project_scope_id"],
                        row["source_governance_rule_id"],
                    ),
                ).fetchone()
                source_valid = source_row is not None
                if source_row is not None:
                    source_hash = source_row["content_hash"]
                    source_valid = (
                        source_row["status"] == "active"
                        and bool(source_row["task_bound"])
                    )
            if not source_valid or source_hash != row["content_hash"]:
                cls._finding(
                    findings,
                    "I3D-CONTEXT-SOURCE",
                    object_id=identifier,
                    task_id=row["task_id"],
                    session_id=row["session_id"],
                    table="task_context_items",
                    detail="typed context source or exact source hash is invalid",
                )

        for finalization in connection.execute(
            """
            SELECT * FROM task_context_finalizations
            ORDER BY finalized_at, finalization_id
            """
        ):
            task_id = finalization["task_id"]
            task_rows = by_task.get(task_id, [])
            authoritative = connection.execute(
                """
                SELECT task.task_id AS authoritative_task_id,
                       task.session_id AS authoritative_session_id,
                       task.project_scope_id
                           AS authoritative_project_scope_id,
                       session_record.session_id
                           AS authoritative_session_record_id,
                       session_record.active_project_scope
                           AS authoritative_session_project_scope_id
                FROM tasks AS task
                LEFT JOIN sessions AS session_record
                  ON session_record.session_id = task.session_id
                WHERE task.task_id = ?
                """,
                (task_id,),
            ).fetchone()
            binding_valid = (
                authoritative is not None
                and finalization["task_id"]
                == authoritative["authoritative_task_id"]
                and finalization["session_id"]
                == authoritative["authoritative_session_id"]
                and finalization["project_scope_id"]
                == authoritative["authoritative_project_scope_id"]
                and finalization["session_id"]
                == authoritative["authoritative_session_record_id"]
                and finalization["project_scope_id"]
                == authoritative[
                    "authoritative_session_project_scope_id"
                ]
                and cls._was_live_at(
                    connection,
                    task_id=finalization["task_id"],
                    session_id=finalization["session_id"],
                    timestamp=finalization["finalized_at"],
                )
            )
            if not binding_valid:
                cls._finding(
                    findings,
                    "I3D-CONTEXT-FINALIZATION-BINDING",
                    object_id=finalization["finalization_id"],
                    task_id=task_id,
                    session_id=finalization["session_id"],
                    table="task_context_finalizations",
                    detail=(
                        "context finalization differs from authoritative "
                        "task/session/project binding or historical live state"
                    ),
                )
            expected_orders = tuple(range(len(task_rows)))
            actual_orders = tuple(row["injection_order"] for row in task_rows)
            if (
                actual_orders != expected_orders
                or finalization["item_count"] != len(task_rows)
            ):
                cls._finding(
                    findings,
                    "I3D-CONTEXT-ORDER",
                    object_id=finalization["finalization_id"],
                    task_id=task_id,
                    session_id=finalization["session_id"],
                    table="task_context_finalizations",
                    detail="finalized context order is not complete and gap-free",
                )
            try:
                value = TaskContextFinalization(
                    finalization_id=finalization["finalization_id"],
                    task_id=task_id,
                    session_id=finalization["session_id"],
                    project_scope_id=finalization["project_scope_id"],
                    ordered_item_ids=tuple(
                        row["context_item_id"] for row in task_rows
                    ),
                    ordered_item_hashes=tuple(
                        row["canonical_hash"] for row in task_rows
                    ),
                    finalized_at=finalization["finalized_at"],
                    finalized_by_principal=
                        finalization["finalized_by_principal"],
                )
                parsed = parse_json(finalization["canonical_json"])
                if (
                    canonical_json_text(parsed) != finalization["canonical_json"]
                    or parsed != value.canonical_value()
                    or value.content_hash != finalization["content_hash"]
                ):
                    raise ValueError("finalization canonical content differs")
            except Exception as exc:
                cls._finding(
                    findings,
                    "I3D-CONTEXT-FINALIZATION",
                    object_id=finalization["finalization_id"],
                    task_id=task_id,
                    session_id=finalization["session_id"],
                    table="task_context_finalizations",
                    detail=f"context finalization integrity failed: {exc}",
                )

    @classmethod
    def _inspect_uncertainties(
        cls,
        connection: sqlite3.Connection,
        findings: list[SessionTaskIntegrityFinding],
    ) -> None:
        rows = tuple(
            connection.execute(
                """
                SELECT uncertainty.record_id AS uncertainty_record_id,
                       uncertainty.task_id AS uncertainty_task_id,
                       uncertainty.session_id AS uncertainty_session_id,
                       uncertainty.project_scope_id
                            AS uncertainty_project_scope_id,
                       uncertainty.uncertainty_statement,
                       uncertainty.impact,
                       uncertainty.resolution_required,
                       uncertainty.created_at AS uncertainty_created_at,
                       uncertainty.canonical_json
                            AS uncertainty_canonical_json,
                       uncertainty.created_by_principal
                            AS uncertainty_created_by_principal,
                       record.record_id AS envelope_record_id,
                       record.record_family AS envelope_record_family,
                       record.record_type AS envelope_record_type,
                       record.schema_version AS envelope_schema_version,
                       record.construct_scope_id
                            AS envelope_construct_scope_id,
                       record.project_scope_id
                            AS envelope_project_scope_id,
                       record.subject_entity_id
                            AS envelope_subject_entity_id,
                       record.session_id AS envelope_session_id,
                       record.task_id AS envelope_task_id,
                       record.lifecycle_state AS envelope_lifecycle_state,
                       record.approval_status AS envelope_approval_status,
                       record.authority_class AS envelope_authority_class,
                       record.certainty_class AS envelope_certainty_class,
                       record.sensitivity_class
                            AS envelope_sensitivity_class,
                       record.privacy_class AS envelope_privacy_class,
                       record.retention_class AS envelope_retention_class,
                       record.training_eligibility
                            AS envelope_training_eligibility,
                       record.created_at AS envelope_created_at,
                       record.created_by_entity_id
                            AS envelope_created_by_entity_id,
                       record.created_by_runtime_id
                            AS envelope_created_by_runtime_id,
                       record.effective_from AS envelope_effective_from,
                       record.effective_until AS envelope_effective_until,
                       record.review_due_at AS envelope_review_due_at,
                       record.supersedes_record_id
                            AS envelope_supersedes_record_id,
                       record.superseded_by_record_id
                            AS envelope_superseded_by_record_id,
                       record.previous_version_id
                            AS envelope_previous_version_id,
                       record.source_kind AS envelope_source_kind,
                       record.provenance_summary
                            AS envelope_provenance_summary,
                       record.retrieval_policy_json
                            AS envelope_retrieval_policy_json,
                       record.deletion_policy_json
                            AS envelope_deletion_policy_json,
                       record.agent_write_policy
                            AS envelope_agent_write_policy,
                       record.content_hash AS envelope_content_hash,
                       record.integrity_status AS envelope_integrity_status,
                       record.deleted_at AS envelope_deleted_at,
                       record.deletion_basis AS envelope_deletion_basis,
                       creator.entity_kind AS creator_kind
                FROM active_uncertainties AS uncertainty
                JOIN records AS record
                  ON record.record_id = uncertainty.record_id
                LEFT JOIN entities AS creator
                  ON creator.entity_id = record.created_by_entity_id
                ORDER BY uncertainty.created_at, uncertainty.record_id
                """
            )
        )
        payload_ids: set[str] = set()
        for row in rows:
            record_id = row["uncertainty_record_id"]
            payload_ids.add(record_id)
            task_id = row["uncertainty_task_id"]
            session_id = row["uncertainty_session_id"]
            try:
                payload = ActiveUncertaintyPayload(
                    record_id=record_id,
                    task_id=task_id,
                    session_id=session_id,
                    project_scope_id=row["uncertainty_project_scope_id"],
                    uncertainty_statement=row["uncertainty_statement"],
                    impact=row["impact"],
                    resolution_required=bool(row["resolution_required"]),
                    created_at=row["uncertainty_created_at"],
                    created_by_principal=
                        row["uncertainty_created_by_principal"],
                )
                envelope = _uncertainty_envelope(dict(row))
                parsed = parse_json(row["uncertainty_canonical_json"])
                if (
                    canonical_json_text(parsed)
                    != row["uncertainty_canonical_json"]
                    or parsed != payload.canonical_content()
                    or active_uncertainty_content_hash(envelope, payload)
                    != row["envelope_content_hash"]
                ):
                    raise ValueError("uncertainty canonical content differs")
            except Exception as exc:
                cls._finding(
                    findings,
                    "I3D-UNCERTAINTY-CANONICAL",
                    object_id=record_id,
                    task_id=task_id,
                    session_id=session_id,
                    table="active_uncertainties",
                    detail=f"uncertainty canonical integrity failed: {exc}",
                )
            if (
                row["envelope_record_id"] != record_id
                or row["envelope_task_id"] != task_id
                or row["envelope_session_id"] != session_id
                or row["envelope_project_scope_id"]
                != row["uncertainty_project_scope_id"]
                or row["envelope_created_at"]
                != row["uncertainty_created_at"]
            ):
                cls._finding(
                    findings,
                    "I3D-UNCERTAINTY-BINDING",
                    object_id=record_id,
                    task_id=task_id,
                    session_id=session_id,
                    table="active_uncertainties",
                    detail="uncertainty envelope binding differs from payload",
                )
            if not cls._was_live_at(
                connection,
                task_id=task_id,
                session_id=session_id,
                timestamp=row["uncertainty_created_at"],
            ):
                cls._finding(
                    findings,
                    "I3D-UNCERTAINTY-CREATION-STATE",
                    object_id=record_id,
                    task_id=task_id,
                    session_id=session_id,
                    table="active_uncertainties",
                    detail="uncertainty was not created during a live task/session",
                )
            expected_kind = (
                "person"
                if row["uncertainty_created_by_principal"] == "operator"
                else "system"
            )
            if row["creator_kind"] != expected_kind:
                cls._finding(
                    findings,
                    "I3D-UNCERTAINTY-CREATOR",
                    object_id=record_id,
                    task_id=task_id,
                    session_id=session_id,
                    table="active_uncertainties",
                    detail="uncertainty creator identity kind is invalid",
                )
            lifecycle_history = _transition_history(
                connection,
                record_id=record_id,
                effective_at=None,
                history_kind="lifecycle",
            )
            approval_history = _transition_history(
                connection,
                record_id=record_id,
                effective_at=None,
                history_kind="approval",
            )
            history_failures: list[str] = []
            if not lifecycle_history.valid:
                history_failures.append("lifecycle_history_invalid")
            if not approval_history.valid:
                history_failures.append("approval_history_invalid")
            if (
                lifecycle_history.latest_state
                != row["envelope_lifecycle_state"]
            ):
                history_failures.append("lifecycle_envelope_mismatch")
            if (
                approval_history.latest_state
                != row["envelope_approval_status"]
            ):
                history_failures.append("approval_envelope_mismatch")
            if history_failures:
                cls._finding(
                    findings,
                    "I3D-UNCERTAINTY-HISTORY",
                    object_id=record_id,
                    task_id=task_id,
                    session_id=session_id,
                    table="memory_record_lifecycle_transitions",
                    detail=(
                        "uncertainty transition history is invalid: "
                        + ",".join(history_failures)
                    ),
                )

        for row in connection.execute(
            """
            SELECT record_id, task_id, session_id
            FROM records
            WHERE record_family = 'session_task_memory'
              AND record_type = 'active_uncertainty'
            """
        ):
            if row["record_id"] not in payload_ids:
                cls._finding(
                    findings,
                    "I3D-UNCERTAINTY-PAYLOAD",
                    object_id=row["record_id"],
                    task_id=row["task_id"],
                    session_id=row["session_id"],
                    table="active_uncertainties",
                    detail="active-uncertainty record lacks its payload",
                )

        for row in connection.execute(
            "SELECT * FROM uncertainty_resolutions ORDER BY resolved_at, resolution_id"
        ):
            uncertainty = connection.execute(
                "SELECT * FROM active_uncertainties WHERE record_id = ?",
                (row["uncertainty_record_id"],),
            ).fetchone()
            if uncertainty is None:
                cls._finding(
                    findings,
                    "I3D-RESOLUTION-BINDING",
                    object_id=row["resolution_id"],
                    task_id=row["task_id"],
                    session_id=row["session_id"],
                    table="uncertainty_resolutions",
                    detail="resolution uncertainty payload is missing",
                )
                continue
            assessment = _resolution_effectiveness(
                connection,
                dict(row),
                dict(uncertainty),
            )
            reasons = set(assessment.reason_codes)
            if "resolution_canonical_invalid" in reasons:
                cls._finding(
                    findings,
                    "I3D-RESOLUTION-CANONICAL",
                    object_id=row["resolution_id"],
                    task_id=row["task_id"],
                    session_id=row["session_id"],
                    table="uncertainty_resolutions",
                    detail="resolution canonical integrity failed",
                )
            binding_reasons = reasons & {
                "resolution_binding_invalid",
                "uncertainty_not_current_at_resolution",
            }
            if binding_reasons:
                cls._finding(
                    findings,
                    "I3D-RESOLUTION-BINDING",
                    object_id=row["resolution_id"],
                    task_id=row["task_id"],
                    session_id=row["session_id"],
                    table="uncertainty_resolutions",
                    detail=(
                        "resolution binding, timestamp or uncertainty lifecycle "
                        "is invalid: "
                        + ",".join(sorted(binding_reasons))
                    ),
                )
            source_reasons = reasons - {
                "resolution_canonical_invalid",
                "resolution_binding_invalid",
                "uncertainty_not_current_at_resolution",
            }
            if source_reasons:
                cls._finding(
                    findings,
                    "I3D-RESOLUTION-SOURCE",
                    object_id=row["resolution_id"],
                    task_id=row["task_id"],
                    session_id=row["session_id"],
                    table="uncertainty_resolutions",
                    detail=(
                        "resolution source is currently ineffective: "
                        + ",".join(sorted(source_reasons))
                    ),
                )

    @classmethod
    def _inspect_connection(
        cls,
        connection: sqlite3.Connection,
    ) -> SessionTaskIntegrityReport:
        findings: list[SessionTaskIntegrityFinding] = []
        cls._inspect_existing_i2_runtime(connection, findings)
        cls._inspect_i2_sessions(connection, findings)
        cls._inspect_i2_tasks(connection, findings)
        cls._inspect_context(connection, findings)
        cls._inspect_uncertainties(connection, findings)
        return SessionTaskIntegrityReport(
            findings=tuple(
                sorted(
                    findings,
                    key=lambda item: (
                        item.source,
                        item.code,
                        item.table,
                        item.object_id or "",
                        item.task_id or "",
                        item.session_id or "",
                        item.detail,
                    ),
                )
            )
        )

    def inspect(self) -> SessionTaskIntegrityReport:
        return self._kernel.read(self._inspect_connection)
