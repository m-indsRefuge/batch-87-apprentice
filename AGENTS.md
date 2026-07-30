# Batch-87 Apprentice Repository Instructions

## Current architecture state

B87-D0 — Developmental Architecture and Boundary Definition is accepted, closed,
and merged into `main`.

The active target system is:

> B87-S1 — Governed Memory Apprentice

The D0 closure establishes that the architecture is coherent, bounded,
implementable, and testable. It does not establish model behaviour, memory
efficacy, developmental compounding, or base-model suitability.

B87-I1 - Persistence Kernel is accepted, merged, live-validated,
post-merge validated, and closed. The accepted implementation commit is
51307bebd8980a10c36980fae4b1e09dee20a6db; the merge commit is
dde512942fb40f099749a57258c47a5388cceaa3.

The governing acceptance records are:

    docs/implementation/B87-I1-PERSISTENCE-KERNEL-ACCEPTANCE-DECISION.md
    docs/implementation/B87-I1-PERSISTENCE-KERNEL-ACCEPTANCE-EVIDENCE.md

The B87-I1 Controlled-Resilience Reference Boundary Decision is ratified and
accepted. It resolves the A4.2 foreign-key and phase-ownership ambiguity by
permitting typed persistence-only reference anchors without implementing later-
phase experiment execution, context assembly, model invocation, recovery, or
formal evaluation completion.

The governing decision is:

```text
docs/implementation/B87-I1-CONTROLLED-RESILIENCE-REFERENCE-BOUNDARY-DECISION.md
```

B87-I2 - Governed Task Runtime is accepted, merged, Byte-reviewed,
review-directed-repair validated, post-merge validated, and closed. The accepted
implementation commit is 01f00e419f30db2b5025f9c2e9920506a598c8aa; the
accepted repair commit is 5da8110b5c844b1a3d419ad3e5dd5a76f774c162; the merge
commit is 7294efcbe455e6a8b10fc7027a5bcedb12a7001d.

The governing acceptance records are:

    docs/implementation/B87-I2-GOVERNED-TASK-RUNTIME-ACCEPTANCE-DECISION.md
    docs/implementation/B87-I2-GOVERNED-TASK-RUNTIME-ACCEPTANCE-EVIDENCE.md

B87-I3 - Three Memory Domains and Evidence Integration is accepted, merged, and
closed through these bounded sub-slices:

- B87-I3-A - Shared Memory Kernel, accepted implementation series
  c9c0fdc9b59f7bf1f0fdb537e3ada4f64c196e75,
  75ff2d36365f84a3b9f7d903eb92d7eb39dcc5de, and
  65c485008b26025a794fba737eaa46ab14cb969e; merge commit
  d630aedf69c9ebd4f2e3cf7ba36c9455b8315b49.
- B87-I3-B - Construct and Relational Memory, accepted implementation commit
  f51a87cb6f023b594cd46e53e62463b98fe36a63; merge commit
  359f89326d4f3e21c06667aa5c2ce75ecc90643a.
- B87-I3-C1 - Factual Self-Model Foundation, accepted implementation commit
  c46304226b599dd77189087d145735af87b8d5e0; merge commit
  e581f770188f8df96c19a435ddc84447913f1888.
- B87-I3-C2 - Episode and Correction Ledger, accepted implementation commit
  3a3429708b724573e8eb1b11477658b055bbaa87; merge commit
  bce4d6083b3aa8024e486c03e972218a779d4b89.
- B87-I3-C3 - Developmental Derivation, accepted implementation commit
  866fb27eaaebabe7ad5bc8d886edc82ac1ffd946 with test-hardening commit
  99e1230ee8690c2f3ffd24b6fbb465bc372ae8a5; merge commit
  75ce3044501a66ef1ba6f8ed9e9c87cea809d0ac.
- B87-I3-D - Session and Task Memory, accepted implementation commit
  66ce74745f35b73607b54c90cc991aa2e54c50f6; merge commit
  d1b561c1f28816ddac0b5cd418fd77e3ea634629.

B87-I4-A - Governed Retrieval and Context Assembly is accepted, merged, and
closed. The accepted implementation commit is
29300272aa3745b79d7c0d474cad41ec90c9d723; the merge commit is
093e07a6aa9209a6ea8efe2aaecfcbdeb6829d0a.

