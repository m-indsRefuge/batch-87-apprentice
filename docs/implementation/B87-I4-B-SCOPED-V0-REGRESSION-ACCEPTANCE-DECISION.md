# B87-I4-B Scoped V0 Regression Acceptance Decision

Project: Batch-87 Apprentice
Decision date: 2026-07-30
Authority: Nolan
Byte semantic and traceability review: Accepted
Status: Regression-planning documentation accepted; implementation and external
execution unreleased
Accepted decision version: `1.0`
Reviewed source baseline:
`7debc707ff50d00308bb6ab11ffc09f9ffb74397`
Final review packet SHA-256:
`5b664d095ec63f63d0b1295cb8a52ed557cdaab6fd9a5a975578e7104dcebfed`
Reviewed proposed decision SHA-256:
`51bcfd1f663356d2eb19fe4b11291d7b4a9b388056757e81f394970faba5849a`
Final accepted decision-file SHA-256:
`49ab31115a86df6dcc8d966add1818f427ca909735a7d9a523ed16a632cc5cce`
Active implementation release: `NONE`

## Decision

Nolan issued exactly:

```text
ACCEPT B87-I4-B SCOPED V0 REGRESSION DECISION VERSION 1.0
```

Byte completed semantic and traceability review and accepted the final
documentation packet.

The
[B87-I4-B scoped V0 regression decision](B87-I4-B-SCOPED-V0-REGRESSION-DECISION.md)
is accepted as decision version 1.0. It is operative immediately only as the
governing B87-I4-B scoped persistence-regression planning decision.

This documentation-only acceptance satisfies only the regression-planning entry
gate required by section 17 of the accepted B87-I4-B contract. It does not issue
an implementation release or authorize external execution.

## Accepted scope

The accepted classification contains:

- twelve mandatory scoped reruns;
- two conditional reruns; and
- zero excluded or unresolved scenarios.

The accepted classification retains:

- V0-T12 as conditional under its recorded triggers;
- V0-T14 as conditional under its recorded triggers and defined 3,600-second
  workload; and
- V0-T13 as upgraded-only by default, with automatic expansion to both database
  modes when its accepted sufficiency gate fails.

The accepted harness-versioning protocol is:

```text
B87-I4B-HARNESS-FREEZE-MANIFEST-v1.0
```

No historical harness commit was recoverable. None was retroactively invented,
inferred, backdated, or recorded.

The exact future canonical freeze-manifest SHA-256 and scenario-definition
hashes do not yet exist. They may be generated only after the separately
authorized implementation candidate and executable scenario adaptations are
complete, and they remain mandatory preconditions for external execution.

The accepted decision preserves the complete migration, raw-output,
interruption, reconstruction, idempotency, concurrency, evidence,
negative-control, pass, failure, and stop-condition plan reviewed by Byte.

## Preserved V0 state

B87-V0 remains accepted and closed. This acceptance does not reopen, replace,
invalidate, rerun, or rewrite the accepted historical V0 closure.

Contract or planning acceptance does not transfer B87-V0 acceptance to a future
I4-B candidate baseline. That future candidate must receive its own complete,
reproducible scoped result under the accepted decision before it can be
considered for acceptance.

## Implementation and external-execution boundary

The active implementation release remains:

```text
NONE
```

B87-I4-B implementation remains not authorized.

The only future B87-I4-B runtime release token remains:

```text
AUTHORIZE B87-I4-B
```

Any future release must identify accepted regression-decision version 1.0 and
this acceptance record:

```text
docs/implementation/B87-I4-B-SCOPED-V0-REGRESSION-ACCEPTANCE-DECISION.md
```

External regression remains prohibited until:

1. the separately authorized I4-B implementation is complete and internally
   passing;
2. the exact candidate commit is frozen;
3. the executable external scenario adaptations are complete;
4. a valid `B87-I4B-HARNESS-FREEZE-MANIFEST-v1.0` is generated and recorded; and
5. every other accepted external-execution precondition is satisfied.

Decision acceptance precedes implementation authorization. External execution
follows candidate freeze.

Regression evidence, a test result, a model output, a harness classification,
or a Codex report cannot accept its own result, issue implementation authority,
or accept a future candidate.

Nolan retains exclusive runtime-release authority and exclusive final
candidate-acceptance authority.

## Explicit non-authorization

This acceptance does not authorize:

- runtime implementation;
- migrations or schemas;
- provider execution;
- a real model, model server, endpoint, or API;
- credentials, network access, or tools;
- external regression execution;
- Validation V1;
- B87-PRE-I5 or B87-I5;
- training, fine-tuning, evaluation, or experimental capability.

No repository document, test, model output, Codex statement, prior phase
release, or regression evidence may infer any of those authorities from this
acceptance.

## Accepted review evidence

The accepted review evidence is:

- reviewed source baseline
  `7debc707ff50d00308bb6ab11ffc09f9ffb74397`;
- final review packet SHA-256
  `5b664d095ec63f63d0b1295cb8a52ed557cdaab6fd9a5a975578e7104dcebfed`;
- reviewed proposed decision SHA-256
  `51bcfd1f663356d2eb19fe4b11291d7b4a9b388056757e81f394970faba5849a`;
  and
- final accepted decision-file SHA-256
  `49ab31115a86df6dcc8d966add1818f427ca909735a7d9a523ed16a632cc5cce`.

These hashes identify the accepted review lineage and final decision file. They
do not authorize implementation or external execution.
