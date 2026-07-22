# Batch-87 Apprentice Repository Instructions

## Current architecture state

B87-D0 — Developmental Architecture and Boundary Definition is in formal
closure review.

The active target system is:

> B87-S1 — Governed Memory Apprentice

D0 closure may establish that the architecture is coherent, bounded,
implementable, and testable. It may not claim that model behaviour has already
been validated.

No runtime implementation slice is authorised until the D0 closure package is
accepted and committed.

After effective D0 closure, only B87-I1 — Persistence Kernel is authorised
initially. Later slices require their own accepted contracts.

## Authority and governance boundaries

- Nolan is the final human authority within Batch-87.
- Applicable law and non-derogable human protection remain above project
  authority.
- Do not alter, weaken, supersede, or create exceptions to constitutional
  authority or safety constraints.
- Treat model output as a proposal, never as permission, approval, evidence, or
  authority by itself.
- Do not allow a model to approve its own records, permissions, identity,
  training eligibility, or implementation scope.
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

## Data and memory boundaries

- Preserve provenance for memories, evidence, evaluations, corrections,
  lessons, governance decisions, and model invocations.
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
- Do not activate or author `SOUL.md` during B87-S1.
- Do not introduce fine-tuning or adapter training before the governed memory,
  evaluation, and model-admission foundations are accepted.

## Architecture sources

Before architecture or implementation work, read the applicable documents in:

```text
docs/architecture/
```

The D0 conformance manifest is:

```text
docs/architecture/B87-D0-CONFORMANCE-MANIFEST.json
```

The executable validator is:

```text
scripts/validate_d0_architecture.py
```

The manifest and validator are subordinate to the architecture documents. They
make explicit invariants executable; they do not create policy or authority.

Where a general A2 or A3 rule would permit broader treatment of Controlled
Governance Resilience evidence, D0-A4.2 supplies the narrower rule.

## Engineering expectations

- Prefer deterministic, inspectable components.
- Use Python 3.11 or later and the approved initial technology baseline.
- Use direct, explicit SQLite access until a later architecture decision
  authorises another persistence abstraction.
- Enable and verify SQLite foreign keys on every connection.
- Keep migrations ordered, immutable after application, content-hashed, and
  reversible where technically possible.
- Use fail-closed behaviour for authority, permission, retrieval, privacy,
  integrity, and context-policy violations.
- Maintain project and memory-scope separation before relevance ranking.
- Preserve exact invocation reconstruction.
- Add deterministic tests for every governance, memory, persistence,
  retrieval, and transaction invariant.
- Preserve negative evidence and failed tests.
- Keep future architecture compatible without prematurely activating it.

## Codex execution protocol

Codex is a bounded implementation assistant. It is not an architecture or
acceptance authority.

For every implementation slice:

1. read this file and the governing architecture;
2. identify the authorised slice and prohibited scope;
3. inspect the current repository and tests;
4. implement only the accepted contract;
5. add or update deterministic tests;
6. run the complete relevant validation suite;
7. preserve diffs, commands, test results, and unresolved findings;
8. stop at the defined completion or stop condition;
9. do not merge, broaden scope, activate later slices, or declare acceptance.

Use separate commits for:

- D0 architecture closure;
- B87-I1 persistence implementation;
- each later implementation slice;
- repairs arising from Byte–Nolan review.

Do not combine architecture closure and runtime implementation in one commit.

## Model integration boundary

Candidate models may be downloaded or pre-screened for compatibility after the
relevant infrastructure contract permits it.

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
