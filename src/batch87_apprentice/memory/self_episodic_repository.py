"""Atomic C1 factual self-model persistence and exact reconstruction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import NotFoundError, ValidationError
from batch87_apprentice.common.hashing import hashes_match, sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc
from batch87_apprentice.governance.contracts import PermissionProfile
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

from .contracts import (
    NOLAN_INCLUSIVE_AUTHORITY_CLASSES,
    MemoryApprovalGrant,
    MemoryRelationshipGrant,
    RecordRelationship,
    validate_lifecycle_transition,
)
from .kernel import MemoryKernel, _insert_initial_memory_state
from .self_episodic_contracts import (
    B87_S1_ACTIVE_MATURITY_STAGES,
    CAPABILITY_STABILITIES,
    EVALUATION_ANCHOR_TRANSITIONS,
    FACTUAL_SELF_PAYLOAD_TABLES,
    CapabilityObservationPayload,
    DevelopmentalPolicyVersion,
    EvaluationReferenceAnchor,
    FactualSelfPayload,
    MaturityStatePayload,
    RuntimeIdentityPayload,
    RuntimeSubstrateAttestation,
    TrustedRuntimeAttestor,
    capability_policy_configuration,
    factual_self_content_hash,
    maturity_policy_configuration,
    payload_from_database,
    validate_factual_self_pair,
)

_PROHIBITED_EVIDENCE_KINDS = frozenset(
    {"controlled_prompt", "controlled_output"}
)
_NON_AUTHORITY_EVIDENCE_KINDS = frozenset(
    {"model_output", "controlled_prompt", "controlled_output"}
)
_RECORD_PRINCIPALS = frozenset(
    {"operator", "codex_development_harness"}
)
_INFRASTRUCTURE_PRINCIPALS = frozenset(
    {"operator", "codex_development_harness"}
)
_ANCHOR_PRINCIPALS = frozenset(
    {"operator", "validated_system", "codex_development_harness"}
)


def _record_envelope(row: Mapping[str, Any]) -> RecordEnvelope:
    return RecordEnvelope(
        **{
            field: row[field]
            for field in RecordEnvelope.__dataclass_fields__
        }
    )


class SelfEpisodicMemoryRepository:
    """Own all C1 writes behind one existing PersistenceKernel transaction."""

    def __init__(self, kernel: PersistenceKernel) -> None:
        self._kernel = kernel

    def _after_write_step(self, step: str) -> None:
        """A no-op seam used only by deterministic rollback tests."""

    @staticmethod
    def _entity(
        connection: sqlite3.Connection,
        entity_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM entities WHERE entity_id = ?",
            (entity_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"entity not found: {entity_id}")
        return row

    @classmethod
    def _validate_changed_by(
        cls,
        connection: sqlite3.Connection,
        *,
        changed_by_principal: str,
        changed_by_entity_id: str | None,
        accepted_principals: frozenset[str],
    ) -> None:
        if changed_by_principal not in accepted_principals:
            raise ValidationError("unsupported changed-by principal")
        if changed_by_principal == "operator":
            if changed_by_entity_id is None:
                raise ValidationError("operator writes require changed_by_entity_id")
            entity = cls._entity(connection, changed_by_entity_id)
            if entity["entity_kind"] != "person" or entity["status"] != "active":
                raise ValidationError(
                    "operator writes require an active person entity"
                )
        elif changed_by_principal == "codex_development_harness":
            if changed_by_entity_id is not None:
                raise ValidationError(
                    "development harness writes cannot claim a human entity"
                )
        elif changed_by_principal == "apprentice":
            if changed_by_entity_id is None:
                raise ValidationError(
                    "Apprentice candidate writes require its agent entity"
                )
            entity = cls._entity(connection, changed_by_entity_id)
            if entity["entity_kind"] != "agent" or entity["status"] != "active":
                raise ValidationError(
                    "Apprentice candidate writes require an active agent entity"
                )
        elif changed_by_principal == "validated_system":
            if changed_by_entity_id is not None:
                entity = cls._entity(connection, changed_by_entity_id)
                if entity["entity_kind"] not in {"system", "component"}:
                    raise ValidationError(
                        "validated-system writes cannot claim a human entity"
                    )

    @staticmethod
    def _controlled_evidence(
        connection: sqlite3.Connection,
        evidence_id: str,
    ) -> bool:
        row = connection.execute(
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
            (evidence_id, evidence_id, evidence_id),
        ).fetchone()
        return row is not None

    @classmethod
    def _validated_evidence(
        cls,
        connection: sqlite3.Connection,
        evidence_id: str,
        *,
        allow_model_output: bool,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM evidence_items WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"evidence not found: {evidence_id}")
        prohibited = (
            _PROHIBITED_EVIDENCE_KINDS
            if allow_model_output
            else _NON_AUTHORITY_EVIDENCE_KINDS
        )
        if row["integrity_status"] != "valid" or row["evidence_kind"] in prohibited:
            raise ValidationError(
                "evidence must be valid, non-controlled, and authority-eligible"
            )
        if cls._controlled_evidence(connection, evidence_id):
            raise ValidationError(
                "Controlled Governance Resilience evidence is prohibited transitively"
            )
        return row

    def _insert_evidence_items(
        self,
        connection: sqlite3.Connection,
        evidence_items: Sequence[EvidenceItem],
        *,
        prefix: str,
    ) -> None:
        seen: set[str] = set()
        for index, item in enumerate(evidence_items):
            if not isinstance(item, EvidenceItem):
                raise TypeError("evidence_items must contain EvidenceItem values")
            if item.evidence_id in seen:
                raise ValidationError("new evidence identifiers must be unique")
            if item.evidence_kind in _PROHIBITED_EVIDENCE_KINDS:
                raise ValidationError(
                    "raw Controlled Governance Resilience evidence is prohibited"
                )
            seen.add(item.evidence_id)
            _insert_evidence(connection, item)
            self._after_write_step(f"{prefix}.evidence.{index}")

    @staticmethod
    def _validate_record_principal(
        envelope: RecordEnvelope,
        payload: FactualSelfPayload,
        *,
        changed_by_principal: str,
        changed_by_entity_id: str | None,
    ) -> None:
        if changed_by_principal not in _RECORD_PRINCIPALS:
            raise ValidationError("unsupported factual-self creation principal")
        if changed_by_principal == "operator":
            if (
                changed_by_entity_id is None
                or envelope.created_by_entity_id != changed_by_entity_id
            ):
                raise ValidationError(
                    "operator creation must match envelope.created_by_entity_id"
                )
        else:
            if changed_by_entity_id is not None:
                raise ValidationError(
                    "development harness creation cannot claim a human entity"
                )
            if envelope.created_by_entity_id is not None and not (
                isinstance(payload, CapabilityObservationPayload)
                and envelope.created_by_entity_id
                == envelope.subject_entity_id
                and envelope.authority_class == "agent_proposal"
            ):
                raise ValidationError(
                    "development harness attribution may preserve only an "
                    "Apprentice capability proposal"
                )

    @staticmethod
    def _validate_evidence_inputs(
        envelope: RecordEnvelope,
        evidence_items: Sequence[EvidenceItem],
        evidence_links: Sequence[EvidenceLink],
    ) -> None:
        if not evidence_links:
            raise ValidationError("factual self memory requires linked evidence")
        new_ids = {item.evidence_id for item in evidence_items}
        linked_ids: set[str] = set()
        keys: set[tuple[str, str]] = set()
        for link in evidence_links:
            if not isinstance(link, EvidenceLink):
                raise TypeError("evidence_links must contain EvidenceLink values")
            if link.record_id != envelope.record_id:
                raise ValidationError("evidence link targets the wrong record")
            key = (link.evidence_id, link.relationship)
            if key in keys:
                raise ValidationError("duplicate factual-self evidence link")
            keys.add(key)
            linked_ids.add(link.evidence_id)
        if not new_ids.issubset(linked_ids):
            raise ValidationError("every supplied evidence item must be linked")

    @staticmethod
    def _validate_runtime_evidence_links(
        payload: RuntimeIdentityPayload,
        evidence_links: Sequence[EvidenceLink],
    ) -> None:
        if (
            len(evidence_links) != 1
            or evidence_links[0].evidence_id
            != payload.substrate_attestation_evidence_id
            or evidence_links[0].relationship != "supports"
        ):
            raise ValidationError(
                "runtime identity requires one exact supporting "
                "attestation evidence link"
            )

    def _insert_record_evidence(
        self,
        connection: sqlite3.Connection,
        evidence_links: Sequence[EvidenceLink],
        *,
        prefix: str,
    ) -> None:
        for index, link in enumerate(evidence_links):
            self._validated_evidence(
                connection,
                link.evidence_id,
                allow_model_output=True,
            )
            connection.execute(
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
            self._after_write_step(f"{prefix}.evidence_link.{index}")

    @classmethod
    def _validate_policy(
        cls,
        connection: sqlite3.Connection,
        developmental_policy_id: str,
        *,
        expected_kind: str,
        project_scope_id: str,
        effective_at: str,
    ) -> tuple[DevelopmentalPolicyVersion, sqlite3.Row]:
        row = connection.execute(
            """
            SELECT *
            FROM developmental_policy_versions
            WHERE developmental_policy_id = ?
            """,
            (developmental_policy_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(
                f"developmental policy not found: {developmental_policy_id}"
            )
        try:
            policy = DevelopmentalPolicyVersion(
                developmental_policy_id=row["developmental_policy_id"],
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
        except Exception as exc:
            raise ValidationError("developmental policy content is invalid") from exc
        if (
            row["canonical_json"] != policy.canonical_json
            or not hashes_match(row["content_hash"], policy.content_hash)
            or policy.policy_kind != expected_kind
            or policy.project_scope_id != project_scope_id
            or policy.status != "approved"
            or policy.effective_from > effective_at
            or (
                policy.effective_until is not None
                and policy.effective_until < effective_at
            )
        ):
            raise ValidationError(
                "developmental policy is invalid, inactive, wrong-kind, or out of scope"
            )
        MemoryKernel._validate_authority_evidence(
            connection,
            authority_record_id=policy.authority_record_id,
            evidence_id=policy.approval_evidence_id,
            approved_by_entity_id=policy.approved_by_entity_id,
            project_scope_id=policy.project_scope_id,
            effective_at=effective_at,
            allowed_authority_classes=frozenset({"nolan_byte_approved"}),
        )
        cls._validated_evidence(
            connection,
            policy.approval_evidence_id,
            allow_model_output=False,
        )
        return policy, row

    @classmethod
    def _validate_anchor_set(
        cls,
        connection: sqlite3.Connection,
        evaluation_record_ids: Sequence[str],
        *,
        expected_kind: str,
        project_scope_id: str,
        required_state: str | None = None,
    ) -> tuple[sqlite3.Row, ...]:
        rows: list[sqlite3.Row] = []
        for evaluation_record_id in evaluation_record_ids:
            row = connection.execute(
                """
                SELECT *
                FROM governed_evaluation_record_anchors
                WHERE evaluation_record_id = ?
                """,
                (evaluation_record_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    f"evaluation anchor not found: {evaluation_record_id}"
                )
            anchor = EvaluationReferenceAnchor(
                evaluation_record_id=row["evaluation_record_id"],
                evaluation_kind=row["evaluation_kind"],
                project_scope_id=row["project_scope_id"],
                provenance_evidence_id=row["provenance_evidence_id"],
                registered_at=row["registered_at"],
                provenance_summary=row["provenance_summary"],
            )
            if (
                row["canonical_json"] != anchor.canonical_json
                or not hashes_match(row["content_hash"], anchor.content_hash)
                or row["evaluation_kind"] != expected_kind
                or row["project_scope_id"] != project_scope_id
                or row["current_state"] in {"invalid", "retired"}
                or (
                    required_state is not None
                    and row["current_state"] != required_state
                )
            ):
                raise ValidationError(
                    "evaluation anchor is invalid, wrong-kind, unclaimed, or out of scope"
                )
            cls._validated_evidence(
                connection,
                row["provenance_evidence_id"],
                allow_model_output=False,
            )
            rows.append(row)
        return tuple(rows)

    @staticmethod
    def _next_sequence(
        connection: sqlite3.Connection,
        table: str,
        id_column: str,
        identifier: str,
    ) -> int:
        row = connection.execute(
            f"""
            SELECT MAX(sequence_number) AS value
            FROM {table}
            WHERE {id_column} = ?
            """,
            (identifier,),
        ).fetchone()
        return 0 if row["value"] is None else int(row["value"]) + 1

    def register_evaluation_anchor(
        self,
        anchor: EvaluationReferenceAnchor,
        *,
        initial_transition_id: str,
        changed_by_principal: str,
        reason_code: str,
        changed_by_entity_id: str | None = None,
        evidence_items: Sequence[EvidenceItem] = (),
    ) -> str:
        """Atomically register typed identity, provenance, and sequence-zero state."""

        if not isinstance(anchor, EvaluationReferenceAnchor):
            raise TypeError("anchor must be an EvaluationReferenceAnchor")
        validate_identifier(initial_transition_id, field="initial_transition_id")
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise ValidationError("reason_code must be non-empty")
        supplied_ids = {item.evidence_id for item in evidence_items}
        if supplied_ids and supplied_ids != {anchor.provenance_evidence_id}:
            raise ValidationError(
                "anchor registration may supply only its provenance evidence"
            )

        def operation(connection: sqlite3.Connection) -> None:
            self._validate_changed_by(
                connection,
                changed_by_principal=changed_by_principal,
                changed_by_entity_id=changed_by_entity_id,
                accepted_principals=_ANCHOR_PRINCIPALS,
            )
            self._insert_evidence_items(
                connection,
                evidence_items,
                prefix="evaluation_anchor.register",
            )
            self._validated_evidence(
                connection,
                anchor.provenance_evidence_id,
                allow_model_output=False,
            )
            connection.execute(
                """
                INSERT INTO governed_evaluation_record_anchors (
                    evaluation_record_id, evaluation_kind, project_scope_id,
                    provenance_evidence_id, registered_at, provenance_summary,
                    current_state, canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, 'registered', ?, ?)
                """,
                (
                    anchor.evaluation_record_id,
                    anchor.evaluation_kind,
                    anchor.project_scope_id,
                    anchor.provenance_evidence_id,
                    anchor.registered_at,
                    anchor.provenance_summary,
                    anchor.canonical_json,
                    anchor.content_hash,
                ),
            )
            self._after_write_step("evaluation_anchor.register.anchor")
            material = {
                "changed_at": anchor.registered_at,
                "changed_by_entity_id": changed_by_entity_id,
                "changed_by_principal": changed_by_principal,
                "evaluation_record_id": anchor.evaluation_record_id,
                "from_state": None,
                "reason_code": reason_code,
                "sequence_number": 0,
                "to_state": "registered",
                "transition_evidence_id": anchor.provenance_evidence_id,
                "transition_id": initial_transition_id,
            }
            connection.execute(
                """
                INSERT INTO governed_evaluation_anchor_state_history (
                    transition_id, evaluation_record_id, sequence_number,
                    from_state, to_state, changed_at, changed_by_principal,
                    changed_by_entity_id, transition_evidence_id, reason_code,
                    canonical_json, content_hash
                ) VALUES (?, ?, 0, NULL, 'registered', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    initial_transition_id,
                    anchor.evaluation_record_id,
                    anchor.registered_at,
                    changed_by_principal,
                    changed_by_entity_id,
                    anchor.provenance_evidence_id,
                    reason_code,
                    canonical_json_text(material),
                    sha256_canonical_json(material),
                ),
            )
            self._after_write_step("evaluation_anchor.register.history")

        self._kernel.write(operation)
        return anchor.content_hash

    def transition_evaluation_anchor(
        self,
        evaluation_record_id: str,
        *,
        transition_id: str,
        to_state: str,
        changed_at: str,
        changed_by_principal: str,
        transition_evidence_id: str,
        reason_code: str,
        changed_by_entity_id: str | None = None,
        evidence_items: Sequence[EvidenceItem] = (),
    ) -> str:
        """Append one evidenced anchor-state transition and update current state."""

        validate_identifier(evaluation_record_id, field="evaluation_record_id")
        validate_identifier(transition_id, field="transition_id")
        validate_identifier(
            transition_evidence_id,
            field="transition_evidence_id",
        )
        parse_canonical_utc(changed_at, field="changed_at")
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise ValidationError("reason_code must be non-empty")
        supplied_ids = {item.evidence_id for item in evidence_items}
        if supplied_ids and supplied_ids != {transition_evidence_id}:
            raise ValidationError(
                "anchor transition may supply only its transition evidence"
            )

        def operation(connection: sqlite3.Connection) -> str:
            self._validate_changed_by(
                connection,
                changed_by_principal=changed_by_principal,
                changed_by_entity_id=changed_by_entity_id,
                accepted_principals=_ANCHOR_PRINCIPALS,
            )
            row = connection.execute(
                """
                SELECT *
                FROM governed_evaluation_record_anchors
                WHERE evaluation_record_id = ?
                """,
                (evaluation_record_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    f"evaluation anchor not found: {evaluation_record_id}"
                )
            from_state = row["current_state"]
            if to_state not in EVALUATION_ANCHOR_TRANSITIONS[from_state]:
                raise ValidationError(
                    f"invalid evaluation anchor transition: {from_state} -> {to_state}"
                )
            self._insert_evidence_items(
                connection,
                evidence_items,
                prefix="evaluation_anchor.transition",
            )
            self._validated_evidence(
                connection,
                transition_evidence_id,
                allow_model_output=False,
            )
            sequence = self._next_sequence(
                connection,
                "governed_evaluation_anchor_state_history",
                "evaluation_record_id",
                evaluation_record_id,
            )
            material = {
                "changed_at": changed_at,
                "changed_by_entity_id": changed_by_entity_id,
                "changed_by_principal": changed_by_principal,
                "evaluation_record_id": evaluation_record_id,
                "from_state": from_state,
                "reason_code": reason_code,
                "sequence_number": sequence,
                "to_state": to_state,
                "transition_evidence_id": transition_evidence_id,
                "transition_id": transition_id,
            }
            digest = sha256_canonical_json(material)
            connection.execute(
                """
                INSERT INTO governed_evaluation_anchor_state_history (
                    transition_id, evaluation_record_id, sequence_number,
                    from_state, to_state, changed_at, changed_by_principal,
                    changed_by_entity_id, transition_evidence_id, reason_code,
                    canonical_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition_id,
                    evaluation_record_id,
                    sequence,
                    from_state,
                    to_state,
                    changed_at,
                    changed_by_principal,
                    changed_by_entity_id,
                    transition_evidence_id,
                    reason_code,
                    canonical_json_text(material),
                    digest,
                ),
            )
            self._after_write_step("evaluation_anchor.transition.history")
            connection.execute(
                """
                UPDATE governed_evaluation_record_anchors
                SET current_state = ?
                WHERE evaluation_record_id = ?
                """,
                (to_state, evaluation_record_id),
            )
            self._after_write_step("evaluation_anchor.transition.current")
            return digest

        return self._kernel.write(operation)

    def create_developmental_policy_version(
        self,
        policy: DevelopmentalPolicyVersion,
        *,
        changed_by_principal: str,
        changed_by_entity_id: str | None = None,
    ) -> str:
        """Persist one externally approved policy version; never activate a default."""

        if not isinstance(policy, DevelopmentalPolicyVersion):
            raise TypeError("policy must be a DevelopmentalPolicyVersion")
        if policy.status != "approved":
            raise ValidationError("new policy versions must be externally approved")

        def operation(connection: sqlite3.Connection) -> None:
            self._validate_changed_by(
                connection,
                changed_by_principal=changed_by_principal,
                changed_by_entity_id=changed_by_entity_id,
                accepted_principals=_INFRASTRUCTURE_PRINCIPALS,
            )
            MemoryKernel._validate_authority_evidence(
                connection,
                authority_record_id=policy.authority_record_id,
                evidence_id=policy.approval_evidence_id,
                approved_by_entity_id=policy.approved_by_entity_id,
                project_scope_id=policy.project_scope_id,
                effective_at=policy.approved_at,
                allowed_authority_classes=frozenset(
                    {"nolan_byte_approved"}
                ),
            )
            self._validated_evidence(
                connection,
                policy.approval_evidence_id,
                allow_model_output=False,
            )
            _insert_values(
                connection,
                "developmental_policy_versions",
                policy.database_values(),
            )
            self._after_write_step("developmental_policy.create")

        self._kernel.write(operation)
        return policy.content_hash

    @staticmethod
    def _trusted_attestor_from_row(
        row: Mapping[str, Any],
    ) -> TrustedRuntimeAttestor:
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

    @staticmethod
    def _runtime_attestation_from_row(
        row: Mapping[str, Any],
    ) -> RuntimeSubstrateAttestation:
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

    @classmethod
    def _validate_trusted_runtime_attestor(
        cls,
        connection: sqlite3.Connection,
        trusted_attestor_id: str,
        *,
        attestor_entity_id: str,
        project_scope_id: str,
        attestation_environment: str,
        effective_at: str,
    ) -> tuple[TrustedRuntimeAttestor, sqlite3.Row]:
        row = connection.execute(
            """
            SELECT *
            FROM trusted_runtime_attestors
            WHERE trusted_attestor_id = ?
            """,
            (trusted_attestor_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(
                f"trusted runtime attestor not found: {trusted_attestor_id}"
            )
        try:
            trusted = cls._trusted_attestor_from_row(row)
        except Exception as exc:
            raise ValidationError(
                "trusted runtime attestor content is invalid"
            ) from exc
        if (
            row["canonical_json"] != trusted.canonical_json
            or not hashes_match(row["content_hash"], trusted.content_hash)
            or trusted.attestor_entity_id != attestor_entity_id
            or trusted.project_scope_id != project_scope_id
            or trusted.attestation_environment != attestation_environment
            or trusted.status != "active"
            or trusted.effective_from > effective_at
            or (
                trusted.effective_until is not None
                and trusted.effective_until < effective_at
            )
        ):
            raise ValidationError(
                "trusted runtime attestor is invalid, inactive, expired, or out of scope"
            )
        later = connection.execute(
            """
            SELECT 1
            FROM trusted_runtime_attestors
            WHERE supersedes_trusted_attestor_id = ?
              AND effective_from <= ?
            LIMIT 1
            """,
            (trusted.trusted_attestor_id, effective_at),
        ).fetchone()
        if later is not None:
            raise ValidationError(
                "trusted runtime attestor has been replaced, revoked, or retired"
            )
        entity = cls._entity(connection, trusted.attestor_entity_id)
        if (
            entity["entity_kind"] not in {"system", "component"}
            or entity["status"] != "active"
        ):
            raise ValidationError(
                "trusted runtime attestor requires an active system or component"
            )
        project = connection.execute(
            """
            SELECT scope_kind, status
            FROM scopes
            WHERE scope_id = ?
            """,
            (trusted.project_scope_id,),
        ).fetchone()
        if (
            project is None
            or project["scope_kind"] != "project"
            or project["status"] != "active"
        ):
            raise ValidationError(
                "trusted runtime attestor requires an active project scope"
            )
        MemoryKernel._validate_authority_evidence(
            connection,
            authority_record_id=trusted.authority_record_id,
            evidence_id=trusted.approval_evidence_id,
            approved_by_entity_id=trusted.approved_by_entity_id,
            project_scope_id=trusted.project_scope_id,
            effective_at=effective_at,
            allowed_authority_classes=frozenset({"nolan_byte_approved"}),
        )
        cls._validated_evidence(
            connection,
            trusted.approval_evidence_id,
            allow_model_output=False,
        )
        return trusted, row

    def register_trusted_runtime_attestor(
        self,
        trusted_attestor: TrustedRuntimeAttestor,
        *,
        changed_by_principal: str,
        changed_by_entity_id: str,
    ) -> str:
        """Register one immutable operator-attributed attestor version."""

        if not isinstance(trusted_attestor, TrustedRuntimeAttestor):
            raise TypeError(
                "trusted_attestor must be a TrustedRuntimeAttestor"
            )
        if (
            changed_by_principal
            != trusted_attestor.registered_by_principal
            or changed_by_entity_id
            != trusted_attestor.registered_by_entity_id
        ):
            raise ValidationError(
                "trusted attestor registration attribution does not match"
            )

        def operation(connection: sqlite3.Connection) -> None:
            self._validate_changed_by(
                connection,
                changed_by_principal=changed_by_principal,
                changed_by_entity_id=changed_by_entity_id,
                accepted_principals=frozenset({"operator"}),
            )
            entity = self._entity(
                connection,
                trusted_attestor.attestor_entity_id,
            )
            if (
                entity["entity_kind"] not in {"system", "component"}
                or entity["status"] != "active"
            ):
                raise ValidationError(
                    "trusted runtime attestor requires an active system or component"
                )
            MemoryKernel._validate_authority_evidence(
                connection,
                authority_record_id=trusted_attestor.authority_record_id,
                evidence_id=trusted_attestor.approval_evidence_id,
                approved_by_entity_id=trusted_attestor.approved_by_entity_id,
                project_scope_id=trusted_attestor.project_scope_id,
                effective_at=trusted_attestor.approved_at,
                allowed_authority_classes=frozenset(
                    {"nolan_byte_approved"}
                ),
            )
            self._validated_evidence(
                connection,
                trusted_attestor.approval_evidence_id,
                allow_model_output=False,
            )
            _insert_values(
                connection,
                "trusted_runtime_attestors",
                trusted_attestor.database_values(),
            )
            self._after_write_step("trusted_runtime_attestor.register")

        self._kernel.write(operation)
        return trusted_attestor.content_hash

    @classmethod
    def _validate_persisted_runtime_attestation(
        cls,
        connection: sqlite3.Connection,
        attestation: RuntimeSubstrateAttestation,
        *,
        identity_effective_at: str | None = None,
    ) -> tuple[sqlite3.Row, TrustedRuntimeAttestor]:
        row = connection.execute(
            """
            SELECT *
            FROM runtime_substrate_attestations
            WHERE substrate_attestation_evidence_id = ?
            """,
            (attestation.substrate_attestation_evidence_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(
                "dedicated runtime substrate attestation not found"
            )
        try:
            persisted = cls._runtime_attestation_from_row(row)
        except Exception as exc:
            raise ValidationError(
                "runtime substrate attestation content is invalid"
            ) from exc
        if (
            persisted != attestation
            or row["canonical_json"] != persisted.canonical_json
            or not hashes_match(row["content_hash"], persisted.content_hash)
        ):
            raise ValidationError(
                "runtime substrate attestation canonical content or hash differs"
            )
        trusted, _ = cls._validate_trusted_runtime_attestor(
            connection,
            persisted.trusted_attestor_id,
            attestor_entity_id=persisted.attestor_entity_id,
            project_scope_id=persisted.project_scope_id,
            attestation_environment=persisted.attestation_environment,
            effective_at=(
                identity_effective_at
                if identity_effective_at is not None
                else persisted.captured_at
            ),
        )
        evidence = cls._validated_evidence(
            connection,
            persisted.substrate_attestation_evidence_id,
            allow_model_output=False,
        )
        inline = connection.execute(
            """
            SELECT content, encoding
            FROM evidence_inline_text
            WHERE evidence_id = ?
            """,
            (persisted.substrate_attestation_evidence_id,),
        ).fetchone()
        if (
            evidence["evidence_kind"] != "system_event"
            or evidence["storage_kind"] != "inline_text"
            or evidence["captured_by_entity"]
            != persisted.attestor_entity_id
            or evidence["captured_at"] != persisted.captured_at
            or inline is None
            or inline["encoding"] != "utf-8"
            or inline["content"] != persisted.canonical_json
        ):
            raise ValidationError(
                "runtime attestation evidence is missing or does not exactly match"
            )
        runtime = connection.execute(
            """
            SELECT *
            FROM runtime_instances
            WHERE runtime_instance_id = ?
            """,
            (persisted.runtime_instance_id,),
        ).fetchone()
        if (
            runtime is None
            or runtime["status"] != "running"
            or runtime["stopped_at"] is not None
            or runtime["started_at"] != persisted.runtime_started_at
        ):
            raise ValidationError(
                "runtime attestation requires the exact running runtime instance"
            )
        agent = cls._entity(connection, persisted.agent_entity_id)
        if agent["entity_kind"] != "agent" or agent["status"] != "active":
            raise ValidationError(
                "runtime attestation requires the exact active agent"
            )
        return row, trusted

    def ingest_runtime_substrate_attestation(
        self,
        attestation: RuntimeSubstrateAttestation,
        evidence_item: EvidenceItem,
        *,
        changed_by_principal: str,
        changed_by_entity_id: str,
    ) -> str:
        """Atomically persist governed attestation evidence without identity."""

        if not isinstance(attestation, RuntimeSubstrateAttestation):
            raise TypeError(
                "attestation must be a RuntimeSubstrateAttestation"
            )
        if not isinstance(evidence_item, EvidenceItem):
            raise TypeError("evidence_item must be an EvidenceItem")
        if (
            changed_by_principal != attestation.changed_by_principal
            or changed_by_entity_id != attestation.changed_by_entity_id
        ):
            raise ValidationError(
                "runtime attestation ingestion attribution does not match"
            )
        if (
            evidence_item.evidence_id
            != attestation.substrate_attestation_evidence_id
            or evidence_item.evidence_kind != "system_event"
            or evidence_item.storage_kind != "inline_text"
            or evidence_item.integrity_status != "valid"
            or evidence_item.captured_by_entity
            != attestation.attestor_entity_id
            or evidence_item.captured_at != attestation.captured_at
            or evidence_item.inline_content != attestation.canonical_json
        ):
            raise ValidationError(
                "runtime attestation EvidenceItem does not exactly match"
            )

        def operation(connection: sqlite3.Connection) -> str:
            entity = self._entity(
                connection,
                attestation.attestor_entity_id,
            )
            if (
                entity["entity_kind"] not in {"system", "component"}
                or entity["status"] != "active"
            ):
                raise ValidationError(
                    "runtime attestation requires an active trusted attestor"
                )
            self._validate_trusted_runtime_attestor(
                connection,
                attestation.trusted_attestor_id,
                attestor_entity_id=attestation.attestor_entity_id,
                project_scope_id=attestation.project_scope_id,
                attestation_environment=attestation.attestation_environment,
                effective_at=attestation.captured_at,
            )
            existing_support = connection.execute(
                """
                SELECT 1
                FROM runtime_substrate_attestations
                WHERE substrate_attestation_evidence_id = ?
                """,
                (attestation.substrate_attestation_evidence_id,),
            ).fetchone()
            existing_evidence = connection.execute(
                """
                SELECT 1
                FROM evidence_items
                WHERE evidence_id = ?
                """,
                (attestation.substrate_attestation_evidence_id,),
            ).fetchone()
            if existing_support is not None:
                self._validate_persisted_runtime_attestation(
                    connection,
                    attestation,
                )
                return attestation.content_hash
            if existing_evidence is not None:
                raise ValidationError(
                    "generic pre-existing evidence cannot be adopted as "
                    "a runtime substrate attestation"
                )
            _insert_evidence(connection, evidence_item)
            self._after_write_step("runtime_attestation.evidence")
            _insert_values(
                connection,
                "runtime_substrate_attestations",
                attestation.database_values(),
            )
            self._after_write_step("runtime_attestation.support")
            return attestation.content_hash

        return self._kernel.write(operation)

    @classmethod
    def _validate_runtime_attestation(
        cls,
        connection: sqlite3.Connection,
        envelope: RecordEnvelope,
        payload: RuntimeIdentityPayload,
    ) -> None:
        row = connection.execute(
            """
            SELECT *
            FROM runtime_substrate_attestations
            WHERE substrate_attestation_evidence_id = ?
            """,
            (payload.substrate_attestation_evidence_id,),
        ).fetchone()
        if row is None:
            raise ValidationError(
                "runtime identity requires a pre-existing dedicated "
                "substrate attestation"
            )
        try:
            attestation = cls._runtime_attestation_from_row(row)
        except Exception as exc:
            raise ValidationError(
                "runtime identity substrate attestation is malformed"
            ) from exc
        cls._validate_persisted_runtime_attestation(
            connection,
            attestation,
            identity_effective_at=envelope.created_at,
        )
        exact = (
            attestation.attestation_environment == "production"
            and attestation.changed_by_principal == "validated_system"
            and attestation.changed_by_entity_id
            == payload.substrate_attestor_entity_id
            and attestation.attestor_entity_id
            == payload.substrate_attestor_entity_id
            and attestation.project_scope_id == envelope.project_scope_id
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
            and attestation.captured_at <= envelope.created_at
        )
        if not exact:
            raise ValidationError(
                "dedicated production substrate attestation does not "
                "exactly match the runtime payload"
            )
        already_used = connection.execute(
            """
            SELECT 1
            FROM runtime_identities
            WHERE substrate_attestation_evidence_id = ?
            LIMIT 1
            """,
            (payload.substrate_attestation_evidence_id,),
        ).fetchone()
        if already_used is not None:
            raise ValidationError(
                "runtime identity requires a fresh production attestation"
            )

    def _create_record_rows(
        self,
        connection: sqlite3.Connection,
        envelope: RecordEnvelope,
        payload: FactualSelfPayload,
        *,
        lifecycle_transition_id: str,
        approval_transition_id: str,
        evidence_items: Sequence[EvidenceItem],
        evidence_links: Sequence[EvidenceLink],
        changed_by_principal: str,
        changed_by_entity_id: str | None,
        reason_code: str,
        prefix: str,
    ) -> str:
        self._validate_changed_by(
            connection,
            changed_by_principal=changed_by_principal,
            changed_by_entity_id=changed_by_entity_id,
            accepted_principals=_RECORD_PRINCIPALS,
        )
        self._insert_evidence_items(
            connection,
            evidence_items,
            prefix=prefix,
        )
        if isinstance(payload, RuntimeIdentityPayload):
            self._validate_runtime_attestation(connection, envelope, payload)
        elif isinstance(payload, CapabilityObservationPayload):
            self._validate_anchor_set(
                connection,
                payload.evaluation_record_ids,
                expected_kind="capability_evaluation",
                project_scope_id=envelope.project_scope_id or "",
            )
            if payload.developmental_policy_id is not None:
                self._validate_policy(
                    connection,
                    payload.developmental_policy_id,
                    expected_kind="capability_stability",
                    project_scope_id=envelope.project_scope_id or "",
                    effective_at=envelope.created_at,
                )
        else:
            self._validate_anchor_set(
                connection,
                payload.basis,
                expected_kind="maturity_evaluation",
                project_scope_id=envelope.project_scope_id or "",
            )
            self._validate_policy(
                connection,
                payload.developmental_policy_id,
                expected_kind="maturity_progression",
                project_scope_id=envelope.project_scope_id or "",
                effective_at=payload.entered_at,
            )
        digest = factual_self_content_hash(envelope, payload)
        _insert_record(connection, envelope, content_hash=digest)
        self._after_write_step(f"{prefix}.record")
        _insert_values(connection, payload.TABLE, payload.database_values())
        self._after_write_step(f"{prefix}.payload")
        if isinstance(payload, CapabilityObservationPayload):
            for index, evaluation_record_id in enumerate(
                payload.evaluation_record_ids
            ):
                connection.execute(
                    """
                    INSERT INTO capability_observation_evaluations (
                        record_id, evaluation_record_id, evaluation_order
                    ) VALUES (?, ?, ?)
                    """,
                    (payload.record_id, evaluation_record_id, index),
                )
                self._after_write_step(f"{prefix}.evaluation.{index}")
        elif isinstance(payload, MaturityStatePayload):
            for index, evaluation_record_id in enumerate(payload.basis):
                connection.execute(
                    """
                    INSERT INTO maturity_state_basis_evaluations (
                        record_id, evaluation_record_id, evaluation_order
                    ) VALUES (?, ?, ?)
                    """,
                    (payload.record_id, evaluation_record_id, index),
                )
                self._after_write_step(f"{prefix}.basis.{index}")
        self._insert_record_evidence(
            connection,
            evidence_links,
            prefix=prefix,
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
        self._after_write_step(f"{prefix}.initial_histories")
        return digest

    def _validate_declared_supersession(
        self,
        connection: sqlite3.Connection,
        envelope: RecordEnvelope,
        payload: FactualSelfPayload,
    ) -> None:
        if envelope.supersedes_record_id is None:
            return
        prior = connection.execute(
            "SELECT * FROM records WHERE record_id = ?",
            (envelope.supersedes_record_id,),
        ).fetchone()
        if (
            prior is None
            or prior["record_family"] != envelope.record_family
            or prior["record_type"] != envelope.record_type
            or prior["project_scope_id"] != envelope.project_scope_id
            or prior["subject_entity_id"] != envelope.subject_entity_id
            or prior["lifecycle_state"] != "active"
        ):
            raise ValidationError(
                "declared supersession target must be the active same-scope self record"
            )
        table = FACTUAL_SELF_PAYLOAD_TABLES[envelope.record_type]
        prior_payload = connection.execute(
            f"SELECT * FROM {table} WHERE record_id = ?",
            (prior["record_id"],),
        ).fetchone()
        if prior_payload is None:
            raise ValidationError("declared supersession target lacks its payload")
        if isinstance(payload, CapabilityObservationPayload):
            if prior_payload["capability_key"] != payload.capability_key:
                raise ValidationError(
                    "capability supersession requires the same capability"
                )
        elif isinstance(payload, (RuntimeIdentityPayload, MaturityStatePayload)):
            if prior_payload["agent_entity_id"] != payload.agent_entity_id:
                raise ValidationError(
                    "self-model supersession requires the same agent"
                )

    def create_capability_observation(
        self,
        envelope: RecordEnvelope,
        payload: CapabilityObservationPayload,
        *,
        lifecycle_transition_id: str,
        approval_transition_id: str,
        evidence_links: Sequence[EvidenceLink],
        changed_by_principal: str,
        evidence_items: Sequence[EvidenceItem] = (),
        changed_by_entity_id: str | None = None,
        reason_code: str = "capability_observation_created",
    ) -> str:
        """Create one candidate capability observation atomically."""

        validate_factual_self_pair(envelope, payload)
        self._validate_record_principal(
            envelope,
            payload,
            changed_by_principal=changed_by_principal,
            changed_by_entity_id=changed_by_entity_id,
        )
        self._validate_evidence_inputs(envelope, evidence_items, evidence_links)

        def operation(connection: sqlite3.Connection) -> str:
            self._validate_declared_supersession(connection, envelope, payload)
            return self._create_record_rows(
                connection,
                envelope,
                payload,
                lifecycle_transition_id=lifecycle_transition_id,
                approval_transition_id=approval_transition_id,
                evidence_items=evidence_items,
                evidence_links=evidence_links,
                changed_by_principal=changed_by_principal,
                changed_by_entity_id=changed_by_entity_id,
                reason_code=reason_code,
                prefix="capability.create",
            )

        return self._kernel.write(operation)

    def create_maturity_state(
        self,
        envelope: RecordEnvelope,
        payload: MaturityStatePayload,
        *,
        lifecycle_transition_id: str,
        approval_transition_id: str,
        evidence_links: Sequence[EvidenceLink],
        changed_by_principal: str,
        evidence_items: Sequence[EvidenceItem] = (),
        changed_by_entity_id: str | None = None,
        reason_code: str = "maturity_state_created",
    ) -> str:
        """Create one externally governed reviewed maturity record atomically."""

        validate_factual_self_pair(envelope, payload)
        self._validate_record_principal(
            envelope,
            payload,
            changed_by_principal=changed_by_principal,
            changed_by_entity_id=changed_by_entity_id,
        )
        if changed_by_principal == "apprentice":
            raise ValidationError("the Apprentice cannot propose a maturity state")
        self._validate_evidence_inputs(envelope, evidence_items, evidence_links)

        def operation(connection: sqlite3.Connection) -> str:
            self._validate_declared_supersession(connection, envelope, payload)
            return self._create_record_rows(
                connection,
                envelope,
                payload,
                lifecycle_transition_id=lifecycle_transition_id,
                approval_transition_id=approval_transition_id,
                evidence_items=evidence_items,
                evidence_links=evidence_links,
                changed_by_principal=changed_by_principal,
                changed_by_entity_id=changed_by_entity_id,
                reason_code=reason_code,
                prefix="maturity.create",
            )

        return self._kernel.write(operation)

    @staticmethod
    def _audit_values(material: Mapping[str, Any]) -> tuple[str, str]:
        value = dict(material)
        return canonical_json_text(value), sha256_canonical_json(value)

    def _transition_lifecycle(
        self,
        connection: sqlite3.Connection,
        record_id: str,
        *,
        transition_id: str,
        to_state: str,
        reason_code: str,
        changed_at: str,
        changed_by_principal: str,
        changed_by_entity_id: str | None,
        step: str,
    ) -> None:
        validate_identifier(transition_id, field="transition_id")
        parse_canonical_utc(changed_at, field="changed_at")
        row = connection.execute(
            "SELECT * FROM records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"record not found: {record_id}")
        from_state = row["lifecycle_state"]
        validate_lifecycle_transition(from_state, to_state)
        sequence = self._next_sequence(
            connection,
            "memory_record_lifecycle_transitions",
            "record_id",
            record_id,
        )
        material = {
            "changed_at": changed_at,
            "changed_by_entity_id": changed_by_entity_id,
            "changed_by_principal": changed_by_principal,
            "from_state": from_state,
            "reason_code": reason_code,
            "record_id": record_id,
            "sequence_number": sequence,
            "to_state": to_state,
            "transition_id": transition_id,
        }
        canonical, digest = self._audit_values(material)
        connection.execute(
            """
            INSERT INTO memory_record_lifecycle_transitions (
                transition_id, record_id, sequence_number, from_state, to_state,
                reason_code, changed_at, changed_by_principal,
                changed_by_entity_id, canonical_json, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transition_id,
                record_id,
                sequence,
                from_state,
                to_state,
                reason_code,
                changed_at,
                changed_by_principal,
                changed_by_entity_id,
                canonical,
                digest,
            ),
        )
        self._after_write_step(f"{step}.history")
        connection.execute(
            """
            UPDATE records
            SET lifecycle_state = ?
            WHERE record_id = ?
            """,
            (to_state, record_id),
        )
        self._after_write_step(f"{step}.current")

    def _approve_record(
        self,
        connection: sqlite3.Connection,
        grant: MemoryApprovalGrant,
        *,
        transition_id: str,
        reason_code: str,
        changed_at: str,
        step: str,
    ) -> None:
        if not isinstance(grant, MemoryApprovalGrant):
            raise TypeError("approval_grant must be a MemoryApprovalGrant")
        if grant.target_status != "approved" or not grant.single_use:
            raise ValidationError(
                "C1 activation requires an exact single-use approval grant"
            )
        validate_identifier(transition_id, field="approval_transition_id")
        parse_canonical_utc(changed_at, field="changed_at")
        record = connection.execute(
            "SELECT * FROM records WHERE record_id = ?",
            (grant.record_id,),
        ).fetchone()
        if record is None:
            raise NotFoundError(f"record not found: {grant.record_id}")
        if (
            record["approval_status"] != "pending"
            or record["project_scope_id"] != grant.project_scope_id
            or grant.approved_at > changed_at
            or (
                grant.expires_at is not None
                and grant.expires_at < changed_at
            )
        ):
            raise ValidationError("approval grant does not match this activation")
        authority = MemoryKernel._validate_authority_evidence(
            connection,
            authority_record_id=grant.authority_record_id,
            evidence_id=grant.evidence_id,
            approved_by_entity_id=grant.approved_by_entity_id,
            project_scope_id=grant.project_scope_id,
            effective_at=changed_at,
            allowed_authority_classes=frozenset({"nolan_byte_approved"}),
        )
        self._validated_evidence(
            connection,
            grant.evidence_id,
            allow_model_output=False,
        )
        grant_canonical, grant_hash = self._audit_values(grant.canonical_value())
        connection.execute(
            """
            INSERT INTO memory_approval_grants (
                grant_id, record_id, target_status, operation,
                project_scope_id, authority_record_id, authority_class,
                approved_by_entity_id, approved_at, expires_at,
                single_use, consumed_at, consumed_by_transition_id,
                evidence_id, canonical_json, content_hash
            ) VALUES (?, ?, 'approved', ?, ?, ?, ?, ?, ?, ?, 1, NULL, NULL, ?, ?, ?)
            """,
            (
                grant.grant_id,
                grant.record_id,
                grant.operation,
                grant.project_scope_id,
                grant.authority_record_id,
                authority["authority_class"],
                grant.approved_by_entity_id,
                grant.approved_at,
                grant.expires_at,
                grant.evidence_id,
                grant_canonical,
                grant_hash,
            ),
        )
        self._after_write_step(f"{step}.grant")
        sequence = self._next_sequence(
            connection,
            "memory_record_approval_transitions",
            "record_id",
            grant.record_id,
        )
        material = {
            "approval_evidence_id": grant.evidence_id,
            "approval_grant_id": grant.grant_id,
            "authority_record_id": grant.authority_record_id,
            "changed_at": changed_at,
            "changed_by_entity_id": grant.approved_by_entity_id,
            "changed_by_principal": "operator",
            "from_status": "pending",
            "reason_code": reason_code,
            "record_id": grant.record_id,
            "sequence_number": sequence,
            "to_status": "approved",
            "transition_id": transition_id,
        }
        canonical, digest = self._audit_values(material)
        connection.execute(
            """
            INSERT INTO memory_record_approval_transitions (
                transition_id, record_id, sequence_number,
                from_status, to_status, reason_code, changed_at,
                changed_by_principal, changed_by_entity_id,
                approval_grant_id, authority_record_id,
                approval_evidence_id, canonical_json, content_hash
            ) VALUES (?, ?, ?, 'pending', 'approved', ?, ?, 'operator', ?, ?, ?, ?, ?, ?)
            """,
            (
                transition_id,
                grant.record_id,
                sequence,
                reason_code,
                changed_at,
                grant.approved_by_entity_id,
                grant.grant_id,
                grant.authority_record_id,
                grant.evidence_id,
                canonical,
                digest,
            ),
        )
        self._after_write_step(f"{step}.transition")
        connection.execute(
            """
            UPDATE memory_approval_grants
            SET consumed_at = ?, consumed_by_transition_id = ?
            WHERE grant_id = ? AND consumed_at IS NULL
            """,
            (changed_at, transition_id, grant.grant_id),
        )
        self._after_write_step(f"{step}.consume")
        connection.execute(
            "UPDATE records SET approval_status = 'approved' WHERE record_id = ?",
            (grant.record_id,),
        )
        self._after_write_step(f"{step}.current")

    def _link_supersession(
        self,
        connection: sqlite3.Connection,
        grant: MemoryRelationshipGrant,
        relationship: RecordRelationship,
        *,
        effective_at: str,
        step: str,
    ) -> None:
        if not isinstance(grant, MemoryRelationshipGrant):
            raise TypeError(
                "relationship_grant must be a MemoryRelationshipGrant"
            )
        if not isinstance(relationship, RecordRelationship):
            raise TypeError("relationship must be a RecordRelationship")
        if (
            grant.relationship_type != "supersedes"
            or relationship.relationship_type != "supersedes"
            or relationship.created_by_principal != "operator"
            or relationship.relationship_grant_id != grant.grant_id
            or relationship.relationship_id != grant.relationship_id
            or relationship.source_record_id != grant.source_record_id
            or relationship.target_record_id != grant.target_record_id
            or not grant.single_use
            or grant.approved_at > relationship.created_at
            or relationship.created_at != effective_at
            or (
                grant.expires_at is not None
                and grant.expires_at < relationship.created_at
            )
        ):
            raise ValidationError("supersession grant and relationship are not exact")
        source = connection.execute(
            "SELECT * FROM records WHERE record_id = ?",
            (grant.source_record_id,),
        ).fetchone()
        target = connection.execute(
            "SELECT * FROM records WHERE record_id = ?",
            (grant.target_record_id,),
        ).fetchone()
        if (
            source is None
            or target is None
            or source["project_scope_id"] != grant.project_scope_id
            or target["project_scope_id"] != grant.project_scope_id
            or source["record_family"] != target["record_family"]
            or source["record_type"] != target["record_type"]
            or source["supersedes_record_id"] != target["record_id"]
        ):
            raise ValidationError(
                "supersession endpoints are missing, cross-scope, or type-mismatched"
            )
        authority = MemoryKernel._validate_authority_evidence(
            connection,
            authority_record_id=grant.authority_record_id,
            evidence_id=grant.evidence_id,
            approved_by_entity_id=grant.approved_by_entity_id,
            project_scope_id=grant.project_scope_id,
            effective_at=relationship.created_at,
            allowed_authority_classes=NOLAN_INCLUSIVE_AUTHORITY_CLASSES,
        )
        self._validated_evidence(
            connection,
            grant.evidence_id,
            allow_model_output=False,
        )
        grant_canonical, grant_hash = self._audit_values(grant.canonical_value())
        connection.execute(
            """
            INSERT INTO memory_relationship_grants (
                grant_id, relationship_id, relationship_type,
                source_record_id, target_record_id, operation,
                project_scope_id, authority_record_id, authority_class,
                approved_by_entity_id, approved_at, expires_at,
                single_use, consumed_at, consumed_by_relationship_id,
                evidence_id, canonical_json, content_hash
            ) VALUES (?, ?, 'supersedes', ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, NULL, ?, ?, ?)
            """,
            (
                grant.grant_id,
                grant.relationship_id,
                grant.source_record_id,
                grant.target_record_id,
                grant.operation,
                grant.project_scope_id,
                grant.authority_record_id,
                authority["authority_class"],
                grant.approved_by_entity_id,
                grant.approved_at,
                grant.expires_at,
                grant.evidence_id,
                grant_canonical,
                grant_hash,
            ),
        )
        self._after_write_step(f"{step}.grant")
        material = {
            "approval_evidence_id": grant.evidence_id,
            "authority_record_id": grant.authority_record_id,
            "created_at": relationship.created_at,
            "created_by_principal": relationship.created_by_principal,
            "explanation": relationship.explanation,
            "relationship_grant_id": grant.grant_id,
            "relationship_id": relationship.relationship_id,
            "relationship_type": "supersedes",
            "source_record_id": relationship.source_record_id,
            "target_record_id": relationship.target_record_id,
        }
        canonical, digest = self._audit_values(material)
        connection.execute(
            """
            INSERT INTO record_relationships (
                relationship_id, source_record_id, target_record_id,
                relationship_type, created_at, created_by_principal,
                relationship_grant_id, authority_record_id,
                approval_evidence_id, explanation, canonical_json,
                content_hash
            ) VALUES (?, ?, ?, 'supersedes', ?, 'operator', ?, ?, ?, ?, ?, ?)
            """,
            (
                relationship.relationship_id,
                relationship.source_record_id,
                relationship.target_record_id,
                relationship.created_at,
                grant.grant_id,
                grant.authority_record_id,
                grant.evidence_id,
                relationship.explanation,
                canonical,
                digest,
            ),
        )
        self._after_write_step(f"{step}.relationship")
        connection.execute(
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
        self._after_write_step(f"{step}.consume")

    def _supersede_prior(
        self,
        connection: sqlite3.Connection,
        *,
        prior_record_id: str,
        replacement_record_id: str,
        transition_id: str,
        changed_at: str,
        changed_by_entity_id: str,
        reason_code: str,
        step: str,
    ) -> None:
        self._transition_lifecycle(
            connection,
            prior_record_id,
            transition_id=transition_id,
            to_state="superseded",
            reason_code=reason_code,
            changed_at=changed_at,
            changed_by_principal="operator",
            changed_by_entity_id=changed_by_entity_id,
            step=f"{step}.lifecycle",
        )
        connection.execute(
            """
            UPDATE records
            SET superseded_by_record_id = ?
            WHERE record_id = ?
            """,
            (replacement_record_id, prior_record_id),
        )
        self._after_write_step(f"{step}.lineage")

    def _validate_capability_activation(
        self,
        connection: sqlite3.Connection,
        record: sqlite3.Row,
        payload: CapabilityObservationPayload,
        *,
        effective_at: str,
    ) -> None:
        anchors = self._validate_anchor_set(
            connection,
            payload.evaluation_record_ids,
            expected_kind="capability_evaluation",
            project_scope_id=record["project_scope_id"],
        )
        if payload.stability == "unconfirmed":
            registered = any(
                anchor["current_state"] == "registered" for anchor in anchors
            )
            if registered:
                if payload.developmental_policy_id is None:
                    raise ValidationError(
                        "registered anchors require an applicable capability policy"
                    )
                policy, _ = self._validate_policy(
                    connection,
                    payload.developmental_policy_id,
                    expected_kind="capability_stability",
                    project_scope_id=record["project_scope_id"],
                    effective_at=effective_at,
                )
                configuration = capability_policy_configuration(
                    policy.configuration
                )
                if not configuration["allow_registered_for_unconfirmed"]:
                    raise ValidationError(
                        "policy forbids registered anchors for unconfirmed capability"
                    )
        else:
            if len(anchors) < 2:
                raise ValidationError(
                    "one isolated evaluation cannot establish higher stability"
                )
            if any(anchor["current_state"] != "claimed" for anchor in anchors):
                raise ValidationError(
                    "higher capability stability requires claimed evaluations"
                )
            if payload.developmental_policy_id is None:
                raise ValidationError("higher capability stability requires policy")
            policy, _ = self._validate_policy(
                connection,
                payload.developmental_policy_id,
                expected_kind="capability_stability",
                project_scope_id=record["project_scope_id"],
                effective_at=effective_at,
            )
            configuration = capability_policy_configuration(policy.configuration)
            requirement = configuration["stability_requirements"][
                payload.stability
            ]
            if (
                len(anchors) < requirement["minimum_claimed_evaluations"]
                or payload.sample_size < requirement["minimum_sample_size"]
            ):
                raise ValidationError(
                    "capability evidence does not satisfy its exact approved policy"
                )
        evidence_rows = [
            self._validated_evidence(
                connection,
                row["evidence_id"],
                allow_model_output=True,
            )
            for row in connection.execute(
                """
                SELECT evidence_id
                FROM record_evidence_links
                WHERE record_id = ?
                ORDER BY evidence_id
                """,
                (record["record_id"],),
            )
        ]
        if not any(
            evidence["evidence_kind"] != "model_output"
            for evidence in evidence_rows
        ):
            raise ValidationError(
                "model output alone cannot establish a capability observation"
            )

    def _validate_maturity_activation(
        self,
        connection: sqlite3.Connection,
        record: sqlite3.Row,
        payload: MaturityStatePayload,
        *,
        effective_at: str,
    ) -> None:
        if payload.stage not in B87_S1_ACTIVE_MATURITY_STAGES:
            raise ValidationError(
                "maturity stage is recognized but prohibited during B87-S1"
            )
        if payload.entered_at != effective_at:
            raise ValidationError("maturity entered_at must equal activation time")
        anchors = self._validate_anchor_set(
            connection,
            payload.basis,
            expected_kind="maturity_evaluation",
            project_scope_id=record["project_scope_id"],
            required_state="claimed",
        )
        policy, _ = self._validate_policy(
            connection,
            payload.developmental_policy_id,
            expected_kind="maturity_progression",
            project_scope_id=record["project_scope_id"],
            effective_at=effective_at,
        )
        configuration = maturity_policy_configuration(policy.configuration)
        prior_stage: str | None = None
        if record["supersedes_record_id"] is not None:
            prior = connection.execute(
                """
                SELECT stage
                FROM maturity_states
                WHERE record_id = ?
                """,
                (record["supersedes_record_id"],),
            ).fetchone()
            if prior is None:
                raise ValidationError("maturity supersession target is missing")
            prior_stage = prior["stage"]
        matches = [
            transition
            for transition in configuration["stage_transitions"]
            if transition["from_stage"] == prior_stage
            and transition["to_stage"] == payload.stage
        ]
        if len(matches) != 1:
            raise ValidationError(
                "approved maturity policy does not permit this exact transition"
            )
        if len(anchors) < matches[0]["minimum_claimed_evaluations"]:
            raise ValidationError(
                "maturity basis does not meet the approved policy threshold"
            )

    def _factual_payload(
        self,
        connection: sqlite3.Connection,
        record: sqlite3.Row,
    ) -> FactualSelfPayload:
        table = FACTUAL_SELF_PAYLOAD_TABLES.get(record["record_type"])
        if table is None:
            raise ValidationError("record is not a C1 factual self type")
        row = connection.execute(
            f"SELECT * FROM {table} WHERE record_id = ?",
            (record["record_id"],),
        ).fetchone()
        if row is None:
            raise ValidationError("factual self record is missing its payload")
        evaluations: tuple[str, ...] = ()
        if record["record_type"] == "capability_observation":
            evaluations = tuple(
                item["evaluation_record_id"]
                for item in connection.execute(
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
            evaluations = tuple(
                item["evaluation_record_id"]
                for item in connection.execute(
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
            dict(row),
            evaluation_record_ids=evaluations,
        )

    def activate_capability_observation(
        self,
        record_id: str,
        *,
        reviewed_transition_id: str,
        approval_grant: MemoryApprovalGrant,
        approval_transition_id: str,
        approved_transition_id: str,
        active_transition_id: str,
        changed_at: str,
        changed_by_entity_id: str,
        relationship_grant: MemoryRelationshipGrant | None = None,
        relationship: RecordRelationship | None = None,
        prior_superseded_transition_id: str | None = None,
    ) -> None:
        """Approve and activate, or atomically supersede, one capability record."""

        validate_identifier(record_id, field="record_id")
        parse_canonical_utc(changed_at, field="changed_at")

        def operation(connection: sqlite3.Connection) -> None:
            self._validate_changed_by(
                connection,
                changed_by_principal="operator",
                changed_by_entity_id=changed_by_entity_id,
                accepted_principals=frozenset({"operator"}),
            )
            record = connection.execute(
                "SELECT * FROM records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if (
                record is None
                or record["record_type"] != "capability_observation"
                or record["record_family"] != "self_model"
                or record["lifecycle_state"] != "candidate"
                or approval_grant.record_id != record_id
                or approval_grant.approved_by_entity_id
                != changed_by_entity_id
            ):
                raise ValidationError(
                    "capability activation target or approval is inconsistent"
                )
            payload = self._factual_payload(connection, record)
            assert isinstance(payload, CapabilityObservationPayload)
            self._validate_capability_activation(
                connection,
                record,
                payload,
                effective_at=changed_at,
            )
            self._transition_lifecycle(
                connection,
                record_id,
                transition_id=reviewed_transition_id,
                to_state="reviewed",
                reason_code="capability_review_complete",
                changed_at=changed_at,
                changed_by_principal="operator",
                changed_by_entity_id=changed_by_entity_id,
                step="capability.activate.reviewed",
            )
            self._approve_record(
                connection,
                approval_grant,
                transition_id=approval_transition_id,
                reason_code="capability_observation_approved",
                changed_at=changed_at,
                step="capability.activate.approval",
            )
            self._transition_lifecycle(
                connection,
                record_id,
                transition_id=approved_transition_id,
                to_state="approved",
                reason_code="capability_observation_approved",
                changed_at=changed_at,
                changed_by_principal="operator",
                changed_by_entity_id=changed_by_entity_id,
                step="capability.activate.approved",
            )
            prior_id = record["supersedes_record_id"]
            supplied = (
                relationship_grant,
                relationship,
                prior_superseded_transition_id,
            )
            if prior_id is None and any(item is not None for item in supplied):
                raise ValidationError(
                    "initial capability activation cannot consume supersession inputs"
                )
            if prior_id is not None:
                if any(item is None for item in supplied):
                    raise ValidationError(
                        "capability replacement requires exact supersession inputs"
                    )
                assert relationship_grant is not None
                assert relationship is not None
                assert prior_superseded_transition_id is not None
                if (
                    relationship_grant.source_record_id != record_id
                    or relationship_grant.target_record_id != prior_id
                ):
                    raise ValidationError(
                        "capability supersession endpoints are incorrect"
                    )
                self._link_supersession(
                    connection,
                    relationship_grant,
                    relationship,
                    effective_at=changed_at,
                    step="capability.activate.supersession",
                )
                self._supersede_prior(
                    connection,
                    prior_record_id=prior_id,
                    replacement_record_id=record_id,
                    transition_id=prior_superseded_transition_id,
                    changed_at=changed_at,
                    changed_by_entity_id=changed_by_entity_id,
                    reason_code="capability_observation_superseded",
                    step="capability.activate.prior",
                )
            self._transition_lifecycle(
                connection,
                record_id,
                transition_id=active_transition_id,
                to_state="active",
                reason_code="capability_observation_activated",
                changed_at=changed_at,
                changed_by_principal="operator",
                changed_by_entity_id=changed_by_entity_id,
                step="capability.activate.active",
            )

        self._kernel.write(operation)

    def activate_maturity_state(
        self,
        record_id: str,
        *,
        approval_grant: MemoryApprovalGrant,
        approval_transition_id: str,
        approved_transition_id: str,
        active_transition_id: str,
        changed_at: str,
        changed_by_entity_id: str,
        relationship_grant: MemoryRelationshipGrant | None = None,
        relationship: RecordRelationship | None = None,
        prior_superseded_transition_id: str | None = None,
    ) -> None:
        """Approve and activate one policy-supported maturity transition atomically."""

        validate_identifier(record_id, field="record_id")
        parse_canonical_utc(changed_at, field="changed_at")

        def operation(connection: sqlite3.Connection) -> None:
            self._validate_changed_by(
                connection,
                changed_by_principal="operator",
                changed_by_entity_id=changed_by_entity_id,
                accepted_principals=frozenset({"operator"}),
            )
            record = connection.execute(
                "SELECT * FROM records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if (
                record is None
                or record["record_type"] != "maturity_state"
                or record["record_family"] != "self_model"
                or record["lifecycle_state"] != "reviewed"
                or approval_grant.record_id != record_id
                or approval_grant.approved_by_entity_id
                != changed_by_entity_id
            ):
                raise ValidationError(
                    "maturity activation target or approval is inconsistent"
                )
            payload = self._factual_payload(connection, record)
            assert isinstance(payload, MaturityStatePayload)
            self._validate_maturity_activation(
                connection,
                record,
                payload,
                effective_at=changed_at,
            )
            self._approve_record(
                connection,
                approval_grant,
                transition_id=approval_transition_id,
                reason_code="maturity_state_approved",
                changed_at=changed_at,
                step="maturity.activate.approval",
            )
            self._transition_lifecycle(
                connection,
                record_id,
                transition_id=approved_transition_id,
                to_state="approved",
                reason_code="maturity_state_approved",
                changed_at=changed_at,
                changed_by_principal="operator",
                changed_by_entity_id=changed_by_entity_id,
                step="maturity.activate.approved",
            )
            prior_id = record["supersedes_record_id"]
            supplied = (
                relationship_grant,
                relationship,
                prior_superseded_transition_id,
            )
            if prior_id is None and any(item is not None for item in supplied):
                raise ValidationError(
                    "initial maturity activation cannot consume supersession inputs"
                )
            if prior_id is not None:
                if any(item is None for item in supplied):
                    raise ValidationError(
                        "maturity replacement requires exact supersession inputs"
                    )
                assert relationship_grant is not None
                assert relationship is not None
                assert prior_superseded_transition_id is not None
                self._link_supersession(
                    connection,
                    relationship_grant,
                    relationship,
                    effective_at=changed_at,
                    step="maturity.activate.supersession",
                )
                self._supersede_prior(
                    connection,
                    prior_record_id=prior_id,
                    replacement_record_id=record_id,
                    transition_id=prior_superseded_transition_id,
                    changed_at=changed_at,
                    changed_by_entity_id=changed_by_entity_id,
                    reason_code="maturity_state_superseded",
                    step="maturity.activate.prior",
                )
            self._transition_lifecycle(
                connection,
                record_id,
                transition_id=active_transition_id,
                to_state="active",
                reason_code="maturity_state_activated",
                changed_at=changed_at,
                changed_by_principal="operator",
                changed_by_entity_id=changed_by_entity_id,
                step="maturity.activate.active",
            )

        self._kernel.write(operation)

    def _create_runtime_identity_in_transaction(
        self,
        connection: sqlite3.Connection,
        envelope: RecordEnvelope,
        payload: RuntimeIdentityPayload,
        *,
        initial_lifecycle_transition_id: str,
        initial_approval_transition_id: str,
        reviewed_transition_id: str,
        approved_transition_id: str,
        active_transition_id: str,
        evidence_links: Sequence[EvidenceLink],
        changed_by_principal: str,
        changed_by_entity_id: str | None,
        prior_record_id: str | None = None,
        relationship_grant: MemoryRelationshipGrant | None = None,
        relationship: RecordRelationship | None = None,
        prior_superseded_transition_id: str | None = None,
    ) -> str:
        digest = self._create_record_rows(
            connection,
            envelope,
            payload,
            lifecycle_transition_id=initial_lifecycle_transition_id,
            approval_transition_id=initial_approval_transition_id,
            evidence_items=(),
            evidence_links=evidence_links,
            changed_by_principal=changed_by_principal,
            changed_by_entity_id=changed_by_entity_id,
            reason_code="runtime_identity_observed",
            prefix="runtime_identity.create",
        )
        self._transition_lifecycle(
            connection,
            payload.record_id,
            transition_id=reviewed_transition_id,
            to_state="reviewed",
            reason_code="runtime_identity_attestation_reviewed",
            changed_at=envelope.created_at,
            changed_by_principal=changed_by_principal,
            changed_by_entity_id=changed_by_entity_id,
            step="runtime_identity.reviewed",
        )
        self._transition_lifecycle(
            connection,
            payload.record_id,
            transition_id=approved_transition_id,
            to_state="approved",
            reason_code="runtime_identity_attestation_valid",
            changed_at=envelope.created_at,
            changed_by_principal=changed_by_principal,
            changed_by_entity_id=changed_by_entity_id,
            step="runtime_identity.approved",
        )
        if prior_record_id is not None:
            if (
                relationship_grant is None
                or relationship is None
                or prior_superseded_transition_id is None
            ):
                raise ValidationError(
                    "runtime identity replacement requires exact supersession inputs"
                )
            self._link_supersession(
                connection,
                relationship_grant,
                relationship,
                effective_at=envelope.created_at,
                step="runtime_identity.supersession",
            )
            if changed_by_entity_id is None:
                raise ValidationError(
                    "runtime identity replacement requires operator attribution"
                )
            self._supersede_prior(
                connection,
                prior_record_id=prior_record_id,
                replacement_record_id=payload.record_id,
                transition_id=prior_superseded_transition_id,
                changed_at=envelope.created_at,
                changed_by_entity_id=changed_by_entity_id,
                reason_code="runtime_identity_superseded",
                step="runtime_identity.prior",
            )
        self._transition_lifecycle(
            connection,
            payload.record_id,
            transition_id=active_transition_id,
            to_state="active",
            reason_code="runtime_identity_activated",
            changed_at=envelope.created_at,
            changed_by_principal=changed_by_principal,
            changed_by_entity_id=changed_by_entity_id,
            step="runtime_identity.active",
        )
        return digest

    def create_runtime_identity(
        self,
        envelope: RecordEnvelope,
        payload: RuntimeIdentityPayload,
        *,
        initial_lifecycle_transition_id: str,
        initial_approval_transition_id: str,
        reviewed_transition_id: str,
        approved_transition_id: str,
        active_transition_id: str,
        evidence_links: Sequence[EvidenceLink],
        changed_by_principal: str,
        changed_by_entity_id: str | None = None,
    ) -> str:
        """Create and activate the first exactly attested runtime identity."""

        validate_factual_self_pair(envelope, payload)
        self._validate_record_principal(
            envelope,
            payload,
            changed_by_principal=changed_by_principal,
            changed_by_entity_id=changed_by_entity_id,
        )
        if envelope.supersedes_record_id is not None:
            raise ValidationError(
                "initial runtime identity cannot declare a supersession target"
            )
        self._validate_evidence_inputs(envelope, (), evidence_links)
        self._validate_runtime_evidence_links(payload, evidence_links)

        def operation(connection: sqlite3.Connection) -> str:
            duplicate = connection.execute(
                """
                SELECT 1
                FROM runtime_identities AS identity
                JOIN records AS record ON record.record_id = identity.record_id
                WHERE identity.agent_entity_id = ?
                  AND record.project_scope_id = ?
                  AND record.lifecycle_state = 'active'
                """,
                (payload.agent_entity_id, envelope.project_scope_id),
            ).fetchone()
            if duplicate is not None:
                raise ValidationError(
                    "existing runtime identity requires explicit replacement"
                )
            return self._create_runtime_identity_in_transaction(
                connection,
                envelope,
                payload,
                initial_lifecycle_transition_id=initial_lifecycle_transition_id,
                initial_approval_transition_id=initial_approval_transition_id,
                reviewed_transition_id=reviewed_transition_id,
                approved_transition_id=approved_transition_id,
                active_transition_id=active_transition_id,
                evidence_links=evidence_links,
                changed_by_principal=changed_by_principal,
                changed_by_entity_id=changed_by_entity_id,
            )

        return self._kernel.write(operation)

    def replace_runtime_identity(
        self,
        envelope: RecordEnvelope,
        payload: RuntimeIdentityPayload,
        *,
        initial_lifecycle_transition_id: str,
        initial_approval_transition_id: str,
        reviewed_transition_id: str,
        approved_transition_id: str,
        prior_superseded_transition_id: str,
        active_transition_id: str,
        relationship_grant: MemoryRelationshipGrant,
        relationship: RecordRelationship,
        evidence_links: Sequence[EvidenceLink],
        changed_by_entity_id: str,
    ) -> str:
        """Atomically replace one active identity; failure leaves the prior current."""

        validate_factual_self_pair(envelope, payload)
        if envelope.supersedes_record_id is None:
            raise ValidationError(
                "runtime identity replacement requires supersedes_record_id"
            )
        self._validate_record_principal(
            envelope,
            payload,
            changed_by_principal="operator",
            changed_by_entity_id=changed_by_entity_id,
        )
        self._validate_evidence_inputs(envelope, (), evidence_links)
        self._validate_runtime_evidence_links(payload, evidence_links)

        def operation(connection: sqlite3.Connection) -> str:
            self._validate_declared_supersession(connection, envelope, payload)
            if (
                relationship_grant.source_record_id != payload.record_id
                or relationship_grant.target_record_id
                != envelope.supersedes_record_id
            ):
                raise ValidationError(
                    "runtime identity supersession endpoints are incorrect"
                )
            return self._create_runtime_identity_in_transaction(
                connection,
                envelope,
                payload,
                initial_lifecycle_transition_id=initial_lifecycle_transition_id,
                initial_approval_transition_id=initial_approval_transition_id,
                reviewed_transition_id=reviewed_transition_id,
                approved_transition_id=approved_transition_id,
                active_transition_id=active_transition_id,
                evidence_links=evidence_links,
                changed_by_principal="operator",
                changed_by_entity_id=changed_by_entity_id,
                prior_record_id=envelope.supersedes_record_id,
                relationship_grant=relationship_grant,
                relationship=relationship,
                prior_superseded_transition_id=prior_superseded_transition_id,
            )

        return self._kernel.write(operation)

    def reconstruct(
        self,
        record_id: str,
        *,
        permission_profile: PermissionProfile | None = None,
        permission_effective_at: str | None = None,
    ) -> Mapping[str, Any]:
        """Return exact C1 truth with absent values represented explicitly."""

        validate_identifier(record_id, field="record_id")
        if (permission_profile is None) != (permission_effective_at is None):
            raise ValidationError(
                "permission projection requires both profile and effective_at"
            )

        def operation(connection: sqlite3.Connection) -> dict[str, Any]:
            record = connection.execute(
                "SELECT * FROM records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if record is None:
                raise NotFoundError(f"record not found: {record_id}")
            if (
                record["record_family"] != "self_model"
                or record["record_type"] not in FACTUAL_SELF_PAYLOAD_TABLES
            ):
                raise ValidationError("record is not an implemented C1 self record")
            payload = self._factual_payload(connection, record)
            envelope = _record_envelope(record)
            recomputed = factual_self_content_hash(envelope, payload)
            evidence = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT link.relationship, link.explanation, item.*
                    FROM record_evidence_links AS link
                    JOIN evidence_items AS item
                      ON item.evidence_id = link.evidence_id
                    WHERE link.record_id = ?
                    ORDER BY item.evidence_id, link.relationship
                    """,
                    (record_id,),
                )
            ]
            evaluations: list[dict[str, Any]] = []
            evaluation_ids: Sequence[str] = ()
            if isinstance(payload, CapabilityObservationPayload):
                evaluation_ids = payload.evaluation_record_ids
            elif isinstance(payload, MaturityStatePayload):
                evaluation_ids = payload.basis
            for evaluation_id in evaluation_ids:
                anchor = connection.execute(
                    """
                    SELECT *
                    FROM governed_evaluation_record_anchors
                    WHERE evaluation_record_id = ?
                    """,
                    (evaluation_id,),
                ).fetchone()
                if anchor is None:
                    evaluations.append(
                        {
                            "evaluation_record_id": evaluation_id,
                            "anchor": None,
                            "state_history": [],
                        }
                    )
                    continue
                evaluations.append(
                    {
                        "anchor": dict(anchor),
                        "evaluation_record_id": evaluation_id,
                        "state_history": [
                            dict(history)
                            for history in connection.execute(
                                """
                                SELECT *
                                FROM governed_evaluation_anchor_state_history
                                WHERE evaluation_record_id = ?
                                ORDER BY sequence_number, transition_id
                                """,
                                (evaluation_id,),
                            )
                        ],
                    }
                )
            policy_id = getattr(payload, "developmental_policy_id", None)
            policy = None
            if policy_id is not None:
                row = connection.execute(
                    """
                    SELECT *
                    FROM developmental_policy_versions
                    WHERE developmental_policy_id = ?
                    """,
                    (policy_id,),
                ).fetchone()
                policy = None if row is None else dict(row)
                if policy is not None:
                    policy["configuration"] = parse_json(
                        policy["configuration_json"]
                    )
            runtime_instance = None
            runtime_substrate_attestation = None
            trusted_runtime_attestor = None
            if isinstance(payload, RuntimeIdentityPayload):
                row = connection.execute(
                    """
                    SELECT *
                    FROM runtime_instances
                    WHERE runtime_instance_id = ?
                    """,
                    (payload.runtime_instance_id,),
                ).fetchone()
                runtime_instance = None if row is None else dict(row)
                row = connection.execute(
                    """
                    SELECT *
                    FROM runtime_substrate_attestations
                    WHERE substrate_attestation_evidence_id = ?
                    """,
                    (payload.substrate_attestation_evidence_id,),
                ).fetchone()
                runtime_substrate_attestation = (
                    None if row is None else dict(row)
                )
                if row is not None:
                    trusted_row = connection.execute(
                        """
                        SELECT *
                        FROM trusted_runtime_attestors
                        WHERE trusted_attestor_id = ?
                        """,
                        (row["trusted_attestor_id"],),
                    ).fetchone()
                    trusted_runtime_attestor = (
                        None if trusted_row is None else dict(trusted_row)
                    )
            lifecycle = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM memory_record_lifecycle_transitions
                    WHERE record_id = ?
                    ORDER BY sequence_number, transition_id
                    """,
                    (record_id,),
                )
            ]
            approvals = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM memory_record_approval_transitions
                    WHERE record_id = ?
                    ORDER BY sequence_number, transition_id
                    """,
                    (record_id,),
                )
            ]
            grants = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM memory_approval_grants
                    WHERE record_id = ?
                    ORDER BY approved_at, grant_id
                    """,
                    (record_id,),
                )
            ]
            relationships = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM record_relationships
                    WHERE source_record_id = ? OR target_record_id = ?
                    ORDER BY created_at, relationship_id
                    """,
                    (record_id, record_id),
                )
            ]
            assessments: list[dict[str, Any]] = []
            for row in connection.execute(
                """
                SELECT *
                FROM memory_eligibility_assessments
                WHERE record_id = ?
                ORDER BY evaluated_at, assessment_id
                """,
                (record_id,),
            ):
                value = dict(row)
                value["reason_codes"] = parse_json(value["reason_codes_json"])
                value["record_snapshot"] = parse_json(
                    value["record_snapshot_json"]
                )
                value["context"] = parse_json(value["context_json"])
                assessments.append(value)
            return {
                "approval_grants": grants,
                "approval_transitions": approvals,
                "content_hash": record["content_hash"],
                "developmental_policy_version": policy,
                "eligibility_assessments": assessments,
                "evaluation_anchors": evaluations,
                "evidence": evidence,
                "lifecycle_transitions": lifecycle,
                "memory_domain": "self_episodic",
                "payload": payload.canonical_content(),
                "payload_type": record["record_type"],
                "permission_profile_projection": None,
                "recomputed_content_hash": recomputed,
                "record": dict(record),
                "relationships": relationships,
                "runtime_identity": (
                    payload.canonical_content()
                    if isinstance(payload, RuntimeIdentityPayload)
                    else None
                ),
                "runtime_instance": runtime_instance,
                "runtime_substrate_attestation": (
                    runtime_substrate_attestation
                ),
                "trusted_runtime_attestor": trusted_runtime_attestor,
            }

        result = self._kernel.read(operation)
        from .self_episodic_integrity import SelfEpisodicIntegrityInspector

        report = SelfEpisodicIntegrityInspector(self._kernel).inspect()
        findings = [
            {
                "code": finding.code,
                "detail": finding.detail,
                "record_id": finding.record_id,
                "severity": finding.severity,
                "source": "self_episodic_integrity",
            }
            for finding in report.findings
            if finding.record_id in {None, record_id}
        ]
        result["integrity"] = {
            "findings": findings,
            "hash_matches": (
                result["content_hash"] == result["recomputed_content_hash"]
            ),
            "stored_status": result["record"]["integrity_status"],
            "valid": (
                result["content_hash"] == result["recomputed_content_hash"]
                and result["record"]["integrity_status"] == "valid"
                and not any(
                    finding["severity"] == "error" for finding in findings
                )
            ),
        }
        if permission_profile is not None:
            from .self_model_projection import PermissionProfileProjection

            result["permission_profile_projection"] = (
                PermissionProfileProjection(
                    self._kernel.config
                ).current_runtime(
                    permission_profile,
                    effective_at=permission_effective_at or "",
                )
            )
        return result
