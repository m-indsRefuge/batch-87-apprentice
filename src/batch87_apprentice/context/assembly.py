"""Pure structured-context assembly and independent contamination inspection."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_canonical_json

from .contracts import (
    CONTEXT_SECTIONS,
    ContaminationFinding,
    OrderedContextEntry,
    RankedCandidate,
    RetrievalManifestEntry,
)


def _require_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{field} must be an object")
    return value


def build_authoritative_task_section(
    authoritative_i2: Mapping[str, Any],
    active_uncertainties: tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    """Build the canonical task section from exact I2 and I3-D truth."""

    task = _require_mapping(authoritative_i2.get("task"), "I2 task")
    session = _require_mapping(
        authoritative_i2.get("session"),
        "I2 session",
    )
    operation = _require_mapping(
        task.get("requested_operation"),
        "I2 requested operation",
    )
    return {
        "active_non_blocking_uncertainties": [
            {
                "impact": uncertainty["impact"],
                "record_id": uncertainty["record_id"],
                "statement": uncertainty["uncertainty_statement"],
            }
            for uncertainty in active_uncertainties
        ],
        "current_state": {
            "session_status": session["status"],
            "task_status": authoritative_i2["task_status"],
        },
        "effective_at": task["effective_at"],
        "expected_output_schema_id": task["expected_output_schema_id"],
        "governing_constraints": list(task["governing_constraints"]),
        "model_boundary": {
            "authority": "none",
            "tool_access": "none",
            "statement": (
                "A future model may observe this context but has no "
                "authority and no tool access."
            ),
        },
        "objective": task["objective"],
        "prohibited_actions": list(task["prohibited_actions"]),
        "project_scope_id": task["project_scope_id"],
        "requested_operation": {
            "action_class": operation["action_class"],
            "autonomous": operation["autonomous"],
            "name": operation["name"],
        },
        "requested_scope_id": task["requested_scope_id"],
        "requesting_principal": task["requesting_principal"],
        "session_id": task["session_id"],
        "stop_conditions": list(task["stop_conditions"]),
        "task_id": task["task_id"],
        "task_type": task["task_type"],
    }


def build_authoritative_authority_section(
    authoritative_i2: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the canonical authority section from exact I2 truth."""

    decision = _require_mapping(
        authoritative_i2.get("decision"),
        "I2 governance decision",
    )
    profile = _require_mapping(
        authoritative_i2.get("permission_profile"),
        "I2 permission profile",
    )
    return {
        "authority_classification": "authoritative system decision",
        "authority_inputs": list(authoritative_i2["authority_inputs"]),
        "context_classification": "context supplied to a future model",
        "governance_decision": {
            "decided_at": decision["decided_at"],
            "governance_decision_id": decision["governance_decision_id"],
            "governing_rule_ids": list(decision["governing_rule_ids"]),
            "outcome": decision["outcome"],
            "reasons": list(decision["reasons"]),
            "requested_operation": decision["requested_operation"],
        },
        "governing_rule_references": list(authoritative_i2["rules"]),
        "human_approvals": list(authoritative_i2["human_approval_inputs"]),
        "operation_definition": authoritative_i2["operation_definition"],
        "permission_profile": profile,
        "read_only_statement": (
            "A future model may observe but may not alter this authority."
        ),
        "stop_event": authoritative_i2["stop_event"],
    }


