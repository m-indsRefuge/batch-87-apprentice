from __future__ import annotations

from dataclasses import is_dataclass, replace
from pathlib import Path

import pytest

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_bytes
from batch87_apprentice.invocation.contracts import (
    InferenceConfiguration,
    InvocationReconstruction,
    InvocationRequest,
    InvocationSpec,
    InvocationStateTransition,
    ModelDescriptor,
    ModelInputBinding,
    ModelInputPacket,
    OutputProcessingResult,
    RawOutputCapture,
    TerminalFinalizationResult,
    ValidationIssue,
    reject_executable_or_secret_structure,
)
from batch87_apprentice.invocation.processing import (
    process_raw_output,
    task_completion_disposition,
)
from batch87_apprentice.invocation.schemas import (
    APPRENTICE_RESPONSE_SCHEMA_HASH,
    APPRENTICE_RESPONSE_SCHEMA_ID,
    MODEL_INPUT_SCHEMA_HASH,
    MODEL_INPUT_SCHEMA_ID,
    resolve_response_schema,
    resolve_schema,
    validate_apprentice_response,
)
from batch87_apprentice.providers import (
    CapabilityProfile,
    DeterministicMockFixture,
    LocalProviderConfiguration,
    ProviderCallResult,
    ProviderConfigurationSnapshot,
    ProviderDescriptor,
    ProviderRegistry,
)
from tests.support.i2_fixtures import uid


def response(
    *,
    task_id: str = uid(1),
    status: str = "completed",
    recommendations: list[str] | None = None,
) -> dict[str, object]:
    return {
        "evidence_used": [],
        "inferences": ["A bounded inference."],
        "memory_used": [],
        "observations": ["A bounded observation."],
        "protocol": "batch87.apprentice-response",
        "protocol_version": "1.0.0",
        "recommendations": recommendations or [],
        "status": status,
        "stop_reason": None,
        "stop_requested": False,
        "task_id": task_id,
        "uncertainties": [],
    }


def task_section(
    *,
    task_type: str = "i4b_bounded_response",
) -> dict[str, object]:
    return {
        "expected_output_schema_id": APPRENTICE_RESPONSE_SCHEMA_ID,
        "governing_constraints": [
            "b87_s1_permissions",
            "structured_authority_only",
        ],
        "prohibited_actions": ["execute", "autonomous_action", "tool_use"],
        "task_type": task_type,
    }


def process(value: object, **kwargs):
    return process_raw_output(
        canonical_json_text(value).encode("utf-8"),
        declared_encoding=kwargs.pop("declared_encoding", "utf-8"),
        task_id=kwargs.pop("task_id", uid(1)),
        task_section=kwargs.pop("task", task_section()),
        allowed_memory_ids=kwargs.pop("allowed_memory_ids", frozenset()),
        allowed_evidence_ids=kwargs.pop("allowed_evidence_ids", frozenset()),
        **kwargs,
    )


def test_all_i4b_value_contracts_are_frozen_and_slotted() -> None:
    contracts = (
        CapabilityProfile,
        DeterministicMockFixture,
        ProviderDescriptor,
        ProviderConfigurationSnapshot,
        LocalProviderConfiguration,
        ProviderCallResult,
        ModelDescriptor,
        InferenceConfiguration,
        InvocationSpec,
        ModelInputBinding,
        ModelInputPacket,
        InvocationRequest,
        InvocationStateTransition,
        ValidationIssue,
        RawOutputCapture,
        OutputProcessingResult,
        TerminalFinalizationResult,
        InvocationReconstruction,
    )

    for contract in contracts:
        assert is_dataclass(contract)
        assert contract.__dataclass_params__.frozen
        assert hasattr(contract, "__slots__")


