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

# Type-specific implementation of the accepted memory approval matrix.  A
# general Observe/Analyse authority is never sufficient by itself; it may only
# support an exact immutable grant, and its authority class must appear here.
MEMORY_APPROVAL_AUTHORITY_CLASSES: Mapping[
    tuple[str, str], frozenset[str]
] = {
    ("construct_memory", "construct_entity"): frozenset(
        {"nolan_byte_approved"}
    ),
    ("construct_memory", "construct_relationship"): frozenset(
        {"nolan_byte_approved"}
    ),
    ("construct_memory", "architecture_decision"): frozenset(
        {"nolan_approved"}
    ),
    ("construct_memory", "project_state"): frozenset(
        {"validated_system_evidence", "nolan_byte_approved"}
    ),
    ("construct_memory", "construct_doctrine"): frozenset(
        {"nolan_approved"}
    ),
    ("construct_memory", "terminology_definition"): frozenset(
        {"nolan_byte_approved"}
    ),
    ("construct_memory", "preference_record"): frozenset(
        {"nolan_approved"}
    ),
    ("self_model", "capability_observation"): frozenset(
        {"nolan_byte_approved"}
    ),
    ("self_model", "maturity_state"): frozenset(
        {"nolan_byte_approved"}
    ),
    ("episodic_memory", "episode"): frozenset(
        {"validated_system_evidence", "nolan_approved", "nolan_byte_approved"}
    ),
    ("episodic_memory", "correction"): frozenset(
        {"nolan_approved", "nolan_byte_approved"}
    ),
    ("episodic_memory", "lesson_candidate"): frozenset(
        {"nolan_approved", "nolan_byte_approved"}
    ),
    ("episodic_memory", "approved_lesson"): frozenset(
        {"nolan_byte_approved"}
    ),
    ("episodic_memory", "failure_pattern"): frozenset(
        {"validated_system_evidence", "nolan_byte_approved"}
    ),
    ("episodic_memory", "success_pattern"): frozenset(
        {"validated_system_evidence", "nolan_byte_approved"}
    ),
}

MEMORY_APPROVAL_OPERATION = "approve_memory_record"
MEMORY_RELATIONSHIP_OPERATION = "governed_record_relationship"
NOLAN_INCLUSIVE_AUTHORITY_CLASSES = frozenset(
    {"nolan_approved", "nolan_byte_approved"}
)
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


def approval_authority_classes_for(
    record_family: str,
    record_type: str,
) -> frozenset[str]:
    """Return exact authority classes permitted to back an approval grant."""

    return MEMORY_APPROVAL_AUTHORITY_CLASSES.get(
        (record_family, record_type),
        frozenset(),
    )


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


def _nonempty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be non-empty")
    return value


def _optional_expiry(approved_at: str, expires_at: str | None) -> None:
    parse_canonical_utc(approved_at, field="approved_at")
    if expires_at is not None:
        parse_canonical_utc(expires_at, field="expires_at")
        if expires_at < approved_at:
            raise ValidationError("expires_at cannot precede approved_at")


@dataclass(frozen=True, slots=True)
class MemoryApprovalGrant:
    """Immutable, exact grant for one record approval-state transition."""

    grant_id: str
    record_id: str
    target_status: str
    project_scope_id: str
    authority_record_id: str
    approved_by_entity_id: str
    approved_at: str
    evidence_id: str
    single_use: bool = True
    expires_at: str | None = None
    operation: str = MEMORY_APPROVAL_OPERATION

    def __post_init__(self) -> None:
        validate_identifier(self.grant_id, field="grant_id")
        validate_identifier(self.record_id, field="record_id")
        validate_identifier(self.project_scope_id, field="project_scope_id")
        validate_identifier(self.authority_record_id, field="authority_record_id")
        validate_identifier(
            self.approved_by_entity_id,
            field="approved_by_entity_id",
        )
        validate_identifier(self.evidence_id, field="evidence_id")
        if self.target_status not in {"approved", "rejected", "withdrawn"}:
            raise ValidationError("memory approval grant target_status is unsupported")
        if self.operation != MEMORY_APPROVAL_OPERATION:
            raise ValidationError("memory approval grant operation is not exact")
        if not isinstance(self.single_use, bool):
            raise ValidationError("single_use must be boolean")
        _optional_expiry(self.approved_at, self.expires_at)

    def canonical_value(self) -> dict[str, object]:
        return {
            "grant_id": self.grant_id,
            "record_id": self.record_id,
            "target_status": self.target_status,
            "operation": self.operation,
            "project_scope_id": self.project_scope_id,
            "authority_record_id": self.authority_record_id,
            "approved_by_entity_id": self.approved_by_entity_id,
            "approved_at": self.approved_at,
            "expires_at": self.expires_at,
            "single_use": self.single_use,
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True, slots=True)
class MemoryRelationshipGrant:
    """Immutable Nolan-inclusive grant for one governed record relationship."""

    grant_id: str
    relationship_id: str
    relationship_type: str
    source_record_id: str
    target_record_id: str
    project_scope_id: str
    authority_record_id: str
    approved_by_entity_id: str
    approved_at: str
    evidence_id: str
    single_use: bool = True
    expires_at: str | None = None
    operation: str = MEMORY_RELATIONSHIP_OPERATION

    def __post_init__(self) -> None:
        for field, value in (
            ("grant_id", self.grant_id),
            ("relationship_id", self.relationship_id),
            ("source_record_id", self.source_record_id),
            ("target_record_id", self.target_record_id),
            ("project_scope_id", self.project_scope_id),
            ("authority_record_id", self.authority_record_id),
            ("approved_by_entity_id", self.approved_by_entity_id),
            ("evidence_id", self.evidence_id),
        ):
            validate_identifier(value, field=field)
        if self.source_record_id == self.target_record_id:
            raise ValidationError("relationship grant cannot target one record twice")
        if self.relationship_type not in GOVERNED_RELATIONSHIP_TYPES:
            raise ValidationError("relationship grant requires a governed type")
        if self.operation != MEMORY_RELATIONSHIP_OPERATION:
            raise ValidationError("relationship grant operation is not exact")
        if not isinstance(self.single_use, bool):
            raise ValidationError("single_use must be boolean")
        _optional_expiry(self.approved_at, self.expires_at)

    def canonical_value(self) -> dict[str, object]:
        return {
            "grant_id": self.grant_id,
            "relationship_id": self.relationship_id,
            "relationship_type": self.relationship_type,
            "source_record_id": self.source_record_id,
            "target_record_id": self.target_record_id,
            "operation": self.operation,
            "project_scope_id": self.project_scope_id,
            "authority_record_id": self.authority_record_id,
            "approved_by_entity_id": self.approved_by_entity_id,
            "approved_at": self.approved_at,
            "expires_at": self.expires_at,
            "single_use": self.single_use,
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True, slots=True)
class RecordRelationship:
    relationship_id: str
    source_record_id: str
    target_record_id: str
    relationship_type: str
    created_at: str
    created_by_principal: str
    explanation: str
    relationship_grant_id: str | None = None

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
        _nonempty(self.explanation, "relationship explanation")
        if self.relationship_grant_id is not None:
            validate_identifier(
                self.relationship_grant_id,
                field="relationship_grant_id",
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
        _nonempty(self.policy_version, "policy_version")

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
