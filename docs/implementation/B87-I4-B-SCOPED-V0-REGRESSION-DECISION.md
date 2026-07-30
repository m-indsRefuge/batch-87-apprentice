# B87-I4-B Scoped V0 Regression Decision

## 1. Decision status and release boundary

**Status:** ACCEPTED

**Decision version:** 1.0

**Decision date:** 2026-07-30

**Acceptance date:** 2026-07-30

**Acceptance decision:**

```text
docs/implementation/B87-I4-B-SCOPED-V0-REGRESSION-ACCEPTANCE-DECISION.md
```

**Accepted documentation baseline:**
`7debc707ff50d00308bb6ab11ffc09f9ffb74397`

**Future I4-B candidate source commit:** not yet available; it must be frozen and
recorded before external regression begins

**External harness versioning protocol:**
`B87-I4B-HARNESS-FREEZE-MANIFEST-v1.0`

**Active implementation release:** `NONE`

**B87-I4-B implementation:** `NOT AUTHORIZED`

**Accepted B87-V0 state:** `CLOSED`

This is the accepted documentation-only regression-planning decision. It is
operative only as the governing B87-I4-B scoped persistence-regression planning
decision. It does not authorize a migration, schema, provider, invocation,
runtime, test, external validation, model, API, tool, experimental capability,
or other implementation work.

### 1.1 External-harness identity finding

Read-only semantic review of the external validation workspace established:

- the workspace is a Git working tree;
- its branch was `master`;
- no valid commit could be resolved from `HEAD`;
- no remote was configured;
- the inspected files were untracked; and
- no accepted evidence record supplied a harness commit or working-tree
  manifest hash.

No historical harness commit may be invented, inferred, backdated, or claimed
retroactively. The accepted historical V0 remains accepted through its closure
decision and preserved immutable run evidence. This harness-identity finding
does not reopen or invalidate V0.

### 1.2 Harness-versioning decision

The external harness versioning mechanism for I4-B scoped regression is:

```text
B87-I4B-HARNESS-FREEZE-MANIFEST-v1.0
```

Acceptance of this regression decision confirms that immutable versioning
protocol. It does not require the hash of a future executable harness before
the I4-B implementation and scenario adaptations exist. The exact canonical
freeze-manifest hash becomes a mandatory external-execution precondition after
the candidate and executable scenario surface are complete.

Upon Nolan–Byte acceptance, this decision becomes operative immediately as the
governing B87-I4-B scoped persistence-regression planning decision. Its
acceptance satisfies only the regression-planning entry gate required by
section 17 of the accepted I4-B contract.

Operation as a planning decision does not authorize implementation or external
execution.

B87-I4-B implementation may begin only after Nolan separately issues exactly:

```text
AUTHORIZE B87-I4-B
```

That release must identify accepted regression-decision version 1.0 and its
acceptance record:

```text
docs/implementation/B87-I4-B-SCOPED-V0-REGRESSION-ACCEPTANCE-DECISION.md
```

External regression execution may begin only after:

1. the separately authorized I4-B implementation is complete and internally
   passing;
2. the exact candidate commit is frozen;
3. the executable external scenario adaptations are complete;
4. a valid `B87-I4B-HARNESS-FREEZE-MANIFEST-v1.0` is generated and recorded; and
5. all other section 10 preconditions are satisfied.

Decision acceptance therefore precedes implementation authorization, while
external execution follows candidate freeze.

The accepted historical V0 baseline remains closed and unchanged. This decision
does not reopen, replace, invalidate, or rerun all of V0 by default.

## 2. Purpose and decision effect

The accepted B87-I4-B contract anticipates an additive migration and new
invocation persistence, transaction, identity, reconstruction, and integrity
surfaces. Those changes trigger a scoped persistence-regression decision under
the accepted V0 closure rule.

This decision applies the least-regression-sufficient principle: repeat only the
accepted V0 scenarios needed to establish that a frozen I4-B candidate preserves
the accepted persistence foundation while correctly adding the I4-B write path.
It also defines I4-B-specific variations, evidence, pass conditions, and stop
conditions for those scenarios.

Acceptance of this document satisfies only the regression-planning entry gate.
It does not:

- transfer V0 acceptance to a future I4-B baseline;
- authorize B87-I4-B implementation or external execution;
- authorize Validation V1;
- alter an accepted I1, I2, I3, or I4-A boundary;
- select or connect a provider or model; or
- make any future regression result self-accepting.

## 3. Governing sources and preserved boundaries

This decision reconciles, without rewriting, the following accepted records:

- the [B87-I4-B provider-neutral model and invocation bridge contract](B87-I4-B-PROVIDER-NEUTRAL-MODEL-AND-INVOCATION-BRIDGE-CONTRACT.md);
- the [programme-state and I4-B contract acceptance decision](B87-PROGRAMME-STATE-AND-I4-B-CONTRACT-ACCEPTANCE-DECISION.md);
- the [programme-state reconciliation through I4-A and V0](B87-PROGRAMME-STATE-RECONCILIATION-THROUGH-I4-A-AND-V0.md);
- the [B87-V0 persistence-validation closure and V1 entry gate](B87-V0-PERSISTENCE-VALIDATION-CLOSURE-AND-V1-ENTRY-GATE.md);
- the [pre-LLM implementation programme contract](B87-PRE-LLM-IMPLEMENTATION-PROGRAMME-CONTRACT.md);
- the [B87-I1 persistence-kernel acceptance decision](B87-I1-PERSISTENCE-KERNEL-ACCEPTANCE-DECISION.md);
- the [B87-I1 controlled-resilience reference-boundary decision](B87-I1-CONTROLLED-RESILIENCE-REFERENCE-BOUNDARY-DECISION.md);
- the [B87-I2 governed-task-runtime acceptance decision](B87-I2-GOVERNED-TASK-RUNTIME-ACCEPTANCE-DECISION.md); and
- the [D0-A3 persistence and protocol architecture](../architecture/B87-D0-A3-PERSISTENCE-AND-PROTOCOL-ARCHITECTURE.md).

The following boundaries remain fixed:

- the accepted implementation ledger through I4-A is unchanged;
- the I4-A/I4-B ownership partition is unchanged;
- migrations `0001` through `0011` remain immutable;
- I4-B may use only the repository-owned inactive provider and deterministic
  mock provider described by the accepted contract;
- no arbitrary provider injection, real provider, model, server, endpoint, API,
  credential, tool, evaluation, training, identity progression, Validation V1,
  or experimental implementation is authorized;
- provider calls remain outside database transactions;
- exact returned bytes must be captured in a dedicated transaction before
  decoding, parsing, validation, or finalization;
- terminal finalization remains a separate transaction;
- automatic retry remains prohibited;
- model output remains evidence, not authority, memory, approval, evaluation,
  or identity; and
