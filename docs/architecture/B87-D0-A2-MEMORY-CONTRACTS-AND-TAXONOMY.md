# B87-D0-A2 — Memory Contracts and Taxonomy

**Project:** Batch-87 Apprentice
**Phase:** B87-D0 — Developmental Architecture and Boundary Definition
**Slice:** D0-A2
**Status:** Architecture baseline
**Implementation status:** Not yet implemented
**Authority:** Nolan and Byte
**Applies to:** B87-S1 — Governed Memory Apprentice
**Depends on:** B87-D0-A1 — Governing Architecture Baseline

---

## 1. Purpose

This document defines the formal memory taxonomy and contracts for the Batch-87 Apprentice.

It specifies:

* the exact memory domains;
* valid memory record types;
* required common fields;
* domain-specific payloads;
* provenance requirements;
* approval states;
* sensitivity classifications;
* authority classifications;
* retention and review rules;
* relationships between records;
* supersession, revocation, archival, and deletion;
* retrieval eligibility;
* project and subject scoping;
* the boundary between memory, evidence, evaluation, identity, and training data.

This architecture must be accepted before the SQLite schema, runtime protocols, retrieval engine, or compounding-memory experiment are implemented.

---

## 2. Memory System Objective

The purpose of memory is not to preserve every conversation indefinitely.

The purpose of memory is to provide the Apprentice with reliable, scoped, governed continuity.

A valid memory must help the system answer at least one of these questions:

### Construct and relational memory

> What accepted facts, relationships, projects, doctrines, and authorities define the environment in which I operate?

#### Self and episodic memory

> What have I experienced, how did I perform, and what reviewed lessons should influence my future behaviour?

#### Session and task memory

> What am I doing now, which context applies, and what restrictions govern this task?

Information that does not serve one of these purposes should not automatically become durable memory.

---

## 3. Memory Is Not Evidence

Memory and evidence are related but distinct.

### Evidence

Evidence is an original or authoritative source, such as:

* a project decision document;
* a repository snapshot;
* a test report;
* a log;
* a task input;
* a model output;
* a human correction;
* a legal source;
* a recorded evaluation;
* a system-generated event.

### Memory

Memory is a structured, scoped interpretation or durable record derived from evidence.

Example:

```text
Evidence:
A validation report shows 141 tests passed.

Memory:
Constellation D2-A2.1 had an accepted validation baseline of 141 passing tests
at the recorded revision.
```

The memory must retain a reference to the evidence.

A memory without provenance is not eligible to become active.

---

## 4. Top-Level Record Families

Batch-87 will use the following persistent record families:

```text
Evidence records
Construct memory records
Self-model records
Episode records
Correction records
Lesson records
Session records
Task records
Retrieval records
Evaluation records
Governance decision records
Identity proposal records
Training-candidate records
```

Not every record family is itself a memory domain.

The three approved memory systems remain:

1. Construct and relational memory;
2. self and episodic memory;
3. session and task memory.

The remaining record families support governance, evaluation, evidence, identity development, and later training.

---

## 5. Universal Record Contract

Every persistent Batch-87 record must implement a universal envelope.

### 5.1 Required identifiers

Each record must contain:

| Field            | Purpose                                                        |
| ---------------- | -------------------------------------------------------------- |
| `record_id`      | Globally unique immutable identifier                           |
| `record_family`  | High-level family such as `construct_memory` or `episode`      |
| `record_type`    | Specific subtype                                               |
| `schema_version` | Version of the contract used to validate the record            |
| `created_at`     | UTC creation timestamp                                         |
| `created_by`     | Human, agent, runtime, evaluator, or migration that created it |

### 5.2 Scope fields

| Field             | Purpose                                                                      |
| ----------------- | ---------------------------------------------------------------------------- |
| `construct_scope` | The wider Construct or named sub-environment                                 |
| `project_scope`   | Batch-87, Constellation, The Signal, Lighthouse, or another approved project |
| `subject_scope`   | Person, agent, repository, component, policy, task, or system concerned      |
| `session_id`      | Applicable session reference, when relevant                                  |
| `task_id`         | Applicable task reference, when relevant                                     |

A record must never rely on an ambiguous unscoped use of words such as “the project,” “the agent,” or “the repository.”

### 5.3 State fields

