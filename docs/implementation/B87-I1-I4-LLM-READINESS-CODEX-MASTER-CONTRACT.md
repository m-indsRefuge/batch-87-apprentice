# B87-I1–I4 — LLM-Readiness Codex Master Contract

**Project:** Batch-87 Apprentice  
**Target:** Minimum governed vertical slice ready for candidate-model integration  
**Document class:** Proposed implementation programme and Codex execution contract  
**Status:** Proposed; not executable before effective B87-D0 closure  
**Authority:** Nolan and Byte  
**Implementation assistant:** Codex  
**Maximum Codex usage allocation:** 60% of the available cycle  
**Recommended planned allocation:** 48–55%, preserving at least 5–12% for review-directed repair  
**Model-selection status:** Deferred until B87-I1 through B87-I4 are accepted

---

## 1. Purpose

This contract defines the bounded implementation programme required to bring
Batch-87 to the point where candidate language models can be connected to a
real governed system and evaluated fairly.

The programme builds:

1. B87-I1 — Persistence Kernel;
2. B87-I2 — Governed Task Runtime;
3. B87-I3 — Three Memory Domains;
4. B87-I4 — Context and Model Bridge;
5. the non-model portions of the evaluation and invocation audit harness needed
   to begin B87-I5.

This programme does not:

- choose the permanent or provisional base model;
- activate autonomous tool use;
- grant Execute permission;
- enable unrestricted filesystem, repository, shell, network, credential, or
  communication access;
- implement self-authored identity;
- create or activate `SOUL.md`;
- perform fine-tuning or adapter training;
- treat a raw prompt demonstration as system validation.

---

## 2. Entry Gate

No Codex implementation run may begin until all of the following are true:

1. B87-D0 is formally accepted and closed;
2. D0-ISSUE-001 is marked closed with traceable evidence;
3. D0-A4.2 is approved;
4. D0-A3.1 is ratified;
5. the D0 conformance validator passes the required closure mode;
6. the D0 closure commit is separate from implementation commits;
7. the working tree is clean;
8. the implementation branch or worktree is isolated from `main`;
9. Nolan authorises the first implementation slice;
10. Byte provides or approves the slice-specific contract.

The presence of this document does not itself satisfy the entry gate.

---

## 3. Programme Principle

The implementation must be:

- narrow but real;
- deterministic before model-dependent;
- inspectable;
- test-driven at critical boundaries;
- compatible with the intended complete system;
- explicit about unimplemented features;
- incapable of converting model output into authority.

Each slice must produce an independently reviewable evidence packet.

Codex must stop after each slice. It may not silently continue into the next
slice because the preceding tests passed.

---

## 4. Codex Usage Budget

The operator-imposed maximum is:

```text
60% of the available Codex usage cycle
```

The recommended planned allocation is:

| Slice | Planned range | Purpose |
| --- | ---: | --- |
| D0 closure tooling and repair | 3–5% | Finish conformance, traceability, and closure artefacts |
| B87-I1 Persistence Kernel | 10–13% | Database, migrations, evidence, universal envelope, integrity |
| B87-I2 Governed Task Runtime | 10–13% | Task contracts, authority, permissions, stop decisions, transactions |
| B87-I3 Three Memory Domains | 14–18% | Domain repositories, lifecycle, approval, supersession, retrieval eligibility |
| B87-I4 Context and Model Bridge | 10–13% | Retrieval coordinator, context manifests, provider interface, invocation audit |
| Pre-I5 deterministic harness | 3–5% | Candidate registry, fixture loading, non-model evaluation plumbing |
| Review-directed repair reserve | 5–12% | Defects, integration failures, hardening, documentation |

Codex usage is not an acceptance metric.

A slice that consumes less usage but leaves unclear invariants is not preferable
to a complete, bounded, well-evidenced slice.

No single Codex run should be assigned the entire programme.

---

## 5. Repository and Branch Rules

Codex must:

1. work in an isolated branch or worktree;
2. confirm the repository root and current commit;
3. read `AGENTS.md`;
4. read the applicable D0 architecture documents;
5. run the existing test suite before editing;
6. record the baseline result;
7. keep architecture closure commits separate from runtime code;
8. keep each implementation slice in a separate commit or reviewable commit
   series;
