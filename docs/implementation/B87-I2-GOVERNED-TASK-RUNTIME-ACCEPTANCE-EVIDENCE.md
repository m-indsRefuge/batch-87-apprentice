# B87-I2 Governed Task Runtime Acceptance Evidence

Status: Complete
Accepted implementation commit: 01f00e419f30db2b5025f9c2e9920506a598c8aa
Accepted review-directed repair commit: 5da8110b5c844b1a3d419ad3e5dd5a76f774c162
Merge commit: 7294efcbe455e6a8b10fc7027a5bcedb12a7001d
Pull request: #6

## Validation record

- Complete accepted test suite before merge: 149 passed
- Complete post-merge test suite on `main`: 149 passed
- Strict D0 closure validation: PASS
- Structural and invariant errors: 0
- Closure blockers: 0
- Byte semantic and adversarial review: complete
- Review-directed repair validation: PASS
- File-backed SQLite reconstruction: PASS
- Decision, evidence, and task-stop rollback validation: PASS
- Authority, human-approval, operation-classification, and principal-boundary tests: PASS
- Post-merge local and remote parity: PASS
- Final working tree: clean

The standing D0 closure-claim warning remains expected: architecture closure does
not establish future model behaviour, memory efficacy, developmental compounding,
or base-model suitability.

## Migration hashes

    0001_system_entities_records.sql
    4b17bba385254cc532785e2dfed08e27ffbc5b1c4537c22447982cb24a053f77

    0002_evidence.sql
    d266b07159f002f5a068d7e8ca0314c5a5e2e9a829639ac1f961941e3c629134

    0003_controlled_resilience.sql
    982872f104192f243d8ab676ab448daa004d40be9de560efd065fbabb2c19a28

    0004_governed_task_runtime.sql
    54f2d1e10d7ffdcee4e64e6746b883b2f1d366da3d78ac656e631f71a1527a70

## Accepted governance evidence

The accepted runtime proves that:

- Observe and Analyse are the Apprentice's only B87-S1 permissions;
- Execute and autonomous action remain unavailable;
- development execution is attributed to `codex_development_harness`, not the Apprentice;
- authority must be typed, pre-registered, scope-bounded, and time-bounded;
- unsupported, missing, expired, future, mismatched, revoked, or out-of-scope authority fails closed;
- human approvals are explicit, scoped, expiring, and single-use where required;
- authoritative operation definitions prevent caller misclassification;
- lower authority cannot override higher authority;
- model-shaped content cannot create authority or change a governance decision;
- required task stops and decision relationships are persisted atomically;
- incomplete decision evidence cannot finalise a transaction;
- failed decision, evidence, or task-stop persistence rolls back completely;
- file-backed reopening reconstructs the exact governed transaction;
- integrity inspection exposes incomplete or corrupted I2 relationships and lifecycle history.

## Review-directed repair closure

Byte review identified and the accepted repair closed:

- missing explicit single-use human-approval semantics;
- caller-controlled operation-classification bypass;
- incomplete decision-evidence finalisation;
- pre-merge lifecycle compatibility for sessions, tasks, and authority revocation.

The repair remained within B87-I2 and introduced no migration `0005` or later-phase behaviour.

## Scope exclusions

B87-I2 did not implement memory-domain behaviour, retrieval, ranking, context
assembly, providers, model loading or invocation, model selection, recovery,
training, identity progression, autonomous tools, experimental laboratories,
deployment, or B87-I3 behaviour.

## Conclusion

    B87-I2 ACCEPTANCE EVIDENCE COMPLETE
