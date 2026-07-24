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

CREATE TRIGGER sessions_immutable
BEFORE UPDATE ON sessions
BEGIN
    SELECT RAISE(ABORT, 'session contracts are immutable');
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
    sequence_number INTEGER NOT NULL CHECK (sequence_number IN (0, 1)),
    from_status TEXT,
    to_status TEXT NOT NULL CHECK (
        to_status IN ('pending', 'active', 'stopped')
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
        (sequence_number = 1 AND from_status = 'pending'
            AND to_status IN ('active', 'stopped'))
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
            'authority_operation_mismatch'
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

CREATE TABLE governance_decision_evidence (
    governance_decision_id TEXT NOT NULL,
    input_order INTEGER NOT NULL CHECK (input_order >= 0),
    required_evidence_id TEXT NOT NULL,
    resolved_evidence_id TEXT,
    input_kind TEXT NOT NULL CHECK (
        input_kind IN ('task', 'authority', 'policy')
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
                 claimed_authority_ids_json, allowed_sources_json,
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
      AND transition.sequence_number = 1
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
    NEW.sequence_number = 1
    AND (
        (SELECT status FROM tasks WHERE task_id = NEW.task_id) <> 'pending'
        OR NOT EXISTS (
            SELECT 1 FROM task_state_transitions
            WHERE task_id = NEW.task_id
              AND sequence_number = 0
              AND from_status IS NULL
              AND to_status = 'pending'
        )
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
