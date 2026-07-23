"""Explicit failures raised by the B87-I1 persistence boundary."""


class PersistenceError(RuntimeError):
    """Base class for persistence-boundary failures."""


class ConfigurationError(PersistenceError):
    """The database configuration is invalid or unsafe."""


class ConnectionVerificationError(PersistenceError):
    """SQLite could not prove the required connection settings."""


class MigrationError(PersistenceError):
    """A migration could not be applied or verified."""


class MigrationHistoryError(MigrationError):
    """The stored migration history is missing, ahead, or tampered with."""


class TransactionError(PersistenceError):
    """A governed transaction failed."""


class ValidationError(PersistenceError, ValueError):
    """A value does not satisfy a persistence contract."""


class ConflictError(PersistenceError):
    """An immutable identity or record conflicts with stored state."""


class NotFoundError(PersistenceError):
    """A referenced governed object does not exist."""


class IntegrityInspectionError(PersistenceError):
    """The integrity inspector itself could not complete."""