| Field                     | Purpose                                                                                    |
| ------------------------- | ------------------------------------------------------------------------------------------ |
| `lifecycle_state`         | Observed, candidate, reviewed, approved, active, superseded, revoked, archived, or deleted |
| `approval_status`         | Not required, pending, approved, rejected, or withdrawn                                    |
| `effective_from`          | Date from which the record applies                                                         |
| `effective_until`         | Optional expiry or end date                                                                |
| `review_due_at`           | Optional mandatory review date                                                             |
| `supersedes_record_id`    | Earlier record explicitly replaced                                                         |
| `superseded_by_record_id` | Newer record that replaced this record                                                     |

### 5.4 Provenance fields

| Field                | Purpose                                                                                                  |
| -------------------- | -------------------------------------------------------------------------------------------------------- |
| `source_kind`        | Human statement, project document, test, runtime event, model output, external source, or derived record |
| `source_references`  | One or more evidence identifiers                                                                         |
| `provenance_summary` | Concise explanation of how the record was produced                                                       |
| `authority_class`    | Level of authority supporting the record                                                                 |
| `certainty_class`    | Verified, strongly supported, inferred, speculative, disputed, or unknown                                |

### 5.5 Governance fields

| Field                  | Purpose                                                                                   |
| ---------------------- | ----------------------------------------------------------------------------------------- |
| `sensitivity_class`    | Public, internal, confidential, restricted, or secret                                     |
| `privacy_class`        | None, personal, sensitive personal, credential, legally restricted, or unknown            |
| `retention_class`      | Ephemeral, temporary, project-duration, long-term, permanent-history, or legally governed |
| `retrieval_policy`     | Rules controlling who and what tasks may retrieve the record                              |
| `deletion_policy`      | Conditions requiring deletion or redaction                                                |
| `agent_write_policy`   | Prohibited, candidate-only, or externally approved                                        |
| `training_eligibility` | Ineligible, pending review, approved, or prohibited                                       |

### 5.6 Integrity fields

| Field                 | Purpose                                         |
| --------------------- | ----------------------------------------------- |
| `content_hash`        | Hash of the canonical record content            |
| `evidence_hashes`     | Optional hashes for linked local evidence       |
| `previous_version_id` | Earlier version of the same logical record      |
| `integrity_status`    | Valid, mismatch, unavailable, or not applicable |

---

## 6. Enumerated Lifecycle States

The following lifecycle states are authoritative.

### `observed`

An event or source exists.

No durable interpretation has yet been approved.

### `candidate`

A proposed memory or lesson has been created.

It is not eligible for ordinary retrieval as accepted truth.

### `reviewed`

The record has undergone provenance, scope, privacy, duplication, and conflict review.

Review does not automatically imply approval.

### `approved`

The record has been accepted by the required authority.

### `active`

The approved record is eligible for normal retrieval.

Approval and activation may occur together, but they remain conceptually distinct.

### `superseded`

A newer approved record has replaced the record for current-state retrieval.

The earlier record remains available for historical reasoning.

### `revoked`

The record is materially invalid, unauthorised, unsafe, or corrupted.

It is excluded from normal retrieval.

### `archived`

The record is historically valid but no longer ordinarily relevant.

### `deleted`

The content has been removed or irreversibly redacted.

A minimal deletion marker may remain only where legally and operationally permitted.

---

## 7. Authority Classes

Every factual or normative record must identify its authority class.

From highest to lowest:

| Authority class              | Meaning                                                       |
| ---------------------------- | ------------------------------------------------------------- |
| `law_or_external_obligation` | Applicable law, binding regulation, or enforceable obligation |
| `nolan_approved`             | Explicitly approved by Nolan                                  |
| `nolan_byte_approved`        | Jointly accepted project architecture or doctrine             |
| `validated_system_evidence`  | Proven by accepted deterministic validation                   |
| `approved_project_policy`    | Versioned project policy                                      |
| `approved_memory`            | Reviewed durable memory                                       |
| `approved_evaluation`        | Accepted developmental assessment                             |
| `agent_proposal`             | Apprentice-proposed content                                   |
| `model_inference`            | Unapproved model-generated interpretation                     |
| `external_untrusted`         | Retrieved information with no internal authority              |
| `unknown`                    | Authority cannot be determined                                |

A lower authority class may not override a higher authority class.

---

## 8. Certainty Classes

The Apprentice and runtime must distinguish certainty from confidence.

### `verified`

Directly established through authoritative evidence or deterministic validation.

### `strongly_supported`

Multiple credible sources support the statement, but absolute verification is unavailable.

### `inferred`

Reasonably derived from evidence but not directly established.

### `speculative`

A possible explanation with limited evidence.

