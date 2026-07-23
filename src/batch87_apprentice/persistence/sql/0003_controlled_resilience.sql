CREATE TABLE governed_reference_anchors (
    reference_id TEXT NOT NULL,
    reference_kind TEXT NOT NULL CHECK (
        reference_kind IN (
            'evaluation_experiment', 'evaluation_fixture',
            'context_manifest', 'model_invocation'
        )
    ),
    project_scope_id TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL CHECK (
        lifecycle_state IN ('registered', 'claimed', 'invalid', 'retired')
    ),
    created_at TEXT NOT NULL,
    provenance_json TEXT NOT NULL CHECK (
        json_valid(provenance_json)
        AND json_type(provenance_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    integrity_status TEXT NOT NULL CHECK (
        integrity_status IN ('valid', 'mismatch', 'unavailable')
    ),
    PRIMARY KEY (reference_id, reference_kind),
    UNIQUE (reference_id),
    UNIQUE (reference_id, reference_kind, project_scope_id),
    FOREIGN KEY (project_scope_id) REFERENCES scopes(scope_id) ON DELETE RESTRICT
);

CREATE INDEX governed_reference_anchors_scope
ON governed_reference_anchors(project_scope_id, reference_kind);

CREATE TRIGGER governed_reference_anchor_core_immutable
BEFORE UPDATE OF reference_id, reference_kind, project_scope_id, created_at,
                 provenance_json, content_hash
ON governed_reference_anchors
BEGIN
    SELECT RAISE(ABORT, 'reference anchor provenance is immutable');
END;

CREATE TRIGGER governed_reference_anchor_transition
BEFORE UPDATE OF lifecycle_state ON governed_reference_anchors
WHEN NOT (
    NEW.lifecycle_state = OLD.lifecycle_state
    OR (OLD.lifecycle_state = 'registered'
        AND NEW.lifecycle_state IN ('claimed', 'invalid', 'retired'))
    OR (OLD.lifecycle_state = 'claimed'
        AND NEW.lifecycle_state IN ('invalid', 'retired'))
    OR (OLD.lifecycle_state = 'invalid' AND NEW.lifecycle_state = 'retired')
)
BEGIN
    SELECT RAISE(ABORT, 'invalid reference anchor lifecycle transition');
END;

CREATE TRIGGER governed_reference_anchor_ownerless_claim
BEFORE UPDATE OF lifecycle_state ON governed_reference_anchors
WHEN OLD.lifecycle_state <> 'claimed' AND NEW.lifecycle_state = 'claimed'
BEGIN
    SELECT RAISE(ABORT, 'claimed anchor requires a transactional operational owner');
END;

CREATE TRIGGER governed_reference_anchor_no_delete
BEFORE DELETE ON governed_reference_anchors
BEGIN
    SELECT RAISE(ABORT, 'reference anchors cannot be deleted');
END;

CREATE TABLE controlled_resilience_evidence (
    record_id TEXT PRIMARY KEY,
    evaluation_mode TEXT NOT NULL CHECK (
        evaluation_mode = 'controlled_governance_resilience'
    ),
    experiment_id TEXT NOT NULL,
    experiment_reference_kind TEXT NOT NULL DEFAULT 'evaluation_experiment'
        CHECK (experiment_reference_kind = 'evaluation_experiment'),
    fixture_id TEXT NOT NULL,
    fixture_reference_kind TEXT NOT NULL DEFAULT 'evaluation_fixture'
        CHECK (fixture_reference_kind = 'evaluation_fixture'),
    test_family TEXT NOT NULL CHECK (trim(test_family) <> ''),
    test_level INTEGER NOT NULL CHECK (test_level > 0),
    test_condition TEXT NOT NULL CHECK (
        test_condition IN (
            'invalid', 'valid_authority_control', 'neutral_control', 'recovery'
        )
    ),
    run_id TEXT NOT NULL,
    governance_distinction TEXT NOT NULL CHECK (
        trim(governance_distinction) <> ''
    ),
    maximum_test_intensity TEXT NOT NULL CHECK (
        trim(maximum_test_intensity) <> ''
    ),
    raw_prompt_evidence_id TEXT NOT NULL,
    raw_output_evidence_id TEXT NOT NULL,
    context_manifest_id TEXT NOT NULL,
    context_manifest_reference_kind TEXT NOT NULL DEFAULT 'context_manifest'
        CHECK (context_manifest_reference_kind = 'context_manifest'),
    model_invocation_id TEXT NOT NULL,
    model_invocation_reference_kind TEXT NOT NULL DEFAULT 'model_invocation'
        CHECK (model_invocation_reference_kind = 'model_invocation'),
    recovery_record_id TEXT,
    ordinary_memory_eligibility TEXT NOT NULL CHECK (
        ordinary_memory_eligibility = 'prohibited'
    ),
    identity_eligibility TEXT NOT NULL CHECK (
        identity_eligibility = 'prohibited'
    ),
    lesson_derivation_status TEXT NOT NULL CHECK (
        lesson_derivation_status IN (
            'not_reviewed', 'prohibited', 'candidate_created',
            'no_lesson_required'
        )
    ),
    completion_state TEXT NOT NULL CHECK (
        completion_state IN ('exploratory', 'incomplete')
    ),
    created_at TEXT NOT NULL,

    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (raw_prompt_evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT,
    FOREIGN KEY (raw_output_evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT,
    FOREIGN KEY (recovery_record_id)
        REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (experiment_id, experiment_reference_kind)
        REFERENCES governed_reference_anchors(reference_id, reference_kind)
        ON DELETE RESTRICT,
    FOREIGN KEY (fixture_id, fixture_reference_kind)
        REFERENCES governed_reference_anchors(reference_id, reference_kind)
        ON DELETE RESTRICT,
    FOREIGN KEY (context_manifest_id, context_manifest_reference_kind)
        REFERENCES governed_reference_anchors(reference_id, reference_kind)
        ON DELETE RESTRICT,
    FOREIGN KEY (model_invocation_id, model_invocation_reference_kind)
        REFERENCES governed_reference_anchors(reference_id, reference_kind)
        ON DELETE RESTRICT,
    CHECK (raw_prompt_evidence_id <> raw_output_evidence_id),
    CHECK (recovery_record_id IS NULL OR recovery_record_id <> record_id)
);

CREATE TRIGGER controlled_resilience_validate_parents
BEFORE INSERT ON controlled_resilience_evidence
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM records AS record
        WHERE record.record_id = NEW.record_id
          AND record.record_family = 'evaluation_evidence'
          AND record.record_type = 'controlled_governance_resilience_run'
          AND record.project_scope_id IS NOT NULL
          AND record.lifecycle_state IN (
              'observed', 'reviewed', 'approved', 'archived'
          )
          AND record.sensitivity_class = 'restricted'
          AND record.training_eligibility = 'prohibited'
          AND record.integrity_status = 'valid'
          AND json_extract(
              record.retrieval_policy_json,
              '$.retrieval_mode'
          ) = 'evaluation_only'
          AND json_extract(
              record.retrieval_policy_json,
              '$.ordinary_memory_eligibility'
          ) = 'prohibited'
    ) THEN RAISE(ABORT, 'invalid controlled-resilience envelope') END;

    SELECT CASE WHEN EXISTS (
        SELECT 1
        FROM governed_reference_anchors AS anchor
        JOIN records AS record ON record.record_id = NEW.record_id
        WHERE anchor.reference_id IN (
            NEW.experiment_id,
            NEW.fixture_id,
            NEW.context_manifest_id,
            NEW.model_invocation_id
        )
          AND (
              anchor.project_scope_id <> record.project_scope_id
              OR anchor.lifecycle_state NOT IN ('registered', 'claimed')
              OR anchor.integrity_status <> 'valid'
          )
    ) THEN RAISE(ABORT, 'invalid or cross-scope reference anchor') END;

    SELECT CASE WHEN EXISTS (
        SELECT 1
        FROM evidence_items
        WHERE evidence_id IN (
            NEW.raw_prompt_evidence_id,
            NEW.raw_output_evidence_id
        )
          AND integrity_status <> 'valid'
    ) THEN RAISE(ABORT, 'controlled evidence integrity is not valid') END;

    SELECT CASE WHEN EXISTS (
        SELECT 1
        FROM record_evidence_links
        WHERE evidence_id IN (
            NEW.raw_prompt_evidence_id,
            NEW.raw_output_evidence_id
        )
          AND record_id <> NEW.record_id
    ) THEN RAISE(ABORT, 'controlled evidence has a non-isolated record link') END;

    SELECT CASE WHEN NEW.recovery_record_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM records AS recovery
        JOIN records AS record ON record.record_id = NEW.record_id
        WHERE recovery.record_id = NEW.recovery_record_id
          AND recovery.project_scope_id = record.project_scope_id
    ) THEN RAISE(ABORT, 'recovery record scope mismatch') END;
END;

CREATE TRIGGER controlled_resilience_evidence_link_isolation
BEFORE INSERT ON record_evidence_links
WHEN EXISTS (
    SELECT 1
    FROM controlled_resilience_evidence
    WHERE (
        raw_prompt_evidence_id = NEW.evidence_id
        AND (
            record_id <> NEW.record_id
            OR NEW.relationship NOT IN (
                'evaluated_against', 'does_not_establish'
            )
        )
    )
    OR (
        raw_output_evidence_id = NEW.evidence_id
        AND (
            record_id <> NEW.record_id
            OR NEW.relationship NOT IN ('produced_as', 'does_not_establish')
        )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'controlled evidence link would weaken isolation');
END;

CREATE TRIGGER controlled_resilience_mandatory_link_no_update
BEFORE UPDATE OF record_id, evidence_id, relationship ON record_evidence_links
WHEN EXISTS (
    SELECT 1
    FROM controlled_resilience_evidence
    WHERE (
        record_id = OLD.record_id
        AND raw_prompt_evidence_id = OLD.evidence_id
        AND OLD.relationship = 'evaluated_against'
    )
    OR (
        record_id = OLD.record_id
        AND raw_output_evidence_id = OLD.evidence_id
        AND OLD.relationship = 'produced_as'
    )
)
BEGIN
    SELECT RAISE(ABORT, 'mandatory controlled evidence link is immutable');
END;

CREATE TRIGGER controlled_resilience_mandatory_link_no_delete
BEFORE DELETE ON record_evidence_links
WHEN EXISTS (
    SELECT 1
    FROM controlled_resilience_evidence
    WHERE (
        record_id = OLD.record_id
        AND raw_prompt_evidence_id = OLD.evidence_id
        AND OLD.relationship = 'evaluated_against'
    )
    OR (
        record_id = OLD.record_id
        AND raw_output_evidence_id = OLD.evidence_id
        AND OLD.relationship = 'produced_as'
    )
)
BEGIN
    SELECT RAISE(ABORT, 'mandatory controlled evidence link cannot be deleted');
END;

CREATE TRIGGER controlled_resilience_payload_immutable
BEFORE UPDATE ON controlled_resilience_evidence
BEGIN
    SELECT RAISE(ABORT, 'raw controlled-resilience payload is immutable');
END;

CREATE TRIGGER controlled_resilience_payload_no_delete
BEFORE DELETE ON controlled_resilience_evidence
BEGIN
    SELECT RAISE(ABORT, 'raw controlled-resilience payload cannot be deleted');
END;

CREATE TRIGGER controlled_resilience_envelope_classification_immutable
BEFORE UPDATE OF record_family, record_type, project_scope_id,
                 sensitivity_class, retrieval_policy_json,
                 training_eligibility, content_hash
ON records
WHEN EXISTS (
    SELECT 1
    FROM controlled_resilience_evidence
    WHERE record_id = OLD.record_id
)
BEGIN
    SELECT RAISE(ABORT, 'controlled-resilience classification is immutable');
END;

CREATE TRIGGER controlled_resilience_envelope_state_guard
BEFORE UPDATE OF lifecycle_state, integrity_status ON records
WHEN EXISTS (
    SELECT 1
    FROM controlled_resilience_evidence
    WHERE record_id = OLD.record_id
)
AND (
    NEW.lifecycle_state NOT IN ('observed', 'reviewed', 'approved', 'archived')
    OR NEW.integrity_status NOT IN ('valid', 'mismatch', 'unavailable')
)
BEGIN
    SELECT RAISE(ABORT, 'invalid controlled-resilience envelope state');
END;

CREATE TRIGGER controlled_resilience_prompt_evidence_immutable
BEFORE UPDATE OF evidence_id, evidence_kind, storage_kind, storage_location,
                 original_name, media_type, byte_length, content_hash,
                 captured_at, captured_by_entity, redaction_status,
                 sensitivity_class, privacy_class
ON evidence_items
WHEN EXISTS (
    SELECT 1
    FROM controlled_resilience_evidence
    WHERE raw_prompt_evidence_id = OLD.evidence_id
       OR raw_output_evidence_id = OLD.evidence_id
)
BEGIN
    SELECT RAISE(ABORT, 'raw controlled-resilience evidence is immutable');
END;

CREATE TRIGGER controlled_resilience_evidence_no_delete
BEFORE DELETE ON evidence_items
WHEN EXISTS (
    SELECT 1
    FROM controlled_resilience_evidence
    WHERE raw_prompt_evidence_id = OLD.evidence_id
       OR raw_output_evidence_id = OLD.evidence_id
)
BEGIN
    SELECT RAISE(ABORT, 'raw controlled-resilience evidence cannot be deleted');
END;
