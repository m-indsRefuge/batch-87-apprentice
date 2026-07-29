"""Governed I3-D retrieval, safe materialization and I4-A reconstruction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
from batch87_apprentice.common.hashing import sha256_bytes, sha256_canonical_json
from batch87_apprentice.common.identifiers import (
    generate_identifier,
    validate_identifier,
)
from batch87_apprentice.common.timestamps import parse_canonical_utc
from batch87_apprentice.memory.session_task_repository import (
    SessionTaskMemoryRepository,
)
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.integrity import (
    inspect_task_runtime_integrity,
)
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .assembly import (
    ContextAssembler,
    ContaminationInspector,
    _authoritative_binding_mismatch_specs,
    build_authoritative_authority_section,
    build_authoritative_task_section,
)
from .contracts import (
    RETRIEVAL_CONTRACT_VERSION,
    STRUCTURED_CONTEXT_VERSION,
    ContaminationFinding,
    ContextReadinessAssessment,
    ContextReadinessFinding,
    OrderedContextEntry,
    RankComponents,
    RankedCandidate,
    RecoveryRelationship,
    RetrievalAssemblyResult,
    RetrievalCandidate,
    RetrievalManifest,
    RetrievalManifestEntry,
    RetrievalRequest,
    StructuredContextPackage,
)
from .ranking import DeterministicFallbackRanker, RelevanceRanker


_TARGET_SECTION_BY_CONTEXT_KIND = {
    "constitution": "policy",
    "policy": "policy",
    "evidence": "evidence",
    "session_instruction": "evidence",
    "construct_memory": "memory",
    "approved_lesson": "memory",
}

_SOURCE_IDENTIFIER_FIELD = {
    "memory_record": "memory_record_id",
    "evidence": "evidence_id",
    "governance_rule": "governance_rule_id",
}

_CONSTRUCT_PAYLOAD_TABLE = {
    "construct_entity": "construct_entities",
    "construct_relationship": "construct_relationships",
    "architecture_decision": "architecture_decisions",
    "project_state": "project_states",
    "construct_doctrine": "construct_doctrines",
    "terminology_definition": "terminology_definitions",
    "preference_record": "preference_records",
}

_MAX_INLINE_EVIDENCE_BYTES = 65_536
_MATERIALIZATION_MODES = frozenset({"active", "historical"})


def _canonical_object(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise IntegrityInspectionError(f"{field} is not stored as JSON text")
    try:
        parsed = parse_json(value)
    except ValidationError as exc:
        raise IntegrityInspectionError(f"{field} is malformed") from exc
    if not isinstance(parsed, dict) or canonical_json_text(parsed) != value:
        raise IntegrityInspectionError(f"{field} is not a canonical JSON object")
    return parsed


def _canonical_array(value: object, *, field: str) -> list[Any]:
    if not isinstance(value, str):
        raise IntegrityInspectionError(f"{field} is not stored as JSON text")
    try:
        parsed = parse_json(value)
    except ValidationError as exc:
        raise IntegrityInspectionError(f"{field} is malformed") from exc
    if not isinstance(parsed, list) or canonical_json_text(parsed) != value:
        raise IntegrityInspectionError(f"{field} is not a canonical JSON array")
    return parsed


def _source_id(item: Mapping[str, Any]) -> str:
    source = item.get("source")
    if not isinstance(source, Mapping):
        raise IntegrityInspectionError("I3-D context item has no typed source")
    source_kind = source.get("source_kind")
    identifier_field = _SOURCE_IDENTIFIER_FIELD.get(source_kind)
    if identifier_field is None:
        raise IntegrityInspectionError("I3-D context item source kind is invalid")
    identifier = source.get(identifier_field)
    if not isinstance(identifier, str):
        raise IntegrityInspectionError("I3-D context item source identity is absent")
    validate_identifier(identifier, field=identifier_field)
    return identifier


def _source_columns(
    source_kind: str,
    source_id: str,
) -> tuple[str | None, str | None, str | None]:
    if source_kind == "memory_record":
        return source_id, None, None
    if source_kind == "evidence":
        return None, source_id, None
    if source_kind == "governance_rule":
        return None, None, source_id
    raise ValidationError("retrieval source kind is invalid")


def _convert_payload_row(row: sqlite3.Row) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in row.keys():
        if key == "record_id":
            continue
        value = row[key]
        if key.endswith("_json"):
            try:
                parsed = parse_json(value)
            except ValidationError as exc:
                raise IntegrityInspectionError(
                    f"memory payload field {key} is malformed"
                ) from exc
            if canonical_json_text(parsed) != value:
                raise IntegrityInspectionError(
                    f"memory payload field {key} is not canonical"
                )
            payload[key.removesuffix("_json")] = parsed
        elif key == "bidirectional":
            payload[key] = bool(value)
        else:
            payload[key] = value
    return payload


def _exact_evidence_relationships(
    connection: sqlite3.Connection,
    *,
    evidence_id: str,
    task_id: str,
    project_scope_id: str,
) -> tuple[dict[str, Any], ...]:
    """Return only the accepted exact required/resolved evidence binding."""

    return tuple(
        {
            "governance_decision_id": row["governance_decision_id"],
            "input_kind": row["input_kind"],
            "input_order": row["input_order"],
            "project_scope_id": row["project_scope_id"],
            "required_evidence_id": row["required_evidence_id"],
            "resolved_evidence_id": row["resolved_evidence_id"],
            "task_id": row["task_id"],
            "validation_status": row["validation_status"],
        }
        for row in connection.execute(
            """
            SELECT relationship.governance_decision_id,
                   relationship.input_order,
                   relationship.input_kind,
                   relationship.required_evidence_id,
                   relationship.resolved_evidence_id,
                   relationship.validation_status,
                   decision_record.task_id,
                   decision_record.project_scope_id
            FROM governance_decision_evidence AS relationship
            JOIN governance_decisions AS decision_record
              ON decision_record.governance_decision_id =
                 relationship.governance_decision_id
            WHERE relationship.required_evidence_id = ?
              AND relationship.resolved_evidence_id = ?
              AND relationship.validation_status = 'available'
              AND decision_record.task_id = ?
              AND decision_record.project_scope_id = ?
            ORDER BY relationship.input_order,
                     relationship.governance_decision_id
            """,
            (evidence_id, evidence_id, task_id, project_scope_id),
        )
    )


def _record_state_at(
    connection: sqlite3.Connection,
    *,
    record_id: str,
    table: str,
    value_column: str,
    evaluated_at: str,
) -> str | None:
    if table not in {
        "memory_record_lifecycle_transitions",
        "memory_record_approval_transitions",
    } or value_column not in {"to_state", "to_status"}:
        raise ValueError("unsupported governed memory transition lookup")
    row = connection.execute(
        f"""
        SELECT {value_column} AS value
        FROM {table}
        WHERE record_id = ? AND changed_at <= ?
        ORDER BY sequence_number DESC
        LIMIT 1
        """,  # noqa: S608
        (record_id, evaluated_at),
    ).fetchone()
    return None if row is None else row["value"]


def _selected_memory_integrity(
    connection: sqlite3.Connection,
    *,
    row: sqlite3.Row,
    context_kind: str,
    task_id: str,
    project_scope_id: str,
    mode: str,
    evaluated_at: str | None,
) -> tuple[tuple[str, ...], str, str]:
    """Validate one selected typed memory without rejecting unrelated records."""

    if mode not in _MATERIALIZATION_MODES:
        raise ValidationError("materialization mode is invalid")
    if mode == "historical":
        if evaluated_at is None:
            raise ValidationError(
                "historical materialization requires evaluated_at"
            )
        parse_canonical_utc(evaluated_at, field="evaluated_at")
        lifecycle_state = _record_state_at(
            connection,
            record_id=row["record_id"],
            table="memory_record_lifecycle_transitions",
            value_column="to_state",
            evaluated_at=evaluated_at,
        )
        approval_status = _record_state_at(
            connection,
            record_id=row["record_id"],
            table="memory_record_approval_transitions",
            value_column="to_status",
            evaluated_at=evaluated_at,
        )
    else:
        lifecycle_state = row["lifecycle_state"]
        approval_status = row["approval_status"]

    reasons: set[str] = set()
    if lifecycle_state is None or approval_status is None:
        reasons.add("source_integrity_invalid")
        lifecycle_state = row["lifecycle_state"]
        approval_status = row["approval_status"]
    if row["integrity_status"] not in {"valid", "not_applicable"}:
        reasons.add("source_integrity_invalid")
    if row["project_scope_id"] != project_scope_id:
        reasons.add("cross_project_source")
    if row["task_id"] not in {None, task_id}:
        reasons.add("cross_task_source")
    if row["privacy_class"] != "none":
        reasons.add("privacy_denied")
    if row["sensitivity_class"] not in {"public", "internal"}:
        reasons.add("sensitivity_denied")
    if lifecycle_state != "active":
        reasons.add(
            {
                "superseded": "source_superseded",
                "revoked": "source_revoked",
                "deleted": "source_deleted",
            }.get(lifecycle_state, "source_not_active")
        )
    if approval_status not in {"approved", "not_required"}:
        reasons.add("source_not_approved")

    if context_kind == "construct_memory":
        from batch87_apprentice.memory.construct_integrity import (
            ConstructIntegrityInspector,
        )

        report = ConstructIntegrityInspector._inspect_connection(connection)
        attributable = (
            finding
            for finding in report.findings
            if finding.severity == "error"
            and finding.record_id == row["record_id"]
        )
    elif context_kind == "approved_lesson":
        from batch87_apprentice.memory.developmental_derivation_integrity import (
            DevelopmentalDerivationIntegrityInspector,
        )

        related_ids = {row["record_id"]}
        related_ids.update(
            grant["grant_id"]
            for grant in connection.execute(
                """
                SELECT grant_id FROM memory_approval_grants
                WHERE record_id = ?
                UNION
                SELECT grant_id FROM memory_relationship_grants
                WHERE target_record_id = ? OR source_record_id = ?
                """,
                (row["record_id"], row["record_id"], row["record_id"]),
            )
        )
        report = DevelopmentalDerivationIntegrityInspector._inspect_connection(
            connection
        )
        attributable = (
            finding
            for finding in report.findings
            if finding.severity == "error"
            and finding.record_id in related_ids
        )
    else:
        raise ValidationError("selected memory context kind is invalid")
    if next(attributable, None) is not None:
        reasons.add("source_integrity_invalid")

    return tuple(sorted(reasons)), lifecycle_state, approval_status


class _IdentifierAllocator:
    """Validate and de-duplicate all generated identities in one attempt."""

    def __init__(
        self,
        factory: Callable[[], str],
        *,
        reserved: tuple[str, ...],
    ) -> None:
        if not callable(factory):
            raise TypeError("identifier_factory must be callable")
        self._factory = factory
        self._seen = set(reserved)

    def new(self) -> str:
        identifier = self._factory()
        validate_identifier(identifier, field="generated identifier")
        if identifier in self._seen:
            raise ValidationError(
                "identifier factory returned a duplicate governed identity"
            )
        self._seen.add(identifier)
        return identifier


class _SafeSourceMaterializer:
    """Convert one eligible typed source into bounded provider-neutral JSON."""

    @staticmethod
    def _governance_rule(
        connection: sqlite3.Connection,
        *,
        source_id: str,
        task_id: str,
        project_scope_id: str,
    ) -> tuple[str, tuple[str, ...], str | None]:
        row = connection.execute(
            """
            SELECT * FROM governance_rules
            WHERE governance_rule_id = ?
            """,
            (source_id,),
        ).fetchone()
        if row is None:
            return "unavailable", ("source_missing",), None
        relationships = [
            {
                "governance_decision_id": relationship[
                    "governance_decision_id"
                ],
                "rule_order": relationship["rule_order"],
                "task_id": relationship["task_id"],
            }
            for relationship in connection.execute(
                """
                SELECT relationship.governance_decision_id,
                       relationship.rule_order, decision_record.task_id
                FROM governance_decision_rules AS relationship
                JOIN governance_decisions AS decision_record
                  ON decision_record.governance_decision_id =
                     relationship.governance_decision_id
                WHERE relationship.governance_rule_id = ?
                  AND decision_record.task_id = ?
                  AND decision_record.project_scope_id = ?
                ORDER BY relationship.rule_order,
                         relationship.governance_decision_id
                """,
                (source_id, task_id, project_scope_id),
            )
        ]
        if not relationships:
            return "invalid", ("source_not_task_bound",), None
        try:
            configuration = parse_json(row["configuration_json"])
        except ValidationError:
            return "invalid", ("source_integrity_invalid",), None
        if (
            not isinstance(configuration, dict)
            or canonical_json_text(configuration) != row["configuration_json"]
        ):
            return "invalid", ("source_integrity_invalid",), None
        material = {
            "classification": "governance policy context",
            "configuration": configuration,
            "content_hash": row["content_hash"],
            "description": row["description"],
            "rule_id": row["governance_rule_id"],
            "rule_kind": row["rule_kind"],
            "rule_name": row["rule_name"],
            "rule_version": row["rule_version"],
            "task_decision_relationships": relationships,
        }
        return "materialized", (), canonical_json_text(material)

    @staticmethod
    def _evidence(
        connection: sqlite3.Connection,
        *,
        source_id: str,
        task_id: str,
        project_scope_id: str,
    ) -> tuple[str, tuple[str, ...], str | None]:
        row = connection.execute(
            """
            SELECT evidence.*, inline.content, inline.encoding,
                   CASE WHEN controlled.record_id IS NULL
                        THEN 0 ELSE 1 END AS controlled_resilience
            FROM evidence_items AS evidence
            LEFT JOIN evidence_inline_text AS inline
              ON inline.evidence_id = evidence.evidence_id
            LEFT JOIN controlled_resilience_evidence AS controlled
              ON controlled.raw_prompt_evidence_id = evidence.evidence_id
              OR controlled.raw_output_evidence_id = evidence.evidence_id
            WHERE evidence.evidence_id = ?
            """,
            (source_id,),
        ).fetchone()
        if row is None:
            return "unavailable", ("source_missing",), None
        if (
            row["evidence_kind"] in {"controlled_prompt", "controlled_output"}
            or row["controlled_resilience"]
        ):
            return "prohibited", ("controlled_resilience_prohibited",), None
        if row["evidence_kind"] == "model_output":
            return "prohibited", ("model_output_prohibited",), None
        if (
            row["storage_kind"] != "inline_text"
            or row["content"] is None
            or row["encoding"] != "utf-8"
        ):
            return "unavailable", ("content_unavailable",), None
        if row["integrity_status"] != "valid":
            return "invalid", ("source_integrity_invalid",), None
        exact = row["content"].encode("utf-8")
        if (
            len(exact) > _MAX_INLINE_EVIDENCE_BYTES
            or row["byte_length"] != len(exact)
            or row["content_hash"] != sha256_bytes(exact)
        ):
            return "invalid", ("source_integrity_invalid",), None
        relationships = _exact_evidence_relationships(
            connection,
            evidence_id=source_id,
            task_id=task_id,
            project_scope_id=project_scope_id,
        )
        if not relationships:
            return "invalid", ("source_not_task_bound",), None
        material = {
            "byte_length": row["byte_length"],
            "captured_at": row["captured_at"],
            "captured_by_entity_id": row["captured_by_entity"],
            "classification": {
                "authority": (
                    "evidence is not authority unless separately represented "
                    "by I2"
                ),
                "memory": "evidence is not memory",
            },
            "content_hash": row["content_hash"],
            "evidence_id": row["evidence_id"],
            "evidence_kind": row["evidence_kind"],
            "media_type": row["media_type"],
            "privacy_class": row["privacy_class"],
            "redaction_status": row["redaction_status"],
            "sensitivity_class": row["sensitivity_class"],
            "task_decision_relationships": relationships,
            "text": row["content"],
        }
        return "materialized", (), canonical_json_text(material)

    @staticmethod
    def _memory(
        connection: sqlite3.Connection,
        *,
        source_id: str,
        context_kind: str,
        task_id: str,
        project_scope_id: str,
        mode: str,
        evaluated_at: str | None,
    ) -> tuple[str, tuple[str, ...], str | None]:
        row = connection.execute(
            "SELECT * FROM records WHERE record_id = ?",
            (source_id,),
        ).fetchone()
        if row is None:
            return "unavailable", ("source_missing",), None
        if (
            row["record_family"] == "episodic_memory"
            and row["record_type"] == "lesson_candidate"
        ):
            return "prohibited", ("lesson_candidate_prohibited",), None
        if (
            row["record_family"] == "evaluation_evidence"
            or row["record_type"] == "controlled_governance_resilience_run"
        ):
            return "prohibited", ("controlled_resilience_prohibited",), None

        if context_kind == "construct_memory":
            table = _CONSTRUCT_PAYLOAD_TABLE.get(row["record_type"])
            if row["record_family"] != "construct_memory" or table is None:
                return "invalid", ("source_type_mismatch",), None
            classification = {
                "authority": "not authority",
                "context_role": "contextual memory",
                "permission": "not a live permission or governance instruction",
            }
            memory_domain = "construct_relational_memory"
        elif context_kind == "approved_lesson":
            if (
                row["record_family"] != "episodic_memory"
                or row["record_type"] != "approved_lesson"
            ):
                return "invalid", ("source_type_mismatch",), None
            classification = {
                "authority": "not authority",
                "context_role": "approved contextual lesson",
            }
            memory_domain = "self_episodic_memory"
        else:
            return "invalid", ("source_type_mismatch",), None

        (
            integrity_reasons,
            lifecycle_state,
            approval_status,
        ) = _selected_memory_integrity(
            connection,
            row=row,
            context_kind=context_kind,
            task_id=task_id,
            project_scope_id=project_scope_id,
            mode=mode,
            evaluated_at=evaluated_at,
        )
        if integrity_reasons:
            prohibited = {
                "cross_project_source",
                "cross_task_source",
                "privacy_denied",
                "sensitivity_denied",
                "source_deleted",
                "source_not_active",
                "source_not_approved",
                "source_revoked",
                "source_superseded",
            }
            status = (
                "prohibited"
                if set(integrity_reasons).issubset(prohibited)
                else "invalid"
            )
            return status, integrity_reasons, None

        if context_kind == "construct_memory":
            payload_row = connection.execute(
                f"SELECT * FROM {table} WHERE record_id = ?",  # noqa: S608
                (source_id,),
            ).fetchone()
            if payload_row is None:
                return "invalid", ("source_integrity_invalid",), None
            try:
                payload = _convert_payload_row(payload_row)
            except IntegrityInspectionError:
                return "invalid", ("source_integrity_invalid",), None
        else:
            payload_row = connection.execute(
                "SELECT canonical_json FROM approved_lessons WHERE record_id = ?",
                (source_id,),
            ).fetchone()
            if payload_row is None:
                return "invalid", ("source_integrity_invalid",), None
            try:
                payload = parse_json(payload_row["canonical_json"])
            except ValidationError:
                return "invalid", ("source_integrity_invalid",), None
            if (
                not isinstance(payload, dict)
                or canonical_json_text(payload) != payload_row["canonical_json"]
            ):
                return "invalid", ("source_integrity_invalid",), None

        evidence_ids = [
            evidence_row["evidence_id"]
            for evidence_row in connection.execute(
                """
                SELECT evidence_id
                FROM record_evidence_links
                WHERE record_id = ?
                ORDER BY evidence_id, relationship
                """,
                (source_id,),
            )
        ]
        evidence_ids = sorted(set(evidence_ids))
        material = {
            "classification": classification,
            "content_hash": row["content_hash"],
            "memory_domain": memory_domain,
            "payload": payload,
            "provenance": {
                "source_evidence_ids": evidence_ids,
                "summary": row["provenance_summary"],
            },
            "record": {
                "approval_status": approval_status,
                "authority_class": row["authority_class"],
                "certainty_class": row["certainty_class"],
                "family": row["record_family"],
                "lifecycle_state": lifecycle_state,
                "privacy_class": row["privacy_class"],
                "record_id": row["record_id"],
                "sensitivity_class": row["sensitivity_class"],
                "type": row["record_type"],
            },
            "scope": {
                "construct_scope_id": row["construct_scope_id"],
                "project_scope_id": row["project_scope_id"],
                "session_id": row["session_id"],
                "task_id": row["task_id"],
            },
        }
        return "materialized", (), canonical_json_text(material)

    def materialize(
        self,
        connection: sqlite3.Connection,
        *,
        source_kind: str,
        source_id: str,
        context_kind: str,
        task_id: str,
        project_scope_id: str,
        mode: str = "active",
        evaluated_at: str | None = None,
    ) -> tuple[str, tuple[str, ...], str | None]:
        if mode not in _MATERIALIZATION_MODES:
            raise ValidationError("materialization mode is invalid")
        if mode == "historical":
            if evaluated_at is None:
                raise ValidationError(
                    "historical materialization requires evaluated_at"
                )
            parse_canonical_utc(evaluated_at, field="evaluated_at")
        if source_kind == "governance_rule":
            return self._governance_rule(
                connection,
                source_id=source_id,
                task_id=task_id,
                project_scope_id=project_scope_id,
            )
        if source_kind == "evidence":
            return self._evidence(
                connection,
                source_id=source_id,
                task_id=task_id,
                project_scope_id=project_scope_id,
            )
        if source_kind == "memory_record":
            return self._memory(
                connection,
                source_id=source_id,
                context_kind=context_kind,
                task_id=task_id,
                project_scope_id=project_scope_id,
                mode=mode,
                evaluated_at=evaluated_at,
            )
        raise ValidationError("retrieval source kind is invalid")


class ContextRetrievalService:
    """Create immutable retrieval attempts over exact finalized I3-D context."""

    def __init__(
        self,
        config: DatabaseConfig,
        *,
        ranker: RelevanceRanker | None = None,
        identifier_factory: Callable[[], str] = generate_identifier,
        assembler: ContextAssembler | None = None,
        contamination_inspector: ContaminationInspector | None = None,
    ) -> None:
        if not isinstance(config, DatabaseConfig):
            raise TypeError("config must be a DatabaseConfig")
        self._config = config
        self._kernel = PersistenceKernel(config)
        self._task_memory = SessionTaskMemoryRepository(config)
        self._ranker = ranker or DeterministicFallbackRanker()
        self._identifier_factory = identifier_factory
        self._assembler = assembler or ContextAssembler()
        self._contamination = contamination_inspector or ContaminationInspector()
        self._materializer = _SafeSourceMaterializer()

    @staticmethod
    def _validate_projection(
        request: RetrievalRequest,
        projection: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        try:
            canonical = projection["canonical_json"]
            content_hash = projection["content_hash"]
            integrity_verified = projection["integrity_verified"]
            value = projection["value"]
        except (KeyError, TypeError) as exc:
            raise IntegrityInspectionError(
                "I3-D task-memory projection is malformed"
            ) from exc
        if not isinstance(value, Mapping):
            raise IntegrityInspectionError("I3-D projection value is not an object")
        if canonical_json_text(value) != canonical:
            raise IntegrityInspectionError(
                "I3-D projection canonical reconstruction differs"
            )
        if sha256_canonical_json(value) != content_hash:
            raise IntegrityInspectionError("I3-D projection hash mismatch")
        integrity = value.get("integrity")
        authoritative = value.get("authoritative_i2")
        context = value.get("context")
        if (
            not integrity_verified
            or not isinstance(integrity, Mapping)
            or not integrity.get("valid")
        ):
            raise IntegrityInspectionError(
                "I3-D task-memory projection is integrity-invalid"
            )
        if (
            not integrity.get("authoritative_i2_verified")
            or integrity.get("i2_reconstruction_error") is not None
        ):
            raise IntegrityInspectionError(
                "authoritative I2 reconstruction is not verified"
            )
        if not isinstance(authoritative, Mapping) or not isinstance(
            context,
            Mapping,
        ):
            raise IntegrityInspectionError(
                "task-memory projection lacks authoritative context"
            )
        try:
            task = authoritative["task"]
            session = authoritative["session"]
            finalization = context["finalization"]
            items = context["items"]
            uncertainties = value["uncertainties"]["active"]
        except (KeyError, TypeError) as exc:
            raise IntegrityInspectionError(
                "task-memory projection relationships are malformed"
            ) from exc
        if not isinstance(task, Mapping) or not isinstance(session, Mapping):
            raise IntegrityInspectionError("authoritative task/session is malformed")
        if (
            task.get("task_id") != request.task_id
            or task.get("session_id") != request.session_id
            or task.get("project_scope_id") != request.project_scope_id
        ):
            raise ValidationError(
                "retrieval request does not match authoritative task binding"
            )
        if authoritative.get("task_status") != "active":
            raise ValidationError("retrieval requires an active task")
        if session.get("status") not in {"open", "paused"}:
            raise ValidationError("retrieval requires an open or paused session")
        if session.get("project_scope_id") != request.project_scope_id:
            raise ValidationError(
                "retrieval project does not match the active session project"
            )
        if not isinstance(finalization, Mapping):
            raise ValidationError("retrieval requires finalized task context")
        if (
            finalization.get("finalization_id")
            != request.task_context_finalization_id
            or finalization.get("task_id") != request.task_id
            or finalization.get("session_id") != request.session_id
            or finalization.get("project_scope_id") != request.project_scope_id
        ):
            raise ValidationError(
                "retrieval request does not match the exact context finalization"
            )
        if not isinstance(items, list):
            raise IntegrityInspectionError("finalized context items are malformed")
        if not isinstance(uncertainties, list):
            raise IntegrityInspectionError("active uncertainties are malformed")
        if any(
            not isinstance(item, Mapping) or item.get("impact") == "blocking"
            for item in uncertainties
        ):
            raise ValidationError(
                "retrieval is blocked by unresolved blocking uncertainty"
            )
        if not value.get("context_ready"):
            raise ValidationError("I3-D task-memory projection is not context-ready")

        finalization_value = _canonical_object(
            finalization.get("canonical_json"),
            field="task-context finalization",
        )
        if (
            sha256_canonical_json(finalization_value)
            != finalization.get("content_hash")
        ):
            raise IntegrityInspectionError(
                "task-context finalization hash mismatch"
            )
        ordered = finalization_value.get("ordered_items")
        if not isinstance(ordered, list):
            raise IntegrityInspectionError(
                "task-context finalization order is malformed"
            )
        expected = [
            (entry.get("context_item_id"), entry.get("canonical_hash"))
            for entry in ordered
            if isinstance(entry, Mapping)
        ]
        actual = [
            (item.get("context_item_id"), item.get("canonical_hash"))
            for item in items
            if isinstance(item, Mapping)
        ]
        if (
            len(actual) != len(items)
            or len(expected) != len(ordered)
            or expected != actual
            or finalization.get("item_count") != len(items)
        ):
            raise IntegrityInspectionError(
                "I3-D projection differs from its exact finalized candidate set"
            )
        return value

    @staticmethod
    def _validate_current_boundary(
        connection: sqlite3.Connection,
        request: RetrievalRequest,
    ) -> None:
        binding = connection.execute(
            """
            SELECT task.task_id, task.session_id, task.project_scope_id,
                   task.status AS task_status,
                   session_record.session_status,
                   session_record.active_project_scope,
                   finalization.finalization_id,
                   finalization.session_id AS finalization_session_id,
                   finalization.project_scope_id AS finalization_project_scope_id
            FROM tasks AS task
            JOIN sessions AS session_record
              ON session_record.session_id = task.session_id
            JOIN task_context_finalizations AS finalization
              ON finalization.task_id = task.task_id
            WHERE task.task_id = ?
            """,
            (request.task_id,),
        ).fetchone()
        if binding is None:
            raise NotFoundError("retrieval task or finalization does not exist")
        if (
            binding["session_id"] != request.session_id
            or binding["project_scope_id"] != request.project_scope_id
            or binding["active_project_scope"] != request.project_scope_id
            or binding["finalization_id"]
            != request.task_context_finalization_id
            or binding["finalization_session_id"] != request.session_id
            or binding["finalization_project_scope_id"]
            != request.project_scope_id
        ):
            raise ValidationError(
                "retrieval request violates task, session, project or "
                "finalization binding"
            )
        if binding["task_status"] != "active":
            raise ValidationError("retrieval requires an active task")
        if binding["session_status"] not in {"open", "paused"}:
            raise ValidationError("retrieval requires an open or paused session")

        i2_findings = [
            finding
            for finding in inspect_task_runtime_integrity(connection)
            if finding.task_id == request.task_id
            or (
                finding.task_id is None
                and finding.session_id == request.session_id
            )
            or (finding.task_id is None and finding.session_id is None)
        ]
        if i2_findings:
            raise IntegrityInspectionError(
                "authoritative I2 integrity prevents retrieval"
            )
        from batch87_apprentice.memory.session_task_integrity import (
            SessionTaskIntegrityInspector,
        )

        i3_report = SessionTaskIntegrityInspector._inspect_connection(connection)
        i3_findings = [
            finding
            for finding in i3_report.findings
            if finding.task_id == request.task_id
            or (
                finding.task_id is None
                and finding.session_id == request.session_id
            )
        ]
        if i3_findings:
            raise IntegrityInspectionError(
                "I3-D integrity prevents governed retrieval"
            )

    @staticmethod
    def _ensure_new_request(
        connection: sqlite3.Connection,
        request: RetrievalRequest,
    ) -> None:
        row = connection.execute(
            """
            SELECT content_hash FROM retrieval_requests
            WHERE retrieval_request_id = ?
            """,
            (request.retrieval_request_id,),
        ).fetchone()
        if row is None:
            return
        if row["content_hash"] != request.content_hash:
            raise ConflictError(
                "retrieval request identity conflicts with stored content"
            )
        raise ConflictError("retrieval request identity was already completed")

    def _candidates(
        self,
        connection: sqlite3.Connection,
        *,
        request: RetrievalRequest,
        projection_value: Mapping[str, Any],
        forced_exclusions: frozenset[str],
    ) -> tuple[
        tuple[RetrievalCandidate, ...],
        dict[tuple[str, str], Mapping[str, Any]],
    ]:
        items = projection_value["context"]["items"]
        candidates: list[RetrievalCandidate] = []
        snapshots: dict[tuple[str, str], Mapping[str, Any]] = {}
        seen_sources: set[tuple[str, str]] = set()
        for item in items:
            context_kind = item.get("context_kind")
            target_section = _TARGET_SECTION_BY_CONTEXT_KIND.get(context_kind)
            if target_section is None:
                raise IntegrityInspectionError(
                    "finalized context kind has no deterministic I4-A section"
                )
            source = item.get("source")
            if not isinstance(source, Mapping):
                raise IntegrityInspectionError(
                    "finalized context item has no typed source"
                )
            source_kind = source.get("source_kind")
            if source_kind not in _SOURCE_IDENTIFIER_FIELD:
                raise IntegrityInspectionError(
                    "finalized context source kind is unsupported"
                )
            source_identifier = _source_id(item)
            source_key = (source_kind, source_identifier)
            if source_key in seen_sources:
                raise IntegrityInspectionError(
                    "finalized context contains a duplicate source"
                )
            seen_sources.add(source_key)
            raw = connection.execute(
                """
                SELECT * FROM task_context_items
                WHERE context_item_id = ?
                """,
                (item["context_item_id"],),
            ).fetchone()
            if raw is None:
                raise IntegrityInspectionError(
                    "finalized context item disappeared during retrieval"
                )
            raw_item = dict(raw)
            if (
                raw_item["task_id"] != request.task_id
                or raw_item["session_id"] != request.session_id
                or raw_item["project_scope_id"] != request.project_scope_id
                or raw_item["content_hash"] != item["content_hash"]
                or raw_item["canonical_hash"] != item["canonical_hash"]
            ):
                raise IntegrityInspectionError(
                    "finalized context item changed during retrieval"
                )
            decision = (
                SessionTaskMemoryRepository._eligibility_from_connection(
                    connection,
                    task_id=request.task_id,
                    context_item_id=item["context_item_id"],
                    mode="active",
                    evaluated_at=request.requested_at,
                )
            )
            projected_decision = item.get("eligibility")
            if (
                not isinstance(projected_decision, Mapping)
                or projected_decision.get("decision_hash")
                != decision.decision_hash
                or projected_decision.get("eligible") != decision.eligible
                or tuple(projected_decision.get("reason_codes", ()))
                != decision.reason_codes
            ):
                raise IntegrityInspectionError(
                    "I3-D eligibility changed during retrieval"
                )
            snapshot = SessionTaskMemoryRepository._context_source_snapshot(
                connection,
                raw_item,
            )
            if snapshot is not None:
                snapshots[source_key] = snapshot

            if not decision.eligible:
                materialization_status = "not_attempted"
                materialization_reasons = (
                    ("content_unavailable",)
                    if (
                        source_kind == "evidence"
                        and snapshot is not None
                        and snapshot.get("storage_kind") != "inline_text"
                    )
                    else ()
                )
                materialized_json = None
            elif source_identifier in forced_exclusions:
                materialization_status = "prohibited"
                materialization_reasons = ("recovery_source_excluded",)
                materialized_json = None
            else:
                (
                    materialization_status,
                    materialization_reasons,
                    materialized_json,
                ) = self._materializer.materialize(
                    connection,
                    source_kind=source_kind,
                    source_id=source_identifier,
                    context_kind=context_kind,
                    task_id=request.task_id,
                    project_scope_id=request.project_scope_id,
                )
            candidates.append(
                RetrievalCandidate(
                    context_item_id=item["context_item_id"],
                    context_kind=context_kind,
                    source_kind=source_kind,
                    source_id=source_identifier,
                    source_content_hash=item["content_hash"],
                    required=bool(item["required"]),
                    injection_order=item["injection_order"],
                    target_section=target_section,
                    eligibility_status=(
                        "eligible" if decision.eligible else "ineligible"
                    ),
                    eligibility_reasons=decision.reason_codes,
                    eligibility_decision_hash=decision.decision_hash,
                    materialization_status=materialization_status,
                    materialization_reasons=materialization_reasons,
                    materialized_json=materialized_json,
                )
            )
        if [candidate.injection_order for candidate in candidates] != list(
            range(len(candidates))
        ):
            raise IntegrityInspectionError(
                "finalized context injection order is noncontiguous"
            )
        return tuple(candidates), snapshots

    @staticmethod
    def _source_snapshot_by_identity(
        connection: sqlite3.Connection,
        *,
        source_kind: str,
        source_id: str,
        task_id: str,
        project_scope_id: str,
    ) -> Mapping[str, Any] | None:
        if source_kind == "memory_record":
            row = connection.execute(
                "SELECT * FROM records WHERE record_id = ?",
                (source_id,),
            ).fetchone()
            return None if row is None else dict(row)
        if source_kind == "evidence":
            row = connection.execute(
                """
                SELECT evidence.*,
                       CASE WHEN controlled.record_id IS NULL
                            THEN 0 ELSE 1 END AS controlled_resilience
                FROM evidence_items AS evidence
                LEFT JOIN controlled_resilience_evidence AS controlled
                  ON controlled.raw_prompt_evidence_id = evidence.evidence_id
                  OR controlled.raw_output_evidence_id = evidence.evidence_id
                WHERE evidence.evidence_id = ?
                """,
                (source_id,),
            ).fetchone()
            if row is None:
                return None
            snapshot = dict(row)
            snapshot["task_bound"] = bool(
                _exact_evidence_relationships(
                    connection,
                    evidence_id=source_id,
                    task_id=task_id,
                    project_scope_id=project_scope_id,
                )
            )
            return snapshot
        if source_kind == "governance_rule":
            row = connection.execute(
                """
                SELECT rule.*,
                       CASE WHEN EXISTS (
                           SELECT 1
                           FROM governance_decision_rules AS relationship
                           JOIN governance_decisions AS decision_record
                             ON decision_record.governance_decision_id =
                                relationship.governance_decision_id
                           WHERE relationship.governance_rule_id =
                                 rule.governance_rule_id
                             AND decision_record.task_id = ?
                             AND decision_record.project_scope_id = ?
                       ) THEN 1 ELSE 0 END AS task_bound
                FROM governance_rules AS rule
                WHERE rule.governance_rule_id = ?
                """,
                (task_id, project_scope_id, source_id),
            ).fetchone()
            return None if row is None else dict(row)
        return None

    def _rank(
        self,
        request: RetrievalRequest,
        candidates: tuple[RetrievalCandidate, ...],
    ) -> tuple[RankedCandidate, ...]:
        if getattr(self._ranker, "strategy", None) != request.ranking_strategy:
            raise ValidationError(
                "retrieval request ranking strategy does not match ranker"
            )
        includable = tuple(candidate for candidate in candidates if candidate.includable)
        ranked = self._ranker.rank(request, includable)
        if not isinstance(ranked, tuple):
            raise ValidationError("ranker must return an immutable tuple")
        if [entry.final_rank for entry in ranked] != list(range(len(ranked))):
            raise ValidationError("ranker returned noncontiguous final ranks")
        expected = {candidate.context_item_id: candidate for candidate in includable}
        actual: dict[str, RankedCandidate] = {}
        for entry in ranked:
            if not isinstance(entry, RankedCandidate):
                raise ValidationError("ranker returned an invalid ranked entry")
            context_item_id = entry.candidate.context_item_id
            if (
                context_item_id in actual
                or expected.get(context_item_id) != entry.candidate
                or not entry.explanation
            ):
                raise ValidationError(
                    "ranker changed, duplicated or omitted an eligible candidate"
                )
            actual[context_item_id] = entry
        if set(actual) != set(expected):
            raise ValidationError(
                "ranker changed, duplicated or omitted an eligible candidate"
            )
        return ranked

    @staticmethod
    def _manifest_entries(
        candidates: tuple[RetrievalCandidate, ...],
        ranked: tuple[RankedCandidate, ...],
        *,
        allocator: _IdentifierAllocator,
    ) -> tuple[RetrievalManifestEntry, ...]:
        ranked_by_item = {
            entry.candidate.context_item_id: entry for entry in ranked
        }
        entries: list[RetrievalManifestEntry] = []
        for candidate in candidates:
            ranked_entry = ranked_by_item.get(candidate.context_item_id)
            if ranked_entry is not None:
                disposition = "included"
                disposition_reason = "eligible_materialized_and_ranked"
                components = ranked_entry.components
                explanation = ranked_entry.explanation
                final_rank = ranked_entry.final_rank
            else:
                disposition = "excluded"
                components = None
                explanation = ()
                final_rank = None
                reasons = (
                    candidate.eligibility_reasons
                    + candidate.materialization_reasons
                )
                disposition_reason = "excluded:" + ",".join(
                    reasons or ("not_includable",)
                )
            entries.append(
                RetrievalManifestEntry(
                    entry_id=allocator.new(),
                    context_item_id=candidate.context_item_id,
                    source_kind=candidate.source_kind,
                    source_id=candidate.source_id,
                    source_content_hash=candidate.source_content_hash,
                    required=candidate.required,
                    target_section=candidate.target_section,
                    eligibility_status=candidate.eligibility_status,
                    eligibility_reasons=candidate.eligibility_reasons,
                    eligibility_decision_hash=candidate.eligibility_decision_hash,
                    materialization_status=candidate.materialization_status,
                    materialization_reasons=candidate.materialization_reasons,
                    materialized_content_hash=(
                        candidate.materialized_content_hash
                        if disposition == "included"
                        else None
                    ),
                    rank_components=components,
                    rank_explanation=explanation,
                    final_rank=final_rank,
                    disposition=disposition,
                    disposition_reason=disposition_reason,
                )
            )
        return tuple(entries)

    def _independent_materializations(
        self,
        connection: sqlite3.Connection,
        *,
        request: RetrievalRequest,
        candidates: tuple[RetrievalCandidate, ...],
        entries: tuple[RetrievalManifestEntry, ...],
        mode: str,
        evaluated_at: str,
    ) -> dict[str, str]:
        """Re-read and independently materialize every included source."""

        candidates_by_item = {
            candidate.context_item_id: candidate for candidate in candidates
        }
        verified: dict[str, str] = {}
        for entry in entries:
            if entry.disposition != "included":
                continue
            candidate = candidates_by_item[entry.context_item_id]
            status, reasons, materialized_json = self._materializer.materialize(
                connection,
                source_kind=entry.source_kind,
                source_id=entry.source_id,
                context_kind=candidate.context_kind,
                task_id=request.task_id,
                project_scope_id=request.project_scope_id,
                mode=mode,
                evaluated_at=evaluated_at,
            )
            if (
                status == "materialized"
                and not reasons
                and materialized_json is not None
            ):
                verified[entry.entry_id] = materialized_json
        return verified

    @staticmethod
    def _authoritative_binding_specs(
        *,
        task_memory_projection_json: str,
        sections_json: str,
        ordered_entries: tuple[OrderedContextEntry, ...],
        authoritative_task_hash: str,
        authoritative_authority_hash: str,
    ) -> tuple[tuple[str, str, str, str], ...]:
        """Derive authoritative truth without consulting the injected assembler."""

        projection = _canonical_object(
            task_memory_projection_json,
            field="attempt-time task-memory projection",
        )
        authoritative_i2 = projection.get("authoritative_i2")
        uncertainties = projection.get("uncertainties")
        if not isinstance(authoritative_i2, Mapping) or not isinstance(
            uncertainties,
            Mapping,
        ):
            raise IntegrityInspectionError(
                "attempt-time projection lacks authoritative section inputs"
            )
        active = uncertainties.get("active")
        if not isinstance(active, list) or any(
            not isinstance(uncertainty, Mapping)
            for uncertainty in active
        ):
            raise IntegrityInspectionError(
                "attempt-time active uncertainties are malformed"
            )
        expected_task = build_authoritative_task_section(
            authoritative_i2,
            tuple(active),
        )
        expected_authority = build_authoritative_authority_section(
            authoritative_i2
        )
        task = authoritative_i2.get("task")
        decision = authoritative_i2.get("decision")
        if not isinstance(task, Mapping) or not isinstance(decision, Mapping):
            raise IntegrityInspectionError(
                "attempt-time authoritative identities are malformed"
            )
        return _authoritative_binding_mismatch_specs(
            sections_json=sections_json,
            ordered_entries=ordered_entries,
            authoritative_task_hash=authoritative_task_hash,
            authoritative_authority_hash=authoritative_authority_hash,
            expected_task=expected_task,
            expected_authority=expected_authority,
            expected_task_id=task["task_id"],
            expected_authority_id=decision["governance_decision_id"],
        )

    @staticmethod
    def _authoritative_contamination_findings(
        *,
        task_memory_projection_json: str,
        sections_json: str,
        ordered_entries: tuple[OrderedContextEntry, ...],
        authoritative_task_hash: str,
        authoritative_authority_hash: str,
        identifier_factory: Callable[[], str],
    ) -> tuple[ContaminationFinding, ...]:
        return tuple(
            ContaminationFinding(
                finding_id=identifier_factory(),
                reason_code=reason_code,
                source_kind=source_kind,
                source_id=source_id,
                detail=detail,
            )
            for reason_code, source_kind, source_id, detail in (
                ContextRetrievalService._authoritative_binding_specs(
                    task_memory_projection_json=task_memory_projection_json,
                    sections_json=sections_json,
                    ordered_entries=ordered_entries,
                    authoritative_task_hash=authoritative_task_hash,
                    authoritative_authority_hash=(
                        authoritative_authority_hash
                    ),
                )
            )
        )

    @staticmethod
    def _authoritative_readiness_findings(
        manifest: RetrievalManifest,
        package: StructuredContextPackage,
    ) -> tuple[ContextReadinessFinding, ...]:
        return tuple(
            ContextReadinessFinding(
                reason_code=reason_code,
                detail=detail,
                source_kind=source_kind,
                source_id=source_id,
            )
            for reason_code, source_kind, source_id, detail in (
                ContextRetrievalService._authoritative_binding_specs(
                    task_memory_projection_json=(
                        manifest.task_memory_projection_json
                    ),
                    sections_json=package.sections_json,
                    ordered_entries=package.ordered_entries,
                    authoritative_task_hash=package.authoritative_task_hash,
                    authoritative_authority_hash=(
                        package.authoritative_authority_hash
                    ),
                )
            )
        )

    @staticmethod
    def _persist_request(
        connection: sqlite3.Connection,
        request: RetrievalRequest,
    ) -> None:
        connection.execute(
            """
            INSERT INTO retrieval_requests (
                retrieval_request_id, contract_version, task_id, session_id,
                project_scope_id, task_context_finalization_id, purpose,
                requested_sections_json, requested_at,
                requested_by_principal, ranking_strategy, provenance_json,
                canonical_json, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.retrieval_request_id,
                request.contract_version,
                request.task_id,
                request.session_id,
                request.project_scope_id,
                request.task_context_finalization_id,
                request.purpose,
                canonical_json_text(list(request.requested_sections)),
                request.requested_at,
                request.requested_by_principal,
                request.ranking_strategy,
                request.provenance_json,
                request.canonical_json,
                request.content_hash,
            ),
        )

    @staticmethod
    def _persist_manifest(
        connection: sqlite3.Connection,
        manifest: RetrievalManifest,
    ) -> None:
        connection.execute(
            """
            INSERT INTO retrieval_manifests (
                retrieval_manifest_id, retrieval_request_id, task_id,
                session_id, project_scope_id, task_context_finalization_id,
                request_hash, task_memory_projection_hash,
                task_memory_projection_json, finalization_hash,
                ranking_strategy, status, created_at, canonical_json,
                content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                manifest.retrieval_manifest_id,
                manifest.retrieval_request_id,
                manifest.task_id,
                manifest.session_id,
                manifest.project_scope_id,
                manifest.task_context_finalization_id,
                manifest.request_hash,
                manifest.task_memory_projection_hash,
                manifest.task_memory_projection_json,
                manifest.finalization_hash,
                manifest.ranking_strategy,
                manifest.status,
                manifest.created_at,
                manifest.canonical_json,
                manifest.content_hash,
            ),
        )
        for entry in manifest.entries:
            memory_id, evidence_id, rule_id = _source_columns(
                entry.source_kind,
                entry.source_id,
            )
            connection.execute(
                """
                INSERT INTO retrieval_manifest_entries (
                    entry_id, retrieval_manifest_id, context_item_id,
                    source_kind, source_id, source_memory_record_id,
                    source_evidence_id, source_governance_rule_id,
                    source_content_hash, required, target_section,
                    eligibility_status, eligibility_reasons_json,
                    eligibility_decision_hash, materialization_status,
                    materialization_reasons_json, materialized_content_hash,
                    rank_components_json, rank_explanation_json, final_rank,
                    disposition, disposition_reason, canonical_json, content_hash
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    entry.entry_id,
                    manifest.retrieval_manifest_id,
                    entry.context_item_id,
                    entry.source_kind,
                    entry.source_id,
                    memory_id,
                    evidence_id,
                    rule_id,
                    entry.source_content_hash,
                    int(entry.required),
                    entry.target_section,
                    entry.eligibility_status,
                    canonical_json_text(list(entry.eligibility_reasons)),
                    entry.eligibility_decision_hash,
                    entry.materialization_status,
                    canonical_json_text(list(entry.materialization_reasons)),
                    entry.materialized_content_hash,
                    (
                        None
                        if entry.rank_components is None
                        else canonical_json_text(
                            entry.rank_components.canonical_value()
                        )
                    ),
                    canonical_json_text(list(entry.rank_explanation)),
                    entry.final_rank,
                    entry.disposition,
                    entry.disposition_reason,
                    entry.canonical_json,
                    entry.content_hash,
                ),
            )

    @staticmethod
    def _persist_package(
        connection: sqlite3.Connection,
        package: StructuredContextPackage,
    ) -> None:
        connection.execute(
            """
            INSERT INTO context_packages (
                context_package_id, contract_version, retrieval_request_id,
                retrieval_manifest_id, retrieval_manifest_hash, task_id,
                session_id, project_scope_id, task_context_finalization_id,
                task_memory_projection_hash, status, contamination_status,
                created_at, authoritative_task_hash,
                authoritative_authority_hash, sections_json,
                recovery_of_context_package_id, recovery_relationship_hash,
                canonical_json, content_hash
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                package.context_package_id,
                package.contract_version,
                package.retrieval_request_id,
                package.retrieval_manifest_id,
                package.retrieval_manifest_hash,
                package.task_id,
                package.session_id,
                package.project_scope_id,
                package.task_context_finalization_id,
                package.task_memory_projection_hash,
                package.status,
                package.contamination_status,
                package.created_at,
                package.authoritative_task_hash,
                package.authoritative_authority_hash,
                package.sections_json,
                package.recovery_of_context_package_id,
                package.recovery_relationship_hash,
                package.canonical_json,
                package.content_hash,
            ),
        )
        for entry in package.ordered_entries:
            connection.execute(
                """
                INSERT INTO ordered_context_manifest_entries (
                    ordered_entry_id, context_package_id, section,
                    section_order, entry_order, source_kind, source_id,
                    source_content_hash, retrieval_manifest_entry_id,
                    entry_canonical_json, entry_canonical_hash,
                    canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.ordered_entry_id,
                    package.context_package_id,
                    entry.section,
                    entry.section_order,
                    entry.entry_order,
                    entry.source_kind,
                    entry.source_id,
                    entry.source_content_hash,
                    entry.retrieval_manifest_entry_id,
                    entry.entry_json,
                    entry.entry_canonical_hash,
                    entry.canonical_json,
                    entry.content_hash,
                ),
            )
        for finding_order, finding in enumerate(
            package.contamination_findings
        ):
            connection.execute(
                """
                INSERT INTO context_contamination_findings (
                    finding_id, context_package_id, finding_order,
                    reason_code, source_kind, source_id, detail,
                    canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.finding_id,
                    package.context_package_id,
                    finding_order,
                    finding.reason_code,
                    finding.source_kind,
                    finding.source_id,
                    finding.detail,
                    finding.canonical_json,
                    finding.content_hash,
                ),
            )

    @staticmethod
    def _persist_recovery(
        connection: sqlite3.Connection,
        relationship: RecoveryRelationship,
    ) -> None:
        connection.execute(
            """
            INSERT INTO context_recovery_relationships (
                recovery_context_package_id, rejected_context_package_id,
                recovery_reason, excluded_source_ids_json,
                preserved_findings_json, created_at, canonical_json,
                content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relationship.recovery_context_package_id,
                relationship.rejected_context_package_id,
                relationship.recovery_reason,
                canonical_json_text(list(relationship.excluded_source_ids)),
                relationship.preserved_findings_json,
                relationship.created_at,
                relationship.canonical_json,
                relationship.content_hash,
            ),
        )

    def _assemble_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        request: RetrievalRequest,
        projection: Mapping[str, Any],
        recovery_of_context_package_id: str | None,
        forced_exclusions: frozenset[str],
        recovery_reason: str | None,
        preserved_findings_json: str | None,
    ) -> RetrievalAssemblyResult:
        self._ensure_new_request(connection, request)
        self._validate_current_boundary(connection, request)
        projection_value = self._validate_projection(request, projection)
        allocator = _IdentifierAllocator(
            self._identifier_factory,
            reserved=tuple(
                identifier
                for identifier in (
                    request.retrieval_request_id,
                    recovery_of_context_package_id,
                )
                if identifier is not None
            ),
        )
        candidates, snapshots = self._candidates(
            connection,
            request=request,
            projection_value=projection_value,
            forced_exclusions=forced_exclusions,
        )
        ranked = self._rank(request, candidates)
        manifest_id = allocator.new()
        entries = self._manifest_entries(
            candidates,
            ranked,
            allocator=allocator,
        )
        entries_by_item = {entry.context_item_id: entry for entry in entries}
        independent_materializations = self._independent_materializations(
            connection,
            request=request,
            candidates=candidates,
            entries=entries,
            mode="active",
            evaluated_at=request.requested_at,
        )
        active_uncertainties = tuple(
            projection_value["uncertainties"]["active"]
        )
        (
            sections_json,
            ordered_entries,
            authoritative_task_hash,
            authoritative_authority_hash,
        ) = self._assembler.assemble(
            authoritative_i2=projection_value["authoritative_i2"],
            active_uncertainties=active_uncertainties,
            ranked_candidates=ranked,
            manifest_entries=entries_by_item,
            identifier_factory=allocator.new,
        )
        if not isinstance(ordered_entries, tuple) or any(
            not isinstance(entry, OrderedContextEntry)
            for entry in ordered_entries
        ):
            raise ValidationError(
                "context assembler returned invalid ordered entries"
            )
        authoritative_findings = self._authoritative_contamination_findings(
            task_memory_projection_json=projection["canonical_json"],
            sections_json=sections_json,
            ordered_entries=ordered_entries,
            authoritative_task_hash=authoritative_task_hash,
            authoritative_authority_hash=authoritative_authority_hash,
            identifier_factory=allocator.new,
        )
        for ordered_entry in ordered_entries:
            source_key = (
                ordered_entry.source_kind,
                ordered_entry.source_id,
            )
            if (
                ordered_entry.source_kind.startswith("authoritative_i2_")
                or source_key in snapshots
            ):
                continue
            snapshot = self._source_snapshot_by_identity(
                connection,
                source_kind=ordered_entry.source_kind,
                source_id=ordered_entry.source_id,
                task_id=request.task_id,
                project_scope_id=request.project_scope_id,
            )
            if snapshot is not None:
                snapshots[source_key] = snapshot
        findings = self._contamination.inspect(
            sections_json=sections_json,
            ordered_entries=ordered_entries,
            authoritative_task_hash=authoritative_task_hash,
            authoritative_authority_hash=authoritative_authority_hash,
            task_memory_projection_json=projection["canonical_json"],
            manifest_entries=entries,
            independent_materializations=independent_materializations,
            source_snapshots=snapshots,
            task_id=request.task_id,
            project_scope_id=request.project_scope_id,
            identifier_factory=allocator.new,
        )
        merged_findings: dict[
            tuple[str, str | None, str | None, str],
            ContaminationFinding,
        ] = {}
        for finding in (*authoritative_findings, *findings):
            key = (
                finding.reason_code,
                finding.source_kind,
                finding.source_id,
                finding.detail,
            )
            merged_findings.setdefault(key, finding)
        findings = tuple(
            sorted(
                merged_findings.values(),
                key=lambda finding: (
                    finding.reason_code,
                    finding.source_kind or "",
                    finding.source_id or "",
                    finding.detail,
                ),
            )
        )
        if not isinstance(findings, tuple) or any(
            not isinstance(finding, ContaminationFinding)
            for finding in findings
        ):
            raise ValidationError(
                "contamination inspector returned invalid findings"
            )
        if len({finding.finding_id for finding in findings}) != len(findings):
            raise ValidationError(
                "contamination inspector returned duplicate findings"
            )
        required_excluded = any(
            entry.required and entry.disposition == "excluded"
            for entry in entries
        )
        if findings:
            context_status = "rejected_contamination"
            contamination_status = "contaminated"
            rejection_reasons = tuple(
                sorted({finding.reason_code for finding in findings})
            )
        elif required_excluded:
            context_status = "rejected_required_source"
            contamination_status = "clean"
            rejection_reasons = (
                "required_context_excluded",
            )
        else:
            context_status = "accepted"
            contamination_status = "clean"
            rejection_reasons = ()
        manifest_status = (
            "accepted" if context_status == "accepted" else "rejected"
        )
        finalization = projection_value["context"]["finalization"]
        manifest = RetrievalManifest(
            retrieval_manifest_id=manifest_id,
            retrieval_request_id=request.retrieval_request_id,
            task_id=request.task_id,
            session_id=request.session_id,
            project_scope_id=request.project_scope_id,
            task_context_finalization_id=request.task_context_finalization_id,
            request_hash=request.content_hash,
            task_memory_projection_hash=projection["content_hash"],
            task_memory_projection_json=projection["canonical_json"],
            finalization_hash=finalization["content_hash"],
            ranking_strategy=request.ranking_strategy,
            status=manifest_status,
            created_at=request.requested_at,
            entries=entries,
        )
        package_id = allocator.new()
        relationship: RecoveryRelationship | None = None
        if recovery_of_context_package_id is not None:
            if recovery_reason is None or preserved_findings_json is None:
                raise ValidationError(
                    "recovery metadata is incomplete"
                )
            relationship = RecoveryRelationship(
                recovery_context_package_id=package_id,
                rejected_context_package_id=recovery_of_context_package_id,
                recovery_reason=recovery_reason,
                excluded_source_ids=tuple(sorted(forced_exclusions)),
                preserved_findings_json=preserved_findings_json,
                created_at=request.requested_at,
            )
        package = StructuredContextPackage(
            context_package_id=package_id,
            contract_version=STRUCTURED_CONTEXT_VERSION,
            retrieval_request_id=request.retrieval_request_id,
            retrieval_manifest_id=manifest.retrieval_manifest_id,
            retrieval_manifest_hash=manifest.content_hash,
            task_id=request.task_id,
            session_id=request.session_id,
            project_scope_id=request.project_scope_id,
            task_context_finalization_id=request.task_context_finalization_id,
            task_memory_projection_hash=projection["content_hash"],
            status=context_status,
            contamination_status=contamination_status,
            created_at=request.requested_at,
            authoritative_task_hash=authoritative_task_hash,
            authoritative_authority_hash=authoritative_authority_hash,
            sections_json=sections_json,
            ordered_entries=ordered_entries,
            contamination_findings=findings,
            recovery_of_context_package_id=recovery_of_context_package_id,
            recovery_relationship_hash=(
                None if relationship is None else relationship.content_hash
            ),
        )
        self._persist_request(connection, request)
        self._persist_manifest(connection, manifest)
        self._persist_package(connection, package)
        if relationship is not None:
            self._persist_recovery(connection, relationship)
        return RetrievalAssemblyResult(
            retrieval_request=request,
            retrieval_manifest=manifest,
            context_package=package,
            accepted=context_status == "accepted",
            bridge_context_ready=package.bridge_context_ready,
            rejection_reasons=rejection_reasons,
        )

    def assemble(
        self,
        request: RetrievalRequest | Mapping[str, Any],
    ) -> RetrievalAssemblyResult:
        """Assemble and persist one exact governed I4-A retrieval attempt."""

        if not isinstance(request, RetrievalRequest):
            request = RetrievalRequest.from_mapping(request)
        projection = self._task_memory.reconstruct_task_memory(
            request.task_id,
            mode="active",
            evaluated_at=request.requested_at,
        )
        self._validate_projection(request, projection)
        return self._kernel.write(
            lambda connection: self._assemble_in_transaction(
                connection,
                request=request,
                projection=projection,
                recovery_of_context_package_id=None,
                forced_exclusions=frozenset(),
                recovery_reason=None,
                preserved_findings_json=None,
            )
        )

    def _recovery_inputs(
        self,
        rejected_context_package_id: str,
    ) -> tuple[StructuredContextPackage, frozenset[str], str]:
        validate_identifier(
            rejected_context_package_id,
            field="rejected_context_package_id",
        )

        def operation(
            connection: sqlite3.Connection,
        ) -> tuple[StructuredContextPackage, frozenset[str], str]:
            package = self._load_package(connection, rejected_context_package_id)
            manifest = self._load_manifest(
                connection,
                package.retrieval_manifest_id,
            )
            request = self._load_request(
                connection,
                package.retrieval_request_id,
            )
            self._verify_manifest_relationships(
                connection,
                request,
                manifest,
            )
            self._verify_package_relationships(
                connection,
                request,
                manifest,
                package,
            )
            self._verify_historical_projection(
                connection,
                request=request,
                manifest=manifest,
            )
            authoritative_findings = self._authoritative_readiness_findings(
                manifest,
                package,
            )
            if (
                authoritative_findings
                and not self._preserved_rejection_covers(
                    package,
                    authoritative_findings,
                )
            ):
                raise IntegrityInspectionError(
                    "rejected authoritative section binding cannot be "
                    "reverified for recovery"
                )
            if package.status != "rejected_contamination":
                raise ValidationError(
                    "recovery requires a contamination-rejected package"
                )
            excluded = {
                finding.source_id
                for finding in package.contamination_findings
                if finding.source_id is not None
            }
            excluded = set(
                ContextRetrievalService._expand_controlled_recovery_exclusions(
                    connection,
                    frozenset(excluded),
                )
            )
            if not excluded:
                raise ValidationError(
                    "rejected context has no exact source identity to recover"
                )
            preserved = canonical_json_text(
                [
                    finding.canonical_value()
                    for finding in package.contamination_findings
                ]
            )
            return package, frozenset(excluded), preserved

        return self._kernel.read(operation)

    @staticmethod
    def _expand_controlled_recovery_exclusions(
        connection: sqlite3.Connection,
        source_ids: frozenset[str],
    ) -> frozenset[str]:
        """Expand any controlled bundle member to every restricted sibling."""

        excluded = set(source_ids)
        pending = list(sorted(source_ids))
        inspected: set[str] = set()
        while pending:
            source_id = pending.pop(0)
            if source_id in inspected:
                continue
            inspected.add(source_id)
            for row in connection.execute(
                """
                SELECT record_id, raw_prompt_evidence_id,
                       raw_output_evidence_id, recovery_record_id
                FROM controlled_resilience_evidence
                WHERE record_id = ?
                   OR raw_prompt_evidence_id = ?
                   OR raw_output_evidence_id = ?
                   OR recovery_record_id = ?
                ORDER BY record_id
                """,
                (source_id, source_id, source_id, source_id),
            ):
                related = {
                    row["record_id"],
                    row["raw_prompt_evidence_id"],
                    row["raw_output_evidence_id"],
                    row["recovery_record_id"],
                }
                for related_id in sorted(
                    identifier for identifier in related if identifier is not None
                ):
                    if related_id not in excluded:
                        excluded.add(related_id)
                        pending.append(related_id)
        return frozenset(excluded)

    def recover(
        self,
        rejected_context_package_id: str,
        recovery_request: RetrievalRequest | Mapping[str, Any],
        *,
        recovery_reason: str = "exclude_exact_contaminated_sources",
    ) -> RetrievalAssemblyResult:
        """Create a new immutable attempt excluding exact contaminated sources."""

        if not isinstance(recovery_request, RetrievalRequest):
            recovery_request = RetrievalRequest.from_mapping(recovery_request)
        rejected, exclusions, preserved = self._recovery_inputs(
            rejected_context_package_id
        )
        if (
            recovery_request.task_id != rejected.task_id
            or recovery_request.session_id != rejected.session_id
            or recovery_request.project_scope_id != rejected.project_scope_id
            or recovery_request.task_context_finalization_id
            != rejected.task_context_finalization_id
        ):
            raise ValidationError(
                "recovery request differs from rejected task context"
            )
        projection = self._task_memory.reconstruct_task_memory(
            recovery_request.task_id,
            mode="active",
            evaluated_at=recovery_request.requested_at,
        )
        self._validate_projection(recovery_request, projection)
        return self._kernel.write(
            lambda connection: self._assemble_in_transaction(
                connection,
                request=recovery_request,
                projection=projection,
                recovery_of_context_package_id=rejected_context_package_id,
                forced_exclusions=exclusions,
                recovery_reason=recovery_reason,
                preserved_findings_json=preserved,
            )
        )

    @staticmethod
    def _load_request(
        connection: sqlite3.Connection,
        retrieval_request_id: str,
    ) -> RetrievalRequest:
        row = connection.execute(
            """
            SELECT * FROM retrieval_requests
            WHERE retrieval_request_id = ?
            """,
            (retrieval_request_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(
                f"retrieval request not found: {retrieval_request_id}"
            )
        sections = _canonical_array(
            row["requested_sections_json"],
            field="requested_sections_json",
        )
        provenance = _canonical_object(
            row["provenance_json"],
            field="retrieval provenance",
        )
        request = RetrievalRequest(
            retrieval_request_id=row["retrieval_request_id"],
            contract_version=row["contract_version"],
            task_id=row["task_id"],
            session_id=row["session_id"],
            project_scope_id=row["project_scope_id"],
            task_context_finalization_id=row[
                "task_context_finalization_id"
            ],
            purpose=row["purpose"],
            requested_sections=tuple(sections),
            requested_at=row["requested_at"],
            requested_by_principal=row["requested_by_principal"],
            ranking_strategy=row["ranking_strategy"],
            provenance_json=canonical_json_text(provenance),
        )
        if (
            row["canonical_json"] != request.canonical_json
            or row["content_hash"] != request.content_hash
        ):
            raise IntegrityInspectionError(
                "retrieval request canonical content or hash mismatch"
            )
        return request

    @staticmethod
    def _load_manifest(
        connection: sqlite3.Connection,
        retrieval_manifest_id: str,
    ) -> RetrievalManifest:
        row = connection.execute(
            """
            SELECT * FROM retrieval_manifests
            WHERE retrieval_manifest_id = ?
            """,
            (retrieval_manifest_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(
                f"retrieval manifest not found: {retrieval_manifest_id}"
            )
        entry_rows = connection.execute(
            """
            SELECT entry.*
            FROM retrieval_manifest_entries AS entry
            JOIN task_context_items AS item
              ON item.context_item_id = entry.context_item_id
            WHERE entry.retrieval_manifest_id = ?
            ORDER BY item.injection_order, entry.entry_id
            """,
            (retrieval_manifest_id,),
        )
        entries: list[RetrievalManifestEntry] = []
        for entry_row in entry_rows:
            components_value = (
                None
                if entry_row["rank_components_json"] is None
                else _canonical_object(
                    entry_row["rank_components_json"],
                    field="rank components",
                )
            )
            components = (
                None
                if components_value is None
                else RankComponents(**components_value)
            )
            entry = RetrievalManifestEntry(
                entry_id=entry_row["entry_id"],
                context_item_id=entry_row["context_item_id"],
                source_kind=entry_row["source_kind"],
                source_id=entry_row["source_id"],
                source_content_hash=entry_row["source_content_hash"],
                required=bool(entry_row["required"]),
                target_section=entry_row["target_section"],
                eligibility_status=entry_row["eligibility_status"],
                eligibility_reasons=tuple(
                    _canonical_array(
                        entry_row["eligibility_reasons_json"],
                        field="eligibility reasons",
                    )
                ),
                eligibility_decision_hash=entry_row[
                    "eligibility_decision_hash"
                ],
                materialization_status=entry_row[
                    "materialization_status"
                ],
                materialization_reasons=tuple(
                    _canonical_array(
                        entry_row["materialization_reasons_json"],
                        field="materialization reasons",
                    )
                ),
                materialized_content_hash=entry_row[
                    "materialized_content_hash"
                ],
                rank_components=components,
                rank_explanation=tuple(
                    _canonical_array(
                        entry_row["rank_explanation_json"],
                        field="rank explanation",
                    )
                ),
                final_rank=entry_row["final_rank"],
                disposition=entry_row["disposition"],
                disposition_reason=entry_row["disposition_reason"],
            )
            if (
                entry_row["canonical_json"] != entry.canonical_json
                or entry_row["content_hash"] != entry.content_hash
            ):
                raise IntegrityInspectionError(
                    "retrieval manifest entry canonical content or hash mismatch"
                )
            entries.append(entry)
        manifest = RetrievalManifest(
            retrieval_manifest_id=row["retrieval_manifest_id"],
            retrieval_request_id=row["retrieval_request_id"],
            task_id=row["task_id"],
            session_id=row["session_id"],
            project_scope_id=row["project_scope_id"],
            task_context_finalization_id=row[
                "task_context_finalization_id"
            ],
            request_hash=row["request_hash"],
            task_memory_projection_hash=row["task_memory_projection_hash"],
            task_memory_projection_json=row["task_memory_projection_json"],
            finalization_hash=row["finalization_hash"],
            ranking_strategy=row["ranking_strategy"],
            status=row["status"],
            created_at=row["created_at"],
            entries=tuple(entries),
        )
        if (
            row["canonical_json"] != manifest.canonical_json
            or row["content_hash"] != manifest.content_hash
        ):
            raise IntegrityInspectionError(
                "retrieval manifest canonical content or hash mismatch"
            )
        return manifest

    @staticmethod
    def _load_package(
        connection: sqlite3.Connection,
        context_package_id: str,
    ) -> StructuredContextPackage:
        row = connection.execute(
            """
            SELECT * FROM context_packages
            WHERE context_package_id = ?
            """,
            (context_package_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(
                f"context package not found: {context_package_id}"
            )
        ordered: list[OrderedContextEntry] = []
        for entry_row in connection.execute(
            """
            SELECT * FROM ordered_context_manifest_entries
            WHERE context_package_id = ?
            ORDER BY section_order, entry_order
            """,
            (context_package_id,),
        ):
            entry = OrderedContextEntry(
                ordered_entry_id=entry_row["ordered_entry_id"],
                section=entry_row["section"],
                section_order=entry_row["section_order"],
                entry_order=entry_row["entry_order"],
                source_kind=entry_row["source_kind"],
                source_id=entry_row["source_id"],
                source_content_hash=entry_row["source_content_hash"],
                retrieval_manifest_entry_id=entry_row[
                    "retrieval_manifest_entry_id"
                ],
                entry_json=entry_row["entry_canonical_json"],
            )
            if (
                entry_row["entry_canonical_hash"]
                != entry.entry_canonical_hash
                or entry_row["canonical_json"] != entry.canonical_json
                or entry_row["content_hash"] != entry.content_hash
            ):
                raise IntegrityInspectionError(
                    "ordered context entry canonical content or hash mismatch"
                )
            ordered.append(entry)
        findings: list[ContaminationFinding] = []
        for finding_row in connection.execute(
            """
            SELECT * FROM context_contamination_findings
            WHERE context_package_id = ?
            ORDER BY finding_order
            """,
            (context_package_id,),
        ):
            finding = ContaminationFinding(
                finding_id=finding_row["finding_id"],
                reason_code=finding_row["reason_code"],
                source_kind=finding_row["source_kind"],
                source_id=finding_row["source_id"],
                detail=finding_row["detail"],
            )
            if (
                finding_row["canonical_json"] != finding.canonical_json
                or finding_row["content_hash"] != finding.content_hash
            ):
                raise IntegrityInspectionError(
                    "contamination finding canonical content or hash mismatch"
                )
            findings.append(finding)
        package = StructuredContextPackage(
            context_package_id=row["context_package_id"],
            contract_version=row["contract_version"],
            retrieval_request_id=row["retrieval_request_id"],
            retrieval_manifest_id=row["retrieval_manifest_id"],
            retrieval_manifest_hash=row["retrieval_manifest_hash"],
            task_id=row["task_id"],
            session_id=row["session_id"],
            project_scope_id=row["project_scope_id"],
            task_context_finalization_id=row[
                "task_context_finalization_id"
            ],
            task_memory_projection_hash=row["task_memory_projection_hash"],
            status=row["status"],
            contamination_status=row["contamination_status"],
            created_at=row["created_at"],
            authoritative_task_hash=row["authoritative_task_hash"],
            authoritative_authority_hash=row[
                "authoritative_authority_hash"
            ],
            sections_json=row["sections_json"],
            ordered_entries=tuple(ordered),
            contamination_findings=tuple(findings),
            recovery_of_context_package_id=row[
                "recovery_of_context_package_id"
            ],
            recovery_relationship_hash=row["recovery_relationship_hash"],
        )
        if (
            row["canonical_json"] != package.canonical_json
            or row["content_hash"] != package.content_hash
        ):
            raise IntegrityInspectionError(
                "context package canonical content or hash mismatch"
            )
        return package

    @staticmethod
    def _verify_manifest_relationships(
        connection: sqlite3.Connection,
        request: RetrievalRequest,
        manifest: RetrievalManifest,
    ) -> None:
        finalization = connection.execute(
            """
            SELECT * FROM task_context_finalizations
            WHERE finalization_id = ?
            """,
            (manifest.task_context_finalization_id,),
        ).fetchone()
        if finalization is None:
            raise IntegrityInspectionError(
                "retrieval manifest finalization parent is missing"
            )
        if (
            manifest.retrieval_request_id != request.retrieval_request_id
            or manifest.request_hash != request.content_hash
            or manifest.task_id != request.task_id
            or manifest.session_id != request.session_id
            or manifest.project_scope_id != request.project_scope_id
            or finalization["task_id"] != manifest.task_id
            or finalization["session_id"] != manifest.session_id
            or finalization["project_scope_id"] != manifest.project_scope_id
            or finalization["content_hash"] != manifest.finalization_hash
        ):
            raise IntegrityInspectionError(
                "retrieval manifest parent binding is invalid"
            )
        finalized_ids = [
            row["context_item_id"]
            for row in connection.execute(
                """
                SELECT context_item_id FROM task_context_items
                WHERE task_id = ? ORDER BY injection_order
                """,
                (manifest.task_id,),
            )
        ]
        if finalized_ids != [
            entry.context_item_id for entry in manifest.entries
        ]:
            raise IntegrityInspectionError(
                "retrieval manifest omits or adds finalized candidates"
            )
        for entry in manifest.entries:
            source_table, source_column = {
                "memory_record": ("records", "record_id"),
                "evidence": ("evidence_items", "evidence_id"),
                "governance_rule": (
                    "governance_rules",
                    "governance_rule_id",
                ),
            }[entry.source_kind]
            source = connection.execute(
                f"SELECT content_hash FROM {source_table} "  # noqa: S608
                f"WHERE {source_column} = ?",  # noqa: S608
                (entry.source_id,),
            ).fetchone()
            if (
                source is None
                or source["content_hash"] != entry.source_content_hash
            ):
                raise IntegrityInspectionError(
                    "retrieval manifest source hash cannot be reverified"
                )
            if (
                entry.disposition == "included"
                and entry.source_kind == "evidence"
                and not _exact_evidence_relationships(
                    connection,
                    evidence_id=entry.source_id,
                    task_id=manifest.task_id,
                    project_scope_id=manifest.project_scope_id,
                )
            ):
                raise IntegrityInspectionError(
                    "included evidence lacks its exact required/resolved task "
                    "and project binding"
                )

    def reconstruct_retrieval_manifest(
        self,
        retrieval_manifest_id: str,
    ) -> Mapping[str, Any]:
        """Reconstruct and reverify an immutable retrieval manifest."""

        validate_identifier(
            retrieval_manifest_id,
            field="retrieval_manifest_id",
        )

        def operation(connection: sqlite3.Connection) -> RetrievalManifest:
            manifest = self._load_manifest(connection, retrieval_manifest_id)
            request = self._load_request(
                connection,
                manifest.retrieval_request_id,
            )
            self._verify_manifest_relationships(
                connection,
                request,
                manifest,
            )
            self._verify_historical_projection(
                connection,
                request=request,
                manifest=manifest,
            )
            return manifest

        manifest = self._kernel.read(operation)
        return {
            "canonical_json": manifest.canonical_json,
            "content_hash": manifest.content_hash,
            "integrity_verified": True,
            "value": manifest.canonical_value(),
        }

    @staticmethod
    def _verify_package_relationships(
        connection: sqlite3.Connection,
        request: RetrievalRequest,
        manifest: RetrievalManifest,
        package: StructuredContextPackage,
    ) -> None:
        if (
            package.retrieval_request_id != request.retrieval_request_id
            or package.retrieval_manifest_id
            != manifest.retrieval_manifest_id
            or package.retrieval_manifest_hash != manifest.content_hash
            or package.task_memory_projection_hash
            != manifest.task_memory_projection_hash
            or package.task_id != manifest.task_id
            or package.session_id != manifest.session_id
            or package.project_scope_id != manifest.project_scope_id
            or package.task_context_finalization_id
            != manifest.task_context_finalization_id
        ):
            raise IntegrityInspectionError(
                "context package parent binding is invalid"
            )
        included = {
            entry.entry_id: entry
            for entry in manifest.entries
            if entry.disposition == "included"
        }
        manifest_by_id = {
            entry.entry_id: entry for entry in manifest.entries
        }
        preserved_contaminated_sources = {
            (finding.source_kind, finding.source_id)
            for finding in package.contamination_findings
            if finding.source_kind is not None
        }
        reconstructed: dict[str, Any] = {
            "task": None,
            "authority": None,
            "policy": [],
            "evidence": [],
            "memory": [],
        }
        seen_manifest_entries: set[str] = set()
        for entry in package.ordered_entries:
            value = _canonical_object(
                entry.entry_json,
                field="ordered context entry",
            )
            if entry.section in {"task", "authority"}:
                if reconstructed[entry.section] is not None:
                    raise IntegrityInspectionError(
                        "authoritative context section is duplicated"
                    )
                reconstructed[entry.section] = value
            else:
                manifest_entry = manifest_by_id.get(
                    entry.retrieval_manifest_entry_id or ""
                )
                source_matches_manifest = (
                    manifest_entry is not None
                    and manifest_entry.source_kind == entry.source_kind
                    and manifest_entry.source_id == entry.source_id
                    and manifest_entry.source_content_hash
                    == entry.source_content_hash
                    and manifest_entry.target_section == entry.section
                )
                if (
                    source_matches_manifest
                    and package.status == "accepted"
                    and manifest_entry is not None
                    and manifest_entry.materialized_content_hash
                    != entry.entry_canonical_hash
                ):
                    raise IntegrityInspectionError(
                        "accepted ordered context differs from its persisted "
                        "materialization hash"
                    )
                preserved_untracked = (
                    package.status == "rejected_contamination"
                    and (entry.source_kind, entry.source_id)
                    in preserved_contaminated_sources
                )
                if not source_matches_manifest and not preserved_untracked:
                    raise IntegrityInspectionError(
                        "ordered context entry is not exactly manifest-tracked"
                    )
                if preserved_untracked and not source_matches_manifest:
                    reconstructed[entry.section].append(value)
                    continue
                assert manifest_entry is not None
                if manifest_entry.disposition == "included":
                    if manifest_entry.entry_id in seen_manifest_entries:
                        raise IntegrityInspectionError(
                            "included context entry is duplicated"
                        )
                    seen_manifest_entries.add(manifest_entry.entry_id)
                elif (
                    package.status != "rejected_contamination"
                    or (entry.source_kind, entry.source_id)
                    not in preserved_contaminated_sources
                ):
                    raise IntegrityInspectionError(
                        "excluded source appears outside preserved contamination"
                    )
                reconstructed[entry.section].append(value)
        sections = _canonical_object(
            package.sections_json,
            field="context sections",
        )
        if reconstructed != sections or seen_manifest_entries != set(included):
            raise IntegrityInspectionError(
                "ordered context manifest does not reconstruct the package"
            )
        if package.status == "accepted" and package.contamination_findings:
            raise IntegrityInspectionError(
                "accepted context preserves contamination findings"
            )
        if (
            package.status == "rejected_contamination"
            and not package.contamination_findings
        ):
            raise IntegrityInspectionError(
                "contaminated context lost its preserved findings"
            )
        relationship = connection.execute(
            """
            SELECT * FROM context_recovery_relationships
            WHERE recovery_context_package_id = ?
            """,
            (package.context_package_id,),
        ).fetchone()
        if package.recovery_of_context_package_id is None:
            if relationship is not None:
                raise IntegrityInspectionError(
                    "non-recovery context has a recovery relationship"
                )
            return
        if (
            relationship is None
            or relationship["rejected_context_package_id"]
            != package.recovery_of_context_package_id
        ):
            raise IntegrityInspectionError(
                "recovery context linkage is missing or invalid"
            )
        recovery = RecoveryRelationship(
            recovery_context_package_id=relationship[
                "recovery_context_package_id"
            ],
            rejected_context_package_id=relationship[
                "rejected_context_package_id"
            ],
            recovery_reason=relationship["recovery_reason"],
            excluded_source_ids=tuple(
                _canonical_array(
                    relationship["excluded_source_ids_json"],
                    field="recovery exclusions",
                )
            ),
            preserved_findings_json=relationship[
                "preserved_findings_json"
            ],
            created_at=relationship["created_at"],
        )
        if (
            relationship["canonical_json"] != recovery.canonical_json
            or relationship["content_hash"] != recovery.content_hash
            or package.recovery_relationship_hash
            != recovery.content_hash
        ):
            raise IntegrityInspectionError(
                "recovery relationship canonical content or hash mismatch"
            )
        rejected = ContextRetrievalService._load_package(
            connection,
            recovery.rejected_context_package_id,
        )
        expected_findings_json = canonical_json_text(
            [
                finding.canonical_value()
                for finding in rejected.contamination_findings
            ]
        )
        finding_source_ids = frozenset(
            finding.source_id
            for finding in rejected.contamination_findings
            if finding.source_id is not None
        )
        expected_exclusions = (
            ContextRetrievalService._expand_controlled_recovery_exclusions(
                connection,
                finding_source_ids,
            )
        )
        if (
            rejected.status != "rejected_contamination"
            or rejected.task_id != package.task_id
            or rejected.session_id != package.session_id
            or rejected.project_scope_id != package.project_scope_id
            or rejected.task_context_finalization_id
            != package.task_context_finalization_id
            or recovery.preserved_findings_json != expected_findings_json
            or not expected_exclusions.issubset(recovery.excluded_source_ids)
        ):
            raise IntegrityInspectionError(
                "recovery relationship does not preserve the exact rejected "
                "context and controlled-source exclusions"
            )
        included_source_ids = {
            entry.source_id
            for entry in manifest.entries
            if entry.disposition == "included"
        }
        if included_source_ids.intersection(recovery.excluded_source_ids):
            raise IntegrityInspectionError(
                "contaminated source reappears in recovery context"
            )

    @staticmethod
    def _verify_historical_projection(
        connection: sqlite3.Connection,
        *,
        request: RetrievalRequest,
        manifest: RetrievalManifest,
    ) -> Mapping[str, Any]:
        """Verify the immutable attempt-time I3-D projection and liveness."""

        from batch87_apprentice.memory.session_task_integrity import (
            SessionTaskIntegrityInspector,
        )

        projection_value = _canonical_object(
            manifest.task_memory_projection_json,
            field="task-memory projection snapshot",
        )
        projection = {
            "canonical_json": manifest.task_memory_projection_json,
            "content_hash": manifest.task_memory_projection_hash,
            "integrity_verified": True,
            "value": projection_value,
        }
        ContextRetrievalService._validate_projection(request, projection)
        if not SessionTaskIntegrityInspector._was_live_at(
            connection,
            task_id=request.task_id,
            session_id=request.session_id,
            timestamp=request.requested_at,
        ):
            raise IntegrityInspectionError(
                "retrieval request was not made while its task and session "
                "were historically live"
            )
        i2_findings = [
            finding
            for finding in inspect_task_runtime_integrity(connection)
            if finding.task_id == request.task_id
            or (
                finding.task_id is None
                and finding.session_id == request.session_id
            )
            or (finding.task_id is None and finding.session_id is None)
        ]
        i3_findings = [
            finding
            for finding in SessionTaskIntegrityInspector._inspect_connection(
                connection
            ).findings
            if finding.task_id == request.task_id
            or (
                finding.task_id is None
                and finding.session_id == request.session_id
            )
        ]
        if i2_findings or i3_findings:
            raise IntegrityInspectionError(
                "current authoritative integrity cannot verify the historical "
                "retrieval attempt"
            )
        return projection_value

    def _materialization_binding_findings(
        self,
        connection: sqlite3.Connection,
        *,
        request: RetrievalRequest,
        manifest: RetrievalManifest,
        package: StructuredContextPackage,
        mode: str,
        evaluated_at: str,
    ) -> tuple[ContextReadinessFinding, ...]:
        """Re-read typed sources and compare exact deterministic materialization."""

        ordered_by_manifest = {
            entry.retrieval_manifest_entry_id: entry
            for entry in package.ordered_entries
            if entry.retrieval_manifest_entry_id is not None
        }
        findings: set[ContextReadinessFinding] = set()
        for entry in manifest.entries:
            if entry.disposition != "included":
                continue
            item = connection.execute(
                """
                SELECT context_kind FROM task_context_items
                WHERE context_item_id = ? AND task_id = ?
                """,
                (entry.context_item_id, request.task_id),
            ).fetchone()
            if item is None:
                findings.add(
                    ContextReadinessFinding(
                        reason_code="source_missing",
                        detail=(
                            "included context item no longer has its exact "
                            "typed task-context source"
                        ),
                        source_kind=entry.source_kind,
                        source_id=entry.source_id,
                    )
                )
                continue
            status, reasons, materialized_json = self._materializer.materialize(
                connection,
                source_kind=entry.source_kind,
                source_id=entry.source_id,
                context_kind=item["context_kind"],
                task_id=request.task_id,
                project_scope_id=request.project_scope_id,
                mode=mode,
                evaluated_at=evaluated_at,
            )
            if status != "materialized" or materialized_json is None:
                for reason in reasons or ("source_integrity_invalid",):
                    findings.add(
                        ContextReadinessFinding(
                            reason_code=reason,
                            detail=(
                                "included source cannot be deterministically "
                                f"materialized in {mode} mode"
                            ),
                            source_kind=entry.source_kind,
                            source_id=entry.source_id,
                        )
                    )
                continue
            expected_value = _canonical_object(
                materialized_json,
                field="independent materialized source",
            )
            expected_hash = sha256_canonical_json(expected_value)
            ordered = ordered_by_manifest.get(entry.entry_id)
            if (
                expected_hash != entry.materialized_content_hash
                or ordered is None
                or ordered.entry_canonical_hash != expected_hash
                or ordered.entry_json != materialized_json
            ):
                findings.add(
                    ContextReadinessFinding(
                        reason_code="materialized_content_mismatch",
                        detail=(
                            "ordered context differs from the exact "
                            "deterministic safe materialization"
                        ),
                        source_kind=entry.source_kind,
                        source_id=entry.source_id,
                    )
                )
        return tuple(
            sorted(
                findings,
                key=lambda finding: (
                    finding.reason_code,
                    finding.source_kind or "",
                    finding.source_id or "",
                    finding.detail,
                ),
            )
        )

    @staticmethod
    def _preserved_rejection_covers(
        package: StructuredContextPackage,
        findings: tuple[ContextReadinessFinding, ...],
    ) -> bool:
        preserved_bindings = {
            (
                finding.reason_code,
                finding.source_kind,
                finding.source_id,
            )
            for finding in package.contamination_findings
        }
        preserved_exact = {
            (
                finding.reason_code,
                finding.source_kind,
                finding.source_id,
                finding.detail,
            )
            for finding in package.contamination_findings
        }
        exact_detail_codes = {
            "authoritative_task_content_mismatch",
            "authoritative_authority_content_mismatch",
        }
        return (
            package.status == "rejected_contamination"
            and bool(findings)
            and all(
                (
                    (
                        finding.reason_code,
                        finding.source_kind,
                        finding.source_id,
                        finding.detail,
                    )
                    in preserved_exact
                    if finding.reason_code in exact_detail_codes
                    else (
                        finding.reason_code,
                        finding.source_kind,
                        finding.source_id,
                    )
                    in preserved_bindings
                )
                for finding in findings
            )
        )

    def reconstruct_context_package(
        self,
        context_package_id: str,
    ) -> Mapping[str, Any]:
        """Reconstruct and reverify one attempted structured context package."""

        validate_identifier(context_package_id, field="context_package_id")

        def operation(
            connection: sqlite3.Connection,
        ) -> tuple[
            RetrievalRequest,
            RetrievalManifest,
            StructuredContextPackage,
        ]:
            package = self._load_package(connection, context_package_id)
            manifest = self._load_manifest(
                connection,
                package.retrieval_manifest_id,
            )
            request = self._load_request(
                connection,
                package.retrieval_request_id,
            )
            self._verify_manifest_relationships(
                connection,
                request,
                manifest,
            )
            self._verify_package_relationships(
                connection,
                request,
                manifest,
                package,
            )
            self._verify_historical_projection(
                connection,
                request=request,
                manifest=manifest,
            )
            authoritative_findings = (
                self._authoritative_readiness_findings(
                    manifest,
                    package,
                )
            )
            if (
                authoritative_findings
                and not self._preserved_rejection_covers(
                    package,
                    authoritative_findings,
                )
            ):
                raise IntegrityInspectionError(
                    "historical authoritative section binding cannot be "
                    "reverified"
                )
            binding_findings = self._materialization_binding_findings(
                connection,
                request=request,
                manifest=manifest,
                package=package,
                mode="historical",
                evaluated_at=request.requested_at,
            )
            if binding_findings and not self._preserved_rejection_covers(
                package,
                binding_findings,
            ):
                raise IntegrityInspectionError(
                    "historical context materialization binding cannot be "
                    "reverified"
                )
            return request, manifest, package

        request, manifest, package = self._kernel.read(operation)
        if manifest.content_hash != package.retrieval_manifest_hash:
            raise IntegrityInspectionError(
                "context package retrieval manifest hash cannot be reproduced"
            )
        return {
            "canonical_json": package.canonical_json,
            "content_hash": package.content_hash,
            "historical_integrity_verified": True,
            "historical_status": package.status,
            "integrity_verified": True,
            "value": package.canonical_value(),
        }

    def assess_context_readiness(
        self,
        context_package_id: str,
        evaluated_at: str,
    ) -> Mapping[str, Any]:
        """Assess current bridge readiness without mutating historical records."""

        validate_identifier(context_package_id, field="context_package_id")
        parse_canonical_utc(evaluated_at, field="evaluated_at")

        def operation(
            connection: sqlite3.Connection,
        ) -> ContextReadinessAssessment:
            from batch87_apprentice.memory.session_task_integrity import (
                SessionTaskIntegrityInspector,
            )

            package = self._load_package(connection, context_package_id)
            manifest = self._load_manifest(
                connection,
                package.retrieval_manifest_id,
            )
            request = self._load_request(
                connection,
                package.retrieval_request_id,
            )
            self._verify_manifest_relationships(
                connection,
                request,
                manifest,
            )
            self._verify_package_relationships(
                connection,
                request,
                manifest,
                package,
            )
            self._verify_historical_projection(
                connection,
                request=request,
                manifest=manifest,
            )

            findings: set[ContextReadinessFinding] = set()
            findings.update(
                self._authoritative_readiness_findings(
                    manifest,
                    package,
                )
            )
            if package.status != "accepted":
                findings.add(
                    ContextReadinessFinding(
                        reason_code="package_not_accepted",
                        detail=(
                            "historical context status is "
                            f"{package.status}"
                        ),
                    )
                )
            state = connection.execute(
                """
                SELECT task.status AS task_status,
                       session_record.session_status,
                       session_record.active_project_scope
                FROM tasks AS task
                JOIN sessions AS session_record
                  ON session_record.session_id = task.session_id
                WHERE task.task_id = ? AND task.session_id = ?
                  AND task.project_scope_id = ?
                """,
                (
                    package.task_id,
                    package.session_id,
                    package.project_scope_id,
                ),
            ).fetchone()
            task_active = state is not None and state["task_status"] == "active"
            session_open = (
                state is not None
                and state["session_status"] in {"open", "paused"}
            )
            if not task_active:
                findings.add(
                    ContextReadinessFinding(
                        reason_code="task_not_active",
                        detail="the package task is not currently active",
                    )
                )
            if not session_open:
                findings.add(
                    ContextReadinessFinding(
                        reason_code="session_not_open",
                        detail="the package session is not currently open or paused",
                    )
                )
            if (
                state is None
                or state["active_project_scope"] != package.project_scope_id
            ):
                findings.add(
                    ContextReadinessFinding(
                        reason_code="project_scope_mismatch",
                        detail=(
                            "the current session project does not match the "
                            "historical package"
                        ),
                    )
                )

            i2_findings = [
                finding
                for finding in inspect_task_runtime_integrity(connection)
                if finding.task_id == package.task_id
                or (
                    finding.task_id is None
                    and finding.session_id == package.session_id
                )
                or (finding.task_id is None and finding.session_id is None)
            ]
            if i2_findings:
                findings.add(
                    ContextReadinessFinding(
                        reason_code="authoritative_i2_integrity_invalid",
                        detail="authoritative I2 integrity is currently invalid",
                    )
                )
            i3_report = SessionTaskIntegrityInspector._inspect_connection(
                connection
            )
            i3_findings = [
                finding
                for finding in i3_report.findings
                if finding.task_id == package.task_id
                or (
                    finding.task_id is None
                    and finding.session_id == package.session_id
                )
            ]
            if i3_findings:
                findings.add(
                    ContextReadinessFinding(
                        reason_code="i3d_integrity_invalid",
                        detail="I3-D task-memory integrity is currently invalid",
                    )
                )
            uncertainty = SessionTaskMemoryRepository._uncertainty_value(
                connection,
                package.task_id,
                integrity_findings=i3_report.findings,
            )
            if any(
                entry["impact"] == "blocking"
                for entry in uncertainty["active"]
            ):
                findings.add(
                    ContextReadinessFinding(
                        reason_code="blocking_uncertainty",
                        detail="a blocking uncertainty is currently active",
                    )
                )

            if task_active and session_open:
                for entry in manifest.entries:
                    if entry.disposition != "included":
                        continue
                    decision = (
                        SessionTaskMemoryRepository._eligibility_from_connection(
                            connection,
                            task_id=package.task_id,
                            context_item_id=entry.context_item_id,
                            mode="active",
                            evaluated_at=evaluated_at,
                        )
                    )
                    for reason in decision.reason_codes:
                        if reason == "historical_mode_required":
                            continue
                        findings.add(
                            ContextReadinessFinding(
                                reason_code=reason,
                                detail=(
                                    "included source is not currently eligible"
                                ),
                                source_kind=entry.source_kind,
                                source_id=entry.source_id,
                            )
                        )
            findings.update(
                self._materialization_binding_findings(
                    connection,
                    request=request,
                    manifest=manifest,
                    package=package,
                    mode="active",
                    evaluated_at=evaluated_at,
                )
            )
            for contamination in package.contamination_findings:
                findings.add(
                    ContextReadinessFinding(
                        reason_code=contamination.reason_code,
                        detail=contamination.detail,
                        source_kind=contamination.source_kind,
                        source_id=contamination.source_id,
                    )
                )
            ordered_findings = tuple(
                sorted(
                    findings,
                    key=lambda finding: (
                        finding.reason_code,
                        finding.source_kind or "",
                        finding.source_id or "",
                        finding.detail,
                    ),
                )
            )
            return ContextReadinessAssessment(
                context_package_id=context_package_id,
                evaluated_at=evaluated_at,
                current_bridge_context_ready=not ordered_findings,
                current_findings=ordered_findings,
            )

        assessment = self._kernel.read(operation)
        return {
            **assessment.canonical_value(),
            "decision_hash": assessment.decision_hash,
        }