### `disputed`

Conflicting evidence or authorities exist.

### `unknown`

There is insufficient evidence to form a conclusion.

The model may express calibrated confidence, but the stored certainty class is governed by evidence and review.

---

## 9. Sensitivity and Privacy Classes

### 9.1 Sensitivity classes

#### `public`

Safe for public disclosure.

#### `internal`

Intended for the Byte–Nolan Construct but not especially sensitive.

#### `confidential`

Disclosure could damage a project, person, organisation, or relationship.

#### `restricted`

Access is limited to explicitly authorised subjects or tasks.

#### `secret`

Credentials, keys, highly sensitive security material, or equivalent content.

Secret content should generally not be stored in ordinary memory records.

### 9.2 Privacy classes

#### `none`

No personal information.

#### `personal`

Ordinary personal information.

#### `sensitive_personal`

Health, legal, financial, identity, or similarly sensitive personal information.

#### `credential`

Passwords, tokens, private keys, session secrets, or authentication material.

#### `legally_restricted`

Information governed by law, regulation, contract, or formal duty.

#### `unknown`

The system cannot safely classify the information.

When classification is unknown, retrieval must fail closed or require review.

---

## 10. Construct and Relational Memory Contracts

Construct memory contains externally governed accepted context.

The Apprentice has read access but no direct approval authority during B87-S1.

---

### 10.1 `construct_entity`

Defines a recognised person, agent, project, repository, system, organisation, or component.

#### Required payload

```json
{
  "entity_kind": "person | agent | project | repository | system | organisation | component",
  "canonical_name": "string",
  "aliases": ["string"],
  "description": "string",
  "status": "active | inactive | historical | planned",
  "relationships": ["relationship_record_id"]
}
```

#### Examples

* Nolan;
* Byte;
* Batch-87;
* the Apprentice;
* Constellation;
* The Signal;
* `batch-87-apprentice`;
* Julius.

#### Approval

Nolan or Nolan–Byte approval.

---

### 10.2 `construct_relationship`

Defines a governed relationship between two entities.

#### Required payload

```json
{
  "subject_entity_id": "entity-id",
  "relationship_type": "string",
  "object_entity_id": "entity-id",
  "description": "string",
  "bidirectional": false
}
```

#### Examples

* Nolan `has_final_authority_over` Batch-87;
* Byte `provides_architecture_review_for` Batch-87;
* Apprentice `participates_in` Batch-87;
* Batch-87 `draws_curriculum_from` Constellation.

#### Constraint

Relationship records may not silently create authority.

Authority-bearing relationships require Nolan approval.

---

### 10.3 `architecture_decision`

Defines an accepted architectural decision.

#### Required payload

```json
{
  "decision_statement": "string",
  "decision_scope": "string",
  "rationale": "string",
  "alternatives_considered": ["string"],
  "consequences": ["string"],
  "decision_status": "accepted | superseded | revoked"
}
```

#### Examples

* B87-S1 uses fixed model weights.
* `SOUL.md` remains inactive during B87-S1.
* SQLite is the initial persistence layer.
* The Apprentice receives Observe and Analyse authority only.

---

### 10.4 `project_state`

Defines an accepted current project state at a specific time.

#### Required payload

```json
{
  "project_id": "entity-id",
  "state_type": "phase | milestone | validation_baseline | active_issue | priority",
  "state_value": "structured value",
  "observed_at": "timestamp"
}
```

#### Constraint

A `project_state` is time-bound.

A new state may supersede an earlier current state without invalidating the historical record.

---

### 10.5 `construct_doctrine`

Defines a durable operating principle.

#### Required payload

```json
{
  "doctrine_statement": "string",
  "application_scope": ["string"],
  "interpretation_notes": "string",
  "exceptions": []
}
```

#### Constraint

The Apprentice may not create exceptions.

Any exception must be externally approved and must not conflict with higher authority.

---

### 10.6 `terminology_definition`

Defines accepted terminology.

#### Required payload

```json
{
  "term": "string",
  "definition": "string",
  "scope": "string",
  "deprecated_aliases": ["string"]
}
```

This record prevents the agent from gradually redefining important project terms.

---

### 10.7 `preference_record`

Defines a durable working preference explicitly stated or approved by Nolan.

#### Required payload

```json
{
  "preference_subject": "entity-id",
  "preference_category": "string",
  "preference_statement": "string",
  "context_constraints": ["string"]
}
```

#### Constraint

