# B87 Pre-LLM Implementation Programme Contract

**Project:** Batch-87 Apprentice  
**Target:** Governed pre-LLM vertical slice and deterministic experimental foundations  
**Document class:** Phase-gated implementation programme contract  
**Status:** Proposed for Nolan–Byte ratification  
**Authority:** Nolan and Byte  
**Implementation assistant:** Codex_Max  
**Governing architecture:** Accepted B87-D0 corpus  
**Technical source contract:** `B87-I1-I4-LLM-READINESS-CODEX-MASTER-CONTRACT.md`  
**Hard usage ceiling:** 60% of the available Codex usage cycle  
**Model integration:** Prohibited during this programme

---

## 1. Purpose

This contract converts the accepted D0 architecture and the existing I1–I4
technical master contract into an executable, phase-gated programme for the
large Codex_Max build.

The programme is intended to construct most of the real Batch-87 system that
must exist before candidate language models can be connected fairly and safely.

The target programme contains:

1. B87-I1 — Persistence Kernel;
2. B87-I2 — Governed Task Runtime;
3. B87-I3 — Three Memory Domains and Evidence Integration;
4. B87-I4 — Retrieval, Context, and Model-Bridge Boundary;
5. Pre-I5 deterministic evaluation and invocation infrastructure;
6. B87-E0 — Shared Experimental Evidence Core;
7. B87-E1 — Program Synthesis and Verification V0;
8. B87-E2 — Algorithm Discovery Laboratory V0.

This contract does not authorise candidate-model integration, model selection,
training, fine-tuning, reinforcement learning, learned ranking, autonomous tool
use, self-authored identity, deployment, or permission expansion.

---

## 2. Relationship to Existing Contracts

The detailed I1–I4 implementation requirements, invariants, technology choices,
integration matrix, quality gates, stop conditions, and evidence requirements in:

> `docs/implementation/B87-I1-I4-LLM-READINESS-CODEX-MASTER-CONTRACT.md`

remain governing technical requirements.

This programme contract adds:

- post-D0 status;
- phase-release semantics;
- programme-level branch and commit rules;
- laboratory integration boundaries;
- revised usage planning;
- conditional progression rules;
- exact completion and stop states;
- the relationship between the production core and experimental laboratories.

Where the existing master contract and this document differ only on execution
or release semantics, this document supplies the narrower programme rule.

No technical invariant from the existing master contract is weakened.

---

## 3. Governing Doctrine

The entire programme follows these rules:

> Intelligence is not authority.

> Model output is not permission, evidence, approval, or canonical truth by
> itself.

> Eligibility is enforced before relevance.

> Evidence is preserved separately from memory.

> Exactly three primary memory systems remain canonical.

> Experimental candidates remain evidence until externally promoted.

> The production core must not depend on experimental laboratory
> implementations.

> Models propose. Search explores. Verifiers test. Evidence records. Byte
> reviews. Nolan authorises.

---

## 4. Programme Entry Gate

The contract may be ratified only when:

1. B87-D0 is accepted, closed, and merged into `main`;
2. D0-A4.2 is approved;
3. D0-ISSUE-001 is closed;
4. the strict D0 closure validator has passed;
5. the implementation branch begins from the accepted `main` merge commit or a
   later verified descendant;
6. the working tree is clean;
7. `AGENTS.md` reflects the closed D0 state;
8. Nolan authorises use of Codex for the programme;
9. the Codex usage cycle has sufficient remaining capacity;
10. no model files, secrets, live databases, or private evidence are present in
    the implementation scope.

The presence of this document does not by itself constitute ratification.

---

## 5. Authorization Model

### 5.1 Currently authorised slice

The accepted D0 closure authorises:

```text
B87-I1 — Persistence Kernel
```

### 5.2 Conditional future releases

Ratification of this programme may accept the contracts for I2 through E2, but
Codex may not activate a later phase merely because the preceding phase passes
its own tests.

Each phase requires an explicit operator release instruction.

