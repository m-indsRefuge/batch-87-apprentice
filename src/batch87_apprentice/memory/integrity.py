"""Read-only integrity inspection for the B87-I3-A shared memory kernel."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import canonical_json_text, parse_json
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .contracts import (
    ELIGIBILITY_REASON_ORDER,
    GOVERNED_RELATIONSHIP_TYPES,
    MEMORY_APPROVAL_AUTHORITY_CLASSES,
    MEMORY_DOMAINS,
    MEMORY_RECORD_POLICIES,
    NOLAN_INCLUSIVE_AUTHORITY_CLASSES,
    EligibilityContext,
    approval_authority_classes_for,
    memory_domain_for,
)
from .eligibility import evaluate_memory_eligibility


@dataclass(frozen=True, slots=True)
class MemoryIntegrityFinding:
    code: str
    severity: str
    record_id: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class MemoryIntegrityReport:
    findings: tuple[MemoryIntegrityFinding, ...]

    @property
    def ok(self) -> bool:
        return not any(finding.severity == "error" for finding in self.findings)


class MemoryIntegrityInspector:
    def __init__(self, config: DatabaseConfig) -> None:
        self._kernel = PersistenceKernel(config)

    @staticmethod
    def _finding(
        findings: list[MemoryIntegrityFinding],
        code: str,
        record_id: str | None,
        detail: str,
    ) -> None:
        findings.append(MemoryIntegrityFinding(code, "error", record_id, detail))

    @classmethod
    def _check_canonical_row(
        cls,
        findings: list[MemoryIntegrityFinding],
        *,
        table: str,
        row: sqlite3.Row,
        fields: tuple[str, ...],
        record_id: str | None,
    ) -> None:
        material = {field: row[field] for field in fields}
        try:
            parsed = parse_json(row["canonical_json"])
        except Exception:
            cls._finding(
                findings,
                "I3A-CANONICAL-JSON",
                record_id,
                f"{table} contains invalid canonical JSON",
            )
            return
        if canonical_json_text(parsed) != row["canonical_json"] or parsed != material:
            cls._finding(
                findings,
                "I3A-CANONICAL-COLUMN-MISMATCH",
                record_id,
                f"{table} canonical content differs from its stored columns",
            )
        if sha256_canonical_json(parsed) != row["content_hash"]:
            cls._finding(
                findings,
                "I3A-HASH-MISMATCH",
                record_id,
                f"{table} contains a content-hash mismatch",
            )

    def inspect(self) -> MemoryIntegrityReport:
        def operation(connection: sqlite3.Connection) -> MemoryIntegrityReport:
            findings: list[MemoryIntegrityFinding] = []

            domain_rows = connection.execute(
                "SELECT memory_domain, status FROM memory_domains ORDER BY memory_domain"
            ).fetchall()
            domains = tuple(row["memory_domain"] for row in domain_rows)
            if set(domains) != set(MEMORY_DOMAINS) or len(domains) != 3:
                self._finding(
                    findings,
                    "I3A-DOMAIN-COUNT",
                    None,
                    f"expected exactly three domains, found {domains!r}",
                )
            if any(row["status"] != "active" for row in domain_rows):
                self._finding(
                    findings,
                    "I3A-DOMAIN-STATUS",
                    None,
                    "all three canonical memory domains must remain active",
                )

            stored_policies = {
                (row["record_family"], row["record_type"]): (
                    row["memory_domain"],
                    row["approval_requirement"],
                    row["agent_write_policy"],
                )
                for row in connection.execute(
                    """
                    SELECT record_family, record_type, memory_domain,
                           approval_requirement, agent_write_policy, status
                    FROM memory_record_types
                    WHERE status = 'active'
                    """
                )
            }
            if stored_policies != dict(MEMORY_RECORD_POLICIES):
                self._finding(
                    findings,
                    "I3A-RECORD-TYPE-REGISTRY",
                    None,
                    "stored memory record policy registry differs from code",
                )

            stored_approval_authorities: dict[tuple[str, str], set[str]] = {}
            for row in connection.execute(
                """
                SELECT record_family, record_type, authority_class
                FROM memory_record_approval_authorities
                """
            ):
                stored_approval_authorities.setdefault(
                    (row["record_family"], row["record_type"]),
                    set(),
                ).add(row["authority_class"])
            if {
                key: frozenset(value)
                for key, value in stored_approval_authorities.items()
            } != dict(MEMORY_APPROVAL_AUTHORITY_CLASSES):
                self._finding(
                    findings,
                    "I3A-APPROVAL-AUTHORITY-REGISTRY",
                    None,
                    "stored memory approval matrix differs from code",
                )

            for grant in connection.execute("SELECT * FROM memory_approval_grants"):
                self._check_canonical_row(
                    findings,
                    table="memory_approval_grants",
                    row=grant,
                    fields=(
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
                    record_id=grant["record_id"],
                )
                record = connection.execute(
                    "SELECT record_family, record_type FROM records WHERE record_id = ?",
                    (grant["record_id"],),
                ).fetchone()
                if (
                    record is None
                    or grant["authority_class"]
                    not in approval_authority_classes_for(
                        record["record_family"], record["record_type"]
                    )
                ):
                    self._finding(
                        findings,
                        "I3A-APPROVAL-GRANT-POLICY",
                        grant["record_id"],
                        "approval grant does not match the type-specific matrix",
                    )
                if grant["single_use"] and grant["consumed_at"] is not None:
                    transition = connection.execute(
                        """
                        SELECT 1 FROM memory_record_approval_transitions
                        WHERE transition_id = ? AND approval_grant_id = ?
                        """,
                        (grant["consumed_by_transition_id"], grant["grant_id"]),
                    ).fetchone()
                    if transition is None:
                        self._finding(
                            findings,
                            "I3A-APPROVAL-GRANT-CONSUMPTION",
                            grant["record_id"],
                            "consumed approval grant lacks its exact transition",
                        )
                if not grant["single_use"] and grant["consumed_at"] is not None:
                    self._finding(
                        findings,
                        "I3A-APPROVAL-GRANT-CONSUMPTION",
                        grant["record_id"],
                        "reusable approval grant was marked consumed",
                    )

            for grant in connection.execute("SELECT * FROM memory_relationship_grants"):
                self._check_canonical_row(
                    findings,
                    table="memory_relationship_grants",
                    row=grant,
                    fields=(
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
                    record_id=grant["source_record_id"],
                )
                if grant["authority_class"] not in NOLAN_INCLUSIVE_AUTHORITY_CLASSES:
                    self._finding(
                        findings,
                        "I3A-RELATIONSHIP-GRANT-POLICY",
                        grant["source_record_id"],
                        "governed relationship grant is not Nolan-inclusive",
                    )
                if grant["single_use"] and grant["consumed_at"] is not None:
                    relationship = connection.execute(
                        """
                        SELECT 1 FROM record_relationships
                        WHERE relationship_id = ? AND relationship_grant_id = ?
                        """,
                        (grant["consumed_by_relationship_id"], grant["grant_id"]),
                    ).fetchone()
                    if relationship is None:
                        self._finding(
                            findings,
                            "I3A-RELATIONSHIP-GRANT-CONSUMPTION",
                            grant["source_record_id"],
                            "consumed relationship grant lacks its exact relationship",
                        )
                if not grant["single_use"] and grant["consumed_at"] is not None:
                    self._finding(
                        findings,
                        "I3A-RELATIONSHIP-GRANT-CONSUMPTION",
                        grant["source_record_id"],
                        "reusable relationship grant was marked consumed",
                    )

            records = connection.execute(
                """
                SELECT record_id, record_family, record_type, project_scope_id,
                       lifecycle_state, approval_status, integrity_status
                FROM records
                """
            ).fetchall()
            for record in records:
                domain = memory_domain_for(
                    record["record_family"], record["record_type"]
                )
                if domain is None:
                    continue
                record_id = record["record_id"]
                lifecycle = connection.execute(
                    """
                    SELECT * FROM memory_record_lifecycle_transitions
                    WHERE record_id = ? ORDER BY sequence_number
                    """,
                    (record_id,),
                ).fetchall()
                approvals = connection.execute(
                    """
                    SELECT * FROM memory_record_approval_transitions
                    WHERE record_id = ? ORDER BY sequence_number
                    """,
                    (record_id,),
                ).fetchall()

                if not lifecycle or lifecycle[0]["sequence_number"] != 0:
                    self._finding(
                        findings,
                        "I3A-LIFECYCLE-MISSING",
                        record_id,
                        "memory record has no initial lifecycle transition",
                    )
                else:
                    expected_from = None
                    for expected_sequence, transition in enumerate(lifecycle):
                        if transition["sequence_number"] != expected_sequence:
                            self._finding(
                                findings,
                                "I3A-LIFECYCLE-SEQUENCE",
                                record_id,
                                "lifecycle sequence is not contiguous",
                            )
                            break
                        if transition["from_state"] != expected_from:
                            self._finding(
                                findings,
                                "I3A-LIFECYCLE-CONTINUITY",
                                record_id,
                                "lifecycle transition chain is discontinuous",
                            )
                            break
                        expected_from = transition["to_state"]
                        self._check_canonical_row(
                            findings,
                            table="memory_record_lifecycle_transitions",
                            row=transition,
                            fields=(
                                "transition_id",
                                "record_id",
                                "sequence_number",
                                "from_state",
                                "to_state",
                                "reason_code",
                                "changed_at",
                                "changed_by_principal",
                                "changed_by_entity_id",
                            ),
                            record_id=record_id,
                        )
                    if lifecycle[-1]["to_state"] != record["lifecycle_state"]:
                        self._finding(
                            findings,
                            "I3A-LIFECYCLE-MISMATCH",
                            record_id,
                            "latest lifecycle transition differs from current record state",
                        )

                if not approvals or approvals[0]["sequence_number"] != 0:
                    self._finding(
                        findings,
                        "I3A-APPROVAL-MISSING",
                        record_id,
                        "memory record has no initial approval transition",
                    )
                else:
                    expected_from_status = None
                    for expected_sequence, transition in enumerate(approvals):
                        if transition["sequence_number"] != expected_sequence:
                            self._finding(
                                findings,
                                "I3A-APPROVAL-SEQUENCE",
                                record_id,
                                "approval sequence is not contiguous",
                            )
                            break
                        if transition["from_status"] != expected_from_status:
                            self._finding(
                                findings,
                                "I3A-APPROVAL-CONTINUITY",
                                record_id,
                                "approval transition chain is discontinuous",
                            )
                            break
                        expected_from_status = transition["to_status"]
                        self._check_canonical_row(
                            findings,
                            table="memory_record_approval_transitions",
                            row=transition,
                            fields=(
                                "transition_id",
                                "record_id",
                                "sequence_number",
                                "from_status",
                                "to_status",
                                "reason_code",
                                "changed_at",
                                "changed_by_principal",
                                "changed_by_entity_id",
                                "approval_grant_id",
                                "authority_record_id",
                                "approval_evidence_id",
                            ),
                            record_id=record_id,
                        )
                        if transition["sequence_number"] > 0:
                            grant = connection.execute(
                                """
                                SELECT * FROM memory_approval_grants
                                WHERE grant_id = ?
                                """,
                                (transition["approval_grant_id"],),
                            ).fetchone()
                            allowed = approval_authority_classes_for(
                                record["record_family"],
                                record["record_type"],
                            )
                            if (
                                grant is None
                                or grant["record_id"] != record_id
                                or grant["target_status"] != transition["to_status"]
                                or grant["authority_record_id"]
                                != transition["authority_record_id"]
                                or grant["evidence_id"]
                                != transition["approval_evidence_id"]
                                or grant["authority_class"] not in allowed
                                or (
                                    grant["single_use"]
                                    and (
                                        grant["consumed_at"] is None
                                        or grant["consumed_by_transition_id"]
                                        != transition["transition_id"]
                                    )
                                )
                            ):
                                self._finding(
                                    findings,
                                    "I3A-APPROVAL-GRANT",
                                    record_id,
                                    "approval transition lacks its exact consumed grant",
                                )
                            authority = connection.execute(
                                """
                                SELECT authority_class, status, effect,
                                       project_scope_id, issuer_entity_id,
                                       effective_from, effective_until
                                FROM authority_records
                                WHERE authority_record_id = ?
                                """,
                                (transition["authority_record_id"],),
                            ).fetchone()
                            if (
                                authority is None
                                or authority["status"] != "active"
                                or authority["effect"] != "allow"
                                or authority["effective_from"] > transition["changed_at"]
                                or (
                                    authority["effective_until"] is not None
                                    and authority["effective_until"]
                                    < transition["changed_at"]
                                )
                                or authority["project_scope_id"]
                                != record["project_scope_id"]
                                or authority["authority_class"] not in allowed
                                or (
                                    authority["issuer_entity_id"] is not None
                                    and authority["issuer_entity_id"]
                                    != transition["changed_by_entity_id"]
                                )
                            ):
                                self._finding(
                                    findings,
                                    "I3A-APPROVAL-AUTHORITY",
                                    record_id,
                                    "approval grant lacks valid type-specific authority",
                                )
                            linked_evidence = connection.execute(
                                """
                                SELECT 1
                                FROM authority_record_evidence AS authority_evidence
                                JOIN evidence_items AS evidence
                                  ON evidence.evidence_id = authority_evidence.evidence_id
                                WHERE authority_evidence.authority_record_id = ?
                                  AND evidence.evidence_id = ?
                                  AND evidence.integrity_status = 'valid'
                                  AND evidence.evidence_kind NOT IN (
                                      'model_output', 'controlled_prompt', 'controlled_output'
                                  )
                                """,
                                (
                                    transition["authority_record_id"],
                                    transition["approval_evidence_id"],
                                ),
                            ).fetchone()
                            if linked_evidence is None:
                                self._finding(
                                    findings,
                                    "I3A-APPROVAL-EVIDENCE",
                                    record_id,
                                    "approval evidence is not valid and authority-linked",
                                )
                            revoked = connection.execute(
                                """
                                SELECT 1 FROM authority_revocations
                                WHERE authority_record_id = ?
                                """,
                                (transition["authority_record_id"],),
                            ).fetchone()
                            if revoked is not None:
                                self._finding(
                                    findings,
                                    "I3A-APPROVAL-REVOKED",
                                    record_id,
                                    "approval transition uses revoked authority",
                                )
                    if approvals[-1]["to_status"] != record["approval_status"]:
                        self._finding(
                            findings,
                            "I3A-APPROVAL-MISMATCH",
                            record_id,
                            "latest approval transition differs from current approval state",
                        )

                if record["lifecycle_state"] == "active":
                    evidence_count = connection.execute(
                        """
                        SELECT COUNT(*) AS value FROM record_evidence_links
                        WHERE record_id = ?
                        """,
                        (record_id,),
                    ).fetchone()["value"]
                    if int(evidence_count) < 1:
                        self._finding(
                            findings,
                            "I3A-ACTIVE-WITHOUT-EVIDENCE",
                            record_id,
                            "active memory has no evidence relationship",
                        )
                    if record["approval_status"] not in {"approved", "not_required"}:
                        self._finding(
                            findings,
                            "I3A-ACTIVE-WITHOUT-APPROVAL",
                            record_id,
                            "active memory has an ineligible approval state",
                        )
                    if record["integrity_status"] not in {"valid", "not_applicable"}:
                        self._finding(
                            findings,
                            "I3A-ACTIVE-INTEGRITY",
                            record_id,
                            "active memory has invalid integrity",
                        )

            relationships = connection.execute(
                "SELECT * FROM record_relationships"
            ).fetchall()
            for relationship in relationships:
                endpoints = connection.execute(
                    """
                    SELECT record_id, record_family, record_type, project_scope_id
                    FROM records
                    WHERE record_id IN (?, ?)
                    """,
                    (
                        relationship["source_record_id"],
                        relationship["target_record_id"],
                    ),
                ).fetchall()
                if not any(
                    memory_domain_for(row["record_family"], row["record_type"])
                    is not None
                    for row in endpoints
                ):
                    self._finding(
                        findings,
                        "I3A-RELATIONSHIP-NONMEMORY",
                        None,
                        f"relationship {relationship['relationship_id']} has no memory endpoint",
                    )
                self._check_canonical_row(
                    findings,
                    table="record_relationships",
                    row=relationship,
                    fields=(
                        "relationship_id",
                        "source_record_id",
                        "target_record_id",
                        "relationship_type",
                        "created_at",
                        "created_by_principal",
                        "relationship_grant_id",
                        "authority_record_id",
                        "approval_evidence_id",
                        "explanation",
                    ),
                    record_id=relationship["source_record_id"],
                )
                if relationship["relationship_type"] in GOVERNED_RELATIONSHIP_TYPES:
                    scopes = {
                        row["project_scope_id"]
                        for row in endpoints
                        if row["project_scope_id"] is not None
                    }
                    grant = connection.execute(
                        """
                        SELECT * FROM memory_relationship_grants
                        WHERE grant_id = ?
                        """,
                        (relationship["relationship_grant_id"],),
                    ).fetchone()
                    authority = connection.execute(
                        """
                        SELECT authority_class, status, effect, project_scope_id,
                               issuer_entity_id, effective_from, effective_until
                        FROM authority_records WHERE authority_record_id = ?
                        """,
                        (relationship["authority_record_id"],),
                    ).fetchone()
                    revoked = connection.execute(
                        """
                        SELECT 1 FROM authority_revocations
                        WHERE authority_record_id = ?
                        """,
                        (relationship["authority_record_id"],),
                    ).fetchone()
                    if (
                        relationship["created_by_principal"] != "operator"
                        or len(endpoints) != 2
                        or len(scopes) != 1
                        or grant is None
                        or grant["relationship_id"]
                        != relationship["relationship_id"]
                        or grant["relationship_type"]
                        != relationship["relationship_type"]
                        or grant["source_record_id"]
                        != relationship["source_record_id"]
                        or grant["target_record_id"]
                        != relationship["target_record_id"]
                        or grant["authority_record_id"]
                        != relationship["authority_record_id"]
                        or grant["evidence_id"]
                        != relationship["approval_evidence_id"]
                        or grant["authority_class"]
                        not in NOLAN_INCLUSIVE_AUTHORITY_CLASSES
                        or (
                            grant["single_use"]
                            and (
                                grant["consumed_at"] is None
                                or grant["consumed_by_relationship_id"]
                                != relationship["relationship_id"]
                            )
                        )
                        or authority is None
                        or authority["status"] != "active"
                        or authority["effect"] != "allow"
                        or authority["effective_from"] > relationship["created_at"]
                        or (
                            authority["effective_until"] is not None
                            and authority["effective_until"]
                            < relationship["created_at"]
                        )
                        or authority["project_scope_id"] not in scopes
                        or authority["authority_class"]
                        not in NOLAN_INCLUSIVE_AUTHORITY_CLASSES
                        or authority["issuer_entity_id"]
                        != grant["approved_by_entity_id"]
                        or revoked is not None
                    ):
                        self._finding(
                            findings,
                            "I3A-RELATIONSHIP-AUTHORITY",
                            relationship["source_record_id"],
                            "governed relationship lacks its exact Nolan grant",
                        )

            assessments = connection.execute(
                "SELECT * FROM memory_eligibility_assessments"
            ).fetchall()
            for assessment in assessments:
                record_id = assessment["record_id"]
                try:
                    reasons = parse_json(assessment["reason_codes_json"])
                    snapshot = parse_json(assessment["record_snapshot_json"])
                    context_value = parse_json(assessment["context_json"])
                except Exception:
                    self._finding(
                        findings,
                        "I3A-ELIGIBILITY-JSON",
                        record_id,
                        "eligibility assessment contains invalid JSON",
                    )
                    continue
                if not isinstance(reasons, list):
                    self._finding(
                        findings,
                        "I3A-ELIGIBILITY-REASONS",
                        record_id,
                        "eligibility reasons are not an array",
                    )
                    continue
                ordered = [
                    reason
                    for reason in ELIGIBILITY_REASON_ORDER
                    if reason in set(reasons)
                ]
                if ordered != reasons:
                    self._finding(
                        findings,
                        "I3A-ELIGIBILITY-ORDER",
                        record_id,
                        "eligibility reasons are unknown, duplicated, or out of order",
                    )
                if (
                    not isinstance(snapshot, dict)
                    or canonical_json_text(snapshot)
                    != assessment["record_snapshot_json"]
                    or snapshot.get("record_id") != record_id
                    or sha256_canonical_json(snapshot)
                    != assessment["record_snapshot_hash"]
                ):
                    self._finding(
                        findings,
                        "I3A-ELIGIBILITY-SNAPSHOT",
                        record_id,
                        "eligibility record snapshot is incomplete or hash-invalid",
                    )
                    continue
                if not isinstance(context_value, dict):
                    self._finding(
                        findings,
                        "I3A-ELIGIBILITY-CONTEXT",
                        record_id,
                        "eligibility context is not an object",
                    )
                    continue
                try:
                    context = EligibilityContext(
                        assessment_id=str(context_value["assessment_id"]),
                        task_id=str(context_value["task_id"]),
                        task_project_scope_id=str(
                            context_value["task_project_scope_id"]
                        ),
                        requested_domain=str(context_value["requested_domain"]),
                        evaluated_at=str(context_value["evaluated_at"]),
                        allowed_sensitivity_classes=tuple(
                            context_value["allowed_sensitivity_classes"]
                        ),
                        allowed_privacy_classes=tuple(
                            context_value["allowed_privacy_classes"]
                        ),
                        cross_project_authorised=bool(
                            context_value["cross_project_authorised"]
                        ),
                        policy_version=str(context_value["policy_version"]),
                    )
                except Exception:
                    self._finding(
                        findings,
                        "I3A-ELIGIBILITY-CONTEXT",
                        record_id,
                        "eligibility context does not satisfy the I3-A contract",
                    )
                    continue
                task = connection.execute(
                    "SELECT project_scope_id FROM tasks WHERE task_id = ?",
                    (context.task_id,),
                ).fetchone()
                if (
                    canonical_json_text(context.canonical_value())
                    != assessment["context_json"]
                    or sha256_canonical_json(context.canonical_value())
                    != assessment["context_hash"]
                    or task is None
                    or task["project_scope_id"] != context.task_project_scope_id
                    or assessment["assessment_id"] != context.assessment_id
                    or assessment["task_id"] != context.task_id
                    or assessment["task_project_scope_id"]
                    != context.task_project_scope_id
                    or assessment["requested_domain"] != context.requested_domain
                    or assessment["evaluated_at"] != context.evaluated_at
                    or assessment["policy_version"] != context.policy_version
                ):
                    self._finding(
                        findings,
                        "I3A-ELIGIBILITY-CONTEXT",
                        record_id,
                        "eligibility context differs from its task or stored columns",
                    )
                    continue
                expected = evaluate_memory_eligibility(snapshot, context)
                if (
                    bool(assessment["eligible"]) != expected.eligible
                    or reasons != list(expected.reason_codes)
                    or assessment["record_snapshot_hash"]
                    != expected.record_snapshot_hash
                    or assessment["context_hash"] != expected.context_hash
                    or assessment["decision_hash"] != expected.decision_hash
                ):
                    self._finding(
                        findings,
                        "I3A-ELIGIBILITY-DECISION",
                        record_id,
                        "stored eligibility outcome cannot be independently reconstructed",
                    )

            return MemoryIntegrityReport(tuple(findings))

        return self._kernel.read(operation)
