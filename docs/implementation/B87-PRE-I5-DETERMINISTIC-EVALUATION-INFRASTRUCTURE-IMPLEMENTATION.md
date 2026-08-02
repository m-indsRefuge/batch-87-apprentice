# B87-PRE-I5 Deterministic Evaluation Infrastructure Implementation

## Status and authority

This record describes the bounded implementation candidate released by Nolan's
exact instruction `AUTHORIZE B87-PRE-I5`. It is an implementation record, not
an acceptance decision. Byte and Nolan retain review and acceptance authority.

The implementation and Byte-Nolan review-directed repair begin from merge baseline
`d8258520a53955e23834e362837088bd1acb12b1`. B87-I5, live-provider use,
candidate-model execution, candidate admission, and B87-E0 through B87-E2
remain inactive and unauthorized.

## Implemented boundary

The `batch87_apprentice.evaluation` package provides deterministic contracts
and services for:

- immutable candidate metadata registration without acceptance or activation;
- immutable configuration, score-schema, critical-failure-schema, condition,
  fixture-set, and resource metadata;
- exact local UTF-8 JSON fixture discovery, hashing, membership, sensitivity,
  provenance, and ordering checks;
- blinded, repeated, enabled, withheld, and over-transfer run planning;
- append-only result evidence and atomic terminal transitions;
- exact candidate, fixture, configuration, plan, run, result, and transition
  reconstruction;
- deterministic blinded reports that separate missing evidence, invalidation,
  numeric observations, and non-identifying latency while retaining raw
  candidate-reported, replay, and runtime metadata only in reconstruction;
- synthetic-only mock campaign recording and replay; and
- read-only PRE-I5 and SQLite integrity inspection.

The public service accepts structured metadata and stored synthetic evidence.
It has no provider registry, invocation method, executable configuration,
network configuration, credential field, process launcher, or model-artifact
path.

## Persistence identity

Migration `0013_deterministic_evaluation.sql` follows accepted migration 0012.
It adds only PRE-I5 tables, indexes, constraints, and immutability/state
transition triggers. Migrations 0001 through 0012 remain byte-identical.

The migration persists:

- candidate metadata;
- fixture-set manifests and exact fixture bytes represented as canonical JSON;
- evaluation configurations;
- plans and blinded candidate bindings;
- ordered runs;
- result evidence; and
- run-state transitions.

Fixture-set identity uses a composite logical `fixture_set_id` plus version, so
multiple immutable set versions coexist under one logical identity. Individual
fixtures, evaluation configurations, and evaluation plans use version-instance
identity: every version receives a new immutable UUID, carries an explicit
`*_family_id`, and is unique by family plus version. Reusing one instance UUID
for another version or registering two instances for one family/version fails
closed. Plans bind the exact configuration UUID/hash and fixture-set
ID/version/hash that existed when they were created; later registrations cannot
silently rebind an earlier plan.

All PRE-I5 records are immutable after insertion. Result insertion and its
terminal transition share one governed transaction. Foreign-key bindings carry
the relevant parent content hash so identity alone cannot silently rebind a
child to altered metadata.

## Deterministic reconstruction and reporting

Reconstruction verifies canonical JSON, content hashes, relational projections,
fixture membership and byte length, parent hashes, complete plan matrices,
ordered run identities, transition histories, result schemas, and result/run
bindings. Contradiction or tamper evidence fails closed.

Reports are derived only from verified reconstruction. They expose blinded
candidate identifiers and explicitly set admission effect and ranking authority
to `none`. Candidate-reported metadata, replay metadata, runtime hardware
metadata, candidate IDs and hashes, model family and revision, identifying
artifact data, and the candidate-to-blind mapping are omitted. A recursive
identity-leak check must pass before a report declares blinding preserved.
The immutable raw evidence remains available through reconstruction only.

The `withheld` condition means approved developmental memory is unavailable; it
is independent of result outcome. Enabled, memory-withheld, and over-transfer
runs may each record `completed`, `critical_failure`, `incomplete`, `invalid`,
or `interrupted`. Reports expose a deterministic enabled-versus-withheld score
and outcome comparison, while genuinely absent results remain
`missing_evidence`. Critical invalidation is not converted to a numeric score,
and negative evidence remains visible.

## Deliberately unimplemented

This slice does not implement or activate:

- any model download, load, serving, provider call, or candidate-suite run;
- provider host, port, endpoint, URL, credential, secret, executable, or model
  path configuration;
- candidate selection, admission, acceptance, activation, or promotion;
- learned evaluation, reward models, ranking, training, reinforcement learning,
  or search-based promotion;
- hidden-reasoning, sentience, loyalty, or anthropomorphic scoring;
- Apprentice Execute permission, tools, autonomous action, or `SOUL.md`;
- B87-I5 or B87-E0 through B87-E2; or
- merge, publication, deployment, or external validation.

## Validation boundary

The candidate validation suite covers contracts, fixture fail-closed behavior,
fresh and populated upgrades, rollback, migration tamper, repeated startup,
version coexistence and identity conflicts, immutable plan bindings, atomic
commit visibility, reconstruction tamper, adversarial report identity leakage,
deterministic enabled-versus-withheld reporting, synthetic campaign replay,
fresh-process replay,
SQLite integrity and foreign keys, dependency direction, and static absence of
live execution paths. Exact commands and results belong in the phase evidence
packet produced after the candidate commit.
