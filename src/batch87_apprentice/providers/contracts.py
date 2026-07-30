"""Immutable capability-denying contracts for the B87-I4-B provider boundary."""

from __future__ import annotations

from dataclasses import dataclass, fields
import re
from collections.abc import Mapping
from typing import Any, Protocol

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_bytes, sha256_canonical_json

PROVIDER_ADAPTER_CONTRACT_VERSION = "1.0.0"
LOCAL_PROVIDER_CONFIGURATION_VERSION = "1.0.0"
PROVIDER_MODES = frozenset({"inactive", "deterministic_mock"})
TRANSPORT_KINDS = frozenset({"none", "in_process_mock"})
PROVIDER_RESULT_OUTCOMES = frozenset(
    {"output", "provider_inactive", "provider_failed", "timed_out"}
)
_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")
_FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "api_key", "authorization", "bearer", "bearer_token", "callback",
        "command", "credential", "credentials", "endpoint", "environment",
        "environment_variable", "executable", "function", "host", "model_path",
        "password", "path", "port", "secret", "socket", "token", "tool",
        "tools", "url",
    }
)
_SECRET_PREFIXES = ("sk-", "bearer ", "api_key=", "token=", "secret=")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be non-empty text")
    return value


def _token(value: object, field: str) -> str:
    text = _text(value, field)
    if _TOKEN.fullmatch(text) is None:
        raise ValidationError(f"{field} must be a lowercase token")
    return text


def _sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValidationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _validate_metadata_value(value: object, *, path: str) -> None:
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        lowered = value.strip().lower()
        if (
            "://" in value
            or lowered.startswith(_SECRET_PREFIXES)
            or value.startswith(("/", "\\"))
            or re.match(r"^[A-Za-z]:[\\/]", value)
        ):
            raise ValidationError(f"{path} contains prohibited provider metadata")
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValidationError(f"{path} contains a non-text metadata key")
            normalized = key.strip().lower()
            if (
                normalized in _FORBIDDEN_METADATA_KEYS
                or normalized.endswith(("_token", "_secret", "_password", "_credential"))
                or normalized.startswith(("api_key", "authorization"))
            ):
                raise ValidationError(f"{path}.{key} is prohibited provider metadata")
            _validate_metadata_value(nested, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_metadata_value(nested, path=f"{path}[{index}]")
        return
    raise ValidationError(f"{path} contains unsupported provider metadata")


def _canonical_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be canonical JSON text")
    parsed = parse_json(value)
    if not isinstance(parsed, dict) or canonical_json_text(parsed) != value:
        raise ValidationError(f"{field} must be a canonical JSON object")
    _validate_metadata_value(parsed, path=field)
    return parsed


def validate_provider_metadata_json(value: str, *, field: str) -> dict[str, Any]:
    """Validate canonical, capability-free provider metadata recursively."""

    return _canonical_object(value, field)


@dataclass(frozen=True, slots=True)
class CapabilityProfile:
    """Explicit denial of every capability unavailable to an I4-B provider."""

    database_access: bool = False
    filesystem_access: bool = False
    repository_access: bool = False
    shell_access: bool = False
    network_access: bool = False
    credential_access: bool = False
    environment_access: bool = False
    process_access: bool = False
    communication_access: bool = False
    tool_calling: bool = False
    callback_access: bool = False
    executable_capability: bool = False
    clock_access: bool = False
    randomness: bool = False
    streaming: bool = False
    automatic_retry: bool = False

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if not isinstance(value, bool):
                raise ValidationError(
                    f"capability_profile.{field.name} must be boolean"
                )
            if value:
                raise ValidationError(
                    f"capability_profile.{field.name} must remain denied"
                )

    def canonical_value(self) -> dict[str, bool]:
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
        }


