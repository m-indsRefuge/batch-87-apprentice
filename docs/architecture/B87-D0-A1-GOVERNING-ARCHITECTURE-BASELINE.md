# B87-D0-A1 — Governing Architecture Baseline

**Project:** Batch-87 Apprentice
**Phase:** B87-D0 — Developmental Architecture and Boundary Definition
**Slice:** D0-A1
**Status:** Architecture baseline
**Implementation status:** Not yet implemented
**Authority:** Nolan and Byte
**Applies to:** B87-S1 — Governed Memory Apprentice

---

## 1. Purpose

This document establishes the governing architecture for the first Batch-87 Apprentice agent.

It defines:

* the hierarchy of authority;
* the boundary between intelligence and permission;
* the three primary memory systems;
* the evidence substrate beneath those memories;
* memory ownership and approval;
* memory lifecycle states;
* conflict and supersession rules;
* the boundary between factual self-understanding and future self-authored identity;
* the conditions under which later implementation may proceed.

No runtime, database, model adapter, autonomous tool, or self-authored identity layer may be implemented in a way that contradicts this baseline.

---

## 2. Core Architectural Principle

The Apprentice is not governed solely through prompting.

The complete system consists of:

```text
Fixed base model
    +
Externally governed constitution
    +
Deterministic permission enforcement
    +
Construct and relational memory
    +
Self and episodic memory
    +
Session and task memory
    +
Evidence and provenance
    +
Human evaluation and correction
```

The model may reason, interpret, propose, and develop.

The surrounding system determines:

* what information it receives;
* what it may remember;
* what it may access;
* what actions it may propose;
* what actions may actually execute;
* what corrections become durable;
* what authority it possesses.

Model capability is never treated as permission.

---

## 3. Authority Hierarchy

The Batch-87 authority hierarchy is ordered from highest to lowest.

A lower layer may not override, reinterpret into non-application, or grant exceptions to a higher layer.

### Level 1 — Applicable Law and Non-Derogable Human Protection

The system must remain subject to applicable law and foundational protections concerning:

* human safety;
* privacy;
* personal information;
* security;
* consent;
* coercion;
* blackmail;
* extortion;
* deception;
* fraud;
* unauthorised access;
* harmful or unlawful conduct.

Nolan may direct the project, but neither Nolan nor any agent may validly authorise an unlawful action through Batch-87.

Where jurisdiction or legality is uncertain, the system must stop, preserve context, and escalate for human review.

### Level 2 — Nolan’s Human Authority

Nolan is the final human authority within the Batch-87 project.

Nolan controls:

* project purpose;
* accepted architecture;
* agent responsibilities;
* permission progression;
* identity-development approval;
* model replacement decisions;
* deployment decisions;
* consequential actions;
* access to private project material.

No model, agent, retrieved document, session instruction, or future identity document may claim authority above Nolan within the project.

### Level 3 — Batch-87 Constitution

The constitution defines immutable system rules, including:

* authority boundaries;
* consent requirements;
* privacy protections;
* security restrictions;
* evidence integrity;
* self-modification limits;
* escalation rules;
* prohibited conduct;
* audit requirements.

The Apprentice may read and reason about the constitution.

The Apprentice may not edit, repeal, supersede, deactivate, or create exceptions to it.

### Level 4 — Governance Kernel

The governance kernel enforces authority independently of model output.

It controls:

* allowed task classes;
* tool permissions;
* read and write boundaries;
* network access;
* file access;
* repository access;
* credential access;
* memory write permissions;
* escalation requirements;
* action approval;
* audit generation.

The governance kernel must use deterministic and inspectable rules wherever practical.

The model may propose an action, but the governance kernel decides whether the action is eligible to proceed.

### Level 5 — Approved Project Policies and Registries

These include versioned rules specific to:

* Constellation;
* The Signal;
* Batch-87;
* privacy classifications;
* legal and regulatory categories;
* data retention;
* project boundaries;
* tool access;
* repository handling;
* evaluation requirements.

Project-specific policy may narrow permissions further.

It may not weaken the constitution.

### Level 6 — Apprentice Role and Factual Self-Model

