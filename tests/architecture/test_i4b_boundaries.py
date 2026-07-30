from __future__ import annotations

import ast
import builtins
import importlib
import inspect
import logging
import os
from pathlib import Path
import random
import secrets
import socket
import sqlite3
import subprocess
import time

import pytest

from batch87_apprentice.invocation.service import InvocationBridge
from batch87_apprentice.invocation.store import InvocationStore
from batch87_apprentice.persistence.service import PersistenceService
from batch87_apprentice.providers.contracts import (
    DeterministicMockFixture,
    ProviderCallResult,
    ProviderDescriptor,
    ProviderProtocol,
)
from batch87_apprentice.providers.inactive import InactiveProvider
from batch87_apprentice.providers.mock import DeterministicMockProvider
from batch87_apprentice.providers.registry import ProviderRegistry

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "batch87_apprentice"
PROVIDER_FILES = (
    SRC / "providers" / "inactive.py",
    SRC / "providers" / "mock.py",
)
I4B_FILES = tuple((SRC / "invocation").glob("*.py"))
FORBIDDEN_IMPORT_ROOTS = {
    "asyncio",
    "builtins",
    "ctypes",
    "http",
    "importlib",
    "logging",
    "multiprocessing",
    "os",
    "pathlib",
    "random",
    "requests",
    "secrets",
    "shutil",
    "socket",
    "sqlite3",
    "subprocess",
    "tempfile",
    "time",
    "urllib",
}
FORBIDDEN_CALL_NAMES = {
    "eval",
    "exec",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "__import__",
}


def parsed(path: Path) -> ast.Module:
    return ast.parse(path.read_text("utf-8"), filename=str(path))


def test_shipped_provider_implementations_have_no_forbidden_imports_or_calls() -> None:
    for path in PROVIDER_FILES:
        tree = parsed(path)
        imported_roots = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_roots.update(
            (node.module or "").split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        attributes = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }

        assert not imported_roots & FORBIDDEN_IMPORT_ROOTS
        assert not calls & FORBIDDEN_CALL_NAMES
        assert not attributes & {
            "environ",
            "getenv",
            "now",
            "open",
            "randint",
            "random",
            "run",
            "system",
            "time",
            "urlopen",
        }


def test_provider_interface_supplies_only_immutable_bytes() -> None:
    protocol = inspect.signature(ProviderProtocol.invoke)
    inactive = inspect.signature(InactiveProvider.invoke)
    mock = inspect.signature(DeterministicMockProvider.invoke)

    assert tuple(protocol.parameters) == ("self", "canonical_input_bytes")
    assert tuple(inactive.parameters) == ("self", "canonical_input_bytes")
    assert tuple(mock.parameters) == ("self", "canonical_input_bytes")
    assert "bytes" in str(protocol.parameters["canonical_input_bytes"].annotation)


def test_shipped_provider_runtime_calls_have_no_observable_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeterministicMockFixture(
        fixture_id="purity_fixture",
        raw_output=b"exact fixture bytes",
        declared_encoding="utf-8",
    )
    providers = (InactiveProvider(), DeterministicMockProvider(fixture))
    observed: list[str] = []

    def blocked(name: str):
        def operation(*args, **kwargs):
            observed.append(name)
            raise AssertionError(f"shipped provider attempted {name}")

        return operation

    class DeniedEnvironment(dict[str, str]):
        def __getitem__(self, key: str) -> str:
            return blocked("environment read")(key)

        def get(self, key: str, default=None):
            return blocked("environment read")(key, default)

    with monkeypatch.context() as isolated:
        for target, attribute, name in (
            (builtins, "open", "filesystem access"),
            (builtins, "print", "uncontrolled output"),
            (importlib, "import_module", "dynamic module loading"),
            (logging.Logger, "_log", "logging"),
            (os, "getenv", "environment access"),
            (os, "system", "process creation"),
            (random, "random", "randomness"),
            (secrets, "token_bytes", "credential randomness"),
            (socket, "socket", "network access"),
            (sqlite3, "connect", "database access"),
            (subprocess, "Popen", "process creation"),
            (subprocess, "run", "process creation"),
            (time, "monotonic", "clock access"),
            (time, "perf_counter", "clock access"),
            (time, "time", "clock access"),
        ):
            isolated.setattr(target, attribute, blocked(name))
        isolated.setattr(os, "environ", DeniedEnvironment())

        descriptors = tuple(provider.describe() for provider in providers)
        results = tuple(provider.invoke(b"canonical input") for provider in providers)

    assert all(isinstance(value, ProviderDescriptor) for value in descriptors)
    assert all(isinstance(value, ProviderCallResult) for value in results)
    assert results[0].outcome == "provider_inactive"
    assert results[1].raw_output == b"exact fixture bytes"
    assert observed == []


def test_registry_and_bridge_do_not_accept_arbitrary_provider_implementations() -> None:
    assert tuple(inspect.signature(ProviderRegistry).parameters) == (
        "mock_fixture",
    )
    assert not hasattr(ProviderRegistry, "register")
    assert "provider" not in inspect.signature(InvocationBridge).parameters
    assert "registry" not in inspect.signature(InvocationBridge).parameters



def test_public_composition_root_does_not_expose_writable_invocation_store() -> None:
    source = inspect.getsource(PersistenceService.__init__)
    assert "model_invocations" not in source
    assert "InvocationStore" not in source


def test_public_invocation_surface_cannot_inject_processing_or_terminal_state() -> None:
    invoke_parameters = set(inspect.signature(InvocationBridge.invoke).parameters)
    assert "provider" not in invoke_parameters
    assert "registry" not in invoke_parameters
    assert "processing" not in invoke_parameters
    assert "proposed_terminal_status" not in invoke_parameters

    finalize_parameters = set(inspect.signature(InvocationStore.finalize).parameters)
    assert "processing" not in finalize_parameters
    assert "proposed_terminal_status" not in finalize_parameters

    package_source = (SRC / "invocation" / "__init__.py").read_text("utf-8")
    assert "InvocationStore" not in package_source

def test_i4b_runtime_has_no_external_provider_or_experimental_imports() -> None:
    forbidden = {
        "anthropic",
        "cohere",
        "google.generativeai",
        "huggingface_hub",
        "llama_cpp",
        "ollama",
        "openai",
        "requests",
        "transformers",
        "batch87_apprentice.experimental",
    }
    for path in I4B_FILES:
        source = path.read_text("utf-8")
        assert not any(name in source for name in forbidden), path


def test_i4b_consumes_only_public_i4a_reconstruction_and_readiness_methods() -> None:
    source = (SRC / "invocation" / "store.py").read_text("utf-8")

    assert ".reconstruct_context_package(" in source
    assert ".reconstruct_retrieval_manifest(" in source
    assert ".assess_context_readiness(" in source
    for private_method in (
        "._load_package(",
        "._load_manifest(",
        "._assemble_in_transaction(",
        "._materialization_binding_findings(",
    ):
        assert private_method not in source
    for direct_table in (
        "FROM context_packages",
        "FROM retrieval_manifests",
        "FROM ordered_context_manifest_entries",
        "FROM retrieval_manifest_entries",
    ):
        assert direct_table not in source


def test_project_dependencies_remain_empty() -> None:
    project = (ROOT / "pyproject.toml").read_text("utf-8")
    assert "dependencies = []" in project
