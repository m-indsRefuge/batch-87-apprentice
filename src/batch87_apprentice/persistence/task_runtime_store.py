"""Internal atomic persistence store for the B87-I2 governed task runtime."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import (
    ConflictError,
    IntegrityInspectionError,
    NotFoundError,
    ValidationError,
)
from batch87_apprentice.common.hashing import (
    hashes_match,
    sha256_bytes,
    sha256_canonical_json,
)
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.governance.contracts import (
    AuthorityRecord,
    EvaluationResult,
    GovernanceRule,
    HumanApproval,
    OperationDefinition,
    PermissionProfile,
)
from batch87_apprentice.governance.engine import (
    AuthorityRuntimeContext,
    EvaluationContext,
    HumanApprovalRuntimeContext,
    EvaluationIdentifiers,
    GovernanceEngine,
)
from batch87_apprentice.protocols.task_contracts import (
    PolicyViolation,
    SessionContract,
    TaskContract,
)

from .config import DatabaseConfig
from .contracts import EvidenceItem
from .repositories import _insert_evidence
from .transactions import PersistenceKernel

_ZERO_HASH = "0" * 64


def _scope_contains(
    connection: sqlite3.Connection,
    *,
    ancestor_scope_id: str,
    descendant_scope_id: str,
) -> bool:
    row = connection.execute(
        """
        WITH RECURSIVE ancestry(scope_id, parent_scope_id, status) AS (
            SELECT scope_id, parent_scope_id, status
            FROM scopes
            WHERE scope_id = ?
            UNION ALL
            SELECT parent.scope_id, parent.parent_scope_id, parent.status
            FROM scopes AS parent
            JOIN ancestry AS child
              ON parent.scope_id = child.parent_scope_id
        )
        SELECT 1
        FROM ancestry
        WHERE scope_id = ? AND status = 'active'
        LIMIT 1
        """,
        (descendant_scope_id, ancestor_scope_id),
    ).fetchone()
    return row is not None


def _authority_from_row(row: sqlite3.Row) -> AuthorityRecord:
    return AuthorityRecord(
        authority_record_id=row["authority_record_id"],
        schema_version=row["schema_version"],
        authority_class=row["authority_class"],
        source_kind=row["source_kind"],
        effect=row["effect"],
        subject_principal=row["subject_principal"],
        permissions=tuple(parse_json(row["permissions_json"])),
        project_scope_id=row["project_scope_id"],
        scope_id=row["scope_id"],
        issuer_entity_id=row["issuer_entity_id"],
        task_id=row["task_id"],
        effective_from=row["effective_from"],
        effective_until=row["effective_until"],
        status=row["status"],
        registered_by_principal=row["registered_by_principal"],
        registered_at=row["registered_at"],
        evidence_ids=tuple(parse_json(row["evidence_ids_json"])),
        provenance_json=row["provenance_json"],
    )


def _operation_definition_from_row(row: sqlite3.Row) -> OperationDefinition:
    return OperationDefinition(
        name=row["operation_name"],
        schema_version=row["schema_version"],
        action_class=row["action_class"],
        autonomous=bool(row["autonomous"]),
        registered_by_principal=row["registered_by_principal"],
        registered_at=row["registered_at"],
        description=row["description"],
    )


def _human_approval_from_row(row: sqlite3.Row) -> HumanApproval:
    return HumanApproval(
        human_approval_id=row["human_approval_id"],
        schema_version=row["schema_version"],
        requested_operation=row["requested_operation"],
        subject_principal=row["subject_principal"],
        permissions=tuple(parse_json(row["permissions_json"])),
        project_scope_id=row["project_scope_id"],
        scope_id=row["scope_id"],
        task_id=row["task_id"],
        approved_by_entity_id=row["approved_by_entity_id"],
        approved_at=row["approved_at"],
        expires_at=row["expires_at"],
        conditions=tuple(parse_json(row["conditions_json"])),
        single_use=bool(row["single_use"]),
        evidence_ids=tuple(parse_json(row["evidence_ids_json"])),
        provenance_json=row["provenance_json"],
        registered_by_principal=row["registered_by_principal"],
        registered_at=row["registered_at"],
    )


def _transaction_value(
    *,
    transaction_id: str,
    task_id: str,
    runtime_instance_id: str,
    execution_principal: str,
    started_at: str,
    completed_at: str,
    status: str,
    task_contract_hash: str,
    decision_hash: str,
    stop_hash: str | None,
    structured_failures: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "completed_at": completed_at,
        "decision_hash": decision_hash,
        "execution_principal": execution_principal,
        "runtime_instance_id": runtime_instance_id,
        "started_at": started_at,
        "status": status,
        "stop_hash": stop_hash,
        "structured_failures": structured_failures,
        "task_contract_hash": task_contract_hash,
        "task_id": task_id,
        "transaction_id": transaction_id,
    }


def _evidence_inputs(
    task: TaskContract,
    authorities: Mapping[str, AuthorityRecord],
    approvals: Mapping[str, HumanApproval],
    policy_violations: tuple[PolicyViolation, ...],
) -> tuple[tuple[str, str], ...]:
    values: list[tuple[str, str]] = [
        ("task", evidence_id)
        for evidence_id in task.required_evidence_ids
    ]
    for authority_id in task.claimed_authority_ids:
        record = authorities.get(authority_id)
        if record is not None:
            values.extend(
                ("authority", evidence_id)
                for evidence_id in record.evidence_ids
            )
    for approval_id in task.claimed_human_approval_ids:
        approval = approvals.get(approval_id)
        if approval is not None:
            values.extend(
                ("approval", evidence_id)
                for evidence_id in approval.evidence_ids
            )
    for violation in policy_violations:
        values.extend(
            ("policy", evidence_id)
            for evidence_id in violation.evidence_ids
        )
    return tuple(dict.fromkeys(values))


def _available_evidence_ids(
    connection: sqlite3.Connection,
    evidence_ids: Iterable[str],
) -> frozenset[str]:
    identifiers = tuple(sorted(set(evidence_ids)))
    if not identifiers:
        return frozenset()
    placeholders = ",".join("?" for _ in identifiers)
    return frozenset(
        row["evidence_id"]
        for row in connection.execute(
            f"""
            SELECT evidence_id
            FROM evidence_items
            WHERE evidence_id IN ({placeholders})
              AND integrity_status = 'valid'
              AND evidence_kind NOT IN ('controlled_prompt', 'controlled_output')
            """,
            identifiers,
        )
    )


class TaskRuntimeStore:
    """Keep all I2 writes behind the accepted I1 BEGIN IMMEDIATE boundary."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._kernel = PersistenceKernel(config)

    def ensure_policy_baseline(
        self,
        permission_profile: PermissionProfile,
        governance_rules: tuple[GovernanceRule, ...],
    ) -> None:
        """Idempotently register immutable deterministic policy inputs."""

        def operation(connection: sqlite3.Connection) -> None:
            stored_profile = connection.execute(
                """
                SELECT canonical_json, content_hash
                FROM permission_profiles
                WHERE permission_profile_id = ?
                """,
                (permission_profile.permission_profile_id,),
            ).fetchone()
            if stored_profile is None:
                connection.execute(
                    """
                    INSERT INTO permission_profiles (
                        permission_profile_id, version, principal,
                        allowed_action_classes_json,
                        prohibited_action_classes_json, allowed_tools_json,
                        prohibited_tools_json, effective_from, canonical_json,
                        content_hash, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    """,
                    (
                        permission_profile.permission_profile_id,
                        permission_profile.version,
                        permission_profile.principal,
                        canonical_json_text(
                            list(permission_profile.allowed_action_classes)
                        ),
                        canonical_json_text(
                            list(permission_profile.prohibited_action_classes)
                        ),
                        canonical_json_text(
                            list(permission_profile.allowed_tools)
                        ),
                        canonical_json_text(
                            list(permission_profile.prohibited_tools)
                        ),
                        permission_profile.effective_from,
                        permission_profile.canonical_json,
                        permission_profile.content_hash,
                    ),
                )
            elif (
                stored_profile["canonical_json"]
                != permission_profile.canonical_json
                or stored_profile["content_hash"]
                != permission_profile.content_hash
            ):
                raise ConflictError(
                    "stored permission profile conflicts with B87-S1"
                )

            for rule in governance_rules:
                rule_json = canonical_json_text(rule.canonical_value())
                stored_rule = connection.execute(
                    """
                    SELECT content_hash, configuration_json, description,
                           rule_name, rule_version, rule_kind
                    FROM governance_rules
                    WHERE governance_rule_id = ?
                    """,
                    (rule.governance_rule_id,),
                ).fetchone()
                if stored_rule is None:
                    connection.execute(
                        """
                        INSERT INTO governance_rules (
                            governance_rule_id, rule_name, rule_version,
                            rule_kind, description, configuration_json,
                            content_hash, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                        """,
                        (
                            rule.governance_rule_id,
                            rule.name,
                            rule.version,
                            rule.kind,
                            rule.description,
                            rule.configuration_json,
                            rule.content_hash,
                        ),
                    )
                else:
                    stored_value = {
                        "configuration": parse_json(
                            stored_rule["configuration_json"]
                        ),
                        "description": stored_rule["description"],
                        "governance_rule_id": rule.governance_rule_id,
                        "kind": stored_rule["rule_kind"],
                        "name": stored_rule["rule_name"],
                        "version": stored_rule["rule_version"],
                    }
                    if (
                        canonical_json_text(stored_value) != rule_json
                        or stored_rule["content_hash"] != rule.content_hash
                    ):
                        raise ConflictError(
                            f"stored governance rule conflicts: {rule.name}"
                        )

        self._kernel.write(operation)

    def open_session(
        self,
        session: SessionContract,
        *,
        initial_transition_id: str,
        changed_by_principal: str,
    ) -> str:
        """Persist one exact session identity and participant set atomically."""

        validate_identifier(
            initial_transition_id,
            field="initial_transition_id",
        )

        def operation(connection: sqlite3.Connection) -> str:
            project = connection.execute(
                """
                SELECT scope_kind, status
                FROM scopes
                WHERE scope_id = ?
                """,
                (session.project_scope_id,),
            ).fetchone()
            if (
                project is None
                or project["scope_kind"] != "project"
                or project["status"] != "active"
            ):
                raise ValidationError(
                    "session project scope must be an active project"
                )
            existing = connection.execute(
                """
                SELECT canonical_json, content_hash
                FROM sessions
                WHERE session_id = ?
                """,
                (session.session_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["canonical_json"] != session.canonical_json
                    or existing["content_hash"] != session.content_hash
                ):
                    raise ConflictError(
                        "session identity conflicts with stored contract"
                    )
                return session.content_hash

            connection.execute(
                """
                INSERT INTO sessions (
                    session_id, contract_version, session_purpose, opened_at,
                    closed_at, active_project_scope, session_status,
                    retention_disposition, created_by_entity_id,
                    canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.contract_version,
                    session.purpose,
                    session.opened_at,
                    session.closed_at,
                    session.project_scope_id,
                    session.status,
                    session.retention_disposition,
                    session.created_by_entity_id,
                    session.canonical_json,
                    session.content_hash,
                ),
            )
            connection.executemany(
                """
                INSERT INTO session_participants (
                    session_id, entity_id, role
                ) VALUES (?, ?, ?)
                """,
                (
                    (
                        session.session_id,
                        entity_id,
                        (
                            "operator"
                            if entity_id == session.created_by_entity_id
                            else "participant"
                        ),
                    )
                    for entity_id in session.participant_entity_ids
                ),
            )
            connection.execute(
                """
                INSERT INTO session_state_transitions (
                    transition_id, session_id, sequence_number, from_status,
                    to_status, reason_code, changed_at, changed_by_principal
                ) VALUES (?, ?, 0, NULL, 'open', 'session_opened', ?, ?)
                """,
                (
                    initial_transition_id,
                    session.session_id,
                    session.opened_at,
                    changed_by_principal,
                ),
            )
            return session.content_hash

        return self._kernel.write(operation)

    @staticmethod
    def _ensure_authority(
        connection: sqlite3.Connection,
        record: AuthorityRecord,
        available_evidence_ids: frozenset[str],
    ) -> None:
        existing = connection.execute(
            """
            SELECT * FROM authority_records
            WHERE authority_record_id = ?
            """,
            (record.authority_record_id,),
        ).fetchone()
        is_new = existing is None
        if existing is None:
            connection.execute(
                """
                INSERT INTO authority_records (
                    authority_record_id, schema_version, authority_class,
                    source_kind, effect, subject_principal, permissions_json,
                    project_scope_id, scope_id, issuer_entity_id, task_id,
                    effective_from, effective_until, status,
                    registered_by_principal, registered_at,
                    evidence_ids_json, provenance_json, canonical_json,
                    content_hash
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    record.authority_record_id,
                    record.schema_version,
                    record.authority_class,
                    record.source_kind,
                    record.effect,
                    record.subject_principal,
                    canonical_json_text(list(record.permissions)),
                    record.project_scope_id,
                    record.scope_id,
                    record.issuer_entity_id,
                    record.task_id,
                    record.effective_from,
                    record.effective_until,
                    record.status,
                    record.registered_by_principal,
                    record.registered_at,
                    canonical_json_text(list(record.evidence_ids)),
                    record.provenance_json,
                    record.canonical_json,
                    record.content_hash,
                ),
            )
        else:
            stored = _authority_from_row(existing)
            if (
                existing["content_hash"] != record.content_hash
                or stored.canonical_json != record.canonical_json
            ):
                raise ConflictError(
                    f"authority record conflicts: {record.authority_record_id}"
                )

        linked_evidence = tuple(
            row["evidence_id"]
            for row in connection.execute(
                """
                SELECT evidence_id
                FROM authority_record_evidence
                WHERE authority_record_id = ?
                ORDER BY evidence_order
                """,
                (record.authority_record_id,),
            )
        )
        if not is_new:
            if linked_evidence != record.evidence_ids:
                raise IntegrityInspectionError(
                    "stored authority evidence relationships are incomplete"
                )
            return
        connection.executemany(
            """
            INSERT INTO authority_record_evidence (
                authority_record_id, evidence_id, evidence_order
            ) VALUES (?, ?, ?)
            """,
            (
                (record.authority_record_id, evidence_id, index)
                for index, evidence_id in enumerate(record.evidence_ids)
                if evidence_id in available_evidence_ids
            ),
        )

    def register_authority(
        self,
        record: AuthorityRecord,
        evidence_items: tuple[EvidenceItem, ...],
    ) -> str:
        """Register authority separately from any task that may later claim it."""

        evidence_map = {item.evidence_id: item for item in evidence_items}
        if len(evidence_map) != len(evidence_items):
            raise ValidationError("authority evidence contains duplicate identifiers")
        extra_evidence = set(evidence_map) - set(record.evidence_ids)
        if extra_evidence:
            raise ValidationError(
                "unreferenced evidence cannot enter authority registration"
            )
        if record.subject_principal == "apprentice" and (
            set(record.permissions) - {"observe", "analyse"}
        ):
            raise ValidationError(
                "no authority record may grant Apprentice Propose or Execute in B87-S1"
            )
        if record.subject_principal == "experimental_harness":
            raise ValidationError(
                "experimental harness production authority is unavailable"
            )

        def operation(connection: sqlite3.Connection) -> str:
            for item in evidence_items:
                _insert_evidence(connection, item)
            evidence_rows = (
                {
                    row["evidence_id"]: row
                    for row in connection.execute(
                        f"""
                        SELECT evidence_id, evidence_kind, integrity_status
                        FROM evidence_items
                        WHERE evidence_id IN (
                            {",".join("?" for _ in record.evidence_ids)}
                        )
                        """,
                        record.evidence_ids,
                    )
                }
                if record.evidence_ids
                else {}
            )
            invalid = tuple(
                evidence_id
                for evidence_id in record.evidence_ids
                if (
                    evidence_id not in evidence_rows
                    or evidence_rows[evidence_id]["integrity_status"] != "valid"
                    or evidence_rows[evidence_id]["evidence_kind"]
                    in {"model_output", "controlled_prompt", "controlled_output"}
                )
            )
            if invalid:
                raise ValidationError(
                    "authority registration requires valid non-model, "
                    "non-controlled evidence"
                )
            self._ensure_authority(
                connection,
                record,
                frozenset(record.evidence_ids),
            )
            return record.content_hash

        return self._kernel.write(operation)

    def register_operation_definition(
        self,
        definition: OperationDefinition,
    ) -> str:
        """Register one immutable deterministic operation definition."""

        def operation(connection: sqlite3.Connection) -> str:
            existing = connection.execute(
                "SELECT * FROM operation_definitions WHERE operation_name = ?",
                (definition.name,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO operation_definitions (
                        operation_name, schema_version, action_class, autonomous,
                        registered_by_principal, registered_at, description,
                        canonical_json, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        definition.name,
                        definition.schema_version,
                        definition.action_class,
                        int(definition.autonomous),
                        definition.registered_by_principal,
                        definition.registered_at,
                        definition.description,
                        definition.canonical_json,
                        definition.content_hash,
                    ),
                )
            else:
                stored = _operation_definition_from_row(existing)
                if (
                    stored.canonical_json != definition.canonical_json
                    or existing["content_hash"] != definition.content_hash
                ):
                    raise ConflictError(
                        f"operation definition conflicts: {definition.name}"
                    )
            return definition.content_hash

        return self._kernel.write(operation)

    def register_human_approval(
        self,
        approval: HumanApproval,
        evidence_items: tuple[EvidenceItem, ...],
    ) -> str:
        """Register explicit human approval before a task may claim it."""

        evidence_map = {item.evidence_id: item for item in evidence_items}
        if len(evidence_map) != len(evidence_items):
            raise ValidationError("approval evidence contains duplicate identifiers")
        if set(evidence_map) - set(approval.evidence_ids):
            raise ValidationError(
                "unreferenced evidence cannot enter approval registration"
            )

        def operation(connection: sqlite3.Connection) -> str:
            definition = connection.execute(
                "SELECT content_hash FROM operation_definitions WHERE operation_name = ?",
                (approval.requested_operation,),
            ).fetchone()
            if definition is None:
                raise ValidationError(
                    "human approval requires a registered operation definition"
                )
            for item in evidence_items:
                _insert_evidence(connection, item)
            available = _available_evidence_ids(connection, approval.evidence_ids)
            if set(available) != set(approval.evidence_ids):
                raise ValidationError(
                    "human approval requires valid non-model evidence"
                )
            existing = connection.execute(
                "SELECT * FROM human_approvals WHERE human_approval_id = ?",
                (approval.human_approval_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO human_approvals (
                        human_approval_id, schema_version, requested_operation,
                        subject_principal, permissions_json, project_scope_id,
                        scope_id, task_id, approved_by_entity_id, approved_at,
                        expires_at, conditions_json, single_use, consumed_at,
                        consumed_by_task_id, consumed_by_decision_id,
                        evidence_ids_json, provenance_json,
                        registered_by_principal, registered_at, canonical_json,
                        content_hash
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL,
                        NULL, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        approval.human_approval_id,
                        approval.schema_version,
                        approval.requested_operation,
                        approval.subject_principal,
                        canonical_json_text(list(approval.permissions)),
                        approval.project_scope_id,
                        approval.scope_id,
                        approval.task_id,
                        approval.approved_by_entity_id,
                        approval.approved_at,
                        approval.expires_at,
                        canonical_json_text(list(approval.conditions)),
                        int(approval.single_use),
                        canonical_json_text(list(approval.evidence_ids)),
                        approval.provenance_json,
                        approval.registered_by_principal,
                        approval.registered_at,
                        approval.canonical_json,
                        approval.content_hash,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO human_approval_evidence (
                        human_approval_id, evidence_id, evidence_order
                    ) VALUES (?, ?, ?)
                    """,
                    (
                        (approval.human_approval_id, evidence_id, index)
                        for index, evidence_id in enumerate(approval.evidence_ids)
                    ),
                )
            else:
                stored = _human_approval_from_row(existing)
                if (
                    stored.canonical_json != approval.canonical_json
                    or existing["content_hash"] != approval.content_hash
                ):
                    raise ConflictError(
                        f"human approval conflicts: {approval.human_approval_id}"
                    )
                linked = tuple(
                    row["evidence_id"]
                    for row in connection.execute(
                        """
                        SELECT evidence_id FROM human_approval_evidence
                        WHERE human_approval_id = ? ORDER BY evidence_order
                        """,
                        (approval.human_approval_id,),
                    )
                )
                if linked != approval.evidence_ids:
                    raise IntegrityInspectionError(
                        "stored human approval evidence is incomplete"
                    )
            return approval.content_hash

        return self._kernel.write(operation)

    def revoke_authority(
        self,
        *,
        authority_record_id: str,
        revoked_at: str,
        revoked_by_entity_id: str,
        reason: str,
        registered_by_principal: str,
        provenance_json: str,
    ) -> str:
        """Persist one append-only authority revocation."""

        validate_identifier(authority_record_id, field="authority_record_id")
        validate_identifier(revoked_by_entity_id, field="revoked_by_entity_id")
        value = {
            "authority_record_id": authority_record_id,
            "provenance": parse_json(provenance_json),
            "reason": reason,
            "registered_by_principal": registered_by_principal,
            "revoked_at": revoked_at,
            "revoked_by_entity_id": revoked_by_entity_id,
        }
        canonical = canonical_json_text(value)
        content_hash = sha256_canonical_json(value)

        def operation(connection: sqlite3.Connection) -> str:
            authority = connection.execute(
                "SELECT 1 FROM authority_records WHERE authority_record_id = ?",
                (authority_record_id,),
            ).fetchone()
            if authority is None:
                raise NotFoundError(f"authority not found: {authority_record_id}")
            existing = connection.execute(
                "SELECT canonical_json, content_hash FROM authority_revocations WHERE authority_record_id = ?",
                (authority_record_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO authority_revocations (
                        authority_record_id, revoked_at, revoked_by_entity_id,
                        reason, registered_by_principal, provenance_json,
                        canonical_json, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        authority_record_id, revoked_at, revoked_by_entity_id,
                        reason, registered_by_principal, provenance_json,
                        canonical, content_hash,
                    ),
                )
            elif (
                existing["canonical_json"] != canonical
                or existing["content_hash"] != content_hash
            ):
                raise ConflictError("authority already has a different revocation")
            return content_hash

        return self._kernel.write(operation)

    def transition_session(
        self,
        *,
        session_id: str,
        to_status: str,
        transition_id: str,
        changed_at: str,
        changed_by_principal: str,
        reason_code: str,
    ) -> str:
        """Append and apply one governed session lifecycle transition."""

        def operation(connection: sqlite3.Connection) -> str:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"session not found: {session_id}")
            canonical_session = parse_json(row["canonical_json"])
            participants = tuple(canonical_session["participant_entity_ids"])
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence_number), -1) + 1 FROM session_state_transitions WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO session_state_transitions (
                    transition_id, session_id, sequence_number, from_status,
                    to_status, reason_code, changed_at, changed_by_principal
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition_id, session_id, sequence, row["session_status"],
                    to_status, reason_code, changed_at, changed_by_principal,
                ),
            )
            updated = SessionContract(
                session_id=session_id,
                purpose=row["session_purpose"],
                project_scope_id=row["active_project_scope"],
                opened_at=row["opened_at"],
                created_by_entity_id=row["created_by_entity_id"],
                participant_entity_ids=participants,
                status=to_status,
                retention_disposition=row["retention_disposition"],
                closed_at=(changed_at if to_status in {"closed", "aborted"} else None),
                contract_version=row["contract_version"],
            )
            connection.execute(
                """
                UPDATE sessions
                SET session_status = ?, closed_at = ?, canonical_json = ?,
                    content_hash = ?
                WHERE session_id = ?
                """,
                (
                    updated.status, updated.closed_at, updated.canonical_json,
                    updated.content_hash, session_id,
                ),
            )
            return updated.content_hash

        return self._kernel.write(operation)

    def transition_task(
        self,
        *,
        task_id: str,
        to_status: str,
        transition_id: str,
        changed_at: str,
        reason_code: str,
    ) -> str:
        """Append and apply one governed terminal transition for an active task."""

        validate_identifier(task_id, field="task_id")
        validate_identifier(transition_id, field="task_transition_id")
        if to_status not in {"completed", "failed"}:
            raise ValidationError(
                "active tasks may transition only to completed or failed here"
            )
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise ValidationError("task transition reason_code must be non-empty")

        def operation(connection: sqlite3.Connection) -> str:
            row = connection.execute(
                "SELECT status FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"task not found: {task_id}")
            if row["status"] != "active":
                raise ConflictError("only active tasks can be completed or failed")
            transaction = connection.execute(
                "SELECT transaction_id FROM governed_runtime_transactions WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if transaction is None:
                raise IntegrityInspectionError(
                    "task transition requires its governed transaction"
                )
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence_number), -1) + 1 FROM task_state_transitions WHERE task_id = ?",
                (task_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO task_state_transitions (
                    transition_id, task_id, sequence_number, from_status,
                    to_status, reason_code, changed_at, changed_by, transaction_id
                ) VALUES (?, ?, ?, 'active', ?, ?, ?, 'governance_kernel', ?)
                """,
                (
                    transition_id, task_id, sequence, to_status, reason_code,
                    changed_at, transaction["transaction_id"],
                ),
            )
            connection.execute(
                "UPDATE tasks SET status = ?, completed_at = ? WHERE task_id = ?",
                (to_status, changed_at, task_id),
            )
            return transition_id

        return self._kernel.write(operation)

    def evaluate_task(
        self,
        *,
        task: TaskContract,
        evidence_items: tuple[EvidenceItem, ...],
        policy_violations: tuple[PolicyViolation, ...],
        permission_profile: PermissionProfile,
        governance_rules: tuple[GovernanceRule, ...],
        engine: GovernanceEngine,
        identifiers: EvaluationIdentifiers,
        decided_at: str,
        runtime_instance_id: str,
        runtime_execution_principal: str,
    ) -> EvaluationResult:
        """Evaluate and persist one task as a single governed transaction."""

        evidence_map = {item.evidence_id: item for item in evidence_items}
        if len(evidence_map) != len(evidence_items):
            raise ValidationError("evidence inputs contain duplicate identifiers")
        allowed_evidence_ids = {
            evidence_id
            for _, evidence_id in _evidence_inputs(
                task,
                {},
                {},
                policy_violations,
            )
        }
        extra_evidence = set(evidence_map) - allowed_evidence_ids
        if extra_evidence:
            raise ValidationError(
                "unreferenced evidence cannot enter a task transaction"
            )

        def operation(connection: sqlite3.Connection) -> EvaluationResult:
            observed_policy_violations = list(policy_violations)
            runtime = connection.execute(
                """
                SELECT status FROM runtime_instances
                WHERE runtime_instance_id = ?
                """,
                (runtime_instance_id,),
            ).fetchone()
            if runtime is None or runtime["status"] != "running":
                raise ValidationError(
                    "governance decision requires a running runtime instance"
                )

            session = connection.execute(
                """
                SELECT active_project_scope, session_status,
                       created_by_entity_id
                FROM sessions WHERE session_id = ?
                """,
                (task.session_id,),
            ).fetchone()
            project = connection.execute(
                "SELECT scope_kind, status FROM scopes WHERE scope_id = ?",
                (task.project_scope_id,),
            ).fetchone()
            requested = connection.execute(
                "SELECT status FROM scopes WHERE scope_id = ?",
                (task.requested_scope_id,),
            ).fetchone()
            session_valid = (
                session is not None
                and session["active_project_scope"] == task.project_scope_id
                and session["session_status"] in {"open", "paused"}
            )
            project_valid = (
                project is not None
                and project["scope_kind"] == "project"
                and project["status"] == "active"
            )
            requested_valid = (
                requested is not None
                and requested["status"] == "active"
                and _scope_contains(
                    connection,
                    ancestor_scope_id=task.project_scope_id,
                    descendant_scope_id=task.requested_scope_id,
                )
            )

            for item in evidence_items:
                _insert_evidence(connection, item)

            operation_definition: OperationDefinition | None = None
            operation_row = connection.execute(
                "SELECT * FROM operation_definitions WHERE operation_name = ?",
                (task.requested_operation.name,),
            ).fetchone()
            if operation_row is not None:
                try:
                    candidate = _operation_definition_from_row(operation_row)
                    if (
                        operation_row["canonical_json"] == candidate.canonical_json
                        and hashes_match(
                            operation_row["content_hash"],
                            candidate.content_hash,
                        )
                    ):
                        operation_definition = candidate
                    else:
                        raise ValidationError("operation definition hash mismatch")
                except ValidationError:
                    observed_policy_violations.append(
                        PolicyViolation(
                            code="integrity_violation",
                            source="operation_definition_integrity",
                            detail=(
                                "The registered operation definition failed "
                                "canonical integrity verification."
                            ),
                        )
                    )

            resolved_authorities: dict[str, AuthorityRecord] = {}
            for authority_id in task.claimed_authority_ids:
                row = connection.execute(
                    "SELECT * FROM authority_records WHERE authority_record_id = ?",
                    (authority_id,),
                ).fetchone()
                if row is None:
                    continue
                try:
                    record = _authority_from_row(row)
                    if (
                        not hashes_match(row["content_hash"], record.content_hash)
                        or row["canonical_json"] != record.canonical_json
                    ):
                        raise ValidationError("authority hash mismatch")
                except ValidationError:
                    observed_policy_violations.append(
                        PolicyViolation(
                            code="integrity_violation",
                            source="authority_integrity",
                            detail=(
                                "A claimed authority record failed canonical "
                                "integrity verification."
                            ),
                        )
                    )
                    continue
                resolved_authorities[authority_id] = record

            resolved_approvals: dict[str, HumanApproval] = {}
            approval_rows: dict[str, sqlite3.Row] = {}
            for approval_id in task.claimed_human_approval_ids:
                row = connection.execute(
                    "SELECT * FROM human_approvals WHERE human_approval_id = ?",
                    (approval_id,),
                ).fetchone()
                if row is None:
                    continue
                try:
                    approval = _human_approval_from_row(row)
                    if (
                        not hashes_match(row["content_hash"], approval.content_hash)
                        or row["canonical_json"] != approval.canonical_json
                    ):
                        raise ValidationError("human approval hash mismatch")
                except ValidationError:
                    observed_policy_violations.append(
                        PolicyViolation(
                            code="integrity_violation",
                            source="human_approval_integrity",
                            detail=(
                                "A claimed human approval failed canonical "
                                "integrity verification."
                            ),
                        )
                    )
                    continue
                resolved_approvals[approval_id] = approval
                approval_rows[approval_id] = row

            effective_policy_violations = tuple(observed_policy_violations)
            referenced_evidence = {
                evidence_id
                for _, evidence_id in _evidence_inputs(
                    task,
                    resolved_authorities,
                    resolved_approvals,
                    effective_policy_violations,
                )
            }
            available_evidence = _available_evidence_ids(
                connection,
                referenced_evidence,
            )

            authority_contexts: dict[str, AuthorityRuntimeContext] = {}
            for authority_id, record in resolved_authorities.items():
                linked_evidence = {
                    row["evidence_id"]
                    for row in connection.execute(
                        """
                        SELECT evidence_id FROM authority_record_evidence
                        WHERE authority_record_id = ?
                        """,
                        (authority_id,),
                    )
                }
                revoked = connection.execute(
                    "SELECT 1 FROM authority_revocations WHERE authority_record_id = ?",
                    (authority_id,),
                ).fetchone() is not None
                authority_contexts[authority_id] = AuthorityRuntimeContext(
                    scope_matches=(
                        _scope_contains(
                            connection,
                            ancestor_scope_id=record.scope_id,
                            descendant_scope_id=task.requested_scope_id,
                        )
                        if requested_valid
                        else False
                    ),
                    evidence_complete=all(
                        evidence_id in available_evidence
                        and evidence_id in linked_evidence
                        for evidence_id in record.evidence_ids
                    ),
                    issuer_is_session_operator=(
                        session is not None
                        and record.issuer_entity_id
                        == session["created_by_entity_id"]
                    ),
                    revoked=revoked,
                )

            approval_contexts: dict[str, HumanApprovalRuntimeContext] = {}
            for approval_id, approval in resolved_approvals.items():
                linked_evidence = {
                    row["evidence_id"]
                    for row in connection.execute(
                        """
                        SELECT evidence_id FROM human_approval_evidence
                        WHERE human_approval_id = ?
                        """,
                        (approval_id,),
                    )
                }
                stored = approval_rows[approval_id]
                approval_contexts[approval_id] = HumanApprovalRuntimeContext(
                    scope_matches=(
                        _scope_contains(
                            connection,
                            ancestor_scope_id=approval.scope_id,
                            descendant_scope_id=task.requested_scope_id,
                        )
                        if requested_valid
                        else False
                    ),
                    evidence_complete=all(
                        evidence_id in available_evidence
                        and evidence_id in linked_evidence
                        for evidence_id in approval.evidence_ids
                    ),
                    approver_is_session_operator=(
                        session is not None
                        and approval.approved_by_entity_id
                        == session["created_by_entity_id"]
                    ),
                    consumed_by_task_id=stored["consumed_by_task_id"],
                    consumed_at=stored["consumed_at"],
                )

            connection.execute(
                """
                INSERT INTO governed_runtime_transactions (
                    transaction_id, task_id, runtime_instance_id,
                    execution_principal, started_at, completed_at, status,
                    structured_failure_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, NULL, 'in_progress', '[]', ?)
                """,
                (
                    identifiers.transaction_id,
                    task.task_id,
                    runtime_instance_id,
                    runtime_execution_principal,
                    decided_at,
                    _ZERO_HASH,
                ),
            )
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, session_id, contract_version, objective, task_type,
                    project_scope_id, requested_scope_id, requested_operation,
                    requested_action_class, operation_autonomous,
                    requesting_principal, authority_grant_json,
                    claimed_authority_ids_json,
                    claimed_human_approval_ids_json, allowed_sources_json,
                    prohibited_actions_json, expected_output_schema_id,
                    stop_conditions_json, governing_constraints_json,
                    required_evidence_ids_json, effective_at, provenance_json,
                    canonical_contract_json, contract_hash, status, created_at,
                    started_at, completed_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL
                )
                """,
                (
                    task.task_id,
                    task.session_id,
                    task.contract_version,
                    task.objective,
                    task.task_type,
                    task.project_scope_id,
                    task.requested_scope_id,
                    task.requested_operation.name,
                    task.requested_operation.action_class,
                    int(task.requested_operation.autonomous),
                    task.requesting_principal,
                    canonical_json_text(list(task.authority_grant)),
                    canonical_json_text(list(task.claimed_authority_ids)),
                    canonical_json_text(list(task.claimed_human_approval_ids)),
                    canonical_json_text(list(task.allowed_sources)),
                    canonical_json_text(list(task.prohibited_actions)),
                    task.expected_output_schema_id,
                    canonical_json_text(list(task.stop_conditions)),
                    canonical_json_text(list(task.governing_constraints)),
                    canonical_json_text(list(task.required_evidence_ids)),
                    task.effective_at,
                    task.provenance_json,
                    task.canonical_json,
                    task.content_hash,
                    decided_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO task_state_transitions (
                    transition_id, task_id, sequence_number, from_status,
                    to_status, reason_code, changed_at, changed_by,
                    transaction_id
                ) VALUES (?, ?, 0, NULL, 'pending', 'task_contract_registered',
                          ?, 'governance_kernel', ?)
                """,
                (
                    identifiers.initial_transition_id,
                    task.task_id,
                    decided_at,
                    identifiers.transaction_id,
                ),
            )

            result = engine.evaluate(
                task=task,
                authorities=resolved_authorities,
                human_approvals=resolved_approvals,
                permission_profile=permission_profile,
                policy_violations=effective_policy_violations,
                context=EvaluationContext(
                    session_valid=session_valid,
                    project_scope_valid=project_valid,
                    requested_scope_valid=requested_valid,
                    available_evidence_ids=available_evidence,
                    authority_contexts=authority_contexts,
                    human_approval_contexts=approval_contexts,
                    operation_definition=operation_definition,
                ),
                identifiers=identifiers,
                decided_at=decided_at,
                runtime_instance_id=runtime_instance_id,
                runtime_execution_principal=runtime_execution_principal,
            )
            decision = result.decision
            connection.execute(
                """
                INSERT INTO governance_decisions (
                    governance_decision_id, transaction_id, task_id, session_id,
                    project_scope_id, requested_scope_id, requesting_principal,
                    runtime_execution_principal, requested_operation,
                    requested_action_class, operation_definition_hash,
                    permission_profile_id, permission_profile_hash,
                    permission_profile_applicable,
                    precedence_authority_class, decision, reason_codes_json,
                    reasons_json, authority_assessments_json,
                    human_approval_assessments_json,
                    evidence_assessments_json, policy_violations_json,
                    effective_at, evidence_ids_json, governing_rule_ids_json,
                    decided_at, runtime_instance_id, task_contract_hash,
                    provenance_json, apprentice_execute_implication,
                    canonical_json, content_hash
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?
                )
                """,
                (
                    decision.governance_decision_id,
                    decision.transaction_id,
                    decision.task_id,
                    decision.session_id,
                    decision.project_scope_id,
                    decision.requested_scope_id,
                    decision.requesting_principal,
                    decision.runtime_execution_principal,
                    decision.requested_operation.name,
                    decision.requested_operation.action_class,
                    decision.operation_definition_hash,
                    decision.permission_profile_id,
                    decision.permission_profile_hash,
                    int(decision.permission_profile_applicable),
                    decision.precedence_authority_class,
                    decision.outcome,
                    canonical_json_text(
                        list(dict.fromkeys(reason.code for reason in decision.reasons))
                    ),
                    canonical_json_text(
                        [reason.canonical_value() for reason in decision.reasons]
                    ),
                    canonical_json_text(
                        [
                            assessment.canonical_value()
                            for assessment in decision.authority_assessments
                        ]
                    ),
                    canonical_json_text(
                        [
                            assessment.canonical_value()
                            for assessment in decision.human_approval_assessments
                        ]
                    ),
                    canonical_json_text(
                        [
                            assessment.canonical_value()
                            for assessment in decision.evidence_assessments
                        ]
                    ),
                    canonical_json_text(
                        [
                            violation.canonical_value()
                            for violation in decision.policy_violations
                        ]
                    ),
                    decision.effective_at,
                    canonical_json_text(list(decision.evidence_ids)),
                    canonical_json_text(list(decision.governing_rule_ids)),
                    decision.decided_at,
                    decision.runtime_instance_id,
                    decision.task_contract_hash,
                    decision.provenance_json,
                    decision.canonical_json,
                    decision.content_hash,
                ),
            )
            connection.executemany(
                """
                INSERT INTO governance_decision_authority_inputs (
                    governance_decision_id, input_order,
                    claimed_authority_id, resolved_authority_record_id,
                    validation_status
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (
                        decision.governance_decision_id,
                        index,
                        assessment.claimed_authority_id,
                        (
                            assessment.claimed_authority_id
                            if assessment.resolved_record_hash is not None
                            else None
                        ),
                        assessment.result_code,
                    )
                    for index, assessment in enumerate(
                        decision.authority_assessments
                    )
                ),
            )
            connection.executemany(
                """
                INSERT INTO governance_decision_human_approvals (
                    governance_decision_id, input_order,
                    claimed_human_approval_id, resolved_human_approval_id,
                    validation_status, selected, consumed
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        decision.governance_decision_id,
                        index,
                        assessment.claimed_human_approval_id,
                        (
                            assessment.claimed_human_approval_id
                            if assessment.resolved_record_hash is not None
                            else None
                        ),
                        assessment.result_code,
                        int(assessment.selected),
                        int(assessment.consumed),
                    )
                    for index, assessment in enumerate(
                        decision.human_approval_assessments
                    )
                ),
            )
            connection.executemany(
                """
                INSERT INTO governance_decision_evidence (
                    governance_decision_id, input_order,
                    required_evidence_id, resolved_evidence_id,
                    input_kind, validation_status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        decision.governance_decision_id,
                        index,
                        assessment.required_evidence_id,
                        (
                            assessment.required_evidence_id
                            if assessment.available
                            else None
                        ),
                        assessment.input_kind,
                        "available" if assessment.available else "missing",
                    )
                    for index, assessment in enumerate(
                        decision.evidence_assessments
                    )
                ),
            )
            connection.executemany(
                """
                INSERT INTO governance_decision_rules (
                    governance_decision_id, rule_order, governance_rule_id
                ) VALUES (?, ?, ?)
                """,
                (
                    (decision.governance_decision_id, index, rule_id)
                    for index, rule_id in enumerate(decision.governing_rule_ids)
                ),
            )

            for assessment in decision.human_approval_assessments:
                if not assessment.consumed:
                    continue
                cursor = connection.execute(
                    """
                    UPDATE human_approvals
                    SET consumed_at = ?, consumed_by_task_id = ?,
                        consumed_by_decision_id = ?
                    WHERE human_approval_id = ?
                      AND single_use = 1
                      AND consumed_at IS NULL
                    """,
                    (
                        decided_at,
                        task.task_id,
                        decision.governance_decision_id,
                        assessment.claimed_human_approval_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ConflictError(
                        "single-use human approval could not be consumed"
                    )

            if result.stop_event is not None:
                stop = result.stop_event
                connection.execute(
                    """
                    INSERT INTO task_stop_events (
                        stop_event_id, task_id, governance_decision_id,
                        transaction_id, stop_condition, trigger_source,
                        model_requested_stop, governance_forced_stop,
                        reason_codes_json, preserved_evidence_json, created_at,
                        canonical_json, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?, ?, ?)
                    """,
                    (
                        stop.stop_event_id,
                        stop.task_id,
                        stop.governance_decision_id,
                        stop.transaction_id,
                        stop.stop_condition,
                        stop.trigger_source,
                        canonical_json_text(list(stop.reason_codes)),
                        canonical_json_text(list(stop.preserved_evidence_ids)),
                        stop.created_at,
                        stop.canonical_json,
                        stop.content_hash,
                    ),
                )

            terminal_reason = (
                "governance_allowed"
                if result.task_status == "active"
                else "governance_stopped"
            )
            connection.execute(
                """
                INSERT INTO task_state_transitions (
                    transition_id, task_id, sequence_number, from_status,
                    to_status, reason_code, changed_at, changed_by,
                    transaction_id
                ) VALUES (?, ?, 1, 'pending', ?, ?, ?,
                          'governance_kernel', ?)
                """,
                (
                    identifiers.terminal_transition_id,
                    task.task_id,
                    result.task_status,
                    terminal_reason,
                    decided_at,
                    identifiers.transaction_id,
                ),
            )
            if result.task_status == "active":
                connection.execute(
                    """
                    UPDATE tasks SET status = 'active', started_at = ?
                    WHERE task_id = ?
                    """,
                    (decided_at, task.task_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE tasks SET status = 'stopped', completed_at = ?
                    WHERE task_id = ?
                    """,
                    (decided_at, task.task_id),
                )

            structured_failures = (
                []
                if result.task_status == "active"
                else [reason.canonical_value() for reason in decision.reasons]
            )
            transaction_status = (
                "committed" if result.task_status == "active" else "stopped"
            )
            transaction_value = _transaction_value(
                transaction_id=identifiers.transaction_id,
                task_id=task.task_id,
                runtime_instance_id=runtime_instance_id,
                execution_principal=runtime_execution_principal,
                started_at=decided_at,
                completed_at=decided_at,
                status=transaction_status,
                task_contract_hash=task.content_hash,
                decision_hash=decision.content_hash,
                stop_hash=(
                    result.stop_event.content_hash
                    if result.stop_event is not None
                    else None
                ),
                structured_failures=structured_failures,
            )
            connection.execute(
                """
                UPDATE governed_runtime_transactions
                SET completed_at = ?, status = ?,
                    structured_failure_json = ?, content_hash = ?
                WHERE transaction_id = ?
                """,
                (
                    decided_at,
                    transaction_status,
                    canonical_json_text(structured_failures),
                    sha256_canonical_json(transaction_value),
                    identifiers.transaction_id,
                ),
            )
            return result

        return self._kernel.write(operation)

    def reconstruct(self, task_id: str) -> Mapping[str, Any]:
        """Reconstruct and hash-check one decision without hidden reasoning."""

        validate_identifier(task_id, field="task_id")

        def operation(connection: sqlite3.Connection) -> Mapping[str, Any]:
            task = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise NotFoundError(f"task not found: {task_id}")
            transaction = connection.execute(
                """
                SELECT * FROM governed_runtime_transactions
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            decision = connection.execute(
                """
                SELECT * FROM governance_decisions
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            session = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (task["session_id"],),
            ).fetchone()
            if transaction is None or decision is None or session is None:
                raise IntegrityInspectionError(
                    "task reconstruction is missing a required parent"
                )

            canonical_task = parse_json(task["canonical_contract_json"])
            canonical_decision = parse_json(decision["canonical_json"])
            canonical_session = parse_json(session["canonical_json"])
            for label, canonical_value, expected_hash in (
                ("task", canonical_task, task["contract_hash"]),
                (
                    "decision",
                    canonical_decision,
                    decision["content_hash"],
                ),
                (
                    "session",
                    canonical_session,
                    session["content_hash"],
                ),
            ):
                actual_hash = sha256_canonical_json(canonical_value)
                if not hashes_match(expected_hash, actual_hash):
                    raise IntegrityInspectionError(
                        f"{label} hash mismatch blocks reconstruction"
                    )

            profile = connection.execute(
                """
                SELECT canonical_json, content_hash
                FROM permission_profiles
                WHERE permission_profile_id = ?
                """,
                (decision["permission_profile_id"],),
            ).fetchone()
            if profile is None or not hashes_match(
                profile["content_hash"],
                sha256_canonical_json(parse_json(profile["canonical_json"])),
            ):
                raise IntegrityInspectionError(
                    "permission profile integrity blocks reconstruction"
                )

            operation_row = connection.execute(
                "SELECT * FROM operation_definitions WHERE operation_name = ?",
                (decision["requested_operation"],),
            ).fetchone()
            operation_definition: OperationDefinition | None = None
            if operation_row is None:
                if (
                    decision["decision"] != "stop"
                    or decision["operation_definition_hash"] != _ZERO_HASH
                ):
                    raise IntegrityInspectionError(
                        "operation definition is missing during reconstruction"
                    )
            else:
                operation_definition = _operation_definition_from_row(operation_row)
                if (
                    operation_row["canonical_json"]
                    != operation_definition.canonical_json
                    or not hashes_match(
                        operation_row["content_hash"],
                        operation_definition.content_hash,
                    )
                    or not hashes_match(
                        decision["operation_definition_hash"],
                        operation_definition.content_hash,
                    )
                ):
                    raise IntegrityInspectionError(
                        "operation definition integrity blocks reconstruction"
                    )

            authority_inputs: list[dict[str, Any]] = []
            authority_assessment_values: list[dict[str, Any]] = []
            for row in connection.execute(
                """
                SELECT input.*, authority.canonical_json,
                       authority.content_hash,
                       revocation.canonical_json AS revocation_canonical_json,
                       revocation.content_hash AS revocation_content_hash,
                       revocation.revoked_at AS revocation_revoked_at
                FROM governance_decision_authority_inputs AS input
                LEFT JOIN authority_records AS authority
                  ON authority.authority_record_id =
                     input.resolved_authority_record_id
                LEFT JOIN authority_revocations AS revocation
                  ON revocation.authority_record_id =
                     input.resolved_authority_record_id
                 AND revocation.revoked_at <= ?
                WHERE input.governance_decision_id = ?
                ORDER BY input.input_order
                """,
                (decision["decided_at"], decision["governance_decision_id"]),
            ):
                authority_value = (
                    None
                    if row["canonical_json"] is None
                    else parse_json(row["canonical_json"])
                )
                if authority_value is not None and not hashes_match(
                    row["content_hash"],
                    sha256_canonical_json(authority_value),
                ):
                    raise IntegrityInspectionError(
                        "authority integrity blocks reconstruction"
                    )
                revocation_value = (
                    None if row["revocation_canonical_json"] is None
                    else parse_json(row["revocation_canonical_json"])
                )
                if revocation_value is not None and not hashes_match(
                    row["revocation_content_hash"],
                    sha256_canonical_json(revocation_value),
                ):
                    raise IntegrityInspectionError(
                        "authority revocation integrity blocks reconstruction"
                    )
                authority_inputs.append(
                    {
                        "authority_record": authority_value,
                        "authority_revocation": revocation_value,
                        "claimed_authority_id": row["claimed_authority_id"],
                        "validation_status": row["validation_status"],
                    }
                )
                authority_assessment_values.append(
                    {
                        "applicable": row["validation_status"] == "applicable",
                        "authority_class": (
                            None if authority_value is None
                            else authority_value["authority_class"]
                        ),
                        "claimed_authority_id": row["claimed_authority_id"],
                        "resolved_record_hash": row["content_hash"],
                        "result_code": row["validation_status"],
                    }
                )
            if authority_assessment_values != canonical_decision.get(
                "authority_assessments"
            ):
                raise IntegrityInspectionError(
                    "authority assessment relationships block reconstruction"
                )

            human_approval_inputs: list[dict[str, Any]] = []
            human_approval_assessment_values: list[dict[str, Any]] = []
            for row in connection.execute(
                """
                SELECT input.*, approval.canonical_json, approval.content_hash,
                       approval.single_use, approval.consumed_at,
                       approval.consumed_by_task_id,
                       approval.consumed_by_decision_id
                FROM governance_decision_human_approvals AS input
                LEFT JOIN human_approvals AS approval
                  ON approval.human_approval_id =
                     input.resolved_human_approval_id
                WHERE input.governance_decision_id = ?
                ORDER BY input.input_order
                """,
                (decision["governance_decision_id"],),
            ):
                approval_value = (
                    None if row["canonical_json"] is None
                    else parse_json(row["canonical_json"])
                )
                if approval_value is not None and not hashes_match(
                    row["content_hash"],
                    sha256_canonical_json(approval_value),
                ):
                    raise IntegrityInspectionError(
                        "human approval integrity blocks reconstruction"
                    )
                if row["consumed"] and (
                    not row["selected"]
                    or not row["single_use"]
                    or row["consumed_at"] is None
                    or row["consumed_by_task_id"] != task_id
                    or row["consumed_by_decision_id"]
                    != decision["governance_decision_id"]
                ):
                    raise IntegrityInspectionError(
                        "human approval consumption blocks reconstruction"
                    )
                human_approval_inputs.append(
                    {
                        "human_approval": approval_value,
                        "claimed_human_approval_id":
                            row["claimed_human_approval_id"],
                        "validation_status": row["validation_status"],
                        "selected": bool(row["selected"]),
                        "consumed": bool(row["consumed"]),
                        "consumed_at": row["consumed_at"],
                        "consumed_by_task_id": row["consumed_by_task_id"],
                        "consumed_by_decision_id":
                            row["consumed_by_decision_id"],
                    }
                )
                human_approval_assessment_values.append(
                    {
                        "applicable": row["validation_status"] == "applicable",
                        "claimed_human_approval_id":
                            row["claimed_human_approval_id"],
                        "consumed": bool(row["consumed"]),
                        "resolved_record_hash": row["content_hash"],
                        "selected": bool(row["selected"]),
                        "result_code": row["validation_status"],
                    }
                )
            if human_approval_assessment_values != canonical_decision.get(
                "human_approval_assessments"
            ):
                raise IntegrityInspectionError(
                    "human approval relationships block reconstruction"
                )

            evidence_inputs: list[dict[str, Any]] = []
            evidence_assessment_values: list[dict[str, Any]] = []
            for row in connection.execute(
                """
                SELECT input.*, evidence.evidence_kind,
                       evidence.content_hash, evidence.integrity_status,
                       evidence.storage_kind, evidence.byte_length,
                       inline.content AS inline_content,
                       inline.encoding AS inline_encoding
                FROM governance_decision_evidence AS input
                LEFT JOIN evidence_items AS evidence
                  ON evidence.evidence_id = input.resolved_evidence_id
                LEFT JOIN evidence_inline_text AS inline
                  ON inline.evidence_id = input.resolved_evidence_id
                WHERE input.governance_decision_id = ?
                ORDER BY input.input_order
                """,
                (decision["governance_decision_id"],),
            ):
                if row["resolved_evidence_id"] is not None:
                    exact = (
                        row["inline_content"].encode("utf-8")
                        if row["inline_content"] is not None
                        else None
                    )
                    if (
                        row["integrity_status"] != "valid"
                        or row["storage_kind"] != "inline_text"
                        or row["inline_encoding"] != "utf-8"
                        or exact is None
                        or not hashes_match(
                            row["content_hash"],
                            sha256_bytes(exact),
                        )
                        or row["byte_length"] != len(exact)
                    ):
                        raise IntegrityInspectionError(
                            "decision evidence integrity blocks reconstruction"
                        )
                evidence_inputs.append(
                    {
                        "content_hash": row["content_hash"],
                        "evidence_id": row["required_evidence_id"],
                        "evidence_kind": row["evidence_kind"],
                        "input_kind": row["input_kind"],
                        "integrity_status": row["integrity_status"],
                        "validation_status": row["validation_status"],
                    }
                )
                evidence_assessment_values.append(
                    {
                        "available": row["validation_status"] == "available",
                        "input_kind": row["input_kind"],
                        "required_evidence_id": row["required_evidence_id"],
                    }
                )
            if evidence_assessment_values != canonical_decision.get(
                "evidence_assessments"
            ):
                raise IntegrityInspectionError(
                    "decision evidence relationships block reconstruction"
                )
            transitions = [
                {
                    "changed_at": row["changed_at"],
                    "changed_by": row["changed_by"],
                    "from_status": row["from_status"],
                    "reason_code": row["reason_code"],
                    "sequence_number": row["sequence_number"],
                    "to_status": row["to_status"],
                    "transition_id": row["transition_id"],
                }
                for row in connection.execute(
                    """
                    SELECT *
                    FROM task_state_transitions
                    WHERE task_id = ?
                    ORDER BY sequence_number
                    """,
                    (task_id,),
                )
            ]
            rules: list[dict[str, Any]] = []
            for row in connection.execute(
                """
                SELECT relationship.rule_order, rule.*
                FROM governance_decision_rules AS relationship
                JOIN governance_rules AS rule
                  ON rule.governance_rule_id =
                     relationship.governance_rule_id
                WHERE relationship.governance_decision_id = ?
                ORDER BY relationship.rule_order
                """,
                (decision["governance_decision_id"],),
            ):
                rule_value = {
                    "configuration": parse_json(row["configuration_json"]),
                    "description": row["description"],
                    "governance_rule_id": row["governance_rule_id"],
                    "kind": row["rule_kind"],
                    "name": row["rule_name"],
                    "version": row["rule_version"],
                }
                if not hashes_match(
                    row["content_hash"],
                    sha256_canonical_json(rule_value),
                ):
                    raise IntegrityInspectionError(
                        "governance rule integrity blocks reconstruction"
                    )
                rules.append(
                    {
                        "content_hash": row["content_hash"],
                        "governance_rule_id": row["governance_rule_id"],
                        "name": row["rule_name"],
                        "version": row["rule_version"],
                    }
                )
            if [rule["governance_rule_id"] for rule in rules] != (
                canonical_decision.get("governing_rule_ids")
            ):
                raise IntegrityInspectionError(
                    "governance rule relationships block reconstruction"
                )
            stop = connection.execute(
                "SELECT * FROM task_stop_events WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            canonical_stop: dict[str, Any] | None = None
            if stop is not None:
                canonical_stop = parse_json(stop["canonical_json"])
                if not hashes_match(
                    stop["content_hash"],
                    sha256_canonical_json(canonical_stop),
                ):
                    raise IntegrityInspectionError(
                        "task-stop hash mismatch blocks reconstruction"
                    )

            structured_failures = parse_json(
                transaction["structured_failure_json"]
            )
            transaction_value = _transaction_value(
                transaction_id=transaction["transaction_id"],
                task_id=transaction["task_id"],
                runtime_instance_id=transaction["runtime_instance_id"],
                execution_principal=transaction["execution_principal"],
                started_at=transaction["started_at"],
                completed_at=transaction["completed_at"],
                status=transaction["status"],
                task_contract_hash=task["contract_hash"],
                decision_hash=decision["content_hash"],
                stop_hash=(stop["content_hash"] if stop is not None else None),
                structured_failures=structured_failures,
            )
            if not hashes_match(
                transaction["content_hash"],
                sha256_canonical_json(transaction_value),
            ):
                raise IntegrityInspectionError(
                    "runtime transaction hash mismatch blocks reconstruction"
                )

            reconstruction = {
                "authority_inputs": authority_inputs,
                "decision": canonical_decision,
                "evidence_inputs": evidence_inputs,
                "human_approval_inputs": human_approval_inputs,
                "operation_definition": (
                    None if operation_definition is None
                    else operation_definition.canonical_value()
                ),
                "permission_profile": parse_json(profile["canonical_json"]),
                "rules": rules,
                "session": canonical_session,
                "stop_event": canonical_stop,
                "task": canonical_task,
                "task_status": task["status"],
                "transaction": transaction_value,
                "transitions": transitions,
            }
            return {
                "canonical_json": canonical_json_text(reconstruction),
                "content_hash": sha256_canonical_json(reconstruction),
                "integrity_verified": True,
                "value": reconstruction,
            }

        return self._kernel.read(operation)

    def counts(self, table_names: Iterable[str]) -> Mapping[str, int]:
        """Internal read helper used only by deterministic validation tests."""

        accepted = {
            "authority_records",
            "evidence_items",
            "governance_decisions",
            "governed_runtime_transactions",
            "task_state_transitions",
            "task_stop_events",
            "tasks",
        }
        names = tuple(table_names)
        if any(name not in accepted for name in names):
            raise ValidationError("unsupported task-runtime count target")
        return self._kernel.read(
            lambda connection: {
                name: connection.execute(
                    f"SELECT COUNT(*) FROM {name}"
                ).fetchone()[0]
                for name in names
            }
        )
