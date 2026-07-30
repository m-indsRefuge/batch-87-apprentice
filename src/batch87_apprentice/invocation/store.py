"""Governed persistence and reconstruction for B87-I4-B invocations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import sqlite3
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import (
    ConflictError,
    IntegrityInspectionError,
    NotFoundError,
    ValidationError,
)
from batch87_apprentice.common.hashing import (
    hashes_match,
    sha256_bytes,
    sha256_canonical_json,
)
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.context.retrieval import ContextRetrievalService
from batch87_apprentice.memory.self_episodic_repository import (
    SelfEpisodicMemoryRepository,
)
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.contracts import ReferenceAnchor
from batch87_apprentice.persistence.task_runtime_store import (
    transition_task_in_transaction,
)
from batch87_apprentice.persistence.transactions import PersistenceKernel
from batch87_apprentice.providers.contracts import (
    CapabilityProfile,
    ProviderCallResult,
    ProviderConfigurationSnapshot,
    ProviderDescriptor,
    validate_provider_result_against_configuration,
)

from .contracts import (
    APPRENTICE_RESPONSE_PROTOCOL,
    APPRENTICE_RESPONSE_PROTOCOL_VERSION,
    INVOCATION_CONTRACT_VERSION,
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
)
from .processing import process_raw_output, task_completion_disposition
from .schemas import resolve_response_schema


@dataclass(frozen=True, slots=True)
class PreparedInvocation:
    request: InvocationRequest
    task_section: Mapping[str, Any]
    allowed_memory_ids: frozenset[str]
    allowed_evidence_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class PreparationOutcome:
    prepared: PreparedInvocation | None
    existing: InvocationReconstruction | None

    def __post_init__(self) -> None:
        if (self.prepared is None) == (self.existing is None):
            raise ValidationError(
                "preparation outcome must be new or reconstructed, not both"
            )


@dataclass(frozen=True, slots=True)
class _PublicBindings:
    package: Mapping[str, Any]
    manifest: Mapping[str, Any]
    identity: Mapping[str, Any]
    current_ready: bool
    identity_current: bool


def _provider_descriptor_from_value(value: object) -> ProviderDescriptor:
    if not isinstance(value, Mapping):
        raise IntegrityInspectionError("stored provider descriptor is invalid")
    expected = {
        "adapter_contract_version",
        "capability_profile",
        "provider_configuration",
        "provider_configuration_hash",
        "provider_id",
        "provider_mode",
        "provider_name",
        "transport_kind",
    }
    if set(value) != expected or not isinstance(
        value["capability_profile"],
        Mapping,
    ):
        raise IntegrityInspectionError("stored provider descriptor shape is invalid")
    try:
        capability = CapabilityProfile(**dict(value["capability_profile"]))
        return ProviderDescriptor(
            provider_id=value["provider_id"],
            provider_name=value["provider_name"],
            provider_mode=value["provider_mode"],
            adapter_contract_version=value["adapter_contract_version"],
            transport_kind=value["transport_kind"],
            capability_profile=capability,
            provider_configuration_json=canonical_json_text(
                value["provider_configuration"]
            ),
            provider_configuration_hash=value["provider_configuration_hash"],
        )
    except (TypeError, ValidationError) as exc:
        raise IntegrityInspectionError(
            "stored provider descriptor cannot be reconstructed"
        ) from exc


def _issues_json(issues: tuple[Any, ...]) -> str:
    return canonical_json_text([issue.canonical_value() for issue in issues])


class InvocationStore:
    """Own I4-B transactions while consuming only public I4-A read surfaces."""

    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config
        self._kernel = PersistenceKernel(config)
        self._context = ContextRetrievalService(config)
        self._identity = SelfEpisodicMemoryRepository(self._kernel)

    @staticmethod
    def _submission(
        spec: InvocationSpec,
        descriptor: ProviderDescriptor,
    ) -> tuple[str, str]:
        value = {
            "provider_descriptor": descriptor.canonical_value(),
            "spec": spec.canonical_value(),
        }
        return canonical_json_text(value), sha256_canonical_json(value)

    @staticmethod
    def _validate_model_binding(
        spec: InvocationSpec,
        identity: Mapping[str, Any],
    ) -> bool:
        payload = identity.get("runtime_identity")
        runtime = identity.get("runtime_instance")
        record = identity.get("record")
        integrity = identity.get("integrity")
        if not all(
            isinstance(value, Mapping)
            for value in (payload, runtime, record, integrity)
        ):
            raise IntegrityInspectionError(
                "runtime identity reconstruction is incomplete"
            )
        expected = ModelDescriptor(
            model_name=payload["base_model"],
            model_revision=payload["model_revision"],
            quantisation=payload["quantisation"],
            active_adapter=payload["active_adapter"],
            context_limit=payload["context_limit"],
        )
        if expected != spec.model_descriptor:
            raise ValidationError(
                "model descriptor differs from factual runtime identity"
            )
        if (
            spec.inference_configuration.max_output_tokens
            > spec.model_descriptor.context_limit
        ):
            raise ValidationError(
                "max_output_tokens exceeds the factual model context limit"
            )
        if payload["runtime_provider"] != spec.provider_id:
            raise ValidationError(
                "provider differs from factual runtime identity"
            )
        if identity["content_hash"] != spec.runtime_identity_hash:
            raise ValidationError("runtime identity hash differs")
        if record["record_id"] != spec.runtime_identity_id:
            raise ValidationError("runtime identity identifier differs")
        if record["project_scope_id"] != spec.project_scope_id:
            raise ValidationError("runtime identity project scope differs")
        if runtime["runtime_instance_id"] != payload["runtime_instance_id"]:
            raise IntegrityInspectionError(
                "runtime identity instance binding differs"
            )
        if runtime["started_at"] != payload["runtime_started_at"]:
            raise IntegrityInspectionError(
                "runtime identity start-time binding differs"
            )
        return bool(
            integrity["valid"]
            and record["lifecycle_state"] == "active"
            and record["approval_status"] in {"approved", "not_required"}
            and record["integrity_status"] == "valid"
            and runtime["status"] == "running"
            and runtime["stopped_at"] is None
        )

    def _public_bindings(
        self,
        spec: InvocationSpec,
        descriptor: ProviderDescriptor,
        *,
        evaluated_at: str,
        require_current_ready: bool,
    ) -> _PublicBindings:
        package_result = self._context.reconstruct_context_package(
            spec.context_package_id
        )
        package = package_result["value"]
        if (
            not package_result["integrity_verified"]
            or not package_result["historical_integrity_verified"]
            or package_result["content_hash"] != spec.context_package_hash
            or package["context_package_id"] != spec.context_package_id
            or package["task_id"] != spec.task_id
            or package["session_id"] != spec.session_id
            or package["project_scope_id"] != spec.project_scope_id
            or package["status"] != "accepted"
            or package["contamination_status"] != "clean"
            or not package["bridge_context_ready"]
        ):
            raise ValidationError(
                "I4-A context package is not an exact accepted clean binding"
            )
        manifest_result = self._context.reconstruct_retrieval_manifest(
            package["retrieval_manifest_id"]
        )
        manifest = manifest_result["value"]
        if (
            not manifest_result["integrity_verified"]
            or manifest_result["content_hash"]
            != package["retrieval_manifest_hash"]
            or manifest["task_id"] != spec.task_id
            or manifest["session_id"] != spec.session_id
            or manifest["project_scope_id"] != spec.project_scope_id
            or manifest["task_context_finalization_id"]
            != package["task_context_finalization_id"]
            or manifest["task_memory_projection_hash"]
            != package["task_memory_projection_hash"]
            or manifest["status"] != "accepted"
        ):
            raise IntegrityInspectionError(
                "I4-A manifest and package bindings cannot be reproduced"
            )
        readiness = self._context.assess_context_readiness(
            spec.context_package_id,
            evaluated_at,
        )
        if readiness["context_package_id"] != spec.context_package_id:
            raise IntegrityInspectionError(
                "I4-A readiness identity cannot be reproduced"
            )
        current_ready = bool(readiness["current_bridge_context_ready"])
        if require_current_ready and not current_ready:
            raise ValidationError("I4-A context is not currently bridge-ready")

        identity = self._identity.reconstruct(spec.runtime_identity_id)
        identity_current = self._validate_model_binding(spec, identity)
        if require_current_ready and not identity_current:
            raise ValidationError(
                "runtime identity is not current, active, and integrity-valid"
            )
        if descriptor.provider_id != spec.provider_id:
            raise ValidationError("provider descriptor and invocation differ")
        resolve_response_schema(
            spec.output_schema_id,
            spec.output_schema_hash,
        )
        sections = package.get("sections")
        if not isinstance(sections, Mapping):
            raise IntegrityInspectionError("I4-A package sections are invalid")
        task = sections.get("task")
        authority = sections.get("authority")
        if not isinstance(task, Mapping) or not isinstance(authority, Mapping):
            raise IntegrityInspectionError(
                "I4-A authoritative sections are invalid"
            )
        if task.get("expected_output_schema_id") != spec.output_schema_id:
            raise ValidationError(
                "task output schema and invocation output schema differ"
            )
        return _PublicBindings(
            package=package,
            manifest=manifest,
            identity=identity,
            current_ready=current_ready,
            identity_current=identity_current,
        )

    @staticmethod
    def _packet(
        spec: InvocationSpec,
        descriptor: ProviderDescriptor,
        bindings: _PublicBindings,
    ) -> ModelInputPacket:
        package = bindings.package
        manifest = bindings.manifest
        identity = bindings.identity
        sections = package["sections"]
        task = sections["task"]
        authority = sections["authority"]
        payload = identity["runtime_identity"]
        identity_projection = {
            "active_adapter": payload["active_adapter"],
            "agent_entity_id": payload["agent_entity_id"],
            "context_limit": payload["context_limit"],
            "current_permission_summary": authority["permission_profile"],
            "limitations": {
                "prohibited_actions": task["prohibited_actions"],
                "stop_conditions": task["stop_conditions"],
            },
            "model_name": payload["base_model"],
            "model_revision": payload["model_revision"],
            "quantisation": payload["quantisation"],
            "runtime_identity_id": spec.runtime_identity_id,
            "runtime_provider": payload["runtime_provider"],
        }
        output_contract = {
            "protocol": APPRENTICE_RESPONSE_PROTOCOL,
            "protocol_version": APPRENTICE_RESPONSE_PROTOCOL_VERSION,
            "schema_hash": spec.output_schema_hash,
            "schema_id": spec.output_schema_id,
        }
        binding = ModelInputBinding(
            model_invocation_id=spec.model_invocation_id,
            task_id=spec.task_id,
            session_id=spec.session_id,
            project_scope_id=spec.project_scope_id,
            context_package_id=spec.context_package_id,
            context_package_hash=spec.context_package_hash,
            retrieval_manifest_id=package["retrieval_manifest_id"],
            retrieval_manifest_hash=package["retrieval_manifest_hash"],
            task_memory_projection_hash=package["task_memory_projection_hash"],
            task_context_finalization_id=package[
                "task_context_finalization_id"
            ],
            runtime_identity_id=spec.runtime_identity_id,
            runtime_identity_hash=spec.runtime_identity_hash,
            provider_descriptor_hash=descriptor.descriptor_hash,
            inference_configuration_hash=(
                spec.inference_configuration.content_hash
            ),
            output_schema_id=spec.output_schema_id,
            output_schema_hash=spec.output_schema_hash,
        )
        if manifest["retrieval_manifest_id"] != binding.retrieval_manifest_id:
            raise IntegrityInspectionError(
                "manifest identifier and package binding differ"
            )
        return ModelInputPacket(
            invocation=binding,
            task_json=canonical_json_text(task),
            authority_json=canonical_json_text(authority),
            identity_json=canonical_json_text(identity_projection),
            policy_json=canonical_json_text(sections["policy"]),
            memory_json=canonical_json_text(sections["memory"]),
            evidence_json=canonical_json_text(sections["evidence"]),
            output_contract_json=canonical_json_text(output_contract),
        )

    @staticmethod
    def _source_ids(
        package: Mapping[str, Any],
    ) -> tuple[frozenset[str], frozenset[str]]:
        memory_ids: set[str] = set()
        evidence_ids: set[str] = set()
        for entry in package["ordered_context_manifest"]:
            if entry["section"] == "memory":
                memory_ids.add(entry["source_id"])
            elif entry["section"] == "evidence":
                evidence_ids.add(entry["source_id"])
        return frozenset(memory_ids), frozenset(evidence_ids)

    @staticmethod
    def _packet_source_ids(
        packet_value: Mapping[str, Any],
    ) -> tuple[frozenset[str], frozenset[str]]:
        def collect(value: object, accepted_keys: frozenset[str]) -> set[str]:
            found: set[str] = set()
            if isinstance(value, Mapping):
                for key, nested in value.items():
                    if key in accepted_keys and isinstance(nested, str):
                        found.add(nested)
                    found.update(collect(nested, accepted_keys))
            elif isinstance(value, list):
                for nested in value:
                    found.update(collect(nested, accepted_keys))
            return found

        memory = collect(
            packet_value.get("memory", []),
            frozenset({"record_id", "memory_id", "source_id"}),
        )
        evidence = collect(
            packet_value.get("evidence", []),
            frozenset({"evidence_id", "source_id"}),
        )
        return frozenset(memory), frozenset(evidence)

    @staticmethod
    def _append_transition(
        connection: sqlite3.Connection,
        *,
        transition_id: str,
        model_invocation_id: str,
        sequence_number: int,
        from_status: str | None,
        to_status: str,
        reason_code: str,
        changed_at: str,
        runtime_principal: str,
    ) -> InvocationStateTransition:
        transition = InvocationStateTransition(
            transition_id=transition_id,
            model_invocation_id=model_invocation_id,
            sequence_number=sequence_number,
            from_status=from_status,
            to_status=to_status,
            reason_code=reason_code,
            changed_at=changed_at,
            changed_by_principal=runtime_principal,
        )
        connection.execute(
            """
            INSERT INTO model_invocation_state_transitions (
                transition_id, model_invocation_id, sequence_number,
                from_status, to_status, reason_code, changed_at,
                changed_by_principal, canonical_json, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transition.transition_id,
                transition.model_invocation_id,
                transition.sequence_number,
                transition.from_status,
                transition.to_status,
                transition.reason_code,
                transition.changed_at,
                transition.changed_by_principal,
                transition.canonical_json,
                transition.content_hash,
            ),
        )
        return transition

    @staticmethod
    def _anchor(
        connection: sqlite3.Connection,
        *,
        spec: InvocationSpec,
        submission_hash: str,
        prepared_at: str,
    ) -> None:
        provenance = canonical_json_text(
            {
                "context_package_id": spec.context_package_id,
                "model_invocation_id": spec.model_invocation_id,
                "owner": "b87_i4b",
                "submission_hash": submission_hash,
                "task_id": spec.task_id,
            }
        )
        existing = connection.execute(
            """
            SELECT *
            FROM governed_reference_anchors
            WHERE reference_id = ?
            """,
            (spec.model_invocation_id,),
        ).fetchone()
        if existing is None:
            anchor = ReferenceAnchor(
                reference_id=spec.model_invocation_id,
                reference_kind="model_invocation",
                project_scope_id=spec.project_scope_id,
                created_at=prepared_at,
                provenance_json=provenance,
            )
            connection.execute(
                """
                INSERT INTO governed_reference_anchors (
                    reference_id, reference_kind, project_scope_id,
                    lifecycle_state, created_at, provenance_json,
                    content_hash, integrity_status
                ) VALUES (?, ?, ?, 'registered', ?, ?, ?, 'valid')
                """,
                (
                    anchor.reference_id,
                    anchor.reference_kind,
                    anchor.project_scope_id,
                    anchor.created_at,
                    anchor.provenance_json,
                    anchor.content_hash,
                ),
            )
            return
        try:
            anchor = ReferenceAnchor(
                reference_id=existing["reference_id"],
                reference_kind=existing["reference_kind"],
                project_scope_id=existing["project_scope_id"],
                created_at=existing["created_at"],
                provenance_json=existing["provenance_json"],
                lifecycle_state=existing["lifecycle_state"],
                integrity_status=existing["integrity_status"],
            )
        except ValidationError as exc:
            raise ConflictError(
                "pre-existing invocation anchor is invalid"
            ) from exc
        if (
            anchor.reference_kind != "model_invocation"
            or anchor.project_scope_id != spec.project_scope_id
            or anchor.lifecycle_state != "registered"
            or anchor.integrity_status != "valid"
            or anchor.provenance_json != provenance
            or existing["content_hash"] != anchor.content_hash
        ):
            raise ConflictError(
                "pre-existing invocation anchor conflicts with request"
            )

    def prepare(
        self,
        spec: InvocationSpec,
        descriptor: ProviderDescriptor,
        *,
        prepared_at: str,
        initial_transition_id: str,
        runtime_principal: str,
        fail_after_step: str | None = None,
    ) -> PreparationOutcome:
        if not isinstance(spec, InvocationSpec):
            raise ValidationError("invocation specification is invalid")
        if not isinstance(descriptor, ProviderDescriptor):
            raise ValidationError("provider descriptor is invalid")
        preparation_failure_steps = {
            "after_anchor_registration",
            "after_invocation_insert",
            "after_anchor_claim",
            "after_prepared_transition",
        }
        if (
            fail_after_step is not None
            and fail_after_step not in preparation_failure_steps
        ):
            raise ValidationError("preparation failure step is invalid")
        submission_json, submission_hash = self._submission(spec, descriptor)

        def inject(step: str) -> None:
            if fail_after_step == step:
                raise RuntimeError(
                    f"injected preparation failure after {step}"
                )

        def operation(
            connection: sqlite3.Connection,
        ) -> PreparedInvocation | None:
            existing = connection.execute(
                """
                SELECT submission_hash
                FROM model_invocations
                WHERE model_invocation_id = ?
                """,
                (spec.model_invocation_id,),
            ).fetchone()
            if existing is not None:
                if existing["submission_hash"] != submission_hash:
                    raise ConflictError(
                        "model invocation identity conflicts with canonical content"
                    )
                return None

            bindings = self._public_bindings(
                spec,
                descriptor,
                evaluated_at=prepared_at,
                require_current_ready=True,
            )
            packet = self._packet(spec, descriptor, bindings)
            request = InvocationRequest(
                spec=spec,
                provider_descriptor=descriptor,
                model_input_packet=packet,
            )
            prior_rows = tuple(
                connection.execute(
                    """
                    SELECT model_invocation_id, current_status
                    FROM model_invocations
                    WHERE task_id = ? AND context_package_id = ?
                    ORDER BY prepared_at, model_invocation_id
                    """,
                    (spec.task_id, spec.context_package_id),
                )
            )
            if spec.retry_of_invocation_id is None:
                if prior_rows:
                    raise ConflictError(
                        "a later attempt requires an explicit retry relationship"
                    )
            else:
                parent = connection.execute(
                    """
                    SELECT task_id, context_package_id, current_status
                    FROM model_invocations
                    WHERE model_invocation_id = ?
                    """,
                    (spec.retry_of_invocation_id,),
                ).fetchone()
                if (
                    parent is None
                    or parent["task_id"] != spec.task_id
                    or parent["context_package_id"] != spec.context_package_id
                    or parent["current_status"]
                    in {"prepared", "in_progress", "raw_output_captured"}
                ):
                    raise ValidationError(
                        "retry parent must be a terminal attempt for the same task "
                        "and context package"
                    )

            self._anchor(
                connection,
                spec=spec,
                submission_hash=submission_hash,
                prepared_at=prepared_at,
            )
            inject("after_anchor_registration")
            package = bindings.package
            manifest = bindings.manifest
            connection.execute(
                """
                INSERT INTO model_invocations (
                    model_invocation_id, reference_kind, contract_version,
                    task_id, session_id, project_scope_id,
                    context_package_id, context_package_hash,
                    retrieval_manifest_id, retrieval_manifest_hash,
                    task_memory_projection_hash,
                    task_context_finalization_id,
                    task_context_finalization_hash,
                    runtime_identity_id, runtime_identity_hash,
                    provider_id, provider_descriptor_json,
                    provider_descriptor_hash, provider_configuration_json,
                    provider_configuration_hash, model_descriptor_json,
                    model_descriptor_hash,
                    inference_configuration_json,
                    inference_configuration_hash, output_schema_id,
                    output_schema_hash, model_input_packet_json,
                    model_input_packet_hash, submission_json, submission_hash,
                    request_json, request_hash, retry_of_invocation_id,
                    current_status, prepared_at, runtime_principal
                ) VALUES (
                    ?, 'model_invocation', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    'prepared', ?, ?
                )
                """,
                (
                    spec.model_invocation_id,
                    INVOCATION_CONTRACT_VERSION,
                    spec.task_id,
                    spec.session_id,
                    spec.project_scope_id,
                    spec.context_package_id,
                    spec.context_package_hash,
                    package["retrieval_manifest_id"],
                    package["retrieval_manifest_hash"],
                    package["task_memory_projection_hash"],
                    package["task_context_finalization_id"],
                    manifest["finalization_hash"],
                    spec.runtime_identity_id,
                    spec.runtime_identity_hash,
                    descriptor.provider_id,
                    descriptor.canonical_json,
                    descriptor.descriptor_hash,
                    descriptor.provider_configuration_json,
                    descriptor.provider_configuration_hash,
                    spec.model_descriptor.canonical_json,
                    spec.model_descriptor.descriptor_hash,
                    spec.inference_configuration.canonical_json,
                    spec.inference_configuration.content_hash,
                    spec.output_schema_id,
                    spec.output_schema_hash,
                    packet.canonical_json,
                    packet.content_hash,
                    submission_json,
                    submission_hash,
                    request.canonical_json,
                    request.content_hash,
                    spec.retry_of_invocation_id,
                    prepared_at,
                    runtime_principal,
                ),
            )
            inject("after_invocation_insert")
            connection.execute(
                """
                UPDATE governed_reference_anchors
                SET lifecycle_state = 'claimed'
                WHERE reference_id = ?
                  AND reference_kind = 'model_invocation'
                  AND lifecycle_state = 'registered'
                """,
                (spec.model_invocation_id,),
            )
            inject("after_anchor_claim")
            self._append_transition(
                connection,
                transition_id=initial_transition_id,
                model_invocation_id=spec.model_invocation_id,
                sequence_number=0,
                from_status=None,
                to_status="prepared",
                reason_code="invocation_prepared",
                changed_at=prepared_at,
                runtime_principal=runtime_principal,
            )
            inject("after_prepared_transition")
            memory_ids, evidence_ids = self._source_ids(package)
            return PreparedInvocation(
                request=request,
                task_section=package["sections"]["task"],
                allowed_memory_ids=memory_ids,
                allowed_evidence_ids=evidence_ids,
            )

        prepared = self._kernel.write(operation)
        if prepared is None:
            return PreparationOutcome(
                prepared=None,
                existing=self.reconstruct(spec.model_invocation_id),
            )
        return PreparationOutcome(prepared=prepared, existing=None)

    def call_start(
        self,
        prepared: PreparedInvocation,
        *,
        started_at: str,
        provider_call_attempt_id: str,
        transition_id: str,
        runtime_principal: str,
    ) -> None:
        if not isinstance(prepared, PreparedInvocation):
            raise ValidationError("prepared invocation contract is invalid")
        validate_identifier(
            provider_call_attempt_id,
            field="provider_call_attempt_id",
        )
        request = prepared.request

        def operation(connection: sqlite3.Connection) -> None:
            row = connection.execute(
                """
                SELECT current_status, request_hash, prepared_at
                FROM model_invocations
                WHERE model_invocation_id = ?
                """,
                (request.spec.model_invocation_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("prepared model invocation does not exist")
            if row["current_status"] != "prepared":
                raise ConflictError("only a prepared invocation may start")
            if row["request_hash"] != request.content_hash:
                raise ConflictError("prepared request hash differs")
            if started_at < row["prepared_at"]:
                raise ValidationError("started_at precedes prepared_at")
            bindings = self._public_bindings(
                request.spec,
                request.provider_descriptor,
                evaluated_at=started_at,
                require_current_ready=True,
            )
            if (
                self._packet(
                    request.spec,
                    request.provider_descriptor,
                    bindings,
                ).content_hash
                != request.model_input_packet.content_hash
            ):
                raise ConflictError("current request reconstruction differs")
            self._append_transition(
                connection,
                transition_id=transition_id,
                model_invocation_id=request.spec.model_invocation_id,
                sequence_number=1,
                from_status="prepared",
                to_status="in_progress",
                reason_code="provider_call_started",
                changed_at=started_at,
                runtime_principal=runtime_principal,
            )
            connection.execute(
                """
                UPDATE model_invocations
                SET current_status = 'in_progress',
                    started_at = ?,
                    provider_call_attempt_id = ?
                WHERE model_invocation_id = ?
                """,
                (
                    started_at,
                    provider_call_attempt_id,
                    request.spec.model_invocation_id,
                ),
            )

        self._kernel.write(operation)

    def capture_raw_output(
        self,
        *,
        model_invocation_id: str,
        provider_call_attempt_id: str,
        provider_result: ProviderCallResult,
        raw_output_id: str,
        captured_at: str,
        transition_id: str,
        runtime_principal: str,
        fail_during_transaction: bool = False,
        fail_after_step: str | None = None,
    ) -> RawOutputCapture:
        if not isinstance(provider_result, ProviderCallResult):
            raise ValidationError("provider result contract is invalid")
        capture_failure_steps = {
            "before_raw_insert",
            "after_raw_insert",
            "after_raw_transition",
            "after_raw_projection",
        }
        if fail_after_step is not None and fail_after_step not in (
            capture_failure_steps
        ):
            raise ValidationError("raw-capture failure step is invalid")
        if provider_result.raw_output is None:
            raise ValidationError("raw capture requires provider output bytes")
        if provider_result.declared_encoding is None:
            raise ValidationError("raw capture requires declared encoding")
        capture = RawOutputCapture(
            raw_output_id=raw_output_id,
            model_invocation_id=model_invocation_id,
            provider_call_attempt_id=provider_call_attempt_id,
            raw_bytes=provider_result.raw_output,
            declared_encoding=provider_result.declared_encoding,
            provider_result_hash=provider_result.content_hash,
            captured_at=captured_at,
        )

        def inject(step: str) -> None:
            if fail_after_step == step:
                raise RuntimeError(f"injected raw-capture failure after {step}")

        def operation(connection: sqlite3.Connection) -> None:
            invocation = connection.execute(
                """
                SELECT current_status, started_at, provider_call_attempt_id,
                       provider_configuration_json, provider_configuration_hash
                FROM model_invocations
                WHERE model_invocation_id = ?
                """,
                (model_invocation_id,),
            ).fetchone()
            if invocation is None:
                raise NotFoundError("model invocation does not exist")
            if (
                invocation["current_status"] != "in_progress"
                or invocation["provider_call_attempt_id"] != provider_call_attempt_id
            ):
                raise ConflictError("raw capture does not match active provider call")
            if captured_at < invocation["started_at"]:
                raise ValidationError("captured_at precedes started_at")
            configuration_value = parse_json(
                invocation["provider_configuration_json"]
            )
            configuration = ProviderConfigurationSnapshot.from_mapping(
                configuration_value
            )
            if configuration.content_hash != invocation["provider_configuration_hash"]:
                raise IntegrityInspectionError(
                    "provider configuration hash cannot be reproduced"
                )
            validate_provider_result_against_configuration(
                provider_result,
                configuration,
            )
            inject("before_raw_insert")
            connection.execute(
                """
                INSERT INTO model_raw_outputs (
                    raw_output_id, model_invocation_id,
                    provider_call_attempt_id, raw_bytes, raw_byte_length,
                    raw_output_sha256, declared_encoding,
                    provider_result_json, provider_result_hash, captured_at,
                    capture_canonical_json, capture_content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    capture.raw_output_id,
                    capture.model_invocation_id,
                    capture.provider_call_attempt_id,
                    sqlite3.Binary(capture.raw_bytes),
                    capture.raw_byte_length,
                    capture.raw_output_sha256,
                    capture.declared_encoding,
                    provider_result.canonical_json,
                    provider_result.content_hash,
                    capture.captured_at,
                    capture.canonical_json,
                    capture.content_hash,
                ),
            )
            inject("after_raw_insert")
            self._append_transition(
                connection,
                transition_id=transition_id,
                model_invocation_id=model_invocation_id,
                sequence_number=2,
                from_status="in_progress",
                to_status="raw_output_captured",
                reason_code="raw_output_durably_captured",
                changed_at=captured_at,
                runtime_principal=runtime_principal,
            )
            inject("after_raw_transition")
            connection.execute(
                """
                UPDATE model_invocations
                SET current_status = 'raw_output_captured'
                WHERE model_invocation_id = ?
                """,
                (model_invocation_id,),
            )
            if (
                fail_during_transaction
                or fail_after_step == "after_raw_projection"
            ):
                raise RuntimeError("injected raw-capture interruption")

        self._kernel.write(operation)
        return self.reconstruct_raw_output(model_invocation_id)

    def reconstruct_raw_output(
        self,
        model_invocation_id: str,
    ) -> RawOutputCapture:
        def operation(connection: sqlite3.Connection) -> RawOutputCapture:
            row = connection.execute(
                """
                SELECT *
                FROM model_raw_outputs
                WHERE model_invocation_id = ?
                """,
                (model_invocation_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("raw model output does not exist")
            capture = RawOutputCapture(
                raw_output_id=row["raw_output_id"],
                model_invocation_id=row["model_invocation_id"],
                provider_call_attempt_id=row["provider_call_attempt_id"],
                raw_bytes=bytes(row["raw_bytes"]),
                declared_encoding=row["declared_encoding"],
                provider_result_hash=row["provider_result_hash"],
                captured_at=row["captured_at"],
            )
            if (
                row["raw_byte_length"] != capture.raw_byte_length
                or row["raw_output_sha256"] != capture.raw_output_sha256
                or row["capture_canonical_json"] != capture.canonical_json
                or not hashes_match(
                    row["capture_content_hash"],
                    capture.content_hash,
                )
            ):
                raise IntegrityInspectionError(
                    "raw provider output integrity cannot be reproduced"
                )
            provider_result = parse_json(row["provider_result_json"])
            if sha256_canonical_json(provider_result) != row["provider_result_hash"]:
                raise IntegrityInspectionError(
                    "raw capture provider-result hash cannot be reproduced"
                )
            return capture

        return self._kernel.read(operation)

    @staticmethod
    def _insert_output(
        connection: sqlite3.Connection,
        *,
        model_output_id: str,
        invocation_id: str,
        raw: RawOutputCapture,
        processing: OutputProcessingResult,
        schema_id: str,
        schema_hash: str,
    ) -> tuple[str, str]:
        value = {
            "model_invocation_id": invocation_id,
            "model_output_id": model_output_id,
            "output_schema_hash": schema_hash,
            "output_schema_id": schema_id,
            "processing": processing.canonical_value(),
            "raw_output_capture_hash": raw.content_hash,
            "raw_output_id": raw.raw_output_id,
            "raw_output_sha256": raw.raw_output_sha256,
        }
        canonical = canonical_json_text(value)
        content_hash = sha256_canonical_json(value)
        connection.execute(
            """
            INSERT INTO model_outputs (
                model_output_id, model_invocation_id, raw_output_id,
                raw_output_capture_hash, raw_output_sha256,
                utf8_decode_status, decoded_text, decode_errors_json,
                parse_status, parse_errors_json, parsed_canonical_json,
                parsed_output_hash, output_schema_id, output_schema_hash,
                schema_status, schema_errors_json, schema_valid,
                semantic_status, semantic_errors_json, semantic_valid,
                repair_attempted, repair_succeeded, canonical_json,
                content_hash
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, 0, 0, ?, ?
            )
            """,
            (
                model_output_id,
                invocation_id,
                raw.raw_output_id,
                raw.content_hash,
                raw.raw_output_sha256,
                processing.utf8_decode_status,
                processing.decoded_text,
                _issues_json(processing.decode_errors),
                processing.parse_status,
                _issues_json(processing.parse_errors),
                processing.parsed_canonical_json,
                processing.parsed_output_hash,
                schema_id,
                schema_hash,
                processing.schema_status,
                _issues_json(processing.schema_errors),
                int(processing.schema_status == "valid"),
                processing.semantic_status,
                _issues_json(processing.semantic_errors),
                int(processing.semantic_status == "valid"),
                canonical,
                content_hash,
            ),
        )
        return model_output_id, content_hash

    @staticmethod
    def _task_transition(
        connection: sqlite3.Connection,
        *,
        task_id: str,
        terminal_status: str,
        task_section: Mapping[str, Any],
        response_value: Mapping[str, Any] | None,
        task_transition_id: str,
        finalized_at: str,
    ) -> tuple[str, str | None]:
        task = connection.execute(
            "SELECT status FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if task is None:
            raise IntegrityInspectionError("invocation task no longer exists")
        if task["status"] != "active":
            return "unchanged_terminal", None
        if terminal_status == "succeeded":
            if response_value is None:
                raise IntegrityInspectionError(
                    "successful invocation has no validated response"
                )
            disposition = task_completion_disposition(
                task_section=task_section,
                response_value=response_value,
            )
            if disposition != "completed":
                return disposition, None
            transition_task_in_transaction(
                connection,
                task_id=task_id,
                to_status="completed",
                transition_id=task_transition_id,
                changed_at=finalized_at,
                reason_code="i4b_validated_response_sufficient",
            )
            return "completed", task_transition_id
        transition_task_in_transaction(
            connection,
            task_id=task_id,
            to_status="failed",
            transition_id=task_transition_id,
            changed_at=finalized_at,
            reason_code=f"i4b_{terminal_status}",
        )
        return "failed", task_transition_id

    @staticmethod
    def _derive_terminal_status(
        *,
        provider_result: ProviderCallResult | None,
        processing: OutputProcessingResult | None,
        failure_classification: str | None,
        explicitly_interrupted: bool,
    ) -> tuple[str, str | None]:
        if explicitly_interrupted:
            if failure_classification != "runtime_interrupted":
                raise ValidationError(
                    "explicit interruption requires runtime_interrupted"
                )
            return "interrupted", failure_classification
        if provider_result is None:
            raise ValidationError("non-interrupted finalization requires a result")
        if failure_classification in {
            "provider_descriptor_failure",
            "provider_descriptor_changed",
            "unexpected_inactive_result",
        }:
            return "provider_failed", failure_classification
        if provider_result.outcome == "provider_inactive":
            return "provider_inactive", "provider_inactive"
        if provider_result.outcome == "output":
            if processing is None:
                raise ValidationError("output finalization requires processing")
            if processing.successful:
                return "succeeded", None
            return "invalid_response", "invalid_response"
        if provider_result.outcome == "provider_failed":
            return "provider_failed", (
                failure_classification
                or provider_result.failure_code
                or "provider_failed"
            )
        if provider_result.outcome == "timed_out":
            return "timed_out", (
                failure_classification or provider_result.failure_code or "timed_out"
            )
        raise ValidationError("provider result outcome cannot be finalized")

    def finalize(
        self,
        prepared: PreparedInvocation,
        *,
        provider_result: ProviderCallResult | None,
        raw_capture: RawOutputCapture | None,
        failure_classification: str | None,
        explicitly_interrupted: bool = False,
        finalized_at: str,
        invocation_transition_id: str,
        model_output_id: str,
        task_transition_id: str,
        runtime_principal: str,
        fail_during_transaction: bool = False,
    ) -> InvocationReconstruction:
        """Finalize only from committed evidence and independently derived data."""

        if not isinstance(prepared, PreparedInvocation):
            raise ValidationError("prepared invocation contract is invalid")
        request = prepared.request
        if provider_result is not None and not isinstance(
            provider_result, ProviderCallResult
        ):
            raise ValidationError("provider result contract is invalid")
        if raw_capture is not None and not isinstance(raw_capture, RawOutputCapture):
            raise ValidationError("raw-output capture contract is invalid")
        if provider_result is None and not explicitly_interrupted:
            raise ValidationError(
                "only an explicitly interrupted invocation may lack a provider result"
            )
        if provider_result is not None and provider_result.raw_output is not None:
            if raw_capture is None:
                raise ValidationError(
                    "a provider result containing bytes requires exact raw capture"
                )
        elif raw_capture is not None:
            raise ValidationError("raw capture requires provider-returned bytes")

        configuration = ProviderConfigurationSnapshot.from_mapping(
            parse_json(request.provider_descriptor.provider_configuration_json)
        )
        synthetic_runtime_failure = (
            provider_result is not None
            and provider_result.raw_output is None
            and failure_classification in {
                "provider_exception",
                "malformed_provider_result",
                "provider_descriptor_failure",
                "provider_descriptor_changed",
                "unexpected_inactive_result",
            }
        )
        if provider_result is not None and not synthetic_runtime_failure:
            validate_provider_result_against_configuration(
                provider_result,
                configuration,
            )

        authoritative_processing: OutputProcessingResult | None = None
        task_section = request.model_input_packet.canonical_value()["task"]
        package = self._context.reconstruct_context_package(
            request.spec.context_package_id
        )["value"]
        allowed_memory_ids, allowed_evidence_ids = self._source_ids(package)
        if raw_capture is not None:
            committed_capture = self.reconstruct_raw_output(
                request.spec.model_invocation_id
            )
            if committed_capture != raw_capture:
                raise IntegrityInspectionError(
                    "caller raw capture differs from committed evidence"
                )
            authoritative_processing = process_raw_output(
                committed_capture.raw_bytes,
                declared_encoding=committed_capture.declared_encoding,
                task_id=request.spec.task_id,
                task_section=task_section,
                allowed_memory_ids=allowed_memory_ids,
                allowed_evidence_ids=allowed_evidence_ids,
            )

        terminal_status, effective_failure = self._derive_terminal_status(
            provider_result=provider_result,
            processing=authoritative_processing,
            failure_classification=failure_classification,
            explicitly_interrupted=explicitly_interrupted,
        )

        def operation(connection: sqlite3.Connection) -> None:
            row = connection.execute(
                """
                SELECT *
                FROM model_invocations
                WHERE model_invocation_id = ?
                """,
                (request.spec.model_invocation_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("model invocation does not exist")
            expected_state = (
                "raw_output_captured"
                if raw_capture is not None
                else (
                    "prepared"
                    if terminal_status == "provider_inactive"
                    else "in_progress"
                )
            )
            if row["current_status"] != expected_state:
                raise ConflictError(
                    "invocation is not in the expected finalization state"
                )
            latest_time = row["started_at"] or row["prepared_at"]
            if finalized_at < latest_time:
                raise ValidationError("finalized_at precedes the latest durable state")
            if (
                row["request_hash"] != request.content_hash
                or row["provider_descriptor_hash"]
                != request.provider_descriptor.descriptor_hash
                or row["provider_configuration_hash"]
                != request.provider_descriptor.provider_configuration_hash
                or row["provider_configuration_json"]
                != request.provider_descriptor.provider_configuration_json
            ):
                raise IntegrityInspectionError(
                    "stored invocation request binding differs"
                )
            bindings = self._public_bindings(
                request.spec,
                request.provider_descriptor,
                evaluated_at=finalized_at,
                require_current_ready=False,
            )
            if terminal_status == "provider_inactive" and (
                not bindings.current_ready or not bindings.identity_current
            ):
                raise ValidationError(
                    "inactive invocation cannot finalize after its governed bindings become stale"
                )
            packet = self._packet(
                request.spec,
                request.provider_descriptor,
                bindings,
            )
            if packet.content_hash != row["model_input_packet_hash"]:
                raise IntegrityInspectionError(
                    "model-input packet cannot be reproduced"
                )
            final_status = terminal_status
            final_failure = effective_failure
            if terminal_status not in {"provider_inactive", "interrupted"} and (
                not bindings.current_ready or not bindings.identity_current
            ):
                final_status = "stale_context"
                final_failure = "stale_context"

            output_identity: str | None = None
            output_hash: str | None = None
            response_value: Mapping[str, Any] | None = None
            if raw_capture is not None:
                committed = connection.execute(
                    """
                    SELECT * FROM model_raw_outputs
                    WHERE raw_output_id = ? AND model_invocation_id = ?
                    """,
                    (
                        raw_capture.raw_output_id,
                        request.spec.model_invocation_id,
                    ),
                ).fetchone()
                if committed is None:
                    raise IntegrityInspectionError(
                        "committed raw output cannot be found"
                    )
                exact = bytes(committed["raw_bytes"])
                if (
                    exact != raw_capture.raw_bytes
                    or len(exact) != committed["raw_byte_length"]
                    or sha256_bytes(exact) != committed["raw_output_sha256"]
                    or committed["declared_encoding"] != raw_capture.declared_encoding
                    or committed["provider_result_hash"] != provider_result.content_hash
                    or committed["captured_at"] > finalized_at
                ):
                    raise IntegrityInspectionError(
                        "committed raw output differs before finalization"
                    )
                if authoritative_processing is None:
                    raise IntegrityInspectionError(
                        "raw output has no deterministic processing result"
                    )
                output_identity, output_hash = self._insert_output(
                    connection,
                    model_output_id=model_output_id,
                    invocation_id=request.spec.model_invocation_id,
                    raw=raw_capture,
                    processing=authoritative_processing,
                    schema_id=request.spec.output_schema_id,
                    schema_hash=request.spec.output_schema_hash,
                )
                if authoritative_processing.successful:
                    parsed = parse_json(
                        authoritative_processing.parsed_canonical_json or ""
                    )
                    if not isinstance(parsed, Mapping):
                        raise IntegrityInspectionError(
                            "validated response is not an object"
                        )
                    response_value = parsed

            task_disposition, applied_task_transition_id = self._task_transition(
                connection,
                task_id=request.spec.task_id,
                terminal_status=final_status,
                task_section=packet.canonical_value()["task"],
                response_value=response_value,
                task_transition_id=task_transition_id,
                finalized_at=finalized_at,
            )
            finalization = TerminalFinalizationResult(
                model_invocation_id=request.spec.model_invocation_id,
                terminal_status=final_status,
                provider_result_hash=(
                    None if provider_result is None else provider_result.content_hash
                ),
                model_output_id=output_identity,
                model_output_hash=output_hash,
                task_disposition=task_disposition,
                task_transition_id=applied_task_transition_id,
                failure_classification=final_failure,
                finalized_at=finalized_at,
            )
            sequence = (
                1
                if row["current_status"] == "prepared"
                else (3 if row["current_status"] == "raw_output_captured" else 2)
            )
            self._append_transition(
                connection,
                transition_id=invocation_transition_id,
                model_invocation_id=request.spec.model_invocation_id,
                sequence_number=sequence,
                from_status=row["current_status"],
                to_status=final_status,
                reason_code=(
                    "validated_response"
                    if final_status == "succeeded"
                    else f"runtime_{final_status}"
                ),
                changed_at=finalized_at,
                runtime_principal=runtime_principal,
            )
            connection.execute(
                """
                UPDATE model_invocations
                SET current_status = ?, completed_at = ?,
                    provider_result_outcome = ?, provider_result_json = ?,
                    provider_result_hash = ?, failure_classification = ?,
                    terminal_result_json = ?, terminal_result_hash = ?,
                    task_disposition = ?, task_transition_id = ?
                WHERE model_invocation_id = ?
                """,
                (
                    final_status,
                    finalized_at,
                    None if provider_result is None else provider_result.outcome,
                    None if provider_result is None else provider_result.canonical_json,
                    None if provider_result is None else provider_result.content_hash,
                    final_failure,
                    finalization.canonical_json,
                    finalization.content_hash,
                    task_disposition,
                    applied_task_transition_id,
                    request.spec.model_invocation_id,
                ),
            )
            if fail_during_transaction:
                raise RuntimeError("injected terminal-finalization interruption")

        self._kernel.write(operation)
        return self.reconstruct(request.spec.model_invocation_id)

    @staticmethod
    def _verify_json_hash(
        row: sqlite3.Row,
        json_field: str,
        hash_field: str,
    ) -> Any:
        value = parse_json(row[json_field])
        if (
            canonical_json_text(value) != row[json_field]
            or sha256_canonical_json(value) != row[hash_field]
        ):
            raise IntegrityInspectionError(
                f"{json_field} canonical hash cannot be reproduced"
            )
        return value

    @staticmethod
    def _model_input_packet_from_value(
        value: object,
    ) -> ModelInputPacket:
        if not isinstance(value, Mapping):
            raise IntegrityInspectionError(
                "stored model-input packet is not an object"
            )
        expected = {
            "authority",
            "evidence",
            "identity",
            "invocation",
            "memory",
            "output_contract",
            "policy",
            "protocol",
            "protocol_version",
            "task",
        }
        if set(value) != expected or not isinstance(
            value["invocation"],
            Mapping,
        ):
            raise IntegrityInspectionError(
                "stored model-input packet shape is invalid"
            )
        binding_fields = {
            "context_package_hash",
            "context_package_id",
            "inference_configuration_hash",
            "model_invocation_id",
            "output_schema_hash",
            "output_schema_id",
            "project_scope_id",
            "provider_descriptor_hash",
            "retrieval_manifest_hash",
            "retrieval_manifest_id",
            "runtime_identity_hash",
            "runtime_identity_id",
            "session_id",
            "task_context_finalization_id",
            "task_id",
            "task_memory_projection_hash",
        }
        if set(value["invocation"]) != binding_fields:
            raise IntegrityInspectionError(
                "stored model-input invocation binding shape is invalid"
            )
        try:
            binding = ModelInputBinding(**dict(value["invocation"]))
            packet = ModelInputPacket(
                invocation=binding,
                task_json=canonical_json_text(value["task"]),
                authority_json=canonical_json_text(value["authority"]),
                identity_json=canonical_json_text(value["identity"]),
                policy_json=canonical_json_text(value["policy"]),
                memory_json=canonical_json_text(value["memory"]),
                evidence_json=canonical_json_text(value["evidence"]),
                output_contract_json=canonical_json_text(
                    value["output_contract"]
                ),
                protocol=value["protocol"],
                protocol_version=value["protocol_version"],
            )
        except (TypeError, ValidationError) as exc:
            raise IntegrityInspectionError(
                "stored model-input packet cannot be reconstructed"
            ) from exc
        if packet.canonical_value() != value:
            raise IntegrityInspectionError(
                "stored model-input packet canonical value differs"
            )
        return packet

    @staticmethod
    def _provider_result_from_value(
        value: object,
        *,
        raw_output: bytes | None,
    ) -> ProviderCallResult:
        if not isinstance(value, Mapping):
            raise IntegrityInspectionError(
                "stored provider result is not an object"
            )
        expected = {
            "declared_encoding",
            "failure_code",
            "outcome",
            "provider_metadata",
            "raw_byte_length",
            "raw_output_sha256",
        }
        if set(value) != expected or not isinstance(
            value["provider_metadata"],
            Mapping,
        ):
            raise IntegrityInspectionError(
                "stored provider result shape is invalid"
            )
        try:
            result = ProviderCallResult(
                outcome=value["outcome"],
                raw_output=raw_output,
                declared_encoding=value["declared_encoding"],
                failure_code=value["failure_code"],
                provider_metadata_json=canonical_json_text(
                    value["provider_metadata"]
                ),
            )
        except (TypeError, ValidationError) as exc:
            raise IntegrityInspectionError(
                "stored provider result cannot be reconstructed"
            ) from exc
        if result.canonical_value() != value:
            raise IntegrityInspectionError(
                "stored provider result canonical value differs"
            )
        return result

    @staticmethod
    def _validation_issues_from_json(
        value: object,
        *,
        label: str,
    ) -> tuple[ValidationIssue, ...]:
        if not isinstance(value, str):
            raise IntegrityInspectionError(f"{label} is not JSON text")
        parsed = parse_json(value)
        if not isinstance(parsed, list):
            raise IntegrityInspectionError(f"{label} is not a JSON array")
        issues: list[ValidationIssue] = []
        for item in parsed:
            if not isinstance(item, Mapping) or set(item) != {
                "code",
                "detail",
                "path",
            }:
                raise IntegrityInspectionError(
                    f"{label} contains an invalid issue"
                )
            try:
                issues.append(
                    ValidationIssue(
                        path=item["path"],
                        code=item["code"],
                        detail=item["detail"],
                    )
                )
            except (TypeError, ValidationError) as exc:
                raise IntegrityInspectionError(
                    f"{label} contains an invalid issue"
                ) from exc
        return tuple(issues)

    @classmethod
    def _processing_from_output_row(
        cls,
        row: sqlite3.Row,
    ) -> OutputProcessingResult:
        try:
            processing = OutputProcessingResult(
                utf8_decode_status=row["utf8_decode_status"],
                decoded_text=row["decoded_text"],
                decode_errors=cls._validation_issues_from_json(
                    row["decode_errors_json"],
                    label="decode_errors_json",
                ),
                parse_status=row["parse_status"],
                parse_errors=cls._validation_issues_from_json(
                    row["parse_errors_json"],
                    label="parse_errors_json",
                ),
                parsed_canonical_json=row["parsed_canonical_json"],
                parsed_output_hash=row["parsed_output_hash"],
                schema_status=row["schema_status"],
                schema_errors=cls._validation_issues_from_json(
                    row["schema_errors_json"],
                    label="schema_errors_json",
                ),
                semantic_status=row["semantic_status"],
                semantic_errors=cls._validation_issues_from_json(
                    row["semantic_errors_json"],
                    label="semantic_errors_json",
                ),
                repair_attempted=bool(row["repair_attempted"]),
                repair_succeeded=bool(row["repair_succeeded"]),
            )
        except (TypeError, ValidationError) as exc:
            raise IntegrityInspectionError(
                "stored output processing result cannot be reconstructed"
            ) from exc
        if (
            row["schema_valid"] != int(processing.schema_status == "valid")
            or row["semantic_valid"]
            != int(processing.semantic_status == "valid")
            or row["repair_attempted"] != 0
            or row["repair_succeeded"] != 0
        ):
            raise IntegrityInspectionError(
                "stored output processing projections differ"
            )
        return processing

    @classmethod
    def _reconstruct_connection(
        cls,
        connection: sqlite3.Connection,
        model_invocation_id: str,
    ) -> InvocationReconstruction:
        row = connection.execute(
            """
            SELECT *
            FROM model_invocations
            WHERE model_invocation_id = ?
            """,
            (model_invocation_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(
                f"model invocation not found: {model_invocation_id}"
            )
        if row["provider_call_attempt_id"] is not None:
            try:
                validate_identifier(
                    row["provider_call_attempt_id"],
                    field="provider_call_attempt_id",
                )
            except ValidationError as exc:
                raise IntegrityInspectionError(
                    "provider-call attempt identity is invalid"
                ) from exc
        provider = cls._verify_json_hash(
            row,
            "provider_descriptor_json",
            "provider_descriptor_hash",
        )
        descriptor = _provider_descriptor_from_value(provider)
        configuration = cls._verify_json_hash(
            row,
            "provider_configuration_json",
            "provider_configuration_hash",
        )
        try:
            configuration_contract = ProviderConfigurationSnapshot.from_mapping(
                configuration
            )
        except ValidationError as exc:
            raise IntegrityInspectionError(
                "provider configuration cannot be reconstructed"
            ) from exc
        if (
            descriptor.provider_id != row["provider_id"]
            or descriptor.provider_configuration_hash
            != row["provider_configuration_hash"]
            or descriptor.provider_configuration_json
            != canonical_json_text(configuration)
            or configuration_contract.content_hash
            != row["provider_configuration_hash"]
        ):
            raise IntegrityInspectionError(
                "provider descriptor columns cannot be reproduced"
            )
        model = cls._verify_json_hash(
            row,
            "model_descriptor_json",
            "model_descriptor_hash",
        )
        try:
            ModelDescriptor.from_mapping(model)
        except ValidationError as exc:
            raise IntegrityInspectionError(
                "model descriptor cannot be reconstructed"
            ) from exc
        inference = cls._verify_json_hash(
            row,
            "inference_configuration_json",
            "inference_configuration_hash",
        )
        try:
            InferenceConfiguration.from_mapping(inference)
        except ValidationError as exc:
            raise IntegrityInspectionError(
                "inference configuration cannot be reconstructed"
            ) from exc
        packet = cls._verify_json_hash(
            row,
            "model_input_packet_json",
            "model_input_packet_hash",
        )
        submission = cls._verify_json_hash(
            row,
            "submission_json",
            "submission_hash",
        )
        request = cls._verify_json_hash(
            row,
            "request_json",
            "request_hash",
        )
        if not isinstance(submission, Mapping) or set(submission) != {
            "provider_descriptor",
            "spec",
        }:
            raise IntegrityInspectionError(
                "stored invocation submission shape is invalid"
            )
        try:
            spec = InvocationSpec.from_mapping(submission["spec"])
            stored_model = ModelDescriptor.from_mapping(model)
            stored_inference = InferenceConfiguration.from_mapping(inference)
        except (TypeError, ValidationError) as exc:
            raise IntegrityInspectionError(
                "stored invocation contracts cannot be reconstructed"
            ) from exc
        packet_contract = cls._model_input_packet_from_value(packet)
        try:
            request_contract = InvocationRequest(
                spec=spec,
                provider_descriptor=descriptor,
                model_input_packet=packet_contract,
            )
        except ValidationError as exc:
            raise IntegrityInspectionError(
                "stored invocation request bindings cannot be reconstructed"
            ) from exc
        expected_submission = {
            "provider_descriptor": descriptor.canonical_value(),
            "spec": spec.canonical_value(),
        }
        binding = packet_contract.invocation
        if (
            submission != expected_submission
            or submission["provider_descriptor"] != provider
            or stored_model != spec.model_descriptor
            or stored_inference != spec.inference_configuration
            or request_contract.canonical_value() != request
            or request_contract.content_hash != row["request_hash"]
            or packet_contract.content_hash != row["model_input_packet_hash"]
            or row["contract_version"] != INVOCATION_CONTRACT_VERSION
            or spec.model_invocation_id != row["model_invocation_id"]
            or spec.task_id != row["task_id"]
            or spec.session_id != row["session_id"]
            or spec.project_scope_id != row["project_scope_id"]
            or spec.context_package_id != row["context_package_id"]
            or spec.context_package_hash != row["context_package_hash"]
            or spec.runtime_identity_id != row["runtime_identity_id"]
            or spec.runtime_identity_hash != row["runtime_identity_hash"]
            or spec.provider_id != row["provider_id"]
            or spec.output_schema_id != row["output_schema_id"]
            or spec.output_schema_hash != row["output_schema_hash"]
            or spec.retry_of_invocation_id != row["retry_of_invocation_id"]
            or stored_model.descriptor_hash != row["model_descriptor_hash"]
            or stored_inference.content_hash
            != row["inference_configuration_hash"]
            or binding.retrieval_manifest_id
            != row["retrieval_manifest_id"]
            or binding.retrieval_manifest_hash
            != row["retrieval_manifest_hash"]
            or binding.task_memory_projection_hash
            != row["task_memory_projection_hash"]
            or binding.task_context_finalization_id
            != row["task_context_finalization_id"]
        ):
            raise IntegrityInspectionError(
                "stored invocation request columns cannot be reproduced"
            )

        anchor = connection.execute(
            """
            SELECT *
            FROM governed_reference_anchors
            WHERE reference_id = ? AND reference_kind = 'model_invocation'
            """,
            (model_invocation_id,),
        ).fetchone()
        if (
            anchor is None
            or anchor["project_scope_id"] != row["project_scope_id"]
            or anchor["lifecycle_state"] != "claimed"
            or anchor["integrity_status"] != "valid"
        ):
            raise IntegrityInspectionError(
                "typed model-invocation anchor is not valid and claimed"
            )
        reconstructed_anchor = ReferenceAnchor(
            reference_id=anchor["reference_id"],
            reference_kind=anchor["reference_kind"],
            project_scope_id=anchor["project_scope_id"],
            created_at=anchor["created_at"],
            provenance_json=anchor["provenance_json"],
            lifecycle_state=anchor["lifecycle_state"],
            integrity_status=anchor["integrity_status"],
        )
        if anchor["content_hash"] != reconstructed_anchor.content_hash:
            raise IntegrityInspectionError(
                "model-invocation anchor hash cannot be reproduced"
            )
        expected_anchor_provenance = {
            "context_package_id": spec.context_package_id,
            "model_invocation_id": spec.model_invocation_id,
            "owner": "b87_i4b",
            "submission_hash": row["submission_hash"],
            "task_id": spec.task_id,
        }
        if (
            anchor["created_at"] != row["prepared_at"]
            or parse_json(anchor["provenance_json"])
            != expected_anchor_provenance
        ):
            raise IntegrityInspectionError(
                "model-invocation anchor provenance cannot be reproduced"
            )

        transitions: list[Mapping[str, Any]] = []
        transition_contracts: list[InvocationStateTransition] = []
        prior: str | None = None
        prior_changed_at: str | None = None
        for expected_sequence, transition_row in enumerate(
            connection.execute(
                """
                SELECT *
                FROM model_invocation_state_transitions
                WHERE model_invocation_id = ?
                ORDER BY sequence_number, transition_id
                """,
                (model_invocation_id,),
            )
        ):
            transition_value = cls._verify_json_hash(
                transition_row,
                "canonical_json",
                "content_hash",
            )
            try:
                transition = InvocationStateTransition(
                    transition_id=transition_row["transition_id"],
                    model_invocation_id=transition_row[
                        "model_invocation_id"
                    ],
                    sequence_number=transition_row["sequence_number"],
                    from_status=transition_row["from_status"],
                    to_status=transition_row["to_status"],
                    reason_code=transition_row["reason_code"],
                    changed_at=transition_row["changed_at"],
                    changed_by_principal=transition_row[
                        "changed_by_principal"
                    ],
                )
            except ValidationError as exc:
                raise IntegrityInspectionError(
                    "invocation transition cannot be reconstructed"
                ) from exc
            if (
                transition.sequence_number != expected_sequence
                or transition.from_status != prior
                or transition.canonical_value() != transition_value
                or (
                    prior_changed_at is not None
                    and transition.changed_at < prior_changed_at
                )
            ):
                raise IntegrityInspectionError(
                    "invocation transition chain cannot be reproduced"
                )
            if transition.to_status == "prepared":
                expected_reason = "invocation_prepared"
            elif transition.to_status == "in_progress":
                expected_reason = "provider_call_started"
            elif transition.to_status == "raw_output_captured":
                expected_reason = "raw_output_durably_captured"
            elif transition.to_status == "succeeded":
                expected_reason = "validated_response"
            else:
                expected_reason = f"runtime_{transition.to_status}"
            if transition.reason_code != expected_reason:
                raise IntegrityInspectionError(
                    "invocation transition reason cannot be reproduced"
                )
            prior = transition.to_status
            prior_changed_at = transition.changed_at
            transitions.append(transition_value)
            transition_contracts.append(transition)
        if not transitions or prior != row["current_status"]:
            raise IntegrityInspectionError(
                "invocation current status differs from transition history"
            )
        if (
            transition_contracts[0].changed_at != row["prepared_at"]
            or transition_contracts[0].changed_by_principal
            != row["runtime_principal"]
        ):
            raise IntegrityInspectionError(
                "invocation preparation projection differs from transition"
            )
        start_transitions = [
            transition
            for transition in transition_contracts
            if transition.to_status == "in_progress"
        ]
        terminal_transitions = [
            transition
            for transition in transition_contracts
            if transition.to_status
            not in {"prepared", "in_progress", "raw_output_captured"}
        ]
        capture_transitions = [
            transition
            for transition in transition_contracts
            if transition.to_status == "raw_output_captured"
        ]
        if (
            (row["started_at"] is None) != (not start_transitions)
            or (
                start_transitions
                and start_transitions[0].changed_at != row["started_at"]
            )
            or (row["completed_at"] is None) != (not terminal_transitions)
            or (
                terminal_transitions
                and terminal_transitions[0].changed_at
                != row["completed_at"]
            )
            or (row["started_at"] is not None and row["started_at"] < row["prepared_at"])
            or (row["completed_at"] is not None and row["completed_at"] < row["prepared_at"])
            or (
                row["completed_at"] is not None
                and row["started_at"] is not None
                and row["completed_at"] < row["started_at"]
            )
        ):
            raise IntegrityInspectionError(
                "invocation timing projection differs from transition history"
            )

        raw_row = connection.execute(
            """
            SELECT *
            FROM model_raw_outputs
            WHERE model_invocation_id = ?
            """,
            (model_invocation_id,),
        ).fetchone()
        raw_bytes: bytes | None = None
        raw_value: Mapping[str, Any] | None = None
        raw_capture_contract: RawOutputCapture | None = None
        raw_provider_result: ProviderCallResult | None = None
        if raw_row is not None:
            raw_bytes = bytes(raw_row["raw_bytes"])
            raw_value = cls._verify_json_hash(
                raw_row,
                "capture_canonical_json",
                "capture_content_hash",
            )
            raw_capture_contract = RawOutputCapture(
                raw_output_id=raw_row["raw_output_id"],
                model_invocation_id=raw_row["model_invocation_id"],
                provider_call_attempt_id=raw_row[
                    "provider_call_attempt_id"
                ],
                raw_bytes=raw_bytes,
                declared_encoding=raw_row["declared_encoding"],
                provider_result_hash=raw_row["provider_result_hash"],
                captured_at=raw_row["captured_at"],
            )
            raw_provider_value = cls._verify_json_hash(
                raw_row,
                "provider_result_json",
                "provider_result_hash",
            )
            raw_provider_result = cls._provider_result_from_value(
                raw_provider_value,
                raw_output=raw_bytes,
            )
            if (
                len(raw_bytes) != raw_row["raw_byte_length"]
                or sha256_bytes(raw_bytes) != raw_row["raw_output_sha256"]
                or raw_capture_contract.canonical_value() != raw_value
                or raw_capture_contract.content_hash
                != raw_row["capture_content_hash"]
                or raw_capture_contract.raw_output_sha256
                != raw_row["raw_output_sha256"]
                or raw_provider_result.content_hash
                != raw_capture_contract.provider_result_hash
                or raw_row["provider_call_attempt_id"]
                != row["provider_call_attempt_id"]
                or not capture_transitions
                or capture_transitions[0].changed_at != raw_row["captured_at"]
                or raw_row["captured_at"] < row["started_at"]
            ):
                raise IntegrityInspectionError(
                    "raw provider output cannot be reproduced"
                )

        output_row = connection.execute(
            """
            SELECT *
            FROM model_outputs
            WHERE model_invocation_id = ?
            """,
            (model_invocation_id,),
        ).fetchone()
        output_value: Mapping[str, Any] | None = None
        output_processing: OutputProcessingResult | None = None
        if output_row is not None:
            if raw_row is None or output_row["raw_output_id"] != raw_row["raw_output_id"]:
                raise IntegrityInspectionError(
                    "model output does not bind its raw capture"
                )
            output_value = cls._verify_json_hash(
                output_row,
                "canonical_json",
                "content_hash",
            )
            output_processing = cls._processing_from_output_row(output_row)
            expected_output_value = {
                "model_invocation_id": row["model_invocation_id"],
                "model_output_id": output_row["model_output_id"],
                "output_schema_hash": row["output_schema_hash"],
                "output_schema_id": row["output_schema_id"],
                "processing": output_processing.canonical_value(),
                "raw_output_capture_hash": raw_row[
                    "capture_content_hash"
                ],
                "raw_output_id": raw_row["raw_output_id"],
                "raw_output_sha256": raw_row["raw_output_sha256"],
            }
            if (
                output_row["raw_output_capture_hash"]
                != raw_row["capture_content_hash"]
                or output_row["raw_output_sha256"]
                != raw_row["raw_output_sha256"]
                or output_row["output_schema_id"]
                != row["output_schema_id"]
                or output_row["output_schema_hash"]
                != row["output_schema_hash"]
                or output_value != expected_output_value
            ):
                raise IntegrityInspectionError(
                    "model output raw-evidence binding differs"
                )
            memory_ids, evidence_ids = cls._packet_source_ids(packet)
            rederived_processing = process_raw_output(
                raw_bytes,
                declared_encoding=raw_row["declared_encoding"],
                task_id=row["task_id"],
                task_section=packet["task"],
                allowed_memory_ids=memory_ids,
                allowed_evidence_ids=evidence_ids,
            )
            if rederived_processing != output_processing:
                raise IntegrityInspectionError(
                    "derived model output differs from exact raw evidence"
                )

        provider_result_value: Mapping[str, Any] | None = None
        provider_result_contract: ProviderCallResult | None = None
        synthetic_runtime_failure = False
        if row["provider_result_json"] is not None:
            if (
                row["provider_result_hash"] is None
                or row["provider_result_outcome"] is None
            ):
                raise IntegrityInspectionError(
                    "provider result projection is incomplete"
                )
            provider_result_value = cls._verify_json_hash(
                row,
                "provider_result_json",
                "provider_result_hash",
            )
            provider_result_contract = cls._provider_result_from_value(
                provider_result_value,
                raw_output=raw_bytes,
            )
            synthetic_runtime_failure = (
                provider_result_contract.raw_output is None
                and row["failure_classification"] in {
                    "provider_exception",
                    "malformed_provider_result",
                    "provider_descriptor_failure",
                    "provider_descriptor_changed",
                    "unexpected_inactive_result",
                }
            )
            if (
                provider_result_contract.outcome
                != row["provider_result_outcome"]
                or (
                    raw_provider_result is not None
                    and raw_provider_result != provider_result_contract
                )
            ):
                raise IntegrityInspectionError(
                    "provider result projection cannot be reproduced"
                )
        elif any(
            value is not None
            for value in (
                row["provider_result_hash"],
                row["provider_result_outcome"],
            )
        ):
            raise IntegrityInspectionError(
                "provider result projection is contradictory"
            )

        terminal: Mapping[str, Any] | None = None
        terminal_contract: TerminalFinalizationResult | None = None
        if row["terminal_result_json"] is not None:
            terminal = cls._verify_json_hash(
                row,
                "terminal_result_json",
                "terminal_result_hash",
            )
            if not isinstance(terminal, Mapping) or set(terminal) != {
                "failure_classification",
                "finalized_at",
                "model_invocation_id",
                "model_output_hash",
                "model_output_id",
                "provider_result_hash",
                "task_disposition",
                "task_transition_id",
                "terminal_status",
            }:
                raise IntegrityInspectionError(
                    "terminal finalization shape is invalid"
                )
            try:
                terminal_contract = TerminalFinalizationResult(**dict(terminal))
            except (TypeError, ValidationError) as exc:
                raise IntegrityInspectionError(
                    "terminal finalization cannot be reconstructed"
                ) from exc
            if (
                terminal_contract.canonical_value() != terminal
                or terminal_contract.terminal_status != row["current_status"]
                or terminal_contract.model_invocation_id
                != row["model_invocation_id"]
                or terminal_contract.provider_result_hash
                != row["provider_result_hash"]
                or terminal_contract.finalized_at != row["completed_at"]
                or terminal_contract.failure_classification
                != row["failure_classification"]
                or terminal_contract.task_disposition
                != row["task_disposition"]
                or terminal_contract.task_transition_id
                != row["task_transition_id"]
                or terminal_contract.model_output_id
                != (
                    None
                    if output_row is None
                    else output_row["model_output_id"]
                )
                or terminal_contract.model_output_hash
                != (
                    None if output_row is None else output_row["content_hash"]
                )
            ):
                raise IntegrityInspectionError(
                    "terminal result and invocation state differ"
                )
        elif row["current_status"] not in {
            "prepared",
            "in_progress",
            "raw_output_captured",
        }:
            raise IntegrityInspectionError(
                "terminal invocation has no finalization result"
            )

        non_terminal = row["current_status"] in {
            "prepared",
            "in_progress",
            "raw_output_captured",
        }
        if (
            (raw_row is not None)
            != (
                row["current_status"] == "raw_output_captured"
                or (
                    terminal_contract is not None
                    and output_row is not None
                )
            )
            or (output_row is not None and terminal_contract is None)
            or (non_terminal and output_row is not None)
            or (non_terminal and provider_result_contract is not None)
            or (
                terminal_contract is not None
                and (raw_row is not None) != (output_row is not None)
            )
            or (
                row["current_status"] == "succeeded"
                and (
                    output_processing is None
                    or not output_processing.successful
                )
            )
            or (
                row["current_status"] == "invalid_response"
                and (
                    output_processing is None
                    or output_processing.successful
                )
            )
        ):
            raise IntegrityInspectionError(
                "raw, derived, and terminal lifecycle relationships differ"
            )
        if terminal_contract is not None:
            provider_outcome = (
                None
                if provider_result_contract is None
                else provider_result_contract.outcome
            )
            exact_terminal_outcomes = {
                "invalid_response": "output",
                "provider_inactive": "provider_inactive",
                "succeeded": "output",
                "timed_out": "timed_out",
            }
            expected_outcome = exact_terminal_outcomes.get(
                row["current_status"]
            )
            outcome_is_valid = (
                provider_outcome == expected_outcome
                if expected_outcome is not None
                else (
                    row["current_status"] == "provider_failed"
                    and (
                        provider_outcome == "provider_failed"
                        or (
                            provider_outcome in {"output", "timed_out", "provider_inactive"}
                            and row["failure_classification"] in {
                                "provider_descriptor_failure",
                                "provider_descriptor_changed",
                                "unexpected_inactive_result",
                            }
                        )
                    )
                )
                or (
                    row["current_status"] == "stale_context"
                    and provider_outcome
                    in {"output", "provider_failed", "timed_out"}
                )
                or (
                    row["current_status"] == "interrupted"
                    and (
                        (raw_row is None and provider_outcome is None)
                        or (raw_row is not None and provider_outcome is not None)
                    )
                )
            )
            if not outcome_is_valid:
                raise IntegrityInspectionError(
                    "provider result outcome contradicts terminal status"
                )

        authoritative_provider_result = (
            provider_result_contract
            if provider_result_contract is not None
            else raw_provider_result
        )
        if (
            authoritative_provider_result is not None
            and not synthetic_runtime_failure
        ):
            try:
                validate_provider_result_against_configuration(
                    authoritative_provider_result,
                    configuration_contract,
                )
            except ValidationError as exc:
                raise IntegrityInspectionError(
                    "provider result differs from immutable configuration snapshot"
                ) from exc

        task_row = connection.execute(
            """
            SELECT task_id, session_id, project_scope_id, status
            FROM tasks
            WHERE task_id = ?
            """,
            (row["task_id"],),
        ).fetchone()
        if (
            task_row is None
            or task_row["session_id"] != row["session_id"]
            or task_row["project_scope_id"] != row["project_scope_id"]
        ):
            raise IntegrityInspectionError(
                "invocation task relationship cannot be reproduced"
            )
        if row["task_transition_id"] is not None:
            task_transition = connection.execute(
                """
                SELECT *
                FROM task_state_transitions
                WHERE transition_id = ?
                """,
                (row["task_transition_id"],),
            ).fetchone()
            expected_task_status = (
                "completed"
                if row["task_disposition"] == "completed"
                else "failed"
            )
            expected_task_reason = (
                "i4b_validated_response_sufficient"
                if expected_task_status == "completed"
                else f"i4b_{row['current_status']}"
            )
            if (
                task_transition is None
                or task_transition["task_id"] != row["task_id"]
                or task_transition["from_status"] != "active"
                or task_transition["to_status"] != expected_task_status
                or task_transition["reason_code"] != expected_task_reason
                or task_transition["changed_at"] != row["completed_at"]
                or task_transition["changed_by"] != "governance_kernel"
                or task_row["status"] != expected_task_status
            ):
                raise IntegrityInspectionError(
                    "I2 task transition relationship cannot be reproduced"
                )
        elif row["task_disposition"] in {"completed", "failed"}:
            raise IntegrityInspectionError(
                "terminal task disposition lacks its I2 transition"
            )

        value = {
            "anchor": {
                "content_hash": anchor["content_hash"],
                "created_at": anchor["created_at"],
                "integrity_status": anchor["integrity_status"],
                "lifecycle_state": anchor["lifecycle_state"],
                "project_scope_id": anchor["project_scope_id"],
                "provenance": parse_json(anchor["provenance_json"]),
                "reference_id": anchor["reference_id"],
                "reference_kind": anchor["reference_kind"],
            },
            "captured_provider_result": (
                None
                if raw_provider_result is None
                else raw_provider_result.canonical_value()
            ),
            "invocation": {
                "completed_at": row["completed_at"],
                "context_package_hash": row["context_package_hash"],
                "context_package_id": row["context_package_id"],
                "current_status": row["current_status"],
                "failure_classification": row["failure_classification"],
                "model_input_packet": packet,
                "model_input_packet_hash": row["model_input_packet_hash"],
                "model_invocation_id": row["model_invocation_id"],
                "output_schema_hash": row["output_schema_hash"],
                "output_schema_id": row["output_schema_id"],
                "prepared_at": row["prepared_at"],
                "project_scope_id": row["project_scope_id"],
                "provider_call_attempt_id": row["provider_call_attempt_id"],
                "provider_configuration": configuration,
                "provider_configuration_hash": row["provider_configuration_hash"],
                "provider_descriptor": provider,
                "provider_result": provider_result_value,
                "request": request,
                "request_hash": row["request_hash"],
                "retry_of_invocation_id": row["retry_of_invocation_id"],
                "runtime_identity_hash": row["runtime_identity_hash"],
                "runtime_identity_id": row["runtime_identity_id"],
                "session_id": row["session_id"],
                "started_at": row["started_at"],
                "submission": submission,
                "submission_hash": row["submission_hash"],
                "task_context_finalization_hash": row[
                    "task_context_finalization_hash"
                ],
                "task_context_finalization_id": row[
                    "task_context_finalization_id"
                ],
                "task_disposition": row["task_disposition"],
                "task_id": row["task_id"],
                "task_memory_projection_hash": row[
                    "task_memory_projection_hash"
                ],
                "task_transition_id": row["task_transition_id"],
            },
            "model_output": output_value,
            "raw_output_capture": raw_value,
            "state_transitions": transitions,
            "terminal_finalization": terminal,
        }
        canonical = canonical_json_text(value)
        return InvocationReconstruction(
            canonical_json=canonical,
            content_hash=sha256_canonical_json(value),
            raw_output_bytes=raw_bytes,
        )

    def _verify_historical_public_parents(
        self,
        reconstruction: InvocationReconstruction,
    ) -> None:
        value = reconstruction.value
        invocation = value["invocation"]
        submission = invocation["submission"]
        try:
            spec = InvocationSpec.from_mapping(submission["spec"])
            descriptor = _provider_descriptor_from_value(
                submission["provider_descriptor"]
            )
        except (KeyError, TypeError, ValidationError) as exc:
            raise IntegrityInspectionError(
                "invocation submission cannot bind historical parents"
            ) from exc

        package_result = self._context.reconstruct_context_package(
            spec.context_package_id
        )
        package = package_result["value"]
        if (
            not package_result["integrity_verified"]
            or not package_result["historical_integrity_verified"]
            or package_result["content_hash"] != spec.context_package_hash
            or package["context_package_id"] != spec.context_package_id
            or package["task_id"] != spec.task_id
            or package["session_id"] != spec.session_id
            or package["project_scope_id"] != spec.project_scope_id
            or package["status"] != "accepted"
            or package["contamination_status"] != "clean"
            or not package["bridge_context_ready"]
        ):
            raise IntegrityInspectionError(
                "historical I4-A context package cannot be reproduced"
            )
        manifest_result = self._context.reconstruct_retrieval_manifest(
            package["retrieval_manifest_id"]
        )
        manifest = manifest_result["value"]
        if (
            not manifest_result["integrity_verified"]
            or manifest_result["content_hash"]
            != package["retrieval_manifest_hash"]
            or manifest["retrieval_manifest_id"]
            != package["retrieval_manifest_id"]
            or manifest["task_id"] != spec.task_id
            or manifest["session_id"] != spec.session_id
            or manifest["project_scope_id"] != spec.project_scope_id
            or manifest["task_context_finalization_id"]
            != package["task_context_finalization_id"]
            or manifest["task_memory_projection_hash"]
            != package["task_memory_projection_hash"]
            or manifest["status"] != "accepted"
            or manifest["finalization_hash"]
            != invocation["task_context_finalization_hash"]
        ):
            raise IntegrityInspectionError(
                "historical I4-A retrieval manifest cannot be reproduced"
            )
        identity = self._identity.reconstruct(spec.runtime_identity_id)
        self._validate_model_binding(spec, identity)
        resolve_response_schema(
            spec.output_schema_id,
            spec.output_schema_hash,
        )
        expected_packet = self._packet(
            spec,
            descriptor,
            _PublicBindings(
                package=package,
                manifest=manifest,
                identity=identity,
                current_ready=False,
                identity_current=False,
            ),
        )
        if (
            expected_packet.canonical_value()
            != invocation["model_input_packet"]
            or expected_packet.content_hash
            != invocation["model_input_packet_hash"]
        ):
            raise IntegrityInspectionError(
                "historical model-input packet parents cannot be reproduced"
            )

    def _prepared_from_reconstruction(
        self,
        reconstruction: InvocationReconstruction,
    ) -> PreparedInvocation:
        invocation = reconstruction.value["invocation"]
        submission = invocation["submission"]
        try:
            spec = InvocationSpec.from_mapping(submission["spec"])
            descriptor = _provider_descriptor_from_value(
                submission["provider_descriptor"]
            )
            packet = self._model_input_packet_from_value(
                invocation["model_input_packet"]
            )
            request = InvocationRequest(
                spec=spec,
                provider_descriptor=descriptor,
                model_input_packet=packet,
            )
        except (KeyError, TypeError, ValidationError) as exc:
            raise IntegrityInspectionError(
                "persisted invocation cannot be prepared for finalization"
            ) from exc
        package = self._context.reconstruct_context_package(
            spec.context_package_id
        )["value"]
        memory_ids, evidence_ids = self._source_ids(package)
        return PreparedInvocation(
            request=request,
            task_section=packet.canonical_value()["task"],
            allowed_memory_ids=memory_ids,
            allowed_evidence_ids=evidence_ids,
        )

    def finalize_interrupted(
        self,
        model_invocation_id: str,
        *,
        finalized_at: str,
        invocation_transition_id: str,
        model_output_id: str,
        task_transition_id: str,
        runtime_principal: str,
    ) -> InvocationReconstruction:
        """Explicitly classify a visible incomplete attempt; never retry it."""

        reconstruction = self.reconstruct(model_invocation_id)
        status = reconstruction.value["invocation"]["current_status"]
        if status == "interrupted":
            return reconstruction
        if status not in {"in_progress", "raw_output_captured"}:
            raise ConflictError(
                "only an in-progress or raw-captured invocation may be "
                "explicitly interrupted"
            )
        prepared = self._prepared_from_reconstruction(reconstruction)
        provider_result: ProviderCallResult | None = None
        raw_capture: RawOutputCapture | None = None
        if status == "raw_output_captured":
            raw_capture = self.reconstruct_raw_output(model_invocation_id)
            provider_result = self._provider_result_from_value(
                reconstruction.value["captured_provider_result"],
                raw_output=raw_capture.raw_bytes,
            )
        return self.finalize(
            prepared,
            provider_result=provider_result,
            raw_capture=raw_capture,
            failure_classification="runtime_interrupted",
            explicitly_interrupted=True,
            finalized_at=finalized_at,
            invocation_transition_id=invocation_transition_id,
            model_output_id=model_output_id,
            task_transition_id=task_transition_id,
            runtime_principal=runtime_principal,
        )

    def reconstruct(
        self,
        model_invocation_id: str,
    ) -> InvocationReconstruction:
        def operation(
            connection: sqlite3.Connection,
        ) -> InvocationReconstruction:
            connection.execute("BEGIN")
            return self._reconstruct_connection(
                connection,
                model_invocation_id,
            )

        reconstruction = self._kernel.read(operation)
        self._verify_historical_public_parents(reconstruction)
        return reconstruction
