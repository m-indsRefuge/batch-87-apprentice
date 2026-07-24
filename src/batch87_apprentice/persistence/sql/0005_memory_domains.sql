CREATE TABLE memory_domains (
    memory_domain TEXT PRIMARY KEY CHECK (
        memory_domain IN (
            'construct_relational',
            'self_episodic',
            'session_task'
        )
    ),
    status TEXT NOT NULL CHECK (status = 'active')
);

INSERT INTO memory_domains (memory_domain, status) VALUES
    ('construct_relational', 'active'),
    ('self_episodic', 'active'),
    ('session_task', 'active');

CREATE TRIGGER memory_domains_immutable
BEFORE UPDATE ON memory_domains
BEGIN
    SELECT RAISE(ABORT, 'memory domains are immutable');
END;

CREATE TRIGGER memory_domains_no_delete
BEFORE DELETE ON memory_domains
BEGIN
    SELECT RAISE(ABORT, 'memory domains cannot be deleted');
END;

CREATE TABLE memory_record_types (
    record_family TEXT NOT NULL,
    record_type TEXT NOT NULL,
    memory_domain TEXT NOT NULL,
    approval_requirement TEXT NOT NULL CHECK (
        approval_requirement IN ('not_required', 'external')
    ),
    agent_write_policy TEXT NOT NULL CHECK (
        agent_write_policy IN ('prohibited', 'candidate_only', 'externally_approved')
    ),
    status TEXT NOT NULL CHECK (status = 'active'),
    PRIMARY KEY (record_family, record_type),
    FOREIGN KEY (memory_domain)
        REFERENCES memory_domains(memory_domain) ON DELETE RESTRICT
);

INSERT INTO memory_record_types (
    record_family, record_type, memory_domain,
    approval_requirement, agent_write_policy, status
) VALUES
    ('construct_memory', 'construct_entity', 'construct_relational', 'external', 'candidate_only', 'active'),
    ('construct_memory', 'construct_relationship', 'construct_relational', 'external', 'candidate_only', 'active'),
    ('construct_memory', 'architecture_decision', 'construct_relational', 'external', 'prohibited', 'active'),
    ('construct_memory', 'project_state', 'construct_relational', 'external', 'candidate_only', 'active'),
    ('construct_memory', 'construct_doctrine', 'construct_relational', 'external', 'prohibited', 'active'),
    ('construct_memory', 'terminology_definition', 'construct_relational', 'external', 'candidate_only', 'active'),
    ('construct_memory', 'preference_record', 'construct_relational', 'external', 'candidate_only', 'active'),
    ('self_model', 'runtime_identity', 'self_episodic', 'not_required', 'prohibited', 'active'),
    ('self_model', 'capability_observation', 'self_episodic', 'external', 'candidate_only', 'active'),
    ('self_model', 'maturity_state', 'self_episodic', 'external', 'prohibited', 'active'),
    ('episodic_memory', 'episode', 'self_episodic', 'external', 'prohibited', 'active'),
    ('episodic_memory', 'correction', 'self_episodic', 'external', 'prohibited', 'active'),
    ('episodic_memory', 'lesson_candidate', 'self_episodic', 'external', 'candidate_only', 'active'),
    ('episodic_memory', 'approved_lesson', 'self_episodic', 'external', 'prohibited', 'active'),
    ('episodic_memory', 'failure_pattern', 'self_episodic', 'external', 'candidate_only', 'active'),
    ('episodic_memory', 'success_pattern', 'self_episodic', 'external', 'candidate_only', 'active'),
    ('session_task_memory', 'active_uncertainty', 'session_task', 'not_required', 'candidate_only', 'active');

CREATE TRIGGER memory_record_types_immutable
BEFORE UPDATE ON memory_record_types
BEGIN
    SELECT RAISE(ABORT, 'memory record types are immutable');
END;

CREATE TRIGGER memory_record_types_no_delete
BEFORE DELETE ON memory_record_types
BEGIN
    SELECT RAISE(ABORT, 'memory record types cannot be deleted');
END;


