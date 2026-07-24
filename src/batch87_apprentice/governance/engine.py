"""Pure deterministic governance evaluation for B87-I2."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.protocols.task_contracts import (
    PolicyViolation,
    TaskContract,
)

from .contracts import (
    AuthorityAssessment,
    AuthorityRecord,
    DecisionReason,
    EvaluationResult,
    GovernanceDecision,
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


@dataclass(frozen=True, slots=True)
class AuthorityRuntimeContext:
    """Database-derived facts that a free-form authority record cannot assert."""

    scope_matches: bool
    evidence_complete: bool
    issuer_is_session_operator: bool


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    """The exact relational facts observed inside the governed transaction."""

    session_valid: bool
    project_scope_valid: bool
    requested_scope_valid: bool
    available_evidence_ids: frozenset[str]
    authority_contexts: Mapping[str, AuthorityRuntimeContext]


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
    ) -> tuple[AuthorityAssessment, DecisionReason | None]:
        code: str | None = None
        detail: str | None = None
        if record.status == "historical":
            code = "historical_authority_inactive"
            detail = "Historical instructions remain context, not active authority."
        elif record.status == "revoked":
            code = "authority_revoked"
            detail = "Revoked authority cannot support a current decision."
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
            record.authority_class in {"nolan_approved", "nolan_byte_approved"}
            and not runtime_context.issuer_is_session_operator
        ):
            code = "authority_issuer_mismatch"
            detail = "The approval issuer is not the session's operator authority."
        elif not runtime_context.evidence_complete:
            code = "authority_evidence_missing"
            detail = "Required authority evidence is unavailable."
        elif (
            task.requested_operation.action_class != "ambiguous"
            and task.requested_operation.permission_class not in record.permissions
        ):
            code = "authority_operation_mismatch"
            detail = "The authority record does not cover the requested action class."

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

    def evaluate(
        self,
        *,
        task: TaskContract,
        authorities: Mapping[str, AuthorityRecord],
        permission_profile: PermissionProfile,
        policy_violations: tuple[PolicyViolation, ...],
        context: EvaluationContext,
        identifiers: EvaluationIdentifiers,
        decided_at: str,
        runtime_instance_id: str,
        runtime_execution_principal: str,
    ) -> EvaluationResult:
        """Return the one canonical decision implied by observable inputs."""

        extra = set(authorities) - set(task.claimed_authority_ids)
        if extra:
            raise ValidationError(
                "unclaimed authority records cannot enter a task transaction"
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
                    "The active permission profile was not effective at the task time.",
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
                    "One or more task-contract evidence references are unavailable.",
                )
            )

        for violation in policy_violations:
            reasons.append(
                DecisionReason(
                    code=violation.code,
                    detail=violation.detail,
                )
            )

        assessments: list[AuthorityAssessment] = []
        valid_authorities: list[AuthorityRecord] = []
        for authority_id in task.claimed_authority_ids:
            record = authorities.get(authority_id)
            if record is None:
                assessments.append(
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
            )
            assessments.append(assessment)
            if reason is None:
                valid_authorities.append(record)
            else:
                reasons.append(reason)

        if not task.claimed_authority_ids:
            reasons.append(
                DecisionReason(
                    "missing_authority",
                    "The task contract contains no structured authority reference.",
                )
            )

        permission_class = task.requested_operation.permission_class
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
            if task.requested_operation.autonomous:
                reasons.append(
                    DecisionReason(
                        "autonomous_action_prohibited",
                        "Autonomous action is unavailable during B87-S1.",
                    )
                )
            elif task.requested_operation.action_class == "execute":
                reasons.append(
                    DecisionReason(
                        "apprentice_execute_prohibited",
                        "Execute is unavailable to the Apprentice during B87-S1.",
                    )
                )
            elif task.requested_operation.action_class == "propose":
                reasons.append(
                    DecisionReason(
                        "apprentice_propose_not_authority_bearing",
                        "Propose is not an active independent permission in B87-S1.",
                    )
                )
            elif (
                task.requested_operation.action_class != "ambiguous"
                and permission_class not in task.authority_grant
            ):
                reasons.append(
                    DecisionReason(
                        "task_authority_grant_missing",
                        "The task contract does not grant its requested action class.",
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
            reason.code
            for reason in reasons
            if reason.code
            not in {
                "equal_precedence_conflict",
                "authoritative_denial",
                "explicit_human_review_required",
                "ambiguous_operation_requires_review",
            }
        }

        precedence_class: str | None = None
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
                            "The explicit operation class is ambiguous.",
                        )
                    )
                elif effect == "allow":
                    outcome = "allow"
                    reasons.append(
                        DecisionReason(
                            "authority_and_permission_valid",
                            "Structured authority and the applicable permission boundary allow the request.",
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

        available_decision_evidence = tuple(
            evidence_id
            for evidence_id in dict.fromkeys(
                (
                    *task.required_evidence_ids,
                    *(
                        evidence_id
                        for record in authorities.values()
                        for evidence_id in record.evidence_ids
                    ),
                    *(
                        evidence_id
                        for violation in policy_violations
                        for evidence_id in violation.evidence_ids
                    ),
                )
            )
            if evidence_id in context.available_evidence_ids
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
            permission_profile_id=permission_profile.permission_profile_id,
            permission_profile_hash=permission_profile.content_hash,
            permission_profile_applicable=(
                task.requesting_principal == "apprentice"
            ),
            authority_assessments=tuple(assessments),
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
                    "engine_version": "1.0.0",
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