- an I2 task completion retains the narrow meaning defined by the accepted I4-B
  contract.

The accepted V0 record supplies the exact scenario identifiers and titles used
below. Its historical PASS results and run identifiers remain historical
evidence only; this accepted planning decision does not claim a result for a
future candidate.

## 4. Anticipated I4-B persistence change surface

The regression scope is based on logical persistence consequences, not a
presumption that every concept requires a separate table.

| Anticipated logical surface | Persistence consequence to test | Design freedom preserved |
| --- | --- | --- |
| Additive invocation-related migration | Ordered application after `0011`, immutable prior hashes, fresh and upgrade behavior, rollback, foreign keys, and schema integrity | The exact additive migration count and normalized layout remain implementation-review decisions |
| Provider registration and provider configuration | Immutable repository-owned provider identity, configuration snapshots, hashes, scope binding, and closed registration | Records may be normalized or embedded where the accepted contract permits |
| Immutable invocation request | One canonical request identity bound to task, session, project, context, runtime identity, provider, model descriptor, schema, and configuration | The narrowest additive relational layout may be used |
| Exact model-input packet and hashes | Byte-for-byte or canonical reconstruction, content-hash verification, and no mutation after preparation | Existing accepted I4-A records remain owned by I4-A |
| Invocation idempotency key | Deterministic duplicate handling, different-content conflict, one admissible durable attempt, and no repeat provider call | The accepted invocation identifier may supply the idempotency identity without a separate table |
| Invocation lifecycle states | Append-only ordered transitions, immutable terminal state, visible `in_progress` and `raw_output_captured` states, and contradictory-state detection | Current-status projection may be derived or stored consistently with the accepted contract |
| Dedicated raw-output capture transaction | Atomic exact-byte capture, byte length, SHA-256, declared encoding, capture metadata, and `raw_output_captured` transition | Exact columns and indexes remain implementation-review decisions |
| Decoding, parsing, and validation after capture | Derived deterministic data cannot replace raw evidence; malformed and undecodable output remains reconstructable | Processing may remain outside a database transaction until finalization |
| Separate terminal-finalization transaction | Atomic derived results, model-output record, terminal transition, and any permitted I2 task transition | No new I2 state or provider-controlled transition is permitted |
| Non-terminal recovery and no automatic retry | Restart reveals the exact incomplete state and does not replay, resume, infer timeout, or call the provider | Operator-directed future resolution remains outside I4-B unless separately accepted |
| Invocation output and failure records | Success, expected negative outcomes, provider failure, timeout, stale context, interruption, and unexpected internal failure remain distinguishable | Failure normalization may use the narrowest accepted shape |
| Restart reconstruction | Exact request, input, raw evidence, derived results, transitions, anchors, and task relationships survive reopen and separate-process reconstruction | Existing reconstruction services may be extended without changing accepted historical semantics |
| Reference-anchor and evidence relationships | Typed `model_invocation` anchor, one operational claim, project binding, no orphan records, and preservation of unclaimed anchors after failed creation | Later operational claiming must not rewrite the accepted I1 migration |
| Task-completion relationship | Runtime-owned completion is atomic where permitted and cannot bypass human review or imply truth, approval, suitability, or admission | A succeeded invocation may coexist with an uncompleted task |
| Concurrent invocation attempts | Same-key serialization or deterministic conflict, distinct-key progress, lock handling, and cross-scope isolation | The accepted SQLite ownership and connection configuration remain authoritative |
| Integrity inspection | Missing, partial, terminal, contradictory, tampered, cross-scope, orphaned, multiply claimed, or hash-invalid state is detected | The implementation may add the narrowest deterministic inspection needed |

Any future design that requires destructive migration, changes an accepted
identity rule, changes the SQLite concurrency model, edits migrations `0001`
through `0011`, or changes an accepted I2, I3, or I4-A behavior is outside this
decision and is a stop condition.

## 5. Least-regression-sufficient classification rule

Each accepted V0 scenario is assigned exactly one classification:

1. `MANDATORY SCOPED RERUN` when the anticipated I4-B change directly alters or
   relies on the persistence behavior represented by that scenario;
2. `CONDITIONAL RERUN` when the accepted baseline and mandatory scoped scenarios
   are sufficient unless a listed implementation-design or observed-result
   trigger occurs;
3. `NOT REQUIRED FOR I4-B` when the accepted behavior is outside the authorized
   I4-B change surface and no I4-B claim relies on rerunning it; or
4. `UNRESOLVED — REQUIRES NOLAN-BYTE DECISION` when the repository does not
   contain enough accepted information to decide safely.

No scenario mapping below is unresolved. Nolan–Byte semantic and traceability
review accepts that V0-T12 and V0-T14 retain their conditional classifications
for decision version 1.0. The complete decision is accepted and recorded in
`B87-I4-B-SCOPED-V0-REGRESSION-ACCEPTANCE-DECISION.md`.

The historical harness has no recoverable committed revision. This decision
therefore defines `B87-I4B-HARNESS-FREEZE-MANIFEST-v1.0` as the prospective
immutable versioning protocol. Acceptance confirms the protocol, while the
exact future manifest hash is generated only after the I4-B candidate and
scenario adaptations are complete and is mandatory before external execution.

## 6. Complete scenario classification

| Scenario | Accepted title | Classification | Database mode | Acceptance effect |
| --- | --- | --- | --- | --- |
| V0-T01 | Clean installation | `MANDATORY SCOPED RERUN` | Fresh | Failure blocks I4-B acceptance |
| V0-T02 | Fresh database and migration execution | `MANDATORY SCOPED RERUN` | Both | Failure blocks I4-B acceptance |
| V0-T03 | Separate-process reconstruction | `MANDATORY SCOPED RERUN` | Both | Failure blocks I4-B acceptance |
| V0-T04 | Governed write | `MANDATORY SCOPED RERUN` | Both | Failure blocks I4-B acceptance |
| V0-T05 | Pre-commit termination | `MANDATORY SCOPED RERUN` | Both | Failure blocks I4-B acceptance |
| V0-T06 | Duplicate governed-write rejection | `MANDATORY SCOPED RERUN` | Both | Failure blocks I4-B acceptance |
| V0-T07 | Conflicting governed-identity rejection | `MANDATORY SCOPED RERUN` | Both | Failure blocks I4-B acceptance |
| V0-T08 | Post-commit recovery | `MANDATORY SCOPED RERUN` | Both | Failure blocks I4-B acceptance |
| V0-T09 | Concurrent same-identity contention | `MANDATORY SCOPED RERUN` | Both | Failure blocks I4-B acceptance |
| V0-T10 | Concurrent distinct governed writes | `MANDATORY SCOPED RERUN` | Both | Failure blocks I4-B acceptance |
| V0-T11 | Commit-boundary read visibility | `MANDATORY SCOPED RERUN` | Both | Failure blocks I4-B acceptance |
| V0-T12 | Sustained concurrent-reader stability | `CONDITIONAL RERUN` | Both if triggered | Failure blocks I4-B acceptance when triggered |
| V0-T13 | Sustained multiwriter contention | `MANDATORY SCOPED RERUN` | Upgraded by default; both if the sufficiency gate fails | Failure blocks I4-B acceptance |
| V0-T14 | One-hour bounded soak | `CONDITIONAL RERUN` | Upgraded if triggered | Failure blocks I4-B acceptance when triggered |

