"""Deterministic fail-closed fixture discovery for B87-PRE-I5."""

from __future__ import annotations

from pathlib import Path

from batch87_apprentice.common.canonical_json import parse_json
from batch87_apprentice.common.errors import ValidationError
from batch87_apprentice.common.hashing import sha256_bytes

from .contracts import (
    DiscoveredFixture,
    FixtureDefinition,
    FixtureSet,
    FixtureSetManifest,
)


def discover_fixture_set(root: Path, manifest: FixtureSetManifest) -> FixtureSet:
    """Discover exactly the files named by an immutable fixture-set manifest."""

    if not isinstance(manifest, FixtureSetManifest):
        raise ValidationError("fixture-set manifest is invalid")
    supplied_root = Path(root)
    if supplied_root.is_symlink():
        raise ValidationError("fixture discovery rejects symbolic links")
    fixture_root = supplied_root.resolve(strict=False)
    if not fixture_root.is_dir():
        raise ValidationError("fixture root does not exist")

    actual: dict[str, Path] = {}
    for path in fixture_root.rglob("*"):
        if path.is_symlink():
            raise ValidationError("fixture discovery rejects symbolic links")
        if not path.is_file():
            continue
        resolved = path.resolve(strict=True)
        try:
            relative = resolved.relative_to(fixture_root).as_posix()
        except ValueError as exc:
            raise ValidationError("fixture escaped the discovery root") from exc
        if relative in actual:
            raise ValidationError("duplicate fixture source was discovered")
        actual[relative] = resolved

    expected = {entry.source_name: entry for entry in manifest.entries}
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    if missing:
        raise ValidationError("fixture set is missing: " + ", ".join(missing))
    if unexpected:
        raise ValidationError(
            "fixture set contains unlisted files: " + ", ".join(unexpected)
        )

    fixtures: list[DiscoveredFixture] = []
    for entry in manifest.entries:
        exact = actual[entry.source_name].read_bytes()
        if sha256_bytes(exact) != entry.content_hash:
            raise ValidationError(
                f"fixture content hash changed: {entry.source_name}"
            )
        try:
            text = exact.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError(
                f"fixture is not UTF-8: {entry.source_name}"
            ) from exc
        definition = FixtureDefinition.from_mapping(parse_json(text))
        fixtures.append(
            DiscoveredFixture(
                definition=definition,
                entry=entry,
                exact_bytes=exact,
            )
        )

    return FixtureSet(manifest=manifest, fixtures=tuple(fixtures))
