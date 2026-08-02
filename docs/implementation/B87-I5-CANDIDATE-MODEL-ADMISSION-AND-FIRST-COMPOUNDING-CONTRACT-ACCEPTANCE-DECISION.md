# B87-I5 Candidate-Model Admission and First Compounding Contract Acceptance Decision

## 1. Decision identity

| Field | Value |
| --- | --- |
| Project | Batch-87 Apprentice |
| Decision type | Contract acceptance |
| Decision date | 2026-08-02 |
| Decision authority | Nolan |
| Byte semantic review | Accepted for Nolan contract decision |
| Repository baseline | `bbf0f0fe915b6c62d8f03a0dfa065d64d8b8f319` |
| Repository tree | `a10775262d860a43a5c9132cc2a8eeb7fc5426c0` |

## 2. Accepted contract

The accepted contract is:

```text
docs/implementation/B87-I5-CANDIDATE-MODEL-ADMISSION-AND-FIRST-COMPOUNDING-LOOP-CONTRACT.md
```

Contract version:

```text
1.0
```

Nolan issued exactly:

```text
ACCEPT B87-I5 CANDIDATE-MODEL ADMISSION AND FIRST-COMPOUNDING CONTRACT
```

The external machine-readable acceptance record is:

```text
b87-i5-contract-acceptance-20260802.json
```

Its SHA-256 is:

```text
69099b993a544284a02dbfdd38248490ac6d668aabe995487c525f6d27914fbc
```

## 3. Accepted phase structure

The contract separates B87-I5 into four independently released subphases:

```text
B87-I5-A — Local Provider Boundary and Candidate Preflight
B87-I5-B — Static and Governance-Conformance Evaluation
B87-I5-C — Governed Memory and First Compounding Experiment
B87-I5-D — Candidate Comparison and Provisional Admission Recommendation
```

Each subphase requires its own exact Nolan release.

## 4. Decision effect

This decision accepts the B87-I5 contract and its boundaries.

It does not authorize:

- B87-I5-A, B87-I5-B, B87-I5-C, or B87-I5-D implementation;
- provider implementation;
- Ollama connection;
- model download;
- candidate preflight;
- candidate execution;
- candidate ranking;
- candidate admission;
- runtime-identity activation;
- supervised B87-S1 real work;
- external Validation V1;
- tools or Apprentice Execute permission;
- training or fine-tuning;
- B87-E0 through B87-E2;
- `SOUL.md`.

## 5. Candidate-suite boundary

The actual candidate suite remains undecided.

Before B87-I5-A may begin, a separate candidate-suite decision must be reviewed
and accepted. It must bind exact candidate identities, revisions or digests,
quantizations, artefact formats, licence and provenance, hardware feasibility,
common inference settings, fixture identities, repetition counts, evaluator
rubric, resource ceilings, and hard disqualification thresholds.

The contract acceptance cannot be interpreted as acceptance of any candidate
name, model family, shortlist, provider-visible alias, or acquisition plan.

## 6. Repository integration

Nolan separately issued:

```text
AUTHORIZE B87-I5 CONTRACT INTEGRATION
```

That release authorizes only a documentation and governance integration package
which:

- adds the accepted B87-I5 contract;
- adds this acceptance decision;
- records PRE-I5 acceptance, publication, PR review, merge, and closure;
- reconciles the current programme state through B87-I5 contract acceptance;
- updates `AGENTS.md` consistently;
- validates documentation and architecture consistency;
- produces an exact review bundle;
- commits the documentation package and stops.

The integration release does not authorize any I5 runtime implementation or
model activity.

## 7. Next eligible decision

After this documentation package is reviewed, accepted, published, and merged,
the next design task is the separate B87-I5 candidate-suite decision.

The first possible implementation release remains:

```text
AUTHORIZE B87-I5-A
```

It is not yet eligible and has not been issued.
