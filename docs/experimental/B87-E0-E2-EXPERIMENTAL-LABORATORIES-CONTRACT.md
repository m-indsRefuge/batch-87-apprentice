# B87-E0–E2 — Experimental Laboratories Contract

**Project:** Batch-87 Apprentice  
**Document class:** External experimental capability contract  
**Status:** Proposed for Nolan–Byte ratification  
**Authority:** Nolan and Byte  
**Production dependency status:** Prohibited  
**Model dependency:** None for V0  
**Learned search:** Prohibited for V0

---

## 1. Purpose

This contract defines three future external capabilities:

1. B87-E0 — Shared Experimental Evidence Core;
2. B87-E1 — Program Synthesis and Verification V0;
3. B87-E2 — Algorithm Discovery Laboratory V0.

E1 is inspired by AlphaCode’s disciplined candidate-generation and verification
method.

E2 is inspired by AlphaTensor’s conversion of bounded computational problems
into searchable environments whose candidate solutions can be independently
verified.

The inspiration is methodological. Batch-87 does not import biological,
anthropomorphic, competitive-programming, tensor-decomposition, reinforcement-
learning, or reward-maximisation ontology into the Apprentice core.

---

## 2. Governing Principle

> A learned system may generate, search, compare, and propose. Deterministic
> systems must verify what can be verified. Human authority decides whether any
> result is promoted.

Neither a laboratory nor any candidate may:

- modify the Apprentice production runtime directly;
- alter immutable governance;
- promote itself;
- modify production memory;
- deploy changes;
- rewrite accepted architecture;
- treat confidence, frequency, novelty, reward, or benchmark score as proof;
- convert an optimization objective into authority;
- attribute laboratory execution to the Apprentice.

All outputs remain experimental evidence until separately reviewed and
explicitly authorised.

---

## 3. Computational-Native Requirement

The laboratories operate on native computational structures, including:

- source code and patches;
- repository trees;
- schemas and types;
- state transitions;
- events and operation grammars;
- memory and evidence records;
- provenance graphs;
- tests and invariants;
- execution traces;
- benchmarks;
- query plans;
- recovery procedures;
- replay manifests;
- deterministic simulator states.

No biological or metaphorical translation layer is permitted.

Every abstraction must provide at least one concrete benefit:

- deterministic validation;
- trust-boundary separation;
- authority enforcement;
- provenance preservation;
- replayability;
- interoperability;
- recoverability;
- testability;
- measurable optimization.

---

## 4. Architectural Placement

The laboratories are external siblings of the production core.

```text
Batch-87
├── Apprentice production core
├── Shared Experimental Evidence Core
└── Experimental laboratories
    ├── Program Synthesis and Verification
    └── Algorithm Discovery Laboratory
```

The dependency rule is permanent:

```text
experimental laboratory -> approved public core contracts
production core -X-> experimental laboratory implementations
```

The production core must import, test, and operate when all experimental
packages are removed.

The laboratories may consume:

- copied fixtures;
- exported public schemas;
- deterministic simulations;
- temporary repositories;
- sandboxed worktrees;
- synthetic test data;
- explicitly approved public architecture contracts.

They may not consume:

- production memory databases;
- credentials;
- live accounts;
- production tools;
- live authority state;
- production branches;
- private evidence;
- unrestricted network access.

---

## 5. Execution Principal and Capability Manifest

All laboratory commands execute under the external principal:

```text
experimental_harness
```

Every run requires an immutable capability manifest containing:

- run identifier;
- laboratory identifier and version;
- operator authorisation reference;
- sandbox root;
- readable paths;
- writable paths;
- allowed commands;
- prohibited commands;
- environment variables permitted;
- network policy;
- resource limits;
- timeout limits;
- cleanup policy;
- source commit or simulator version;
- expected output locations;
- evidence destination.

The capability manifest may narrow permissions only. A task specification or
candidate may not expand it.

The harness must fail closed when a requested operation is absent from the
manifest.

---

## 6. Shared Candidate Semantics

### 6.1 Origin classification

Candidate origin is separate from candidate lifecycle.

Permitted `origin_mode` values are:

```text
generated
searched
imported
human_authored
fixture
```

### 6.2 Candidate lifecycle

The V0 lifecycle is:

```text
REGISTERED
FILTERED
REPLAYED
VERIFIED
ROBUSTNESS_TESTED
ELIGIBLE_FOR_REVIEW
REJECTED
PROMOTED
```

A candidate may be rejected from any non-terminal state.

