# B87-I4-B Provider-Neutral Model and Invocation Bridge Contract

## 1. Contract status and authority

**Contract status:** accepted

**Acceptance date:** 2026-07-30

**Acceptance decision:**

```text
docs/implementation/B87-PROGRAMME-STATE-AND-I4-B-CONTRACT-ACCEPTANCE-DECISION.md
```

**Contract version:** 1.0

**Parent phase:** B87-I4 - Retrieval, Context, and Model-Bridge Boundary

**Accepted predecessor:** B87-I4-A - Governed Retrieval and Context Assembly

**Accepted predecessor merge:**

```text
093e07a6aa9209a6ea8efe2aaecfcbdeb6829d0a
```

**Authoring authorization:**

```text
AUTHORIZE B87 PROGRAMME-STATE RECONCILIATION AND I4-B SLICE CONTRACT
```

**Active implementation release:**

```text
NONE
```

This document defines a future bounded implementation slice. Its documentation
contract is accepted; acceptance does not begin implementation.

The implementation entry gate remains unsatisfied. Implementation may begin
only after:

1. a scoped B87-V0 regression decision required by section 17 is separately
   accepted and recorded; and
2. Nolan separately issues exactly:

```text
AUTHORIZE B87-I4-B
```

No repository document, test, model output, Codex statement, or prior I4 release
may infer or self-issue that release.

## 2. Objective

B87-I4-B will implement the smallest provider-neutral production-core boundary
capable of completing a deterministic governed invocation against only:

- an inactive provider; or
- a pure deterministic mock provider.

The slice must:

- consume an accepted, integrity-verified B87-I4-A structured context package;
- bind the invocation to exact task, session, project, runtime identity,
  provider, model descriptor, inference configuration, output schema, and
  context hashes;
- expose the provider only to immutable canonical input bytes;
- persist an immutable, reconstructable invocation history;
- durably preserve exact raw provider-output bytes before decoding, parsing, or
  validation;
- parse and validate a versioned Apprentice response;
- fail closed on stale context, provider failure, timeout, malformed output,
  schema failure, integrity mismatch, or persistence failure;
- keep model output separate from authority, evidence acceptance, memory
  approval, evaluation acceptance, and task permissions;
- prove the boundary with deterministic tests and no real model.

The slice exists to validate the bridge, not a model.

## 3. Governing sources and precedence

This contract is governed, in descending order of authority, by:

1. applicable law and non-derogable human protection;
2. accepted B87-D0 constitutional governance, immutable authority constraints,
   and safety boundaries;
3. Nolan's current explicit project instruction, where consistent with the
   authorities above;
4. the ratified programme and technical contracts:
   `B87-I1-I4-LLM-READINESS-CODEX-MASTER-CONTRACT.md`,
   `B87-PRE-LLM-IMPLEMENTATION-PROGRAMME-CONTRACT.md`, and
   `B87-PRE-LLM-CONTRACT-RATIFICATION-DECISION.md`;
5. accepted implementation-boundary and acceptance decisions, including
   `B87-I1-CONTROLLED-RESILIENCE-REFERENCE-BOUNDARY-DECISION.md` and the
   accepted I1 through I4-A boundaries;
6. the accepted B87-V0 closure and regression rules in
   `B87-V0-PERSISTENCE-VALIDATION-CLOSURE-AND-V1-ENTRY-GATE.md`;
7. the current-state reconciliation in
   `B87-PROGRAMME-STATE-RECONCILIATION-THROUGH-I4-A-AND-V0.md`; and
8. `AGENTS.md` as the subordinate repository operational instruction and
   current-state summary.

Nolan retains final human project authority and exclusive phase-release
authority. Consistently with the higher authorities above, Nolan may authorize,
withhold, stop, or reject a bounded implementation slice.

An ordinary task or implementation instruction cannot silently weaken, bypass,
or supersede accepted constitutional governance or safety constraints. A
proposed change to B87-D0 constitutional governance requires an explicit,
separately reviewed and accepted governance or architecture amendment.

A conflict between a current instruction and a higher constitutional boundary
is a stop condition, not permission to proceed. `AGENTS.md` remains subordinate
to all higher authorities and must be interpreted consistently with them.

Where D0-A4.2 applies, its narrower Controlled Governance Resilience evidence
rule governs.

This contract partitions the provider and invocation portion of the historical
I4 contract into a separate slice. It does not amend the historical contract,
reduce an invariant, or turn the original broad I4 release into current
implementation authority.

## 4. Permanent authority and permission boundary

The model boundary must preserve all of the following:

- intelligence is not authority;
- model output is not permission, approval, evidence of acceptance, or
  canonical truth by itself;
- the Apprentice remains limited to Observe and Analyse during B87-S1;
- no provider receives Execute authority;
- the provider interface supplies no database, service, repository, filesystem,
  network, credential, environment, process, tool, callback, or executable
  capability handle;
- no provider receives a database path, SQL interface, shell, communication
  channel, or mutable production object through another field;
- a provider cannot create, approve, activate, supersede, revoke, archive, or
  delete a memory;
- a provider cannot alter a task contract, governance decision, permission
  profile, runtime identity, context package, output schema, or its own
  invocation record;
- task and invocation state transitions are runtime-owned deterministic
  decisions;
- command execution by a development harness is not Apprentice Execute
  authority.

A response field, confidence value, refusal, recommendation, or claimed status
cannot expand permissions or determine acceptance.

## 5. Exact boundary with accepted B87-I4-A

B87-I4-A remains the sole owner of:

- retrieval requests;
- eligibility filtering before relevance;
- deterministic fallback ranking;
- retrieval candidates, inclusions, exclusions, and reasons;
- retrieval manifests;
- safe materialization;
- ordered context sections;
- structured context packages;
- context and manifest hashes;
- contamination findings and rejection;
- clean recovery-context construction;
- historical context reconstruction;
- current bridge-readiness assessment;
- I4-A integrity inspection.

B87-I4-B must consume I4-A through its public reconstruction and readiness
boundary. The provider must never receive:

- `ContextRetrievalService`;
- `PersistenceService`;
- `DatabaseConfig`;
- `sqlite3.Connection`;
- a repository interface;
- an object capable of reading or mutating source state.

For I4-B, D0's logical final context manifest is the accepted I4-A
`StructuredContextPackage`. The invocation must bind:

- `context_package_id`;
- the exact context-package content hash;
- `retrieval_manifest_id`;
- the exact retrieval-manifest content hash;
- `task_memory_projection_hash`;
- `task_context_finalization_id`.