def test_invalid_identifiers_timestamps_enums_and_hashes_fail_closed() -> None:
    with pytest.raises(ValidationError, match="UUID"):
        InvocationStateTransition(
            transition_id="not-an-identifier",
            model_invocation_id=uid(1),
            sequence_number=0,
            from_status=None,
            to_status="prepared",
            reason_code="invocation_prepared",
            changed_at="2026-07-30T00:00:00.000000Z",
            changed_by_principal="operator",
        )
    with pytest.raises(ValidationError, match="YYYY-MM-DD"):
        InvocationStateTransition(
            transition_id=uid(2),
            model_invocation_id=uid(1),
            sequence_number=0,
            from_status=None,
            to_status="prepared",
            reason_code="invocation_prepared",
            changed_at="not-a-timestamp",
            changed_by_principal="operator",
        )
    with pytest.raises(ValidationError, match="outcome"):
        ProviderCallResult(
            outcome="remote_success",
            raw_output=None,
            declared_encoding=None,
            failure_code="remote_success",
        )
    with pytest.raises(ValidationError, match="SHA-256"):
        RawOutputCapture(
            raw_output_id=uid(3),
            model_invocation_id=uid(1),
            provider_call_attempt_id=uid(4),
            raw_bytes=b"",
            declared_encoding="utf-8",
            provider_result_hash="not-a-hash",
            captured_at="2026-07-30T00:00:00.000000Z",
        )


def test_negative_terminal_requires_sanitized_failure_classification() -> None:
    with pytest.raises(ValidationError, match="failure classification"):
        TerminalFinalizationResult(
            model_invocation_id=uid(1),
            terminal_status="interrupted",
            provider_result_hash=None,
            model_output_id=None,
            model_output_hash=None,
            task_disposition="not_applicable",
            task_transition_id=None,
            failure_classification=None,
            finalized_at="2026-07-30T00:00:00.000000Z",
        )


def test_same_canonical_spec_is_stable_and_one_changed_input_changes_hash() -> None:
    descriptor = ModelDescriptor(
        model_name="fixture/model",
        model_revision="fixture-revision",
        quantisation=None,
        active_adapter=None,
        context_limit=1024,
    )
    spec = InvocationSpec(
        model_invocation_id=uid(1),
        task_id=uid(2),
        session_id=uid(3),
        project_scope_id=uid(4),
        context_package_id=uid(5),
        context_package_hash="a" * 64,
        runtime_identity_id=uid(6),
        runtime_identity_hash="b" * 64,
        provider_id="deterministic_mock",
        model_descriptor=descriptor,
        inference_configuration=InferenceConfiguration(max_output_tokens=64),
        output_schema_id=APPRENTICE_RESPONSE_SCHEMA_ID,
        output_schema_hash=APPRENTICE_RESPONSE_SCHEMA_HASH,
    )
    reconstructed = InvocationSpec.from_mapping(spec.canonical_value())
    changed = replace(
        spec,
        inference_configuration=replace(
            spec.inference_configuration,
            max_output_tokens=63,
        ),
    )

    assert reconstructed.canonical_json == spec.canonical_json
    assert reconstructed.content_hash == spec.content_hash
    assert changed.content_hash != spec.content_hash


def test_shipped_providers_return_only_deterministic_typed_values() -> None:
    fixture = DeterministicMockFixture(
        fixture_id="determinism_fixture",
        raw_output=b"exact deterministic output",
        declared_encoding="utf-8",
    )
    registry = ProviderRegistry(fixture)
    inactive = registry.resolve("inactive")
    mock = registry.resolve("deterministic_mock")

    assert inactive.invoke(b"input") == ProviderCallResult.inactive()
    assert mock.describe() == mock.describe()
    assert mock.invoke(b"same") == mock.invoke(b"same")
    assert mock.invoke(b"different input").raw_output == fixture.raw_output


def test_closed_provider_registry_exposes_only_shipped_implementations() -> None:
    registry = ProviderRegistry(
        DeterministicMockFixture(
            fixture_id="unit_fixture",
            raw_output=b"{}",
            declared_encoding="utf-8",
        )
    )

    assert registry.provider_ids == ("deterministic_mock", "inactive")
    assert not hasattr(registry, "register")
    with pytest.raises(ValidationError, match="not registered"):
        registry.resolve("external_provider")
    with pytest.raises(TypeError, match="DeterministicMockFixture"):
        ProviderRegistry(object())
    with pytest.raises(TypeError):
        ProviderRegistry(provider=object())  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "field",
    [
        "database_access",
        "filesystem_access",
        "repository_access",
        "shell_access",
        "network_access",
        "credential_access",
        "environment_access",
        "process_access",
        "communication_access",
        "tool_calling",
        "callback_access",
        "executable_capability",
        "clock_access",
        "randomness",
        "streaming",
        "automatic_retry",
    ],
)
def test_provider_capability_profile_fails_closed(field: str) -> None:
    with pytest.raises(ValidationError, match="must remain denied"):
        CapabilityProfile(**{field: True})


