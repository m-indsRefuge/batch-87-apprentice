from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import (
    ConflictError,
    IntegrityInspectionError,
    NotFoundError,
    ValidationError,
)
from batch87_apprentice.common.hashing import (
    sha256_bytes,
    sha256_canonical_json,
)
from batch87_apprentice.context.retrieval import ContextRetrievalService
from batch87_apprentice.invocation import (
    InvocationBridge,
    InvocationInterrupted,
)
from batch87_apprentice.invocation.contracts import TerminalFinalizationResult
from batch87_apprentice.invocation.integrity import InvocationIntegrityInspector
from batch87_apprentice.invocation.processing import process_raw_output
import batch87_apprentice.invocation.service as invocation_service_module
from batch87_apprentice.invocation.store import InvocationStore
from batch87_apprentice.persistence.transactions import PersistenceKernel
from batch87_apprentice.providers import (
    DeterministicMockFixture,
    DeterministicMockProvider,
    InactiveProvider,
    ProviderCallResult,
    ProviderRegistry,
)
from tests.support.i2_fixtures import NOW, IdentifierSequence, uid
from tests.support.i2_fixtures import LATER
from batch87_apprentice.runtime import GovernedTaskRuntime
from batch87_apprentice.memory.self_episodic_repository import (
    SelfEpisodicMemoryRepository,
)
from tests.support.i4b_fixtures import (
    I4BHarness,
    bridge_for,
    build_additional_i4b_task,
    build_i4b_harness,
    invocation_spec,
    valid_response_bytes,
)
from tests.support.sql_probe import SqlProbe

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def harness(tmp_path: Path) -> I4BHarness:
    return build_i4b_harness(tmp_path)


def counts(harness: I4BHarness) -> dict[str, int]:
    tables = (
        "model_invocations",
        "model_invocation_state_transitions",
        "model_raw_outputs",
        "model_outputs",
    )
    return SqlProbe(harness.config).read(
        lambda connection: {
            table: connection.execute(
                f"SELECT count(*) FROM {table}"  # noqa: S608
            ).fetchone()[0]
            for table in tables
        }
    )


def task_status(harness: I4BHarness) -> str:
    return harness.i4a.runtime.reconstruct(harness.task_id).value["task_status"]


def reconstruct_in_fresh_process(
    harness: I4BHarness,
    model_invocation_id: str,
) -> tuple[str, str, str]:
    script = (
        "from pathlib import Path;"
        "from batch87_apprentice.persistence.config import DatabaseConfig;"
        "from batch87_apprentice.invocation import InvocationBridge;"
        f"r=InvocationBridge(DatabaseConfig(Path({str(harness.config.path)!r})))"
        f".reconstruct({model_invocation_id!r});"
        "print(r.content_hash);"
        "print(r.value['invocation']['current_status']);"
        "print((r.raw_output_bytes or b'').hex())"
    )
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
        check=True,
        capture_output=True,
        text=True,
    )
    content_hash, status, raw_hex = completed.stdout.splitlines()
    return content_hash, status, raw_hex