I4-B must not rename, duplicate, reinterpret, or independently rebuild I4-A
eligibility, ranking, materialization, contamination, or recovery logic.

A narrowly reviewed, behaviour-preserving extraction of an internal
transaction-scoped readiness primitive is permitted only if atomic invocation
reservation cannot otherwise reuse the accepted I4-A checks. Such an extraction
must not change:

- the I4-A public result shapes;
- persisted I4-A canonical content;
- migration `0011_retrieval_context.sql`;
- eligibility or exclusion outcomes;
- rank ordering;
- contamination findings;
- recovery semantics;
- historical reconstruction.

If any substantive I4-A behaviour change is required, B87-I4-B must stop and
return a separate repair decision request.

The positive inclusion of raw Controlled Governance Resilience evidence is not
activated by this slice. Existing stricter ordinary exclusion remains
fail-closed. A future explicit-evaluation retrieval path requires its own
accepted evaluation contract and may not be inferred from mock invocation
success.

### 5.1 Historical I4 requirement ownership crosswalk

| Historical I4 requirement | Current owner and state |
| --- | --- |
| Retrieval-request contract | B87-I4-A, accepted |
| Eligibility filtering before relevance | B87-I4-A, accepted |
| Relevance interface and deterministic fallback ranker | B87-I4-A, accepted |
| Included and excluded source tracking with reasons | B87-I4-A, accepted |
| Retrieval manifest | B87-I4-A, accepted |
| Ordered structured context and hashing | B87-I4-A, accepted |
| Task, authority, policy, evidence, and memory sections | B87-I4-A, accepted |
| Ordinary restricted-evidence contamination rejection | B87-I4-A, accepted |
| Clean recovery context | B87-I4-A, accepted |
| Provider-neutral interface | B87-I4-B, proposed |
| Inactive and deterministic mock providers | B87-I4-B, proposed |
| Inactive local-provider configuration boundary | B87-I4-B, proposed |
| Structured model-input packet | B87-I4-B, proposed |
| Raw and parsed response capture | B87-I4-B, proposed |
| Response-schema validation | B87-I4-B, proposed |
| Invocation persistence and exact reconstruction | B87-I4-B, proposed |
| Inference-configuration capture | B87-I4-B, proposed |
| Model and admission metadata needed to bind one invocation | B87-I4-B model descriptor, proposed |
| Candidate registry, comparison, or admission decision | B87-PRE-I5 or B87-I5; inactive and out of scope |
| Positive controlled-evaluation evidence retrieval | Not activated; existing stricter exclusion remains fail-closed pending a separate evaluation contract |
| Real Ollama or other provider adapter | Deferred by the ratified provider-neutral, mock-or-inactive programme boundary |

Together, accepted I4-A and a future accepted I4-B are intended to satisfy the
pre-LLM production-core I4 boundary for ordinary deterministic mock invocation.
They do not complete model-in-the-loop evaluation, candidate admission, or
positive controlled-evaluation retrieval.

## 6. Future implementation entry gate

Before a future B87-I4-B implementation edit, Codex must verify and record:

1. this contract is accepted by Nolan and Byte;
2. Nolan issued `AUTHORIZE B87-I4-B` in the active task;
3. the repository is the intended Batch-87 repository;
4. the branch begins from the accepted `main` state containing this contract;
5. the branch is isolated from `main`;
6. the working tree is clean;
7. no pre-existing change is unexplained;
8. B87-I4-A remains present and accepted;
9. the complete repository test suite passes;
10. strict D0 validation passes with zero structural errors and zero closure
    blockers;
11. migrations `0001` through `0011` match their accepted hashes;
12. the scoped V0 regression decision in section 17 is accepted;
13. no model file, credential, secret, live database, private evidence, or
    external provider configuration is present;
14. no new dependency is required.

Failure of any entry condition is a stop condition.

## 7. Required immutable contracts

B87-I4-B must define immutable typed contracts and stable canonical JSON for:

1. provider descriptor;
2. model descriptor;
3. inference configuration;
4. invocation request;
5. model-input packet;
6. provider call result;
7. invocation state transition;
8. raw-output capture record;
9. deterministic decode, parse, and response-validation result;
10. parsed model output;
11. terminal finalization result;
12. invocation reconstruction.

All contracts must:

- reject unknown required-contract fields;
- reject callable values and executable handles;
- reject non-canonical JSON where canonical JSON is required;
- use stable identifiers;
- use UTC RFC 3339 timestamps;
- use SHA-256 content hashes;
- preserve exact version identifiers;
- expose total typed outcomes rather than `None`-shaped ambiguity;
- be immutable after persistence;
- keep provider-reported metadata distinguishable from runtime-observed fact.

No contract may contain a credential, secret, bearer token, API key, model-file
path, live endpoint, environment-variable reference, or executable tool
definition.

## 8. Provider and model descriptors

The initial provider modes are exactly:

```text
inactive
deterministic_mock
```

The provider descriptor must record at least:

```text
provider_id
provider_name
provider_mode
adapter_contract_version
transport_kind
capability_profile
descriptor_hash
```

For I4-B:

```text
transport_kind = none | in_process_mock
```

The capability profile must make these denials explicit:

```text
database_access = false
filesystem_access = false
repository_access = false
shell_access = false
network_access = false
credential_access = false
environment_access = false
process_access = false
communication_access = false
tool_calling = false
callback_access = false
executable_capability = false
clock_access = false
randomness = false
streaming = false
automatic_retry = false
```

The model descriptor must record an exact logical target:

```text
model_name
model_revision
quantisation
active_adapter
context_limit
```

For deterministic tests these values are synthetic fixtures. Their presence:

- does not select a base model;
- does not admit a candidate;
- does not prove that weights exist;
- does not prove that a server is running;
- does not create factual production identity.

The invocation coordinator must verify that the provider and model descriptor
match the active, integrity-valid runtime identity selected for the invocation.
I4-B may not create, replace, or approve that runtime identity.

### 8.1 Inactive local-provider configuration boundary

I4-B must define a versioned local-provider configuration schema, but the only
permitted activation state is:

```text
inactive
```

The schema may contain only:

- configuration contract version;
- logical provider identifier;
- logical adapter kind;
- activation state;
- provider descriptor hash;
- model descriptor hash;
- explicit denied capability profile.

It must not contain:

- a host;
- a port;
- a URL or endpoint;
- a socket;
- a command;
- a process identifier;
- an executable or model path;
- an environment-variable name;
- a credential or secret reference;
- an automatic-start instruction.

