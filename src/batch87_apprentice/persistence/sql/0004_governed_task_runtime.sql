CREATE TABLE permission_profiles (
    permission_profile_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    principal TEXT NOT NULL CHECK (principal = 'apprentice'),
    allowed_action_classes_json TEXT NOT NULL CHECK (
        json_valid(allowed_action_classes_json)
        AND json_type(allowed_action_classes_json) = 'array'
        AND allowed_action_classes_json = '["observe","analyse"]'
    ),
    prohibited_action_classes_json TEXT NOT NULL CHECK (
        json_valid(prohibited_action_classes_json)
        AND json_type(prohibited_action_classes_json) = 'array'
        AND prohibited_action_classes_json =
            '["propose","execute","autonomous_action"]'
    ),
    allowed_tools_json TEXT NOT NULL CHECK (allowed_tools_json = '[]'),
    prohibited_tools_json TEXT NOT NULL CHECK (
        json_valid(prohibited_tools_json)
        AND json_type(prohibited_tools_json) = 'array'
    ),
    effective_from TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json)
        AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    status TEXT NOT NULL CHECK (status = 'active'),
    UNIQUE (principal, version)
);

CREATE TRIGGER permission_profiles_immutable
BEFORE UPDATE ON permission_profiles
BEGIN
    SELECT RAISE(ABORT, 'permission profiles are immutable');
END;

CREATE TRIGGER permission_profiles_no_delete
BEFORE DELETE ON permission_profiles
BEGIN
    SELECT RAISE(ABORT, 'permission profiles cannot be deleted');
END;

CREATE TABLE governance_rules (
    governance_rule_id TEXT PRIMARY KEY,
    rule_name TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    rule_kind TEXT NOT NULL,
    description TEXT NOT NULL,
    configuration_json TEXT NOT NULL CHECK (
        json_valid(configuration_json)
        AND json_type(configuration_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    status TEXT NOT NULL CHECK (status = 'active'),
    UNIQUE (rule_name, rule_version)
);

CREATE TRIGGER governance_rules_immutable
BEFORE UPDATE ON governance_rules
BEGIN
    SELECT RAISE(ABORT, 'governance rules are immutable');
END;

CREATE TRIGGER governance_rules_no_delete
BEFORE DELETE ON governance_rules
BEGIN
    SELECT RAISE(ABORT, 'governance rules cannot be deleted');
END;


CREATE TABLE operation_definitions (
    operation_name TEXT PRIMARY KEY CHECK (trim(operation_name) <> ''),
    schema_version TEXT NOT NULL,
    action_class TEXT NOT NULL CHECK (
        action_class IN ('observe', 'analyse', 'propose', 'execute')
    ),
    autonomous INTEGER NOT NULL CHECK (autonomous IN (0, 1)),
    registered_by_principal TEXT NOT NULL CHECK (
        registered_by_principal IN ('operator', 'codex_development_harness')
    ),
    registered_at TEXT NOT NULL,
    description TEXT NOT NULL CHECK (trim(description) <> ''),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    CHECK (autonomous = 0 OR action_class = 'execute')
);

CREATE TRIGGER operation_definitions_immutable
BEFORE UPDATE ON operation_definitions
BEGIN
    SELECT RAISE(ABORT, 'operation definitions are immutable');
END;

CREATE TRIGGER operation_definitions_no_delete
BEFORE DELETE ON operation_definitions
BEGIN
    SELECT RAISE(ABORT, 'operation definitions cannot be deleted');
END;

CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    contract_version TEXT NOT NULL,
    session_purpose TEXT NOT NULL CHECK (trim(session_purpose) <> ''),
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    active_project_scope TEXT NOT NULL,
    session_status TEXT NOT NULL CHECK (
        session_status IN ('open', 'paused', 'closed', 'aborted')
    ),
    retention_disposition TEXT NOT NULL CHECK (
        retention_disposition IN (
            'delete', 'archive_summary', 'retain_restricted'
        )
    ),
    created_by_entity_id TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json)
        AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (active_project_scope)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    CHECK (
        (session_status IN ('open', 'paused') AND closed_at IS NULL)
        OR
        (session_status IN ('closed', 'aborted') AND closed_at IS NOT NULL)
    ),
    CHECK (closed_at IS NULL OR closed_at >= opened_at)
);

CREATE TABLE session_participants (
    session_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('operator', 'participant')),
    PRIMARY KEY (session_id, entity_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id) ON DELETE RESTRICT
);

CREATE TABLE session_state_transitions (
    transition_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    from_status TEXT,
    to_status TEXT NOT NULL CHECK (
        to_status IN ('open', 'paused', 'closed', 'aborted')
    ),
    reason_code TEXT NOT NULL CHECK (trim(reason_code) <> ''),
    changed_at TEXT NOT NULL,
    changed_by_principal TEXT NOT NULL CHECK (
        changed_by_principal IN ('operator', 'codex_development_harness')
    ),
    UNIQUE (session_id, sequence_number),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    CHECK (
        (sequence_number = 0 AND from_status IS NULL AND to_status = 'open')
        OR
        (sequence_number > 0 AND (
            (from_status = 'open' AND to_status IN ('paused', 'closed', 'aborted'))
            OR
            (from_status = 'paused' AND to_status IN ('open', 'closed', 'aborted'))
        ))
    )
);

CREATE TRIGGER sessions_core_immutable
BEFORE UPDATE OF session_id, contract_version, session_purpose, opened_at,
                 active_project_scope, retention_disposition,
                 created_by_entity_id
ON sessions
BEGIN
    SELECT RAISE(ABORT, 'session identity is immutable');
END;

