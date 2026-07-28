"""Deterministic fixtures for B87-I3-D over accepted I2 and I3 truth."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.governance.contracts import GovernanceRule
from batch87_apprentice.memory import (
    ActiveUncertaintyPayload,
    TaskContextItem,
    TypedSourceReference,
)
from batch87_apprentice.persistence.contracts import RecordEnvelope
from batch87_apprentice.protocols import SessionContract
from tests.support.i2_fixtures import NOW, authority, evidence, task, uid
from tests.support.i3c3_fixtures import C3Harness, build_c3_harness
from tests.support.sql_probe import SqlProbe


@dataclass(frozen=True, slots=True)
class I3DHarness:
    c3: C3Harness
    task_id: str
    task_evidence_id: str

    @property
    def persistence(self):
        return self.c3.persistence

    @property
    def runtime(self):
        return self.c3.runtime

    @property
    def config(self):
        return self.c3.config

    @property
    def operator_id(self) -> str:
        return self.c3.operator_id

    @property
    def project_scope_id(self) -> str:
        return self.c3.project_scope_id

    @property
    def session_id(self) -> str:
        return self.c3.session_id


def build_i3d_harness(
    tmp_path: Path,
    *,
    base: int = 900_000,
) -> I3DHarness:
    c3 = build_c3_harness(tmp_path, identifier_start=base + 500)
    item = evidence(
        base + 1,
        content="Exact task-bound evidence available to the I3-D task.",
        captured_by_entity=c3.operator_id,
    )
    authority_record = authority(
        c3.c2.c1.i2,
        base + 2,
        evidence_ids=(item.evidence_id,),
        permissions=("analyse",),
    )
    c3.runtime.register_authority(
        authority_record,
        evidence_items=(item,),
    )
    contract = task(
        c3.c2.c1.i2,
        base,
        authority_ids=(authority_record.authority_record_id,),
        required_evidence_ids=(item.evidence_id,),
        action_class="analyse",
        objective="Reconstruct exact governed session and task continuity.",
    )
    result = c3.runtime.evaluate(contract)
    assert result.task_status == "active"
    return I3DHarness(
        c3=c3,
        task_id=contract.task_id,
        task_evidence_id=item.evidence_id,
    )


def create_other_project_task_evidence(
    harness: I3DHarness,
    *,
    base: int,
) -> str:
    i2 = harness.c3.c2.c1.i2
    session_id = uid(base)
    harness.runtime.open_session(
        SessionContract(
            session_id=session_id,
            purpose="Deterministic cross-project source fixture.",
            project_scope_id=i2.other_project_scope_id,
            opened_at=NOW,
            created_by_entity_id=harness.operator_id,
            participant_entity_ids=(
                harness.operator_id,
                i2.participant_id,
            ),
        )
    )
    item = evidence(
        base + 1,
        content="Evidence governed only for the other project.",
        captured_by_entity=harness.operator_id,
    )
    authority_record = authority(
        i2,
        base + 2,
        evidence_ids=(item.evidence_id,),
        permissions=("analyse",),
        project_scope_id=i2.other_project_scope_id,
        scope_id=i2.other_scope_id,
    )
    harness.runtime.register_authority(
        authority_record,
        evidence_items=(item,),
    )
    contract = task(
        i2,
        base + 3,
        authority_ids=(authority_record.authority_record_id,),
        required_evidence_ids=(item.evidence_id,),
        action_class="analyse",
        project_scope_id=i2.other_project_scope_id,
        requested_scope_id=i2.other_scope_id,
        session_id=session_id,
    )
    assert harness.runtime.evaluate(contract).task_status == "active"
    return item.evidence_id


def source_hash(
    harness: I3DHarness,
    source: TypedSourceReference,
) -> str:
    probe = SqlProbe(harness.config)
    if source.memory_record_id is not None:
        return probe.read(
            lambda connection: connection.execute(
                "SELECT content_hash FROM records WHERE record_id = ?",
                (source.memory_record_id,),
            ).fetchone()[0]
        )
    if source.evidence_id is not None:
        return probe.read(
            lambda connection: connection.execute(
                "SELECT content_hash FROM evidence_items WHERE evidence_id = ?",
                (source.evidence_id,),
            ).fetchone()[0]
        )
    return probe.read(
        lambda connection: connection.execute(
            """
            SELECT content_hash FROM governance_rules
            WHERE governance_rule_id = ?
            """,
            (source.governance_rule_id,),
        ).fetchone()[0]
    )


def active_rule_source(harness: I3DHarness) -> TypedSourceReference:
    rule_id = SqlProbe(harness.config).read(
        lambda connection: connection.execute(
            """
            SELECT decision_rule.governance_rule_id
            FROM governance_decision_rules AS decision_rule
            JOIN governance_decisions AS decision_record
              ON decision_record.governance_decision_id =
                 decision_rule.governance_decision_id
            JOIN governance_rules AS rule
              ON rule.governance_rule_id =
                 decision_rule.governance_rule_id
            WHERE decision_record.task_id = ?
              AND decision_record.project_scope_id = ?
              AND rule.status = 'active'
            ORDER BY decision_rule.rule_order
            LIMIT 1
            """,
            (harness.task_id, harness.project_scope_id),
        ).fetchone()[0]
    )
    return TypedSourceReference(governance_rule_id=rule_id)


def create_unbound_active_rule_source(
    harness: I3DHarness,
    *,
    base: int,
) -> TypedSourceReference:
    rule = GovernanceRule(
        governance_rule_id=uid(base),
        name=f"i3d_unbound_rule_{base}",
        version="1.0.0",
        kind="task_context",
        description=(
            "Active deterministic fixture rule not recorded for the I3-D task."
        ),
        configuration_json=canonical_json_text(
            {"task_context_eligibility": "explicit_relationship_required"}
        ),
    )
    SqlProbe(harness.config).write(
        lambda connection: connection.execute(
            """
            INSERT INTO governance_rules (
                governance_rule_id, rule_name, rule_version, rule_kind,
                description, configuration_json, content_hash, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                rule.governance_rule_id,
                rule.name,
                rule.version,
                rule.kind,
                rule.description,
                rule.configuration_json,
                rule.content_hash,
            ),
        )
    )
    return TypedSourceReference(governance_rule_id=rule.governance_rule_id)


