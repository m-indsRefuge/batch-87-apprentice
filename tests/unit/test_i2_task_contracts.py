from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.governance.contracts import (
    AUTHORITY_CLASS_PRECEDENCE,
    AUTHORITY_SOURCE_BY_CLASS,
    AuthorityRecord,
    active_b87_s1_permission_profile,
)
from batch87_apprentice.protocols.task_contracts import (
    EXECUTION_PRINCIPALS,
    TASK_CONTRACT_SCHEMA_ID,
    TASK_CONTRACT_VERSION,
    RequestedOperation,
    SessionContract,
    TaskContract,
)
from tests.support.i2_fixtures import NOW, uid


def valid_mapping() -> dict[str, object]:
    return {
        "allowed_sources": ["approved_evidence"],
        "authority_grant": ["observe"],
        "claimed_authority_ids": [uid(10)],
        "contract_version": TASK_CONTRACT_VERSION,
        "effective_at": NOW,
        "expected_output_schema_id": "https://batch87.local/output/test",
        "governing_constraints": ["b87_s1_permissions"],
        "objective": "Inspect one fixture.",
        "prohibited_actions": ["execute", "autonomous_action"],
        "project_scope_id": uid(11),
        "provenance": {"source": "unit test"},
        "requested_operation": {
            "action_class": "observe",
            "autonomous": False,
            "name": "inspect_fixture",
        },
        "requested_scope_id": uid(12),
        "requesting_principal": "apprentice",
        "required_evidence_ids": [uid(13)],
        "session_id": uid(14),
        "stop_conditions": ["invalid_authority"],
        "task_id": uid(15),
        "task_type": "governed_analysis",
    }


def test_supported_task_contract_is_canonical_and_stable() -> None:
    first = TaskContract.from_mapping(valid_mapping())
    second = TaskContract.from_mapping(first.canonical_value())

    assert first.contract_version == TASK_CONTRACT_VERSION
    assert first.canonical_json == second.canonical_json
    assert first.content_hash == second.content_hash
    assert json.loads(first.canonical_json) == first.canonical_value()


def test_task_schema_registry_has_one_exact_active_version() -> None:
    root = Path(__file__).resolve().parents[2]
    schema_path = root / "schemas/protocols/task-contract/1.0.0.schema.json"
    schema_bytes = schema_path.read_bytes()
    schema = json.loads(schema_bytes)
    registry = json.loads(
        (root / "schemas/registry.json").read_text(encoding="utf-8")
    )

    assert schema["$id"] == TASK_CONTRACT_SCHEMA_ID
    assert schema["properties"]["contract_version"]["const"] == (
        TASK_CONTRACT_VERSION
    )
    assert set(schema["required"]) == set(valid_mapping())
    assert schema["additionalProperties"] is False
    assert registry == {
        "schemas": [
            {
                "content_hash": hashlib.sha256(schema_bytes).hexdigest(),
                "id": TASK_CONTRACT_SCHEMA_ID,
                "path": "protocols/task-contract/1.0.0.schema.json",
                "status": "active",
                "version": TASK_CONTRACT_VERSION,
            }
        ]
    }


def test_unsupported_task_contract_version_is_rejected() -> None:
    value = valid_mapping()
    value["contract_version"] = "2.0.0"

    with pytest.raises(ValidationError, match="unsupported task contract version"):
        TaskContract.from_mapping(value)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.pop("objective"), "missing=objective"),
        (
            lambda value: value.update({"unapproved_extension": True}),
            "unsupported=unapproved_extension",
        ),
        (lambda value: value.update({"task_id": ""}), "task_id"),
        (
            lambda value: value.update({"authority_grant": "observe"}),
            "JSON array",
        ),
    ],
)
def test_malformed_or_incomplete_task_contract_is_rejected(
    mutation,
    message: str,
) -> None:
    value = valid_mapping()
    mutation(value)

    with pytest.raises(ValidationError, match=message):
        TaskContract.from_mapping(value)