def test_success_commits_exact_raw_output_then_completes_bounded_task(
    harness: I4BHarness,
) -> None:
    raw = valid_response_bytes(harness.task_id)
    spec = invocation_spec(harness)
    result = bridge_for(harness, raw_output=raw).invoke(spec)

    assert result.raw_output_bytes == raw
    assert result.value["invocation"]["current_status"] == "succeeded"
    assert result.value["invocation"]["task_disposition"] == "completed"
    assert [
        transition["to_status"]
        for transition in result.value["state_transitions"]
    ] == ["prepared", "in_progress", "raw_output_captured", "succeeded"]
    assert result.value["raw_output_capture"]["raw_byte_length"] == len(raw)
    assert result.value["raw_output_capture"]["raw_output_sha256"] == (
        sha256_bytes(raw)
    )
    assert result.value["raw_output_capture"]["declared_encoding"] == "utf-8"
    raw_storage_type = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT typeof(raw_bytes)
            FROM model_raw_outputs
            WHERE model_invocation_id = ?
            """,
            (spec.model_invocation_id,),
        ).fetchone()[0]
    )
    assert raw_storage_type == "blob"
    assert result.value["captured_provider_result"] == (
        result.value["invocation"]["provider_result"]
    )
    assert result.value["model_output"]["processing"]["utf8_decode_status"] == (
        "decoded"
    )
    assert result.value["model_output"]["processing"]["schema_status"] == "valid"
    assert result.value["model_output"]["processing"]["semantic_status"] == "valid"
    assert result.value["anchor"]["lifecycle_state"] == "claimed"
    packet = result.value["invocation"]["model_input_packet"]
    request = result.value["invocation"]["request"]
    assert sha256_bytes(canonical_json_text(packet).encode("utf-8")) == (
        result.value["invocation"]["model_input_packet_hash"]
    )
    assert sha256_canonical_json(request) == (
        result.value["invocation"]["request_hash"]
    )
    assert packet["invocation"]["context_package_id"] == (
        harness.context_package_id
    )
    assert packet["invocation"]["context_package_hash"] == (
        harness.context_package_hash
    )
    assert task_status(harness) == "completed"
    assert counts(harness) == {
        "model_invocations": 1,
        "model_invocation_state_transitions": 4,
        "model_raw_outputs": 1,
        "model_outputs": 1,
    }
    assert harness.i4a.persistence.integrity.inspect().ok
    assert harness.i4a.persistence.model_invocation_integrity.inspect().ok


def test_processing_observes_a_separately_committed_exact_raw_capture(
    harness: I4BHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = valid_response_bytes(harness.task_id)
    original = invocation_service_module.process_raw_output
    observed: list[tuple[str, bytes, int]] = []

    def inspected(raw_bytes, **kwargs):
        durable = SqlProbe(harness.config).read(
            lambda connection: connection.execute(
                """
                SELECT invocation.current_status, raw.raw_bytes,
                       raw.raw_byte_length
                FROM model_invocations AS invocation
                JOIN model_raw_outputs AS raw
                  ON raw.model_invocation_id = invocation.model_invocation_id
                """
            ).fetchone()
        )
        observed.append(
            (
                durable["current_status"],
                bytes(durable["raw_bytes"]),
                durable["raw_byte_length"],
            )
        )
        return original(raw_bytes, **kwargs)

    monkeypatch.setattr(
        invocation_service_module,
        "process_raw_output",
        inspected,
    )
    result = bridge_for(harness, raw_output=raw).invoke(
        invocation_spec(harness)
    )

    assert observed == [("raw_output_captured", raw, len(raw))]
    assert result.value["invocation"]["current_status"] == "succeeded"


def test_same_invocation_is_idempotently_reconstructed_without_provider_call(
    harness: I4BHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = bridge_for(harness)
    spec = invocation_spec(harness)
    first = bridge.invoke(spec)

    def forbidden_call(self, canonical_input_bytes):  # pragma: no cover
        raise AssertionError("duplicate invocation called provider")

    monkeypatch.setattr(DeterministicMockProvider, "invoke", forbidden_call)
    second = bridge.invoke(spec)

    assert second.content_hash == first.content_hash
    assert second.raw_output_bytes == first.raw_output_bytes
    assert counts(harness)["model_invocations"] == 1
    content_hash, status, raw_hex = reconstruct_in_fresh_process(
        harness,
        spec.model_invocation_id,
    )
    assert (content_hash, status, raw_hex) == (
        first.content_hash,
        "succeeded",
        (first.raw_output_bytes or b"").hex(),
    )


def test_same_invocation_identity_with_different_content_is_conflict(
    harness: I4BHarness,
) -> None:
    bridge = bridge_for(harness)
    spec = invocation_spec(harness)
    bridge.invoke(spec)
    changed = replace(
        spec,
        inference_configuration=replace(
            spec.inference_configuration,
            max_output_tokens=256,
        ),
    )

    with pytest.raises(ConflictError, match="conflicts"):
        bridge.invoke(changed)

    assert counts(harness)["model_invocations"] == 1
    content_hash, status, raw_hex = reconstruct_in_fresh_process(
        harness,
        spec.model_invocation_id,
    )
    original = bridge.reconstruct(spec.model_invocation_id)
    assert (content_hash, status, raw_hex) == (
        original.content_hash,
        "succeeded",
        (original.raw_output_bytes or b"").hex(),
    )


@pytest.mark.parametrize(
    ("raw", "decode_status", "parse_status"),
    [
        (b"\xff\x00", "undecodable", "not_attempted"),
        (b"{", "decoded", "malformed_json"),
    ],
)
def test_malformed_output_is_preserved_and_never_succeeds(
    tmp_path: Path,
    raw: bytes,
    decode_status: str,
    parse_status: str,
) -> None:
    harness = build_i4b_harness(tmp_path)
    result = bridge_for(harness, raw_output=raw).invoke(
        invocation_spec(harness)
    )

    assert result.raw_output_bytes == raw
    assert result.value["invocation"]["current_status"] == "invalid_response"
    processing = result.value["model_output"]["processing"]
    assert processing["utf8_decode_status"] == decode_status
    assert processing["parse_status"] == parse_status
    assert task_status(harness) == "failed"


def test_zero_length_and_nul_output_are_durable_exact_evidence(
    tmp_path: Path,
) -> None:
    for offset, raw in enumerate((b"", b'{"value":"\\u0000"}\x00')):
        harness = build_i4b_harness(tmp_path / str(offset), base=2_300_000 + offset * 50_000)
        result = bridge_for(
            harness,
            raw_output=raw,
            identifier_start=2_390_000 + offset * 100,
        ).invoke(invocation_spec(harness, number=2_380_000 + offset))

        assert result.raw_output_bytes == raw
        assert result.value["raw_output_capture"]["raw_byte_length"] == len(raw)
        assert result.value["invocation"]["current_status"] == "invalid_response"


@pytest.mark.parametrize(
    ("raw_factory", "declared_encoding", "expected_code"),
    [
        (
            lambda task_id: b'{"unknown":"field"}',
            "utf-8",
            "missing_field",
        ),
        (
            valid_response_bytes,
            "latin-1",
            "unsupported_declared_encoding",
        ),
    ],
)
def test_schema_invalid_and_non_utf8_declared_output_remain_exact_evidence(
    tmp_path: Path,
    raw_factory,
    declared_encoding: str,
    expected_code: str,
) -> None:
    harness = build_i4b_harness(tmp_path)
    raw = raw_factory(harness.task_id)
    result = bridge_for(
        harness,
        raw_output=raw,
        declared_encoding=declared_encoding,
    ).invoke(invocation_spec(harness))

    assert result.raw_output_bytes == raw
    assert result.value["raw_output_capture"]["declared_encoding"] == (
        declared_encoding
    )
    assert result.value["invocation"]["current_status"] == "invalid_response"
    processing = result.value["model_output"]["processing"]
    assert processing["schema_status"] == "invalid"
    assert expected_code in {
        issue["code"] for issue in processing["schema_errors"]
    }
    assert task_status(harness) == "failed"


@pytest.mark.parametrize("outcome", ["provider_failed", "timed_out"])
def test_provider_failure_without_output_has_no_raw_or_parsed_record(
    tmp_path: Path,
    outcome: str,
) -> None:
    harness = build_i4b_harness(tmp_path)
    result = bridge_for(
        harness,
        raw_output=None,
        declared_encoding=None,
        outcome=outcome,
        failure_code=f"fixture_{outcome}",
    ).invoke(invocation_spec(harness))

    assert result.value["invocation"]["current_status"] == outcome
    assert result.raw_output_bytes is None
    assert result.value["raw_output_capture"] is None
    assert result.value["model_output"] is None
    assert task_status(harness) == "failed"


def test_failure_with_output_captures_and_processes_bytes_before_failure(
    harness: I4BHarness,
) -> None:
    raw = valid_response_bytes(harness.task_id)
    result = bridge_for(
        harness,
        raw_output=raw,
        outcome="provider_failed",
        failure_code="fixture_failure",
    ).invoke(invocation_spec(harness))

    assert result.value["invocation"]["current_status"] == "provider_failed"
    assert result.raw_output_bytes == raw
    assert result.value["model_output"]["processing"]["schema_status"] == "valid"
    assert task_status(harness) == "failed"


@pytest.mark.parametrize(
    ("provider_behavior", "expected_failure"),
    [
        ("raises", "provider_exception"),
        ("malformed_result", "malformed_provider_result"),
    ],
)
def test_provider_exception_and_malformed_result_become_typed_failures(
    harness: I4BHarness,
    monkeypatch: pytest.MonkeyPatch,
    provider_behavior: str,
    expected_failure: str,
) -> None:
    if provider_behavior == "raises":
        def replacement(self, canonical_input_bytes):
            raise RuntimeError("fixture provider failure")
    else:
        def replacement(self, canonical_input_bytes):
            return object()

    monkeypatch.setattr(DeterministicMockProvider, "invoke", replacement)
    result = bridge_for(harness).invoke(invocation_spec(harness))

    assert result.value["invocation"]["current_status"] == "provider_failed"
    assert result.value["invocation"]["failure_classification"] == (
        expected_failure
    )
    assert result.value["invocation"]["provider_result"]["failure_code"] == (
        expected_failure
    )
    assert result.raw_output_bytes is None
    assert result.value["model_output"] is None
    assert task_status(harness) == "failed"


def test_malformed_initial_provider_descriptor_blocks_before_preparation(
    harness: I4BHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = bridge_for(harness)
    monkeypatch.setattr(
        DeterministicMockProvider,
        "describe",
        lambda self: object(),
    )

    with pytest.raises(ValidationError, match="malformed descriptor"):
        bridge.invoke(invocation_spec(harness))
    assert counts(harness)["model_invocations"] == 0


def test_provider_descriptor_drift_after_call_becomes_typed_failure(
    harness: I4BHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = DeterministicMockProvider.describe
    calls = 0

    def changing(self):
        nonlocal calls
        calls += 1
        descriptor = original(self)
        if calls <= 2:
            return descriptor
        return replace(
            descriptor,
            provider_name="deterministic_mock_changed",
        )

    monkeypatch.setattr(DeterministicMockProvider, "describe", changing)
    result = bridge_for(harness).invoke(invocation_spec(harness))

    assert result.value["invocation"]["current_status"] == "provider_failed"
    assert result.value["invocation"]["failure_classification"] == (
        "provider_descriptor_changed"
    )
    assert result.raw_output_bytes == valid_response_bytes(harness.task_id)
    assert result.value["captured_provider_result"]["outcome"] == "output"
    assert result.value["model_output"] is not None
    assert task_status(harness) == "failed"



def test_provider_descriptor_exception_after_call_preserves_exact_returned_bytes(
    harness: I4BHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = DeterministicMockProvider.describe
    calls = 0

    def failing_after_call(self):
        nonlocal calls
        calls += 1
        if calls <= 2:
            return original(self)
        raise RuntimeError("post-call descriptor failure")

    monkeypatch.setattr(DeterministicMockProvider, "describe", failing_after_call)
    result = bridge_for(harness).invoke(invocation_spec(harness))

    assert result.value["invocation"]["current_status"] == "provider_failed"
    assert result.value["invocation"]["failure_classification"] == (
        "provider_descriptor_failure"
    )
    assert result.raw_output_bytes == valid_response_bytes(harness.task_id)
    assert result.value["captured_provider_result"]["outcome"] == "output"
    assert result.value["model_output"] is not None
    assert task_status(harness) == "failed"


def test_provider_configuration_snapshot_is_persisted_and_reconstructable(
    harness: I4BHarness,
) -> None:
    result = bridge_for(harness).invoke(invocation_spec(harness))
    configuration = result.value["invocation"]["provider_configuration"]

    assert configuration["fixture_id"] == "i4b_fixture"
    assert configuration["configured_outcome"] == "output"
    assert configuration["expected_raw_byte_length"] == len(
        valid_response_bytes(harness.task_id)
    )
    assert configuration["expected_raw_sha256"] == sha256_bytes(
        valid_response_bytes(harness.task_id)
    )
    assert sha256_canonical_json(configuration) == (
        result.value["invocation"]["provider_configuration_hash"]
    )


def test_raw_bearing_provider_result_cannot_finalize_without_capture(
    harness: I4BHarness,
) -> None:
    fixture = DeterministicMockFixture(
        fixture_id="missing_capture_fixture",
        raw_output=valid_response_bytes(harness.task_id),
        declared_encoding="utf-8",
    )
    provider = ProviderRegistry(fixture).resolve("deterministic_mock")
    spec = invocation_spec(harness)
    store = InvocationStore(harness.config)
    prepared = store.prepare(
        spec,
        provider.describe(),
        prepared_at=NOW,
        initial_transition_id=uid(2_725_000),
        runtime_principal="codex_development_harness",
    ).prepared
    assert prepared is not None
    store.call_start(
        prepared,
        started_at=NOW,
        provider_call_attempt_id=uid(2_725_001),
        transition_id=uid(2_725_002),
        runtime_principal="codex_development_harness",
    )
    provider_result = provider.invoke(
        prepared.request.model_input_packet.canonical_bytes
    )

    with pytest.raises(ValidationError, match="requires exact raw capture"):
        store.finalize(
            prepared,
            provider_result=provider_result,
            raw_capture=None,
            failure_classification="provider_failed",
            finalized_at=LATER,
            invocation_transition_id=uid(2_725_003),
            model_output_id=uid(2_725_004),
            task_transition_id=uid(2_725_005),
            runtime_principal="codex_development_harness",
        )


def test_consistently_rehashed_derived_output_still_fails_raw_rederivation(
    harness: I4BHarness,
) -> None:
    bridge = bridge_for(harness)
    spec = invocation_spec(harness)
    result = bridge.invoke(spec)
    tampered = deepcopy(result.value["model_output"])
    tampered["processing"]["decoded_text"] += " "
    tampered_json = canonical_json_text(tampered)
    tampered_hash = sha256_canonical_json(tampered)

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("model_outputs_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE model_outputs
            SET decoded_text = ?, canonical_json = ?, content_hash = ?
            WHERE model_invocation_id = ?
            """,
            (
                tampered["processing"]["decoded_text"],
                tampered_json,
                tampered_hash,
                spec.model_invocation_id,
            ),
        ),
    )

    with pytest.raises(
        IntegrityInspectionError,
        match="derived model output differs from exact raw evidence",
    ):
        bridge.reconstruct(spec.model_invocation_id)
    assert not harness.i4a.persistence.model_invocation_integrity.inspect().ok