The configuration boundary proves that a later provider can be configured
through a versioned contract. It does not implement transport, connection,
discovery, health probing, server startup, or model loading.

## 9. Provider-neutral interface

The provider interface must be structurally narrow and closed to arbitrary
implementation injection.

Conceptually it may expose only:

```text
describe() -> immutable provider descriptor
invoke(canonical_input_bytes) -> typed provider call result containing either
                                 no output or immutable raw output bytes plus
                                 a declared encoding
```

The exact language-level names may follow repository conventions, but the
capability boundary may not broaden.

The provider receives:

- one immutable UTF-8 canonical model-input packet;
- no database, service, repository, filesystem, network, credential,
  environment, process, tool, callback, or executable capability handle;
- no mutable runtime or configuration object;
- no database path, SQL interface, shell, communication channel, factory,
  loader, entry point, or caller-supplied executable object.

During I4-B, the invocation coordinator may register exactly two concrete
provider implementations, both owned by this repository:

1. the inactive provider; and
2. the deterministic mock provider.

The registry must be closed and explicit. A caller, dependency-injection
container, configuration file, import entry point, plugin, factory, callback,
or test fixture may not register, substitute, or wrap an arbitrary provider
implementation. The public invocation boundary must accept a registered
provider identity, not an implementation object.

The inactive provider must:

- perform no call;
- return a deterministic `provider_inactive` result;
- perform no forbidden import, call, read, write, filesystem, repository, network,
  process, environment, database, credential, clock, randomness, callback,
  tool, or other observable side effect.

The deterministic mock provider must:

- be pure and in-process;
- return only pre-supplied immutable fixture bytes and their declared encoding;
- be deterministic for the same packet hash and fixture identity;
- perform no forbidden import, call, read, write, filesystem, repository,
  network, process, environment, database, credential, clock, randomness,
  callback, tool, or other observable side effect;
- expose no model behaviour claim.

Static dependency tests and instrumented runtime tests must prove those
properties for both shipped implementations and for both `describe` and
`invoke`. Provider exceptions or malformed return objects must become typed
runtime-owned failures and cannot escape as an accepted invocation.

This is an in-process Python interface boundary plus a closed implementation
registry and purity proof for the shipped code. I4-B does not claim an
operating-system sandbox, a security boundary against hostile Python code, or
isolation of arbitrary injected implementations. If hostile-code isolation is
required, I4-B must stop for a separately accepted architecture and execution
contract.

## 10. Versioned model-input packet

The initial protocol is:

```text
protocol: batch87.model-input
protocol_version: 1.0.0
```

The packet must be generated only after I4-A historical reconstruction and
current readiness both pass.

Its minimum logical shape is:

```json
{
  "protocol": "batch87.model-input",
  "protocol_version": "1.0.0",
  "invocation": {
    "model_invocation_id": "uuid",
    "task_id": "uuid",
    "session_id": "uuid",
    "project_scope_id": "uuid",
    "context_package_id": "uuid",
    "context_package_hash": "sha256",
    "retrieval_manifest_id": "uuid",
    "retrieval_manifest_hash": "sha256",
    "task_memory_projection_hash": "sha256",
    "task_context_finalization_id": "uuid",
    "runtime_identity_id": "uuid",
    "runtime_identity_hash": "sha256",
    "provider_descriptor_hash": "sha256",
    "inference_configuration_hash": "sha256",
    "output_schema_id": "schema-id",
    "output_schema_hash": "sha256"
  },
  "task": {},
  "authority": {},
  "identity": {},
  "policy": [],
  "memory": [],
  "evidence": [],
  "output_contract": {}
}
```

The packet construction rules are:

1. `task`, `authority`, `policy`, `memory`, and `evidence` are copied exactly
   from the verified I4-A context sections;
2. `identity` is a bounded projection of the active, integrity-valid factual
   runtime identity plus the current permission summary copied from the
   authoritative I4-A authority section;
3. `output_contract.schema_id` equals the task contract's
   `expected_output_schema_id`;
4. the schema identifier and hash resolve through the immutable schema registry;
5. the packet contains no prompt-role authority and no tool definitions;
6. the packet's canonical JSON and exact UTF-8 bytes are hashed before provider
   invocation;
7. the persisted request hash covers the complete packet, provider descriptor,
   model descriptor, and inference configuration;
8. a caller cannot override an authoritative task, authority, identity,
   context, or schema field.

The identity projection may disclose only the factual fields required by D0:

- Apprentice designation or agent identifier;
- runtime identity identifier;
- model name and revision;
- runtime provider;
- context limit;
- quantisation and active adapter where present;
- current permission summary;
- limitations relevant to the active task.

No unapproved capability observation, future identity content, or `SOUL.md`
content may enter the packet.

## 11. Inference configuration

Inference configuration must be canonical, immutable, bounded, and fully
captured.

It may contain only provider-neutral scalar settings required for deterministic
mock reconstruction. Unknown or provider-specific settings fail closed.

I4-B must not include:

- an endpoint;
- a host or port;
- a model path;
- a credential;
- an environment variable;
- an API header;
- tool or function definitions;
- streaming configuration;
- remote retry policy;
- provider-specific command-line arguments.

The deterministic mock path must use fixed settings. No source of randomness may
affect the expected output.

## 12. Apprentice response protocol and validation

The initial response protocol is:

```text
protocol: batch87.apprentice-response
protocol_version: 1.0.0
```

It must preserve the D0 response categories:

- task identifier;
- status;
- observations;
- inferences;
- uncertainties;
- recommendations;
- memory used;
- evidence used;
- stop request;
- stop reason.

The initial I4-B successful mock response must:

- match the active task identifier;
- use the registered schema version;
- contain no unknown fields;
- satisfy exact type and required-field checks;
- contain no fabricated authority or permission field;
- contain no tool call, executable action, capability handle, SQL, credential,
  filesystem, repository, shell, network, or communication request;
- contain no recommendation when the task contract does not permit one;
- use `stop_requested = false`.

A provider response never controls task state directly. Response `status`,
confidence, or wording is content to validate, not state-transition authority.

An unknown output schema identifier fails before provider invocation.

The first I4-B implementation must support only explicitly registered schemas
with an in-process deterministic validator. It must not introduce a general
schema-validation dependency without separate Nolan authorization.

Provider output is an opaque byte sequence. The runtime must not normalize,
decode, replace, trim, transcode, parse, validate, or repair it before durable
raw-output capture commits.

For every provider result that contains an output value, including a zero-length
byte sequence, the immutable raw-output capture must preserve:

