"""B87-I3 governed memory contracts and shared kernel."""

from .contracts import (
    APPROVAL_TRANSITIONS,
    ELIGIBILITY_REASON_ORDER,
    GOVERNED_RELATIONSHIP_TYPES,
    LIFECYCLE_TRANSITIONS,
    MEMORY_DOMAINS,
    MEMORY_RECORD_TYPES,
    RELATIONSHIP_TYPES,
    EligibilityContext,
    EligibilityDecision,
    RecordRelationship,
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
    "MEMORY_DOMAINS",
    "MEMORY_RECORD_TYPES",
    "RELATIONSHIP_TYPES",
    "EligibilityContext",
    "EligibilityDecision",
    "MemoryIntegrityFinding",
    "MemoryIntegrityInspector",
    "MemoryIntegrityReport",
    "MemoryKernel",
    "RecordRelationship",
    "evaluate_memory_eligibility",
    "memory_domain_for",
    "validate_approval_transition",
    "validate_lifecycle_transition",
]
