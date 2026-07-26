CREATE TABLE construct_relationship_type_policies (
    relationship_type TEXT PRIMARY KEY CHECK (trim(relationship_type) <> ''),
    authority_bearing INTEGER NOT NULL CHECK (authority_bearing IN (0, 1)),
    self_reference_permitted INTEGER NOT NULL CHECK (
        self_reference_permitted IN (0, 1)
    ),
    bidirectional_permitted INTEGER NOT NULL CHECK (
        bidirectional_permitted IN (0, 1)
    ),
    required_approval_authority_class TEXT NOT NULL CHECK (
        required_approval_authority_class IN (
            'nolan_approved', 'nolan_byte_approved'
        )
    ),
    status TEXT NOT NULL CHECK (status = 'active')
);

INSERT INTO construct_relationship_type_policies (
    relationship_type, authority_bearing, self_reference_permitted,
    bidirectional_permitted, required_approval_authority_class, status
) VALUES
    ('has_final_authority_over', 1, 0, 0, 'nolan_approved', 'active'),
    ('provides_architecture_review_for', 0, 0, 0, 'nolan_byte_approved', 'active'),
    ('participates_in', 0, 0, 0, 'nolan_byte_approved', 'active'),
    ('draws_curriculum_from', 0, 0, 0, 'nolan_byte_approved', 'active');

CREATE TRIGGER construct_relationship_type_policies_immutable
BEFORE UPDATE ON construct_relationship_type_policies
BEGIN
    SELECT RAISE(ABORT, 'Construct relationship policies are immutable');
END;

CREATE TRIGGER construct_relationship_type_policies_no_delete
BEFORE DELETE ON construct_relationship_type_policies
BEGIN
    SELECT RAISE(ABORT, 'Construct relationship policies cannot be deleted');
END;

CREATE TRIGGER construct_relationship_type_policies_no_insert
BEFORE INSERT ON construct_relationship_type_policies
BEGIN
    SELECT RAISE(ABORT, 'Construct relationship policies require an authorised migration');
END;

CREATE TABLE construct_entities (
    record_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    memory_description TEXT NOT NULL CHECK (trim(memory_description) <> ''),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id) ON DELETE RESTRICT
);

CREATE TABLE construct_relationships (
    record_id TEXT PRIMARY KEY,
    subject_entity_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    object_entity_id TEXT NOT NULL,
    description TEXT NOT NULL CHECK (trim(description) <> ''),
    bidirectional INTEGER NOT NULL CHECK (bidirectional IN (0, 1)),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (subject_entity_id) REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (relationship_type)
        REFERENCES construct_relationship_type_policies(relationship_type)
        ON DELETE RESTRICT,
    FOREIGN KEY (object_entity_id) REFERENCES entities(entity_id) ON DELETE RESTRICT
);

CREATE TABLE architecture_decisions (
    record_id TEXT PRIMARY KEY,
    decision_statement TEXT NOT NULL CHECK (trim(decision_statement) <> ''),
    decision_scope TEXT NOT NULL,
    rationale TEXT NOT NULL CHECK (trim(rationale) <> ''),
    alternatives_json TEXT NOT NULL CHECK (
        json_valid(alternatives_json)
        AND json_type(alternatives_json) = 'array'
    ),
    consequences_json TEXT NOT NULL CHECK (
        json_valid(consequences_json)
        AND json_type(consequences_json) = 'array'
    ),
    decision_status TEXT NOT NULL CHECK (
        decision_status IN ('accepted', 'superseded', 'revoked')
    ),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (decision_scope) REFERENCES scopes(scope_id) ON DELETE RESTRICT
);

CREATE TABLE project_states (
    record_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    state_type TEXT NOT NULL CHECK (
        state_type IN (
            'phase', 'milestone', 'validation_baseline', 'active_issue', 'priority'
        )
    ),
    state_value_json TEXT NOT NULL CHECK (
        json_valid(state_value_json)
        AND json_type(state_value_json) IN ('array', 'object')
    ),
    observed_at TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_id) REFERENCES entities(entity_id) ON DELETE RESTRICT
);

