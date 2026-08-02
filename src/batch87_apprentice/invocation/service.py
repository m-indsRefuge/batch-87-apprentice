"""Bounded B87-I4-B invocation orchestration over the closed provider registry."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.identifiers import generate_identifier
from batch87_apprentice.common.timestamps import canonical_utc_now
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.providers.contracts import (
    DeterministicMockFixture,
    ProviderCallResult,
    ProviderDescriptor,
    ProviderProtocol,
)
from batch87_apprentice.providers.registry import ProviderRegistry

from .contracts import InvocationReconstruction, InvocationSpec
from .processing import process_raw_output
from .store import InvocationStore, PreparedInvocation

INTERRUPTION_POINTS = frozenset(
    {
        "after_provider_return_before_raw_capture",
        "after_raw_capture_before_decoding",
        "after_terminal_finalization_before_acknowledgement",
        "after_validation_before_terminal_finalization",
        "before_provider_return",
        "during_parsing_or_validation",
        "during_raw_capture",
        "during_terminal_finalization",
    }
)


class InvocationInterrupted(RuntimeError):
    """Visible injected or runtime-observed interruption; never an auto-retry."""

    def __init__(self, model_invocation_id: str, point: str) -> None:
        super().__init__(
            f"model invocation {model_invocation_id} interrupted at {point}"
        )
        self.model_invocation_id = model_invocation_id
        self.point = point


@dataclass(frozen=True, slots=True)
class _ProviderCallObservation:
    provider_result: ProviderCallResult
    runtime_failure_classification: str | None = None


class InvocationBridge:
    """Invoke only repository-owned inactive or deterministic mock providers."""

    def __init__(
        self,
        config: DatabaseConfig,
        *,
        mock_fixture: DeterministicMockFixture | None = None,
        clock: Callable[[], str] = canonical_utc_now,
        identifier_factory: Callable[[], str] = generate_identifier,
        runtime_principal: str = "codex_development_harness",
    ) -> None:
        if not callable(clock) or not callable(identifier_factory):
            raise TypeError("clock and identifier_factory must be callable")
        if runtime_principal not in {
            "operator",
            "codex_development_harness",
        }:
            raise ValidationError("runtime principal is invalid")
        self._store = InvocationStore(config)
        self._registry = ProviderRegistry(mock_fixture)
        self._clock = clock
        self._identifier_factory = identifier_factory
        self._runtime_principal = runtime_principal

    @staticmethod
    def _safe_descriptor(provider: ProviderProtocol) -> ProviderDescriptor:
        try:
            descriptor = provider.describe()
        except Exception as exc:
            raise ValidationError(
                "repository-owned provider descriptor failed"
            ) from exc
        if not isinstance(descriptor, ProviderDescriptor):
            raise ValidationError(
                "repository-owned provider returned a malformed descriptor"
            )
        return descriptor

    @staticmethod
    def _safe_provider_call(
        provider: ProviderProtocol,
        canonical_input_bytes: bytes,
        expected_descriptor: ProviderDescriptor,
    ) -> _ProviderCallObservation:
        try:
            result = provider.invoke(canonical_input_bytes)
        except Exception:
            return _ProviderCallObservation(
                ProviderCallResult.runtime_failure("provider_exception")
            )
        if not isinstance(result, ProviderCallResult):
            return _ProviderCallObservation(
                ProviderCallResult.runtime_failure("malformed_provider_result")
            )
        try:
            after = provider.describe()
        except Exception:
            return _ProviderCallObservation(
                result,
                "provider_descriptor_failure",
            )
        if not isinstance(after, ProviderDescriptor) or after != expected_descriptor:
            return _ProviderCallObservation(
                result,
                "provider_descriptor_changed",
            )
        if result.outcome == "provider_inactive":
            return _ProviderCallObservation(
                result,
                "unexpected_inactive_result",
            )
        return _ProviderCallObservation(result)

    @staticmethod
    def _interrupt(
        spec: InvocationSpec,
        configured: str | None,
        point: str,
    ) -> None:
        if configured == point:
            raise InvocationInterrupted(spec.model_invocation_id, point)

    def _finalize_inactive(
        self,
        prepared: PreparedInvocation,
        *,
        interruption_point: str | None,
    ) -> InvocationReconstruction:
        result = ProviderCallResult.inactive()
        try:
            finalized = self._store.finalize(
                prepared,
                provider_result=result,
                raw_capture=None,
                failure_classification="provider_inactive",
                finalized_at=self._clock(),
                invocation_transition_id=self._identifier_factory(),
                model_output_id=self._identifier_factory(),
                task_transition_id=self._identifier_factory(),
                runtime_principal=self._runtime_principal,
                fail_during_transaction=(
                    interruption_point == "during_terminal_finalization"
                ),
            )
        except RuntimeError as exc:
            if interruption_point == "during_terminal_finalization":
                raise InvocationInterrupted(
                    prepared.request.spec.model_invocation_id,
                    interruption_point,
                ) from exc
            raise
        self._interrupt(
            prepared.request.spec,
            interruption_point,
            "after_terminal_finalization_before_acknowledgement",
        )
        return finalized

    def invoke(
        self,
        spec: InvocationSpec | Mapping[str, object],
        *,
        interruption_point: str | None = None,
    ) -> InvocationReconstruction:
        """Execute one exact idempotent invocation without retry or tool access."""

        if interruption_point is not None and interruption_point not in (
            INTERRUPTION_POINTS
        ):
            raise ValidationError("interruption_point is invalid")
        if not isinstance(spec, InvocationSpec):
            spec = InvocationSpec.from_mapping(spec)
        provider = self._registry.resolve(spec.provider_id)
        descriptor = self._safe_descriptor(provider)
        outcome = self._store.prepare(
            spec,
            descriptor,
            prepared_at=self._clock(),
            initial_transition_id=self._identifier_factory(),
            runtime_principal=self._runtime_principal,
        )
        if outcome.existing is not None:
            return outcome.existing
        prepared = outcome.prepared
        if prepared is None:
            raise RuntimeError("preparation returned no invocation")
        if descriptor.provider_mode == "inactive":
            return self._finalize_inactive(
                prepared,
                interruption_point=interruption_point,
            )

        provider_call_attempt_id = self._identifier_factory()
        self._store.call_start(
            prepared,
            started_at=self._clock(),
            provider_call_attempt_id=provider_call_attempt_id,
            transition_id=self._identifier_factory(),
            runtime_principal=self._runtime_principal,
        )
        self._interrupt(spec, interruption_point, "before_provider_return")
        observation = self._safe_provider_call(
            provider,
            prepared.request.model_input_packet.canonical_bytes,
            descriptor,
        )
        provider_result = observation.provider_result
        self._interrupt(
            spec,
            interruption_point,
            "after_provider_return_before_raw_capture",
        )

        raw_capture = None
        processing = None
        if provider_result.raw_output is not None:
            try:
                raw_capture = self._store.capture_raw_output(
                    model_invocation_id=spec.model_invocation_id,
                    provider_call_attempt_id=provider_call_attempt_id,
                    provider_result=provider_result,
                    raw_output_id=self._identifier_factory(),
                    captured_at=self._clock(),
                    transition_id=self._identifier_factory(),
                    runtime_principal=self._runtime_principal,
                    fail_during_transaction=(
                        interruption_point == "during_raw_capture"
                    ),
                )
            except RuntimeError as exc:
                if interruption_point == "during_raw_capture":
                    raise InvocationInterrupted(
                        spec.model_invocation_id,
                        interruption_point,
                    ) from exc
                raise
            self._interrupt(
                spec,
                interruption_point,
                "after_raw_capture_before_decoding",
            )
            self._interrupt(
                spec,
                interruption_point,
                "during_parsing_or_validation",
            )
            processing = process_raw_output(
                raw_capture.raw_bytes,
                declared_encoding=raw_capture.declared_encoding,
                task_id=spec.task_id,
                task_section=prepared.task_section,
                allowed_memory_ids=prepared.allowed_memory_ids,
                allowed_evidence_ids=prepared.allowed_evidence_ids,
            )
            self._interrupt(
                spec,
                interruption_point,
                "after_validation_before_terminal_finalization",
            )
        elif interruption_point in {
            "during_raw_capture",
            "after_raw_capture_before_decoding",
            "during_parsing_or_validation",
            "after_validation_before_terminal_finalization",
        }:
            raise ValidationError(
                "configured interruption point requires provider output bytes"
            )

        if observation.runtime_failure_classification is not None:
            failure = observation.runtime_failure_classification
        elif provider_result.outcome == "output":
            if processing is None:
                raise RuntimeError("output result was not deterministically processed")
            failure = None if processing.successful else "invalid_response"
        elif provider_result.outcome in {"provider_failed", "timed_out"}:
            failure = provider_result.failure_code or provider_result.outcome
        else:
            failure = "malformed_provider_result"

        try:
            finalized = self._store.finalize(
                prepared,
                provider_result=provider_result,
                raw_capture=raw_capture,
                failure_classification=failure,
                finalized_at=self._clock(),
                invocation_transition_id=self._identifier_factory(),
                model_output_id=self._identifier_factory(),
                task_transition_id=self._identifier_factory(),
                runtime_principal=self._runtime_principal,
                fail_during_transaction=(
                    interruption_point == "during_terminal_finalization"
                ),
            )
        except RuntimeError as exc:
            if interruption_point == "during_terminal_finalization":
                raise InvocationInterrupted(
                    spec.model_invocation_id,
                    interruption_point,
                ) from exc
            raise
        self._interrupt(
            spec,
            interruption_point,
            "after_terminal_finalization_before_acknowledgement",
        )
        return finalized

    def mark_interrupted(
        self,
        model_invocation_id: str,
    ) -> InvocationReconstruction:
        """Explicitly finalize one visible incomplete attempt without retry."""

        return self._store.finalize_interrupted(
            model_invocation_id,
            finalized_at=self._clock(),
            invocation_transition_id=self._identifier_factory(),
            model_output_id=self._identifier_factory(),
            task_transition_id=self._identifier_factory(),
            runtime_principal=self._runtime_principal,
        )

    def reconstruct(
        self,
        model_invocation_id: str,
    ) -> InvocationReconstruction:
        return self._store.reconstruct(model_invocation_id)
