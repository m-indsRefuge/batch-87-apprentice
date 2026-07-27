"""Independent integrity reconstruction for B87-I3-C3 derivation records."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .developmental_derivation_contracts import (
    ApprovedLessonPayload,
    FailurePatternPayload,
    LessonCandidatePayload,
    SuccessPatternPayload,
    developmental_content_hash,
)
from .developmental_derivation_repository import (
    DevelopmentalDerivationRepository,
    _record_envelope,
)

_PAYLOAD_TABLES = {
    "lesson_candidate": "lesson_candidates",
    "approved_lesson": "approved_lessons",
    "failure_pattern": "failure_patterns",
    "success_pattern": "success_patterns",
}
_VALID_HISTORICAL_TASK_STATUSES = frozenset(
    {"active", "completed", "stopped", "failed"}
)


@dataclass(frozen=True, slots=True)
class DevelopmentalDerivationIntegrityFinding:
    severity: str
    code: str
    table: str
    record_id: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class DevelopmentalDerivationIntegrityReport:
    findings: tuple[DevelopmentalDerivationIntegrityFinding, ...]

    @property
    def ok(self) -> bool:
        return all(finding.severity != "error" for finding in self.findings)

    @property
    def error_count(self) -> int:
        return sum(finding.severity == "error" for finding in self.findings)


class DevelopmentalDerivationIntegrityInspector:
    """Reconstruct every C3 payload, lineage, approval, and evidence boundary."""

    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel

    @staticmethod
    def _add(
        findings: list[DevelopmentalDerivationIntegrityFinding],
        code: str,
        table: str,
        record_id: str | None,
        detail: str,
    ) -> None:
        findings.append(
            DevelopmentalDerivationIntegrityFinding(
                severity="error",
                code=code,
                table=table,
                record_id=record_id,
                detail=detail,
            )
        )

    @classmethod
    def _check_order(
        cls,
        connection: sqlite3.Connection,
        findings: list[DevelopmentalDerivationIntegrityFinding],
        *,
        table: str,
        order_column: str,
        record_id: str,
    ) -> None:
        values = [
            row[order_column]
            for row in connection.execute(
                f"""
                SELECT {order_column}
                FROM {table}
                WHERE record_id = ?
                ORDER BY {order_column}
                """,
                (record_id,),
            )
        ]
        if values != list(range(len(values))):
            cls._add(
                findings,
                "I3C3-LINEAGE-ORDER",
                table,
                record_id,
                f"{order_column} is duplicate, gapped, or non-zero-based",
            )

    @classmethod
    def _check_payload_inventory(
        cls,
        connection: sqlite3.Connection,
        findings: list[DevelopmentalDerivationIntegrityFinding],
    ) -> None:
        for record_type, table in _PAYLOAD_TABLES.items():
            for row in connection.execute(
                f"""
                SELECT payload.record_id, record.record_type
                FROM {table} AS payload
                LEFT JOIN records AS record ON record.record_id = payload.record_id
                WHERE record.record_id IS NULL
                   OR record.record_family <> 'episodic_memory'
                   OR record.record_type <> ?
                ORDER BY payload.record_id
                """,
                (record_type,),
            ):
                cls._add(
                    findings,
                    "I3C3-PAYLOAD-TYPE",
                    table,
                    row["record_id"],
                    "payload is orphaned or attached to the wrong exact record type",
                )

    @classmethod
    def _check_lineage_orders(
        cls,
        connection: sqlite3.Connection,
        findings: list[DevelopmentalDerivationIntegrityFinding],
        *,
        record_type: str,
        record_id: str,
    ) -> None:
        tables = {
            "lesson_candidate": (
                ("lesson_candidate_source_episodes", "source_order"),
                ("lesson_candidate_source_corrections", "source_order"),
                ("lesson_candidate_limitations", "limitation_order"),
            ),
            "approved_lesson": (
                ("approved_lesson_source_episodes", "source_order"),
                ("approved_lesson_source_corrections", "source_order"),
                (
                    "approved_lesson_application_conditions",
                    "condition_order",
                ),
                (
                    "approved_lesson_non_application_conditions",
                    "condition_order",
                ),
                ("approved_lesson_transfer_tests", "transfer_order"),
            ),
            "failure_pattern": (
                ("failure_pattern_episodes", "episode_order"),
            ),
            "success_pattern": (
                ("success_pattern_episodes", "episode_order"),
                ("success_pattern_transfer_scopes", "scope_order"),
            ),
        }[record_type]
        for table, order_column in tables:
            cls._check_order(
                connection,
                findings,
                table=table,
                order_column=order_column,
                record_id=record_id,
            )

    @classmethod
    def _check_sources(
        cls,
        connection: sqlite3.Connection,
        findings: list[DevelopmentalDerivationIntegrityFinding],
        *,
        record_id: str,
        project_scope_id: str,
        episode_ids: tuple[str, ...],
        correction_ids: tuple[str, ...],
        require_corrections: bool,
    ) -> None:
        try:
            DevelopmentalDerivationRepository._validate_sources(
                connection,
                project_scope_id=project_scope_id,
                episode_ids=episode_ids,
                correction_ids=correction_ids,
                require_corrections=require_corrections,
            )
        except Exception as exc:
            cls._add(
                findings,
                "I3C3-SOURCE-INTEGRITY",
                "developmental_lineage",
                record_id,
                str(exc),
            )

    @classmethod
    def _check_historical_agent_task_binding(
        cls,
        connection: sqlite3.Connection,
        findings: list[DevelopmentalDerivationIntegrityFinding],
        *,
        record: sqlite3.Row,
        creator_entity_id: str,
    ) -> None:
        task = connection.execute(
            """
            SELECT task.task_id, task.status, task.requesting_principal,
                   task.requested_action_class, task.project_scope_id,
                   task.session_id, task.started_at, task.completed_at,
                   decision.task_id AS decision_task_id,
                   decision.session_id AS decision_session_id,
                   decision.project_scope_id AS decision_project_scope_id,
                   decision.requesting_principal AS decision_principal,
                   decision.requested_action_class AS decision_action_class,
                   decision.decision,
                   decision.apprentice_execute_implication,
                   transaction_record.task_id AS transaction_task_id,
                   transaction_record.status AS transaction_status,
                   creator.entity_kind AS creator_kind
            FROM tasks AS task
            JOIN governance_decisions AS decision
              ON decision.task_id = task.task_id
            JOIN governed_runtime_transactions AS transaction_record
              ON transaction_record.transaction_id = decision.transaction_id
            JOIN entities AS creator ON creator.entity_id = ?
            WHERE task.task_id = ?
            """,
            (creator_entity_id, record["task_id"]),
        ).fetchone()
        if (
            task is None
            or record["created_by_entity_id"] != creator_entity_id
            or task["task_id"] != record["task_id"]
            or task["status"] not in _VALID_HISTORICAL_TASK_STATUSES
            or task["requesting_principal"] != "apprentice"
            or task["requested_action_class"] != "analyse"
            or task["project_scope_id"] != record["project_scope_id"]
            or task["session_id"] != record["session_id"]
            or task["decision_task_id"] != record["task_id"]
            or task["decision_session_id"] != record["session_id"]
            or task["decision_project_scope_id"] != record["project_scope_id"]
            or task["decision_principal"] != "apprentice"
            or task["decision_action_class"] != "analyse"
            or task["decision"] != "allow"
            or task["apprentice_execute_implication"] != 0
            or task["transaction_task_id"] != record["task_id"]
            or task["transaction_status"] != "committed"
            or task["creator_kind"] != "agent"
            or task["started_at"] is None
            or task["started_at"] > record["created_at"]
            or (
                task["status"] == "active"
                and task["completed_at"] is not None
            )
            or (
                task["status"] != "active"
                and (
                    task["completed_at"] is None
                    or task["completed_at"] < record["created_at"]
                )
            )
        ):
            cls._add(
                findings,
                "I3C3-APPRENTICE-TASK",
                "tasks",
                record["record_id"],
                "agent-origin record lacks its exact governed analysis task",
            )

    @classmethod
    def _check_agent_created_pattern_task(
        cls,
        connection: sqlite3.Connection,
        findings: list[DevelopmentalDerivationIntegrityFinding],
        record: sqlite3.Row,
    ) -> None:
        if record["created_by_entity_id"] is None:
            return
        creator = connection.execute(
            """
            SELECT creator.entity_kind,
                   transition.changed_by_principal
            FROM memory_record_lifecycle_transitions AS transition
            LEFT JOIN entities AS creator
              ON creator.entity_id = ?
            WHERE transition.record_id = ?
              AND transition.sequence_number = 0
            """,
            (record["created_by_entity_id"], record["record_id"]),
        ).fetchone()
        if creator is not None and (
            creator["entity_kind"] == "agent"
            or creator["changed_by_principal"] == "codex_development_harness"
        ):
            cls._check_historical_agent_task_binding(
                connection,
                findings,
                record=record,
                creator_entity_id=record["created_by_entity_id"],
            )

    @classmethod
    def _check_candidate(
        cls,
        connection: sqlite3.Connection,
        findings: list[DevelopmentalDerivationIntegrityFinding],
        record: sqlite3.Row,
        payload: LessonCandidatePayload,
    ) -> None:
        record_id = record["record_id"]
        if (
            record["agent_write_policy"] != "candidate_only"
            or record["approval_status"] != "pending"
            or record["lifecycle_state"] not in {"candidate", "reviewed"}
        ):
            cls._add(
                findings,
                "I3C3-CANDIDATE-ISOLATION",
                "records",
                record_id,
                "lesson candidate escaped the inspect-only candidate/pending boundary",
            )
        if payload.proposed_by == "apprentice":
            cls._check_historical_agent_task_binding(
                connection,
                findings,
                record=record,
                creator_entity_id=payload.proposer_entity_id,
            )
        cls._check_sources(
            connection,
            findings,
            record_id=record_id,
            project_scope_id=record["project_scope_id"],
            episode_ids=payload.source_episode_ids,
            correction_ids=payload.source_correction_ids,
            require_corrections=False,
        )

    @classmethod
    def _check_approved_lesson(
        cls,
        connection: sqlite3.Connection,
        findings: list[DevelopmentalDerivationIntegrityFinding],
        record: sqlite3.Row,
        payload: ApprovedLessonPayload,
    ) -> str | None:
        record_id = record["record_id"]
        candidate = connection.execute(
            "SELECT * FROM records WHERE record_id = ?",
            (payload.candidate_record_id,),
        ).fetchone()
        if (
            candidate is None
            or candidate["record_family"] != "episodic_memory"
            or candidate["record_type"] != "lesson_candidate"
            or candidate["record_id"] == record_id
            or candidate["project_scope_id"] != record["project_scope_id"]
            or candidate["lifecycle_state"] != "reviewed"
            or candidate["approval_status"] != "pending"
            or candidate["integrity_status"] != "valid"
        ):
            cls._add(
                findings,
                "I3C3-CANDIDATE-SEPARATION",
                "approved_lessons",
                record_id,
                "approved lesson does not preserve one separate reviewed candidate",
            )
        else:
            try:
                candidate_payload = (
                    DevelopmentalDerivationRepository._payload_from_connection(
                        connection,
                        candidate,
                    )
                )
                if not isinstance(candidate_payload, LessonCandidatePayload):
                    raise ValueError("candidate payload has wrong exact type")
                if not set(payload.source_episode_ids).issubset(
                    candidate_payload.source_episode_ids
                ) or not set(payload.source_correction_ids).issubset(
                    candidate_payload.source_correction_ids
                ):
                    raise ValueError("approved lesson added unsupported sources")
            except Exception as exc:
                cls._add(
                    findings,
                    "I3C3-UNSUPPORTED-SOURCE",
                    "approved_lessons",
                    record_id,
                    str(exc),
                )
        cls._check_sources(
            connection,
            findings,
            record_id=record_id,
            project_scope_id=record["project_scope_id"],
            episode_ids=payload.source_episode_ids,
            correction_ids=payload.source_correction_ids,
            require_corrections=True,
        )
        try:
            DevelopmentalDerivationRepository._validate_transfer_tests(
                connection,
                payload.transfer_test_evaluation_ids,
                project_scope_id=record["project_scope_id"],
            )
        except Exception as exc:
            cls._add(
                findings,
                "I3C3-TRANSFER-TEST",
                "approved_lesson_transfer_tests",
                record_id,
                str(exc),
            )
        relationships = tuple(
            connection.execute(
                """
                SELECT relationship.*, grant.authority_class AS grant_authority,
                       grant.grant_id AS grant_id,
                       grant.authority_record_id AS grant_authority_record_id,
                       grant.approved_by_entity_id AS grant_approver_entity_id,
                       grant.project_scope_id AS grant_project_scope_id,
                       grant.single_use, grant.consumed_at,
                       grant.consumed_by_relationship_id,
                       grant.source_record_id AS grant_source,
                       grant.target_record_id AS grant_target,
                       grant.relationship_type AS grant_type,
                       grant.evidence_id AS grant_evidence
                FROM record_relationships AS relationship
                LEFT JOIN memory_relationship_grants AS grant
                  ON grant.grant_id = relationship.relationship_grant_id
                WHERE relationship.relationship_type = 'approved_as'
                  AND (
                      relationship.source_record_id = ?
                      OR relationship.target_record_id = ?
                  )
                """,
                (payload.candidate_record_id, record_id),
            )
        )
        relationship_valid = len(relationships) == 1
        if relationship_valid:
            relationship = relationships[0]
            relationship_valid = (
                relationship["source_record_id"]
                == payload.candidate_record_id
                and relationship["target_record_id"] == record_id
                and relationship["grant_source"] == payload.candidate_record_id
                and relationship["grant_target"] == record_id
                and relationship["grant_type"] == "approved_as"
                and relationship["grant_authority"] == "nolan_byte_approved"
                and relationship["relationship_grant_id"]
                == relationship["grant_id"]
                and relationship["authority_record_id"]
                == relationship["grant_authority_record_id"]
                and relationship["approval_evidence_id"]
                == relationship["grant_evidence"]
                and relationship["created_by_principal"] == "operator"
                and relationship["grant_project_scope_id"]
                == record["project_scope_id"]
                and (
                    not relationship["single_use"]
                    or (
                        relationship["consumed_at"] is not None
                        and relationship["consumed_by_relationship_id"]
                        == relationship["relationship_id"]
                    )
                )
            )
        if not relationship_valid:
            cls._add(
                findings,
                "I3C3-APPROVED-AS",
                "record_relationships",
                record_id,
                "approved_as is absent, reversed, duplicated, or grant-inconsistent",
            )
        approvals = tuple(
            connection.execute(
                """
                SELECT transition.*, grant.authority_class AS grant_authority,
                       grant.grant_id AS grant_id,
                       grant.record_id AS grant_record_id,
                       grant.target_status AS grant_target_status,
                       grant.authority_record_id AS grant_authority_record_id,
                       grant.approved_by_entity_id AS grant_approver_entity_id,
                       grant.project_scope_id AS grant_project_scope_id,
                       grant.single_use, grant.consumed_at,
                       grant.consumed_by_transition_id,
                       grant.evidence_id AS grant_evidence
                FROM memory_record_approval_transitions AS transition
                LEFT JOIN memory_approval_grants AS grant
                  ON grant.grant_id = transition.approval_grant_id
                WHERE transition.record_id = ?
                  AND transition.to_status = 'approved'
                """,
                (record_id,),
            )
        )
        approval_evidence_id: str | None = None
        approval_valid = len(approvals) == 1
        if approval_valid:
            approval = approvals[0]
            approval_evidence_id = approval["grant_evidence"]
            approval_valid = (
                approval["grant_authority"] == "nolan_byte_approved"
                and approval["approval_grant_id"] == approval["grant_id"]
                and approval["grant_record_id"] == record_id
                and approval["grant_target_status"] == "approved"
                and approval["grant_project_scope_id"]
                == record["project_scope_id"]
                and approval["authority_record_id"]
                == approval["grant_authority_record_id"]
                and approval["approval_evidence_id"]
                == approval["grant_evidence"]
                and approval["changed_by_principal"] == "operator"
                and approval["changed_by_entity_id"]
                == approval["grant_approver_entity_id"]
                and (
                    not approval["single_use"]
                    or (
                        approval["consumed_at"] is not None
                        and approval["consumed_by_transition_id"]
                        == approval["transition_id"]
                    )
                )
            )
        if not approval_valid:
            cls._add(
                findings,
                "I3C3-APPROVAL-GRANT",
                "memory_approval_grants",
                record_id,
                "approved lesson lacks one exact consumed Nolan-Byte approval",
            )
        if (
            relationship_valid
            and approval_valid
            and (
                relationship["grant_authority_record_id"]
                != approval["grant_authority_record_id"]
                or relationship["grant_approver_entity_id"]
                != approval["grant_approver_entity_id"]
                or relationship["grant_evidence"] != approval["grant_evidence"]
            )
        ):
            relationship_valid = False
            approval_valid = False
            cls._add(
                findings,
                "I3C3-GRANT-CONSISTENCY",
                "memory_approval_grants",
                record_id,
                "approval and approved_as grants do not share exact authority",
            )
        if (
            record["lifecycle_state"] == "active"
            and (
                record["approval_status"] != "approved"
                or not approval_valid
                or not relationship_valid
            )
        ):
            cls._add(
                findings,
                "I3C3-ACTIVE-WITHOUT-APPROVAL",
                "records",
                record_id,
                "active approved lesson lacks exact approval or approved_as evidence",
            )
        return approval_evidence_id

    @classmethod
    def _check_failure_pattern(
        cls,
        connection: sqlite3.Connection,
        findings: list[DevelopmentalDerivationIntegrityFinding],
        record: sqlite3.Row,
        payload: FailurePatternPayload,
    ) -> None:
        cls._check_agent_created_pattern_task(
            connection,
            findings,
            record,
        )
        if len(payload.episode_ids) < 2 or payload.frequency != len(
            payload.episode_ids
        ):
            cls._add(
                findings,
                "I3C3-FAILURE-FREQUENCY",
                "failure_pattern_episodes",
                record["record_id"],
                "failure frequency differs from multiple distinct episodes",
            )
        cls._check_sources(
            connection,
            findings,
            record_id=record["record_id"],
            project_scope_id=record["project_scope_id"],
            episode_ids=payload.episode_ids,
            correction_ids=(),
            require_corrections=False,
        )

    @classmethod
    def _check_success_pattern(
        cls,
        connection: sqlite3.Connection,
        findings: list[DevelopmentalDerivationIntegrityFinding],
        record: sqlite3.Row,
        payload: SuccessPatternPayload,
    ) -> None:
        cls._check_agent_created_pattern_task(
            connection,
            findings,
            record,
        )
        cls._check_sources(
            connection,
            findings,
            record_id=record["record_id"],
            project_scope_id=record["project_scope_id"],
            episode_ids=payload.episode_ids,
            correction_ids=(),
            require_corrections=False,
        )
        rows = tuple(
            connection.execute(
                """
                SELECT episode.record_id, episode.outcome, record.task_id
                FROM success_pattern_episodes AS source
                LEFT JOIN episodes AS episode
                  ON episode.record_id = source.episode_id
                LEFT JOIN records AS record
                  ON record.record_id = episode.record_id
                WHERE source.record_id = ?
                ORDER BY source.episode_order
                """,
                (record["record_id"],),
            )
        )
        task_ids = [row["task_id"] for row in rows]
        if (
            len(rows) < 2
            or any(row["outcome"] != "completed" for row in rows)
            or any(task_id is None for task_id in task_ids)
            or len(set(task_ids)) != len(task_ids)
            or not payload.transfer_scope
        ):
            cls._add(
                findings,
                "I3C3-SUCCESS-REPETITION",
                "success_pattern_episodes",
                record["record_id"],
                "success pattern lacks distinct completed tasks or transfer scope",
            )

    @classmethod
    def _check_evidence(
        cls,
        connection: sqlite3.Connection,
        findings: list[DevelopmentalDerivationIntegrityFinding],
        *,
        record: sqlite3.Row,
        source_ids: tuple[str, ...],
        approval_evidence_id: str | None,
    ) -> None:
        expected_ids = set(
            DevelopmentalDerivationRepository._source_evidence_ids(
                connection,
                source_ids,
            )
        )
        expected = {(evidence_id, "derived_from") for evidence_id in expected_ids}
        if approval_evidence_id is not None:
            expected.add((approval_evidence_id, "supports"))
        actual_rows = tuple(
            connection.execute(
                """
                SELECT link.evidence_id, link.relationship,
                       evidence.integrity_status, evidence.evidence_kind,
                       controlled.record_id AS controlled_record_id
                FROM record_evidence_links AS link
                LEFT JOIN evidence_items AS evidence
                  ON evidence.evidence_id = link.evidence_id
                LEFT JOIN controlled_resilience_evidence AS controlled
                  ON controlled.raw_prompt_evidence_id = link.evidence_id
                  OR controlled.raw_output_evidence_id = link.evidence_id
                WHERE link.record_id = ?
                """,
                (record["record_id"],),
            )
        )
        actual = {
            (row["evidence_id"], row["relationship"]) for row in actual_rows
        }
        if actual != expected:
            cls._add(
                findings,
                "I3C3-EVIDENCE-COMPLETENESS",
                "record_evidence_links",
                record["record_id"],
                "evidence links differ from exact source and approval evidence",
            )
        if any(
            row["integrity_status"] != "valid"
            or row["evidence_kind"] in {"controlled_prompt", "controlled_output"}
            or row["controlled_record_id"] is not None
            for row in actual_rows
        ):
            cls._add(
                findings,
                "I3C3-CGR-CONTAMINATION",
                "record_evidence_links",
                record["record_id"],
                "controlled or integrity-invalid evidence entered C3 lineage",
            )

    @classmethod
    def _inspect_record(
        cls,
        connection: sqlite3.Connection,
        findings: list[DevelopmentalDerivationIntegrityFinding],
        record: sqlite3.Row,
    ) -> None:
        record_id = record["record_id"]
        record_type = record["record_type"]
        if (
            record["lifecycle_state"] == "active"
            and record["approval_status"] != "approved"
        ):
            cls._add(
                findings,
                "I3C3-ACTIVE-WITHOUT-APPROVAL",
                "records",
                record_id,
                "active developmental record is not externally approved",
            )
        counts = {
            payload_type: connection.execute(
                f"SELECT COUNT(*) AS value FROM {table} WHERE record_id = ?",
                (record_id,),
            ).fetchone()["value"]
            for payload_type, table in _PAYLOAD_TABLES.items()
        }
        if counts.get(record_type) != 1 or sum(counts.values()) != 1:
            cls._add(
                findings,
                "I3C3-PAYLOAD-EXACTNESS",
                "records",
                record_id,
                "record lacks exactly one payload of its exact registered type",
            )
            return
        cls._check_lineage_orders(
            connection,
            findings,
            record_type=record_type,
            record_id=record_id,
        )
        try:
            payload = DevelopmentalDerivationRepository._payload_from_connection(
                connection,
                record,
            )
        except Exception as exc:
            cls._add(
                findings,
                "I3C3-PAYLOAD-RECONSTRUCTION",
                _PAYLOAD_TABLES[record_type],
                record_id,
                str(exc),
            )
            return
        stored_json = connection.execute(
            f"""
            SELECT canonical_json FROM {_PAYLOAD_TABLES[record_type]}
            WHERE record_id = ?
            """,
            (record_id,),
        ).fetchone()["canonical_json"]
        if stored_json != payload.canonical_json:
            cls._add(
                findings,
                "I3C3-CANONICAL-JSON",
                _PAYLOAD_TABLES[record_type],
                record_id,
                "stored canonical JSON differs from normalized reconstruction",
            )
        try:
            expected_hash = developmental_content_hash(
                _record_envelope(record),
                payload,
            )
        except Exception as exc:
            cls._add(
                findings,
                "I3C3-ENVELOPE",
                "records",
                record_id,
                str(exc),
            )
            return
        if record["content_hash"] != expected_hash:
            cls._add(
                findings,
                "I3C3-CONTENT-HASH",
                "records",
                record_id,
                "record hash differs from envelope and normalized payload",
            )
        approval_evidence_id: str | None = None
        if isinstance(payload, LessonCandidatePayload):
            cls._check_candidate(connection, findings, record, payload)
            source_ids = (
                *payload.source_episode_ids,
                *payload.source_correction_ids,
            )
        elif isinstance(payload, ApprovedLessonPayload):
            approval_evidence_id = cls._check_approved_lesson(
                connection,
                findings,
                record,
                payload,
            )
            source_ids = (
                *payload.source_episode_ids,
                *payload.source_correction_ids,
            )
        elif isinstance(payload, FailurePatternPayload):
            cls._check_failure_pattern(connection, findings, record, payload)
            source_ids = payload.episode_ids
        else:
            cls._check_success_pattern(connection, findings, record, payload)
            source_ids = payload.episode_ids
        try:
            cls._check_evidence(
                connection,
                findings,
                record=record,
                source_ids=tuple(source_ids),
                approval_evidence_id=approval_evidence_id,
            )
        except Exception as exc:
            cls._add(
                findings,
                "I3C3-EVIDENCE-RECONSTRUCTION",
                "record_evidence_links",
                record_id,
                str(exc),
            )
    @classmethod
    def _check_grant_hashes(
        cls,
        connection: sqlite3.Connection,
        findings: list[DevelopmentalDerivationIntegrityFinding],
    ) -> None:
        for table, id_column, fields in (
            (
                "memory_approval_grants",
                "grant_id",
                (
                    "grant_id",
                    "record_id",
                    "target_status",
                    "operation",
                    "project_scope_id",
                    "authority_record_id",
                    "approved_by_entity_id",
                    "approved_at",
                    "expires_at",
                    "single_use",
                    "evidence_id",
                ),
            ),
            (
                "memory_relationship_grants",
                "grant_id",
                (
                    "grant_id",
                    "relationship_id",
                    "relationship_type",
                    "source_record_id",
                    "target_record_id",
                    "operation",
                    "project_scope_id",
                    "authority_record_id",
                    "approved_by_entity_id",
                    "approved_at",
                    "expires_at",
                    "single_use",
                    "evidence_id",
                ),
            ),
        ):
            query = (
                """
                SELECT grant.*
                FROM memory_relationship_grants AS grant
                JOIN approved_lessons AS approved
                  ON approved.record_id = grant.target_record_id
                WHERE grant.relationship_type = 'approved_as'
                """
                if table == "memory_relationship_grants"
                else """
                SELECT grant.*
                FROM memory_approval_grants AS grant
                JOIN records AS record ON record.record_id = grant.record_id
                WHERE record.record_type = 'approved_lesson'
                """
            )
            for row in connection.execute(query):
                material = {
                    field: (
                        bool(row[field])
                        if field == "single_use"
                        else row[field]
                    )
                    for field in fields
                }
                if (
                    row["canonical_json"] != canonical_json_text(material)
                    or row["content_hash"] != sha256_canonical_json(material)
                ):
                    cls._add(
                        findings,
                        "I3C3-GRANT-HASH",
                        table,
                        row[id_column],
                        "grant canonical JSON or content hash is invalid",
                    )

    @classmethod
    def _inspect_connection(
        cls,
        connection: sqlite3.Connection,
    ) -> DevelopmentalDerivationIntegrityReport:
        findings: list[DevelopmentalDerivationIntegrityFinding] = []
        cls._check_payload_inventory(connection, findings)
        for record in connection.execute(
            """
            SELECT *
            FROM records
            WHERE record_family = 'episodic_memory'
              AND record_type IN (
                  'lesson_candidate', 'approved_lesson',
                  'failure_pattern', 'success_pattern'
              )
            ORDER BY record_id
            """
        ):
            cls._inspect_record(connection, findings, record)
        cls._check_grant_hashes(connection, findings)
        ordered = tuple(
            sorted(
                findings,
                key=lambda item: (
                    item.code,
                    item.table,
                    item.record_id or "",
                    item.detail,
                ),
            )
        )
        return DevelopmentalDerivationIntegrityReport(findings=ordered)

    def inspect(self) -> DevelopmentalDerivationIntegrityReport:
        return self._kernel.read(self._inspect_connection)
