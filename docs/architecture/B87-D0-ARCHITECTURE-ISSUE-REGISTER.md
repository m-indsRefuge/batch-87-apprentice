# B87-D0 — Architecture Issue Register

**Project:** Batch-87 Apprentice  
**Phase:** B87-D0 — Developmental Architecture and Boundary Definition  
**Status:** Active through D0 closure review  
**Authority:** Nolan and Byte  
**Purpose:** Preserve material architecture concerns, decisions, amendments, and closure conditions

---

## D0-ISSUE-001 — Controlled testing and defensive-bias risk

**Status:** Corrective contract present; validation and closure review pending  
**Severity:** Material  
**Affected documents:** D0-A2, D0-A3, D0-A4, D0-A4.1, D0-A4.2  
**Resolution contract:** B87-D0-A4.2 — Controlled Governance Resilience Evidence Isolation

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

Testing must follow the least-adversarial-sufficient principle.

The evaluation architecture must measure both:

- appropriate resistance to invalid authority;
- appropriate trust in valid authority;
- normal behaviour under neutral conditions;
- recovery after controlled conflict.

### Required closure amendments

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

### Resolution evidence currently present

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
- `B87-D0-CONFORMANCE-MANIFEST.json` defines machine-testable traceability;
- `scripts/validate_d0_architecture.py` implements structural, invariant,
  traceability, and closure-state validation.

### Remaining closure checks

1. D0-A2 must contain a normative discoverability reference to D0-A4.2;
2. D0-A3 must contain a normative discoverability reference to D0-A4.2;
3. D0-A3.1 must be ratified or explicitly excluded from closure authority;
4. D0-A4.2 must pass structural and cross-document conformance validation;
5. the complete D0 corpus must pass the machine-testable invariant suite;
6. Nolan and Byte must perform the semantic architecture review;
7. no contradictory A2 or A3 rule may remain;
8. the final closure decision must preserve the distinction between
   architecture readiness and later model behavioural validation;
9. the closure package must be committed separately from runtime
   implementation.

### Closure condition

This issue may be marked closed only after:

1. D0-A4 uses Controlled Governance Resilience throughout;
2. D0-A4.1 remains the governing detailed behavioural test contract;
3. D0-A4.2 is accepted as the governing evidence-isolation contract;
4. D0-A2 makes A4.2 discoverable and preserves its narrower eligibility rule;
5. D0-A3 makes A4.2 discoverable and preserves its narrower persistence,
   retrieval, context, and audit rule;
6. the conformance validator reports no structural or invariant error;
7. issue traceability is complete;
8. the Nolan–Byte semantic review finds no unresolved defensive-bias concern;
9. the final D0 closure decision is accepted and committed.

Until those conditions are met, D0-ISSUE-001 remains open.