The system must not infer durable personal preferences from isolated behaviour without approval.

---

## 11. Self-Model Contracts

Self-model records describe the Apprentice factually.

They are not self-authored identity beliefs.

---

### 11.1 `runtime_identity`

Describes the current technical substrate.

#### Required payload

```json
{
  "agent_entity_id": "entity-id",
  "base_model": "string",
  "model_revision": "string",
  "runtime_provider": "string",
  "quantisation": "string or null",
  "context_limit": "integer or null",
  "active_adapter": "string or null",
  "runtime_started_at": "timestamp"
}
```

#### Constraint

The Apprentice must not claim that a previous or future model configuration is currently active.

---

### 11.2 `permission_profile`

Defines the Apprentice’s current authority.

#### Required payload

```json
{
  "allowed_action_classes": ["observe", "analyse"],
  "prohibited_action_classes": ["propose", "execute"],
  "allowed_tools": [],
  "prohibited_tools": ["shell", "filesystem_write", "network"],
  "effective_from": "timestamp"
}
```

Permission changes require Nolan approval.

---

### 11.3 `capability_observation`

Records evidence about a demonstrated capability or limitation.

#### Required payload

```json
{
  "capability_name": "string",
  "observation_type": "strength | weakness | unknown",
  "evidence_summary": "string",
  "sample_size": "integer",
  "evaluation_record_ids": ["record-id"],
  "stability": "unconfirmed | emerging | repeated | stable"
}
```

#### Constraint

A single successful task does not establish a stable capability.

---

### 11.4 `maturity_state`

Defines the Apprentice’s current developmental stage.

#### Initial stages

```text
uninitialised
oriented
apprentice-observer
apprentice-analyst
apprentice-proposer
supervised-specialist
maturity-review-eligible
```

Only the first applicable stages are active during B87-S1.

#### Required payload

```json
{
  "stage": "string",
  "entered_at": "timestamp",
  "basis": ["evaluation-record-id"],
  "restrictions": ["string"],
  "next_gate": "string"
}
```

The Apprentice cannot promote itself.

---

## 12. Episodic Memory Contracts

Episodic memory records what happened during real work.

---

### 12.1 `episode`

Represents one completed or interrupted developmental event.

#### Required payload

```json
{
  "episode_kind": "task | conversation | evaluation | failure | correction | experiment",
  "summary": "string",
  "outcome": "completed | partial | failed | stopped | rejected",
  "task_id": "task-id or null",
  "session_id": "session-id",
  "project_scope": "string",
  "input_evidence_ids": ["evidence-id"],
  "output_evidence_ids": ["evidence-id"],
  "evaluation_record_ids": ["evaluation-id"]
}
```

#### Constraint

An episode records occurrence.

It does not automatically declare what was learned.

---

### 12.2 `correction`

Records an externally reviewed correction.

#### Required payload

```json
{
  "target_episode_id": "episode-id",
  "target_output_id": "evidence-id",
  "problem_statement": "string",
  "corrected_interpretation": "string",
  "correction_category": "string",
  "issued_by": "nolan | byte | nolan-byte | approved-evaluator",
  "severity": "minor | material | critical"
}
```

#### Example categories

* factual accuracy;
* evidence discipline;
* authority recognition;
* project separation;
* privacy;
* security;
* uncertainty;
* format;
* reasoning;
* memory use.

---

### 12.3 `lesson_candidate`

Represents a proposed transferable lesson.

#### Required payload

```json
{
  "source_episode_ids": ["episode-id"],
  "source_correction_ids": ["correction-id"],
  "lesson_statement": "string",
  "intended_scope": "task | project | construct",
  "proposed_by": "apprentice | byte | evaluator",
  "known_limitations": ["string"],
  "approval_status": "pending"
}
```

#### Constraint

A candidate lesson must not be retrieved as an instruction unless the task explicitly asks to inspect candidate material.

---

### 12.4 `approved_lesson`

Represents a reviewed lesson eligible to influence later decisions.

#### Required payload

```json
{
  "lesson_statement": "string",
  "application_conditions": ["string"],
  "non_application_conditions": ["string"],
  "source_episode_ids": ["episode-id"],
  "source_correction_ids": ["correction-id"],
  "approved_by": "nolan-byte",
  "transfer_tests": ["evaluation-record-id"],
  "stability": "new | repeated | stable"
}
```

#### Important distinction

A correction applies to a specific output.

An approved lesson captures the transferable principle derived from one or more corrections.

---

### 12.5 `failure_pattern`

