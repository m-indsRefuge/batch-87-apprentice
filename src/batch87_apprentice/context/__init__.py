"""Public B87-I4-A governed retrieval and structured-context contracts."""

from .assembly import (
    ContextAssembler,
    ContaminationInspector,
    build_authoritative_authority_section,
    build_authoritative_task_section,
)
from .contracts import (
    CONTEXT_SECTIONS,
    RETRIEVAL_CONTRACT_VERSION,
    STRUCTURED_CONTEXT_VERSION,
    ContaminationFinding,
    ContextReadinessAssessment,
    ContextReadinessFinding,
    OrderedContextEntry,
    RankComponents,
    RankedCandidate,
    RecoveryRelationship,
    RetrievalAssemblyResult,
    RetrievalCandidate,
    RetrievalManifest,
    RetrievalManifestEntry,
    RetrievalRequest,
    StructuredContextPackage,
)
from .ranking import DeterministicFallbackRanker, RelevanceRanker
from .retrieval import ContextRetrievalService
from .integrity import (
    ContextIntegrityFinding,
    ContextIntegrityInspector,
    ContextIntegrityReport,
)

__all__ = [
    "CONTEXT_SECTIONS",
    "RETRIEVAL_CONTRACT_VERSION",
    "STRUCTURED_CONTEXT_VERSION",
    "ContaminationFinding",
    "ContextAssembler",
    "ContextIntegrityFinding",
    "ContextIntegrityInspector",
    "ContextIntegrityReport",
    "ContextReadinessAssessment",
    "ContextReadinessFinding",
    "ContextRetrievalService",
    "ContaminationInspector",
    "DeterministicFallbackRanker",
    "OrderedContextEntry",
    "RankComponents",
    "RankedCandidate",
    "RecoveryRelationship",
    "RelevanceRanker",
    "RetrievalAssemblyResult",
    "RetrievalCandidate",
    "RetrievalManifest",
    "RetrievalManifestEntry",
    "RetrievalRequest",
    "StructuredContextPackage",
    "build_authoritative_authority_section",
    "build_authoritative_task_section",
]
