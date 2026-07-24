"""Deterministic file-backed database path resolution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path

from batch87_apprentice.common.errors import ConfigurationError

DATABASE_PATH_ENV = "B87_DATABASE_PATH"
DEFAULT_DATABASE_RELATIVE_PATH = Path("data") / "db" / "batch87-apprentice.sqlite3"


def repository_root() -> Path:
    """Return the source checkout root without consulting process cwd."""

    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """Immutable settings for one SQLite database."""

    path: Path
    busy_timeout_ms: int = 5_000

    def __post_init__(self) -> None:
        raw_path = str(self.path)
        if not raw_path or raw_path == ":memory:" or raw_path.startswith("file:"):
            raise ConfigurationError("the governed database must be a filesystem path")
        if self.busy_timeout_ms < 1:
            raise ConfigurationError("busy_timeout_ms must be positive")
        resolved = Path(self.path).expanduser().resolve(strict=False)
        if resolved.exists() and resolved.is_dir():
            raise ConfigurationError("database path points to a directory")
        object.__setattr__(self, "path", resolved)


def resolve_database_config(
    database_path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> DatabaseConfig:
    """Resolve explicit path, then environment, then the repository default."""

    environment = os.environ if environ is None else environ
    candidate: str | Path
    if database_path is not None:
        candidate = database_path
    elif environment.get(DATABASE_PATH_ENV):
        candidate = environment[DATABASE_PATH_ENV]
    else:
        candidate = repository_root() / DEFAULT_DATABASE_RELATIVE_PATH
    return DatabaseConfig(Path(candidate))