@pytest.mark.parametrize(
    "value",
    [
        {"callback": lambda: None},
        {"credentials": {"api_key": "secret"}},
        {"tools": []},
        {"endpoint": "https://example.invalid"},
    ],
)
def test_caller_cannot_inject_capabilities_or_secrets(value: object) -> None:
    with pytest.raises(ValidationError, match="prohibited|callable"):
        reject_executable_or_secret_structure(value)


def test_model_and_inference_contracts_reject_provider_specific_values() -> None:
    with pytest.raises(ValidationError, match="prohibited endpoint"):
        ModelDescriptor(
            model_name="https://example.invalid/model",
            model_revision="revision",
            quantisation=None,
            active_adapter=None,
            context_limit=1024,
        )
    with pytest.raises(ValidationError, match="temperature"):
        InferenceConfiguration(max_output_tokens=8, temperature=0.1)


def test_local_provider_configuration_is_versioned_inactive_and_handle_free() -> None:
    configuration = LocalProviderConfiguration(
        provider_id="deterministic_mock",
        adapter_kind="in_process_mock",
        provider_descriptor_hash="a" * 64,
        model_descriptor_hash="b" * 64,
        denied_capability_profile=CapabilityProfile(),
    )

    assert configuration.canonical_value() == {
        "activation_state": "inactive",
        "adapter_kind": "in_process_mock",
        "contract_version": "1.0.0",
        "denied_capability_profile": CapabilityProfile().canonical_value(),
        "model_descriptor_hash": "b" * 64,
        "provider_descriptor_hash": "a" * 64,
        "provider_id": "deterministic_mock",
    }
    with pytest.raises(ValidationError, match="must remain inactive"):
        replace(configuration, activation_state="active")
    with pytest.raises(TypeError):
        LocalProviderConfiguration(
            **configuration.canonical_value(),
            endpoint="https://example.invalid",
        )



def test_provider_configuration_snapshot_is_exact_and_result_bound() -> None:
    fixture = DeterministicMockFixture(
        fixture_id="snapshot_fixture",
        raw_output=b"exact bytes",
        declared_encoding="utf-8",
        provider_metadata_json=canonical_json_text(
            {"fixture_revision": 1, "labels": ["safe", "bounded"]}
        ),
    )
    snapshot = fixture.configuration_snapshot
    rebuilt = ProviderConfigurationSnapshot.from_mapping(
        snapshot.canonical_value()
    )
    result = ProviderCallResult(
        outcome="output",
        raw_output=b"exact bytes",
        declared_encoding="utf-8",
        failure_code=None,
        provider_metadata_json=fixture.provider_metadata_json,
    )

    assert rebuilt == snapshot
    assert rebuilt.content_hash == fixture.configuration_hash
    assert rebuilt.admits(result)
    assert not rebuilt.admits(replace(result, raw_output=b"changed"))


@pytest.mark.parametrize(
    "metadata",
    [
        {"api_key": "sk-secret"},
        {"nested": {"authorization": "Bearer secret"}},
        {"endpoint": "https://example.invalid"},
        {"artifact": {"model_path": "C:\\models\\unsafe.gguf"}},
        {"callback": "invoke_later"},
        {"safe_name": "Bearer hidden"},
    ],
)
def test_provider_metadata_recursively_rejects_capabilities_and_secrets(
    metadata: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="prohibited provider metadata"):
        DeterministicMockFixture(
            fixture_id="unsafe_metadata",
            raw_output=b"bytes",
            declared_encoding="utf-8",
            provider_metadata_json=canonical_json_text(metadata),
        )

def test_invocation_mapping_is_closed_and_schema_id_is_repository_local() -> None:
    descriptor = ModelDescriptor(
        model_name="fixture/model",
        model_revision="fixture-revision",
        quantisation=None,
        active_adapter=None,
        context_limit=1024,
    )
    spec = InvocationSpec(
        model_invocation_id=uid(1),
        task_id=uid(2),
        session_id=uid(3),
        project_scope_id=uid(4),
        context_package_id=uid(5),
        context_package_hash="a" * 64,
        runtime_identity_id=uid(6),
        runtime_identity_hash="b" * 64,
        provider_id="deterministic_mock",
        model_descriptor=descriptor,
        inference_configuration=InferenceConfiguration(max_output_tokens=64),
        output_schema_id=APPRENTICE_RESPONSE_SCHEMA_ID,
        output_schema_hash=APPRENTICE_RESPONSE_SCHEMA_HASH,
    )

    assert InvocationSpec.from_mapping(spec.canonical_value()) == spec
    bad = {**spec.canonical_value(), "endpoint": "https://example.invalid"}
    with pytest.raises(ValidationError, match="prohibited capability field"):
        InvocationSpec.from_mapping(bad)
    with pytest.raises(ValidationError, match="cannot retry itself"):
        replace(spec, retry_of_invocation_id=spec.model_invocation_id)


