"""Atomic governed creation and exact audit reconstruction for B87-I3-B."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import parse_json
from batch87_apprentice.common.errors import NotFoundError, ValidationError
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.persistence.contracts import (
    EvidenceItem,
    EvidenceLink,
    RecordEnvelope,
)
from batch87_apprentice.persistence.repositories import (
    _insert_evidence,
    _insert_record,
    _insert_values,
)
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .construct_contracts import (
    CONSTRUCT_PAYLOAD_TABLES,
    ArchitectureDecisionPayload,
    ConstructDoctrinePayload,
    ConstructEntityPayload,
    ConstructPayload,
    PreferenceRecordPayload,
    ProjectStatePayload,
    TerminologyDefinitionPayload,
    construct_memory_content_hash,
    payload_from_database,
    validate_construct_pair,
)
from .kernel import _insert_initial_memory_state

_PROHIBITED_MEMORY_EVIDENCE_KINDS = frozenset(
    {"controlled_prompt", "controlled_output"}
)


def _record_envelope(row: Mapping[str, Any]) -> RecordEnvelope:
    return RecordEnvelope(
        **{
            field: row[field]
            for field in RecordEnvelope.__dataclass_fields__
        }
    )


class ConstructMemoryRepository:
    """Persist only the seven accepted Construct payloads through one transaction."""

    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel

    @staticmethod
    def _validate_evidence_inputs(
        envelope: RecordEnvelope,
        payload: ConstructPayload,
        evidence_items: Sequence[EvidenceItem],
        evidence_links: Sequence[EvidenceLink],
    ) -> None:
        if not evidence_links:
            raise ValidationError("Construct memory requires explicit linked evidence")
        new_ids: set[str] = set()
        for item in evidence_items:
            if not isinstance(item, EvidenceItem):
                raise TypeError("evidence_items must contain EvidenceItem values")
            if item.evidence_id in new_ids:
                raise ValidationError("new evidence identifiers must be unique")
            if item.evidence_kind in _PROHIBITED_MEMORY_EVIDENCE_KINDS:
                raise ValidationError(
                    "raw Controlled Governance Resilience evidence is not memory evidence"
                )
            new_ids.add(item.evidence_id)
        linked_ids: set[str] = set()
        linked_keys: set[tuple[str, str]] = set()
        for link in evidence_links:
            if not isinstance(link, EvidenceLink):
                raise TypeError("evidence_links must contain EvidenceLink values")
            if link.record_id != envelope.record_id:
                raise ValidationError("evidence link targets the wrong record")
            key = (link.evidence_id, link.relationship)
            if key in linked_keys:
                raise ValidationError("duplicate evidence link")
            linked_keys.add(key)
            linked_ids.add(link.evidence_id)
        if not new_ids.issubset(linked_ids):
            raise ValidationError("every supplied evidence item must be explicitly linked")
        if isinstance(payload, PreferenceRecordPayload) and not linked_ids:
            raise ValidationError("preference records require non-inferred evidence")

    @staticmethod
    def _validate_references(
        connection: sqlite3.Connection,
        payload: ConstructPayload,
    ) -> None:
        if isinstance(payload, ProjectStatePayload):
            row = connection.execute(
                "SELECT entity_kind FROM entities WHERE entity_id = ?",
                (payload.project_id,),
            ).fetchone()
            if row is None or row["entity_kind"] != "project":
                raise ValidationError("project_id must resolve to a project entity")
        if isinstance(payload, ArchitectureDecisionPayload):
            row = connection.execute(
                "SELECT 1 FROM scopes WHERE scope_id = ?",
                (payload.decision_scope,),
            ).fetchone()
            if row is None:
                raise ValidationError("decision_scope must resolve to an existing scope")
        if isinstance(payload, ConstructDoctrinePayload):
            for scope_id in parse_json(payload.application_scopes_json):
                row = connection.execute(
                    "SELECT 1 FROM scopes WHERE scope_id = ?",
                    (scope_id,),
                ).fetchone()
                if row is None:
                    raise ValidationError(
                        f"application scope does not exist: {scope_id}"
                    )
        if isinstance(payload, TerminologyDefinitionPayload):
            row = connection.execute(
                "SELECT 1 FROM scopes WHERE scope_id = ?",
                (payload.definition_scope_id,),
            ).fetchone()
            if row is None:
                raise ValidationError(
                    "definition_scope_id must resolve to an existing scope"
                )

    @staticmethod
    def _validate_persisted_evidence(
        connection: sqlite3.Connection,
        payload: ConstructPayload,
        evidence_links: Sequence[EvidenceLink],
    ) -> None:
        kinds: list[str] = []
        for link in evidence_links:
            row = connection.execute(
                """
                SELECT evidence_kind, integrity_status
                FROM evidence_items WHERE evidence_id = ?
                """,
                (link.evidence_id,),
            ).fetchone()
            if row is None:
                raise ValidationError(f"linked evidence is missing: {link.evidence_id}")
            if row["integrity_status"] != "valid":
                raise ValidationError("linked evidence must have verified integrity")
            if row["evidence_kind"] in _PROHIBITED_MEMORY_EVIDENCE_KINDS:
                raise ValidationError(
                    "raw Controlled Governance Resilience evidence cannot enter memory"
                )
            kinds.append(row["evidence_kind"])
        if isinstance(payload, PreferenceRecordPayload) and set(kinds) <= {
            "model_output"
        }:
            raise ValidationError(
                "a durable preference cannot be created from model inference alone"
            )

    def create(
        self,
        envelope: RecordEnvelope,
        payload: ConstructPayload,
        *,
        lifecycle_transition_id: str,
        approval_transition_id: str,
        evidence_links: Sequence[EvidenceLink],
        changed_by_principal: str,
        evidence_items: Sequence[EvidenceItem] = (),
        changed_by_entity_id: str | None = None,
        reason_code: str = "construct_memory_created",
    ) -> str:
        """Atomically persist evidence, envelope, payload, links, and both histories."""

        validate_construct_pair(envelope, payload)
        if changed_by_principal not in {"operator", "codex_development_harness"}:
            raise ValidationError("unsupported Construct creation principal")
        if changed_by_principal == "operator":
            if changed_by_entity_id is None:
                raise ValidationError("operator creation requires changed_by_entity_id")
            if envelope.created_by_entity_id != changed_by_entity_id:
                raise ValidationError(
                    "operator creation entity must match envelope.created_by_entity_id"
                )
        elif changed_by_entity_id is not None:
            raise ValidationError(
                "Codex development-harness creation cannot claim a human entity"
            )
        self._validate_evidence_inputs(
            envelope,
            payload,
            evidence_items,
            evidence_links,
        )
        digest = construct_memory_content_hash(envelope, payload)

        def operation(connection: sqlite3.Connection) -> None:
            for item in evidence_items:
                _insert_evidence(connection, item)
            self._validate_references(connection, payload)
            self._validate_persisted_evidence(connection, payload, evidence_links)
            _insert_record(connection, envelope, content_hash=digest)
            _insert_values(connection, payload.TABLE, payload.database_values())
            connection.executemany(
                """
                INSERT INTO record_evidence_links (
                    record_id, evidence_id, relationship, explanation
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    (
                        link.record_id,
                        link.evidence_id,
                        link.relationship,
                        link.explanation,
                    )
                    for link in evidence_links
                ),
            )
            _insert_initial_memory_state(
                connection,
                envelope.record_id,
                lifecycle_transition_id=lifecycle_transition_id,
                approval_transition_id=approval_transition_id,
                changed_at=envelope.created_at,
                changed_by_principal=changed_by_principal,
                reason_code=reason_code,
                changed_by_entity_id=changed_by_entity_id,
            )

        self._kernel.write(operation)
        return digest

    def get(self, record_id: str) -> Mapping[str, Any]:
        """Return the exact envelope and typed canonical payload."""

        result = self.reconstruct(record_id)
        return {
            "record": result["record"],
            "payload_type": result["payload_type"],
            "payload": result["payload"],
        }

    def reconstruct(self, record_id: str) -> Mapping[str, Any]:
        """Return deterministic exact-record audit reconstruction, never search."""

        validate_identifier(record_id, field="record_id")

        def operation(connection: sqlite3.Connection) -> dict[str, Any]:
            row = connection.execute(
                "SELECT * FROM records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"record not found: {record_id}")
            record = dict(row)
            table = CONSTRUCT_PAYLOAD_TABLES.get(record["record_type"])
            if record["record_family"] != "construct_memory" or table is None:
                raise ValidationError("record is not an implemented I3-B Construct type")
            payload_row = connection.execute(
                f"SELECT * FROM {table} WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if payload_row is None:
                raise ValidationError("Construct record is missing its typed payload")
            payload = payload_from_database(record["record_type"], dict(payload_row))
            envelope = _record_envelope(record)
            recomputed_hash = construct_memory_content_hash(envelope, payload)

            evidence = [
                dict(evidence_row)
                for evidence_row in connection.execute(
                    """
                    SELECT link.relationship, link.explanation,
                           item.evidence_id, item.evidence_kind, item.storage_kind,
                           item.storage_location, item.original_name, item.media_type,
                           item.byte_length, item.content_hash, item.captured_at,
                           item.captured_by_entity, item.integrity_status,
                           item.redaction_status, item.sensitivity_class,
                           item.privacy_class
                    FROM record_evidence_links AS link
                    JOIN evidence_items AS item
                      ON item.evidence_id = link.evidence_id
                    WHERE link.record_id = ?
                    ORDER BY item.evidence_id, link.relationship
                    """,
                    (record_id,),
                )
            ]
            lifecycle = [
                dict(history)
                for history in connection.execute(
                    """
                    SELECT * FROM memory_record_lifecycle_transitions
                    WHERE record_id = ? ORDER BY sequence_number, transition_id
                    """,
                    (record_id,),
                )
            ]
            approvals = [
                dict(history)
                for history in connection.execute(
                    """
                    SELECT * FROM memory_record_approval_transitions
                    WHERE record_id = ? ORDER BY sequence_number, transition_id
                    """,
                    (record_id,),
                )
            ]
            grants = [
                dict(grant)
                for grant in connection.execute(
                    """
                    SELECT * FROM memory_approval_grants
                    WHERE record_id = ? ORDER BY approved_at, grant_id
                    """,
                    (record_id,),
                )
            ]
            relationships = [
                dict(relationship)
                for relationship in connection.execute(
                    """
                    SELECT * FROM record_relationships
                    WHERE source_record_id = ? OR target_record_id = ?
                    ORDER BY created_at, relationship_id
                    """,
                    (record_id, record_id),
                )
            ]
            construct_relationships = []
            if isinstance(payload, ConstructEntityPayload):
                construct_relationships = [
                    dict(relationship)
                    for relationship in connection.execute(
                        """
                        SELECT relationship.*,
                               record.lifecycle_state,
                               record.approval_status,
                               record.content_hash,
                               record.integrity_status
                        FROM construct_relationships AS relationship
                        JOIN records AS record
                          ON record.record_id = relationship.record_id
                        WHERE relationship.subject_entity_id = ?
                           OR relationship.object_entity_id = ?
                        ORDER BY relationship.relationship_type,
                                 relationship.record_id
                        """,
                        (payload.entity_id, payload.entity_id),
                    )
                ]
            assessments = []
            for assessment in connection.execute(
                """
                SELECT * FROM memory_eligibility_assessments
                WHERE record_id = ? ORDER BY evaluated_at, assessment_id
                """,
                (record_id,),
            ):
                value = dict(assessment)
                value["reason_codes"] = parse_json(value["reason_codes_json"])
                value["record_snapshot"] = parse_json(value["record_snapshot_json"])
                value["context"] = parse_json(value["context_json"])
                assessments.append(value)
            from .construct_integrity import ConstructIntegrityInspector

            inspection = ConstructIntegrityInspector._inspect_connection(connection)
            integrity_findings = [
                {
                    "source": "construct_integrity",
                    "code": finding.code,
                    "severity": finding.severity,
                    "record_id": finding.record_id,
                    "detail": finding.detail,
                }
                for finding in inspection.findings
                if finding.record_id in {None, record_id}
            ]
            return {
                "memory_domain": "construct_relational",
                "record": record,
                "payload_type": record["record_type"],
                "payload": payload.canonical_content(),
                "evidence": evidence,
                "lifecycle_transitions": lifecycle,
                "approval_transitions": approvals,
                "approval_grants": grants,
                "relationships": relationships,
                "construct_relationships": construct_relationships,
                "eligibility_assessments": assessments,
                "content_hash": record["content_hash"],
                "recomputed_content_hash": recomputed_hash,
                "integrity": {
                    "stored_status": record["integrity_status"],
                    "hash_matches": recomputed_hash == record["content_hash"],
                    "valid": (
                        recomputed_hash == record["content_hash"]
                        and record["integrity_status"] == "valid"
                        and not any(
                            finding["severity"] == "error"
                            for finding in integrity_findings
                        )
                    ),
                    "findings": integrity_findings,
                },
            }

        result = self._kernel.read(operation)

        from .integrity import MemoryIntegrityInspector

        shared_report = MemoryIntegrityInspector(self._kernel.config).inspect()
        shared_findings = [
            {
                "source": "shared_memory_integrity",
                "code": finding.code,
                "severity": finding.severity,
                "record_id": finding.record_id,
                "detail": finding.detail,
            }
            for finding in shared_report.findings
            if finding.record_id in {None, record_id}
        ]
        findings = [*result["integrity"]["findings"], *shared_findings]
        result["integrity"] = {
            **result["integrity"],
            "valid": (
                result["integrity"]["hash_matches"]
                and result["integrity"]["stored_status"] == "valid"
                and not any(finding["severity"] == "error" for finding in findings)
            ),
            "findings": findings,
        }
        return result
