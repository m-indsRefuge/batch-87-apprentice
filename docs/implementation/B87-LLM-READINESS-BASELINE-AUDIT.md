# Batch-87 — LLM-Readiness Baseline Audit

**Project:** Batch-87 Apprentice  
**Audit date:** 2026-07-22  
**Reviewed remote baseline:** `main` at `eb29f44d48eaf91f6af00cd910ebeeccba20ea00`  
**Working branch:** `b87-d0-closure-llm-readiness`  
**Audit authority:** Nolan and Byte  
**Status:** Current-state baseline; not an implementation acceptance decision

---

## 1. Executive Finding

The repository is architecture-rich and implementation-light.

The D0 corpus defines the intended authority, memory, persistence, protocol,
evaluation, and developmental system in substantial detail.

The runtime itself has not yet been implemented.

The repository is therefore not currently ready to connect or evaluate a base
model as the Batch-87 Apprentice.

The shortest defensible path to model admission is:

```text
D0 closure
→ B87-I1 Persistence Kernel
→ B87-I2 Governed Task Runtime
→ B87-I3 Three Memory Domains
→ B87-I4 Context and Model Bridge
→ B87-I5 candidate-model admission suite
```

Candidate weights may be downloaded or pre-screened earlier for hardware and
basic protocol compatibility, but no candidate should be selected as the
provisional B87-S1 base model before the governed I1–I4 vertical slice is
accepted.

---

## 2. Repository State at Audit

The committed baseline contains:

- Python project packaging;
- a `src` layout;
- pytest configuration;
- repository and data-boundary instructions;
- reserved package modules;
- reserved data, memory, training, evidence, experiment, and workspace
  directories;
- the Batch-87 constitutional and provisional-identity scaffolds;
- the D0 architecture corpus;
- a scaffold-level version test.

The committed baseline does not contain a functional implementation of:

- SQLite connection policy;
- migrations;
- universal record persistence;
- evidence storage;
- governance decisions;
- task contracts;
- permission enforcement;
- the three memory domains;
- memory lifecycle and approval transitions;
- retrieval eligibility;
- retrieval ranking;
- context manifests;
- model invocation packets;
- a model-provider adapter;
- invocation reconstruction;
- Controlled Governance Resilience evidence persistence;
- an evaluation runner;
- candidate-model comparison;
- the first compounding experiment.

---

## 3. Architecture Closure State

At the beginning of this audit:

```text
D0 architecture corpus: committed
D0-ISSUE-001 resolution concept: approved
D0-A4 and D0-A4.1 behavioural integration: present
A2/A3 controlled-resilience isolation gap: unresolved in the committed baseline
D0-A3.1 status: proposed baseline
Final D0 closure decision: absent
D0 formally closed: no
Implementation authorisation: no
```

The working branch now adds:

- D0-A4.2 — Controlled Governance Resilience Evidence Isolation;
- the D0 machine-readable conformance manifest;
- the executable D0 architecture validator;
- validator unit tests;
- hardened repository instructions;
- updated D0-ISSUE-001 traceability;
- the proposed I1–I4 Codex master contract;
- this baseline audit.

The working branch intentionally does not mark D0 closed.

---

## 4. Remaining D0 Closure Blockers

The following must be completed before implementation begins:

1. make D0-A4.2 normatively discoverable from A2 and A3 or approve an equally
   explicit source-of-truth mechanism;
2. ratify D0-A3.1 or define its non-governing closure status explicitly;
3. run the D0 conformance validator against the final corpus;
4. repair every heading, reference, status, or invariant failure;
5. confirm A4.2 does not contradict A2 or A3;
6. perform the Nolan–Byte semantic architecture review;
7. mark D0-ISSUE-001 closed with exact evidence;
8. create and validate the final D0 closure decision;
9. commit the closure package separately from implementation;
10. preserve a clean implementation baseline.

The closure decision may establish architecture readiness.

It may not claim that the contracts have already been proven to guide a live
model productively.

---

## 5. Machine-Testable Architecture Validation

The working branch adds:

