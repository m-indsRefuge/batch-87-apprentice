"""Read-only factual permission projection over accepted B87-I2 truth."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from batch87_apprentice.common.canonical_json import (
    canonical_json_text,
    parse_json,
)
from batch87_apprentice.common.errors import IntegrityInspectionError
from batch87_apprentice.common.hashing import hashes_match, sha256_canonical_json
from batch87_apprentice.common.identifiers import validate_identifier
from batch87_apprentice.common.timestamps import parse_canonical_utc
from batch87_apprentice.governance.contracts import PermissionProfile
from batch87_apprentice.persistence.config import DatabaseConfig
from batch87_apprentice.persistence.task_runtime_store import TaskRuntimeStore
from batch87_apprentice.persistence.transactions import PersistenceKernel


class PermissionProfileProjection:
    """Verify and expose I2 permission truth without creating memory state."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._kernel = PersistenceKernel(config)
        self._task_runtime = TaskRuntimeStore(config)

    @staticmethod
    def _blocked(detail: str) -> IntegrityInspectionError:
        return IntegrityInspectionError(
            f"permission projection fails closed: {detail}"
        )

    @staticmethod
    def _assert_no_memory_profile(connection: Any) -> None:
        registry = connection.execute(
            """
            SELECT record_family, record_type
            FROM memory_record_types
            WHERE record_type = 'permission_profile'
            ORDER BY record_family
            """
        ).fetchall()
        if registry:
            raise PermissionProfileProjection._blocked(
                "permission_profile was inserted into the memory registry"
            )
        forbidden_table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN (
                  'permission_profile',
                  'self_model_permission_profiles',
                  'self_episodic_permission_profiles'
              )
            ORDER BY name
            """
        ).fetchone()
        if forbidden_table is not None:
            raise PermissionProfileProjection._blocked(
                f"forbidden C1 permission table exists: {forbidden_table['name']}"
            )

    @staticmethod
    def _verified_stored_profile(
        connection: Any,
        permission_profile_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT *
            FROM permission_profiles
            WHERE permission_profile_id = ?
            """,
            (permission_profile_id,),
        ).fetchone()
        if row is None:
            raise PermissionProfileProjection._blocked(
                "runtime-selected I2 permission profile is missing"
            )
        try:
            canonical_value = parse_json(row["canonical_json"])
        except Exception as exc:
            raise PermissionProfileProjection._blocked(
                "stored I2 permission profile JSON is malformed"
            ) from exc
        if (
            not isinstance(canonical_value, dict)
            or canonical_json_text(canonical_value) != row["canonical_json"]
        ):
            raise PermissionProfileProjection._blocked(
                "stored I2 permission profile JSON is not canonical"
            )
        recomputed = sha256_canonical_json(canonical_value)
        if not hashes_match(row["content_hash"], recomputed):
            raise PermissionProfileProjection._blocked(
                "stored I2 permission profile hash mismatches canonical content"
            )
        column_value = {
            "allowed_action_classes": parse_json(
                row["allowed_action_classes_json"]
            ),
            "allowed_tools": parse_json(row["allowed_tools_json"]),
            "effective_from": row["effective_from"],
            "permission_profile_id": row["permission_profile_id"],
            "principal": row["principal"],
            "prohibited_action_classes": parse_json(
                row["prohibited_action_classes_json"]
            ),
            "prohibited_tools": parse_json(row["prohibited_tools_json"]),
            "version": row["version"],
        }
        if column_value != canonical_value:
            raise PermissionProfileProjection._blocked(
                "stored I2 permission profile columns differ from canonical content"
            )
        return {
            "canonical_json": row["canonical_json"],
            "content_hash": row["content_hash"],
            "status": row["status"],
            "value": canonical_value,
        }

    def current_runtime(
        self,
        permission_profile: PermissionProfile,
        *,
        effective_at: str,
    ) -> Mapping[str, Any]:
        """Project one runtime-selected profile after independent I2 verification."""

        if not isinstance(permission_profile, PermissionProfile):
            raise TypeError("permission_profile must be an I2 PermissionProfile")
        parse_canonical_utc(effective_at, field="effective_at")

        def operation(connection: Any) -> dict[str, Any]:
            self._assert_no_memory_profile(connection)
            stored = self._verified_stored_profile(
                connection,
                permission_profile.permission_profile_id,
            )
            selected_value = permission_profile.canonical_value()
            if (
                stored["value"] != selected_value
                or stored["canonical_json"] != permission_profile.canonical_json
                or not hashes_match(
                    stored["content_hash"],
                    permission_profile.content_hash,
                )
            ):
                raise self._blocked(
                    "runtime-selected profile differs from immutable I2 storage"
                )
            applicable = (
                stored["status"] == "active"
                and permission_profile.principal == "apprentice"
                and permission_profile.effective_from <= effective_at
            )
            if not applicable:
                raise self._blocked(
                    "runtime-selected profile is inactive or not yet applicable"
                )
            return {
                "applicable": True,
                "canonical_json": stored["canonical_json"],
                "content_hash": stored["content_hash"],
                "effective_at": effective_at,
                "integrity_verified": True,
                "permission_profile": stored["value"],
                "permission_profile_id": (
                    permission_profile.permission_profile_id
                ),
                "projection_kind": "current_runtime",
                "source": "i2_permission_profiles",
            }

        return self._kernel.read(operation)

    def historical_task(self, task_id: str) -> Mapping[str, Any]:
        """Expose exact decision-time I2 reconstruction without replacing its result."""

        validate_identifier(task_id, field="task_id")
        reconstruction = self._task_runtime.reconstruct(task_id)
        value = reconstruction["value"]
        decision = value["decision"]
        profile = value["permission_profile"]
        profile_id = decision.get("permission_profile_id")
        profile_hash = decision.get("permission_profile_hash")
        if profile_id != profile.get("permission_profile_id"):
            raise self._blocked(
                "historical decision profile ID differs from reconstructed I2 profile"
            )
        recomputed_profile_hash = sha256_canonical_json(profile)
        if not isinstance(profile_hash, str) or not hashes_match(
            profile_hash,
            recomputed_profile_hash,
        ):
            raise self._blocked(
                "historical decision profile hash differs from reconstructed I2 profile"
            )
        if decision.get("effective_at") is None:
            raise self._blocked("historical decision lacks its effective time")

        self._kernel.read(self._assert_no_memory_profile)
        return {
            "applicable": bool(decision.get("permission_profile_applicable")),
            "authority_inputs": value["authority_inputs"],
            "decision": decision,
            "decision_outcome": decision.get("outcome"),
            "effective_at": decision["effective_at"],
            "historical_reconstruction": reconstruction,
            "human_approval_inputs": value["human_approval_inputs"],
            "integrity_verified": bool(reconstruction["integrity_verified"]),
            "permission_profile": profile,
            "permission_profile_hash": profile_hash,
            "permission_profile_id": profile_id,
            "projection_kind": "historical_task",
            "source": "i2_task_runtime_reconstruction",
            "stop_event": value["stop_event"],
            "task_id": task_id,
            "task_status": value["task_status"],
        }
