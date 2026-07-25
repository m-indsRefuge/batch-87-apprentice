"""Deterministic repositories behind the single governed write boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import parse_json
from batch87_apprentice.common.errors import NotFoundError, ValidationError
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc

from .contracts import (
    ControlledResiliencePayload,
    Entity,
    EntityAlias,
    EvidenceItem,
    EvidenceLink,
    RecordEnvelope,
    ReferenceAnchor,
    RuntimeInstance,
    Scope,
    controlled_resilience_content_hash,
    record_content_hash,
)
from .transactions import PersistenceKernel


def _insert_values(
    connection: sqlite3.Connection,
    table: str,
    values: Mapping[str, Any],
) -> None:
    columns = tuple(values)
    placeholders = ", ".join(f":{column}" for column in columns)
    connection.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        dict(values),
    )


def _one(
    connection: sqlite3.Connection,
    statement: str,
    parameters: tuple[Any, ...],
    *,
    kind: str,
    identifier: str,
) -> dict[str, Any]:
    row = connection.execute(statement, parameters).fetchone()
    if row is None:
        raise NotFoundError(f"{kind} not found: {identifier}")
    return dict(row)


def _insert_record(
    connection: sqlite3.Connection,
    envelope: RecordEnvelope,
    *,
    content_hash: str,
) -> None:
    _insert_values(
        connection,
        "records",
        envelope.database_values(content_hash=content_hash),
    )


def _insert_evidence(
    connection: sqlite3.Connection,
    item: EvidenceItem,
) -> None:
    _insert_values(connection, "evidence_items", item.database_values())
    if item.inline_content is not None:
        connection.execute(
            """
            INSERT INTO evidence_inline_text (evidence_id, content, encoding)
            VALUES (?, ?, 'utf-8')
            """,
            (item.evidence_id, item.inline_content),
        )


def _insert_anchor(
    connection: sqlite3.Connection,
    anchor: ReferenceAnchor,
) -> None:
    if anchor.lifecycle_state != "registered" or anchor.integrity_status != "valid":
        raise ValidationError("new anchors must be registered with valid integrity")
    connection.execute(
        """
        INSERT INTO governed_reference_anchors (
            reference_id, reference_kind, project_scope_id, lifecycle_state,
            created_at, provenance_json, content_hash, integrity_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            anchor.reference_id,
            anchor.reference_kind,
            anchor.project_scope_id,
            anchor.lifecycle_state,
            anchor.created_at,
            anchor.provenance_json,
            anchor.content_hash,
            anchor.integrity_status,
        ),
    )


class RuntimeRepository:
    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel

    def start(self, instance: RuntimeInstance) -> None:
        self._kernel.write(
            lambda connection: _insert_values(
                connection,
                "runtime_instances",
                {
                    field: getattr(instance, field)
                    for field in instance.__dataclass_fields__
                },
            )
        )

    def stop(
        self,
        runtime_instance_id: str,
        *,
        stopped_at: str,
        status: str = "stopped",
    ) -> None:
        validate_identifier(runtime_instance_id, field="runtime_instance_id")
        parse_canonical_utc(stopped_at, field="stopped_at")
        if status not in {"stopped", "failed"}:
            raise ValidationError("terminal runtime status must be stopped or failed")

        def operation(connection: sqlite3.Connection) -> None:
            cursor = connection.execute(
                """
                UPDATE runtime_instances
                SET stopped_at = ?, status = ?
                WHERE runtime_instance_id = ? AND status = 'running'
                """,
                (stopped_at, status, runtime_instance_id),
            )
            if cursor.rowcount != 1:
                raise NotFoundError(
                    f"running runtime instance not found: {runtime_instance_id}"
                )

        self._kernel.write(operation)

    def get(self, runtime_instance_id: str) -> Mapping[str, Any]:
        validate_identifier(runtime_instance_id, field="runtime_instance_id")
        return self._kernel.read(
            lambda connection: _one(
                connection,
                "SELECT * FROM runtime_instances WHERE runtime_instance_id = ?",
                (runtime_instance_id,),
                kind="runtime instance",
                identifier=runtime_instance_id,
            )
        )


