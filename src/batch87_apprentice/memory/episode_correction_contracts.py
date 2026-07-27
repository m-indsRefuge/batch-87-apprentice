"""Frozen deterministic Episode and Correction contracts for B87-I3-C2."""

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
SELF_EPISODIC_MEMORY_DOMAIN = "self_episodic"

EPISODE_KINDS = frozenset(
    {
        "task",
        "conversation",
        "evaluation",
        "failure",
        "correction",
        "experiment",
    }
)
EPISODE_OUTCOMES = frozenset(
    {"completed", "partial", "failed", "stopped", "rejected"}
)
CORRECTION_ISSUER_CLASSES = frozenset(
    {"nolan", "byte", "nolan_byte", "approved_evaluator"}
)
CORRECTION_SEVERITIES = frozenset({"minor", "material", "critical"})

C2_PAYLOAD_TABLES: Mapping[str, str] = {
    "episode": "episodes",
    "correction": "corrections",
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
    """Validate an exact ordered identifier sequence without normalising order."""

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


@dataclass(frozen=True, slots=True, init=False)
class EpisodePayload:
    """One occurrence record; it never declares a lesson or pattern."""

    record_id: str
    episode_kind: str
    summary: str
    outcome: str
    input_evidence_ids: tuple[str, ...]
    output_evidence_ids: tuple[str, ...]
    evaluation_record_ids: tuple[str, ...]

    RECORD_TYPE: ClassVar[str] = "episode"
    TABLE: ClassVar[str] = "episodes"

    def __init__(
        self,
        *,
        record_id: str,
        episode_kind: str,
        summary: str,
        outcome: str,
        input_evidence_ids: Sequence[str],
        output_evidence_ids: Sequence[str],
        evaluation_record_ids: Sequence[str],
    ) -> None:
        object.__setattr__(
            self,
            "record_id",
            _identifier(record_id, "record_id"),
        )
        object.__setattr__(
            self,
            "episode_kind",
            _enum(episode_kind, EPISODE_KINDS, "episode_kind"),
        )
        object.__setattr__(self, "summary", _text(summary, "summary"))
        object.__setattr__(
            self,
            "outcome",
            _enum(outcome, EPISODE_OUTCOMES, "outcome"),
        )
        inputs = ordered_unique_identifiers(
            input_evidence_ids,
            "input_evidence_ids",
            allow_empty=True,
        )
        outputs = ordered_unique_identifiers(
            output_evidence_ids,
            "output_evidence_ids",
            allow_empty=True,
        )
        if not inputs and not outputs:
            raise ValidationError(
                "an episode requires at least one input or output evidence identifier"
            )
        overlap = set(inputs) & set(outputs)
        if overlap:
            raise ValidationError(
                "episode input and output evidence identifiers must not overlap"
            )
        object.__setattr__(self, "input_evidence_ids", inputs)
        object.__setattr__(self, "output_evidence_ids", outputs)
        object.__setattr__(
            self,
            "evaluation_record_ids",
            ordered_unique_identifiers(
                evaluation_record_ids,
                "evaluation_record_ids",
                allow_empty=True,
            ),
        )

    def canonical_content(self) -> dict[str, Any]:
        return {
            "episode_kind": self.episode_kind,
            "evaluation_record_ids": list(self.evaluation_record_ids),
            "input_evidence_ids": list(self.input_evidence_ids),
            "outcome": self.outcome,
            "output_evidence_ids": list(self.output_evidence_ids),
            "record_id": self.record_id,
            "summary": self.summary,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_content())

    def database_values(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "episode_kind": self.episode_kind,
            "summary": self.summary,
            "outcome": self.outcome,
            "canonical_json": self.canonical_json,
        }


@dataclass(frozen=True, slots=True)
class CorrectionPayload:
    """One immutable interpretation correcting one exact episode output."""

    record_id: str
    target_episode_id: str
    target_output_evidence_id: str
    problem_statement: str
    corrected_interpretation: str
    correction_category: str
    issued_by_entity_id: str
    issuer_class: str
    severity: str

    RECORD_TYPE: ClassVar[str] = "correction"
    TABLE: ClassVar[str] = "corrections"

    def __post_init__(self) -> None:
        _identifier(self.record_id, "record_id")
        _identifier(self.target_episode_id, "target_episode_id")
        _identifier(
            self.target_output_evidence_id,
            "target_output_evidence_id",
        )
        if self.target_episode_id == self.record_id:
            raise ValidationError("a correction cannot target itself")
        _text(self.problem_statement, "problem_statement")
        _text(self.corrected_interpretation, "corrected_interpretation")
        _text(self.correction_category, "correction_category")
        _identifier(self.issued_by_entity_id, "issued_by_entity_id")
        _enum(
            self.issuer_class,
            CORRECTION_ISSUER_CLASSES,
            "issuer_class",
        )
        _enum(self.severity, CORRECTION_SEVERITIES, "severity")

    def canonical_content(self) -> dict[str, Any]:
        return {
            "corrected_interpretation": self.corrected_interpretation,
            "correction_category": self.correction_category,
            "issued_by_entity_id": self.issued_by_entity_id,
            "issuer_class": self.issuer_class,
            "problem_statement": self.problem_statement,
            "record_id": self.record_id,
            "severity": self.severity,
            "target_episode_id": self.target_episode_id,
            "target_output_evidence_id": self.target_output_evidence_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_content())

    def database_values(self) -> dict[str, Any]:
        return {
            **self.canonical_content(),
            "canonical_json": self.canonical_json,
        }


def _validate_c2_identity(
    envelope: RecordEnvelope,
    payload: EpisodePayload | CorrectionPayload,
) -> None:
    if not isinstance(payload, (EpisodePayload, CorrectionPayload)):
        raise TypeError("payload must be an EpisodePayload or CorrectionPayload")
    if envelope.record_id != payload.record_id:
        raise ValidationError("payload and envelope record identifiers differ")
    if envelope.record_family != EPISODIC_RECORD_FAMILY:
        raise ValidationError(
            "Episode and Correction record family must be episodic_memory"
        )
    if envelope.record_type != payload.RECORD_TYPE:
        raise ValidationError("payload type does not match the record envelope")
    if envelope.project_scope_id is None:
        raise ValidationError("C2 memory requires project_scope_id")
    if envelope.agent_write_policy != "prohibited":
        raise ValidationError("C2 records prohibit Apprentice writes")
    if envelope.integrity_status != "valid":
        raise ValidationError("C2 records require valid initial integrity")
    if envelope.sensitivity_class not in {"public", "internal"}:
        raise ValidationError("C2 ordinary memory requires public or internal sensitivity")
    if envelope.privacy_class != "none":
        raise ValidationError("C2 ordinary memory requires privacy_class='none'")
    if envelope.training_eligibility == "approved":
        raise ValidationError("C2 creation cannot approve training eligibility")


def validate_episode_pair(
    envelope: RecordEnvelope,
    payload: EpisodePayload,
    *,
    for_creation: bool = True,
) -> None:
    _validate_c2_identity(envelope, payload)
    if envelope.session_id is None:
        raise ValidationError("episode memory requires session_id")
    if for_creation:
        if envelope.lifecycle_state != "observed":
            raise ValidationError("an episode must begin observed")
        if envelope.approval_status != "pending":
            raise ValidationError("an episode must begin approval-pending")


def validate_correction_pair(
    envelope: RecordEnvelope,
    payload: CorrectionPayload,
    *,
    for_creation: bool = True,
) -> None:
    _validate_c2_identity(envelope, payload)
    if for_creation:
        if envelope.lifecycle_state != "reviewed":
            raise ValidationError("a correction must begin reviewed")
        if envelope.approval_status != "pending":
            raise ValidationError("a correction must begin approval-pending")


def episode_content_hash(
    envelope: RecordEnvelope,
    payload: EpisodePayload,
) -> str:
    validate_episode_pair(envelope, payload, for_creation=False)
    return sha256_canonical_json(
        {
            "envelope": envelope.hash_material(),
            "payload": payload.canonical_content(),
            "payload_type": payload.RECORD_TYPE,
        }
    )


def correction_content_hash(
    envelope: RecordEnvelope,
    payload: CorrectionPayload,
    supporting_evidence_ids: Sequence[str],
) -> str:
    validate_correction_pair(envelope, payload, for_creation=False)
    support = ordered_unique_identifiers(
        supporting_evidence_ids,
        "supporting_evidence_ids",
        allow_empty=False,
    )
    if payload.target_output_evidence_id in support:
        raise ValidationError(
            "target output evidence must be separate from correction support"
        )
    return sha256_canonical_json(
        {
            "envelope": envelope.hash_material(),
            "payload": payload.canonical_content(),
            "payload_type": payload.RECORD_TYPE,
            "supporting_evidence_ids": list(support),
        }
    )


def episode_from_database(
    row: Mapping[str, Any],
    *,
    input_evidence_ids: Sequence[str],
    output_evidence_ids: Sequence[str],
    evaluation_record_ids: Sequence[str],
) -> EpisodePayload:
    return EpisodePayload(
        record_id=row["record_id"],
        episode_kind=row["episode_kind"],
        summary=row["summary"],
        outcome=row["outcome"],
        input_evidence_ids=input_evidence_ids,
        output_evidence_ids=output_evidence_ids,
        evaluation_record_ids=evaluation_record_ids,
    )


def correction_from_database(row: Mapping[str, Any]) -> CorrectionPayload:
    return CorrectionPayload(
        record_id=row["record_id"],
        target_episode_id=row["target_episode_id"],
        target_output_evidence_id=row["target_output_evidence_id"],
        problem_statement=row["problem_statement"],
        corrected_interpretation=row["corrected_interpretation"],
        correction_category=row["correction_category"],
        issued_by_entity_id=row["issued_by_entity_id"],
        issuer_class=row["issuer_class"],
        severity=row["severity"],
    )
