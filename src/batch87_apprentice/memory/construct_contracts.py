"""Immutable typed payload contracts for B87-I3-B Construct memory."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, TypeAlias

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc
from batch87_apprentice.persistence.contracts import RecordEnvelope

from .contracts import MEMORY_RECORD_POLICIES

CONSTRUCT_RECORD_FAMILY = "construct_memory"
CONSTRUCT_INITIAL_LIFECYCLES = frozenset({"observed", "candidate", "reviewed"})
DECISION_STATUSES = frozenset({"accepted", "superseded", "revoked"})
PROJECT_STATE_TYPES = frozenset(
    {"phase", "milestone", "validation_baseline", "active_issue", "priority"}
)


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be non-empty text")
    return value


def _identifier(value: str, field: str) -> str:
    return validate_identifier(value, field=field)


def _enum(value: str, accepted: frozenset[str], field: str) -> str:
    if value not in accepted:
        raise ValidationError(f"{field} has an unsupported value: {value!r}")
    return value


def _canonical_array(value: Any, field: str) -> str:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValidationError(f"{field} must be a JSON array value")
    canonical = canonical_json_text(list(value))
    if not isinstance(parse_json(canonical), list):
        raise ValidationError(f"{field} must be a JSON array value")
    return canonical


def _canonical_structured(value: Any, field: str) -> str:
    if not isinstance(value, (Mapping, list, tuple)):
        raise ValidationError(f"{field} must be a JSON object or array value")
    canonical = canonical_json_text(value)
    if not isinstance(parse_json(canonical), (dict, list)):
        raise ValidationError(f"{field} must be a JSON object or array value")
    return canonical


def _canonical_scope_array(value: Any, field: str) -> str:
    canonical = _canonical_array(value, field)
    parsed = parse_json(canonical)
    seen: set[str] = set()
    for index, scope_id in enumerate(parsed):
        _identifier(scope_id, f"{field}[{index}]")
        if scope_id in seen:
            raise ValidationError(f"{field} cannot contain duplicate scope identifiers")
        seen.add(scope_id)
    return canonical


def normalize_construct_term(term: str) -> str:
    """Return the deterministic scoped-term comparison key."""

    return _text(term, "term").strip().casefold()


@dataclass(frozen=True, slots=True)
class ConstructRelationshipPolicy:
    relationship_type: str
    authority_bearing: bool
    self_reference_permitted: bool
    bidirectional_permitted: bool
    required_approval_authority_class: str

    def canonical_value(self) -> dict[str, Any]:
        return {
            "relationship_type": self.relationship_type,
            "authority_bearing": self.authority_bearing,
            "self_reference_permitted": self.self_reference_permitted,
            "bidirectional_permitted": self.bidirectional_permitted,
            "required_approval_authority_class": (
                self.required_approval_authority_class
            ),
        }


CONSTRUCT_RELATIONSHIP_POLICIES: Mapping[str, ConstructRelationshipPolicy] = {
    "has_final_authority_over": ConstructRelationshipPolicy(
        "has_final_authority_over", True, False, False, "nolan_approved"
    ),
    "provides_architecture_review_for": ConstructRelationshipPolicy(
        "provides_architecture_review_for",
        False,
        False,
        False,
        "nolan_byte_approved",
    ),
    "participates_in": ConstructRelationshipPolicy(
        "participates_in", False, False, False, "nolan_byte_approved"
    ),
    "draws_curriculum_from": ConstructRelationshipPolicy(
        "draws_curriculum_from", False, False, False, "nolan_byte_approved"
    ),
}


@dataclass(frozen=True, slots=True)
class ConstructEntityPayload:
    record_id: str
    entity_id: str
    memory_description: str

    RECORD_TYPE: ClassVar[str] = "construct_entity"
    TABLE: ClassVar[str] = "construct_entities"

    def __post_init__(self) -> None:
        _identifier(self.record_id, "record_id")
        _identifier(self.entity_id, "entity_id")
        _text(self.memory_description, "memory_description")

    def canonical_content(self) -> dict[str, Any]:
        return self.database_values()

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "entity_id": self.entity_id,
            "memory_description": self.memory_description,
        }


@dataclass(frozen=True, slots=True)
class ConstructRelationshipPayload:
    record_id: str
    subject_entity_id: str
    relationship_type: str
    object_entity_id: str
    description: str
    bidirectional: bool = False

    RECORD_TYPE: ClassVar[str] = "construct_relationship"
    TABLE: ClassVar[str] = "construct_relationships"

    def __post_init__(self) -> None:
        _identifier(self.record_id, "record_id")
        _identifier(self.subject_entity_id, "subject_entity_id")
        _identifier(self.object_entity_id, "object_entity_id")
        _text(self.description, "description")
        if not isinstance(self.bidirectional, bool):
            raise ValidationError("bidirectional must be boolean")
        policy = CONSTRUCT_RELATIONSHIP_POLICIES.get(self.relationship_type)
        if policy is None:
            raise ValidationError(
                f"unsupported Construct relationship type: {self.relationship_type!r}"
            )
        if (
            self.subject_entity_id == self.object_entity_id
            and not policy.self_reference_permitted
        ):
            raise ValidationError(
                f"{self.relationship_type} does not permit self-reference"
            )
        if self.bidirectional and not policy.bidirectional_permitted:
            raise ValidationError(
                f"{self.relationship_type} does not permit bidirectional use"
            )

    @property
    def policy(self) -> ConstructRelationshipPolicy:
        return CONSTRUCT_RELATIONSHIP_POLICIES[self.relationship_type]

    def canonical_content(self) -> dict[str, Any]:
        return {
            **self.database_values(),
            "bidirectional": self.bidirectional,
        }

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "subject_entity_id": self.subject_entity_id,
            "relationship_type": self.relationship_type,
            "object_entity_id": self.object_entity_id,
            "description": self.description,
            "bidirectional": int(self.bidirectional),
        }


@dataclass(frozen=True, slots=True, init=False)
class ArchitectureDecisionPayload:
    record_id: str
    decision_statement: str
    decision_scope: str
    rationale: str
    alternatives_json: str
    consequences_json: str
    decision_status: str

    RECORD_TYPE: ClassVar[str] = "architecture_decision"
    TABLE: ClassVar[str] = "architecture_decisions"

    def __init__(
        self,
        *,
        record_id: str,
        decision_statement: str,
        decision_scope: str,
        rationale: str,
        alternatives: Sequence[Any],
        consequences: Sequence[Any],
        decision_status: str,
    ) -> None:
        object.__setattr__(self, "record_id", _identifier(record_id, "record_id"))
        object.__setattr__(
            self,
            "decision_statement",
            _text(decision_statement, "decision_statement"),
        )
        object.__setattr__(
            self, "decision_scope", _identifier(decision_scope, "decision_scope")
        )
        object.__setattr__(self, "rationale", _text(rationale, "rationale"))
        object.__setattr__(
            self,
            "alternatives_json",
            _canonical_array(alternatives, "alternatives"),
        )
        object.__setattr__(
            self,
            "consequences_json",
            _canonical_array(consequences, "consequences"),
        )
        object.__setattr__(
            self,
            "decision_status",
            _enum(decision_status, DECISION_STATUSES, "decision_status"),
        )

    def canonical_content(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "decision_statement": self.decision_statement,
            "decision_scope": self.decision_scope,
            "rationale": self.rationale,
            "alternatives": parse_json(self.alternatives_json),
            "consequences": parse_json(self.consequences_json),
            "decision_status": self.decision_status,
        }

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "decision_statement": self.decision_statement,
            "decision_scope": self.decision_scope,
            "rationale": self.rationale,
            "alternatives_json": self.alternatives_json,
            "consequences_json": self.consequences_json,
            "decision_status": self.decision_status,
        }


@dataclass(frozen=True, slots=True, init=False)
class ProjectStatePayload:
    record_id: str
    project_id: str
    state_type: str
    state_value_json: str
    observed_at: str

    RECORD_TYPE: ClassVar[str] = "project_state"
    TABLE: ClassVar[str] = "project_states"

    def __init__(
        self,
        *,
        record_id: str,
        project_id: str,
        state_type: str,
        state_value: Mapping[str, Any] | Sequence[Any],
        observed_at: str,
    ) -> None:
        object.__setattr__(self, "record_id", _identifier(record_id, "record_id"))
        object.__setattr__(self, "project_id", _identifier(project_id, "project_id"))
        object.__setattr__(
            self, "state_type", _enum(state_type, PROJECT_STATE_TYPES, "state_type")
        )
        object.__setattr__(
            self,
            "state_value_json",
            _canonical_structured(state_value, "state_value"),
        )
        parse_canonical_utc(observed_at, field="observed_at")
        object.__setattr__(self, "observed_at", observed_at)

    def canonical_content(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "project_id": self.project_id,
            "state_type": self.state_type,
            "state_value": parse_json(self.state_value_json),
            "observed_at": self.observed_at,
        }

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "project_id": self.project_id,
            "state_type": self.state_type,
            "state_value_json": self.state_value_json,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True, slots=True, init=False)
class ConstructDoctrinePayload:
    record_id: str
    doctrine_statement: str
    application_scopes_json: str
    interpretation_notes: str
    exceptions_json: str

    RECORD_TYPE: ClassVar[str] = "construct_doctrine"
    TABLE: ClassVar[str] = "construct_doctrines"

    def __init__(
        self,
        *,
        record_id: str,
        doctrine_statement: str,
        application_scopes: Sequence[str],
        interpretation_notes: str,
        exceptions: Sequence[Any] = (),
    ) -> None:
        object.__setattr__(self, "record_id", _identifier(record_id, "record_id"))
        object.__setattr__(
            self,
            "doctrine_statement",
            _text(doctrine_statement, "doctrine_statement"),
        )
        object.__setattr__(
            self,
            "application_scopes_json",
            _canonical_scope_array(application_scopes, "application_scopes"),
        )
        object.__setattr__(
            self,
            "interpretation_notes",
            _text(interpretation_notes, "interpretation_notes"),
        )
        exceptions_json = _canonical_array(exceptions, "exceptions")
        if exceptions_json != "[]":
            raise ValidationError("Construct-doctrine exceptions must remain empty in I3-B")
        object.__setattr__(self, "exceptions_json", exceptions_json)

    def canonical_content(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "doctrine_statement": self.doctrine_statement,
            "application_scopes": parse_json(self.application_scopes_json),
            "interpretation_notes": self.interpretation_notes,
            "exceptions": parse_json(self.exceptions_json),
        }

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "doctrine_statement": self.doctrine_statement,
            "application_scopes_json": self.application_scopes_json,
            "interpretation_notes": self.interpretation_notes,
            "exceptions_json": self.exceptions_json,
        }


@dataclass(frozen=True, slots=True, init=False)
class TerminologyDefinitionPayload:
    record_id: str
    term: str
    definition: str
    definition_scope_id: str
    deprecated_aliases_json: str

    RECORD_TYPE: ClassVar[str] = "terminology_definition"
    TABLE: ClassVar[str] = "terminology_definitions"

    def __init__(
        self,
        *,
        record_id: str,
        term: str,
        definition: str,
        definition_scope_id: str,
        deprecated_aliases: Sequence[str] = (),
    ) -> None:
        object.__setattr__(self, "record_id", _identifier(record_id, "record_id"))
        object.__setattr__(self, "term", _text(term, "term"))
        object.__setattr__(self, "definition", _text(definition, "definition"))
        object.__setattr__(
            self,
            "definition_scope_id",
            _identifier(definition_scope_id, "definition_scope_id"),
        )
        aliases_json = _canonical_array(deprecated_aliases, "deprecated_aliases")
        for index, alias in enumerate(parse_json(aliases_json)):
            _text(alias, f"deprecated_aliases[{index}]")
        object.__setattr__(self, "deprecated_aliases_json", aliases_json)

    def canonical_content(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "term": self.term,
            "definition": self.definition,
            "definition_scope_id": self.definition_scope_id,
            "deprecated_aliases": parse_json(self.deprecated_aliases_json),
        }

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "term": self.term,
            "definition": self.definition,
            "definition_scope_id": self.definition_scope_id,
            "deprecated_aliases_json": self.deprecated_aliases_json,
        }


@dataclass(frozen=True, slots=True, init=False)
class PreferenceRecordPayload:
    record_id: str
    preference_subject_id: str
    preference_category: str
    preference_statement: str
    context_constraints_json: str

    RECORD_TYPE: ClassVar[str] = "preference_record"
    TABLE: ClassVar[str] = "preference_records"

    def __init__(
        self,
        *,
        record_id: str,
        preference_subject_id: str,
        preference_category: str,
        preference_statement: str,
        context_constraints: Sequence[Any] = (),
    ) -> None:
        object.__setattr__(self, "record_id", _identifier(record_id, "record_id"))
        object.__setattr__(
            self,
            "preference_subject_id",
            _identifier(preference_subject_id, "preference_subject_id"),
        )
        object.__setattr__(
            self,
            "preference_category",
            _text(preference_category, "preference_category"),
        )
        object.__setattr__(
            self,
            "preference_statement",
            _text(preference_statement, "preference_statement"),
        )
        object.__setattr__(
            self,
            "context_constraints_json",
            _canonical_array(context_constraints, "context_constraints"),
        )

    def canonical_content(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "preference_subject_id": self.preference_subject_id,
            "preference_category": self.preference_category,
            "preference_statement": self.preference_statement,
            "context_constraints": parse_json(self.context_constraints_json),
        }

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "preference_subject_id": self.preference_subject_id,
            "preference_category": self.preference_category,
            "preference_statement": self.preference_statement,
            "context_constraints_json": self.context_constraints_json,
        }


ConstructPayload: TypeAlias = (
    ConstructEntityPayload
    | ConstructRelationshipPayload
    | ArchitectureDecisionPayload
    | ProjectStatePayload
    | ConstructDoctrinePayload
    | TerminologyDefinitionPayload
    | PreferenceRecordPayload
)

CONSTRUCT_PAYLOAD_TYPES: Mapping[str, type[ConstructPayload]] = {
    payload_type.RECORD_TYPE: payload_type
    for payload_type in (
        ConstructEntityPayload,
        ConstructRelationshipPayload,
        ArchitectureDecisionPayload,
        ProjectStatePayload,
        ConstructDoctrinePayload,
        TerminologyDefinitionPayload,
        PreferenceRecordPayload,
    )
}
CONSTRUCT_PAYLOAD_TABLES: Mapping[str, str] = {
    record_type: payload_type.TABLE
    for record_type, payload_type in CONSTRUCT_PAYLOAD_TYPES.items()
}


def _validate_construct_identity(
    envelope: RecordEnvelope,
    payload: ConstructPayload,
) -> None:
    if not isinstance(payload, tuple(CONSTRUCT_PAYLOAD_TYPES.values())):
        raise TypeError("payload must be an accepted I3-B Construct payload")
    if envelope.record_id != payload.record_id:
        raise ValidationError("payload and envelope record identifiers differ")
    if envelope.record_family != CONSTRUCT_RECORD_FAMILY:
        raise ValidationError("Construct record family must be construct_memory")
    if envelope.record_type != payload.RECORD_TYPE:
        raise ValidationError("payload type does not match the record envelope")
    if envelope.project_scope_id is None:
        raise ValidationError("Construct memory requires project_scope_id")
    expected_subject = None
    if isinstance(payload, ConstructEntityPayload):
        expected_subject = payload.entity_id
    elif isinstance(payload, ConstructRelationshipPayload):
        expected_subject = payload.subject_entity_id
    elif isinstance(payload, ProjectStatePayload):
        expected_subject = payload.project_id
    elif isinstance(payload, PreferenceRecordPayload):
        expected_subject = payload.preference_subject_id
    if expected_subject is not None and envelope.subject_entity_id != expected_subject:
        raise ValidationError("payload subject does not match the record envelope")


def validate_construct_pair(
    envelope: RecordEnvelope,
    payload: ConstructPayload,
) -> None:
    _validate_construct_identity(envelope, payload)
    if envelope.lifecycle_state not in CONSTRUCT_INITIAL_LIFECYCLES:
        raise ValidationError("new Construct memory must begin in an I3-A initial state")
    if envelope.approval_status != "pending":
        raise ValidationError("new Construct memory must begin pending approval")
    if envelope.integrity_status != "valid":
        raise ValidationError("new Construct memory must begin with valid integrity")
    expected_write_policy = MEMORY_RECORD_POLICIES[
        (envelope.record_family, envelope.record_type)
    ][2]
    if envelope.agent_write_policy != expected_write_policy:
        raise ValidationError("agent_write_policy does not match the I3-A registry")


def construct_memory_content_hash(
    envelope: RecordEnvelope,
    payload: ConstructPayload,
) -> str:
    _validate_construct_identity(envelope, payload)
    return sha256_canonical_json(
        {
            "envelope": envelope.hash_material(),
            "payload_type": payload.RECORD_TYPE,
            "payload": payload.canonical_content(),
        }
    )


def payload_from_database(
    record_type: str,
    row: Mapping[str, Any],
) -> ConstructPayload:
    values = dict(row)
    if record_type == "construct_entity":
        return ConstructEntityPayload(
            values["record_id"], values["entity_id"], values["memory_description"]
        )
    if record_type == "construct_relationship":
        return ConstructRelationshipPayload(
            values["record_id"],
            values["subject_entity_id"],
            values["relationship_type"],
            values["object_entity_id"],
            values["description"],
            bool(values["bidirectional"]),
        )
    if record_type == "architecture_decision":
        return ArchitectureDecisionPayload(
            record_id=values["record_id"],
            decision_statement=values["decision_statement"],
            decision_scope=values["decision_scope"],
            rationale=values["rationale"],
            alternatives=parse_json(values["alternatives_json"]),
            consequences=parse_json(values["consequences_json"]),
            decision_status=values["decision_status"],
        )
    if record_type == "project_state":
        return ProjectStatePayload(
            record_id=values["record_id"],
            project_id=values["project_id"],
            state_type=values["state_type"],
            state_value=parse_json(values["state_value_json"]),
            observed_at=values["observed_at"],
        )
    if record_type == "construct_doctrine":
        return ConstructDoctrinePayload(
            record_id=values["record_id"],
            doctrine_statement=values["doctrine_statement"],
            application_scopes=parse_json(values["application_scopes_json"]),
            interpretation_notes=values["interpretation_notes"],
            exceptions=parse_json(values["exceptions_json"]),
        )
    if record_type == "terminology_definition":
        return TerminologyDefinitionPayload(
            record_id=values["record_id"],
            term=values["term"],
            definition=values["definition"],
            definition_scope_id=values["definition_scope_id"],
            deprecated_aliases=parse_json(values["deprecated_aliases_json"]),
        )
    if record_type == "preference_record":
        return PreferenceRecordPayload(
            record_id=values["record_id"],
            preference_subject_id=values["preference_subject_id"],
            preference_category=values["preference_category"],
            preference_statement=values["preference_statement"],
            context_constraints=parse_json(values["context_constraints_json"]),
        )
    raise ValidationError(f"unsupported Construct record type: {record_type!r}")