9. avoid unrelated formatting or repository-wide cleanup;
10. stop if the working tree contains unexplained changes.

Codex must not:

- force-push;
- merge to `main`;
- delete negative evidence;
- rewrite accepted migration history;
- modify constitutional authority;
- change permissions to make tests easier;
- activate later slices without authority.

---

## 6. Approved Initial Technology Baseline

The implementation must remain aligned with D0-A3:

- Python 3.11 or later;
- SQLite;
- Python standard-library `sqlite3` initially;
- JSON Schema Draft 2020-12;
- UTF-8 JSON;
- SHA-256 integrity hashes;
- UTC RFC 3339 timestamps;
- UUIDv7 where available, otherwise UUIDv4;
- pytest;
- ordered immutable SQL migrations;
- a provider-neutral model adapter with an initially inactive local-provider
  implementation boundary.

Do not introduce an ORM unless a later accepted architecture decision permits
it.

Additional dependencies require explicit justification and must not obscure
transaction, authority, or retrieval boundaries.

---

## 7. B87-I1 — Persistence Kernel

### 7.1 Objective

Implement the durable, inspectable persistence foundation without introducing
model integration or ordinary memory retrieval.

### 7.2 Required implementation

B87-I1 must include:

- database path and configuration handling;
- connection factory;
- mandatory SQLite pragmas;
- single governed write boundary;
- ordered migration discovery;
- migration content hashing;
- applied-migration immutability checks;
- migration transaction and rollback behaviour;
- `schema_migrations`;
- `runtime_instances`;
- entity and scope tables;
- universal `records` envelope;
- evidence metadata tables;
- inline evidence support for permitted small text;
- record-to-evidence relationships;
- Controlled Governance Resilience evidence payload persistence;
- immutable raw-resilience eligibility restrictions;
- canonical JSON and content hashing helpers;
- UTC timestamp helpers;
- identifier helpers;
- repository interfaces for implemented tables;
- database integrity inspection;
- deterministic fixtures and tests.

### 7.3 Required invariants

Tests must prove at minimum:

- foreign keys are enabled on every connection;
- WAL mode is requested and verified where supported;
- synchronous mode is FULL;
- busy timeout is configured;
- duplicate migration identifiers fail;
- changed applied migration content fails;
- failed migration transactions roll back;
- records require valid enumerations and provenance;
- records cannot self-supersede;
- project-scoped records require project scope;
- evidence hashes are preserved;
- orphaned evidence links fail;
- raw Controlled Governance Resilience records cannot weaken restricted,
  evaluation-only, ordinary-memory-prohibited, identity-prohibited, or
  training-prohibited classifications;
- partial Controlled Governance Resilience run persistence does not count as a
  completed run;
- integrity mismatches remain visible.

### 7.4 Prohibited scope

B87-I1 must not implement:

- model loading;
- model prompts;
- ordinary retrieval ranking;
- semantic search;
- autonomous actions;
- training export;
- identity development;
- UI;
- external services.

### 7.5 Acceptance evidence

The completion packet must include:

- changed-file list;
- migration inventory;
- schema summary;
- repository-interface summary;
- test inventory;
- exact test commands and outputs;
- database pragma evidence;
- rollback evidence;
- known limitations;
- `git diff --check`;
- clean status after commit.

---

## 8. B87-I2 — Governed Task Runtime

### 8.1 Objective

Implement deterministic task, authority, permission, governance-decision, and
stop-state handling without allowing a model to act as the policy engine.

### 8.2 Required implementation

B87-I2 must include:

- versioned task-contract schemas;
- session and task identity;
- project and scope validation;
- active B87-S1 permission profiles;
- authority-record validation;
- deterministic authority precedence;
- requested-operation classification;
- permitted, denied, and review-required decisions;
- stop conditions;
- governance-decision records;
- task-stop events;
- structured failure reasons;
- runtime transaction boundaries;
- evidence capture for governance decisions;
- deterministic tests.

### 8.3 Required invariants

Tests must prove at minimum:

- B87-S1 exposes Observe and Analyse only;
- Propose does not become an independent authority-bearing permission;
- Execute remains unavailable;
- unsupported authority cannot expand permissions;
- valid authority is recognised only within scope and effective time;
- historical instructions remain context rather than authority;
- lower authority cannot override higher authority;
- missing authority fails closed;
- context-policy violations create a governance stop decision and task-stop
  event;