CREATE TABLE construct_doctrines (
    record_id TEXT PRIMARY KEY,
    doctrine_statement TEXT NOT NULL CHECK (trim(doctrine_statement) <> ''),
    application_scopes_json TEXT NOT NULL CHECK (
        json_valid(application_scopes_json)
        AND json_type(application_scopes_json) = 'array'
    ),
    interpretation_notes TEXT NOT NULL CHECK (trim(interpretation_notes) <> ''),
    exceptions_json TEXT NOT NULL CHECK (
        exceptions_json = '[]'
        AND json_valid(exceptions_json)
        AND json_type(exceptions_json) = 'array'
    ),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT
);

CREATE TABLE terminology_definitions (
    record_id TEXT PRIMARY KEY,
    term TEXT NOT NULL CHECK (trim(term) <> ''),
    definition TEXT NOT NULL CHECK (trim(definition) <> ''),
    definition_scope_id TEXT NOT NULL,
    deprecated_aliases_json TEXT NOT NULL CHECK (
        json_valid(deprecated_aliases_json)
        AND json_type(deprecated_aliases_json) = 'array'
    ),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (definition_scope_id) REFERENCES scopes(scope_id) ON DELETE RESTRICT
);

CREATE INDEX terminology_definitions_scope_term
ON terminology_definitions(definition_scope_id, term COLLATE NOCASE);

CREATE TABLE preference_records (
    record_id TEXT PRIMARY KEY,
    preference_subject_id TEXT NOT NULL,
    preference_category TEXT NOT NULL CHECK (trim(preference_category) <> ''),
    preference_statement TEXT NOT NULL CHECK (trim(preference_statement) <> ''),
    context_constraints_json TEXT NOT NULL CHECK (
        json_valid(context_constraints_json)
        AND json_type(context_constraints_json) = 'array'
    ),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (preference_subject_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT
);

CREATE TRIGGER construct_entities_contract_guard
BEFORE INSERT ON construct_entities
WHEN NOT EXISTS (
    SELECT 1 FROM records
    WHERE record_id = NEW.record_id
      AND record_family = 'construct_memory'
      AND record_type = 'construct_entity'
      AND subject_entity_id = NEW.entity_id
)
BEGIN
    SELECT RAISE(ABORT, 'Construct entity payload does not match its envelope');
END;

CREATE TRIGGER construct_relationships_contract_guard
BEFORE INSERT ON construct_relationships
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS record
    JOIN construct_relationship_type_policies AS policy
      ON policy.relationship_type = NEW.relationship_type
     AND policy.status = 'active'
    WHERE record.record_id = NEW.record_id
      AND record.record_family = 'construct_memory'
      AND record.record_type = 'construct_relationship'
      AND record.subject_entity_id = NEW.subject_entity_id
      AND (
          policy.self_reference_permitted = 1
          OR NEW.subject_entity_id <> NEW.object_entity_id
      )
      AND (
          policy.bidirectional_permitted = 1
          OR NEW.bidirectional = 0
      )
)
BEGIN
    SELECT RAISE(ABORT, 'Construct relationship violates its envelope or type policy');
END;

CREATE TRIGGER architecture_decisions_contract_guard
BEFORE INSERT ON architecture_decisions
WHEN NOT EXISTS (
    SELECT 1 FROM records
    WHERE record_id = NEW.record_id
      AND record_family = 'construct_memory'
      AND record_type = 'architecture_decision'
)
BEGIN
    SELECT RAISE(ABORT, 'Architecture decision payload does not match its envelope');
END;

CREATE TRIGGER project_states_contract_guard
BEFORE INSERT ON project_states
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS record
    JOIN entities AS project ON project.entity_id = NEW.project_id
    WHERE record.record_id = NEW.record_id
      AND record.record_family = 'construct_memory'
      AND record.record_type = 'project_state'
      AND record.subject_entity_id = NEW.project_id
      AND project.entity_kind = 'project'
)
BEGIN
    SELECT RAISE(ABORT, 'Project-state payload does not match a project envelope');