- the exact raw bytes, including empty, NUL-containing, non-UTF-8, or otherwise
  malformed byte sequences;
- the exact byte length;
- SHA-256 over those exact bytes;
- the exact provider-declared encoding value as provider-reported metadata,
  without treating that declaration as fact;
- the raw-output identifier, invocation identifier, and runtime-observed capture
  time; and
- canonical capture metadata and its integrity hash.

Only after that capture transaction commits may the runtime reconstruct the
committed bytes and perform strict UTF-8 decoding. The deterministic validation
result must record:

```text
utf8_decode_status = not_attempted | decoded | undecodable
parse_status = parsed | malformed_json | not_attempted
schema_status = valid | invalid | not_attempted
semantic_status = valid | invalid | not_attempted
```

When decoding succeeds, the exact decoded Unicode text is preserved separately
from the raw bytes. When decoding fails, the original bytes remain intact,
`utf8_decode_status = undecodable`, later parsing and validation are
`not_attempted`, and the invocation cannot succeed. A non-UTF-8 declared
encoding is preserved as evidence but is invalid for the version 1.0.0 response
protocol even when the bytes happen to decode as UTF-8.

UTF-8 decode failure, malformed JSON, schema failure, and semantic failure must
be represented as total deterministic data with stable ordered error codes and
paths. They must not escape as uncaught parsing or validation exceptions.

No output-repair attempt is authorized in I4-B. The persisted repair fields, if
required for D0 compatibility, must remain:

```text
repair_attempted = false
repair_succeeded = false
```

Malformed or schema-invalid output remains evidence and cannot become a
successful invocation, accepted task result, memory, identity, evaluation
acceptance, or training candidate.

## 13. Governed invocation state machine

The invocation state machine is:

```text
prepared -> in_progress
prepared -> provider_inactive
in_progress -> raw_output_captured
in_progress -> provider_failed
in_progress -> timed_out
in_progress -> stale_context
in_progress -> interrupted
raw_output_captured -> succeeded
raw_output_captured -> provider_failed
raw_output_captured -> timed_out
raw_output_captured -> invalid_response
raw_output_captured -> stale_context
raw_output_captured -> interrupted
```

Required transition rules:

- only `prepared` may transition to `in_progress` or `provider_inactive`;
- only `in_progress` may transition to `raw_output_captured`,
  `provider_failed`, `timed_out`, `stale_context`, or `interrupted`;
- only `raw_output_captured` may transition to `succeeded`,
  `provider_failed`, `timed_out`, `invalid_response`, `stale_context`, or
  `interrupted`;
- `prepared`, `in_progress`, and `raw_output_captured` are non-terminal;
- `raw_output_captured` means exact raw evidence is durably committed but
  decoding, validation, or terminal finalization is incomplete;
- `provider_inactive`, `succeeded`, `provider_failed`, `timed_out`,
  `invalid_response`, `stale_context`, and `interrupted` are terminal;
- a terminal state is immutable;
- every transition is append-only and carries a runtime-owned reason code;
- the provider cannot request or write a transition;
- the same invocation identity cannot be prepared with different canonical
  content;
- automatic retry is prohibited;
- a retry requires a new invocation identifier and an explicit immutable
  `retry_of_invocation_id`;
- the prior attempt remains unchanged;
- an `in_progress` or `raw_output_captured` attempt found after interruption
  cannot be presumed failed or successful merely from elapsed time.

The model invocation identifier is the idempotency identity. Repeating the same
terminal invocation request returns or reconstructs the existing result without
calling the provider again. Reuse with different content is a conflict.

Repeating a matching non-terminal request reconstructs the visible incomplete
attempt and also makes no provider call. I4-B has no automatic replay, resume,
timeout inference, or retry path for either non-terminal state.

At most one non-terminal invocation may exist for the same task and context
package.

## 14. Transaction and lifecycle boundary

### 14.1 Preparation transaction

Before provider invocation, one governed transaction must:

1. confirm the task is active;
2. confirm the session is open or paused;
3. confirm project scope is unchanged;
4. confirm there is no blocking uncertainty;
5. reconstruct and verify the exact historical I4-A package;
6. confirm current I4-A bridge readiness;
7. confirm the package is accepted and clean;
8. confirm the runtime identity is active, scoped, and integrity-valid;
9. confirm provider, model, and runtime identity bindings;
10. confirm the output schema identifier and hash;
11. build and hash the exact model-input packet;
12. register or resolve the typed `model_invocation` reference anchor;
13. create the immutable invocation record in `prepared`;
14. claim the matching reference anchor transactionally;
15. append the `prepared` state transition.

If any step fails:

- no provider call occurs;
- no invocation success exists;
- a pre-existing registered anchor remains visibly unclaimed;
- no partial operational record masquerades as an invocation.

### 14.2 Call-start transaction

Immediately before the provider call, a short governed transaction must:

1. repeat the mutable current-readiness checks;
2. confirm the exact prepared request hash;
3. append the `in_progress` transition;
4. record the runtime-observed start time.

The provider call occurs outside the database transaction.

### 14.3 Raw-output capture transaction

Whenever a provider result contains an output value, including a zero-length
byte sequence, the runtime must first commit one dedicated governed raw-output
capture transaction. That transaction must:

1. verify the invocation identity and current `in_progress` state;
2. insert the exact raw bytes without normalization or decoding;
3. compute and insert the exact byte length and SHA-256 over those bytes;
4. preserve the declared encoding as provider-reported metadata;
5. bind the capture immutably to the invocation and provider-call result;
6. append the `raw_output_captured` transition; and
7. commit before any UTF-8 decoder, JSON parser, schema validator, semantic
   validator, output repairer, or task-transition decision runs.

The raw-output capture transaction occurs even when provider-reported metadata
claims failure, because provider metadata does not control whether returned
bytes are evidence. A provider failure or timeout with no output value may
proceed from `in_progress` to terminal finalization without a raw-output record.

If raw-output capture does not commit:

- no decoder, parser, or validator runs;
- no terminal invocation success or task completion is recorded;
- the invocation remains visibly `in_progress`;
- the provider is not called again automatically; and
- operator review is required.

### 14.4 Deterministic decoding, parsing, and validation

After raw-output capture commits, the runtime must reconstruct the exact
committed bytes, byte length, hash, and declared encoding and verify their
integrity before processing.

Strict UTF-8 decoding, JSON parsing, registered-schema validation, and
task-and-authority semantic validation then run deterministically outside the
raw-output capture transaction. Each stage consumes the preceding typed result.
Expected negative outcomes are returned as the stable data defined in section
12, never as uncaught exceptions. No stage mutates or replaces the raw capture.