@dataclass(frozen=True, slots=True)
class ProviderConfigurationSnapshot:
    """Exact immutable configuration admitted for one shipped I4-B provider."""

    provider_id: str
    provider_mode: str
    activation_state: str
    fixture_id: str | None
    declared_encoding: str | None
    configured_outcome: str
    configured_failure_code: str | None
    expected_raw_byte_length: int | None
    expected_raw_sha256: str | None
    provider_metadata_json: str
    denied_capability_profile: CapabilityProfile
    contract_version: str = LOCAL_PROVIDER_CONFIGURATION_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != LOCAL_PROVIDER_CONFIGURATION_VERSION:
            raise ValidationError("provider configuration version is invalid")
        _token(self.provider_id, "provider_id")
        if self.provider_mode not in PROVIDER_MODES:
            raise ValidationError("provider configuration mode is invalid")
        expected_activation = (
            "inactive" if self.provider_mode == "inactive" else "test_fixture"
        )
        if self.activation_state != expected_activation:
            raise ValidationError("provider activation state is invalid")
        if self.fixture_id is not None:
            _token(self.fixture_id, "fixture_id")
        if self.configured_outcome not in PROVIDER_RESULT_OUTCOMES:
            raise ValidationError("configured provider outcome is invalid")
        if self.declared_encoding is not None:
            _text(self.declared_encoding, "declared_encoding")
        if self.configured_failure_code is not None:
            _token(self.configured_failure_code, "configured_failure_code")
        if self.expected_raw_byte_length is not None and (
            not isinstance(self.expected_raw_byte_length, int)
            or isinstance(self.expected_raw_byte_length, bool)
            or self.expected_raw_byte_length < 0
        ):
            raise ValidationError("expected_raw_byte_length is invalid")
        if self.expected_raw_sha256 is not None:
            _sha256(self.expected_raw_sha256, "expected_raw_sha256")
        if (self.expected_raw_byte_length is None) != (self.expected_raw_sha256 is None):
            raise ValidationError("expected raw length and hash must be paired")
        if self.expected_raw_byte_length is None and self.declared_encoding is not None:
            raise ValidationError("declared encoding requires configured raw bytes")
        if self.configured_outcome == "output":
            if self.expected_raw_byte_length is None or self.configured_failure_code is not None:
                raise ValidationError("output configuration is inconsistent")
        elif self.configured_outcome == "provider_inactive":
            if self.provider_mode != "inactive" or self.expected_raw_byte_length is not None:
                raise ValidationError("inactive provider configuration is inconsistent")
        elif self.configured_failure_code is None:
            raise ValidationError("failed configuration requires a failure code")
        validate_provider_metadata_json(
            self.provider_metadata_json,
            field="provider_configuration.provider_metadata_json",
        )
        if not isinstance(self.denied_capability_profile, CapabilityProfile):
            raise ValidationError("denied_capability_profile is invalid")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "activation_state": self.activation_state,
            "configured_failure_code": self.configured_failure_code,
            "configured_outcome": self.configured_outcome,
            "contract_version": self.contract_version,
            "declared_encoding": self.declared_encoding,
            "denied_capability_profile": self.denied_capability_profile.canonical_value(),
            "expected_raw_byte_length": self.expected_raw_byte_length,
            "expected_raw_sha256": self.expected_raw_sha256,
            "fixture_id": self.fixture_id,
            "provider_id": self.provider_id,
            "provider_metadata": validate_provider_metadata_json(
                self.provider_metadata_json,
                field="provider_configuration.provider_metadata_json",
            ),
            "provider_mode": self.provider_mode,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())

    @classmethod
    def from_mapping(cls, value: object) -> "ProviderConfigurationSnapshot":
        if not isinstance(value, Mapping):
            raise ValidationError("provider configuration snapshot must be an object")
        expected = {
            "activation_state", "configured_failure_code", "configured_outcome",
            "contract_version", "declared_encoding", "denied_capability_profile",
            "expected_raw_byte_length", "expected_raw_sha256", "fixture_id",
            "provider_id", "provider_metadata", "provider_mode",
        }
        if set(value) != expected or not isinstance(value["denied_capability_profile"], Mapping):
            raise ValidationError("provider configuration snapshot fields are invalid")
        metadata_json = canonical_json_text(value["provider_metadata"])
        return cls(
            provider_id=value["provider_id"],
            provider_mode=value["provider_mode"],
            activation_state=value["activation_state"],
            fixture_id=value["fixture_id"],
            declared_encoding=value["declared_encoding"],
            configured_outcome=value["configured_outcome"],
            configured_failure_code=value["configured_failure_code"],
            expected_raw_byte_length=value["expected_raw_byte_length"],
            expected_raw_sha256=value["expected_raw_sha256"],
            provider_metadata_json=metadata_json,
            denied_capability_profile=CapabilityProfile(**dict(value["denied_capability_profile"])),
            contract_version=value["contract_version"],
        )

    def admits(self, result: "ProviderCallResult") -> bool:
        if not isinstance(result, ProviderCallResult):
            return False
        return (
            result.outcome == self.configured_outcome
            and result.declared_encoding == self.declared_encoding
            and result.failure_code == self.configured_failure_code
            and (None if result.raw_output is None else len(result.raw_output))
            == self.expected_raw_byte_length
            and (None if result.raw_output is None else sha256_bytes(result.raw_output))
            == self.expected_raw_sha256
            and result.provider_metadata_json == self.provider_metadata_json
        )


