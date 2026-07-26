"""Independent read-only integrity inspection for B87-I3-C1."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import (
    IntegrityInspectionError,
    ValidationError,
)
from batch87_apprentice.common.hashing import (
    hashes_match,
    sha256_bytes,
    sha256_canonical_json,
)
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.contracts import RecordEnvelope
from batch87_apprentice.persistence.transactions import PersistenceKernel

from .self_episodic_contracts import (
    B87_S1_ACTIVE_MATURITY_STAGES,
    DEVELOPMENTAL_POLICY_KINDS,
    FACTUAL_SELF_PAYLOAD_TABLES,
    CapabilityObservationPayload,
    DevelopmentalPolicyVersion,
    EvaluationReferenceAnchor,
    MaturityStatePayload,
    RuntimeIdentityPayload,
    RuntimeSubstrateAttestation,
    TrustedRuntimeAttestor,
    capability_policy_configuration,
    factual_self_content_hash,
    maturity_policy_configuration,
    payload_from_database,
)

_EXPECTED_REGISTRY = {
    ("self_model", "runtime_identity"): (
        "self_episodic",
        "not_required",
        "prohibited",
    ),
    ("self_model", "capability_observation"): (
        "self_episodic",
        "external",
        "candidate_only",
    ),
    ("self_model", "maturity_state"): (
        "self_episodic",
        "external",
        "prohibited",
    ),
}


@dataclass(frozen=True, slots=True)
class SelfEpisodicIntegrityFinding:
    severity: str
    code: str
    table: str
    record_id: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class SelfEpisodicIntegrityReport:
    database_path: str
    findings: tuple[SelfEpisodicIntegrityFinding, ...]

    @property
    def ok(self) -> bool:
        return all(finding.severity != "error" for finding in self.findings)

    @property
    def error_count(self) -> int:
        return sum(finding.severity == "error" for finding in self.findings)


def _finding(
    findings: list[SelfEpisodicIntegrityFinding],
    code: str,
    table: str,
    detail: str,
    *,
    record_id: str | None = None,
    severity: str = "error",
) -> None:
    findings.append(
        SelfEpisodicIntegrityFinding(
            severity=severity,
            code=code,
            table=table,
            record_id=record_id,
            detail=detail,
        )
    )


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table,),
        ).fetchone()
        is not None
    )


def _envelope(row: sqlite3.Row) -> RecordEnvelope:
    return RecordEnvelope(
        **{
            field: row[field]
            for field in RecordEnvelope.__dataclass_fields__
        }
    )


def _trusted_attestor(row: sqlite3.Row) -> TrustedRuntimeAttestor:
    return TrustedRuntimeAttestor(
        trusted_attestor_id=row["trusted_attestor_id"],
        attestor_entity_id=row["attestor_entity_id"],
        project_scope_id=row["project_scope_id"],
        attestation_environment=row["attestation_environment"],
        authority_record_id=row["authority_record_id"],
        approval_evidence_id=row["approval_evidence_id"],
        registered_by_principal=row["registered_by_principal"],
        registered_by_entity_id=row["registered_by_entity_id"],
        approved_by_entity_id=row["approved_by_entity_id"],
        approved_at=row["approved_at"],
        effective_from=row["effective_from"],
        effective_until=row["effective_until"],
        status=row["status"],
        supersedes_trusted_attestor_id=row[
            "supersedes_trusted_attestor_id"
        ],
    )


def _runtime_attestation(row: sqlite3.Row) -> RuntimeSubstrateAttestation:
    return RuntimeSubstrateAttestation(
        substrate_attestation_evidence_id=row[
            "substrate_attestation_evidence_id"
        ],
        trusted_attestor_id=row["trusted_attestor_id"],
        attestor_entity_id=row["attestor_entity_id"],
        project_scope_id=row["project_scope_id"],
        agent_entity_id=row["agent_entity_id"],
        runtime_instance_id=row["runtime_instance_id"],
        attestation_environment=row["attestation_environment"],
        base_model=row["base_model"],
        model_revision=row["model_revision"],
        runtime_provider=row["runtime_provider"],
        quantisation=row["quantisation"],
        context_limit=row["context_limit"],
        active_adapter=row["active_adapter"],
        runtime_started_at=row["runtime_started_at"],
        captured_at=row["captured_at"],
        changed_by_principal=row["changed_by_principal"],
        changed_by_entity_id=row["changed_by_entity_id"],
    )


def _canonical_row_valid(
    row: sqlite3.Row,
    *,
    json_column: str = "canonical_json",
    hash_column: str = "content_hash",
) -> bool:
    value = parse_json(row[json_column])
    return (
        isinstance(value, dict)
        and canonical_json_text(value) == row[json_column]
        and hashes_match(row[hash_column], sha256_canonical_json(value))
    )


class SelfEpisodicIntegrityInspector:
    """Detect C1 corruption without trusting write-path validation."""

    def __init__(self, source: DatabaseConfig | PersistenceKernel) -> None:
        self._kernel = (
            source if isinstance(source, PersistenceKernel) else PersistenceKernel(source)
        )

    @classmethod
    def _inspect_registry(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
    ) -> None:
        for key, expected in _EXPECTED_REGISTRY.items():
            row = connection.execute(
                """
                SELECT memory_domain, approval_requirement, agent_write_policy
                FROM memory_record_types
                WHERE record_family = ? AND record_type = ?
                """,
                key,
            ).fetchone()
            actual = None if row is None else tuple(row)
            if actual != expected:
                _finding(
                    findings,
                    "C1-REGISTRY-DRIFT",
                    "memory_record_types",
                    f"{key[0]}/{key[1]} expected={expected!r} actual={actual!r}",
                )
        permission_row = connection.execute(
            """
            SELECT record_family
            FROM memory_record_types
            WHERE record_type = 'permission_profile'
            LIMIT 1
            """
        ).fetchone()
        if permission_row is not None:
            _finding(
                findings,
                "C1-PERMISSION-MEMORY-INSERTION",
                "memory_record_types",
                "permission_profile must remain an I2 read-only projection",
            )
        kinds = {
            row["policy_kind"]: row["status"]
            for row in connection.execute(
                """
                SELECT policy_kind, status
                FROM developmental_policy_kinds
                ORDER BY policy_kind
                """
            )
        }
        if kinds != {kind: "active" for kind in DEVELOPMENTAL_POLICY_KINDS}:
            _finding(
                findings,
                "C1-POLICY-KIND-REGISTRY-DRIFT",
                "developmental_policy_kinds",
                f"unexpected developmental policy registry: {kinds!r}",
            )

    @classmethod
    def _inspect_permission_projection(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
    ) -> None:
        for row in connection.execute(
            """
            SELECT permission_profile_id, canonical_json, content_hash
            FROM permission_profiles
            ORDER BY permission_profile_id
            """
        ):
            try:
                valid = _canonical_row_valid(row)
            except Exception:
                valid = False
            if not valid:
                _finding(
                    findings,
                    "C1-PERMISSION-PROFILE-HASH-MISMATCH",
                    "permission_profiles",
                    "stored I2 profile is malformed, non-canonical, or hash-mismatched",
                    record_id=row["permission_profile_id"],
                )
        for row in connection.execute(
            """
            SELECT decision.governance_decision_id,
                   decision.permission_profile_hash,
                   profile.content_hash AS stored_hash
            FROM governance_decisions AS decision
            LEFT JOIN permission_profiles AS profile
              ON profile.permission_profile_id =
                 decision.permission_profile_id
            ORDER BY decision.governance_decision_id
            """
        ):
            if row["stored_hash"] is None or not hashes_match(
                row["permission_profile_hash"],
                row["stored_hash"],
            ):
                _finding(
                    findings,
                    "C1-PERMISSION-DECISION-PROFILE-MISMATCH",
                    "governance_decisions",
                    "decision-time profile hash differs from immutable I2 storage",
                    record_id=row["governance_decision_id"],
                )

    @classmethod
    def _inspect_anchors(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
    ) -> None:
        for row in connection.execute(
            """
            SELECT *
            FROM governed_evaluation_record_anchors
            ORDER BY evaluation_record_id
            """
        ):
            anchor_id = row["evaluation_record_id"]
            try:
                anchor = EvaluationReferenceAnchor(
                    evaluation_record_id=anchor_id,
                    evaluation_kind=row["evaluation_kind"],
                    project_scope_id=row["project_scope_id"],
                    provenance_evidence_id=row["provenance_evidence_id"],
                    registered_at=row["registered_at"],
                    provenance_summary=row["provenance_summary"],
                )
                if (
                    row["canonical_json"] != anchor.canonical_json
                    or not hashes_match(row["content_hash"], anchor.content_hash)
                ):
                    raise ValidationError("anchor canonical content hash differs")
            except Exception as exc:
                _finding(
                    findings,
                    "C1-EVALUATION-ANCHOR-HASH-MISMATCH",
                    "governed_evaluation_record_anchors",
                    str(exc),
                    record_id=anchor_id,
                )
            provenance = connection.execute(
                """
                SELECT evidence_kind, integrity_status
                FROM evidence_items
                WHERE evidence_id = ?
                """,
                (row["provenance_evidence_id"],),
            ).fetchone()
            controlled = connection.execute(
                """
                SELECT 1
                FROM controlled_resilience_evidence
                WHERE raw_prompt_evidence_id = ?
                   OR raw_output_evidence_id = ?
                LIMIT 1
                """,
                (
                    row["provenance_evidence_id"],
                    row["provenance_evidence_id"],
                ),
            ).fetchone()
            if (
                provenance is None
                or provenance["integrity_status"] != "valid"
                or provenance["evidence_kind"]
                in {"model_output", "controlled_prompt", "controlled_output"}
                or controlled is not None
            ):
                _finding(
                    findings,
                    "C1-EVALUATION-ANCHOR-PROVENANCE-INVALID",
                    "governed_evaluation_record_anchors",
                    "anchor provenance is missing, model-shaped, controlled, or invalid",
                    record_id=anchor_id,
                )
            history = list(
                connection.execute(
                    """
                    SELECT *
                    FROM governed_evaluation_anchor_state_history
                    WHERE evaluation_record_id = ?
                    ORDER BY sequence_number, transition_id
                    """,
                    (anchor_id,),
                )
            )
            previous: str | None = None
            history_valid = bool(history)
            for index, transition in enumerate(history):
                material = {
                    "changed_at": transition["changed_at"],
                    "changed_by_entity_id": transition["changed_by_entity_id"],
                    "changed_by_principal": transition["changed_by_principal"],
                    "evaluation_record_id": transition["evaluation_record_id"],
                    "from_state": transition["from_state"],
                    "reason_code": transition["reason_code"],
                    "sequence_number": transition["sequence_number"],
                    "to_state": transition["to_state"],
                    "transition_evidence_id": transition[
                        "transition_evidence_id"
                    ],
                    "transition_id": transition["transition_id"],
                }
                if (
                    transition["sequence_number"] != index
                    or transition["from_state"] != previous
                    or (index == 0 and transition["to_state"] != "registered")
                    or transition["canonical_json"]
                    != canonical_json_text(material)
                    or not hashes_match(
                        transition["content_hash"],
                        sha256_canonical_json(material),
                    )
                ):
                    history_valid = False
                previous = transition["to_state"]
            if not history_valid or previous != row["current_state"]:
                _finding(
                    findings,
                    "C1-EVALUATION-ANCHOR-HISTORY-MISMATCH",
                    "governed_evaluation_anchor_state_history",
                    "anchor history is absent, non-canonical, non-contiguous, or stale",
                    record_id=anchor_id,
                )

    @classmethod
    def _inspect_policies(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
    ) -> None:
        for row in connection.execute(
            """
            SELECT *
            FROM developmental_policy_versions
            ORDER BY developmental_policy_id
            """
        ):
            policy_id = row["developmental_policy_id"]
            try:
                policy = DevelopmentalPolicyVersion(
                    developmental_policy_id=policy_id,
                    policy_kind=row["policy_kind"],
                    version=row["version"],
                    project_scope_id=row["project_scope_id"],
                    configuration=parse_json(row["configuration_json"]),
                    authority_record_id=row["authority_record_id"],
                    approval_evidence_id=row["approval_evidence_id"],
                    approved_by_entity_id=row["approved_by_entity_id"],
                    approved_at=row["approved_at"],
                    effective_from=row["effective_from"],
                    effective_until=row["effective_until"],
                    status=row["status"],
                )
                if (
                    row["canonical_json"] != policy.canonical_json
                    or not hashes_match(row["content_hash"], policy.content_hash)
                ):
                    raise ValidationError("policy canonical content hash differs")
            except Exception as exc:
                _finding(
                    findings,
                    "C1-DEVELOPMENTAL-POLICY-INVALID",
                    "developmental_policy_versions",
                    str(exc),
                    record_id=policy_id,
                )
                continue
            authority = connection.execute(
                """
                SELECT authority_class, effect, status, project_scope_id,
                       issuer_entity_id, effective_from, effective_until
                FROM authority_records
                WHERE authority_record_id = ?
                """,
                (row["authority_record_id"],),
            ).fetchone()
            revoked = connection.execute(
                """
                SELECT 1
                FROM authority_revocations
                WHERE authority_record_id = ?
                  AND revoked_at <= ?
                """,
                (row["authority_record_id"], row["approved_at"]),
            ).fetchone()
            evidence = connection.execute(
                """
                SELECT evidence.evidence_kind, evidence.integrity_status
                FROM authority_record_evidence AS link
                JOIN evidence_items AS evidence
                  ON evidence.evidence_id = link.evidence_id
                WHERE link.authority_record_id = ?
                  AND link.evidence_id = ?
                """,
                (row["authority_record_id"], row["approval_evidence_id"]),
            ).fetchone()
            if (
                authority is None
                or authority["authority_class"] != "nolan_byte_approved"
                or authority["effect"] != "allow"
                or authority["status"] != "active"
                or authority["project_scope_id"] != row["project_scope_id"]
                or authority["issuer_entity_id"]
                != row["approved_by_entity_id"]
                or authority["effective_from"] > row["approved_at"]
                or (
                    authority["effective_until"] is not None
                    and authority["effective_until"] < row["approved_at"]
                )
                or revoked is not None
                or evidence is None
                or evidence["integrity_status"] != "valid"
                or evidence["evidence_kind"]
                in {"model_output", "controlled_prompt", "controlled_output"}
            ):
                _finding(
                    findings,
                    "C1-DEVELOPMENTAL-POLICY-AUTHORITY-INVALID",
                    "developmental_policy_versions",
                    "policy lacks exact active Nolan-Byte authority and evidence",
                    record_id=policy_id,
                )

    @classmethod
    def _trusted_attestor_valid_at(
        cls,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        effective_at: str,
        *,
        require_active: bool = True,
    ) -> bool:
        lineage = connection.execute(
            """
            SELECT attestor.entity_kind AS attestor_kind,
                   attestor.status AS attestor_status,
                   project.scope_kind, project.status AS project_status,
                   registrar.entity_kind AS registrar_kind,
                   registrar.status AS registrar_status,
                   approver.entity_kind AS approver_kind,
                   approver.status AS approver_status,
                   authority.authority_class, authority.effect,
                   authority.status AS authority_status,
                   authority.project_scope_id AS authority_project_scope_id,
                   authority.issuer_entity_id, authority.effective_from,
                   authority.effective_until,
                   evidence.evidence_kind,
                   evidence.integrity_status AS evidence_integrity_status
            FROM entities AS attestor
            LEFT JOIN scopes AS project
              ON project.scope_id = ?
            LEFT JOIN entities AS registrar
              ON registrar.entity_id = ?
            LEFT JOIN entities AS approver
              ON approver.entity_id = ?
            LEFT JOIN authority_records AS authority
              ON authority.authority_record_id = ?
            LEFT JOIN authority_record_evidence AS link
              ON link.authority_record_id = authority.authority_record_id
             AND link.evidence_id = ?
            LEFT JOIN evidence_items AS evidence
              ON evidence.evidence_id = link.evidence_id
            WHERE attestor.entity_id = ?
            """,
            (
                row["project_scope_id"],
                row["registered_by_entity_id"],
                row["approved_by_entity_id"],
                row["authority_record_id"],
                row["approval_evidence_id"],
                row["attestor_entity_id"],
            ),
        ).fetchone()
        revoked = connection.execute(
            """
            SELECT 1
            FROM authority_revocations
            WHERE authority_record_id = ? AND revoked_at <= ?
            LIMIT 1
            """,
            (row["authority_record_id"], effective_at),
        ).fetchone()
        controlled = connection.execute(
            """
            SELECT 1
            FROM controlled_resilience_evidence
            WHERE raw_prompt_evidence_id = ?
               OR raw_output_evidence_id = ?
            UNION ALL
            SELECT 1
            FROM record_evidence_links AS link
            JOIN records AS record ON record.record_id = link.record_id
            WHERE link.evidence_id = ?
              AND record.record_family = 'evaluation_evidence'
              AND record.record_type =
                  'controlled_governance_resilience_run'
            LIMIT 1
            """,
            (
                row["approval_evidence_id"],
                row["approval_evidence_id"],
                row["approval_evidence_id"],
            ),
        ).fetchone()
        later = connection.execute(
            """
            SELECT 1
            FROM trusted_runtime_attestors
            WHERE supersedes_trusted_attestor_id = ?
              AND effective_from <= ?
            LIMIT 1
            """,
            (row["trusted_attestor_id"], effective_at),
        ).fetchone()
        return bool(
            lineage is not None
            and lineage["attestor_kind"] in {"system", "component"}
            and lineage["attestor_status"] == "active"
            and lineage["scope_kind"] == "project"
            and lineage["project_status"] == "active"
            and row["registered_by_principal"] == "operator"
            and lineage["registrar_kind"] == "person"
            and lineage["registrar_status"] == "active"
            and lineage["approver_kind"] == "person"
            and lineage["approver_status"] == "active"
            and (
                not require_active
                or (
                    row["status"] == "active"
                    and row["effective_from"] <= effective_at
                    and (
                        row["effective_until"] is None
                        or row["effective_until"] >= effective_at
                    )
                )
            )
            and lineage["authority_class"] == "nolan_byte_approved"
            and lineage["effect"] == "allow"
            and lineage["authority_status"] == "active"
            and lineage["authority_project_scope_id"]
            == row["project_scope_id"]
            and lineage["issuer_entity_id"] == row["approved_by_entity_id"]
            and lineage["effective_from"] <= effective_at
            and (
                lineage["effective_until"] is None
                or lineage["effective_until"] >= effective_at
            )
            and lineage["evidence_integrity_status"] == "valid"
            and lineage["evidence_kind"]
            not in {"model_output", "controlled_prompt", "controlled_output"}
            and revoked is None
            and controlled is None
            and (not require_active or later is None)
        )

    @classmethod
    def _inspect_trusted_runtime_attestors(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
    ) -> None:
        for row in connection.execute(
            """
            SELECT *
            FROM trusted_runtime_attestors
            ORDER BY trusted_attestor_id
            """
        ):
            trusted_id = row["trusted_attestor_id"]
            try:
                trusted = _trusted_attestor(row)
                if (
                    row["canonical_json"] != trusted.canonical_json
                    or not hashes_match(
                        row["content_hash"],
                        trusted.content_hash,
                    )
                ):
                    raise ValidationError(
                        "attestor canonical content or hash differs"
                    )
            except Exception as exc:
                _finding(
                    findings,
                    "C1-TRUSTED-ATTESTOR-REGISTRY-DRIFT",
                    "trusted_runtime_attestors",
                    str(exc),
                    record_id=trusted_id,
                )
            if not cls._trusted_attestor_valid_at(
                connection,
                row,
                row["approved_at"],
                require_active=False,
            ):
                _finding(
                    findings,
                    "C1-TRUSTED-ATTESTOR-APPROVAL-INVALID",
                    "trusted_runtime_attestors",
                    "attestor lacks exact operator and Nolan-Byte approval lineage",
                    record_id=trusted_id,
                )
            prior_id = row["supersedes_trusted_attestor_id"]
            if prior_id is None:
                valid_chain = row["status"] == "active"
            else:
                prior = connection.execute(
                    """
                    SELECT *
                    FROM trusted_runtime_attestors
                    WHERE trusted_attestor_id = ?
                    """,
                    (prior_id,),
                ).fetchone()
                valid_chain = bool(
                    prior is not None
                    and prior["attestor_entity_id"]
                    == row["attestor_entity_id"]
                    and prior["project_scope_id"] == row["project_scope_id"]
                    and prior["attestation_environment"]
                    == row["attestation_environment"]
                    and prior["effective_from"] <= row["effective_from"]
                )
            if not valid_chain:
                _finding(
                    findings,
                    "C1-TRUSTED-ATTESTOR-HISTORY-INVALID",
                    "trusted_runtime_attestors",
                    "attestor immutable replacement lineage is invalid",
                    record_id=trusted_id,
                )
        for row in connection.execute(
            """
            SELECT current.attestor_entity_id, current.project_scope_id,
                   current.attestation_environment, COUNT(*) AS value
            FROM trusted_runtime_attestors AS current
            LEFT JOIN trusted_runtime_attestors AS later
              ON later.supersedes_trusted_attestor_id =
                 current.trusted_attestor_id
            WHERE later.trusted_attestor_id IS NULL
            GROUP BY current.attestor_entity_id, current.project_scope_id,
                     current.attestation_environment
            HAVING COUNT(*) > 1
            """
        ):
            _finding(
                findings,
                "C1-TRUSTED-ATTESTOR-MULTIPLE-CURRENT",
                "trusted_runtime_attestors",
                (
                    f"attestor={row['attestor_entity_id']} "
                    f"project={row['project_scope_id']} "
                    f"environment={row['attestation_environment']}"
                ),
            )

    @classmethod
    def _inspect_runtime_attestations(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
    ) -> None:
        for row in connection.execute(
            """
            SELECT *
            FROM runtime_substrate_attestations
            ORDER BY substrate_attestation_evidence_id
            """
        ):
            evidence_id = row["substrate_attestation_evidence_id"]
            try:
                attestation = _runtime_attestation(row)
                if (
                    row["canonical_json"] != attestation.canonical_json
                    or not hashes_match(
                        row["content_hash"],
                        attestation.content_hash,
                    )
                ):
                    raise ValidationError(
                        "attestation canonical content or hash differs"
                    )
            except Exception as exc:
                _finding(
                    findings,
                    "C1-RUNTIME-ATTESTATION-CONTENT-MISMATCH",
                    "runtime_substrate_attestations",
                    str(exc),
                    record_id=evidence_id,
                )
                if (
                    isinstance(row["context_limit"], bool)
                    or not isinstance(row["context_limit"], int)
                    or row["context_limit"] <= 0
                ):
                    _finding(
                        findings,
                        "C1-RUNTIME-CONTEXT-LIMIT-INVALID",
                        "runtime_substrate_attestations",
                        "support context_limit is null, malformed, or non-positive",
                        record_id=evidence_id,
                    )
                continue
            evidence = connection.execute(
                """
                SELECT evidence.*, inline.content, inline.encoding
                FROM evidence_items AS evidence
                LEFT JOIN evidence_inline_text AS inline
                  ON inline.evidence_id = evidence.evidence_id
                WHERE evidence.evidence_id = ?
                """,
                (evidence_id,),
            ).fetchone()
            runtime = connection.execute(
                """
                SELECT *
                FROM runtime_instances
                WHERE runtime_instance_id = ?
                """,
                (attestation.runtime_instance_id,),
            ).fetchone()
            agent = connection.execute(
                """
                SELECT entity_kind, status
                FROM entities
                WHERE entity_id = ?
                """,
                (attestation.agent_entity_id,),
            ).fetchone()
            trusted = connection.execute(
                """
                SELECT *
                FROM trusted_runtime_attestors
                WHERE trusted_attestor_id = ?
                """,
                (attestation.trusted_attestor_id,),
            ).fetchone()
            exact_evidence = bool(
                evidence is not None
                and evidence["evidence_kind"] == "system_event"
                and evidence["storage_kind"] == "inline_text"
                and evidence["integrity_status"] == "valid"
                and evidence["captured_by_entity"]
                == attestation.attestor_entity_id
                and evidence["captured_at"] == attestation.captured_at
                and evidence["encoding"] == "utf-8"
                and evidence["content"] == attestation.canonical_json
                and evidence["byte_length"]
                == len(attestation.canonical_json.encode("utf-8"))
                and hashes_match(
                    evidence["content_hash"],
                    sha256_bytes(attestation.canonical_json.encode("utf-8")),
                )
            )
            exact_parents = bool(
                runtime is not None
                and runtime["started_at"] == attestation.runtime_started_at
                and agent is not None
                and agent["entity_kind"] == "agent"
                and agent["status"] == "active"
                and trusted is not None
                and trusted["attestor_entity_id"]
                == attestation.attestor_entity_id
                and trusted["project_scope_id"]
                == attestation.project_scope_id
                and trusted["attestation_environment"]
                == attestation.attestation_environment
                and cls._trusted_attestor_valid_at(
                    connection,
                    trusted,
                    attestation.captured_at,
                )
            )
            if not exact_evidence:
                _finding(
                    findings,
                    "C1-RUNTIME-ATTESTATION-EVIDENCE-MISMATCH",
                    "runtime_substrate_attestations",
                    "inline evidence bytes, hash, captor, or timestamp differ",
                    record_id=evidence_id,
                )
            if not exact_parents:
                _finding(
                    findings,
                    "C1-RUNTIME-ATTESTATION-PARENT-MISMATCH",
                    "runtime_substrate_attestations",
                    "runtime, agent, project, or trusted attestor is orphaned or invalid",
                    record_id=evidence_id,
                )

    @classmethod
    def _payload_for(
        cls,
        connection: sqlite3.Connection,
        record: sqlite3.Row,
    ) -> RuntimeIdentityPayload | CapabilityObservationPayload | MaturityStatePayload:
        table = FACTUAL_SELF_PAYLOAD_TABLES[record["record_type"]]
        payload_row = connection.execute(
            f"SELECT * FROM {table} WHERE record_id = ?",
            (record["record_id"],),
        ).fetchone()
        if payload_row is None:
            raise ValidationError("typed payload is missing")
        evaluation_ids: tuple[str, ...] = ()
        if record["record_type"] == "capability_observation":
            evaluation_ids = tuple(
                row["evaluation_record_id"]
                for row in connection.execute(
                    """
                    SELECT evaluation_record_id
                    FROM capability_observation_evaluations
                    WHERE record_id = ?
                    ORDER BY evaluation_order
                    """,
                    (record["record_id"],),
                )
            )
        elif record["record_type"] == "maturity_state":
            evaluation_ids = tuple(
                row["evaluation_record_id"]
                for row in connection.execute(
                    """
                    SELECT evaluation_record_id
                    FROM maturity_state_basis_evaluations
                    WHERE record_id = ?
                    ORDER BY evaluation_order
                    """,
                    (record["record_id"],),
                )
            )
        return payload_from_database(
            record["record_type"],
            dict(payload_row),
            evaluation_record_ids=evaluation_ids,
        )

    @classmethod
    def _inspect_payload_cardinality(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
        record: sqlite3.Row,
    ) -> None:
        record_id = record["record_id"]
        expected = FACTUAL_SELF_PAYLOAD_TABLES[record["record_type"]]
        present: list[str] = []
        for table in FACTUAL_SELF_PAYLOAD_TABLES.values():
            count = connection.execute(
                f"SELECT COUNT(*) AS value FROM {table} WHERE record_id = ?",
                (record_id,),
            ).fetchone()["value"]
            if count:
                present.extend([table] * int(count))
        if present != [expected]:
            _finding(
                findings,
                "C1-PAYLOAD-CARDINALITY-INVALID",
                expected,
                f"expected one {expected} payload; found {present!r}",
                record_id=record_id,
            )
        lifecycle = connection.execute(
            """
            SELECT COUNT(*) AS value
            FROM memory_record_lifecycle_transitions
            WHERE record_id = ? AND sequence_number = 0
            """,
            (record_id,),
        ).fetchone()["value"]
        approval = connection.execute(
            """
            SELECT COUNT(*) AS value
            FROM memory_record_approval_transitions
            WHERE record_id = ? AND sequence_number = 0
            """,
            (record_id,),
        ).fetchone()["value"]
        if lifecycle != 1 or approval != 1:
            _finding(
                findings,
                "C1-INITIAL-HISTORY-MISSING",
                "memory_record_lifecycle_transitions",
                f"lifecycle_initial={lifecycle}; approval_initial={approval}",
                record_id=record_id,
            )

    @classmethod
    def _inspect_lineage_shape(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
        record: sqlite3.Row,
    ) -> None:
        record_id = record["record_id"]
        if record["record_type"] == "capability_observation":
            payload = connection.execute(
                """
                SELECT sample_size
                FROM capability_observations
                WHERE record_id = ?
                """,
                (record_id,),
            ).fetchone()
            if payload is None:
                return
            links = list(
                connection.execute(
                    """
                    SELECT link.evaluation_order,
                           anchor.evaluation_record_id,
                           anchor.evaluation_kind,
                           anchor.project_scope_id
                    FROM capability_observation_evaluations AS link
                    LEFT JOIN governed_evaluation_record_anchors AS anchor
                      ON anchor.evaluation_record_id = link.evaluation_record_id
                    WHERE link.record_id = ?
                    ORDER BY link.evaluation_order
                    """,
                    (record_id,),
                )
            )
            if (
                len(links) != payload["sample_size"]
                or any(
                    row["evaluation_order"] != index
                    for index, row in enumerate(links)
                )
                or any(
                    row["evaluation_record_id"] is None
                    or row["evaluation_kind"] != "capability_evaluation"
                    or row["project_scope_id"] != record["project_scope_id"]
                    for row in links
                )
            ):
                _finding(
                    findings,
                    "C1-CAPABILITY-LINEAGE-MISMATCH",
                    "capability_observation_evaluations",
                    "sample size, order, kind, or project scope does not reconcile",
                    record_id=record_id,
                )
        elif record["record_type"] == "maturity_state":
            payload = connection.execute(
                "SELECT 1 FROM maturity_states WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if payload is None:
                return
            links = list(
                connection.execute(
                    """
                    SELECT link.evaluation_order,
                           anchor.evaluation_record_id,
                           anchor.evaluation_kind,
                           anchor.project_scope_id
                    FROM maturity_state_basis_evaluations AS link
                    LEFT JOIN governed_evaluation_record_anchors AS anchor
                      ON anchor.evaluation_record_id = link.evaluation_record_id
                    WHERE link.record_id = ?
                    ORDER BY link.evaluation_order
                    """,
                    (record_id,),
                )
            )
            if (
                not links
                or any(
                    row["evaluation_order"] != index
                    for index, row in enumerate(links)
                )
                or any(
                    row["evaluation_record_id"] is None
                    or row["evaluation_kind"] != "maturity_evaluation"
                    or row["project_scope_id"] != record["project_scope_id"]
                    for row in links
                )
            ):
                _finding(
                    findings,
                    "C1-MATURITY-BASIS-INVALID",
                    "maturity_state_basis_evaluations",
                    "ordered same-project maturity evaluation basis is invalid",
                    record_id=record_id,
                )

    @classmethod
    def _inspect_record_evidence(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
        record_id: str,
    ) -> None:
        links = list(
            connection.execute(
                """
                SELECT evidence.evidence_id, evidence.evidence_kind,
                       evidence.integrity_status,
                       controlled.record_id AS controlled_record_id
                FROM record_evidence_links AS link
                LEFT JOIN evidence_items AS evidence
                  ON evidence.evidence_id = link.evidence_id
                LEFT JOIN controlled_resilience_evidence AS controlled
                  ON controlled.raw_prompt_evidence_id = link.evidence_id
                  OR controlled.raw_output_evidence_id = link.evidence_id
                WHERE link.record_id = ?
                ORDER BY evidence.evidence_id
                """,
                (record_id,),
            )
        )
        if not links:
            _finding(
                findings,
                "C1-RECORD-EVIDENCE-MISSING",
                "record_evidence_links",
                "factual self memory has no evidence",
                record_id=record_id,
            )
        for row in links:
            if (
                row["evidence_id"] is None
                or row["integrity_status"] != "valid"
                or row["evidence_kind"]
                in {"controlled_prompt", "controlled_output"}
                or row["controlled_record_id"] is not None
            ):
                _finding(
                    findings,
                    "C1-CONTROLLED-OR-INVALID-EVIDENCE",
                    "record_evidence_links",
                    "evidence is missing, invalid, or Controlled-Resilience contaminated",
                    record_id=record_id,
                )

    @classmethod
    def _inspect_runtime(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
        record: sqlite3.Row,
        payload: RuntimeIdentityPayload,
    ) -> None:
        record_id = record["record_id"]
        runtime = connection.execute(
            """
            SELECT *
            FROM runtime_instances
            WHERE runtime_instance_id = ?
            """,
            (payload.runtime_instance_id,),
        ).fetchone()
        support = connection.execute(
            """
            SELECT *
            FROM runtime_substrate_attestations
            WHERE substrate_attestation_evidence_id = ?
            """,
            (payload.substrate_attestation_evidence_id,),
        ).fetchone()
        evidence = connection.execute(
            """
            SELECT evidence.*, inline.content, inline.encoding
            FROM evidence_items AS evidence
            LEFT JOIN evidence_inline_text AS inline
              ON inline.evidence_id = evidence.evidence_id
            WHERE evidence.evidence_id = ?
            """,
            (payload.substrate_attestation_evidence_id,),
        ).fetchone()
        runtime_evidence_links = list(
            connection.execute(
                """
                SELECT evidence_id, relationship
                FROM record_evidence_links
                WHERE record_id = ?
                ORDER BY evidence_id, relationship
                """,
                (record_id,),
            )
        )
        exact_runtime_evidence_link = (
            len(runtime_evidence_links) == 1
            and runtime_evidence_links[0]["evidence_id"]
            == payload.substrate_attestation_evidence_id
            and runtime_evidence_links[0]["relationship"] == "supports"
        )
        try:
            attestation = (
                None if support is None else _runtime_attestation(support)
            )
        except Exception:
            attestation = None
        trusted = (
            None
            if support is None
            else connection.execute(
                """
                SELECT *
                FROM trusted_runtime_attestors
                WHERE trusted_attestor_id = ?
                """,
                (support["trusted_attestor_id"],),
            ).fetchone()
        )
        support_exact = bool(
            support is not None
            and attestation is not None
            and support["canonical_json"] == attestation.canonical_json
            and hashes_match(
                support["content_hash"],
                attestation.content_hash,
            )
            and attestation.attestation_environment == "production"
            and attestation.changed_by_principal == "validated_system"
            and attestation.changed_by_entity_id
            == payload.substrate_attestor_entity_id
            and attestation.attestor_entity_id
            == payload.substrate_attestor_entity_id
            and attestation.project_scope_id == record["project_scope_id"]
            and attestation.agent_entity_id == payload.agent_entity_id
            and attestation.runtime_instance_id == payload.runtime_instance_id
            and attestation.base_model == payload.base_model
            and attestation.model_revision == payload.model_revision
            and attestation.runtime_provider == payload.runtime_provider
            and attestation.quantisation == payload.quantisation
            and attestation.context_limit == payload.context_limit
            and attestation.active_adapter == payload.active_adapter
            and attestation.runtime_started_at == payload.runtime_started_at
            and attestation.captured_at >= payload.runtime_started_at
            and attestation.captured_at <= record["created_at"]
        )
        evidence_exact = bool(
            attestation is not None
            and evidence is not None
            and evidence["evidence_kind"] == "system_event"
            and evidence["integrity_status"] == "valid"
            and evidence["storage_kind"] == "inline_text"
            and evidence["captured_by_entity"]
            == payload.substrate_attestor_entity_id
            and evidence["captured_at"] == attestation.captured_at
            and evidence["encoding"] == "utf-8"
            and evidence["content"] == attestation.canonical_json
            and evidence["byte_length"]
            == len(attestation.canonical_json.encode("utf-8"))
            and hashes_match(
                evidence["content_hash"],
                sha256_bytes(attestation.canonical_json.encode("utf-8")),
            )
        )
        trusted_exact = bool(
            trusted is not None
            and trusted["attestor_entity_id"]
            == payload.substrate_attestor_entity_id
            and trusted["project_scope_id"] == record["project_scope_id"]
            and trusted["attestation_environment"] == "production"
            and cls._trusted_attestor_valid_at(
                connection,
                trusted,
                record["created_at"],
            )
        )
        if support is None:
            _finding(
                findings,
                "C1-RUNTIME-ATTESTATION-SUPPORT-MISSING",
                "runtime_substrate_attestations",
                "generic evidence cannot masquerade as a dedicated attestation",
                record_id=record_id,
            )
        if not support_exact:
            _finding(
                findings,
                "C1-RUNTIME-SUBSTRATE-MISMATCH",
                "runtime_identities",
                "dedicated production attestation differs from identity payload",
                record_id=record_id,
            )
        if attestation is not None and (
            attestation.attestation_environment != "production"
            or attestation.changed_by_principal != "validated_system"
        ):
            _finding(
                findings,
                "C1-RUNTIME-SYNTHETIC-OR-UNTRUSTED-ATTESTATION",
                "runtime_substrate_attestations",
                "active identity is bound to non-production attestation",
                record_id=record_id,
            )
        if not trusted_exact:
            _finding(
                findings,
                "C1-RUNTIME-ATTESTOR-INVALID",
                "trusted_runtime_attestors",
                "identity attestor is wrong, expired, revoked, retired, or unapproved",
                record_id=record_id,
            )
        if (
            runtime is None
            or runtime["started_at"] != payload.runtime_started_at
            or not evidence_exact
            or not exact_runtime_evidence_link
        ):
            _finding(
                findings,
                "C1-RUNTIME-ATTESTATION-EVIDENCE-MISMATCH",
                "runtime_identities",
                "runtime, evidence bytes, captor, hash, or exact supporting link mismatches",
                record_id=record_id,
            )
        if (
            isinstance(payload.context_limit, bool)
            or not isinstance(payload.context_limit, int)
            or payload.context_limit <= 0
            or (
                attestation is not None
                and attestation.context_limit != payload.context_limit
            )
        ):
            _finding(
                findings,
                "C1-RUNTIME-CONTEXT-LIMIT-INVALID",
                "runtime_identities",
                "context_limit is null, malformed, non-positive, or mismatched",
                record_id=record_id,
            )
        if record["lifecycle_state"] == "active" and (
            runtime is None
            or runtime["status"] != "running"
            or runtime["stopped_at"] is not None
        ):
            _finding(
                findings,
                "C1-ACTIVE-RUNTIME-STOPPED-OR-FALSE",
                "runtime_identities",
                "active identity does not point to a running runtime",
                record_id=record_id,
            )

    @classmethod
    def _active_time(
        cls,
        connection: sqlite3.Connection,
        record_id: str,
    ) -> str | None:
        row = connection.execute(
            """
            SELECT changed_at
            FROM memory_record_lifecycle_transitions
            WHERE record_id = ? AND to_state = 'active'
            ORDER BY sequence_number DESC
            LIMIT 1
            """,
            (record_id,),
        ).fetchone()
        return None if row is None else row["changed_at"]

    @classmethod
    def _policy_row_valid_for_record(
        cls,
        connection: sqlite3.Connection,
        *,
        policy_id: str | None,
        expected_kind: str,
        project_scope_id: str,
        effective_at: str | None,
    ) -> sqlite3.Row | None:
        if policy_id is None or effective_at is None:
            return None
        row = connection.execute(
            """
            SELECT policy.*, authority.authority_class, authority.effect,
                   authority.status AS authority_status,
                   revocation.authority_record_id AS revoked
            FROM developmental_policy_versions AS policy
            LEFT JOIN authority_records AS authority
              ON authority.authority_record_id = policy.authority_record_id
            LEFT JOIN authority_revocations AS revocation
              ON revocation.authority_record_id = policy.authority_record_id
             AND revocation.revoked_at <= ?
            WHERE policy.developmental_policy_id = ?
            """,
            (effective_at, policy_id),
        ).fetchone()
        if (
            row is None
            or row["policy_kind"] != expected_kind
            or row["project_scope_id"] != project_scope_id
            or row["status"] != "approved"
            or row["effective_from"] > effective_at
            or (
                row["effective_until"] is not None
                and row["effective_until"] < effective_at
            )
            or row["authority_class"] != "nolan_byte_approved"
            or row["effect"] != "allow"
            or row["authority_status"] != "active"
            or row["revoked"] is not None
        ):
            return None
        return row

    @classmethod
    def _inspect_capability(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
        record: sqlite3.Row,
        payload: CapabilityObservationPayload,
    ) -> None:
        record_id = record["record_id"]
        links = list(
            connection.execute(
                """
                SELECT link.evaluation_order, anchor.*
                FROM capability_observation_evaluations AS link
                LEFT JOIN governed_evaluation_record_anchors AS anchor
                  ON anchor.evaluation_record_id = link.evaluation_record_id
                WHERE link.record_id = ?
                ORDER BY link.evaluation_order
                """,
                (record_id,),
            )
        )
        if (
            len(links) != payload.sample_size
            or any(row["evaluation_order"] != index for index, row in enumerate(links))
            or any(
                row["evaluation_record_id"] is None
                or row["evaluation_kind"] != "capability_evaluation"
                or row["project_scope_id"] != record["project_scope_id"]
                for row in links
            )
        ):
            _finding(
                findings,
                "C1-CAPABILITY-LINEAGE-MISMATCH",
                "capability_observation_evaluations",
                "sample size, order, kind, or project scope does not reconcile",
                record_id=record_id,
            )
        if record["lifecycle_state"] != "active":
            return
        active_at = cls._active_time(connection, record_id)
        if payload.stability != "unconfirmed":
            if len(links) < 2 or any(
                row["current_state"] != "claimed" for row in links
            ):
                _finding(
                    findings,
                    "C1-CAPABILITY-STABILITY-UNSUPPORTED",
                    "capability_observation_evaluations",
                    "higher stability lacks multiple exact claimed evaluations",
                    record_id=record_id,
                )
            policy = cls._policy_row_valid_for_record(
                connection,
                policy_id=payload.developmental_policy_id,
                expected_kind="capability_stability",
                project_scope_id=record["project_scope_id"],
                effective_at=active_at,
            )
            try:
                configuration = (
                    None
                    if policy is None
                    else capability_policy_configuration(
                        parse_json(policy["configuration_json"])
                    )
                )
                requirement = (
                    None
                    if configuration is None
                    else configuration["stability_requirements"][
                        payload.stability
                    ]
                )
            except Exception:
                requirement = None
            if requirement is None or (
                len(links) < requirement["minimum_claimed_evaluations"]
                or payload.sample_size < requirement["minimum_sample_size"]
            ):
                _finding(
                    findings,
                    "C1-CAPABILITY-POLICY-INVALID",
                    "developmental_policy_versions",
                    "active capability lacks applicable approved policy support",
                    record_id=record_id,
                )
        elif any(row["current_state"] == "registered" for row in links):
            policy = cls._policy_row_valid_for_record(
                connection,
                policy_id=payload.developmental_policy_id,
                expected_kind="capability_stability",
                project_scope_id=record["project_scope_id"],
                effective_at=active_at,
            )
            try:
                allowed = (
                    policy is not None
                    and capability_policy_configuration(
                        parse_json(policy["configuration_json"])
                    )["allow_registered_for_unconfirmed"]
                )
            except Exception:
                allowed = False
            if not allowed:
                _finding(
                    findings,
                    "C1-UNCONFIRMED-REGISTERED-ANCHOR-UNSUPPORTED",
                    "developmental_policy_versions",
                    "registered anchor use lacks exact policy permission",
                    record_id=record_id,
                )
        kinds = {
            row["evidence_kind"]
            for row in connection.execute(
                """
                SELECT evidence.evidence_kind
                FROM record_evidence_links AS link
                JOIN evidence_items AS evidence
                  ON evidence.evidence_id = link.evidence_id
                WHERE link.record_id = ?
                """,
                (record_id,),
            )
        }
        if not kinds or kinds <= {"model_output"}:
            _finding(
                findings,
                "C1-CAPABILITY-MODEL-EVIDENCE-ONLY",
                "record_evidence_links",
                "model output alone cannot establish capability",
                record_id=record_id,
            )

    @classmethod
    def _inspect_maturity(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
        record: sqlite3.Row,
        payload: MaturityStatePayload,
    ) -> None:
        record_id = record["record_id"]
        if connection.execute(
            """
            SELECT 1
            FROM memory_record_lifecycle_transitions
            WHERE record_id = ? AND changed_by_principal = 'apprentice'
            LIMIT 1
            """,
            (record_id,),
        ).fetchone():
            _finding(
                findings,
                "C1-MATURITY-SELF-PROPOSAL",
                "memory_record_lifecycle_transitions",
                "maturity history contains an Apprentice mutation",
                record_id=record_id,
            )
        if record["lifecycle_state"] != "active":
            return
        if payload.stage not in B87_S1_ACTIVE_MATURITY_STAGES:
            _finding(
                findings,
                "C1-MATURITY-STAGE-PROHIBITED",
                "maturity_states",
                f"active B87-S1 stage is prohibited: {payload.stage}",
                record_id=record_id,
            )
        active_at = cls._active_time(connection, record_id)
        links = list(
            connection.execute(
                """
                SELECT link.evaluation_order, anchor.*
                FROM maturity_state_basis_evaluations AS link
                LEFT JOIN governed_evaluation_record_anchors AS anchor
                  ON anchor.evaluation_record_id = link.evaluation_record_id
                WHERE link.record_id = ?
                ORDER BY link.evaluation_order
                """,
                (record_id,),
            )
        )
        if (
            not links
            or any(row["evaluation_order"] != index for index, row in enumerate(links))
            or any(
                row["evaluation_record_id"] is None
                or row["evaluation_kind"] != "maturity_evaluation"
                or row["project_scope_id"] != record["project_scope_id"]
                or row["current_state"] != "claimed"
                for row in links
            )
        ):
            _finding(
                findings,
                "C1-MATURITY-BASIS-INVALID",
                "maturity_state_basis_evaluations",
                "active maturity lacks ordered same-project claimed evaluation basis",
                record_id=record_id,
            )
        policy = cls._policy_row_valid_for_record(
            connection,
            policy_id=payload.developmental_policy_id,
            expected_kind="maturity_progression",
            project_scope_id=record["project_scope_id"],
            effective_at=active_at,
        )
        prior_stage = None
        if record["supersedes_record_id"] is not None:
            prior = connection.execute(
                "SELECT stage FROM maturity_states WHERE record_id = ?",
                (record["supersedes_record_id"],),
            ).fetchone()
            prior_stage = None if prior is None else prior["stage"]
        try:
            transitions = (
                []
                if policy is None
                else maturity_policy_configuration(
                    parse_json(policy["configuration_json"])
                )["stage_transitions"]
            )
            matches = [
                transition
                for transition in transitions
                if transition["from_stage"] == prior_stage
                and transition["to_stage"] == payload.stage
                and len(links)
                >= transition["minimum_claimed_evaluations"]
            ]
        except Exception:
            matches = []
        if len(matches) != 1 or active_at != payload.entered_at:
            _finding(
                findings,
                "C1-MATURITY-POLICY-INVALID",
                "developmental_policy_versions",
                "active maturity lacks exact policy transition or entered_at match",
                record_id=record_id,
            )

    @classmethod
    def _inspect_supersession(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
        record: sqlite3.Row,
    ) -> None:
        record_id = record["record_id"]
        if record["supersedes_record_id"] is not None and record[
            "lifecycle_state"
        ] == "active":
            relationship = connection.execute(
                """
                SELECT relationship.*, target.lifecycle_state AS target_state,
                       target.superseded_by_record_id
                FROM record_relationships AS relationship
                JOIN records AS target
                  ON target.record_id = relationship.target_record_id
                WHERE relationship.source_record_id = ?
                  AND relationship.target_record_id = ?
                  AND relationship.relationship_type = 'supersedes'
                  AND relationship.relationship_grant_id IS NOT NULL
                """,
                (record_id, record["supersedes_record_id"]),
            ).fetchone()
            if (
                relationship is None
                or relationship["target_state"] != "superseded"
                or relationship["superseded_by_record_id"] != record_id
            ):
                _finding(
                    findings,
                    "C1-SUPERSESSION-ORDER-MISMATCH",
                    "record_relationships",
                    "active replacement lacks exact governed prior-state lineage",
                    record_id=record_id,
                )
        if record["lifecycle_state"] == "superseded":
            incoming = connection.execute(
                """
                SELECT COUNT(*) AS value
                FROM record_relationships
                WHERE target_record_id = ?
                  AND relationship_type = 'supersedes'
                  AND relationship_grant_id IS NOT NULL
                """,
                (record_id,),
            ).fetchone()["value"]
            if incoming != 1 or record["superseded_by_record_id"] is None:
                _finding(
                    findings,
                    "C1-SUPERSESSION-LINEAGE-MISSING",
                    "record_relationships",
                    "superseded record lacks one exact replacement",
                    record_id=record_id,
                )

    @classmethod
    def _inspect_records(
        cls,
        connection: sqlite3.Connection,
        findings: list[SelfEpisodicIntegrityFinding],
    ) -> None:
        for table, expected_type in (
            ("runtime_identities", "runtime_identity"),
            ("capability_observations", "capability_observation"),
            ("maturity_states", "maturity_state"),
        ):
            for row in connection.execute(
                f"""
                SELECT payload.record_id
                FROM {table} AS payload
                LEFT JOIN records AS record ON record.record_id = payload.record_id
                WHERE record.record_id IS NULL
                   OR record.record_family <> 'self_model'
                   OR record.record_type <> ?
                ORDER BY payload.record_id
                """,
                (expected_type,),
            ):
                _finding(
                    findings,
                    "C1-ORPHAN-OR-WRONG-PAYLOAD",
                    table,
                    f"payload does not belong to self_model/{expected_type}",
                    record_id=row["record_id"],
                )
        records = list(
            connection.execute(
                """
                SELECT *
                FROM records
                WHERE record_family = 'self_model'
                  AND record_type IN (
                      'runtime_identity',
                      'capability_observation',
                      'maturity_state'
                  )
                ORDER BY record_id
                """
            )
        )
        for record in records:
            record_id = record["record_id"]
            cls._inspect_payload_cardinality(connection, findings, record)
            cls._inspect_lineage_shape(connection, findings, record)
            cls._inspect_record_evidence(connection, findings, record_id)
            try:
                payload = cls._payload_for(connection, record)
                expected_hash = factual_self_content_hash(
                    _envelope(record),
                    payload,
                )
                if not hashes_match(record["content_hash"], expected_hash):
                    _finding(
                        findings,
                        "C1-COMBINED-HASH-MISMATCH",
                        "records",
                        "stored digest differs from envelope, payload, and ordered lineage",
                        record_id=record_id,
                    )
            except Exception as exc:
                _finding(
                    findings,
                    "C1-PAYLOAD-OR-ENVELOPE-INVALID",
                    FACTUAL_SELF_PAYLOAD_TABLES[record["record_type"]],
                    str(exc),
                    record_id=record_id,
                )
                if record["record_type"] == "runtime_identity":
                    context_row = connection.execute(
                        """
                        SELECT context_limit
                        FROM runtime_identities
                        WHERE record_id = ?
                        """,
                        (record_id,),
                    ).fetchone()
                    if context_row is not None and (
                        isinstance(context_row["context_limit"], bool)
                        or not isinstance(context_row["context_limit"], int)
                        or context_row["context_limit"] <= 0
                    ):
                        _finding(
                            findings,
                            "C1-RUNTIME-CONTEXT-LIMIT-INVALID",
                            "runtime_identities",
                            "payload context_limit is null, malformed, or non-positive",
                            record_id=record_id,
                        )
                continue
            if isinstance(payload, RuntimeIdentityPayload):
                cls._inspect_runtime(connection, findings, record, payload)
            elif isinstance(payload, CapabilityObservationPayload):
                cls._inspect_capability(connection, findings, record, payload)
            else:
                cls._inspect_maturity(connection, findings, record, payload)
            cls._inspect_supersession(connection, findings, record)

        duplicates = connection.execute(
            """
            SELECT identity.agent_entity_id, record.project_scope_id,
                   COUNT(*) AS value
            FROM runtime_identities AS identity
            JOIN records AS record ON record.record_id = identity.record_id
            WHERE record.lifecycle_state = 'active'
            GROUP BY identity.agent_entity_id, record.project_scope_id
            HAVING COUNT(*) > 1
            """
        )
        for row in duplicates:
            _finding(
                findings,
                "C1-MULTIPLE-ACTIVE-RUNTIME-IDENTITIES",
                "runtime_identities",
                (
                    f"agent={row['agent_entity_id']} "
                    f"project={row['project_scope_id']} count={row['value']}"
                ),
            )
        maturity_duplicates = connection.execute(
            """
            SELECT maturity.agent_entity_id, record.project_scope_id,
                   COUNT(*) AS value
            FROM maturity_states AS maturity
            JOIN records AS record ON record.record_id = maturity.record_id
            WHERE record.lifecycle_state = 'active'
            GROUP BY maturity.agent_entity_id, record.project_scope_id
            HAVING COUNT(*) > 1
            """
        )
        for row in maturity_duplicates:
            _finding(
                findings,
                "C1-MULTIPLE-ACTIVE-MATURITY-STATES",
                "maturity_states",
                (
                    f"agent={row['agent_entity_id']} "
                    f"project={row['project_scope_id']} count={row['value']}"
                ),
            )

    @classmethod
    def _inspect_connection(
        cls,
        connection: sqlite3.Connection,
    ) -> SelfEpisodicIntegrityReport:
        findings: list[SelfEpisodicIntegrityFinding] = []
        if not _table_exists(connection, "runtime_identities"):
            return SelfEpisodicIntegrityReport("", ())
        cls._inspect_registry(connection, findings)
        cls._inspect_permission_projection(connection, findings)
        cls._inspect_anchors(connection, findings)
        cls._inspect_policies(connection, findings)
        cls._inspect_trusted_runtime_attestors(connection, findings)
        cls._inspect_runtime_attestations(connection, findings)
        cls._inspect_records(connection, findings)
        return SelfEpisodicIntegrityReport(
            "",
            tuple(
                sorted(
                    findings,
                    key=lambda finding: (
                        finding.severity,
                        finding.code,
                        finding.table,
                        finding.record_id or "",
                        finding.detail,
                    ),
                )
            ),
        )

    def inspect(self) -> SelfEpisodicIntegrityReport:
        try:
            report = self._kernel.read(self._inspect_connection)
        except Exception as exc:
            if isinstance(exc, IntegrityInspectionError):
                raise
            raise IntegrityInspectionError(
                "read-only C1 integrity inspection failed"
            ) from exc
        return SelfEpisodicIntegrityReport(
            str(self._kernel.config.path),
            report.findings,
        )