## 7. Detailed scenario decisions

### 7.1 V0-T01 — Clean installation

- **Classification:** `MANDATORY SCOPED RERUN`.
- **I4-B trigger:** the candidate adds an invocation package surface, at least
  one additive migration, schema-registry entries, and composition-root wiring.
- **Database mode:** fresh database.
- **Required workload or variation:** from a pristine checkout of the exact
  frozen candidate, use the repository's accepted dependency baseline to
  install the package in an isolated environment, import the production
  package with experimental packages absent, initialize a new database, and
  verify that no provider server, model, endpoint, credential, or network access
  is required.
- **Required evidence:** candidate commit and clean status, platform and Python
  versions, exact installation and import commands, exit codes, dependency
  inventory, created-file inventory, and the initialized database path and
  hash.
- **Pass condition:** installation and import are reproducible; initialization
  reaches the candidate migration chain without a prohibited dependency,
  artifact, external call, or source-tree mutation.
- **Acceptance effect:** any failure blocks I4-B acceptance.

### 7.2 V0-T02 — Fresh database and migration execution

- **Classification:** `MANDATORY SCOPED RERUN`.
- **I4-B trigger:** I4-B necessarily proposes an ordered additive migration
  after `0011`.
- **Database mode:** both a fresh database and an upgraded accepted-baseline
  database.
- **Required workload or variation:** apply the complete migration chain to an
  empty database; independently copy a representative accepted pre-I4-B
  database at migration `0011`, record its accepted rows and hashes, and apply
  only the additive candidate migration or migrations. Repeat startup against
  both databases. Inject migration failure where SQLite permits and verify
  rollback.
- **Required evidence:** migration filenames, order, and SHA-256 values;
  before-and-after `schema_migrations`; schema and index inventories; foreign-key
  checks; SQLite integrity checks; pre-I4-B table counts and deterministic
  record hashes; rollback snapshots; and repeated-startup transcripts.
- **Pass condition:** the fresh chain and upgrade both succeed; migrations
  `0001` through `0011` retain their accepted bytes, order, and hashes; the new
  migration is additive; failed application leaves no partial schema or
  migration record; foreign keys and integrity are clean; and accepted
  pre-I4-B records are neither lost nor mutated.
- **Acceptance effect:** any failure blocks I4-B acceptance.

### 7.3 V0-T03 — Separate-process reconstruction

- **Classification:** `MANDATORY SCOPED RERUN`.
- **I4-B trigger:** exact invocation reconstruction after restart is an
  acceptance requirement.
- **Database mode:** both fresh and upgraded databases.
- **Required workload or variation:** seed deterministic examples of a valid
  success, a terminal expected failure, malformed output, undecodable output,
  an `in_progress` invocation, and a `raw_output_captured` invocation. Close the
  creating process. In a separately started process, reconstruct each
  invocation and its request, canonical input packet, hashes, provider and model
  descriptor snapshots, state history, raw evidence, derived results, anchors,
  and task relationship.
- **Required evidence:** creator and reconstructor process identities and exit
  codes; canonical reconstruction artifacts and hashes from both processes;
  exact raw-byte artifacts with byte length and SHA-256; declared encoding and
  decode status; state-transition sequence; foreign-key and integrity reports;
  and negative-control results for missing, contradictory, or tampered
  relationships.
- **Pass condition:** reconstruction is exact in both database modes; successful,
  failed, and incomplete states remain distinguishable; malformed and
  undecodable bytes are preserved; tampering is detected; and historical output
  is not reinterpreted as authority, approval, memory, evaluation, identity, or
  task completion.
- **Acceptance effect:** any failure blocks I4-B acceptance.

### 7.4 V0-T04 — Governed write

- **Classification:** `MANDATORY SCOPED RERUN`.
- **I4-B trigger:** I4-B adds the governed invocation preparation, capture, and
  finalization write path.
- **Database mode:** both fresh and upgraded databases.
- **Required workload or variation:** using only the repository-owned inactive
  and deterministic mock providers, exercise provider-inactive, valid success,
  zero-length output, undecodable bytes, malformed JSON, schema-invalid output,
  semantic-invalid output, provider failure with returned bytes, and provider
  failure without returned bytes. Include one task whose contract permits
  runtime completion and one that still requires human review.
- **Required evidence:** exact requests and input hashes; provider-call count;
  state transitions; raw bytes, length, SHA-256, declared encoding, and capture
  metadata; decode, parse, schema, and semantic results; output and failure
  records; task state before and after; anchor claim; and transaction-level
  database snapshots.
- **Pass condition:** every variation reaches only its deterministic admissible
  state; returned bytes are durably captured before processing; expected
  negative outcomes are data rather than uncaught exceptions; provider facts
  remain separate from runtime conclusions; and task completion occurs only
  when the deterministic task/output contract permits it without outstanding
  human review.
- **Acceptance effect:** any failure blocks I4-B acceptance.

### 7.5 V0-T05 — Pre-commit termination

- **Classification:** `MANDATORY SCOPED RERUN`.
- **I4-B trigger:** I4-B introduces preparation, call-start, raw-capture, and
  terminal-finalization boundaries with distinct interruption semantics.
- **Database mode:** both fresh and upgraded databases.
- **Required workload or variation:** use deterministic external process barriers
  to terminate separately at the first seven interruption points defined in
  section 8.3. For termination during raw capture and during finalization, inject
  the stop after each material transaction step that the implementation exposes.
  Reopen the database after every termination.
- **Required evidence:** barrier identifier; process start, termination, and exit
  information; provider-call count; before-and-after database snapshots;
  transaction and WAL observations where available; state history; raw and
  derived record inventory; task state; restart reconstruction; foreign-key and
  integrity reports; and a harness negative control proving the asserted
  boundary would detect a forbidden partial commit.
- **Pass condition:** every termination yields exactly the durable state in
  section 8.3; no partial transaction masquerades as committed; committed raw
  evidence is never lost or mutated; no success or task completion appears
  before finalization commits; and no automatic provider retry occurs.
- **Acceptance effect:** any failure blocks I4-B acceptance.