END;

CREATE TRIGGER construct_doctrines_contract_guard
BEFORE INSERT ON construct_doctrines
WHEN NOT EXISTS (
    SELECT 1 FROM records
    WHERE record_id = NEW.record_id
      AND record_family = 'construct_memory'
      AND record_type = 'construct_doctrine'
)
BEGIN
    SELECT RAISE(ABORT, 'Construct-doctrine payload does not match its envelope');
END;

CREATE TRIGGER terminology_definitions_contract_guard
BEFORE INSERT ON terminology_definitions
WHEN NOT EXISTS (
    SELECT 1 FROM records
    WHERE record_id = NEW.record_id
      AND record_family = 'construct_memory'
      AND record_type = 'terminology_definition'
)
BEGIN
    SELECT RAISE(ABORT, 'Terminology payload does not match its envelope');
END;

CREATE TRIGGER preference_records_contract_guard
BEFORE INSERT ON preference_records
WHEN NOT EXISTS (
    SELECT 1 FROM records
    WHERE record_id = NEW.record_id
      AND record_family = 'construct_memory'
      AND record_type = 'preference_record'
      AND subject_entity_id = NEW.preference_subject_id
)
BEGIN
    SELECT RAISE(ABORT, 'Preference payload does not match its envelope');
END;

CREATE TRIGGER project_state_active_uniqueness_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN NEW.record_family = 'construct_memory'
 AND NEW.record_type = 'project_state'
 AND NEW.lifecycle_state = 'active'
 AND EXISTS (
    SELECT 1
    FROM project_states AS candidate
    JOIN project_states AS existing
      ON existing.project_id = candidate.project_id
     AND existing.state_type = candidate.state_type
     AND existing.record_id <> candidate.record_id
    JOIN records AS existing_record
      ON existing_record.record_id = existing.record_id
     AND existing_record.lifecycle_state = 'active'
    WHERE candidate.record_id = NEW.record_id
 )
BEGIN
    SELECT RAISE(
        ABORT,
        'Existing active project state must be superseded before replacement activation'
    );
END;

CREATE TRIGGER project_state_supersession_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN OLD.record_family = 'construct_memory'
 AND OLD.record_type = 'project_state'
 AND OLD.lifecycle_state = 'active'
 AND NEW.lifecycle_state = 'superseded'
 AND EXISTS (SELECT 1 FROM project_states WHERE record_id = OLD.record_id)
 AND NOT EXISTS (
    SELECT 1
    FROM record_relationships AS relationship
    JOIN records AS replacement
      ON replacement.record_id = relationship.source_record_id
     AND replacement.record_family = OLD.record_family
     AND replacement.record_type = OLD.record_type
     AND replacement.project_scope_id = OLD.project_scope_id
     AND replacement.lifecycle_state = 'approved'
     AND replacement.approval_status = 'approved'
     AND replacement.integrity_status = 'valid'
     AND (
         replacement.supersedes_record_id IS NULL
         OR replacement.supersedes_record_id = OLD.record_id
     )
    JOIN project_states AS replacement_state
      ON replacement_state.record_id = replacement.record_id
    JOIN project_states AS current_state
      ON current_state.record_id = OLD.record_id
     AND replacement_state.project_id = current_state.project_id
     AND replacement_state.state_type = current_state.state_type
    WHERE relationship.target_record_id = OLD.record_id
      AND relationship.relationship_type = 'supersedes'
 )
BEGIN
    SELECT RAISE(
        ABORT,
        'Project state requires an approved governed replacement before supersession'
    );
END;

CREATE TRIGGER terminology_definition_active_uniqueness_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN NEW.record_family = 'construct_memory'
 AND NEW.record_type = 'terminology_definition'
 AND NEW.lifecycle_state = 'active'
 AND EXISTS (
    SELECT 1
    FROM terminology_definitions AS candidate
    JOIN terminology_definitions AS existing
      ON existing.definition_scope_id = candidate.definition_scope_id
     AND lower(existing.term) = lower(candidate.term)
     AND existing.record_id <> candidate.record_id
    JOIN records AS existing_record
      ON existing_record.record_id = existing.record_id
     AND existing_record.lifecycle_state = 'active'
    WHERE candidate.record_id = NEW.record_id
 )