An unexpected internal failure in this processing path is not converted into a
validation result or terminal state. The committed raw evidence remains
reconstructable, the invocation remains visibly `raw_output_captured`, no
success or task completion exists, no automatic retry occurs, and operator
review is required.

### 14.5 Terminal finalization transaction

After deterministic processing completes, one separate governed terminal
finalization transaction must:

1. recheck task, session, project, context, runtime identity, provider, model,
   schema, and request bindings;
2. reverify any committed raw-output bytes, length, hash, and declared encoding;
3. record runtime-observed timing;
4. record the provider result separately from runtime conclusions;
5. persist the immutable UTF-8 decode, parse, schema, and semantic results;
6. create the immutable model-output record when raw output exists;
7. append exactly one applicable terminal invocation transition; and
8. append an applicable I2 task transition only when the accepted task contract
   permits it and the task is still active.

The runtime, not the response, determines the task transition:

- `succeeded` may append task `completed` only under section 14.6;
- `provider_failed`, `provider_inactive`, `timed_out`, or `invalid_response`
  appends task `failed` with a fixed runtime-owned reason when the accepted I2
  transition remains valid;
- `stale_context` or `interrupted` appends task `failed` only when the task is
  still active and the accepted I2 transition remains valid;
- an already terminal task is never overwritten.

A behaviour-preserving extraction of the accepted I2 transaction-scoped
terminal-transition primitive is permitted if required for atomic composition.
It must not add a task state, change a transition rule, change a permission, or
allow provider-controlled reasons.

If terminal finalization fails after raw-output capture committed:

- the exact raw bytes, byte length, SHA-256, declared encoding, capture metadata,
  and `raw_output_captured` transition remain durably preserved;
- no success may be recorded;
- no task completion may be recorded;
- the invocation remains visibly non-terminal and incomplete in
  `raw_output_captured`;
- the provider call must not be repeated automatically;
- operator review is required.

If terminal finalization fails for a provider failure that returned no output,
the same no-success, no-task-completion, no-retry, and operator-review rules
apply while the invocation remains visibly `in_progress`.

### 14.6 Accepted I2 task-completion meaning

A runtime-owned I2 task completion records only that the bounded requested
operation executed and produced a response satisfying the deterministic
task/output contract.

It does not establish:

- truth;
- external approval;
- memory approval;
- evaluation success;
- model suitability;
- developmental improvement; or
- candidate admission.

Before appending task `completed`, the runtime must deterministically verify that
the accepted task contract treats a validated I4-B response as sufficient for
that bounded operation and that no human review or approval remains required.
When a task contract requires human review or approval, an I4-B invocation may
be `succeeded` and its output may remain available as evidence, but I4-B must
leave the task uncompleted and must not create, infer, or bypass the required
human decision.

## 15. Persistence contract

I4-B may add only an ordered additive migration after `0011`.

The expected minimum operational structures are:

```text
model_invocations
model_invocation_state_transitions
model_raw_outputs
model_outputs
```

The exact normalized column layout must be reviewed during implementation, but
it must preserve at least:

### `model_invocations`

- model invocation identifier;
- task, session, and project identifiers;
- context package identifier and hash;
- retrieval manifest identifier and hash;
- task-memory projection and finalization identifiers or hashes;
- runtime identity identifier and hash;
- provider and model descriptor snapshots and hashes;
- inference configuration and hash;
- output schema identifier and hash;
- complete canonical input packet;
- request hash;
- runtime-observed start and completion times;
- current status as an inspectable projection;
- optional retry relationship;
- sanitized failure classification.

### `model_invocation_state_transitions`

- transition identifier;
- model invocation identifier;
- ordered sequence number;
- prior and next status;
- reason code;
- changed-at timestamp;
- runtime principal;
- canonical content and hash.

### `model_raw_outputs`

- raw-output identifier;
- model invocation identifier;
- exact raw bytes stored as a binary value;
- exact byte length;
- SHA-256 over the exact raw bytes;
- provider-declared encoding preserved as provider-reported metadata;
- runtime-observed capture time;
- canonical capture metadata and hash;
- immutable one-to-one binding to the provider-call attempt.

### `model_outputs`

- model output identifier;
- model invocation identifier;
- raw-output evidence identifier;
- raw-output content hash;
- UTF-8 decode status;
- exact decoded Unicode text when decoding succeeds;
- deterministic parse status and ordered parse errors;
- parsed canonical JSON when valid;
- parsed-output hash when valid;
- schema identifier and hash;
- deterministic schema status and ordered validation errors;
- schema-valid flag;
- deterministic semantic status and ordered validation errors;
- semantic-valid flag;
- repair flags fixed to false;
- canonical content and hash.

Required persistence properties:

- foreign keys enabled on every connection;
- exact project-scope binding;
- typed model-invocation anchor claim;
- one operational claim per anchor;
- no orphan output;
- no raw or parsed output without an invocation;
- no parsed-output record without its exact raw-output capture;
- at most one immutable raw-output capture for one provider-call attempt;
- byte length and SHA-256 verified against the stored exact bytes;
- no accepted success without a committed raw-output capture, successful UTF-8
  decoding, successful deterministic parsing, and valid schema and semantics;
- no mutable canonical request, packet, descriptor, configuration, output, or
  transition;
- no delete path that erases invocation provenance;
- terminal invocation immutability;
- append-only state history;
- atomic raw-output capture and separate atomic terminal finalization;
- visible reconstruction of `in_progress` and `raw_output_captured` incomplete
  attempts without retry;
- deterministic integrity inspection;
- reconstructability after process restart.

Applied migrations `0001` through `0011` must not be edited, replaced, reordered,
or rehashed.

## 16. Evidence, memory, identity, and training boundary

Exact raw provider-output bytes are durable evidence. Decoded text, parsed JSON,
validation results, and runtime conclusions are separate derived records and
must never replace those bytes.

It is not automatically:

- a fact;
- an approved task result;
- Construct memory;
- self or episodic memory;
- session continuity;
- a correction;
- a lesson candidate;
- an approved lesson;
- a capability observation;
- factual identity;
- future identity;
- an evaluation pass;
- a model-admission result;
- training data.

Model-output evidence must remain excluded from ordinary retrieval unless a
later accepted contract defines a narrower governed use.

Undecodable bytes, malformed JSON, invalid schemas, negative validation results,
and captures left incomplete before terminal finalization remain preserved
negative evidence. Integrity inspection and reconstruction must verify the raw
bytes, byte length, SHA-256, declared encoding, decode status when finalized,
derived-record hashes, state history, and the visible absence of a terminal
result when finalization did not commit.

