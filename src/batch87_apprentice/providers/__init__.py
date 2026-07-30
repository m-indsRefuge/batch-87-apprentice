"""Closed provider boundary for B87-I4-B."""

from .contracts import (
    CapabilityProfile,
    DeterministicMockFixture,
    LocalProviderConfiguration,
    ProviderCallResult,
    ProviderConfigurationSnapshot,
    ProviderDescriptor,
    ProviderProtocol,
)
from .inactive import InactiveProvider
from .mock import DeterministicMockProvider
from .registry import ProviderRegistry

__all__ = [
    "CapabilityProfile",
    "DeterministicMockFixture",
    "DeterministicMockProvider",
    "InactiveProvider",
    "LocalProviderConfiguration",
    "ProviderCallResult",
    "ProviderConfigurationSnapshot",
    "ProviderDescriptor",
    "ProviderProtocol",
    "ProviderRegistry",
]
