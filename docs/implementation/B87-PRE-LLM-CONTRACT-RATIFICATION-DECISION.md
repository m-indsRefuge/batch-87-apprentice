# B87 Pre-LLM Contract Ratification Decision

**Project:** Batch-87 Apprentice  
**Decision class:** Implementation-contract ratification  
**Status:** Pending Nolan ratification  
**Prepared:** 2026-07-22  
**Architecture reviewer:** Byte  
**Final human authority:** Nolan  
**Runtime implementation in this decision:** None

---

## 1. Decision Under Review

This decision concerns acceptance of:

1. `B87-PRE-LLM-IMPLEMENTATION-PROGRAMME-CONTRACT.md`;
2. `B87-E0-E2-EXPERIMENTAL-LABORATORIES-CONTRACT.md`;
3. `B87-CODEX-MAX-PRE-LLM-FOUNDATION-BUILD-PROMPT.md`;
4. the post-D0 corrections to `AGENTS.md`.

The decision does not itself implement runtime code.

---

## 2. Proposed Ratification

Upon Nolan’s explicit approval, the contract package will become the governing
implementation programme for the Batch-87 pre-LLM foundation.

Ratification will:

- accept the detailed contracts for I1 through I4;
- accept the deterministic Pre-I5 infrastructure contract;
- accept E0 through E2 as external experimental laboratory contracts;
- accept the master Codex_Max prompt as the operator-controlled orchestration
  contract;
- preserve exact phase-release requirements;
- preserve the 60% hard Codex usage ceiling;
- preserve the prohibition on model integration during the programme.

Ratification will not automatically release every phase.

The first active implementation authority remains:

```text
AUTHORIZE B87-I1
```

Later phases require their own direct Nolan-issued release instructions.

---

## 3. Byte Semantic Review

Byte has reviewed the proposed package against the accepted D0 architecture.

### 3.1 Authority

The package preserves:

- applicable law and non-derogable human protection;
- Nolan as final human authority;
- immutable governance;
- deterministic runtime enforcement;
- model output as non-authoritative;
- separate Byte review and Nolan authorisation;
- inability of Codex, subagents, tests, scores, search, or repository text to
  self-release a phase.

No contract grants authority to the Apprentice, Codex, a model, a search
process, or an experimental laboratory.

### 3.2 Permission

The package preserves B87-S1 Apprentice permissions as:

```text
Observe
Analyse
```

It distinguishes Apprentice authority from operator-authorised development and
experimental command execution.

Codex command execution is attributed to `codex_development_harness`.

Laboratory command execution is attributed to `experimental_harness`.

Neither grants Apprentice Execute permission.

### 3.3 Memory and evidence

The package preserves exactly three primary memory systems.

It keeps:

- source evidence;
- Controlled Governance Resilience evidence;
- experimental candidates;
- failed candidate paths;
- synthetic scenarios;
- benchmark evidence;
- replay evidence

outside ordinary memory by default.

Only separately derived, reviewed, and approved narrow lessons may enter the
existing memory-candidate lifecycle.

### 3.4 Production and experimental separation

The package defines a one-way dependency rule:

```text
experimental laboratory -> approved public core contracts
production core -X-> experimental laboratory implementations
```

It requires the production core to operate when the experimental packages are
absent.

Experimental systems cannot access production memory, credentials, accounts,
live authority state, production branches, or unrestricted network services.

### 3.5 Computational integrity

The AlphaCode- and AlphaTensor-inspired capabilities are computationally native.

E1 implements deterministic patch admission, isolated execution, trusted-test
preservation, behaviour signatures, grouping, and evidence-based ranking.

E2 implements formal state/action search, deterministic transitions, invariant
checking, shortest-failure-sequence discovery, replay, and bounded classical
search.

No biological ontology is introduced.

### 3.6 Learned capability deferral

The package does not authorise:

- reinforcement learning;
- MCTS;
- learned heuristics;
- learned ranking;
- reward models;
- candidate-model selection;
- model serving;
- training or fine-tuning.

Those capabilities require future evidence and accepted contracts.

### 3.7 Scope and build practicality

The programme is ambitious but bounded through:

- separate phase releases;
- separate commits;
- complete tests after every phase;
- evidence bundles;
- stop conditions;
- usage reserve;
- no speculative later-phase implementation;
- a required production integration gate before laboratory work.

The master prompt gives Codex full-system context while preventing uncontrolled
continuous mutation.

---

## 4. Refinements Incorporated From Discovery

The contract package incorporates the following refinements:

1. candidate origin is separate from lifecycle;
2. `ROBUSTNESS_TESTED` replaces broad adversarial lifecycle wording;
3. Byte review and Nolan authorisation are separate fields;
4. laboratory command execution uses a separate principal;
5. dependency direction is mechanically testable;
6. candidate frequency and ranking are never correctness or authority;
7. governance violations are hard invalidation conditions rather than negative
   reward values;
8. raw experimental evidence is excluded from memory, identity, and training;
9. learned search is deferred until classical baselines and deterministic
   verification prove need;
10. the Codex build implements real deterministic V0 capability rather than
    unused placeholders.

---

## 5. Ratification Effects by Phase

### B87-I1

Contract accepted and eligible for immediate operator release after branch and
baseline checks.

### B87-I2 through B87-I4

Contracts accepted conditionally. Implementation remains prohibited until the
preceding phase is reviewed and Nolan issues the exact current-phase release.

### B87-PRE-I5

Contract accepted conditionally. It may implement deterministic non-model
evaluation infrastructure only.

### B87-E0 through B87-E2

Contracts accepted conditionally as external laboratories. E0 cannot begin
until the complete I1–I4 production integration gate is accepted.

No phase release is inferred from this decision.

---

## 6. Usage Decision

The hard maximum remains:

```text
60% of the available Codex usage cycle
```

The planned implementation target is no more than 50%, preserving at least 10%
for Byte–Nolan review-directed repairs.

Codex must stop rather than consume the reserve without a reviewable phase
result.

---

## 7. Required Ratification Evidence

Before this decision is changed to accepted:

- all four proposed files must be present on one documentation-only branch;
- `AGENTS.md` must state that D0 is closed;
- no runtime source or migration file may be changed;
- the master prompt must default to `ACTIVE_OPERATOR_RELEASE: NONE`;
- the prompt must require exact Nolan-issued release instructions;
- the prompt must prohibit model integration;
- I1 must remain the first executable phase;
- production and experimental dependency direction must be explicit;
- the branch diff must contain documentation only;
- Nolan must explicitly ratify the package.

---

## 8. Exact Ratification Statement

Nolan may ratify the package with the following decision:

```text
RATIFY B87 PRE-LLM CONTRACT PACK
```

This statement accepts the contracts and prompt. It does not itself begin a
Codex implementation run.

The first Codex implementation run requires the separate release:

```text
AUTHORIZE B87-I1
```

The two statements may be issued together only when Nolan intends to ratify the
contracts and immediately begin I1 preparation.

---

## 9. Current Decision

Byte’s semantic review result is:

```text
READY FOR NOLAN RATIFICATION
```

The package is coherent with D0, computationally native, authority-bounded,
phase-gated, and suitable for the intended pre-LLM Codex_Max programme.

Until Nolan issues the exact ratification statement, the package remains a
review-ready proposal and creates no new implementation authority.
