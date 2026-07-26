"""Independent B87-I3-B Construct-memory integrity reconstruction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import parse_json
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.contracts import RecordEnvelope
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .construct_contracts import (
    CONSTRUCT_PAYLOAD_TABLES,
    CONSTRUCT_RELATIONSHIP_POLICIES,
    ArchitectureDecisionPayload,
    ConstructDoctrinePayload,
    ConstructEntityPayload,
    ConstructRelationshipPayload,
    PreferenceRecordPayload,
    ProjectStatePayload,
    TerminologyDefinitionPayload,
    construct_memory_content_hash,
    normalize_construct_term,
    payload_from_database,
)


@dataclass(frozen=True, slots=True)
class ConstructIntegrityFinding:
    code: str
    severity: str
    record_id: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class ConstructIntegrityReport:
    findings: tuple[ConstructIntegrityFinding, ...]

    @property
    def ok(self) -> bool:
        return not any(finding.severity == "error" for finding in self.findings)


def _envelope(row: Mapping[str, Any]) -> RecordEnvelope:
    return RecordEnvelope(
        **{
            field: row[field]
            for field in RecordEnvelope.__dataclass_fields__
        }
    )


class ConstructIntegrityInspector:
    """Recompute I3-B structure, policy, references, histories, and hashes."""

    def __init__(self, source: DatabaseConfig | PersistenceKernel) -> None:
        self._kernel = (
            source if isinstance(source, PersistenceKernel) else PersistenceKernel(source)
        )

    @staticmethod
    def _finding(
        findings: list[ConstructIntegrityFinding],
        record_errors: set[str],
        code: str,
        record_id: str | None,
        detail: str,
    ) -> None:
        findings.append(ConstructIntegrityFinding(code, "error", record_id, detail))
        if record_id is not None:
            record_errors.add(record_id)

    @classmethod
    def _check_registry(
        cls,
        connection: sqlite3.Connection,
        findings: list[ConstructIntegrityFinding],
        record_errors: set[str],
    ) -> None:
        stored = {
            row["relationship_type"]: {
                "relationship_type": row["relationship_type"],
                "authority_bearing": bool(row["authority_bearing"]),
                "self_reference_permitted": bool(
                    row["self_reference_permitted"]
                ),
                "bidirectional_permitted": bool(row["bidirectional_permitted"]),
                "required_approval_authority_class": (
                    row["required_approval_authority_class"]
                ),
                "status": row["status"],
            }
            for row in connection.execute(
                """
                SELECT * FROM construct_relationship_type_policies
                ORDER BY relationship_type
                """
            )
        }
        expected = {
            relationship_type: {**policy.canonical_value(), "status": "active"}
            for relationship_type, policy in CONSTRUCT_RELATIONSHIP_POLICIES.items()
        }
        if stored != expected:
            cls._finding(
                findings,
                record_errors,
                "I3B-RELATIONSHIP-POLICY-REGISTRY",
                None,
                "stored Construct relationship policies differ from the accepted registry",
            )

    @classmethod
    def _check_references(
        cls,
        connection: sqlite3.Connection,
        payload: Any,
        findings: list[ConstructIntegrityFinding],
        record_errors: set[str],
    ) -> None:
        record_id = payload.record_id

        def entity_exists(entity_id: str, *, project: bool = False) -> bool:
            row = connection.execute(
                "SELECT entity_kind FROM entities WHERE entity_id = ?",
                (entity_id,),
            ).fetchone()
            return row is not None and (not project or row["entity_kind"] == "project")

        def scope_exists(scope_id: str) -> bool:
            return (
                connection.execute(
                    "SELECT 1 FROM scopes WHERE scope_id = ?",
                    (scope_id,),
                ).fetchone()
                is not None
            )

        invalid_entity = False
        invalid_scope = False
        if isinstance(payload, ConstructEntityPayload):
            invalid_entity = not entity_exists(payload.entity_id)
        elif isinstance(payload, ConstructRelationshipPayload):
            invalid_entity = not entity_exists(
                payload.subject_entity_id
            ) or not entity_exists(payload.object_entity_id)
        elif isinstance(payload, ProjectStatePayload):
            invalid_entity = not entity_exists(payload.project_id, project=True)
        elif isinstance(payload, PreferenceRecordPayload):
            invalid_entity = not entity_exists(payload.preference_subject_id)
        elif isinstance(payload, ArchitectureDecisionPayload):
            invalid_scope = not scope_exists(payload.decision_scope)
        elif isinstance(payload, ConstructDoctrinePayload):
            invalid_scope = any(
                not scope_exists(scope_id)
                for scope_id in parse_json(payload.application_scopes_json)
            )
        elif isinstance(payload, TerminologyDefinitionPayload):
            invalid_scope = not scope_exists(payload.definition_scope_id)
        if invalid_entity:
            cls._finding(
                findings,
                record_errors,
                "I3B-ENTITY-REFERENCE",
                record_id,
                "Construct payload contains an invalid entity reference",
            )
        if invalid_scope:
            cls._finding(
                findings,
                record_errors,
                "I3B-SCOPE-REFERENCE",
                record_id,
                "Construct payload contains an invalid scope reference",
            )

    @classmethod
    def _check_relationship_policy(
        cls,
        connection: sqlite3.Connection,
        payload: ConstructRelationshipPayload,
        findings: list[ConstructIntegrityFinding],
        record_errors: set[str],
    ) -> None:
        policy = CONSTRUCT_RELATIONSHIP_POLICIES.get(payload.relationship_type)
        if policy is None:
            cls._finding(
                findings,
                record_errors,
                "I3B-RELATIONSHIP-TYPE",
                payload.record_id,
                "Construct relationship type is not registered",
            )
            return
        if (
            payload.subject_entity_id == payload.object_entity_id
            and not policy.self_reference_permitted
        ):
            cls._finding(
                findings,
                record_errors,
                "I3B-RELATIONSHIP-SELF-REFERENCE",
                payload.record_id,
                "Construct relationship violates self-reference policy",
            )
        if payload.bidirectional and not policy.bidirectional_permitted:
            cls._finding(
                findings,
                record_errors,
                "I3B-RELATIONSHIP-BIDIRECTIONAL",
                payload.record_id,
                "Construct relationship violates bidirectional policy",
            )
        for grant in connection.execute(
            "SELECT authority_class FROM memory_approval_grants WHERE record_id = ?",
            (payload.record_id,),
        ):
            if grant["authority_class"] != policy.required_approval_authority_class:
                cls._finding(
                    findings,
                    record_errors,
                    "I3B-RELATIONSHIP-AUTHORITY",
                    payload.record_id,
                    "Construct relationship grant does not meet its exact authority floor",
                )
        current = connection.execute(
            "SELECT approval_status FROM records WHERE record_id = ?",
            (payload.record_id,),
        ).fetchone()
        if (
            policy.authority_bearing
            and current is not None
            and current["approval_status"] == "approved"
            and connection.execute(
                """
                SELECT 1
                FROM memory_record_approval_transitions AS transition
                JOIN memory_approval_grants AS grant_record
                  ON grant_record.grant_id = transition.approval_grant_id
                WHERE transition.record_id = ?
                  AND transition.to_status = 'approved'
                  AND grant_record.authority_class = ?
                LIMIT 1
                """,
                (
                    payload.record_id,
                    policy.required_approval_authority_class,
                ),
            ).fetchone()
            is None
        ):
            cls._finding(
                findings,
                record_errors,
                "I3B-RELATIONSHIP-AUTHORITY",
                payload.record_id,
                "authority-bearing relationship lacks Nolan-specific approval",
            )

    @classmethod
    def _check_construct_supersession(
        cls,
        connection: sqlite3.Connection,
        findings: list[ConstructIntegrityFinding],
        record_errors: set[str],
    ) -> None:
        active_states: dict[tuple[str, str], str] = {}
        for row in connection.execute(
            """
            SELECT state.record_id, state.project_id, state.state_type,
                   record.lifecycle_state, record.supersedes_record_id
            FROM project_states AS state
            JOIN records AS record ON record.record_id = state.record_id
            ORDER BY state.project_id, state.state_type, state.record_id
            """
        ):
            key = (row["project_id"], row["state_type"])
            if row["lifecycle_state"] == "active":
                if key in active_states:
                    cls._finding(
                        findings,
                        record_errors,
                        "I3B-ACTIVE-PROJECT-STATE-DUPLICATE",
                        row["record_id"],
                        "multiple active project states share a project and state type",
                    )
                else:
                    active_states[key] = row["record_id"]
            cls._check_one_supersession(
                connection,
                row["record_id"],
                "project_state",
                row["lifecycle_state"],
                row["supersedes_record_id"],
                findings,
                record_errors,
            )

        active_terms: dict[tuple[str, str], str] = {}
        for row in connection.execute(
            """
            SELECT definition.record_id, definition.definition_scope_id,
                   definition.term, record.lifecycle_state,
                   record.supersedes_record_id
            FROM terminology_definitions AS definition
            JOIN records AS record ON record.record_id = definition.record_id
            ORDER BY definition.definition_scope_id, definition.term,
                     definition.record_id
            """
        ):
            key = (
                row["definition_scope_id"],
                normalize_construct_term(row["term"]),
            )
            if row["lifecycle_state"] == "active":
                if key in active_terms:
                    cls._finding(
                        findings,
                        record_errors,
                        "I3B-ACTIVE-TERM-DUPLICATE",
                        row["record_id"],
                        "multiple active term definitions share a normalized scoped term",
                    )
                else:
                    active_terms[key] = row["record_id"]
            cls._check_one_supersession(
                connection,
                row["record_id"],
                "terminology_definition",
                row["lifecycle_state"],
                row["supersedes_record_id"],
                findings,
                record_errors,
            )

    @staticmethod
    def _supersession_payloads_match(
        connection: sqlite3.Connection,
        record_type: str,
        source_record_id: str,
        target_record_id: str,
    ) -> bool:
        if record_type == "project_state":
            source = connection.execute(
                "SELECT project_id, state_type FROM project_states WHERE record_id = ?",
                (source_record_id,),
            ).fetchone()
            target = connection.execute(
                "SELECT project_id, state_type FROM project_states WHERE record_id = ?",
                (target_record_id,),
            ).fetchone()
            return (
                source is not None
                and target is not None
                and source["project_id"] == target["project_id"]
                and source["state_type"] == target["state_type"]
            )
        source = connection.execute(
            """
            SELECT term, definition_scope_id
            FROM terminology_definitions WHERE record_id = ?
            """,
            (source_record_id,),
        ).fetchone()
        target = connection.execute(
            """
            SELECT term, definition_scope_id
            FROM terminology_definitions WHERE record_id = ?
            """,
            (target_record_id,),
        ).fetchone()
        return (
            source is not None
            and target is not None
            and source["definition_scope_id"] == target["definition_scope_id"]
            and normalize_construct_term(source["term"])
            == normalize_construct_term(target["term"])
        )

    @classmethod
    def _check_one_supersession(
        cls,
        connection: sqlite3.Connection,
        record_id: str,
        record_type: str,
        lifecycle_state: str,
        declared_target: str | None,
        findings: list[ConstructIntegrityFinding],
        record_errors: set[str],
    ) -> None:
        outgoing = list(
            connection.execute(
                """
                SELECT relationship.target_record_id,
                       target.lifecycle_state AS target_lifecycle_state,
                       target.record_type AS target_record_type
                FROM record_relationships AS relationship
                JOIN records AS target
                  ON target.record_id = relationship.target_record_id
                WHERE relationship.source_record_id = ?
                  AND relationship.relationship_type = 'supersedes'
                ORDER BY relationship.relationship_id
                """,
                (record_id,),
            )
        )
        incoming = list(
            connection.execute(
                """
                SELECT relationship.source_record_id,
                       source.lifecycle_state AS source_lifecycle_state,
                       source.approval_status AS source_approval_status,
                       source.integrity_status AS source_integrity_status,
                       source.supersedes_record_id AS source_supersedes_record_id,
                       source.record_type AS source_record_type
                FROM record_relationships AS relationship
                JOIN records AS source
                  ON source.record_id = relationship.source_record_id
                WHERE relationship.target_record_id = ?
                  AND relationship.relationship_type = 'supersedes'
                ORDER BY relationship.relationship_id
                """,
                (record_id,),
            )
        )
        if lifecycle_state == "superseded":
            matching = [
                row
                for row in incoming
                if row["source_record_type"] == record_type
                and row["source_lifecycle_state"] in {"approved", "active"}
                and row["source_approval_status"] == "approved"
                and row["source_integrity_status"] == "valid"
                and row["source_supersedes_record_id"] in {None, record_id}
                and cls._supersession_payloads_match(
                    connection,
                    record_type,
                    row["source_record_id"],
                    record_id,
                )
            ]
            if len(matching) != 1:
                cls._finding(
                    findings,
                    record_errors,
                    "I3B-SUPERSESSION-REPLACEMENT",
                    record_id,
                    "superseded Construct record lacks one governed approved replacement",
                )
        if lifecycle_state == "active" and (declared_target is not None or outgoing):
            if (
                len(outgoing) != 1
                or outgoing[0]["target_record_type"] != record_type
                or outgoing[0]["target_lifecycle_state"] != "superseded"
                or not cls._supersession_payloads_match(
                    connection,
                    record_type,
                    record_id,
                    outgoing[0]["target_record_id"],
                )
                or (
                    declared_target is not None
                    and outgoing[0]["target_record_id"] != declared_target
                )
            ):
                cls._finding(
                    findings,
                    record_errors,
                    "I3B-SUPERSESSION-TARGET",
                    record_id,
                    "active Construct replacement does not point to one matching superseded target",
                )

    @classmethod
    def _inspect_connection(
        cls,
        connection: sqlite3.Connection,
    ) -> ConstructIntegrityReport:
        findings: list[ConstructIntegrityFinding] = []
        record_errors: set[str] = set()
        cls._check_registry(connection, findings, record_errors)

        payload_locations: dict[str, list[tuple[str, sqlite3.Row]]] = {}
        for record_type, table in CONSTRUCT_PAYLOAD_TABLES.items():
            for payload_row in connection.execute(f"SELECT * FROM {table}"):
                payload_locations.setdefault(payload_row["record_id"], []).append(
                    (record_type, payload_row)
                )
                envelope_row = connection.execute(
                    "SELECT record_family, record_type FROM records WHERE record_id = ?",
                    (payload_row["record_id"],),
                ).fetchone()
                if envelope_row is None:
                    cls._finding(
                        findings,
                        record_errors,
                        "I3B-ORPHAN-PAYLOAD",
                        payload_row["record_id"],
                        f"{table} payload has no universal envelope",
                    )
                elif (
                    envelope_row["record_family"] != "construct_memory"
                    or envelope_row["record_type"] != record_type
                ):
                    cls._finding(
                        findings,
                        record_errors,
                        "I3B-WRONG-PAYLOAD-TABLE",
                        payload_row["record_id"],
                        f"{table} payload does not match its envelope type",
                    )

        records = list(
            connection.execute(
                """
                SELECT * FROM records
                WHERE record_family = 'construct_memory'
                  AND record_type IN (
                    'construct_entity', 'construct_relationship',
                    'architecture_decision', 'project_state',
                    'construct_doctrine', 'terminology_definition',
                    'preference_record'
                  )
                ORDER BY record_id
                """
            )
        )
        for record in records:
            record_id = record["record_id"]
            locations = payload_locations.get(record_id, [])
            if not locations:
                cls._finding(
                    findings,
                    record_errors,
                    "I3B-MISSING-PAYLOAD",
                    record_id,
                    "Construct envelope has no typed payload",
                )
                continue
            if len(locations) > 1:
                cls._finding(
                    findings,
                    record_errors,
                    "I3B-DUPLICATE-PAYLOAD",
                    record_id,
                    "Construct envelope has incompatible duplicate payloads",
                )
                continue
            stored_type, payload_row = locations[0]
            if stored_type != record["record_type"]:
                continue
            try:
                payload = payload_from_database(stored_type, dict(payload_row))
                if payload.database_values() != dict(payload_row):
                    cls._finding(
                        findings,
                        record_errors,
                        "I3B-NONCANONICAL-PAYLOAD",
                        record_id,
                        "persisted payload differs from its canonical typed values",
                    )
            except Exception as exc:
                cls._finding(
                    findings,
                    record_errors,
                    "I3B-MALFORMED-PAYLOAD",
                    record_id,
                    f"typed payload cannot be reconstructed: {type(exc).__name__}",
                )
                continue
            cls._check_references(
                connection,
                payload,
                findings,
                record_errors,
            )
            if isinstance(payload, ConstructRelationshipPayload):
                cls._check_relationship_policy(
                    connection,
                    payload,
                    findings,
                    record_errors,
                )
            try:
                expected_hash = construct_memory_content_hash(
                    _envelope(record),
                    payload,
                )
            except Exception as exc:
                cls._finding(
                    findings,
                    record_errors,
                    "I3B-ENVELOPE-PAYLOAD-MISMATCH",
                    record_id,
                    f"envelope and payload cannot be combined: {type(exc).__name__}",
                )
            else:
                if expected_hash != record["content_hash"]:
                    cls._finding(
                        findings,
                        record_errors,
                        "I3B-CONTENT-HASH",
                        record_id,
                        "combined envelope-plus-payload hash does not match",
                    )
            if not record["provenance_summary"].strip():
                cls._finding(
                    findings,
                    record_errors,
                    "I3B-MISSING-PROVENANCE",
                    record_id,
                    "Construct record is missing provenance",
                )
            evidence_rows = list(
                connection.execute(
                    """
                    SELECT item.evidence_kind, item.integrity_status
                    FROM record_evidence_links AS link
                    JOIN evidence_items AS item
                      ON item.evidence_id = link.evidence_id
                    WHERE link.record_id = ?
                    """,
                    (record_id,),
                )
            )
            if (
                not evidence_rows
                or any(
                    evidence["integrity_status"] != "valid"
                    or evidence["evidence_kind"] in {
                        "controlled_prompt",
                        "controlled_output",
                    }
                    for evidence in evidence_rows
                )
                or (
                    isinstance(payload, PreferenceRecordPayload)
                    and {row["evidence_kind"] for row in evidence_rows}
                    <= {"model_output"}
                )
            ):
                cls._finding(
                    findings,
                    record_errors,
                    "I3B-MISSING-OR-INVALID-EVIDENCE",
                    record_id,
                    "Construct record lacks an accepted valid evidence source",
                )
            lifecycle = connection.execute(
                """
                SELECT 1 FROM memory_record_lifecycle_transitions
                WHERE record_id = ? AND sequence_number = 0
                  AND from_state IS NULL
                  AND to_state IN ('observed', 'candidate', 'reviewed')
                """,
                (record_id,),
            ).fetchone()
            if lifecycle is None:
                cls._finding(
                    findings,
                    record_errors,
                    "I3B-MISSING-INITIAL-LIFECYCLE",
                    record_id,
                    "Construct record lacks matching sequence-zero lifecycle history",
                )
            approval = connection.execute(
                """
                SELECT 1 FROM memory_record_approval_transitions
                WHERE record_id = ? AND sequence_number = 0
                  AND from_status IS NULL AND to_status = 'pending'
                """,
                (record_id,),
            ).fetchone()
            if approval is None:
                cls._finding(
                    findings,
                    record_errors,
                    "I3B-MISSING-INITIAL-APPROVAL",
                    record_id,
                    "Construct record lacks sequence-zero approval history",
                )

        cls._check_construct_supersession(
            connection,
            findings,
            record_errors,
        )

        for record in records:
            recomputed_valid = record["record_id"] not in record_errors
            stored_valid = record["integrity_status"] == "valid"
            if recomputed_valid != stored_valid:
                findings.append(
                    ConstructIntegrityFinding(
                        "I3B-STORED-INTEGRITY-DISAGREEMENT",
                        "error",
                        record["record_id"],
                        "stored integrity_status disagrees with independent recomputation",
                    )
                )
        return ConstructIntegrityReport(tuple(findings))

    def inspect(self) -> ConstructIntegrityReport:
        return self._kernel.read(self._inspect_connection)
