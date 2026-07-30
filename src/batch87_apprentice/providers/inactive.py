"""Repository-owned inactive I4-B provider."""

from __future__ import annotations

from .contracts import (
    CapabilityProfile,
    PROVIDER_ADAPTER_CONTRACT_VERSION,
    ProviderCallResult,
    ProviderConfigurationSnapshot,
    ProviderDescriptor,
)

_INACTIVE_CONFIGURATION = ProviderConfigurationSnapshot(
    provider_id="inactive",
    provider_mode="inactive",
    activation_state="inactive",
    fixture_id=None,
    declared_encoding=None,
    configured_outcome="provider_inactive",
    configured_failure_code="provider_inactive",
    expected_raw_byte_length=None,
    expected_raw_sha256=None,
    provider_metadata_json="{}",
    denied_capability_profile=CapabilityProfile(),
)


class InactiveProvider:
    """A provider that never performs an invocation."""

    __slots__ = ("_descriptor",)

    def __init__(self) -> None:
        self._descriptor = ProviderDescriptor(
            provider_id="inactive",
            provider_name="inactive",
            provider_mode="inactive",
            adapter_contract_version=PROVIDER_ADAPTER_CONTRACT_VERSION,
            transport_kind="none",
            capability_profile=CapabilityProfile(),
            provider_configuration_json=_INACTIVE_CONFIGURATION.canonical_json,
            provider_configuration_hash=_INACTIVE_CONFIGURATION.content_hash,
        )

    def describe(self) -> ProviderDescriptor:
        return self._descriptor

    def invoke(self, canonical_input_bytes: bytes) -> ProviderCallResult:
        if not isinstance(canonical_input_bytes, bytes):
            raise TypeError("canonical_input_bytes must be immutable bytes")
        return ProviderCallResult.inactive()
