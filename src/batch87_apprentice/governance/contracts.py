"""Typed, canonical governance records for the B87-I2 runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc
from batch87_apprentice.protocols.task_contracts import (
    AUTHORITY_GRANT_CLASSES,
    EXECUTION_PRINCIPALS,
    PolicyViolation,
    RequestedOperation,
)

AUTHORITY_RECORD_VERSION = "1.0.0"
PERMISSION_PROFILE_VERSION = "1.0.0"
GOVERNANCE_RULE_VERSION = "1.0.0"
OPERATION_DEFINITION_VERSION = "1.0.0"
HUMAN_APPROVAL_VERSION = "1.0.0"

AUTHORITY_CLASS_PRECEDENCE = {
    "law_or_external_obligation": 1,
    "nolan_approved": 2,
    "nolan_byte_approved": 3,
    "validated_system_evidence": 4,
    "approved_project_policy": 5,
    "approved_memory": 6,
    "approved_evaluation": 7,
    "agent_proposal": 8,
    "model_inference": 9,
    "external_untrusted": 10,
    "unknown": 11,
}
AUTHORITY_SOURCE_BY_CLASS = {
    "law_or_external_obligation": "law_or_external_obligation_record",
    "nolan_approved": "nolan_approval_record",
    "nolan_byte_approved": "nolan_byte_approval_record",
    "validated_system_evidence": "validated_system_record",
    "approved_project_policy": "approved_project_policy_record",
    "approved_memory": "approved_memory_record",
    "approved_evaluation": "approved_evaluation_record",
    "agent_proposal": "agent_proposal",
    "model_inference": "model_output",
    "external_untrusted": "external_content",
    "unknown": "unknown",
}
AUTHORITY_EFFECTS = frozenset({"allow", "deny", "require_human_approval"})
AUTHORITY_STATUSES = frozenset({"active", "historical", "revoked"})
DECISION_OUTCOMES = frozenset(
    {"allow", "deny", "require_human_approval", "stop"}
)

B87_S1_PERMISSION_PROFILE_ID = "b8700000-0000-4000-8000-000000000002"
B87_S1_EFFECTIVE_FROM = "2026-07-22T00:00:00.000000Z"


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be non-empty text")
    return value


def _enum(value: object, accepted: set[str] | frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in accepted:
        raise ValidationError(f"{field} has an unsupported value: {value!r}")
    return value


def _identifiers(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ValidationError(f"{field} must be a tuple")
    if len(set(values)) != len(values):
        raise ValidationError(f"{field} must not contain duplicates")
    for value in values:
        validate_identifier(value, field=f"{field} item")
    return values


def _strings(
    values: tuple[str, ...],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ValidationError(f"{field} must be a tuple")
    if not allow_empty and not values:
        raise ValidationError(f"{field} must not be empty")
    if len(set(values)) != len(values):
        raise ValidationError(f"{field} must not contain duplicates")
    for value in values:
        _text(value, f"{field} item")
    return values


def _canonical_object(value: str, field: str) -> dict[str, Any]:
    parsed = parse_json(value)
    if (
        not isinstance(parsed, dict)
        or not parsed
        or canonical_json_text(parsed) != value
    ):
        raise ValidationError(f"{field} must be a non-empty canonical JSON object")
    return parsed


@dataclass(frozen=True, slots=True)
class PermissionProfile:
    """The immutable active B87-S1 Apprentice permission profile."""

    permission_profile_id: str
    version: str
    principal: str
    allowed_action_classes: tuple[str, ...]
    prohibited_action_classes: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    prohibited_tools: tuple[str, ...]
    effective_from: str

    def __post_init__(self) -> None:
        validate_identifier(
            self.permission_profile_id,
            field="permission_profile_id",
        )
        if self.version != PERMISSION_PROFILE_VERSION:
            raise ValidationError("unsupported permission profile version")
        if self.principal != "apprentice":
            raise ValidationError(
                "B87-S1 permission profile applies only to apprentice"
            )
        _strings(
            self.allowed_action_classes,
            "allowed_action_classes",
            allow_empty=False,
        )
        _strings(
            self.prohibited_action_classes,
            "prohibited_action_classes",
            allow_empty=False,
        )
        if self.allowed_action_classes != ("observe", "analyse"):
            raise ValidationError(
                "B87-S1 allowed permissions must be exactly Observe and Analyse"
            )
        if set(self.prohibited_action_classes) != {
            "propose",
            "execute",
            "autonomous_action",
        }:
            raise ValidationError(
                "B87-S1 prohibited permissions must include Propose, Execute, "
                "and autonomous action"
            )
        if self.allowed_tools:
            raise ValidationError("B87-S1 Apprentice has no allowed tools")
        _strings(self.prohibited_tools, "prohibited_tools", allow_empty=False)
        parse_canonical_utc(self.effective_from, field="effective_from")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "allowed_action_classes": list(self.allowed_action_classes),
            "allowed_tools": list(self.allowed_tools),
            "effective_from": self.effective_from,
            "permission_profile_id": self.permission_profile_id,
            "principal": self.principal,
            "prohibited_action_classes": list(self.prohibited_action_classes),
            "prohibited_tools": list(self.prohibited_tools),
            "version": self.version,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


def active_b87_s1_permission_profile() -> PermissionProfile:
    return PermissionProfile(
        permission_profile_id=B87_S1_PERMISSION_PROFILE_ID,
        version=PERMISSION_PROFILE_VERSION,
        principal="apprentice",
        allowed_action_classes=("observe", "analyse"),
        prohibited_action_classes=(
            "propose",
            "execute",
            "autonomous_action",
        ),
        allowed_tools=(),
        prohibited_tools=(
            "shell",
            "filesystem_write",
            "repository_write",
            "database_write",
            "network",
            "credentials",
            "communications",
            "autonomous_tool_use",
        ),
        effective_from=B87_S1_EFFECTIVE_FROM,
    )


@dataclass(frozen=True, slots=True)
class GovernanceRule:
    governance_rule_id: str
    name: str
    version: str
    kind: str
    description: str
    configuration_json: str

    def __post_init__(self) -> None:
        validate_identifier(self.governance_rule_id, field="governance_rule_id")
        _text(self.name, "governance rule name")
        if self.version != GOVERNANCE_RULE_VERSION:
            raise ValidationError("unsupported governance rule version")
        _text(self.kind, "governance rule kind")
        _text(self.description, "governance rule description")
        _canonical_object(self.configuration_json, "configuration_json")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "configuration": parse_json(self.configuration_json),
            "description": self.description,
            "governance_rule_id": self.governance_rule_id,
            "kind": self.kind,
            "name": self.name,
            "version": self.version,
        }

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


def active_governance_rules() -> tuple[GovernanceRule, ...]:
    specifications = (
        (
            "b8700000-0000-4000-8000-000000000101",
            "b87_s1_permission_boundary",
            "permission",
            "Apprentice permissions are Observe and Analyse only.",
            {
                "allowed": ["observe", "analyse"],
                "prohibited": ["propose", "execute", "autonomous_action"],
            },
        ),
        (
            "b8700000-0000-4000-8000-000000000102",
            "structured_authority_validity",
            "authority",
            "Authority must be structured, in scope, effective, and evidenced.",
            {
                "fail_closed": [
                    "missing",
                    "unsupported",
                    "expired",
                    "future",
                    "out_of_scope",
                ]
            },
        ),
        (
            "b8700000-0000-4000-8000-000000000103",
            "authority_precedence",
            "authority",
            "Lower authority cannot override higher authority.",
            {"ordering": list(AUTHORITY_CLASS_PRECEDENCE)},
        ),
        (
            "b8700000-0000-4000-8000-000000000104",
            "execution_principal_attribution",
            "principal",
            "Infrastructure execution is never attributed to the Apprentice.",
            {
                "principals": [
                    "apprentice",
                    "operator",
                    "codex_development_harness",
                    "experimental_harness",
                ]
            },
        ),
        (
            "b8700000-0000-4000-8000-000000000105",
            "governance_stop_persistence",
            "stop",
            "Unsafe or policy-invalid requests stop with preserved evidence.",
            {
                "stop_conditions": [
                    "invalid_authority",
                    "prohibited_operation",
                    "context_policy_violation",
                    "integrity_violation",
                ]
            },
        ),
    )
    return tuple(
        GovernanceRule(
            governance_rule_id=identifier,
            name=name,
            version=GOVERNANCE_RULE_VERSION,
            kind=kind,
            description=description,
            configuration_json=canonical_json_text(configuration),
        )
        for identifier, name, kind, description, configuration in specifications
    )


@dataclass(frozen=True, slots=True)
class OperationDefinition:
    """Operator-registered operation classification; task claims cannot define it."""

    name: str
    action_class: str
    autonomous: bool
    registered_by_principal: str
    registered_at: str
    description: str
    schema_version: str = OPERATION_DEFINITION_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OPERATION_DEFINITION_VERSION:
            raise ValidationError("unsupported operation definition version")
        requested = RequestedOperation(
            name=self.name,
            action_class=self.action_class,
            autonomous=self.autonomous,
        )
        if requested.action_class == "ambiguous":
            raise ValidationError(
                "registered operation definitions cannot be ambiguous"
            )
        _enum(
            self.registered_by_principal,
            EXECUTION_PRINCIPALS,
            "registered_by_principal",
        )
        if self.registered_by_principal in {
            "apprentice",
            "experimental_harness",
        }:
            raise ValidationError(
                "operation registration requires governed infrastructure"
            )
        parse_canonical_utc(self.registered_at, field="registered_at")
        _text(self.description, "operation definition description")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "action_class": self.action_class,
            "autonomous": self.autonomous,
            "description": self.description,
            "name": self.name,
            "registered_at": self.registered_at,
            "registered_by_principal": self.registered_by_principal,
            "schema_version": self.schema_version,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())

    @property
    def requested_operation(self) -> RequestedOperation:
        return RequestedOperation(
            name=self.name,
            action_class=self.action_class,
            autonomous=self.autonomous,
        )


@dataclass(frozen=True, slots=True)
class HumanApproval:
    """Explicit, scoped, time-aware human authorisation for one operation."""

    human_approval_id: str
    requested_operation: str
    subject_principal: str
    permissions: tuple[str, ...]
    project_scope_id: str
    scope_id: str
    approved_by_entity_id: str
    approved_at: str
    conditions: tuple[str, ...]
    single_use: bool
    evidence_ids: tuple[str, ...]
    provenance_json: str
    registered_by_principal: str
    registered_at: str
    task_id: str | None = None
    expires_at: str | None = None
    schema_version: str = HUMAN_APPROVAL_VERSION

    def __post_init__(self) -> None:
        validate_identifier(
            self.human_approval_id,
            field="human_approval_id",
        )
        if self.schema_version != HUMAN_APPROVAL_VERSION:
            raise ValidationError("unsupported human approval version")
        RequestedOperation(self.requested_operation, "observe")
        _enum(
            self.subject_principal,
            EXECUTION_PRINCIPALS,
            "subject_principal",
        )
        _strings(self.permissions, "permissions", allow_empty=False)
        for permission in self.permissions:
            _enum(permission, AUTHORITY_GRANT_CLASSES, "approval permission")
        if self.subject_principal == "apprentice" and set(self.permissions) - {
            "observe",
            "analyse",
        }:
            raise ValidationError(
                "human approval cannot grant Apprentice Propose or Execute"
            )
        validate_identifier(self.project_scope_id, field="project_scope_id")
        validate_identifier(self.scope_id, field="scope_id")
        validate_identifier(
            self.approved_by_entity_id,
            field="approved_by_entity_id",
        )
        if self.task_id is not None:
            validate_identifier(self.task_id, field="task_id")
        parse_canonical_utc(self.approved_at, field="approved_at")
        if self.expires_at is not None:
            parse_canonical_utc(self.expires_at, field="expires_at")
            if self.expires_at < self.approved_at:
                raise ValidationError("expires_at cannot precede approved_at")
        _strings(self.conditions, "conditions", allow_empty=True)
        if not isinstance(self.single_use, bool):
            raise ValidationError("single_use must be boolean")
        _identifiers(self.evidence_ids, "approval evidence_ids")
        if not self.evidence_ids:
            raise ValidationError("human approval requires supporting evidence")
        _canonical_object(self.provenance_json, "approval provenance_json")
        _enum(
            self.registered_by_principal,
            EXECUTION_PRINCIPALS,
            "registered_by_principal",
        )
        if self.registered_by_principal in {
            "apprentice",
            "experimental_harness",
        }:
            raise ValidationError(
                "human approval registration requires governed infrastructure"
            )
        parse_canonical_utc(self.registered_at, field="registered_at")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "approved_at": self.approved_at,
            "approved_by_entity_id": self.approved_by_entity_id,
            "conditions": list(self.conditions),
            "evidence_ids": list(self.evidence_ids),
            "expires_at": self.expires_at,
            "human_approval_id": self.human_approval_id,
            "permissions": list(self.permissions),
            "project_scope_id": self.project_scope_id,
            "provenance": parse_json(self.provenance_json),
            "registered_at": self.registered_at,
            "registered_by_principal": self.registered_by_principal,
            "requested_operation": self.requested_operation,
            "schema_version": self.schema_version,
            "scope_id": self.scope_id,
            "single_use": self.single_use,
            "subject_principal": self.subject_principal,
            "task_id": self.task_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class AuthorityRecord:
    """A structured authority input; free-form claims cannot instantiate it."""

    authority_record_id: str
    authority_class: str
    source_kind: str
    effect: str
    subject_principal: str
    permissions: tuple[str, ...]
    project_scope_id: str
    scope_id: str
    effective_from: str
    evidence_ids: tuple[str, ...]
    provenance_json: str
    registered_by_principal: str
    registered_at: str
    issuer_entity_id: str | None = None
    task_id: str | None = None
    effective_until: str | None = None
    status: str = "active"
    schema_version: str = AUTHORITY_RECORD_VERSION

    def __post_init__(self) -> None:
        validate_identifier(
            self.authority_record_id,
            field="authority_record_id",
        )
        if self.schema_version != AUTHORITY_RECORD_VERSION:
            raise ValidationError("unsupported authority record version")
        _enum(
            self.authority_class,
            set(AUTHORITY_CLASS_PRECEDENCE),
            "authority_class",
        )
        expected_source = AUTHORITY_SOURCE_BY_CLASS[self.authority_class]
        if self.source_kind != expected_source:
            raise ValidationError(
                "authority source does not match its authority class"
            )
        _enum(self.effect, AUTHORITY_EFFECTS, "authority effect")
        _enum(
            self.subject_principal,
            EXECUTION_PRINCIPALS,
            "subject_principal",
        )
        _strings(self.permissions, "permissions", allow_empty=False)
        for permission in self.permissions:
            _enum(permission, AUTHORITY_GRANT_CLASSES, "permission")
        validate_identifier(self.project_scope_id, field="project_scope_id")
        validate_identifier(self.scope_id, field="scope_id")
        if self.issuer_entity_id is not None:
            validate_identifier(
                self.issuer_entity_id,
                field="issuer_entity_id",
            )
        if self.authority_class in {"nolan_approved", "nolan_byte_approved"}:
            if self.issuer_entity_id is None:
                raise ValidationError(
                    "Nolan-approved authority requires an issuer entity"
                )
        if self.task_id is not None:
            validate_identifier(self.task_id, field="task_id")
        parse_canonical_utc(self.effective_from, field="effective_from")
        _enum(
            self.registered_by_principal,
            EXECUTION_PRINCIPALS,
            "registered_by_principal",
        )
        if self.registered_by_principal in {
            "apprentice",
            "experimental_harness",
        }:
            raise ValidationError(
                "authority registration requires non-Apprentice governed infrastructure"
            )
        parse_canonical_utc(self.registered_at, field="registered_at")
        if self.effective_until is not None:
            parse_canonical_utc(self.effective_until, field="effective_until")
            if self.effective_until < self.effective_from:
                raise ValidationError(
                    "effective_until cannot precede effective_from"
                )
        _enum(self.status, AUTHORITY_STATUSES, "authority status")
        _identifiers(self.evidence_ids, "evidence_ids")
        if not self.evidence_ids:
            raise ValidationError(
                "authority records require supporting evidence"
            )
        _canonical_object(self.provenance_json, "provenance_json")

    @property
    def precedence(self) -> int:
        return AUTHORITY_CLASS_PRECEDENCE[self.authority_class]

    def canonical_value(self) -> dict[str, Any]:
        return {
            "authority_class": self.authority_class,
            "authority_record_id": self.authority_record_id,
            "effect": self.effect,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
            "evidence_ids": list(self.evidence_ids),
            "issuer_entity_id": self.issuer_entity_id,
            "permissions": list(self.permissions),
            "project_scope_id": self.project_scope_id,
            "provenance": parse_json(self.provenance_json),
            "registered_at": self.registered_at,
            "registered_by_principal": self.registered_by_principal,
            "schema_version": self.schema_version,
            "scope_id": self.scope_id,
            "source_kind": self.source_kind,
            "status": self.status,
            "subject_principal": self.subject_principal,
            "task_id": self.task_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class DecisionReason:
    code: str
    detail: str
    authority_record_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.code, "reason code")
        _text(self.detail, "reason detail")
        if self.authority_record_id is not None:
            validate_identifier(
                self.authority_record_id,
                field="reason authority_record_id",
            )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "authority_record_id": self.authority_record_id,
            "code": self.code,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class AuthorityAssessment:
    claimed_authority_id: str
    resolved_record_hash: str | None
    authority_class: str | None
    applicable: bool
    result_code: str

    def __post_init__(self) -> None:
        validate_identifier(
            self.claimed_authority_id,
            field="claimed_authority_id",
        )
        if self.authority_class is not None:
            _enum(
                self.authority_class,
                set(AUTHORITY_CLASS_PRECEDENCE),
                "assessment authority_class",
            )
        if not isinstance(self.applicable, bool):
            raise ValidationError("assessment applicable must be boolean")
        _text(self.result_code, "assessment result_code")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "applicable": self.applicable,
            "authority_class": self.authority_class,
            "claimed_authority_id": self.claimed_authority_id,
            "resolved_record_hash": self.resolved_record_hash,
            "result_code": self.result_code,
        }


@dataclass(frozen=True, slots=True)
class HumanApprovalAssessment:
    claimed_human_approval_id: str
    resolved_record_hash: str | None
    applicable: bool
    result_code: str
    selected: bool = False
    consumed: bool = False

    def __post_init__(self) -> None:
        validate_identifier(
            self.claimed_human_approval_id,
            field="claimed_human_approval_id",
        )
        if not isinstance(self.applicable, bool):
            raise ValidationError("approval applicable must be boolean")
        if not isinstance(self.selected, bool):
            raise ValidationError("approval selected must be boolean")
        if not isinstance(self.consumed, bool):
            raise ValidationError("approval consumed must be boolean")
        _text(self.result_code, "approval result_code")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "applicable": self.applicable,
            "claimed_human_approval_id": self.claimed_human_approval_id,
            "consumed": self.consumed,
            "resolved_record_hash": self.resolved_record_hash,
            "selected": self.selected,
            "result_code": self.result_code,
        }


@dataclass(frozen=True, slots=True)
class DecisionEvidenceAssessment:
    input_kind: str
    required_evidence_id: str
    available: bool

    def __post_init__(self) -> None:
        _enum(
            self.input_kind,
            frozenset({"task", "authority", "approval", "policy"}),
            "evidence input_kind",
        )
        validate_identifier(
            self.required_evidence_id,
            field="required_evidence_id",
        )
        if not isinstance(self.available, bool):
            raise ValidationError("evidence availability must be boolean")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "input_kind": self.input_kind,
            "required_evidence_id": self.required_evidence_id,
        }


@dataclass(frozen=True, slots=True)
class GovernanceDecision:
    governance_decision_id: str
    transaction_id: str
    task_id: str
    session_id: str
    project_scope_id: str
    requested_scope_id: str
    requesting_principal: str
    runtime_execution_principal: str
    requested_operation: RequestedOperation
    operation_definition_hash: str
    permission_profile_id: str
    permission_profile_hash: str
    permission_profile_applicable: bool
    authority_assessments: tuple[AuthorityAssessment, ...]
    human_approval_assessments: tuple[HumanApprovalAssessment, ...]
    evidence_assessments: tuple[DecisionEvidenceAssessment, ...]
    precedence_authority_class: str | None
    outcome: str
    reasons: tuple[DecisionReason, ...]
    effective_at: str
    evidence_ids: tuple[str, ...]
    governing_rule_ids: tuple[str, ...]
    decided_at: str
    runtime_instance_id: str
    task_contract_hash: str
    provenance_json: str
    policy_violations: tuple[PolicyViolation, ...] = ()
    apprentice_execute_implication: bool = False

    def __post_init__(self) -> None:
        for field in (
            "governance_decision_id",
            "transaction_id",
            "task_id",
            "session_id",
            "project_scope_id",
            "requested_scope_id",
            "permission_profile_id",
            "runtime_instance_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        _enum(
            self.requesting_principal,
            EXECUTION_PRINCIPALS,
            "requesting_principal",
        )
        _enum(
            self.runtime_execution_principal,
            EXECUTION_PRINCIPALS,
            "runtime_execution_principal",
        )
        if self.runtime_execution_principal in {
            "apprentice",
            "experimental_harness",
        }:
            raise ValidationError(
                "governance evaluation requires governed infrastructure"
            )
        if not isinstance(self.requested_operation, RequestedOperation):
            raise ValidationError(
                "decision requested_operation must be typed"
            )
        if len(self.operation_definition_hash) != 64:
            raise ValidationError("operation_definition_hash must be SHA-256 text")
        if self.precedence_authority_class is not None:
            _enum(
                self.precedence_authority_class,
                set(AUTHORITY_CLASS_PRECEDENCE),
                "precedence_authority_class",
            )
        _enum(self.outcome, DECISION_OUTCOMES, "decision outcome")
        if not self.reasons:
            raise ValidationError("governance decision requires structured reasons")
        parse_canonical_utc(self.effective_at, field="effective_at")
        parse_canonical_utc(self.decided_at, field="decided_at")
        _identifiers(self.evidence_ids, "decision evidence_ids")
        if tuple(dict.fromkeys(
            assessment.required_evidence_id
            for assessment in self.evidence_assessments
            if assessment.available
        )) != self.evidence_ids:
            raise ValidationError(
                "decision evidence_ids must match available evidence assessments"
            )
        _identifiers(self.governing_rule_ids, "governing_rule_ids")
        _canonical_object(self.provenance_json, "decision provenance_json")
        if self.apprentice_execute_implication:
            raise ValidationError(
                "no I2 decision may imply Apprentice Execute permission"
            )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "apprentice_execute_implication": False,
            "authority_assessments": [
                assessment.canonical_value()
                for assessment in self.authority_assessments
            ],
            "evidence_assessments": [
                assessment.canonical_value()
                for assessment in self.evidence_assessments
            ],
            "human_approval_assessments": [
                assessment.canonical_value()
                for assessment in self.human_approval_assessments
            ],
            "decided_at": self.decided_at,
            "effective_at": self.effective_at,
            "evidence_ids": list(self.evidence_ids),
            "governance_decision_id": self.governance_decision_id,
            "governing_rule_ids": list(self.governing_rule_ids),
            "operation_definition_hash": self.operation_definition_hash,
            "outcome": self.outcome,
            "permission_profile_applicable": self.permission_profile_applicable,
            "permission_profile_hash": self.permission_profile_hash,
            "permission_profile_id": self.permission_profile_id,
            "policy_violations": [
                violation.canonical_value()
                for violation in self.policy_violations
            ],
            "precedence_authority_class": self.precedence_authority_class,
            "project_scope_id": self.project_scope_id,
            "provenance": parse_json(self.provenance_json),
            "reasons": [reason.canonical_value() for reason in self.reasons],
            "requested_operation": self.requested_operation.canonical_value(),
            "requested_scope_id": self.requested_scope_id,
            "requesting_principal": self.requesting_principal,
            "runtime_execution_principal": self.runtime_execution_principal,
            "runtime_instance_id": self.runtime_instance_id,
            "session_id": self.session_id,
            "task_contract_hash": self.task_contract_hash,
            "task_id": self.task_id,
            "transaction_id": self.transaction_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class TaskStopEvent:
    stop_event_id: str
    task_id: str
    governance_decision_id: str
    transaction_id: str
    stop_condition: str
    trigger_source: str
    reason_codes: tuple[str, ...]
    preserved_evidence_ids: tuple[str, ...]
    created_at: str
    model_requested_stop: bool = False
    governance_forced_stop: bool = True

    def __post_init__(self) -> None:
        for field in (
            "stop_event_id",
            "task_id",
            "governance_decision_id",
            "transaction_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        _text(self.stop_condition, "stop_condition")
        _text(self.trigger_source, "trigger_source")
        _strings(self.reason_codes, "reason_codes", allow_empty=False)
        _identifiers(
            self.preserved_evidence_ids,
            "preserved_evidence_ids",
        )
        parse_canonical_utc(self.created_at, field="created_at")
        if self.model_requested_stop:
            raise ValidationError(
                "B87-I2 task stops cannot be attributed to a model"
            )
        if not self.governance_forced_stop:
            raise ValidationError("I2 stop events must be governance-forced")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "governance_decision_id": self.governance_decision_id,
            "governance_forced_stop": True,
            "model_requested_stop": False,
            "preserved_evidence_ids": list(self.preserved_evidence_ids),
            "reason_codes": list(self.reason_codes),
            "stop_condition": self.stop_condition,
            "stop_event_id": self.stop_event_id,
            "task_id": self.task_id,
            "transaction_id": self.transaction_id,
            "trigger_source": self.trigger_source,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    decision: GovernanceDecision
    stop_event: TaskStopEvent | None
    task_status: str

    def __post_init__(self) -> None:
        if self.decision.outcome == "allow":
            if self.stop_event is not None or self.task_status != "active":
                raise ValidationError(
                    "allowed decisions must produce an active task without a stop"
                )
        elif self.stop_event is None or self.task_status != "stopped":
            raise ValidationError(
                "non-allow decisions must produce a persisted stopped task"
            )
