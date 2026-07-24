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

The current active implementation release remains:

```text
NONE
```

B87-I2 - Governed Task Runtime is the next eligible implementation slice.

B87-I2 may begin only after Nolan separately issues:

    AUTHORIZE B87-I2

B87-I3 through B87-I5 require their own accepted contracts and explicit
phase release before implementation begins.

The Shared Experimental Evidence Core, Program Synthesis and Verification V0,
and Algorithm Discovery Laboratory V0 are future external laboratory
capabilities. They are not production-runtime dependencies and may not be
implemented before their own accepted contracts and release gates.

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
