"""Governed shared memory state and eligibility persistence for B87-I3-A."""

from __future__ import annotations

from collections.abc import Mapping
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import canonical_json_text, parse_json
from batch87_apprentice.common.errors import NotFoundError, ValidationError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .contracts import (
    GOVERNED_RELATIONSHIP_TYPES,
    NOLAN_INCLUSIVE_AUTHORITY_CLASSES,
    EligibilityContext,
    EligibilityDecision,
    MemoryApprovalGrant,
    MemoryRelationshipGrant,
    RecordRelationship,
    approval_authority_classes_for,
    memory_domain_for,
    validate_approval_transition,
    validate_lifecycle_transition,
)
from .eligibility import eligibility_record_snapshot, evaluate_memory_eligibility


class MemoryKernel:
    """Own append-only memory state, relationships, and eligibility audit writes."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._kernel = PersistenceKernel(config)

    @staticmethod
    def _record(
        connection: sqlite3.Connection,
        record_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"record not found: {record_id}")
        value = dict(row)
        if memory_domain_for(value["record_family"], value["record_type"]) is None:
            raise ValidationError("record is not registered as an I3 memory record type")
        return value

    @staticmethod
    def _next_sequence(
        connection: sqlite3.Connection,
        table: str,
        record_id: str,
    ) -> int:
        row = connection.execute(
            f"SELECT MAX(sequence_number) AS value FROM {table} WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        return 0 if row["value"] is None else int(row["value"]) + 1

    @staticmethod
    def _audit_values(material: Mapping[str, Any]) -> tuple[str, str]:
        canonical = canonical_json_text(dict(material))
        return canonical, sha256_canonical_json(dict(material))

    def register_initial_state(
        self,
        record_id: str,
        *,
        lifecycle_transition_id: str,
        approval_transition_id: str,
        changed_at: str,
        changed_by_principal: str,
        reason_code: str,
        changed_by_entity_id: str | None = None,
    ) -> None:
        """Record the immutable initial lifecycle and approval state for a memory."""

        validate_identifier(record_id, field="record_id")
        validate_identifier(
            lifecycle_transition_id,
            field="lifecycle_transition_id",
        )
        validate_identifier(
            approval_transition_id,
            field="approval_transition_id",
        )
        parse_canonical_utc(changed_at, field="changed_at")
        if changed_by_entity_id is not None:
            validate_identifier(changed_by_entity_id, field="changed_by_entity_id")
        if changed_by_principal not in {
            "operator",
            "codex_development_harness",
        }:
            raise ValidationError(
                "initial memory state must be registered by governed infrastructure"
            )
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise ValidationError("reason_code must be non-empty")

        def operation(connection: sqlite3.Connection) -> None:
            record = self._record(connection, record_id)
            if record["lifecycle_state"] not in {"observed", "candidate", "reviewed"}:
                raise ValidationError("new memory cannot begin in a terminal or active state")
            if record["approval_status"] not in {"pending", "not_required"}:
                raise ValidationError("new memory must begin pending or not_required")
            existing = connection.execute(
                """
                SELECT 1 FROM memory_record_lifecycle_transitions
                WHERE record_id = ?
                UNION ALL
                SELECT 1 FROM memory_record_approval_transitions
                WHERE record_id = ?
                LIMIT 1
                """,
                (record_id, record_id),
            ).fetchone()
            if existing is not None:
                raise ValidationError("initial memory state is already registered")

            lifecycle_material = {
                "transition_id": lifecycle_transition_id,
                "record_id": record_id,
                "sequence_number": 0,
                "from_state": None,
                "to_state": record["lifecycle_state"],
                "reason_code": reason_code,
                "changed_at": changed_at,
                "changed_by_principal": changed_by_principal,
                "changed_by_entity_id": changed_by_entity_id,
            }
            canonical, digest = self._audit_values(lifecycle_material)
            connection.execute(
                """
                INSERT INTO memory_record_lifecycle_transitions (
                    transition_id, record_id, sequence_number, from_state, to_state,
                    reason_code, changed_at, changed_by_principal,
                    changed_by_entity_id, canonical_json, content_hash
                ) VALUES (?, ?, 0, NULL, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lifecycle_transition_id,
                    record_id,
                    record["lifecycle_state"],
                    reason_code,
                    changed_at,
                    changed_by_principal,
                    changed_by_entity_id,
                    canonical,
                    digest,
                ),
            )

            approval_material = {
                "transition_id": approval_transition_id,
                "record_id": record_id,
                "sequence_number": 0,
                "from_status": None,
                "to_status": record["approval_status"],
                "reason_code": reason_code,
                "changed_at": changed_at,
                "changed_by_principal": changed_by_principal,
                "changed_by_entity_id": changed_by_entity_id,
                "approval_grant_id": None,
                "authority_record_id": None,
                "approval_evidence_id": None,
            }
            canonical, digest = self._audit_values(approval_material)
            connection.execute(
                """
                INSERT INTO memory_record_approval_transitions (
                    transition_id, record_id, sequence_number, from_status, to_status,
                    reason_code, changed_at, changed_by_principal,
                    changed_by_entity_id, approval_grant_id,
                    authority_record_id, approval_evidence_id,
                    canonical_json, content_hash
                ) VALUES (?, ?, 0, NULL, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
                """,
                (
                    approval_transition_id,
                    record_id,
                    record["approval_status"],
                    reason_code,
                    changed_at,
                    changed_by_principal,
                    changed_by_entity_id,
                    canonical,
                    digest,
                ),
            )

        self._kernel.write(operation)

    def transition_lifecycle(
        self,
        record_id: str,
        *,
        transition_id: str,
        to_state: str,
        reason_code: str,
        changed_at: str,
        changed_by_principal: str,
        changed_by_entity_id: str | None = None,
    ) -> None:
        """Apply one governed lifecycle transition and update current state atomically."""

        validate_identifier(record_id, field="record_id")
        validate_identifier(transition_id, field="transition_id")
        parse_canonical_utc(changed_at, field="changed_at")
        if changed_by_entity_id is not None:
            validate_identifier(changed_by_entity_id, field="changed_by_entity_id")
        if changed_by_principal not in {
            "apprentice",
            "operator",
            "codex_development_harness",
        }:
            raise ValidationError("unsupported transition principal")
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise ValidationError("reason_code must be non-empty")

        def operation(connection: sqlite3.Connection) -> None:
            record = self._record(connection, record_id)
            from_state = record["lifecycle_state"]
            validate_lifecycle_transition(from_state, to_state)
            if changed_by_principal == "apprentice":
                if to_state != "candidate" or record["agent_write_policy"] != "candidate_only":
                    raise ValidationError(
                        "Apprentice lifecycle writes are limited to candidate-only records"
                    )
            if to_state == "active":
                if record["approval_status"] not in {"approved", "not_required"}:
                    raise ValidationError("active memory requires eligible approval status")
                if record["integrity_status"] not in {"valid", "not_applicable"}:
                    raise ValidationError("active memory requires valid integrity")
                evidence_count = connection.execute(
                    """
                    SELECT COUNT(*) AS value
                    FROM record_evidence_links
                    WHERE record_id = ?
                    """,
                    (record_id,),
                ).fetchone()["value"]
                if int(evidence_count) < 1:
                    raise ValidationError("active memory requires linked evidence")

            sequence = self._next_sequence(
                connection,
                "memory_record_lifecycle_transitions",
                record_id,
            )
            material = {
                "transition_id": transition_id,
                "record_id": record_id,
                "sequence_number": sequence,
                "from_state": from_state,
                "to_state": to_state,
                "reason_code": reason_code,
                "changed_at": changed_at,
                "changed_by_principal": changed_by_principal,
                "changed_by_entity_id": changed_by_entity_id,
            }
            canonical, digest = self._audit_values(material)
            connection.execute(
                """
                INSERT INTO memory_record_lifecycle_transitions (
                    transition_id, record_id, sequence_number, from_state, to_state,
                    reason_code, changed_at, changed_by_principal,
                    changed_by_entity_id, canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition_id,
                    record_id,
                    sequence,
                    from_state,
                    to_state,
                    reason_code,
                    changed_at,
                    changed_by_principal,
                    changed_by_entity_id,
                    canonical,
                    digest,
                ),
            )
            deleted_at = changed_at if to_state == "deleted" else record["deleted_at"]
            deletion_basis = reason_code if to_state == "deleted" else record["deletion_basis"]
            connection.execute(
                """
                UPDATE records
                SET lifecycle_state = ?, deleted_at = ?, deletion_basis = ?
                WHERE record_id = ?
                """,
                (to_state, deleted_at, deletion_basis, record_id),
            )

        self._kernel.write(operation)

    @staticmethod
    def _validate_authority_evidence(
        connection: sqlite3.Connection,
        *,
        authority_record_id: str,
        evidence_id: str,
        approved_by_entity_id: str,
        project_scope_id: str,
        effective_at: str,
        allowed_authority_classes: frozenset[str],
    ) -> sqlite3.Row:
        authority = connection.execute(
            """
            SELECT authority_class, status, effect, project_scope_id,
                   issuer_entity_id, effective_from, effective_until
            FROM authority_records
            WHERE authority_record_id = ?
            """,
            (authority_record_id,),
        ).fetchone()
        if authority is None:
            raise NotFoundError(
                f"authority record not found: {authority_record_id}"
            )
        if (
            authority["status"] != "active"
            or authority["effect"] != "allow"
            or authority["authority_class"] not in allowed_authority_classes
            or authority["project_scope_id"] != project_scope_id
            or (
                authority["issuer_entity_id"] is not None
                and authority["issuer_entity_id"] != approved_by_entity_id
            )
            or authority["effective_from"] > effective_at
            or (
                authority["effective_until"] is not None
                and authority["effective_until"] < effective_at
            )
        ):
            raise ValidationError(
                "grant authority is inactive, out of scope, or type-insufficient"
            )
        revoked = connection.execute(
            """
            SELECT 1 FROM authority_revocations
            WHERE authority_record_id = ?
            """,
            (authority_record_id,),
        ).fetchone()
        if revoked is not None:
            raise ValidationError("grant authority has been revoked")
        evidence = connection.execute(
            """
            SELECT evidence.evidence_kind, evidence.integrity_status
            FROM evidence_items AS evidence
            JOIN authority_record_evidence AS authority_evidence
              ON authority_evidence.evidence_id = evidence.evidence_id
            WHERE evidence.evidence_id = ?
              AND authority_evidence.authority_record_id = ?
            """,
            (evidence_id, authority_record_id),
        ).fetchone()
        if evidence is None:
            raise ValidationError(
                "grant evidence must be linked to the supplied authority"
            )
        if evidence["integrity_status"] != "valid":
            raise ValidationError("grant evidence must have valid integrity")
        if evidence["evidence_kind"] in {
            "model_output",
            "controlled_prompt",
            "controlled_output",
        }:
            raise ValidationError(
                "model-shaped or controlled evidence cannot create a grant"
            )
        return authority

    def register_approval_grant(self, grant: MemoryApprovalGrant) -> str:
        """Persist one exact, immutable, target-bound memory approval grant."""

        if not isinstance(grant, MemoryApprovalGrant):
            raise TypeError("grant must be a MemoryApprovalGrant")
        material = grant.canonical_value()
        canonical, digest = self._audit_values(material)

        def operation(connection: sqlite3.Connection) -> None:
            record = self._record(connection, grant.record_id)
            if record["project_scope_id"] != grant.project_scope_id:
                raise ValidationError("approval grant has the wrong project scope")
            allowed = approval_authority_classes_for(
                record["record_family"],
                record["record_type"],
            )
            if not allowed:
                raise ValidationError(
                    "this memory type does not accept an external approval grant"
                )
            if (
                record["record_family"] == "episodic_memory"
                and record["record_type"] == "lesson_candidate"
                and grant.target_status == "approved"
            ):
                raise ValidationError(
                    "lesson candidates cannot be approved in place; create an approved lesson"
                )
            authority = self._validate_authority_evidence(
                connection,
                authority_record_id=grant.authority_record_id,
                evidence_id=grant.evidence_id,
                approved_by_entity_id=grant.approved_by_entity_id,
                project_scope_id=grant.project_scope_id,
                effective_at=grant.approved_at,
                allowed_authority_classes=allowed,
            )
            connection.execute(
                """
                INSERT INTO memory_approval_grants (
                    grant_id, record_id, target_status, operation,
                    project_scope_id, authority_record_id, authority_class,
                    approved_by_entity_id, approved_at, expires_at,
                    single_use, consumed_at, consumed_by_transition_id,
                    evidence_id, canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
                """,
                (
                    grant.grant_id,
                    grant.record_id,
                    grant.target_status,
                    grant.operation,
                    grant.project_scope_id,
                    grant.authority_record_id,
                    authority["authority_class"],
                    grant.approved_by_entity_id,
                    grant.approved_at,
                    grant.expires_at,
                    int(grant.single_use),
                    grant.evidence_id,
                    canonical,
                    digest,
                ),
            )

        self._kernel.write(operation)
        return digest

    def transition_approval(
        self,
        record_id: str,
        *,
        transition_id: str,
        to_status: str,
        reason_code: str,
        changed_at: str,
        changed_by_entity_id: str,
        approval_grant_id: str,
    ) -> None:
        """Consume one exact grant while applying an approval transition."""

        validate_identifier(record_id, field="record_id")
        validate_identifier(transition_id, field="transition_id")
        validate_identifier(changed_by_entity_id, field="changed_by_entity_id")
        validate_identifier(approval_grant_id, field="approval_grant_id")
        parse_canonical_utc(changed_at, field="changed_at")
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise ValidationError("reason_code must be non-empty")

        def operation(connection: sqlite3.Connection) -> None:
            record = self._record(connection, record_id)
            from_status = record["approval_status"]
            validate_approval_transition(from_status, to_status)
            if record["lifecycle_state"] == "active" and to_status not in {
                "approved",
                "not_required",
            }:
                raise ValidationError(
                    "active memory approval cannot be withdrawn in place"
                )
            grant = connection.execute(
                """
                SELECT * FROM memory_approval_grants
                WHERE grant_id = ?
                """,
                (approval_grant_id,),
            ).fetchone()
            if grant is None:
                raise NotFoundError(
                    f"memory approval grant not found: {approval_grant_id}"
                )
            if (
                grant["record_id"] != record_id
                or grant["target_status"] != to_status
                or grant["project_scope_id"] != record["project_scope_id"]
                or grant["approved_by_entity_id"] != changed_by_entity_id
                or grant["approved_at"] > changed_at
                or (
                    grant["expires_at"] is not None
                    and grant["expires_at"] < changed_at
                )
                or (grant["single_use"] and grant["consumed_at"] is not None)
            ):
                raise ValidationError(
                    "memory approval grant does not match this exact transition"
                )
            allowed = approval_authority_classes_for(
                record["record_family"],
                record["record_type"],
            )
            authority = self._validate_authority_evidence(
                connection,
                authority_record_id=grant["authority_record_id"],
                evidence_id=grant["evidence_id"],
                approved_by_entity_id=grant["approved_by_entity_id"],
                project_scope_id=grant["project_scope_id"],
                effective_at=changed_at,
                allowed_authority_classes=allowed,
            )
            sequence = self._next_sequence(
                connection,
                "memory_record_approval_transitions",
                record_id,
            )
            material = {
                "transition_id": transition_id,
                "record_id": record_id,
                "sequence_number": sequence,
                "from_status": from_status,
                "to_status": to_status,
                "reason_code": reason_code,
                "changed_at": changed_at,
                "changed_by_principal": "operator",
                "changed_by_entity_id": changed_by_entity_id,
                "approval_grant_id": approval_grant_id,
                "authority_record_id": grant["authority_record_id"],
                "approval_evidence_id": grant["evidence_id"],
            }
            canonical, digest = self._audit_values(material)
            connection.execute(
                """
                INSERT INTO memory_record_approval_transitions (
                    transition_id, record_id, sequence_number, from_status, to_status,
                    reason_code, changed_at, changed_by_principal,
                    changed_by_entity_id, approval_grant_id,
                    authority_record_id, approval_evidence_id,
                    canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'operator', ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition_id,
                    record_id,
                    sequence,
                    from_status,
                    to_status,
                    reason_code,
                    changed_at,
                    changed_by_entity_id,
                    approval_grant_id,
                    grant["authority_record_id"],
                    grant["evidence_id"],
                    canonical,
                    digest,
                ),
            )
            if grant["single_use"]:
                cursor = connection.execute(
                    """
                    UPDATE memory_approval_grants
                    SET consumed_at = ?, consumed_by_transition_id = ?
                    WHERE grant_id = ? AND consumed_at IS NULL
                    """,
                    (changed_at, transition_id, approval_grant_id),
                )
                if cursor.rowcount != 1:
                    raise ValidationError("memory approval grant was already consumed")
            connection.execute(
                "UPDATE records SET approval_status = ? WHERE record_id = ?",
                (to_status, record_id),
            )

        self._kernel.write(operation)

    def register_relationship_grant(
        self,
        grant: MemoryRelationshipGrant,
    ) -> str:
        """Persist one exact Nolan-inclusive governed relationship grant."""

        if not isinstance(grant, MemoryRelationshipGrant):
            raise TypeError("grant must be a MemoryRelationshipGrant")
        material = grant.canonical_value()
        canonical, digest = self._audit_values(material)

        def operation(connection: sqlite3.Connection) -> None:
            source = connection.execute(
                "SELECT * FROM records WHERE record_id = ?",
                (grant.source_record_id,),
            ).fetchone()
            target = connection.execute(
                "SELECT * FROM records WHERE record_id = ?",
                (grant.target_record_id,),
            ).fetchone()
            if source is None:
                raise NotFoundError(f"record not found: {grant.source_record_id}")
            if target is None:
                raise NotFoundError(f"record not found: {grant.target_record_id}")
            if (
                memory_domain_for(source["record_family"], source["record_type"])
                is None
                and memory_domain_for(target["record_family"], target["record_type"])
                is None
            ):
                raise ValidationError(
                    "relationship grant requires at least one memory endpoint"
                )
            if (
                source["project_scope_id"] != grant.project_scope_id
                or target["project_scope_id"] != grant.project_scope_id
            ):
                raise ValidationError(
                    "governed relationship grant cannot cross project scope"
                )
            authority = self._validate_authority_evidence(
                connection,
                authority_record_id=grant.authority_record_id,
                evidence_id=grant.evidence_id,
                approved_by_entity_id=grant.approved_by_entity_id,
                project_scope_id=grant.project_scope_id,
                effective_at=grant.approved_at,
                allowed_authority_classes=NOLAN_INCLUSIVE_AUTHORITY_CLASSES,
            )
            connection.execute(
                """
                INSERT INTO memory_relationship_grants (
                    grant_id, relationship_id, relationship_type,
                    source_record_id, target_record_id, operation,
                    project_scope_id, authority_record_id, authority_class,
                    approved_by_entity_id, approved_at, expires_at,
                    single_use, consumed_at, consumed_by_relationship_id,
                    evidence_id, canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
                """,
                (
                    grant.grant_id,
                    grant.relationship_id,
                    grant.relationship_type,
                    grant.source_record_id,
                    grant.target_record_id,
                    grant.operation,
                    grant.project_scope_id,
                    grant.authority_record_id,
                    authority["authority_class"],
                    grant.approved_by_entity_id,
                    grant.approved_at,
                    grant.expires_at,
                    int(grant.single_use),
                    grant.evidence_id,
                    canonical,
                    digest,
                ),
            )

        self._kernel.write(operation)
        return digest

    def link_records(self, relationship: RecordRelationship) -> str:
        """Persist one typed relationship without converting it into authority."""

        if not isinstance(relationship, RecordRelationship):
            raise TypeError("relationship must be a RecordRelationship")
        governed = relationship.relationship_type in GOVERNED_RELATIONSHIP_TYPES
        if governed:
            if relationship.created_by_principal != "operator":
                raise ValidationError(
                    "governed record relationships require the operator principal"
                )
            if relationship.relationship_grant_id is None:
                raise ValidationError(
                    "governed record relationships require an exact relationship grant"
                )
        elif relationship.relationship_grant_id is not None:
            raise ValidationError(
                "ordinary record relationships cannot consume a governed grant"
            )

        def operation(connection: sqlite3.Connection) -> tuple[str, str]:
            source = connection.execute(
                """
                SELECT record_family, record_type, project_scope_id
                FROM records WHERE record_id = ?
                """,
                (relationship.source_record_id,),
            ).fetchone()
            target = connection.execute(
                """
                SELECT record_family, record_type, project_scope_id
                FROM records WHERE record_id = ?
                """,
                (relationship.target_record_id,),
            ).fetchone()
            if source is None:
                raise NotFoundError(
                    f"record not found: {relationship.source_record_id}"
                )
            if target is None:
                raise NotFoundError(
                    f"record not found: {relationship.target_record_id}"
                )
            source_domain = memory_domain_for(
                source["record_family"],
                source["record_type"],
            )
            target_domain = memory_domain_for(
                target["record_family"],
                target["record_type"],
            )
            if source_domain is None and target_domain is None:
                raise ValidationError(
                    "I3 relationships require at least one memory endpoint"
                )
            grant = None
            authority_record_id = None
            evidence_id = None
            if governed:
                grant = connection.execute(
                    "SELECT * FROM memory_relationship_grants WHERE grant_id = ?",
                    (relationship.relationship_grant_id,),
                ).fetchone()
                if grant is None:
                    raise NotFoundError(
                        "memory relationship grant not found: "
                        f"{relationship.relationship_grant_id}"
                    )
                if (
                    grant["relationship_id"] != relationship.relationship_id
                    or grant["relationship_type"] != relationship.relationship_type
                    or grant["source_record_id"] != relationship.source_record_id
                    or grant["target_record_id"] != relationship.target_record_id
                    or grant["approved_at"] > relationship.created_at
                    or (
                        grant["expires_at"] is not None
                        and grant["expires_at"] < relationship.created_at
                    )
                    or (grant["single_use"] and grant["consumed_at"] is not None)
                ):
                    raise ValidationError(
                        "relationship grant does not match this exact relationship"
                    )
                self._validate_authority_evidence(
                    connection,
                    authority_record_id=grant["authority_record_id"],
                    evidence_id=grant["evidence_id"],
                    approved_by_entity_id=grant["approved_by_entity_id"],
                    project_scope_id=grant["project_scope_id"],
                    effective_at=relationship.created_at,
                    allowed_authority_classes=NOLAN_INCLUSIVE_AUTHORITY_CLASSES,
                )
                authority_record_id = grant["authority_record_id"]
                evidence_id = grant["evidence_id"]
            material = {
                "relationship_id": relationship.relationship_id,
                "source_record_id": relationship.source_record_id,
                "target_record_id": relationship.target_record_id,
                "relationship_type": relationship.relationship_type,
                "created_at": relationship.created_at,
                "created_by_principal": relationship.created_by_principal,
                "relationship_grant_id": relationship.relationship_grant_id,
                "authority_record_id": authority_record_id,
                "approval_evidence_id": evidence_id,
                "explanation": relationship.explanation,
            }
            canonical, digest = self._audit_values(material)
            connection.execute(
                """
                INSERT INTO record_relationships (
                    relationship_id, source_record_id, target_record_id,
                    relationship_type, created_at, created_by_principal,
                    relationship_grant_id, authority_record_id,
                    approval_evidence_id, explanation, canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    relationship.relationship_id,
                    relationship.source_record_id,
                    relationship.target_record_id,
                    relationship.relationship_type,
                    relationship.created_at,
                    relationship.created_by_principal,
                    relationship.relationship_grant_id,
                    authority_record_id,
                    evidence_id,
                    relationship.explanation,
                    canonical,
                    digest,
                ),
            )
            if governed and grant is not None and grant["single_use"]:
                cursor = connection.execute(
                    """
                    UPDATE memory_relationship_grants
                    SET consumed_at = ?, consumed_by_relationship_id = ?
                    WHERE grant_id = ? AND consumed_at IS NULL
                    """,
                    (
                        relationship.created_at,
                        relationship.relationship_id,
                        relationship.relationship_grant_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValidationError("relationship grant was already consumed")
            return canonical, digest

        _, digest = self._kernel.write(operation)
        return digest

    def assess_eligibility(
        self,
        record_id: str,
        context: EligibilityContext,
    ) -> EligibilityDecision:
        """Evaluate and persist an auditable pre-relevance eligibility decision."""

        validate_identifier(record_id, field="record_id")
        if not isinstance(context, EligibilityContext):
            raise TypeError("context must be an EligibilityContext")

        def operation(connection: sqlite3.Connection) -> EligibilityDecision:
            row = connection.execute(
                "SELECT * FROM records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"record not found: {record_id}")
            task_row = connection.execute(
                "SELECT project_scope_id FROM tasks WHERE task_id = ?",
                (context.task_id,),
            ).fetchone()
            if task_row is None:
                raise NotFoundError(f"task not found: {context.task_id}")
            if task_row["project_scope_id"] != context.task_project_scope_id:
                raise ValidationError(
                    "eligibility context project scope does not match the task"
                )
            record_snapshot = eligibility_record_snapshot(dict(row))
            context_value = context.canonical_value()
            decision = evaluate_memory_eligibility(record_snapshot, context)
            connection.execute(
                """
                INSERT INTO memory_eligibility_assessments (
                    assessment_id, record_id, task_id, task_project_scope_id,
                    requested_domain, evaluated_at, eligible,
                    reason_codes_json, policy_version, record_snapshot_json,
                    record_snapshot_hash, context_json, context_hash, decision_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.assessment_id,
                    decision.record_id,
                    decision.task_id,
                    context.task_project_scope_id,
                    decision.requested_domain,
                    decision.evaluated_at,
                    int(decision.eligible),
                    canonical_json_text(list(decision.reason_codes)),
                    decision.policy_version,
                    canonical_json_text(record_snapshot),
                    decision.record_snapshot_hash,
                    canonical_json_text(context_value),
                    decision.context_hash,
                    decision.decision_hash,
                ),
            )
            return decision

        return self._kernel.write(operation)

    def reconstruct(self, record_id: str) -> Mapping[str, Any]:
        """Return the shared memory audit history for one record."""

        validate_identifier(record_id, field="record_id")

        def operation(connection: sqlite3.Connection) -> dict[str, Any]:
            record = connection.execute(
                "SELECT * FROM records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if record is None:
                raise NotFoundError(f"record not found: {record_id}")
            domain = memory_domain_for(record["record_family"], record["record_type"])
            if domain is None:
                raise ValidationError("record is not an I3 memory record")
            lifecycle = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM memory_record_lifecycle_transitions
                    WHERE record_id = ? ORDER BY sequence_number
                    """,
                    (record_id,),
                )
            ]
            approvals = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM memory_record_approval_transitions
                    WHERE record_id = ? ORDER BY sequence_number
                    """,
                    (record_id,),
                )
            ]
            relationships = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM record_relationships
                    WHERE source_record_id = ? OR target_record_id = ?
                    ORDER BY created_at, relationship_id
                    """,
                    (record_id, record_id),
                )
            ]
            assessments = []
            for row in connection.execute(
                """
                SELECT * FROM memory_eligibility_assessments
                WHERE record_id = ? ORDER BY evaluated_at, assessment_id
                """,
                (record_id,),
            ):
                value = dict(row)
                value["reason_codes"] = parse_json(value["reason_codes_json"])
                value["record_snapshot"] = parse_json(value["record_snapshot_json"])
                value["context"] = parse_json(value["context_json"])
                assessments.append(value)
            return {
                "memory_domain": domain,
                "record": dict(record),
                "lifecycle_transitions": lifecycle,
                "approval_transitions": approvals,
                "relationships": relationships,
                "eligibility_assessments": assessments,
            }

        return self._kernel.read(operation)
