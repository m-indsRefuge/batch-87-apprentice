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
        self.config = config
        self.kernel = PersistenceKernel(config)
        self.runtime_instances = RuntimeRepository(self.kernel)
        self.entities = EntityRepository(self.kernel)
        self.scopes = ScopeRepository(self.kernel)
        self.records = RecordRepository(self.kernel)
        self.evidence = EvidenceRepository(self.kernel)
        self.reference_anchors = ReferenceAnchorRepository(self.kernel)
        self.controlled_resilience = ControlledResilienceRepository(self.kernel)
        self.integrity = IntegrityInspector(self.kernel)

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
