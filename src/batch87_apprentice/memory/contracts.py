"""Shared deterministic contracts for B87-I3 memory governance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc

MEMORY_DOMAINS = (
    "construct_relational",
    "self_episodic",
    "session_task",
)

MEMORY_RECORD_POLICIES: Mapping[tuple[str, str], tuple[str, str, str]] = {
    ("construct_memory", "construct_entity"): (
        "construct_relational", "external", "candidate_only"
    ),
    ("construct_memory", "construct_relationship"): (
        "construct_relational", "external", "candidate_only"
    ),
    ("construct_memory", "architecture_decision"): (
        "construct_relational", "external", "prohibited"
    ),
    ("construct_memory", "project_state"): (
        "construct_relational", "external", "candidate_only"
    ),
    ("construct_memory", "construct_doctrine"): (
        "construct_relational", "external", "prohibited"
    ),
    ("construct_memory", "terminology_definition"): (
        "construct_relational", "external", "candidate_only"
    ),
    ("construct_memory", "preference_record"): (
        "construct_relational", "external", "candidate_only"
    ),
    ("self_model", "runtime_identity"): (
        "self_episodic", "not_required", "prohibited"
    ),
    ("self_model", "capability_observation"): (
        "self_episodic", "external", "candidate_only"
    ),
    ("self_model", "maturity_state"): (
        "self_episodic", "external", "prohibited"
    ),
    ("episodic_memory", "episode"): (
        "self_episodic", "external", "prohibited"
    ),
    ("episodic_memory", "correction"): (
        "self_episodic", "external", "prohibited"
    ),
    ("episodic_memory", "lesson_candidate"): (
        "self_episodic", "external", "candidate_only"
    ),
    ("episodic_memory", "approved_lesson"): (
        "self_episodic", "external", "prohibited"
    ),
    ("episodic_memory", "failure_pattern"): (
        "self_episodic", "external", "candidate_only"
    ),
    ("episodic_memory", "success_pattern"): (
        "self_episodic", "external", "candidate_only"
    ),
    ("session_task_memory", "active_uncertainty"): (
        "session_task", "not_required", "candidate_only"
    ),
}

MEMORY_RECORD_TYPES: Mapping[tuple[str, str], str] = {
    key: policy[0] for key, policy in MEMORY_RECORD_POLICIES.items()
}

I3A_ORDINARY_SENSITIVITY_CLASSES = frozenset({"public", "internal"})
I3A_ORDINARY_PRIVACY_CLASSES = frozenset({"none"})

LIFECYCLE_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "observed": frozenset({"candidate", "reviewed", "revoked", "archived", "deleted"}),
    "candidate": frozenset({"reviewed", "revoked", "archived", "deleted"}),
    "reviewed": frozenset({"approved", "revoked", "archived", "deleted"}),
    "approved": frozenset({"active", "revoked", "archived", "deleted"}),
    "active": frozenset({"superseded", "revoked", "archived", "deleted"}),
    "superseded": frozenset({"revoked", "archived", "deleted"}),
    "revoked": frozenset({"archived", "deleted"}),
    "archived": frozenset({"deleted"}),
    "deleted": frozenset(),
}

APPROVAL_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "pending": frozenset({"approved", "rejected", "withdrawn"}),
    "not_required": frozenset(),
    "approved": frozenset({"withdrawn"}),
    "rejected": frozenset(),
    "withdrawn": frozenset(),
}

RELATIONSHIP_TYPES = frozenset(
    {
        "derived_from",
        "supports",
        "contradicts",
        "corrects",
        "evaluates",
        "supersedes",
        "revokes",
        "applies_to",
        "occurred_during",
        "approved_as",
        "blocked_by",
        "requires_review",
    }
)


GOVERNED_RELATIONSHIP_TYPES = frozenset(
    {"corrects", "supersedes", "revokes", "approved_as"}
)

ELIGIBILITY_REASON_ORDER = (
    "restricted_evaluation_evidence",
    "ordinary_retrieval_prohibited",
    "not_memory_record",
    "wrong_memory_domain",
    "candidate_inactive",
    "lifecycle_not_active",
    "approval_rejected",
    "approval_not_eligible",
    "integrity_invalid",
    "not_yet_effective",
    "expired",
    "superseded",
    "revoked",
    "archived",
    "deleted",
    "wrong_project_scope",
    "cross_project_not_authorised",
    "retrieval_policy_denied",
    "sensitivity_denied",
    "privacy_denied",
)


def memory_domain_for(record_family: str, record_type: str) -> str | None:
    """Return the canonical memory domain for an approved memory record type."""

    return MEMORY_RECORD_TYPES.get((record_family, record_type))


def validate_lifecycle_transition(from_state: str, to_state: str) -> None:
    """Reject any lifecycle transition not defined by the accepted A2 state model."""

    if from_state not in LIFECYCLE_TRANSITIONS:
        raise ValidationError(f"unsupported lifecycle state: {from_state!r}")
    if to_state not in LIFECYCLE_TRANSITIONS[from_state]:
        raise ValidationError(
            f"invalid memory lifecycle transition: {from_state!r} -> {to_state!r}"
        )


def validate_approval_transition(from_status: str, to_status: str) -> None:
    """Reject approval transitions that would bypass external review."""

    if from_status not in APPROVAL_TRANSITIONS:
        raise ValidationError(f"unsupported approval status: {from_status!r}")
    if to_status not in APPROVAL_TRANSITIONS[from_status]:
        raise ValidationError(
            f"invalid memory approval transition: {from_status!r} -> {to_status!r}"
        )


@dataclass(frozen=True, slots=True)
class RecordRelationship:
    relationship_id: str
    source_record_id: str
    target_record_id: str
    relationship_type: str
    created_at: str
    created_by_principal: str
    explanation: str
    authority_record_id: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.relationship_id, field="relationship_id")
        validate_identifier(self.source_record_id, field="source_record_id")
        validate_identifier(self.target_record_id, field="target_record_id")
        if self.source_record_id == self.target_record_id:
            raise ValidationError("record relationship cannot target itself")
        if self.relationship_type not in RELATIONSHIP_TYPES:
            raise ValidationError(
                f"unsupported record relationship: {self.relationship_type!r}"
            )
        parse_canonical_utc(self.created_at, field="created_at")
        if self.created_by_principal not in {
            "apprentice",
            "operator",
            "codex_development_harness",
        }:
            raise ValidationError("unsupported relationship principal")
        if not isinstance(self.explanation, str) or not self.explanation.strip():
            raise ValidationError("relationship explanation must be non-empty")
        if self.authority_record_id is not None:
            validate_identifier(
                self.authority_record_id,
                field="authority_record_id",
            )


@dataclass(frozen=True, slots=True)
class EligibilityContext:
    assessment_id: str
    task_id: str
    task_project_scope_id: str
    requested_domain: str
    evaluated_at: str
    allowed_sensitivity_classes: tuple[str, ...]
    allowed_privacy_classes: tuple[str, ...]
    cross_project_authorised: bool = False
    policy_version: str = "b87-i3-eligibility-1.0.0"

    def __post_init__(self) -> None:
        validate_identifier(self.assessment_id, field="assessment_id")
        validate_identifier(self.task_id, field="task_id")
        validate_identifier(
            self.task_project_scope_id,
            field="task_project_scope_id",
        )
        if self.requested_domain not in MEMORY_DOMAINS:
            raise ValidationError("requested_domain is not one of the three memory domains")
        parse_canonical_utc(self.evaluated_at, field="evaluated_at")
        if not self.allowed_sensitivity_classes:
            raise ValidationError("allowed_sensitivity_classes cannot be empty")
        if len(set(self.allowed_sensitivity_classes)) != len(
            self.allowed_sensitivity_classes
        ):
            raise ValidationError("allowed_sensitivity_classes contains duplicates")
        if not set(self.allowed_sensitivity_classes) <= I3A_ORDINARY_SENSITIVITY_CLASSES:
            raise ValidationError(
                "I3-A ordinary eligibility permits public and internal sensitivity only"
            )
        if not self.allowed_privacy_classes:
            raise ValidationError("allowed_privacy_classes cannot be empty")
        if len(set(self.allowed_privacy_classes)) != len(self.allowed_privacy_classes):
            raise ValidationError("allowed_privacy_classes contains duplicates")
        if not set(self.allowed_privacy_classes) <= I3A_ORDINARY_PRIVACY_CLASSES:
            raise ValidationError(
                "I3-A ordinary eligibility permits privacy_class='none' only"
            )
        if self.cross_project_authorised:
            raise ValidationError(
                "cross-project memory authorization is deferred to the governed I4 path"
            )
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValidationError("policy_version must be non-empty")

    def canonical_value(self) -> dict[str, object]:
        return {
            "assessment_id": self.assessment_id,
            "task_id": self.task_id,
            "task_project_scope_id": self.task_project_scope_id,
            "requested_domain": self.requested_domain,
            "evaluated_at": self.evaluated_at,
            "allowed_sensitivity_classes": list(self.allowed_sensitivity_classes),
            "allowed_privacy_classes": list(self.allowed_privacy_classes),
            "cross_project_authorised": self.cross_project_authorised,
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    assessment_id: str
    record_id: str
    task_id: str
    requested_domain: str
    evaluated_at: str
    eligible: bool
    reason_codes: tuple[str, ...]
    policy_version: str
    record_snapshot_hash: str
    context_hash: str
    decision_hash: str

    def __post_init__(self) -> None:
        validate_identifier(self.assessment_id, field="assessment_id")
        validate_identifier(self.record_id, field="record_id")
        validate_identifier(self.task_id, field="task_id")
        if self.requested_domain not in MEMORY_DOMAINS:
            raise ValidationError("requested_domain is invalid")
        parse_canonical_utc(self.evaluated_at, field="evaluated_at")
        unknown = set(self.reason_codes) - set(ELIGIBILITY_REASON_ORDER)
        if unknown:
            raise ValidationError(f"unknown eligibility reason codes: {sorted(unknown)!r}")
        if self.eligible and self.reason_codes:
            raise ValidationError("eligible decisions cannot contain exclusion reasons")
        if not self.eligible and not self.reason_codes:
            raise ValidationError("ineligible decisions require at least one reason")
        for field, value in (
            ("record_snapshot_hash", self.record_snapshot_hash),
            ("context_hash", self.context_hash),
            ("decision_hash", self.decision_hash),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise ValidationError(f"{field} must be a SHA-256 digest")
            if any(character not in "0123456789abcdef" for character in value):
                raise ValidationError(f"{field} must be lowercase hexadecimal")
