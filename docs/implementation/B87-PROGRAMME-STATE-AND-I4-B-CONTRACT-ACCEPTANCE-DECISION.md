# B87 Programme-State and I4-B Contract Acceptance Decision

Project: Batch-87 Apprentice
Decision date: 2026-07-30
Authority: Nolan
Byte semantic review: Accepted
Status: Documentation accepted; implementation unreleased
Reviewed source baseline: `a91c82f7c68143b26b655a05fcbc6571e5358006`
Final review packet SHA-256:
`21945f165f46e93e8d90e08614fbb515ffa5aa21eb8451ff03e7034afd2e9ba2`
Accepted I4-B contract SHA-256:
`c94c20e198c314478a3658465343ada208f5ee2ef0606856bf7a336657226e37`
Active implementation release: `NONE`

## Decision

Nolan issued exactly:

```text
ACCEPT B87 PROGRAMME-STATE RECONCILIATION AND I4-B CONTRACT
```

Byte completed semantic review and accepted the final documentation packet.

The following documentation is accepted:

1. `B87-PROGRAMME-STATE-RECONCILIATION-THROUGH-I4-A-AND-V0.md`;
2. `B87-I4-B-PROVIDER-NEUTRAL-MODEL-AND-INVOCATION-BRIDGE-CONTRACT.md`,
   contract version 1.0.

This is a documentation-only acceptance. It records the reconciled programme
state and accepts the bounded I4-B contract without issuing an implementation
release.

## Implementation release boundary

The active implementation release remains:

```text
NONE
```

B87-I4-B implementation is not authorized.

The only future runtime release token for B87-I4-B remains:

```text
AUTHORIZE B87-I4-B
```

Before that token can release implementation, the requirement for a separately
accepted scoped B87-V0 regression decision under section 17 of the I4-B contract
remains an unsatisfied implementation entry gate.

Contract acceptance does not transfer B87-V0 acceptance from source baseline
`093e07a6aa9209a6ea8efe2aaecfcbdeb6829d0a` to a future B87-I4-B baseline. Any
future I4-B persistence baseline must receive the separately accepted scoped V0
regression decision and evidence required by the contract.

## Current scoped-regression planning status

Scoped V0 regression decision version 1.0 and its acceptance decision were
subsequently accepted:

```text
docs/implementation/B87-I4-B-SCOPED-V0-REGRESSION-DECISION.md
docs/implementation/B87-I4-B-SCOPED-V0-REGRESSION-ACCEPTANCE-DECISION.md
```

That later acceptance satisfies the previously unsatisfied regression-planning
entry gate without rewriting this record's original decision-time state. It
does not authorize I4-B implementation, issue `AUTHORIZE B87-I4-B`, transfer V0
acceptance, or change active implementation release `NONE`. Any future runtime
release must identify accepted regression-decision version 1.0 and its
acceptance record. B87-V0 remains accepted and closed. External regression
remains prohibited until the exact candidate commit and a valid
`B87-I4B-HARNESS-FREEZE-MANIFEST-v1.0` are frozen and every other accepted
external-execution precondition is satisfied.

## Explicit non-authorization

This decision does not authorize:

- runtime implementation;
- migrations or schema changes;
- a real provider;
- a model, model server, endpoint, or API;
- a credential;
- a tool or expanded Apprentice permission;
- evaluation or Validation V1;
- training or identity progression;
- B87-PRE-I5 or B87-I5; or
- B87-E0, B87-E1, B87-E2, or other experimental capability.

No documentation, test, model output, Codex statement, or prior phase release
may infer implementation authority from this acceptance.

## Accepted evidence

The accepted final review evidence is:

```text
final_review_packet_sha256:
21945f165f46e93e8d90e08614fbb515ffa5aa21eb8451ff03e7034afd2e9ba2

accepted_i4_b_contract_sha256:
c94c20e198c314478a3658465343ada208f5ee2ef0606856bf7a336657226e37

reviewed_source_baseline:
a91c82f7c68143b26b655a05fcbc6571e5358006
```

This decision accepts documentation only. It does not alter an earlier
decision's original decision-time state or reopen an accepted historical
record.