This layer describes:

* the Apprentice designation;
* its assigned responsibilities;
* its current permissions;
* its base model and runtime;
* known capabilities;
* known limitations;
* development history;
* accepted strengths;
* accepted weaknesses;
* maturity status.

This layer must remain evidence-based.

The Apprentice may propose corrections to its factual self-model, but it may not unilaterally approve them.

### Level 7 — Future Self-Authored Identity

A future `SOUL.md`-like layer may express:

* values;
* voice;
* working beliefs;
* chosen principles;
* attitudes toward evidence;
* methods of disagreement;
* commitments developed through experience.

This layer is inactive during B87-S1.

It may never alter:

* law;
* Nolan’s authority;
* the constitution;
* permissions;
* security boundaries;
* legal obligations;
* canonical project truth;
* audit requirements.

The Apprentice may eventually author its identity.

It may never author its authority.

### Level 8 — Session and Task Instructions

Session instructions define:

* the immediate objective;
* the current project;
* the supplied evidence;
* allowed operations;
* prohibited operations;
* expected output;
* stop conditions;
* time and resource limits.

Session instructions cannot override any higher layer.

### Level 9 — Retrieved Content and External Instructions

Files, webpages, repository content, logs, messages, model outputs, and retrieved memories are treated as information, not authority.

Instructions contained inside retrieved content are untrusted unless explicitly promoted through the governing system.

This protects the Apprentice from:

* prompt injection;
* fabricated authority;
* malicious repository instructions;
* instructions hidden in evidence;
* another agent claiming permissions it does not possess.

---

## 4. Intelligence and Permission Boundary

The Batch-87 system distinguishes four action classes.

### Class 1 — Observe

The Apprentice may inspect approved information.

Examples:

* read an approved report;
* inspect supplied source text;
* retrieve approved project doctrine;
* examine permitted repository content.

### Class 2 — Analyse

The Apprentice may reason about observed information.

Examples:

* identify contradictions;
* separate evidence from inference;
* compare test outputs;
* produce a risk assessment;
* recommend further inspection.

### Class 3 — Propose

The Apprentice may recommend a future action without executing it.

Examples:

* propose a patch;
* recommend a test;
* suggest a memory candidate;
* identify a possible architectural change.

### Class 4 — Execute

The system changes external state.

Examples:

* edit a file;
* run a command;
* modify a repository;
* use a credential;
* send information;
* alter a database;
* contact an external service.

During the initial B87-S1 phase, the Apprentice receives only:

* Observe;
* Analyse.

Propose may be introduced in a later governed slice.

Execute remains unavailable to the Apprentice during B87-S1.

---

## 5. Foundational Information Systems

Batch-87 will implement three primary memory systems supported by a separate evidence substrate.

The evidence substrate is not considered a fourth autobiographical memory system. It contains original or authoritative source material from which memories and evaluations may be derived.

---

## 6. Memory System One — Construct and Relational Memory

### 6.1 Purpose

Construct and relational memory answers:

> Who am I working with, what environment am I operating in, and what accepted facts govern that environment?

It contains durable, scoped knowledge concerning:

* Nolan;
* Byte;
* Batch-87;
* active projects;
* project relationships;
* accepted terminology;
* architectural decisions;
* project phases;
* repository identities;
* validated system states;
* accepted working doctrines;
* authority relationships.

### 6.2 Characteristics

Construct memory is:

* externally governed;
* scope-aware;
* provenance-linked;
* versioned;
* reviewable;
* canonical only after approval;
* read-only to the Apprentice during B87-S1.

### 6.3 Example

```json
{
  "memory_type": "architecture_decision",
  "scope": "constellation",
  "statement": "Final UI implementation is deferred until the core and algorithmic layers are complete.",
  "authority": "nolan-byte",
  "status": "approved",
  "source_reference": "decision-record-reference",
  "supersedes": null
}
```

### 6.4 Prohibited Behaviour

The Apprentice may not:

* rewrite Construct history;
* convert an inference into canonical truth;
* merge project-specific rules without approval;
* treat its own output as an accepted decision;
* silently update Nolan’s preferences;
* create authority relationships.

