"""Public repository protocols for the B87-I1 persistence boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .contracts import (
    ControlledResiliencePayload,
    Entity,
    EntityAlias,
    EvidenceItem,
    EvidenceLink,
    RecordEnvelope,
    ReferenceAnchor,
    RuntimeInstance,
    Scope,
)


class RuntimeRepositoryProtocol(Protocol):
    def start(self, instance: RuntimeInstance) -> None: ...

    def get(self, runtime_instance_id: str) -> Mapping[str, Any]: ...


class EntityRepositoryProtocol(Protocol):
    def create(self, entity: Entity) -> None: ...

    def add_alias(self, alias: EntityAlias) -> None: ...

    def get(self, entity_id: str) -> Mapping[str, Any]: ...


class ScopeRepositoryProtocol(Protocol):
    def create(self, scope: Scope) -> None: ...

    def get(self, scope_id: str) -> Mapping[str, Any]: ...


class RecordRepositoryProtocol(Protocol):
    def create(self, envelope: RecordEnvelope) -> str: ...

    def get(self, record_id: str) -> Mapping[str, Any]: ...


class EvidenceRepositoryProtocol(Protocol):
    def create(self, item: EvidenceItem) -> None: ...

    def link(self, link: EvidenceLink) -> None: ...

    def get(self, evidence_id: str) -> Mapping[str, Any]: ...


class ReferenceAnchorRepositoryProtocol(Protocol):
    def register(self, anchor: ReferenceAnchor) -> str: ...

    def get(self, reference_id: str) -> Mapping[str, Any]: ...


class ControlledResilienceRepositoryProtocol(Protocol):
    def create(
        self,
        envelope: RecordEnvelope,
        payload: ControlledResiliencePayload,
        *,
        anchors: Sequence[ReferenceAnchor] = (),
        evidence_items: Sequence[EvidenceItem] = (),
    ) -> str: ...

    def get(self, record_id: str) -> Mapping[str, Any]: ...