def test_invocation_chronology_rejects_start_before_preparation(
    harness: I4BHarness,
) -> None:
    provider = ProviderRegistry(
        DeterministicMockFixture(
            fixture_id="chronology_fixture",
            raw_output=valid_response_bytes(harness.task_id),
            declared_encoding="utf-8",
        )
    ).resolve("deterministic_mock")
    spec = invocation_spec(harness)
    store = InvocationStore(harness.config)
    prepared = store.prepare(
        spec,
        provider.describe(),
        prepared_at=LATER,
        initial_transition_id=uid(2_726_000),
        runtime_principal="codex_development_harness",
    ).prepared
    assert prepared is not None

    with pytest.raises(ValidationError, match="started_at precedes prepared_at"):
        store.call_start(
            prepared,
            started_at=NOW,
            provider_call_attempt_id=uid(2_726_001),
            transition_id=uid(2_726_002),
            runtime_principal="codex_development_harness",
        )

def test_inactive_provider_is_terminal_without_invoking_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build_i4b_harness(tmp_path, runtime_provider="inactive")

    def forbidden_call(self, canonical_input_bytes):  # pragma: no cover
        raise AssertionError("inactive provider was invoked")

    monkeypatch.setattr(InactiveProvider, "invoke", forbidden_call)
    result = bridge_for(harness).invoke(
        invocation_spec(harness, provider_id="inactive")
    )

    assert result.value["invocation"]["current_status"] == "provider_inactive"
    assert [
        transition["to_status"]
        for transition in result.value["state_transitions"]
    ] == ["prepared", "provider_inactive"]
    assert result.raw_output_bytes is None
    assert task_status(harness) == "failed"


def test_valid_response_cannot_bypass_required_human_review(
    tmp_path: Path,
) -> None:
    harness = build_i4b_harness(
        tmp_path,
        human_review_required=True,
    )
    result = bridge_for(harness).invoke(invocation_spec(harness))

    assert result.value["invocation"]["current_status"] == "succeeded"
    assert result.value["invocation"]["task_disposition"] == (
        "deferred_human_review"
    )
    assert result.value["invocation"]["task_transition_id"] is None
    assert task_status(harness) == "active"


def test_success_without_explicit_response_sufficiency_leaves_task_active(
    tmp_path: Path,
) -> None:
    harness = build_i4b_harness(tmp_path, completion_marker=False)
    result = bridge_for(harness).invoke(invocation_spec(harness))

    assert result.value["invocation"]["current_status"] == "succeeded"
    assert result.value["invocation"]["task_disposition"] == "not_applicable"
    assert task_status(harness) == "active"


def test_provider_stop_request_cannot_choose_an_i2_task_transition(
    tmp_path: Path,
) -> None:
    harness = build_i4b_harness(tmp_path, completion_marker=False)
    raw = valid_response_bytes(
        harness.task_id,
        stop_requested=True,
        stop_reason="Provider content requests a stop.",
    )
    result = bridge_for(harness, raw_output=raw).invoke(
        invocation_spec(harness)
    )

    assert result.value["invocation"]["current_status"] == "invalid_response"
    assert result.value["invocation"]["task_disposition"] == "failed"
    assert result.value["model_output"]["processing"]["semantic_status"] == (
        "invalid"
    )
    assert task_status(harness) == "failed"


def test_model_output_is_not_auto_promoted_to_evidence_memory_or_authority(
    harness: I4BHarness,
) -> None:
    def promotion_counts() -> tuple[int, ...]:
        return SqlProbe(harness.config).read(
            lambda connection: (
                connection.execute(
                    "SELECT count(*) FROM evidence_items"
                ).fetchone()[0],
                connection.execute(
                    """
                    SELECT count(*)
                    FROM records AS record
                    WHERE EXISTS (
                        SELECT 1
                        FROM memory_record_types AS type
                        WHERE type.record_family = record.record_family
                          AND type.record_type = record.record_type
                    )
                    """
                ).fetchone()[0],
                connection.execute(
                    "SELECT count(*) FROM memory_eligibility_assessments"
                ).fetchone()[0],
                connection.execute(
                    "SELECT count(*) FROM memory_approval_grants"
                ).fetchone()[0],
                connection.execute(
                    "SELECT count(*) FROM human_approvals"
                ).fetchone()[0],
                connection.execute(
                    "SELECT count(*) FROM capability_observation_evaluations"
                ).fetchone()[0],
                connection.execute(
                    "SELECT count(*) FROM maturity_state_basis_evaluations"
                ).fetchone()[0],
                connection.execute(
                    "SELECT count(*) FROM lesson_candidates"
                ).fetchone()[0],
            )
        )

    before = promotion_counts()
    result = bridge_for(harness).invoke(invocation_spec(harness))
    after = promotion_counts()

    assert result.value["invocation"]["current_status"] == "succeeded"
    assert before == after
    assert result.value["model_output"] is not None
    assert result.value["model_output"]["processing"]["semantic_status"] == (
        "valid"
    )


def test_recommendation_permission_is_deterministic_task_contract_data(
    tmp_path: Path,
) -> None:
    denied_harness = build_i4b_harness(tmp_path / "denied")
    denied_raw = valid_response_bytes(
        denied_harness.task_id,
        recommendations=("Review the bounded result.",),
    )
    denied = bridge_for(denied_harness, raw_output=denied_raw).invoke(
        invocation_spec(denied_harness)
    )
    allowed_harness = build_i4b_harness(
        tmp_path / "allowed",
        base=2_500_000,
        recommendations_allowed=True,
    )
    allowed_raw = valid_response_bytes(
        allowed_harness.task_id,
        recommendations=("Review the bounded result.",),
    )
    allowed = bridge_for(
        allowed_harness,
        raw_output=allowed_raw,
        identifier_start=2_590_000,
    ).invoke(invocation_spec(allowed_harness, number=2_580_000))

    assert denied.value["invocation"]["current_status"] == "invalid_response"
    assert allowed.value["invocation"]["current_status"] == "succeeded"


