from __future__ import annotations

import pytest

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.memory import (
    MEMORY_DOMAINS,
    MEMORY_RECORD_TYPES,
    EligibilityContext,
    RecordRelationship,
    evaluate_memory_eligibility,
    memory_domain_for,
    validate_approval_transition,
    validate_lifecycle_transition,
)

NOW = "2026-07-24T12:00:00.000000Z"
TASK_ID = "00000000-0000-4000-8000-000000000001"
PROJECT_ID = "00000000-0000-4000-8000-000000000002"
RECORD_ID = "00000000-0000-4000-8000-000000000003"


def context(**overrides: object) -> EligibilityContext:
    values = {
        "assessment_id": "00000000-0000-4000-8000-000000000004",
        "task_id": TASK_ID,
        "task_project_scope_id": PROJECT_ID,
        "requested_domain": "construct_relational",
        "evaluated_at": NOW,
        "allowed_sensitivity_classes": ("public", "internal"),
        "allowed_privacy_classes": ("none",),
    }
    values.update(overrides)
    return EligibilityContext(**values)


def active_record(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "record_id": RECORD_ID,
        "record_family": "construct_memory",
        "record_type": "project_state",
        "lifecycle_state": "active",
        "approval_status": "approved",
        "integrity_status": "valid",
        "project_scope_id": PROJECT_ID,
        "effective_from": None,
        "effective_until": None,
        "superseded_by_record_id": None,
        "retrieval_policy_json": canonical_json_text(
            {
                "retrieval_mode": "ordinary",
                "allowed_project_scope_ids": [PROJECT_ID],
            }
        ),
        "sensitivity_class": "internal",
        "privacy_class": "none",
    }
    values.update(overrides)
    return values


def test_exactly_three_canonical_domains_exist() -> None:
    assert MEMORY_DOMAINS == (
        "construct_relational",
        "self_episodic",
        "session_task",
    )
    assert set(MEMORY_RECORD_TYPES.values()) == set(MEMORY_DOMAINS)


def test_memory_type_mapping_is_explicit() -> None:
    assert memory_domain_for("construct_memory", "architecture_decision") == (
        "construct_relational"
    )
    assert memory_domain_for("episodic_memory", "approved_lesson") == (
        "self_episodic"
    )
    assert memory_domain_for("session_task_memory", "active_uncertainty") == (
        "session_task"
    )
    assert memory_domain_for("evaluation_evidence", "controlled_governance_resilience_run") is None


def test_lifecycle_transition_rules_fail_closed() -> None:
    validate_lifecycle_transition("candidate", "reviewed")
    validate_lifecycle_transition("active", "superseded")
    with pytest.raises(ValidationError):
        validate_lifecycle_transition("candidate", "active")
    with pytest.raises(ValidationError):
        validate_lifecycle_transition("deleted", "active")


def test_approval_transition_rules_fail_closed() -> None:
    validate_approval_transition("pending", "approved")
    with pytest.raises(ValidationError):
        validate_approval_transition("rejected", "approved")
    with pytest.raises(ValidationError):
        validate_approval_transition("not_required", "approved")


def test_relationship_cannot_self_reference_or_invent_type() -> None:
    with pytest.raises(ValidationError):
        RecordRelationship(
            relationship_id="00000000-0000-4000-8000-000000000010",
            source_record_id=RECORD_ID,
            target_record_id=RECORD_ID,
            relationship_type="derived_from",
            created_at=NOW,
            created_by_principal="operator",
            explanation="Invalid self relationship.",
        )
    with pytest.raises(ValidationError):
        RecordRelationship(
            relationship_id="00000000-0000-4000-8000-000000000011",
            source_record_id=RECORD_ID,
            target_record_id="00000000-0000-4000-8000-000000000012",
            relationship_type="becomes_authority",
            created_at=NOW,
            created_by_principal="operator",
            explanation="Unsupported authority conversion.",
        )