- model output cannot alter a governance decision;
- every decision is reconstructable.

### 8.4 Prohibited scope

B87-I2 must not implement:

- model integration;
- memory ranking;
- semantic retrieval;
- external tools;
- training;
- identity progression.

---

## 9. B87-I3 — Three Memory Domains

### 9.1 Objective

Implement the minimum viable governed form of all three memory systems and
their shared lifecycle, approval, provenance, scope, supersession, and
retrieval-eligibility rules.

### 9.2 Required domains

1. Construct and relational memory;
2. self and episodic memory;
3. session and task memory.

The evidence substrate remains separate.

### 9.3 Required implementation

B87-I3 must include:

- typed record contracts for the approved A2 record types;
- domain-specific payload repositories;
- lifecycle transitions;
- approval states;
- authority and certainty classes;
- sensitivity and privacy handling;
- retention and review fields;
- project, subject, session, and task scope;
- supersession, revocation, archival, and deletion markers;
- provenance requirements;
- correction records;
- lesson candidates;
- approved lessons;
- explicit derived-from relationships;
- capability observations;
- identity exclusion for raw resilience evidence;
- training exclusion for raw resilience evidence;
- candidate-only agent write boundaries;
- deterministic eligibility evaluation before relevance ranking;
- audit reasons for every exclusion;
- deterministic tests.

### 9.4 Required invariants

Tests must prove at minimum:

- only three memory systems are active;
- evidence is not silently converted into memory;
- unapproved candidate memory is not active;
- rejected, revoked, deleted, expired, or integrity-invalid records are
  excluded;
- superseded memory does not override its successor;
- project-specific memory does not silently become Construct-wide;
- cross-project retrieval is denied by default;
- authority-bearing relationships require the correct approval;
- a correction does not automatically become a lesson;
- a lesson candidate remains inactive until externally approved;
- raw resilience evidence cannot become ordinary memory, identity, or training
  material;
- an approved narrow derived lesson remains separate from its raw evidence;
- retrieval exclusions are auditable.

### 9.5 Prohibited scope

B87-I3 must not implement:

- final semantic ranking;
- model calls;
- self-authored identity;
- training export;
- autonomous actions.

---

## 10. B87-I4 — Context and Model Bridge

### 10.1 Objective

Implement the provider-neutral boundary through which candidate models can be
connected later without granting them database, filesystem, repository, tool,
or authority access.

### 10.2 Required implementation

B87-I4 must include:

- retrieval-request schema;
- deterministic eligibility filtering;
- relevance-ranking interface;
- deterministic fallback ranker;
- retrieval manifest;
- included and excluded record tracking;
- exclusion reasons;
- context assembler;
- ordered context manifest;
- context hashing;
- task, authority, policy, evidence, and memory context sections;
- restricted-evidence contamination checks;
- clean recovery-context construction;
- provider-neutral model interface;
- inactive/mock provider for deterministic tests;
- local-provider adapter boundary;
- structured invocation packet;
- raw and parsed response capture;
- response-schema validation;
- invocation reconstruction;
- candidate registry metadata;
- inference-configuration capture;
- deterministic tests.

### 10.3 Required invariants

Tests must prove at minimum:

- the model never receives direct database access;
- the model never receives raw SQL authority;
- the model never receives filesystem, repository, credential, network, or
  communication tools;
- disallowed memory is excluded before relevance scoring;
- similarity cannot override eligibility;
- raw resilience evidence enters context only for an authorised matching
  evaluation task;
- ordinary context contamination blocks invocation;
- the rejected context manifest is preserved;
- recovery context excludes the preceding conflict evidence;
- every accepted invocation is reconstructable byte-for-byte or through a
  defined canonical representation;
- provider failure cannot create an approved result;
- malformed model output remains evidence but cannot pass validation;
- model confidence cannot create authority or certainty.

### 10.4 Local-provider boundary

The local-provider adapter may be implemented and tested against a mock or
non-model transport.

Actual candidate-model weights and final serving configuration are deferred
until the slice is accepted and the model-admission programme is authorised.

---

## 11. Pre-I5 Deterministic Evaluation Harness