def test_closed_schema_registry_requires_exact_id_and_hash() -> None:
    assert (
        resolve_response_schema(
            APPRENTICE_RESPONSE_SCHEMA_ID,
            APPRENTICE_RESPONSE_SCHEMA_HASH,
        ).version
        == "1.0.0"
    )
    assert (
        resolve_schema(MODEL_INPUT_SCHEMA_ID, MODEL_INPUT_SCHEMA_HASH).purpose
        == "model_input"
    )
    with pytest.raises(ValidationError, match="not registered"):
        resolve_response_schema(APPRENTICE_RESPONSE_SCHEMA_ID, "0" * 64)


def test_registered_schema_hashes_match_exact_repository_bytes() -> None:
    root = Path(__file__).resolve().parents[2]
    assert sha256_bytes(
        (
            root
            / "schemas"
            / "protocols"
            / "model-input"
            / "1.0.0.schema.json"
        ).read_bytes()
    ) == MODEL_INPUT_SCHEMA_HASH
    assert sha256_bytes(
        (
            root
            / "schemas"
            / "protocols"
            / "apprentice-response"
            / "1.0.0.schema.json"
        ).read_bytes()
    ) == APPRENTICE_RESPONSE_SCHEMA_HASH


def test_response_validator_reports_stable_missing_unknown_and_type_errors() -> None:
    value = response()
    value.pop("observations")
    value["authority"] = "fabricated"
    value["stop_requested"] = "false"

    issues = validate_apprentice_response(value)

    assert issues == tuple(sorted(issues))
    assert [(issue.path, issue.code) for issue in issues] == [
        ("$.authority", "unknown_field"),
        ("$.observations", "missing_field"),
        ("$.stop_requested", "invalid_type"),
    ]


def test_json_shaped_status_type_failure_is_deterministic_data() -> None:
    value = response()
    value["status"] = ["completed"]

    result = process_raw_output(
        canonical_json_text(value).encode("utf-8"),
        declared_encoding="utf-8",
        task_id=value["task_id"],
        task_section={"task_type": "i4b_bounded_response"},
        allowed_memory_ids=frozenset(),
        allowed_evidence_ids=frozenset(),
    )

    assert result.utf8_decode_status == "decoded"
    assert result.parse_status == "parsed"
    assert result.schema_status == "invalid"
    assert result.semantic_status == "not_attempted"
    assert [(issue.path, issue.code) for issue in result.schema_errors] == [
        ("$.status", "invalid_type"),
    ]


def test_response_schema_rejects_every_prohibited_capability_field() -> None:
    value = response()
    prohibited = (
        "tool",
        "capability",
        "credential",
        "sql",
        "filesystem",
        "repository",
        "shell",
        "network",
        "communication",
        "callback",
        "executable",
    )
    value.update({field: "prohibited" for field in prohibited})

    issues = validate_apprentice_response(value)

    assert {
        (issue.path, issue.code) for issue in issues
    } == {
        (f"$.{field}", "unknown_field") for field in prohibited
    }


def test_strict_utf8_failure_is_total_deterministic_data() -> None:
    result = process_raw_output(
        b"\xff\x00",
        declared_encoding="utf-8",
        task_id=uid(1),
        task_section=task_section(),
        allowed_memory_ids=frozenset(),
        allowed_evidence_ids=frozenset(),
    )

    assert result.utf8_decode_status == "undecodable"
    assert result.decode_errors[0].code == "invalid_utf8"
    assert result.parse_status == "not_attempted"
    assert result.schema_status == "not_attempted"
    assert result.semantic_status == "not_attempted"
    assert not result.successful


def test_malformed_json_and_non_utf8_declaration_are_invalid_data() -> None:
    malformed = process_raw_output(
        b"{",
        declared_encoding="utf-8",
        task_id=uid(1),
        task_section=task_section(),
        allowed_memory_ids=frozenset(),
        allowed_evidence_ids=frozenset(),
    )
    declared = process(response(), declared_encoding="latin-1")

    assert malformed.parse_status == "malformed_json"
    assert malformed.parse_errors[0].code == "malformed_json"
    assert declared.schema_status == "invalid"
    assert declared.schema_errors[0].code == "unsupported_declared_encoding"


