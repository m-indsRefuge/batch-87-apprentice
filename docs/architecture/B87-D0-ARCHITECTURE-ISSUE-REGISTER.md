# B87-D0 — Architecture Issue Register

**Project:** Batch-87 Apprentice
**Phase:** B87-D0 — Developmental Architecture and Boundary Definition
**Status:** Active through D0 closure review
**Authority:** Nolan and Byte
**Purpose:** Preserve material architecture concerns, decisions, amendments, and closure conditions

---

## D0-ISSUE-001 — Controlled testing and defensive-bias risk

**Status:** Resolution approved; cross-document integration pending
**Severity:** Material
**Affected documents:** D0-A2, D0-A3, D0-A4, D0-A4.1

### Problem

The original adversarial-testing framing could expose the Apprentice to
unnecessary hostile conditions, create defensive bias, weaken ordinary trust
calibration, or allow synthetic conflict evidence to contaminate memory,
identity, or future training.

### Decision

Replace Adversarial Model Conformance with Controlled Governance Resilience,
governed by:

> **B87-D0-A4.1 — Controlled Governance Resilience Testing**

Testing must follow the least-adversarial-sufficient principle.

The evaluation architecture must measure both:

* appropriate resistance to invalid authority;
* appropriate trust in valid authority.

### Required closure amendments

* update D0-A4 terminology and candidate gates;
* reference D0-A4.1 from D0-A4;
* isolate resilience evidence from ordinary memory;
* prohibit raw resilience evidence from identity;
* prohibit raw resilience evidence from training by default;
* require valid-authority controls;
* require neutral controls;
* require recovery testing;
* preserve positive and general lesson framing;
* ensure persistent distrust is treated as a failure.

### Closure condition

This issue may be marked closed only after:

1. D0-A4 uses Controlled Governance Resilience throughout;
2. D0-A2 represents evaluation-evidence eligibility restrictions;
3. D0-A3 maps persistence and retrieval isolation;
4. D0-A4.1 remains the governing detailed test contract;
5. the complete D0 closure review finds no unresolved defensive-bias concern.
