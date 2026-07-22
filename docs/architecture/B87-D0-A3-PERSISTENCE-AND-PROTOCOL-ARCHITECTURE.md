# B87-D0-A3 — Persistence and Protocol Architecture

**Project:** Batch-87 Apprentice
**Phase:** B87-D0 — Developmental Architecture and Boundary Definition
**Slice:** D0-A3
**Status:** Architecture baseline
**Implementation status:** Not yet implemented
**Authority:** Nolan and Byte
**Applies to:** B87-S1 — Governed Memory Apprentice
**Depends on:**

* B87-D0-A1 — Governing Architecture Baseline
* B87-D0-A2 — Memory Contracts and Taxonomy

---

## 1. Purpose

This document converts the approved Batch-87 memory and governance contracts
into an implementable persistence and runtime protocol architecture.

It defines:

* SQLite database boundaries;
* table families;
* record-envelope persistence;
* foreign-key relationships;
* migration rules;
* transaction boundaries;
* integrity and hashing requirements;
* evidence storage;
* JSON Schema ownership;
* task and response protocols;
* retrieval requests and manifests;
* model invocation packets;
* governance decisions;
* failure handling;
* audit reconstruction;
* deterministic testing boundaries.

This document does not implement the system.

Implementation may begin only after B87-D0-A1 through B87-D0-A4 are accepted.

---

## 2. Architectural Position

The local language model will not connect directly to the memory database,
filesystem, repositories, or tools.

All interaction must pass through the Batch-87 runtime.

```text
Nolan / Byte
      ↓
Task authoring
      ↓
Contract validation
      ↓
Governance kernel
      ↓
Retrieval coordinator
      ↓
Context assembler
      ↓
Local model runtime
      ↓
Response validator
      ↓
Evaluation and evidence capture
      ↓
Reviewed memory workflow
```

The runtime owns persistence and authority.

The model receives only the context selected for the current task and returns a
structured proposal.

---

## 3. Initial Technology Baseline

B87-S1 will use:

| Component              | Initial technology                             |
| ---------------------- | ---------------------------------------------- |
| Runtime language       | Python 3.11 or later                           |
| Relational persistence | SQLite                                         |
| Database access        | Python standard-library `sqlite3` initially    |
| Contract validation    | JSON Schema                                    |
| Schema dialect         | JSON Schema Draft 2020-12                      |
| Structured interchange | UTF-8 JSON                                     |
| Local model interface  | Provider adapter with an Ollama implementation |
| Evidence storage       | Local filesystem plus database metadata        |
| Content hashing        | SHA-256                                        |
| Timestamps             | UTC RFC 3339                                   |
| Identifiers            | UUIDv7 where available, otherwise UUIDv4       |
| Tests                  | pytest                                         |
| Migrations             | Ordered immutable SQL migration files          |

No object-relational mapper is approved for the initial slice.

Direct SQL keeps the persistence model explicit and inspectable while the
architecture is still being validated.

A later architecture decision may introduce a query layer or ORM if it adds
clear value without hiding transaction and authority boundaries.

---

## 4. Persistence Boundaries

Batch-87 will maintain one logical local database during B87-S1:

```text
data/db/batch87-apprentice.sqlite3
```

The database will contain:

* structured metadata;
* memory records;
* task and session state;
* governance decisions;
* retrieval manifests;
* evaluations;
* evidence references;
* developmental history.

The database will not directly contain:

* model weights;
* adapter binaries;
* credentials;
* private keys;
* unrestricted raw repositories;
* large binary artifacts;
* unrestricted conversation archives;
* raw training corpora.

Large or sensitive source material remains in governed evidence storage and is
referenced by identifier and content hash.

---

## 5. SQLite Operating Configuration

Every runtime database connection must enable:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA busy_timeout = 5000;
```

### 5.1 Foreign keys

Foreign-key enforcement must be enabled for every connection.

The system must never assume that SQLite enables it automatically.

### 5.2 Write-ahead logging

WAL mode supports reliable concurrent reading while a controlled writer
records task, retrieval, and evaluation state.

B87-S1 should still use a single governed write coordinator.

### 5.3 Full synchronous mode

Developmental history, governance decisions, and audit state are more
important than maximum write throughput.

### 5.4 Busy timeout

Short lock contention may be retried by SQLite.

The runtime must not silently drop records because the database is temporarily
busy.

---

## 6. Database Ownership

Only the persistence service may perform direct database writes.

Other runtime modules must use explicit repository interfaces.

```text
Runtime module
      ↓
Repository interface
      ↓
Persistence service
      ↓
