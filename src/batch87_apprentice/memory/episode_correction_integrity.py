"""Independent integrity reconstruction for the B87-I3-C2 ledgers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import sqlite3
from typing import Any

from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_bytes
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.contracts import RecordEnvelope
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .episode_correction_contracts import (
    CorrectionPayload,
    EpisodePayload,
    correction_content_hash,
    correction_from_database,
    episode_content_hash,
    episode_from_database,
    validate_correction_pair,
    validate_episode_pair,
)
from .episode_correction_repository import EpisodeCorrectionLedgerRepository


@dataclass(frozen=True, slots=True)
class EpisodeCorrectionIntegrityFinding:
    code: str
    severity: str
    record_id: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class EpisodeCorrectionIntegrityReport:
    findings: tuple[EpisodeCorrectionIntegrityFinding, ...]

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.findings)


def _envelope(row: Mapping[str, Any]) -> RecordEnvelope:
    return RecordEnvelope(
        **{
            field: row[field]
            for field in RecordEnvelope.__dataclass_fields__
        }
    )


class EpisodeCorrectionIntegrityInspector:
    """Detect structural, lineage, occurrence, authority, and hash defects."""

    def __init__(self, source: DatabaseConfig | PersistenceKernel) -> None:
        self._kernel = (
            source if isinstance(source, PersistenceKernel) else PersistenceKernel(source)
        )

    @staticmethod
    def _schema_present(connection: sqlite3.Connection) -> bool:
        return (
            connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'episodes'
                """
            ).fetchone()
            is not None
        )

    @staticmethod
    def _finding(
        findings: list[EpisodeCorrectionIntegrityFinding],
        code: str,
        record_id: str | None,
        detail: str,
    ) -> None:
        findings.append(
            EpisodeCorrectionIntegrityFinding(
                code=code,
                severity="error",
                record_id=record_id,
                detail=detail,
            )
        )

    @classmethod
    def _check_payload_composition(
        cls,
        connection: sqlite3.Connection,
        findings: list[EpisodeCorrectionIntegrityFinding],
    ) -> None:
        for record in connection.execute(
            """
            SELECT record.record_id, record.record_type,
                   episode.record_id AS episode_payload_id,
                   correction.record_id AS correction_payload_id
            FROM records AS record
            LEFT JOIN episodes AS episode ON episode.record_id = record.record_id
            LEFT JOIN corrections AS correction
              ON correction.record_id = record.record_id
            WHERE record.record_family = 'episodic_memory'
              AND record.record_type IN ('episode', 'correction')
            ORDER BY record.record_id
            """
        ):
            expected = (
                record["episode_payload_id"]
                if record["record_type"] == "episode"
                else record["correction_payload_id"]
            )
            unexpected = (
                record["correction_payload_id"]
                if record["record_type"] == "episode"
                else record["episode_payload_id"]
            )
            if expected is None:
                cls._finding(
                    findings,
                    "I3C2-MISSING-PAYLOAD",
                    record["record_id"],
                    "C2 envelope has no matching payload row",
                )
            if unexpected is not None:
                cls._finding(
                    findings,
                    "I3C2-PAYLOAD-TYPE-MISMATCH",
                    record["record_id"],
                    "C2 envelope also has a payload of the wrong type",
                )
        for table, expected_type in (
            ("episodes", "episode"),
            ("corrections", "correction"),
        ):
            for row in connection.execute(
                f"""
                SELECT payload.record_id
                FROM {table} AS payload
                LEFT JOIN records AS record ON record.record_id = payload.record_id
                WHERE record.record_id IS NULL
                   OR record.record_family <> 'episodic_memory'
                   OR record.record_type <> ?
                """,
                (expected_type,),
            ):
                cls._finding(
                    findings,
                    "I3C2-ORPHANED-PAYLOAD",
                    row["record_id"],
                    f"{expected_type} payload has no matching exact envelope",
                )

    @staticmethod
    def _ordered_rows(
        connection: sqlite3.Connection,
        table: str,
        identifier_column: str,
        order_column: str,
        record_id: str,
    ) -> tuple[tuple[int, str], ...]:
        return tuple(
            (int(row[order_column]), row[identifier_column])
            for row in connection.execute(
                f"""
                SELECT {order_column}, {identifier_column}
                FROM {table}
                WHERE record_id = ?
                ORDER BY {order_column}, {identifier_column}
                """,
                (record_id,),
            )
        )

    @classmethod
    def _check_order(
        cls,
        findings: list[EpisodeCorrectionIntegrityFinding],
        record_id: str,
        label: str,
        rows: tuple[tuple[int, str], ...],
    ) -> tuple[str, ...]:
        identifiers = tuple(identifier for _, identifier in rows)
        if tuple(order for order, _ in rows) != tuple(range(len(rows))):
            cls._finding(
                findings,
                "I3C2-LINEAGE-ORDER",
                record_id,
                f"{label} ordinals are missing, duplicated, or reordered",
            )
        if len(set(identifiers)) != len(identifiers):
            cls._finding(
                findings,
                "I3C2-LINEAGE-DUPLICATE",
                record_id,
                f"{label} identifiers are duplicated",
            )
        return identifiers

    @classmethod
    def _check_evidence(
        cls,
        connection: sqlite3.Connection,
        envelope: RecordEnvelope,
        evidence_ids: tuple[str, ...],
        findings: list[EpisodeCorrectionIntegrityFinding],
    ) -> None:
        record_id = envelope.record_id
        for evidence_id in evidence_ids:
            evidence = connection.execute(
                """
                SELECT evidence.*, inline.content AS inline_content
                FROM evidence_items AS evidence
                LEFT JOIN evidence_inline_text AS inline
                  ON inline.evidence_id = evidence.evidence_id
                WHERE evidence.evidence_id = ?
                """,
                (evidence_id,),
            ).fetchone()
            if evidence is None:
                cls._finding(
                    findings,
                    "I3C2-EVIDENCE-MISSING",
                    record_id,
                    f"lineage evidence is missing: {evidence_id}",
                )
                continue
            if evidence["integrity_status"] != "valid":
                cls._finding(
                    findings,
                    "I3C2-EVIDENCE-INTEGRITY",
                    record_id,
                    f"lineage evidence is not valid: {evidence_id}",
                )
            if evidence["storage_kind"] == "inline_text":
                content = evidence["inline_content"]
                exact = None if content is None else content.encode("utf-8")
                if (
                    exact is None
                    or evidence["content_hash"] != sha256_bytes(exact)
                    or evidence["byte_length"] != len(exact)
                ):
                    cls._finding(
                        findings,
                        "I3C2-EVIDENCE-CONTENT",
                        record_id,
                        f"lineage evidence bytes or metadata changed: {evidence_id}",
                    )
            if evidence["evidence_kind"] in {
                "controlled_prompt",
                "controlled_output",
            }:
                cls._finding(
                    findings,
                    "I3C2-CGR-CONTAMINATION",
                    record_id,
                    f"controlled prompt/output kind entered C2 lineage: {evidence_id}",
                )
            if (
                evidence["sensitivity_class"] != envelope.sensitivity_class
                or evidence["privacy_class"] != envelope.privacy_class
            ):
                cls._finding(
                    findings,
                    "I3C2-EVIDENCE-BOUNDARY",
                    record_id,
                    f"lineage evidence crosses privacy/sensitivity: {evidence_id}",
                )
            if connection.execute(
                """
                SELECT 1 FROM controlled_resilience_evidence
                WHERE raw_prompt_evidence_id = ?
                   OR raw_output_evidence_id = ?
                """,
                (evidence_id, evidence_id),
            ).fetchone():
                cls._finding(
                    findings,
                    "I3C2-CGR-CONTAMINATION",
                    record_id,
                    f"raw controlled evidence entered C2 lineage: {evidence_id}",
                )
            if connection.execute(
                """
                SELECT 1
                FROM record_evidence_links AS link
                JOIN records AS linked ON linked.record_id = link.record_id
                WHERE link.evidence_id = ?
                  AND linked.project_scope_id IS NOT NULL
                  AND linked.project_scope_id <> ?
                LIMIT 1
                """,
                (evidence_id, envelope.project_scope_id),
            ).fetchone():
                cls._finding(
                    findings,
                    "I3C2-EVIDENCE-PROJECT",
                    record_id,
                    f"lineage evidence is linked across project scope: {evidence_id}",
                )

    @classmethod
    def _check_exact_links(
        cls,
        connection: sqlite3.Connection,
        record_id: str,
        expected: set[tuple[str, str]],
        findings: list[EpisodeCorrectionIntegrityFinding],
    ) -> None:
        actual_rows = tuple(
            (row["evidence_id"], row["relationship"])
            for row in connection.execute(
                """
                SELECT evidence_id, relationship
                FROM record_evidence_links
                WHERE record_id = ?
                ORDER BY evidence_id, relationship
                """,
                (record_id,),
            )
        )
        actual = set(actual_rows)
        if len(actual_rows) != len(actual):
            cls._finding(
                findings,
                "I3C2-EVIDENCE-LINK-DUPLICATE",
                record_id,
                "C2 evidence links contain duplicate lineage",
            )
        missing = expected - actual
        additional = actual - expected
        if missing:
            cls._finding(
                findings,
                "I3C2-EVIDENCE-LINK-MISSING",
                record_id,
                f"required C2 evidence links are missing: {sorted(missing)!r}",
            )
        if additional:
            cls._finding(
                findings,
                "I3C2-EVIDENCE-LINK-ADDITIONAL",
                record_id,
                f"additional or wrong C2 evidence links exist: {sorted(additional)!r}",
            )

    @classmethod
    def _check_active_approval(
        cls,
        connection: sqlite3.Connection,
        record: Mapping[str, Any],
        findings: list[EpisodeCorrectionIntegrityFinding],
    ) -> None:
        if record["lifecycle_state"] != "active":
            return
        valid = connection.execute(
            """
            SELECT 1
            FROM memory_record_approval_transitions AS transition
            JOIN memory_approval_grants AS grant_record
              ON grant_record.grant_id = transition.approval_grant_id
             AND grant_record.consumed_by_transition_id =
                 transition.transition_id
             AND grant_record.consumed_at IS NOT NULL
            JOIN authority_records AS authority
              ON authority.authority_record_id =
                 transition.authority_record_id
             AND authority.authority_record_id =
                 grant_record.authority_record_id
            JOIN memory_record_approval_authorities AS permitted
              ON permitted.record_family = ?
             AND permitted.record_type = ?
             AND permitted.authority_class = authority.authority_class
            JOIN evidence_items AS evidence
              ON evidence.evidence_id = transition.approval_evidence_id
             AND evidence.evidence_id = grant_record.evidence_id
            WHERE transition.record_id = ?
              AND transition.to_status = 'approved'
              AND grant_record.record_id = transition.record_id
              AND grant_record.project_scope_id = ?
              AND authority.status = 'active'
              AND authority.effect = 'allow'
              AND evidence.integrity_status = 'valid'
              AND NOT EXISTS (
                  SELECT 1 FROM authority_revocations AS revocation
                  WHERE revocation.authority_record_id =
                        authority.authority_record_id
              )
            LIMIT 1
            """,
            (
                record["record_family"],
                record["record_type"],
                record["record_id"],
                record["project_scope_id"],
            ),
        ).fetchone()
        if record["approval_status"] != "approved" or valid is None:
            cls._finding(
                findings,
                "I3C2-ACTIVE-WITHOUT-APPROVAL",
                record["record_id"],
                "active C2 memory lacks valid consumed external approval",
            )

    @classmethod
    def _inspect_episode(
        cls,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        findings: list[EpisodeCorrectionIntegrityFinding],
    ) -> None:
        record_id = row["record_id"]
        record = connection.execute(
            "SELECT * FROM records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if record is None:
            return
        try:
            envelope = _envelope(dict(record))
        except ValidationError as exc:
            cls._finding(
                findings,
                "I3C2-EPISODE-ENVELOPE",
                record_id,
                str(exc),
            )
            return
        inputs = cls._check_order(
            findings,
            record_id,
            "episode input",
            cls._ordered_rows(
                connection,
                "episode_input_evidence",
                "evidence_id",
                "evidence_order",
                record_id,
            ),
        )
        outputs = cls._check_order(
            findings,
            record_id,
            "episode output",
            cls._ordered_rows(
                connection,
                "episode_output_evidence",
                "evidence_id",
                "evidence_order",
                record_id,
            ),
        )
        evaluations = cls._check_order(
            findings,
            record_id,
            "episode evaluation",
            cls._ordered_rows(
                connection,
                "episode_evaluation_anchors",
                "evaluation_record_id",
                "evaluation_order",
                record_id,
            ),
        )
        if set(inputs) & set(outputs):
            cls._finding(
                findings,
                "I3C2-EPISODE-EVIDENCE-OVERLAP",
                record_id,
                "episode input and output evidence overlap",
            )
        if not inputs and not outputs:
            cls._finding(
                findings,
                "I3C2-EPISODE-EVIDENCE-EMPTY",
                record_id,
                "episode has no input or output evidence",
            )
        try:
            payload = episode_from_database(
                dict(row),
                input_evidence_ids=inputs,
                output_evidence_ids=outputs,
                evaluation_record_ids=evaluations,
            )
            validate_episode_pair(envelope, payload, for_creation=False)
        except (ValidationError, TypeError) as exc:
            cls._finding(
                findings,
                "I3C2-EPISODE-CONTRACT",
                record_id,
                str(exc),
            )
            payload = None
        try:
            EpisodeCorrectionLedgerRepository._validate_episode_occurrence(
                connection,
                envelope,
                payload
                if isinstance(payload, EpisodePayload)
                else EpisodePayload(
                    record_id=record_id,
                    episode_kind=row["episode_kind"],
                    summary=row["summary"],
                    outcome=row["outcome"],
                    input_evidence_ids=inputs,
                    output_evidence_ids=outputs,
                    evaluation_record_ids=evaluations,
                ),
            )
        except (ValidationError, TypeError) as exc:
            cls._finding(
                findings,
                "I3C2-EPISODE-OCCURRENCE",
                record_id,
                str(exc),
            )
        cls._check_evidence(
            connection,
            envelope,
            (*inputs, *outputs),
            findings,
        )
        cls._check_exact_links(
            connection,
            record_id,
            {
                *((evidence_id, "derived_from") for evidence_id in inputs),
                *((evidence_id, "produced_as") for evidence_id in outputs),
            },
            findings,
        )
        for evaluation_id in evaluations:
            anchor = connection.execute(
                """
                SELECT project_scope_id, current_state
                FROM governed_evaluation_record_anchors
                WHERE evaluation_record_id = ?
                """,
                (evaluation_id,),
            ).fetchone()
            if anchor is None:
                cls._finding(
                    findings,
                    "I3C2-EVALUATION-ANCHOR-MISSING",
                    record_id,
                    f"episode anchor is missing: {evaluation_id}",
                )
            elif (
                anchor["project_scope_id"] != envelope.project_scope_id
                or anchor["current_state"] != "claimed"
            ):
                cls._finding(
                    findings,
                    "I3C2-EVALUATION-ANCHOR-INVALID",
                    record_id,
                    f"episode anchor is unclaimed or cross-project: {evaluation_id}",
                )
        if payload is not None:
            if row["canonical_json"] != payload.canonical_json:
                cls._finding(
                    findings,
                    "I3C2-EPISODE-CANONICAL-JSON",
                    record_id,
                    "episode canonical JSON differs from reconstructed payload",
                )
            try:
                expected_hash = episode_content_hash(envelope, payload)
                if expected_hash != record["content_hash"]:
                    cls._finding(
                        findings,
                        "I3C2-EPISODE-CONTENT-HASH",
                        record_id,
                        "episode hash differs from ordered reconstructed content",
                    )
            except ValidationError as exc:
                cls._finding(
                    findings,
                    "I3C2-EPISODE-CONTENT-HASH",
                    record_id,
                    str(exc),
                )
        cls._check_active_approval(connection, dict(record), findings)

    @classmethod
    def _valid_corrects_grant(
        cls,
        connection: sqlite3.Connection,
        record_id: str,
        target_episode_id: str,
    ) -> bool:
        return (
            connection.execute(
                """
                SELECT 1
                FROM record_relationships AS relationship
                JOIN memory_relationship_grants AS grant_record
                  ON grant_record.grant_id = relationship.relationship_grant_id
                 AND grant_record.relationship_id =
                     relationship.relationship_id
                 AND grant_record.consumed_by_relationship_id =
                     relationship.relationship_id
                 AND grant_record.consumed_at IS NOT NULL
                JOIN authority_records AS authority
                  ON authority.authority_record_id =
                     grant_record.authority_record_id
                JOIN evidence_items AS evidence
                  ON evidence.evidence_id = grant_record.evidence_id
                WHERE relationship.source_record_id = ?
                  AND relationship.target_record_id = ?
                  AND relationship.relationship_type = 'corrects'
                  AND grant_record.relationship_type = 'corrects'
                  AND grant_record.source_record_id = ?
                  AND grant_record.target_record_id = ?
                  AND grant_record.authority_class IN (
                      'nolan_approved', 'nolan_byte_approved'
                  )
                  AND authority.status = 'active'
                  AND authority.effect = 'allow'
                  AND evidence.integrity_status = 'valid'
                  AND NOT EXISTS (
                      SELECT 1 FROM authority_revocations AS revocation
                      WHERE revocation.authority_record_id =
                            authority.authority_record_id
                  )
                LIMIT 1
                """,
                (
                    record_id,
                    target_episode_id,
                    record_id,
                    target_episode_id,
                ),
            ).fetchone()
            is not None
        )

    @classmethod
    def _inspect_correction(
        cls,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        findings: list[EpisodeCorrectionIntegrityFinding],
    ) -> None:
        record_id = row["record_id"]
        record = connection.execute(
            "SELECT * FROM records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if record is None:
            return
        try:
            envelope = _envelope(dict(record))
            payload = correction_from_database(dict(row))
            validate_correction_pair(envelope, payload, for_creation=False)
        except (ValidationError, TypeError) as exc:
            cls._finding(
                findings,
                "I3C2-CORRECTION-CONTRACT",
                record_id,
                str(exc),
            )
            return
        support = cls._check_order(
            findings,
            record_id,
            "correction support",
            cls._ordered_rows(
                connection,
                "correction_supporting_evidence",
                "evidence_id",
                "evidence_order",
                record_id,
            ),
        )
        if not support:
            cls._finding(
                findings,
                "I3C2-CORRECTION-SUPPORT-MISSING",
                record_id,
                "correction has no supporting evidence",
            )
        if payload.target_output_evidence_id in support:
            cls._finding(
                findings,
                "I3C2-CORRECTION-SUPPORT-OVERLAP",
                record_id,
                "correction target output is also used as support",
            )
        try:
            EpisodeCorrectionLedgerRepository._validate_correction_target(
                connection,
                envelope,
                payload,
            )
        except ValidationError as exc:
            cls._finding(
                findings,
                "I3C2-CORRECTION-TARGET",
                record_id,
                str(exc),
            )
        cls._check_evidence(
            connection,
            envelope,
            (payload.target_output_evidence_id, *support),
            findings,
        )
        cls._check_exact_links(
            connection,
            record_id,
            {
                (payload.target_output_evidence_id, "derived_from"),
                *((evidence_id, "supports") for evidence_id in support),
            },
            findings,
        )
        issuer = connection.execute(
            "SELECT status FROM entities WHERE entity_id = ?",
            (payload.issued_by_entity_id,),
        ).fetchone()
        if issuer is None or issuer["status"] != "active":
            cls._finding(
                findings,
                "I3C2-CORRECTION-ISSUER",
                record_id,
                "correction issuer is missing or inactive",
            )
        if payload.issuer_class == "approved_evaluator":
            cls._finding(
                findings,
                "I3C2-CORRECTION-EVALUATOR-AUTHORITY",
                record_id,
                "accepted authority contracts do not prove evaluator correction issuance",
            )
        relationships = tuple(
            connection.execute(
                """
                SELECT * FROM record_relationships
                WHERE relationship_type = 'corrects'
                  AND (source_record_id = ? OR target_record_id = ?)
                ORDER BY relationship_id
                """,
                (record_id, record_id),
            )
        )
        exact = tuple(
            item
            for item in relationships
            if item["source_record_id"] == record_id
            and item["target_record_id"] == payload.target_episode_id
        )
        relationship_required = record["lifecycle_state"] == "active"
        if (
            (relationship_required and len(relationships) != 1)
            or len(relationships) > 1
            or (relationships and len(exact) != 1)
        ):
            cls._finding(
                findings,
                "I3C2-CORRECTS-RELATIONSHIP",
                record_id,
                "correction has a missing, additional, or wrong-direction relationship",
            )
        if exact and not cls._valid_corrects_grant(
            connection,
            record_id,
            payload.target_episode_id,
        ):
            cls._finding(
                findings,
                "I3C2-CORRECTS-GRANT",
                record_id,
                "corrects relationship lacks an exact consumed Nolan-inclusive grant",
            )
        if row["canonical_json"] != payload.canonical_json:
            cls._finding(
                findings,
                "I3C2-CORRECTION-CANONICAL-JSON",
                record_id,
                "correction canonical JSON differs from reconstructed payload",
            )
        try:
            expected_hash = correction_content_hash(envelope, payload, support)
            if expected_hash != record["content_hash"]:
                cls._finding(
                    findings,
                    "I3C2-CORRECTION-CONTENT-HASH",
                    record_id,
                    "correction hash differs from target, issuer, and support lineage",
                )
        except ValidationError as exc:
            cls._finding(
                findings,
                "I3C2-CORRECTION-CONTENT-HASH",
                record_id,
                str(exc),
            )
        cls._check_active_approval(connection, dict(record), findings)

    @classmethod
    def _inspect_connection(
        cls,
        connection: sqlite3.Connection,
    ) -> EpisodeCorrectionIntegrityReport:
        if not cls._schema_present(connection):
            return EpisodeCorrectionIntegrityReport(findings=())
        findings: list[EpisodeCorrectionIntegrityFinding] = []
        cls._check_payload_composition(connection, findings)
        for row in connection.execute("SELECT * FROM episodes ORDER BY record_id"):
            cls._inspect_episode(connection, row, findings)
        for row in connection.execute("SELECT * FROM corrections ORDER BY record_id"):
            cls._inspect_correction(connection, row, findings)
        return EpisodeCorrectionIntegrityReport(
            findings=tuple(
                sorted(
                    findings,
                    key=lambda item: (
                        item.code,
                        item.record_id or "",
                        item.detail,
                    ),
                )
            )
        )

    def inspect(self) -> EpisodeCorrectionIntegrityReport:
        return self._kernel.read(self._inspect_connection)
