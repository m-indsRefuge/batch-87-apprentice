"""Deterministic file-backed fixtures for B87-I2 tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.governance.contracts import (
    AUTHORITY_SOURCE_BY_CLASS,
    AuthorityRecord,
    HumanApproval,
    OperationDefinition,
)
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.contracts import (
    Entity,
    EvidenceItem,
    RuntimeInstance,
    Scope,
)
from batch87_apprentice.persistence.service import PersistenceService
from batch87_apprentice.protocols.task_contracts import (
    RequestedOperation,
    SessionContract,
    TaskContract,
)
from batch87_apprentice.runtime.service import GovernedTaskRuntime

NOW = "2026-07-23T12:00:00.000000Z"
EARLIER = "2026-07-22T12:00:00.000000Z"
LATER = "2026-07-24T12:00:00.000000Z"


def uid(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012x}"


class IdentifierSequence:
    def __init__(self, start: int = 50_000) -> None:
        self._next = start

    def __call__(self) -> str:
        value = uid(self._next)
        self._next += 1
        return value


@dataclass(frozen=True, slots=True)
class I2Harness:
    config: DatabaseConfig
    persistence: PersistenceService
    runtime: GovernedTaskRuntime
    operator_id: str
    participant_id: str
    runtime_id: str
    project_scope_id: str
    task_scope_id: str
    nested_scope_id: str
    other_project_scope_id: str
    other_scope_id: str
    session_id: str


def build_harness(
    tmp_path: Path,
    *,
    identifier_start: int = 50_000,
) -> I2Harness:
    config = DatabaseConfig(tmp_path / "b87-i2.sqlite3")
    persistence = PersistenceService.initialize(config)
    operator_id = uid(1)
    participant_id = uid(2)
    runtime_id = uid(3)
    project_scope_id = uid(4)
    task_scope_id = uid(5)
    nested_scope_id = uid(6)
    other_project_scope_id = uid(7)
    other_scope_id = uid(8)
    session_id = uid(9)

    persistence.entities.create(
        Entity(
            entity_id=operator_id,
            entity_kind="person",
            canonical_name="Nolan",
            description="Deterministic Operator fixture.",
            status="active",
            created_at=NOW,
        )
    )
    persistence.entities.create(
        Entity(
            entity_id=participant_id,
            entity_kind="system",
            canonical_name="Codex development harness",
            description="Non-Apprentice infrastructure fixture.",
            status="active",
            created_at=NOW,
        )
    )
    persistence.runtime_instances.start(
        RuntimeInstance(
            runtime_instance_id=runtime_id,
            started_at=NOW,
            application_version="b87-i2-test",
        )
    )
    persistence.scopes.create(
        Scope(
            scope_id=project_scope_id,
            scope_kind="project",
            canonical_name="Batch-87",
            status="active",
        )
    )
    persistence.scopes.create(
        Scope(
            scope_id=task_scope_id,
            scope_kind="task",
            canonical_name="B87-I2",
            status="active",
            parent_scope_id=project_scope_id,
        )
    )
    persistence.scopes.create(
        Scope(
            scope_id=nested_scope_id,
            scope_kind="component",
            canonical_name="Governance kernel",
            status="active",
            parent_scope_id=task_scope_id,
        )
    )
    persistence.scopes.create(
        Scope(
            scope_id=other_project_scope_id,
            scope_kind="project",
            canonical_name="Other project",
            status="active",
        )
    )
    persistence.scopes.create(
        Scope(
            scope_id=other_scope_id,
            scope_kind="task",
            canonical_name="Other task",
            status="active",
            parent_scope_id=other_project_scope_id,
        )
    )

    runtime = GovernedTaskRuntime(
        config,
        runtime_instance_id=runtime_id,
        clock=lambda: NOW,
        identifier_factory=IdentifierSequence(identifier_start),
    )
    for operation_name, action_class, autonomous in (
        ("observe_fixture", "observe", False),
        ("analyse_fixture", "analyse", False),
        ("propose_fixture", "propose", False),
        ("execute_fixture", "execute", False),
        ("autonomous_execute_fixture", "execute", True),
    ):
        runtime.register_operation_definition(
            OperationDefinition(
                name=operation_name,
                action_class=action_class,
                autonomous=autonomous,
                registered_by_principal="codex_development_harness",
                registered_at=NOW,
                description=f"Deterministic {operation_name} operation.",
            )
        )

    runtime.open_session(
        SessionContract(
            session_id=session_id,
            purpose="Deterministic B87-I2 validation.",
            project_scope_id=project_scope_id,
            opened_at=NOW,
            created_by_entity_id=operator_id,
            participant_entity_ids=(operator_id, participant_id),
        )
    )
    return I2Harness(
        config=config,
        persistence=persistence,
        runtime=runtime,
        operator_id=operator_id,
        participant_id=participant_id,
        runtime_id=runtime_id,
        project_scope_id=project_scope_id,
        task_scope_id=task_scope_id,
        nested_scope_id=nested_scope_id,
        other_project_scope_id=other_project_scope_id,
        other_scope_id=other_scope_id,
        session_id=session_id,
    )


def evidence(
    number: int,
    *,
    content: str = "Structured Operator authority evidence.",
    captured_by_entity: str | None = None,
    evidence_kind: str = "human_statement",
) -> EvidenceItem:
    return EvidenceItem.inline_text(
        evidence_id=uid(number),
        evidence_kind=evidence_kind,
        content=content,
        captured_at=NOW,
        captured_by_entity=captured_by_entity,
    )


def authority(
    harness: I2Harness,
    number: int,
    *,
    evidence_ids: tuple[str, ...],
    authority_class: str = "approved_project_policy",
    effect: str = "allow",
    principal: str = "apprentice",
    permissions: tuple[str, ...] = ("observe",),
    project_scope_id: str | None = None,
    scope_id: str | None = None,
    issuer_entity_id: str | None = None,
    task_id: str | None = None,
    effective_from: str = EARLIER,
    effective_until: str | None = LATER,
    status: str = "active",
    registered_by_principal: str = "codex_development_harness",
) -> AuthorityRecord:
    if issuer_entity_id is None and authority_class in {
        "nolan_approved",
        "nolan_byte_approved",
    }:
        issuer_entity_id = harness.operator_id
    return AuthorityRecord(
        authority_record_id=uid(number),
        authority_class=authority_class,
        source_kind=AUTHORITY_SOURCE_BY_CLASS[authority_class],
        effect=effect,
        subject_principal=principal,
        permissions=permissions,
        project_scope_id=(
            harness.project_scope_id
            if project_scope_id is None
            else project_scope_id
        ),
        scope_id=harness.project_scope_id if scope_id is None else scope_id,
        issuer_entity_id=issuer_entity_id,
        task_id=task_id,
        effective_from=effective_from,
        effective_until=effective_until,
        status=status,
        evidence_ids=evidence_ids,
        provenance_json=canonical_json_text(
            {"source": "deterministic I2 test fixture"}
        ),
        registered_by_principal=registered_by_principal,
        registered_at=NOW,
    )


def human_approval(
    harness: I2Harness,
    number: int,
    *,
    evidence_ids: tuple[str, ...],
    requested_operation: str = "observe_fixture",
    principal: str = "apprentice",
    permissions: tuple[str, ...] = ("observe",),
    project_scope_id: str | None = None,
    scope_id: str | None = None,
    task_id: str | None = None,
    approved_at: str = NOW,
    expires_at: str | None = LATER,
    single_use: bool = True,
    conditions: tuple[str, ...] = (),
) -> HumanApproval:
    return HumanApproval(
        human_approval_id=uid(number),
        requested_operation=requested_operation,
        subject_principal=principal,
        permissions=permissions,
        project_scope_id=(
            harness.project_scope_id if project_scope_id is None else project_scope_id
        ),
        scope_id=harness.project_scope_id if scope_id is None else scope_id,
        task_id=task_id,
        approved_by_entity_id=harness.operator_id,
        approved_at=approved_at,
        expires_at=expires_at,
        conditions=conditions,
        single_use=single_use,
        evidence_ids=evidence_ids,
        provenance_json=canonical_json_text(
            {"source": "deterministic human approval fixture"}
        ),
        registered_by_principal="codex_development_harness",
        registered_at=NOW,
    )


def task(
    harness: I2Harness,
    number: int,
    *,
    authority_ids: tuple[str, ...],
    human_approval_ids: tuple[str, ...] = (),
    required_evidence_ids: tuple[str, ...] = (),
    action_class: str = "observe",
    operation_name: str | None = None,
    autonomous: bool = False,
    principal: str = "apprentice",
    authority_grant: tuple[str, ...] | None = None,
    project_scope_id: str | None = None,
    requested_scope_id: str | None = None,
    session_id: str | None = None,
    objective: str = "Inspect deterministic fixture.",
    provenance: dict[str, str] | None = None,
    task_type: str = "governed_analysis",
    governing_constraints: tuple[str, ...] = (
        "b87_s1_permissions",
        "structured_authority_only",
    ),
    prohibited_actions: tuple[str, ...] | None = None,
    expected_output_schema_id: str = (
        "https://batch87.local/schemas/output/test-analysis"
    ),
    stop_conditions: tuple[str, ...] = (
        "invalid_authority",
        "permission_violation",
        "context_policy_violation",
    ),
) -> TaskContract:
    if authority_grant is None:
        authority_grant = (
            (action_class,)
            if action_class in {"observe", "analyse", "propose", "execute"}
            else ()
        )
    return TaskContract(
        contract_version="1.0.0",
        task_id=uid(number),
        session_id=harness.session_id if session_id is None else session_id,
        project_scope_id=(
            harness.project_scope_id
            if project_scope_id is None
            else project_scope_id
        ),
        requested_scope_id=(
            harness.task_scope_id
            if requested_scope_id is None
            else requested_scope_id
        ),
        objective=objective,
        task_type=task_type,
        requested_operation=RequestedOperation(
            name=(
                operation_name
                or ("autonomous_execute_fixture" if autonomous else f"{action_class}_fixture")
            ),
            action_class=action_class,
            autonomous=autonomous,
        ),
        requesting_principal=principal,
        authority_grant=authority_grant,
        claimed_authority_ids=authority_ids,
        claimed_human_approval_ids=human_approval_ids,
        effective_at=NOW,
        governing_constraints=governing_constraints,
        required_evidence_ids=required_evidence_ids,
        allowed_sources=("approved_evidence",),
        prohibited_actions=(
            prohibited_actions
            if prohibited_actions is not None
            else (
                ("execute", "autonomous_action")
                if principal == "apprentice"
                else ("autonomous_action",)
            )
        ),
        expected_output_schema_id=expected_output_schema_id,
        stop_conditions=stop_conditions,
        provenance_json=canonical_json_text(
            provenance or {"source": "deterministic I2 test fixture"}
        ),
    )