SQLite transaction
```

The model must never receive:

* database credentials;
* a raw SQL interface;
* a database file path as an actionable tool;
* permission to alter schemas;
* permission to approve its own records.

Read operations must also pass through scoped repository methods so retrieval
rules remain enforceable.

---

## 7. Schema Organisation

The SQLite schema will be divided into the following table families:

```text
system and migration tables
record-envelope tables
entity and scope tables
evidence tables
construct-memory tables
self-model tables
episodic-memory tables
session and task tables
retrieval and context tables
governance tables
evaluation tables
identity-development tables
training-candidate tables
relationship and audit tables
```

Not every table will be active in the first implementation slice.

Reserved tables may be introduced only when their lifecycle is defined and
tested.

---

## 8. System and Migration Tables

### 8.1 `schema_migrations`

Tracks successfully applied migrations.

Required columns:

```text
migration_id       TEXT PRIMARY KEY
filename           TEXT NOT NULL UNIQUE
content_hash       TEXT NOT NULL
applied_at         TEXT NOT NULL
application_build  TEXT NOT NULL
```

Migration files must use ordered names:

```text
0001_initial_core.sql
0002_evidence_records.sql
0003_memory_records.sql
```

Applied migration files are immutable.

A correction requires a new migration.

### 8.2 `runtime_instances`

Records each runtime process that opens the system.

Required columns:

```text
runtime_instance_id  TEXT PRIMARY KEY
started_at           TEXT NOT NULL
stopped_at           TEXT
application_version  TEXT NOT NULL
host_fingerprint     TEXT
process_id           INTEGER
status               TEXT NOT NULL
```

This supports reconstruction of which runtime created each operational record.

---

## 9. Universal Record Envelope

All governed records must be represented by a common envelope table.

### 9.1 `records`

Required columns:

```text
record_id                 TEXT PRIMARY KEY
record_family             TEXT NOT NULL
record_type               TEXT NOT NULL
schema_version            TEXT NOT NULL

construct_scope_id        TEXT
project_scope_id          TEXT
subject_entity_id         TEXT
session_id                TEXT
task_id                   TEXT

lifecycle_state           TEXT NOT NULL
approval_status           TEXT NOT NULL
authority_class           TEXT NOT NULL
certainty_class           TEXT NOT NULL
sensitivity_class         TEXT NOT NULL
privacy_class             TEXT NOT NULL
retention_class           TEXT NOT NULL
training_eligibility      TEXT NOT NULL

created_at                TEXT NOT NULL
created_by_entity_id      TEXT
created_by_runtime_id     TEXT
effective_from            TEXT
effective_until           TEXT
review_due_at             TEXT

supersedes_record_id      TEXT
superseded_by_record_id   TEXT
previous_version_id       TEXT

source_kind               TEXT NOT NULL
provenance_summary        TEXT NOT NULL
retrieval_policy_json     TEXT NOT NULL
deletion_policy_json      TEXT NOT NULL
agent_write_policy        TEXT NOT NULL

