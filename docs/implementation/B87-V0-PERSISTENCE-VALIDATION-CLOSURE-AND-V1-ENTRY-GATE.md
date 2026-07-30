# B87-V0 Persistence Validation Closure and V1 Entry Gate

## 1. Decision status

**Decision:** ACCEPTED AND CLOSED

**Accepted source baseline:**

```text
branch: main
commit: 093e07a6aa9209a6ea8efe2aaecfcbdeb6829d0a
```

**External validation harness:**

```text
C:\Users\nolan\AIProjects\batch-87-external-validation
```

**Validated repository:**

```text
C:\Users\nolan\AIProjects\batch-87-apprentice
```

This record closes the first external validation phase for the Batch-87
Apprentice persistence foundation. It does not replace the governing D0
architecture, implementation contracts, implementation acceptance decisions,
or repository authority boundaries.

## 2. Scope of acceptance

B87-V0 tested whether the accepted Batch-87 source baseline could be installed,
migrated, reconstructed, written to, interrupted, recovered, read concurrently,
written concurrently, and operated under a bounded sustained workload without
violating the tested persistence and integrity invariants.

B87-V0 therefore accepts the persistence subsystem as a sufficiently validated
foundation for the next memory-system validation phase under the tested
configuration and workload boundaries.

This acceptance does not establish that the complete Apprentice system works.
It does not establish model behaviour, memory efficacy, retrieval quality,
context quality, developmental compounding, base-model suitability, autonomous
action, or general production readiness.

## 3. Accepted validation sequence

The following external validation scenarios are accepted:

| Test | Validation purpose | Result |
| --- | --- | --- |
| V0-T01 | Clean installation | PASS |
| V0-T02 | Fresh database and migration execution | PASS |
| V0-T03 | Separate-process reconstruction | PASS |
| V0-T04 | Governed write | PASS |
| V0-T05 | Pre-commit termination | PASS |
| V0-T06 | Duplicate governed-write rejection | PASS |
| V0-T07 | Conflicting governed-identity rejection | PASS |
| V0-T08 | Post-commit recovery | PASS |
| V0-T09 | Concurrent same-identity contention | PASS |
| V0-T10 | Concurrent distinct governed writes | PASS |
| V0-T11 | Commit-boundary read visibility | PASS |
| V0-T12 | Sustained concurrent-reader stability | PASS |
| V0-T13 | Sustained multiwriter contention | PASS |
| V0-T14 | One-hour bounded soak | PASS |

The external evidence repository and its immutable run directories remain the
authoritative detailed evidence source for commands, assertions, process data,
database snapshots, hashes, negative controls, and terminal transcripts.

## 4. Key accepted evidence

### 4.1 V0-T13 sustained multiwriter contention

```text
run_id: 20260730T071712Z
writers: 3
readers: 4
expected_records: 24
committed_records: 24
reader_observations: 169
writer_lock_errors: 0
reader_lock_errors: 0
classification: successful_validation
status: PASS
```

V0-T13 demonstrated successful multi-process contention with all expected
writes committed, no writer or reader lock errors, unique committed identities,
valid observed committed states, clean foreign-key checks, clean SQLite
integrity, and a successful negative control.

### 4.2 V0-T14 one-hour bounded soak

```text
run_id: 20260730T072321Z
configured_duration_seconds: 3600
observed_duration_seconds: 3602.514
writers: 2
readers: 3
committed_records: 11311
reader_observations: 36071
checkpoints: 11
writer_lock_errors: 0
reader_lock_errors: 0
classification: successful_validation
status: PASS
```

V0-T14 demonstrated full-duration bounded operation with sustained governed
writes and concurrent reads, periodic progress checkpoints, deterministic stop
and collection, no reported writer or reader lock errors, and successful final
classification by the external controller assertion set.

## 5. Accepted conclusions

Subject to the limits in this record, the validated persistence foundation has
demonstrated:

- reproducible installation from the accepted source baseline;
- deterministic fresh-database migration execution;
- reconstruction from a separate process;
- governed record creation and retention;
- rejection of tested duplicate and conflicting governed identities;
- preservation of transaction boundaries under tested termination conditions;
- recovery after tested pre-commit and post-commit process interruption;
- valid commit-boundary read visibility;
- concurrent same-identity and distinct-identity handling;
- sustained concurrent-reader stability;
- sustained multiwriter operation without observed lock failure;
- one-hour bounded endurance at the validated workload scale;
- clean tested SQLite integrity and foreign-key conditions;
- preservation of the accepted Batch-87 source checkout during validation; and
- detection of the harness negative controls used by the accepted scenarios.

These results materially reduce persistence-layer uncertainty. Future defects
must still be investigated from evidence, but ordinary development should not
reopen the persistence foundation without a concrete trigger.

## 6. Limits and non-claims

B87-V0 does not prove:

- correctness under every operating system, filesystem, SQLite build, hardware
  configuration, or deployment topology;
