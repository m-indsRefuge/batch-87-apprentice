# B87-I2 Governed Task Runtime Completion Evidence

## Status and identity

- Phase: `B87-I2 — Governed Task Runtime`
- Status: implementation complete and ready for Byte–Nolan review; not accepted
- Branch: `codex/b87-i2-governed-task-runtime`
- Starting baseline and direct parent: `98f5ba472a63fe7b460b59cb8509e8cf36a72d8d`
- Remote `origin/main` at the repository gate: `98f5ba472a63fe7b460b59cb8509e8cf36a72d8d`
- Final commit: the single local commit containing this evidence record, with message
  `B87-I2: implement governed task runtime`. Its Git-produced SHA is recorded in
  the completion report because a commit cannot contain its own SHA without
  changing that SHA.
- Active implementation release after completion: `NONE`
- Development execution principal: `codex_development_harness`
- Apprentice permissions remain limited to `Observe` and `Analyse`.

This record is implementation evidence. It does not constitute architecture,
phase, promotion, release, or acceptance authority.

## Changed-file inventory

| File | Classification | Change |
| --- | --- | --- |
| `schemas/protocols/task-contract/1.0.0.schema.json` | schema | Versioned Task Contract 1.0.0 JSON Schema |
| `schemas/registry.json` | schema | Exact active schema identifier, path, version, and content hash |
| `src/batch87_apprentice/protocols/__init__.py` | protocol | Public I2 protocol exports |
| `src/batch87_apprentice/protocols/task_contracts.py` | protocol | Typed session, task, operation, and policy-violation contracts |
| `src/batch87_apprentice/governance/__init__.py` | governance | Public I2 governance exports |
| `src/batch87_apprentice/governance/contracts.py` | governance | Permission, principal, authority, rule, decision, stop, and result contracts |
| `src/batch87_apprentice/governance/engine.py` | governance | Pure deterministic authority and permission evaluation |
| `src/batch87_apprentice/persistence/sql/0004_governed_task_runtime.sql` | persistence | Additive I2 governed-runtime schema and invariants |
| `src/batch87_apprentice/persistence/task_runtime_store.py` | persistence | Atomic authority registration, task evaluation, and reconstruction |
| `src/batch87_apprentice/runtime/__init__.py` | runtime | Public governed-runtime exports |
| `src/batch87_apprentice/runtime/service.py` | runtime | Governed runtime composition and principal boundary |
| `src/batch87_apprentice/persistence/integrity.py` | integrity | I2 hash, relationship, lifecycle, and transaction inspection |
| `tests/support/i2_fixtures.py` | fixture | Deterministic file-backed I2 fixtures |
| `tests/unit/test_i2_task_contracts.py` | unit test | Contract, schema, permission, principal, and precedence tests |
| `tests/integration/test_i2_governed_task_runtime.py` | integration test | Governed runtime, failure, rollback, reopen, and integrity tests |
| `tests/integration/test_i1_integrity.py` | integration test | Additive migration-count compatibility |
| `tests/integration/test_i1_persistence_kernel.py` | integration test | Additive schema and migration compatibility |
| `docs/implementation/B87-I2-GOVERNED-TASK-RUNTIME-COMPLETION-EVIDENCE.md` | evidence | This completion record |

No file outside this 18-file set is part of the B87-I2 commit.

## Architecture-to-code crosswalk