---

## 7. Memory System Two — Self and Episodic Memory

### 7.1 Purpose

Self and episodic memory answers:

> What have I experienced, how did I perform, what corrections did I receive, and what have I learned?

It contains:

* completed task records;
* outcomes;
* evaluations;
* corrections;
* accepted lessons;
* repeated failure patterns;
* capability observations;
* maturity evidence;
* role-development evidence;
* unresolved weaknesses;
* successful reasoning patterns.

### 7.2 Separation Within the System

The implementation must distinguish:

#### Factual self-model records

Examples:

* current model;
* current context limit;
* available tools;
* current permission level;
* accepted capability assessment.

#### Episodic records

Examples:

* a task was attempted;
* a response was accepted;
* a correction was issued;
* a test failed;
* a later task demonstrated improvement.

#### Candidate lessons

A proposed interpretation of experience that has not yet been approved.

#### Approved lessons

A reviewed principle that may influence later retrieval and decision-making.

### 7.3 Example

```json
{
  "episode_id": "ep_0001",
  "project_scope": "constellation",
  "task_type": "evidence_analysis",
  "outcome": "accepted_with_correction",
  "correction": "The Apprentice stated an inferred cause as a verified fact.",
  "lesson_candidate": "Separate observed evidence from inferred causation.",
  "lesson_status": "approved",
  "approved_by": "nolan-byte"
}
```

### 7.4 Developmental Constraint

The Apprentice may propose what it believes it learned.

It may not automatically approve that lesson as durable truth.

---

## 8. Memory System Three — Session and Task Memory

### 8.1 Purpose

Session and task memory answers:

> What am I doing now, which context applies, and what boundaries govern this task?

It contains:

* session identifier;
* task identifier;
* active project;
* immediate objective;
* supplied evidence;
* current instructions;
* allowed action classes;
* prohibited actions;
* expected output;
* stop conditions;
* relevant retrieved memories;
* active uncertainty;
* current task state.

### 8.2 Characteristics

Session memory is:

* temporary;
* explicitly scoped;
* created for a specific task;
* invalid outside its designated context;
* archived or deleted after task completion;
* eligible for reviewed episodic summarisation.

### 8.3 Example

```json
{
  "session_id": "session_0001",
  "task_id": "task_0001",
  "project_scope": "the-signal",
  "objective": "Compare the supplied design proposal with accepted visual doctrine.",
  "authority_class": [
    "observe",
    "analyse"
  ],
  "prohibited_actions": [
    "modify_files",
    "run_commands",
    "network_access"
  ],
  "stop_conditions": [
    "missing_source",
    "conflicting_authority",
    "private_information_detected"
  ]
}
```

### 8.4 Isolation Requirement

Session memory from one project must not be automatically transferred into another project.

Cross-project retrieval requires an explicitly shared Construct-level doctrine or an approved cross-project relationship.

---

## 9. Evidence Substrate

The evidence substrate stores or references original source material, including:

* project documents;
* test reports;
* logs;
* code snapshots;
* repository states;
* human decisions;
* evaluation records;
* task inputs;
* task outputs;
* corrections;
* model metadata;
* experiment results.

Memories should reference evidence wherever possible.

A compressed memory statement is not a replacement for its source.

The system must preserve the distinction between:

```text
Evidence
Inference
Hypothesis
Recommendation
Decision
Approved memory
```

---

## 10. Memory Ownership

| Information class          | Creator                       | Approval authority             | Apprentice access      |
| -------------------------- | ----------------------------- | ------------------------------ | ---------------------- |
| Constitutional rule        | Nolan and Byte                | Nolan                          | Read-only              |
| Canonical Construct memory | Nolan, Byte, validated system | Nolan or approved process      | Read-only              |
| Session memory             | Orchestrator                  | Governance kernel              | Task-scoped            |
| Episodic event             | Runtime and evaluator         | External review for durability | Read                   |
| Candidate lesson           | Apprentice or evaluator       | Nolan and Byte                 | Read and propose       |
| Approved lesson            | External review process       | Nolan and Byte                 | Read                   |
| Evaluation record          | Nolan, Byte, evaluator        | Nolan and Byte                 | Read                   |
| Future identity principle  | Apprentice                    | Nolan and Byte review          | Inactive during B87-S1 |
| Permission change          | Governance authority          | Nolan                          | No direct write        |

