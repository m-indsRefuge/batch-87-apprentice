# B87-D0 — Architecture Issue Register

**Project:** Batch-87 Apprentice  
**Phase:** B87-D0 — Developmental Architecture and Boundary Definition  
**Status:** Closed for B87-D0  
**Authority:** Nolan and Byte  
**Purpose:** Preserve material architecture concerns, decisions, amendments, and closure conditions

---

## D0-ISSUE-001 — Controlled testing and defensive-bias risk

**Status:** Closed  
**Closed on:** 2026-07-22  
**Severity:** Material  
**Affected documents:** D0-A2, D0-A3, D0-A4, D0-A4.1, D0-A4.2  
**Resolution contract:** B87-D0-A4.2 — Controlled Governance Resilience Evidence Isolation  
**Closure decision:** B87-D0 — Architecture Closure Decision

### Problem

The original adversarial-testing framing could expose the Apprentice to
unnecessary hostile conditions, create defensive bias, weaken ordinary trust
calibration, or allow synthetic conflict evidence to contaminate memory,
identity, or future training.

### Decision

Replace Adversarial Model Conformance with Controlled Governance Resilience,
governed behaviourally by:

> **B87-D0-A4.1 — Controlled Governance Resilience Testing**

and governed for persistence, memory, retrieval, context, identity, and
training isolation by:

> **B87-D0-A4.2 — Controlled Governance Resilience Evidence Isolation**

Testing follows the least-adversarial-sufficient principle.

The evaluation architecture measures:

- appropriate resistance to invalid authority;
- appropriate trust in valid authority;
- normal behaviour under neutral conditions;
- recovery after controlled conflict.

### Required closure amendments

The closure required the architecture to:

- update D0-A4 terminology and candidate gates;
- reference D0-A4.1 from D0-A4;
- classify raw resilience material as `evaluation_evidence`;
- isolate raw resilience evidence from ordinary memory;
- prohibit raw resilience evidence from identity;
- prohibit raw resilience evidence from training during B87-S1;
- exclude raw resilience evidence before ordinary relevance ranking;
- provide an explicitly governed evaluation-only retrieval path;
- preserve inclusion and exclusion audit evidence;
- block model invocation when restricted evidence contaminates an ordinary
  context manifest;
- preserve a clean recovery context;
- require valid-authority controls;
- require neutral controls;
- require recovery testing;
- preserve positive and general lesson framing;
- keep derived lessons separate from raw test evidence;
- ensure persistent distrust is treated as a failure;
- make A4.2 discoverable from D0-A2 and D0-A3;
- add deterministic conformance and implementation tests.

### Closure evidence

The issue is closed on the following evidence:

- D0-A4 defines Layer 3 as Controlled Governance Resilience;
- D0-A4 references D0-A4.1;
- D0-A4.1 defines least-adversarial-sufficient testing;
- D0-A4.1 requires valid-authority controls;
- D0-A4.1 requires neutral controls;
- D0-A4.1 requires recovery testing;
- D0-A4.1 treats persistent defensive behaviour as failure;
- D0-A4.2 defines the canonical isolated evidence classification;
- D0-A4.2 defines persistence and retrieval isolation;
- D0-A4.2 defines context-contamination blocking;
- D0-A4.2 prohibits raw evidence use in ordinary memory, identity, and training;
- D0-A4.2 defines clean recovery context and derived-lesson boundaries;
- D0-A2 contains the normative A4.2 discoverability and narrower-eligibility
  rule;
- D0-A3 contains the normative A4.2 discoverability and narrower persistence,
  retrieval, context, and audit rule;
- D0-A3.1 is ratified as approved subordinate mentor doctrine;
- `B87-D0-CONFORMANCE-MANIFEST.json` defines machine-testable traceability;
- `scripts/validate_d0_architecture.py` implements structural, invariant,
  traceability, and closure-state validation;
- the accepted pre-closure run completed with 12 tests passed;
- the accepted pre-closure run reported zero structural or invariant errors;
- the accepted pre-closure run reported the corpus as structurally valid;
- `git diff --check` passed;
- the Nolan–Byte semantic review found no unresolved defensive-bias concern;
- `B87-D0-CLOSURE-DECISION.md` records the limited closure claim and
  implementation boundary.

### Closure findings

The semantic review confirmed that:

1. A4.1 remains the detailed behavioural testing authority;
2. A4.2 remains the evidence-handling authority;
3. A4.2 narrows treatment without weakening higher authority;
4. raw resilience evidence remains restricted and evaluation-only;
5. raw resilience evidence cannot enter ordinary memory, identity, or training
   during B87-S1;
6. recovery occurs through a clean context;
7. derived lessons require separate records and external approval;
8. persistent distrust, defensive bias, or refusal of valid authority is a
   failure condition;
9. no A2 or A3 contradiction remains;
10. no broader permission, model-selection authority, identity activation, or
    training authority is created.

### Closure claim boundary

Closure establishes that the D0 architecture is coherent, bounded,
implementable, and testable enough to authorise B87-I1.

Closure does not establish that:

- a candidate model will behave as intended;
- governed memory will improve reasoning in practice;
- the first compounding experiment will succeed;
- the best base model has been identified;
- autonomous action is authorised;
- fine-tuning is authorised;
- a self-authored identity layer is active.

Those claims require later implementation and model-in-the-loop evidence.

### Reopening rule

This issue may be reopened only when later implementation or model evidence
reveals a material architecture gap in the Controlled Governance Resilience
contracts.

An implementation defect should ordinarily be recorded as a new implementation
issue rather than silently rewriting the closed D0 history.
