#!/usr/bin/env python3
"""Validate the explicit, machine-testable parts of the Batch-87 D0 corpus.

This validator proves document structure, declared invariants, reference
traceability, and closure-state discipline. It does not replace Nolan–Byte
semantic architecture review and does not claim to validate model behaviour.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


DEFAULT_MANIFEST = Path("docs/architecture/B87-D0-CONFORMANCE-MANIFEST.json")
STATUS_PATTERN = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$", re.MULTILINE)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    document: str | None = None
    line: int | None = None


@dataclass
class ValidationReport:
    phase: str
    corpus_hashes: dict[str, str] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    semantic_review_required: bool = True
    behavioural_validation_completed: bool = False

    @property
    def errors(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == "error"]

    @property
    def blockers(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == "blocker"]

    @property
    def warnings(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == "warning"]

    @property
    def structurally_valid(self) -> bool:
        return not self.errors

    @property
    def closure_ready(self) -> bool:
        return not self.errors and not self.blockers

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        *,
        document: str | None = None,
        line: int | None = None,
    ) -> None:
        self.findings.append(
            Finding(
                severity=severity,
                code=code,
                message=message,
                document=document,
                line=line,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "corpus_hashes": self.corpus_hashes,
            "findings": [asdict(item) for item in self.findings],
            "summary": {
                "errors": len(self.errors),
                "blockers": len(self.blockers),
                "warnings": len(self.warnings),
                "structurally_valid": self.structurally_valid,
                "closure_ready": self.closure_ready,
                "semantic_review_required": self.semantic_review_required,
                "behavioural_validation_completed": self.behavioural_validation_completed,
            },
        }


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError(f"Unable to locate repository root from {start}")


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"Conformance manifest not found: {path}") from exc

    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid conformance manifest JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    required_keys = {"schema_version", "phase", "documents", "invariants", "issue_traceability"}
    missing = sorted(required_keys.difference(manifest))
    if missing:
        raise RuntimeError(f"Conformance manifest is missing keys: {', '.join(missing)}")

    return manifest


def read_corpus(repo_root: Path, documents: dict[str, str]) -> dict[str, str]:
    corpus: dict[str, str] = {}
    for key, relative_path in documents.items():
        path = repo_root / relative_path
        try:
            corpus[key] = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise RuntimeError(f"Required D0 document is missing: {relative_path}") from exc
    return corpus


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_headings(text: str) -> list[tuple[int, int, str]]:
    headings: list[tuple[int, int, str]] = []
    inside_fence = False
    fence_marker: str | None = None

    for line_number, line in enumerate(text.splitlines(), start=1):
        fence_match = FENCE_PATTERN.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if not inside_fence:
                inside_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                inside_fence = False
                fence_marker = None
            continue

        if inside_fence:
            continue

        heading_match = HEADING_PATTERN.match(line)
        if heading_match:
            headings.append(
                (line_number, len(heading_match.group(1)), heading_match.group(2))
            )

    return headings


def document_status(text: str) -> str | None:
    match = STATUS_PATTERN.search(text)
    return match.group(1).strip() if match else None


def validate_document_structure(
    report: ValidationReport,
    document_key: str,
    relative_path: str,
    text: str,
) -> None:
    headings = parse_headings(text)
    h1_headings = [heading for heading in headings if heading[1] == 1]

    if not headings:
        report.add(
            "error",
            "DOC-NO-HEADINGS",
            "Document contains no Markdown headings.",
            document=document_key,
        )
        return

    if headings[0][1] != 1 or headings[0][0] != 1:
        report.add(
            "error",
            "DOC-FIRST-H1",
            "The first line must be the sole top-level title.",
            document=document_key,
            line=headings[0][0],
        )

    if len(h1_headings) != 1:
        report.add(
            "error",
            "DOC-H1-COUNT",
            f"Expected exactly one H1; found {len(h1_headings)}.",
            document=document_key,
        )

    previous_level = 0
    for line_number, level, title in headings:
        if previous_level and level > previous_level + 1:
            report.add(
                "error",
                "DOC-HEADING-JUMP",
                f"Heading level jumps from H{previous_level} to H{level}: {title}",
                document=document_key,
                line=line_number,
            )
        previous_level = level

    if not text.endswith("\n"):
        report.add(
            "warning",
            "DOC-FINAL-NEWLINE",
            f"Document has no final newline: {relative_path}",
            document=document_key,
        )

    status = document_status(text)
    if status is None:
        report.add(
            "error",
            "DOC-STATUS-MISSING",
            "Document has no recognised '**Status:**' metadata field.",
            document=document_key,
        )


def _matches(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL | re.MULTILINE) is not None


def validate_invariant(
    report: ValidationReport,
    invariant: dict[str, Any],
    corpus: dict[str, str],
) -> None:
    invariant_id = invariant["id"]
    required_documents = invariant.get("required_in", [])
    closure_blocking = bool(invariant.get("closure_blocking", False))
    failure_severity = "blocker" if closure_blocking else "error"

    for document_key in required_documents:
        text = corpus.get(document_key)
        if text is None:
            report.add(
                "error",
                "INV-DOCUMENT-MISSING",
                f"{invariant_id} references unknown document {document_key}.",
                document=document_key,
            )
            continue

        literals = invariant.get("required_literals", [])
        for literal in literals:
            if literal.casefold() not in text.casefold():
                report.add(
                    failure_severity,
                    invariant_id,
                    f"Missing required literal: {literal}",
                    document=document_key,
                )

        patterns = invariant.get("required_patterns", [])
        if patterns and not any(_matches(text, pattern) for pattern in patterns):
            report.add(
                failure_severity,
                invariant_id,
                "None of the required patterns matched this document.",
                document=document_key,
            )

        for pattern in invariant.get("forbidden_patterns", []):
            if _matches(text, pattern):
                report.add(
                    "error",
                    invariant_id,
                    f"Forbidden pattern matched: {pattern}",
                    document=document_key,
                )

    joined_corpus = "\n\n".join(corpus.values())
    for pattern in invariant.get("forbidden_global_patterns", []):
        if _matches(joined_corpus, pattern):
            report.add(
                "error",
                invariant_id,
                f"Forbidden cross-corpus pattern matched: {pattern}",
            )


def validate_issue_traceability(
    report: ValidationReport,
    manifest: dict[str, Any],
    corpus: dict[str, str],
) -> None:
    for issue_id, issue in manifest.get("issue_traceability", {}).items():
        register_key = issue["register_document"]
        register_text = corpus.get(register_key, "")
        if issue_id.casefold() not in register_text.casefold():
            report.add(
                "error",
                "ISSUE-REGISTER-MISSING",
                f"Issue register does not contain {issue_id}.",
                document=register_key,
            )

        for evidence in issue.get("required_resolution_evidence", []):
            document_key = evidence["document"]
            pattern = evidence["pattern"]
            text = corpus.get(document_key)
            if text is None or not _matches(text, pattern):
                report.add(
                    "blocker",
                    issue_id,
                    f"Required resolution evidence is missing: {pattern}",
                    document=document_key,
                )


def validate_closure_state(
    report: ValidationReport,
    repo_root: Path,
    manifest: dict[str, Any],
    corpus: dict[str, str],
    *,
    require_closed: bool,
) -> None:
    rules = manifest.get("closure_rules", {})
    issue_register = corpus.get("issue_register", "")

    for document_key in rules.get("required_approved_status_documents", []):
        status = document_status(corpus.get(document_key, ""))
        if status is None:
            continue

        accepted = {
            "architecture baseline",
            "approved architecture baseline",
            "approved and closed",
        }
        if status.casefold() not in accepted:
            report.add(
                "blocker",
                "CLOSURE-STATUS",
                f"Document status is not closure-ready: {status}",
                document=document_key,
            )

    closure_path = repo_root / rules.get(
        "closure_decision_path", "docs/architecture/B87-D0-CLOSURE-DECISION.md"
    )
    if not closure_path.exists():
        report.add(
            "blocker",
            "CLOSURE-DECISION-MISSING",
            f"Closure decision does not exist: {closure_path.relative_to(repo_root)}",
        )

    closed_pattern = rules.get("closed_issue_status_pattern", "Closed")
    issue_is_closed = _matches(issue_register, rf"\*\*Status:\*\*\s*{re.escape(closed_pattern)}")
    if not issue_is_closed:
        report.add(
            "blocker",
            "CLOSURE-ISSUE-OPEN",
            "D0-ISSUE-001 is not yet marked closed in the issue register.",
            document="issue_register",
        )

    claim_limit = rules.get("closure_claim_limit")
    if claim_limit:
        report.add(
            "warning",
            "CLOSURE-CLAIM-LIMIT",
            claim_limit,
        )

    if require_closed and report.blockers:
        return


def validate(
    repo_root: Path,
    manifest_path: Path,
    *,
    require_closed: bool = False,
) -> ValidationReport:
    manifest = load_manifest(manifest_path)
    report = ValidationReport(phase=manifest["phase"])

    try:
        corpus = read_corpus(repo_root, manifest["documents"])
    except RuntimeError as exc:
        report.add("error", "CORPUS-LOAD", str(exc))
        return report

    report.corpus_hashes = {
        key: sha256_text(text) for key, text in sorted(corpus.items())
    }

    for key, relative_path in manifest["documents"].items():
        validate_document_structure(report, key, relative_path, corpus[key])

    for invariant in manifest.get("invariants", []):
        validate_invariant(report, invariant, corpus)

    validate_issue_traceability(report, manifest, corpus)
    validate_closure_state(
        report,
        repo_root,
        manifest,
        corpus,
        require_closed=require_closed,
    )

    return report


def render_report(report: ValidationReport) -> str:
    lines = [
        "B87-D0 ARCHITECTURE CONFORMANCE REPORT",
        "=" * 47,
        f"Phase: {report.phase}",
        f"Structural/invariant errors: {len(report.errors)}",
        f"Closure blockers: {len(report.blockers)}",
        f"Warnings: {len(report.warnings)}",
        f"Structurally valid: {str(report.structurally_valid).lower()}",
        f"Closure ready: {str(report.closure_ready).lower()}",
        "Semantic Nolan–Byte review required: true",
        "Model behavioural validation completed: false",
        "",
    ]

    if report.findings:
        lines.append("FINDINGS")
        lines.append("--------")
        for item in report.findings:
            location = ""
            if item.document:
                location = f" [{item.document}"
                if item.line:
                    location += f":{item.line}"
                location += "]"
            lines.append(
                f"{item.severity.upper():7} {item.code}{location}: {item.message}"
            )
    else:
        lines.append("No machine-testable conformance findings.")

    lines.extend(
        [
            "",
            "CORPUS HASHES",
            "-------------",
        ]
    )
    for key, digest in sorted(report.corpus_hashes.items()):
        lines.append(f"{key:14} {digest}")

    return "\n".join(lines)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root. Defaults to automatic discovery.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"Manifest path relative to the repository root (default: {DEFAULT_MANIFEST}).",
    )
    parser.add_argument(
        "--require-closed",
        action="store_true",
        help="Require closure decision, approved statuses, and closed issue state.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional path for a machine-readable JSON report.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root(Path.cwd())
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = repo_root / manifest_path

    try:
        report = validate(
            repo_root,
            manifest_path,
            require_closed=args.require_closed,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(render_report(report))

    if args.json_output:
        output_path = args.json_output
        if not output_path.is_absolute():
            output_path = repo_root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if report.errors:
        return 1
    if args.require_closed and report.blockers:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
