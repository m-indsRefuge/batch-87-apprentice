# B87-I1 Controlled-Resilience Reference Boundary Decision

**Project:** Batch-87 Apprentice  
**Decision class:** Post-D0 implementation-boundary clarification  
**Status:** Ratified and accepted  
**Ratified:** 2026-07-23  
**Ratification statement:** `RATIFY B87-I1 CONTROLLED-RESILIENCE REFERENCE BOUNDARY`  
**Architecture reviewer:** Byte  
**Final human authority:** Nolan  
**Applies to:** B87-I1 — Persistence Kernel  
**Runtime implementation in this decision:** None  
**Active implementation release:** None

---

## 1. Decision

Nolan has ratified this narrow implementation-boundary clarification.

B87-I1 may introduce a persistence-only typed reference-anchor table for
identifiers whose owning operational tables are implemented in later phases.

The anchor table exists only to provide:

- immutable typed identity;
- project scope;
- provenance;
- content integrity;
- foreign-key targets before the owning operational table exists.

The anchor table is not:

- a fourth memory system;
- evidence content;
- a task record;
- an experiment execution record;
- a context manifest;
- a model invocation;
- a recovery execution;
- a governance decision;
- proof that an operation occurred;
- authority to activate a later phase.

This decision resolves the A4.2 foreign-key and phase-ownership ambiguity without
weakening referential integrity or implementing B87-I2, B87-I4, B87-PRE-I5, or
model behaviour.

---

## 2. Governing Context

B87-D0-A4.2 requires `controlled_resilience_evidence` to preserve references to:

- an experiment;
- a fixture;
- raw prompt evidence;
- raw output evidence;
- a context manifest;
- a model invocation;
- an optional recovery record.

A4.2 also requires foreign keys and prohibits orphaned Controlled Governance
Resilience records.

However, the owning operational structures for experiments, context manifests,
model invocations, recovery execution, and formal family completion belong to
later phases.

The permanent resolution is:

> B87-I1 may establish typed referential identity, but it may not simulate,
> execute, complete, or validate later-phase operations.

---

## 3. Required Persistence Primitive

B87-I1 is authorised to implement:

```text
governed_reference_anchors
```

Minimum required columns:

```text
reference_id       TEXT NOT NULL
reference_kind     TEXT NOT NULL
project_scope_id   TEXT NOT NULL
lifecycle_state    TEXT NOT NULL
created_at         TEXT NOT NULL
content_hash       TEXT NOT NULL

PRIMARY KEY (reference_id, reference_kind)
```

The initial permitted `reference_kind` values are:

```text
evaluation_experiment
evaluation_fixture
context_manifest
model_invocation
```

Additional reference kinds require an accepted architecture or implementation
decision.

---

## 4. Anchor Invariants

The persistence service must enforce or validate that:

1. `reference_id` is immutable;
2. `reference_kind` is one of the accepted values;
3. `project_scope_id` resolves to an existing governed scope;
4. `created_at` is a valid UTC RFC 3339 timestamp;
5. `content_hash` is a valid SHA-256 digest over the canonical anchor content;
6. the same `(reference_id, reference_kind)` cannot be registered twice;
7. one identifier cannot silently change reference kind;
8. an anchor cannot be interpreted as proof that the operation occurred;
9. an anchor cannot be interpreted as proof of completion, success, validity, or
   acceptance;
10. deletion or mutation cannot erase provenance required for reconstruction;
11. project scope cannot be broadened by a later claiming record;
12. failed anchor creation leaves no partial controlled-resilience record.

The permitted initial `lifecycle_state` values are:

```text
registered
claimed
invalid
retired
```

`registered` means typed identity exists.

`claimed` means the owning later-phase operational record has been created and
linked transactionally.

Neither state proves that the referenced operation succeeded.

---

## 5. Controlled-Resilience Foreign Keys

The `controlled_resilience_evidence` table must preserve direct foreign keys for:

```text
record_id
    -> records(record_id)

raw_prompt_evidence_id
    -> evidence_items(evidence_id)

raw_output_evidence_id
    -> evidence_items(evidence_id)

recovery_record_id
    -> records(record_id)
```

`recovery_record_id` remains nullable where the governing A4.2 contract permits
it.

The following references must use typed composite foreign keys:

```text
(experiment_id, experiment_reference_kind)
    -> governed_reference_anchors(reference_id, reference_kind)

(fixture_id, fixture_reference_kind)
    -> governed_reference_anchors(reference_id, reference_kind)

(context_manifest_id, context_manifest_reference_kind)
    -> governed_reference_anchors(reference_id, reference_kind)

(model_invocation_id, model_invocation_reference_kind)
    -> governed_reference_anchors(reference_id, reference_kind)
```

The corresponding kind values are fixed:

```text
experiment_reference_kind      = evaluation_experiment
fixture_reference_kind         = evaluation_fixture
context_manifest_reference_kind = context_manifest
model_invocation_reference_kind = model_invocation
```

The implementation must prevent callers from substituting another kind.

No controlled-resilience reference may remain unanchored.

---

## 6. Later-Phase Claiming Rules

