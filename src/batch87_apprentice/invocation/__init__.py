"""B87-I4-B provider-neutral invocation bridge."""

from .contracts import (
    InferenceConfiguration,
    InvocationReconstruction,
    InvocationSpec,
    ModelDescriptor,
)
from .service import InvocationBridge, InvocationInterrupted
from .integrity import InvocationIntegrityInspector, InvocationIntegrityReport

__all__ = [
    "InferenceConfiguration",
    "InvocationBridge",
    "InvocationIntegrityInspector",
    "InvocationIntegrityReport",
    "InvocationInterrupted",
    "InvocationReconstruction",
    "InvocationSpec",
    "ModelDescriptor",
]
