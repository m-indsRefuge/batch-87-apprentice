CREATE TABLE runtime_instances (
    runtime_instance_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    stopped_at TEXT,
    application_version TEXT NOT NULL CHECK (trim(application_version) <> ''),
    host_fingerprint TEXT,
    process_id INTEGER CHECK (process_id IS NULL OR process_id > 0),
    status TEXT NOT NULL CHECK (status IN ('running', 'stopped', 'failed')),
    CHECK (stopped_at IS NULL OR stopped_at >= started_at)
);

CREATE TABLE entities (
    entity_id TEXT PRIMARY KEY,
    entity_kind TEXT NOT NULL CHECK (
        entity_kind IN (
            'person', 'agent', 'project', 'repository',
            'organisation', 'system', 'component'
        )
    ),
    canonical_name TEXT NOT NULL CHECK (trim(canonical_name) <> ''),
    description TEXT NOT NULL CHECK (trim(description) <> ''),
    status TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'archived')),
    created_at TEXT NOT NULL
);

CREATE TABLE scopes (
    scope_id TEXT PRIMARY KEY,
    scope_kind TEXT NOT NULL CHECK (
        scope_kind IN (
            'construct', 'project', 'repository', 'component',
            'session', 'task', 'evaluation'
        )
    ),
    canonical_name TEXT NOT NULL CHECK (trim(canonical_name) <> ''),
    parent_scope_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'archived')),
    FOREIGN KEY (parent_scope_id) REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    CHECK (parent_scope_id IS NULL OR parent_scope_id <> scope_id),
    UNIQUE (scope_kind, canonical_name)
);

CREATE TABLE entity_aliases (
    entity_alias_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    alias TEXT NOT NULL CHECK (trim(alias) <> ''),
    scope_id TEXT,
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (scope_id) REFERENCES scopes(scope_id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX entity_aliases_scoped_alias
ON entity_aliases (
    entity_id,
    alias,
    COALESCE(scope_id, '')
);

CREATE TABLE records (
    record_id TEXT PRIMARY KEY,
    record_family TEXT NOT NULL CHECK (trim(record_family) <> ''),
    record_type TEXT NOT NULL CHECK (trim(record_type) <> ''),
    schema_version TEXT NOT NULL CHECK (trim(schema_version) <> ''),

    construct_scope_id TEXT,
    project_scope_id TEXT,
    subject_entity_id TEXT,
    session_id TEXT,
    task_id TEXT,

    lifecycle_state TEXT NOT NULL CHECK (
        lifecycle_state IN (
            'observed', 'candidate', 'reviewed', 'approved', 'active',
            'superseded', 'revoked', 'archived', 'deleted'
        )
    ),
    approval_status TEXT NOT NULL CHECK (
        approval_status IN (
            'not_required', 'pending', 'approved', 'rejected', 'withdrawn'
        )
    ),
    authority_class TEXT NOT NULL CHECK (
        authority_class IN (
            'law_or_external_obligation', 'nolan_approved',
            'nolan_byte_approved', 'validated_system_evidence',
            'approved_project_policy', 'approved_memory',
            'approved_evaluation', 'agent_proposal', 'model_inference',
            'external_untrusted', 'unknown'
        )
    ),
    certainty_class TEXT NOT NULL CHECK (
        certainty_class IN (
            'verified', 'strongly_supported', 'inferred',
            'speculative', 'disputed', 'unknown'
        )
    ),
    sensitivity_class TEXT NOT NULL CHECK (
        sensitivity_class IN (
            'public', 'internal', 'confidential', 'restricted', 'secret'
        )
    ),
    privacy_class TEXT NOT NULL CHECK (
        privacy_class IN (
            'none', 'personal', 'sensitive_personal', 'credential',
            'legally_restricted', 'unknown'
        )
    ),
    retention_class TEXT NOT NULL CHECK (
        retention_class IN (
            'ephemeral', 'temporary', 'project_duration', 'long_term',
            'permanent_history', 'legally_governed'
        )
    ),
    training_eligibility TEXT NOT NULL CHECK (
        training_eligibility IN (
            'ineligible', 'pending_review', 'approved', 'prohibited'
        )
    ),

    created_at TEXT NOT NULL,
    created_by_entity_id TEXT,
    created_by_runtime_id TEXT,
    effective_from TEXT,
    effective_until TEXT,
    review_due_at TEXT,

    supersedes_record_id TEXT,
    superseded_by_record_id TEXT,
    previous_version_id TEXT,

    source_kind TEXT NOT NULL CHECK (
        source_kind IN (
            'human_statement', 'project_document', 'test', 'runtime_event',
            'model_output', 'external_source', 'derived_record'
        )
    ),
    provenance_summary TEXT NOT NULL CHECK (trim(provenance_summary) <> ''),
    retrieval_policy_json TEXT NOT NULL CHECK (
        json_valid(retrieval_policy_json)
        AND json_type(retrieval_policy_json) = 'object'
    ),
    deletion_policy_json TEXT NOT NULL CHECK (
        json_valid(deletion_policy_json)
        AND json_type(deletion_policy_json) = 'object'
    ),
    agent_write_policy TEXT NOT NULL CHECK (
        agent_write_policy IN (
            'prohibited', 'candidate_only', 'externally_approved'
        )
    ),

    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    integrity_status TEXT NOT NULL CHECK (
        integrity_status IN ('valid', 'mismatch', 'unavailable', 'not_applicable')
    ),
    deleted_at TEXT,
    deletion_basis TEXT,

    FOREIGN KEY (construct_scope_id) REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id) REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (subject_entity_id) REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by_entity_id) REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by_runtime_id)
        REFERENCES runtime_instances(runtime_instance_id) ON DELETE RESTRICT,
    FOREIGN KEY (supersedes_record_id)
        REFERENCES records(record_id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (superseded_by_record_id)
        REFERENCES records(record_id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (previous_version_id)
        REFERENCES records(record_id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,

    CHECK (
        NOT (lifecycle_state = 'active' AND approval_status = 'rejected')
    ),
    CHECK (
        supersedes_record_id IS NULL OR supersedes_record_id <> record_id
    ),
    CHECK (
        superseded_by_record_id IS NULL OR superseded_by_record_id <> record_id
    ),
    CHECK (previous_version_id IS NULL OR previous_version_id <> record_id),
    CHECK (
        effective_from IS NULL
        OR effective_until IS NULL
        OR effective_from <= effective_until
    ),
    CHECK (
        training_eligibility <> 'approved' OR privacy_class = 'none'
    ),
    CHECK (
        record_family <> 'evaluation_evidence' OR project_scope_id IS NOT NULL
    ),
    CHECK (
        (lifecycle_state = 'deleted' AND deleted_at IS NOT NULL
            AND deletion_basis IS NOT NULL)
        OR
        (lifecycle_state <> 'deleted' AND deleted_at IS NULL)
    )
);

CREATE INDEX records_family_type
ON records(record_family, record_type);

CREATE INDEX records_project_lifecycle
ON records(project_scope_id, lifecycle_state);

CREATE INDEX records_approval_lifecycle
ON records(approval_status, lifecycle_state);

CREATE INDEX records_subject
ON records(subject_entity_id);

CREATE INDEX records_supersedes
ON records(supersedes_record_id);

CREATE TRIGGER records_record_id_immutable
BEFORE UPDATE OF record_id ON records
WHEN NEW.record_id <> OLD.record_id
BEGIN
    SELECT RAISE(ABORT, 'record_id is immutable');
END;
