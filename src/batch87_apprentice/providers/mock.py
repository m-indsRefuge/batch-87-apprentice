"""Repository-owned deterministic data-only I4-B mock provider."""

from __future__ import annotations

from .contracts import (
    CapabilityProfile,
    DeterministicMockFixture,
    PROVIDER_ADAPTER_CONTRACT_VERSION,
    ProviderCallResult,
    ProviderDescriptor,
)


class DeterministicMockProvider:
    """Return one immutable fixture without observing any external capability."""

    __slots__ = ("_descriptor", "_fixture")

    def __init__(self, fixture: DeterministicMockFixture) -> None:
        if not isinstance(fixture, DeterministicMockFixture):
            raise TypeError("fixture must be a DeterministicMockFixture")
        self._fixture = fixture
        self._descriptor = ProviderDescriptor(
            provider_id="deterministic_mock",
            provider_name="deterministic_mock",
            provider_mode="deterministic_mock",
            adapter_contract_version=PROVIDER_ADAPTER_CONTRACT_VERSION,
            transport_kind="in_process_mock",
            capability_profile=CapabilityProfile(),
            provider_configuration_json=fixture.configuration_snapshot.canonical_json,
            provider_configuration_hash=fixture.configuration_hash,
        )

    def describe(self) -> ProviderDescriptor:
        return self._descriptor

    def invoke(self, canonical_input_bytes: bytes) -> ProviderCallResult:
        if not isinstance(canonical_input_bytes, bytes):
            raise TypeError("canonical_input_bytes must be immutable bytes")
        return ProviderCallResult(
            outcome=self._fixture.outcome,
            raw_output=self._fixture.raw_output,
            declared_encoding=self._fixture.declared_encoding,
            failure_code=self._fixture.failure_code,
            provider_metadata_json=self._fixture.provider_metadata_json,
        )
