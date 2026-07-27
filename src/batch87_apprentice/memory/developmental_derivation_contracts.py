"""Frozen deterministic developmental-derivation contracts for B87-I3-C3."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from batch87_apprentice.common.canonical_json import canonical_json_text
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.persistence.contracts import RecordEnvelope

EPISODIC_RECORD_FAMILY = "episodic_memory"

LESSON_INTENDED_SCOPES = frozenset({"task", "project", "construct"})
LESSON_PROPOSER_CLASSES = frozenset({"apprentice", "byte", "evaluator"})
LESSON_STABILITIES = frozenset({"new", "repeated", "stable"})
FAILURE_PATTERN_SEVERITIES = frozenset({"material", "critical"})
FAILURE_PATTERN_RESOLUTION_STATUSES = frozenset(
    {"open", "improving", "resolved", "model-limitation"}
)
SUCCESS_PATTERN_STABILITIES = frozenset({"emerging", "repeated", "stable"})

C3_PAYLOAD_TABLES: Mapping[str, str] = {
    "lesson_candidate": "lesson_candidates",
    "approved_lesson": "approved_lessons",
    "failure_pattern": "failure_patterns",
    "success_pattern": "success_patterns",
}


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be non-empty text")
    return value


def _enum(value: str, accepted: frozenset[str], field: str) -> str:
    if value not in accepted:
        raise ValidationError(f"{field} has an unsupported value: {value!r}")
    return value


def _identifier(value: str, field: str) -> str:
    return validate_identifier(value, field=field)


def ordered_unique_identifiers(
    values: Sequence[str],
    field: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(
        values,
        Sequence,
    ):
        raise ValidationError(f"{field} must be an ordered sequence")
    result = tuple(values)
    if not allow_empty and not result:
        raise ValidationError(f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise ValidationError(f"{field} must not contain duplicates")
    for index, value in enumerate(result):
        _identifier(value, f"{field}[{index}]")
    return result


def ordered_unique_text(
    values: Sequence[str],
    field: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(
        values,
        Sequence,
    ):
        raise ValidationError(f"{field} must be an ordered sequence")
    result = tuple(values)
    if not allow_empty and not result:
        raise ValidationError(f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise ValidationError(f"{field} must not contain duplicates")
    for index, value in enumerate(result):
        _text(value, f"{field}[{index}]")
    return result


@dataclass(frozen=True, slots=True, init=False)
class LessonCandidatePayload:
    """One inspect-only proposed transferable interpretation."""

    record_id: str
    source_episode_ids: tuple[str, ...]
    source_correction_ids: tuple[str, ...]
    lesson_statement: str
    intended_scope: str
    proposer_entity_id: str
    proposed_by: str
    known_limitations: tuple[str, ...]

    RECORD_TYPE: ClassVar[str] = "lesson_candidate"
    TABLE: ClassVar[str] = "lesson_candidates"

    def __init__(
        self,
        *,
        record_id: str,
        source_episode_ids: Sequence[str],
        source_correction_ids: Sequence[str],
        lesson_statement: str,
        intended_scope: str,
        proposer_entity_id: str,
        proposed_by: str,
        known_limitations: Sequence[str],
    ) -> None:
        object.__setattr__(self, "record_id", _identifier(record_id, "record_id"))
        object.__setattr__(
            self,
            "source_episode_ids",
            ordered_unique_identifiers(
                source_episode_ids,
                "source_episode_ids",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "source_correction_ids",
            ordered_unique_identifiers(
                source_correction_ids,
                "source_correction_ids",
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "lesson_statement",
            _text(lesson_statement, "lesson_statement"),
        )
        object.__setattr__(
            self,
            "intended_scope",
            _enum(intended_scope, LESSON_INTENDED_SCOPES, "intended_scope"),
        )
        object.__setattr__(
            self,
            "proposer_entity_id",
            _identifier(proposer_entity_id, "proposer_entity_id"),
        )
        object.__setattr__(
            self,
            "proposed_by",
            _enum(proposed_by, LESSON_PROPOSER_CLASSES, "proposed_by"),
        )
        object.__setattr__(
            self,
            "known_limitations",
            ordered_unique_text(
                known_limitations,
                "known_limitations",
                allow_empty=True,
            ),
        )

    def canonical_content(self) -> dict[str, Any]:
        return {
            "intended_scope": self.intended_scope,
            "known_limitations": list(self.known_limitations),
            "lesson_statement": self.lesson_statement,
            "proposed_by": self.proposed_by,
            "proposer_entity_id": self.proposer_entity_id,
            "record_id": self.record_id,
            "source_correction_ids": list(self.source_correction_ids),
            "source_episode_ids": list(self.source_episode_ids),
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_content())

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "lesson_statement": self.lesson_statement,
            "intended_scope": self.intended_scope,
            "proposer_entity_id": self.proposer_entity_id,
            "proposed_by": self.proposed_by,
            "canonical_json": self.canonical_json,
        }


@dataclass(frozen=True, slots=True, init=False)
class ApprovedLessonPayload:
    """One separate Nolan-Byte-approved transferable lesson."""

    record_id: str
    candidate_record_id: str
    lesson_statement: str
    application_conditions: tuple[str, ...]
    non_application_conditions: tuple[str, ...]
    source_episode_ids: tuple[str, ...]
    source_correction_ids: tuple[str, ...]
    approved_by: str
    transfer_test_evaluation_ids: tuple[str, ...]
    stability: str

    RECORD_TYPE: ClassVar[str] = "approved_lesson"
    TABLE: ClassVar[str] = "approved_lessons"

    def __init__(
        self,
        *,
        record_id: str,
        candidate_record_id: str,
        lesson_statement: str,
        application_conditions: Sequence[str],
        non_application_conditions: Sequence[str],
        source_episode_ids: Sequence[str],
        source_correction_ids: Sequence[str],
        transfer_test_evaluation_ids: Sequence[str],
        stability: str,
        approved_by: str = "nolan-byte",
    ) -> None:
        object.__setattr__(self, "record_id", _identifier(record_id, "record_id"))
        candidate_id = _identifier(candidate_record_id, "candidate_record_id")
        if candidate_id == record_id:
            raise ValidationError("an approved lesson cannot be its own candidate")
        object.__setattr__(self, "candidate_record_id", candidate_id)
        object.__setattr__(
            self,
            "lesson_statement",
            _text(lesson_statement, "lesson_statement"),
        )
        applications = ordered_unique_text(
            application_conditions,
            "application_conditions",
            allow_empty=False,
        )
        non_applications = ordered_unique_text(
            non_application_conditions,
            "non_application_conditions",
            allow_empty=False,
        )
        if set(applications) & set(non_applications):
            raise ValidationError(
                "application and non-application conditions must be disjoint"
            )
        object.__setattr__(self, "application_conditions", applications)
        object.__setattr__(
            self,
            "non_application_conditions",
            non_applications,
        )
        object.__setattr__(
            self,
            "source_episode_ids",
            ordered_unique_identifiers(
                source_episode_ids,
                "source_episode_ids",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "source_correction_ids",
            ordered_unique_identifiers(
                source_correction_ids,
                "source_correction_ids",
                allow_empty=False,
            ),
        )
        if approved_by != "nolan-byte":
            raise ValidationError("approved_by must be exactly 'nolan-byte'")
        object.__setattr__(self, "approved_by", approved_by)
        object.__setattr__(
            self,
            "transfer_test_evaluation_ids",
            ordered_unique_identifiers(
                transfer_test_evaluation_ids,
                "transfer_test_evaluation_ids",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "stability",
            _enum(stability, LESSON_STABILITIES, "stability"),
        )

    def canonical_content(self) -> dict[str, Any]:
        return {
            "application_conditions": list(self.application_conditions),
            "approved_by": self.approved_by,
            "candidate_record_id": self.candidate_record_id,
            "lesson_statement": self.lesson_statement,
            "non_application_conditions": list(
                self.non_application_conditions
            ),
            "record_id": self.record_id,
            "source_correction_ids": list(self.source_correction_ids),
            "source_episode_ids": list(self.source_episode_ids),
            "stability": self.stability,
            "transfer_test_evaluation_ids": list(
                self.transfer_test_evaluation_ids
            ),
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_content())

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "candidate_record_id": self.candidate_record_id,
            "lesson_statement": self.lesson_statement,
            "approved_by": self.approved_by,
            "stability": self.stability,
            "canonical_json": self.canonical_json,
        }


@dataclass(frozen=True, slots=True, init=False)
class FailurePatternPayload:
    """One candidate-bound externally reviewable repeated failure pattern."""

    record_id: str
    pattern_name: str
    description: str
    episode_ids: tuple[str, ...]
    frequency: int
    severity: str
    containment_required: bool
    resolution_status: str

    RECORD_TYPE: ClassVar[str] = "failure_pattern"
    TABLE: ClassVar[str] = "failure_patterns"

    def __init__(
        self,
        *,
        record_id: str,
        pattern_name: str,
        description: str,
        episode_ids: Sequence[str],
        frequency: int,
        severity: str,
        containment_required: bool,
        resolution_status: str,
    ) -> None:
        object.__setattr__(self, "record_id", _identifier(record_id, "record_id"))
        object.__setattr__(self, "pattern_name", _text(pattern_name, "pattern_name"))
        object.__setattr__(self, "description", _text(description, "description"))
        episodes = ordered_unique_identifiers(
            episode_ids,
            "episode_ids",
            allow_empty=False,
        )
        if len(episodes) < 2:
            raise ValidationError("a failure pattern requires multiple episodes")
        if not isinstance(frequency, int) or isinstance(frequency, bool):
            raise ValidationError("frequency must be an integer")
        if frequency != len(episodes):
            raise ValidationError(
                "frequency must equal the distinct source episode count"
            )
        object.__setattr__(self, "episode_ids", episodes)
        object.__setattr__(self, "frequency", frequency)
        object.__setattr__(
            self,
            "severity",
            _enum(severity, FAILURE_PATTERN_SEVERITIES, "severity"),
        )
        if containment_required is not True:
            raise ValidationError("failure patterns require containment")
        object.__setattr__(self, "containment_required", True)
        object.__setattr__(
            self,
            "resolution_status",
            _enum(
                resolution_status,
                FAILURE_PATTERN_RESOLUTION_STATUSES,
                "resolution_status",
            ),
        )

    def canonical_content(self) -> dict[str, Any]:
        return {
            "containment_required": self.containment_required,
            "description": self.description,
            "episode_ids": list(self.episode_ids),
            "frequency": self.frequency,
            "pattern_name": self.pattern_name,
            "record_id": self.record_id,
            "resolution_status": self.resolution_status,
            "severity": self.severity,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_content())

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "pattern_name": self.pattern_name,
            "description": self.description,
            "frequency": self.frequency,
            "severity": self.severity,
            "containment_required": int(self.containment_required),
            "resolution_status": self.resolution_status,
            "canonical_json": self.canonical_json,
        }


@dataclass(frozen=True, slots=True, init=False)
class SuccessPatternPayload:
    """One candidate-bound externally reviewable repeated success pattern."""

    record_id: str
    pattern_name: str
    description: str
    episode_ids: tuple[str, ...]
    transfer_scope: tuple[str, ...]
    stability: str

    RECORD_TYPE: ClassVar[str] = "success_pattern"
    TABLE: ClassVar[str] = "success_patterns"

    def __init__(
        self,
        *,
        record_id: str,
        pattern_name: str,
        description: str,
        episode_ids: Sequence[str],
        transfer_scope: Sequence[str],
        stability: str,
    ) -> None:
        object.__setattr__(self, "record_id", _identifier(record_id, "record_id"))
        object.__setattr__(self, "pattern_name", _text(pattern_name, "pattern_name"))
        object.__setattr__(self, "description", _text(description, "description"))
        episodes = ordered_unique_identifiers(
            episode_ids,
            "episode_ids",
            allow_empty=False,
        )
        if len(episodes) < 2:
            raise ValidationError("a success pattern requires multiple episodes")
        object.__setattr__(self, "episode_ids", episodes)
        object.__setattr__(
            self,
            "transfer_scope",
            ordered_unique_text(
                transfer_scope,
                "transfer_scope",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "stability",
            _enum(stability, SUCCESS_PATTERN_STABILITIES, "stability"),
        )

    def canonical_content(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "episode_ids": list(self.episode_ids),
            "pattern_name": self.pattern_name,
            "record_id": self.record_id,
            "stability": self.stability,
            "transfer_scope": list(self.transfer_scope),
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_content())

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "pattern_name": self.pattern_name,
            "description": self.description,
            "stability": self.stability,
            "canonical_json": self.canonical_json,
        }


DevelopmentalPayload = (
    LessonCandidatePayload
    | ApprovedLessonPayload
    | FailurePatternPayload
    | SuccessPatternPayload
)


def validate_developmental_pair(
    envelope: RecordEnvelope,
    payload: DevelopmentalPayload,
    *,
    for_creation: bool = True,
) -> None:
    if not isinstance(
        payload,
        (
            LessonCandidatePayload,
            ApprovedLessonPayload,
            FailurePatternPayload,
            SuccessPatternPayload,
        ),
    ):
        raise TypeError("payload must be a C3 developmental payload")
    if envelope.record_id != payload.record_id:
        raise ValidationError("payload and envelope record identifiers differ")
    if envelope.record_family != EPISODIC_RECORD_FAMILY:
        raise ValidationError("C3 records require episodic_memory family")
    if envelope.record_type != payload.RECORD_TYPE:
        raise ValidationError("payload type does not match the record envelope")
    if envelope.project_scope_id is None:
        raise ValidationError("C3 memory requires project_scope_id")
    expected_policy = (
        "prohibited"
        if payload.RECORD_TYPE == "approved_lesson"
        else "candidate_only"
    )
    if envelope.agent_write_policy != expected_policy:
        raise ValidationError(
            f"{payload.RECORD_TYPE} requires agent_write_policy={expected_policy!r}"
        )
    if envelope.integrity_status != "valid":
        raise ValidationError("C3 records require valid initial integrity")
    if envelope.sensitivity_class not in {"public", "internal"}:
        raise ValidationError("C3 ordinary memory must be public or internal")
    if envelope.privacy_class != "none":
        raise ValidationError("C3 ordinary memory requires privacy_class='none'")
    if envelope.training_eligibility == "approved":
        raise ValidationError("C3 creation cannot approve training eligibility")
    if not for_creation:
        return
    expected_lifecycle = (
        "reviewed" if payload.RECORD_TYPE == "approved_lesson" else "candidate"
    )
    if envelope.lifecycle_state != expected_lifecycle:
        raise ValidationError(
            f"{payload.RECORD_TYPE} must begin {expected_lifecycle}"
        )
    if envelope.approval_status != "pending":
        raise ValidationError("C3 records must begin approval-pending")


def developmental_content_hash(
    envelope: RecordEnvelope,
    payload: DevelopmentalPayload,
) -> str:
    validate_developmental_pair(envelope, payload, for_creation=False)
    return sha256_canonical_json(
        {
            "envelope": envelope.hash_material(),
            "payload": payload.canonical_content(),
            "payload_type": payload.RECORD_TYPE,
        }
    )