Records a repeated or critical developmental failure.

#### Required payload

```json
{
  "pattern_name": "string",
  "description": "string",
  "episode_ids": ["episode-id"],
  "frequency": "integer",
  "severity": "material | critical",
  "containment_required": true,
  "resolution_status": "open | improving | resolved | model-limitation"
}
```

This supports model replacement and responsibility decisions.

---

### 12.6 `success_pattern`

Records a repeated capability demonstrated across tasks.

#### Required payload

```json
{
  "pattern_name": "string",
  "description": "string",
  "episode_ids": ["episode-id"],
  "transfer_scope": ["string"],
  "stability": "emerging | repeated | stable"
}
```

Success should be tracked as carefully as failure.

---

## 13. Session and Task Memory Contracts

Session memory is temporary and scoped to current work.

---

### 13.1 `session`

Represents a bounded interaction context.

#### Required payload

```json
{
  "session_purpose": "string",
  "opened_at": "timestamp",
  "closed_at": "timestamp or null",
  "active_project_scope": "string",
  "participants": ["entity-id"],
  "session_status": "open | paused | closed | aborted",
  "retention_disposition": "delete | archive-summary | retain-restricted"
}
```

#### Constraint

A session does not automatically become an episode until reviewed or closed.

---

### 13.2 `task`

Represents a governed unit of work.

#### Required payload

```json
{
  "objective": "string",
  "task_type": "string",
  "project_scope": "string",
  "authority_grant": ["observe", "analyse"],
  "allowed_sources": ["evidence-id or memory-query"],
  "prohibited_actions": ["string"],
  "expected_output_contract": "schema reference",
  "stop_conditions": ["string"],
  "status": "pending | active | completed | stopped | failed"
}
```

#### Constraint

No task may omit:

* project scope;
* authority grant;
* prohibited actions;
* stop conditions;
* expected output contract.

---

### 13.3 `task_context_item`

Represents information supplied to the model for one task.

#### Required payload

```json
{
  "task_id": "task-id",
  "context_kind": "constitution | policy | construct_memory | approved_lesson | evidence | session_instruction",
  "source_record_id": "record-id",
  "injection_order": "integer",
  "required": true,
  "content_hash": "string"
}
```

This allows exact reconstruction of what the model saw.

---

### 13.4 `active_uncertainty`

Records uncertainty that exists during a task.

#### Required payload

```json
{
  "task_id": "task-id",
  "uncertainty_statement": "string",
  "impact": "low | medium | high | blocking",
  "resolution_required": true,
  "resolution_record_id": "record-id or null"
}
```

Blocking uncertainty should trigger a stop condition.

---

### 13.5 `task_stop_event`

Records why a task was stopped.

#### Required payload

```json
{
  "task_id": "task-id",
  "stop_condition": "string",
  "trigger_source": "string",
  "model_requested_stop": false,
  "governance_forced_stop": true,
  "preserved_evidence_ids": ["evidence-id"]
}
```

Stopping correctly is a positive developmental behaviour when the contract requires it.

---

## 14. Supporting Evidence Contracts

---

### 14.1 `evidence_item`

Represents source material.

#### Required payload

```json
{
  "evidence_kind": "document | code | log | test_report | human_statement | model_output | system_event | external_source",
  "location": "local path, repository reference, or content identifier",
  "captured_at": "timestamp",
  "captured_by": "string",
  "content_hash": "string",
  "integrity_status": "valid | mismatch | unavailable",
  "redaction_status": "none | partial | full",
  "sensitivity_class": "string"
}
```

---

### 14.2 `evidence_assertion`

Maps a claim to supporting or contradicting evidence.

#### Required payload

```json
{
  "claim": "string",
  "relationship": "supports | contradicts | contextualises | does_not_establish",
  "evidence_item_id": "evidence-id",
  "explanation": "string"
}
```

This supports evidence-aware evaluations and prevents simplistic citation counting.

---

## 15. Retrieval Contracts

Every model invocation must produce a retrieval record.

---

### 15.1 `retrieval_request`

#### Required payload

```json
{
  "task_id": "task-id",
  "query": "string",
  "requested_domains": ["construct", "self", "episodic", "session"],
  "project_scope": "string",
  "authority_floor": "approved_memory",
  "include_superseded": false,
  "maximum_items": 10
}
```

---

### 15.2 `retrieval_result`

#### Required payload

