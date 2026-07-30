"""Closed repository-owned provider registry for B87-I4-B."""

from __future__ import annotations

from batch87_apprentice.common.errors import ValidationError

from .contracts import DeterministicMockFixture, ProviderProtocol
from .inactive import InactiveProvider
from .mock import DeterministicMockProvider


class ProviderRegistry:
    """Resolve exactly the two shipped implementations; registration is absent."""

    __slots__ = ("_providers",)

    def __init__(self, mock_fixture: DeterministicMockFixture | None = None) -> None:
        fixture = mock_fixture or DeterministicMockFixture(
            fixture_id="default_empty_output",
            raw_output=b"",
            declared_encoding="utf-8",
        )
        providers: tuple[ProviderProtocol, ...] = (
            InactiveProvider(),
            DeterministicMockProvider(fixture),
        )
        self._providers = {
            provider.describe().provider_id: provider
            for provider in providers
        }
        if tuple(sorted(self._providers)) != (
            "deterministic_mock",
            "inactive",
        ):
            raise RuntimeError("closed provider registry is malformed")

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def resolve(self, provider_id: str) -> ProviderProtocol:
        if not isinstance(provider_id, str):
            raise ValidationError("provider_id must be text")
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ValidationError("provider is not registered for I4-B") from exc