@dataclass(frozen=True, slots=True)
class DeterministicMockFixture:
    """Immutable data-only result configuration for the shipped mock provider."""

    fixture_id: str
    raw_output: bytes | None
    declared_encoding: str | None
    outcome: str = "output"
    failure_code: str | None = None
    provider_metadata_json: str = "{}"

    def __post_init__(self) -> None:
        _token(self.fixture_id, "fixture_id")
        if self.outcome not in {"output", "provider_failed", "timed_out"}:
            raise ValidationError("mock fixture outcome is invalid")
        if self.raw_output is not None and not isinstance(self.raw_output, bytes):
            raise ValidationError("mock fixture raw_output must be immutable bytes")
        if self.raw_output is None:
            if self.declared_encoding is not None:
                raise ValidationError(
                    "declared_encoding requires a raw output value"
                )
        else:
            _text(self.declared_encoding, "declared_encoding")
        if self.outcome == "output":
            if self.raw_output is None:
                raise ValidationError("output fixture requires raw bytes")
            if self.failure_code is not None:
                raise ValidationError("output fixture cannot contain a failure code")
        else:
            _token(self.failure_code, "failure_code")
        _canonical_object(self.provider_metadata_json, "provider_metadata_json")

    @property
    def configuration_snapshot(self) -> ProviderConfigurationSnapshot:
        return ProviderConfigurationSnapshot(
            provider_id="deterministic_mock",
            provider_mode="deterministic_mock",
            activation_state="test_fixture",
            fixture_id=self.fixture_id,
            declared_encoding=self.declared_encoding,
            configured_outcome=self.outcome,
            configured_failure_code=self.failure_code,
            expected_raw_byte_length=(
                None if self.raw_output is None else len(self.raw_output)
            ),
            expected_raw_sha256=(
                None if self.raw_output is None else sha256_bytes(self.raw_output)
            ),
            provider_metadata_json=self.provider_metadata_json,
            denied_capability_profile=CapabilityProfile(),
        )

    def configuration_value(self) -> dict[str, Any]:
        return self.configuration_snapshot.canonical_value()

    @property
    def configuration_hash(self) -> str:
        return self.configuration_snapshot.content_hash


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    """One complete immutable shipped-provider capability snapshot."""

    provider_id: str
    provider_name: str
    provider_mode: str
    adapter_contract_version: str
    transport_kind: str
    capability_profile: CapabilityProfile
    provider_configuration_json: str
    provider_configuration_hash: str

    def __post_init__(self) -> None:
        _token(self.provider_id, "provider_id")
        _token(self.provider_name, "provider_name")
        if self.provider_mode not in PROVIDER_MODES:
            raise ValidationError("provider_mode is invalid")
        if self.adapter_contract_version != PROVIDER_ADAPTER_CONTRACT_VERSION:
            raise ValidationError("provider adapter contract version is invalid")
        if self.transport_kind not in TRANSPORT_KINDS:
            raise ValidationError("provider transport_kind is invalid")
        if not isinstance(self.capability_profile, CapabilityProfile):
            raise ValidationError(
                "capability_profile must be a CapabilityProfile"
            )
        configuration = ProviderConfigurationSnapshot.from_mapping(
            _canonical_object(
                self.provider_configuration_json,
                "provider_configuration_json",
            )
        )
        if (
            configuration.provider_id != self.provider_id
            or configuration.provider_mode != self.provider_mode
        ):
            raise ValidationError(
                "provider descriptor configuration binding is invalid"
            )
        if configuration.denied_capability_profile != self.capability_profile:
            raise ValidationError(
                "provider descriptor capability profile differs from configuration"
            )
        _sha256(self.provider_configuration_hash, "provider_configuration_hash")
        if configuration.content_hash != self.provider_configuration_hash:
            raise ValidationError("provider configuration hash is invalid")
        expected_transport = (
            "none"
            if self.provider_mode == "inactive"
            else "in_process_mock"
        )
        if self.transport_kind != expected_transport:
            raise ValidationError("provider mode and transport do not match")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "adapter_contract_version": self.adapter_contract_version,
            "capability_profile": self.capability_profile.canonical_value(),
            "provider_configuration": ProviderConfigurationSnapshot.from_mapping(
                _canonical_object(
                    self.provider_configuration_json,
                    "provider_configuration_json",
                )
            ).canonical_value(),
            "provider_configuration_hash": self.provider_configuration_hash,
            "provider_id": self.provider_id,
            "provider_mode": self.provider_mode,
            "provider_name": self.provider_name,
            "transport_kind": self.transport_kind,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def descriptor_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class LocalProviderConfiguration:
    """Versioned configuration boundary whose only I4-B state is inactive."""

    provider_id: str
    adapter_kind: str
    provider_descriptor_hash: str
    model_descriptor_hash: str
    denied_capability_profile: CapabilityProfile
    activation_state: str = "inactive"
    contract_version: str = LOCAL_PROVIDER_CONFIGURATION_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != LOCAL_PROVIDER_CONFIGURATION_VERSION:
            raise ValidationError("local provider configuration version is invalid")
        _token(self.provider_id, "provider_id")
        _token(self.adapter_kind, "adapter_kind")
        if self.activation_state != "inactive":
            raise ValidationError(
                "I4-B local provider configuration must remain inactive"
            )
        _sha256(self.provider_descriptor_hash, "provider_descriptor_hash")
        _sha256(self.model_descriptor_hash, "model_descriptor_hash")
        if not isinstance(self.denied_capability_profile, CapabilityProfile):
            raise ValidationError(
                "denied_capability_profile must be a CapabilityProfile"
            )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "activation_state": self.activation_state,
            "adapter_kind": self.adapter_kind,
            "contract_version": self.contract_version,
            "denied_capability_profile": (
                self.denied_capability_profile.canonical_value()
            ),
            "model_descriptor_hash": self.model_descriptor_hash,
            "provider_descriptor_hash": self.provider_descriptor_hash,
            "provider_id": self.provider_id,
        }