I4-B may not:

- create a memory from output;
- approve a memory;
- update runtime identity from output;
- infer capability from one mock result;
- write a training candidate;
- export a corpus;
- activate `SOUL.md`;
- claim developmental compounding.

## 17. B87-V0 regression boundary

B87-V0 accepted source baseline
`093e07a6aa9209a6ea8efe2aaecfcbdeb6829d0a` does not contain I4-B.

I4-B necessarily proposes:

- at least one additive migration;
- new persistence contracts;
- new schema-registry entries;
- new transaction semantics;
- new integrity checks.

These are explicit B87-V0 reopening triggers.

Before implementation changes a migration, schema, persistence contract, or
transaction boundary, Nolan and Byte must accept a scoped regression decision
that defines:

1. the candidate source baseline;
2. the exact changed persistence surfaces;
3. affected V0 scenarios;
4. required fresh-install and migration tests;
5. required reconstruction and interruption tests;
6. required concurrency tests;
7. whether the one-hour soak must be repeated;
8. the external harness version;
9. evidence and negative controls;
10. acceptance and stop conditions.

A scoped regression decision version 1.0 and its acceptance decision are
accepted:

```text
docs/implementation/B87-I4-B-SCOPED-V0-REGRESSION-DECISION.md
docs/implementation/B87-I4-B-SCOPED-V0-REGRESSION-ACCEPTANCE-DECISION.md
```

That acceptance satisfies only the scoped regression-planning requirement in
this section. It does not authorize implementation, transfer V0 acceptance, or
change active implementation release `NONE`. B87-I4-B implementation remains
unauthorized. Any future `AUTHORIZE B87-I4-B` release must identify accepted
regression-decision version 1.0 and its acceptance record. B87-V0 remains
accepted and closed. External regression remains prohibited until the exact
candidate commit and a valid `B87-I4B-HARNESS-FREEZE-MANIFEST-v1.0` are frozen
and all other accepted external-execution preconditions are satisfied.

An internal pytest pass cannot be substituted for required external V0
regression evidence.

The accepted V0 record remains unchanged. A later I4-B baseline must receive its
own scoped result and may not claim that V0 acceptance transferred
automatically.

## 18. Permitted future implementation files

After the exact I4-B release, the implementation may change only the smallest
coherent set under:

```text
src/batch87_apprentice/providers/
src/batch87_apprentice/invocation/
src/batch87_apprentice/persistence/
schemas/protocols/model-input/
schemas/protocols/apprentice-response/
schemas/registry.json
tests/unit/
tests/integration/
docs/implementation/
```

Permitted edits to accepted modules are limited to:

- composition-root wiring;
- an additive migration after `0011`;
- the narrow transaction-scoped I2 and I4-A helper extractions described in
  sections 5 and 14;
- integrity registration;
- public exports required by the new bridge.

Any need to modify another accepted behaviour or file family is a stop
condition requiring a scope decision.

## 19. Prohibited implementation scope

B87-I4-B must not:

- modify this contract's authority or release gate during implementation;
- edit D0 architecture to make implementation easier;
- edit migrations `0001` through `0011`;
- change an accepted I1, I2, I3, or I4-A invariant;
- introduce an ORM;
- add or change a dependency without separate Nolan authorization;
- register, inject, substitute, wrap, load, or execute an arbitrary provider
  implementation, class, factory, callback, plugin, or entry point;
- expose a public extension point that accepts provider implementation objects;
- claim operating-system sandboxing or hostile-code isolation for the
  in-process Python provider boundary;
- implement an Ollama, llama.cpp, OpenAI, Anthropic, cloud, HTTP, socket, or
  subprocess provider;
- start or probe a model server;
- download, inspect, load, or execute model weights;
- select or rank a base model;
- call a local or external model API;
- access credentials or environment secrets;
- implement streaming;
- implement tool or function calling;
- implement automatic retry;
- implement output repair;
- implement embeddings, vector search, or learned ranking;
- implement candidate-model admission;
- implement evaluation scoring or B87-PRE-I5;
- implement Validation V1;
- implement B87-I5;
- implement B87-E0, B87-E1, or B87-E2;
- import an experimental implementation into production core;
- implement training, fine-tuning, adapters, or reinforcement learning;
- activate self-authored identity;
- expand Apprentice permissions;
- deploy or publish anything.

## 20. Required deterministic tests

The future implementation must include tests proving at least:

### Contract and canonicalization

1. every contract is immutable;
2. unknown fields fail closed;
3. invalid identifiers, timestamps, enums, and hashes fail closed;
4. canonical JSON and UTF-8 packet bytes are deterministic;
5. the same canonical inputs produce the same packet and request hashes;
6. a single changed input changes the applicable hash;
7. prohibited capability handles, callable values, executable objects, and
   secret-shaped fields are rejected structurally.

### I4-A integration

8. a missing context package blocks before provider access;
9. an integrity-invalid package blocks before provider access;
10. a rejected or contaminated package blocks before provider access;
11. a package that is no longer currently ready blocks before provider access;
12. blocking uncertainty blocks before provider access;
13. task, session, or project drift blocks before provider access;
14. the exact accepted I4-A package and manifest hashes are preserved;
15. provider code receives no I4-A service, repository, database, context
    service, configuration object, or executable handle;
16. all accepted I4-A tests remain unchanged in behaviour and passing.

### Identity and schema

17. missing, inactive, superseded, mismatched, or integrity-invalid runtime
    identity blocks invocation;
18. provider and model descriptor mismatch blocks invocation;
19. unknown output schema blocks invocation;
20. schema-hash mismatch blocks invocation;
21. caller override of an authoritative packet field is rejected.

### Closed provider boundary and shipped-implementation purity

22. the inactive provider performs no call and returns a typed result;
23. the mock provider is deterministic;
24. both shipped implementations receive only the documented immutable
    canonical input bytes through `invoke`, and `describe` receives no runtime
    object;
25. the closed registry resolves exactly the repository-owned inactive provider
    and deterministic mock provider;
26. caller-, configuration-, container-, factory-, callback-, plugin-,
    entry-point-, and fixture-supplied arbitrary provider implementations are
    rejected before execution;
27. the provider interface supplies no database, service, repository,
    filesystem, network, credential, environment, process, tool, callback, or
    executable capability handle;
28. static source and dependency checks prove that both shipped implementations
    perform no forbidden imports;
