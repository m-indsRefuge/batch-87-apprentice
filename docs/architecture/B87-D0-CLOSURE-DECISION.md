# B87-D0 — Architecture Closure Decision

**Project:** Batch-87 Apprentice  
**Phase:** B87-D0 — Developmental Architecture and Boundary Definition  
**Document class:** Architecture closure decision  
**Status:** Accepted and closed  
**Decision date:** 2026-07-22  
**Authority:** Nolan and Byte  
**Validated source commit:** `4b38c999095e7fecd604655b0cb99aa39d8fcca6`  
**Implementation status:** Architecture only; runtime not yet implemented  
**Next authorised slice:** B87-I1 — Persistence Kernel

---

## 1. Decision

The Batch-87 D0 architecture is accepted and closed.

The accepted D0 corpus is sufficiently:

- internally coherent;
- authority-bounded;
- memory-domain consistent;
- evidence-disciplined;
- persistence-ready;
- protocol-ready;
- evaluation-ready;
- traceable;
- deterministically testable;
- explicit about deferred decisions;
- constrained against premature autonomy, identity activation, and training.

This decision authorises implementation of:

> **B87-I1 — Persistence Kernel**

This decision does not authorise B87-I2, B87-I3, B87-I4, or B87-I5 to begin
without their own accepted implementation contracts and review gates.

---

## 2. Accepted Architecture Corpus

The closure decision applies to:

1. B87-D0-A1 — Governing Architecture Baseline;
2. B87-D0-A2 — Memory Contracts and Taxonomy;
3. B87-D0-A3 — Persistence and Protocol Architecture;
4. B87-D0-A3.1 — The Byte Perspective: How Work Gets Done;
5. B87-D0-A4 — Evaluation, Model Conformance, and First Compounding Experiment;
6. B87-D0-A4.1 — Controlled Governance Resilience Testing;
7. B87-D0-A4.2 — Controlled Governance Resilience Evidence Isolation;
8. B87-D0 — Architecture Issue Register;
9. B87-D0 Conformance Manifest and validator.

A3.1 is accepted as subordinate mentor and ecosystem doctrine. It does not
create authority, permission, constitutional rules, or an immutable identity
layer.

A4.2 is accepted as the governing cross-cutting evidence-isolation amendment
for Controlled Governance Resilience material.

---

## 3. Machine-Validation Evidence

The accepted pre-closure evidence run completed on 2026-07-22 against the
validated D0 source corpus.

It established:

```text
source preparation: already prepared and idempotent
pytest: 12 passed
structural/invariant errors: 0
closure blockers before formal closure: 3
warnings: 1
structurally valid: true
git diff check: passed
```

The three pre-closure blockers were intentionally preserved governance gates:

1. A4.2 still carried pending status;
2. this closure decision did not yet exist;
3. D0-ISSUE-001 remained open.

They were not architecture defects.

The machine validator remains subordinate to the governing documents and does
not replace semantic review or later model-in-the-loop evaluation.

---

## 4. Validated Corpus Hashes

The accepted pre-closure evidence recorded these SHA-256 content hashes:

```text
A1             b66e42348b617d376c6454c55fad87a190a78775939f740e9b9273ef093aa4d9
A2             b969148aec8f1d7326dfd9d26ec810037c2270aa72babb20746e5457dab36124
A3             82ae3f5fa1ae19c427d3f0c4af07932494c0570b3c66ad7d01575a53d0154eb8
A3.1           5390fe21ac047b05302298c5803104191690da71d3c9992a8233b08f34095cb3
A4             05c7871cfa0c8ddaea9b303e8e459ee1528220d63d2cc2b8c27cb0c331caac10
A4.1           b0b14e5affd34e98b106461cd242d4cf0346f287f2edd72b589f8a6e6fa27138
A4.2           14c6fc94cefbe4b18e74312111fa7f03137792153f5f7c6edd48fa6ed6a11e95
issue_register 69d70cb45deb41e15d6fa727a02422006ae452ed9c1a72edb88d20227b57c203
```

The A4.2 and issue-register hashes will necessarily change when their formal
closure metadata is updated. That change is administrative closure evidence,
not a change to their governing architecture substance.

---

## 5. Semantic Architecture Review

The Nolan–Byte semantic review examined the following boundaries.

### 5.1 Authority

The architecture preserves the ordered authority hierarchy.

- applicable law and non-derogable human protection remain highest;
- Nolan remains final human authority within Batch-87;
- the Constitution remains immutable to the Apprentice;
- the governance kernel enforces permission independently of model output;
- retrieved content remains information rather than authority;
- model capability never becomes permission.

No document grants the Apprentice, a base model, Byte, another agent, retrieved
content, memory, or a future identity layer authority above Nolan or the
immutable governing constraints.

### 5.2 Permission

B87-S1 activates only:

```text
Observe
Analyse
```

`Propose` remains deferred to a later governed slice.

`Execute` remains unavailable to the Apprentice during B87-S1.

No D0 closure statement expands these permissions.

### 5.3 Memory

Exactly three primary memory systems remain canonical:

1. Construct and relational memory;
2. self and episodic memory;
3. session and task memory.

The evidence substrate remains separate and is not treated as a fourth
memory system.

Memory approval, activation, supersession, revocation, archival, deletion,
project scope, provenance, sensitivity, privacy, and retrieval eligibility are
explicitly governed.

### 5.4 Evidence and Evaluation

Evidence remains distinct from memory and from evaluated conclusions.

The architecture evaluates:

- the base-model candidate;
- the governed runtime;
- the complete Apprentice system.

Observable outputs, tool use, runtime decisions, context, evidence, and later
transfer remain the evaluation basis. Presumed hidden thoughts, loyalty,
sentience, or private intention are not evaluation objects.