def _authoritative_binding_mismatch_specs(
    *,
    sections_json: str,
    ordered_entries: tuple[OrderedContextEntry, ...],
    authoritative_task_hash: str,
    authoritative_authority_hash: str,
    expected_task: Mapping[str, Any],
    expected_authority: Mapping[str, Any],
    expected_task_id: str,
    expected_authority_id: str,
    stored_entry_hashes: Mapping[str, str] | None = None,
) -> tuple[tuple[str, str, str, str], ...]:
    """Compare persisted/attempted authoritative material with independent truth."""

    try:
        sections_value = parse_json(sections_json)
    except ValidationError:
        sections_value = None
    sections = sections_value if isinstance(sections_value, dict) else None
    hash_overrides = stored_entry_hashes or {}
    mismatches: list[tuple[str, str, str, str]] = []
    specifications = (
        (
            "task",
            "authoritative_i2_task",
            expected_task_id,
            expected_task,
            authoritative_task_hash,
            "authoritative_task_content_mismatch",
        ),
        (
            "authority",
            "authoritative_i2_authority",
            expected_authority_id,
            expected_authority,
            authoritative_authority_hash,
            "authoritative_authority_content_mismatch",
        ),
    )
    for (
        section,
        source_kind,
        source_id,
        expected_value,
        package_hash,
        reason_code,
    ) in specifications:
        expected_json = canonical_json_text(expected_value)
        expected_hash = sha256_canonical_json(expected_value)
        section_entries = tuple(
            entry for entry in ordered_entries if entry.section == section
        )
        source_entries = tuple(
            entry
            for entry in ordered_entries
            if entry.source_kind == source_kind
        )
        failed_checks: list[str] = []
        if len(section_entries) != 1:
            failed_checks.append("section_entry_count")
        if len(source_entries) != 1:
            failed_checks.append("source_kind_count")
        entry = section_entries[0] if len(section_entries) == 1 else None
        if (
            entry is None
            or len(source_entries) != 1
            or source_entries[0].ordered_entry_id != entry.ordered_entry_id
        ):
            failed_checks.append("section_source_binding")
        if entry is not None:
            if entry.section_order != CONTEXT_SECTIONS.index(section):
                failed_checks.append("section_order")
            if entry.entry_order != 0:
                failed_checks.append("entry_order")
            if entry.source_kind != source_kind:
                failed_checks.append("source_kind")
            if entry.source_id != source_id:
                failed_checks.append("source_id")
            if entry.retrieval_manifest_entry_id is not None:
                failed_checks.append("retrieval_manifest_entry_id")
            if entry.entry_json != expected_json:
                failed_checks.append("entry_json")
            stored_entry_hash = hash_overrides.get(
                entry.ordered_entry_id,
                entry.entry_canonical_hash,
            )
            if stored_entry_hash != expected_hash:
                failed_checks.append("entry_canonical_hash")
            if entry.source_content_hash != expected_hash:
                failed_checks.append("source_content_hash")
        if package_hash != expected_hash:
            failed_checks.append("package_hash")
        section_value = None if sections is None else sections.get(section)
        if section_value != expected_value:
            failed_checks.append("sections_json")
        if not failed_checks:
            continue

        actual_entry_hashes = sorted(
            {
                hash_overrides.get(
                    candidate.ordered_entry_id,
                    candidate.entry_canonical_hash,
                )
                for candidate in (*section_entries, *source_entries)
            }
        )
        actual_source_ids = sorted(
            {
                candidate.source_id
                for candidate in (*section_entries, *source_entries)
            }
        )
        section_hash = (
            sha256_canonical_json(section_value)
            if isinstance(section_value, Mapping)
            else "missing_or_invalid"
        )
        detail = (
            f"authoritative {section} binding differs from the persisted "
            "attempt-time projection "
            f"(failed_checks={','.join(sorted(set(failed_checks)))}; "
            f"expected_hash={expected_hash}; "
            f"section_hash={section_hash}; "
            f"entry_hashes={','.join(actual_entry_hashes) or 'none'}; "
            f"package_hash={package_hash}; "
            f"source_ids={','.join(actual_source_ids) or 'none'})"
        )
        mismatches.append((reason_code, source_kind, source_id, detail))
    return tuple(mismatches)