B87-V0 - Persistence Validation is accepted and closed against source baseline
093e07a6aa9209a6ea8efe2aaecfcbdeb6829d0a. The closure record commit is
a91c82f7c68143b26b655a05fcbc6571e5358006.

The governing current-state record and its acceptance decision are:

    docs/implementation/B87-PROGRAMME-STATE-RECONCILIATION-THROUGH-I4-A-AND-V0.md
    docs/implementation/B87-PROGRAMME-STATE-AND-I4-B-CONTRACT-ACCEPTANCE-DECISION.md

The programme-state reconciliation and B87-I4-B contract version 1.0 are
accepted documentation as of 2026-07-30. Their acceptance does not release
implementation.

The current active implementation release is:

```text
NONE
```

B87-I4-B - Provider-Neutral Model and Invocation Bridge is the next bounded
implementation slice. Its contract is accepted but implementation remains
unreleased:

    docs/implementation/B87-I4-B-PROVIDER-NEUTRAL-MODEL-AND-INVOCATION-BRIDGE-CONTRACT.md

B87-I4-B implementation may begin only after a scoped V0 regression decision
required by section 17 is separately accepted and recorded, and Nolan
separately issues:

    AUTHORIZE B87-I4-B

The documentation acceptance, programme-state reconciliation, and earlier
contract-authoring authorization do not issue that implementation release.

B87-PRE-I5 and B87-E0 through B87-E2 already have conditionally accepted
contracts under the ratified pre-LLM contract pack. They remain inactive because
their entry gates are unsatisfied and no current phase release exists.
Conditional contract acceptance does not authorize implementation or execution;
each phase still requires satisfaction of its accepted entry gate and its exact
explicit phase release.

B87-I5 and external Validation V1 are distinct from those conditionally accepted
phases. They remain inactive and still require separately accepted execution
contracts, satisfied entry gates, and explicit Nolan authorization before
implementation or execution. The accepted V0 closure record defines the
Validation V1 entry-gate boundary but does not supply its execution contract or
authorization.

The Shared Experimental Evidence Core, Program Synthesis and Verification V0,
and Algorithm Discovery Laboratory V0 are the conditionally accepted B87-E0
through B87-E2 external laboratory capabilities referenced above. They are not
production-runtime dependencies and remain inactive until their accepted entry
gates are satisfied and their exact phase releases are issued.

## Authority and governance boundaries

- Nolan is the final human authority within Batch-87.
- Applicable law and non-derogable human protection remain above project
  authority.
- Do not alter, weaken, supersede, or create exceptions to constitutional
  authority or safety constraints.
- Treat model output as a proposal, never as permission, approval, evidence, or
  authority by itself.
- Do not allow a model, search process, benchmark, candidate frequency, ranking
  score, or laboratory to approve its own records, permissions, identity,
  training eligibility, implementation scope, or promotion.
- Stop rather than invent authority, consent, legal certainty, provenance, or
  evidence.

## B87-S1 permission boundary

The Apprentice permissions during B87-S1 are limited to:

- Observe;
- Analyse.

The following are unavailable:

- Propose as an independent authority-bearing permission;
- Execute;
- autonomous tool use;
- unrestricted shell, filesystem, repository, database, network, credential,
  or communication access.

Analytical recommendations may appear only where an approved task contract
permits them. A recommendation does not create action authority.

Any command execution performed by Codex or a future experimental harness is
operator-authorised development infrastructure. It must not be attributed to
the Apprentice or used to imply Apprentice Execute authority.

## Data and memory boundaries

- Preserve provenance for memories, evidence, evaluations, corrections,
  lessons, governance decisions, model invocations, experimental runs, and
  candidate artefacts.
- Keep evidence separate from interpreted memory.
- Keep the three memory systems distinct:
  - Construct and relational memory;
  - self and episodic memory;
  - session and task memory.
- Maintain project, subject, session, task, sensitivity, privacy, lifecycle,
  approval, authority, and retrieval scope.
- Do not commit secrets, credentials, personal information, live memory
  databases, private evidence, model files, raw sessions, or unreviewed
  training data.
- Raw Controlled Governance Resilience evidence is restricted,
  evaluation-only, and prohibited from ordinary memory, identity, and training
  during B87-S1.
- Experimental candidates, failed search paths, synthetic scenarios, and
  sandbox outputs belong in experimental evidence. They must not silently enter
  Construct, episodic, session, identity, or training records.