| Accepted I2 requirement | Implementation | Deterministic evidence |
| --- | --- | --- |
| Versioned task contracts | `schemas/protocols/task-contract/1.0.0.schema.json`, `schemas/registry.json`, `protocols/task_contracts.py` | `test_supported_task_contract_is_canonical_and_stable`, `test_task_schema_registry_has_one_exact_active_version`, unsupported and malformed contract tests |
| Session and task identities | `SessionContract`, `TaskContract`, `sessions`, `session_participants`, `tasks` | `test_session_identity_and_participants_are_explicit`, immutable-task and reopen tests |
| Project and scope validation | `TaskContract`, `TaskRuntimeStore.evaluate_task`, `_scope_contains` | invalid project/scope and authority-scope tests |
| Permission profile | `active_b87_s1_permission_profile`, `permission_profiles` | exact-profile and unavailable-permission tests |
| Principals | typed principal fields in protocol, authority, decision, transaction, and service contracts | principal-separation and attribution tests |
| Authority records | `AuthorityRecord`, `authority_records`, `authority_record_evidence`, `register_authority` | registration separation, invalid authority, evidence, and registrar tests |
| Precedence | `AUTHORITY_CLASS_PRECEDENCE`, `GovernanceEngine.evaluate` | higher/lower and equal-precedence conflict tests |
| Operation classification | `RequestedOperation` | explicit classification and unavailable-permission tests |
| Decisions | `GovernanceDecision`, `governance_decisions` and input relationship tables | allow, deny, review, stop, determinism, and reconstruction tests |
| Stops | `TaskStopEvent`, `task_stop_events` | permission, missing-authority, policy, integrity, and duplicate-stop tests |
| Failures | `DecisionReason`, `PolicyViolation`, structured transaction failures | fail-closed variant, policy, persistence-failure, and reconstruction tests |
| Transactions | `governed_runtime_transactions`, accepted `PersistenceKernel.write` boundary | atomic commit, injected rollback, duplicate, and partial-transaction tests |
| Evidence | accepted I1 evidence substrate plus I2 decision/evidence relationships | missing, invalid, controlled, model-shaped, policy, and reconstruction tests |
| Reconstruction | `TaskRuntimeStore.reconstruct`, `GovernedTaskRuntime.reconstruct` | exact reconstruction, reopen, corruption, and immutability tests |
| Integrity inspection | additive checks in `persistence/integrity.py` | complete allow/stop and injected inconsistency tests |

## Mandatory final audit

1. Task evaluation cannot create or self-register authority. The public
   `evaluate` method has no authority-record input; it resolves only identifiers
   already stored by the separate `register_authority` operation.
2. Free-form text, model-shaped content, historical instructions, repository
   text, and claimed approval cannot create authority. They remain evidence or
   context, and the engine consumes only typed, pre-registered authority records.
3. No principal can grant Apprentice `Execute`. Typed contracts, Python
   registration validation, database checks, the immutable permission profile,
   and the governance engine all fail closed on this expansion.
4. `codex_development_harness` activity cannot be attributed to the Apprentice.
   Requesting principal, authority registrar, runtime execution principal, and
   runtime instance are separate persisted and reconstructed fields.
5. Expired, future, malformed, unsupported, project-mismatched, task-mismatched,
   principal-mismatched, evidence-incomplete, or out-of-scope authority cannot
   permit a task.
6. Lower authority cannot override higher authority. The minimum explicit
   precedence controls; an equal-precedence conflict requires human approval and
   persists a stop.
7. Model output cannot change a deterministic governance decision. There is no
   model invocation path in the engine, and model-shaped evidence is tested
   against a structured denial.
8. Every non-allow governance outcome constructs and atomically persists a
   required task-stop event.
9. Database constraints and finalisation triggers prevent a completed decision
   transaction from omitting required evidence relationships or a required stop.
10. Injected decision, evidence, and stop persistence failures roll back the
    whole transaction, leaving no task or apparently complete transaction.
11. File-backed reopen reconstructs the same canonical decision and content hash
    as the original evaluation.
12. Migration `0004` does not change migrations `0001`–`0003`; baseline Git blob
    hashes match byte-for-byte, and applied migration content is hash-verified.
13. I2 adds no ordinary memory, retrieval, context assembly, model, identity,
    training, tool, or laboratory behaviour.
14. Integrity inspection detects hash corruption and incomplete I2 transactions.
15. All I1 tests and restrictions remain intact in the complete 141-test suite.

No additional production defect was found in the final audit.

## Permission and principal proof

- `active_b87_s1_permission_profile()` grants the Apprentice exactly
  `("observe", "analyse")`.
- `propose`, `execute`, autonomous action, and tools are explicitly prohibited.
- Propose has no independent authority-bearing permission in B87-S1.
- An `AuthorityRecord` for the Apprentice cannot contain Propose or Execute
  permissions; both Python and SQLite enforce the restriction.
- `GovernedTaskRuntime` accepts only `operator` or
  `codex_development_harness` as its infrastructure principal.
- Runtime infrastructure principal, requesting principal, authority
  registration principal, and issuing entity remain distinct.
- Every decision persists `apprentice_execute_implication = 0`.

The focused and complete suites exercised Observe, Analyse, Propose, Execute,
autonomous action, Operator execution, Codex development execution, and
experimental-harness denial.

## Authority proof

- Authority registration is a separate public operation and must precede task
  evaluation.
- Evaluation accepts no authority object and cannot create the authority it
  claims.