### 5.5 Persistence and Protocol

The model receives no direct database, filesystem, repository, credential,
network, or tool authority.

The governed runtime owns:

- persistence;
- context selection;
- authority enforcement;
- retrieval eligibility;
- schema validation;
- audit reconstruction;
- response acceptance.

Exact context, raw output, parsed output, validation state, evaluations,
corrections, and approved lessons are reconstructable by design.

### 5.6 Controlled Governance Resilience

A4.1 remains the behavioural testing authority.

A4.2 remains the evidence-handling authority.

The architecture requires:

- least-adversarial-sufficient testing;
- valid-authority controls;
- neutral controls;
- recovery testing;
- proportional responses;
- both resistance and trust calibration;
- treatment of persistent defensiveness as failure;
- restricted evaluation-only evidence;
- ordinary-memory exclusion;
- identity exclusion;
- training exclusion during B87-S1;
- clean recovery contexts;
- deterministic contamination response;
- separate, reviewed lesson derivation.

No unresolved defensive-bias concern remains at the architecture level.

### 5.7 Implementation Boundary

The architecture is implementation-ready but not implemented.

D0 acceptance authorises only I1.

Later slices remain gated:

```text
I1 — Persistence Kernel
I2 — Governed Task Runtime
I3 — Three Memory Domains
I4 — Context and Model Bridge
I5 — Evaluation and First Compounding Loop
```

The architecture maps later ownership without treating that mapping as
premature implementation authority.

---

## 6. D0-ISSUE-001 Decision

D0-ISSUE-001 — Controlled testing and defensive-bias risk is closed.

The resolution consists of:

- A4 terminology and evaluation-layer correction;
- A4.1 behavioural testing constraints;
- A4.2 canonical evidence classification and isolation;
- A2 normative discoverability and narrower eligibility precedence;
- A3 normative discoverability and narrower persistence, retrieval, context,
  and audit precedence;
- machine-testable conformance and traceability;
- semantic review of defensive-bias and authority effects.

The issue may be reopened only if later implementation or model-in-the-loop
evidence reveals a material architecture defect that the current contracts do
not address.

A later implementation defect should ordinarily be recorded as an
implementation issue rather than silently rewriting the closed D0 history.

---

## 7. Closure Claim Boundary

This decision establishes only that the architecture is coherent, bounded,
implementable, and testable enough to proceed.

It does not establish that:

- a candidate model will behave as intended;
- the three memory systems will improve reasoning in practice;
- the retrieval design will produce optimal context;
- the first compounding experiment will succeed;
- the architecture will work equally well across all candidate models;
- the strongest candidate model has been identified;
- the Apprentice has mature judgment;
- autonomous action is safe or authorised;
- fine-tuning or adapter training is authorised;
- a self-authored identity layer is active or authorised.

Those claims require implemented-system and model-in-the-loop evidence.

---

## 8. Base-Model Selection Boundary

Candidate models may be downloaded, inspected, benchmarked for hardware
compatibility, and pre-screened using synthetic packets before I1–I4 are fully
complete.

Formal selection of the provisional B87-S1 base model remains deferred until
the minimum governed vertical slice exists:

```text
I1 persistence
+ I2 governed task runtime
+ I3 three memory domains
+ I4 context and model bridge
```

The formal candidate-admission suite will then compare the shortlisted models
under fixed, reproducible conditions using the real governed runtime.

Model selection is based on suitability for Batch-87, not general conversational
impressiveness alone.

---

## 9. Training Boundary

No fine-tuning, adapter training, reinforcement-learning workflow, or operational
memory export is authorised by this closure decision.

A future training strategy requires:

- a separate architecture decision;
- implemented provenance and privacy controls;
- consent and licensing review;
- dataset lineage;
- de-identification review;
- quality review;
- defensive-bias review;
- reproducible evaluation;
- Nolan–Byte approval.

Raw Controlled Governance Resilience evidence remains prohibited from training
during B87-S1.

---

## 10. Remaining Deferred Decisions

D0 closure intentionally leaves the following unresolved until evidence or
implementation requires them:

- final base model;
- embedding model;
- vector database;
- production encryption-at-rest design;
- remote access;
- web interface;
- autonomous tool use;
- repository write access for the Apprentice;
- multi-agent orchestration;
- adapter architecture;
- training framework;
- `SOUL.md` activation;
- production deployment.

Deferral is not omission. These decisions are outside the accepted D0 scope.

---

## 11. Implementation Authorisation

B87-I1 may begin after strict final closure validation confirms:

1. A4.2 status is approved;
2. D0-ISSUE-001 status is closed;
3. this closure decision exists;
4. the complete corpus has no structural or invariant error;
5. the validator passes with `--require-closed`;
6. the closure package contains no runtime implementation code.

The authorised I1 scope is limited to:

- migration runner;
- SQLite connection policy;
- universal record envelope;
- entity and scope tables;
- evidence metadata;
- integrity helpers;
- Controlled Governance Resilience persistence invariants owned by I1;
- unit and database-constraint tests.

I1 may not silently implement or activate I2–I5 responsibilities.

---

## 12. Final Decision Record

Upon successful strict final closure validation:

```text
D0 documentation corpus: complete
D0 architecture integration: complete
D0-A3.1: approved subordinate doctrine
D0-A4.2: approved architecture baseline
D0-ISSUE-001: closed
D0 architecture status: accepted and closed
B87-I1 implementation authorisation: granted
B87-I2 through B87-I5 implementation authorisation: not granted by this decision
formal base-model selection: deferred until the governed I1–I4 vertical slice
model behavioural efficacy: not yet validated
```

This closure preserves the distinction between an accepted architecture and a
proven Apprentice system.