CREATE TRIGGER sessions_status_requires_transition
BEFORE UPDATE OF session_status, closed_at, canonical_json, content_hash
ON sessions
WHEN NEW.session_status <> OLD.session_status
AND NOT EXISTS (
    SELECT 1
    FROM session_state_transitions AS transition
    WHERE transition.session_id = OLD.session_id
      AND transition.sequence_number = (
          SELECT MAX(sequence_number)
          FROM session_state_transitions
          WHERE session_id = OLD.session_id
      )
      AND transition.from_status = OLD.session_status
      AND transition.to_status = NEW.session_status
)
BEGIN
    SELECT RAISE(ABORT, 'session status change requires a recorded transition');
END;

CREATE TRIGGER session_state_transitions_validate_current_state
BEFORE INSERT ON session_state_transitions
WHEN (
    NEW.sequence_number = 0
    AND (
        (SELECT session_status FROM sessions WHERE session_id = NEW.session_id) <> 'open'
        OR EXISTS (
            SELECT 1 FROM session_state_transitions
            WHERE session_id = NEW.session_id
        )
    )
)
OR (
    NEW.sequence_number > 0
    AND (
        (SELECT session_status FROM sessions WHERE session_id = NEW.session_id)
            <> NEW.from_status
        OR NEW.sequence_number <> COALESCE((
            SELECT MAX(sequence_number) + 1
            FROM session_state_transitions
            WHERE session_id = NEW.session_id
        ), 0)
    )
)
BEGIN
    SELECT RAISE(ABORT, 'session transition does not match current state');
END;

CREATE TRIGGER session_state_transitions_immutable
BEFORE UPDATE ON session_state_transitions
BEGIN
    SELECT RAISE(ABORT, 'session transitions are immutable');
END;

CREATE TRIGGER session_state_transitions_no_delete
BEFORE DELETE ON session_state_transitions
BEGIN
    SELECT RAISE(ABORT, 'session transitions cannot be deleted');
END;

CREATE TRIGGER sessions_no_delete
BEFORE DELETE ON sessions
BEGIN
    SELECT RAISE(ABORT, 'sessions cannot be deleted');
END;

CREATE TRIGGER session_participants_immutable
BEFORE UPDATE ON session_participants
BEGIN
    SELECT RAISE(ABORT, 'session participation is immutable');
END;

CREATE TRIGGER session_participants_no_delete
BEFORE DELETE ON session_participants
BEGIN
    SELECT RAISE(ABORT, 'session participants cannot be deleted');
END;

CREATE TABLE authority_records (
    authority_record_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    authority_class TEXT NOT NULL CHECK (
        authority_class IN (
            'law_or_external_obligation', 'nolan_approved',
            'nolan_byte_approved', 'validated_system_evidence',
            'approved_project_policy', 'approved_memory',
            'approved_evaluation', 'agent_proposal', 'model_inference',
            'external_untrusted', 'unknown'
        )
    ),
    source_kind TEXT NOT NULL CHECK (
        source_kind IN (
            'law_or_external_obligation_record', 'nolan_approval_record',
            'nolan_byte_approval_record', 'validated_system_record',
            'approved_project_policy_record', 'approved_memory_record',
            'approved_evaluation_record', 'agent_proposal', 'model_output',
            'external_content', 'unknown'
        )
    ),
    effect TEXT NOT NULL CHECK (
        effect IN ('allow', 'deny', 'require_human_approval')
    ),
    subject_principal TEXT NOT NULL CHECK (
        subject_principal IN (
            'apprentice', 'operator', 'codex_development_harness',
            'experimental_harness'
        )
    ),
    permissions_json TEXT NOT NULL CHECK (
        json_valid(permissions_json)
        AND json_type(permissions_json) = 'array'
    ),
    project_scope_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    issuer_entity_id TEXT,
    task_id TEXT,
    effective_from TEXT NOT NULL,
    effective_until TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('active', 'historical', 'revoked')
    ),
    registered_by_principal TEXT NOT NULL CHECK (
        registered_by_principal IN ('operator', 'codex_development_harness')
    ),
    registered_at TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL CHECK (
        json_valid(evidence_ids_json)
        AND json_type(evidence_ids_json) = 'array'
    ),
    provenance_json TEXT NOT NULL CHECK (
        json_valid(provenance_json)
        AND json_type(provenance_json) = 'object'
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json)
        AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (scope_id) REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (issuer_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    CHECK (effective_until IS NULL OR effective_until >= effective_from),
    CHECK (
        authority_class NOT IN ('nolan_approved', 'nolan_byte_approved')
        OR issuer_entity_id IS NOT NULL
    ),
    CHECK (
        subject_principal <> 'apprentice'
        OR (
            permissions_json NOT LIKE '%"propose"%'
            AND permissions_json NOT LIKE '%"execute"%'
        )
    )
);