- correctness under arbitrary process counts, database sizes, write rates,
  transaction shapes, or indefinite runtime;
- resistance to hardware failure, disk exhaustion, filesystem corruption,
  malicious database modification, or power loss at every possible boundary;
- semantic correctness of memory retrieval, synthesis, conflict resolution,
  context assembly, or developmental derivation;
- model-level reasoning, learning, continuity, identity, or safe tool use;
- that all future migrations or schema changes inherit this acceptance; or
- permission to activate future Apprentice capabilities.

Any material change to migrations, transaction semantics, persistence contracts,
identity rules, integrity enforcement, or deployment environment requires a
scoped regression decision and may require partial or complete V0 revalidation.

## 7. V0 closure rule

V0 is closed. Additional persistence scenarios are not required merely because
more tests are possible.

Persistence validation reopens only when triggered by one or more of:

- a persistence defect or unexplained integrity anomaly;
- a migration or schema change;
- a transaction-boundary or concurrency-model change;
- a governed identity or persistence-contract change;
- a materially different runtime or deployment environment;
- a materially different workload profile; or
- an explicit Nolan–Byte acceptance decision.

## 8. Validation V1 definition

**Validation V1** is an external validation programme phase. It is distinct from
and must not be confused with the repository's B87-I1 through B87-I5
implementation sequence.

Validation V1 asks:

> Can the implemented Batch-87 memory system persist, reconstruct, retrieve,
> isolate, conflict-check, finalize, and resume governed memory across processes
> and sessions without inventing continuity or violating authority, provenance,
> privacy, lifecycle, retention, or evidence boundaries?

Validation V1 may test only capabilities already implemented and released under
the governing implementation contracts. A validation plan cannot authorize new
runtime capability.

## 9. Validation V1 entry gate

Validation V1 may begin only when all of the following are true:

1. the candidate source commit is explicitly frozen and recorded;
2. the applicable memory-domain and retrieval implementation slices are merged
   and internally accepted;
3. the complete repository test suite passes at the candidate commit;
4. strict D0 architecture validation passes;
5. migrations apply successfully to a fresh database;
6. the external harness operates outside the Batch-87 source repository;
7. test data is synthetic or specifically approved and contains no prohibited
   secrets or personal information;
8. expected authority, provenance, lifecycle, privacy, retention, uncertainty,
   and retrieval outcomes are defined before execution;
9. negative controls are included; and
10. Nolan explicitly authorizes the Validation V1 execution sequence.

## 10. Proposed Validation V1 sequence

The proposed sequence is:

| Test | Proposed validation purpose |
| --- | --- |
| V1-T01 | Full three-memory-domain reconstruction across a fresh process |
| V1-T02 | Memory-domain and scope isolation |
| V1-T03 | Governed retrieval inclusion and exclusion |
| V1-T04 | Conflicting evidence and uncertainty preservation |
| V1-T05 | Session finalization and promotion-boundary enforcement |
| V1-T06 | Cross-session continuity without invented state |
| V1-T07 | Bounded multi-session correction-retention experiment |

Each test requires its own contract, fixtures, assertions, negative control,
evidence bundle, stop conditions, and Nolan–Byte acceptance review.

## 11. First compounding-development experiment boundary

After V1-T01 through V1-T06 are accepted, V1-T07 may test whether an approved
correction from an earlier bounded task improves a later related decision
without base-weight modification.

The experiment must verify at least:

- the correction is retained with exact provenance;
- retrieval occurs only in an eligible context;
- the correction remains distinguishable from fact, authority, and evidence;
- the later task benefits without repeating the correction manually;
- the system does not overgeneralize the correction;
- conflicting or lower-authority evidence is not silently erased;
- no session evidence enters durable memory without the required lifecycle and
  approval path; and
- measured improvement is attributed to governed memory use rather than an
  unsupported claim of learning or intelligence.

## 12. Immediate programme action

The primary build thread should now:

1. record this V0 closure as the accepted external persistence-validation
   milestone;
2. inspect the current implementation state after commit
   `093e07a6aa9209a6ea8efe2aaecfcbdeb6829d0a`;
3. reconcile repository documentation that still describes an earlier active
   implementation phase;
4. identify the next authorized implementation slice under the existing
   programme contracts;
5. avoid further horizontal V0 expansion unless a reopening trigger exists;
6. prepare the Validation V1 contract only for capabilities that are already
   implemented and internally accepted; and
7. preserve Nolan's explicit phase-release authority before implementation or
   validation execution.

## 13. Authority statement

This closure accepts an evidence-backed subsystem milestone. It does not grant
the Apprentice, Codex, a model, a harness, or a validation result any authority
to release phases, approve memories, expand permissions, modify governance,
activate identity development, or perform consequential action.

Nolan retains final human authority. Byte provides architecture, synthesis,
governance review, and developmental evaluation. Applicable law and
non-derogable human protection remain above project authority.