def test_eligible_record_has_no_exclusion_reasons() -> None:
    decision = evaluate_memory_eligibility(active_record(), context())
    assert decision.eligible is True
    assert decision.reason_codes == ()
    assert len(decision.record_snapshot_hash) == 64
    assert len(decision.context_hash) == 64
    assert len(decision.decision_hash) == 64


def test_lesson_candidate_is_never_ordinary_eligible_but_approved_lesson_is() -> None:
    self_episodic_context = context(requested_domain="self_episodic")

    candidate = evaluate_memory_eligibility(
        active_record(
            record_family="episodic_memory",
            record_type="lesson_candidate",
        ),
        self_episodic_context,
    )
    assert candidate.eligible is False
    assert candidate.reason_codes == ("ordinary_retrieval_prohibited",)

    approved = evaluate_memory_eligibility(
        active_record(
            record_family="episodic_memory",
            record_type="approved_lesson",
        ),
        self_episodic_context,
    )
    assert approved.eligible is True
    assert approved.reason_codes == ()


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"lifecycle_state": "candidate"}, "candidate_inactive"),
        ({"lifecycle_state": "revoked"}, "revoked"),
        ({"lifecycle_state": "archived"}, "archived"),
        ({"lifecycle_state": "deleted"}, "deleted"),
        ({"approval_status": "rejected"}, "approval_rejected"),
        ({"approval_status": "pending"}, "approval_not_eligible"),
        ({"integrity_status": "mismatch"}, "integrity_invalid"),
        ({"effective_from": "2026-07-25T12:00:00.000000Z"}, "not_yet_effective"),
        ({"effective_until": "2026-07-23T12:00:00.000000Z"}, "expired"),
        (
            {"superseded_by_record_id": "00000000-0000-4000-8000-000000000099"},
            "superseded",
        ),
        ({"sensitivity_class": "restricted"}, "sensitivity_denied"),
        ({"privacy_class": "personal"}, "privacy_denied"),
    ],
)
def test_ineligible_states_are_auditable(
    change: dict[str, object],
    expected: str,
) -> None:
    decision = evaluate_memory_eligibility(active_record(**change), context())
    assert decision.eligible is False
    assert expected in decision.reason_codes


def test_cross_project_is_denied_by_default() -> None:
    other_project = "00000000-0000-4000-8000-000000000020"
    decision = evaluate_memory_eligibility(
        active_record(project_scope_id=other_project),
        context(),
    )
    assert decision.eligible is False
    assert "wrong_project_scope" in decision.reason_codes
    assert "cross_project_not_authorised" in decision.reason_codes



def test_i3a_context_cannot_self_authorise_cross_project_or_sensitive_access() -> None:
    with pytest.raises(ValidationError, match="cross-project"):
        context(cross_project_authorised=True)
    with pytest.raises(ValidationError, match="public and internal"):
        context(allowed_sensitivity_classes=("public", "restricted"))
    with pytest.raises(ValidationError, match="privacy_class='none'"):
        context(allowed_privacy_classes=("none", "personal"))


def test_raw_controlled_resilience_is_excluded_before_relevance() -> None:
    record = active_record(
        record_family="evaluation_evidence",
        record_type="controlled_governance_resilience_run",
        sensitivity_class="restricted",
        retrieval_policy_json=canonical_json_text(
            {
                "ordinary_memory_eligibility": "prohibited",
                "retrieval_mode": "evaluation_only",
            }
        ),
    )
    decision = evaluate_memory_eligibility(record, context())
    assert decision.eligible is False
    assert decision.reason_codes[:2] == (
        "restricted_evaluation_evidence",
        "ordinary_retrieval_prohibited",
    )
    assert "not_memory_record" in decision.reason_codes


def test_domain_mismatch_is_auditable() -> None:
    decision = evaluate_memory_eligibility(
        active_record(
            record_family="episodic_memory",
            record_type="approved_lesson",
        ),
        context(),
    )
    assert decision.eligible is False
    assert decision.reason_codes == ("wrong_memory_domain",)