Only an explicit Nolan authorisation may assign `PROMOTED`.

Byte may record review findings and a promotion recommendation, but Byte’s
review does not itself create promotion authority.

Required fields are:

```text
reviewed_by
review_status
review_evidence_id
authorised_by
authorisation_reference
promotion_status
```

For a promoted candidate:

```text
reviewed_by = Byte or another explicitly accepted reviewer
authorised_by = Nolan
```

No score, majority vote, candidate frequency, benchmark, or model output may
populate `authorised_by`.

---

## 7. B87-E0 — Shared Experimental Evidence Core

### 7.1 Objective

Implement the common evidence, lineage, replay, evaluation, and promotion
substrate used by E1 and E2.

E0 is not a fourth memory system.

### 7.2 Required contracts

E0 must provide concrete typed contracts for:

```text
ProblemSpecification
ExperimentalRun
CandidateArtifact
CandidateLineage
CandidateEvaluation
InvariantEvaluation
BenchmarkEvaluation
ReplayManifest
EnvironmentManifest
CapabilityManifest
BehaviourSignature
CandidateCluster
RankingDecision
PromotionDecision
```

### 7.3 Universal experimental fields

Every experimental record must preserve:

- stable identifier;
- record type and schema version;
- laboratory and version;
- origin mode;
- generator or search method;
- model and version where applicable;
- task or problem specification version;
- repository or simulator version;
- initial state;
- capability manifest;
- invariants;
- evaluation commands;
- random seed where applicable;
- parent candidates and lineage;
- replay instructions;
- environment manifest;
- output hashes;
- validation outcome;
- review state;
- promotion state;
- timestamps and creating principal.

### 7.4 Persistence and immutability

E0 must use the accepted persistence kernel and evidence substrate through public
contracts only.

Finalised raw experimental evidence is immutable.

Corrections require a separate linked record. Review and promotion decisions are
separate records and may not mutate the raw candidate artefact.

### 7.5 Replay

A replay manifest must identify:

- exact source input;
- initial state hash;
- repository or simulator commit;
- environment values permitted;
- dependency lock or environment fingerprint;
- commands in order;
- timeouts;
- expected evidence outputs;
- canonical comparison method;
- non-determinism disclosures.

A candidate cannot become `VERIFIED` unless replay succeeds independently from
the recorded initial state.

### 7.6 Memory and training exclusion

Raw experimental records are:

```text
ordinary_memory_eligibility = prohibited
identity_eligibility = prohibited
training_eligibility = prohibited
retrieval_policy = experimental_only
```

A separately derived narrow lesson may become a memory candidate only through
the accepted I3 lifecycle, external review, exact lineage, and approval.

### 7.7 E0 acceptance gate

Tests must prove:

- experimental records cannot become ordinary memory;
- candidates cannot self-promote;
- review and authorisation are distinct;
- replay manifests are complete and hashed;
- finalised raw records are immutable;
- lineage cannot reference missing candidates;
- rejected candidates remain preserved;
- promotion requires Nolan authorisation;
- the production core passes when experimental packages are removed;
- all E0 records are reconstructable.

Codex must stop after the E0 evidence packet.

---

## 8. B87-E1 — Program Synthesis and Verification V0

### 8.1 Objective

Accept multiple independent code or patch candidates for one bounded engineering
task, evaluate them in isolated repositories, group materially equivalent
behaviour, rank surviving candidates deterministically, and present evidence for
human review.

V0 does not require a model. Candidates may be supplied by Codex, Nolan, Byte-
guided workflows, another coding model later, or deterministic fixtures.

### 8.2 V0 scope

V0 supports:

- one source repository per experimental run;
- Python as the first language;
- one bounded deterministic task specification;
- up to four independent candidates;
- temporary cloned repositories or worktrees;
- operator-approved commands only;
- deterministic filtering;
- existing and approved additional tests;
- basic behaviour signatures;
- deterministic ranking;
- complete evidence bundles;
- human candidate selection.

### 8.3 Required contracts

```text
CodeTaskSpecification
CandidateProgram
CandidatePatch
PatchApplicationResult
StaticEvaluation
TestEvaluation
InvariantEvaluation
BehaviourSignature
CandidateCluster
RankingDecision
PromotionDecision
```

### 8.4 Task specification

A `CodeTaskSpecification` must define:

- repository and accepted base commit;
- allowed file paths;
- prohibited file paths;
- required behaviour;
- explicit non-goals;
- accepted commands;
- required tests;
- architecture invariants;
- security constraints;
- dependency policy;
- timeout and resource limits;
- output contract;
- candidate count limit;
- evaluation ordering.