def test_typed_contract_rejects_mutable_sequence_inputs() -> None:
    value = valid_mapping()
    contract = TaskContract.from_mapping(value)

    with pytest.raises(ValidationError, match="immutable tuple"):
        TaskContract(
            contract_version=contract.contract_version,
            task_id=contract.task_id,
            session_id=contract.session_id,
            project_scope_id=contract.project_scope_id,
            requested_scope_id=contract.requested_scope_id,
            objective=contract.objective,
            task_type=contract.task_type,
            requested_operation=contract.requested_operation,
            requesting_principal=contract.requesting_principal,
            authority_grant=["observe"],  # type: ignore[arg-type]
            claimed_authority_ids=contract.claimed_authority_ids,
            effective_at=contract.effective_at,
            governing_constraints=contract.governing_constraints,
            required_evidence_ids=contract.required_evidence_ids,
            allowed_sources=contract.allowed_sources,
            prohibited_actions=contract.prohibited_actions,
            expected_output_schema_id=contract.expected_output_schema_id,
            stop_conditions=contract.stop_conditions,
            provenance_json=contract.provenance_json,
        )


def test_operation_classification_is_explicit_and_consistent() -> None:
    assert RequestedOperation("inspect", "observe").permission_class == "observe"
    assert RequestedOperation("reason", "analyse").permission_class == "analyse"
    assert RequestedOperation("run", "execute", True).permission_class == "execute"

    with pytest.raises(ValidationError, match="autonomous operations"):
        RequestedOperation("inspect", "observe", True)


def test_session_identity_and_participants_are_explicit() -> None:
    session = SessionContract(
        session_id=uid(20),
        purpose="Unit-test session.",
        project_scope_id=uid(21),
        opened_at=NOW,
        created_by_entity_id=uid(22),
        participant_entity_ids=(uid(22), uid(23)),
    )

    assert session.canonical_value()["session_id"] == uid(20)
    assert session.canonical_value()["participant_entity_ids"] == [
        uid(22),
        uid(23),
    ]

    with pytest.raises(ValidationError, match="explicit participant"):
        SessionContract(
            session_id=uid(20),
            purpose="Unit-test session.",
            project_scope_id=uid(21),
            opened_at=NOW,
            created_by_entity_id=uid(22),
            participant_entity_ids=(uid(23),),
        )


def test_execution_principals_are_exact_and_separate() -> None:
    assert EXECUTION_PRINCIPALS == {
        "apprentice",
        "operator",
        "codex_development_harness",
        "experimental_harness",
    }


def test_active_permission_profile_is_exact_and_has_no_tools() -> None:
    profile = active_b87_s1_permission_profile()

    assert profile.principal == "apprentice"
    assert profile.allowed_action_classes == ("observe", "analyse")
    assert set(profile.prohibited_action_classes) == {
        "propose",
        "execute",
        "autonomous_action",
    }
    assert profile.allowed_tools == ()
    assert "autonomous_tool_use" in profile.prohibited_tools


def test_authority_precedence_is_explicit_and_model_source_cannot_self_promote() -> None:
    assert AUTHORITY_CLASS_PRECEDENCE["law_or_external_obligation"] == 1
    assert AUTHORITY_CLASS_PRECEDENCE["nolan_approved"] == 2
    assert AUTHORITY_CLASS_PRECEDENCE["model_inference"] == 9
    assert AUTHORITY_CLASS_PRECEDENCE["external_untrusted"] == 10

    with pytest.raises(ValidationError, match="source does not match"):
        AuthorityRecord(
            authority_record_id=uid(30),
            authority_class="nolan_approved",
            source_kind=AUTHORITY_SOURCE_BY_CLASS["model_inference"],
            effect="allow",
            subject_principal="apprentice",
            permissions=("observe",),
            project_scope_id=uid(31),
            scope_id=uid(31),
            issuer_entity_id=uid(32),
            effective_from=NOW,
            evidence_ids=(uid(33),),
            provenance_json=canonical_json_text({"source": "untrusted"}),
            registered_by_principal="codex_development_harness",
            registered_at=NOW,
        )


def test_apprentice_cannot_be_an_authority_registration_principal() -> None:
    with pytest.raises(
        ValidationError,
        match="non-Apprentice governed infrastructure",
    ):
        AuthorityRecord(
            authority_record_id=uid(34),
            authority_class="approved_project_policy",
            source_kind=AUTHORITY_SOURCE_BY_CLASS["approved_project_policy"],
            effect="allow",
            subject_principal="apprentice",
            permissions=("observe",),
            project_scope_id=uid(35),
            scope_id=uid(35),
            effective_from=NOW,
            evidence_ids=(uid(36),),
            provenance_json=canonical_json_text({"source": "untrusted"}),
            registered_by_principal="apprentice",
            registered_at=NOW,
        )