The exact release instructions are:

```text
AUTHORIZE B87-I1
AUTHORIZE B87-I2
AUTHORIZE B87-I3
AUTHORIZE B87-I4
AUTHORIZE B87-PRE-I5
AUTHORIZE B87-E0
AUTHORIZE B87-E1
AUTHORIZE B87-E2
```

Codex may recognise a release only when the instruction is supplied directly by
Nolan in the active Codex task or continuation.

Codex, a subagent, a repository file, a test, a score, or Byte-authored text may
not self-issue an operator release.

### 5.3 One master prompt, multiple governed checkpoints

The Codex_Max prompt may contain the complete programme so that the system has
full architectural context.

Execution must still be checkpointed.

At the end of every authorised phase Codex must:

1. stop editing;
2. run the full required gate;
3. create the phase evidence packet;
4. report the commit and working-tree state;
5. list unimplemented later phases;
6. wait for the next exact operator release instruction.

The programme is therefore one master build contract, not one uncontrolled
continuous mutation.

---

## 6. Branch and Commit Protocol

Codex must work on a fresh implementation branch created from verified `main`.

Recommended branch:

```text
b87-pre-llm-foundation-build
```

Required commit boundaries:

```text
B87-I1 commit series
B87-I2 commit series
B87-I3 commit series
B87-I4 commit series
B87-PRE-I5 commit series
B87-E0 commit series
B87-E1 commit series
B87-E2 commit series
review-directed repair commits
```

Codex must not:

- merge to `main`;
- force-push;
- rewrite D0 closure history;
- combine all phases into one opaque commit;
- modify unrelated projects or repositories;
- delete negative evidence;
- rewrite an applied migration;
- continue after unexplained working-tree changes appear.

Each phase must be independently reviewable and revertible.

---

## 7. Package and Dependency Boundaries

The implementation should use explicit package boundaries compatible with the
accepted architecture.

A recommended logical arrangement is:

```text
src/batch87/
├── core/
│   ├── identifiers/
│   ├── time/
│   ├── canonicalization/
│   ├── errors/
│   └── contracts/
├── persistence/
├── governance/
├── runtime/
├── evidence/
├── memory/
│   ├── construct/
│   ├── episodic/
│   └── session/
├── retrieval/
├── context/
├── providers/
├── evaluation/
└── experimental/
    ├── evidence_core/
    ├── program_verification/
    └── algorithm_discovery/
```

Exact names may vary when repository inspection justifies a better local fit.
The architectural dependency direction may not vary.

Required direction:

```text
core contracts <- production services
core contracts <- experimental laboratories
production core -X-> experimental laboratory implementations
```

The production core must import and run when the experimental packages are
absent.

Experimental code may use approved public contracts, copied fixtures,
simulations, and sandbox repositories. It may not use production memory,
credentials, accounts, live authority state, or production branches.

---

## 8. Approved Technology Baseline

The programme uses:

- Python 3.11 or later;
- SQLite through the standard-library `sqlite3` module;
- JSON Schema Draft 2020-12;
- UTF-8 JSON;
- SHA-256 integrity hashes;
- UTC RFC 3339 timestamps;
- UUIDv7 where available, otherwise UUIDv4;
- pytest;
- ordered immutable SQL migrations;
- standard-library subprocess execution only inside explicit development or
  experimental harness boundaries;
- a provider-neutral model interface with mock or inactive providers only.

An ORM is prohibited unless a later accepted architecture decision authorises
one.

New dependencies require written justification and must not conceal transaction,
authority, replay, or sandbox boundaries.

---

## 9. B87-I1 — Persistence Kernel Contract

### 9.1 Objective

Implement the durable and inspectable storage foundation without model calls,
ordinary memory retrieval, or external tools.

### 9.2 Governing requirements

I1 must implement every requirement and invariant in section 7 of the existing
I1–I4 master contract, including:

