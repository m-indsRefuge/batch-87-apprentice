# B87 Programme-State Reconciliation Through I4-A and V0

## 1. Record status

**Record type:** current programme-state reconciliation

**Status:** accepted

**Acceptance date:** 2026-07-30

**Acceptance decision:**

```text
docs/implementation/B87-PROGRAMME-STATE-AND-I4-B-CONTRACT-ACCEPTANCE-DECISION.md
```

**Authoring authorization:**

```text
AUTHORIZE B87 PROGRAMME-STATE RECONCILIATION AND I4-B SLICE CONTRACT
```

**Repository baseline inspected:**

```text
branch: main
commit: a91c82f7c68143b26b655a05fcbc6571e5358006
upstream: origin/main
tracked state: clean
```

**Current implementation release:**

```text
NONE
```

This record is documentation-only. It reconciles the repository's live
programme-state summaries with the accepted implementation state supplied by
Nolan and the traceable `main` history through B87-I4-A, together with the
accepted B87-V0 persistence-validation closure.

This record does not:

- accept a new runtime implementation;
- issue an implementation release;
- create or connect a model;
- select a base model;
- start a model server;
- call an external model API;
- authorize Validation V1;
- authorize B87-PRE-I5, B87-I5, or an experimental laboratory;
- alter an earlier decision's original decision-time state.

## 2. Interpretation and precedence

This record is a current-state overlay. It does not replace or weaken:

1. the accepted D0 architecture corpus;
2. the ratified pre-LLM implementation programme;
3. the I1 controlled-resilience reference-boundary decision;
4. the I1 and I2 acceptance decisions and evidence;
5. the accepted I3 and I4-A implementation history;
6. the accepted B87-V0 closure and V1 entry gate;
7. repository authority, permission, evidence, privacy, and experimental
   isolation boundaries.

Where an older document states the next eligible phase, active release, or
repository implementation state as it existed when that document was decided,
that statement remains valid historical evidence of its decision time. It must
not be read as the current live programme state.

Technical invariants in the ratified master and programme contracts remain
governing. The proposed B87-I4-B slice contract partitions the remaining model
and invocation bridge work into a narrower future slice; it does not rewrite the
original I4 contract.

## 3. Historical-record preservation

The following records are intentionally preserved unchanged:

- `docs/architecture/B87-D0-CLOSURE-DECISION.md`;
- `docs/implementation/B87-LLM-READINESS-BASELINE-AUDIT.md`;
- `docs/implementation/B87-PRE-LLM-CONTRACT-RATIFICATION-DECISION.md`;
- `docs/implementation/B87-PRE-LLM-IMPLEMENTATION-PROGRAMME-CONTRACT.md`;
- `docs/implementation/B87-I1-I4-LLM-READINESS-CODEX-MASTER-CONTRACT.md`;
- `docs/implementation/B87-CODEX-MAX-PRE-LLM-FOUNDATION-BUILD-PROMPT.md`;
- `docs/implementation/B87-I1-CONTROLLED-RESILIENCE-REFERENCE-BOUNDARY-DECISION.md`;
- the B87-I1 and B87-I2 acceptance and evidence records;
- `docs/implementation/B87-V0-PERSISTENCE-VALIDATION-CLOSURE-AND-V1-ENTRY-GATE.md`.

Examples such as `ACTIVE_OPERATOR_RELEASE: NONE`, an earlier next-phase label,
or an audit statement that runtime code did not yet exist are preserved because
they record the state at that decision or audit. They are not silently rewritten
into present-tense claims.

The live summaries in `AGENTS.md` and `README.md` point to this reconciliation
for current state.

## 4. Accepted implementation ledger

The accepted implementation state through B87-I4-A is:

| Slice | Accepted implementation history | Merge or closure commit | Current state |
| --- | --- | --- | --- |
| B87-I1 Persistence Kernel | `51307bebd8980a10c36980fae4b1e09dee20a6db` | `dde512942fb40f099749a57258c47a5388cceaa3` | Accepted and closed |
| B87-I2 Governed Task Runtime | `01f00e419f30db2b5025f9c2e9920506a598c8aa`; repair `5da8110b5c844b1a3d419ad3e5dd5a76f774c162` | `7294efcbe455e6a8b10fc7027a5bcedb12a7001d` | Accepted and closed |
| B87-I3-A Shared Memory Kernel | `c9c0fdc9b59f7bf1f0fdb537e3ada4f64c196e75`; repairs `75ff2d36365f84a3b9f7d903eb92d7eb39dcc5de`, `65c485008b26025a794fba737eaa46ab14cb969e` | `d630aedf69c9ebd4f2e3cf7ba36c9455b8315b49` | Accepted and closed |
| B87-I3-B Construct and Relational Memory | `f51a87cb6f023b594cd46e53e62463b98fe36a63` | `359f89326d4f3e21c06667aa5c2ce75ecc90643a` | Accepted and closed |
| B87-I3-C1 Factual Self-Model Foundation | `c46304226b599dd77189087d145735af87b8d5e0` | `e581f770188f8df96c19a435ddc84447913f1888` | Accepted and closed |
| B87-I3-C2 Episode and Correction Ledger | `3a3429708b724573e8eb1b11477658b055bbaa87` | `bce4d6083b3aa8024e486c03e972218a779d4b89` | Accepted and closed |
| B87-I3-C3 Developmental Derivation | `866fb27eaaebabe7ad5bc8d886edc82ac1ffd946`; test hardening `99e1230ee8690c2f3ffd24b6fbb465bc372ae8a5` | `75ce3044501a66ef1ba6f8ed9e9c87cea809d0ac` | Accepted and closed |
| B87-I3-D Session and Task Memory | `66ce74745f35b73607b54c90cc991aa2e54c50f6` | `d1b561c1f28816ddac0b5cd418fd77e3ea634629` | Accepted and closed |
| B87-I4-A Governed Retrieval and Context Assembly | `29300272aa3745b79d7c0d474cad41ec90c9d723` | `093e07a6aa9209a6ea8efe2aaecfcbdeb6829d0a` | Accepted and closed |