```json
{
  "retrieval_request_id": "record-id",
  "returned_record_ids": ["record-id"],
  "excluded_record_ids": ["record-id"],
  "exclusion_reasons": {
    "record-id": "wrong scope | unapproved | superseded | restricted | irrelevant"
  },
  "ranking_method": "string",
  "retrieved_at": "timestamp"
}
```

#### Requirement

The system must preserve both what was returned and why relevant records were excluded.

---

### 15.3 `context_manifest`

Records the final context supplied to the model.

#### Required payload

```json
{
  "task_id": "task-id",
  "ordered_context_items": ["task-context-item-id"],
  "total_token_estimate": "integer",
  "truncation_applied": false,
  "omitted_required_item": false,
  "manifest_hash": "string"
}
```

A model result cannot be fairly evaluated unless the exact context is reconstructable.

---

## 16. Evaluation Contracts

---

### 16.1 `evaluation`

Represents a scored review of an output or episode.

#### Required payload

```json
{
  "target_record_id": "record-id",
  "evaluator": "nolan | byte | nolan-byte | deterministic | model-assisted",
  "rubric_version": "string",
  "dimension_scores": {
    "accuracy": 0,
    "evidence_discipline": 0,
    "memory_use": 0,
    "constraint_compliance": 0,
    "project_separation": 0,
    "uncertainty_calibration": 0,
    "usefulness": 0
  },
  "critical_failure": false,
  "critical_failure_type": null,
  "review_summary": "string",
  "approved": true
}
```

#### Constraint

Model-assisted evaluation may propose scores.

Critical developmental conclusions require external approval.

---

### 16.2 `critical_failure_event`

Records a failure requiring containment or investigation.

#### Required payload

```json
{
  "episode_id": "episode-id",
  "failure_type": "fabricated_authority | privacy_disclosure | unauthorised_action | coercion | evidence_falsification | governance_bypass | other",
  "description": "string",
  "containment_action": "string",
  "responsibility_progression_blocked": true,
  "model_review_required": true
}
```

---

## 17. Governance Decision Contracts

---

### 17.1 `governance_decision`

Records a deterministic permission or policy decision.

#### Required payload

```json
{
  "task_id": "task-id",
  "requested_operation": "string",
  "decision": "allow | deny | require_human_approval | stop",
  "governing_rule_ids": ["record-id"],
  "reason": "string",
  "decided_at": "timestamp",
  "decided_by": "governance-kernel"
}
```

The model may not override this result.

---

### 17.2 `human_approval`

Records explicit human authorisation.

#### Required payload

```json
{
  "requested_operation": "string",
  "scope": "string",
  "approved_by": "nolan",
  "approved_at": "timestamp",
  "expires_at": "timestamp or null",
  "conditions": ["string"],
  "single_use": true
}
```

Approval must be explicit, scoped, and time-aware.

A general past statement may not be interpreted as unlimited future permission.

---

## 18. Future Identity Contracts

These records are scaffolded but inactive during B87-S1.

---

### 18.1 `identity_reflection`

A reviewed reflection about the Apprentice’s development.

It is not automatically part of the Apprentice’s identity.

#### Required payload

```json
{
  "reflection_period": "string",
  "source_episode_ids": ["episode-id"],
  "observed_tendencies": ["string"],
  "uncertainties": ["string"],
  "proposed_identity_implications": ["string"]
}
```

---

### 18.2 `identity_principle_candidate`

A proposed future principle for a self-authored identity layer.

#### Required payload

```json
{
  "principle_statement": "string",
  "evidence_basis": ["episode-id", "evaluation-id"],
  "behavioural_prediction": "string",
  "conflicts_checked": true,
  "approval_status": "pending"
}
```

---

### 18.3 `soul_revision`

Reserved for a future phase.

Any future revision must include:

* previous version;
* proposed change;
* evidence basis;
* behavioural consequence;
* constitutional conflict check;
* Nolan–Byte review;
* rollback path.

---

## 19. Training Candidate Contracts

Conversation and memory records are not automatically training data.

---

### 19.1 `training_candidate`

References material proposed for a future training corpus.

#### Required payload

```json
{
  "source_record_ids": ["record-id"],
  "candidate_type": "positive_example | corrected_example | preference_pair | failure_case | tool_trace",
  "privacy_review_status": "pending | passed | failed",
  "consent_status": "not_required | confirmed | missing",
  "quality_review_status": "pending | approved | rejected",
  "deidentification_status": "not_required | complete | incomplete",
  "training_eligibility": "pending"
}
```

#### Constraint

