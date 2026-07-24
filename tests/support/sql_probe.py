"""Narrow SQL access for persistence tests and deliberate corruption fixtures."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import re
import sqlite3
from typing import TypeVar

from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.integrity import (
    IntegrityInspector,
    IntegrityReport,
)
from batch87_apprentice.persistence.migrations import MigrationRunner
from batch87_apprentice.persistence.transactions import PersistenceKernel

T = TypeVar("T")

_TRIGGER_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class SqlProbe:
    """Expose raw SQL only from the test tree, never from the service API."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._kernel = PersistenceKernel(config)

    def read(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        return self._kernel.read(operation)

    def write(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        return self._kernel.write(operation)

    def corrupt_after_dropping_triggers(
        self,
        trigger_names: Iterable[str],
        operation: Callable[[sqlite3.Connection], T],
    ) -> T:
        """Create otherwise-impossible state in one disposable test transaction."""

        names = tuple(trigger_names)
        if not names or any(_TRIGGER_NAME.fullmatch(name) is None for name in names):
            raise ValueError("test corruption requires explicit trigger names")

        def corrupt(connection: sqlite3.Connection) -> T:
            for name in names:
                connection.execute(f'DROP TRIGGER "{name}"')
            return operation(connection)

        return self._kernel.write(corrupt)

    def inspect(
        self,
        *,
        migration_runner: MigrationRunner | None = None,
    ) -> IntegrityReport:
        return IntegrityInspector(
            self._kernel,
            migration_runner=migration_runner,
        ).inspect()
