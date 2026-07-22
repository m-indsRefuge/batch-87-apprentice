#!/usr/bin/env python3
"""Run strict Batch-87 D0 final-closure validation and create a ZIP bundle."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class StepResult:
    number: int
    label: str
    argv: tuple[str, ...]
    exit_code: int
    output: str
    log_path: Path


class StepFailure(RuntimeError):
    def __init__(self, result: StepResult) -> None:
        super().__init__(
            f"{result.label} failed with exit code {result.exit_code}."
        )
        self.result = result


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError(f"Unable to locate repository root from {start}")


def run_step(
    *,
    number: int,
    label: str,
    argv: list[str],
    repo_root: Path,
    logs_dir: Path,
    allowed_exit_codes: set[int] | None = None,
) -> StepResult:
    allowed = allowed_exit_codes or {0}
    completed = subprocess.run(
        argv,
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    safe_label = "-".join(
        part.lower()
        for part in label.replace("/", " ").replace("_", " ").split()
    )
    log_path = logs_dir / f"{number:02d}-{safe_label}.log"
    log_text = (
        f"Label: {label}\n"
        f"Command: {json.dumps(argv, ensure_ascii=False)}\n"
        f"Exit code: {completed.returncode}\n\n"
        f"{completed.stdout}"
    )
    log_path.write_text(log_text, encoding="utf-8", newline="\n")

    result = StepResult(
        number=number,
        label=label,
        argv=tuple(argv),
        exit_code=completed.returncode,
        output=completed.stdout,
        log_path=log_path,
    )

    print()
    print(f"=== {label} ===")
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    print(f"EXIT: {completed.returncode}")

    if completed.returncode not in allowed:
        raise StepFailure(result)

    return result


def write_summary(
    *,
    path: Path,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    repo_root: Path,
    branch: str,
    commit: str,
    steps: list[StepResult],
    failure: str | None,
    json_path: Path,
    bundle_path: Path,
) -> None:
    lines = [
        "# B87-D0 Final Closure Validation Summary",
        "",
        f"**Status:** {status}  ",
        f"**Started:** {started_at.isoformat()}  ",
        f"**Finished:** {finished_at.isoformat()}  ",
        f"**Repository:** {repo_root}  ",
        f"**Branch:** {branch}  ",
        f"**Commit before closure commit:** {commit}  ",
        "**Validation mode:** strict `--require-closed`",
        "",
        "## Result",
        "",
    ]

    if status == "PASS":
        lines.extend(
            [
                "The finalised D0 corpus passed pytest, strict architecture",
                "conformance, Git diff integrity, and closure-state validation.",
            ]
        )
    else:
        lines.append(f"The run stopped at the first failure: {failure}")

    lines.extend(
        [
            "",
            "## Steps",
            "",
        ]
    )
    for step in steps:
        lines.append(
            f"- {step.number:02d} {step.label}: exit {step.exit_code} "
            f"({step.log_path.name})"
        )

    lines.extend(
        [
            "",
            "## Shareable artefacts",
            "",
            f"- Conformance JSON: {json_path.name if json_path.exists() else 'Not produced'}",
            f"- Logs directory: {steps[0].log_path.parent.name if steps else 'logs'}",
            f"- Bundle: {bundle_path.name}",
            "",
            "## Interpretation boundary",
            "",
            "This strict run establishes D0 architecture closure state only.",
            "It does not validate model behaviour, memory efficacy, or base-model",
            "selection. Those claims require implemented-system evidence.",
        ]
    )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def create_bundle(run_dir: Path, bundle_path: Path) -> None:
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(run_dir.rglob("*")):
            if path.is_file() and path != bundle_path:
                archive.write(path, path.relative_to(run_dir))


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = (
        args.repo_root.resolve()
        if args.repo_root
        else find_repo_root(Path.cwd())
    )

    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    run_dir = repo_root / "artifacts" / "validation-runs" / f"d0-final-{timestamp}"
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    summary_path = run_dir / f"B87-D0-Final-Closure-Summary-{timestamp}.md"
    json_path = run_dir / f"B87-D0-Final-Conformance-{timestamp}.json"
    bundle_path = run_dir / f"B87-D0-Final-Closure-Bundle-{timestamp}.zip"

    started_at = datetime.now().astimezone()
    steps: list[StepResult] = []
    failure: str | None = None
    branch = "unknown"
    commit = "unknown"

    try:
        result = run_step(
            number=1,
            label="READ CURRENT BRANCH",
            argv=["git", "branch", "--show-current"],
            repo_root=repo_root,
            logs_dir=logs_dir,
        )
        steps.append(result)
        branch = result.output.strip()

        result = run_step(
            number=2,
            label="READ CURRENT COMMIT",
            argv=["git", "rev-parse", "HEAD"],
            repo_root=repo_root,
            logs_dir=logs_dir,
        )
        steps.append(result)
        commit = result.output.strip()

        step_specs = [
            (
                3,
                "VERIFY D0 CLOSURE FINALISATION",
                [sys.executable, "scripts/finalize_d0_closure.py", "--check"],
            ),
            (4, "RUN PYTEST", [sys.executable, "-m", "pytest"]),
            (
                5,
                "RUN STRICT D0 ARCHITECTURE CONFORMANCE",
                [
                    sys.executable,
                    "scripts/validate_d0_architecture.py",
                    "--require-closed",
                    "--json-output",
                    str(json_path),
                ],
            ),
            (6, "RUN GIT DIFF CHECK", ["git", "diff", "--check"]),
            (7, "READ GIT DIFF STAT", ["git", "diff", "--stat"]),
            (8, "READ GIT STATUS", ["git", "status", "--short"]),
        ]

        for number, label, command in step_specs:
            result = run_step(
                number=number,
                label=label,
                argv=command,
                repo_root=repo_root,
                logs_dir=logs_dir,
            )
            steps.append(result)

        status = "PASS"
        exit_code = 0
    except (RuntimeError, StepFailure) as exc:
        failure = str(exc)
        status = "FAIL"
        exit_code = 1

    finished_at = datetime.now().astimezone()
    write_summary(
        path=summary_path,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        repo_root=repo_root,
        branch=branch,
        commit=commit,
        steps=steps,
        failure=failure,
        json_path=json_path,
        bundle_path=bundle_path,
    )
    create_bundle(run_dir, bundle_path)

    print()
    print("============================================================")
    print("B87-D0 FINAL CLOSURE ARTEFACTS")
    print("============================================================")
    print(f"Summary: {summary_path}")
    print(f"JSON:    {json_path}")
    print(f"Logs:    {logs_dir}")
    print(f"Bundle:  {bundle_path}")

    if exit_code:
        print(f"FAIL: {failure}", file=sys.stderr)
    else:
        print("PASS: strict D0 final closure validation completed.")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