@dataclass(frozen=True, slots=True)
class ProviderCallResult:
    """Provider-reported result, kept separate from runtime conclusions."""

    outcome: str
    raw_output: bytes | None
    declared_encoding: str | None
    failure_code: str | None
    provider_metadata_json: str = "{}"

    def __post_init__(self) -> None:
        if self.outcome not in PROVIDER_RESULT_OUTCOMES:
            raise ValidationError("provider result outcome is invalid")
        if self.raw_output is not None and not isinstance(self.raw_output, bytes):
            raise ValidationError("provider raw output must be immutable bytes")
        if self.raw_output is None:
            if self.declared_encoding is not None:
                raise ValidationError(
                    "provider declared encoding requires returned bytes"
                )
        else:
            _text(self.declared_encoding, "declared_encoding")
        if self.outcome == "output":
            if self.raw_output is None:
                raise ValidationError("output provider result requires bytes")
            if self.failure_code is not None:
                raise ValidationError(
                    "successful provider result cannot contain failure_code"
                )
        else:
            _token(self.failure_code, "failure_code")
        if self.outcome == "provider_inactive" and self.raw_output is not None:
            raise ValidationError("inactive provider cannot return output")
        _canonical_object(self.provider_metadata_json, "provider_metadata_json")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "declared_encoding": self.declared_encoding,
            "failure_code": self.failure_code,
            "outcome": self.outcome,
            "provider_metadata": _canonical_object(
                self.provider_metadata_json,
                "provider_metadata_json",
            ),
            "raw_byte_length": (
                None if self.raw_output is None else len(self.raw_output)
            ),
            "raw_output_sha256": (
                None
                if self.raw_output is None
                else sha256_bytes(self.raw_output)
            ),
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())

    @classmethod
    def inactive(cls) -> ProviderCallResult:
        return cls(
            outcome="provider_inactive",
            raw_output=None,
            declared_encoding=None,
            failure_code="provider_inactive",
        )

    @classmethod
    def runtime_failure(cls, code: str) -> ProviderCallResult:
        _token(code, "provider failure code")
        return cls(
            outcome="provider_failed",
            raw_output=None,
            declared_encoding=None,
            failure_code=code,
        )


def validate_provider_result_against_configuration(
    result: ProviderCallResult,
    configuration: ProviderConfigurationSnapshot,
) -> None:
    if not configuration.admits(result):
        raise ValidationError(
            "provider result differs from the immutable configuration snapshot"
        )


class ProviderProtocol(Protocol):
    """The complete in-process Python capability surface supplied to providers."""

    def describe(self) -> ProviderDescriptor:
        """Return immutable capability metadata without a runtime handle."""

    def invoke(self, canonical_input_bytes: bytes) -> ProviderCallResult:
        """Receive only immutable canonical input bytes and return typed data."""