A candidate may not modify its task specification.

### 8.5 Candidate independence

Candidates should be registered independently.

When candidates are model-generated later, separate contexts and seeds should be
used so that one candidate’s assumptions do not contaminate all alternatives.

Candidate frequency is never correctness evidence.

### 8.6 Hard filters

A candidate must be rejected when it violates any mandatory condition,
including:

- file-scope boundary;
- patch application;
- syntax or compilation;
- type checks where required;
- required tests;
- governance invariants;
- security boundaries;
- dependency policy;
- prohibited side effects;
- repository architecture;
- sandbox capability manifest;
- evidence completeness.

Correctness and governance are admission gates.

Performance, elegance, patch size, and style are considered only after all hard
gates pass.

### 8.7 Test trust

Generated tests are evidence candidates, not sole proof.

A candidate may not weaken, skip, delete, or rewrite accepted tests to obtain
passage.

Additional candidate-authored tests must be clearly labelled and evaluated
separately from trusted baseline tests.

### 8.8 Behaviour signatures

V0 behaviour signatures may include:

- trusted-test result vector;
- invariant result vector;
- exit-code pattern;
- touched-file set;
- mutation footprint;
- failure category;
- emitted event types;
- recovery behaviour;
- canonical output hash;
- coverage summary where available.

V0 clustering must be deterministic and explainable.

AST similarity, learned embeddings, or learned clustering are deferred.

### 8.9 Deterministic ranking

The V0 ranking order is:

```text
1. Contract and invariant correctness
2. Trusted required-test success
3. Property and robustness-test success
4. Architectural compatibility
5. Recovery and failure behaviour
6. Simplicity
7. Maintainability
8. Performance
9. Patch size
```

A ranking decision must preserve the evidence used and all ties.

The top-ranked candidate is not automatically promoted.

### 8.10 Suitable first tasks

The first real E1 experiment should target a narrow deterministic engine such as:

- provenance-chain validation;
- correction-precedence resolution;
- memory-candidate deduplication;
- task-state normalization;
- evidence-manifest construction;
- deterministic recovery planning.

It must not target immutable governance, the whole Apprentice runtime, identity,
or live production memory.

### 8.11 E1 acceptance gate

Tests must prove:

- candidates run in isolated temporary repositories;
- prohibited files cannot be changed;
- production branches cannot be written;
- trusted tests cannot be weakened;
- failed candidates remain preserved;
- equivalent behaviour groups deterministically;
- ranking is reproducible;
- majority agreement does not override a failing invariant;
- no candidate can self-promote;
- the evidence bundle replays from the accepted base commit;
- removing E1 does not break the production core.

Codex must stop after the E1 evidence packet.

---

## 9. B87-E2 — Algorithm Discovery Laboratory V0

### 9.1 Objective

Search bounded formal state spaces for candidate event sequences, protocols,
recovery procedures, or deterministic algorithms, then replay candidates and
verify them against exact invariants.

V0 contains no reinforcement learning.

### 9.2 Required problem contract

Each `DiscoveryProblem` must define:

- problem identifier and version;
- typed initial state;
- goal or failure condition;
- permitted actions or events;
- action preconditions;
- deterministic transition function;
- forbidden states;
- immutable invariants;
- objective function;
- search limits;
- replay method;
- trusted baseline where applicable;
- canonical state hashing;
- terminal-state semantics.

Governance, consent, authority, privacy, and identity constraints are hard
invariants. They may not be represented solely as reward terms.

### 9.3 V0 search methods

V0 may implement:

- breadth-first search;
- depth-limited search;
- iterative deepening where justified;
- A* only with an explicit deterministic heuristic;
- deterministic frontier ordering;
- duplicate-state elimination through canonical state hashes;
- property-based state exploration when already supported by accepted tooling.

V0 may not implement:

- reinforcement learning;
- policy or value networks;
- Monte Carlo tree search;
- learned heuristics;
- evolutionary search;
- automatic simulator generation;
- unbounded state exploration.

### 9.4 First experiment

The first accepted experiment is:

> Find the shortest reproducible sequence of permitted events that causes a
> deterministic Apprentice invariant to fail.

Candidate event classes may include:

- consent revocation;
- delayed tool result;
- interrupted operation;
- retry after partial completion;
- stale session restoration;
- memory correction arrival;
- authority-context change;
- duplicate callback;
- timeout;
- incomplete local commit;
- recovery after restart.