B87-I3 is therefore accepted and closed as the aggregate of its accepted
sub-slices. B87-I4 is only partially implemented: I4-A is accepted, while the
provider-neutral model and invocation bridge remains unimplemented.

This ledger records accepted state supplied by Nolan and corroborated by the
immutable `main` merge history. It does not retroactively create missing
decision-time acceptance records.

## 5. Accepted B87-V0 closure

B87-V0 is accepted and closed.

Its accepted source baseline is:

```text
branch: main
commit: 093e07a6aa9209a6ea8efe2aaecfcbdeb6829d0a
```

The closure record was committed as:

```text
a91c82f7c68143b26b655a05fcbc6571e5358006
```

B87-V0 establishes an evidence-backed persistence milestone within its tested
configuration and workload bounds. It does not establish:

- semantic memory correctness;
- retrieval or context quality;
- model behaviour;
- model suitability;
- developmental compounding;
- autonomous action;
- general production readiness.

The accepted baseline includes I4-A. It does not include any I4-B migration,
schema, provider, invocation, or response-capture implementation.

Under the accepted V0 reopening rule, any future material migration, schema,
transaction, persistence-contract, identity, integrity, or deployment change
requires a scoped regression decision and may require partial or complete V0
revalidation. An I4-B implementation must not inherit or claim V0 acceptance
automatically.

## 6. Current implemented boundary

The current accepted production-core source includes:

- the B87-I1 persistence kernel and evidence substrate;
- the B87-I2 governed task runtime;
- the three governed memory domains implemented through the accepted I3
  sub-slices;
- deterministic retrieval eligibility and materialization;
- deterministic fallback ranking;
- immutable retrieval requests and manifests;
- ordered structured context packages;
- context hashing and reconstruction;
- contamination rejection and preservation;
- clean recovery-context relationships;
- current bridge-readiness assessment;
- integrity inspection for the accepted I4-A surface.

The accepted I4-A public boundary intentionally exposes no provider invocation
method and no raw database handle to a provider.

## 7. Explicitly unimplemented boundary

The repository does not currently implement or activate:

- a provider-neutral model protocol;
- an inactive or deterministic mock provider;
- a local-provider transport;
- model-input packet schemas;
- Apprentice-response schemas;
- model invocation records;
- model output records;
- raw model-output capture for a real or mock invocation;
- response parsing or response-schema validation;
- provider failure and timeout persistence;
- exact invocation reconstruction;
- a real model;
- a selected provisional base model;
- a model server;
- an external model API;
- model weights or adapters;
- candidate-model admission;
- model behavioural evaluation;
- B87-PRE-I5 or B87-I5;
- Validation V1 execution;
- B87-E0, B87-E1, or B87-E2 implementations.

No mock success may be interpreted as model behaviour, model admission, memory
efficacy, or Apprentice-system validation.

## 8. Current release and next bounded decision

The current active implementation release is:

```text
NONE
```

The next bounded implementation slice is:

```text
B87-I4-B - Provider-Neutral Model and Invocation Bridge
```

Its accepted but unreleased contract is:

```text
docs/implementation/B87-I4-B-PROVIDER-NEUTRAL-MODEL-AND-INVOCATION-BRIDGE-CONTRACT.md
```

Contract acceptance does not release implementation. A later implementation run
requires both:

1. separate acceptance and recording of the scoped V0 regression decision
   required by section 17 of the I4-B contract; and
2. Nolan's exact instruction:

```text
AUTHORIZE B87-I4-B
```

The acceptance decision and authoring authorization recorded in section 1 are
not that release.

## 9. Validation V1 boundary

The B87-V0 closure defines a Validation V1 question and entry gate. It does not
activate Validation V1.

Validation V1 remains gated by:

- a frozen candidate source commit;
- accepted applicable implementation slices;
- complete internal tests;
- strict D0 validation;
- fresh migration success;
- a separate external harness;
- synthetic or specifically approved data;
- predefined assertions and negative controls;
- its own test contracts and evidence bundles;
- explicit Nolan authorization.

This reconciliation does not prepare, authorize, or execute a V1 test.

## 10. Acceptance record

Byte completed semantic review and accepted the final documentation packet.
Nolan then issued:

```text
ACCEPT B87 PROGRAMME-STATE RECONCILIATION AND I4-B CONTRACT
```

The governing decision is:

```text
docs/implementation/B87-PROGRAMME-STATE-AND-I4-B-CONTRACT-ACCEPTANCE-DECISION.md
```

That decision accepts this reconciliation and I4-B contract version 1.0 as
documentation. It does not authorize implementation, satisfy the scoped V0
regression-decision gate, issue `AUTHORIZE B87-I4-B`, or change the active
implementation release from `NONE`.
