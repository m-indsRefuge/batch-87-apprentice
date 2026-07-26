from __future__ import annotations

import sqlite3

from batch87_apprentice.memory import ProjectStatePayload
from tests.integration.test_i3b_construct_memory import (
    PROJECT_ENTITY_ID,
    add_project_entity,
    create_payload,
)
from tests.support.i2_fixtures import NOW, build_harness, uid
from tests.support.sql_probe import SqlProbe


def create_valid_state(harness, *, base: int = 160_000) -> ProjectStatePayload:
    payload = ProjectStatePayload(
        record_id=uid(base),
        project_id=PROJECT_ENTITY_ID,
        state_type="phase",
        state_value={"phase": "I3-B", "status": "validated"},
        observed_at=NOW,
    )
    create_payload(harness, payload, base=base + 10)
    assert harness.persistence.construct_integrity.inspect().ok is True
    return payload


def test_direct_payload_mutation_after_trigger_removal_breaks_combined_hash(
    tmp_path,
) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    payload = create_valid_state(harness)

    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("project_states_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE project_states
            SET state_value_json = '{"phase":"corrupted"}'
            WHERE record_id = ?
            """,
            (payload.record_id,),
        ),
    )

    codes = {
        finding.code
        for finding in harness.persistence.construct_integrity.inspect().findings
    }
    assert "I3B-CONTENT-HASH" in codes
    assert "I3B-STORED-INTEGRITY-DISAGREEMENT" in codes
    main_report = harness.persistence.integrity.inspect()
    assert main_report.ok is False
    assert "construct_memory_i3b_content_hash" in {
        finding.code for finding in main_report.findings
    }


def test_missing_payload_and_initial_histories_are_detected_independently(
    tmp_path,
) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    first = create_valid_state(harness, base=161_000)
    second = create_valid_state(harness, base=161_100)
    probe = SqlProbe(harness.config)
    probe.corrupt_after_dropping_triggers(
        ("project_states_no_delete",),
        lambda connection: connection.execute(
            "DELETE FROM project_states WHERE record_id = ?",
            (first.record_id,),
        ),
    )
    probe.corrupt_after_dropping_triggers(
        (
            "memory_lifecycle_transitions_no_delete",
            "memory_approval_transitions_no_delete",
        ),
        lambda connection: (
            connection.execute(
                """
                DELETE FROM memory_record_lifecycle_transitions
                WHERE record_id = ?
                """,
                (second.record_id,),
            ),
            connection.execute(
                """
                DELETE FROM memory_record_approval_transitions
                WHERE record_id = ?
                """,
                (second.record_id,),
            ),
        ),
    )

    codes = {
        finding.code
        for finding in harness.persistence.construct_integrity.inspect().findings
    }
    assert "I3B-MISSING-PAYLOAD" in codes
    assert "I3B-MISSING-INITIAL-LIFECYCLE" in codes
    assert "I3B-MISSING-INITIAL-APPROVAL" in codes


def test_noncanonical_and_malformed_structured_json_are_detected(tmp_path) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    noncanonical = create_valid_state(harness, base=162_000)
    malformed = create_valid_state(harness, base=162_100)
    probe = SqlProbe(harness.config)
    probe.corrupt_after_dropping_triggers(
        ("project_states_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE project_states
            SET state_value_json = '{ "phase": "I3-B", "status": "validated" }'
            WHERE record_id = ?
            """,
            (noncanonical.record_id,),
        ),
    )

    def write_malformed(connection) -> None:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            """
            UPDATE project_states
            SET state_value_json = 'not-json'
            WHERE record_id = ?
            """,
            (malformed.record_id,),
        )

    probe.write(write_malformed)
    codes = {
        finding.code
        for finding in harness.persistence.construct_integrity.inspect().findings
    }
    assert "I3B-NONCANONICAL-PAYLOAD" in codes
    assert "I3B-MALFORMED-PAYLOAD" in codes


def test_duplicate_wrong_payload_and_policy_registry_corruption_are_detected(
    tmp_path,
) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    payload = create_valid_state(harness, base=163_000)
    probe = SqlProbe(harness.config)

    def duplicate_payload(connection) -> None:
        connection.execute("DROP TRIGGER preference_records_contract_guard")
        connection.execute(
            """
            INSERT INTO preference_records (
                record_id, preference_subject_id, preference_category,
                preference_statement, context_constraints_json
            ) VALUES (?, ?, 'corruption', 'Wrong payload table.', '[]')
            """,
            (payload.record_id, harness.operator_id),
        )

    probe.write(duplicate_payload)
    probe.corrupt_after_dropping_triggers(
        ("construct_relationship_type_policies_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE construct_relationship_type_policies
            SET required_approval_authority_class = 'nolan_byte_approved'
            WHERE relationship_type = 'has_final_authority_over'
            """
        ),
    )
    codes = {
        finding.code
        for finding in harness.persistence.construct_integrity.inspect().findings
    }
    assert "I3B-DUPLICATE-PAYLOAD" in codes
    assert "I3B-WRONG-PAYLOAD-TABLE" in codes
    assert "I3B-RELATIONSHIP-POLICY-REGISTRY" in codes


def test_orphan_and_invalid_entity_reference_are_detected_with_fks_disabled(
    tmp_path,
) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    payload = create_valid_state(harness, base=164_000)

    connection = sqlite3.connect(harness.config.path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DROP TRIGGER project_states_immutable")
        connection.execute(
            "UPDATE project_states SET project_id = ? WHERE record_id = ?",
            (uid(164_999), payload.record_id),
        )
        connection.execute("DROP TRIGGER construct_entities_contract_guard")
        connection.execute(
            """
            INSERT INTO construct_entities (
                record_id, entity_id, memory_description
            ) VALUES (?, ?, 'Orphan corruption fixture.')
            """,
            (uid(164_998), uid(164_997)),
        )
        connection.commit()
    finally:
        connection.close()

    codes = {
        finding.code
        for finding in harness.persistence.construct_integrity.inspect().findings
    }
    assert "I3B-ENTITY-REFERENCE" in codes
    assert "I3B-ORPHAN-PAYLOAD" in codes



def test_reconstruction_combines_shared_i3a_and_construct_integrity(tmp_path) -> None:
    harness = build_harness(tmp_path)
    add_project_entity(harness)
    payload = create_valid_state(harness, base=165_000)
    SqlProbe(harness.config).corrupt_after_dropping_triggers(
        ("memory_lifecycle_transitions_immutable",),
        lambda connection: connection.execute(
            """
            UPDATE memory_record_lifecycle_transitions
            SET content_hash = ?
            WHERE record_id = ? AND sequence_number = 0
            """,
            ("0" * 64, payload.record_id),
        ),
    )

    audit = harness.persistence.construct_memory.reconstruct(payload.record_id)

    assert audit["integrity"]["valid"] is False
    assert {
        (finding["source"], finding["code"])
        for finding in audit["integrity"]["findings"]
    } >= {("shared_memory_integrity", "I3A-HASH-MISMATCH")}