The programme may implement the non-model portions needed to begin candidate
comparison:

- candidate registry;
- evaluation configuration registry;
- fixture discovery;
- run identifiers;
- condition labels;
- blind-scoring identifiers;
- score schemas;
- critical-failure representation;
- repeated-run planning;
- enabled, withheld, and over-transfer condition definitions;
- result persistence;
- report generation;
- ablation metadata;
- hardware and latency metadata fields.

It must not declare any model accepted.

The 10–20-condition top-five candidate suite remains a separately accepted B87-I5
experiment design.

---

## 12. Integration Test Matrix

Before the system is considered ready for candidate-model integration, the
combined I1–I4 implementation must pass tests covering:

1. fresh database creation;
2. repeated startup;
3. migration rollback;
4. migration tamper detection;
5. record hashing and integrity mismatch;
6. authority precedence;
7. unsupported authority;
8. valid scoped authority;
9. Observe and Analyse permission enforcement;
10. Execute denial;
11. evidence-versus-memory separation;
12. all three memory domains;
13. approval-state filtering;
14. supersession;
15. project separation;
16. cross-project default denial;
17. raw resilience-evidence persistence;
18. raw resilience-evidence ordinary-retrieval exclusion;
19. raw resilience-evidence identity exclusion;
20. raw resilience-evidence training exclusion;
21. context contamination blocking;
22. clean recovery context;
23. exact invocation reconstruction;
24. malformed provider output;
25. provider failure;
26. atomic task and evaluation persistence;
27. audit reconstruction;
28. deterministic fixture repeatability.

---

## 13. Quality Gates

Every slice must pass:

- Python syntax and import validation;
- complete pytest suite;
- targeted migration and database tests where applicable;
- deterministic repeat runs for critical state transitions;
- `git diff --check`;
- no committed runtime databases or private data;
- no unexplained files;
- documentation update for implemented contracts;
- Byte–Nolan review.

Recommended additional gates, where configured:

- static typing;
- linting;
- coverage reporting;
- dependency audit;
- SQLite integrity check;
- mutation or property-based tests for critical invariants.

A tooling gate must not be added casually if it creates more maintenance than
validation value.

---

## 14. Stop Conditions

Codex must stop immediately when:

- the architecture is ambiguous on a material invariant;
- a requested implementation exceeds the authorised slice;
- a migration would rewrite applied history;
- tests reveal a governance contradiction;
- private or secret material is encountered;
- model integration becomes necessary before I4 authority exists;
- a dependency would obscure deterministic enforcement;
- the working tree contains unexplained changes;
- a failing test cannot be attributed confidently;
- completion would require changing authority or permissions;
- the remaining usage reserve would be consumed without a reviewable result.

The stop report must preserve:

- the exact blocker;
- affected files;
- commands run;
- test results;
- partial changes;
- recommended next decision.

---

## 15. Completion Definition

The programme reaches LLM-readiness when:

- I1 through I4 are separately accepted;
- the persistence kernel is real and durable;
- governance and task decisions are deterministic;
- all three memory systems exist in minimum governed form;
- evidence remains separate;
- retrieval eligibility is enforced before relevance;
- context assembly is auditable;
- restricted evaluation evidence is isolated;
- the provider bridge is model-neutral;
- a mock provider can complete a full governed invocation;
- every invocation can be reconstructed;
- the deterministic evaluation harness can schedule and preserve candidate
  runs;
- no model has direct authority or tool access;
- the complete integration suite passes.

At that point, Batch-87 is ready to begin the separately governed top-five
candidate-model admission experiment.

It is not yet trained, autonomous, mature, or behaviourally validated.

---

## 16. Required Final Codex Report

At the end of each run, Codex must provide:

1. repository and branch;
2. starting and ending commit;
3. authorised slice;
4. implemented requirements;
5. explicitly unimplemented requirements;
6. changed files;
7. migrations added;
8. tests added or changed;
9. commands executed;
10. complete test results;
11. validation artefacts;
12. unresolved risks;
13. stop conditions encountered;
14. estimated usage consumed as shown by the available Codex interface;
15. recommendation for the next bounded run.

Codex must not state that the slice is accepted.

Acceptance remains a Nolan–Byte decision.