class EntityRepository:
    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel

    def create(self, entity: Entity) -> None:
        self._kernel.write(
            lambda connection: _insert_values(
                connection,
                "entities",
                {
                    field: getattr(entity, field)
                    for field in entity.__dataclass_fields__
                },
            )
        )

    def add_alias(self, alias: EntityAlias) -> None:
        self._kernel.write(
            lambda connection: _insert_values(
                connection,
                "entity_aliases",
                {
                    field: getattr(alias, field)
                    for field in alias.__dataclass_fields__
                },
            )
        )

    def get(self, entity_id: str) -> Mapping[str, Any]:
        validate_identifier(entity_id, field="entity_id")
        return self._kernel.read(
            lambda connection: _one(
                connection,
                "SELECT * FROM entities WHERE entity_id = ?",
                (entity_id,),
                kind="entity",
                identifier=entity_id,
            )
        )


class ScopeRepository:
    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel

    def create(self, scope: Scope) -> None:
        self._kernel.write(
            lambda connection: _insert_values(
                connection,
                "scopes",
                {
                    field: getattr(scope, field)
                    for field in scope.__dataclass_fields__
                },
            )
        )

    def get(self, scope_id: str) -> Mapping[str, Any]:
        validate_identifier(scope_id, field="scope_id")
        return self._kernel.read(
            lambda connection: _one(
                connection,
                "SELECT * FROM scopes WHERE scope_id = ?",
                (scope_id,),
                kind="scope",
                identifier=scope_id,
            )
        )


class RecordRepository:
    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel

    def create(self, envelope: RecordEnvelope) -> str:
        if (
            envelope.record_family == "evaluation_evidence"
            and envelope.record_type == "controlled_governance_resilience_run"
        ):
            raise ValidationError(
                "controlled-resilience records require their atomic repository"
            )
        registered_memory = self._kernel.read(
            lambda connection: (
                connection.execute(
                    """
                    SELECT 1
                    FROM memory_record_types
                    WHERE record_family = ?
                      AND record_type = ?
                      AND status = 'active'
                    """,
                    (envelope.record_family, envelope.record_type),
                ).fetchone()
                is not None
            )
        )
        if registered_memory:
            raise ValidationError(
                "memory records require a governed domain repository"
            )
        digest = record_content_hash(envelope)
        self._kernel.write(
            lambda connection: _insert_record(
                connection,
                envelope,
                content_hash=digest,
            )
        )
        return digest

    def get(self, record_id: str) -> Mapping[str, Any]:
        validate_identifier(record_id, field="record_id")
        return self._kernel.read(
            lambda connection: _one(
                connection,
                "SELECT * FROM records WHERE record_id = ?",
                (record_id,),
                kind="record",
                identifier=record_id,
            )
        )


