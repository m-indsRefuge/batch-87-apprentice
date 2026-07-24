"""The single governed application write boundary."""

from __future__ import annotations

from collections.abc import Callable
import sqlite3
from typing import TypeVar

from batch87_apprentice.common.errors import (
    ConflictError,
    PersistenceError,
    TransactionError,
)

from .config import DatabaseConfig
from .connection import open_connection, read_connection

T = TypeVar("T")


class PersistenceKernel:
    """Own all runtime database reads and writes for one configured database."""

    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config

    def read(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        """Run an operation on a verified query-only connection."""

        try:
            with read_connection(self.config) as connection:
                return operation(connection)
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise TransactionError("governed read failed") from exc

    def write(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        """Run one operation atomically under BEGIN IMMEDIATE."""

        connection = open_connection(self.config)
        try:
            connection.execute("BEGIN IMMEDIATE")
            result = operation(connection)
            connection.commit()
            return result
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                connection.rollback()
            raise ConflictError("governed write violated an integrity constraint") from exc
        except PersistenceError:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.rollback()
            raise TransactionError("governed write failed") from exc
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
