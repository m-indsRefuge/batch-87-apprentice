# B87 Pre-LLM Contract Ratification Decision

**Project:** Batch-87 Apprentice
**Decision class:** Implementation-contract ratification
**Status:** Ratified and accepted
**Prepared:** 2026-07-22
**Ratified:** 2026-07-22
**Ratification statement:** `RATIFY B87 PRE-LLM CONTRACT PACK`
**Architecture reviewer:** Byte
**Final human authority:** Nolan
**Runtime implementation in this decision:** None
**Active implementation release:** None

---

## 1. Decision

Nolan has explicitly ratified the Batch-87 pre-LLM contract pack.

The following are accepted as the governing implementation programme for the
pre-LLM foundation:

1. `B87-PRE-LLM-IMPLEMENTATION-PROGRAMME-CONTRACT.md`;
2. `B87-E0-E2-EXPERIMENTAL-LABORATORIES-CONTRACT.md`;
3. `B87-CODEX-MAX-PRE-LLM-FOUNDATION-BUILD-PROMPT.md`;
4. the post-D0 corrections to `AGENTS.md`.

This decision ratifies contracts and orchestration rules only. It does not
implement runtime code, modify migrations, connect a model, or begin a Codex
implementation phase.

---

## 2. Ratification Effects

Ratification:

- accepts the detailed contracts for B87-I1 through B87-I4;
- accepts the deterministic B87-PRE-I5 infrastructure contract;
- accepts B87-E0 through B87-E2 as external experimental laboratory contracts;
- accepts the Codex_Max prompt as the operator-controlled orchestration
  contract;
- preserves exact phase-release requirements;
- preserves the 60% hard Codex usage ceiling;
- preserves the prohibition on model integration during the programme;
- preserves separate commits, evidence packets, stop gates, and Nolan-issued
  releases for every phase.

Ratification does not release all phases and does not authorise Codex to infer
that implementation should begin.

The first eligible implementation release is:

```text
AUTHORIZE B87-I1
```

That release has not been issued by this decision.

Later phases require their own direct Nolan-issued release instructions.

---

## 3. Byte Semantic Review

Byte reviewed the complete contract pack against the accepted D0 architecture
and records the following accepted findings.

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

Codex development commands are attributed to `codex_development_harness`.

Laboratory commands are attributed to `experimental_harness`.

Neither principal grants or demonstrates Apprentice Execute permission.

### 3.3 Memory and evidence

The package preserves exactly three primary memory systems.

The following remain outside ordinary memory by default:

- source evidence;
- Controlled Governance Resilience evidence;
- experimental candidates;
- failed candidate paths;
- synthetic scenarios;
- benchmark evidence;
- replay evidence.

Only separately derived, reviewed, and approved narrow lessons may enter the
existing memory-candidate lifecycle.

### 3.4 Production and experimental separation

The accepted dependency rule is:

```text
experimental laboratory -> approved public core contracts
production core -X-> experimental laboratory implementations
```

The production core must operate when experimental packages are absent.

Experimental systems cannot access production memory, credentials, accounts,
live authority state, production branches, private evidence, or unrestricted
network services.

### 3.5 Computational integrity

The AlphaCode- and AlphaTensor-inspired capabilities are computationally native.

B87-E1 defines deterministic patch admission, isolated execution, trusted-test
preservation, behaviour signatures, grouping, and evidence-based ranking.

B87-E2 defines formal state/action search, deterministic transitions, invariant
checking, shortest-failure-sequence discovery, replay, and bounded classical
search.

No biological or anthropomorphic ontology is introduced.

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

Those capabilities require future evidence and separately accepted contracts.

### 3.7 Scope and build practicality

The programme is bounded through:

- separate phase releases;
- separate reviewable commits;
- complete tests after every phase;
- evidence bundles;
- explicit stop conditions;
- a protected usage reserve;
- no speculative later-phase implementation;
- a required production integration gate before laboratory work.

The master prompt gives Codex full-system context while preventing uncontrolled
continuous mutation.

---

## 4. Discovery Refinements Accepted

The contract pack incorporates and ratifies these refinements:

1. candidate origin is separate from candidate lifecycle;
2. `ROBUSTNESS_TESTED` replaces broad adversarial lifecycle wording;
3. Byte review and Nolan authorisation are separate fields;
4. laboratory command execution uses a separate principal;
5. dependency direction is mechanically testable;
6. candidate frequency and ranking are never correctness or authority;
7. governance violations are hard invalidation conditions rather than negative
   reward values;
8. raw experimental evidence is excluded from memory, identity, and training;
9. learned search is deferred until classical baselines and deterministic
   verification establish need;
10. the Codex build targets real deterministic V0 capability rather than unused
    placeholders.

---

## 5. Accepted Phase State

### B87-I1

The contract is accepted and eligible for a separate operator release after
branch and baseline checks.

### B87-I2 through B87-I4

The contracts are accepted conditionally. Implementation remains prohibited
until the preceding phase is reviewed and Nolan issues the exact current-phase
release.

### B87-PRE-I5

The contract is accepted conditionally. It may implement deterministic
non-model evaluation infrastructure only after I1 through I4 pass their gates.

### B87-E0 through B87-E2

The contracts are accepted conditionally as external laboratories. B87-E0
cannot begin until the complete I1-I4 production integration gate is accepted.
B87-E1 requires accepted E0, and B87-E2 requires accepted E0 plus its own
release.

No phase release is inferred from this decision.

---

## 6. Usage Decision

The hard maximum remains:

```text
60% of the available Codex usage cycle
```

The planned implementation target remains no more than 50%, preserving at
least 10% for Byte-Nolan review-directed repairs.

Codex must stop rather than consume the protected reserve without a reviewable
phase result.

---

## 7. Ratification Evidence

The following evidence was satisfied before acceptance:

- all four proposed artefacts were present on one documentation-only branch;
- `AGENTS.md` stated that D0 was closed and merged;
- no runtime source or migration file was changed;
- the master prompt defaulted to `ACTIVE_OPERATOR_RELEASE: NONE`;
- exact Nolan-issued phase releases were required;
- model integration was prohibited;
- I1 remained the first executable phase;
- production and experimental dependency direction was explicit;
- the branch diff contained documentation only;
- PR #2 was open and mergeable;
- Nolan issued the exact ratification statement.

---

## 8. Recorded Ratification Statement

Nolan issued:

```text
RATIFY B87 PRE-LLM CONTRACT PACK
```

This statement accepts the contracts and prompt. It does not begin a Codex
implementation run.

The first implementation run still requires:

```text
AUTHORIZE B87-I1
```

---

## 9. Final Decision

```text
RATIFIED AND ACCEPTED
```

The pre-LLM contract pack is coherent with D0, computationally native,
authority-bounded, phase-gated, and accepted as the governing Codex_Max
implementation programme.

Current execution state:

```text
ACTIVE_OPERATOR_RELEASE: NONE
```

No runtime implementation authority beyond the already eligible B87-I1
contract is activated until Nolan separately issues `AUTHORIZE B87-I1`.