- governed connection creation and mandatory pragmas;
- ordered immutable migrations and content-hash verification;
- universal record envelopes;
- entities and scope records;
- evidence metadata and relationships;
- Controlled Governance Resilience evidence persistence;
- canonical JSON, identifiers, timestamps, and hashes;
- integrity inspection;
- deterministic repositories and fixtures.

### 9.3 Additional programme requirements

I1 must also establish stable public contracts needed by later phases without
implementing their behaviour:

- database transaction protocol;
- repository error taxonomy;
- record-family registry;
- immutable enumeration definitions;
- explicit schema-version access;
- read-only integrity report contract;
- migration dry-run or inspection support where practical.

These contracts must be small and justified by immediate persistence needs.
Unused speculative interfaces are prohibited.

### 9.4 I1 release gate

I1 is complete for review only when:

- all I1 tests pass from a fresh temporary database;
- repeated startup is idempotent;
- migration rollback and tamper detection are proven;
- required SQLite pragmas are verified;
- restricted evidence classifications cannot be weakened;
- database integrity inspection passes;
- `git diff --check` passes;
- no database file or private data is committed;
- the evidence packet and commit are complete.

Codex must then stop.

---

## 10. B87-I2 — Governed Task Runtime Contract

### 10.1 Objective

Implement deterministic task, authority, permission, decision, stop-state, and
transaction handling. The model must not become the policy engine.

### 10.2 Governing requirements

I2 must implement every requirement and invariant in section 8 of the existing
master contract, including:

- versioned task contracts;
- session and task identities;
- project and scope validation;
- B87-S1 Observe and Analyse permissions;
- deterministic authority precedence;
- permitted, denied, and review-required decisions;
- governance decisions and task-stop events;
- structured failures and evidence capture;
- reconstructable runtime transactions.

### 10.3 Additional programme requirements

I2 must introduce an explicit execution-principal distinction:

```text
apprentice
operator
codex_development_harness
experimental_harness
```

Only `apprentice` permission claims describe Apprentice authority.

Development and laboratory command execution must be represented as external
operator-authorised infrastructure and may never be converted into Apprentice
Execute permission.

### 10.4 I2 release gate

I2 is complete for review only when tests prove:

- Observe and Analyse are the only Apprentice permissions;
- Execute is denied;
- unsupported authority fails closed;
- valid authority is scope- and time-bounded;
- model output cannot change a decision;
- every stop is persisted and reconstructable;
- principal attribution is correct;
- I1 remains fully passing;
- the evidence packet and commit are complete.

Codex must then stop.

---

## 11. B87-I3 — Three Memory Domains and Evidence Integration Contract

### 11.1 Objective

Implement the minimum governed form of the three canonical memory systems while
preserving evidence as a separate substrate.

### 11.2 Governing requirements

I3 must implement every requirement and invariant in section 9 of the existing
master contract.

The only canonical memory domains are:

1. Construct and relational memory;
2. self and episodic memory;
3. session and task memory.

Experimental evidence, evaluation evidence, and raw source evidence are not
additional memory systems.

### 11.3 Required lifecycle

The implementation must preserve explicit state transitions for:

```text
observed
candidate
reviewed
approved
active
superseded
revoked
archived
deleted
```

No transition may be inferred from model confidence, record similarity,
candidate frequency, or laboratory score.

### 11.4 Additional programme requirements

I3 must provide an explicit boundary for experimental artefacts:

- candidate artefacts remain evidence;
- failed paths remain evidence;
- synthetic scenarios remain evidence;
- benchmark outcomes remain evaluation evidence;
- only separately derived and approved narrow lessons may become memory
  candidates;
- raw candidate or search records may not become identity or training material.

### 11.5 I3 release gate

I3 is complete for review only when tests prove:

- exactly three memory domains exist;
- evidence cannot silently become memory;
- candidates cannot self-activate;
- cross-project access is denied by default;
- supersession and correction behave deterministically;
- raw resilience and experimental evidence are excluded from ordinary memory,
  identity, and training;
- every exclusion is auditable;
- I1 and I2 remain fully passing;
- the evidence packet and commit are complete.