### 7.6 V0-T06 — Duplicate governed-write rejection

- **Classification:** `MANDATORY SCOPED RERUN`.
- **I4-B trigger:** the invocation identifier is the idempotency identity and
  duplicate durable creation must not produce a second attempt.
- **Database mode:** both fresh and upgraded databases.
- **Required workload or variation:** submit the same canonical invocation
  request repeatedly before completion, after `raw_output_captured`, and after a
  terminal result. Attempt matching duplicate durable creation through the
  governed public boundary.
- **Required evidence:** all submitted request hashes; provider-call count;
  invocation, transition, raw-output, model-output, and task-transition counts;
  returned or reconstructed results; and before-and-after canonical hashes of
  the original attempt.
- **Pass condition:** direct duplicate creation is rejected or resolved without a
  second durable invocation; matching resubmission reconstructs the one existing
  terminal or incomplete attempt; the provider is called at most once; and prior
  raw output and state are unchanged.
- **Acceptance effect:** any failure blocks I4-B acceptance.

### 7.7 V0-T07 — Conflicting governed-identity rejection

- **Classification:** `MANDATORY SCOPED RERUN`.
- **I4-B trigger:** I4-B creates a new governed invocation identity and requires
  deterministic rejection when the same invocation identifier is reused with
  different canonical content.
- **Database mode:** both fresh and upgraded databases.
- **Required workload or variation:** use the following conflict sequence:

    1. create one canonical invocation request under invocation identifier A;
    2. attempt to reuse identifier A with different canonical input;
    3. vary at least task identity, session or project binding,
       context-package hash, provider or configuration snapshot,
       expected-output schema, and model-input packet or request hash;
    4. attempt conflicting reuse after preparation, after raw-output capture,
       and after terminal finalization; and
    5. reconstruct the original invocation after every conflict attempt.

- **Required evidence:** original and conflicting canonical request bodies and
  hashes; provider-call counts; before-and-after invocation, transition,
  raw-output, model-output, anchor, and task inventories; original-record
  hashes; conflict classifications; separate-process reconstruction; and
  foreign-key and integrity results.
- **Pass condition:** every conflicting reuse is rejected deterministically; no
  second provider call occurs; no original record, transition, raw output,
  output, anchor, or task relationship changes; no second durable invocation is
  created under the reused identity; the original invocation reconstructs
  exactly; different scope bindings cannot be smuggled through the existing
  identity; and fresh and upgraded database behavior is equivalent.
- **Acceptance effect:** any failure blocks I4-B acceptance.

V0-T06 and V0-T07 retain separate purposes. V0-T06 tests matching duplicate
governed-write submission and idempotent reconstruction. V0-T07 tests
conflicting reuse of the same governed identity with different canonical
content.

### 7.8 V0-T08 — Post-commit recovery

- **Classification:** `MANDATORY SCOPED RERUN`.
- **I4-B trigger:** a caller may fail to receive acknowledgement after terminal
  finalization has committed.
- **Database mode:** both fresh and upgraded databases.
- **Required workload or variation:** terminate the caller or worker after the
  terminal-finalization commit is externally observable but before the caller
  receives acknowledgement. Restart in a new process and resubmit the matching
  request. Repeat for a successful result and an expected terminal negative
  result.
- **Required evidence:** deterministic post-commit barrier, transaction evidence,
  absent caller acknowledgement, process termination and restart records,
  provider-call count, reconstruction, invocation and transition counts, raw and
  derived hashes, and task-state history.
- **Pass condition:** restart and matching resubmission return or reconstruct the
  one committed result; no second provider call, invocation, raw capture, model
  output, terminal transition, or task completion is created.
- **Acceptance effect:** any failure blocks I4-B acceptance.

### 7.9 V0-T09 — Concurrent same-identity contention

- **Classification:** `MANDATORY SCOPED RERUN`.
- **I4-B trigger:** concurrent attempts may submit the same invocation
  idempotency identity.
- **Database mode:** both fresh and upgraded databases.
- **Required workload or variation:** release multiple processes simultaneously
  against one matching invocation request, then against one invocation
  identifier split between matching and conflicting canonical content. Observe
  contention at preparation, raw capture, and finalization.
- **Required evidence:** process barrier and ordering data; request hashes;
  provider-call count; lock and busy-timeout observations; durable row and
  transition counts; returned or reconstructed results; conflict results; task
  state; and final foreign-key and integrity reports.
- **Pass condition:** exactly one admissible durable invocation exists; matching
  callers observe that invocation; conflicting content is rejected
  deterministically; uniqueness is preserved at every lifecycle stage; no
  automatic retry occurs; and lock contention does not create partial or
  contradictory state.
- **Acceptance effect:** any failure blocks I4-B acceptance.

### 7.10 V0-T10 — Concurrent distinct governed writes

- **Classification:** `MANDATORY SCOPED RERUN`.
- **I4-B trigger:** distinct invocation identities may progress concurrently
  through multiple short transactions.
- **Database mode:** both fresh and upgraded databases.
- **Required workload or variation:** use concurrent processes to create
  distinct deterministic invocations across multiple tasks, sessions, and
  projects, including valid, malformed, and provider-failure outputs. Include
  separate invocations for the same task and context only where the accepted
  at-most-one-non-terminal rule permits their ordering.
- **Required evidence:** process and barrier logs; identity and scope matrix;
  provider-call counts; lock observations; complete invocation and transition
  inventory; raw and derived hashes; task outcomes; and cross-project,
  cross-session, and cross-task relationship checks.
- **Pass condition:** every admissible identity has exactly one correct durable
  result; prohibited overlapping non-terminal attempts are rejected; all
  transaction and scope bindings are correct; no lock failure creates false
  success; and no record or output crosses project, session, or task scope.
- **Acceptance effect:** any failure blocks I4-B acceptance.

### 7.11 V0-T11 — Commit-boundary read visibility

- **Classification:** `MANDATORY SCOPED RERUN`.
- **I4-B trigger:** raw capture and terminal finalization intentionally expose
  two different committed visibility boundaries.
- **Database mode:** both fresh and upgraded databases.
- **Required workload or variation:** hold external readers at deterministic
  barriers before and after preparation, `in_progress`, raw-capture commit, and
  terminal-finalization commit. Include rollback during raw capture and during
  finalization.
- **Required evidence:** writer barrier and commit events; reader process
  snapshots; state history; raw, derived, terminal, and task-record visibility;
  transaction rollback evidence; and integrity reports.
- **Pass condition:** readers never observe a partial transaction; exact raw
  bytes and `raw_output_captured` become visible atomically; derived output,
  terminal state, and any permitted task transition become visible only with the
  finalization commit; rollback exposes none of the failed transaction's partial
  effects.
- **Acceptance effect:** any failure blocks I4-B acceptance.