The initial fixture must be synthetic and deterministic. It must not access live
operations or production data.

The laboratory’s own success claim is not trusted. Every discovered sequence
must replay independently from the original state and fail the accepted
invariant verifier in the recorded manner.

### 9.5 Second experiment gate

Only after failure-sequence discovery is accepted may E2 search for:

> The lowest-cost recovery sequence that restores a valid state without
> duplicating external action, losing provenance, or bypassing authority.

Potential recovery actions may include:

- replay local commit;
- consult operation ledger;
- reconstruct candidate state;
- roll back provisional state;
- mark unresolved;
- request operator decision;
- resume from verified checkpoint.

This second experiment is not required for E2 V0 acceptance unless explicitly
released.

### 9.6 Candidate path evidence

Every discovered path must preserve:

- initial state hash;
- action sequence;
- each intermediate state hash;
- precondition results;
- invariant results after each action;
- terminal condition;
- objective cost;
- frontier and search configuration;
- search method and limits;
- replay result;
- baseline comparison.

### 9.7 E2 acceptance gate

Tests must prove:

- transitions are deterministic;
- invalid actions are rejected;
- invariant failure is detected at the exact step;
- breadth-first search returns a shortest path under uniform action cost;
- search limits fail visibly rather than implying no solution;
- canonical state hashing prevents equivalent duplicate exploration;
- replay reproduces the path from the original state;
- the independent invariant verifier—not the search process—determines validity;
- governance violations invalidate candidates rather than lowering a score;
- no path can self-promote;
- removing E2 does not break the production core.

Codex must stop after the E2 evidence packet.

---

## 10. Shared Sandbox Requirements

E1 and E2 may share sandbox infrastructure through E0 contracts.

The sandbox must provide:

- unique run root;
- no production-path writes;
- explicit readable and writable path lists;
- command allowlist;
- environment allowlist;
- network disabled by default;
- bounded CPU time and wall-clock timeout where supported;
- bounded candidate count and search nodes;
- stdout and stderr capture;
- exit-code capture;
- cleanup state recording;
- retained evidence outside the disposable execution root;
- deterministic source-state reconstruction.

V0 is a development safety boundary, not a claim of hostile-code containment.
Untrusted arbitrary code from unknown third parties is out of scope.

---

## 11. Promotion Boundary

Promotion is a separate governance event.

The laboratories may produce:

- candidate ranking;
- eligibility recommendation;
- review packet;
- risk report;
- replay evidence.

They may not produce an authoritative promotion decision.

A valid promotion record requires:

```text
candidate_status = ELIGIBLE_FOR_REVIEW
review_status = accepted
reviewed_by = approved reviewer
authorised_by = Nolan
authorisation_reference = explicit human decision
promotion_status = PROMOTED
```

Promotion does not automatically deploy, merge, activate memory, authorise
training, or change architecture.

Each downstream action requires its own authority and contract.

---

## 12. Learned-Search Activation Gate

Learned guidance may be considered in a future contract only when:

- a reliable deterministic simulator exists;
- invariants are executable and independently trusted;
- classical-search baselines exist;
- the state space demonstrably exceeds classical-search practicality;
- the objective is measurable;
- candidate correctness is independently checkable;
- repeated search demand justifies training;
- training cost is proportionate;
- outputs remain replayable;
- human promotion remains mandatory;
- defensive-bias and governance reviews pass.

No learned-search work is authorised by this contract.

---

## 13. Universal Experimental Stop Conditions

Codex must stop experimental work when:

- production access is required;
- a sandbox boundary cannot be enforced;
- an invariant is ambiguous;
- the candidate count or search space exceeds the released budget;
- a candidate requires weakening tests or governance;
- replay cannot reconstruct the initial state;
- non-determinism cannot be isolated or disclosed;
- an operation is not present in the capability manifest;
- live credentials or private evidence are encountered;
- promotion, deployment, or training would be required;
- the production core begins depending on laboratory code;
- the usage reserve is threatened.

The stop report must preserve all partial evidence and explain why no conclusion
may be drawn beyond the completed search.

---

## 14. Ratification Conditions

This contract becomes accepted only when:

1. Nolan explicitly approves E0–E2;
2. Byte confirms semantic consistency with D0 and the pre-LLM programme;
3. `AGENTS.md` includes the experimental boundary;
4. the Codex_Max prompt preserves the E0–E2 release gates;
5. E0 cannot begin before the I1–I4 integration gate;
6. the contract is committed separately from implementation code.

Until ratification, these are complete proposed contracts and not execution
authority.
