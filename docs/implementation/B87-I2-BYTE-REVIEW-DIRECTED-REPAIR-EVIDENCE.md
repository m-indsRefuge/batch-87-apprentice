# B87-I2 Byte Review-Directed Repair Evidence

## Status and authority

- Phase: `B87-I2 — Governed Task Runtime`
- Repair authority: Nolan's direct request for Byte coding after accepting the Byte review findings
- Repair base commit: `01f00e419f30db2b5025f9c2e9920506a598c8aa`
- Branch target: `codex/b87-i2-governed-task-runtime`
- Status: repair implementation validated in an isolated committed-tree reproduction; pending application and Nolan–Byte review in the local repository
- Active implementation release after repair: `NONE`
- B87-I3 remains unauthorised

This record preserves the review findings, exact repair boundary, and validation evidence. It does not constitute acceptance, release, push, pull-request, or merge authority.

## Confirmed review findings repaired

### 1. Explicit human approval model

The runtime now implements a typed and persisted `HumanApproval` contract with:

- explicit approval identity;
- requested operation;
- subject principal and permission scope;
- project, scope, and optional task binding;
- approving human entity;
- approval and expiry timestamps;
- explicit conditions;
- single-use state;
- supporting evidence and provenance;
- transactional consumption fields.

Human approvals are registered independently from task evaluation. A Nolan or Nolan–Byte allow authority requires a valid explicit approval. A single-use approval is consumed in the same governed transaction as the permitting decision and cannot be reused.

### 2. Deterministic operation classification

Operation classification is no longer accepted from the task caller as policy truth. Immutable `OperationDefinition` records are registered through governed infrastructure. Evaluation resolves the authoritative definition by operation name and compares the task's claimed class and autonomy flag against it.

The runtime now fails closed when:

- no operation definition exists;
- the caller misclassifies an operation;
- the operation or authoritative action class is prohibited by the task;
- an autonomous operation is prohibited;
- authority does not cover the authoritative action class.

Identity-bearing tasks with an unregistered operation persist a reconstructable governance stop rather than failing through a foreign-key accident.

### 3. Complete decision relationships

The transaction-finalisation boundary now requires relationship counts to match the canonical decision assessments for:

- authority inputs;
- human approval inputs;
- evidence inputs;
- governing rules.

Missing relationship rows prevent transaction finalisation and roll the full write back. Reconstruction and read-only integrity inspection independently compare ordered relationship values against the canonical decision arrays. Deliberate post-finalisation corruption is therefore visible even when database triggers are removed in a test-only corruption fixture.

## Lifecycle repair

Migration `0004` now preserves compatible governed lifecycle paths before merge:

- append-only session transitions support open, pause, resume, close, and abort;
- append-only authority revocation is represented separately from the immutable authority record;
- task transitions support pending to active/stopped/failed and active to completed/stopped/failed;
- the public runtime provides governed active-task completion or failure;
- integrity inspection validates contiguous transition history against current state.

No later-phase memory, model, retrieval, context, training, identity, tool, or laboratory behaviour was introduced.

## Integrity and reconstruction repair

Reconstruction now verifies and exposes:

- the immutable operation definition or an explicit missing-definition stop;
- ordered authority assessments;
- applicable authority revocation evidence at decision time;
- ordered human approval assessments;
- approval selection and consumption state;
- ordered evidence assessments;
- governing-rule relationships;
- task and session transition histories;
- decision, stop, and transaction hashes.

Integrity inspection now covers canonical operation definitions, human approvals, authority revocations, approval-evidence links, approval consumption, session transitions, task transitions, and exact decision relationships.

## Task contract and schema

Task Contract 1.0.0 now includes the required immutable field:

```text
claimed_human_approval_ids
```

Schema registry SHA-256:

```text
18095a99e6e3e70da3d4305edf4c0623ea2e49af19895dd4d621097ecd573a7f
```

## Migration inventory

Migrations `0001`–`0003` remain byte-identical:

| Version | SHA-256 |
| --- | --- |
| `0001` | `4b17bba385254cc532785e2dfed08e27ffbc5b1c4537c22447982cb24a053f77` |
| `0002` | `d266b07159f002f5a068d7e8ca0314c5a5e2e9a829639ac1f961941e3c629134` |
| `0003` | `982872f104192f243d8ab676ab448daa004d40be9de560efd065fbabb2c19a28` |

Repaired, still-unmerged migration `0004`:

```text
54f2d1e10d7ffdcee4e64e6746b883b2f1d366da3d78ac656e631f71a1527a70
```

No migration `0005` was created.

## Changed-file boundary

The Byte repair changes exactly these 14 files:

1. `docs/implementation/B87-I2-BYTE-REVIEW-DIRECTED-REPAIR-EVIDENCE.md`
2. `schemas/protocols/task-contract/1.0.0.schema.json`
3. `schemas/registry.json`
4. `src/batch87_apprentice/governance/__init__.py`
5. `src/batch87_apprentice/governance/contracts.py`
6. `src/batch87_apprentice/governance/engine.py`
7. `src/batch87_apprentice/persistence/integrity.py`
8. `src/batch87_apprentice/persistence/sql/0004_governed_task_runtime.sql`
9. `src/batch87_apprentice/persistence/task_runtime_store.py`
10. `src/batch87_apprentice/protocols/task_contracts.py`
11. `src/batch87_apprentice/runtime/service.py`
12. `tests/integration/test_i2_governed_task_runtime.py`
13. `tests/support/i2_fixtures.py`
14. `tests/unit/test_i2_task_contracts.py`

## Adversarial proof matrix

New or strengthened deterministic tests prove:

- a single-use human approval is consumed atomically;
- the consumed approval cannot authorise a second task;
- authoritative operation classification overrides caller mislabelling;
- an Execute operation labelled Observe still stops;
- an unregistered operation persists a reconstructable stop;
- omitted decision-evidence relationships prevent finalisation and roll back;
- post-finalisation relationship deletion is detected by inspection and reconstruction;
- authority revocation fails closed;
- session lifecycle transitions remain governed and integrity-clean;
- active tasks can complete through a governed transition;
- unsupported human-approval conditions fail closed.

## Byte validation

Validation was run against an isolated reproduction of the exact committed tree at the review base.

### Complete suite

```text
149 passed
```

### Strict D0 final-closure wrapper

```text
pytest: 149 passed
Structural/invariant errors: 0
Closure blockers: 0
Strict result: PASS
Git diff check: PASS
```

The expected D0 closure-claim warning remains and is not a blocker.

### Scope confirmation

The repair adds no:

- memory-domain behaviour;
- retrieval or ranking;
- context assembly;
- model loading or invocation;
- training or fine-tuning;
- identity progression;
- autonomous tool access;
- external service;
- experimental laboratory;
- B87-I3 implementation.

## Review state

After application to Nolan's local branch, the complete suite and strict D0 wrapper must be rerun in that repository. The repair must remain uncommitted until Nolan reviews the resulting local validation output and separately authorises the repair commit.