class ContextAssembler:
    """Build provider-neutral sections from verified I2 and ranked I3-D inputs."""

    @staticmethod
    def task_section(
        authoritative_i2: Mapping[str, Any],
        *,
        active_uncertainties: tuple[Mapping[str, Any], ...],
    ) -> dict[str, Any]:
        return build_authoritative_task_section(
            authoritative_i2,
            active_uncertainties,
        )

    @staticmethod
    def authority_section(
        authoritative_i2: Mapping[str, Any],
    ) -> dict[str, Any]:
        return build_authoritative_authority_section(authoritative_i2)

    def assemble(
        self,
        *,
        authoritative_i2: Mapping[str, Any],
        active_uncertainties: tuple[Mapping[str, Any], ...],
        ranked_candidates: tuple[RankedCandidate, ...],
        manifest_entries: Mapping[str, RetrievalManifestEntry],
        identifier_factory: Callable[[], str],
    ) -> tuple[
        str,
        tuple[OrderedContextEntry, ...],
        str,
        str,
    ]:
        if not callable(identifier_factory):
            raise TypeError("identifier_factory must be callable")
        task = build_authoritative_task_section(
            authoritative_i2,
            active_uncertainties,
        )
        authority = build_authoritative_authority_section(authoritative_i2)
        sections: dict[str, Any] = {
            "task": task,
            "authority": authority,
            "policy": [],
            "evidence": [],
            "memory": [],
        }
        for ranked in ranked_candidates:
            content = parse_json(ranked.candidate.materialized_json or "{}")
            if not isinstance(content, dict):
                raise ValidationError(
                    "materialized ranked context must be an object"
                )
            sections[ranked.candidate.target_section].append(content)

        task_hash = sha256_canonical_json(task)
        authority_hash = sha256_canonical_json(authority)
        ordered: list[OrderedContextEntry] = [
            OrderedContextEntry(
                ordered_entry_id=identifier_factory(),
                section="task",
                section_order=0,
                entry_order=0,
                source_kind="authoritative_i2_task",
                source_id=authoritative_i2["task"]["task_id"],
                source_content_hash=task_hash,
                retrieval_manifest_entry_id=None,
                entry_json=canonical_json_text(task),
            ),
            OrderedContextEntry(
                ordered_entry_id=identifier_factory(),
                section="authority",
                section_order=1,
                entry_order=0,
                source_kind="authoritative_i2_authority",
                source_id=authoritative_i2["decision"][
                    "governance_decision_id"
                ],
                source_content_hash=authority_hash,
                retrieval_manifest_entry_id=None,
                entry_json=canonical_json_text(authority),
            ),
        ]
        section_counts = {section: 0 for section in CONTEXT_SECTIONS}
        section_counts["task"] = 1
        section_counts["authority"] = 1
        for ranked in ranked_candidates:
            candidate = ranked.candidate
            manifest_entry = manifest_entries.get(candidate.context_item_id)
            if (
                manifest_entry is None
                or manifest_entry.disposition != "included"
                or manifest_entry.materialized_content_hash
                != candidate.materialized_content_hash
            ):
                raise ValidationError(
                    "ranked context lacks its exact materialized manifest binding"
                )
            entry_order = section_counts[candidate.target_section]
            ordered.append(
                OrderedContextEntry(
                    ordered_entry_id=identifier_factory(),
                    section=candidate.target_section,
                    section_order=CONTEXT_SECTIONS.index(
                        candidate.target_section
                    ),
                    entry_order=entry_order,
                    source_kind=candidate.source_kind,
                    source_id=candidate.source_id,
                    source_content_hash=candidate.source_content_hash,
                    retrieval_manifest_entry_id=manifest_entry.entry_id,
                    entry_json=candidate.materialized_json or "{}",
                )
            )
            section_counts[candidate.target_section] += 1
        identifiers = [entry.ordered_entry_id for entry in ordered]
        if len(set(identifiers)) != len(identifiers):
            raise ValidationError(
                "identifier factory returned duplicate ordered-entry identities"
            )
        sections_json = canonical_json_text(sections)
        ordered.sort(
            key=lambda entry: (entry.section_order, entry.entry_order)
        )
        return sections_json, tuple(ordered), task_hash, authority_hash


_CAPABILITY_KEYS = frozenset(
    {
        "communication_handle",
        "database_connection",
        "executable_capability",
        "filesystem_handle",
        "network_handle",
        "raw_sql_handle",
        "repository_handle",
        "shell_handle",
        "sql_handle",
        "credential_handle",
        "tool_handle",
    }
)