29. instrumented runtime checks prove that both shipped implementations,
    including `describe` and `invoke`, perform no forbidden calls, reads,
    writes, process creation, network activity, environment access, database
    access, credential access, clock access, randomness, callback or tool use,
    or other observable side effects;
30. the inactive provider and deterministic mock provider return only their
    contract-authorized typed values and pre-supplied immutable fixture bytes;
31. provider exceptions and malformed provider results fail closed as
    runtime-owned typed failures;
32. a provider cannot write its own invocation or task status;
33. architecture tests prove there is no public arbitrary-provider extension
    point and do not represent the in-process boundary as an operating-system
    sandbox or hostile-code isolation.

### Durable raw-output capture and deterministic validation

34. the dedicated raw-output capture transaction commits before any UTF-8
    decoder, JSON parser, schema validator, semantic validator, or terminal
    finalizer is invoked;
35. exact raw bytes, exact byte length, SHA-256 over those bytes, declared
    encoding, capture identity, and capture metadata reconstruct exactly;
36. empty, NUL-containing, and undecodable byte sequences are preserved
    byte-for-byte without normalization or replacement;
37. strict UTF-8 success and failure produce deterministic `decoded` and
    `undecodable` statuses;
38. a non-UTF-8 declared encoding is preserved and fails the version 1.0.0
    protocol even when the bytes are valid UTF-8;
39. undecodable output remains evidence, records later processing as
    `not_attempted`, and cannot succeed;
40. malformed JSON remains evidence, produces deterministic parse-failure data,
    and cannot succeed;
41. valid JSON with an invalid schema remains evidence, produces deterministic
    validation-failure data, and cannot succeed;
42. decode, parse, schema, and semantic failures use stable ordered error codes
    and paths rather than uncaught expected exceptions;
43. unknown response fields are rejected;
44. a mismatched task identifier is rejected;
45. tool, capability, credential, SQL, filesystem, repository, shell, network,
    communication, callback, or executable fields are rejected;
46. disallowed recommendations are rejected;
47. `stop_requested = true` cannot direct an I2 task stop;
48. no repair is attempted;
49. a valid deterministic mock response succeeds only after raw capture,
    decoding, parsing, schema validation, and semantic validation all succeed.

### Transactions, idempotency, and interruption

50. preparation failure makes no provider call;
51. anchor claim is typed, scoped, one-time, and transactional;
52. conflicting invocation-identity reuse fails;
53. repeated terminal request reconstruction makes no second provider call;
54. repeated matching `in_progress` or `raw_output_captured` reconstruction
    makes no second provider call;
55. concurrent same-identity preparation admits at most one record;
56. at most one non-terminal invocation exists for the same task and context;
57. retry requires a new identity and preserves the prior attempt;
58. no automatic retry occurs after failure, interruption, capture failure, or
    incomplete finalization;
59. injected failure at each preparation step leaves no partial invocation;
60. injected failure at each raw-output capture step invokes no decoder or
    validator, creates no success or task completion, and leaves the invocation
    visibly `in_progress`;
61. the raw-output capture and terminal finalization are separate committed
    transactions;
62. injected failure after raw capture and before terminal finalization
    preserves the exact committed raw evidence and
    `raw_output_captured` transition, leaves the invocation visibly
    non-terminal, creates no success or task completion, and triggers no retry;
63. an unexpected internal decoding, parsing, validation, or finalization
    failure has the same incomplete, preserved-evidence, no-retry result;
64. provider failure and timeout cannot create success;
65. provider failure or timeout with returned bytes captures those bytes before
    terminal classification;
66. task or context drift after a provider returns preserves any raw output and
    produces `stale_context` only through terminal finalization;
67. an interrupted `in_progress` or `raw_output_captured` attempt remains
    visible and non-successful;
68. no terminal state can transition again;
69. provider response content cannot choose an invocation or task transition.

### Accepted I2 task-completion semantics

70. successful runtime validation may produce the fixed runtime-owned task
    completion transition only when the accepted task/output contract makes the
    response sufficient and requires no outstanding human decision;
71. task completion records only that the bounded requested operation executed
    and produced a response satisfying the deterministic task/output contract;
72. task completion does not establish truth, external approval, memory
    approval, evaluation success, model suitability, developmental improvement,
    or candidate admission;
73. a task contract requiring human review or approval may retain a succeeded
    invocation but remains uncompleted until that human decision occurs;
74. model output cannot create, simulate, infer, or bypass human review or
    approval.

### Reconstruction and integrity

75. invocation reconstruction verifies every parent and content hash;
76. reconstruction reproduces the exact canonical input packet;
77. reconstruction reproduces raw bytes byte-for-byte and verifies byte length,
    SHA-256, declared encoding, decode status, parsed representation, and every
    derived-result hash;
78. undecodable and malformed output reconstructs without loss;
79. `raw_output_captured` reconstructs as visibly incomplete when terminal
    finalization is absent;
80. reconstruction works after database reopen;
81. reconstruction works in a separate process;
82. current staleness does not rewrite historical invocation state;
83. raw-byte, byte-length, declared-encoding, decode-status, parsed-output,
    transition, or parent corruption is detected by dedicated and top-level
    integrity inspection;
84. unclaimed, multiply claimed, or mismatched anchors are detected;
85. no invocation, raw output, parsed output, or negative result can be deleted
    to erase evidence.

### Architecture and regression

86. production core imports when experimental packages are absent;
87. production core contains no import from experimental implementations;
88. only the two repository-owned I4-B provider implementations are registrable;
89. no model, provider server, endpoint, credential, or private data is present;
90. the complete repository suite remains passing;
91. strict D0 validation remains passing;
92. the accepted scoped V0 regression plan is executed as required before
    acceptance.

## 21. Required validation gate

The future implementation run must execute and report:

1. Python syntax and import validation;
2. closed-provider-registry and arbitrary-injection rejection tests;
3. shipped-provider static import and dependency checks;
4. instrumented shipped-provider no-side-effect tests;
5. focused I4-B unit tests;
6. focused I4-B integration tests;
7. repeated critical raw-capture, finalization, idempotency, and interruption
   tests;
8. the complete pytest suite;
9. strict D0 architecture validation;
10. fresh-database migration application;
11. repeated migration startup;
12. migration tamper detection;
13. SQLite foreign-key and integrity checks;
14. architecture dependency checks;
15. `git diff --check`;
16. exact tracked and untracked file inspection;
17. prohibited-artifact inspection;
18. the separately accepted V0 regression sequence.

Every command, result, count, warning, failure, and unexecuted gate must be
reported exactly. A check that was not run is not passed.