@pytest.mark.parametrize(
    "condition",
    [
        "integrity_invalid",
        "rejected",
        "contaminated",
        "historically_not_ready",
        "currently_not_ready",
    ],
)
def test_i4a_rejection_conditions_block_before_provider_or_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    condition: str,
) -> None:
    harness = build_i4b_harness(tmp_path)
    original_package = ContextRetrievalService.reconstruct_context_package
    original_readiness = ContextRetrievalService.assess_context_readiness

    if condition == "currently_not_ready":
        def readiness(self, context_package_id, evaluated_at):
            value = deepcopy(
                original_readiness(self, context_package_id, evaluated_at)
            )
            value["current_bridge_context_ready"] = False
            return value

        monkeypatch.setattr(
            ContextRetrievalService,
            "assess_context_readiness",
            readiness,
        )
    else:
        def package(self, context_package_id):
            value = deepcopy(original_package(self, context_package_id))
            if condition == "integrity_invalid":
                value["integrity_verified"] = False
            elif condition == "rejected":
                value["value"]["status"] = "rejected"
            elif condition == "contaminated":
                value["value"]["contamination_status"] = "contaminated"
            else:
                value["value"]["bridge_context_ready"] = False
            return value

        monkeypatch.setattr(
            ContextRetrievalService,
            "reconstruct_context_package",
            package,
        )

    def forbidden_call(self, canonical_input_bytes):  # pragma: no cover
        raise AssertionError("invalid I4-A package reached provider")

    monkeypatch.setattr(DeterministicMockProvider, "invoke", forbidden_call)
    with pytest.raises(ValidationError):
        bridge_for(harness).invoke(invocation_spec(harness))

    assert counts(harness) == {
        "model_invocations": 0,
        "model_invocation_state_transitions": 0,
        "model_raw_outputs": 0,
        "model_outputs": 0,
    }


@pytest.mark.parametrize(
    "drift",
    [
        "missing_context",
        "context_hash",
        "task",
        "session",
        "project",
        "missing_identity",
        "identity_hash",
        "provider",
        "model",
        "unknown_schema",
        "schema_hash",
    ],
)
def test_identity_scope_schema_and_binding_drift_blocks_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    harness = build_i4b_harness(tmp_path)
    spec = invocation_spec(harness)
    if drift == "missing_context":
        spec = replace(spec, context_package_id=uid(2_590_001))
    elif drift == "context_hash":
        spec = replace(spec, context_package_hash="0" * 64)
    elif drift == "task":
        spec = replace(spec, task_id=uid(2_590_002))
    elif drift == "session":
        spec = replace(spec, session_id=uid(2_590_003))
    elif drift == "project":
        spec = replace(spec, project_scope_id=uid(2_590_004))
    elif drift == "missing_identity":
        spec = replace(spec, runtime_identity_id=uid(2_590_005))
    elif drift == "identity_hash":
        spec = replace(spec, runtime_identity_hash="0" * 64)
    elif drift == "provider":
        spec = replace(spec, provider_id="inactive")
    elif drift == "model":
        spec = replace(
            spec,
            model_descriptor=replace(
                spec.model_descriptor,
                model_revision="different-revision",
            ),
        )
    elif drift == "unknown_schema":
        spec = replace(
            spec,
            output_schema_id="https://batch87.local/schemas/unknown/1.0.0",
            output_schema_hash="0" * 64,
        )
    else:
        spec = replace(spec, output_schema_hash="0" * 64)

    def forbidden_call(self, canonical_input_bytes):  # pragma: no cover
        raise AssertionError("invalid binding reached provider")

    monkeypatch.setattr(DeterministicMockProvider, "invoke", forbidden_call)
    with pytest.raises((ValidationError, NotFoundError)):
        bridge_for(harness).invoke(spec)

    assert counts(harness) == {
        "model_invocations": 0,
        "model_invocation_state_transitions": 0,
        "model_raw_outputs": 0,
        "model_outputs": 0,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("lifecycle_state", "retired"),
        ("approval_status", "revoked"),
        ("integrity_status", "invalid"),
    ],
)
def test_non_current_runtime_identity_blocks_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    harness = build_i4b_harness(tmp_path)
    original = SelfEpisodicMemoryRepository.reconstruct

    def identity(self, record_id):
        reconstructed = deepcopy(original(self, record_id))
        reconstructed["record"][field] = value
        return reconstructed

    def forbidden_call(self, canonical_input_bytes):  # pragma: no cover
        raise AssertionError("non-current identity reached provider")

    monkeypatch.setattr(SelfEpisodicMemoryRepository, "reconstruct", identity)
    monkeypatch.setattr(DeterministicMockProvider, "invoke", forbidden_call)
    with pytest.raises(ValidationError, match="not current"):
        bridge_for(harness).invoke(invocation_spec(harness))
    assert counts(harness)["model_invocations"] == 0