### 7.12 V0-T12 — Sustained concurrent-reader stability

- **Classification:** `CONDITIONAL RERUN`.
- **I4-B trigger:** run V0-T12 if the actual design introduces a long-lived read
  transaction, continuously polling or background reconstruction reader,
  connection-pool behavior, changed SQLite connection settings, a materially
  new index/query plan, or a sustained-reader pattern not exercised by the
  mandatory V0-T13 scoped workload.
- **Database mode:** both fresh and upgraded databases if triggered.
- **Required workload or variation:** preserve the accepted V0-T12 validation
  purpose and define a prospective I4-B-adapted workload that reconstructs
  representative terminal and incomplete I4-B invocations while deterministic
  I4-B writes occur. The exact reader and writer counts, duration or operation
  count, read mix, expected observations, and negative control must be defined
  before execution and included in the harness freeze manifest. Historical
  parameters not present in accepted evidence must not be inferred.
- **Required evidence:** frozen workload definition, reader and writer process
  logs, reconstruction hashes, read observations, lock and busy-timeout
  observations, database snapshots, foreign-key and integrity reports, and the
  accepted negative control.
- **Pass condition:** all observations are committed admissible states;
  reconstructions remain exact; no reader sees cross-scope or partial data; no
  reader or writer lock failure violates the workload contract; and integrity
  remains clean.
- **Acceptance effect:** when a trigger is present, failure blocks I4-B
  acceptance. When no trigger is present, V0-T03, V0-T11, and the reader portion
  of V0-T13 provide the required scoped read evidence and V0-T12 is not run.

### 7.13 V0-T13 — Sustained multiwriter contention

- **Classification:** `MANDATORY SCOPED RERUN`.
- **I4-B trigger:** the invocation path introduces multiple ordered write
  transactions per invocation and same-identity uniqueness under process
  contention.
- **Database mode:** upgraded accepted-baseline database by default. The scope
  automatically expands to both fresh and upgraded databases if the sufficiency
  gate below fails.
- **Upgraded-only sufficiency gate:** upgraded-only execution is valid only when:

    1. V0-T02 proves that fresh and upgraded databases reach an equivalent final
       candidate schema, including tables, columns, indexes, triggers,
       foreign-key relationships, migration ledger, journal mode, and relevant
       SQLite connection configuration; and
    2. V0-T09 and V0-T10 pass their fresh-database contention workloads.

  If equivalence cannot be demonstrated, either fresh-database contention
  scenario fails, or an implementation difference could affect sustained
  contention, V0-T13 automatically expands to both fresh and upgraded
  databases. The expansion does not change the mandatory classification and
  must be recorded before external execution.
- **Required workload or variation:** preserve at least the accepted V0-T13
  process shape of three writers and four readers and at least 24 expected
  candidate invocations. Use deterministic inactive and mock-provider cases
  spanning valid, malformed, undecodable, schema-invalid, provider-failure, and
  same-idempotency-key attempts. Readers must reconstruct terminal and incomplete
  attempts while writers progress. The exact deterministic mix and expected
  state counts must be frozen before execution.
- **Required evidence:** frozen workload and expected state matrix; all process
  logs and exit codes; provider-call counters; committed invocation, transition,
  raw-output, output, and task counts; reader observations and reconstruction
  hashes; lock and busy-timeout observations; preserved pre-I4-B record hashes;
  the V0-T02 equivalence report; fresh V0-T09 and V0-T10 results; the recorded
  database-mode decision; foreign-key and SQLite integrity results; and a
  negative control.
- **Pass condition:** every expected admissible write is present exactly once;
  same-key contention produces one invocation and at most one provider call;
  all reader observations are valid committed states; raw and terminal
  transaction ordering is preserved; no lock error violates the workload
  contract; accepted pre-I4-B records are unchanged; final integrity is clean;
  and the upgraded-only sufficiency gate passes or the scenario passes against
  both database modes.
- **Acceptance effect:** any failure blocks I4-B acceptance.

### 7.14 V0-T14 — One-hour bounded soak

- **Classification:** `CONDITIONAL RERUN`; it is not mandatory by default.
- **I4-B trigger:** run V0-T14 if the actual implementation introduces
  time-dependent or long-lived state beyond the accepted contract's bounded
  calls, such as connection pooling, a continuously active worker, polling,
  queued finalization, time-based cleanup, or other retained resources; if the
  measured I4-B write profile is materially different from the mandatory
  contention workload; or if V0-T09, V0-T10, V0-T12, or V0-T13 reveals
  accumulating incomplete states, lock pressure, resource growth, or another
  duration-sensitive anomaly.
- **Database mode:** upgraded accepted-baseline database if triggered.
- **Required workload or variation:** run for 3,600 seconds with the accepted
  process shape of two writers and three readers. Repeat a deterministic
  ten-invocation cycle containing four valid schema-and-semantic successes, one
  zero-length output, one undecodable byte sequence, one malformed JSON output,
  one schema-invalid JSON output, one provider failure with returned bytes, and
  one provider failure without returned bytes. For this workload,
  syntactically malformed or undecodable output is therefore 20%; zero-length
  and schema-invalid output are separately classified at 10% each. Inject one
  interruption after every 100 attempted invocations, alternating between
  raw-capture and terminal-finalization transaction steps, and restart the
  terminated writer immediately through a new database connection. Restart one
  reader process every ten minutes in round-robin order. Perform foreign-key,
  SQLite integrity, state-machine, raw-hash, and representative reconstruction
  checks every five minutes and after the run. Freeze the expected classification
  rules and interruption sequence before execution.
- **Required evidence:** frozen workload and ratios; duration and operation
  counts; checkpoints; process starts, interruptions, restarts, and exits;
  provider-call counters; lock observations; state and result counts; raw-byte
  verification samples; reconstruction samples; preserved pre-I4-B record
  hashes; periodic and final integrity results; and a negative control.
- **Pass condition:** the full 3,600-second workload completes; all predetermined
  checkpoints and restarts are accounted for; every invocation is in its
  expected terminal or intentionally incomplete state; no automatic retry,
  duplicate completion, raw-evidence mutation, cross-scope contamination, or
  duration-sensitive lock failure occurs; and all final integrity and
  reconstruction checks pass.
- **Acceptance effect:** when a trigger is present, failure blocks I4-B
  acceptance. When no trigger is present, the accepted historical V0-T14
  endurance evidence plus the mandatory scoped interruption, reconstruction,
  visibility, and V0-T13 contention evidence is sufficient because I4-B permits
  no real provider, server, streaming, automatic retry, background recovery, or
  other inherently long-running provider behavior.

## 8. Mandatory coverage matrices

### 8.1 Installation and migration