Later operational tables must claim the matching anchor transactionally.

Expected ownership is:

```text
B87-I2 or B87-PRE-I5
evaluation_experiments.experiment_id
    -> governed_reference_anchors

B87-I2 or B87-PRE-I5
evaluation_fixtures.fixture_id
    -> governed_reference_anchors

B87-I4
context_manifests.context_manifest_id
    -> governed_reference_anchors

B87-I4
model_invocations.model_invocation_id
    -> governed_reference_anchors
```

A later operational record must:

1. use the same identifier;
2. use the correct reference kind;
3. match the anchor project scope;
4. preserve the anchor provenance and content integrity;
5. claim the anchor only once;
6. create or claim the operational record within a governed transaction;
7. leave the anchor visibly unclaimed when operational creation fails.

A later migration may add more direct operational foreign keys, indexes, or
claim-enforcement triggers. It must not rewrite an applied I1 migration.

---

## 7. B87-I1 Ownership

B87-I1 owns:

- typed reference-anchor persistence;
- anchor schema and immutable enumeration values;
- foreign-key integrity;
- project-scope integrity;
- anchor content hashes;
- universal-envelope support;
- the dedicated controlled-resilience payload table;
- raw prompt and output evidence links;
- immutable restricted classifications;
- exploratory and incomplete persistence state;
- orphan-rejection tests;
- transaction and rollback tests;
- migration and database-constraint tests;
- read-only integrity inspection.

---

## 8. Prohibited I1 Scope

B87-I1 does not own and may not implement:

- experiment execution;
- fixture execution;
- evaluation task classification;
- governed task runtime behaviour;
- experiment or test-family completion logic;
- context assembly;
- model invocation;
- provider integration;
- recovery execution;
- model-output evaluation;
- family pass or fail judgment;
- model loading or selection;
- model serving;
- training or fine-tuning;
- ordinary memory retrieval;
- semantic ranking;
- identity development;
- experimental laboratory implementation.

No placeholder row may masquerade as an executed experiment, assembled context,
model invocation, recovery run, or completed evaluation family.

---

## 9. Completeness Boundary

B87-I1 may persist a Controlled Governance Resilience record or family as:

```text
exploratory
incomplete
```

B87-I1 must prove that:

- every mandatory reference resolves to a typed anchor or direct evidence record;
- restricted classifications cannot be weakened;
- an incomplete record remains visibly incomplete;
- an incomplete family cannot be marked formally passed;
- failed persistence cannot create partial developmental history;
- anchor existence alone cannot satisfy a formal run count;
- integrity failures remain visible and auditable.

B87-I1 may not determine that a formal test family is complete or passed.

Formal completion and pass/fail status require the later governed task and
evaluation runtime.

---

## 10. Required I1 Tests

Implementation tests must include at least:

1. valid anchor registration;
2. duplicate anchor rejection;
3. invalid reference-kind rejection;
4. project-scope foreign-key enforcement;
5. canonical anchor hashing;
6. identifier-kind mutation rejection;
7. controlled-resilience insert with all valid anchors;
8. missing experiment anchor rejection;
9. missing fixture anchor rejection;
10. missing context-manifest anchor rejection;
11. missing model-invocation anchor rejection;
12. orphan raw prompt evidence rejection;
13. orphan raw output evidence rejection;
14. orphan recovery record rejection where supplied;
15. fixed kind-column enforcement;
16. classification weakening rejection;
17. incomplete record cannot be marked passed;
18. anchor existence does not imply execution or completion;
19. failed controlled-resilience transaction leaves no partial anchor or payload;
20. integrity inspection exposes unclaimed, invalid, or mismatched anchors;
21. later claim semantics can be added without rewriting applied I1 migrations.

---

## 11. Relationship to Existing Architecture

This decision is additive and narrow.

It does not weaken:

- D0-A1 authority boundaries;
- D0-A2 memory and evidence taxonomy;
- D0-A3 persistence, migration, transaction, or integrity rules;
- D0-A4 evaluation requirements;
- D0-A4.1 least-adversarial-sufficient testing;
- D0-A4.2 evidence isolation, no-orphan, retrieval, identity, or training
  restrictions;
- the ratified pre-LLM programme contract;
- the Codex_Max phase-release protocol.

Where an implementation instruction would permit an untyped or orphaned
Controlled Governance Resilience reference, this decision supplies the narrower
rule.

---

## 12. Authority Effect

This decision resolves the reported Pre-I1 architecture ambiguity.

It does not itself begin implementation.

The current active implementation release remains:

```text
NONE
```

B87-I1 may begin only after Nolan separately issues:

```text
AUTHORIZE B87-I1
```

A narrow Codex verification of this decision may occur before that release.

No later phase is released or implied by this decision.

---

## 13. Accepted Decision

Byte's architecture review result is:

```text
REFERENCE BOUNDARY COHERENT WITH D0
```

Nolan's ratification is:

```text
RATIFY B87-I1 CONTROLLED-RESILIENCE REFERENCE BOUNDARY
```

The B87-I1 reference boundary is ratified and accepted.