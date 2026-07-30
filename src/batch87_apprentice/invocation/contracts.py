"""Immutable canonical contracts for the B87-I4-B invocation bridge."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_bytes,
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_bytes, sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc
from batch87_apprentice.providers.contracts import ProviderDescriptor

MODEL_INPUT_PROTOCOL = "batch87.model-input"
MODEL_INPUT_PROTOCOL_VERSION = "1.0.0"
APPRENTICE_RESPONSE_PROTOCOL = "batch87.apprentice-response"
APPRENTICE_RESPONSE_PROTOCOL_VERSION = "1.0.0"
INVOCATION_CONTRACT_VERSION = "1.0.0"
INFERENCE_CONFIGURATION_VERSION = "1.0.0"

INVOCATION_STATES = frozenset(
    {
        "prepared",
        "in_progress",
        "raw_output_captured",
        "provider_inactive",
        "succeeded",
        "provider_failed",
        "timed_out",
        "invalid_response",
        "stale_context",
        "interrupted",
    }
)
NON_TERMINAL_INVOCATION_STATES = frozenset(
    {"prepared", "in_progress", "raw_output_captured"}
)
TERMINAL_INVOCATION_STATES = INVOCATION_STATES - NON_TERMINAL_INVOCATION_STATES
DECODE_STATUSES = frozenset({"not_attempted", "decoded", "undecodable"})
PARSE_STATUSES = frozenset({"parsed", "malformed_json", "not_attempted"})
VALIDATION_STATUSES = frozenset({"valid", "invalid", "not_attempted"})
TASK_DISPOSITIONS = frozenset(
    {
        "completed",
        "failed",
        "deferred_human_review",
        "unchanged_terminal",
        "not_applicable",
    }
)
_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")
_FORBIDDEN_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "bearer_token",
        "callback",
        "command",
        "credential",
        "credentials",
        "endpoint",
        "environment_variable",
        "executable",
        "function",
        "host",
        "model_path",
        "password",
        "port",
        "secret",
        "socket",
        "token",
        "tool",
        "tools",
        "url",
    }
)
_ALLOWED_TRANSITIONS = frozenset(
    {
        (None, "prepared"),
        ("prepared", "in_progress"),
        ("prepared", "provider_inactive"),
        ("in_progress", "raw_output_captured"),
        ("in_progress", "provider_failed"),
        ("in_progress", "timed_out"),
        ("in_progress", "stale_context"),
        ("in_progress", "interrupted"),
        ("raw_output_captured", "succeeded"),
        ("raw_output_captured", "provider_failed"),
        ("raw_output_captured", "timed_out"),
        ("raw_output_captured", "invalid_response"),
        ("raw_output_captured", "stale_context"),
        ("raw_output_captured", "interrupted"),
    }
)


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


def _canonical_value(
    value: object,
    field: str,
    *,
    expected_type: type,
) -> Any:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be canonical JSON text")
    parsed = parse_json(value)
    if not isinstance(parsed, expected_type) or canonical_json_text(parsed) != value:
        raise ValidationError(
            f"{field} must be canonical JSON {expected_type.__name__}"
        )
    return parsed


def _safe_scalar_text(value: object, field: str) -> str:
    text = _text(value, field)
    lowered = text.lower()
    if (
        "://" in text
        or lowered.startswith(("sk-", "bearer ", "api_key="))
        or text.startswith(("/", "\\\\"))
        or re.match(r"^[a-zA-Z]:[\\/]", text)
    ):
        raise ValidationError(f"{field} contains a prohibited endpoint, path, or secret")
    return text


def reject_executable_or_secret_structure(
    value: object,
    *,
    path: str = "$",
) -> None:
    """Reject caller-shaped capability handles before canonicalization."""

    if callable(value):
        raise ValidationError(f"{path} contains a callable capability")
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValidationError(f"{path} contains a non-text field")
            child = f"{path}.{key}"
            if key.lower() in _FORBIDDEN_KEYS:
                raise ValidationError(f"{child} is a prohibited capability field")
            reject_executable_or_secret_structure(nested, path=child)
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            reject_executable_or_secret_structure(
                nested,
                path=f"{path}[{index}]",
            )


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    """Exact logical model target copied from factual runtime identity."""

    model_name: str
    model_revision: str
    quantisation: str | None
    active_adapter: str | None
    context_limit: int
    descriptor_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if self.descriptor_version != "1.0.0":
            raise ValidationError("model descriptor version is invalid")
        _safe_scalar_text(self.model_name, "model_name")
        _safe_scalar_text(self.model_revision, "model_revision")
        if self.quantisation is not None:
            _safe_scalar_text(self.quantisation, "quantisation")
        if self.active_adapter is not None:
            _safe_scalar_text(self.active_adapter, "active_adapter")
        if (
            not isinstance(self.context_limit, int)
            or isinstance(self.context_limit, bool)
            or self.context_limit <= 0
        ):
            raise ValidationError("context_limit must be a positive integer")

    @classmethod
    def from_mapping(cls, value: object) -> ModelDescriptor:
        if not isinstance(value, Mapping):
            raise ValidationError("model_descriptor must be an object")
        reject_executable_or_secret_structure(value, path="model_descriptor")
        expected = {
            "active_adapter",
            "context_limit",
            "descriptor_version",
            "model_name",
            "model_revision",
            "quantisation",
        }
        if set(value) != expected:
            raise ValidationError("model_descriptor fields are invalid")
        return cls(**{key: value[key] for key in expected})

    def canonical_value(self) -> dict[str, Any]:
        return {
            "active_adapter": self.active_adapter,
            "context_limit": self.context_limit,
            "descriptor_version": self.descriptor_version,
            "model_name": self.model_name,
            "model_revision": self.model_revision,
            "quantisation": self.quantisation,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def descriptor_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class InferenceConfiguration:
    """Provider-neutral deterministic scalar settings used by I4-B."""

    max_output_tokens: int
    temperature: float = 0.0
    top_p: float = 1.0
    contract_version: str = INFERENCE_CONFIGURATION_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != INFERENCE_CONFIGURATION_VERSION:
            raise ValidationError("inference configuration version is invalid")
        if (
            not isinstance(self.max_output_tokens, int)
            or isinstance(self.max_output_tokens, bool)
            or self.max_output_tokens <= 0
        ):
            raise ValidationError("max_output_tokens must be a positive integer")
        if (
            not isinstance(self.temperature, (int, float))
            or isinstance(self.temperature, bool)
            or float(self.temperature) != 0.0
        ):
            raise ValidationError("I4-B temperature must be exactly zero")
        if (
            not isinstance(self.top_p, (int, float))
            or isinstance(self.top_p, bool)
            or float(self.top_p) != 1.0
        ):
            raise ValidationError("I4-B top_p must be exactly one")

    @classmethod
    def from_mapping(cls, value: object) -> InferenceConfiguration:
        if not isinstance(value, Mapping):
            raise ValidationError("inference_configuration must be an object")
        reject_executable_or_secret_structure(
            value,
            path="inference_configuration",
        )
        expected = {
            "contract_version",
            "max_output_tokens",
            "temperature",
            "top_p",
        }
        if set(value) != expected:
            raise ValidationError("inference_configuration fields are invalid")
        return cls(**{key: value[key] for key in expected})

    def canonical_value(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "max_output_tokens": self.max_output_tokens,
            "temperature": float(self.temperature),
            "top_p": float(self.top_p),
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class InvocationSpec:
    """Caller request containing identities and expected immutable bindings only."""

    model_invocation_id: str
    task_id: str
    session_id: str
    project_scope_id: str
    context_package_id: str
    context_package_hash: str
    runtime_identity_id: str
    runtime_identity_hash: str
    provider_id: str
    model_descriptor: ModelDescriptor
    inference_configuration: InferenceConfiguration
    output_schema_id: str
    output_schema_hash: str
    retry_of_invocation_id: str | None = None
    contract_version: str = INVOCATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != INVOCATION_CONTRACT_VERSION:
            raise ValidationError("invocation contract version is invalid")
        for field in (
            "model_invocation_id",
            "task_id",
            "session_id",
            "project_scope_id",
            "context_package_id",
            "runtime_identity_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        if self.retry_of_invocation_id is not None:
            validate_identifier(
                self.retry_of_invocation_id,
                field="retry_of_invocation_id",
            )
            if self.retry_of_invocation_id == self.model_invocation_id:
                raise ValidationError("invocation cannot retry itself")
        _sha256(self.context_package_hash, "context_package_hash")
        _sha256(self.runtime_identity_hash, "runtime_identity_hash")
        _token(self.provider_id, "provider_id")
        if not isinstance(self.model_descriptor, ModelDescriptor):
            raise ValidationError("model_descriptor is invalid")
        if not isinstance(self.inference_configuration, InferenceConfiguration):
            raise ValidationError("inference_configuration is invalid")
        _text(self.output_schema_id, "output_schema_id")
        _sha256(self.output_schema_hash, "output_schema_hash")

    @classmethod
    def from_mapping(cls, value: object) -> InvocationSpec:
        if not isinstance(value, Mapping):
            raise ValidationError("invocation spec must be an object")
        reject_executable_or_secret_structure(value, path="invocation")
        expected = {
            "context_package_hash",
            "context_package_id",
            "contract_version",
            "inference_configuration",
            "model_descriptor",
            "model_invocation_id",
            "output_schema_hash",
            "output_schema_id",
            "project_scope_id",
            "provider_id",
            "retry_of_invocation_id",
            "runtime_identity_hash",
            "runtime_identity_id",
            "session_id",
            "task_id",
        }
        if set(value) != expected:
            raise ValidationError("invocation spec fields are invalid")
        return cls(
            model_invocation_id=value["model_invocation_id"],
            task_id=value["task_id"],
            session_id=value["session_id"],
            project_scope_id=value["project_scope_id"],
            context_package_id=value["context_package_id"],
            context_package_hash=value["context_package_hash"],
            runtime_identity_id=value["runtime_identity_id"],
            runtime_identity_hash=value["runtime_identity_hash"],
            provider_id=value["provider_id"],
            model_descriptor=ModelDescriptor.from_mapping(
                value["model_descriptor"]
            ),
            inference_configuration=InferenceConfiguration.from_mapping(
                value["inference_configuration"]
            ),
            output_schema_id=value["output_schema_id"],
            output_schema_hash=value["output_schema_hash"],
            retry_of_invocation_id=value["retry_of_invocation_id"],
            contract_version=value["contract_version"],
        )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "context_package_hash": self.context_package_hash,
            "context_package_id": self.context_package_id,
            "contract_version": self.contract_version,
            "inference_configuration": (
                self.inference_configuration.canonical_value()
            ),
            "model_descriptor": self.model_descriptor.canonical_value(),
            "model_invocation_id": self.model_invocation_id,
            "output_schema_hash": self.output_schema_hash,
            "output_schema_id": self.output_schema_id,
            "project_scope_id": self.project_scope_id,
            "provider_id": self.provider_id,
            "retry_of_invocation_id": self.retry_of_invocation_id,
            "runtime_identity_hash": self.runtime_identity_hash,
            "runtime_identity_id": self.runtime_identity_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class ModelInputBinding:
    model_invocation_id: str
    task_id: str
    session_id: str
    project_scope_id: str
    context_package_id: str
    context_package_hash: str
    retrieval_manifest_id: str
    retrieval_manifest_hash: str
    task_memory_projection_hash: str
    task_context_finalization_id: str
    runtime_identity_id: str
    runtime_identity_hash: str
    provider_descriptor_hash: str
    inference_configuration_hash: str
    output_schema_id: str
    output_schema_hash: str

    def __post_init__(self) -> None:
        for field in (
            "model_invocation_id",
            "task_id",
            "session_id",
            "project_scope_id",
            "context_package_id",
            "retrieval_manifest_id",
            "task_context_finalization_id",
            "runtime_identity_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        for field in (
            "context_package_hash",
            "retrieval_manifest_hash",
            "task_memory_projection_hash",
            "runtime_identity_hash",
            "provider_descriptor_hash",
            "inference_configuration_hash",
            "output_schema_hash",
        ):
            _sha256(getattr(self, field), field)
        _text(self.output_schema_id, "output_schema_id")

    def canonical_value(self) -> dict[str, str]:
        return {
            "context_package_hash": self.context_package_hash,
            "context_package_id": self.context_package_id,
            "inference_configuration_hash": self.inference_configuration_hash,
            "model_invocation_id": self.model_invocation_id,
            "output_schema_hash": self.output_schema_hash,
            "output_schema_id": self.output_schema_id,
            "project_scope_id": self.project_scope_id,
            "provider_descriptor_hash": self.provider_descriptor_hash,
            "retrieval_manifest_hash": self.retrieval_manifest_hash,
            "retrieval_manifest_id": self.retrieval_manifest_id,
            "runtime_identity_hash": self.runtime_identity_hash,
            "runtime_identity_id": self.runtime_identity_id,
            "session_id": self.session_id,
            "task_context_finalization_id": self.task_context_finalization_id,
            "task_id": self.task_id,
            "task_memory_projection_hash": self.task_memory_projection_hash,
        }


@dataclass(frozen=True, slots=True)
class ModelInputPacket:
    """Canonical immutable packet copied from verified I4-A sections."""

    invocation: ModelInputBinding
    task_json: str
    authority_json: str
    identity_json: str
    policy_json: str
    memory_json: str
    evidence_json: str
    output_contract_json: str
    protocol: str = MODEL_INPUT_PROTOCOL
    protocol_version: str = MODEL_INPUT_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.protocol != MODEL_INPUT_PROTOCOL:
            raise ValidationError("model-input protocol is invalid")
        if self.protocol_version != MODEL_INPUT_PROTOCOL_VERSION:
            raise ValidationError("model-input protocol version is invalid")
        if not isinstance(self.invocation, ModelInputBinding):
            raise ValidationError("model-input invocation binding is invalid")
        for field in ("task_json", "authority_json", "identity_json"):
            _canonical_value(getattr(self, field), field, expected_type=dict)
        for field in ("policy_json", "memory_json", "evidence_json"):
            _canonical_value(getattr(self, field), field, expected_type=list)
        _canonical_value(
            self.output_contract_json,
            "output_contract_json",
            expected_type=dict,
        )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "authority": _canonical_value(
                self.authority_json,
                "authority_json",
                expected_type=dict,
            ),
            "evidence": _canonical_value(
                self.evidence_json,
                "evidence_json",
                expected_type=list,
            ),
            "identity": _canonical_value(
                self.identity_json,
                "identity_json",
                expected_type=dict,
            ),
            "invocation": self.invocation.canonical_value(),
            "memory": _canonical_value(
                self.memory_json,
                "memory_json",
                expected_type=list,
            ),
            "output_contract": _canonical_value(
                self.output_contract_json,
                "output_contract_json",
                expected_type=dict,
            ),
            "policy": _canonical_value(
                self.policy_json,
                "policy_json",
                expected_type=list,
            ),
            "protocol": self.protocol,
            "protocol_version": self.protocol_version,
            "task": _canonical_value(
                self.task_json,
                "task_json",
                expected_type=dict,
            ),
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_bytes(self.canonical_bytes)


@dataclass(frozen=True, slots=True)
class InvocationRequest:
    """Complete canonical request persisted before provider execution."""

    spec: InvocationSpec
    provider_descriptor: ProviderDescriptor
    model_input_packet: ModelInputPacket

    def __post_init__(self) -> None:
        if not isinstance(self.spec, InvocationSpec):
            raise ValidationError("request spec is invalid")
        if not isinstance(self.provider_descriptor, ProviderDescriptor):
            raise ValidationError("provider descriptor is invalid")
        if not isinstance(self.model_input_packet, ModelInputPacket):
            raise ValidationError("model-input packet is invalid")
        binding = self.model_input_packet.invocation
        if (
            binding.model_invocation_id != self.spec.model_invocation_id
            or binding.task_id != self.spec.task_id
            or binding.session_id != self.spec.session_id
            or binding.project_scope_id != self.spec.project_scope_id
            or binding.context_package_id != self.spec.context_package_id
            or binding.context_package_hash != self.spec.context_package_hash
            or binding.runtime_identity_id != self.spec.runtime_identity_id
            or binding.runtime_identity_hash != self.spec.runtime_identity_hash
            or binding.provider_descriptor_hash
            != self.provider_descriptor.descriptor_hash
            or binding.inference_configuration_hash
            != self.spec.inference_configuration.content_hash
            or binding.output_schema_id != self.spec.output_schema_id
            or binding.output_schema_hash != self.spec.output_schema_hash
        ):
            raise ValidationError("request and model-input bindings differ")
        if self.provider_descriptor.provider_id != self.spec.provider_id:
            raise ValidationError("request provider identity differs")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "inference_configuration": (
                self.spec.inference_configuration.canonical_value()
            ),
            "model_descriptor": self.spec.model_descriptor.canonical_value(),
            "model_input_packet": self.model_input_packet.canonical_value(),
            "provider_descriptor": self.provider_descriptor.canonical_value(),
            "retry_of_invocation_id": self.spec.retry_of_invocation_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class InvocationStateTransition:
    transition_id: str
    model_invocation_id: str
    sequence_number: int
    from_status: str | None
    to_status: str
    reason_code: str
    changed_at: str
    changed_by_principal: str

    def __post_init__(self) -> None:
        validate_identifier(self.transition_id, field="transition_id")
        validate_identifier(
            self.model_invocation_id,
            field="model_invocation_id",
        )
        if (
            not isinstance(self.sequence_number, int)
            or isinstance(self.sequence_number, bool)
            or self.sequence_number < 0
        ):
            raise ValidationError("transition sequence must be non-negative")
        if self.from_status is not None and self.from_status not in INVOCATION_STATES:
            raise ValidationError("transition from_status is invalid")
        if self.to_status not in INVOCATION_STATES:
            raise ValidationError("transition to_status is invalid")
        if (self.from_status, self.to_status) not in _ALLOWED_TRANSITIONS:
            raise ValidationError("invocation transition is not permitted")
        if (self.sequence_number == 0) != (self.from_status is None):
            raise ValidationError("initial transition shape is invalid")
        _token(self.reason_code, "reason_code")
        parse_canonical_utc(self.changed_at, field="changed_at")
        if self.changed_by_principal not in {
            "operator",
            "codex_development_harness",
        }:
            raise ValidationError("transition principal is invalid")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "changed_at": self.changed_at,
            "changed_by_principal": self.changed_by_principal,
            "from_status": self.from_status,
            "model_invocation_id": self.model_invocation_id,
            "reason_code": self.reason_code,
            "sequence_number": self.sequence_number,
            "to_status": self.to_status,
            "transition_id": self.transition_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True, order=True)
class ValidationIssue:
    path: str
    code: str
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.startswith("$"):
            raise ValidationError("validation issue path must start with '$'")
        _token(self.code, "validation issue code")
        _text(self.detail, "validation issue detail")

    def canonical_value(self) -> dict[str, str]:
        return {
            "code": self.code,
            "detail": self.detail,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True)
class RawOutputCapture:
    raw_output_id: str
    model_invocation_id: str
    provider_call_attempt_id: str
    raw_bytes: bytes
    declared_encoding: str
    provider_result_hash: str
    captured_at: str

    def __post_init__(self) -> None:
        for field in (
            "raw_output_id",
            "model_invocation_id",
            "provider_call_attempt_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        if not isinstance(self.raw_bytes, bytes):
            raise ValidationError("raw_bytes must be immutable bytes")
        _text(self.declared_encoding, "declared_encoding")
        _sha256(self.provider_result_hash, "provider_result_hash")
        parse_canonical_utc(self.captured_at, field="captured_at")

    @property
    def raw_byte_length(self) -> int:
        return len(self.raw_bytes)

    @property
    def raw_output_sha256(self) -> str:
        return sha256_bytes(self.raw_bytes)

    def canonical_value(self) -> dict[str, Any]:
        return {
            "captured_at": self.captured_at,
            "declared_encoding": self.declared_encoding,
            "model_invocation_id": self.model_invocation_id,
            "provider_call_attempt_id": self.provider_call_attempt_id,
            "provider_result_hash": self.provider_result_hash,
            "raw_byte_length": self.raw_byte_length,
            "raw_output_id": self.raw_output_id,
            "raw_output_sha256": self.raw_output_sha256,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class OutputProcessingResult:
    utf8_decode_status: str
    decoded_text: str | None
    decode_errors: tuple[ValidationIssue, ...]
    parse_status: str
    parse_errors: tuple[ValidationIssue, ...]
    parsed_canonical_json: str | None
    parsed_output_hash: str | None
    schema_status: str
    schema_errors: tuple[ValidationIssue, ...]
    semantic_status: str
    semantic_errors: tuple[ValidationIssue, ...]
    repair_attempted: bool = False
    repair_succeeded: bool = False

    def __post_init__(self) -> None:
        if self.utf8_decode_status not in DECODE_STATUSES:
            raise ValidationError("utf8_decode_status is invalid")
        if self.parse_status not in PARSE_STATUSES:
            raise ValidationError("parse_status is invalid")
        if self.schema_status not in VALIDATION_STATUSES:
            raise ValidationError("schema_status is invalid")
        if self.semantic_status not in VALIDATION_STATUSES:
            raise ValidationError("semantic_status is invalid")
        for field in (
            "decode_errors",
            "parse_errors",
            "schema_errors",
            "semantic_errors",
        ):
            value = getattr(self, field)
            if not isinstance(value, tuple) or any(
                not isinstance(issue, ValidationIssue) for issue in value
            ):
                raise ValidationError(f"{field} must contain validation issues")
            if value != tuple(sorted(value)):
                raise ValidationError(f"{field} must use stable sorted order")
        if self.repair_attempted or self.repair_succeeded:
            raise ValidationError("I4-B output repair is prohibited")
        if self.utf8_decode_status == "decoded":
            if not isinstance(self.decoded_text, str):
                raise ValidationError("decoded output requires exact Unicode text")
            if self.decode_errors:
                raise ValidationError("decoded output cannot contain decode errors")
        elif self.decoded_text is not None:
            raise ValidationError("non-decoded output cannot contain decoded text")
        elif self.utf8_decode_status == "undecodable" and not self.decode_errors:
            raise ValidationError("undecodable output requires a stable error")
        if self.parse_status == "parsed":
            if self.decoded_text is None or self.parsed_canonical_json is None:
                raise ValidationError("parsed output requires decoded and parsed values")
            parsed = parse_json(self.parsed_canonical_json)
            if canonical_json_text(parsed) != self.parsed_canonical_json:
                raise ValidationError("parsed output must be canonical JSON")
            expected_hash = sha256_canonical_json(parsed)
            if self.parsed_output_hash != expected_hash:
                raise ValidationError("parsed output hash is invalid")
            if self.parse_errors:
                raise ValidationError("parsed output cannot contain parse errors")
        else:
            if self.parsed_canonical_json is not None or self.parsed_output_hash is not None:
                raise ValidationError("unparsed output cannot contain parsed data")
            if self.parse_status == "malformed_json" and not self.parse_errors:
                raise ValidationError("malformed JSON requires a stable error")
        if self.schema_status == "valid" and self.schema_errors:
            raise ValidationError("schema-valid output cannot contain schema errors")
        if self.schema_status == "invalid" and not self.schema_errors:
            raise ValidationError("schema-invalid output requires errors")
        if self.semantic_status == "valid" and self.semantic_errors:
            raise ValidationError("semantic-valid output cannot contain errors")
        if self.semantic_status == "invalid" and not self.semantic_errors:
            raise ValidationError("semantic-invalid output requires errors")
        if self.utf8_decode_status != "decoded" and (
            self.parse_status != "not_attempted"
            or self.schema_status != "not_attempted"
            or self.semantic_status != "not_attempted"
        ):
            raise ValidationError("decode failure must stop later processing")
        if self.parse_status != "parsed" and (
            self.schema_status != "not_attempted"
            or self.semantic_status != "not_attempted"
        ):
            raise ValidationError("parse failure must stop later validation")
        if self.schema_status != "valid" and self.semantic_status != "not_attempted":
            raise ValidationError("semantic validation requires schema success")

    @property
    def successful(self) -> bool:
        return (
            self.utf8_decode_status == "decoded"
            and self.parse_status == "parsed"
            and self.schema_status == "valid"
            and self.semantic_status == "valid"
        )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "decode_errors": [
                issue.canonical_value() for issue in self.decode_errors
            ],
            "decoded_text": self.decoded_text,
            "parse_errors": [
                issue.canonical_value() for issue in self.parse_errors
            ],
            "parse_status": self.parse_status,
            "parsed_output": (
                None
                if self.parsed_canonical_json is None
                else parse_json(self.parsed_canonical_json)
            ),
            "parsed_output_hash": self.parsed_output_hash,
            "repair_attempted": self.repair_attempted,
            "repair_succeeded": self.repair_succeeded,
            "schema_errors": [
                issue.canonical_value() for issue in self.schema_errors
            ],
            "schema_status": self.schema_status,
            "semantic_errors": [
                issue.canonical_value() for issue in self.semantic_errors
            ],
            "semantic_status": self.semantic_status,
            "utf8_decode_status": self.utf8_decode_status,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class TerminalFinalizationResult:
    model_invocation_id: str
    terminal_status: str
    provider_result_hash: str | None
    model_output_id: str | None
    model_output_hash: str | None
    task_disposition: str
    task_transition_id: str | None
    failure_classification: str | None
    finalized_at: str

    def __post_init__(self) -> None:
        validate_identifier(
            self.model_invocation_id,
            field="model_invocation_id",
        )
        if self.terminal_status not in TERMINAL_INVOCATION_STATES:
            raise ValidationError("finalization requires a terminal status")
        if self.provider_result_hash is not None:
            _sha256(self.provider_result_hash, "provider_result_hash")
        if (self.model_output_id is None) != (self.model_output_hash is None):
            raise ValidationError("model output identity and hash must be paired")
        if self.model_output_id is not None:
            validate_identifier(self.model_output_id, field="model_output_id")
            _sha256(self.model_output_hash, "model_output_hash")
        if self.task_disposition not in TASK_DISPOSITIONS:
            raise ValidationError("task_disposition is invalid")
        if self.task_transition_id is not None:
            validate_identifier(
                self.task_transition_id,
                field="task_transition_id",
            )
        if self.task_disposition in {"completed", "failed"}:
            if self.task_transition_id is None:
                raise ValidationError(
                    "task terminal disposition requires its transition"
                )
        elif self.task_transition_id is not None:
            raise ValidationError(
                "non-transition task disposition cannot carry a transition"
            )
        if self.failure_classification is not None:
            _token(self.failure_classification, "failure_classification")
        if self.terminal_status == "succeeded":
            if self.model_output_id is None or self.failure_classification is not None:
                raise ValidationError("successful finalization is inconsistent")
        elif self.failure_classification is None:
            raise ValidationError(
                "non-successful finalization requires a failure classification"
            )
        parse_canonical_utc(self.finalized_at, field="finalized_at")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "failure_classification": self.failure_classification,
            "finalized_at": self.finalized_at,
            "model_invocation_id": self.model_invocation_id,
            "model_output_hash": self.model_output_hash,
            "model_output_id": self.model_output_id,
            "provider_result_hash": self.provider_result_hash,
            "task_disposition": self.task_disposition,
            "task_transition_id": self.task_transition_id,
            "terminal_status": self.terminal_status,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class InvocationReconstruction:
    """Integrity-verified reconstruction with exact bytes kept out of JSON."""

    canonical_json: str
    content_hash: str
    raw_output_bytes: bytes | None
    integrity_verified: bool = True

    def __post_init__(self) -> None:
        value = _canonical_value(
            self.canonical_json,
            "reconstruction canonical_json",
            expected_type=dict,
        )
        if sha256_canonical_json(value) != self.content_hash:
            raise ValidationError("reconstruction content hash is invalid")
        if self.raw_output_bytes is not None and not isinstance(
            self.raw_output_bytes,
            bytes,
        ):
            raise ValidationError("reconstruction raw output must be bytes")
        if not isinstance(self.integrity_verified, bool):
            raise ValidationError("integrity_verified must be boolean")

    @property
    def value(self) -> dict[str, Any]:
        return _canonical_value(
            self.canonical_json,
            "reconstruction canonical_json",
            expected_type=dict,
        )