- Do not activate or author `SOUL.md` during B87-S1.
- Do not introduce fine-tuning or adapter training before the governed memory,
  evaluation, and model-admission foundations are accepted.

## Architecture and implementation sources

Before architecture or implementation work, read the applicable documents in:

```text
docs/architecture/
docs/implementation/
docs/experimental/
```

The D0 conformance manifest is:

```text
docs/architecture/B87-D0-CONFORMANCE-MANIFEST.json
```

The executable D0 validator is:

```text
scripts/validate_d0_architecture.py
```

The manifest and validators are subordinate to the accepted architecture and
implementation contracts. They make explicit invariants executable; they do
not create policy or authority.

Where a general A2 or A3 rule would permit broader treatment of Controlled
Governance Resilience evidence, D0-A4.2 supplies the narrower rule.

Where A4.2 requires later-phase operational identifiers to exist before their
owning tables are active, the ratified B87-I1 reference-boundary decision
supplies the narrower typed-anchor rule. Anchor existence creates referential
identity only and never proves execution, completion, validity, or success.

## Engineering expectations

- Prefer deterministic, inspectable components.
- Use Python 3.11 or later and the approved initial technology baseline.
- Use direct, explicit SQLite access until a later architecture decision
  authorises another persistence abstraction.
- Enable and verify SQLite foreign keys on every connection.
- Keep migrations ordered, immutable after application, content-hashed, and
  reversible where technically possible.
- Use fail-closed behaviour for authority, permission, retrieval, privacy,
  integrity, context-policy, laboratory-isolation, and promotion violations.
- Maintain project and memory-scope separation before relevance ranking.
- Preserve exact invocation and experimental replay reconstruction.
- Add deterministic tests for every governance, memory, persistence,
  retrieval, transaction, sandbox, replay, and promotion invariant.
- Preserve negative evidence and failed tests.
- Keep future architecture compatible without prematurely activating it.
- The Apprentice production runtime must not import or depend upon experimental
  laboratory implementations.
- No placeholder or anchor row may masquerade as an executed experiment,
  assembled context, model invocation, recovery run, or completed evaluation.

## Codex execution protocol

Codex is a bounded implementation assistant. It is not an architecture,
promotion, release, or acceptance authority.

For every implementation slice:

1. read this file and the governing architecture and implementation contract;
2. identify the explicitly authorised slice and prohibited scope;
3. inspect the current repository, branch, status, and tests;
4. record the baseline before editing;
5. implement only the accepted contract;
6. add or update deterministic tests;
7. run the complete relevant validation suite;
8. preserve diffs, commands, test results, evidence bundles, and unresolved
   findings;
9. stop at the defined completion or stop condition;
10. do not merge, broaden scope, activate later slices, or declare acceptance;
11. do not continue to another slice without the exact operator phase-release
    instruction required by the governing programme contract.

Use separate reviewable commits for:

- B87-I1 persistence implementation;
- each later implementation slice;
- the Shared Experimental Evidence Core;
- Program Synthesis and Verification V0;
- Algorithm Discovery Laboratory V0;
- repairs arising from Byte–Nolan review.

Do not combine architecture or contract ratification with runtime
implementation in one commit.

## Model integration boundary

Candidate models may be downloaded or pre-screened for compatibility only after
the relevant infrastructure contract permits it.

No model becomes the provisional B87-S1 base model until the minimum governed
vertical slice exists and the candidate passes the approved admission suite.

The minimum governed vertical slice includes:

- persistence kernel;
- governed task runtime;
- three memory domains;
- evidence substrate;
- governed retrieval;
- context assembly;
- model-provider bridge;
- evaluation and invocation audit support.

A raw prompt demonstration is not evidence that the Apprentice system works.

## Experimental-laboratory boundary

The experimental laboratories may consume copied fixtures, simulations,
sandbox repositories, and approved public core contracts.

They may not access production memory, credentials, accounts, tools, live
authority state, or production branches. They may not modify governance,
promote candidates, deploy results, weaken tests, or convert optimization goals
into authority.

The permanent dependency rule is:

```text
experimental laboratory -> approved public core contracts
production core -X-> experimental laboratory implementations
```

Models propose. Search explores. Verifiers test. Evidence records. Byte reviews.
Nolan authorises.
