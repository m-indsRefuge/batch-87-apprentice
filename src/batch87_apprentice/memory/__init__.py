"""B87-I3 governed memory contracts and shared kernel."""

from .contracts import (
    APPROVAL_TRANSITIONS,
    ELIGIBILITY_REASON_ORDER,
    GOVERNED_RELATIONSHIP_TYPES,
    LIFECYCLE_TRANSITIONS,
    MEMORY_APPROVAL_AUTHORITY_CLASSES,
    MEMORY_APPROVAL_OPERATION,
    MEMORY_DOMAINS,
    MEMORY_RECORD_TYPES,
    MEMORY_RELATIONSHIP_OPERATION,
    NOLAN_INCLUSIVE_AUTHORITY_CLASSES,
    RELATIONSHIP_TYPES,
    EligibilityContext,
    EligibilityDecision,
    MemoryApprovalGrant,
    MemoryRelationshipGrant,
    RecordRelationship,
    approval_authority_classes_for,
    memory_domain_for,
    validate_approval_transition,
    validate_lifecycle_transition,
)
from .eligibility import evaluate_memory_eligibility
from .integrity import (
    MemoryIntegrityFinding,
    MemoryIntegrityInspector,
    MemoryIntegrityReport,
)
from .kernel import MemoryKernel

__all__ = [
    "APPROVAL_TRANSITIONS",
    "ELIGIBILITY_REASON_ORDER",
    "GOVERNED_RELATIONSHIP_TYPES",
    "LIFECYCLE_TRANSITIONS",
    "MEMORY_APPROVAL_AUTHORITY_CLASSES",
    "MEMORY_APPROVAL_OPERATION",
    "MEMORY_DOMAINS",
    "MEMORY_RECORD_TYPES",
    "MEMORY_RELATIONSHIP_OPERATION",
    "NOLAN_INCLUSIVE_AUTHORITY_CLASSES",
    "RELATIONSHIP_TYPES",
    "EligibilityContext",
    "EligibilityDecision",
    "MemoryApprovalGrant",
    "MemoryIntegrityFinding",
    "MemoryIntegrityInspector",
    "MemoryIntegrityReport",
    "MemoryKernel",
    "MemoryRelationshipGrant",
    "RecordRelationship",
    "approval_authority_classes_for",
    "evaluate_memory_eligibility",
    "memory_domain_for",
    "validate_approval_transition",
    "validate_lifecycle_transition",
]