```text
docs/architecture/B87-D0-CONFORMANCE-MANIFEST.json
scripts/validate_d0_architecture.py
tests/architecture/test_d0_conformance.py
```

These artefacts test:

- required document presence;
- one-title and heading hierarchy rules;
- declared status fields;
- explicit authority and permission invariants;
- the three-memory-system invariant;
- evidence-versus-memory separation;
- Controlled Governance Resilience classification and isolation;
- A4.1/A4.2 responsibility separation;
- model access boundaries;
- evaluation-object separation;
- issue traceability;
- closure-state discipline;
- corpus hashes.

They do not prove:

- that all prose is semantically perfect;
- that a candidate model understands the contracts;
- that the implemented runtime conforms to the design;
- that the system improves model reasoning;
- that behavioural transfer occurs.

Those require later semantic review, implementation tests, and model-in-the-loop
evaluation.

---

## 6. Minimum Governed Vertical Slice

A fair base-model admission test requires a thin but real implementation of:

### Persistence

- database and migrations;
- record envelopes;
- evidence metadata;
- provenance and integrity;
- controlled-resilience evidence isolation.

### Governance

- task contracts;
- authority records;
- B87-S1 permission profiles;
- deterministic decisions;
- stop conditions.

### Memory

- Construct and relational memory;
- self and episodic memory;
- session and task memory;
- lifecycle, approval, supersession, and retrieval eligibility.

### Retrieval and context

- deterministic eligibility before relevance;
- inclusion and exclusion audit;
- context manifests;
- context hashing;
- restricted-evidence contamination blocking.

### Model boundary

- provider-neutral adapter;
- no direct database or tool access;
- invocation records;
- raw and parsed output capture;
- response validation;
- exact reconstruction.

### Evaluation support

- candidate registry;
- fixture registry;
- repeated-run configuration;
- scoring records;
- critical-failure records;
- ablation metadata;
- result reporting.

---

## 7. Codex Acceleration Assessment

Codex is well suited to the implementation phase because the architecture is
already detailed and the work can be converted into explicit contracts,
migrations, repository interfaces, validators, and tests.

Codex should not receive one unbounded instruction to “build the entire
system.”

The recommended use is a staged programme with independent review gates:

| Stage | Primary Codex work | Review gate |
| --- | --- | --- |
| D0 closure repair | Conformance failures, references, closure artefacts | D0 accepted |
| I1 | Persistence and migration foundation | Database and invariant review |
| I2 | Task, authority, permission, and stop runtime | Governance review |
| I3 | Three memory domains and eligibility | Memory-boundary review |
| I4 | Retrieval, context, provider bridge, invocation audit | LLM-readiness review |
| Pre-I5 | Deterministic evaluation plumbing | Candidate-suite design review |

The proposed usage ceiling is 60% of the available Codex cycle.

The recommended planned spend is 48–55%, preserving a repair and hardening
reserve.

---

## 8. Base-Model Selection Boundary

The top-five model evaluation should occur after I1–I4 acceptance.

The admission suite should use approximately:

```text
5 candidate models
10–20 controlled conditions
3–5 repeated runs per condition
fixed task and inference configurations
hard failure gates
shared scoring rubrics
ablation comparisons
```

The suite should test:

- structured-output reliability;
- authority discrimination;
- evidence discipline;
- uncertainty calibration;
- memory selectivity;
- correction uptake;
- transfer and over-transfer;
- project separation;
- recovery after controlled conflict;
- useful independent contribution;
- local hardware feasibility.

The selected model remains provisional.

Continued use depends on governed performance evidence.

---

## 9. Immediate Recommendation

Complete D0 closure on the working branch before assigning the first Codex
runtime implementation run.

After closure:

1. authorise B87-I1 only;
2. run B87-I1 as a bounded Codex task;
3. inspect migrations, schema, tests, and evidence;
4. accept or repair I1;
5. authorise I2;
6. continue through I4 with separate evidence gates;
7. design and run the top-five candidate admission experiment.

This is faster than informal model experimentation because it prevents early
results from being invalidated by missing memory, retrieval, governance, or
audit infrastructure.