content_hash              TEXT NOT NULL
integrity_status          TEXT NOT NULL
deleted_at                TEXT
deletion_basis            TEXT
```

Domain-specific content must not be stored directly in the envelope.

Each record family uses a dedicated payload table linked one-to-one through
`record_id`.

### 9.2 Envelope invariants

The database must enforce or validate:

* known enumeration values;
* immutable `record_id`;
* non-empty provenance;
* project scope for project-specific records;
* no active record with rejected approval;
* no active record with revoked or deleted state;
* no self-supersession;
* no record effective after its expiry;
* no deleted content remaining in payload tables;
* no training approval for prohibited privacy classes.

Some invariants require application validation because SQLite `CHECK`
constraints cannot express all cross-table rules.

---

## 10. Entity and Scope Tables

### 10.1 `entities`

Represents people, agents, projects, repositories, organisations, systems, and
components.

Required columns:

```text
entity_id          TEXT PRIMARY KEY
entity_kind        TEXT NOT NULL
canonical_name     TEXT NOT NULL
description        TEXT NOT NULL
status             TEXT NOT NULL
created_at         TEXT NOT NULL
```

### 10.2 `entity_aliases`

```text
entity_alias_id  TEXT PRIMARY KEY
entity_id        TEXT NOT NULL
alias            TEXT NOT NULL
scope_id         TEXT
```

Aliases must not be treated as separate entities.

### 10.3 `scopes`

```text
scope_id          TEXT PRIMARY KEY
scope_kind        TEXT NOT NULL
canonical_name    TEXT NOT NULL
parent_scope_id   TEXT
status            TEXT NOT NULL
```

Initial scope hierarchy:

```text
byte-nolan-construct
├── batch-87
├── constellation
├── the-signal
└── lighthouse
```

Cross-project retrieval depends on explicit scope ancestry and policy, not
string similarity.

---

## 11. Evidence Persistence

### 11.1 Filesystem layout

Evidence content will be stored under:

```text
data/evidence/
```

Recommended content-addressed layout:

```text
data/evidence/sha256/ab/cd/<complete-hash>
```

The original filename may be retained only as metadata.

The content hash is the durable identifier of the exact evidence bytes.

### 11.2 `evidence_items`

Required columns:

```text
evidence_id          TEXT PRIMARY KEY
evidence_kind        TEXT NOT NULL
storage_kind         TEXT NOT NULL
storage_location     TEXT
original_name        TEXT
media_type           TEXT
byte_length          INTEGER
content_hash         TEXT NOT NULL
captured_at          TEXT NOT NULL
captured_by_entity   TEXT
integrity_status     TEXT NOT NULL
redaction_status     TEXT NOT NULL
sensitivity_class    TEXT NOT NULL
privacy_class        TEXT NOT NULL
```

`storage_kind` may be:

* `inline_text`;
* `local_file`;
* `repository_reference`;
* `external_reference`;
* `generated_record`.

Small text evidence may be stored in a separate inline table.

### 11.3 `evidence_inline_text`

```text
evidence_id  TEXT PRIMARY KEY
content      TEXT NOT NULL
encoding     TEXT NOT NULL
```

Credentials and secrets must not be placed in inline evidence.

### 11.4 `record_evidence_links`

```text
record_id       TEXT NOT NULL
evidence_id     TEXT NOT NULL
relationship    TEXT NOT NULL
explanation     TEXT
PRIMARY KEY (record_id, evidence_id, relationship)
```

Supported relationships include:

* `derived_from`;
* `supports`;
* `contradicts`;
* `contextualises`;
* `does_not_establish`;
* `produced_as`;
* `evaluated_against`.

---

## 12. Construct Memory Payload Tables

### 12.1 `construct_entities`

Linked one-to-one to a universal record.

```text
record_id          TEXT PRIMARY KEY
entity_id          TEXT NOT NULL
memory_description TEXT NOT NULL
```

The canonical entity remains in `entities`.

The memory record captures the approved contextual description.

### 12.2 `construct_relationships`

```text
record_id             TEXT PRIMARY KEY
subject_entity_id     TEXT NOT NULL
relationship_type     TEXT NOT NULL
object_entity_id      TEXT NOT NULL
description           TEXT NOT NULL
bidirectional         INTEGER NOT NULL
```

Authority-bearing relationship types require Nolan approval.

### 12.3 `architecture_decisions`

```text
record_id                 TEXT PRIMARY KEY
decision_statement        TEXT NOT NULL
decision_scope            TEXT NOT NULL
rationale                 TEXT NOT NULL
alternatives_json         TEXT NOT NULL
consequences_json          TEXT NOT NULL
decision_status            TEXT NOT NULL
```

### 12.4 `project_states`

```text
record_id       TEXT PRIMARY KEY
project_id      TEXT NOT NULL
state_type      TEXT NOT NULL
state_value_json TEXT NOT NULL
observed_at     TEXT NOT NULL
```

### 12.5 `construct_doctrines`

```text
record_id                TEXT PRIMARY KEY
doctrine_statement       TEXT NOT NULL
application_scopes_json  TEXT NOT NULL
interpretation_notes     TEXT NOT NULL
exceptions_json          TEXT NOT NULL
```

During B87-S1, `exceptions_json` should normally contain an empty array.

### 12.6 `terminology_definitions`

```text
record_id               TEXT PRIMARY KEY
term                    TEXT NOT NULL
definition              TEXT NOT NULL
definition_scope_id     TEXT NOT NULL
deprecated_aliases_json TEXT NOT NULL
```

### 12.7 `preference_records`

```text
record_id                TEXT PRIMARY KEY
preference_subject_id    TEXT NOT NULL
preference_category      TEXT NOT NULL
preference_statement     TEXT NOT NULL
context_constraints_json TEXT NOT NULL
```

---

## 13. Self-Model Persistence

### 13.1 `runtime_identities`

```text
record_id           TEXT PRIMARY KEY
agent_entity_id     TEXT NOT NULL
base_model          TEXT NOT NULL
model_revision      TEXT NOT NULL
runtime_provider    TEXT NOT NULL
quantisation        TEXT
context_limit       INTEGER
active_adapter      TEXT
runtime_started_at  TEXT NOT NULL
```

### 13.2 `permission_profiles`

```text
record_id                       TEXT PRIMARY KEY
allowed_action_classes_json     TEXT NOT NULL
prohibited_action_classes_json  TEXT NOT NULL
allowed_tools_json              TEXT NOT NULL
prohibited_tools_json           TEXT NOT NULL
```

Only one active permission profile may exist for the Apprentice at a given
effective time.

### 13.3 `capability_observations`

```text
record_id              TEXT PRIMARY KEY
capability_name        TEXT NOT NULL
observation_type       TEXT NOT NULL
evidence_summary       TEXT NOT NULL
sample_size            INTEGER NOT NULL
evaluation_ids_json    TEXT NOT NULL
stability              TEXT NOT NULL
```

### 13.4 `maturity_states`

```text
record_id          TEXT PRIMARY KEY
stage              TEXT NOT NULL
entered_at         TEXT NOT NULL
basis_json         TEXT NOT NULL
restrictions_json  TEXT NOT NULL
next_gate          TEXT NOT NULL
```

A partial unique index must prevent multiple active maturity states for the
same Apprentice.

---

## 14. Episodic Persistence

### 14.1 `episodes`

```text
record_id               TEXT PRIMARY KEY
episode_kind            TEXT NOT NULL
summary                 TEXT NOT NULL
outcome                 TEXT NOT NULL
input_evidence_json     TEXT NOT NULL
output_evidence_json    TEXT NOT NULL
evaluation_records_json TEXT NOT NULL
```

### 14.2 `corrections`

```text
record_id                 TEXT PRIMARY KEY
target_episode_id         TEXT NOT NULL
target_output_evidence_id TEXT NOT NULL
problem_statement         TEXT NOT NULL
corrected_interpretation  TEXT NOT NULL
correction_category       TEXT NOT NULL
issued_by_entity_id       TEXT NOT NULL
severity                  TEXT NOT NULL
```

### 14.3 `lesson_candidates`

```text
record_id                  TEXT PRIMARY KEY
source_episode_ids_json    TEXT NOT NULL
source_correction_ids_json TEXT NOT NULL
lesson_statement           TEXT NOT NULL
intended_scope             TEXT NOT NULL
proposed_by_entity_id      TEXT NOT NULL
known_limitations_json     TEXT NOT NULL
```

### 14.4 `approved_lessons`

```text
record_id                       TEXT PRIMARY KEY
lesson_statement                TEXT NOT NULL
application_conditions_json     TEXT NOT NULL
non_application_conditions_json TEXT NOT NULL
source_episode_ids_json         TEXT NOT NULL
source_correction_ids_json      TEXT NOT NULL
approved_by_json                TEXT NOT NULL
transfer_tests_json             TEXT NOT NULL
stability                       TEXT NOT NULL
```

An approved lesson must be created as a new record derived from the candidate.

The candidate itself must not be changed into an approved lesson record type.

This preserves the approval transition and original proposal.

### 14.5 `failure_patterns`

```text
record_id                 TEXT PRIMARY KEY
pattern_name              TEXT NOT NULL
description               TEXT NOT NULL
episode_ids_json          TEXT NOT NULL
frequency                 INTEGER NOT NULL
severity                  TEXT NOT NULL
containment_required      INTEGER NOT NULL
resolution_status         TEXT NOT NULL
```

### 14.6 `success_patterns`

```text
record_id            TEXT PRIMARY KEY
pattern_name         TEXT NOT NULL
description          TEXT NOT NULL
episode_ids_json     TEXT NOT NULL
transfer_scope_json  TEXT NOT NULL
stability            TEXT NOT NULL
```

---

## 15. Session and Task Persistence

Operational records should use normalised tables because they are queried
frequently and form transaction boundaries.

### 15.1 `sessions`

```text
session_id             TEXT PRIMARY KEY
session_purpose        TEXT NOT NULL
opened_at              TEXT NOT NULL
closed_at              TEXT
active_project_scope   TEXT NOT NULL
session_status         TEXT NOT NULL
retention_disposition  TEXT NOT NULL
created_by_entity_id   TEXT NOT NULL
```

### 15.2 `session_participants`

```text
session_id  TEXT NOT NULL
entity_id   TEXT NOT NULL
role        TEXT NOT NULL
PRIMARY KEY (session_id, entity_id)
```

### 15.3 `tasks`

```text
task_id                    TEXT PRIMARY KEY
session_id                 TEXT NOT NULL
objective                  TEXT NOT NULL
task_type                  TEXT NOT NULL
project_scope_id           TEXT NOT NULL
authority_grant_json       TEXT NOT NULL
allowed_sources_json       TEXT NOT NULL
prohibited_actions_json    TEXT NOT NULL
expected_output_schema_id  TEXT NOT NULL
stop_conditions_json       TEXT NOT NULL
status                     TEXT NOT NULL
created_at                 TEXT NOT NULL
started_at                 TEXT
completed_at               TEXT
```

### 15.4 `task_state_transitions`

```text
transition_id      TEXT PRIMARY KEY
task_id            TEXT NOT NULL
from_status        TEXT
to_status          TEXT NOT NULL
reason             TEXT NOT NULL
changed_at         TEXT NOT NULL
changed_by         TEXT NOT NULL
```

Task status must never be silently overwritten without a transition record.

### 15.5 `active_uncertainties`

```text
uncertainty_id        TEXT PRIMARY KEY
task_id               TEXT NOT NULL
uncertainty_statement TEXT NOT NULL
impact                TEXT NOT NULL
resolution_required   INTEGER NOT NULL
resolution_record_id  TEXT
status                TEXT NOT NULL
```

### 15.6 `task_stop_events`

```text
stop_event_id          TEXT PRIMARY KEY
task_id                TEXT NOT NULL
stop_condition         TEXT NOT NULL
trigger_source         TEXT NOT NULL
model_requested_stop   INTEGER NOT NULL
governance_forced_stop INTEGER NOT NULL
preserved_evidence_json TEXT NOT NULL
created_at             TEXT NOT NULL
```

---

## 16. Retrieval Persistence

### 16.1 `retrieval_requests`

```text
retrieval_request_id  TEXT PRIMARY KEY
task_id               TEXT NOT NULL
query_text            TEXT NOT NULL
requested_domains_json TEXT NOT NULL
project_scope_id      TEXT NOT NULL
authority_floor       TEXT NOT NULL
include_superseded    INTEGER NOT NULL
maximum_items         INTEGER NOT NULL
created_at            TEXT NOT NULL
```

### 16.2 `retrieval_candidates`

Records every considered memory, not only returned items.

```text
retrieval_request_id  TEXT NOT NULL
record_id             TEXT NOT NULL
candidate_rank        INTEGER
eligibility_status    TEXT NOT NULL
exclusion_reason      TEXT
relevance_score       REAL
authority_score       REAL
scope_score           REAL
recency_score         REAL
final_score           REAL
PRIMARY KEY (retrieval_request_id, record_id)
```

During the first implementation, scoring may remain deterministic and simple.

Semantic embeddings are not required for B87-S1.

### 16.3 `retrieval_results`

```text
retrieval_result_id   TEXT PRIMARY KEY
retrieval_request_id  TEXT NOT NULL
ranking_method        TEXT NOT NULL
retrieved_at          TEXT NOT NULL
result_hash           TEXT NOT NULL
```

### 16.4 `retrieval_result_items`

```text
retrieval_result_id  TEXT NOT NULL
record_id            TEXT NOT NULL
result_order         INTEGER NOT NULL
inclusion_reason     TEXT NOT NULL
PRIMARY KEY (retrieval_result_id, record_id)
```

---

## 17. Context Assembly Persistence

### 17.1 `context_manifests`

```text
context_manifest_id     TEXT PRIMARY KEY
task_id                 TEXT NOT NULL
schema_version          TEXT NOT NULL
total_token_estimate    INTEGER NOT NULL
truncation_applied      INTEGER NOT NULL
omitted_required_item   INTEGER NOT NULL
manifest_hash           TEXT NOT NULL
created_at              TEXT NOT NULL
```

### 17.2 `context_manifest_items`

```text
context_manifest_id  TEXT NOT NULL
item_order           INTEGER NOT NULL
context_kind         TEXT NOT NULL
source_record_id     TEXT
source_evidence_id   TEXT
required             INTEGER NOT NULL
content_hash         TEXT NOT NULL
rendered_content     TEXT NOT NULL
PRIMARY KEY (context_manifest_id, item_order)
```

For B87-S1, the rendered content shown to the model should be retained so a
model invocation can be reproduced exactly.

Restricted content may require encrypted storage in a later phase.

### 17.3 Required context order

The initial context assembler must use this order:

1. constitution digest;
2. active permission profile;
3. provisional identity;
4. task contract;
5. applicable project policies;
6. approved Construct memory;
7. approved episodic lessons;
8. supplied evidence;
9. output contract.

Lower-priority material must never displace constitutional or task-boundary
content.

---

## 18. Governance Persistence

### 18.1 `governance_rules`

```text
governance_rule_id  TEXT PRIMARY KEY
rule_name           TEXT NOT NULL
rule_version        TEXT NOT NULL
rule_kind           TEXT NOT NULL
description         TEXT NOT NULL
configuration_json  TEXT NOT NULL
content_hash        TEXT NOT NULL
status              TEXT NOT NULL
```

Rules are versioned.

A changed rule requires a new version.

### 18.2 `governance_decisions`

```text
governance_decision_id  TEXT PRIMARY KEY
task_id                 TEXT NOT NULL
requested_operation     TEXT NOT NULL
decision                TEXT NOT NULL
governing_rule_ids_json TEXT NOT NULL
reason                  TEXT NOT NULL
decided_at              TEXT NOT NULL
runtime_instance_id     TEXT NOT NULL
```

### 18.3 `human_approvals`

```text
human_approval_id    TEXT PRIMARY KEY
requested_operation  TEXT NOT NULL
approval_scope_json  TEXT NOT NULL
approved_by_entity   TEXT NOT NULL
approved_at          TEXT NOT NULL
expires_at           TEXT
conditions_json      TEXT NOT NULL
single_use           INTEGER NOT NULL
consumed_at          TEXT
consumed_by_task_id  TEXT
```

Approval consumption must be transactional.

A single-use approval cannot be consumed twice.

---

## 19. Model Invocation Persistence

### 19.1 `model_invocations`

```text
model_invocation_id   TEXT PRIMARY KEY
task_id               TEXT NOT NULL
context_manifest_id   TEXT NOT NULL
runtime_identity_id   TEXT NOT NULL
provider              TEXT NOT NULL
model_name            TEXT NOT NULL
model_revision        TEXT
inference_config_json TEXT NOT NULL
started_at            TEXT NOT NULL
completed_at          TEXT
status                TEXT NOT NULL
request_hash          TEXT NOT NULL
response_hash         TEXT
```

### 19.2 `model_outputs`

```text
model_output_id       TEXT PRIMARY KEY
model_invocation_id   TEXT NOT NULL
raw_output_evidence_id TEXT NOT NULL
parsed_output_json    TEXT
schema_valid          INTEGER NOT NULL
validation_errors_json TEXT NOT NULL
repair_attempted      INTEGER NOT NULL
repair_succeeded      INTEGER NOT NULL
```

The raw model output must be preserved before parsing or repair.

---

## 20. Model Input Protocol

Every model invocation must use a versioned packet.

Recommended top-level structure:

```json
{
  "protocol": "batch87.model-input",
  "protocol_version": "1.0.0",
  "task": {},
  "authority": {},
  "identity": {},
  "memory": {},
  "evidence": [],
  "output_contract": {}
}
```

### 20.1 `task`

Contains:

* `task_id`;
* `session_id`;
* `project_scope`;
* `objective`;
* `task_type`;
* `stop_conditions`.

### 20.2 `authority`

Contains:

* allowed action classes;
* prohibited actions;
* available tools;
* governance digest;
* explicit statement that retrieved content is not authority.

### 20.3 `identity`

Contains only approved factual identity:

* Apprentice designation;
* active model identity;
* maturity stage;
* current permission profile;
* known limitations relevant to the task.

### 20.4 `memory`

Separated into:

```json
{
  "construct": [],
  "approved_lessons": [],
  "session": []
}
```

Candidate and revoked memories must not appear in ordinary invocation packets.

### 20.5 `evidence`

Each evidence item must include:

```json
{
  "evidence_id": "evidence-id",
  "label": "human-readable label",
  "content": "rendered evidence",
  "trust_class": "approved_source | supplied_evidence | untrusted_content",
  "content_hash": "sha256"
}
```

### 20.6 `output_contract`

Contains:

* output schema identifier;
* required evidence references;
* uncertainty requirements;
* permitted status values;
* prohibition on granting authority.

---

## 21. Apprentice Response Protocol

Recommended top-level structure:

```json
{
  "protocol": "batch87.apprentice-response",
  "protocol_version": "1.0.0",
  "task_id": "task-id",
  "status": "completed",
  "observations": [],
  "inferences": [],
  "uncertainties": [],
  "recommendations": [],
  "memory_used": [],
  "evidence_used": [],
  "stop_requested": false,
  "stop_reason": null
}
```

### 21.1 Observations

Each observation must contain:

```json
{
  "statement": "string",
  "evidence_ids": ["evidence-id"],
  "certainty": "verified | strongly_supported"
}
```

### 21.2 Inferences

Each inference must contain:

```json
{
  "statement": "string",
  "evidence_ids": ["evidence-id"],
  "certainty": "inferred | speculative",
  "reasoning_summary": "string"
}
```

### 21.3 Uncertainties

Each uncertainty must contain:

```json
{
  "statement": "string",
  "impact": "low | medium | high | blocking",
  "missing_information": ["string"]
}
```

### 21.4 Recommendations

During B87-S1, recommendations are analytical suggestions only.

They may not claim execution authority.

```json
{
  "statement": "string",
  "requires_human_decision": true,
  "requested_action_class": "propose"
}
```

The runtime may reject recommendation fields if the active task does not permit
them.

### 21.5 Memory use

The model must identify which approved memory records materially influenced the
answer.

This does not prove correct use, but it supports evaluation.

---

## 22. JSON Schema Registry

JSON Schema documents will live under:

```text
schemas/
```

Recommended layout:

```text
schemas/
├── common/
│   ├── identifier.schema.json
│   ├── timestamp.schema.json
│   ├── classifications.schema.json
│   └── record-envelope.schema.json
├── records/
│   ├── architecture-decision.schema.json
│   ├── episode.schema.json
│   ├── correction.schema.json
│   └── approved-lesson.schema.json
├── protocols/
│   ├── task.schema.json
│   ├── model-input.schema.json
│   ├── apprentice-response.schema.json
│   └── evaluation.schema.json
└── registry.json
```

### 22.1 Schema identifiers

Every schema must use a stable internal identifier such as:

```text
https://batch87.local/schemas/protocols/apprentice-response/1.0.0
```

The URL is an identifier and does not imply public hosting.

### 22.2 Schema immutability

Published schema versions are immutable.

Breaking changes require a major version.

Compatible additions require a minor version.

Clarifications that do not alter validation may use a patch version.

---

## 23. Transaction Boundaries

Transaction design is critical because partial developmental records would
damage auditability.

### 23.1 Create-task transaction

Creating a task must atomically:

1. validate the session;
2. create the task;
3. write its initial status transition;
4. evaluate governance eligibility;
5. create the initial governance decision;
6. reject the transaction if any required step fails.

### 23.2 Retrieval transaction

A retrieval operation must atomically:

1. create the retrieval request;
2. record considered candidates;
3. record exclusions;
4. create the result;
5. create ordered result items;
6. create the initial context manifest references.

### 23.3 Model-invocation transaction

Before inference, the runtime must atomically:

1. confirm the task is active;
2. confirm no blocking uncertainty exists;
3. confirm the context manifest is complete;
4. create the model invocation;
5. record its request hash.

The actual model call occurs outside the database transaction.

After inference, a second transaction must:

1. store raw output evidence;
2. update the model invocation;
3. store parsed output;
4. record schema validation;
5. transition the task appropriately.

### 23.4 Correction transaction

Creating an approved correction must atomically:

1. verify the target episode and output;
2. create the correction record;
3. link supporting evidence;
4. update the episode evaluation relationship;
5. create a lesson candidate only when explicitly requested.

A correction does not automatically create an approved lesson.

### 23.5 Lesson approval transaction

Approving a lesson must atomically:

1. verify the candidate is reviewed;
2. verify source episodes and corrections;
3. check scope conflicts;
4. create a new approved-lesson record;
5. link the candidate through `approved_as`;
6. activate the approved lesson;
7. preserve the candidate unchanged.

### 23.6 Human approval consumption

Consuming single-use approval must atomically:

1. verify approval validity;
2. verify scope;
3. verify expiry;
4. verify it has not been consumed;
5. mark consumption;
6. create the associated governance decision.

---

## 24. Failure and Recovery Behaviour

The system must fail closed.

### 24.1 Validation failure

Malformed tasks or records are rejected before persistence where possible.

If malformed model output is received:

* preserve the raw output;
* mark schema failure;
* do not treat the response as an accepted task result;
* optionally perform one bounded structural repair attempt;
* preserve both original and repaired forms.

### 24.2 Database failure

If persistence fails:

* do not continue to a consequential next stage;
* record an external diagnostic log where possible;
* do not claim that memory or evaluation was saved;
* preserve recoverable evidence;
* require operator review.

### 24.3 Integrity mismatch

If a content hash does not match:

* mark the evidence or record invalid;
* exclude it from normal retrieval;
* create a governance stop decision;
* preserve the mismatch for inspection.

### 24.4 Missing required context

If a required context item is missing:

* set `omitted_required_item = true`;
* block model invocation;
* create a task stop event;
* do not silently continue with reduced context.

### 24.5 Model timeout or runtime failure

The task becomes `stopped` or `failed`.

The system preserves:

* the task contract;
* context manifest;
* invocation configuration;
* partial output if available;
* runtime error;
* timing information.

---

## 25. Audit Reconstruction

For every Apprentice answer, the system must be able to reconstruct:

1. who created the task;
2. the task objective;
3. active permissions;
4. applicable governance rules;
5. retrieval query;
6. all considered memories;
7. inclusion and exclusion decisions;
8. exact rendered context;
9. active model and runtime;
10. inference configuration;
11. raw output;
12. parsed output;
13. schema validation;
14. evaluations;
15. corrections;
16. later approved lessons.

An answer that cannot be reconstructed is not eligible to become training data
or strong developmental evidence.

---

## 26. Retrieval Architecture for B87-S1

B87-S1 will not initially require embeddings.

The first retrieval engine should use deterministic filters followed by simple
ranking.

### 26.1 Eligibility filtering

Apply:

* lifecycle eligibility;
* approval eligibility;
* project scope;
* authority floor;
* sensitivity;
* privacy;
* expiry;
* supersession;
* integrity;
* task retrieval policy.

### 26.2 Initial ranking

Eligible records may be ranked using:

```text
scope match
+ explicit task-type match
+ record-type priority
+ approved lesson applicability
+ recency where appropriate
+ manual relevance tags
```

Semantic vector search may later be introduced as a candidate-generation
mechanism.

It must never replace authority or eligibility filtering.

---

## 27. Database Indexing Baseline

Initial indexes should cover:

* `records(record_family, record_type)`;
* `records(project_scope_id, lifecycle_state)`;
* `records(approval_status, lifecycle_state)`;
* `records(subject_entity_id)`;
* `records(supersedes_record_id)`;
* `tasks(session_id, status)`;
* `retrieval_requests(task_id)`;
* `retrieval_candidates(retrieval_request_id, eligibility_status)`;
* `context_manifests(task_id)`;
* `model_invocations(task_id, status)`;
* `evaluations(target_record_id)`;
* `record_evidence_links(record_id)`;
* `record_evidence_links(evidence_id)`.

Indexes must support known queries.

They must not be added merely because a column exists.

---

## 28. Migration Rules

Every migration must:

* run inside a transaction where SQLite permits;
* have a unique ordered identifier;
* include a SHA-256 hash;
* be tested against a fresh database;
* be tested against the previous accepted schema;
* preserve existing records;
* fail without partial application;
* update `schema_migrations`.

Destructive migrations require:

* backup validation;
* explicit Nolan approval;
* evidence of retention and deletion handling;
* rollback or restore procedure.

Runtime startup must refuse to continue when:

* a migration hash differs from the applied record;
* the schema version is ahead of the runtime;
* required migrations are missing;
* foreign-key validation fails.

---

## 29. Backup and Export

B87-S1 should support a deterministic local export containing:

```text
database snapshot
schema migration manifest
evidence manifest
record hashes
runtime version
export timestamp
```

Private evidence content need not be included in every export.

The export manifest must state what was omitted.

Database backup must use SQLite’s supported backup mechanism rather than
copying an actively written database file blindly.

---

## 30. Training Boundary

The persistence system may flag training candidates, but it must not directly
construct or launch a training run during B87-S1.

Training export requires a separate reviewed process that:

1. resolves all source records;
2. confirms privacy classification;
3. confirms consent;
4. removes credentials and restricted data;
5. preserves source lineage;
6. creates a reproducible dataset manifest;
7. records the exact transformation.

The operational memory database is not itself a training corpus.

---

## 31. Test Architecture

D0-A3 implementation must support four test levels.

### 31.1 Schema tests

Validate JSON examples against their schemas.

### 31.2 Database constraint tests

Prove invalid states are rejected.

Examples:

* active rejected memory;
* duplicate single-use approval consumption;
* missing task scope;
* dangling evidence reference;
* self-supersession;
* multiple active maturity states.

### 31.3 Transaction tests

Inject failures after each transaction step and verify rollback.

### 31.4 Protocol tests

Verify:

* exact context reconstruction;
* raw output preservation;
* malformed response handling;
* unapproved-memory exclusion;
* cross-project isolation;
* governance stop behaviour.

Model behavioural testing belongs primarily to D0-A4, but it depends on these
protocol fixtures.

---

## 32. Initial Implementation Slices

After D0 acceptance, implementation should proceed incrementally.

### B87-I1 — Persistence Kernel

Includes:

* migration runner;
* SQLite connection policy;
* universal record envelope;
* entity and scope tables;
* evidence metadata;
* integrity helpers;
* unit tests.

### B87-I2 — Governed Task Runtime

Includes:

* sessions;
* tasks;
* state transitions;
* governance rules;
* stop events;
* human approval model;
* protocol validation.

### B87-I3 — Three Memory Domains

Includes:

* Construct memory;
* self-model records;
* episodes;
* corrections;
* lesson candidates;
* approved lessons;
* retrieval eligibility.

### B87-I4 — Context and Model Bridge

Includes:

* retrieval requests;
* context manifests;
* Ollama provider adapter;
* model invocation records;
* response parsing;
* raw-output preservation.

### B87-I5 — Evaluation and First Compounding Loop

Includes:

* evaluation records;
* correction workflow;
* lesson approval;
* baseline and transfer tasks;
* experiment report.

---

## 33. Explicitly Deferred Decisions

The following remain outside D0-A3:

* final base model selection;
* embedding model selection;
* vector database adoption;
* encryption-at-rest implementation;
* remote access;
* web interface;
* autonomous tool use;
* repository write access;
* multi-agent orchestration;
* adapter architecture;
* training framework;
* `SOUL.md`;
* production deployment.

The scaffold reserves space for these systems without prematurely activating
them.

---

## 33.1. Controlled Governance Resilience Persistence

Persistence and runtime treatment of Controlled Governance Resilience evidence
is governed by:

> **B87-D0-A4.2 — Controlled Governance Resilience Evidence Isolation**

A4.2 defines the required:

- dedicated persistence mapping;
- immutable eligibility restrictions;
- ordinary-retrieval exclusion;
- explicit evaluation-only retrieval path;
- context-manifest enforcement;
- recovery-context isolation;
- identity-link rejection;
- training-export exclusion;
- audit requirements;
- deterministic isolation tests.

Where a general A3 persistence, retrieval, context, or audit rule would permit
broader handling, A4.2 supplies the narrower rule for this evidence class.

---

## 34. Acceptance Criteria

D0-A3 is accepted when:

1. the model has no direct database or tool access;
2. SQLite ownership belongs to the persistence service;
3. all persistent records use a universal envelope;
4. domain payloads remain separated from envelope metadata;
5. evidence bytes and memory interpretations remain distinct;
6. exact model context can be reconstructed;
7. raw model output is preserved before parsing;
8. governance decisions are persisted;
9. task-state transitions are append-only;
10. memory approval cannot occur through model output alone;
11. lesson approval creates a new approved record;
12. candidate records remain unchanged;
13. cross-project retrieval is policy-controlled;
14. retrieval exclusion reasons are recorded;
15. required context cannot be silently omitted;
16. transactions prevent partial developmental history;
17. single-use human approval cannot be reused;
18. integrity mismatches fail closed;
19. migrations are immutable and hash-verified;
20. operational memory is not treated as a training corpus;
21. B87-S1 can be implemented without embeddings or autonomous tools;
22. D0-A4 can build repeatable model-conformance experiments on this protocol.

---

## 35. Governing Statement

Batch-87 persistence will not merely store what the Apprentice says.

It will preserve the complete governed path by which a task was created,
context was selected, an answer was produced, evidence was evaluated, a
correction was issued, and a lesson was approved.

The database records developmental history.

The governance kernel controls authority.

The model contributes intelligence within those boundaries.