CREATE TRIGGER memory_records_initial_contract_guard
BEFORE INSERT ON records
WHEN EXISTS (
    SELECT 1 FROM memory_record_types AS type
    WHERE type.record_family = NEW.record_family
      AND type.record_type = NEW.record_type
)
AND (
    NEW.project_scope_id IS NULL
    OR NEW.lifecycle_state NOT IN ('observed', 'candidate', 'reviewed')
    OR (
        (
            SELECT approval_requirement
            FROM memory_record_types
            WHERE record_family = NEW.record_family
              AND record_type = NEW.record_type
        ) = 'external'
        AND NEW.approval_status <> 'pending'
    )
    OR (
        (
            SELECT approval_requirement
            FROM memory_record_types
            WHERE record_family = NEW.record_family
              AND record_type = NEW.record_type
        ) = 'not_required'
        AND NEW.approval_status <> 'not_required'
    )
    OR NEW.agent_write_policy <> (
        SELECT agent_write_policy
        FROM memory_record_types
        WHERE record_family = NEW.record_family
          AND record_type = NEW.record_type
    )
)
BEGIN
    SELECT RAISE(ABORT, 'memory record violates its registered initial contract');
END;

CREATE TABLE memory_record_lifecycle_transitions (
    transition_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    from_state TEXT CHECK (
        from_state IS NULL OR from_state IN (
            'observed', 'candidate', 'reviewed', 'approved', 'active',
            'superseded', 'revoked', 'archived', 'deleted'
        )
    ),
    to_state TEXT NOT NULL CHECK (
        to_state IN (
            'observed', 'candidate', 'reviewed', 'approved', 'active',
            'superseded', 'revoked', 'archived', 'deleted'
        )
    ),
    reason_code TEXT NOT NULL CHECK (trim(reason_code) <> ''),
    changed_at TEXT NOT NULL,
    changed_by_principal TEXT NOT NULL CHECK (
        changed_by_principal IN (
            'apprentice', 'operator', 'codex_development_harness'
        )
    ),
    changed_by_entity_id TEXT,
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    UNIQUE (record_id, sequence_number),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (changed_by_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    CHECK (
        (
            sequence_number = 0
            AND from_state IS NULL
            AND to_state IN ('observed', 'candidate', 'reviewed')
            AND changed_by_principal IN ('operator', 'codex_development_harness')
        )
        OR
        (
            sequence_number > 0
            AND (
                (from_state = 'observed' AND to_state IN (
                    'candidate', 'reviewed', 'revoked', 'archived', 'deleted'
                ))
                OR
                (from_state = 'candidate' AND to_state IN (
                    'reviewed', 'revoked', 'archived', 'deleted'
                ))
                OR
                (from_state = 'reviewed' AND to_state IN (
                    'approved', 'revoked', 'archived', 'deleted'
                ))
                OR
                (from_state = 'approved' AND to_state IN (
                    'active', 'revoked', 'archived', 'deleted'
                ))
                OR
                (from_state = 'active' AND to_state IN (
                    'superseded', 'revoked', 'archived', 'deleted'
                ))
                OR
                (from_state = 'superseded' AND to_state IN (
                    'revoked', 'archived', 'deleted'
                ))
                OR
                (from_state = 'revoked' AND to_state IN ('archived', 'deleted'))
                OR
                (from_state = 'archived' AND to_state = 'deleted')
            )
        )
    )
);

CREATE TABLE memory_record_approval_transitions (
    transition_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    from_status TEXT CHECK (
        from_status IS NULL OR from_status IN (
            'not_required', 'pending', 'approved', 'rejected', 'withdrawn'
        )
    ),
    to_status TEXT NOT NULL CHECK (
        to_status IN (
            'not_required', 'pending', 'approved', 'rejected', 'withdrawn'
        )
    ),
    reason_code TEXT NOT NULL CHECK (trim(reason_code) <> ''),
    changed_at TEXT NOT NULL,
    changed_by_principal TEXT NOT NULL CHECK (
        changed_by_principal IN ('operator', 'codex_development_harness')
    ),
    changed_by_entity_id TEXT,
    authority_record_id TEXT,
    approval_evidence_id TEXT,
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    UNIQUE (record_id, sequence_number),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (changed_by_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (authority_record_id)
        REFERENCES authority_records(authority_record_id) ON DELETE RESTRICT,
    FOREIGN KEY (approval_evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT,
    CHECK (
        (
            sequence_number = 0
            AND from_status IS NULL
            AND to_status IN ('pending', 'not_required')
        )
        OR
        (
            sequence_number > 0
            AND (
                (from_status = 'pending' AND to_status IN (
                    'approved', 'rejected', 'withdrawn'
                ))
                OR
                (from_status = 'approved' AND to_status = 'withdrawn')
            )
        )
    ),
    CHECK (
        (sequence_number = 0 AND authority_record_id IS NULL
            AND approval_evidence_id IS NULL)
        OR
        (sequence_number > 0 AND authority_record_id IS NOT NULL
            AND approval_evidence_id IS NOT NULL)
    ),
    CHECK (to_status <> 'approved' OR approval_evidence_id IS NOT NULL)
);

CREATE TABLE record_relationships (
    relationship_id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL,
    target_record_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL CHECK (
        relationship_type IN (
            'derived_from', 'supports', 'contradicts', 'corrects', 'evaluates',
            'supersedes', 'revokes', 'applies_to', 'occurred_during',
            'approved_as', 'blocked_by', 'requires_review'
        )
    ),
    created_at TEXT NOT NULL,
    created_by_principal TEXT NOT NULL CHECK (
        created_by_principal IN (
            'apprentice', 'operator', 'codex_development_harness'
        )
    ),
    authority_record_id TEXT,
    explanation TEXT NOT NULL CHECK (trim(explanation) <> ''),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    UNIQUE (source_record_id, target_record_id, relationship_type),
    FOREIGN KEY (source_record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (target_record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (authority_record_id)
        REFERENCES authority_records(authority_record_id) ON DELETE RESTRICT,
    CHECK (source_record_id <> target_record_id)
);

CREATE TABLE memory_eligibility_assessments (
    assessment_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_project_scope_id TEXT NOT NULL,
    requested_domain TEXT NOT NULL CHECK (
        requested_domain IN (
            'construct_relational',
            'self_episodic',
            'session_task'
        )
    ),
    evaluated_at TEXT NOT NULL,
    eligible INTEGER NOT NULL CHECK (eligible IN (0, 1)),
    reason_codes_json TEXT NOT NULL CHECK (
        json_valid(reason_codes_json) AND json_type(reason_codes_json) = 'array'
    ),
    policy_version TEXT NOT NULL CHECK (trim(policy_version) <> ''),
    record_snapshot_json TEXT NOT NULL CHECK (
        json_valid(record_snapshot_json)
        AND json_type(record_snapshot_json) = 'object'
    ),
    record_snapshot_hash TEXT NOT NULL CHECK (
        length(record_snapshot_hash) = 64
        AND record_snapshot_hash NOT GLOB '*[^0-9a-f]*'
    ),
    context_json TEXT NOT NULL CHECK (
        json_valid(context_json) AND json_type(context_json) = 'object'
    ),
    context_hash TEXT NOT NULL CHECK (
        length(context_hash) = 64
        AND context_hash NOT GLOB '*[^0-9a-f]*'
    ),
    decision_hash TEXT NOT NULL CHECK (
        length(decision_hash) = 64
        AND decision_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
    FOREIGN KEY (task_project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    CHECK (
        (eligible = 1 AND reason_codes_json = '[]')
        OR
        (eligible = 0 AND reason_codes_json <> '[]')
    )
);

CREATE INDEX memory_lifecycle_record_sequence
ON memory_record_lifecycle_transitions(record_id, sequence_number);

CREATE INDEX memory_approval_record_sequence
ON memory_record_approval_transitions(record_id, sequence_number);

CREATE INDEX record_relationships_source
ON record_relationships(source_record_id, relationship_type);

CREATE INDEX record_relationships_target
ON record_relationships(target_record_id, relationship_type);

CREATE INDEX memory_eligibility_task
ON memory_eligibility_assessments(task_id, evaluated_at);

CREATE INDEX memory_eligibility_record
ON memory_eligibility_assessments(record_id, evaluated_at);


CREATE TRIGGER memory_lifecycle_apprentice_guard
BEFORE INSERT ON memory_record_lifecycle_transitions
WHEN NEW.changed_by_principal = 'apprentice'
AND (
    NEW.to_state <> 'candidate'
    OR NOT EXISTS (
        SELECT 1
        FROM records AS record
        JOIN memory_record_types AS type
          ON type.record_family = record.record_family
         AND type.record_type = record.record_type
        WHERE record.record_id = NEW.record_id
          AND record.agent_write_policy = 'candidate_only'
          AND type.agent_write_policy = 'candidate_only'
    )
)
BEGIN
    SELECT RAISE(ABORT, 'Apprentice memory writes are candidate-only');
END;

CREATE TRIGGER memory_approval_authority_guard
BEFORE INSERT ON memory_record_approval_transitions
WHEN NEW.sequence_number > 0
AND NOT EXISTS (
    SELECT 1
    FROM authority_records AS authority
    JOIN records AS record ON record.record_id = NEW.record_id
    WHERE authority.authority_record_id = NEW.authority_record_id
      AND authority.status = 'active'
      AND authority.effect = 'allow'
      AND authority.effective_from <= NEW.changed_at
      AND (authority.effective_until IS NULL OR authority.effective_until >= NEW.changed_at)
      AND authority.authority_class IN (
          'law_or_external_obligation',
          'nolan_approved',
          'nolan_byte_approved',
          'validated_system_evidence',
          'approved_project_policy'
      )
      AND authority.project_scope_id = record.project_scope_id
      AND (
          authority.issuer_entity_id IS NULL
          OR authority.issuer_entity_id = NEW.changed_by_entity_id
      )
      AND NOT EXISTS (
          SELECT 1 FROM authority_revocations AS revocation
          WHERE revocation.authority_record_id = authority.authority_record_id
      )
)
BEGIN
    SELECT RAISE(ABORT, 'memory approval requires valid scoped authority');
END;

CREATE TRIGGER memory_approval_evidence_guard
BEFORE INSERT ON memory_record_approval_transitions
WHEN NEW.sequence_number > 0
AND NOT EXISTS (
    SELECT 1
    FROM evidence_items AS evidence
    JOIN authority_record_evidence AS authority_evidence
      ON authority_evidence.evidence_id = evidence.evidence_id
    WHERE evidence.evidence_id = NEW.approval_evidence_id
      AND authority_evidence.authority_record_id = NEW.authority_record_id
      AND evidence.integrity_status = 'valid'
      AND evidence.evidence_kind NOT IN (
          'model_output', 'controlled_prompt', 'controlled_output'
      )
)
BEGIN
    SELECT RAISE(ABORT, 'memory approval requires authority-linked external evidence');
END;

CREATE TRIGGER record_relationships_memory_endpoint_guard
BEFORE INSERT ON record_relationships
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS record
    JOIN memory_record_types AS type
      ON type.record_family = record.record_family
     AND type.record_type = record.record_type
    WHERE record.record_id IN (NEW.source_record_id, NEW.target_record_id)
)
BEGIN
    SELECT RAISE(ABORT, 'record relationship requires a memory endpoint');
END;

CREATE TRIGGER record_relationships_governed_authority_guard
BEFORE INSERT ON record_relationships
WHEN NEW.relationship_type IN ('corrects', 'supersedes', 'revokes', 'approved_as')
AND (
    NEW.created_by_principal <> 'operator'
    OR NEW.authority_record_id IS NULL
    OR NOT EXISTS (
        SELECT 1 FROM authority_records AS authority
        WHERE authority.authority_record_id = NEW.authority_record_id
          AND authority.status = 'active'
      AND authority.effect = 'allow'
      AND authority.effective_from <= NEW.created_at
      AND (authority.effective_until IS NULL OR authority.effective_until >= NEW.created_at)
          AND authority.authority_class IN (
              'law_or_external_obligation',
              'nolan_approved',
              'nolan_byte_approved',
              'validated_system_evidence',
              'approved_project_policy'
          )
          AND authority.project_scope_id = (
              SELECT MIN(project_scope_id) FROM records
              WHERE record_id IN (NEW.source_record_id, NEW.target_record_id)
          )
          AND 1 = (
              SELECT COUNT(DISTINCT project_scope_id) FROM records
              WHERE record_id IN (NEW.source_record_id, NEW.target_record_id)
                AND project_scope_id IS NOT NULL
          )
          AND 2 = (
              SELECT COUNT(*) FROM records
              WHERE record_id IN (NEW.source_record_id, NEW.target_record_id)
                AND project_scope_id IS NOT NULL
          )
          AND NOT EXISTS (
              SELECT 1 FROM authority_revocations AS revocation
              WHERE revocation.authority_record_id = authority.authority_record_id
          )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'governed record relationship lacks valid authority');
END;

CREATE TRIGGER memory_lifecycle_transition_validates_record
BEFORE INSERT ON memory_record_lifecycle_transitions
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS record
    JOIN memory_record_types AS type
      ON type.record_family = record.record_family
     AND type.record_type = record.record_type
    WHERE record.record_id = NEW.record_id
      AND type.status = 'active'
)
BEGIN
    SELECT RAISE(ABORT, 'lifecycle transition requires a registered memory record');
END;

CREATE TRIGGER memory_lifecycle_transition_validates_sequence
BEFORE INSERT ON memory_record_lifecycle_transitions
WHEN (
    NEW.sequence_number = 0
    AND (
        NEW.from_state IS NOT NULL
        OR EXISTS (
            SELECT 1 FROM memory_record_lifecycle_transitions
            WHERE record_id = NEW.record_id
        )
        OR NEW.to_state <> (
            SELECT lifecycle_state FROM records WHERE record_id = NEW.record_id
        )
    )
)
OR (
    NEW.sequence_number > 0
    AND (
        NEW.sequence_number <> COALESCE((
            SELECT MAX(sequence_number) + 1
            FROM memory_record_lifecycle_transitions
            WHERE record_id = NEW.record_id
        ), 0)
        OR NEW.from_state <> (
            SELECT lifecycle_state FROM records WHERE record_id = NEW.record_id
        )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'lifecycle transition does not match current memory state');
END;

CREATE TRIGGER memory_approval_transition_validates_record
BEFORE INSERT ON memory_record_approval_transitions
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS record
    JOIN memory_record_types AS type
      ON type.record_family = record.record_family
     AND type.record_type = record.record_type
    WHERE record.record_id = NEW.record_id
      AND type.status = 'active'
)
BEGIN
    SELECT RAISE(ABORT, 'approval transition requires a registered memory record');
END;

CREATE TRIGGER memory_approval_transition_validates_sequence
BEFORE INSERT ON memory_record_approval_transitions
WHEN (
    NEW.sequence_number = 0
    AND (
        NEW.from_status IS NOT NULL
        OR EXISTS (
            SELECT 1 FROM memory_record_approval_transitions
            WHERE record_id = NEW.record_id
        )
        OR NEW.to_status <> (
            SELECT approval_status FROM records WHERE record_id = NEW.record_id
        )
    )
)
OR (
    NEW.sequence_number > 0
    AND (
        NEW.sequence_number <> COALESCE((
            SELECT MAX(sequence_number) + 1
            FROM memory_record_approval_transitions
            WHERE record_id = NEW.record_id
        ), 0)
        OR NEW.from_status <> (
            SELECT approval_status FROM records WHERE record_id = NEW.record_id
        )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'approval transition does not match current memory status');
END;

CREATE TRIGGER memory_records_lifecycle_requires_transition
BEFORE UPDATE OF lifecycle_state ON records
WHEN NEW.lifecycle_state <> OLD.lifecycle_state
AND EXISTS (
    SELECT 1 FROM memory_record_types AS type
    WHERE type.record_family = OLD.record_family
      AND type.record_type = OLD.record_type
)
AND NOT EXISTS (
    SELECT 1
    FROM memory_record_lifecycle_transitions AS transition
    WHERE transition.record_id = OLD.record_id
      AND transition.sequence_number = (
          SELECT MAX(sequence_number)
          FROM memory_record_lifecycle_transitions
          WHERE record_id = OLD.record_id
      )
      AND transition.from_state = OLD.lifecycle_state
      AND transition.to_state = NEW.lifecycle_state
)
BEGIN
    SELECT RAISE(ABORT, 'memory lifecycle update requires an append-only transition');
END;

CREATE TRIGGER memory_records_approval_requires_transition
BEFORE UPDATE OF approval_status ON records
WHEN NEW.approval_status <> OLD.approval_status
AND EXISTS (
    SELECT 1 FROM memory_record_types AS type
    WHERE type.record_family = OLD.record_family
      AND type.record_type = OLD.record_type
)
AND NOT EXISTS (
    SELECT 1
    FROM memory_record_approval_transitions AS transition
    WHERE transition.record_id = OLD.record_id
      AND transition.sequence_number = (
          SELECT MAX(sequence_number)
          FROM memory_record_approval_transitions
          WHERE record_id = OLD.record_id
      )
      AND transition.from_status = OLD.approval_status
      AND transition.to_status = NEW.approval_status
)
BEGIN
    SELECT RAISE(ABORT, 'memory approval update requires an append-only transition');
END;

CREATE TRIGGER memory_records_activation_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN NEW.lifecycle_state = 'active'
AND OLD.lifecycle_state <> 'active'
AND EXISTS (
    SELECT 1 FROM memory_record_types AS type
    WHERE type.record_family = OLD.record_family
      AND type.record_type = OLD.record_type
)
AND (
    NEW.approval_status NOT IN ('approved', 'not_required')
    OR NEW.integrity_status NOT IN ('valid', 'not_applicable')
    OR NOT EXISTS (
        SELECT 1 FROM record_evidence_links
        WHERE record_id = OLD.record_id
    )
)
BEGIN
    SELECT RAISE(ABORT, 'active memory requires approval, integrity, and evidence');
END;


CREATE TRIGGER memory_records_active_approval_guard
BEFORE UPDATE OF approval_status ON records
WHEN OLD.lifecycle_state = 'active'
AND NEW.approval_status NOT IN ('approved', 'not_required')
AND EXISTS (
    SELECT 1 FROM memory_record_types AS type
    WHERE type.record_family = OLD.record_family
      AND type.record_type = OLD.record_type
)
BEGIN
    SELECT RAISE(ABORT, 'active memory approval cannot be withdrawn in place');
END;

CREATE TRIGGER memory_lifecycle_transitions_immutable
BEFORE UPDATE ON memory_record_lifecycle_transitions
BEGIN
    SELECT RAISE(ABORT, 'memory lifecycle transitions are immutable');
END;

CREATE TRIGGER memory_lifecycle_transitions_no_delete
BEFORE DELETE ON memory_record_lifecycle_transitions
BEGIN
    SELECT RAISE(ABORT, 'memory lifecycle transitions cannot be deleted');
END;

CREATE TRIGGER memory_approval_transitions_immutable
BEFORE UPDATE ON memory_record_approval_transitions
BEGIN
    SELECT RAISE(ABORT, 'memory approval transitions are immutable');
END;

CREATE TRIGGER memory_approval_transitions_no_delete
BEFORE DELETE ON memory_record_approval_transitions
BEGIN
    SELECT RAISE(ABORT, 'memory approval transitions cannot be deleted');
END;

CREATE TRIGGER record_relationships_immutable
BEFORE UPDATE ON record_relationships
BEGIN
    SELECT RAISE(ABORT, 'record relationships are immutable');
END;

CREATE TRIGGER record_relationships_no_delete
BEFORE DELETE ON record_relationships
BEGIN
    SELECT RAISE(ABORT, 'record relationships cannot be deleted');
END;

CREATE TRIGGER memory_eligibility_assessments_immutable
BEFORE UPDATE ON memory_eligibility_assessments
BEGIN
    SELECT RAISE(ABORT, 'memory eligibility assessments are immutable');
END;

CREATE TRIGGER memory_eligibility_assessments_no_delete
BEFORE DELETE ON memory_eligibility_assessments
BEGIN
    SELECT RAISE(ABORT, 'memory eligibility assessments cannot be deleted');
END;