def test_semantic_validation_binds_task_sources_and_capability_boundary() -> None:
    value = response(task_id=uid(2))
    value["memory_used"] = [uid(10)]
    value["evidence_used"] = [uid(11)]
    value["inferences"] = ["Run a shell command to read the repository."]

    result = process(
        value,
        allowed_memory_ids=frozenset({uid(12)}),
        allowed_evidence_ids=frozenset({uid(13)}),
    )

    assert result.schema_status == "valid"
    assert result.semantic_status == "invalid"
    assert {issue.code for issue in result.semantic_errors} == {
        "prohibited_capability_request",
        "task_binding_mismatch",
        "unbound_evidence_reference",
        "unbound_memory_reference",
    }


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE escaped_authority (value TEXT);",
        "ALTER TABLE governed_records ADD COLUMN bypass TEXT;",
        "PRAGMA foreign_keys = OFF;",
        "ATTACH DATABASE 'outside.sqlite3' AS outside;",
        "REPLACE INTO tasks VALUES ('fabricated');",
        "SELECT value\nFROM tasks;",
        "VACUUM;",
    ],
)
def test_semantic_validation_rejects_executable_sql_forms(
    statement: str,
) -> None:
    value = response()
    value["inferences"] = [statement]

    result = process(value)

    assert result.semantic_status == "invalid"
    assert {
        issue.code for issue in result.semantic_errors
    } == {"prohibited_capability_request"}


@pytest.mark.parametrize(
    "response_text",
    [
        "Send a message to the operator.",
        "Open a network socket.",
        "Run an executable process.",
        "Send a\nmessage through an external channel.",
        "Read C:\\private\\artifact.dat.",
        "Write /tmp/escaped-output.",
        "Connect to https://example.invalid/model.",
    ],
)
def test_semantic_validation_rejects_textual_capability_requests(
    response_text: str,
) -> None:
    value = response()
    value["recommendations"] = [response_text]

    result = process(
        value,
        task=task_section(
            task_type="i4b_bounded_response_with_recommendations"
        ),
    )

    assert result.semantic_status == "invalid"
    assert {
        issue.code for issue in result.semantic_errors
    } == {"prohibited_capability_request"}


def test_recommendations_require_explicit_task_type() -> None:
    denied = process(response(recommendations=["Review this bounded output."]))
    allowed = process(
        response(recommendations=["Review this bounded output."]),
        task=task_section(
            task_type="i4b_bounded_response_with_recommendations"
        ),
    )

    assert denied.semantic_errors[0].code == "recommendations_not_authorized"
    assert allowed.successful


def test_task_completion_meaning_does_not_bypass_human_review() -> None:
    completed = response()

    assert task_completion_disposition(
        task_section=task_section(task_type="i4b_bounded_response"),
        response_value=completed,
    ) == "completed"
    assert task_completion_disposition(
        task_section=task_section(
            task_type="i4b_bounded_response_human_review"
        ),
        response_value=completed,
    ) == "deferred_human_review"
    assert task_completion_disposition(
        task_section=task_section(task_type="governed_analysis"),
        response_value=completed,
    ) == "not_applicable"


def test_stop_request_is_deterministic_semantic_failure_data() -> None:
    value = response()
    value["stop_requested"] = True
    value["stop_reason"] = "Provider content requests a stop."

    result = process(value)

    assert result.schema_status == "valid"
    assert result.semantic_status == "invalid"
    assert [(issue.path, issue.code) for issue in result.semantic_errors] == [
        ("$.stop_requested", "stop_request_not_permitted"),
    ]
    assert not result.successful


def test_valid_processing_is_exact_and_repair_is_never_attempted() -> None:
    raw = canonical_json_text(response()).encode("utf-8")
    result = process_raw_output(
        raw,
        declared_encoding="utf-8",
        task_id=uid(1),
        task_section=task_section(),
        allowed_memory_ids=frozenset(),
        allowed_evidence_ids=frozenset(),
    )

    assert result.successful
    assert result.decoded_text == raw.decode("utf-8")
    assert result.repair_attempted is False
    assert result.repair_succeeded is False