def test_real_session_drift_blocks_before_provider(
    harness: I4BHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    later_runtime = GovernedTaskRuntime(
        harness.config,
        runtime_instance_id=harness.i4a.c3.c2.c1.i2.runtime_id,
        clock=lambda: LATER,
        identifier_factory=IdentifierSequence(2_594_000),
    )
    later_runtime.transition_session(
        harness.session_id,
        to_status="closed",
        reason_code="operator_close_before_invocation",
    )

    def forbidden_call(self, canonical_input_bytes):  # pragma: no cover
        raise AssertionError("stale session reached provider")

    monkeypatch.setattr(DeterministicMockProvider, "invoke", forbidden_call)
    with pytest.raises(ValidationError, match="not currently bridge-ready"):
        bridge_for(harness).invoke(invocation_spec(harness))
    assert counts(harness)["model_invocations"] == 0


@pytest.mark.parametrize(
    "failure_step",
    [
        "after_anchor_registration",
        "after_invocation_insert",
        "after_anchor_claim",
        "after_prepared_transition",
    ],
)
def test_every_persistent_preparation_step_rolls_back_atomically(
    tmp_path: Path,
    failure_step: str,
) -> None:
    harness = build_i4b_harness(tmp_path)
    spec = invocation_spec(harness)
    registry = ProviderRegistry(
        DeterministicMockFixture(
            fixture_id="preparation_rollback",
            raw_output=valid_response_bytes(harness.task_id),
            declared_encoding="utf-8",
        )
    )
    store = InvocationStore(harness.config)

    with pytest.raises(RuntimeError, match="injected preparation failure"):
        store.prepare(
            spec,
            registry.resolve("deterministic_mock").describe(),
            prepared_at=LATER,
            initial_transition_id=uid(2_595_000),
            runtime_principal="codex_development_harness",
            fail_after_step=failure_step,
        )

    assert counts(harness) == {
        "model_invocations": 0,
        "model_invocation_state_transitions": 0,
        "model_raw_outputs": 0,
        "model_outputs": 0,
    }
    anchor_count = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT count(*)
            FROM governed_reference_anchors
            WHERE reference_id = ?
            """,
            (spec.model_invocation_id,),
        ).fetchone()[0]
    )
    assert anchor_count == 0
    assert task_status(harness) == "active"


def test_invalid_provider_call_attempt_identity_fails_before_state_change(
    tmp_path: Path,
) -> None:
    harness = build_i4b_harness(tmp_path)
    spec = invocation_spec(harness)
    registry = ProviderRegistry(
        DeterministicMockFixture(
            fixture_id="invalid_call_attempt_identity",
            raw_output=valid_response_bytes(harness.task_id),
            declared_encoding="utf-8",
        )
    )
    store = InvocationStore(harness.config)
    outcome = store.prepare(
        spec,
        registry.resolve("deterministic_mock").describe(),
        prepared_at=LATER,
        initial_transition_id=uid(2_595_100),
        runtime_principal="codex_development_harness",
    )
    assert outcome.prepared is not None

    with pytest.raises(ValidationError, match="provider_call_attempt_id"):
        store.call_start(
            outcome.prepared,
            started_at=LATER,
            provider_call_attempt_id="not-an-identifier",
            transition_id=uid(2_595_101),
            runtime_principal="codex_development_harness",
        )

    reconstructed = store.reconstruct(spec.model_invocation_id)
    assert reconstructed.value["invocation"]["current_status"] == "prepared"
    assert len(reconstructed.value["state_transitions"]) == 1
    assert counts(harness)["model_raw_outputs"] == 0
    assert counts(harness)["model_outputs"] == 0
    assert task_status(harness) == "active"


@pytest.mark.parametrize(
    "failure_step",
    [
        "before_raw_insert",
        "after_raw_insert",
        "after_raw_transition",
        "after_raw_projection",
    ],
)
def test_every_raw_capture_step_rolls_back_without_processing_or_retry(
    tmp_path: Path,
    failure_step: str,
) -> None:
    harness = build_i4b_harness(tmp_path)
    spec = invocation_spec(harness)
    fixture = DeterministicMockFixture(
        fixture_id="raw_capture_rollback",
        raw_output=valid_response_bytes(harness.task_id),
        declared_encoding="utf-8",
    )
    registry = ProviderRegistry(fixture)
    provider = registry.resolve("deterministic_mock")
    store = InvocationStore(harness.config)
    prepared = store.prepare(
        spec,
        provider.describe(),
        prepared_at=LATER,
        initial_transition_id=uid(2_596_000),
        runtime_principal="codex_development_harness",
    ).prepared
    assert prepared is not None
    provider_call_attempt_id = uid(2_596_001)
    store.call_start(
        prepared,
        started_at=LATER,
        provider_call_attempt_id=provider_call_attempt_id,
        transition_id=uid(2_596_002),
        runtime_principal="codex_development_harness",
    )
    provider_result = provider.invoke(
        prepared.request.model_input_packet.canonical_bytes
    )

    with pytest.raises(RuntimeError, match="injected raw-capture"):
        store.capture_raw_output(
            model_invocation_id=spec.model_invocation_id,
            provider_call_attempt_id=provider_call_attempt_id,
            provider_result=provider_result,
            raw_output_id=uid(2_596_003),
            captured_at=LATER,
            transition_id=uid(2_596_004),
            runtime_principal="codex_development_harness",
            fail_after_step=failure_step,
        )

    reconstructed = store.reconstruct(spec.model_invocation_id)
    assert reconstructed.value["invocation"]["current_status"] == "in_progress"
    assert reconstructed.value["raw_output_capture"] is None
    assert reconstructed.value["model_output"] is None
    assert counts(harness) == {
        "model_invocations": 1,
        "model_invocation_state_transitions": 2,
        "model_raw_outputs": 0,
        "model_outputs": 0,
    }
    assert task_status(harness) == "active"


@pytest.mark.parametrize(
    ("point", "expected_status"),
    [
        ("before_provider_return", "in_progress"),
        ("after_provider_return_before_raw_capture", "in_progress"),
        ("during_raw_capture", "in_progress"),
        ("after_raw_capture_before_decoding", "raw_output_captured"),
        ("during_parsing_or_validation", "raw_output_captured"),
        ("after_validation_before_terminal_finalization", "raw_output_captured"),
        ("during_terminal_finalization", "raw_output_captured"),
        (
            "after_terminal_finalization_before_acknowledgement",
            "succeeded",
        ),
    ],
)
def test_interruption_seams_preserve_visible_non_success_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    point: str,
    expected_status: str,
) -> None:
    base = 2_600_000 + list(
        (
            "before_provider_return",
            "after_provider_return_before_raw_capture",
            "during_raw_capture",
            "after_raw_capture_before_decoding",
            "during_parsing_or_validation",
            "after_validation_before_terminal_finalization",
            "during_terminal_finalization",
            "after_terminal_finalization_before_acknowledgement",
        )
    ).index(point) * 50_000
    harness = build_i4b_harness(tmp_path, base=base)
    spec = invocation_spec(harness, number=base + 40_000)
    bridge = bridge_for(harness, identifier_start=base + 41_000)
    original = DeterministicMockProvider.invoke
    calls = 0

    def counted(self, canonical_input_bytes):
        nonlocal calls
        calls += 1
        return original(self, canonical_input_bytes)

    monkeypatch.setattr(DeterministicMockProvider, "invoke", counted)

    with pytest.raises(InvocationInterrupted) as raised:
        bridge.invoke(spec, interruption_point=point)

    assert raised.value.point == point
    reconstructed = bridge.reconstruct(spec.model_invocation_id)
    assert reconstructed.value["invocation"]["current_status"] == expected_status
    if expected_status == "in_progress":
        assert reconstructed.value["raw_output_capture"] is None
        assert reconstructed.value["model_output"] is None
    elif expected_status == "raw_output_captured":
        assert reconstructed.raw_output_bytes == valid_response_bytes(
            harness.task_id
        )
        assert reconstructed.value["model_output"] is None
    else:
        assert reconstructed.value["model_output"] is not None
    assert task_status(harness) == (
        "completed" if expected_status == "succeeded" else "active"
    )
    expected_calls = 0 if point == "before_provider_return" else 1
    assert calls == expected_calls
    repeated = bridge.invoke(spec)
    assert repeated.content_hash == reconstructed.content_hash
    assert calls == expected_calls


def test_unexpected_processing_failure_preserves_raw_incomplete_without_retry(
    harness: I4BHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = invocation_spec(harness)
    bridge = bridge_for(harness)

    def fail_processing(*args, **kwargs):
        raise RuntimeError("unexpected processing defect")

    monkeypatch.setattr(
        invocation_service_module,
        "process_raw_output",
        fail_processing,
    )
    with pytest.raises(RuntimeError, match="unexpected processing defect"):
        bridge.invoke(spec)

    reconstructed = bridge.reconstruct(spec.model_invocation_id)
    assert reconstructed.value["invocation"]["current_status"] == (
        "raw_output_captured"
    )
    assert reconstructed.raw_output_bytes == valid_response_bytes(
        harness.task_id
    )
    assert reconstructed.value["model_output"] is None
    assert reconstructed.value["terminal_finalization"] is None
    assert task_status(harness) == "active"

    def forbidden_call(self, canonical_input_bytes):  # pragma: no cover
        raise AssertionError("processing failure triggered retry")

    monkeypatch.setattr(DeterministicMockProvider, "invoke", forbidden_call)
    repeated = bridge_for(harness).invoke(spec)
    assert repeated.content_hash == reconstructed.content_hash


def test_matching_incomplete_duplicate_never_resumes_or_retries(
    harness: I4BHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = bridge_for(harness)
    spec = invocation_spec(harness)
    with pytest.raises(InvocationInterrupted):
        bridge.invoke(
            spec,
            interruption_point="after_raw_capture_before_decoding",
        )

    def forbidden_call(self, canonical_input_bytes):  # pragma: no cover
        raise AssertionError("incomplete duplicate called provider")

    monkeypatch.setattr(DeterministicMockProvider, "invoke", forbidden_call)
    repeated = bridge.invoke(spec)

    assert repeated.value["invocation"]["current_status"] == (
        "raw_output_captured"
    )
    assert task_status(harness) == "active"


@pytest.mark.parametrize(
    ("point", "has_raw_output"),
    [
        ("before_provider_return", False),
        ("after_raw_capture_before_decoding", True),
    ],
)
def test_explicit_interruption_finalization_is_terminal_reconstructable_and_no_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    point: str,
    has_raw_output: bool,
) -> None:
    harness = build_i4b_harness(tmp_path)
    spec = invocation_spec(harness)
    bridge = bridge_for(harness)
    with pytest.raises(InvocationInterrupted):
        bridge.invoke(spec, interruption_point=point)

    def forbidden_call(self, canonical_input_bytes):  # pragma: no cover
        raise AssertionError("interruption finalization called provider")

    monkeypatch.setattr(DeterministicMockProvider, "invoke", forbidden_call)
    finalized = bridge_for(
        harness,
        identifier_start=2_695_000,
    ).mark_interrupted(spec.model_invocation_id)

    assert finalized.value["invocation"]["current_status"] == "interrupted"
    assert finalized.value["invocation"]["failure_classification"] == (
        "runtime_interrupted"
    )
    assert (finalized.raw_output_bytes is not None) is has_raw_output
    assert (
        finalized.value["model_output"] is not None
    ) is has_raw_output
    assert task_status(harness) == "failed"
    repeated = bridge_for(
        harness,
        identifier_start=2_696_000,
    ).mark_interrupted(spec.model_invocation_id)
    assert repeated.content_hash == finalized.content_hash

    script = (
        "from pathlib import Path;"
        "from batch87_apprentice.persistence.config import DatabaseConfig;"
        "from batch87_apprentice.invocation import InvocationBridge;"
        f"r=InvocationBridge(DatabaseConfig(Path({str(harness.config.path)!r})))"
        f".reconstruct({spec.model_invocation_id!r});"
        "print(r.value['invocation']['current_status']);"
        "print((r.raw_output_bytes or b'').hex())"
    )
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.splitlines() == [
        "interrupted",
        (finalized.raw_output_bytes or b"").hex(),
    ]


def test_second_nonterminal_attempt_for_same_task_and_context_is_rejected(
    harness: I4BHarness,
) -> None:
    bridge = bridge_for(harness)
    first = invocation_spec(harness)
    with pytest.raises(InvocationInterrupted):
        bridge.invoke(first, interruption_point="before_provider_return")
    second = invocation_spec(harness, number=2_100_100)

    with pytest.raises(ConflictError, match="retry relationship"):
        bridge.invoke(second)

    assert counts(harness)["model_invocations"] == 1


def test_explicit_retry_uses_new_identity_and_preserves_terminal_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build_i4b_harness(tmp_path, completion_marker=False)
    original = DeterministicMockProvider.invoke
    calls = 0

    def counted(self, canonical_input_bytes):
        nonlocal calls
        calls += 1
        return original(self, canonical_input_bytes)

    monkeypatch.setattr(DeterministicMockProvider, "invoke", counted)
    bridge = bridge_for(harness)
    parent_spec = invocation_spec(harness)
    parent = bridge.invoke(parent_spec)
    retry_spec = invocation_spec(
        harness,
        number=2_699_000,
        retry_of_invocation_id=parent_spec.model_invocation_id,
    )
    retry = bridge_for(
        harness,
        identifier_start=2_699_100,
    ).invoke(retry_spec)

    assert calls == 2
    assert parent.value["invocation"]["current_status"] == "succeeded"
    assert parent.value["invocation"]["task_disposition"] == "not_applicable"
    assert retry.value["invocation"]["current_status"] == "succeeded"
    assert retry.value["invocation"]["retry_of_invocation_id"] == (
        parent_spec.model_invocation_id
    )
    reconstructed_parent = bridge.reconstruct(parent_spec.model_invocation_id)
    assert reconstructed_parent.content_hash == parent.content_hash
    assert task_status(harness) == "active"
    assert counts(harness)["model_invocations"] == 2


def test_concurrent_duplicate_has_one_provider_call_and_one_result(
    harness: I4BHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = DeterministicMockProvider.invoke
    lock = threading.Lock()
    calls = 0

    def counted(self, canonical_input_bytes):
        nonlocal calls
        with lock:
            calls += 1
        return original(self, canonical_input_bytes)

    monkeypatch.setattr(DeterministicMockProvider, "invoke", counted)
    spec = invocation_spec(harness)
    bridges = (
        bridge_for(harness, identifier_start=2_700_000),
        bridge_for(harness, identifier_start=2_710_000),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(lambda bridge: bridge.invoke(spec), bridges)
        )

    assert calls == 1
    assert {
        result.value["invocation"]["current_status"] for result in results
    } <= {"prepared", "in_progress", "raw_output_captured", "succeeded"}
    final = bridges[0].reconstruct(spec.model_invocation_id)
    assert final.value["invocation"]["current_status"] == "succeeded"
    assert counts(harness)["model_invocations"] == 1


def test_concurrent_conflicting_same_identity_admits_one_request_and_one_call(
    harness: I4BHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = DeterministicMockProvider.invoke
    lock = threading.Lock()
    calls = 0

    def counted(self, canonical_input_bytes):
        nonlocal calls
        with lock:
            calls += 1
        return original(self, canonical_input_bytes)

    monkeypatch.setattr(DeterministicMockProvider, "invoke", counted)
    original_spec = invocation_spec(harness)
    conflicting_spec = replace(
        original_spec,
        inference_configuration=replace(
            original_spec.inference_configuration,
            max_output_tokens=256,
        ),
    )
    bridges = (
        bridge_for(harness, identifier_start=2_714_000),
        bridge_for(harness, identifier_start=2_715_000),
    )

    def attempt(arguments):
        bridge, spec = arguments
        try:
            return bridge.invoke(spec)
        except ConflictError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(
                attempt,
                zip(
                    bridges,
                    (original_spec, conflicting_spec),
                    strict=True,
                ),
            )
        )

    assert calls == 1
    assert sum(isinstance(result, ConflictError) for result in results) == 1
    assert counts(harness)["model_invocations"] == 1
    reconstructed = bridges[0].reconstruct(original_spec.model_invocation_id)
    assert reconstructed.value["invocation"]["current_status"] == "succeeded"


def test_concurrent_distinct_tasks_and_contexts_both_complete_without_cross_binding(
    harness: I4BHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    second = build_additional_i4b_task(harness, base=2_716_000)
    original = DeterministicMockProvider.invoke
    lock = threading.Lock()
    calls = 0

    def counted(self, canonical_input_bytes):
        nonlocal calls
        with lock:
            calls += 1
        return original(self, canonical_input_bytes)

    monkeypatch.setattr(DeterministicMockProvider, "invoke", counted)
    first_spec = invocation_spec(harness, number=2_717_000)
    second_spec = invocation_spec(second, number=2_718_000)
    bridges = (
        bridge_for(harness, identifier_start=2_719_000),
        bridge_for(second, identifier_start=2_720_000),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(
                lambda pair: pair[0].invoke(pair[1]),
                zip(bridges, (first_spec, second_spec), strict=True),
            )
        )

    assert calls == 2
    assert {
        result.value["invocation"]["current_status"] for result in results
    } == {"succeeded"}
    assert {
        result.value["invocation"]["task_id"] for result in results
    } == {harness.task_id, second.task_id}
    assert {
        result.value["invocation"]["context_package_id"]
        for result in results
    } == {harness.context_package_id, second.context_package_id}
    assert counts(harness)["model_invocations"] == 2


def test_terminal_finalization_rechecks_current_i4a_readiness(
    harness: I4BHarness,
) -> None:
    raw = valid_response_bytes(harness.task_id)
    fixture = DeterministicMockFixture(
        fixture_id="stale_fixture",
        raw_output=raw,
        declared_encoding="utf-8",
    )
    registry = ProviderRegistry(fixture)
    provider = registry.resolve("deterministic_mock")
    descriptor = provider.describe()
    spec = invocation_spec(harness)
    store = InvocationStore(harness.config)
    prepared = store.prepare(
        spec,
        descriptor,
        prepared_at=NOW,
        initial_transition_id=uid(2_720_000),
        runtime_principal="codex_development_harness",
    ).prepared
    assert prepared is not None
    store.call_start(
        prepared,
        started_at=NOW,
        provider_call_attempt_id=uid(2_720_001),
        transition_id=uid(2_720_002),
        runtime_principal="codex_development_harness",
    )
    provider_result = provider.invoke(
        prepared.request.model_input_packet.canonical_bytes
    )
    capture = store.capture_raw_output(
        model_invocation_id=spec.model_invocation_id,
        provider_call_attempt_id=uid(2_720_001),
        provider_result=provider_result,
        raw_output_id=uid(2_720_003),
        captured_at=NOW,
        transition_id=uid(2_720_004),
        runtime_principal="codex_development_harness",
    )
    processing = process_raw_output(
        capture.raw_bytes,
        declared_encoding=capture.declared_encoding,
        task_id=spec.task_id,
        task_section=prepared.task_section,
        allowed_memory_ids=prepared.allowed_memory_ids,
        allowed_evidence_ids=prepared.allowed_evidence_ids,
    )
    later_runtime = GovernedTaskRuntime(
        harness.config,
        runtime_instance_id=harness.i4a.c3.c2.c1.i2.runtime_id,
        clock=lambda: LATER,
        identifier_factory=IdentifierSequence(2_721_000),
    )
    later_runtime.transition_session(
        harness.session_id,
        to_status="closed",
        reason_code="operator_close_before_finalization",
    )
    result = store.finalize(
        prepared,
        provider_result=provider_result,
        raw_capture=capture,
        failure_classification=None,
        finalized_at=LATER,
        invocation_transition_id=uid(2_720_005),
        model_output_id=uid(2_720_006),
        task_transition_id=uid(2_720_007),
        runtime_principal="codex_development_harness",
    )

    assert result.value["invocation"]["current_status"] == "stale_context"
    assert result.raw_output_bytes == raw
    assert task_status(harness) == "failed"


def test_later_current_staleness_does_not_rewrite_historical_terminal_state(
    harness: I4BHarness,
) -> None:
    bridge = bridge_for(harness)
    spec = invocation_spec(harness)
    completed = bridge.invoke(spec)
    later_runtime = GovernedTaskRuntime(
        harness.config,
        runtime_instance_id=harness.i4a.c3.c2.c1.i2.runtime_id,
        clock=lambda: LATER,
        identifier_factory=IdentifierSequence(2_722_000),
    )
    later_runtime.transition_session(
        harness.session_id,
        to_status="closed",
        reason_code="operator_close_after_invocation",
    )

    reconstructed = bridge.reconstruct(spec.model_invocation_id)
    assert reconstructed.content_hash == completed.content_hash
    assert reconstructed.value["invocation"]["current_status"] == "succeeded"


def test_raw_output_and_terminal_records_reject_direct_mutation(
    harness: I4BHarness,
) -> None:
    result = bridge_for(harness).invoke(invocation_spec(harness))
    invocation_id = result.value["invocation"]["model_invocation_id"]

    with pytest.raises(ConflictError):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                UPDATE model_raw_outputs
                SET raw_bytes = X'00'
                WHERE model_invocation_id = ?
                """,
                (invocation_id,),
            )
        )
    with pytest.raises(ConflictError):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                "DELETE FROM model_outputs WHERE model_invocation_id = ?",
                (invocation_id,),
            )
        )
    for table, identity_column in (
        ("model_invocation_state_transitions", "model_invocation_id"),
        ("model_raw_outputs", "model_invocation_id"),
        ("model_invocations", "model_invocation_id"),
        ("governed_reference_anchors", "reference_id"),
    ):
        with pytest.raises(ConflictError):
            SqlProbe(harness.config).write(
                lambda connection, table=table, identity_column=identity_column: (
                    connection.execute(
                        f"DELETE FROM {table} "  # noqa: S608
                        f"WHERE {identity_column} = ?",  # noqa: S608
                        (invocation_id,),
                    )
                )
            )
    with pytest.raises(ConflictError):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                UPDATE model_invocations
                SET provider_configuration_hash = ?
                WHERE model_invocation_id = ?
                """,
                ("0" * 64, invocation_id),
            )
        )
    with pytest.raises(ConflictError):
        SqlProbe(harness.config).write(
            lambda connection: connection.execute(
                """
                UPDATE model_invocations
                SET current_status = 'provider_failed'
                WHERE model_invocation_id = ?
                """,
                (invocation_id,),
            )
        )


def test_integrity_inspector_detects_exact_raw_byte_corruption(
    harness: I4BHarness,
) -> None:
    result = bridge_for(harness).invoke(invocation_spec(harness))
    invocation_id = result.value["invocation"]["model_invocation_id"]
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("model_raw_outputs_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE model_raw_outputs
            SET raw_bytes = X'00'
            WHERE model_invocation_id = ?
            """,
            (invocation_id,),
        ),
    )

    report = InvocationIntegrityInspector(
        PersistenceKernel(harness.config)
    ).inspect()
    top_level = harness.i4a.persistence.integrity.inspect()

    assert not report.ok
    assert report.findings[0].code == "invocation_reconstruction_invalid"
    assert not top_level.ok
    assert "model_invocation_invocation_reconstruction_invalid" in {
        finding.code for finding in top_level.findings
    }


