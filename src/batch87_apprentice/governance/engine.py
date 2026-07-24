"""Pure deterministic governance evaluation for B87-I2."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.protocols.task_contracts import (
    PolicyViolation,
    TaskContract,
)

from .contracts import (
    AuthorityAssessment,
    AuthorityRecord,
    DecisionEvidenceAssessment,
    DecisionReason,
    EvaluationResult,
    GovernanceDecision,
    HumanApproval,
    HumanApprovalAssessment,
    OperationDefinition,
    PermissionProfile,
    TaskStopEvent,
    active_governance_rules,
)

_PERMISSION_GRANTING_CLASSES = frozenset(
    {
        "law_or_external_obligation",
        "nolan_approved",
        "nolan_byte_approved",
        "validated_system_evidence",
        "approved_project_policy",
    }
)
_HUMAN_AUTHORITY_CLASSES = frozenset({"nolan_approved", "nolan_byte_approved"})
_SUPPORTED_GOVERNING_CONSTRAINTS = frozenset(
    {"b87_s1_permissions", "structured_authority_only"}
)
_SUPPORTED_ALLOWED_SOURCES = frozenset({"approved_evidence"})
_SUPPORTED_APPROVAL_CONDITIONS = frozenset(
    {"task_bound", "single_use", "session_operator"}
)
_SUPPORTED_STOP_CONDITIONS = frozenset(
    {
        "invalid_authority",
        "permission_violation",
        "context_policy_violation",
        "integrity_violation",
        "human_approval_invalid",
        "operation_definition_invalid",
    }
)
_REVIEW_REASON_CODES = frozenset(
    {
        "equal_precedence_conflict",
        "authoritative_denial",
        "explicit_human_review_required",
        "ambiguous_operation_requires_review",
        "human_approval_required",
    }
)


@dataclass(frozen=True, slots=True)
class AuthorityRuntimeContext:
    """Database-derived facts that a free-form authority record cannot assert."""

    scope_matches: bool
    evidence_complete: bool
    issuer_is_session_operator: bool
    revoked: bool = False


@dataclass(frozen=True, slots=True)
class HumanApprovalRuntimeContext:
    """Database-derived approval facts used by the deterministic engine."""

    scope_matches: bool
    evidence_complete: bool
    approver_is_session_operator: bool
    consumed_by_task_id: str | None = None
    consumed_at: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    """The exact relational facts observed inside the governed transaction."""

    session_valid: bool
    project_scope_valid: bool
    requested_scope_valid: bool
    available_evidence_ids: frozenset[str]
    authority_contexts: Mapping[str, AuthorityRuntimeContext]
    human_approval_contexts: Mapping[str, HumanApprovalRuntimeContext]
    operation_definition: OperationDefinition | None


@dataclass(frozen=True, slots=True)
class EvaluationIdentifiers:
    transaction_id: str
    governance_decision_id: str
    stop_event_id: str
    initial_transition_id: str
    terminal_transition_id: str


class GovernanceEngine:
    """Decide from structured inputs only; model output has no decision path."""

    @staticmethod
    def _assess_authority(
        *,
        task: TaskContract,
        record: AuthorityRecord,
        runtime_context: AuthorityRuntimeContext,
        operation_definition: OperationDefinition,
    ) -> tuple[AuthorityAssessment, DecisionReason | None]:
        code: str | None = None
        detail: str | None = None
        if runtime_context.revoked or record.status == "revoked":
            code = "authority_revoked"
            detail = "Revoked authority cannot support a current decision."
        elif record.status == "historical":
            code = "historical_authority_inactive"
            detail = "Historical instructions remain context, not active authority."
        elif record.authority_class not in _PERMISSION_GRANTING_CLASSES:
            code = "unsupported_authority_class"
            detail = (
                "The authority class may be preserved as information but cannot "
                "grant task permission."
            )
        elif record.subject_principal != task.requesting_principal:
            code = "authority_principal_mismatch"
            detail = "The authority record is bound to another execution principal."
        elif record.project_scope_id != task.project_scope_id:
            code = "authority_project_mismatch"
            detail = "The authority record belongs to another project."
        elif not runtime_context.scope_matches:
            code = "authority_out_of_scope"
            detail = "The requested scope is outside the recorded authority scope."
        elif record.task_id is not None and record.task_id != task.task_id:
            code = "authority_task_mismatch"
            detail = "Task-bound authority cannot be reused for another task."
        elif task.effective_at < record.effective_from:
            code = "authority_not_yet_effective"
            detail = "The authority record is not yet effective."
        elif (
            record.effective_until is not None
            and task.effective_at > record.effective_until
        ):
            code = "authority_expired"
            detail = "The authority record expired before the evaluation time."
        elif (
            record.authority_class in _HUMAN_AUTHORITY_CLASSES
            and not runtime_context.issuer_is_session_operator
        ):
            code = "authority_issuer_mismatch"
            detail = "The approval issuer is not the session's operator authority."
        elif not runtime_context.evidence_complete:
            code = "authority_evidence_missing"
            detail = "Required authority evidence is unavailable."
        elif (
            operation_definition.action_class
            not in record.permissions
        ):
            code = "authority_operation_mismatch"
            detail = "The authority record does not cover the classified operation."

        if code is None:
            return (
                AuthorityAssessment(
                    claimed_authority_id=record.authority_record_id,
                    resolved_record_hash=record.content_hash,
                    authority_class=record.authority_class,
                    applicable=True,
                    result_code="applicable",
                ),
                None,
            )
        return (
            AuthorityAssessment(
                claimed_authority_id=record.authority_record_id,
                resolved_record_hash=record.content_hash,
                authority_class=record.authority_class,
                applicable=False,
                result_code=code,
            ),
            DecisionReason(
                code=code,
                detail=detail,
                authority_record_id=record.authority_record_id,
            ),
        )

    @staticmethod
    def _assess_human_approval(
        *,
        task: TaskContract,
        approval: HumanApproval,
        runtime_context: HumanApprovalRuntimeContext,
        operation_definition: OperationDefinition,
    ) -> tuple[HumanApprovalAssessment, DecisionReason | None]:
        code: str | None = None
        detail: str | None = None
        if approval.subject_principal != task.requesting_principal:
            code = "human_approval_principal_mismatch"
            detail = "The human approval is bound to another principal."
        elif approval.project_scope_id != task.project_scope_id:
            code = "human_approval_project_mismatch"
            detail = "The human approval belongs to another project."
        elif not runtime_context.scope_matches:
            code = "human_approval_out_of_scope"
            detail = "The requested scope is outside the approval scope."
        elif approval.task_id is not None and approval.task_id != task.task_id:
            code = "human_approval_task_mismatch"
            detail = "Task-bound human approval cannot be reused for another task."
        elif approval.requested_operation != operation_definition.name:
            code = "human_approval_operation_mismatch"
            detail = "The human approval names a different operation."
        elif operation_definition.action_class not in approval.permissions:
            code = "human_approval_permission_mismatch"
            detail = "The human approval does not cover the classified action."
        elif task.effective_at < approval.approved_at:
            code = "human_approval_not_yet_effective"
            detail = "The human approval is not yet effective."
        elif approval.expires_at is not None and task.effective_at > approval.expires_at:
            code = "human_approval_expired"
            detail = "The human approval expired before evaluation."
        elif not runtime_context.approver_is_session_operator:
            code = "human_approval_issuer_mismatch"
            detail = "The approver is not the session operator authority."
        elif not runtime_context.evidence_complete:
            code = "human_approval_evidence_missing"
            detail = "Required human-approval evidence is unavailable."
        elif set(approval.conditions) - set(_SUPPORTED_APPROVAL_CONDITIONS):
            code = "human_approval_conditions_unsupported"
            detail = "The human approval contains unsupported conditions."
        elif "task_bound" in approval.conditions and approval.task_id is None:
            code = "human_approval_condition_unsatisfied"
            detail = "The task-bound condition requires an explicit task identity."
        elif "single_use" in approval.conditions and not approval.single_use:
            code = "human_approval_condition_unsatisfied"
            detail = "The single-use condition requires single_use=true."
        elif approval.single_use and runtime_context.consumed_at is not None:
            code = "human_approval_already_consumed"
            detail = "The single-use human approval has already been consumed."

        if code is None:
            return (
                HumanApprovalAssessment(
                    claimed_human_approval_id=approval.human_approval_id,
                    resolved_record_hash=approval.content_hash,
                    applicable=True,
                    result_code="applicable",
                ),
                None,
            )
        return (
            HumanApprovalAssessment(
                claimed_human_approval_id=approval.human_approval_id,
                resolved_record_hash=approval.content_hash,
                applicable=False,
                result_code=code,
            ),
            DecisionReason(code=code, detail=detail),
        )

    @staticmethod
    def _evidence_assessments(
        *,
        task: TaskContract,
        authorities: Mapping[str, AuthorityRecord],
        approvals: Mapping[str, HumanApproval],
        policy_violations: tuple[PolicyViolation, ...],
        available_evidence_ids: frozenset[str],
    ) -> tuple[DecisionEvidenceAssessment, ...]:
        ordered: list[tuple[str, str]] = [
            ("task", evidence_id) for evidence_id in task.required_evidence_ids
        ]
        for authority_id in task.claimed_authority_ids:
            record = authorities.get(authority_id)
            if record is not None:
                ordered.extend(
                    ("authority", evidence_id) for evidence_id in record.evidence_ids
                )
        for approval_id in task.claimed_human_approval_ids:
            approval = approvals.get(approval_id)
            if approval is not None:
                ordered.extend(
                    ("approval", evidence_id) for evidence_id in approval.evidence_ids
                )
        for violation in policy_violations:
            ordered.extend(
                ("policy", evidence_id) for evidence_id in violation.evidence_ids
            )
        deduplicated = tuple(dict.fromkeys(ordered))
        return tuple(
            DecisionEvidenceAssessment(
                input_kind=input_kind,
                required_evidence_id=evidence_id,
                available=evidence_id in available_evidence_ids,
            )
            for input_kind, evidence_id in deduplicated
        )

    def evaluate(
        self,
        *,
        task: TaskContract,
        authorities: Mapping[str, AuthorityRecord],
        human_approvals: Mapping[str, HumanApproval],
        permission_profile: PermissionProfile,
        policy_violations: tuple[PolicyViolation, ...],
        context: EvaluationContext,
        identifiers: EvaluationIdentifiers,
        decided_at: str,
        runtime_instance_id: str,
        runtime_execution_principal: str,
    ) -> EvaluationResult:
        """Return the one canonical decision implied by observable inputs."""

        extra_authority = set(authorities) - set(task.claimed_authority_ids)
        if extra_authority:
            raise ValidationError(
                "unclaimed authority records cannot enter a task transaction"
            )
        extra_approvals = set(human_approvals) - set(
            task.claimed_human_approval_ids
        )
        if extra_approvals:
            raise ValidationError(
                "unclaimed human approvals cannot enter a task transaction"
            )

        reasons: list[DecisionReason] = []
        if not context.session_valid:
            reasons.append(
                DecisionReason(
                    "session_invalid",
                    "The task session is missing, closed, or belongs to another project.",
                )
            )
        if not context.project_scope_valid:
            reasons.append(
                DecisionReason(
                    "project_scope_invalid",
                    "The project scope is missing, inactive, or not a project.",
                )
            )
        if not context.requested_scope_valid:
            reasons.append(
                DecisionReason(
                    "requested_scope_invalid",
                    "The requested scope is missing, inactive, or outside the project.",
                )
            )
        if task.effective_at < permission_profile.effective_from:
            reasons.append(
                DecisionReason(
                    "permission_profile_not_effective",
                    "The active permission profile was not effective at task time.",
                )
            )

        operation_definition = context.operation_definition
        if operation_definition is None:
            reasons.append(
                DecisionReason(
                    "operation_definition_missing",
                    "The requested operation has no registered deterministic definition.",
                )
            )
            operation_definition_hash = "0" * 64
        else:
            operation_definition_hash = operation_definition.content_hash
            if (
                task.requested_operation.name != operation_definition.name
                or task.requested_operation.action_class
                != operation_definition.action_class
                or task.requested_operation.autonomous
                != operation_definition.autonomous
            ):
                reasons.append(
                    DecisionReason(
                        "operation_classification_mismatch",
                        "The task's operation claim differs from the registered definition.",
                    )
                )
            if (
                operation_definition.name in task.prohibited_actions
                or operation_definition.action_class in task.prohibited_actions
                or (
                    operation_definition.autonomous
                    and "autonomous_action" in task.prohibited_actions
                )
            ):
                reasons.append(
                    DecisionReason(
                        "task_prohibited_operation",
                        "The classified operation is prohibited by the task contract.",
                    )
                )

        unsupported_constraints = set(task.governing_constraints) - set(
            _SUPPORTED_GOVERNING_CONSTRAINTS
        )
        missing_constraints = set(_SUPPORTED_GOVERNING_CONSTRAINTS) - set(
            task.governing_constraints
        )
        if unsupported_constraints or missing_constraints:
            reasons.append(
                DecisionReason(
                    "governing_constraints_invalid",
                    "The task does not use the complete supported I2 constraint set.",
                )
            )
        if set(task.allowed_sources) - set(_SUPPORTED_ALLOWED_SOURCES):
            reasons.append(
                DecisionReason(
                    "allowed_sources_invalid",
                    "The task names an unsupported evidence-source class.",
                )
            )
        if set(task.stop_conditions) - set(_SUPPORTED_STOP_CONDITIONS):
            reasons.append(
                DecisionReason(
                    "stop_conditions_invalid",
                    "The task names an unsupported stop condition.",
                )
            )

        missing_evidence = tuple(
            evidence_id
            for evidence_id in task.required_evidence_ids
            if evidence_id not in context.available_evidence_ids
        )
        if missing_evidence:
            reasons.append(
                DecisionReason(
                    "missing_required_evidence",
                    "One or more task evidence references are unavailable.",
                )
            )

        for violation in policy_violations:
            reasons.append(
                DecisionReason(code=violation.code, detail=violation.detail)
            )

        authority_assessments: list[AuthorityAssessment] = []
        valid_authorities: list[AuthorityRecord] = []
        if operation_definition is not None:
            for authority_id in task.claimed_authority_ids:
                record = authorities.get(authority_id)
                if record is None:
                    authority_assessments.append(
                        AuthorityAssessment(
                            claimed_authority_id=authority_id,
                            resolved_record_hash=None,
                            authority_class=None,
                            applicable=False,
                            result_code="missing_authority",
                        )
                    )
                    reasons.append(
                        DecisionReason(
                            code="missing_authority",
                            detail="A claimed authority record does not exist.",
                            authority_record_id=authority_id,
                        )
                    )
                    continue
                runtime_context = context.authority_contexts.get(authority_id)
                if runtime_context is None:
                    runtime_context = AuthorityRuntimeContext(False, False, False)
                assessment, reason = self._assess_authority(
                    task=task,
                    record=record,
                    runtime_context=runtime_context,
                    operation_definition=operation_definition,
                )
                authority_assessments.append(assessment)
                if reason is None:
                    valid_authorities.append(record)
                else:
                    reasons.append(reason)
        else:
            for authority_id in task.claimed_authority_ids:
                record = authorities.get(authority_id)
                authority_assessments.append(
                    AuthorityAssessment(
                        claimed_authority_id=authority_id,
                        resolved_record_hash=(
                            record.content_hash if record is not None else None
                        ),
                        authority_class=(
                            record.authority_class if record is not None else None
                        ),
                        applicable=False,
                        result_code="operation_definition_missing",
                    )
                )

        if not task.claimed_authority_ids:
            reasons.append(
                DecisionReason(
                    "missing_authority",
                    "The task contains no structured authority reference.",
                )
            )

        approval_assessments: list[HumanApprovalAssessment] = []
        valid_approvals: list[HumanApproval] = []
        if operation_definition is not None:
            for approval_id in task.claimed_human_approval_ids:
                approval = human_approvals.get(approval_id)
                if approval is None:
                    approval_assessments.append(
                        HumanApprovalAssessment(
                            claimed_human_approval_id=approval_id,
                            resolved_record_hash=None,
                            applicable=False,
                            result_code="missing_human_approval",
                        )
                    )
                    reasons.append(
                        DecisionReason(
                            "missing_human_approval",
                            "A claimed human approval does not exist.",
                        )
                    )
                    continue
                runtime_context = context.human_approval_contexts.get(approval_id)
                if runtime_context is None:
                    runtime_context = HumanApprovalRuntimeContext(False, False, False)
                assessment, reason = self._assess_human_approval(
                    task=task,
                    approval=approval,
                    runtime_context=runtime_context,
                    operation_definition=operation_definition,
                )
                approval_assessments.append(assessment)
                if reason is None:
                    valid_approvals.append(approval)
                else:
                    reasons.append(reason)
        else:
            for approval_id in task.claimed_human_approval_ids:
                approval = human_approvals.get(approval_id)
                approval_assessments.append(
                    HumanApprovalAssessment(
                        claimed_human_approval_id=approval_id,
                        resolved_record_hash=(
                            approval.content_hash if approval is not None else None
                        ),
                        applicable=False,
                        result_code="operation_definition_missing",
                    )
                )

        permission_class = (
            operation_definition.action_class
            if operation_definition is not None
            else task.requested_operation.permission_class
        )
        operation_autonomous = (
            operation_definition.autonomous
            if operation_definition is not None
            else task.requested_operation.autonomous
        )
        if task.requesting_principal == "apprentice":
            forbidden_grants = set(task.authority_grant) - set(
                permission_profile.allowed_action_classes
            )
            if forbidden_grants:
                reasons.append(
                    DecisionReason(
                        "apprentice_permission_expansion_prohibited",
                        "The task authority grant exceeds Observe and Analyse.",
                    )
                )
            if operation_autonomous:
                reasons.append(
                    DecisionReason(
                        "autonomous_action_prohibited",
                        "Autonomous action is unavailable during B87-S1.",
                    )
                )
            elif permission_class == "execute":
                reasons.append(
                    DecisionReason(
                        "apprentice_execute_prohibited",
                        "Execute is unavailable to the Apprentice during B87-S1.",
                    )
                )
            elif permission_class == "propose":
                reasons.append(
                    DecisionReason(
                        "apprentice_propose_not_authority_bearing",
                        "Propose is not an active independent permission in B87-S1.",
                    )
                )
            elif permission_class not in task.authority_grant:
                reasons.append(
                    DecisionReason(
                        "task_authority_grant_missing",
                        "The task contract does not grant the classified action.",
                    )
                )
        elif task.requesting_principal == "experimental_harness":
            reasons.append(
                DecisionReason(
                    "experimental_harness_production_authority_prohibited",
                    "I2 cannot grant the experimental harness production authority.",
                )
            )

        invalid_codes = {
            reason.code for reason in reasons if reason.code not in _REVIEW_REASON_CODES
        }
        precedence_class: str | None = None
        selected_approval_id: str | None = None
        outcome: str
        if invalid_codes:
            outcome = "stop"
        elif not valid_authorities:
            outcome = "stop"
            if not any(reason.code == "missing_authority" for reason in reasons):
                reasons.append(
                    DecisionReason(
                        "missing_authority",
                        "No valid authority remains after deterministic validation.",
                    )
                )
        else:
            highest_precedence = min(record.precedence for record in valid_authorities)
            controlling = tuple(
                record
                for record in valid_authorities
                if record.precedence == highest_precedence
            )
            precedence_class = controlling[0].authority_class
            effects = {record.effect for record in controlling}
            if len(effects) > 1:
                outcome = "require_human_approval"
                reasons.append(
                    DecisionReason(
                        "equal_precedence_conflict",
                        "Equal-precedence authority records conflict and require review.",
                    )
                )
            else:
                effect = next(iter(effects))
                if task.requested_operation.action_class == "ambiguous":
                    outcome = "require_human_approval"
                    reasons.append(
                        DecisionReason(
                            "ambiguous_operation_requires_review",
                            "The requested operation is explicitly ambiguous.",
                        )
                    )
                elif effect == "allow":
                    human_control = any(
                        record.authority_class in _HUMAN_AUTHORITY_CLASSES
                        for record in controlling
                    )
                    if human_control:
                        if not valid_approvals:
                            outcome = "require_human_approval"
                            reasons.append(
                                DecisionReason(
                                    "human_approval_required",
                                    "A valid explicit human approval is required.",
                                )
                            )
                        else:
                            selected = valid_approvals[0]
                            selected_approval_id = selected.human_approval_id
                            outcome = "allow"
                            reasons.append(
                                DecisionReason(
                                    "authority_permission_and_approval_valid",
                                    "Structured authority, permission, and explicit human approval allow the request.",
                                )
                            )
                    else:
                        outcome = "allow"
                        reasons.append(
                            DecisionReason(
                                "authority_and_permission_valid",
                                "Structured authority and permission allow the request.",
                            )
                        )
                elif effect == "deny":
                    outcome = "deny"
                    reasons.append(
                        DecisionReason(
                            "authoritative_denial",
                            "The highest-precedence applicable authority denies the request.",
                        )
                    )
                else:
                    outcome = "require_human_approval"
                    reasons.append(
                        DecisionReason(
                            "explicit_human_review_required",
                            "The controlling authority requires explicit human review.",
                        )
                    )

        if selected_approval_id is not None:
            approval_by_id = {
                approval.human_approval_id: approval for approval in valid_approvals
            }
            approval_assessments = [
                replace(
                    assessment,
                    selected=(
                        assessment.claimed_human_approval_id
                        == selected_approval_id
                    ),
                    consumed=(
                        assessment.claimed_human_approval_id
                        == selected_approval_id
                        and approval_by_id[selected_approval_id].single_use
                    ),
                )
                for assessment in approval_assessments
            ]

        evidence_assessments = self._evidence_assessments(
            task=task,
            authorities=authorities,
            approvals=human_approvals,
            policy_violations=policy_violations,
            available_evidence_ids=context.available_evidence_ids,
        )
        available_decision_evidence = tuple(
            dict.fromkeys(
                assessment.required_evidence_id
                for assessment in evidence_assessments
                if assessment.available
            )
        )
        rule_ids = tuple(
            rule.governance_rule_id for rule in active_governance_rules()
        )
        decision = GovernanceDecision(
            governance_decision_id=identifiers.governance_decision_id,
            transaction_id=identifiers.transaction_id,
            task_id=task.task_id,
            session_id=task.session_id,
            project_scope_id=task.project_scope_id,
            requested_scope_id=task.requested_scope_id,
            requesting_principal=task.requesting_principal,
            runtime_execution_principal=runtime_execution_principal,
            requested_operation=task.requested_operation,
            operation_definition_hash=operation_definition_hash,
            permission_profile_id=permission_profile.permission_profile_id,
            permission_profile_hash=permission_profile.content_hash,
            permission_profile_applicable=(
                task.requesting_principal == "apprentice"
            ),
            authority_assessments=tuple(authority_assessments),
            human_approval_assessments=tuple(approval_assessments),
            evidence_assessments=evidence_assessments,
            precedence_authority_class=precedence_class,
            outcome=outcome,
            reasons=tuple(reasons),
            effective_at=task.effective_at,
            evidence_ids=available_decision_evidence,
            governing_rule_ids=rule_ids,
            decided_at=decided_at,
            runtime_instance_id=runtime_instance_id,
            task_contract_hash=task.content_hash,
            provenance_json=canonical_json_text(
                {
                    "decision_engine": "b87_i2_governance_kernel",
                    "engine_version": "1.1.0",
                    "runtime_execution_principal": runtime_execution_principal,
                    "runtime_instance_id": runtime_instance_id,
                }
            ),
            policy_violations=policy_violations,
        )
        if outcome == "allow":
            return EvaluationResult(
                decision=decision,
                stop_event=None,
                task_status="active",
            )

        if any(
            violation.code == "context_policy_violation"
            for violation in policy_violations
        ):
            trigger_source = "context_policy_violation"
        elif any(
            violation.code == "integrity_violation"
            for violation in policy_violations
        ):
            trigger_source = "integrity_violation"
        else:
            trigger_source = "governance_kernel"
        stop_event = TaskStopEvent(
            stop_event_id=identifiers.stop_event_id,
            task_id=task.task_id,
            governance_decision_id=decision.governance_decision_id,
            transaction_id=identifiers.transaction_id,
            stop_condition=decision.reasons[0].code,
            trigger_source=trigger_source,
            reason_codes=tuple(
                dict.fromkeys(reason.code for reason in decision.reasons)
            ),
            preserved_evidence_ids=available_decision_evidence,
            created_at=decided_at,
        )
        return EvaluationResult(
            decision=decision,
            stop_event=stop_event,
            task_status="stopped",
        )