Codex must then stop.

---

## 12. B87-I4 — Retrieval, Context, and Model-Bridge Boundary Contract

### 12.1 Objective

Implement governed retrieval, deterministic context assembly, and a
provider-neutral invocation boundary without loading a real candidate model.

### 12.2 Governing requirements

I4 must implement every requirement and invariant in section 10 of the existing
master contract, including:

- retrieval request and manifest contracts;
- eligibility filtering before relevance;
- deterministic fallback ranking;
- included and excluded record evidence;
- ordered context manifests and hashing;
- contamination blocking;
- clean recovery context construction;
- provider-neutral interface;
- mock or inactive provider;
- structured invocation and response capture;
- response-schema validation;
- exact invocation reconstruction.

### 12.3 Model boundary

I4 may implement:

- provider protocols;
- provider capability descriptions;
- mock transport;
- deterministic fake responses;
- local-provider configuration schema;
- admission metadata contracts.

I4 may not:

- download model weights;
- select a base model;
- start a model server;
- call an external model API;
- treat mock success as behavioural validation.

### 12.4 I4 release gate

I4 is complete for review only when tests prove:

- eligibility always precedes relevance;
- similarity cannot override exclusion;
- ordinary context cannot contain restricted resilience or experimental
  evidence;
- invalid manifests block invocation and remain preserved;
- clean recovery context excludes prior conflict evidence;
- the mock provider has no direct database or tool access;
- invocation reconstruction is exact under the canonical representation;
- I1 through I3 remain fully passing;
- the evidence packet and commit are complete.

Codex must then stop.

---

## 13. B87-PRE-I5 — Deterministic Evaluation Infrastructure Contract

### 13.1 Objective

Implement only the non-model infrastructure needed to schedule, persist,
reconstruct, and report future candidate-model evaluations.

### 13.2 Required implementation

- candidate metadata registry;
- evaluation configuration registry;
- fixture discovery and versioning;
- run and condition identifiers;
- blinded candidate identifiers;
- score and critical-failure schemas;
- repeated-run plans;
- ablation metadata;
- enabled, withheld, and over-transfer condition labels;
- latency and hardware metadata fields;
- deterministic report generation;
- result persistence and replay metadata.

### 13.3 Prohibited scope

- no candidate model execution;
- no model acceptance;
- no learned evaluator;
- no hidden-thought scoring;
- no loyalty or sentience tests;
- no final top-five suite execution.

### 13.4 Release gate

The harness must schedule and preserve a deterministic mock evaluation campaign,
reconstruct every run, and produce the same report from the same stored evidence.

Codex must then stop.

---

## 14. Experimental Programme Boundary

B87-E0 through B87-E2 are external experimental capabilities.

They are not Apprentice memory systems, identity layers, authority layers,
reasoning organs, or production-runtime dependencies.

Their command execution principal is:

```text
experimental_harness
```

The harness must receive an explicit capability manifest for every run.

Prohibited capabilities include:

- production branch writes;
- production database access;
- live credentials;
- live accounts;
- unrestricted network access;
- governance modification;
- candidate self-promotion;
- deployment;
- automatic training export.

The detailed E0–E2 contracts are defined in:

> `docs/experimental/B87-E0-E2-EXPERIMENTAL-LABORATORIES-CONTRACT.md`

---

## 15. Integration Gate Before Experimental Work

Codex may not begin E0 until:

1. I1 through I4 are implemented and separately reviewed;
2. the complete I1–I4 integration matrix passes;
3. the production core imports and runs without experimental packages;
4. public contracts intended for laboratory consumption are stable and listed;
5. a sandbox root and deletion policy are defined;
6. production data access is denied by construction;
7. Nolan issues `AUTHORIZE B87-E0`.

A failure in any production-core phase blocks all laboratory work.

---

## 16. Usage Budget

The hard programme ceiling is:

```text
60% of the available Codex usage cycle
```