| Required coverage | Primary external scenario | Required internal support |
| --- | --- | --- |
| Clean installation at the frozen candidate | V0-T01 | Packaging and import tests |
| Complete fresh migration chain | V0-T02 fresh mode | Fresh-database migration tests |
| Upgrade from the accepted pre-I4-B baseline | V0-T02 upgraded mode | Upgrade fixture and migration tests |
| Additive behavior and prior migration immutability | V0-T02 | Migration hash, order, rollback, and tamper tests |
| Foreign-key and schema integrity | V0-T02 and final checks in all mandatory database scenarios | Connection, foreign-key, schema-registry, and integrity tests |
| Preservation of accepted pre-I4-B records | V0-T02, V0-T03, and V0-T13 | Deterministic pre/post record-hash comparison |
| Fresh/upgraded equivalence for V0-T13 scope | V0-T02, plus fresh V0-T09 and V0-T10 | Schema, journal-mode, connection-configuration, and contention comparison |

The accepted pre-I4-B upgrade fixture must be created from the accepted schema
through migration `0011` and contain representative accepted I1, I2, I3, and
I4-A records. Its origin, construction command, row inventory, and deterministic
hashes must be recorded before use. It must not contain secrets, private
evidence, or live memory data.

V0-T02 must produce an explicit fresh-versus-upgraded equivalence report for
tables, columns, indexes, triggers, foreign-key relationships, migration ledger,
journal mode, and relevant SQLite connection configuration. Together with the
fresh V0-T09 and V0-T10 results, that report decides whether V0-T13 remains
upgraded-only or automatically expands to both database modes.

### 8.2 Raw-output durability

V0-T04, V0-T05, V0-T08, and V0-T11 together must prove:

- exact returned bytes, including zero-length bytes, commit before decoding,
  parsing, schema validation, semantic validation, or finalization;
- the stored byte length and SHA-256 match those exact bytes;
- provider-declared encoding is preserved as metadata without controlling the
  strict UTF-8 decode result;
- undecodable bytes, malformed JSON, schema-invalid output, and
  semantic-invalid output remain preserved;
- parse and validation failures are deterministic data, not uncaught
  exceptions;
- no derived record can replace or mutate raw evidence;
- a failure after raw capture but before finalization leaves the invocation
  visibly `raw_output_captured`, with no success, task completion, or automatic
  retry; and
- reconstruction and integrity inspection detect missing, altered, mismatched,
  or contradictory raw and derived relationships.

### 8.3 Interruption boundaries and expected durable state

| Interruption point | External mapping | Required durable state after restart |
| --- | --- | --- |
| Before provider return | V0-T05 | Invocation remains `in_progress`; no raw-output, derived-output, terminal, success, or task-completion record exists; no automatic retry occurs |
| After provider return but before raw-output capture | V0-T05 | Invocation remains `in_progress`; returned bytes were not durably captured and must not be claimed as captured; no partial raw record, success, task completion, or automatic retry exists; operator review is required |
| During raw-output capture | V0-T05 | The capture transaction rolls back atomically; invocation remains `in_progress`; no partial bytes, length, hash, metadata, or `raw_output_captured` transition exists; no processing or retry occurs |
| After raw-output capture but before decoding | V0-T05 | Exact bytes, length, SHA-256, declared encoding, capture metadata, and `raw_output_captured` are durable; no decode, parse, validation, terminal, success, or task-completion record exists |
| During parsing or validation | V0-T05 | The same exact `raw_output_captured` evidence remains durable and unchanged; no partial derived result, terminal state, success, task completion, or retry exists |
| After validation but before terminal finalization | V0-T05 | Raw evidence and `raw_output_captured` remain the only committed result of the provider output path; uncommitted derived results are not reconstructed as durable; no terminal state or task transition exists |
| During terminal finalization | V0-T05 | Finalization rolls back atomically; raw evidence and `raw_output_captured` remain; no partial model-output, terminal transition, success, failure classification, or task transition exists |
| After terminal finalization but before caller acknowledgement | V0-T08 | The one terminal invocation, immutable derived result, and any permitted task transition remain committed; matching resubmission reconstructs them without another provider call or duplicate record |

The unavoidable process-loss window after provider return and before capture does
not permit the runtime to claim bytes it did not commit. The required safety
property at that boundary is visible incompleteness, not invented evidence or an
automatic second call. Once raw capture commits, loss or mutation of that
evidence is never admissible.

### 8.4 Idempotency and retry behavior

V0-T06, V0-T07, V0-T08, and V0-T09 must jointly prove:

- the invocation identifier is the idempotency identity;
- matching terminal resubmission reconstructs the existing result;
- matching non-terminal resubmission reconstructs the visible incomplete
  attempt;
- different canonical content under the same identifier produces a conflict;
- ambiguous acknowledgement cannot create a second provider call or completion;
- concurrent same-key attempts yield exactly one admissible durable invocation;
- any explicit future retry would require a new invocation identifier and an
  immutable `retry_of_invocation_id`;
- the prior attempt and captured raw output remain unchanged; and
- no timeout inference, replay, resume, or provider retry occurs automatically.

### 8.5 Reconstruction and integrity

V0-T03 and V0-T11, supported by integrity assertions in every mandatory external
scenario, must cover:

- exact reconstruction after database close and process restart;
- both fresh and upgraded databases;
- successful, terminal-failed, `in_progress`, and `raw_output_captured`
  invocations;
- canonical input, descriptor, configuration, schema, request, raw-output,
  parsed-output, transition, anchor, and task hashes;
- exact bytes, byte length, SHA-256, declared encoding, and decode status;
- detection of missing, orphaned, multiply claimed, mismatched, cross-scope,
  contradictory, reordered, or tampered relationships;
- immutable terminal state and append-only transition order; and
- preservation of model output as evidence without reinterpretation as
  authority, memory, approval, evaluation, capability, identity, or training
  material.

### 8.6 I2 task-completion distinction

Internal I4-B tests and external V0-T04 must include deterministic task
contracts that distinguish:

1. a bounded task/output contract for which a valid response is sufficient and
   runtime-owned completion is permitted; and
2. a contract for which the invocation may succeed but human review or approval
   remains outstanding.

The first may produce one atomic I2 completion when all accepted preconditions
remain true. The second must leave the task uncompleted. Neither result
establishes truth, external approval, memory approval, evaluation success, model
suitability, developmental improvement, or candidate admission. Model output
cannot create, infer, simulate, or bypass a required human decision.

### 8.7 Bounded-soak decision

V0-T14 is not a mandatory default rerun. The accepted V0 baseline already
contains one-hour endurance evidence for the unchanged SQLite foundation, while
the bounded I4-B contract prohibits the principal new sources of indefinite
provider behavior: real servers, streaming, automatic retry, background
recovery, and external model calls.