def test_integrity_detects_invalid_provider_call_identity_without_raw_output(
    tmp_path: Path,
) -> None:
    harness = build_i4b_harness(tmp_path)
    result = bridge_for(
        harness,
        raw_output=None,
        outcome="provider_failed",
        declared_encoding=None,
        failure_code="fixture_failure",
    ).invoke(invocation_spec(harness))
    invocation_id = result.value["invocation"]["model_invocation_id"]
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (
            "model_invocations_terminal_immutable",
            "model_invocations_projection_update_requires_transition",
        ),
        lambda connection: connection.execute(
            """
            UPDATE model_invocations
            SET provider_call_attempt_id = 'not-an-identifier'
            WHERE model_invocation_id = ?
            """,
            (invocation_id,),
        ),
    )

    with pytest.raises(
        IntegrityInspectionError,
        match="provider-call attempt identity",
    ):
        InvocationStore(harness.config).reconstruct(invocation_id)
    dedicated = InvocationIntegrityInspector(
        PersistenceKernel(harness.config)
    ).inspect()
    top_level = harness.i4a.persistence.integrity.inspect()
    assert not dedicated.ok
    assert not top_level.ok
    assert any(
        finding.model_invocation_id == invocation_id
        for finding in dedicated.findings
    )
    assert any(
        finding.object_id == invocation_id
        for finding in top_level.findings
    )