class EvidenceRepository:
    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel

    def create(self, item: EvidenceItem) -> None:
        self._kernel.write(lambda connection: _insert_evidence(connection, item))

    def link(self, link: EvidenceLink) -> None:
        self._kernel.write(
            lambda connection: connection.execute(
                """
                INSERT INTO record_evidence_links (
                    record_id, evidence_id, relationship, explanation
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    link.record_id,
                    link.evidence_id,
                    link.relationship,
                    link.explanation,
                ),
            )
        )

    def get(self, evidence_id: str) -> Mapping[str, Any]:
        validate_identifier(evidence_id, field="evidence_id")

        def operation(connection: sqlite3.Connection) -> dict[str, Any]:
            result = _one(
                connection,
                """
                SELECT item.*, inline.content AS inline_content,
                       inline.encoding AS inline_encoding
                FROM evidence_items AS item
                LEFT JOIN evidence_inline_text AS inline
                  ON inline.evidence_id = item.evidence_id
                WHERE item.evidence_id = ?
                """,
                (evidence_id,),
                kind="evidence",
                identifier=evidence_id,
            )
            return result

        return self._kernel.read(operation)


class ReferenceAnchorRepository:
    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel

    def register(self, anchor: ReferenceAnchor) -> str:
        self._kernel.write(lambda connection: _insert_anchor(connection, anchor))
        return anchor.content_hash

    def get(self, reference_id: str) -> Mapping[str, Any]:
        validate_identifier(reference_id, field="reference_id")
        return self._kernel.read(
            lambda connection: _one(
                connection,
                """
                SELECT * FROM governed_reference_anchors
                WHERE reference_id = ?
                """,
                (reference_id,),
                kind="reference anchor",
                identifier=reference_id,
            )
        )


class ControlledResilienceRepository:
    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel

    @staticmethod
    def _validate_pair(
        envelope: RecordEnvelope,
        payload: ControlledResiliencePayload,
    ) -> None:
        if payload.record_id != envelope.record_id:
            raise ValidationError("payload and envelope record identifiers differ")
        if envelope.record_family != "evaluation_evidence":
            raise ValidationError("controlled record family must be evaluation_evidence")
        if envelope.record_type != "controlled_governance_resilience_run":
            raise ValidationError(
                "controlled record type must be controlled_governance_resilience_run"
            )
        if envelope.lifecycle_state not in {
            "observed",
            "reviewed",
            "approved",
            "archived",
        }:
            raise ValidationError("controlled record has an invalid lifecycle")
        if envelope.sensitivity_class != "restricted":
            raise ValidationError("controlled records must remain restricted")
        if envelope.training_eligibility != "prohibited":
            raise ValidationError("controlled records prohibit training")
        if envelope.integrity_status != "valid":
            raise ValidationError("new controlled records require valid integrity")
        retrieval = parse_json(envelope.retrieval_policy_json)
        if (
            retrieval.get("ordinary_memory_eligibility") != "prohibited"
            or retrieval.get("retrieval_mode") != "evaluation_only"
        ):
            raise ValidationError("controlled retrieval policy is not isolated")
        if payload.lesson_derivation_status == "candidate_created":
            raise ValidationError("B87-I1 cannot create lesson candidates")
        if payload.created_at != envelope.created_at:
            raise ValidationError("payload and envelope timestamps must match")

    @staticmethod
    def _validate_raw_evidence(
        connection: sqlite3.Connection,
        payload: ControlledResiliencePayload,
    ) -> None:
        rows = {
            row["evidence_id"]: row
            for row in connection.execute(
                """
                SELECT evidence_id, evidence_kind, sensitivity_class,
                       integrity_status
                FROM evidence_items
                WHERE evidence_id IN (?, ?)
                """,
                (
                    payload.raw_prompt_evidence_id,
                    payload.raw_output_evidence_id,
                ),
            )
        }
        expected = {
            payload.raw_prompt_evidence_id: "controlled_prompt",
            payload.raw_output_evidence_id: "controlled_output",
        }
        for evidence_id, evidence_kind in expected.items():
            row = rows.get(evidence_id)
            if row is None:
                raise ValidationError(
                    f"required controlled evidence is missing: {evidence_id}"
                )
            if (
                row["evidence_kind"] != evidence_kind
                or row["sensitivity_class"] != "restricted"
                or row["integrity_status"] != "valid"
            ):
                raise ValidationError(
                    f"controlled evidence classification is invalid: {evidence_id}"
                )

    def create(
        self,
        envelope: RecordEnvelope,
        payload: ControlledResiliencePayload,
        *,
        anchors: Sequence[ReferenceAnchor] = (),
        evidence_items: Sequence[EvidenceItem] = (),
    ) -> str:
        """Atomically persist supplied anchors, evidence, envelope, and payload."""

        self._validate_pair(envelope, payload)
        digest = controlled_resilience_content_hash(envelope, payload)

        def operation(connection: sqlite3.Connection) -> None:
            for anchor in anchors:
                _insert_anchor(connection, anchor)
            for item in evidence_items:
                _insert_evidence(connection, item)
            self._validate_raw_evidence(connection, payload)
            _insert_record(connection, envelope, content_hash=digest)
            _insert_values(
                connection,
                "controlled_resilience_evidence",
                payload.database_values(),
            )
            connection.executemany(
                """
                INSERT INTO record_evidence_links (
                    record_id, evidence_id, relationship, explanation
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    (
                        envelope.record_id,
                        payload.raw_prompt_evidence_id,
                        "evaluated_against",
                        "Exact controlled prompt evidence.",
                    ),
                    (
                        envelope.record_id,
                        payload.raw_output_evidence_id,
                        "produced_as",
                        "Exact controlled output evidence.",
                    ),
                ),
            )

        self._kernel.write(operation)
        return digest

    def get(self, record_id: str) -> Mapping[str, Any]:
        validate_identifier(record_id, field="record_id")
        return self._kernel.read(
            lambda connection: _one(
                connection,
                """
                SELECT payload.*, record.project_scope_id,
                       record.lifecycle_state, record.approval_status,
                       record.sensitivity_class, record.training_eligibility,
                       record.content_hash, record.integrity_status
                FROM controlled_resilience_evidence AS payload
                JOIN records AS record ON record.record_id = payload.record_id
                WHERE payload.record_id = ?
                """,
                (record_id,),
                kind="controlled-resilience record",
                identifier=record_id,
            )
        )