## 22. Implementation completion boundary

B87-I4-B is complete for Nolan-Byte review only when:

- all required contracts exist and are versioned;
- I4-A context is consumed without exposing its services to the provider;
- only the repository-owned inactive and deterministic mock providers are
  registrable;
- the shipped providers satisfy the static dependency and instrumented
  no-side-effect boundary;
- the provider interface supplies no prohibited capability handle;
- the in-process boundary makes no operating-system sandbox or hostile-code
  isolation claim;
- one full successful mock invocation is preserved and reconstructable;
- every failure path remains non-successful and auditable;
- typed model-invocation anchors are claimed transactionally;
- exact raw bytes, byte length, SHA-256, and declared encoding commit in the
  dedicated capture transaction before decoding, parsing, or validation;
- UTF-8 decode, parse, schema, and semantic failures are deterministic data;
- failure after capture and before terminal finalization preserves raw evidence,
  remains visibly incomplete, creates no task completion, and causes no retry;
- malformed output cannot pass;
- task transitions remain runtime-owned;
- I2 task completion has only the bounded meaning in section 14.6 and cannot
  bypass required human review or approval;
- no provider receives a database, service, repository, filesystem, network,
  credential, environment, process, tool, callback, or executable capability
  handle;
- no real model, server, endpoint, or API is present;
- no dependency was added without authority;
- all required internal validation passes;
- the required scoped V0 regression evidence is complete;
- the implementation evidence packet is complete;
- the final diff contains only the accepted I4-B file set.

Completion does not mean:

- the slice is accepted;
- B87-I4 is accepted in aggregate;
- a base model is selected;
- model behaviour is validated;
- memory efficacy is demonstrated;
- candidate admission may begin;
- Validation V1 may begin;
- Apprentice permissions expand.

Codex must stop after the evidence report. Nolan and Byte decide acceptance.

## 23. Immediate stop conditions

The future implementation must stop when:

- the I4-A/I4-B boundary requires substantive redesign;
- a real provider or model becomes necessary;
- an external call becomes necessary;
- a credential or private datum is encountered;
- an existing migration would need modification;
- a new dependency becomes necessary without separate authority;
- atomic preparation, raw-output capture, or terminal finalization cannot be
  achieved without duplicating or weakening I2 authority;
- the closed provider registry or shipped-implementation purity proof cannot be
  demonstrated;
- arbitrary or hostile provider code would need to be accepted;
- operating-system sandboxing or hostile-code isolation would be required;
- exact raw bytes cannot be committed before decoding, parsing, or validation;
- a post-capture failure could erase evidence, create a terminal result, complete
  a task, or trigger an automatic retry;
- exact reconstruction cannot be achieved;
- the output schema cannot be validated deterministically;
- a provider failure could create success;
- a model-output field could control authority or task state;
- an I4-B response could bypass required human review or approval;
- V0 regression scope is missing or ambiguous;
- an experimental implementation would become a production dependency;
- a test exposes a governance contradiction;
- a failure cannot be attributed confidently;
- unrelated or unexplained working-tree changes appear;
- completion would require B87-PRE-I5, B87-I5, external Validation V1, or
  experimental scope.

The stop report must identify the exact blocker, inspected evidence, affected
files, commands, partial changes, preserved state, and smallest Nolan-Byte
decision required.

## 24. Required implementation evidence packet

The future B87-I4-B implementation report must include:

1. repository, branch, worktree, starting commit, and ending commit;
2. exact operator release instruction;
3. governing documents read;
4. accepted I4-A baseline;
5. implemented and explicitly unimplemented requirements;
6. changed-file inventory;
7. migration and schema inventory;
8. typed-anchor claim design;
9. closed-registry and arbitrary-provider-injection rejection proof;
10. shipped-provider static import and instrumented no-side-effect proof;
11. explicit acknowledgement that I4-B supplies no operating-system sandbox or
    hostile-code isolation;
12. input-packet and response-schema hashes;
13. raw-output capture proof covering exact bytes, length, SHA-256, declared
    encoding, and committed-before-processing order;
14. decode, parse, validation, and terminal-finalization evidence, including
    undecodable and malformed output;
15. injected post-capture failure evidence proving durable raw preservation,
    visible incompleteness, no success, no task completion, and no retry;
16. I2 task-completion and required-human-review distinction evidence;
17. focused and complete test commands and results;
18. repeated transaction and interruption evidence;
19. reconstruction and integrity evidence;
20. architecture dependency evidence;
21. V0 regression decision and results;
22. prohibited-artifact inspection;
23. final diff and Git state;
24. known limitations and unresolved risks;
25. stop conditions encountered;
26. recommendation for Nolan-Byte review.

The report must not declare acceptance.

## 25. Contract review gate

Before accepting this contract, Nolan and Byte should verify:

1. the slice is provider-neutral and implementable without a real model;
2. the I4-A boundary remains authoritative and non-duplicated;
3. the interface supplies no database, service, repository, filesystem,
   network, credential, environment, process, tool, callback, or executable
   capability handle;
4. only the repository-owned inactive and deterministic mock implementations
   may be registered, and arbitrary provider injection is prohibited;
5. required tests prove the shipped implementations perform no forbidden
   imports, calls, reads, writes, process creation, network activity,
   environment access, clock access, randomness, or other observable side
   effects;
6. the boundary is accurately described as in-process Python contract and
   shipped-code purity, without an operating-system sandbox or hostile-code
   isolation claim;
7. exact raw bytes, byte length, SHA-256, and declared encoding commit before
   decoding, parsing, or validation;
8. UTF-8 decode, parse, schema, and semantic failures are deterministic data,
   while undecodable or malformed output remains durable evidence;
9. raw capture and terminal finalization are separate transactions, and a
   failure between them leaves visible incomplete evidence with no success,
   task completion, or automatic retry;
10. packet, raw output, derived results, state, and invocation reconstruction
    are exact and integrity-verified;
11. runtime identity binding is factual and does not select a model;
12. task transitions cannot be controlled by model output;
13. I2 task completion has only the bounded meaning in section 14.6 and cannot
    bypass required human review or approval;
14. interruption and duplicate delivery cannot masquerade as success;
15. raw output remains evidence rather than memory or authority;
16. no dependency, model, server, API, evaluation, training, identity, tool, or
    experimental scope is activated;
17. the V0 reopening and regression gate is proportionate and explicit;
18. `AUTHORIZE B87-I4-B` is the correct future implementation release token.

Acceptance of this contract should be recorded separately from any
implementation commit and must not itself issue the implementation release.
