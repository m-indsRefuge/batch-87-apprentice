"""Composition root for the B87-I1 persistence kernel."""

from __future__ import annotations

from pathlib import Path

from .config import DatabaseConfig
from .integrity import IntegrityInspector
from .migrations import MigrationRunner
from .repositories import (
    ControlledResilienceRepository,
    EntityRepository,
    EvidenceRepository,
    RecordRepository,
    ReferenceAnchorRepository,
    RuntimeRepository,
    ScopeRepository,
)
from .transactions import PersistenceKernel


class PersistenceService:
    """Expose implemented repositories over one governed kernel."""

    def __init__(self, config: DatabaseConfig) -> None:
        from batch87_apprentice.memory.construct_integrity import (
            ConstructIntegrityInspector,
        )
        from batch87_apprentice.memory.construct_repository import (
            ConstructMemoryRepository,
        )

        self.config = config
        kernel = PersistenceKernel(config)
        self.runtime_instances = RuntimeRepository(kernel)
        self.entities = EntityRepository(kernel)
        self.scopes = ScopeRepository(kernel)
        self.records = RecordRepository(kernel)
        self.evidence = EvidenceRepository(kernel)
        self.reference_anchors = ReferenceAnchorRepository(kernel)
        self.controlled_resilience = ControlledResilienceRepository(kernel)
        self.construct_memory = ConstructMemoryRepository(kernel)
        self.construct_integrity = ConstructIntegrityInspector(kernel)
        self.integrity = IntegrityInspector(kernel)

    @classmethod
    def initialize(
        cls,
        config: DatabaseConfig,
        *,
        migrations_path: Path | None = None,
    ) -> PersistenceService:
        """Apply verified migrations before exposing any repository."""

        MigrationRunner(config, migrations_path).apply_all()
        return cls(config)