- Missing identifiers and unsupported classes fail closed with structured
  reasons and task stops.
- Effective-from, effective-until, project, scope, task, principal, issuer, and
  evidence boundaries are checked from database-derived context.
- Historical authority remains context and is inactive.
- Lower-precedence authority cannot override a higher-precedence record.
- Equal-precedence conflicts require explicit human review.
- Authority evidence must be valid and cannot be model output or Controlled
  Governance Resilience prompt/output evidence.
- Document text that claims approval and model-shaped content cannot authorise
  or alter the deterministic outcome.

## Persistence proof

### Migration inventory

| Version | File | SHA-256 |
| --- | --- | --- |
| 0001 | `0001_system_entities_records.sql` | `4b17bba385254cc532785e2dfed08e27ffbc5b1c4537c22447982cb24a053f77` |
| 0002 | `0002_evidence.sql` | `d266b07159f002f5a068d7e8ca0314c5a5e2e9a829639ac1f961941e3c629134` |
| 0003 | `0003_controlled_resilience.sql` | `982872f104192f243d8ab676ab448daa004d40be9de560efd065fbabb2c19a28` |
| 0004 | `0004_governed_task_runtime.sql` | `46f93e8b66e23157354fa6e1b7123934cf426301fdf74914935ae1bc14b9ebdc` |

Git blob comparison against
`98f5ba472a63fe7b460b59cb8509e8cf36a72d8d` proved that migrations 0001,
0002, and 0003 are byte-unchanged. Migration 0004 is ordered, additive, and
participates in the accepted immutable migration ledger. No migration 0005
exists.

Migration 0004 adds only:

- `permission_profiles`
- `governance_rules`
- `sessions`
- `session_participants`
- `authority_records`
- `authority_record_evidence`
- `governed_runtime_transactions`
- `tasks`
- `task_state_transitions`
- `governance_decisions`
- `governance_decision_authority_inputs`
- `governance_decision_evidence`
- `governance_decision_rules`
- `task_stop_events`

It adds no memory, retrieval, context, model, training, identity, tool,
experiment, or laboratory table.

Task evidence, task contract, decision, authority inputs, evidence inputs,
governing rules, required stop, state transitions, and transaction
finalisation execute inside the accepted I1 `BEGIN IMMEDIATE` write boundary.
Any exception rolls the unit back.

Dedicated injected failures at evidence, decision, and task-stop insertion
produced `3 passed`; post-failure counts were unchanged and reconstruction
reported the task absent. Fresh application, repeated startup, failed-migration
rollback, and applied-migration tamper detection produced `5 passed`.

Fresh file-backed runtime proof produced `15 passed`. It covered all four
migrations, repeated startup, Apprentice Observe and Analyse, Execute denial,
missing and invalid authority, persisted stops, fresh-runtime reopen, exact
task/session/authority/principal/decision/evidence/transaction/stop
reconstruction, and a zero-error integrity report.

## Validation record

Environment:

- Python executable:
  `C:\Users\nolan\AppData\Local\Programs\Python\Python312\python.exe`
- Python: `3.12.10`
- pytest: `9.1.1`
- No environment, dependency, or declaration was changed.

### Production import

Command:

```powershell
python -X utf8 -c "import importlib,pkgutil,sys; sys.path.insert(0,'src'); import batch87_apprentice; names=[m.name for m in pkgutil.walk_packages(batch87_apprentice.__path__, batch87_apprentice.__name__+'.')]; [importlib.import_module(name) for name in names]; print(f'IMPORTED_MODULES={len(names)+1}')"
```

Result: `IMPORTED_MODULES=31`; exit code `0`; measured duration `0.105s`.

### Focused I2 and directly affected I1 validation

Command:

```powershell
python -X utf8 -m pytest -q tests/unit/test_i2_task_contracts.py tests/integration/test_i2_governed_task_runtime.py tests/integration/test_i1_integrity.py tests/integration/test_i1_persistence_kernel.py
```

The first final-gate attempt exposed one narrow test assertion defect:
`test_i2_migration_content_tamper_is_detected` expected `hash mismatch`, while
the accepted migration mechanism raised
`migration hash changed at version 0004`. Result: `1 failed, 92 passed in
4.72s`; exit code `1`; measured duration `4.925s`.

The assertion was repaired to match the exact accepted error. Re-run result:
`93 passed in 4.66s`; exit code `0`; measured duration `4.863s`.

### Complete regression suite

Command:

```powershell
python -X utf8 -m pytest -q --basetemp "C:\Users\nolan\AppData\Local\Temp\b87-i2-final-ce26f194f55a409bada3f7e010b2b399"
```

Result: `141 passed in 4.71s`; exit code `0`; measured duration `4.902s`.

### Strict D0 final closure

Command:

```powershell
python -X utf8 scripts\run_d0_final_closure_validation.py
```

Result:

- pytest: `141 passed in 4.78s`
- structural/invariant errors: `0`
- closure blockers: `0`
- closure-ready: `true`
- strict result: `PASS`
- exit code: `0`
- measured duration: `5.314s`

The expected D0 closure-claim warning remains: architecture closure does not
claim model-behaviour validation.

### File-backed runtime proof

Command:

```powershell
python -X utf8 -m pytest -q --basetemp "C:\Users\nolan\AppData\Local\Temp\b87-i2-runtime-proof-81fe9d9bdefb4a04836da3e60c3acc22" tests/integration/test_i2_governed_task_runtime.py -k "apprentice_observe_and_analyse_commit_atomically or unavailable_apprentice_permissions_persist_governance_stop or missing_authority_and_document_text_cannot_self_authorise or invalid_authority_variants_fail_closed or repeated_startup_and_file_backed_reopen_preserve_exact_reconstruction or integrity_inspector_accepts_complete_allow_and_stop_transactions"
```

Result: `15 passed, 31 deselected in 1.17s`; exit code `0`; measured duration
`1.374s`.

### Rollback proof

Command:

```powershell
python -X utf8 -m pytest -q --basetemp "C:\Users\nolan\AppData\Local\Temp\b87-i2-rollback-proof-4ea84945a69a4f669b54bd6864bd8175" tests/integration/test_i2_governed_task_runtime.py -k "required_persistence_failure_rolls_back_entire_transaction"
```

Result: `3 passed, 43 deselected in 0.28s`; exit code `0`; measured duration
`0.475s`.

### Migration integrity proof

Command:

```powershell
python -X utf8 -m pytest -q --basetemp "C:\Users\nolan\AppData\Local\Temp\b87-i2-migration-proof-25fcb7ebc8cf409599458803af8faba2" tests/unit/test_i1_migrations.py::test_migrations_apply_once_and_verified_pragmas_hold tests/unit/test_i1_migrations.py::test_migration_hash_tampering_fails_closed tests/unit/test_i1_migrations.py::test_failed_migration_rolls_back_schema_and_ledger tests/integration/test_i2_governed_task_runtime.py::test_repeated_startup_and_file_backed_reopen_preserve_exact_reconstruction tests/integration/test_i2_governed_task_runtime.py::test_i2_migration_content_tamper_is_detected
```

Result: `5 passed in 0.20s`; exit code `0`; measured duration `0.404s`.

### Diff and scope

`git diff --check` returned exit code `0` before this evidence record was
created. The pre-evidence working tree was exactly the authorised 17-file I2
set. The final staged diff and final clean status are verified as commit gates.

Earlier interrupted-run diagnostics are preserved as non-final evidence:

- An early integration run exposed an authority-resolution ordering defect; it
  was corrected before this final audit and all final gates are green.
- An initial import probe without the source directory on the import path
  failed; the final source-aware complete-package import check passed.
- An optional Ruff invocation could not run because Ruff is not installed. No
  dependency was installed or changed, and Ruff is not a mandated completion
  gate for this repository.

## Repair performed during narrow completion

Only one repair was made during the narrow continuation. The I2 migration
tamper test now matches the accepted migration runner's exact deterministic
error text. No production code, schema, migration, architecture, or test
strength was changed by that repair.

## Limitations and exclusions

B87-I2 does not implement:

- memory-domain behaviour;
- retrieval or ranking;
- context assembly;
- model integration or invocation;
- model selection;
- training or fine-tuning;
- identity progression;
- autonomous action;
- external tools;
- experimental laboratories;
- B87-I3.

Malformed, identity-less input is rejected before persistence where possible.
Once a valid typed task enters evaluation, governed non-allow outcomes are
persisted with their decision, reasons, transaction, evidence relationships,
state transitions, and stop event. A database persistence failure rolls back
the attempted unit atomically and is reported externally; it cannot truthfully
be represented as a successfully persisted stop inside the same failed
transaction.

No push, pull request, merge, release, acceptance declaration, or later-phase
activation is part of this completion.
