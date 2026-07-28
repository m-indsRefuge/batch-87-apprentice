CREATE TABLE task_context_items (
    context_item_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_scope_id TEXT NOT NULL,
    context_kind TEXT NOT NULL CHECK (
        context_kind IN (
            'constitution', 'policy', 'construct_memory',
            'approved_lesson', 'evidence', 'session_instruction'
        )
    ),
    source_kind TEXT NOT NULL CHECK (
        source_kind IN ('memory_record', 'evidence', 'governance_rule')
    ),
    source_memory_record_id TEXT,
    source_evidence_id TEXT,
    source_governance_rule_id TEXT,
    injection_order INTEGER NOT NULL CHECK (injection_order >= 0),
    required INTEGER NOT NULL CHECK (required IN (0, 1)),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL,
    created_by_principal TEXT NOT NULL CHECK (
        created_by_principal IN ('operator', 'codex_development_harness')
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    canonical_hash TEXT NOT NULL CHECK (
        length(canonical_hash) = 64
        AND canonical_hash NOT GLOB '*[^0-9a-f]*'
    ),
    UNIQUE (task_id, injection_order),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (source_memory_record_id)
        REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (source_evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT,
    FOREIGN KEY (source_governance_rule_id)
        REFERENCES governance_rules(governance_rule_id) ON DELETE RESTRICT,
    CHECK (
        (
            source_kind = 'memory_record'
            AND source_memory_record_id IS NOT NULL
            AND source_evidence_id IS NULL
            AND source_governance_rule_id IS NULL
            AND context_kind IN ('construct_memory', 'approved_lesson')
        )
        OR
        (
            source_kind = 'evidence'
            AND source_memory_record_id IS NULL
            AND source_evidence_id IS NOT NULL
            AND source_governance_rule_id IS NULL
            AND context_kind IN ('evidence', 'session_instruction')
        )
        OR
        (
            source_kind = 'governance_rule'
            AND source_memory_record_id IS NULL
            AND source_evidence_id IS NULL
            AND source_governance_rule_id IS NOT NULL
            AND context_kind IN ('constitution', 'policy')
        )
    )
);

CREATE TABLE task_context_finalizations (
    finalization_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    project_scope_id TEXT NOT NULL,
    item_count INTEGER NOT NULL CHECK (item_count > 0),
    finalized_at TEXT NOT NULL,
    finalized_by_principal TEXT NOT NULL CHECK (
        finalized_by_principal IN ('operator', 'codex_development_harness')
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT
);

CREATE TABLE active_uncertainties (
    record_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_scope_id TEXT NOT NULL,
    uncertainty_statement TEXT NOT NULL CHECK (
        trim(uncertainty_statement) <> ''
    ),
    impact TEXT NOT NULL CHECK (
        impact IN ('low', 'medium', 'high', 'blocking')
    ),
    resolution_required INTEGER NOT NULL CHECK (
        resolution_required IN (0, 1)
    ),
    created_at TEXT NOT NULL,
    created_by_principal TEXT NOT NULL CHECK (
        created_by_principal IN ('operator', 'codex_development_harness')
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    CHECK (impact <> 'blocking' OR resolution_required = 1)
);

CREATE TABLE uncertainty_resolutions (
    resolution_id TEXT PRIMARY KEY,
    uncertainty_record_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_scope_id TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK (
        source_kind IN ('memory_record', 'evidence')
    ),
    source_memory_record_id TEXT,
    source_evidence_id TEXT,
    source_content_hash TEXT NOT NULL CHECK (
        length(source_content_hash) = 64
        AND source_content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    resolved_at TEXT NOT NULL,
    created_by_principal TEXT NOT NULL CHECK (
        created_by_principal IN ('operator', 'codex_development_harness')
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (uncertainty_record_id)
        REFERENCES active_uncertainties(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (source_memory_record_id)
        REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (source_evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT,
    CHECK (
        (
            source_kind = 'memory_record'
            AND source_memory_record_id IS NOT NULL
            AND source_evidence_id IS NULL
        )
        OR
        (
            source_kind = 'evidence'
            AND source_memory_record_id IS NULL
            AND source_evidence_id IS NOT NULL
        )
    )
);

CREATE INDEX task_context_items_task_order
ON task_context_items(task_id, injection_order);

CREATE INDEX task_context_items_memory_source
ON task_context_items(source_memory_record_id);

CREATE INDEX task_context_items_evidence_source
ON task_context_items(source_evidence_id);

CREATE INDEX active_uncertainties_task
ON active_uncertainties(task_id, impact);

CREATE INDEX uncertainty_resolutions_task
ON uncertainty_resolutions(task_id, resolved_at);

CREATE TRIGGER task_context_items_insert_guard
BEFORE INSERT ON task_context_items
WHEN NOT EXISTS (
    SELECT 1
    FROM tasks AS task
    JOIN sessions AS session_record
      ON session_record.session_id = task.session_id
    WHERE task.task_id = NEW.task_id
      AND task.session_id = NEW.session_id
      AND task.project_scope_id = NEW.project_scope_id
      AND session_record.active_project_scope = NEW.project_scope_id
      AND task.status = 'active'
      AND session_record.session_status IN ('open', 'paused')
      AND NEW.created_at >= task.created_at
      AND NEW.created_at >= session_record.opened_at
)
OR EXISTS (
    SELECT 1 FROM task_context_finalizations
    WHERE task_id = NEW.task_id
)
OR (
    NEW.source_kind = 'memory_record'
    AND NOT EXISTS (
        SELECT 1
        FROM records AS source
        WHERE source.record_id = NEW.source_memory_record_id
          AND source.project_scope_id = NEW.project_scope_id
          AND source.lifecycle_state = 'active'
          AND source.approval_status IN ('approved', 'not_required')
          AND source.integrity_status IN ('valid', 'not_applicable')
          AND source.superseded_by_record_id IS NULL
          AND source.sensitivity_class IN ('public', 'internal')
          AND source.privacy_class = 'none'
          AND source.content_hash = NEW.content_hash
          AND (
              (
                  NEW.context_kind = 'construct_memory'
                  AND source.record_family = 'construct_memory'
              )
              OR
              (
                  NEW.context_kind = 'approved_lesson'
                  AND source.record_family = 'episodic_memory'
                  AND source.record_type = 'approved_lesson'
              )
          )
    )
)
OR (
    NEW.source_kind = 'evidence'
    AND NOT EXISTS (
        SELECT 1
        FROM evidence_items AS evidence
        JOIN governance_decision_evidence AS decision_evidence
          ON decision_evidence.resolved_evidence_id = evidence.evidence_id
         AND decision_evidence.required_evidence_id = evidence.evidence_id
         AND decision_evidence.validation_status = 'available'
        JOIN governance_decisions AS decision_record
          ON decision_record.governance_decision_id =
             decision_evidence.governance_decision_id
         AND decision_record.task_id = NEW.task_id
         AND decision_record.project_scope_id = NEW.project_scope_id
        WHERE evidence.evidence_id = NEW.source_evidence_id
          AND evidence.integrity_status = 'valid'
          AND evidence.evidence_kind NOT IN (
              'controlled_prompt', 'controlled_output'
          )
          AND evidence.sensitivity_class <> 'secret'
          AND evidence.privacy_class = 'none'
          AND evidence.content_hash = NEW.content_hash
          AND NOT EXISTS (
              SELECT 1
              FROM controlled_resilience_evidence AS controlled
              WHERE controlled.raw_prompt_evidence_id = evidence.evidence_id
                 OR controlled.raw_output_evidence_id = evidence.evidence_id
          )
    )
)
OR (
    NEW.source_kind = 'governance_rule'
    AND NOT EXISTS (
        SELECT 1
        FROM governance_rules AS rule
        JOIN governance_decision_rules AS decision_rule
          ON decision_rule.governance_rule_id = rule.governance_rule_id
        JOIN governance_decisions AS decision_record
          ON decision_record.governance_decision_id =
             decision_rule.governance_decision_id
         AND decision_record.task_id = NEW.task_id
         AND decision_record.project_scope_id = NEW.project_scope_id
        WHERE rule.governance_rule_id = NEW.source_governance_rule_id
          AND rule.status = 'active'
          AND rule.content_hash = NEW.content_hash
    )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'task context violates task, session, source or finalization boundary'
    );
END;

CREATE TRIGGER task_context_finalizations_insert_guard
BEFORE INSERT ON task_context_finalizations
WHEN NOT EXISTS (
    SELECT 1
    FROM tasks AS task
    JOIN sessions AS session_record
      ON session_record.session_id = task.session_id
    WHERE task.task_id = NEW.task_id
      AND task.session_id = NEW.session_id
      AND task.project_scope_id = NEW.project_scope_id
      AND session_record.active_project_scope = NEW.project_scope_id
      AND task.status = 'active'
      AND session_record.session_status IN ('open', 'paused')
)
OR NEW.item_count <> (
    SELECT COUNT(*) FROM task_context_items
    WHERE task_id = NEW.task_id
)
OR (
    SELECT MIN(injection_order) FROM task_context_items
    WHERE task_id = NEW.task_id
) <> 0
OR (
    SELECT MAX(injection_order) FROM task_context_items
    WHERE task_id = NEW.task_id
) <> NEW.item_count - 1
OR EXISTS (
    SELECT 1 FROM task_context_items
    WHERE task_id = NEW.task_id
      AND created_at > NEW.finalized_at
)
BEGIN
    SELECT RAISE(
        ABORT,
        'task context finalization requires a complete gap-free active-task set'
    );
END;

CREATE TRIGGER active_uncertainties_insert_guard
BEFORE INSERT ON active_uncertainties
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS envelope
    JOIN tasks AS task ON task.task_id = NEW.task_id
    JOIN sessions AS session_record
      ON session_record.session_id = NEW.session_id
    JOIN entities AS creator
      ON creator.entity_id = envelope.created_by_entity_id
    WHERE envelope.record_id = NEW.record_id
      AND envelope.record_family = 'session_task_memory'
      AND envelope.record_type = 'active_uncertainty'
      AND envelope.task_id = NEW.task_id
      AND envelope.session_id = NEW.session_id
      AND envelope.project_scope_id = NEW.project_scope_id
      AND envelope.created_at = NEW.created_at
      AND envelope.lifecycle_state = 'observed'
      AND envelope.approval_status = 'not_required'
      AND envelope.agent_write_policy = 'candidate_only'
      AND envelope.integrity_status = 'valid'
      AND envelope.sensitivity_class IN ('public', 'internal')
      AND envelope.privacy_class = 'none'
      AND task.session_id = NEW.session_id
      AND task.project_scope_id = NEW.project_scope_id
      AND task.status = 'active'
      AND session_record.active_project_scope = NEW.project_scope_id
      AND session_record.session_status IN ('open', 'paused')
      AND NEW.created_at >= task.created_at
      AND NEW.created_at >= session_record.opened_at
      AND creator.status = 'active'
      AND (
          (
              NEW.created_by_principal = 'operator'
              AND creator.entity_kind = 'person'
          )
          OR
          (
              NEW.created_by_principal = 'codex_development_harness'
              AND creator.entity_kind = 'system'
          )
      )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'active uncertainty violates task, session, envelope or creator boundary'
    );
END;

CREATE TRIGGER active_uncertainty_initial_history_guard
BEFORE INSERT ON memory_record_lifecycle_transitions
WHEN NEW.sequence_number = 0
AND (
    SELECT record_type FROM records WHERE record_id = NEW.record_id
) = 'active_uncertainty'
AND NOT EXISTS (
    SELECT 1 FROM active_uncertainties
    WHERE record_id = NEW.record_id
)
BEGIN
    SELECT RAISE(
        ABORT,
        'active uncertainty history requires its immutable payload'
    );
END;

CREATE TRIGGER uncertainty_resolutions_insert_guard
BEFORE INSERT ON uncertainty_resolutions
WHEN NOT EXISTS (
    SELECT 1
    FROM active_uncertainties AS uncertainty
    JOIN records AS uncertainty_record
      ON uncertainty_record.record_id = uncertainty.record_id
    WHERE uncertainty.record_id = NEW.uncertainty_record_id
      AND uncertainty.task_id = NEW.task_id
      AND uncertainty.session_id = NEW.session_id
      AND uncertainty.project_scope_id = NEW.project_scope_id
      AND uncertainty_record.task_id = NEW.task_id
      AND uncertainty_record.session_id = NEW.session_id
      AND uncertainty_record.project_scope_id = NEW.project_scope_id
      AND uncertainty_record.integrity_status = 'valid'
      AND NEW.resolved_at >= uncertainty.created_at
      AND (
          SELECT transition.to_state
          FROM memory_record_lifecycle_transitions AS transition
          WHERE transition.record_id = uncertainty.record_id
            AND transition.changed_at <= NEW.resolved_at
          ORDER BY transition.sequence_number DESC
          LIMIT 1
      ) NOT IN ('superseded', 'revoked', 'archived', 'deleted')
)
OR (
    NEW.source_kind = 'memory_record'
    AND NOT EXISTS (
        SELECT 1
        FROM records AS source
        WHERE source.record_id = NEW.source_memory_record_id
          AND source.task_id = NEW.task_id
          AND source.project_scope_id = NEW.project_scope_id
          AND source.lifecycle_state = 'active'
          AND source.approval_status IN ('approved', 'not_required')
          AND source.integrity_status IN ('valid', 'not_applicable')
          AND source.superseded_by_record_id IS NULL
          AND source.content_hash = NEW.source_content_hash
          AND (
              SELECT transition.to_state
              FROM memory_record_lifecycle_transitions AS transition
              WHERE transition.record_id = source.record_id
                AND transition.changed_at <= NEW.resolved_at
              ORDER BY transition.sequence_number DESC
              LIMIT 1
          ) = 'active'
          AND (
              SELECT transition.to_status
              FROM memory_record_approval_transitions AS transition
              WHERE transition.record_id = source.record_id
                AND transition.changed_at <= NEW.resolved_at
              ORDER BY transition.sequence_number DESC
              LIMIT 1
          ) IN ('approved', 'not_required')
    )
)
OR (
    NEW.source_kind = 'evidence'
    AND NOT EXISTS (
        SELECT 1
        FROM evidence_items AS evidence
        JOIN governance_decision_evidence AS decision_evidence
          ON decision_evidence.resolved_evidence_id = evidence.evidence_id
         AND decision_evidence.validation_status = 'available'
         AND decision_evidence.required_evidence_id = evidence.evidence_id
        JOIN governance_decisions AS decision_record
          ON decision_record.governance_decision_id =
             decision_evidence.governance_decision_id
         AND decision_record.task_id = NEW.task_id
         AND decision_record.project_scope_id = NEW.project_scope_id
        WHERE evidence.evidence_id = NEW.source_evidence_id
          AND evidence.integrity_status = 'valid'
          AND evidence.evidence_kind NOT IN (
              'controlled_prompt', 'controlled_output'
          )
          AND evidence.content_hash = NEW.source_content_hash
          AND NOT EXISTS (
              SELECT 1
              FROM controlled_resilience_evidence AS controlled
              WHERE controlled.raw_prompt_evidence_id = evidence.evidence_id
                 OR controlled.raw_output_evidence_id = evidence.evidence_id
          )
    )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'uncertainty resolution violates binding, time or source boundary'
    );
END;

CREATE TRIGGER task_context_items_immutable
BEFORE UPDATE ON task_context_items
BEGIN
    SELECT RAISE(ABORT, 'task context items are immutable');
END;

CREATE TRIGGER task_context_items_no_delete
BEFORE DELETE ON task_context_items
BEGIN
    SELECT RAISE(ABORT, 'task context items cannot be deleted');
END;

CREATE TRIGGER task_context_finalizations_immutable
BEFORE UPDATE ON task_context_finalizations
BEGIN
    SELECT RAISE(ABORT, 'task context finalizations are immutable');
END;

CREATE TRIGGER task_context_finalizations_no_delete
BEFORE DELETE ON task_context_finalizations
BEGIN
    SELECT RAISE(ABORT, 'task context finalizations cannot be deleted');
END;

CREATE TRIGGER active_uncertainties_immutable
BEFORE UPDATE ON active_uncertainties
BEGIN
    SELECT RAISE(ABORT, 'active uncertainties are immutable');
END;

CREATE TRIGGER active_uncertainty_records_immutable
BEFORE UPDATE OF record_family, record_type, schema_version,
                 construct_scope_id, project_scope_id, subject_entity_id,
                 session_id, task_id, authority_class, certainty_class,
                 sensitivity_class, privacy_class, retention_class,
                 training_eligibility, created_at, created_by_entity_id,
                 created_by_runtime_id, effective_from, effective_until,
                 review_due_at, supersedes_record_id, previous_version_id,
                 source_kind, provenance_summary, retrieval_policy_json,
                 deletion_policy_json, agent_write_policy, content_hash
ON records
WHEN EXISTS (
    SELECT 1 FROM active_uncertainties
    WHERE record_id = OLD.record_id
)
BEGIN
    SELECT RAISE(
        ABORT,
        'active uncertainty record identity and content are immutable'
    );
END;

CREATE TRIGGER active_uncertainties_no_delete
BEFORE DELETE ON active_uncertainties
BEGIN
    SELECT RAISE(ABORT, 'active uncertainties cannot be deleted');
END;

CREATE TRIGGER uncertainty_resolutions_immutable
BEFORE UPDATE ON uncertainty_resolutions
BEGIN
    SELECT RAISE(ABORT, 'uncertainty resolutions are immutable');
END;

CREATE TRIGGER uncertainty_resolutions_no_delete
BEFORE DELETE ON uncertainty_resolutions
BEGIN
    SELECT RAISE(ABORT, 'uncertainty resolutions cannot be deleted');
END;

CREATE TRIGGER session_participants_contract_guard
BEFORE INSERT ON session_participants
WHEN NOT EXISTS (
    SELECT 1
    FROM sessions AS session_record
    WHERE session_record.session_id = NEW.session_id
      AND json_type(
          session_record.canonical_json,
          '$.participant_entity_ids'
      ) = 'array'
      AND EXISTS (
          SELECT 1
          FROM json_each(
              session_record.canonical_json,
              '$.participant_entity_ids'
          ) AS participant
          WHERE participant.type = 'text'
            AND participant.value = NEW.entity_id
      )
      AND (
          (
              NEW.entity_id = session_record.created_by_entity_id
              AND NEW.role = 'operator'
          )
          OR
          (
              NEW.entity_id <> session_record.created_by_entity_id
              AND NEW.role = 'participant'
          )
      )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'session participant differs from the canonical session contract'
    );
END;

CREATE TRIGGER session_state_transitions_monotonic_time_guard
BEFORE INSERT ON session_state_transitions
WHEN NEW.sequence_number > 0
AND NEW.changed_at < (
    SELECT prior.changed_at
    FROM session_state_transitions AS prior
    WHERE prior.session_id = NEW.session_id
    ORDER BY prior.sequence_number DESC
    LIMIT 1
)
BEGIN
    SELECT RAISE(
        ABORT,
        'session transition timestamp cannot regress'
    );
END;

CREATE TRIGGER task_state_transitions_monotonic_time_guard
BEFORE INSERT ON task_state_transitions
WHEN NEW.sequence_number > 0
AND NEW.changed_at < (
    SELECT prior.changed_at
    FROM task_state_transitions AS prior
    WHERE prior.task_id = NEW.task_id
    ORDER BY prior.sequence_number DESC
    LIMIT 1
)
BEGIN
    SELECT RAISE(
        ABORT,
        'task transition timestamp cannot regress'
    );
END;

CREATE TRIGGER task_state_transitions_transaction_guard
BEFORE INSERT ON task_state_transitions
WHEN NOT EXISTS (
    SELECT 1
    FROM governed_runtime_transactions AS transaction_record
    WHERE transaction_record.transaction_id = NEW.transaction_id
      AND transaction_record.task_id = NEW.task_id
)
BEGIN
    SELECT RAISE(
        ABORT,
        'task transition requires its exact governed transaction'
    );
END;
