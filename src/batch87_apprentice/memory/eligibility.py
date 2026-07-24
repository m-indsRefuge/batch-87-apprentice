"""Pure eligibility evaluation for B87-I3 memory records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from batch87_apprentice.common.canonical_json import parse_json
from batch87_apprentice.common.hashing import sha256_canonical_json

from .contracts import (
    ELIGIBILITY_REASON_ORDER,
    EligibilityContext,
    EligibilityDecision,
    memory_domain_for,
)


_RECORD_SNAPSHOT_FIELDS = (
    "record_id",
    "record_family",
    "record_type",
    "project_scope_id",
    "lifecycle_state",
    "approval_status",
    "integrity_status",
    "sensitivity_class",
    "privacy_class",
    "effective_from",
    "effective_until",
    "superseded_by_record_id",
    "retrieval_policy_json",
)


def eligibility_record_snapshot(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact governed record fields that determine I3-A eligibility."""

    return {field: record.get(field) for field in _RECORD_SNAPSHOT_FIELDS}


def _ordered_reasons(found: set[str]) -> tuple[str, ...]:
    return tuple(reason for reason in ELIGIBILITY_REASON_ORDER if reason in found)


def evaluate_memory_eligibility(
    record: Mapping[str, Any],
    context: EligibilityContext,
) -> EligibilityDecision:
    """Evaluate deterministic eligibility without relevance scoring or retrieval."""

    snapshot = eligibility_record_snapshot(record)
    reasons: set[str] = set()
    family = str(snapshot.get("record_family", ""))
    record_type = str(snapshot.get("record_type", ""))
    record_id = str(snapshot.get("record_id", ""))

    if (
        family == "evaluation_evidence"
        and record_type == "controlled_governance_resilience_run"
    ):
        reasons.add("restricted_evaluation_evidence")
        reasons.add("ordinary_retrieval_prohibited")

    domain = memory_domain_for(family, record_type)
    if domain is None:
        reasons.add("not_memory_record")
    elif domain != context.requested_domain:
        reasons.add("wrong_memory_domain")

    lifecycle = snapshot.get("lifecycle_state")
    if lifecycle == "candidate":
        reasons.add("candidate_inactive")
    if lifecycle == "superseded":
        reasons.add("superseded")
    if lifecycle == "revoked":
        reasons.add("revoked")
    if lifecycle == "archived":
        reasons.add("archived")
    if lifecycle == "deleted":
        reasons.add("deleted")
    if lifecycle != "active":
        reasons.add("lifecycle_not_active")

    approval = snapshot.get("approval_status")
    if approval == "rejected":
        reasons.add("approval_rejected")
    if approval not in {"approved", "not_required"}:
        reasons.add("approval_not_eligible")
    if snapshot.get("integrity_status") not in {"valid", "not_applicable"}:
        reasons.add("integrity_invalid")

    effective_from = snapshot.get("effective_from")
    if isinstance(effective_from, str) and effective_from > context.evaluated_at:
        reasons.add("not_yet_effective")
    effective_until = snapshot.get("effective_until")
    if isinstance(effective_until, str) and effective_until < context.evaluated_at:
        reasons.add("expired")
    if snapshot.get("superseded_by_record_id") is not None:
        reasons.add("superseded")

    record_project_scope = snapshot.get("project_scope_id")
    if record_project_scope != context.task_project_scope_id:
        reasons.add("wrong_project_scope")
        reasons.add("cross_project_not_authorised")

    try:
        retrieval_policy = parse_json(
            str(snapshot.get("retrieval_policy_json", "{}"))
        )
    except Exception:
        retrieval_policy = {}
        reasons.add("retrieval_policy_denied")

    if (
        retrieval_policy.get("ordinary_memory_eligibility") == "prohibited"
        or retrieval_policy.get("retrieval_mode")
        in {"prohibited", "evaluation_only"}
    ):
        reasons.add("ordinary_retrieval_prohibited")
    allowed_projects = retrieval_policy.get("allowed_project_scope_ids")
    if (
        isinstance(allowed_projects, list)
        and context.task_project_scope_id not in allowed_projects
    ):
        reasons.add("retrieval_policy_denied")

    if snapshot.get("sensitivity_class") not in context.allowed_sensitivity_classes:
        reasons.add("sensitivity_denied")
    if snapshot.get("privacy_class") not in context.allowed_privacy_classes:
        reasons.add("privacy_denied")

    ordered = _ordered_reasons(reasons)
    context_material = context.canonical_value()
    context_hash = sha256_canonical_json(context_material)
    record_snapshot_hash = sha256_canonical_json(snapshot)
    decision_material = {
        "assessment_id": context.assessment_id,
        "record_id": record_id,
        "task_id": context.task_id,
        "requested_domain": context.requested_domain,
        "evaluated_at": context.evaluated_at,
        "eligible": not ordered,
        "reason_codes": list(ordered),
        "policy_version": context.policy_version,
        "record_snapshot_hash": record_snapshot_hash,
        "context_hash": context_hash,
    }
    return EligibilityDecision(
        assessment_id=context.assessment_id,
        record_id=record_id,
        task_id=context.task_id,
        requested_domain=context.requested_domain,
        evaluated_at=context.evaluated_at,
        eligible=not ordered,
        reason_codes=ordered,
        policy_version=context.policy_version,
        record_snapshot_hash=record_snapshot_hash,
        context_hash=context_hash,
        decision_hash=sha256_canonical_json(decision_material),
    )