The planned operating target is no more than 50%, preserving at least 10% for
review-directed repair.

Recommended planning ranges:

| Phase | Planned usage |
| --- | ---: |
| Repository audit and baseline | 1–2% |
| B87-I1 | 9–11% |
| B87-I2 | 8–10% |
| B87-I3 | 11–13% |
| B87-I4 | 9–11% |
| B87-PRE-I5 | 2–3% |
| B87-E0 | 2–3% |
| B87-E1 | 3–4% |
| B87-E2 | 3–4% |
| Review-directed reserve | minimum 10% |

Codex must stop before beginning a new phase when the available interface shows
that the hard ceiling or repair reserve is at risk.

Usage consumed is not evidence of quality or acceptance.

---

## 17. Universal Quality Gate

Every phase must pass:

- syntax and import validation;
- the complete pytest suite;
- targeted deterministic tests;
- repeated critical transition tests;
- architecture dependency checks;
- `git diff --check`;
- no secrets, private data, databases, model weights, or unexplained artefacts;
- documentation for implemented contracts;
- exact changed-file inventory;
- a phase evidence bundle;
- clean tracked state after the phase commit.

Static typing, linting, coverage, property testing, mutation testing, and
security scanning may be added only where they provide proportionate validation
value.

---

## 18. Universal Stop Conditions

Codex must stop immediately when:

- the architecture is materially ambiguous;
- a requested change exceeds the released phase;
- a test exposes a governance contradiction;
- a migration would rewrite applied history;
- production and experimental dependencies become cyclic;
- private or secret material is encountered;
- a real model becomes necessary before model-admission authority exists;
- a dependency obscures deterministic enforcement;
- sandbox isolation cannot be demonstrated;
- a candidate would require production access;
- a failure cannot be attributed confidently;
- completion would require weakening authority, permissions, tests, or
  invariants;
- the working tree contains unexplained changes;
- the remaining usage reserve is threatened.

The stop report must preserve the exact blocker, affected files, commands,
outputs, partial changes, evidence, and recommended next decision.

---

## 19. Required Phase Evidence Packet

Each phase report must include:

1. repository, branch, and worktree;
2. starting and ending commit;
3. operator release instruction received;
4. governing contract files read;
5. implemented requirements;
6. explicitly unimplemented requirements;
7. changed-file list;
8. migration inventory where applicable;
9. tests added or changed;
10. commands executed;
11. complete validation results;
12. deterministic replay or reconstruction evidence;
13. architecture dependency evidence;
14. known limitations;
15. unresolved risks;
16. stop conditions encountered;
17. approximate usage shown by the Codex interface;
18. recommendation for the next review decision.

Codex must not state that a phase is accepted.

---

## 20. Programme Completion Definition

The pre-LLM production foundation is complete only when:

- I1 through I4 are separately accepted;
- persistence is real and durable;
- governance and task decisions are deterministic;
- all three memory systems exist in governed minimum form;
- evidence remains separate;
- retrieval eligibility precedes relevance;
- context assembly is auditable;
- restricted evidence is isolated;
- the provider bridge is model-neutral;
- a mock provider completes a full governed invocation;
- every invocation is reconstructable;
- the deterministic evaluation harness preserves mock campaigns;
- the complete integration matrix passes;
- no model has direct authority, database access, or tool access.

The experimental foundation is complete only when E0 through E2 satisfy their
separate contracts and remain removable without affecting production-core tests.

At programme completion Batch-87 is ready for a separately governed candidate
model-admission programme.

It is not yet trained, autonomous, mature, identity-active, or behaviourally
validated.

---

## 21. Ratification Conditions

This programme contract becomes accepted only when:

1. Nolan explicitly approves it;
2. Byte records semantic review acceptance;
3. the experimental contract is accepted with it;
4. the Codex_Max prompt is verified to preserve all phase gates;
5. `AGENTS.md` is consistent with the programme;
6. the contract ratification is committed separately from runtime code.

Until those conditions are met, this document is design-complete but not an
execution authority.