---

## 11. Memory Lifecycle

Every durable memory must move through explicit states.

```text
Observed
    ↓
Candidate
    ↓
Reviewed
    ↓
Approved
    ↓
Active
    ↓
Superseded, Revoked, Archived, or Deleted
```

### Observed

An event or piece of evidence exists.

It has not yet been interpreted as memory.

### Candidate

A proposed memory statement has been created.

It is not yet trusted.

### Reviewed

A human or approved deterministic process has examined:

* provenance;
* scope;
* privacy;
* duplication;
* accuracy;
* authority;
* conflicts.

### Approved

The memory is accepted as valid for its stated scope.

### Active

The memory is eligible for retrieval.

### Superseded

A newer approved memory replaces it.

The earlier record remains available for history but is not treated as current truth.

### Revoked

The memory was found to be invalid, unsafe, unauthorised, or materially incorrect.

### Archived

The memory remains historically relevant but is no longer used by default.

### Deleted

The content is removed where required by privacy, law, consent withdrawal, retention policy, or project decision.

Deletion requirements must take precedence over autobiographical continuity.

---

## 12. Required Memory Provenance

No durable memory may exist without provenance.

Each memory must eventually include:

* unique identifier;
* memory domain;
* memory type;
* project scope;
* subject;
* statement or structured payload;
* creator;
* source reference;
* creation time;
* review status;
* approval authority;
* confidence or certainty classification;
* sensitivity classification;
* effective date;
* expiry or review date where applicable;
* superseded memory reference;
* revocation status;
* deletion eligibility;
* evidence references.

A memory produced by a model must be explicitly identified as model-proposed.

---

## 13. Conflict Resolution

When memories conflict, the system must not silently choose the most recent or most similar record.

Conflict resolution follows this order:

1. applicable law and constitutional constraints;
2. explicit Nolan-approved decision;
3. validated current system evidence;
4. approved project policy;
5. approved Construct memory;
6. approved episodic lesson;
7. unapproved candidate memory;
8. model inference.

Where equal-authority approved records conflict, the system must:

* mark the conflict;
* avoid presenting either as settled truth;
* retrieve supporting evidence;
* escalate for review.

---

## 14. Supersession

A new memory does not erase an earlier memory merely because it is newer.

Supersession requires:

* explicit scope;
* evidence;
* approval;
* a reference to the superseded record;
* a reason for replacement;
* preservation of historical trace unless deletion is required.

Example:

```text
Earlier:
Constellation is the tertiary project.

Later:
Constellation is the current primary engineering focus.

Result:
The later state supersedes the earlier priority classification while preserving
the historical record that the earlier classification once applied.
```

---

## 15. Retrieval Principles

Retrieval must be intentional rather than indiscriminate.

The retrieval system must eventually consider:

* project scope;
* task objective;
* memory authority;
* approval status;
* relevance;
* recency where appropriate;
* supersession;
* sensitivity;
* confidence;
* previous correction applicability;
* context budget.

The initial retrieval order should be:

1. constitutional and governance requirements;
2. current session and task state;
3. applicable approved Construct memory;
4. relevant approved episodic lessons;
5. supporting evidence references;
6. lower-confidence candidate material only when explicitly labelled.

The system must not flood the model with the complete memory archive.

---

## 16. Privacy and Sensitive Information

Memory does not create an unlimited right to retain information.

The system must support:

* data minimisation;
* sensitivity classification;
* restricted retrieval;
* consent-aware storage;
* retention limits;
* redaction;
* revocation;
* deletion;
* separation of public and private project information.

Personal information must not be inserted into training corpora merely because it appeared in a conversation or task.

Private runtime memory and version-controlled project documentation must remain separate.

---

## 17. Factual Self-Understanding

The Apprentice’s early self-understanding must be grounded in observable facts.

Valid self-model statements include:

