"""Atomic Episode and Correction ledger operations for B87-I3-C2."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import sqlite3
from typing import Any

from batch87_apprentice.common.errors import NotFoundError, ValidationError
from batch87_apprentice.common.hashing import sha256_bytes
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.persistence.contracts import EvidenceItem, RecordEnvelope
from batch87_apprentice.persistence.repositories import (
    _insert_evidence,
    _insert_record,
    _insert_values,
)
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .episode_correction_contracts import (
    CorrectionPayload,
    EpisodePayload,
    correction_content_hash,
    correction_from_database,
    episode_content_hash,
    episode_from_database,
    ordered_unique_identifiers,
    validate_correction_pair,
    validate_episode_pair,
)
from .kernel import _insert_initial_memory_state

_CREATION_PRINCIPALS = frozenset({"operator", "codex_development_harness"})
_HUMAN_AUTHORITY_CLASSES = {
    "nolan": frozenset({"nolan_approved", "nolan_byte_approved"}),
    "nolan_byte": frozenset({"nolan_byte_approved"}),
}


def _record_envelope(row: Mapping[str, Any]) -> RecordEnvelope:
    return RecordEnvelope(
        **{
            field: row[field]
            for field in RecordEnvelope.__dataclass_fields__
        }
    )


class EpisodeCorrectionLedgerRepository:
    """Persist and reconstruct only the accepted Episode and Correction records."""

    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel

    def _after_write_step(
        self,
        step: str,
        connection: sqlite3.Connection,
    ) -> None:
        """Test seam used only to prove transaction rollback."""

    @staticmethod
    def _validate_creation_principal(
        envelope: RecordEnvelope,
        *,
        changed_by_principal: str,
        changed_by_entity_id: str | None,
    ) -> None:
        if changed_by_principal not in _CREATION_PRINCIPALS:
            raise ValidationError("unsupported C2 creation principal")
        if changed_by_principal == "operator":
            if changed_by_entity_id is None:
                raise ValidationError("operator creation requires an entity")
            validate_identifier(
                changed_by_entity_id,
                field="changed_by_entity_id",
            )
            if envelope.created_by_entity_id != changed_by_entity_id:
                raise ValidationError(
                    "operator creation entity must match envelope creator"
                )
        elif changed_by_entity_id is not None:
            raise ValidationError(
                "development harness creation cannot claim a human actor"
            )
        if (
            changed_by_principal == "codex_development_harness"
            and envelope.created_by_entity_id is not None
        ):
            raise ValidationError(
                "development harness creation cannot attribute a human creator"
            )

    @staticmethod
    def _validate_new_evidence(
        evidence_items: Sequence[EvidenceItem],
        *,
        allowed_ids: set[str],
    ) -> None:
        seen: set[str] = set()
        for item in evidence_items:
            if not isinstance(item, EvidenceItem):
                raise TypeError("evidence_items must contain EvidenceItem values")
            if item.evidence_id in seen:
                raise ValidationError("new evidence identifiers must be unique")
            if item.evidence_id not in allowed_ids:
                raise ValidationError(
                    "every supplied evidence item must appear in exact C2 lineage"
                )
            seen.add(item.evidence_id)

    @staticmethod
    def _validate_persisted_evidence(
        connection: sqlite3.Connection,
        envelope: RecordEnvelope,
        evidence_ids: Sequence[str],
    ) -> None:
        for evidence_id in evidence_ids:
            row = connection.execute(
                """
                SELECT evidence.*, inline.content AS inline_content,
                       inline.encoding AS inline_encoding
                FROM evidence_items AS evidence
                LEFT JOIN evidence_inline_text AS inline
                  ON inline.evidence_id = evidence.evidence_id
                WHERE evidence.evidence_id = ?
                """,
                (evidence_id,),
            ).fetchone()
            if row is None:
                raise ValidationError(f"C2 evidence is missing: {evidence_id}")
            if row["integrity_status"] != "valid":
                raise ValidationError("C2 evidence must have valid integrity")
            if (
                row["storage_kind"] != "inline_text"
                or row["inline_content"] is None
                or row["inline_encoding"] != "utf-8"
            ):
                raise ValidationError(
                    "C2 evidence requires preserved exact inline bytes"
                )
            exact = row["inline_content"].encode("utf-8")
            if (
                row["content_hash"] != sha256_bytes(exact)
                or row["byte_length"] != len(exact)
            ):
                raise ValidationError(
                    "C2 evidence bytes do not match immutable metadata"
                )
            if row["evidence_kind"] in {"controlled_prompt", "controlled_output"}:
                raise ValidationError(
                    "raw Controlled Governance Resilience evidence is prohibited"
                )
            if (
                row["sensitivity_class"] != envelope.sensitivity_class
                or row["privacy_class"] != envelope.privacy_class
            ):
                raise ValidationError(
                    "C2 evidence crosses its privacy or sensitivity boundary"
                )
            contaminated = connection.execute(
                """
                SELECT 1
                FROM controlled_resilience_evidence
                WHERE raw_prompt_evidence_id = ?
                   OR raw_output_evidence_id = ?
                LIMIT 1
                """,
                (evidence_id, evidence_id),
            ).fetchone()
            if contaminated is not None:
                raise ValidationError(
                    "raw Controlled Governance Resilience evidence is prohibited"
                )
            cross_project = connection.execute(
                """
                SELECT 1
                FROM record_evidence_links AS link
                JOIN records AS record ON record.record_id = link.record_id
                WHERE link.evidence_id = ?
                  AND record.project_scope_id IS NOT NULL
                  AND record.project_scope_id <> ?
                LIMIT 1
                """,
                (evidence_id, envelope.project_scope_id),
            ).fetchone()
            if cross_project is not None:
                raise ValidationError("C2 evidence is already scoped to another project")

    @staticmethod
    def _validate_episode_occurrence(
        connection: sqlite3.Connection,
        envelope: RecordEnvelope,
        payload: EpisodePayload,
    ) -> None:
        session = connection.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (envelope.session_id,),
        ).fetchone()
        if session is None:
            raise ValidationError("episode session does not exist")
        if session["active_project_scope"] != envelope.project_scope_id:
            raise ValidationError("episode session belongs to another project")
        if envelope.task_id is None:
            if (
                session["session_status"] not in {"closed", "aborted"}
                or session["closed_at"] is None
            ):
                raise ValidationError("taskless episode requires a terminal session")
            terminal_at = session["closed_at"]
            allowed = (
                (payload.outcome == "completed" and session["session_status"] == "closed")
                or (
                    payload.outcome in {"partial", "stopped"}
                    and session["session_status"] == "aborted"
                )
            )
        else:
            task = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (envelope.task_id,),
            ).fetchone()
            if task is None:
                raise ValidationError("episode task does not exist")
            if (
                task["session_id"] != envelope.session_id
                or task["project_scope_id"] != envelope.project_scope_id
            ):
                raise ValidationError("episode task/session/project linkage differs")
            if (
                task["status"] not in {"completed", "stopped", "failed"}
                or task["completed_at"] is None
            ):
                raise ValidationError("episode task is not terminal")
            terminal_at = task["completed_at"]
            allowed = (
                (payload.outcome == "completed" and task["status"] == "completed")
                or (payload.outcome == "failed" and task["status"] == "failed")
                or (payload.outcome == "stopped" and task["status"] == "stopped")
                or (
                    payload.outcome == "partial"
                    and task["status"] in {"stopped", "failed"}
                )
                or (
                    payload.outcome == "rejected"
                    and task["status"] == "stopped"
                    and connection.execute(
                        """
                        SELECT 1 FROM task_stop_events
                        WHERE task_id = ? AND governance_forced_stop = 1
                        """,
                        (envelope.task_id,),
                    ).fetchone()
                    is not None
                )
            )
        if not allowed:
            raise ValidationError("episode outcome contradicts occurrence status")
        if envelope.created_at < terminal_at:
            raise ValidationError("episode creation precedes occurrence termination")
        if (
            envelope.effective_from is not None
            and envelope.effective_from < terminal_at
        ):
            raise ValidationError("episode effective time precedes occurrence termination")

    @staticmethod
    def _validate_evaluation_anchors(
        connection: sqlite3.Connection,
        envelope: RecordEnvelope,
        evaluation_record_ids: Sequence[str],
    ) -> None:
        for evaluation_record_id in evaluation_record_ids:
            row = connection.execute(
                """
                SELECT project_scope_id, current_state
                FROM governed_evaluation_record_anchors
                WHERE evaluation_record_id = ?
                """,
                (evaluation_record_id,),
            ).fetchone()
            if row is None:
                raise ValidationError(
                    f"evaluation anchor is missing: {evaluation_record_id}"
                )
            if row["project_scope_id"] != envelope.project_scope_id:
                raise ValidationError("evaluation anchor belongs to another project")
            if row["current_state"] != "claimed":
                raise ValidationError("episode evaluation anchors must be claimed")

    @staticmethod
    def _validate_correction_target(
        connection: sqlite3.Connection,
        envelope: RecordEnvelope,
        payload: CorrectionPayload,
    ) -> None:
        row = connection.execute(
            """
            SELECT record.project_scope_id, record.lifecycle_state,
                   evidence.integrity_status
            FROM episodes AS episode
            JOIN records AS record ON record.record_id = episode.record_id
            JOIN episode_output_evidence AS output
              ON output.record_id = episode.record_id
             AND output.evidence_id = ?
            JOIN evidence_items AS evidence
              ON evidence.evidence_id = output.evidence_id
            WHERE episode.record_id = ?
            """,
            (
                payload.target_output_evidence_id,
                payload.target_episode_id,
            ),
        ).fetchone()
        if row is None:
            raise ValidationError(
                "correction target must be an exact episode output"
            )
        if row["project_scope_id"] != envelope.project_scope_id:
            raise ValidationError("correction target belongs to another project")
        if row["lifecycle_state"] in {"revoked", "deleted"}:
            raise ValidationError("correction target is revoked or deleted")
        if row["integrity_status"] != "valid":
            raise ValidationError("correction target evidence lacks valid integrity")
        issuer = connection.execute(
            "SELECT status FROM entities WHERE entity_id = ?",
            (payload.issued_by_entity_id,),
        ).fetchone()
        if issuer is None or issuer["status"] != "active":
            raise ValidationError("correction issuer must be an active entity")

    @staticmethod
    def _validate_harness_issuer_attribution(
        connection: sqlite3.Connection,
        envelope: RecordEnvelope,
        payload: CorrectionPayload,
        *,
        changed_by_principal: str,
        issuer_authority_record_id: str | None,
        issuer_evidence_id: str | None,
    ) -> None:
        if payload.issuer_class == "approved_evaluator":
            raise ValidationError(
                "current authority contracts cannot prove correction-issuing "
                "permission for approved_evaluator attribution"
            )
        if changed_by_principal != "codex_development_harness":
            return
        allowed = _HUMAN_AUTHORITY_CLASSES.get(payload.issuer_class)
        if (
            allowed is None
            or issuer_authority_record_id is None
            or issuer_evidence_id is None
        ):
            raise ValidationError(
                "harness human attribution requires exact existing authority evidence"
            )
        placeholders = ", ".join("?" for _ in allowed)
        row = connection.execute(
            f"""
            SELECT 1
            FROM authority_records AS authority
            JOIN authority_record_evidence AS authority_evidence
              ON authority_evidence.authority_record_id =
                 authority.authority_record_id
            JOIN evidence_items AS evidence
              ON evidence.evidence_id = authority_evidence.evidence_id
            WHERE authority.authority_record_id = ?
              AND authority_evidence.evidence_id = ?
              AND authority.authority_class IN ({placeholders})
              AND authority.effect = 'allow'
              AND authority.status = 'active'
              AND authority.issuer_entity_id = ?
              AND authority.project_scope_id = ?
              AND authority.effective_from <= ?
              AND (
                  authority.effective_until IS NULL
                  OR authority.effective_until >= ?
              )
              AND evidence.integrity_status = 'valid'
              AND NOT EXISTS (
                  SELECT 1 FROM authority_revocations AS revocation
                  WHERE revocation.authority_record_id =
                        authority.authority_record_id
              )
            """,
            (
                issuer_authority_record_id,
                issuer_evidence_id,
                *sorted(allowed),
                payload.issued_by_entity_id,
                envelope.project_scope_id,
                envelope.created_at,
                envelope.created_at,
            ),
        ).fetchone()
        if row is None:
            raise ValidationError(
                "harness issuer attribution lacks exact active governed authority"
            )

    def create_episode(
        self,
        envelope: RecordEnvelope,
        payload: EpisodePayload,
        *,
        lifecycle_transition_id: str,
        approval_transition_id: str,
        changed_by_principal: str,
        evidence_items: Sequence[EvidenceItem] = (),
        changed_by_entity_id: str | None = None,
        reason_code: str = "episode_created",
    ) -> str:
        """Create one non-active occurrence ledger entry atomically."""

        validate_episode_pair(envelope, payload)
        self._validate_creation_principal(
            envelope,
            changed_by_principal=changed_by_principal,
            changed_by_entity_id=changed_by_entity_id,
        )
        lineage = (*payload.input_evidence_ids, *payload.output_evidence_ids)
        self._validate_new_evidence(evidence_items, allowed_ids=set(lineage))
        digest = episode_content_hash(envelope, payload)

        def operation(connection: sqlite3.Connection) -> None:
            for item in evidence_items:
                _insert_evidence(connection, item)
            self._after_write_step("evidence", connection)
            self._validate_episode_occurrence(connection, envelope, payload)
            self._validate_persisted_evidence(connection, envelope, lineage)
            self._validate_evaluation_anchors(
                connection,
                envelope,
                payload.evaluation_record_ids,
            )
            _insert_record(connection, envelope, content_hash=digest)
            self._after_write_step("record", connection)
            _insert_values(connection, payload.TABLE, payload.database_values())
            connection.executemany(
                """
                INSERT INTO episode_input_evidence (
                    record_id, evidence_id, evidence_order
                ) VALUES (?, ?, ?)
                """,
                (
                    (payload.record_id, evidence_id, order)
                    for order, evidence_id in enumerate(
                        payload.input_evidence_ids
                    )
                ),
            )
            connection.executemany(
                """
                INSERT INTO episode_output_evidence (
                    record_id, evidence_id, evidence_order
                ) VALUES (?, ?, ?)
                """,
                (
                    (payload.record_id, evidence_id, order)
                    for order, evidence_id in enumerate(
                        payload.output_evidence_ids
                    )
                ),
            )
            connection.executemany(
                """
                INSERT INTO episode_evaluation_anchors (
                    record_id, evaluation_record_id, evaluation_order
                ) VALUES (?, ?, ?)
                """,
                (
                    (payload.record_id, evaluation_record_id, order)
                    for order, evaluation_record_id in enumerate(
                        payload.evaluation_record_ids
                    )
                ),
            )
            self._after_write_step("payload_and_lineage", connection)
            connection.executemany(
                """
                INSERT INTO record_evidence_links (
                    record_id, evidence_id, relationship, explanation
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    *(
                        (
                            payload.record_id,
                            evidence_id,
                            "derived_from",
                            "Exact episode input evidence.",
                        )
                        for evidence_id in payload.input_evidence_ids
                    ),
                    *(
                        (
                            payload.record_id,
                            evidence_id,
                            "produced_as",
                            "Exact episode output evidence.",
                        )
                        for evidence_id in payload.output_evidence_ids
                    ),
                ),
            )
            self._after_write_step("evidence_links", connection)
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
            self._after_write_step("histories", connection)

        self._kernel.write(operation)
        return digest

    def create_correction(
        self,
        envelope: RecordEnvelope,
        payload: CorrectionPayload,
        *,
        supporting_evidence_ids: Sequence[str],
        lifecycle_transition_id: str,
        approval_transition_id: str,
        changed_by_principal: str,
        evidence_items: Sequence[EvidenceItem] = (),
        changed_by_entity_id: str | None = None,
        issuer_authority_record_id: str | None = None,
        issuer_evidence_id: str | None = None,
        reason_code: str = "correction_created",
    ) -> str:
        """Create one non-active immutable correction interpretation atomically."""

        validate_correction_pair(envelope, payload)
        self._validate_creation_principal(
            envelope,
            changed_by_principal=changed_by_principal,
            changed_by_entity_id=changed_by_entity_id,
        )
        support = ordered_unique_identifiers(
            supporting_evidence_ids,
            "supporting_evidence_ids",
            allow_empty=False,
        )
        if payload.target_output_evidence_id in support:
            raise ValidationError(
                "correction support must be separate from the target output"
            )
        self._validate_new_evidence(evidence_items, allowed_ids=set(support))
        digest = correction_content_hash(envelope, payload, support)

        def operation(connection: sqlite3.Connection) -> None:
            for item in evidence_items:
                _insert_evidence(connection, item)
            self._after_write_step("evidence", connection)
            self._validate_correction_target(connection, envelope, payload)
            self._validate_persisted_evidence(
                connection,
                envelope,
                (payload.target_output_evidence_id, *support),
            )
            self._validate_harness_issuer_attribution(
                connection,
                envelope,
                payload,
                changed_by_principal=changed_by_principal,
                issuer_authority_record_id=issuer_authority_record_id,
                issuer_evidence_id=issuer_evidence_id,
            )
            _insert_record(connection, envelope, content_hash=digest)
            self._after_write_step("record", connection)
            _insert_values(connection, payload.TABLE, payload.database_values())
            connection.executemany(
                """
                INSERT INTO correction_supporting_evidence (
                    record_id, evidence_id, evidence_order
                ) VALUES (?, ?, ?)
                """,
                (
                    (payload.record_id, evidence_id, order)
                    for order, evidence_id in enumerate(support)
                ),
            )
            self._after_write_step("payload_and_lineage", connection)
            connection.execute(
                """
                INSERT INTO record_evidence_links (
                    record_id, evidence_id, relationship, explanation
                ) VALUES (?, ?, 'derived_from', ?)
                """,
                (
                    payload.record_id,
                    payload.target_output_evidence_id,
                    "Exact corrected episode output.",
                ),
            )
            connection.executemany(
                """
                INSERT INTO record_evidence_links (
                    record_id, evidence_id, relationship, explanation
                ) VALUES (?, ?, 'supports', ?)
                """,
                (
                    (
                        payload.record_id,
                        evidence_id,
                        "Exact correction supporting evidence.",
                    )
                    for evidence_id in support
                ),
            )
            self._after_write_step("evidence_links", connection)
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
            self._after_write_step("histories", connection)

        self._kernel.write(operation)
        return digest

    @staticmethod
    def _common_reconstruction(
        connection: sqlite3.Connection,
        record_id: str,
    ) -> tuple[dict[str, Any], RecordEnvelope]:
        row = connection.execute(
            "SELECT * FROM records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"record not found: {record_id}")
        record = dict(row)
        envelope = _record_envelope(record)
        return record, envelope

    def reconstruct_episode(self, record_id: str) -> Mapping[str, Any]:
        """Rebuild one exact episode with ordered lineage and integrity evidence."""

        validate_identifier(record_id, field="record_id")

        def operation(connection: sqlite3.Connection) -> dict[str, Any]:
            record, envelope = self._common_reconstruction(connection, record_id)
            row = connection.execute(
                "SELECT * FROM episodes WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"episode payload not found: {record_id}")
            inputs = tuple(
                item["evidence_id"]
                for item in connection.execute(
                    """
                    SELECT evidence_id FROM episode_input_evidence
                    WHERE record_id = ? ORDER BY evidence_order
                    """,
                    (record_id,),
                )
            )
            outputs = tuple(
                item["evidence_id"]
                for item in connection.execute(
                    """
                    SELECT evidence_id FROM episode_output_evidence
                    WHERE record_id = ? ORDER BY evidence_order
                    """,
                    (record_id,),
                )
            )
            evaluations = tuple(
                item["evaluation_record_id"]
                for item in connection.execute(
                    """
                    SELECT evaluation_record_id
                    FROM episode_evaluation_anchors
                    WHERE record_id = ? ORDER BY evaluation_order
                    """,
                    (record_id,),
                )
            )
            payload = episode_from_database(
                dict(row),
                input_evidence_ids=inputs,
                output_evidence_ids=outputs,
                evaluation_record_ids=evaluations,
            )
            validate_episode_pair(envelope, payload, for_creation=False)
            recomputed = episode_content_hash(envelope, payload)
            links = [
                dict(item)
                for item in connection.execute(
                    """
                    SELECT * FROM record_evidence_links
                    WHERE record_id = ?
                    ORDER BY evidence_id, relationship
                    """,
                    (record_id,),
                )
            ]
            return {
                "memory_domain": "self_episodic",
                "record": record,
                "payload_type": "episode",
                "payload": payload.canonical_content(),
                "input_evidence_ids": inputs,
                "output_evidence_ids": outputs,
                "evaluation_record_ids": evaluations,
                "evidence_links": links,
                "canonical_json": row["canonical_json"],
                "content_hash": record["content_hash"],
                "recomputed_content_hash": recomputed,
            }

        result = self._kernel.read(operation)
        return self._attach_integrity(result, record_id)

    def reconstruct_correction(self, record_id: str) -> Mapping[str, Any]:
        """Rebuild one exact correction with target and ordered support lineage."""

        validate_identifier(record_id, field="record_id")

        def operation(connection: sqlite3.Connection) -> dict[str, Any]:
            record, envelope = self._common_reconstruction(connection, record_id)
            row = connection.execute(
                "SELECT * FROM corrections WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"correction payload not found: {record_id}")
            support = tuple(
                item["evidence_id"]
                for item in connection.execute(
                    """
                    SELECT evidence_id FROM correction_supporting_evidence
                    WHERE record_id = ? ORDER BY evidence_order
                    """,
                    (record_id,),
                )
            )
            payload = correction_from_database(dict(row))
            validate_correction_pair(envelope, payload, for_creation=False)
            recomputed = correction_content_hash(envelope, payload, support)
            links = [
                dict(item)
                for item in connection.execute(
                    """
                    SELECT * FROM record_evidence_links
                    WHERE record_id = ?
                    ORDER BY evidence_id, relationship
                    """,
                    (record_id,),
                )
            ]
            relationships = [
                dict(item)
                for item in connection.execute(
                    """
                    SELECT * FROM record_relationships
                    WHERE source_record_id = ? OR target_record_id = ?
                    ORDER BY created_at, relationship_id
                    """,
                    (record_id, record_id),
                )
            ]
            return {
                "memory_domain": "self_episodic",
                "record": record,
                "payload_type": "correction",
                "payload": payload.canonical_content(),
                "supporting_evidence_ids": support,
                "evidence_links": links,
                "relationships": relationships,
                "canonical_json": row["canonical_json"],
                "content_hash": record["content_hash"],
                "recomputed_content_hash": recomputed,
            }

        result = self._kernel.read(operation)
        return self._attach_integrity(result, record_id)

    def _attach_integrity(
        self,
        result: dict[str, Any],
        record_id: str,
    ) -> Mapping[str, Any]:
        from .episode_correction_integrity import EpisodeCorrectionIntegrityInspector

        report = EpisodeCorrectionIntegrityInspector(self._kernel).inspect()
        findings = [
            {
                "code": finding.code,
                "severity": finding.severity,
                "record_id": finding.record_id,
                "detail": finding.detail,
            }
            for finding in report.findings
            if finding.record_id in {None, record_id}
        ]
        result["integrity"] = {
            "stored_status": result["record"]["integrity_status"],
            "hash_matches": (
                result["content_hash"] == result["recomputed_content_hash"]
            ),
            "valid": (
                result["record"]["integrity_status"] == "valid"
                and result["content_hash"] == result["recomputed_content_hash"]
                and not any(item["severity"] == "error" for item in findings)
            ),
            "findings": findings,
        }
        return result
