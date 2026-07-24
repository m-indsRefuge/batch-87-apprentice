"""Public composition root for the B87-I2 governed task runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.identifiers import (
    generate_identifier,
    validate_identifier,
)
from batch87_apprentice.common.timestamps import (
    canonical_utc_now,
    parse_canonical_utc,
)
from batch87_apprentice.governance.contracts import (
    AuthorityRecord,
    EvaluationResult,
    HumanApproval,
    OperationDefinition,
    active_b87_s1_permission_profile,
    active_governance_rules,
)
from batch87_apprentice.governance.engine import (
    EvaluationIdentifiers,
    GovernanceEngine,
)
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.contracts import EvidenceItem
from batch87_apprentice.persistence.migrations import MigrationRunner
from batch87_apprentice.persistence.task_runtime_store import TaskRuntimeStore
from batch87_apprentice.protocols.task_contracts import (
    PolicyViolation,
    SessionContract,
    TaskContract,
)


@dataclass(frozen=True, slots=True)
class TaskReconstruction:
    """Integrity-verified, canonical reconstruction of one I2 transaction."""

    canonical_json: str
    content_hash: str
    value: Mapping[str, Any]
    integrity_verified: bool = True


class GovernedTaskRuntime:
    """Evaluate typed task contracts without a model-controlled decision path."""

    def __init__(
        self,
        config: DatabaseConfig,
        *,
        runtime_instance_id: str,
        infrastructure_principal: str = "codex_development_harness",
        clock: Callable[[], str] = canonical_utc_now,
        identifier_factory: Callable[[], str] = generate_identifier,
    ) -> None:
        validate_identifier(
            runtime_instance_id,
            field="runtime_instance_id",
        )
        if infrastructure_principal not in {
            "operator",
            "codex_development_harness",
        }:
            raise ValidationError(
                "runtime infrastructure principal must be operator or "
                "codex_development_harness"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        if not callable(identifier_factory):
            raise TypeError("identifier_factory must be callable")
        self._runtime_instance_id = runtime_instance_id
        self._infrastructure_principal = infrastructure_principal
        self._clock = clock
        self._identifier_factory = identifier_factory
        self._permission_profile = active_b87_s1_permission_profile()
        self._governance_rules = active_governance_rules()
        self._engine = GovernanceEngine()
        self._store = TaskRuntimeStore(config)
        self._store.ensure_policy_baseline(
            self._permission_profile,
            self._governance_rules,
        )

    @classmethod
    def initialize(
        cls,
        config: DatabaseConfig,
        *,
        runtime_instance_id: str,
        infrastructure_principal: str = "codex_development_harness",
        migrations_path: Path | None = None,
        clock: Callable[[], str] = canonical_utc_now,
        identifier_factory: Callable[[], str] = generate_identifier,
    ) -> GovernedTaskRuntime:
        """Apply verified migrations, then expose the governed runtime."""

        MigrationRunner(config, migrations_path).apply_all()
        return cls(
            config,
            runtime_instance_id=runtime_instance_id,
            infrastructure_principal=infrastructure_principal,
            clock=clock,
            identifier_factory=identifier_factory,
        )

    @property
    def runtime_instance_id(self) -> str:
        return self._runtime_instance_id

    @property
    def infrastructure_principal(self) -> str:
        return self._infrastructure_principal

    def open_session(self, session: SessionContract) -> str:
        """Persist an exact session contract and its initial transition."""

        if not isinstance(session, SessionContract):
            raise TypeError("session must be a validated SessionContract")
        if session.status != "open":
            raise ValidationError("new sessions must begin in open state")
        transition_id = self._identifier_factory()
        validate_identifier(transition_id, field="session_transition_id")
        return self._store.open_session(
            session,
            initial_transition_id=transition_id,
            changed_by_principal=self._infrastructure_principal,
        )

    def register_operation_definition(
        self,
        definition: OperationDefinition,
    ) -> str:
        """Register deterministic operation classification outside task input."""

        if not isinstance(definition, OperationDefinition):
            raise TypeError("definition must be an OperationDefinition")
        if definition.registered_by_principal != self._infrastructure_principal:
            raise ValidationError(
                "operation registrar does not match runtime infrastructure principal"
            )
        return self._store.register_operation_definition(definition)

    def register_human_approval(
        self,
        approval: HumanApproval,
        *,
        evidence_items: tuple[EvidenceItem, ...] = (),
    ) -> str:
        """Register explicit scoped approval before a task claims it."""

        if not isinstance(approval, HumanApproval):
            raise TypeError("approval must be a HumanApproval")
        if approval.registered_by_principal != self._infrastructure_principal:
            raise ValidationError(
                "approval registrar does not match runtime infrastructure principal"
            )
        if not isinstance(evidence_items, tuple):
            raise TypeError("evidence_items must be an immutable tuple")
        if any(not isinstance(item, EvidenceItem) for item in evidence_items):
            raise TypeError("evidence_items contains an invalid value")
        return self._store.register_human_approval(approval, evidence_items)

    def revoke_authority(
        self,
        authority_record_id: str,
        *,
        revoked_by_entity_id: str,
        reason: str,
        provenance_json: str,
    ) -> str:
        """Persist an append-only authority revocation."""

        revoked_at = self._clock()
        parse_canonical_utc(revoked_at, field="revocation clock")
        return self._store.revoke_authority(
            authority_record_id=authority_record_id,
            revoked_at=revoked_at,
            revoked_by_entity_id=revoked_by_entity_id,
            reason=reason,
            registered_by_principal=self._infrastructure_principal,
            provenance_json=provenance_json,
        )

    def transition_session(
        self,
        session_id: str,
        *,
        to_status: str,
        reason_code: str,
    ) -> str:
        """Apply one append-only governed session-state transition."""

        transition_id = self._identifier_factory()
        validate_identifier(transition_id, field="session_transition_id")
        changed_at = self._clock()
        parse_canonical_utc(changed_at, field="session transition clock")
        return self._store.transition_session(
            session_id=session_id,
            to_status=to_status,
            transition_id=transition_id,
            changed_at=changed_at,
            changed_by_principal=self._infrastructure_principal,
            reason_code=reason_code,
        )

    def transition_task(
        self,
        task_id: str,
        *,
        to_status: str,
        reason_code: str,
    ) -> str:
        """Complete or fail one active task through an append-only transition."""

        transition_id = self._identifier_factory()
        validate_identifier(transition_id, field="task_transition_id")
        changed_at = self._clock()
        parse_canonical_utc(changed_at, field="task transition clock")
        return self._store.transition_task(
            task_id=task_id,
            to_status=to_status,
            transition_id=transition_id,
            changed_at=changed_at,
            reason_code=reason_code,
        )

    def register_authority(
        self,
        record: AuthorityRecord,
        *,
        evidence_items: tuple[EvidenceItem, ...] = (),
    ) -> str:
        """Register a structured authority record before any task claims it."""

        if not isinstance(record, AuthorityRecord):
            raise TypeError("record must be a validated AuthorityRecord")
        if not isinstance(evidence_items, tuple):
            raise TypeError("evidence_items must be an immutable tuple")
        if any(not isinstance(item, EvidenceItem) for item in evidence_items):
            raise TypeError("evidence_items contains an invalid value")
        if record.registered_by_principal != self._infrastructure_principal:
            raise ValidationError(
                "authority registrar does not match runtime infrastructure principal"
            )
        return self._store.register_authority(record, evidence_items)

    def evaluate(
        self,
        task: TaskContract,
        *,
        evidence_items: tuple[EvidenceItem, ...] = (),
        policy_violations: tuple[PolicyViolation, ...] = (),
    ) -> EvaluationResult:
        """Evaluate and persist one complete task transaction atomically."""

        if not isinstance(task, TaskContract):
            raise TypeError("task must be a validated TaskContract")
        for field, value, expected_type in (
            ("evidence_items", evidence_items, EvidenceItem),
            ("policy_violations", policy_violations, PolicyViolation),
        ):
            if not isinstance(value, tuple):
                raise TypeError(f"{field} must be an immutable tuple")
            if any(not isinstance(item, expected_type) for item in value):
                raise TypeError(f"{field} contains an invalid value")

        decided_at = self._clock()
        parse_canonical_utc(decided_at, field="decision clock")
        generated = tuple(self._identifier_factory() for _ in range(5))
        labels = (
            "transaction_id",
            "governance_decision_id",
            "stop_event_id",
            "initial_transition_id",
            "terminal_transition_id",
        )
        for label, identifier in zip(labels, generated, strict=True):
            validate_identifier(identifier, field=label)
        if len(set(generated)) != len(generated):
            raise ValidationError(
                "identifier factory returned duplicate identifiers"
            )
        identifiers = EvaluationIdentifiers(*generated)

        return self._store.evaluate_task(
            task=task,
            evidence_items=evidence_items,
            policy_violations=policy_violations,
            permission_profile=self._permission_profile,
            governance_rules=self._governance_rules,
            engine=self._engine,
            identifiers=identifiers,
            decided_at=decided_at,
            runtime_instance_id=self._runtime_instance_id,
            runtime_execution_principal=self._infrastructure_principal,
        )

    def reconstruct(self, task_id: str) -> TaskReconstruction:
        """Reconstruct an exact persisted decision and verify all hashes."""

        value = self._store.reconstruct(task_id)
        return TaskReconstruction(
            canonical_json=value["canonical_json"],
            content_hash=value["content_hash"],
            integrity_verified=value["integrity_verified"],
            value=value["value"],
        )