def context_item(
    harness: I3DHarness,
    *,
    base: int,
    context_kind: str = "evidence",
    source: TypedSourceReference | None = None,
    injection_order: int = 0,
    required: bool = True,
    task_id: str | None = None,
    session_id: str | None = None,
    project_scope_id: str | None = None,
    content_hash: str | None = None,
) -> TaskContextItem:
    if source is None:
        source = TypedSourceReference(evidence_id=harness.task_evidence_id)
    return TaskContextItem(
        context_item_id=uid(base),
        task_id=harness.task_id if task_id is None else task_id,
        session_id=harness.session_id if session_id is None else session_id,
        project_scope_id=(
            harness.project_scope_id
            if project_scope_id is None
            else project_scope_id
        ),
        context_kind=context_kind,
        source=source,
        injection_order=injection_order,
        required=required,
        content_hash=(
            source_hash(harness, source)
            if content_hash is None
            else content_hash
        ),
        created_at=NOW,
        created_by_principal="codex_development_harness",
    )


def uncertainty_components(
    harness: I3DHarness,
    *,
    base: int,
    impact: str = "medium",
    task_id: str | None = None,
    session_id: str | None = None,
    project_scope_id: str | None = None,
) -> tuple[RecordEnvelope, ActiveUncertaintyPayload]:
    payload = ActiveUncertaintyPayload(
        record_id=uid(base),
        task_id=harness.task_id if task_id is None else task_id,
        session_id=harness.session_id if session_id is None else session_id,
        project_scope_id=(
            harness.project_scope_id
            if project_scope_id is None
            else project_scope_id
        ),
        uncertainty_statement=(
            "The exact downstream interpretation requires governed resolution."
        ),
        impact=impact,
        resolution_required=impact in {"high", "blocking"},
        created_at=NOW,
        created_by_principal="operator",
    )
    envelope = RecordEnvelope(
        record_id=payload.record_id,
        record_family="session_task_memory",
        record_type="active_uncertainty",
        schema_version="1.0.0",
        lifecycle_state="observed",
        approval_status="not_required",
        authority_class="nolan_approved",
        certainty_class="unknown",
        sensitivity_class="internal",
        privacy_class="none",
        retention_class="project_duration",
        training_eligibility="prohibited",
        created_at=NOW,
        source_kind="human_statement",
        provenance_summary="Explicit operator-recorded task uncertainty.",
        retrieval_policy_json=canonical_json_text(
            {"allowed_project_scope_ids": [payload.project_scope_id]}
        ),
        deletion_policy_json=canonical_json_text(
            {"deletion_mode": "governed"}
        ),
        agent_write_policy="candidate_only",
        project_scope_id=payload.project_scope_id,
        subject_entity_id=harness.c3.agent_id,
        session_id=payload.session_id,
        task_id=payload.task_id,
        created_by_entity_id=harness.operator_id,
    )
    return envelope, payload


def create_uncertainty(
    harness: I3DHarness,
    *,
    base: int,
    impact: str = "medium",
) -> tuple[RecordEnvelope, ActiveUncertaintyPayload]:
    envelope, payload = uncertainty_components(
        harness,
        base=base,
        impact=impact,
    )
    harness.persistence.session_task_memory.create_uncertainty(
        envelope,
        payload,
        lifecycle_transition_id=uid(base + 1),
        approval_transition_id=uid(base + 2),
        changed_by_principal="operator",
        changed_by_entity_id=harness.operator_id,
    )
    return envelope, payload