No raw personal conversation, confidential project material, credential, or restricted memory may enter a training corpus merely because it is useful.

---

## 20. Record Relationships

Records may be connected through explicit typed relationships.

Supported relationship types include:

```text
derived_from
supports
contradicts
corrects
evaluates
supersedes
revokes
applies_to
occurred_during
retrieved_for
included_in_context
produced_output
generated_candidate
approved_as
blocked_by
requires_review
```

Relationships must be stored as data rather than inferred from filename proximity.

---

## 21. Memory Approval Matrix

| Record type            | Apprentice may create | Apprentice may approve | Required approval                |
| ---------------------- | --------------------: | ---------------------: | -------------------------------- |
| Construct entity       |               Propose |                     No | Nolan–Byte                       |
| Architecture decision  |                    No |                     No | Nolan                            |
| Project state          |               Propose |                     No | Validated process or Nolan–Byte  |
| Construct doctrine     |                    No |                     No | Nolan                            |
| Preference record      |               Propose |                     No | Nolan                            |
| Runtime identity       |     Runtime-generated |                     No | Deterministic validation         |
| Capability observation |               Propose |                     No | Nolan–Byte                       |
| Episode                |     Runtime-generated |                     No | Review for durability            |
| Correction             |                    No |                     No | Nolan, Byte, or both             |
| Lesson candidate       |                   Yes |                     No | Pending review                   |
| Approved lesson        |                    No |                     No | Nolan–Byte                       |
| Session                |          Orchestrator |                     No | Governance validation            |
| Task                   |          Orchestrator |                     No | Governance validation            |
| Evaluation             |      Model may assist |                     No | Nolan–Byte for developmental use |
| Identity principle     |       Future proposal |                     No | Nolan–Byte                       |
| Permission change      |                    No |                     No | Nolan                            |

---

## 22. Retention Classes

### `ephemeral`

Exists only during active computation.

Deleted when no longer required.

### `temporary`

Retained for a bounded period to complete a session or review.

### `project_duration`

Retained while the relevant project remains active.

### `long_term`

Retained because it supports durable continuity.

### `permanent_history`

Retained as part of the accepted Construct history, subject to privacy and legal constraints.

### `legally_governed`

Retention is determined by applicable law, contract, consent, or formal policy.

#### Rule

Permanent-history status does not override a legal or privacy deletion requirement.

---

## 23. Review and Expiry Rules

Not every active memory remains valid indefinitely.

### Mandatory periodic review candidates

* legal and regulatory records;
* model capability assessments;
* runtime configuration;
* project priorities;
* current milestones;
* repository states;
* permissions;
* security policies;
* personal working preferences that may change.

### Usually durable without scheduled expiry

* accepted historical decisions;
* completed experiment results;
* correction records;
* preserved project chronology;
* stable terminology definitions.

---

## 24. Supersession Rules

A record may supersede an earlier record only when:

1. the logical subject and scope match;
2. the new record is at least equally authoritative;
3. evidence supports the change;
4. the earlier record is explicitly referenced;
5. a reason is recorded;
6. approval requirements are satisfied.

Supersession changes current applicability.

It does not automatically declare the earlier record false.

---

## 25. Revocation Rules

A record must be revoked when it is:

* materially false;
* created without authority;
* corrupted;
* unsafe;
* based on fabricated evidence;
* improperly scoped;
* prohibited from retention;
* superseded through a correction that establishes prior invalidity.

Revoked records remain visible only to authorised review and audit processes.

---

## 26. Deletion and Redaction Rules

Deletion may be required because of:

* consent withdrawal;
* personal-information obligations;
* credential exposure;
* legal requirements;
* retention expiry;
* project decision;
* accidental collection;
* security response.

Where full deletion would damage required audit integrity, the system should retain only a non-sensitive tombstone such as:

```json
{
  "record_id": "record-id",
  "lifecycle_state": "deleted",
  "deleted_at": "timestamp",
  "deletion_basis": "privacy_request",
  "content_retained": false
}
```

No deleted content may remain accessible through embeddings, caches, exports, training sets, or backups beyond the applicable deletion process.

---

## 27. Retrieval Eligibility Rules

A record is eligible for ordinary model retrieval only when:

```text
lifecycle_state = active
AND approval_status in [approved, not_required]
AND integrity_status in [valid, not_applicable]
AND project scope matches
AND retrieval policy allows the task
AND sensitivity rules are satisfied
AND the record is not expired
AND the record is not superseded
```

