# B87-I5-B Governance Ordering Addendum

| Field | Value |
| --- | --- |
| Project | Batch-87 Apprentice |
| Applies to | `docs/superpowers/specs/2026-08-29-b87-i5-b-executable-evaluation-subsystem-design.md` |
| Applies to design commit | `2b2de756b49609cd4ee2e1b993ad92e198cece79` |
| Addendum date | 2026-08-29 |
| Scope | Governance-ordering clarification only |

## Purpose

The accepted B87-I5 contract requires the relevant exact subphase release before any B87-I5 implementation edit. The I5-B design's Section 25 could be read as issuing `AUTHORIZE B87-I5-B` only after the harness is implemented. That reading would conflict with the controlling contract.

This addendum resolves the ordering without widening authority or changing the approved research design.

## Controlling ordering

The correct sequence is:

```text
1. Accepted I5-B design and implementation plan
2. Exact Nolan phase release: AUTHORIZE B87-I5-B
3. I5-B implementation and mock/synthetic verification only
4. Executable cases and exact frozen campaign manifest produced
5. Human review and acceptance of that exact executable campaign manifest
6. Formal real-candidate campaign launch
7. H5 blinded evidence review
```

`AUTHORIZE B87-I5-B` is therefore required **before Task 1 implementation begins**.

The phase release authorizes work within the accepted B87-I5-B subphase. It does **not**, by itself, make an as-yet-unbuilt or unreviewed campaign executable.

Formal real-candidate execution additionally requires all of the design's pre-execution conditions, including:

- complete implementation evidence review;
- successful deterministic/mock verification;
- exact executable-case review;
- frozen campaign manifest;
- frozen blind-map commitment;
- human acceptance of the exact executable campaign manifest.

Until those later conditions are satisfied, implementation may use deterministic/mock providers only and must not generate formal candidate-selection evidence.

## Authority preservation

This addendum does not authorize:

- B87-I5-B implementation by itself;
- formal B87-I5-B candidate execution;
- B87-I5-C or B87-I5-D;
- model admission or ranking;
- memory compounding;
- training or weight modification;
- model tools or Execute authority;
- push, PR, merge, tag, force-push, or branch deletion.

The exact phase release remains:

```text
AUTHORIZE B87-I5-B
```

No other text or artifact may substitute for that release.
