from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_d0_architecture.py"


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_d0_architecture",
        VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load validator: {VALIDATOR_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load_validator()


def test_parse_headings_ignores_fenced_content() -> None:
    text = """# Title

## Section

```text
# Not a heading
### Also not a heading
```

### Child
"""

    assert validator.parse_headings(text) == [
        (1, 1, "Title"),
        (3, 2, "Section"),
        (10, 3, "Child"),
    ]


def test_document_structure_rejects_multiple_h1() -> None:
    report = validator.ValidationReport(phase="B87-D0")
    text = """# Title

**Status:** Architecture baseline

# Duplicate
"""

    validator.validate_document_structure(
        report,
        "A1",
        "docs/architecture/example.md",
        text,
    )

    assert any(item.code == "DOC-H1-COUNT" for item in report.errors)


def test_closure_blocking_invariant_creates_blocker() -> None:
    report = validator.ValidationReport(phase="B87-D0")
    invariant = {
        "id": "B87-CGR-005",
        "required_in": ["A2"],
        "required_literals": ["B87-D0-A4.2"],
        "closure_blocking": True,
    }

    validator.validate_invariant(report, invariant, {"A2": "No amendment reference."})

    assert not report.errors
    assert len(report.blockers) == 1
    assert report.blockers[0].code == "B87-CGR-005"


def test_forbidden_global_pattern_is_reported() -> None:
    report = validator.ValidationReport(phase="B87-D0")
    invariant = {
        "id": "B87-PERM-001",
        "required_in": [],
        "forbidden_global_patterns": [r"B87-S1 permits Execute"],
    }

    validator.validate_invariant(
        report,
        invariant,
        {"A1": "B87-S1 permits Execute"},
    )

    assert len(report.errors) == 1
    assert report.errors[0].code == "B87-PERM-001"


def test_load_manifest_rejects_missing_required_keys(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"phase": "B87-D0"}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing keys"):
        validator.load_manifest(manifest_path)


def test_report_closure_ready_requires_no_errors_or_blockers() -> None:
    report = validator.ValidationReport(phase="B87-D0")
    assert report.closure_ready

    report.add("warning", "WARN", "Warning only")
    assert report.closure_ready

    report.add("blocker", "BLOCK", "Closure blocker")
    assert not report.closure_ready

    report.add("error", "ERROR", "Structural error")
    assert not report.structurally_valid
    assert not report.closure_ready