The new multi-transaction risk is addressed directly by mandatory interruption,
commit-visibility, restart, idempotency, same-key, distinct-key, and sustained
multiwriter regressions. V0-T14 becomes mandatory only when one of the explicit
duration-sensitive triggers in section 7.14 exists.

## 9. Mandatory internal repository gate before candidate freeze

Before a candidate may be frozen for external regression, the future authorized
I4-B implementation must pass all of the following inside the source
repository:

1. the complete fresh migration chain and an upgrade fixture from migration
   `0011`, including repeat startup, rollback injection, migration tamper
   detection, foreign-key checks, schema integrity, and preservation hashes;
2. provider registration and configuration immutability, closed registry,
   arbitrary-injection rejection, and shipped-provider no-side-effect tests;
3. canonical input-packet construction, hash verification, invocation
   idempotency, different-content conflict, anchor claiming, project binding,
   and immutable request tests;
4. state-machine tests for every allowed and forbidden transition, terminal
   immutability, at-most-one non-terminal attempt, and no automatic retry;
5. raw-capture transaction failure injection after every material step,
   including zero-length, undecodable, malformed, schema-invalid, and
   provider-failure output;
6. deterministic UTF-8, parse, schema, and semantic result tests proving that
   expected failures are data and raw bytes never change;
7. finalization failure injection after every material step, atomic model-output
   and task-transition tests, and the I2 human-review distinction in section
   8.6;
8. file-backed integration tests for restart reconstruction of successful,
   failed, and incomplete invocations on fresh and upgraded databases;
9. integrity tests for byte, length, hash, encoding, derived output, transition,
   terminal, anchor, task, orphan, missing, contradictory, and cross-scope
   corruption;
10. deterministic same-key and distinct-key contention tests, including
    ambiguous caller acknowledgement and provider-call counts;
11. the complete pytest suite, architecture tests, strict D0 validation,
    migration validation, schema-registry checks, dependency and prohibited
    import checks, Markdown and documentation checks, `git diff --check`, and
    prohibited-artifact inspection; and
12. a clean candidate inventory containing only reviewed, authorized I4-B
    implementation and documentation changes.

Internal tests are necessary but cannot substitute for mandatory external
process restart, clean installation, upgrade, interruption, visibility, or
contention evidence.

## 10. External regression gate after candidate freeze

### 10.1 Preconditions

External regression may begin only when:

- the exact I4-B candidate commit is frozen and recorded;
- all mandatory internal gates in section 9 pass at that commit;
- Nolan–Byte has accepted this decision and recorded its version;
- the implementation authorization identifies that accepted decision version;
- a valid `B87-I4B-HARNESS-FREEZE-MANIFEST-v1.0` has been generated after the
  candidate and executable scenario adaptations are complete;
- the exact canonical freeze-manifest SHA-256 and scenario-specific definition
  hashes are recorded;
- evidence proves that every executed harness file matches the manifest;
- any valid harness Git commit that later exists is recorded alongside the
  mandatory freeze-manifest hash;
- the V0-T13 database-mode sufficiency decision is recorded;
- the harness remains outside the source repository;
- the source checkout is clean and is not modified by validation;
- all fixtures are synthetic or specifically approved and contain no secrets,
  credentials, personal information, live memory data, or private evidence; and
- expected outcomes and negative controls are frozen before execution.

Acceptance of this planning decision does not require a future executable
harness hash. External execution does.

### 10.2 Harness freeze protocol

Before any I4-B external scoped regression executes, the external harness must
produce a canonical immutable freeze manifest under:

```text
B87-I4B-HARNESS-FREEZE-MANIFEST-v1.0
```

The manifest must contain:

- manifest protocol and version;
- frozen I4-B candidate commit;
- harness root identifier;
- generation timestamp;
- for every allowlisted file, its normalized repository-relative path, exact
  byte length, SHA-256 over exact raw file bytes, scenario identifiers supplied
  by that file, and controller, assertion, fixture, or negative-control
  classification;
- dependency and environment-definition files;
- the explicit allowlist and exclusions;
- canonical manifest JSON;
- SHA-256 over the canonical manifest;
- scenario-specific definition hashes;
- a clean frozen-source inventory; and
- evidence that the files executed for each scenario match the manifest.

The allowlist must include all executable and decision-affecting harness
material:

- scenario controllers;
- writer, reader, fixture, reconstruction, and snapshot scripts;
- assertion definitions;
- negative controls;
- workload configurations;
- dependency or lock files;
- shared harness libraries; and
- scenario contracts and configuration files.

The manifest must exclude generated or mutable material:

- `evidence/`;
- `runtime/`;
- `review-packets/`;
- `.venv/`;
- `.git/`;
- caches and `__pycache__/`;
- SQLite databases and sidecars;
- logs, transcripts, and generated summaries;
- ZIP evidence bundles; and
- temporary files.

Paths must be normalized to forward-slash repository-relative form and sorted
ordinally. File byte lengths and hashes must cover exact raw bytes. Canonical
manifest JSON must use UTF-8, ordinally sorted object keys and path entries, and
no insignificant whitespace; its SHA-256 covers those exact canonical JSON
bytes. Scenario-specific definition hashes must cover the ordered allowlisted
files that can execute or decide that scenario.

No external run may begin with an absent, mutable, or mismatched manifest. If a
valid harness Git commit later exists, both that commit and the freeze-manifest
hash must be recorded. The freeze manifest remains mandatory because it
identifies the exact executable scenario surface.

Any harness source change after freeze requires a new manifest. The change
invalidates unexecuted or affected evidence under the earlier manifest; the
replacement manifest and the affected scenario reruns must be recorded.

### 10.3 Mandatory external regressions

The frozen candidate must pass:

- V0-T01 — Clean installation;
- V0-T02 — Fresh database and migration execution;
- V0-T03 — Separate-process reconstruction;
- V0-T04 — Governed write;
- V0-T05 — Pre-commit termination;
- V0-T06 — Duplicate governed-write rejection;
- V0-T07 — Conflicting governed-identity rejection;
- V0-T08 — Post-commit recovery;
- V0-T09 — Concurrent same-identity contention;
- V0-T10 — Concurrent distinct governed writes;
- V0-T11 — Commit-boundary read visibility; and
- V0-T13 — Sustained multiwriter contention.

Only the scoped workloads and database modes in section 7 are mandatory. This
list does not silently import every historical V0 workload variation.

V0-T13 runs against the upgraded database by default only after its section
7.13 sufficiency gate passes. If that gate fails, its mandatory scope
automatically expands to both database modes and the expansion must be recorded
before execution.

### 10.4 Conditional external regressions

- V0-T12 — Sustained concurrent-reader stability runs only when a trigger in
  section 7.12 exists.
- V0-T14 — One-hour bounded soak runs only when a trigger in section 7.14 exists.