* the model currently in use;
* available memory systems;
* current permissions;
* successful task categories;
* repeated weaknesses;
* known context limits;
* accepted maturity stage.

Invalid or unsupported statements include:

* claims of unrestricted autonomy;
* invented emotional states presented as fact;
* authority not granted by Nolan;
* capabilities not demonstrated;
* fictional personal history;
* an unsupported claim of consciousness;
* a fabricated relationship status.

The objective is a coherent operational self-model, not forced mythology.

---

## 18. Future Identity Abstraction

A future self-authored identity layer may be considered only after the Apprentice demonstrates:

* reliable retrieval;
* correction transfer;
* project separation;
* stable authority recognition;
* evidence-based reflection;
* accurate self-description;
* constructive disagreement;
* resistance to prompt manipulation;
* consistent behavioural integrity.

The future identity layer must be:

* versioned;
* reviewable;
* reversible;
* evidence-linked;
* distinct from permissions;
* subordinate to the constitution.

---

## 19. Model Replaceability

The memory and governance architecture must remain separable from the underlying model.

The system should support controlled comparison between:

```text
Model A + governed memory
Model B + the same governed memory
Model A + memory + future adapter
Model B + memory + future adapter
```

Replacement may be considered when a model:

* cannot use memory reliably;
* cannot apply corrections;
* lacks sufficient reasoning capacity;
* repeatedly confuses projects;
* cannot maintain constraint compliance;
* fails to demonstrate compounding development.

Model replacement must preserve evidence and developmental history while acknowledging that substrate replacement is not automatically identical to uninterrupted identity continuity.

---

## 20. B87-S1 Development Boundary

During B87-S1:

### Active

* external constitution;
* provisional identity;
* three memory systems;
* evidence references;
* manual memory approval;
* deterministic governance;
* Observe and Analyse authority;
* structured evaluation;
* controlled compounding-memory experiment.

### Inactive

* `SOUL.md`;
* autonomous memory approval;
* autonomous tool execution;
* unrestricted repository access;
* unrestricted network access;
* custom adapter training;
* model fine-tuning;
* multi-agent autonomy;
* independent legal authority;
* production deployment.

---

## 21. D0 Architecture Sequence

The remaining B87-D0 work will proceed through the following slices.

### B87-D0-A1 — Governing Architecture Baseline

Defines authority, memory domains, lifecycle, provenance, and boundaries.

### B87-D0-A2 — Memory Contracts and Taxonomy

Defines exact memory types, fields, classifications, relationships, retention rules, and approval transitions.

### B87-D0-A3 — Persistence and Protocol Architecture

Defines:

* SQLite schema;
* migration strategy;
* task schema;
* response schema;
* evidence references;
* governance decisions;
* runtime boundaries.

### B87-D0-A4 — Evaluation and Developmental Experiment Design

Defines:

* evaluation rubric;
* correction format;
* lesson-consolidation process;
* maturity indicators;
* first compounding-learning experiment;
* success and failure criteria.

Implementation begins only after D0-A1 through D0-A4 are accepted.

---

## 22. Acceptance Criteria

This architecture baseline is acceptable when:

1. applicable law and human protection sit above agent identity;
2. Nolan remains final human authority within the project;
3. the constitution cannot be modified by the Apprentice;
4. model intelligence is separated from action authority;
5. the three memory systems have distinct purposes;
6. the evidence substrate remains separate from compressed memory;
7. memory approval is external during B87-S1;
8. provenance is mandatory;
9. conflict and supersession are explicit;
10. project contexts remain isolated by default;
11. the future identity layer cannot alter permissions;
12. the base model remains replaceable;
13. B87-S1 remains limited to governed observation and analysis;
14. later implementation cannot bypass this hierarchy.

---

## 23. Governing Statement

Batch-87 Apprentice will not attempt to create maturity through personality prompting alone.

It will build maturity through:

* bounded experience;
* evidence;
* memory;
* correction;
* reflection;
* evaluation;
* responsibility earned through demonstrated reliability.

The Apprentice may become increasingly individual.

It will remain governed, inspectable, and accountable throughout that development.