def test_integrity_detects_provider_outcome_terminal_contradiction(
    tmp_path: Path,
) -> None:
    harness = build_i4b_harness(tmp_path)
    result = bridge_for(
        harness,
        raw_output=None,
        outcome="provider_failed",
        declared_encoding=None,
        failure_code="fixture_failure",
    ).invoke(invocation_spec(harness))
    invocation_id = result.value["invocation"]["model_invocation_id"]
    original_terminal = result.value["terminal_finalization"]
    contradictory_provider = ProviderCallResult(
        outcome="timed_out",
        raw_output=None,
        declared_encoding=None,
        failure_code="fixture_timeout",
    )
    contradictory_terminal = TerminalFinalizationResult(
        model_invocation_id=invocation_id,
        terminal_status="provider_failed",
        provider_result_hash=contradictory_provider.content_hash,
        model_output_id=None,
        model_output_hash=None,
        task_disposition=original_terminal["task_disposition"],
        task_transition_id=original_terminal["task_transition_id"],
        failure_classification=original_terminal["failure_classification"],
        finalized_at=original_terminal["finalized_at"],
    )

    def corrupt(connection) -> None:
        connection.execute(
            """
            UPDATE model_invocations
            SET provider_result_outcome = ?,
                provider_result_json = ?,
                provider_result_hash = ?,
                terminal_result_json = ?,
                terminal_result_hash = ?
            WHERE model_invocation_id = ?
            """,
            (
                contradictory_provider.outcome,
                contradictory_provider.canonical_json,
                contradictory_provider.content_hash,
                contradictory_terminal.canonical_json,
                contradictory_terminal.content_hash,
                invocation_id,
            ),
        )

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (
            "model_invocations_terminal_immutable",
            "model_invocations_projection_update_requires_transition",
        ),
        corrupt,
    )

    with pytest.raises(
        IntegrityInspectionError,
        match="provider result outcome contradicts terminal status",
    ):
        InvocationStore(harness.config).reconstruct(invocation_id)
    dedicated = InvocationIntegrityInspector(
        PersistenceKernel(harness.config)
    ).inspect()
    top_level = harness.i4a.persistence.integrity.inspect()
    assert not dedicated.ok
    assert not top_level.ok