CREATE TABLE authority_record_evidence (
    authority_record_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    evidence_order INTEGER NOT NULL CHECK (evidence_order >= 0),
    PRIMARY KEY (authority_record_id, evidence_id),
    UNIQUE (authority_record_id, evidence_order),
    FOREIGN KEY (authority_record_id)
        REFERENCES authority_records(authority_record_id) ON DELETE RESTRICT,
    FOREIGN KEY (evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT
);

CREATE INDEX authority_records_scope_time
ON authority_records(project_scope_id, scope_id, effective_from, effective_until);

CREATE TRIGGER authority_record_evidence_validate
BEFORE INSERT ON authority_record_evidence
WHEN NOT EXISTS (
    SELECT 1
    FROM evidence_items
    WHERE evidence_id = NEW.evidence_id
      AND integrity_status = 'valid'
      AND evidence_kind NOT IN (
          'model_output', 'controlled_prompt', 'controlled_output'
      )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'authority evidence must be valid, non-model, and non-controlled'
    );
END;

CREATE TRIGGER authority_records_immutable
BEFORE UPDATE ON authority_records
BEGIN
    SELECT RAISE(ABORT, 'authority records are immutable');
END;

CREATE TRIGGER authority_records_no_delete
BEFORE DELETE ON authority_records
BEGIN
    SELECT RAISE(ABORT, 'authority records cannot be deleted');
END;

CREATE TRIGGER authority_record_evidence_immutable
BEFORE UPDATE ON authority_record_evidence
BEGIN
    SELECT RAISE(ABORT, 'authority evidence relationships are immutable');
END;

CREATE TRIGGER authority_record_evidence_no_delete
BEFORE DELETE ON authority_record_evidence
BEGIN
    SELECT RAISE(ABORT, 'authority evidence relationships cannot be deleted');
END;

CREATE TABLE authority_revocations (
    authority_record_id TEXT PRIMARY KEY,
    revoked_at TEXT NOT NULL,
    revoked_by_entity_id TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (trim(reason) <> ''),
    registered_by_principal TEXT NOT NULL CHECK (
        registered_by_principal IN ('operator', 'codex_development_harness')
    ),
    provenance_json TEXT NOT NULL CHECK (
        json_valid(provenance_json) AND json_type(provenance_json) = 'object'
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (authority_record_id)
        REFERENCES authority_records(authority_record_id) ON DELETE RESTRICT,
    FOREIGN KEY (revoked_by_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT
);

CREATE TRIGGER authority_revocations_immutable
BEFORE UPDATE ON authority_revocations
BEGIN
    SELECT RAISE(ABORT, 'authority revocations are immutable');
END;

CREATE TRIGGER authority_revocations_no_delete
BEFORE DELETE ON authority_revocations
BEGIN
    SELECT RAISE(ABORT, 'authority revocations cannot be deleted');
END;

CREATE TABLE human_approvals (
    human_approval_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    requested_operation TEXT NOT NULL,
    subject_principal TEXT NOT NULL CHECK (
        subject_principal IN (
            'apprentice', 'operator', 'codex_development_harness',
            'experimental_harness'
        )
    ),
    permissions_json TEXT NOT NULL CHECK (
        json_valid(permissions_json) AND json_type(permissions_json) = 'array'
    ),
    project_scope_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    task_id TEXT,
    approved_by_entity_id TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    expires_at TEXT,
    conditions_json TEXT NOT NULL CHECK (
        json_valid(conditions_json) AND json_type(conditions_json) = 'array'
    ),
    single_use INTEGER NOT NULL CHECK (single_use IN (0, 1)),
    consumed_at TEXT,
    consumed_by_task_id TEXT,
    consumed_by_decision_id TEXT,
    evidence_ids_json TEXT NOT NULL CHECK (
        json_valid(evidence_ids_json) AND json_type(evidence_ids_json) = 'array'
    ),
    provenance_json TEXT NOT NULL CHECK (
        json_valid(provenance_json) AND json_type(provenance_json) = 'object'
    ),
    registered_by_principal TEXT NOT NULL CHECK (
        registered_by_principal IN ('operator', 'codex_development_harness')
    ),
    registered_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (scope_id) REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (approved_by_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    CHECK (expires_at IS NULL OR expires_at >= approved_at),
    CHECK (
        (single_use = 0 AND consumed_at IS NULL
            AND consumed_by_task_id IS NULL AND consumed_by_decision_id IS NULL)
        OR
        (single_use = 1 AND (
            (consumed_at IS NULL AND consumed_by_task_id IS NULL
                AND consumed_by_decision_id IS NULL)
            OR
            (consumed_at IS NOT NULL AND consumed_by_task_id IS NOT NULL
                AND consumed_by_decision_id IS NOT NULL)
        ))
    ),
    CHECK (
        subject_principal <> 'apprentice'
        OR (
            permissions_json NOT LIKE '%"propose"%'
            AND permissions_json NOT LIKE '%"execute"%'
        )
    )
);

CREATE TABLE human_approval_evidence (
    human_approval_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    evidence_order INTEGER NOT NULL CHECK (evidence_order >= 0),
    PRIMARY KEY (human_approval_id, evidence_id),
    UNIQUE (human_approval_id, evidence_order),
    FOREIGN KEY (human_approval_id)
        REFERENCES human_approvals(human_approval_id) ON DELETE RESTRICT,
    FOREIGN KEY (evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT
);

CREATE TRIGGER human_approval_evidence_validate
BEFORE INSERT ON human_approval_evidence
WHEN NOT EXISTS (
    SELECT 1 FROM evidence_items
    WHERE evidence_id = NEW.evidence_id
      AND integrity_status = 'valid'
      AND evidence_kind NOT IN (
          'model_output', 'controlled_prompt', 'controlled_output'
      )
)
BEGIN
    SELECT RAISE(ABORT, 'human approval evidence must be valid and non-model');
END;

CREATE TRIGGER human_approvals_core_immutable
BEFORE UPDATE OF human_approval_id, schema_version, requested_operation,
                 subject_principal, permissions_json, project_scope_id,
                 scope_id, task_id, approved_by_entity_id, approved_at,
                 expires_at, conditions_json, single_use, evidence_ids_json,
                 provenance_json, registered_by_principal, registered_at,
                 canonical_json, content_hash
ON human_approvals
BEGIN
    SELECT RAISE(ABORT, 'human approval identity is immutable');
END;

CREATE TRIGGER human_approvals_no_delete
BEFORE DELETE ON human_approvals
BEGIN
    SELECT RAISE(ABORT, 'human approvals cannot be deleted');
END;

CREATE TRIGGER human_approval_evidence_immutable
BEFORE UPDATE ON human_approval_evidence
BEGIN
    SELECT RAISE(ABORT, 'human approval evidence is immutable');
END;

CREATE TRIGGER human_approval_evidence_no_delete
BEFORE DELETE ON human_approval_evidence
BEGIN
    SELECT RAISE(ABORT, 'human approval evidence cannot be deleted');
END;

CREATE TABLE governed_runtime_transactions (
    transaction_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    runtime_instance_id TEXT NOT NULL,
    execution_principal TEXT NOT NULL CHECK (
        execution_principal IN ('operator', 'codex_development_harness')
    ),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('in_progress', 'committed', 'stopped')
    ),
    structured_failure_json TEXT NOT NULL CHECK (
        json_valid(structured_failure_json)
        AND json_type(structured_failure_json) = 'array'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
        ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (runtime_instance_id)
        REFERENCES runtime_instances(runtime_instance_id) ON DELETE RESTRICT,
    CHECK (
        (status = 'in_progress' AND completed_at IS NULL)
        OR
        (status IN ('committed', 'stopped') AND completed_at IS NOT NULL)
    )
);

CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    objective TEXT NOT NULL CHECK (trim(objective) <> ''),
    task_type TEXT NOT NULL CHECK (trim(task_type) <> ''),
    project_scope_id TEXT NOT NULL,
    requested_scope_id TEXT NOT NULL,
    requested_operation TEXT NOT NULL CHECK (trim(requested_operation) <> ''),
    requested_action_class TEXT NOT NULL CHECK (
        requested_action_class IN (
            'observe', 'analyse', 'propose', 'execute', 'ambiguous'
        )
    ),
    operation_autonomous INTEGER NOT NULL CHECK (
        operation_autonomous IN (0, 1)
    ),
    requesting_principal TEXT NOT NULL CHECK (
        requesting_principal IN (
            'apprentice', 'operator', 'codex_development_harness',
            'experimental_harness'
        )
    ),
    authority_grant_json TEXT NOT NULL CHECK (
        json_valid(authority_grant_json)
        AND json_type(authority_grant_json) = 'array'
    ),
    claimed_authority_ids_json TEXT NOT NULL CHECK (
        json_valid(claimed_authority_ids_json)
        AND json_type(claimed_authority_ids_json) = 'array'
    ),
    claimed_human_approval_ids_json TEXT NOT NULL CHECK (
        json_valid(claimed_human_approval_ids_json)
        AND json_type(claimed_human_approval_ids_json) = 'array'
    ),
    allowed_sources_json TEXT NOT NULL CHECK (
        json_valid(allowed_sources_json)
        AND json_type(allowed_sources_json) = 'array'
    ),
    prohibited_actions_json TEXT NOT NULL CHECK (
        json_valid(prohibited_actions_json)
        AND json_type(prohibited_actions_json) = 'array'
    ),
    expected_output_schema_id TEXT NOT NULL CHECK (
        trim(expected_output_schema_id) <> ''
    ),
    stop_conditions_json TEXT NOT NULL CHECK (
        json_valid(stop_conditions_json)
        AND json_type(stop_conditions_json) = 'array'
    ),
    governing_constraints_json TEXT NOT NULL CHECK (
        json_valid(governing_constraints_json)
        AND json_type(governing_constraints_json) = 'array'
    ),
    required_evidence_ids_json TEXT NOT NULL CHECK (
        json_valid(required_evidence_ids_json)
        AND json_type(required_evidence_ids_json) = 'array'
    ),
    effective_at TEXT NOT NULL,
    provenance_json TEXT NOT NULL CHECK (
        json_valid(provenance_json)
        AND json_type(provenance_json) = 'object'
    ),
    canonical_contract_json TEXT NOT NULL CHECK (
        json_valid(canonical_contract_json)
        AND json_type(canonical_contract_json) = 'object'
    ),
    contract_hash TEXT NOT NULL CHECK (
        length(contract_hash) = 64
        AND contract_hash NOT GLOB '*[^0-9a-f]*'
    ),
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'active', 'completed', 'stopped', 'failed')
    ),
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (requested_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    CHECK (
        (status = 'pending' AND started_at IS NULL AND completed_at IS NULL)
        OR
        (status = 'active' AND started_at IS NOT NULL AND completed_at IS NULL)
        OR
        (status IN ('completed', 'stopped', 'failed')
            AND completed_at IS NOT NULL)
    )
);

CREATE INDEX tasks_session_status
ON tasks(session_id, status);

CREATE INDEX tasks_project_status
ON tasks(project_scope_id, status);

CREATE TABLE task_state_transitions (
    transition_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    from_status TEXT,
    to_status TEXT NOT NULL CHECK (
        to_status IN ('pending', 'active', 'completed', 'stopped', 'failed')
    ),
    reason_code TEXT NOT NULL CHECK (trim(reason_code) <> ''),
    changed_at TEXT NOT NULL,
    changed_by TEXT NOT NULL CHECK (changed_by = 'governance_kernel'),
    transaction_id TEXT NOT NULL,
    UNIQUE (task_id, sequence_number),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id)
        REFERENCES governed_runtime_transactions(transaction_id)
        ON DELETE RESTRICT,
    CHECK (
        (sequence_number = 0 AND from_status IS NULL AND to_status = 'pending')
        OR
        (sequence_number > 0 AND (
            (from_status = 'pending' AND to_status IN ('active', 'stopped', 'failed'))
            OR
            (from_status = 'active' AND to_status IN ('completed', 'stopped', 'failed'))
        ))
    )
);

CREATE TABLE governance_decisions (
    governance_decision_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    project_scope_id TEXT NOT NULL,
    requested_scope_id TEXT NOT NULL,
    requesting_principal TEXT NOT NULL CHECK (
        requesting_principal IN (
            'apprentice', 'operator', 'codex_development_harness',
            'experimental_harness'
        )
    ),
    runtime_execution_principal TEXT NOT NULL CHECK (
        runtime_execution_principal IN (
            'operator', 'codex_development_harness'
        )
    ),
    requested_operation TEXT NOT NULL CHECK (trim(requested_operation) <> ''),
    requested_action_class TEXT NOT NULL CHECK (
        requested_action_class IN (
            'observe', 'analyse', 'propose', 'execute', 'ambiguous'
        )
    ),
    operation_definition_hash TEXT NOT NULL CHECK (
        length(operation_definition_hash) = 64
        AND operation_definition_hash NOT GLOB '*[^0-9a-f]*'
    ),
    permission_profile_id TEXT NOT NULL,
    permission_profile_hash TEXT NOT NULL CHECK (
        length(permission_profile_hash) = 64
        AND permission_profile_hash NOT GLOB '*[^0-9a-f]*'
    ),
    permission_profile_applicable INTEGER NOT NULL CHECK (
        permission_profile_applicable IN (0, 1)
    ),
    precedence_authority_class TEXT CHECK (
        precedence_authority_class IS NULL
        OR precedence_authority_class IN (
            'law_or_external_obligation', 'nolan_approved',
            'nolan_byte_approved', 'validated_system_evidence',
            'approved_project_policy', 'approved_memory',
            'approved_evaluation', 'agent_proposal', 'model_inference',
            'external_untrusted', 'unknown'
        )
    ),
    decision TEXT NOT NULL CHECK (
        decision IN ('allow', 'deny', 'require_human_approval', 'stop')
    ),
    reason_codes_json TEXT NOT NULL CHECK (
        json_valid(reason_codes_json)
        AND json_type(reason_codes_json) = 'array'
    ),
    reasons_json TEXT NOT NULL CHECK (
        json_valid(reasons_json)
        AND json_type(reasons_json) = 'array'
    ),
    authority_assessments_json TEXT NOT NULL CHECK (
        json_valid(authority_assessments_json)
        AND json_type(authority_assessments_json) = 'array'
    ),
    human_approval_assessments_json TEXT NOT NULL CHECK (
        json_valid(human_approval_assessments_json)
        AND json_type(human_approval_assessments_json) = 'array'
    ),
    evidence_assessments_json TEXT NOT NULL CHECK (
        json_valid(evidence_assessments_json)
        AND json_type(evidence_assessments_json) = 'array'
    ),
    policy_violations_json TEXT NOT NULL CHECK (
        json_valid(policy_violations_json)
        AND json_type(policy_violations_json) = 'array'
    ),
    effective_at TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL CHECK (
        json_valid(evidence_ids_json)
        AND json_type(evidence_ids_json) = 'array'
    ),
    governing_rule_ids_json TEXT NOT NULL CHECK (
        json_valid(governing_rule_ids_json)
        AND json_type(governing_rule_ids_json) = 'array'
    ),
    decided_at TEXT NOT NULL,
    runtime_instance_id TEXT NOT NULL,
    task_contract_hash TEXT NOT NULL CHECK (
        length(task_contract_hash) = 64
        AND task_contract_hash NOT GLOB '*[^0-9a-f]*'
    ),
    provenance_json TEXT NOT NULL CHECK (
        json_valid(provenance_json)
        AND json_type(provenance_json) = 'object'
    ),
    apprentice_execute_implication INTEGER NOT NULL CHECK (
        apprentice_execute_implication = 0
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json)
        AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (transaction_id)
        REFERENCES governed_runtime_transactions(transaction_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (requested_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (permission_profile_id)
        REFERENCES permission_profiles(permission_profile_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (runtime_instance_id)
        REFERENCES runtime_instances(runtime_instance_id) ON DELETE RESTRICT
);

CREATE TABLE governance_decision_authority_inputs (
    governance_decision_id TEXT NOT NULL,
    input_order INTEGER NOT NULL CHECK (input_order >= 0),
    claimed_authority_id TEXT NOT NULL,
    resolved_authority_record_id TEXT,
    validation_status TEXT NOT NULL CHECK (
        validation_status IN (
            'applicable', 'missing_authority', 'historical_authority_inactive',
            'authority_revoked', 'unsupported_authority_class',
            'authority_principal_mismatch', 'authority_project_mismatch',
            'authority_out_of_scope', 'authority_task_mismatch',
            'authority_not_yet_effective', 'authority_expired',
            'authority_issuer_mismatch', 'authority_evidence_missing',
            'authority_operation_mismatch', 'operation_definition_missing'
        )
    ),
    PRIMARY KEY (governance_decision_id, input_order),
    UNIQUE (governance_decision_id, claimed_authority_id),
    FOREIGN KEY (governance_decision_id)
        REFERENCES governance_decisions(governance_decision_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (resolved_authority_record_id)
        REFERENCES authority_records(authority_record_id) ON DELETE RESTRICT,
    CHECK (
        (validation_status = 'missing_authority'
            AND resolved_authority_record_id IS NULL)
        OR
        (validation_status <> 'missing_authority'
            AND resolved_authority_record_id = claimed_authority_id)
    )
);

CREATE TABLE governance_decision_human_approvals (
    governance_decision_id TEXT NOT NULL,
    input_order INTEGER NOT NULL CHECK (input_order >= 0),
    claimed_human_approval_id TEXT NOT NULL,
    resolved_human_approval_id TEXT,
    validation_status TEXT NOT NULL CHECK (
        validation_status IN (
            'applicable', 'missing_human_approval',
            'human_approval_principal_mismatch',
            'human_approval_project_mismatch',
            'human_approval_out_of_scope', 'human_approval_task_mismatch',
            'human_approval_operation_mismatch',
            'human_approval_permission_mismatch',
            'human_approval_not_yet_effective', 'human_approval_expired',
            'human_approval_issuer_mismatch',
            'human_approval_evidence_missing',
            'human_approval_already_consumed',
            'human_approval_conditions_unsupported',
            'human_approval_condition_unsatisfied',
            'operation_definition_missing'
        )
    ),
    selected INTEGER NOT NULL CHECK (selected IN (0, 1)),
    consumed INTEGER NOT NULL CHECK (consumed IN (0, 1)),
    PRIMARY KEY (governance_decision_id, input_order),
    UNIQUE (governance_decision_id, claimed_human_approval_id),
    FOREIGN KEY (governance_decision_id)
        REFERENCES governance_decisions(governance_decision_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (resolved_human_approval_id)
        REFERENCES human_approvals(human_approval_id) ON DELETE RESTRICT,
    CHECK (
        (validation_status = 'missing_human_approval'
            AND resolved_human_approval_id IS NULL)
        OR
        (validation_status <> 'missing_human_approval'
            AND resolved_human_approval_id = claimed_human_approval_id)
    ),
    CHECK (consumed = 0 OR selected = 1)
);

CREATE TABLE governance_decision_evidence (
    governance_decision_id TEXT NOT NULL,
    input_order INTEGER NOT NULL CHECK (input_order >= 0),
    required_evidence_id TEXT NOT NULL,
    resolved_evidence_id TEXT,
    input_kind TEXT NOT NULL CHECK (
        input_kind IN ('task', 'authority', 'approval', 'policy')
    ),
    validation_status TEXT NOT NULL CHECK (
        validation_status IN ('available', 'missing')
    ),
    PRIMARY KEY (governance_decision_id, input_order),
    FOREIGN KEY (governance_decision_id)
        REFERENCES governance_decisions(governance_decision_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (resolved_evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT,
    CHECK (
        (validation_status = 'available'
            AND resolved_evidence_id = required_evidence_id)
        OR
        (validation_status = 'missing' AND resolved_evidence_id IS NULL)
    )
);

CREATE TABLE governance_decision_rules (
    governance_decision_id TEXT NOT NULL,
    rule_order INTEGER NOT NULL CHECK (rule_order >= 0),
    governance_rule_id TEXT NOT NULL,
    PRIMARY KEY (governance_decision_id, governance_rule_id),
    UNIQUE (governance_decision_id, rule_order),
    FOREIGN KEY (governance_decision_id)
        REFERENCES governance_decisions(governance_decision_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (governance_rule_id)
        REFERENCES governance_rules(governance_rule_id) ON DELETE RESTRICT
);

CREATE TABLE task_stop_events (
    stop_event_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    governance_decision_id TEXT NOT NULL UNIQUE,
    transaction_id TEXT NOT NULL UNIQUE,
    stop_condition TEXT NOT NULL CHECK (trim(stop_condition) <> ''),
    trigger_source TEXT NOT NULL CHECK (trim(trigger_source) <> ''),
    model_requested_stop INTEGER NOT NULL CHECK (model_requested_stop = 0),
    governance_forced_stop INTEGER NOT NULL CHECK (governance_forced_stop = 1),
    reason_codes_json TEXT NOT NULL CHECK (
        json_valid(reason_codes_json)
        AND json_type(reason_codes_json) = 'array'
    ),
    preserved_evidence_json TEXT NOT NULL CHECK (
        json_valid(preserved_evidence_json)
        AND json_type(preserved_evidence_json) = 'array'
    ),
    created_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json)
        AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
    FOREIGN KEY (governance_decision_id)
        REFERENCES governance_decisions(governance_decision_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id)
        REFERENCES governed_runtime_transactions(transaction_id)
        ON DELETE RESTRICT
);

CREATE TRIGGER tasks_core_immutable
BEFORE UPDATE OF task_id, session_id, contract_version, objective, task_type,
                 project_scope_id, requested_scope_id, requested_operation,
                 requested_action_class, operation_autonomous,
                 requesting_principal, authority_grant_json,
                 claimed_authority_ids_json, claimed_human_approval_ids_json,
                 allowed_sources_json,
                 prohibited_actions_json, expected_output_schema_id,
                 stop_conditions_json, governing_constraints_json,
                 required_evidence_ids_json, effective_at, provenance_json,
                 canonical_contract_json, contract_hash, created_at
ON tasks
BEGIN
    SELECT RAISE(ABORT, 'task identity and contract are immutable');
END;

CREATE TRIGGER tasks_status_requires_transition
BEFORE UPDATE OF status ON tasks
WHEN NEW.status <> OLD.status
AND NOT EXISTS (
    SELECT 1
    FROM task_state_transitions AS transition
    WHERE transition.task_id = OLD.task_id
      AND transition.sequence_number = (
          SELECT MAX(sequence_number)
          FROM task_state_transitions
          WHERE task_id = OLD.task_id
      )
      AND transition.from_status = OLD.status
      AND transition.to_status = NEW.status
)
BEGIN
    SELECT RAISE(ABORT, 'task status change requires a recorded transition');
END;

CREATE TRIGGER tasks_stop_requires_event
BEFORE UPDATE OF status ON tasks
WHEN NEW.status = 'stopped'
AND NOT EXISTS (
    SELECT 1
    FROM task_stop_events
    WHERE task_id = OLD.task_id
)
BEGIN
    SELECT RAISE(ABORT, 'stopped task requires a task-stop event');
END;

CREATE TRIGGER tasks_no_delete
BEFORE DELETE ON tasks
BEGIN
    SELECT RAISE(ABORT, 'tasks cannot be deleted');
END;

CREATE TRIGGER task_transitions_validate_current_state
BEFORE INSERT ON task_state_transitions
WHEN (
    NEW.sequence_number = 0
    AND (
        (SELECT status FROM tasks WHERE task_id = NEW.task_id) <> 'pending'
        OR EXISTS (
            SELECT 1 FROM task_state_transitions
            WHERE task_id = NEW.task_id
        )
    )
)
OR (
    NEW.sequence_number > 0
    AND (
        (SELECT status FROM tasks WHERE task_id = NEW.task_id)
            <> NEW.from_status
        OR NEW.sequence_number <> COALESCE((
            SELECT MAX(sequence_number) + 1
            FROM task_state_transitions
            WHERE task_id = NEW.task_id
        ), 0)
    )
)
BEGIN
    SELECT RAISE(ABORT, 'task transition does not match current state');
END;

CREATE TRIGGER task_transitions_immutable
BEFORE UPDATE ON task_state_transitions
BEGIN
    SELECT RAISE(ABORT, 'task transitions are immutable');
END;

CREATE TRIGGER task_transitions_no_delete
BEFORE DELETE ON task_state_transitions
BEGIN
    SELECT RAISE(ABORT, 'task transitions cannot be deleted');
END;

CREATE TRIGGER governance_decisions_validate_pending_task
BEFORE INSERT ON governance_decisions
WHEN NOT EXISTS (
    SELECT 1
    FROM tasks AS task
    JOIN governed_runtime_transactions AS transaction_record
      ON transaction_record.transaction_id = NEW.transaction_id
    JOIN permission_profiles AS profile
      ON profile.permission_profile_id = NEW.permission_profile_id
    WHERE task.task_id = NEW.task_id
      AND task.session_id = NEW.session_id
      AND task.project_scope_id = NEW.project_scope_id
      AND task.requested_scope_id = NEW.requested_scope_id
      AND task.status = 'pending'
      AND task.contract_hash = NEW.task_contract_hash
      AND transaction_record.task_id = NEW.task_id
      AND transaction_record.status = 'in_progress'
      AND profile.content_hash = NEW.permission_profile_hash
)
BEGIN
    SELECT RAISE(ABORT, 'governance decision inputs do not match pending task');
END;

CREATE TRIGGER governance_decisions_immutable
BEFORE UPDATE ON governance_decisions
BEGIN
    SELECT RAISE(ABORT, 'governance decisions are immutable');
END;

CREATE TRIGGER governance_decisions_no_delete
BEFORE DELETE ON governance_decisions
BEGIN
    SELECT RAISE(ABORT, 'governance decisions cannot be deleted');
END;

CREATE TRIGGER governance_decision_authority_inputs_immutable
BEFORE UPDATE ON governance_decision_authority_inputs
BEGIN
    SELECT RAISE(ABORT, 'decision authority inputs are immutable');
END;

CREATE TRIGGER governance_decision_authority_inputs_no_delete
BEFORE DELETE ON governance_decision_authority_inputs
BEGIN
    SELECT RAISE(ABORT, 'decision authority inputs cannot be deleted');
END;

CREATE TRIGGER governance_decision_human_approvals_immutable
BEFORE UPDATE ON governance_decision_human_approvals
BEGIN
    SELECT RAISE(ABORT, 'decision human approvals are immutable');
END;

CREATE TRIGGER governance_decision_human_approvals_no_delete
BEFORE DELETE ON governance_decision_human_approvals
BEGIN
    SELECT RAISE(ABORT, 'decision human approvals cannot be deleted');
END;

CREATE TRIGGER governance_decision_evidence_immutable
BEFORE UPDATE ON governance_decision_evidence
BEGIN
    SELECT RAISE(ABORT, 'decision evidence inputs are immutable');
END;

CREATE TRIGGER governance_decision_evidence_no_delete
BEFORE DELETE ON governance_decision_evidence
BEGIN
    SELECT RAISE(ABORT, 'decision evidence inputs cannot be deleted');
END;

CREATE TRIGGER governance_decision_rules_immutable
BEFORE UPDATE ON governance_decision_rules
BEGIN
    SELECT RAISE(ABORT, 'decision rule relationships are immutable');
END;

CREATE TRIGGER governance_decision_rules_no_delete
BEFORE DELETE ON governance_decision_rules
BEGIN
    SELECT RAISE(ABORT, 'decision rule relationships cannot be deleted');
END;

CREATE TRIGGER task_stop_events_validate_decision
BEFORE INSERT ON task_stop_events
WHEN NOT EXISTS (
    SELECT 1
    FROM governance_decisions AS decision_record
    WHERE decision_record.governance_decision_id = NEW.governance_decision_id
      AND decision_record.task_id = NEW.task_id
      AND decision_record.transaction_id = NEW.transaction_id
      AND decision_record.decision <> 'allow'
)
BEGIN
    SELECT RAISE(ABORT, 'task-stop event requires a matching non-allow decision');
END;

CREATE TRIGGER task_stop_events_immutable
BEFORE UPDATE ON task_stop_events
BEGIN
    SELECT RAISE(ABORT, 'task-stop events are immutable');
END;

CREATE TRIGGER task_stop_events_no_delete
BEFORE DELETE ON task_stop_events
BEGIN
    SELECT RAISE(ABORT, 'task-stop events cannot be deleted');
END;

CREATE TRIGGER human_approvals_consume_once
BEFORE UPDATE OF consumed_at, consumed_by_task_id, consumed_by_decision_id
ON human_approvals
WHEN NOT (
    OLD.single_use = 1
    AND OLD.consumed_at IS NULL
    AND OLD.consumed_by_task_id IS NULL
    AND OLD.consumed_by_decision_id IS NULL
    AND NEW.consumed_at IS NOT NULL
    AND NEW.consumed_by_task_id IS NOT NULL
    AND NEW.consumed_by_decision_id IS NOT NULL
    AND EXISTS (
        SELECT 1
        FROM governance_decisions AS decision_record
        JOIN governance_decision_human_approvals AS relationship
          ON relationship.governance_decision_id =
             decision_record.governance_decision_id
        WHERE decision_record.governance_decision_id =
              NEW.consumed_by_decision_id
          AND decision_record.task_id = NEW.consumed_by_task_id
          AND decision_record.decision = 'allow'
          AND relationship.claimed_human_approval_id =
              OLD.human_approval_id
          AND relationship.selected = 1
          AND relationship.consumed = 1
    )
)
BEGIN
    SELECT RAISE(ABORT, 'single-use human approval consumption is invalid');
END;

CREATE TRIGGER governed_runtime_transaction_finalise
BEFORE UPDATE OF status, completed_at, structured_failure_json, content_hash
ON governed_runtime_transactions
WHEN NOT (
    OLD.status = 'in_progress'
    AND NEW.status IN ('committed', 'stopped')
    AND NEW.completed_at IS NOT NULL
    AND EXISTS (
        SELECT 1
        FROM tasks AS task
        JOIN governance_decisions AS decision_record
          ON decision_record.task_id = task.task_id
        WHERE task.task_id = OLD.task_id
          AND (
              decision_record.operation_definition_hash = (
                  SELECT content_hash FROM operation_definitions
                  WHERE operation_name = decision_record.requested_operation
              )
              OR (
                  decision_record.decision = 'stop'
                  AND decision_record.operation_definition_hash =
                      '0000000000000000000000000000000000000000000000000000000000000000'
                  AND NOT EXISTS (
                      SELECT 1 FROM operation_definitions
                      WHERE operation_name = decision_record.requested_operation
                  )
              )
          )
          AND (SELECT COUNT(*) FROM governance_decision_authority_inputs
               WHERE governance_decision_id = decision_record.governance_decision_id)
              = json_array_length(decision_record.authority_assessments_json)
          AND (SELECT COUNT(*) FROM governance_decision_human_approvals
               WHERE governance_decision_id = decision_record.governance_decision_id)
              = json_array_length(decision_record.human_approval_assessments_json)
          AND (SELECT COUNT(*) FROM governance_decision_evidence
               WHERE governance_decision_id = decision_record.governance_decision_id)
              = json_array_length(decision_record.evidence_assessments_json)
          AND (SELECT COUNT(*) FROM governance_decision_rules
               WHERE governance_decision_id = decision_record.governance_decision_id)
              = json_array_length(decision_record.governing_rule_ids_json)
          AND (
              decision_record.decision <> 'allow'
              OR decision_record.precedence_authority_class NOT IN (
                  'nolan_approved', 'nolan_byte_approved'
              )
              OR (
                  SELECT COUNT(*)
                  FROM governance_decision_human_approvals
                  WHERE governance_decision_id = decision_record.governance_decision_id
                    AND selected = 1
              ) = 1
          )
          AND NOT EXISTS (
              SELECT 1
              FROM governance_decision_human_approvals AS approval_link
              JOIN human_approvals AS approval
                ON approval.human_approval_id =
                   approval_link.resolved_human_approval_id
              WHERE approval_link.governance_decision_id =
                    decision_record.governance_decision_id
                AND approval_link.selected = 1
                AND approval.single_use = 1
                AND (
                    approval_link.consumed <> 1
                    OR approval.consumed_by_task_id <> task.task_id
                    OR approval.consumed_by_decision_id <>
                       decision_record.governance_decision_id
                )
          )
          AND (
              (NEW.status = 'committed'
                  AND task.status = 'active'
                  AND decision_record.decision = 'allow'
                  AND NOT EXISTS (
                      SELECT 1 FROM task_stop_events
                      WHERE task_id = task.task_id
                  ))
              OR
              (NEW.status = 'stopped'
                  AND task.status = 'stopped'
                  AND decision_record.decision <> 'allow'
                  AND EXISTS (
                      SELECT 1 FROM task_stop_events
                      WHERE task_id = task.task_id
                  ))
          )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'runtime transaction cannot finalise incompletely');
END;

CREATE TRIGGER governed_runtime_transactions_core_immutable
BEFORE UPDATE OF transaction_id, task_id, runtime_instance_id,
                 execution_principal, started_at
ON governed_runtime_transactions
BEGIN
    SELECT RAISE(ABORT, 'runtime transaction identity is immutable');
END;

CREATE TRIGGER governed_runtime_transactions_no_second_update
BEFORE UPDATE ON governed_runtime_transactions
WHEN OLD.status <> 'in_progress'
BEGIN
    SELECT RAISE(ABORT, 'finalised runtime transactions are immutable');
END;

CREATE TRIGGER governed_runtime_transactions_no_delete
BEFORE DELETE ON governed_runtime_transactions
BEGIN
    SELECT RAISE(ABORT, 'runtime transactions cannot be deleted');
END;