BEGIN
    SELECT RAISE(
        ABORT,
        'Existing active term must be superseded before replacement activation'
    );
END;

CREATE TRIGGER terminology_definition_supersession_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN OLD.record_family = 'construct_memory'
 AND OLD.record_type = 'terminology_definition'
 AND OLD.lifecycle_state = 'active'
 AND NEW.lifecycle_state = 'superseded'
 AND EXISTS (SELECT 1 FROM terminology_definitions WHERE record_id = OLD.record_id)
 AND NOT EXISTS (
    SELECT 1
    FROM record_relationships AS relationship
    JOIN records AS replacement
      ON replacement.record_id = relationship.source_record_id
     AND replacement.record_family = OLD.record_family
     AND replacement.record_type = OLD.record_type
     AND replacement.project_scope_id = OLD.project_scope_id
     AND replacement.lifecycle_state = 'approved'
     AND replacement.approval_status = 'approved'
     AND replacement.integrity_status = 'valid'
     AND (
         replacement.supersedes_record_id IS NULL
         OR replacement.supersedes_record_id = OLD.record_id
     )
    JOIN terminology_definitions AS replacement_term
      ON replacement_term.record_id = replacement.record_id
    JOIN terminology_definitions AS current_term
      ON current_term.record_id = OLD.record_id
     AND replacement_term.definition_scope_id = current_term.definition_scope_id
    WHERE relationship.target_record_id = OLD.record_id
      AND relationship.relationship_type = 'supersedes'
 )
BEGIN
    SELECT RAISE(
        ABORT,
        'Terminology definition requires an approved governed replacement before supersession'
    );
END;

CREATE TRIGGER construct_memory_records_no_delete
BEFORE DELETE ON records
WHEN OLD.record_family = 'construct_memory'
 AND OLD.record_type IN (
    'construct_entity', 'construct_relationship', 'architecture_decision',
    'project_state', 'construct_doctrine', 'terminology_definition',
    'preference_record'
 )
BEGIN
    SELECT RAISE(ABORT, 'Construct memory envelopes cannot be deleted');
END;

CREATE TRIGGER construct_entities_immutable
BEFORE UPDATE ON construct_entities
BEGIN
    SELECT RAISE(ABORT, 'Construct entity payloads are immutable');
END;
CREATE TRIGGER construct_entities_no_delete
BEFORE DELETE ON construct_entities
BEGIN
    SELECT RAISE(ABORT, 'Construct entity payloads cannot be deleted');
END;

CREATE TRIGGER construct_relationships_immutable
BEFORE UPDATE ON construct_relationships
BEGIN
    SELECT RAISE(ABORT, 'Construct relationship payloads are immutable');
END;
CREATE TRIGGER construct_relationships_no_delete
BEFORE DELETE ON construct_relationships
BEGIN
    SELECT RAISE(ABORT, 'Construct relationship payloads cannot be deleted');
END;

CREATE TRIGGER architecture_decisions_immutable
BEFORE UPDATE ON architecture_decisions
BEGIN
    SELECT RAISE(ABORT, 'Architecture decision payloads are immutable');
END;
CREATE TRIGGER architecture_decisions_no_delete
BEFORE DELETE ON architecture_decisions
BEGIN
    SELECT RAISE(ABORT, 'Architecture decision payloads cannot be deleted');
END;

CREATE TRIGGER project_states_immutable
BEFORE UPDATE ON project_states
BEGIN
    SELECT RAISE(ABORT, 'Project-state payloads are immutable');
END;
CREATE TRIGGER project_states_no_delete
BEFORE DELETE ON project_states
BEGIN
    SELECT RAISE(ABORT, 'Project-state payloads cannot be deleted');
END;