The final implementation evidence packet must explicitly evaluate every
conditional trigger. It may not omit a conditional scenario without recording
why no trigger is present. If implementation details materially change the
trigger analysis, this decision must be amended and accepted before external
execution.

### 10.5 No accepted scenario excluded

No accepted V0 scenario is excluded from consideration. Twelve scenarios are
mandatory scoped reruns and two are conditional reruns. Zero scenarios are
classified `NOT REQUIRED FOR I4-B`.

## 11. External evidence and negative-control contract

Every required external scenario must produce an immutable evidence bundle that
records at least:

- decision version, frozen candidate commit, branch, and clean source status;
- `B87-I4B-HARNESS-FREEZE-MANIFEST-v1.0`, its canonical JSON, exact SHA-256,
  allowlist, exclusions, clean frozen-source inventory, and scenario-specific
  definition hashes;
- any valid harness Git commit that exists at freeze time;
- exact file-match evidence proving the executed controllers, helpers,
  assertions, fixtures, configurations, and negative controls match the
  manifest;
- operating system, Python, SQLite, filesystem, and relevant process
  configuration;
- exact command, environment allowlist, start and finish times, duration, exit
  code, stdout, stderr, and warnings;
- database mode, fixture origin, fixture hash, and pre-run inventory;
- process identifiers, barriers, terminations, restarts, and provider-call
  counters;
- expected and observed invocation, transition, raw-output, model-output, task,
  anchor, and scope relationships;
- exact raw-byte evidence or safe synthetic fixtures, byte lengths, SHA-256
  values, declared encodings, and reconstruction hashes;
- database snapshots or hashes at defined boundaries;
- foreign-key, SQLite integrity, state-machine, reconstruction, and
  cross-scope results;
- negative-control method and proof that the harness detected it;
- final PASS or FAIL classification produced by predefined assertions; and
- source-repository status proving the harness did not modify the candidate.

Required negative controls must include, across the scoped sequence:

- altered raw bytes or a mismatched byte length or SHA-256;
- a missing, orphaned, mismatched, multiply claimed, or cross-project
  relationship;
- a duplicate or different-content invocation identity;
- a forbidden partial capture or partial finalization observation;
- a provider-call counter that would detect automatic retry;
- a contradictory or reordered terminal transition; and
- deliberate assertion corruption proving that the external controller does not
  report PASS when a required invariant is false.

Failed runs and negative evidence must be retained. A rerun does not erase or
replace an earlier failure.

## 12. Failure and stop conditions

Any of the following blocks I4-B acceptance:

- destructive or non-additive migration behavior;
- loss or mutation of accepted pre-I4-B records;
- raw-output evidence loss, meaning loss of a committed capture or a false claim
  that uncaptured bytes were preserved, or any mutation of captured bytes;
- duplicate invocation completion;
- automatic provider retry;
- unreconstructable invocation state;
- contradictory terminal states;
- incorrect task completion or bypass of required human review;
- cross-task, cross-session, or cross-project contamination;
- undetected integrity failure;
- inability to reproduce a required scoped regression;
- an absent, mutable, or mismatched harness freeze manifest or
  scenario-definition hash;
- execution of a harness file that is absent from the manifest or differs in
  byte length or SHA-256;
- an unrun mandatory scenario or triggered conditional scenario;
- source-repository mutation by the external harness; or
- any result that would require an unreviewed change to an accepted V0, I2, I3,
  or I4-A contract.

A failed scoped regression does not retroactively invalidate the accepted
historical V0 baseline. It blocks acceptance of the future I4-B candidate and
requires repair or an explicit Nolan–Byte reframe. Repair must preserve the
failed evidence and rerun every affected mandatory or triggered conditional
scenario against a newly frozen candidate commit.

Execution must stop if:

- the candidate commit, canonical manifest hash, scenario-definition hash, or
  executed harness file differs from the frozen record;
- a harness source change occurs after freeze without a new manifest and
  recorded invalidation of unexecuted or affected earlier-manifest evidence;
- the source tree or external evidence inventory cannot be made exact;
- a required fixture provenance or expected result is unknown;
- a conditional trigger cannot be determined;
- the implementation changes an accepted boundary outside I4-B;
- a test would require real provider, model, server, endpoint, API, credential,
  network, tool, Validation V1, or experimental capability; or
- an honest PASS or FAIL result cannot be produced from preserved evidence.

## 13. Relationship to implementation authorization and acceptance

Acceptance of this regression decision satisfies only the regression-planning
entry gate. It does not authorize implementation.

Nolan must still separately issue:

```text
AUTHORIZE B87-I4-B
```

That implementation authorization must identify accepted regression-decision
version 1.0 and its acceptance record,
`B87-I4-B-SCOPED-V0-REGRESSION-ACCEPTANCE-DECISION.md`. Neither this accepted
planning decision nor its acceptance record is that release.

Actual implementation details may narrow or expand the conditional reruns only
through the triggers already defined here. Any material divergence in migration,
transaction, identity, concurrency, reconstruction, persistence, integrity, or
workload design requires an amended regression decision and renewed Nolan–Byte
acceptance.

External regression may run only against a frozen I4-B candidate commit. I4-B
cannot be accepted until every mandatory scoped regression and every triggered
conditional regression has passed with complete, reproducible evidence.

No model output, test result, Codex report, harness classification, or prior
acceptance may issue implementation authority or accept the future candidate.
Nolan retains exclusive phase-release and final acceptance authority; Byte
provides architecture, governance, synthesis, and semantic review.

## 14. Nolan–Byte acceptance confirmation

Nolan–Byte semantic and traceability review accepts decision version 1.0. The
acceptance is recorded in
`B87-I4-B-SCOPED-V0-REGRESSION-ACCEPTANCE-DECISION.md`.

The accepted review confirms:

1. `B87-I4B-HARNESS-FREEZE-MANIFEST-v1.0` as the immutable prospective
   harness-versioning protocol without requiring a not-yet-existent executable
   manifest hash at planning-decision acceptance;
2. that the historical harness identity finding does not alter the accepted V0
   closure or its preserved immutable run evidence;
3. the twelve mandatory, two conditional, and zero-not-required scenario
   classifications, including V0-T12 as conditional under section 7.12 and
   V0-T14 as conditional under section 7.14 with its defined 3,600-second
   workload;
4. the V0-T13 upgraded-only sufficiency gate and automatic expansion to both
   database modes when equivalence or fresh contention is not established; and
5. that acceptance records only regression planning, leaves active
   implementation release `NONE`, and does not issue `AUTHORIZE B87-I4-B`.

The decision is operative only as the accepted regression-planning decision.
B87-I4-B implementation remains `NOT AUTHORIZED`, B87-V0 remains `CLOSED`, and
all external-execution gates remain in force.
