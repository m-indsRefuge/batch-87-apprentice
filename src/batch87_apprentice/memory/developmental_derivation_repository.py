"""Atomic developmental-derivation operations for B87-I3-C3."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import NotFoundError, ValidationError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.persistence.contracts import RecordEnvelope
from batch87_apprentice.persistence.repositories import _insert_record, _insert_values
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .contracts import (
    MemoryApprovalGrant,
    MemoryRelationshipGrant,
    RecordRelationship,
)
from .developmental_derivation_contracts import (
    ApprovedLessonPayload,
    DevelopmentalPayload,
    FailurePatternPayload,
    LessonCandidatePayload,
    SuccessPatternPayload,
    developmental_content_hash,
    validate_developmental_pair,
)
from .episode_correction_contracts import (
    CorrectionPayload,
    EpisodePayload,
    correction_content_hash,
    episode_content_hash,
)
from .kernel import MemoryKernel, _insert_initial_memory_state

_CREATION_PRINCIPALS = frozenset({"operator", "codex_development_harness"})
_C3_TYPES = frozenset(
    {"lesson_candidate", "approved_lesson", "failure_pattern", "success_pattern"}
)


def _record_envelope(row: Mapping[str, Any]) -> RecordEnvelope:
    return RecordEnvelope(
        **{field: row[field] for field in RecordEnvelope.__dataclass_fields__}
    )


def _audit_values(material: Mapping[str, Any]) -> tuple[str, str]:
    value = dict(material)
    return canonical_json_text(value), sha256_canonical_json(value)


class DevelopmentalDerivationRepository:
    """Persist, approve, and reconstruct only the accepted C3 payloads."""

    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel

    def _after_write_step(
        self,
        step: str,
        connection: sqlite3.Connection,
    ) -> None:
        """Test seam used only to prove complete transaction rollback."""

    @staticmethod
    def _validate_creation_principal(
        connection: sqlite3.Connection,
        envelope: RecordEnvelope,
        *,
        changed_by_principal: str,
        changed_by_entity_id: str | None,
        apprentice_origin: bool,
    ) -> None:
        if changed_by_principal not in _CREATION_PRINCIPALS:
            raise ValidationError("unsupported C3 creation principal")
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
            if apprentice_origin:
                raise ValidationError(
                    "Apprentice-origin creation must use governed infrastructure"
                )
            return
        if changed_by_entity_id is not None:
            raise ValidationError(
                "development harness creation cannot claim a human actor"
            )
        if apprentice_origin:
            DevelopmentalDerivationRepository._validate_apprentice_task(
                connection,
                envelope,
            )
        elif envelope.created_by_entity_id is not None:
            raise ValidationError(
                "infrastructure-only creation cannot attribute an entity"
            )

    @staticmethod
    def _validate_apprentice_task(
        connection: sqlite3.Connection,
        envelope: RecordEnvelope,
    ) -> None:
        if envelope.task_id is None or envelope.created_by_entity_id is None:
            raise ValidationError(
                "Apprentice-origin candidate creation requires task and creator"
            )
        row = connection.execute(
            """
            SELECT task.project_scope_id, task.session_id, task.status,
                   task.requesting_principal, task.requested_action_class,
                   task.started_at, task.completed_at,
                   decision.project_scope_id AS decision_project_scope_id,
                   decision.session_id AS decision_session_id,
                   decision.requesting_principal AS decision_principal,
                   decision.requested_action_class AS decision_action_class,
                   decision.decision, decision.apprentice_execute_implication,
                   transaction_record.status AS transaction_status,
                   transaction_record.task_id AS transaction_task_id,
                   entity.entity_kind,
                   entity.status AS entity_status
            FROM tasks AS task
            JOIN governance_decisions AS decision
              ON decision.task_id = task.task_id
            JOIN governed_runtime_transactions AS transaction_record
              ON transaction_record.transaction_id = decision.transaction_id
            JOIN entities AS entity
              ON entity.entity_id = ?
            WHERE task.task_id = ?
            """,
            (envelope.created_by_entity_id, envelope.task_id),
        ).fetchone()
        if (
            row is None
            or row["project_scope_id"] != envelope.project_scope_id
            or row["session_id"] != envelope.session_id
            or row["status"] != "active"
            or row["started_at"] is None
            or row["started_at"] > envelope.created_at
            or row["completed_at"] is not None
            or row["requesting_principal"] != "apprentice"
            or row["requested_action_class"] != "analyse"
            or row["decision_project_scope_id"] != envelope.project_scope_id
            or row["decision_session_id"] != envelope.session_id
            or row["decision_principal"] != "apprentice"
            or row["decision_action_class"] != "analyse"
            or row["decision"] != "allow"
            or row["apprentice_execute_implication"] != 0
            or row["transaction_status"] != "committed"
            or row["transaction_task_id"] != envelope.task_id
            or row["entity_kind"] != "agent"
            or row["entity_status"] != "active"
        ):
            raise ValidationError(
                "Apprentice-origin creation requires one active governed analysis task"
            )

    @staticmethod
    def _ordered_values(
        connection: sqlite3.Connection,
        table: str,
        value_column: str,
        order_column: str,
        record_id: str,
    ) -> tuple[str, ...]:
        return tuple(
            row[value_column]
            for row in connection.execute(
                f"""
                SELECT {value_column}
                FROM {table}
                WHERE record_id = ?
                ORDER BY {order_column}
                """,
                (record_id,),
            )
        )

    @classmethod
    def _validate_source_episode(
        cls,
        connection: sqlite3.Connection,
        episode_id: str,
        *,
        project_scope_id: str,
    ) -> tuple[sqlite3.Row, EpisodePayload]:
        row = connection.execute(
            """
            SELECT record.*, episode.episode_kind, episode.summary,
                   episode.outcome, episode.canonical_json AS payload_json
            FROM records AS record
            JOIN episodes AS episode ON episode.record_id = record.record_id
            WHERE record.record_id = ?
            """,
            (episode_id,),
        ).fetchone()
        if row is None:
            raise ValidationError(f"source episode is missing: {episode_id}")
        if (
            row["record_family"] != "episodic_memory"
            or row["record_type"] != "episode"
            or row["project_scope_id"] != project_scope_id
            or row["lifecycle_state"] in {"revoked", "deleted"}
            or row["integrity_status"] != "valid"
        ):
            raise ValidationError(
                "source episode is invalid, revoked, deleted, or out of scope"
            )
        inputs = cls._ordered_values(
            connection,
            "episode_input_evidence",
            "evidence_id",
            "evidence_order",
            episode_id,
        )
        outputs = cls._ordered_values(
            connection,
            "episode_output_evidence",
            "evidence_id",
            "evidence_order",
            episode_id,
        )
        evaluations = cls._ordered_values(
            connection,
            "episode_evaluation_anchors",
            "evaluation_record_id",
            "evaluation_order",
            episode_id,
        )
        payload = EpisodePayload(
            record_id=episode_id,
            episode_kind=row["episode_kind"],
            summary=row["summary"],
            outcome=row["outcome"],
            input_evidence_ids=inputs,
            output_evidence_ids=outputs,
            evaluation_record_ids=evaluations,
        )
        envelope = _record_envelope(row)
        if (
            row["payload_json"] != payload.canonical_json
            or row["content_hash"] != episode_content_hash(envelope, payload)
        ):
            raise ValidationError("source episode canonical integrity is invalid")
        cls._validate_source_evidence(
            connection,
            episode_id,
            project_scope_id=project_scope_id,
        )
        return row, payload

    @classmethod
    def _validate_source_correction(
        cls,
        connection: sqlite3.Connection,
        correction_id: str,
        *,
        project_scope_id: str,
        accepted_episode_ids: set[str],
    ) -> tuple[sqlite3.Row, CorrectionPayload]:
        row = connection.execute(
            """
            SELECT record.*, correction.target_episode_id,
                   correction.target_output_evidence_id,
                   correction.problem_statement,
                   correction.corrected_interpretation,
                   correction.correction_category,
                   correction.issued_by_entity_id,
                   correction.issuer_class, correction.severity,
                   correction.canonical_json AS payload_json
            FROM records AS record
            JOIN corrections AS correction
              ON correction.record_id = record.record_id
            WHERE record.record_id = ?
            """,
            (correction_id,),
        ).fetchone()
        if row is None:
            raise ValidationError(f"source correction is missing: {correction_id}")
        if (
            row["record_family"] != "episodic_memory"
            or row["record_type"] != "correction"
            or row["project_scope_id"] != project_scope_id
            or row["lifecycle_state"] in {"revoked", "deleted"}
            or row["integrity_status"] != "valid"
        ):
            raise ValidationError(
                "source correction is invalid, revoked, deleted, or out of scope"
            )
        if row["target_episode_id"] not in accepted_episode_ids:
            raise ValidationError(
                "source correction does not target a supplied source episode"
            )
        output = connection.execute(
            """
            SELECT 1 FROM episode_output_evidence
            WHERE record_id = ? AND evidence_id = ?
            """,
            (
                row["target_episode_id"],
                row["target_output_evidence_id"],
            ),
        ).fetchone()
        if output is None:
            raise ValidationError(
                "source correction does not target an exact episode output"
            )
        support = cls._ordered_values(
            connection,
            "correction_supporting_evidence",
            "evidence_id",
            "evidence_order",
            correction_id,
        )
        payload = CorrectionPayload(
            record_id=correction_id,
            target_episode_id=row["target_episode_id"],
            target_output_evidence_id=row["target_output_evidence_id"],
            problem_statement=row["problem_statement"],
            corrected_interpretation=row["corrected_interpretation"],
            correction_category=row["correction_category"],
            issued_by_entity_id=row["issued_by_entity_id"],
            issuer_class=row["issuer_class"],
            severity=row["severity"],
        )
        envelope = _record_envelope(row)
        if (
            row["payload_json"] != payload.canonical_json
            or row["content_hash"]
            != correction_content_hash(envelope, payload, support)
        ):
            raise ValidationError("source correction canonical integrity is invalid")
        cls._validate_source_evidence(
            connection,
            correction_id,
            project_scope_id=project_scope_id,
        )
        return row, payload

    @staticmethod
    def _validate_source_evidence(
        connection: sqlite3.Connection,
        record_id: str,
        *,
        project_scope_id: str,
    ) -> None:
        links = tuple(
            connection.execute(
                """
                SELECT evidence.evidence_id, evidence.integrity_status,
                       evidence.evidence_kind, evidence.sensitivity_class,
                       evidence.privacy_class,
                       controlled.record_id AS controlled_record_id
                FROM record_evidence_links AS link
                JOIN evidence_items AS evidence
                  ON evidence.evidence_id = link.evidence_id
                LEFT JOIN controlled_resilience_evidence AS controlled
                  ON controlled.raw_prompt_evidence_id = evidence.evidence_id
                  OR controlled.raw_output_evidence_id = evidence.evidence_id
                WHERE link.record_id = ?
                """,
                (record_id,),
            )
        )
        if not links:
            raise ValidationError("developmental source lacks linked evidence")
        for row in links:
            if (
                row["integrity_status"] != "valid"
                or row["evidence_kind"]
                in {"controlled_prompt", "controlled_output"}
                or row["controlled_record_id"] is not None
            ):
                raise ValidationError(
                    "controlled or integrity-invalid evidence cannot enter C3 lineage"
                )

    @classmethod
    def _validate_sources(
        cls,
        connection: sqlite3.Connection,
        *,
        project_scope_id: str,
        episode_ids: Sequence[str],
        correction_ids: Sequence[str],
        require_corrections: bool,
    ) -> tuple[dict[str, sqlite3.Row], dict[str, sqlite3.Row]]:
        episodes: dict[str, sqlite3.Row] = {}
        for episode_id in episode_ids:
            row, _ = cls._validate_source_episode(
                connection,
                episode_id,
                project_scope_id=project_scope_id,
            )
            episodes[episode_id] = row
        corrections: dict[str, sqlite3.Row] = {}
        for correction_id in correction_ids:
            row, _ = cls._validate_source_correction(
                connection,
                correction_id,
                project_scope_id=project_scope_id,
                accepted_episode_ids=set(episode_ids),
            )
            corrections[correction_id] = row
        if require_corrections and not corrections:
            raise ValidationError(
                "an approved lesson requires at least one source correction"
            )
        return episodes, corrections

    @staticmethod
    def _source_evidence_ids(
        connection: sqlite3.Connection,
        source_record_ids: Sequence[str],
    ) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[str] = set()
        for source_id in source_record_ids:
            for row in connection.execute(
                """
                SELECT evidence_id
                FROM record_evidence_links
                WHERE record_id = ?
                ORDER BY evidence_id, relationship
                """,
                (source_id,),
            ):
                if row["evidence_id"] not in seen:
                    seen.add(row["evidence_id"])
                    result.append(row["evidence_id"])
        if not result:
            raise ValidationError("C3 lineage must resolve to evidence")
        return tuple(result)

    @staticmethod
    def _insert_source_evidence_links(
        connection: sqlite3.Connection,
        record_id: str,
        evidence_ids: Sequence[str],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO record_evidence_links (
                record_id, evidence_id, relationship, explanation
            ) VALUES (?, ?, 'derived_from', ?)
            """,
            (
                (
                    record_id,
                    evidence_id,
                    "Exact evidence preserved by a normalized C3 source record.",
                )
                for evidence_id in evidence_ids
            ),
        )

    @staticmethod
    def _insert_candidate_payload(
        connection: sqlite3.Connection,
        payload: LessonCandidatePayload,
    ) -> None:
        _insert_values(connection, payload.TABLE, payload.database_values())
        connection.executemany(
            """
            INSERT INTO lesson_candidate_source_episodes (
                record_id, episode_id, source_order
            ) VALUES (?, ?, ?)
            """,
            (
                (payload.record_id, source_id, index)
                for index, source_id in enumerate(payload.source_episode_ids)
            ),
        )
        connection.executemany(
            """
            INSERT INTO lesson_candidate_source_corrections (
                record_id, correction_id, source_order
            ) VALUES (?, ?, ?)
            """,
            (
                (payload.record_id, source_id, index)
                for index, source_id in enumerate(payload.source_correction_ids)
            ),
        )
        connection.executemany(
            """
            INSERT INTO lesson_candidate_limitations (
                record_id, limitation_order, limitation
            ) VALUES (?, ?, ?)
            """,
            (
                (payload.record_id, index, limitation)
                for index, limitation in enumerate(payload.known_limitations)
            ),
        )

    @staticmethod
    def _insert_failure_payload(
        connection: sqlite3.Connection,
        payload: FailurePatternPayload,
    ) -> None:
        _insert_values(connection, payload.TABLE, payload.database_values())
        connection.executemany(
            """
            INSERT INTO failure_pattern_episodes (
                record_id, episode_id, episode_order
            ) VALUES (?, ?, ?)
            """,
            (
                (payload.record_id, episode_id, index)
                for index, episode_id in enumerate(payload.episode_ids)
            ),
        )

    @staticmethod
    def _insert_success_payload(
        connection: sqlite3.Connection,
        payload: SuccessPatternPayload,
    ) -> None:
        _insert_values(connection, payload.TABLE, payload.database_values())
        connection.executemany(
            """
            INSERT INTO success_pattern_episodes (
                record_id, episode_id, episode_order
            ) VALUES (?, ?, ?)
            """,
            (
                (payload.record_id, episode_id, index)
                for index, episode_id in enumerate(payload.episode_ids)
            ),
        )
        connection.executemany(
            """
            INSERT INTO success_pattern_transfer_scopes (
                record_id, scope_order, transfer_scope
            ) VALUES (?, ?, ?)
            """,
            (
                (payload.record_id, index, scope)
                for index, scope in enumerate(payload.transfer_scope)
            ),
        )

    def _create_candidate_bound(
        self,
        envelope: RecordEnvelope,
        payload: LessonCandidatePayload | FailurePatternPayload | SuccessPatternPayload,
        *,
        lifecycle_transition_id: str,
        approval_transition_id: str,
        changed_by_principal: str,
        changed_by_entity_id: str | None,
        reason_code: str,
    ) -> str:
        validate_developmental_pair(envelope, payload)
        validate_identifier(
            lifecycle_transition_id,
            field="lifecycle_transition_id",
        )
        validate_identifier(
            approval_transition_id,
            field="approval_transition_id",
        )
        if payload.RECORD_TYPE == "lesson_candidate":
            episode_ids = payload.source_episode_ids
            correction_ids = payload.source_correction_ids
        else:
            episode_ids = payload.episode_ids
            correction_ids = ()
        digest = developmental_content_hash(envelope, payload)

        def operation(connection: sqlite3.Connection) -> None:
            creator = (
                connection.execute(
                    """
                    SELECT entity_kind
                    FROM entities
                    WHERE entity_id = ?
                    """,
                    (envelope.created_by_entity_id,),
                ).fetchone()
                if envelope.created_by_entity_id is not None
                else None
            )
            if isinstance(payload, LessonCandidatePayload):
                apprentice_origin = payload.proposed_by == "apprentice"
            else:
                apprentice_origin = (
                    creator is not None
                    and creator["entity_kind"] == "agent"
                )
            self._validate_creation_principal(
                connection,
                envelope,
                changed_by_principal=changed_by_principal,
                changed_by_entity_id=changed_by_entity_id,
                apprentice_origin=apprentice_origin,
            )
            if isinstance(payload, LessonCandidatePayload):
                proposer = connection.execute(
                    "SELECT status FROM entities WHERE entity_id = ?",
                    (payload.proposer_entity_id,),
                ).fetchone()
                if proposer is None or proposer["status"] != "active":
                    raise ValidationError("candidate proposer must be active")
                if (
                    apprentice_origin
                    and envelope.created_by_entity_id
                    != payload.proposer_entity_id
                ):
                    raise ValidationError(
                        "Apprentice proposal identity must match record creator"
                    )
            episodes, _ = self._validate_sources(
                connection,
                project_scope_id=envelope.project_scope_id or "",
                episode_ids=episode_ids,
                correction_ids=correction_ids,
                require_corrections=False,
            )
            if isinstance(payload, SuccessPatternPayload):
                task_ids = [row["task_id"] for row in episodes.values()]
                if (
                    any(row["outcome"] != "completed" for row in episodes.values())
                    or any(task_id is None for task_id in task_ids)
                    or len(set(task_ids)) != len(task_ids)
                ):
                    raise ValidationError(
                        "success pattern requires completed episodes across "
                        "distinct tasks"
                    )
            _insert_record(connection, envelope, content_hash=digest)
            self._after_write_step("record", connection)
            if isinstance(payload, LessonCandidatePayload):
                self._insert_candidate_payload(connection, payload)
            elif isinstance(payload, FailurePatternPayload):
                self._insert_failure_payload(connection, payload)
            else:
                self._insert_success_payload(connection, payload)
            self._after_write_step("payload_and_lineage", connection)
            evidence_ids = self._source_evidence_ids(
                connection,
                (*episode_ids, *correction_ids),
            )
            self._insert_source_evidence_links(
                connection,
                envelope.record_id,
                evidence_ids,
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

    def create_lesson_candidate(
        self,
        envelope: RecordEnvelope,
        payload: LessonCandidatePayload,
        *,
        lifecycle_transition_id: str,
        approval_transition_id: str,
        changed_by_principal: str,
        changed_by_entity_id: str | None = None,
        reason_code: str = "lesson_candidate_created",
    ) -> str:
        return self._create_candidate_bound(
            envelope,
            payload,
            lifecycle_transition_id=lifecycle_transition_id,
            approval_transition_id=approval_transition_id,
            changed_by_principal=changed_by_principal,
            changed_by_entity_id=changed_by_entity_id,
            reason_code=reason_code,
        )

    def create_failure_pattern(
        self,
        envelope: RecordEnvelope,
        payload: FailurePatternPayload,
        *,
        lifecycle_transition_id: str,
        approval_transition_id: str,
        changed_by_principal: str,
        changed_by_entity_id: str | None = None,
        reason_code: str = "failure_pattern_created",
    ) -> str:
        return self._create_candidate_bound(
            envelope,
            payload,
            lifecycle_transition_id=lifecycle_transition_id,
            approval_transition_id=approval_transition_id,
            changed_by_principal=changed_by_principal,
            changed_by_entity_id=changed_by_entity_id,
            reason_code=reason_code,
        )

    def create_success_pattern(
        self,
        envelope: RecordEnvelope,
        payload: SuccessPatternPayload,
        *,
        lifecycle_transition_id: str,
        approval_transition_id: str,
        changed_by_principal: str,
        changed_by_entity_id: str | None = None,
        reason_code: str = "success_pattern_created",
    ) -> str:
        return self._create_candidate_bound(
            envelope,
            payload,
            lifecycle_transition_id=lifecycle_transition_id,
            approval_transition_id=approval_transition_id,
            changed_by_principal=changed_by_principal,
            changed_by_entity_id=changed_by_entity_id,
            reason_code=reason_code,
        )

    @classmethod
    def _validated_candidate(
        cls,
        connection: sqlite3.Connection,
        payload: ApprovedLessonPayload,
        *,
        project_scope_id: str,
    ) -> sqlite3.Row:
        candidate = connection.execute(
            """
            SELECT record.*, payload.canonical_json AS payload_json
            FROM records AS record
            JOIN lesson_candidates AS payload
              ON payload.record_id = record.record_id
            WHERE record.record_id = ?
            """,
            (payload.candidate_record_id,),
        ).fetchone()
        if candidate is None:
            raise ValidationError("approved lesson candidate is missing")
        if (
            candidate["record_family"] != "episodic_memory"
            or candidate["record_type"] != "lesson_candidate"
            or candidate["project_scope_id"] != project_scope_id
            or candidate["lifecycle_state"] != "reviewed"
            or candidate["approval_status"] != "pending"
            or candidate["agent_write_policy"] != "candidate_only"
            or candidate["integrity_status"] != "valid"
        ):
            raise ValidationError(
                "approved lesson requires an unchanged reviewed candidate"
            )
        candidate_payload = cls._payload_from_connection(
            connection,
            candidate,
        )
        if not isinstance(candidate_payload, LessonCandidatePayload):
            raise ValidationError("approved lesson candidate has wrong payload type")
        if (
            candidate["payload_json"] != candidate_payload.canonical_json
            or candidate["content_hash"]
            != developmental_content_hash(
                _record_envelope(candidate),
                candidate_payload,
            )
        ):
            raise ValidationError("candidate canonical integrity is invalid")
        if not set(payload.source_episode_ids).issubset(
            candidate_payload.source_episode_ids
        ) or not set(payload.source_correction_ids).issubset(
            candidate_payload.source_correction_ids
        ):
            raise ValidationError("approved lesson adds unsupported sources")
        cls._validate_sources(
            connection,
            project_scope_id=project_scope_id,
            episode_ids=payload.source_episode_ids,
            correction_ids=payload.source_correction_ids,
            require_corrections=True,
        )
        return candidate

    @staticmethod
    def _validate_transfer_tests(
        connection: sqlite3.Connection,
        evaluation_ids: Sequence[str],
        *,
        project_scope_id: str,
    ) -> None:
        for evaluation_id in evaluation_ids:
            row = connection.execute(
                """
                SELECT evaluation.*, evidence.integrity_status,
                       evidence.evidence_kind,
                       controlled.record_id AS controlled_record_id
                FROM governed_evaluation_record_anchors AS evaluation
                JOIN evidence_items AS evidence
                  ON evidence.evidence_id = evaluation.provenance_evidence_id
                LEFT JOIN controlled_resilience_evidence AS controlled
                  ON controlled.raw_prompt_evidence_id = evidence.evidence_id
                  OR controlled.raw_output_evidence_id = evidence.evidence_id
                WHERE evaluation.evaluation_record_id = ?
                """,
                (evaluation_id,),
            ).fetchone()
            if (
                row is None
                or row["evaluation_kind"] != "capability_evaluation"
                or row["project_scope_id"] != project_scope_id
                or row["current_state"] != "claimed"
                or row["integrity_status"] != "valid"
                or row["evidence_kind"]
                in {"model_output", "controlled_prompt", "controlled_output"}
                or row["controlled_record_id"] is not None
            ):
                raise ValidationError(
                    "transfer test must be a claimed same-project capability anchor"
                )

    @staticmethod
    def _insert_approved_payload(
        connection: sqlite3.Connection,
        payload: ApprovedLessonPayload,
    ) -> None:
        _insert_values(connection, payload.TABLE, payload.database_values())
        connection.executemany(
            """
            INSERT INTO approved_lesson_source_episodes (
                record_id, episode_id, source_order
            ) VALUES (?, ?, ?)
            """,
            (
                (payload.record_id, source_id, index)
                for index, source_id in enumerate(payload.source_episode_ids)
            ),
        )
        connection.executemany(
            """
            INSERT INTO approved_lesson_source_corrections (
                record_id, correction_id, source_order
            ) VALUES (?, ?, ?)
            """,
            (
                (payload.record_id, source_id, index)
                for index, source_id in enumerate(payload.source_correction_ids)
            ),
        )
        connection.executemany(
            """
            INSERT INTO approved_lesson_application_conditions (
                record_id, condition_order, condition
            ) VALUES (?, ?, ?)
            """,
            (
                (payload.record_id, index, condition)
                for index, condition in enumerate(payload.application_conditions)
            ),
        )
        connection.executemany(
            """
            INSERT INTO approved_lesson_non_application_conditions (
                record_id, condition_order, condition
            ) VALUES (?, ?, ?)
            """,
            (
                (payload.record_id, index, condition)
                for index, condition in enumerate(
                    payload.non_application_conditions
                )
            ),
        )
        connection.executemany(
            """
            INSERT INTO approved_lesson_transfer_tests (
                record_id, evaluation_record_id, transfer_order
            ) VALUES (?, ?, ?)
            """,
            (
                (payload.record_id, evaluation_id, index)
                for index, evaluation_id in enumerate(
                    payload.transfer_test_evaluation_ids
                )
            ),
        )

    @staticmethod
    def _insert_approval_grant(
        connection: sqlite3.Connection,
        grant: MemoryApprovalGrant,
        *,
        authority_class: str,
    ) -> None:
        canonical, digest = _audit_values(grant.canonical_value())
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
                authority_class,
                grant.approved_by_entity_id,
                grant.approved_at,
                grant.expires_at,
                int(grant.single_use),
                grant.evidence_id,
                canonical,
                digest,
            ),
        )

    @staticmethod
    def _insert_relationship_grant(
        connection: sqlite3.Connection,
        grant: MemoryRelationshipGrant,
        *,
        authority_class: str,
    ) -> None:
        canonical, digest = _audit_values(grant.canonical_value())
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
                authority_class,
                grant.approved_by_entity_id,
                grant.approved_at,
                grant.expires_at,
                int(grant.single_use),
                grant.evidence_id,
                canonical,
                digest,
            ),
        )

    @staticmethod
    def _insert_approval_transition(
        connection: sqlite3.Connection,
        *,
        record_id: str,
        transition_id: str,
        changed_at: str,
        changed_by_entity_id: str,
        grant: MemoryApprovalGrant,
    ) -> None:
        material = {
            "transition_id": transition_id,
            "record_id": record_id,
            "sequence_number": 1,
            "from_status": "pending",
            "to_status": "approved",
            "reason_code": "nolan_byte_lesson_approval",
            "changed_at": changed_at,
            "changed_by_principal": "operator",
            "changed_by_entity_id": changed_by_entity_id,
            "approval_grant_id": grant.grant_id,
            "authority_record_id": grant.authority_record_id,
            "approval_evidence_id": grant.evidence_id,
        }
        canonical, digest = _audit_values(material)
        connection.execute(
            """
            INSERT INTO memory_record_approval_transitions (
                transition_id, record_id, sequence_number, from_status, to_status,
                reason_code, changed_at, changed_by_principal,
                changed_by_entity_id, approval_grant_id,
                authority_record_id, approval_evidence_id,
                canonical_json, content_hash
            ) VALUES (?, ?, 1, 'pending', 'approved', ?, ?, 'operator',
                      ?, ?, ?, ?, ?, ?)
            """,
            (
                transition_id,
                record_id,
                material["reason_code"],
                changed_at,
                changed_by_entity_id,
                grant.grant_id,
                grant.authority_record_id,
                grant.evidence_id,
                canonical,
                digest,
            ),
        )
        if grant.single_use:
            updated = connection.execute(
                """
                UPDATE memory_approval_grants
                SET consumed_at = ?, consumed_by_transition_id = ?
                WHERE grant_id = ? AND consumed_at IS NULL
                """,
                (changed_at, transition_id, grant.grant_id),
            )
            if updated.rowcount != 1:
                raise ValidationError("approval grant was already consumed")
        connection.execute(
            "UPDATE records SET approval_status = 'approved' WHERE record_id = ?",
            (record_id,),
        )

    @staticmethod
    def _insert_lifecycle_transition(
        connection: sqlite3.Connection,
        *,
        record_id: str,
        transition_id: str,
        sequence_number: int,
        from_state: str,
        to_state: str,
        reason_code: str,
        changed_at: str,
        changed_by_entity_id: str,
    ) -> None:
        material = {
            "transition_id": transition_id,
            "record_id": record_id,
            "sequence_number": sequence_number,
            "from_state": from_state,
            "to_state": to_state,
            "reason_code": reason_code,
            "changed_at": changed_at,
            "changed_by_principal": "operator",
            "changed_by_entity_id": changed_by_entity_id,
        }
        canonical, digest = _audit_values(material)
        connection.execute(
            """
            INSERT INTO memory_record_lifecycle_transitions (
                transition_id, record_id, sequence_number, from_state, to_state,
                reason_code, changed_at, changed_by_principal,
                changed_by_entity_id, canonical_json, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'operator', ?, ?, ?)
            """,
            (
                transition_id,
                record_id,
                sequence_number,
                from_state,
                to_state,
                reason_code,
                changed_at,
                changed_by_entity_id,
                canonical,
                digest,
            ),
        )
        connection.execute(
            "UPDATE records SET lifecycle_state = ? WHERE record_id = ?",
            (to_state, record_id),
        )

    @staticmethod
    def _insert_relationship(
        connection: sqlite3.Connection,
        relationship: RecordRelationship,
        grant: MemoryRelationshipGrant,
    ) -> None:
        material = {
            "relationship_id": relationship.relationship_id,
            "source_record_id": relationship.source_record_id,
            "target_record_id": relationship.target_record_id,
            "relationship_type": relationship.relationship_type,
            "created_at": relationship.created_at,
            "created_by_principal": relationship.created_by_principal,
            "relationship_grant_id": relationship.relationship_grant_id,
            "authority_record_id": grant.authority_record_id,
            "approval_evidence_id": grant.evidence_id,
            "explanation": relationship.explanation,
        }
        canonical, digest = _audit_values(material)
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
                grant.authority_record_id,
                grant.evidence_id,
                relationship.explanation,
                canonical,
                digest,
            ),
        )
        if grant.single_use:
            updated = connection.execute(
                """
                UPDATE memory_relationship_grants
                SET consumed_at = ?, consumed_by_relationship_id = ?
                WHERE grant_id = ? AND consumed_at IS NULL
                """,
                (
                    relationship.created_at,
                    relationship.relationship_id,
                    grant.grant_id,
                ),
            )
            if updated.rowcount != 1:
                raise ValidationError("relationship grant was already consumed")

    def create_approved_lesson(
        self,
        envelope: RecordEnvelope,
        payload: ApprovedLessonPayload,
        *,
        initial_lifecycle_transition_id: str,
        initial_approval_transition_id: str,
        approval_transition_id: str,
        approved_lifecycle_transition_id: str,
        active_lifecycle_transition_id: str,
        approval_grant: MemoryApprovalGrant,
        relationship_grant: MemoryRelationshipGrant,
        relationship: RecordRelationship,
    ) -> str:
        """Create, externally approve, relate, and activate one lesson atomically."""

        validate_developmental_pair(envelope, payload)
        for field, value in (
            ("initial_lifecycle_transition_id", initial_lifecycle_transition_id),
            ("initial_approval_transition_id", initial_approval_transition_id),
            ("approval_transition_id", approval_transition_id),
            (
                "approved_lifecycle_transition_id",
                approved_lifecycle_transition_id,
            ),
            ("active_lifecycle_transition_id", active_lifecycle_transition_id),
        ):
            validate_identifier(value, field=field)
        if not isinstance(approval_grant, MemoryApprovalGrant):
            raise TypeError("approval_grant must be a MemoryApprovalGrant")
        if not isinstance(relationship_grant, MemoryRelationshipGrant):
            raise TypeError(
                "relationship_grant must be a MemoryRelationshipGrant"
            )
        if not isinstance(relationship, RecordRelationship):
            raise TypeError("relationship must be a RecordRelationship")
        exact = (
            approval_grant.record_id == envelope.record_id
            and approval_grant.target_status == "approved"
            and approval_grant.project_scope_id == envelope.project_scope_id
            and relationship_grant.relationship_type == "approved_as"
            and relationship_grant.source_record_id
            == payload.candidate_record_id
            and relationship_grant.target_record_id == envelope.record_id
            and relationship_grant.project_scope_id == envelope.project_scope_id
            and relationship.relationship_id
            == relationship_grant.relationship_id
            and relationship.source_record_id == payload.candidate_record_id
            and relationship.target_record_id == envelope.record_id
            and relationship.relationship_type == "approved_as"
            and relationship.relationship_grant_id
            == relationship_grant.grant_id
            and relationship.created_by_principal == "operator"
            and approval_grant.authority_record_id
            == relationship_grant.authority_record_id
            and approval_grant.approved_by_entity_id
            == relationship_grant.approved_by_entity_id
            and approval_grant.evidence_id == relationship_grant.evidence_id
            and approval_grant.single_use
            and relationship_grant.single_use
        )
        if not exact:
            raise ValidationError(
                "approved lesson requires exact single-use approval and "
                "approved_as grants"
            )
        if (
            approval_grant.approved_at > envelope.created_at
            or relationship_grant.approved_at > relationship.created_at
            or relationship.created_at != envelope.created_at
        ):
            raise ValidationError(
                "lesson approval and relationship times are inconsistent"
            )
        digest = developmental_content_hash(envelope, payload)

        def operation(connection: sqlite3.Connection) -> None:
            self._validated_candidate(
                connection,
                payload,
                project_scope_id=envelope.project_scope_id or "",
            )
            self._validate_transfer_tests(
                connection,
                payload.transfer_test_evaluation_ids,
                project_scope_id=envelope.project_scope_id or "",
            )
            self._after_write_step("validated_candidate", connection)
            authority = MemoryKernel._validate_authority_evidence(
                connection,
                authority_record_id=approval_grant.authority_record_id,
                evidence_id=approval_grant.evidence_id,
                approved_by_entity_id=approval_grant.approved_by_entity_id,
                project_scope_id=approval_grant.project_scope_id,
                effective_at=envelope.created_at,
                allowed_authority_classes=frozenset(
                    {"nolan_byte_approved"}
                ),
            )
            if authority["authority_class"] != "nolan_byte_approved":
                raise ValidationError(
                    "approved lesson requires exact Nolan-Byte authority"
                )
            _insert_record(connection, envelope, content_hash=digest)
            self._after_write_step("record", connection)
            self._insert_approved_payload(connection, payload)
            self._after_write_step("payload_and_lineage", connection)
            self._insert_approval_grant(
                connection,
                approval_grant,
                authority_class=authority["authority_class"],
            )
            self._after_write_step("approval_grant", connection)
            self._insert_relationship_grant(
                connection,
                relationship_grant,
                authority_class=authority["authority_class"],
            )
            self._after_write_step("relationship_grant", connection)
            source_evidence = self._source_evidence_ids(
                connection,
                (*payload.source_episode_ids, *payload.source_correction_ids),
            )
            self._insert_source_evidence_links(
                connection,
                envelope.record_id,
                source_evidence,
            )
            connection.execute(
                """
                INSERT INTO record_evidence_links (
                    record_id, evidence_id, relationship, explanation
                ) VALUES (?, ?, 'supports', ?)
                """,
                (
                    envelope.record_id,
                    approval_grant.evidence_id,
                    "Exact Nolan-Byte approval evidence.",
                ),
            )
            self._after_write_step("evidence_links", connection)
            _insert_initial_memory_state(
                connection,
                envelope.record_id,
                lifecycle_transition_id=initial_lifecycle_transition_id,
                approval_transition_id=initial_approval_transition_id,
                changed_at=envelope.created_at,
                changed_by_principal="operator",
                reason_code="approved_lesson_created",
                changed_by_entity_id=approval_grant.approved_by_entity_id,
            )
            self._after_write_step("histories", connection)
            self._insert_approval_transition(
                connection,
                record_id=envelope.record_id,
                transition_id=approval_transition_id,
                changed_at=envelope.created_at,
                changed_by_entity_id=approval_grant.approved_by_entity_id,
                grant=approval_grant,
            )
            self._after_write_step("approval_transition", connection)
            self._insert_lifecycle_transition(
                connection,
                record_id=envelope.record_id,
                transition_id=approved_lifecycle_transition_id,
                sequence_number=1,
                from_state="reviewed",
                to_state="approved",
                reason_code="external_approval_recorded",
                changed_at=envelope.created_at,
                changed_by_entity_id=approval_grant.approved_by_entity_id,
            )
            self._after_write_step("approved_state", connection)
            self._insert_relationship(
                connection,
                relationship,
                relationship_grant,
            )
            self._after_write_step("approved_as_relationship", connection)
            self._insert_lifecycle_transition(
                connection,
                record_id=envelope.record_id,
                transition_id=active_lifecycle_transition_id,
                sequence_number=2,
                from_state="approved",
                to_state="active",
                reason_code="approved_lesson_activated",
                changed_at=envelope.created_at,
                changed_by_entity_id=approval_grant.approved_by_entity_id,
            )
            self._after_write_step("active_state", connection)

        self._kernel.write(operation)
        return digest

    @classmethod
    def _payload_from_connection(
        cls,
        connection: sqlite3.Connection,
        record: Mapping[str, Any],
    ) -> DevelopmentalPayload:
        record_id = record["record_id"]
        record_type = record["record_type"]
        table = {
            "lesson_candidate": "lesson_candidates",
            "approved_lesson": "approved_lessons",
            "failure_pattern": "failure_patterns",
            "success_pattern": "success_patterns",
        }.get(record_type)
        if table is None:
            raise ValidationError("record is not a C3 developmental payload")
        row = connection.execute(
            f"SELECT * FROM {table} WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"C3 payload not found: {record_id}")
        if record_type == "lesson_candidate":
            return LessonCandidatePayload(
                record_id=record_id,
                source_episode_ids=cls._ordered_values(
                    connection,
                    "lesson_candidate_source_episodes",
                    "episode_id",
                    "source_order",
                    record_id,
                ),
                source_correction_ids=cls._ordered_values(
                    connection,
                    "lesson_candidate_source_corrections",
                    "correction_id",
                    "source_order",
                    record_id,
                ),
                lesson_statement=row["lesson_statement"],
                intended_scope=row["intended_scope"],
                proposer_entity_id=row["proposer_entity_id"],
                proposed_by=row["proposed_by"],
                known_limitations=cls._ordered_values(
                    connection,
                    "lesson_candidate_limitations",
                    "limitation",
                    "limitation_order",
                    record_id,
                ),
            )
        if record_type == "approved_lesson":
            return ApprovedLessonPayload(
                record_id=record_id,
                candidate_record_id=row["candidate_record_id"],
                lesson_statement=row["lesson_statement"],
                application_conditions=cls._ordered_values(
                    connection,
                    "approved_lesson_application_conditions",
                    "condition",
                    "condition_order",
                    record_id,
                ),
                non_application_conditions=cls._ordered_values(
                    connection,
                    "approved_lesson_non_application_conditions",
                    "condition",
                    "condition_order",
                    record_id,
                ),
                source_episode_ids=cls._ordered_values(
                    connection,
                    "approved_lesson_source_episodes",
                    "episode_id",
                    "source_order",
                    record_id,
                ),
                source_correction_ids=cls._ordered_values(
                    connection,
                    "approved_lesson_source_corrections",
                    "correction_id",
                    "source_order",
                    record_id,
                ),
                approved_by=row["approved_by"],
                transfer_test_evaluation_ids=cls._ordered_values(
                    connection,
                    "approved_lesson_transfer_tests",
                    "evaluation_record_id",
                    "transfer_order",
                    record_id,
                ),
                stability=row["stability"],
            )
        if record_type == "failure_pattern":
            episodes = cls._ordered_values(
                connection,
                "failure_pattern_episodes",
                "episode_id",
                "episode_order",
                record_id,
            )
            return FailurePatternPayload(
                record_id=record_id,
                pattern_name=row["pattern_name"],
                description=row["description"],
                episode_ids=episodes,
                frequency=row["frequency"],
                severity=row["severity"],
                containment_required=bool(row["containment_required"]),
                resolution_status=row["resolution_status"],
            )
        return SuccessPatternPayload(
            record_id=record_id,
            pattern_name=row["pattern_name"],
            description=row["description"],
            episode_ids=cls._ordered_values(
                connection,
                "success_pattern_episodes",
                "episode_id",
                "episode_order",
                record_id,
            ),
            transfer_scope=cls._ordered_values(
                connection,
                "success_pattern_transfer_scopes",
                "transfer_scope",
                "scope_order",
                record_id,
            ),
            stability=row["stability"],
        )

    def reconstruct(self, record_id: str) -> Mapping[str, Any]:
        validate_identifier(record_id, field="record_id")

        def operation(connection: sqlite3.Connection) -> dict[str, Any]:
            row = connection.execute(
                "SELECT * FROM records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"record not found: {record_id}")
            if row["record_type"] not in _C3_TYPES:
                raise ValidationError("record is not a C3 developmental record")
            payload = self._payload_from_connection(connection, row)
            expected_hash = developmental_content_hash(
                _record_envelope(row),
                payload,
            )
            return {
                "envelope": dict(row),
                "payload": payload.canonical_content(),
                "stored_payload_json": connection.execute(
                    f"""
                    SELECT canonical_json
                    FROM {payload.TABLE}
                    WHERE record_id = ?
                    """,
                    (record_id,),
                ).fetchone()["canonical_json"],
                "expected_content_hash": expected_hash,
                "stored_content_hash": row["content_hash"],
                "integrity_ok": expected_hash == row["content_hash"],
            }

        result = self._kernel.read(operation)
        from .developmental_derivation_integrity import (
            DevelopmentalDerivationIntegrityInspector,
        )

        report = DevelopmentalDerivationIntegrityInspector(
            self._kernel
        ).inspect()
        findings = tuple(
            finding
            for finding in report.findings
            if finding.record_id == record_id
        )
        return {
            **result,
            "integrity_ok": result["integrity_ok"] and not findings,
            "integrity_findings": findings,
        }
