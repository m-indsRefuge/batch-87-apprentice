"""Immutable canonical contracts for B87-I4-A retrieval and context assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc


RETRIEVAL_CONTRACT_VERSION = "1.0.0"
STRUCTURED_CONTEXT_VERSION = "1.0.0"
RETRIEVAL_PRINCIPALS = frozenset(
    {"operator", "codex_development_harness"}
)
CONTEXT_SECTIONS = ("task", "authority", "policy", "evidence", "memory")
RANKABLE_SECTIONS = ("policy", "evidence", "memory")
RANKING_STRATEGIES = frozenset({"deterministic_fallback_v1"})
ELIGIBILITY_STATUSES = frozenset({"eligible", "ineligible"})
MATERIALIZATION_STATUSES = frozenset(
    {"materialized", "not_attempted", "unavailable", "prohibited", "invalid"}
)
DISPOSITIONS = frozenset({"included", "excluded"})
MANIFEST_STATUSES = frozenset({"accepted", "rejected"})
CONTEXT_STATUSES = frozenset(
    {
        "accepted",
        "rejected_contamination",
        "rejected_required_source",
        "rejected_integrity",
    }
)
CONTAMINATION_STATUSES = frozenset({"clean", "contaminated"})
_PROHIBITED_REQUEST_KEYS = frozenset(
    {
        "credential",
        "credentials",
        "executable_code",
        "filesystem_path",
        "inference_settings",
        "model",
        "model_name",
        "network_destination",
        "prompt_role",
        "provider",
        "provider_name",
        "raw_sql",
        "sql",
        "tool",
        "tool_definitions",
        "tools",
    }
)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be non-empty text")
    return value


def _sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValidationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _enum(value: object, accepted: frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in accepted:
        raise ValidationError(f"{field} is invalid")
    return value


def _canonical_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be canonical JSON text")
    parsed = parse_json(value)
    if (
        not isinstance(parsed, dict)
        or not parsed
        or canonical_json_text(parsed) != value
    ):
        raise ValidationError(f"{field} must be a non-empty canonical JSON object")
    return parsed


def _canonical_value(value: object, field: str) -> Any:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be canonical JSON text")
    parsed = parse_json(value)
    if canonical_json_text(parsed) != value:
        raise ValidationError(f"{field} must use the canonical JSON representation")
    return parsed


def _reason_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValidationError(f"{field} must be an immutable tuple")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValidationError(f"{field} contains invalid reason text")
    if len(set(value)) != len(value):
        raise ValidationError(f"{field} cannot contain duplicates")
    return value


def _prohibited_request_paths(
    value: object,
    *,
    path: str = "provenance",
) -> tuple[str, ...]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            child = f"{path}.{key}"
            if key.lower() in _PROHIBITED_REQUEST_KEYS:
                found.append(child)
            found.extend(_prohibited_request_paths(nested, path=child))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(
                _prohibited_request_paths(
                    nested,
                    path=f"{path}[{index}]",
                )
            )
    return tuple(found)


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    """One immutable request over an exact finalized I3-D task-context set."""

    retrieval_request_id: str
    contract_version: str
    task_id: str
    session_id: str
    project_scope_id: str
    task_context_finalization_id: str
    purpose: str
    requested_sections: tuple[str, ...]
    requested_at: str
    requested_by_principal: str
    ranking_strategy: str
    provenance_json: str

    def __post_init__(self) -> None:
        for field in (
            "retrieval_request_id",
            "task_id",
            "session_id",
            "project_scope_id",
            "task_context_finalization_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        if self.contract_version != RETRIEVAL_CONTRACT_VERSION:
            raise ValidationError("unsupported retrieval contract version")
        _text(self.purpose, "purpose")
        if self.requested_sections != CONTEXT_SECTIONS:
            raise ValidationError(
                "requested_sections must be exactly task, authority, policy, "
                "evidence, memory"
            )
        if len(set(self.requested_sections)) != len(self.requested_sections):
            raise ValidationError("requested_sections cannot contain duplicates")
        parse_canonical_utc(self.requested_at, field="requested_at")
        _enum(
            self.requested_by_principal,
            RETRIEVAL_PRINCIPALS,
            "requested_by_principal",
        )
        _enum(self.ranking_strategy, RANKING_STRATEGIES, "ranking_strategy")
        provenance = _canonical_object(self.provenance_json, "provenance_json")
        prohibited_paths = _prohibited_request_paths(provenance)
        if prohibited_paths:
            raise ValidationError(
                "retrieval provenance contains prohibited execution or "
                "provider fields: "
                + ",".join(prohibited_paths)
            )

    @classmethod
    def from_mapping(cls, value: object) -> RetrievalRequest:
        if not isinstance(value, Mapping):
            raise ValidationError("retrieval request must be an object")
        fields = {
            "retrieval_request_id",
            "contract_version",
            "task_id",
            "session_id",
            "project_scope_id",
            "task_context_finalization_id",
            "purpose",
            "requested_sections",
            "requested_at",
            "requested_by_principal",
            "ranking_strategy",
            "provenance",
        }
        missing = sorted(fields - set(value))
        unsupported = sorted(set(value) - fields)
        if missing or unsupported:
            parts = []
            if missing:
                parts.append("missing=" + ",".join(missing))
            if unsupported:
                parts.append("unsupported=" + ",".join(unsupported))
            raise ValidationError(
                "retrieval request fields are invalid: " + "; ".join(parts)
            )
        sections = value["requested_sections"]
        if not isinstance(sections, (list, tuple)):
            raise ValidationError("requested_sections must be an array")
        provenance = value["provenance"]
        if not isinstance(provenance, Mapping):
            raise ValidationError("provenance must be an object")
        return cls(
            retrieval_request_id=value["retrieval_request_id"],
            contract_version=value["contract_version"],
            task_id=value["task_id"],
            session_id=value["session_id"],
            project_scope_id=value["project_scope_id"],
            task_context_finalization_id=value["task_context_finalization_id"],
            purpose=value["purpose"],
            requested_sections=tuple(sections),
            requested_at=value["requested_at"],
            requested_by_principal=value["requested_by_principal"],
            ranking_strategy=value["ranking_strategy"],
            provenance_json=canonical_json_text(dict(provenance)),
        )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "project_scope_id": self.project_scope_id,
            "provenance": _canonical_object(
                self.provenance_json,
                "provenance_json",
            ),
            "purpose": self.purpose,
            "ranking_strategy": self.ranking_strategy,
            "requested_at": self.requested_at,
            "requested_by_principal": self.requested_by_principal,
            "requested_sections": list(self.requested_sections),
            "retrieval_request_id": self.retrieval_request_id,
            "session_id": self.session_id,
            "task_context_finalization_id": self.task_context_finalization_id,
            "task_id": self.task_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    """One finalized I3-D item after the accepted eligibility decision."""

    context_item_id: str
    context_kind: str
    source_kind: str
    source_id: str
    source_content_hash: str
    required: bool
    injection_order: int
    target_section: str
    eligibility_status: str
    eligibility_reasons: tuple[str, ...]
    eligibility_decision_hash: str
    materialization_status: str
    materialization_reasons: tuple[str, ...]
    materialized_json: str | None

    def __post_init__(self) -> None:
        validate_identifier(self.context_item_id, field="context_item_id")
        validate_identifier(self.source_id, field="source_id")
        _text(self.context_kind, "context_kind")
        if self.source_kind not in {
            "memory_record",
            "evidence",
            "governance_rule",
        }:
            raise ValidationError("source_kind is invalid")
        _sha256(self.source_content_hash, "source_content_hash")
        if not isinstance(self.required, bool):
            raise ValidationError("required must be boolean")
        if (
            not isinstance(self.injection_order, int)
            or isinstance(self.injection_order, bool)
            or self.injection_order < 0
        ):
            raise ValidationError(
                "injection_order must be a non-negative integer"
            )
        if self.target_section not in RANKABLE_SECTIONS:
            raise ValidationError("candidate target_section is invalid")
        _enum(
            self.eligibility_status,
            ELIGIBILITY_STATUSES,
            "eligibility_status",
        )
        _reason_tuple(self.eligibility_reasons, "eligibility_reasons")
        _sha256(self.eligibility_decision_hash, "eligibility_decision_hash")
        _enum(
            self.materialization_status,
            MATERIALIZATION_STATUSES,
            "materialization_status",
        )
        _reason_tuple(self.materialization_reasons, "materialization_reasons")
        if self.eligibility_status == "eligible" and self.eligibility_reasons:
            raise ValidationError(
                "eligible candidate cannot contain eligibility reasons"
            )
        if (
            self.eligibility_status == "ineligible"
            and self.materialization_status != "not_attempted"
        ):
            raise ValidationError(
                "ineligible candidate cannot be materialized"
            )
        if self.materialization_status == "materialized":
            if self.materialized_json is None:
                raise ValidationError(
                    "materialized candidate requires canonical content"
                )
            _canonical_object(self.materialized_json, "materialized_json")
            if self.materialization_reasons:
                raise ValidationError(
                    "materialized candidate cannot have failure reasons"
                )
        elif self.materialized_json is not None:
            raise ValidationError(
                "non-materialized candidate cannot expose content"
            )

    @property
    def includable(self) -> bool:
        return (
            self.eligibility_status == "eligible"
            and self.materialization_status == "materialized"
        )

    @property
    def materialized_content_hash(self) -> str | None:
        if self.materialized_json is None:
            return None
        return sha256_canonical_json(
            _canonical_object(self.materialized_json, "materialized_json")
        )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "context_item_id": self.context_item_id,
            "context_kind": self.context_kind,
            "eligibility": {
                "decision_hash": self.eligibility_decision_hash,
                "reasons": list(self.eligibility_reasons),
                "status": self.eligibility_status,
            },
            "injection_order": self.injection_order,
            "materialization": {
                "content": (
                    None
                    if self.materialized_json is None
                    else _canonical_object(
                        self.materialized_json,
                        "materialized_json",
                    )
                ),
                "reasons": list(self.materialization_reasons),
                "status": self.materialization_status,
            },
            "required": self.required,
            "source_content_hash": self.source_content_hash,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "target_section": self.target_section,
        }


@dataclass(frozen=True, slots=True)
class RankComponents:
    required_priority: int
    section_priority: int
    finalized_injection_order: int
    stable_tiebreak: str

    def __post_init__(self) -> None:
        if self.required_priority not in {0, 1}:
            raise ValidationError("required_priority must be zero or one")
        if self.section_priority not in {0, 1, 2}:
            raise ValidationError("section_priority is invalid")
        if (
            not isinstance(self.finalized_injection_order, int)
            or isinstance(self.finalized_injection_order, bool)
            or self.finalized_injection_order < 0
        ):
            raise ValidationError(
                "finalized_injection_order must be non-negative"
            )
        _text(self.stable_tiebreak, "stable_tiebreak")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "finalized_injection_order": self.finalized_injection_order,
            "required_priority": self.required_priority,
            "section_priority": self.section_priority,
            "stable_tiebreak": self.stable_tiebreak,
        }


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: RetrievalCandidate
    components: RankComponents
    explanation: tuple[str, ...]
    final_rank: int

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, RetrievalCandidate):
            raise ValidationError("ranked candidate is invalid")
        if not self.candidate.includable:
            raise ValidationError("ranker received a non-includable candidate")
        if not isinstance(self.components, RankComponents):
            raise ValidationError("rank components are invalid")
        _reason_tuple(self.explanation, "ranking explanation")
        if (
            not isinstance(self.final_rank, int)
            or isinstance(self.final_rank, bool)
            or self.final_rank < 0
        ):
            raise ValidationError("final_rank must be non-negative")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "context_item_id": self.candidate.context_item_id,
            "explanation": list(self.explanation),
            "final_rank": self.final_rank,
            "score_components": self.components.canonical_value(),
        }


@dataclass(frozen=True, slots=True)
class RetrievalManifestEntry:
    entry_id: str
    context_item_id: str
    source_kind: str
    source_id: str
    source_content_hash: str
    required: bool
    target_section: str
    eligibility_status: str
    eligibility_reasons: tuple[str, ...]
    eligibility_decision_hash: str
    materialization_status: str
    materialization_reasons: tuple[str, ...]
    materialized_content_hash: str | None
    rank_components: RankComponents | None
    rank_explanation: tuple[str, ...]
    final_rank: int | None
    disposition: str
    disposition_reason: str

    def __post_init__(self) -> None:
        for field in ("entry_id", "context_item_id", "source_id"):
            validate_identifier(getattr(self, field), field=field)
        if self.source_kind not in {
            "memory_record",
            "evidence",
            "governance_rule",
        }:
            raise ValidationError("manifest source_kind is invalid")
        _sha256(self.source_content_hash, "source_content_hash")
        if not isinstance(self.required, bool):
            raise ValidationError("required must be boolean")
        if self.target_section not in RANKABLE_SECTIONS:
            raise ValidationError("manifest target_section is invalid")
        _enum(
            self.eligibility_status,
            ELIGIBILITY_STATUSES,
            "eligibility_status",
        )
        _reason_tuple(self.eligibility_reasons, "eligibility_reasons")
        _sha256(self.eligibility_decision_hash, "eligibility_decision_hash")
        _enum(
            self.materialization_status,
            MATERIALIZATION_STATUSES,
            "materialization_status",
        )
        _reason_tuple(self.materialization_reasons, "materialization_reasons")
        _reason_tuple(self.rank_explanation, "rank_explanation")
        _enum(self.disposition, DISPOSITIONS, "disposition")
        _text(self.disposition_reason, "disposition_reason")
        if self.disposition == "included":
            if (
                self.eligibility_status != "eligible"
                or self.materialization_status != "materialized"
                or self.materialized_content_hash is None
                or self.rank_components is None
                or self.final_rank is None
                or self.final_rank < 0
            ):
                raise ValidationError(
                    "included entry requires eligibility, materialization and rank"
                )
            _sha256(
                self.materialized_content_hash,
                "materialized_content_hash",
            )
        elif (
            self.materialized_content_hash is not None
            or self.rank_components is not None
            or self.final_rank is not None
            or self.rank_explanation
        ):
            raise ValidationError(
                "excluded entry cannot retain materialized content or an included rank"
            )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "context_item_id": self.context_item_id,
            "disposition": self.disposition,
            "disposition_reason": self.disposition_reason,
            "eligibility_reasons": list(self.eligibility_reasons),
            "eligibility_status": self.eligibility_status,
            "eligibility_decision_hash": self.eligibility_decision_hash,
            "entry_id": self.entry_id,
            "final_rank": self.final_rank,
            "materialization_reasons": list(self.materialization_reasons),
            "materialization_status": self.materialization_status,
            "materialized_content_hash": self.materialized_content_hash,
            "rank_components": (
                None
                if self.rank_components is None
                else self.rank_components.canonical_value()
            ),
            "rank_explanation": list(self.rank_explanation),
            "required": self.required,
            "source_content_hash": self.source_content_hash,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "target_section": self.target_section,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class RetrievalManifest:
    retrieval_manifest_id: str
    retrieval_request_id: str
    task_id: str
    session_id: str
    project_scope_id: str
    task_context_finalization_id: str
    request_hash: str
    task_memory_projection_hash: str
    task_memory_projection_json: str
    finalization_hash: str
    ranking_strategy: str
    status: str
    created_at: str
    entries: tuple[RetrievalManifestEntry, ...]

    def __post_init__(self) -> None:
        for field in (
            "retrieval_manifest_id",
            "retrieval_request_id",
            "task_id",
            "session_id",
            "project_scope_id",
            "task_context_finalization_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        for field in (
            "request_hash",
            "task_memory_projection_hash",
            "finalization_hash",
        ):
            _sha256(getattr(self, field), field)
        projection = _canonical_object(
            self.task_memory_projection_json,
            "task_memory_projection_json",
        )
        if (
            sha256_canonical_json(projection)
            != self.task_memory_projection_hash
        ):
            raise ValidationError(
                "task-memory projection JSON differs from its stored hash"
            )
        _enum(self.ranking_strategy, RANKING_STRATEGIES, "ranking_strategy")
        _enum(self.status, MANIFEST_STATUSES, "manifest status")
        parse_canonical_utc(self.created_at, field="created_at")
        item_ids = [entry.context_item_id for entry in self.entries]
        entry_ids = [entry.entry_id for entry in self.entries]
        sources = [
            (entry.source_kind, entry.source_id) for entry in self.entries
        ]
        if (
            len(set(item_ids)) != len(item_ids)
            or len(set(entry_ids)) != len(entry_ids)
            or len(set(sources)) != len(sources)
        ):
            raise ValidationError(
                "retrieval manifest contains duplicate candidates or sources"
            )
        ranks = sorted(
            entry.final_rank
            for entry in self.entries
            if entry.final_rank is not None
        )
        if ranks != list(range(len(ranks))):
            raise ValidationError("included manifest ranks must be contiguous")
        if self.status == "accepted" and any(
            entry.required and entry.disposition == "excluded"
            for entry in self.entries
        ):
            raise ValidationError(
                "accepted manifest cannot exclude required context"
            )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "entries": [entry.canonical_value() for entry in self.entries],
            "finalization_hash": self.finalization_hash,
            "project_scope_id": self.project_scope_id,
            "ranking_strategy": self.ranking_strategy,
            "request_hash": self.request_hash,
            "retrieval_manifest_id": self.retrieval_manifest_id,
            "retrieval_request_id": self.retrieval_request_id,
            "session_id": self.session_id,
            "status": self.status,
            "task_context_finalization_id": self.task_context_finalization_id,
            "task_id": self.task_id,
            "task_memory_projection_hash": self.task_memory_projection_hash,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class OrderedContextEntry:
    ordered_entry_id: str
    section: str
    section_order: int
    entry_order: int
    source_kind: str
    source_id: str
    source_content_hash: str
    retrieval_manifest_entry_id: str | None
    entry_json: str

    def __post_init__(self) -> None:
        for field in ("ordered_entry_id", "source_id"):
            validate_identifier(getattr(self, field), field=field)
        if self.retrieval_manifest_entry_id is not None:
            validate_identifier(
                self.retrieval_manifest_entry_id,
                field="retrieval_manifest_entry_id",
            )
        if self.section not in CONTEXT_SECTIONS:
            raise ValidationError("ordered context section is invalid")
        expected_section_order = CONTEXT_SECTIONS.index(self.section)
        if self.section_order != expected_section_order:
            raise ValidationError("ordered context section order is invalid")
        if (
            not isinstance(self.entry_order, int)
            or isinstance(self.entry_order, bool)
            or self.entry_order < 0
        ):
            raise ValidationError("entry_order must be non-negative")
        if self.source_kind not in {
            "authoritative_i2_task",
            "authoritative_i2_authority",
            "memory_record",
            "evidence",
            "governance_rule",
        }:
            raise ValidationError("ordered context source_kind is invalid")
        if self.source_kind.startswith("authoritative_i2_"):
            if self.retrieval_manifest_entry_id is not None:
                raise ValidationError(
                    "authoritative I2 entry cannot reference retrieval rank"
                )
        elif self.retrieval_manifest_entry_id is None:
            raise ValidationError(
                "retrieved context entry requires its manifest entry"
            )
        _sha256(self.source_content_hash, "source_content_hash")
        _canonical_object(self.entry_json, "entry_json")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "entry": _canonical_object(self.entry_json, "entry_json"),
            "entry_canonical_hash": self.entry_canonical_hash,
            "entry_order": self.entry_order,
            "ordered_entry_id": self.ordered_entry_id,
            "retrieval_manifest_entry_id": self.retrieval_manifest_entry_id,
            "section": self.section,
            "section_order": self.section_order,
            "source_content_hash": self.source_content_hash,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
        }

    @property
    def entry_canonical_hash(self) -> str:
        return sha256_canonical_json(
            _canonical_object(self.entry_json, "entry_json")
        )

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class ContaminationFinding:
    finding_id: str
    reason_code: str
    source_kind: str | None
    source_id: str | None
    detail: str

    def __post_init__(self) -> None:
        validate_identifier(self.finding_id, field="finding_id")
        _text(self.reason_code, "reason_code")
        _text(self.detail, "detail")
        if (self.source_kind is None) != (self.source_id is None):
            raise ValidationError(
                "contamination source kind and identity must be paired"
            )
        if self.source_id is not None:
            validate_identifier(self.source_id, field="source_id")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "detail": self.detail,
            "finding_id": self.finding_id,
            "reason_code": self.reason_code,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class StructuredContextPackage:
    context_package_id: str
    contract_version: str
    retrieval_request_id: str
    retrieval_manifest_id: str
    retrieval_manifest_hash: str
    task_id: str
    session_id: str
    project_scope_id: str
    task_context_finalization_id: str
    task_memory_projection_hash: str
    status: str
    contamination_status: str
    created_at: str
    authoritative_task_hash: str
    authoritative_authority_hash: str
    sections_json: str
    ordered_entries: tuple[OrderedContextEntry, ...]
    contamination_findings: tuple[ContaminationFinding, ...]
    recovery_of_context_package_id: str | None = None
    recovery_relationship_hash: str | None = None

    def __post_init__(self) -> None:
        for field in (
            "context_package_id",
            "retrieval_request_id",
            "retrieval_manifest_id",
            "task_id",
            "session_id",
            "project_scope_id",
            "task_context_finalization_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        if self.recovery_of_context_package_id is not None:
            validate_identifier(
                self.recovery_of_context_package_id,
                field="recovery_of_context_package_id",
            )
            if self.recovery_of_context_package_id == self.context_package_id:
                raise ValidationError("context package cannot recover itself")
            if self.recovery_relationship_hash is None:
                raise ValidationError(
                    "recovery context requires its relationship hash"
                )
            _sha256(
                self.recovery_relationship_hash,
                "recovery_relationship_hash",
            )
        elif self.recovery_relationship_hash is not None:
            raise ValidationError(
                "non-recovery context cannot carry a recovery relationship hash"
            )
        if self.contract_version != STRUCTURED_CONTEXT_VERSION:
            raise ValidationError("unsupported structured context version")
        for field in (
            "retrieval_manifest_hash",
            "task_memory_projection_hash",
            "authoritative_task_hash",
            "authoritative_authority_hash",
        ):
            _sha256(getattr(self, field), field)
        _enum(self.status, CONTEXT_STATUSES, "context status")
        _enum(
            self.contamination_status,
            CONTAMINATION_STATUSES,
            "contamination_status",
        )
        parse_canonical_utc(self.created_at, field="created_at")
        sections = _canonical_object(self.sections_json, "sections_json")
        if set(sections) != set(CONTEXT_SECTIONS):
            raise ValidationError(
                "structured context must contain exactly the fixed sections"
            )
        if not self.ordered_entries:
            raise ValidationError("structured context requires ordered entries")
        section_orders: dict[str, list[int]] = {
            section: [] for section in CONTEXT_SECTIONS
        }
        for entry in self.ordered_entries:
            section_orders[entry.section].append(entry.entry_order)
        for section, orders in section_orders.items():
            if orders != list(range(len(orders))):
                raise ValidationError(
                    f"{section} context entry order must be contiguous"
                )
        if self.status == "accepted":
            if self.contamination_status != "clean":
                raise ValidationError(
                    "accepted context cannot be contaminated"
                )
            if self.contamination_findings:
                raise ValidationError(
                    "accepted context cannot contain contamination findings"
                )
        if self.status == "rejected_contamination":
            if (
                self.contamination_status != "contaminated"
                or not self.contamination_findings
            ):
                raise ValidationError(
                    "contamination rejection requires preserved findings"
                )

    @property
    def bridge_context_ready(self) -> bool:
        return self.status == "accepted" and self.contamination_status == "clean"

    def canonical_value(self) -> dict[str, Any]:
        return {
            "authoritative_authority_hash": self.authoritative_authority_hash,
            "authoritative_task_hash": self.authoritative_task_hash,
            "bridge_context_ready": self.bridge_context_ready,
            "contamination_findings": [
                finding.canonical_value()
                for finding in self.contamination_findings
            ],
            "contamination_status": self.contamination_status,
            "context_package_id": self.context_package_id,
            "contract_version": self.contract_version,
            "created_at": self.created_at,
            "ordered_context_manifest": [
                entry.canonical_value() for entry in self.ordered_entries
            ],
            "project_scope_id": self.project_scope_id,
            "recovery_of_context_package_id":
                self.recovery_of_context_package_id,
            "recovery_relationship_hash": self.recovery_relationship_hash,
            "retrieval_manifest_hash": self.retrieval_manifest_hash,
            "retrieval_manifest_id": self.retrieval_manifest_id,
            "retrieval_request_id": self.retrieval_request_id,
            "sections": _canonical_object(self.sections_json, "sections_json"),
            "session_id": self.session_id,
            "status": self.status,
            "task_context_finalization_id": self.task_context_finalization_id,
            "task_id": self.task_id,
            "task_memory_projection_hash": self.task_memory_projection_hash,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class RecoveryRelationship:
    recovery_context_package_id: str
    rejected_context_package_id: str
    recovery_reason: str
    excluded_source_ids: tuple[str, ...]
    preserved_findings_json: str
    created_at: str

    def __post_init__(self) -> None:
        for field in (
            "recovery_context_package_id",
            "rejected_context_package_id",
        ):
            validate_identifier(getattr(self, field), field=field)
        if self.recovery_context_package_id == self.rejected_context_package_id:
            raise ValidationError("recovery relationship cannot be self-linked")
        _text(self.recovery_reason, "recovery_reason")
        if not self.excluded_source_ids:
            raise ValidationError("recovery requires explicit excluded sources")
        for source_id in self.excluded_source_ids:
            validate_identifier(source_id, field="excluded_source_id")
        if len(set(self.excluded_source_ids)) != len(
            self.excluded_source_ids
        ):
            raise ValidationError("recovery exclusions cannot contain duplicates")
        findings = _canonical_value(
            self.preserved_findings_json,
            "preserved_findings_json",
        )
        if not isinstance(findings, list) or not findings:
            raise ValidationError(
                "recovery must preserve contamination findings"
            )
        parse_canonical_utc(self.created_at, field="created_at")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "excluded_source_ids": list(self.excluded_source_ids),
            "preserved_findings": _canonical_value(
                self.preserved_findings_json,
                "preserved_findings_json",
            ),
            "recovery_context_package_id":
                self.recovery_context_package_id,
            "recovery_reason": self.recovery_reason,
            "rejected_context_package_id": self.rejected_context_package_id,
        }

    @property
    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_value())

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class RetrievalAssemblyResult:
    retrieval_request: RetrievalRequest
    retrieval_manifest: RetrievalManifest
    context_package: StructuredContextPackage
    accepted: bool
    bridge_context_ready: bool
    rejection_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.accepted != (self.context_package.status == "accepted"):
            raise ValidationError("result acceptance conflicts with context status")
        if self.bridge_context_ready != self.context_package.bridge_context_ready:
            raise ValidationError(
                "result bridge readiness conflicts with context package"
            )
        _reason_tuple(self.rejection_reasons, "rejection_reasons")
        if self.accepted == bool(self.rejection_reasons):
            raise ValidationError(
                "accepted result and rejection reasons conflict"
            )
        if (
            self.retrieval_request.retrieval_request_id
            != self.retrieval_manifest.retrieval_request_id
            or self.retrieval_manifest.retrieval_manifest_id
            != self.context_package.retrieval_manifest_id
        ):
            raise ValidationError("result identities are not consistently bound")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "bridge_context_ready": self.bridge_context_ready,
            "context_package_hash": self.context_package.content_hash,
            "rejection_reasons": list(self.rejection_reasons),
            "retrieval_manifest_hash": self.retrieval_manifest.content_hash,
            "retrieval_request_hash": self.retrieval_request.content_hash,
        }

    @property
    def content_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class ContextReadinessFinding:
    """One deterministic reason a historical package is not currently ready."""

    reason_code: str
    detail: str
    source_kind: str | None = None
    source_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.reason_code, "reason_code")
        _text(self.detail, "detail")
        if (self.source_kind is None) != (self.source_id is None):
            raise ValidationError(
                "readiness source kind and identity must be paired"
            )
        if self.source_id is not None:
            validate_identifier(self.source_id, field="source_id")

    def canonical_value(self) -> dict[str, Any]:
        return {
            "detail": self.detail,
            "reason_code": self.reason_code,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
        }


@dataclass(frozen=True, slots=True)
class ContextReadinessAssessment:
    """Read-only current readiness decision over one immutable attempt."""

    context_package_id: str
    evaluated_at: str
    current_bridge_context_ready: bool
    current_findings: tuple[ContextReadinessFinding, ...]

    def __post_init__(self) -> None:
        validate_identifier(
            self.context_package_id,
            field="context_package_id",
        )
        parse_canonical_utc(self.evaluated_at, field="evaluated_at")
        if not isinstance(self.current_bridge_context_ready, bool):
            raise ValidationError(
                "current_bridge_context_ready must be boolean"
            )
        if any(
            not isinstance(finding, ContextReadinessFinding)
            for finding in self.current_findings
        ):
            raise ValidationError(
                "current_findings must contain readiness findings"
            )
        canonical_findings = tuple(
            finding.canonical_value() for finding in self.current_findings
        )
        serialized_findings = {
            canonical_json_text(value) for value in canonical_findings
        }
        if len(serialized_findings) != len(canonical_findings):
            raise ValidationError("current_findings cannot contain duplicates")
        if self.current_bridge_context_ready == bool(self.current_findings):
            raise ValidationError(
                "current readiness and current findings conflict"
            )

    def canonical_value(self) -> dict[str, Any]:
        return {
            "context_package_id": self.context_package_id,
            "current_bridge_context_ready": self.current_bridge_context_ready,
            "current_findings": [
                finding.canonical_value() for finding in self.current_findings
            ],
            "evaluated_at": self.evaluated_at,
        }

    @property
    def decision_hash(self) -> str:
        return sha256_canonical_json(self.canonical_value())
