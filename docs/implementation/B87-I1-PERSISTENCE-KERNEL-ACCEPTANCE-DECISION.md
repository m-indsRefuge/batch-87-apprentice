# B87-I1 Persistence Kernel Acceptance Decision

Project: Batch-87 Apprentice
Phase: B87-I1 - Persistence Kernel
Status: Accepted, merged, validated, and closed
Decision date: 2026-07-24
Authority: Nolan
Accepted implementation commit: 51307bebd8980a10c36980fae4b1e09dee20a6db
Merge commit: dde512942fb40f099749a57258c47a5388cceaa3
Merged pull request: #4
Next eligible phase: B87-I2 - Governed Task Runtime
Active implementation release: NONE

## Decision

Nolan issued:

    ACCEPT B87-I1

B87-I1 is accepted as the governed persistence foundation for the Batch-87
Apprentice.

Acceptance followed complete automated tests, strict D0 validation, real
file-backed SQLite validation, separate-process reopening, negative mutation
tests, semantic review, and post-merge validation.

## Accepted boundary

B87-I1 establishes governed SQLite persistence, immutable migrations, governed
record and evidence storage, controlled-resilience isolation, integrity
inspection, and explicit transaction boundaries.

It does not establish model behaviour, memory efficacy, retrieval, context
assembly, model invocation, model suitability, training readiness, identity,
deployment, autonomous action, or external-tool authority.

## Next phase

B87-I2 is eligible but not active.

It may begin only after Nolan separately issues:

    AUTHORIZE B87-I2

B87-I3 and later phases remain unauthorised.