def test_integrity_detects_cross_task_retry_parent_tamper(
    tmp_path: Path,
) -> None:
    harness = build_i4b_harness(tmp_path, completion_marker=False)
    parent_spec = invocation_spec(harness, number=2_780_000)
    bridge_for(harness, identifier_start=2_781_000).invoke(parent_spec)
    child_spec = invocation_spec(
        harness,
        number=2_780_001,
        retry_of_invocation_id=parent_spec.model_invocation_id,
    )
    bridge_for(harness, identifier_start=2_782_000).invoke(child_spec)

    other = build_additional_i4b_task(harness, base=2_790_000)
    other_spec = invocation_spec(other, number=2_790_500)
    bridge_for(other, identifier_start=2_791_000).invoke(other_spec)

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        (
            "model_invocations_core_immutable",
            "model_invocations_terminal_immutable",
        ),
        lambda connection: connection.execute(
            """
            UPDATE model_invocations
            SET retry_of_invocation_id = ?
            WHERE model_invocation_id = ?
            """,
            (
                other_spec.model_invocation_id,
                child_spec.model_invocation_id,
            ),
        ),
    )

    dedicated = InvocationIntegrityInspector(
        PersistenceKernel(harness.config)
    ).inspect()
    top_level = harness.i4a.persistence.integrity.inspect()
    assert "retry_parent_invalid" in {
        finding.code
        for finding in dedicated.findings
        if finding.model_invocation_id == child_spec.model_invocation_id
    }
    assert "model_invocation_retry_parent_invalid" in {
        finding.code
        for finding in top_level.findings
        if finding.object_id == child_spec.model_invocation_id
    }


@pytest.mark.parametrize(
    "corruption",
    [
        "raw_length",
        "raw_hash",
        "declared_encoding",
        "derived_output",
        "transition",
        "packet_parent",
        "anchor",
    ],
)
def test_reconstruction_and_both_integrity_layers_detect_i4b_corruption(
    tmp_path: Path,
    corruption: str,
) -> None:
    harness = build_i4b_harness(tmp_path)
    spec = invocation_spec(harness)
    bridge = bridge_for(harness)
    bridge.invoke(spec)
    probe = SqlProbe(harness.config)

    if corruption == "raw_length":
        triggers = ("model_raw_outputs_immutable",)
        statement = (
            "UPDATE model_raw_outputs "
            "SET raw_byte_length = raw_byte_length + 1 "
            "WHERE model_invocation_id = ?"
        )
    elif corruption == "raw_hash":
        triggers = ("model_raw_outputs_immutable",)
        statement = (
            "UPDATE model_raw_outputs SET raw_output_sha256 = "
            f"'{('0' * 64)}' WHERE model_invocation_id = ?"
        )
    elif corruption == "declared_encoding":
        triggers = ("model_raw_outputs_immutable",)
        statement = (
            "UPDATE model_raw_outputs SET declared_encoding = 'latin-1' "
            "WHERE model_invocation_id = ?"
        )
    elif corruption == "derived_output":
        triggers = ("model_outputs_immutable",)
        statement = (
            "UPDATE model_outputs SET decoded_text = decoded_text || 'x' "
            "WHERE model_invocation_id = ?"
        )
    elif corruption == "transition":
        triggers = ("model_invocation_state_transitions_immutable",)
        statement = (
            "UPDATE model_invocation_state_transitions "
            "SET reason_code = 'tampered_reason' "
            "WHERE model_invocation_id = ? AND sequence_number = 1"
        )
    elif corruption == "packet_parent":
        triggers = (
            "model_invocations_core_immutable",
            "model_invocations_terminal_immutable",
        )
        statement = (
            "UPDATE model_invocations SET model_input_packet_hash = "
            f"'{('0' * 64)}' WHERE model_invocation_id = ?"
        )
    else:
        triggers = ("governed_reference_anchor_core_immutable",)
        statement = (
            "UPDATE governed_reference_anchors SET content_hash = "
            f"'{('0' * 64)}' WHERE reference_id = ?"
        )

    probe.corrupt_after_dropping_triggers(
        triggers,
        lambda connection: connection.execute(
            statement,
            (spec.model_invocation_id,),
        ),
    )

    with pytest.raises(IntegrityInspectionError):
        bridge.reconstruct(spec.model_invocation_id)
    dedicated = harness.i4a.persistence.model_invocation_integrity.inspect()
    top_level = harness.i4a.persistence.integrity.inspect()
    assert not dedicated.ok
    assert not top_level.ok
    assert any(
        finding.model_invocation_id == spec.model_invocation_id
        for finding in dedicated.findings
    )
    assert any(
        finding.object_id == spec.model_invocation_id
        for finding in top_level.findings
    )


@pytest.mark.parametrize(
    "case",
    [
        "prepared",
        "raw_captured",
        "success",
        "provider_failure",
        "decode_failure",
        "parse_failure",
        "schema_failure",
        "interrupted",
    ],
)
def test_every_required_lifecycle_class_reconstructs_in_a_fresh_process(
    tmp_path: Path,
    case: str,
) -> None:
    harness = build_i4b_harness(tmp_path)
    spec = invocation_spec(harness)
    bridge = bridge_for(harness)
    if case == "prepared":
        registry = ProviderRegistry(
            DeterministicMockFixture(
                fixture_id="prepared_reconstruction",
                raw_output=valid_response_bytes(harness.task_id),
                declared_encoding="utf-8",
            )
        )
        store = InvocationStore(harness.config)
        outcome = store.prepare(
            spec,
            registry.resolve("deterministic_mock").describe(),
            prepared_at=LATER,
            initial_transition_id=uid(2_800_000),
            runtime_principal="codex_development_harness",
        )
        assert outcome.prepared is not None
        expected = store.reconstruct(spec.model_invocation_id)
    elif case == "raw_captured":
        with pytest.raises(InvocationInterrupted):
            bridge.invoke(
                spec,
                interruption_point="after_raw_capture_before_decoding",
            )
        expected = bridge.reconstruct(spec.model_invocation_id)
    elif case == "success":
        expected = bridge.invoke(spec)
    elif case == "provider_failure":
        expected = bridge_for(
            harness,
            raw_output=None,
            declared_encoding=None,
            outcome="provider_failed",
            failure_code="fixture_provider_failure",
        ).invoke(spec)
    elif case == "decode_failure":
        expected = bridge_for(harness, raw_output=b"\xff").invoke(spec)
    elif case == "parse_failure":
        expected = bridge_for(harness, raw_output=b"{").invoke(spec)
    elif case == "schema_failure":
        expected = bridge_for(
            harness,
            raw_output=b'{"unknown":"field"}',
        ).invoke(spec)
    else:
        with pytest.raises(InvocationInterrupted):
            bridge.invoke(spec, interruption_point="before_provider_return")
        expected = bridge_for(
            harness,
            identifier_start=2_801_000,
        ).mark_interrupted(spec.model_invocation_id)

    content_hash, status, raw_hex = reconstruct_in_fresh_process(
        harness,
        spec.model_invocation_id,
    )
    assert content_hash == expected.content_hash
    assert status == expected.value["invocation"]["current_status"]
    assert raw_hex == (expected.raw_output_bytes or b"").hex()


def test_reconstruction_is_exact_in_a_fresh_python_process(
    harness: I4BHarness,
) -> None:
    spec = invocation_spec(harness)
    expected = bridge_for(harness).invoke(spec)
    script = (
        "from pathlib import Path;"
        "from batch87_apprentice.persistence.config import DatabaseConfig;"
        "from batch87_apprentice.invocation import InvocationBridge;"
        f"r=InvocationBridge(DatabaseConfig(Path({str(harness.config.path)!r})))"
        f".reconstruct({spec.model_invocation_id!r});"
        "print(r.content_hash);"
        "print((r.raw_output_bytes or b'').hex())"
    )
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
        check=True,
        capture_output=True,
        text=True,
    )

    lines = completed.stdout.splitlines()
    assert lines == [
        expected.content_hash,
        (expected.raw_output_bytes or b"").hex(),
    ]