def _capability_paths(value: object, *, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            child = f"{path}.{key}"
            if (
                key in _CAPABILITY_KEYS
                and nested is not None
                and nested is not False
                and nested != ""
            ):
                found.append(child)
            found.extend(_capability_paths(nested, path=child))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(_capability_paths(nested, path=f"{path}[{index}]"))
    return found


class ContaminationInspector:
    """Inspect classification, provenance, hashes and structural capabilities."""

    def inspect(
        self,
        *,
        sections_json: str,
        ordered_entries: tuple[OrderedContextEntry, ...],
        authoritative_task_hash: str,
        authoritative_authority_hash: str,
        task_memory_projection_json: str,
        manifest_entries: tuple[RetrievalManifestEntry, ...],
        independent_materializations: Mapping[str, str],
        source_snapshots: Mapping[tuple[str, str], Mapping[str, Any]],
        task_id: str,
        project_scope_id: str,
        identifier_factory: Callable[[], str],
    ) -> tuple[ContaminationFinding, ...]:
        sections = parse_json(sections_json)
        if not isinstance(sections, dict):
            raise ValidationError("assembled sections must be an object")
        findings: list[tuple[str, str | None, str | None, str]] = []
        projection = _require_mapping(
            parse_json(task_memory_projection_json),
            "attempt-time task-memory projection",
        )
        authoritative_i2 = _require_mapping(
            projection.get("authoritative_i2"),
            "attempt-time authoritative I2 projection",
        )
        uncertainty_projection = _require_mapping(
            projection.get("uncertainties"),
            "attempt-time uncertainty projection",
        )
        active = uncertainty_projection.get("active")
        if not isinstance(active, list) or any(
            not isinstance(uncertainty, Mapping)
            for uncertainty in active
        ):
            raise ValidationError(
                "attempt-time active uncertainties must be an array of objects"
            )
        expected_task = build_authoritative_task_section(
            authoritative_i2,
            tuple(active),
        )
        expected_authority = build_authoritative_authority_section(
            authoritative_i2
        )
        findings.extend(
            _authoritative_binding_mismatch_specs(
                sections_json=sections_json,
                ordered_entries=ordered_entries,
                authoritative_task_hash=authoritative_task_hash,
                authoritative_authority_hash=authoritative_authority_hash,
                expected_task=expected_task,
                expected_authority=expected_authority,
                expected_task_id=authoritative_i2["task"]["task_id"],
                expected_authority_id=authoritative_i2["decision"][
                    "governance_decision_id"
                ],
            )
        )
        manifest_by_id = {
            entry.entry_id: entry for entry in manifest_entries
        }
        included_ids = {
            entry.entry_id
            for entry in manifest_entries
            if entry.disposition == "included"
        }
        excluded_sources = {
            (entry.source_kind, entry.source_id)
            for entry in manifest_entries
            if entry.disposition == "excluded"
        }

        seen_sources: set[tuple[str, str]] = set()
        for entry in ordered_entries:
            source_key = (entry.source_kind, entry.source_id)
            if source_key in seen_sources:
                findings.append(
                    (
                        "duplicate_context_source",
                        entry.source_kind,
                        entry.source_id,
                        "the assembled package repeats a source identity",
                    )
                )
            seen_sources.add(source_key)
            if entry.retrieval_manifest_entry_id is not None:
                manifest_entry = manifest_by_id.get(
                    entry.retrieval_manifest_entry_id
                )
                if (
                    manifest_entry is None
                    or entry.retrieval_manifest_entry_id not in included_ids
                ):
                    findings.append(
                        (
                            "untracked_material",
                            entry.source_kind,
                            entry.source_id,
                            "assembled material lacks an included manifest entry",
                        )
                    )
                elif (
                    manifest_entry.source_kind != entry.source_kind
                    or manifest_entry.source_id != entry.source_id
                    or manifest_entry.source_content_hash
                    != entry.source_content_hash
                ):
                    findings.append(
                        (
                            "manifest_source_mismatch",
                            entry.source_kind,
                            entry.source_id,
                            "ordered material differs from its manifest source",
                        )
                    )
                else:
                    expected_json = independent_materializations.get(
                        manifest_entry.entry_id
                    )
                    expected_hash = (
                        None
                        if expected_json is None
                        else sha256_canonical_json(parse_json(expected_json))
                    )
                    if (
                        expected_json is None
                        or expected_hash
                        != manifest_entry.materialized_content_hash
                        or expected_hash != entry.entry_canonical_hash
                        or expected_json != entry.entry_json
                    ):
                        findings.append(
                            (
                                "materialized_content_mismatch",
                                entry.source_kind,
                                entry.source_id,
                                (
                                    "ordered context differs from the "
                                    "independent deterministic safe "
                                    "materialization"
                                ),
                            )
                        )
            if source_key in excluded_sources:
                findings.append(
                    (
                        "excluded_source_present",
                        entry.source_kind,
                        entry.source_id,
                        "an excluded retrieval source appears in context",
                    )
                )

            snapshot = source_snapshots.get(source_key)
            if (
                entry.source_kind
                not in {
                    "authoritative_i2_task",
                    "authoritative_i2_authority",
                }
                and snapshot is None
            ):
                findings.append(
                    (
                        "source_missing",
                        entry.source_kind,
                        entry.source_id,
                        "an assembled source no longer exists",
                    )
                )
                continue
            if snapshot is None:
                continue
            current_hash = snapshot.get("content_hash")
            if current_hash != entry.source_content_hash:
                findings.append(
                    (
                        "source_hash_drift",
                        entry.source_kind,
                        entry.source_id,
                        "the current source hash differs from assembled context",
                    )
                )
            if entry.source_kind == "evidence":
                evidence_kind = snapshot.get("evidence_kind")
                if snapshot.get("task_bound") is False:
                    findings.append(
                        (
                            "source_not_task_bound",
                            entry.source_kind,
                            entry.source_id,
                            "evidence is not bound to the requested task and project",
                        )
                    )
                if evidence_kind == "controlled_prompt":
                    findings.append(
                        (
                            "controlled_prompt",
                            entry.source_kind,
                            entry.source_id,
                            "controlled prompt evidence entered ordinary context",
                        )
                    )
                if evidence_kind == "controlled_output":
                    findings.append(
                        (
                            "controlled_output",
                            entry.source_kind,
                            entry.source_id,
                            "controlled output evidence entered ordinary context",
                        )
                    )
                if snapshot.get("controlled_resilience"):
                    findings.append(
                        (
                            "controlled_resilience_evidence",
                            entry.source_kind,
                            entry.source_id,
                            "evidence is linked to controlled resilience",
                        )
                    )
                if evidence_kind == "model_output":
                    findings.append(
                        (
                            "model_output_evidence",
                            entry.source_kind,
                            entry.source_id,
                            "model output evidence entered ordinary context",
                        )
                    )
            if entry.source_kind == "memory_record":
                if (
                    snapshot.get("record_family") == "evaluation_evidence"
                    or snapshot.get("record_type")
                    == "controlled_governance_resilience_run"
                ):
                    findings.append(
                        (
                            "controlled_resilience_record",
                            entry.source_kind,
                            entry.source_id,
                            "a raw controlled-resilience record entered ordinary context",
                        )
                    )
                if (
                    snapshot.get("record_family") == "episodic_memory"
                    and snapshot.get("record_type") == "lesson_candidate"
                ):
                    findings.append(
                        (
                            "lesson_candidate_as_approved",
                            entry.source_kind,
                            entry.source_id,
                            "a candidate lesson is represented as approved",
                        )
                    )
                lifecycle = snapshot.get("lifecycle_state")
                if lifecycle in {"revoked", "deleted"}:
                    findings.append(
                        (
                            f"source_{lifecycle}",
                            entry.source_kind,
                            entry.source_id,
                            f"a {lifecycle} source appears in context",
                        )
                    )
                if snapshot.get("integrity_status") not in {
                    "valid",
                    "not_applicable",
                }:
                    findings.append(
                        (
                            "source_integrity_invalid",
                            entry.source_kind,
                            entry.source_id,
                            "an integrity-invalid source appears in context",
                        )
                    )
                if snapshot.get("task_id") not in {None, task_id}:
                    findings.append(
                        (
                            "cross_task_source",
                            entry.source_kind,
                            entry.source_id,
                            "a source is bound to another task",
                        )
                    )
                if snapshot.get("project_scope_id") != project_scope_id:
                    findings.append(
                        (
                            "cross_project_source",
                            entry.source_kind,
                            entry.source_id,
                            "a source belongs to another project",
                        )
                    )
            if (
                entry.source_kind == "governance_rule"
                and snapshot.get("task_bound") is False
            ):
                findings.append(
                    (
                        "source_not_task_bound",
                        entry.source_kind,
                        entry.source_id,
                        "governance rule is not bound to the requested task and project",
                    )
                )

        reconstructed_sections: dict[str, Any] = {}
        for section in CONTEXT_SECTIONS:
            values = [
                parse_json(entry.entry_json)
                for entry in ordered_entries
                if entry.section == section
            ]
            reconstructed_sections[section] = (
                values[0] if section in {"task", "authority"} and values else values
            )
        if reconstructed_sections != sections:
            findings.append(
                (
                    "untracked_material",
                    None,
                    None,
                    "section content does not match the ordered context manifest",
                )
            )
        for path in _capability_paths(sections):
            findings.append(
                (
                    "executable_capability_exposed",
                    None,
                    None,
                    f"structured executable capability appears at {path}",
                )
            )

        unique = sorted(
            set(findings),
            key=lambda item: (
                item[0],
                item[1] or "",
                item[2] or "",
                item[3],
            ),
        )
        results = tuple(
            ContaminationFinding(
                finding_id=identifier_factory(),
                reason_code=reason,
                source_kind=source_kind,
                source_id=source_id,
                detail=detail,
            )
            for reason, source_kind, source_id, detail in unique
        )
        ids = [finding.finding_id for finding in results]
        if len(set(ids)) != len(ids):
            raise ValidationError(
                "identifier factory returned duplicate contamination identities"
            )
        return results
