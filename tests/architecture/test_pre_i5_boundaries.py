from __future__ import annotations

import ast
from dataclasses import fields
import inspect
from pathlib import Path

from batch87_apprentice.evaluation import (
    CandidateMetadata,
    DeterministicEvaluationService,
    EvaluationConfiguration,
    EvaluationResult,
    ResourceLimits,
    RuntimeObservation,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "batch87_apprentice"
EVALUATION_FILES = tuple(sorted((PACKAGE / "evaluation").glob("*.py")))

FORBIDDEN_IMPORT_ROOTS = {
    "aiohttp",
    "anthropic",
    "asyncio",
    "http",
    "huggingface_hub",
    "importlib",
    "llama_cpp",
    "multiprocessing",
    "ollama",
    "openai",
    "requests",
    "socket",
    "subprocess",
    "transformers",
    "urllib",
}
FORBIDDEN_CONTRACT_FIELDS = {
    "credential",
    "endpoint",
    "executable_path",
    "host",
    "model_path",
    "port",
    "provider_id",
    "secret",
    "token",
    "url",
}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text("utf-8-sig"), filename=str(path))


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_pre_i5_has_no_network_process_live_provider_or_model_runtime_imports() -> None:
    for path in EVALUATION_FILES:
        imported = _imported_modules(path)
        roots = {module.split(".", 1)[0] for module in imported}
        assert not roots & FORBIDDEN_IMPORT_ROOTS, path
        assert not any(
            module.startswith(
                (
                    "batch87_apprentice.experimental",
                    "batch87_apprentice.invocation",
                    "batch87_apprentice.providers",
                )
            )
            for module in imported
        ), path


def test_production_packages_do_not_depend_on_experimental_laboratories() -> None:
    for path in PACKAGE.rglob("*.py"):
        if "experimental" in path.relative_to(PACKAGE).parts:
            continue
        assert not any(
            module.startswith("batch87_apprentice.experimental")
            for module in _imported_modules(path)
        ), path


def test_public_pre_i5_contracts_have_no_live_capability_fields() -> None:
    contract_types = (
        CandidateMetadata,
        EvaluationConfiguration,
        EvaluationResult,
        ResourceLimits,
        RuntimeObservation,
    )
    names = {
        field.name
        for contract_type in contract_types
        for field in fields(contract_type)
    }
    assert not names & FORBIDDEN_CONTRACT_FIELDS


def test_public_service_cannot_receive_provider_or_execution_capabilities() -> None:
    constructor = set(inspect.signature(DeterministicEvaluationService).parameters)
    schedule = set(
        inspect.signature(DeterministicEvaluationService.schedule).parameters
    )
    mock_campaign = set(
        inspect.signature(
            DeterministicEvaluationService.record_mock_campaign
        ).parameters
    )

    assert not constructor & FORBIDDEN_CONTRACT_FIELDS
    assert not schedule & FORBIDDEN_CONTRACT_FIELDS
    assert not mock_campaign & FORBIDDEN_CONTRACT_FIELDS
    assert not hasattr(DeterministicEvaluationService, "invoke")
    assert not hasattr(DeterministicEvaluationService, "execute")


def test_evaluation_package_does_not_export_the_writable_store() -> None:
    package_source = (PACKAGE / "evaluation" / "__init__.py").read_text("utf-8")
    assert "EvaluationStore" not in package_source


def test_project_dependency_set_remains_empty() -> None:
    assert "dependencies = []" in (ROOT / "pyproject.toml").read_text("utf-8")