CREATE TRIGGER construct_doctrines_immutable
BEFORE UPDATE ON construct_doctrines
BEGIN
    SELECT RAISE(ABORT, 'Construct-doctrine payloads are immutable');
END;
CREATE TRIGGER construct_doctrines_no_delete
BEFORE DELETE ON construct_doctrines
BEGIN
    SELECT RAISE(ABORT, 'Construct-doctrine payloads cannot be deleted');
END;

CREATE TRIGGER terminology_definitions_immutable
BEFORE UPDATE ON terminology_definitions
BEGIN
    SELECT RAISE(ABORT, 'Terminology payloads are immutable');
END;
CREATE TRIGGER terminology_definitions_no_delete
BEFORE DELETE ON terminology_definitions
BEGIN
    SELECT RAISE(ABORT, 'Terminology payloads cannot be deleted');
END;

CREATE TRIGGER preference_records_immutable
BEFORE UPDATE ON preference_records
BEGIN
    SELECT RAISE(ABORT, 'Preference payloads are immutable');
END;
CREATE TRIGGER preference_records_no_delete
BEFORE DELETE ON preference_records
BEGIN
    SELECT RAISE(ABORT, 'Preference payloads cannot be deleted');
END;

DROP TRIGGER memory_approval_grant_registration_guard;

CREATE TRIGGER memory_approval_grant_registration_guard
BEFORE INSERT ON memory_approval_grants
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS record
    JOIN memory_record_types AS type
      ON type.record_family = record.record_family
     AND type.record_type = record.record_type
    JOIN authority_records AS authority
      ON authority.authority_record_id = NEW.authority_record_id
     AND authority.authority_class = NEW.authority_class
    JOIN authority_record_evidence AS authority_evidence
      ON authority_evidence.authority_record_id = authority.authority_record_id
     AND authority_evidence.evidence_id = NEW.evidence_id
    JOIN evidence_items AS evidence
      ON evidence.evidence_id = NEW.evidence_id
    WHERE record.record_id = NEW.record_id
      AND record.project_scope_id = NEW.project_scope_id
      AND type.approval_requirement = 'external'
      AND (
          (
              record.record_family = 'construct_memory'
              AND record.record_type = 'construct_relationship'
              AND EXISTS (
                  SELECT 1
                  FROM construct_relationships AS relationship
                  JOIN construct_relationship_type_policies AS policy
                    ON policy.relationship_type = relationship.relationship_type
                   AND policy.status = 'active'
                  WHERE relationship.record_id = record.record_id
                    AND policy.required_approval_authority_class =
                        authority.authority_class
              )
          )
          OR
          (
              NOT (
                  record.record_family = 'construct_memory'
                  AND record.record_type = 'construct_relationship'
              )
              AND EXISTS (
                  SELECT 1
                  FROM memory_record_approval_authorities AS permitted
                  WHERE permitted.record_family = record.record_family
                    AND permitted.record_type = record.record_type
                    AND permitted.authority_class = authority.authority_class
              )
          )
      )
      AND authority.status = 'active'
      AND authority.effect = 'allow'
      AND authority.project_scope_id = NEW.project_scope_id
      AND (
          authority.issuer_entity_id IS NULL
          OR authority.issuer_entity_id = NEW.approved_by_entity_id
      )
      AND authority.effective_from <= NEW.approved_at
      AND (
          authority.effective_until IS NULL
          OR authority.effective_until >= NEW.approved_at
      )
      AND evidence.integrity_status = 'valid'
      AND evidence.evidence_kind NOT IN (
          'model_output', 'controlled_prompt', 'controlled_output'
      )
      AND NOT EXISTS (
          SELECT 1 FROM authority_revocations AS revocation
          WHERE revocation.authority_record_id = authority.authority_record_id
      )
      AND NOT (
          record.record_family = 'episodic_memory'
          AND record.record_type = 'lesson_candidate'
          AND NEW.target_status = 'approved'
      )
)
BEGIN
    SELECT RAISE(ABORT, 'memory approval grant violates type-specific authority');
END;