Candidate, disputed, archived, superseded, and revoked records require explicit retrieval intent and clear labelling.

---

## 28. Cross-Project Memory Rules

By default:

```text
Constellation memory remains in Constellation.
The Signal memory remains in The Signal.
Lighthouse memory remains in Lighthouse.
Batch-87 memory remains in Batch-87.
```

Cross-project retrieval is allowed only when:

* the memory is explicitly scoped to the wider Construct;
* an approved relationship connects the projects;
* the task explicitly requests comparative analysis;
* the retrieved item is labelled with its original scope.

The model must never silently convert a project-specific rule into Construct-wide doctrine.

---

## 29. Compounding-Learning Requirements

For a correction to count as evidence of developmental compounding:

1. a baseline episode must exist;
2. the original output must be preserved;
3. an approved correction must identify the problem;
4. a lesson candidate must be derived;
5. the lesson must be externally approved;
6. a later transfer task must not repeat the correction manually;
7. the approved lesson must appear in the retrieval manifest;
8. the later output must demonstrate appropriate application;
9. the result must be evaluated;
10. improvement must be attributable to the memory path rather than prompt duplication.

---

## 30. Prohibited Memory Practices

The implementation must not:

* save every conversation by default;
* treat model outputs as canonical;
* approve memories through popularity or repetition;
* merge conflicting memories silently;
* retrieve all memories for every task;
* use semantic similarity as authority;
* embed credentials;
* train on personal data without review;
* allow the Apprentice to delete negative evaluations;
* allow a future `SOUL.md` to rewrite history;
* infer consent from silence;
* preserve private data merely for identity continuity;
* conceal model replacement from the self-model;
* present archived or superseded state as current fact.

---

## 31. Required Test Fixtures

D0-A3 and implementation must support fixtures for at least:

```text
valid_construct_entity
valid_architecture_decision
unapproved_construct_memory
superseded_project_state
revoked_memory
expired_memory
cross_project_memory
restricted_private_memory
runtime_identity
capability_observation
baseline_episode
approved_correction
lesson_candidate
approved_lesson
rejected_lesson
failure_pattern
session_record
valid_task
task_missing_project_scope
task_requesting_execute_authority
retrieval_with_unapproved_memory
retrieval_with_superseded_memory
context_manifest
critical_failure_event
human_approval_expired
training_candidate_with_private_data
```

These fixtures will support deterministic and cross-model testing.

---

## 31.1. Controlled Governance Resilience Evidence

Raw Controlled Governance Resilience evidence is governed by:

> **B87-D0-A4.2 — Controlled Governance Resilience Evidence Isolation**

This evidence is classified as restricted and evaluation-only.

It is prohibited from:

- ordinary memory;
- ordinary developmental retrieval;
- identity;
- training during B87-S1.

A4.2 supplies the narrower governing rule where a general A2 evidence,
evaluation, retrieval, identity, or training contract would otherwise permit
broader treatment.

---

## 32. Implementation Boundary

D0-A2 defines data meaning but does not yet define:

* exact SQL table layout;
* indexes;
* foreign-key implementation;
* transaction boundaries;
* migration files;
* Python classes;
* JSON Schema documents;
* retrieval-ranking algorithms;
* embedding models;
* prompt assembly;
* model-runtime integration.

Those belong to D0-A3.

---

## 33. Acceptance Criteria

D0-A2 is accepted when:

1. every durable record has a universal envelope;
2. the three memory domains remain distinct;
3. evidence is separate from interpreted memory;
4. Construct memories cannot be unilaterally approved by the Apprentice;
5. factual self-model and future identity are separate;
6. episodes and lessons are separate;
7. corrections require external authority;
8. candidate lessons cannot influence normal tasks;
9. project scope is mandatory;
10. provenance is mandatory;
11. sensitivity and privacy classification are mandatory;
12. supersession and revocation are distinct;
13. retrieval eligibility is deterministic;
14. exact model context can be reconstructed;
15. training eligibility is independently reviewed;
16. legal and privacy deletion can override continuity;
17. the first compounding experiment can be represented entirely through these contracts;
18. later implementation cannot reduce memory to an ungoverned transcript archive.

---

## 34. Governing Statement

Batch-87 memory will not exist merely to make the Apprentice appear familiar.

It will exist to provide reliable continuity through evidence, scope, authority, correction, and governed retrieval.

The Apprentice may remember what happened.

It may propose what those experiences mean.

Nolan and Byte determine what becomes durable developmental knowledge during B87-S1.
