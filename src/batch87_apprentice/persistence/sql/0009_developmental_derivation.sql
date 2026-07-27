CREATE TABLE lesson_candidates (
    record_id TEXT PRIMARY KEY,
    lesson_statement TEXT NOT NULL CHECK (trim(lesson_statement) <> ''),
    intended_scope TEXT NOT NULL CHECK (
        intended_scope IN ('task', 'project', 'construct')
    ),
    proposer_entity_id TEXT NOT NULL,
    proposed_by TEXT NOT NULL CHECK (
        proposed_by IN ('apprentice', 'byte', 'evaluator')
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (proposer_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT
);

CREATE TABLE lesson_candidate_source_episodes (
    record_id TEXT NOT NULL,
    episode_id TEXT NOT NULL,
    source_order INTEGER NOT NULL CHECK (source_order >= 0),
    PRIMARY KEY (record_id, episode_id),
    UNIQUE (record_id, source_order),
    FOREIGN KEY (record_id)
        REFERENCES lesson_candidates(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (episode_id) REFERENCES episodes(record_id) ON DELETE RESTRICT
);

CREATE TABLE lesson_candidate_source_corrections (
    record_id TEXT NOT NULL,
    correction_id TEXT NOT NULL,
    source_order INTEGER NOT NULL CHECK (source_order >= 0),
    PRIMARY KEY (record_id, correction_id),
    UNIQUE (record_id, source_order),
    FOREIGN KEY (record_id)
        REFERENCES lesson_candidates(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (correction_id)
        REFERENCES corrections(record_id) ON DELETE RESTRICT
);

CREATE TABLE lesson_candidate_limitations (
    record_id TEXT NOT NULL,
    limitation_order INTEGER NOT NULL CHECK (limitation_order >= 0),
    limitation TEXT NOT NULL CHECK (trim(limitation) <> ''),
    PRIMARY KEY (record_id, limitation_order),
    UNIQUE (record_id, limitation),
    FOREIGN KEY (record_id)
        REFERENCES lesson_candidates(record_id) ON DELETE RESTRICT
);

CREATE TABLE approved_lessons (
    record_id TEXT PRIMARY KEY,
    candidate_record_id TEXT NOT NULL UNIQUE,
    lesson_statement TEXT NOT NULL CHECK (trim(lesson_statement) <> ''),
    approved_by TEXT NOT NULL CHECK (approved_by = 'nolan-byte'),
    stability TEXT NOT NULL CHECK (
        stability IN ('new', 'repeated', 'stable')
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (candidate_record_id)
        REFERENCES lesson_candidates(record_id) ON DELETE RESTRICT,
    CHECK (record_id <> candidate_record_id)
);

CREATE TABLE approved_lesson_source_episodes (
    record_id TEXT NOT NULL,
    episode_id TEXT NOT NULL,
    source_order INTEGER NOT NULL CHECK (source_order >= 0),
    PRIMARY KEY (record_id, episode_id),
    UNIQUE (record_id, source_order),
    FOREIGN KEY (record_id)
        REFERENCES approved_lessons(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (episode_id) REFERENCES episodes(record_id) ON DELETE RESTRICT
);

CREATE TABLE approved_lesson_source_corrections (
    record_id TEXT NOT NULL,
    correction_id TEXT NOT NULL,
    source_order INTEGER NOT NULL CHECK (source_order >= 0),
    PRIMARY KEY (record_id, correction_id),
    UNIQUE (record_id, source_order),
    FOREIGN KEY (record_id)
        REFERENCES approved_lessons(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (correction_id)
        REFERENCES corrections(record_id) ON DELETE RESTRICT
);

CREATE TABLE approved_lesson_application_conditions (
    record_id TEXT NOT NULL,
    condition_order INTEGER NOT NULL CHECK (condition_order >= 0),
    condition TEXT NOT NULL CHECK (trim(condition) <> ''),
    PRIMARY KEY (record_id, condition_order),
    UNIQUE (record_id, condition),
    FOREIGN KEY (record_id)
        REFERENCES approved_lessons(record_id) ON DELETE RESTRICT
);

CREATE TABLE approved_lesson_non_application_conditions (
    record_id TEXT NOT NULL,
    condition_order INTEGER NOT NULL CHECK (condition_order >= 0),
    condition TEXT NOT NULL CHECK (trim(condition) <> ''),
    PRIMARY KEY (record_id, condition_order),
    UNIQUE (record_id, condition),
    FOREIGN KEY (record_id)
        REFERENCES approved_lessons(record_id) ON DELETE RESTRICT
);

CREATE TABLE approved_lesson_transfer_tests (
    record_id TEXT NOT NULL,
    evaluation_record_id TEXT NOT NULL,
    transfer_order INTEGER NOT NULL CHECK (transfer_order >= 0),
    PRIMARY KEY (record_id, evaluation_record_id),
    UNIQUE (record_id, transfer_order),
    FOREIGN KEY (record_id)
        REFERENCES approved_lessons(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (evaluation_record_id)
        REFERENCES governed_evaluation_record_anchors(evaluation_record_id)
        ON DELETE RESTRICT
);

CREATE TABLE failure_patterns (
    record_id TEXT PRIMARY KEY,
    pattern_name TEXT NOT NULL CHECK (trim(pattern_name) <> ''),
    description TEXT NOT NULL CHECK (trim(description) <> ''),
    frequency INTEGER NOT NULL CHECK (frequency >= 2),
    severity TEXT NOT NULL CHECK (severity IN ('material', 'critical')),
    containment_required INTEGER NOT NULL CHECK (containment_required = 1),
    resolution_status TEXT NOT NULL CHECK (
        resolution_status IN ('open', 'improving', 'resolved', 'model-limitation')
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT
);

CREATE TABLE failure_pattern_episodes (
    record_id TEXT NOT NULL,
    episode_id TEXT NOT NULL,
    episode_order INTEGER NOT NULL CHECK (episode_order >= 0),
    PRIMARY KEY (record_id, episode_id),
    UNIQUE (record_id, episode_order),
    FOREIGN KEY (record_id)
        REFERENCES failure_patterns(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (episode_id) REFERENCES episodes(record_id) ON DELETE RESTRICT
);

CREATE TABLE success_patterns (
    record_id TEXT PRIMARY KEY,
    pattern_name TEXT NOT NULL CHECK (trim(pattern_name) <> ''),
    description TEXT NOT NULL CHECK (trim(description) <> ''),
    stability TEXT NOT NULL CHECK (
        stability IN ('emerging', 'repeated', 'stable')
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT
);

CREATE TABLE success_pattern_episodes (
    record_id TEXT NOT NULL,
    episode_id TEXT NOT NULL,
    episode_order INTEGER NOT NULL CHECK (episode_order >= 0),
    PRIMARY KEY (record_id, episode_id),
    UNIQUE (record_id, episode_order),
    FOREIGN KEY (record_id)
        REFERENCES success_patterns(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (episode_id) REFERENCES episodes(record_id) ON DELETE RESTRICT
);

CREATE TABLE success_pattern_transfer_scopes (
    record_id TEXT NOT NULL,
    scope_order INTEGER NOT NULL CHECK (scope_order >= 0),
    transfer_scope TEXT NOT NULL CHECK (trim(transfer_scope) <> ''),
    PRIMARY KEY (record_id, scope_order),
    UNIQUE (record_id, transfer_scope),
    FOREIGN KEY (record_id)
        REFERENCES success_patterns(record_id) ON DELETE RESTRICT
);

CREATE INDEX lesson_candidate_episode_lineage
ON lesson_candidate_source_episodes(episode_id, record_id);

CREATE INDEX lesson_candidate_correction_lineage
ON lesson_candidate_source_corrections(correction_id, record_id);

CREATE INDEX approved_lesson_episode_lineage
ON approved_lesson_source_episodes(episode_id, record_id);

CREATE INDEX approved_lesson_correction_lineage
ON approved_lesson_source_corrections(correction_id, record_id);

CREATE INDEX approved_lesson_transfer_lineage
ON approved_lesson_transfer_tests(evaluation_record_id, record_id);

CREATE INDEX failure_pattern_episode_lineage
ON failure_pattern_episodes(episode_id, record_id);

CREATE INDEX success_pattern_episode_lineage
ON success_pattern_episodes(episode_id, record_id);


CREATE TRIGGER lesson_candidates_insert_guard
BEFORE INSERT ON lesson_candidates
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS record
    JOIN entities AS proposer ON proposer.entity_id = NEW.proposer_entity_id
    WHERE record.record_id = NEW.record_id
      AND record.record_family = 'episodic_memory'
      AND record.record_type = 'lesson_candidate'
      AND record.lifecycle_state = 'candidate'
      AND record.approval_status = 'pending'
      AND record.agent_write_policy = 'candidate_only'
      AND record.integrity_status = 'valid'
      AND record.project_scope_id IS NOT NULL
      AND record.sensitivity_class IN ('public', 'internal')
      AND record.privacy_class = 'none'
      AND proposer.status = 'active'
      AND (
          NEW.proposed_by <> 'apprentice'
           OR (
               record.task_id IS NOT NULL
               AND record.created_by_entity_id = NEW.proposer_entity_id
               AND proposer.entity_kind = 'agent'
               AND EXISTS (
                  SELECT 1
                  FROM tasks AS task
                  JOIN governance_decisions AS decision
                    ON decision.task_id = task.task_id
                  JOIN governed_runtime_transactions AS transaction_record
                    ON transaction_record.transaction_id = decision.transaction_id
                   WHERE task.task_id = record.task_id
                     AND task.project_scope_id = record.project_scope_id
                     AND task.session_id = record.session_id
                     AND task.requesting_principal = 'apprentice'
                     AND task.requested_action_class = 'analyse'
                     AND task.status = 'active'
                     AND task.started_at <= record.created_at
                     AND task.completed_at IS NULL
                     AND decision.project_scope_id = record.project_scope_id
                     AND decision.session_id = record.session_id
                     AND decision.requesting_principal = 'apprentice'
                     AND decision.requested_action_class = 'analyse'
                     AND decision.decision = 'allow'
                     AND decision.apprentice_execute_implication = 0
                     AND transaction_record.task_id = task.task_id
                     AND transaction_record.status = 'committed'
               )
          )
      )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'lesson candidate requires exact type, active proposer, and governed task'
    );
END;

CREATE TRIGGER approved_lessons_insert_guard
BEFORE INSERT ON approved_lessons
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS approved
    JOIN records AS candidate
      ON candidate.record_id = NEW.candidate_record_id
    JOIN lesson_candidates AS payload
      ON payload.record_id = candidate.record_id
    WHERE approved.record_id = NEW.record_id
      AND approved.record_family = 'episodic_memory'
      AND approved.record_type = 'approved_lesson'
      AND approved.lifecycle_state = 'reviewed'
      AND approved.approval_status = 'pending'
      AND approved.agent_write_policy = 'prohibited'
      AND approved.integrity_status = 'valid'
      AND approved.project_scope_id = candidate.project_scope_id
      AND candidate.record_family = 'episodic_memory'
      AND candidate.record_type = 'lesson_candidate'
      AND candidate.lifecycle_state = 'reviewed'
      AND candidate.approval_status = 'pending'
      AND candidate.integrity_status = 'valid'
)
BEGIN
    SELECT RAISE(ABORT, 'approved lesson requires one exact reviewed candidate');
END;

CREATE TRIGGER failure_patterns_insert_guard
BEFORE INSERT ON failure_patterns
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS record
    WHERE record.record_id = NEW.record_id
      AND record.record_family = 'episodic_memory'
      AND record.record_type = 'failure_pattern'
      AND record.lifecycle_state = 'candidate'
      AND record.approval_status = 'pending'
      AND record.agent_write_policy = 'candidate_only'
      AND record.integrity_status = 'valid'
      AND record.project_scope_id IS NOT NULL
      AND record.sensitivity_class IN ('public', 'internal')
      AND record.privacy_class = 'none'
      AND (
          record.created_by_entity_id IS NULL
          OR EXISTS (
              SELECT 1
              FROM entities AS creator
              WHERE creator.entity_id = record.created_by_entity_id
                AND creator.entity_kind <> 'agent'
          )
          OR EXISTS (
              SELECT 1
              FROM entities AS creator
              JOIN tasks AS task ON task.task_id = record.task_id
              JOIN governance_decisions AS decision
                ON decision.task_id = task.task_id
              JOIN governed_runtime_transactions AS transaction_record
                ON transaction_record.transaction_id = decision.transaction_id
              WHERE creator.entity_id = record.created_by_entity_id
                AND creator.entity_kind = 'agent'
                AND creator.status = 'active'
                AND task.project_scope_id = record.project_scope_id
                AND task.session_id = record.session_id
                AND task.requesting_principal = 'apprentice'
                AND task.requested_action_class = 'analyse'
                AND task.status = 'active'
                AND task.started_at <= record.created_at
                AND task.completed_at IS NULL
                AND decision.project_scope_id = record.project_scope_id
                AND decision.session_id = record.session_id
                AND decision.requesting_principal = 'apprentice'
                AND decision.requested_action_class = 'analyse'
                AND decision.decision = 'allow'
                AND decision.apprentice_execute_implication = 0
                AND transaction_record.task_id = task.task_id
                AND transaction_record.status = 'committed'
          )
      )
)
BEGIN
    SELECT RAISE(ABORT, 'failure pattern requires exact candidate-bound record');
END;

CREATE TRIGGER success_patterns_insert_guard
BEFORE INSERT ON success_patterns
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS record
    WHERE record.record_id = NEW.record_id
      AND record.record_family = 'episodic_memory'
      AND record.record_type = 'success_pattern'
      AND record.lifecycle_state = 'candidate'
      AND record.approval_status = 'pending'
      AND record.agent_write_policy = 'candidate_only'
      AND record.integrity_status = 'valid'
      AND record.project_scope_id IS NOT NULL
      AND record.sensitivity_class IN ('public', 'internal')
      AND record.privacy_class = 'none'
      AND (
          record.created_by_entity_id IS NULL
          OR EXISTS (
              SELECT 1
              FROM entities AS creator
              WHERE creator.entity_id = record.created_by_entity_id
                AND creator.entity_kind <> 'agent'
          )
          OR EXISTS (
              SELECT 1
              FROM entities AS creator
              JOIN tasks AS task ON task.task_id = record.task_id
              JOIN governance_decisions AS decision
                ON decision.task_id = task.task_id
              JOIN governed_runtime_transactions AS transaction_record
                ON transaction_record.transaction_id = decision.transaction_id
              WHERE creator.entity_id = record.created_by_entity_id
                AND creator.entity_kind = 'agent'
                AND creator.status = 'active'
                AND task.project_scope_id = record.project_scope_id
                AND task.session_id = record.session_id
                AND task.requesting_principal = 'apprentice'
                AND task.requested_action_class = 'analyse'
                AND task.status = 'active'
                AND task.started_at <= record.created_at
                AND task.completed_at IS NULL
                AND decision.project_scope_id = record.project_scope_id
                AND decision.session_id = record.session_id
                AND decision.requesting_principal = 'apprentice'
                AND decision.requested_action_class = 'analyse'
                AND decision.decision = 'allow'
                AND decision.apprentice_execute_implication = 0
                AND transaction_record.task_id = task.task_id
                AND transaction_record.status = 'committed'
          )
      )
)
BEGIN
    SELECT RAISE(ABORT, 'success pattern requires exact candidate-bound record');
END;


CREATE TRIGGER lesson_candidate_source_episode_guard
BEFORE INSERT ON lesson_candidate_source_episodes
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
)
OR NOT EXISTS (
    SELECT 1
    FROM lesson_candidates AS candidate
    JOIN records AS candidate_record
      ON candidate_record.record_id = candidate.record_id
    JOIN episodes AS episode ON episode.record_id = NEW.episode_id
    JOIN records AS episode_record ON episode_record.record_id = episode.record_id
    WHERE candidate.record_id = NEW.record_id
      AND candidate_record.project_scope_id = episode_record.project_scope_id
      AND episode_record.record_family = 'episodic_memory'
      AND episode_record.record_type = 'episode'
      AND episode_record.lifecycle_state NOT IN ('revoked', 'deleted')
      AND episode_record.integrity_status = 'valid'
      AND NOT EXISTS (
          SELECT 1
          FROM record_evidence_links AS link
          JOIN evidence_items AS evidence ON evidence.evidence_id = link.evidence_id
            WHERE link.record_id = episode.record_id
              AND (
                evidence.integrity_status <> 'valid'
                OR evidence.evidence_kind IN (
                    'controlled_prompt', 'controlled_output'
                )
                OR EXISTS (
                    SELECT 1 FROM controlled_resilience_evidence AS controlled
                    WHERE controlled.raw_prompt_evidence_id = evidence.evidence_id
                       OR controlled.raw_output_evidence_id = evidence.evidence_id
                )
            )
      )
)
BEGIN
    SELECT RAISE(ABORT, 'invalid or post-finalization candidate episode source');
END;

CREATE TRIGGER lesson_candidate_source_correction_guard
BEFORE INSERT ON lesson_candidate_source_corrections
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
)
OR NOT EXISTS (
    SELECT 1
    FROM lesson_candidates AS candidate
    JOIN records AS candidate_record
      ON candidate_record.record_id = candidate.record_id
    JOIN corrections AS correction
      ON correction.record_id = NEW.correction_id
    JOIN records AS correction_record
      ON correction_record.record_id = correction.record_id
    JOIN lesson_candidate_source_episodes AS source_episode
      ON source_episode.record_id = candidate.record_id
     AND source_episode.episode_id = correction.target_episode_id
    JOIN episode_output_evidence AS output
      ON output.record_id = correction.target_episode_id
     AND output.evidence_id = correction.target_output_evidence_id
    WHERE candidate.record_id = NEW.record_id
      AND candidate_record.project_scope_id = correction_record.project_scope_id
      AND correction_record.record_family = 'episodic_memory'
      AND correction_record.record_type = 'correction'
      AND correction_record.lifecycle_state NOT IN ('revoked', 'deleted')
      AND correction_record.integrity_status = 'valid'
      AND NOT EXISTS (
          SELECT 1
          FROM record_evidence_links AS link
          JOIN evidence_items AS evidence ON evidence.evidence_id = link.evidence_id
            WHERE link.record_id = correction.record_id
              AND (
                evidence.integrity_status <> 'valid'
                OR evidence.evidence_kind IN (
                    'controlled_prompt', 'controlled_output'
                )
                OR EXISTS (
                    SELECT 1 FROM controlled_resilience_evidence AS controlled
                    WHERE controlled.raw_prompt_evidence_id = evidence.evidence_id
                       OR controlled.raw_output_evidence_id = evidence.evidence_id
                )
            )
      )
)
BEGIN
    SELECT RAISE(ABORT, 'invalid or unsupported candidate correction source');
END;

CREATE TRIGGER approved_lesson_source_episode_guard
BEFORE INSERT ON approved_lesson_source_episodes
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
)
OR NOT EXISTS (
    SELECT 1
    FROM approved_lessons AS approved
    JOIN records AS approved_record ON approved_record.record_id = approved.record_id
    JOIN lesson_candidate_source_episodes AS candidate_source
      ON candidate_source.record_id = approved.candidate_record_id
     AND candidate_source.episode_id = NEW.episode_id
    JOIN records AS episode_record
      ON episode_record.record_id = candidate_source.episode_id
    WHERE approved.record_id = NEW.record_id
      AND approved_record.project_scope_id = episode_record.project_scope_id
      AND episode_record.lifecycle_state NOT IN ('revoked', 'deleted')
      AND episode_record.integrity_status = 'valid'
)
BEGIN
    SELECT RAISE(ABORT, 'approved lesson episode is unsupported or post-finalization');
END;

CREATE TRIGGER approved_lesson_source_correction_guard
BEFORE INSERT ON approved_lesson_source_corrections
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
)
OR NOT EXISTS (
    SELECT 1
    FROM approved_lessons AS approved
    JOIN records AS approved_record ON approved_record.record_id = approved.record_id
    JOIN lesson_candidate_source_corrections AS candidate_source
      ON candidate_source.record_id = approved.candidate_record_id
     AND candidate_source.correction_id = NEW.correction_id
    JOIN corrections AS correction
      ON correction.record_id = candidate_source.correction_id
    JOIN records AS correction_record
      ON correction_record.record_id = correction.record_id
    JOIN approved_lesson_source_episodes AS source_episode
      ON source_episode.record_id = approved.record_id
     AND source_episode.episode_id = correction.target_episode_id
    WHERE approved.record_id = NEW.record_id
      AND approved_record.project_scope_id = correction_record.project_scope_id
      AND correction_record.lifecycle_state NOT IN ('revoked', 'deleted')
      AND correction_record.integrity_status = 'valid'
)
BEGIN
    SELECT RAISE(
        ABORT,
        'approved lesson correction is unsupported or post-finalization'
    );
END;

CREATE TRIGGER approved_lesson_transfer_test_guard
BEFORE INSERT ON approved_lesson_transfer_tests
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
)
OR NOT EXISTS (
    SELECT 1
    FROM approved_lessons AS approved
    JOIN records AS record ON record.record_id = approved.record_id
    JOIN governed_evaluation_record_anchors AS evaluation
      ON evaluation.evaluation_record_id = NEW.evaluation_record_id
    JOIN evidence_items AS provenance
      ON provenance.evidence_id = evaluation.provenance_evidence_id
    WHERE approved.record_id = NEW.record_id
      AND evaluation.evaluation_kind = 'capability_evaluation'
      AND evaluation.project_scope_id = record.project_scope_id
      AND evaluation.current_state = 'claimed'
      AND provenance.integrity_status = 'valid'
      AND provenance.evidence_kind NOT IN (
          'model_output', 'controlled_prompt', 'controlled_output'
      )
      AND NOT EXISTS (
          SELECT 1 FROM controlled_resilience_evidence AS controlled
          WHERE controlled.raw_prompt_evidence_id = provenance.evidence_id
             OR controlled.raw_output_evidence_id = provenance.evidence_id
      )
)
BEGIN
    SELECT RAISE(ABORT, 'transfer test must be a claimed same-project anchor');
END;

CREATE TRIGGER failure_pattern_episode_guard
BEFORE INSERT ON failure_pattern_episodes
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
)
OR NOT EXISTS (
    SELECT 1
    FROM failure_patterns AS pattern
    JOIN records AS pattern_record ON pattern_record.record_id = pattern.record_id
    JOIN episodes AS episode ON episode.record_id = NEW.episode_id
    JOIN records AS episode_record ON episode_record.record_id = episode.record_id
    WHERE pattern.record_id = NEW.record_id
      AND pattern_record.project_scope_id = episode_record.project_scope_id
      AND episode_record.lifecycle_state NOT IN ('revoked', 'deleted')
      AND episode_record.integrity_status = 'valid'
      AND NOT EXISTS (
          SELECT 1
          FROM record_evidence_links AS link
          JOIN evidence_items AS evidence ON evidence.evidence_id = link.evidence_id
            WHERE link.record_id = episode.record_id
              AND (
                evidence.integrity_status <> 'valid'
                OR evidence.evidence_kind IN (
                    'controlled_prompt', 'controlled_output'
                )
                OR EXISTS (
                    SELECT 1 FROM controlled_resilience_evidence AS controlled
                    WHERE controlled.raw_prompt_evidence_id = evidence.evidence_id
                       OR controlled.raw_output_evidence_id = evidence.evidence_id
                )
            )
      )
)
BEGIN
    SELECT RAISE(ABORT, 'invalid or post-finalization failure-pattern episode');
END;

CREATE TRIGGER success_pattern_episode_guard
BEFORE INSERT ON success_pattern_episodes
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
)
OR NOT EXISTS (
    SELECT 1
    FROM success_patterns AS pattern
    JOIN records AS pattern_record ON pattern_record.record_id = pattern.record_id
    JOIN episodes AS episode ON episode.record_id = NEW.episode_id
    JOIN records AS episode_record ON episode_record.record_id = episode.record_id
    WHERE pattern.record_id = NEW.record_id
      AND pattern_record.project_scope_id = episode_record.project_scope_id
      AND episode.outcome = 'completed'
      AND episode_record.task_id IS NOT NULL
      AND episode_record.lifecycle_state NOT IN ('revoked', 'deleted')
      AND episode_record.integrity_status = 'valid'
      AND NOT EXISTS (
          SELECT 1
          FROM success_pattern_episodes AS existing
          JOIN records AS existing_episode
            ON existing_episode.record_id = existing.episode_id
          WHERE existing.record_id = pattern.record_id
            AND existing_episode.task_id = episode_record.task_id
      )
      AND NOT EXISTS (
          SELECT 1
          FROM record_evidence_links AS link
          JOIN evidence_items AS evidence ON evidence.evidence_id = link.evidence_id
            WHERE link.record_id = episode.record_id
              AND (
                evidence.integrity_status <> 'valid'
                OR evidence.evidence_kind IN (
                    'controlled_prompt', 'controlled_output'
                )
                OR EXISTS (
                    SELECT 1 FROM controlled_resilience_evidence AS controlled
                    WHERE controlled.raw_prompt_evidence_id = evidence.evidence_id
                       OR controlled.raw_output_evidence_id = evidence.evidence_id
                )
            )
      )
)
BEGIN
    SELECT RAISE(ABORT, 'success pattern requires distinct completed task episodes');
END;


CREATE TRIGGER developmental_evidence_link_insert_guard
BEFORE INSERT ON record_evidence_links
WHEN EXISTS (
    SELECT 1 FROM lesson_candidates
    WHERE record_id = NEW.record_id
    UNION ALL
    SELECT 1 FROM approved_lessons
    WHERE record_id = NEW.record_id
    UNION ALL
    SELECT 1 FROM failure_patterns
    WHERE record_id = NEW.record_id
    UNION ALL
    SELECT 1 FROM success_patterns
    WHERE record_id = NEW.record_id
)
AND (
    EXISTS (
        SELECT 1 FROM memory_record_lifecycle_transitions
        WHERE record_id = NEW.record_id
    )
    OR EXISTS (
        SELECT 1
        FROM evidence_items AS evidence
        WHERE evidence.evidence_id = NEW.evidence_id
          AND (
              evidence.integrity_status <> 'valid'
              OR evidence.evidence_kind IN (
                  'controlled_prompt', 'controlled_output'
              )
              OR EXISTS (
                  SELECT 1 FROM controlled_resilience_evidence AS controlled
                  WHERE controlled.raw_prompt_evidence_id = evidence.evidence_id
                     OR controlled.raw_output_evidence_id = evidence.evidence_id
              )
          )
    )
    OR NOT (
        (
            NEW.relationship = 'derived_from'
            AND EXISTS (
                SELECT 1
                FROM (
                    SELECT candidate.record_id, source.episode_id AS source_id
                    FROM lesson_candidates AS candidate
                    JOIN lesson_candidate_source_episodes AS source
                      ON source.record_id = candidate.record_id
                    UNION ALL
                    SELECT candidate.record_id, source.correction_id
                    FROM lesson_candidates AS candidate
                    JOIN lesson_candidate_source_corrections AS source
                      ON source.record_id = candidate.record_id
                    UNION ALL
                    SELECT approved.record_id, source.episode_id
                    FROM approved_lessons AS approved
                    JOIN approved_lesson_source_episodes AS source
                      ON source.record_id = approved.record_id
                    UNION ALL
                    SELECT approved.record_id, source.correction_id
                    FROM approved_lessons AS approved
                    JOIN approved_lesson_source_corrections AS source
                      ON source.record_id = approved.record_id
                    UNION ALL
                    SELECT pattern.record_id, source.episode_id
                    FROM failure_patterns AS pattern
                    JOIN failure_pattern_episodes AS source
                      ON source.record_id = pattern.record_id
                    UNION ALL
                    SELECT pattern.record_id, source.episode_id
                    FROM success_patterns AS pattern
                    JOIN success_pattern_episodes AS source
                      ON source.record_id = pattern.record_id
                ) AS lineage
                JOIN record_evidence_links AS source_link
                  ON source_link.record_id = lineage.source_id
                 AND source_link.evidence_id = NEW.evidence_id
                WHERE lineage.record_id = NEW.record_id
            )
        )
        OR (
            NEW.relationship = 'supports'
            AND EXISTS (
                SELECT 1
                FROM approved_lessons AS approved
                JOIN memory_approval_grants AS grant_record
                  ON grant_record.record_id = approved.record_id
                 AND grant_record.evidence_id = NEW.evidence_id
                 AND grant_record.target_status = 'approved'
                 AND grant_record.authority_class = 'nolan_byte_approved'
                WHERE approved.record_id = NEW.record_id
            )
        )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'developmental evidence link is late, invalid, or unsupported');
END;

CREATE TRIGGER developmental_evidence_link_update_guard
BEFORE UPDATE ON record_evidence_links
WHEN EXISTS (
    SELECT 1 FROM lesson_candidates
    WHERE record_id = OLD.record_id
    UNION ALL
    SELECT 1 FROM approved_lessons
    WHERE record_id = OLD.record_id
    UNION ALL
    SELECT 1 FROM failure_patterns
    WHERE record_id = OLD.record_id
    UNION ALL
    SELECT 1 FROM success_patterns
    WHERE record_id = OLD.record_id
)
BEGIN
    SELECT RAISE(ABORT, 'developmental evidence links are immutable');
END;

CREATE TRIGGER developmental_evidence_link_delete_guard
BEFORE DELETE ON record_evidence_links
WHEN EXISTS (
    SELECT 1 FROM lesson_candidates
    WHERE record_id = OLD.record_id
    UNION ALL
    SELECT 1 FROM approved_lessons
    WHERE record_id = OLD.record_id
    UNION ALL
    SELECT 1 FROM failure_patterns
    WHERE record_id = OLD.record_id
    UNION ALL
    SELECT 1 FROM success_patterns
    WHERE record_id = OLD.record_id
)
BEGIN
    SELECT RAISE(ABORT, 'developmental evidence links cannot be deleted');
END;


CREATE TRIGGER developmental_initial_finalization_guard
BEFORE INSERT ON memory_record_lifecycle_transitions
WHEN NEW.sequence_number = 0
AND EXISTS (
    SELECT 1 FROM lesson_candidates
    WHERE record_id = NEW.record_id
    UNION ALL
    SELECT 1 FROM approved_lessons
    WHERE record_id = NEW.record_id
    UNION ALL
    SELECT 1 FROM failure_patterns
    WHERE record_id = NEW.record_id
    UNION ALL
    SELECT 1 FROM success_patterns
    WHERE record_id = NEW.record_id
)
AND (
    NOT (
      (
        EXISTS (
            SELECT 1 FROM records
            WHERE record_id = NEW.record_id
              AND record_type = 'lesson_candidate'
              AND lifecycle_state = 'candidate'
              AND approval_status = 'pending'
              AND agent_write_policy = 'candidate_only'
        )
        AND EXISTS (
            SELECT 1 FROM lesson_candidates
            WHERE record_id = NEW.record_id
        )
        AND (SELECT COUNT(*) FROM lesson_candidate_source_episodes
             WHERE record_id = NEW.record_id) >= 1
        AND (SELECT MAX(source_order) FROM lesson_candidate_source_episodes
             WHERE record_id = NEW.record_id) =
            (SELECT COUNT(*) - 1 FROM lesson_candidate_source_episodes
             WHERE record_id = NEW.record_id)
        AND (
            (SELECT COUNT(*) FROM lesson_candidate_source_corrections
             WHERE record_id = NEW.record_id) = 0
            OR (SELECT MAX(source_order) FROM lesson_candidate_source_corrections
                WHERE record_id = NEW.record_id) =
               (SELECT COUNT(*) - 1 FROM lesson_candidate_source_corrections
                WHERE record_id = NEW.record_id)
        )
        AND (
            (SELECT COUNT(*) FROM lesson_candidate_limitations
             WHERE record_id = NEW.record_id) = 0
            OR (SELECT MAX(limitation_order) FROM lesson_candidate_limitations
                WHERE record_id = NEW.record_id) =
               (SELECT COUNT(*) - 1 FROM lesson_candidate_limitations
                WHERE record_id = NEW.record_id)
        )
    )
    OR (
        EXISTS (
            SELECT 1 FROM records
            WHERE record_id = NEW.record_id
              AND record_type = 'approved_lesson'
              AND lifecycle_state = 'reviewed'
              AND approval_status = 'pending'
              AND agent_write_policy = 'prohibited'
        )
        AND EXISTS (
            SELECT 1 FROM approved_lessons
            WHERE record_id = NEW.record_id
        )
        AND (SELECT COUNT(*) FROM approved_lesson_source_episodes
             WHERE record_id = NEW.record_id) >= 1
        AND (SELECT MAX(source_order) FROM approved_lesson_source_episodes
             WHERE record_id = NEW.record_id) =
            (SELECT COUNT(*) - 1 FROM approved_lesson_source_episodes
             WHERE record_id = NEW.record_id)
        AND (SELECT COUNT(*) FROM approved_lesson_source_corrections
             WHERE record_id = NEW.record_id) >= 1
        AND (SELECT MAX(source_order) FROM approved_lesson_source_corrections
             WHERE record_id = NEW.record_id) =
            (SELECT COUNT(*) - 1 FROM approved_lesson_source_corrections
             WHERE record_id = NEW.record_id)
        AND (SELECT COUNT(*) FROM approved_lesson_application_conditions
             WHERE record_id = NEW.record_id) >= 1
        AND (SELECT MAX(condition_order)
             FROM approved_lesson_application_conditions
             WHERE record_id = NEW.record_id) =
            (SELECT COUNT(*) - 1
             FROM approved_lesson_application_conditions
             WHERE record_id = NEW.record_id)
        AND (SELECT COUNT(*) FROM approved_lesson_non_application_conditions
             WHERE record_id = NEW.record_id) >= 1
        AND (SELECT MAX(condition_order)
             FROM approved_lesson_non_application_conditions
             WHERE record_id = NEW.record_id) =
            (SELECT COUNT(*) - 1
             FROM approved_lesson_non_application_conditions
             WHERE record_id = NEW.record_id)
        AND (SELECT COUNT(*) FROM approved_lesson_transfer_tests
             WHERE record_id = NEW.record_id) >= 1
        AND (SELECT MAX(transfer_order) FROM approved_lesson_transfer_tests
             WHERE record_id = NEW.record_id) =
            (SELECT COUNT(*) - 1 FROM approved_lesson_transfer_tests
             WHERE record_id = NEW.record_id)
    )
    OR (
        EXISTS (
            SELECT 1 FROM records
            WHERE record_id = NEW.record_id
              AND record_type = 'failure_pattern'
              AND lifecycle_state = 'candidate'
              AND approval_status = 'pending'
              AND agent_write_policy = 'candidate_only'
        )
        AND EXISTS (
            SELECT 1 FROM failure_patterns
            WHERE record_id = NEW.record_id
              AND frequency = (
                  SELECT COUNT(*) FROM failure_pattern_episodes
                  WHERE record_id = NEW.record_id
              )
        )
        AND (SELECT COUNT(*) FROM failure_pattern_episodes
             WHERE record_id = NEW.record_id) >= 2
        AND (SELECT MAX(episode_order) FROM failure_pattern_episodes
             WHERE record_id = NEW.record_id) =
            (SELECT COUNT(*) - 1 FROM failure_pattern_episodes
             WHERE record_id = NEW.record_id)
    )
    OR (
        EXISTS (
            SELECT 1 FROM records
            WHERE record_id = NEW.record_id
              AND record_type = 'success_pattern'
              AND lifecycle_state = 'candidate'
              AND approval_status = 'pending'
              AND agent_write_policy = 'candidate_only'
        )
        AND EXISTS (
            SELECT 1 FROM success_patterns
            WHERE record_id = NEW.record_id
        )
        AND (SELECT COUNT(*) FROM success_pattern_episodes
             WHERE record_id = NEW.record_id) >= 2
        AND (SELECT MAX(episode_order) FROM success_pattern_episodes
             WHERE record_id = NEW.record_id) =
            (SELECT COUNT(*) - 1 FROM success_pattern_episodes
             WHERE record_id = NEW.record_id)
        AND (SELECT COUNT(*) FROM success_pattern_transfer_scopes
             WHERE record_id = NEW.record_id) >= 1
        AND (SELECT MAX(scope_order) FROM success_pattern_transfer_scopes
             WHERE record_id = NEW.record_id) =
            (SELECT COUNT(*) - 1 FROM success_pattern_transfer_scopes
             WHERE record_id = NEW.record_id)
      )
    )
    OR EXISTS (
        SELECT source_link.evidence_id
        FROM (
            SELECT candidate.record_id, source.episode_id AS source_id
            FROM lesson_candidates AS candidate
            JOIN lesson_candidate_source_episodes AS source
              ON source.record_id = candidate.record_id
            UNION ALL
            SELECT candidate.record_id, source.correction_id
            FROM lesson_candidates AS candidate
            JOIN lesson_candidate_source_corrections AS source
              ON source.record_id = candidate.record_id
            UNION ALL
            SELECT approved.record_id, source.episode_id
            FROM approved_lessons AS approved
            JOIN approved_lesson_source_episodes AS source
              ON source.record_id = approved.record_id
            UNION ALL
            SELECT approved.record_id, source.correction_id
            FROM approved_lessons AS approved
            JOIN approved_lesson_source_corrections AS source
              ON source.record_id = approved.record_id
            UNION ALL
            SELECT pattern.record_id, source.episode_id
            FROM failure_patterns AS pattern
            JOIN failure_pattern_episodes AS source
              ON source.record_id = pattern.record_id
            UNION ALL
            SELECT pattern.record_id, source.episode_id
            FROM success_patterns AS pattern
            JOIN success_pattern_episodes AS source
              ON source.record_id = pattern.record_id
        ) AS lineage
        JOIN record_evidence_links AS source_link
          ON source_link.record_id = lineage.source_id
        WHERE lineage.record_id = NEW.record_id
        EXCEPT
        SELECT target_link.evidence_id
        FROM record_evidence_links AS target_link
        WHERE target_link.record_id = NEW.record_id
          AND target_link.relationship = 'derived_from'
    )
    OR EXISTS (
        SELECT target_link.evidence_id
        FROM record_evidence_links AS target_link
        WHERE target_link.record_id = NEW.record_id
          AND target_link.relationship = 'derived_from'
        EXCEPT
        SELECT source_link.evidence_id
        FROM (
            SELECT candidate.record_id, source.episode_id AS source_id
            FROM lesson_candidates AS candidate
            JOIN lesson_candidate_source_episodes AS source
              ON source.record_id = candidate.record_id
            UNION ALL
            SELECT candidate.record_id, source.correction_id
            FROM lesson_candidates AS candidate
            JOIN lesson_candidate_source_corrections AS source
              ON source.record_id = candidate.record_id
            UNION ALL
            SELECT approved.record_id, source.episode_id
            FROM approved_lessons AS approved
            JOIN approved_lesson_source_episodes AS source
              ON source.record_id = approved.record_id
            UNION ALL
            SELECT approved.record_id, source.correction_id
            FROM approved_lessons AS approved
            JOIN approved_lesson_source_corrections AS source
              ON source.record_id = approved.record_id
            UNION ALL
            SELECT pattern.record_id, source.episode_id
            FROM failure_patterns AS pattern
            JOIN failure_pattern_episodes AS source
              ON source.record_id = pattern.record_id
            UNION ALL
            SELECT pattern.record_id, source.episode_id
            FROM success_patterns AS pattern
            JOIN success_pattern_episodes AS source
              ON source.record_id = pattern.record_id
        ) AS lineage
        JOIN record_evidence_links AS source_link
          ON source_link.record_id = lineage.source_id
        WHERE lineage.record_id = NEW.record_id
    )
    OR (
        EXISTS (
            SELECT 1 FROM approved_lessons
            WHERE record_id = NEW.record_id
        )
        AND (
            (SELECT COUNT(*)
             FROM record_evidence_links
             WHERE record_id = NEW.record_id
               AND relationship = 'supports') <> 1
            OR (
                SELECT COUNT(*)
                FROM memory_approval_grants AS grant_record
                JOIN records AS approved_record
                  ON approved_record.record_id = grant_record.record_id
                WHERE grant_record.record_id = NEW.record_id
                  AND grant_record.target_status = 'approved'
                  AND grant_record.authority_class = 'nolan_byte_approved'
                  AND grant_record.project_scope_id =
                      approved_record.project_scope_id
            ) <> 1
            OR NOT EXISTS (
                SELECT 1
                FROM record_evidence_links AS support_link
                JOIN memory_approval_grants AS grant_record
                  ON grant_record.record_id = support_link.record_id
                 AND grant_record.evidence_id = support_link.evidence_id
                 AND grant_record.target_status = 'approved'
                 AND grant_record.authority_class = 'nolan_byte_approved'
                JOIN records AS approved_record
                  ON approved_record.record_id = grant_record.record_id
                 AND approved_record.project_scope_id =
                     grant_record.project_scope_id
                JOIN evidence_items AS support_evidence
                  ON support_evidence.evidence_id = support_link.evidence_id
                WHERE support_link.record_id = NEW.record_id
                  AND support_link.relationship = 'supports'
                  AND support_evidence.integrity_status = 'valid'
                  AND support_evidence.evidence_kind NOT IN (
                      'controlled_prompt', 'controlled_output'
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM controlled_resilience_evidence AS controlled
                      WHERE controlled.raw_prompt_evidence_id =
                            support_evidence.evidence_id
                         OR controlled.raw_output_evidence_id =
                            support_evidence.evidence_id
                  )
            )
            OR EXISTS (
                SELECT 1
                FROM record_evidence_links
                WHERE record_id = NEW.record_id
                  AND relationship NOT IN ('derived_from', 'supports')
            )
        )
    )
    OR (
        NOT EXISTS (
            SELECT 1 FROM approved_lessons
            WHERE record_id = NEW.record_id
        )
        AND EXISTS (
            SELECT 1
            FROM record_evidence_links
            WHERE record_id = NEW.record_id
              AND relationship <> 'derived_from'
        )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'developmental record is incomplete at finalization');
END;


CREATE TRIGGER approved_as_exact_endpoints_guard
BEFORE INSERT ON record_relationships
WHEN NEW.relationship_type = 'approved_as'
AND (
    EXISTS (
        SELECT 1 FROM lesson_candidates
        WHERE record_id IN (NEW.source_record_id, NEW.target_record_id)
    )
    OR EXISTS (
        SELECT 1 FROM approved_lessons
        WHERE record_id IN (NEW.source_record_id, NEW.target_record_id)
    )
    OR EXISTS (
        SELECT 1 FROM failure_patterns
        WHERE record_id IN (NEW.source_record_id, NEW.target_record_id)
    )
    OR EXISTS (
        SELECT 1 FROM success_patterns
        WHERE record_id IN (NEW.source_record_id, NEW.target_record_id)
    )
)
AND NOT EXISTS (
    SELECT 1
    FROM approved_lessons AS approved
    JOIN records AS source ON source.record_id = NEW.source_record_id
    JOIN records AS target ON target.record_id = NEW.target_record_id
    WHERE approved.record_id = NEW.target_record_id
      AND approved.candidate_record_id = NEW.source_record_id
      AND source.record_family = 'episodic_memory'
      AND source.record_type = 'lesson_candidate'
      AND target.record_family = 'episodic_memory'
      AND target.record_type = 'approved_lesson'
      AND source.project_scope_id = target.project_scope_id
)
BEGIN
    SELECT RAISE(ABORT, 'approved_as must point from exact candidate to lesson');
END;

CREATE TRIGGER approved_as_retarget_guard
BEFORE UPDATE ON record_relationships
WHEN OLD.relationship_type = 'approved_as'
AND EXISTS (
    SELECT 1 FROM approved_lessons
    WHERE record_id = OLD.target_record_id
)
BEGIN
    SELECT RAISE(ABORT, 'approved_as relationship cannot be retargeted');
END;

CREATE TRIGGER approved_as_delete_guard
BEFORE DELETE ON record_relationships
WHEN OLD.relationship_type = 'approved_as'
AND EXISTS (
    SELECT 1 FROM approved_lessons
    WHERE record_id = OLD.target_record_id
)
BEGIN
    SELECT RAISE(ABORT, 'approved_as relationship cannot be deleted');
END;


CREATE TRIGGER approved_lesson_activation_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN OLD.record_family = 'episodic_memory'
AND OLD.record_type = 'approved_lesson'
AND EXISTS (
    SELECT 1 FROM approved_lessons
    WHERE record_id = OLD.record_id
)
AND NEW.lifecycle_state = 'active'
AND OLD.lifecycle_state <> 'active'
AND NOT EXISTS (
    SELECT 1
    FROM approved_lessons AS approved
    JOIN records AS candidate
      ON candidate.record_id = approved.candidate_record_id
    JOIN record_relationships AS relationship
      ON relationship.source_record_id = approved.candidate_record_id
     AND relationship.target_record_id = approved.record_id
     AND relationship.relationship_type = 'approved_as'
    JOIN memory_relationship_grants AS relationship_grant
      ON relationship_grant.grant_id = relationship.relationship_grant_id
     AND relationship_grant.relationship_id = relationship.relationship_id
     AND relationship_grant.authority_class = 'nolan_byte_approved'
     AND (
         relationship_grant.single_use = 0
         OR (
             relationship_grant.consumed_at IS NOT NULL
             AND relationship_grant.consumed_by_relationship_id =
                 relationship.relationship_id
         )
     )
    JOIN memory_record_approval_transitions AS approval_transition
      ON approval_transition.record_id = approved.record_id
     AND approval_transition.to_status = 'approved'
    JOIN memory_approval_grants AS approval_grant
      ON approval_grant.grant_id = approval_transition.approval_grant_id
     AND approval_grant.record_id = approved.record_id
     AND approval_grant.target_status = 'approved'
     AND approval_grant.authority_class = 'nolan_byte_approved'
     AND approval_grant.project_scope_id = NEW.project_scope_id
     AND approval_grant.authority_record_id =
         relationship_grant.authority_record_id
     AND approval_grant.approved_by_entity_id =
         relationship_grant.approved_by_entity_id
     AND approval_grant.evidence_id = relationship_grant.evidence_id
     AND (
         approval_grant.single_use = 0
         OR (
             approval_grant.consumed_at IS NOT NULL
             AND approval_grant.consumed_by_transition_id =
              approval_transition.transition_id
          )
      )
    JOIN record_evidence_links AS approval_support
      ON approval_support.record_id = approved.record_id
     AND approval_support.evidence_id = approval_grant.evidence_id
     AND approval_support.relationship = 'supports'
    JOIN evidence_items AS approval_evidence
      ON approval_evidence.evidence_id = approval_support.evidence_id
    LEFT JOIN controlled_resilience_evidence AS controlled_approval
      ON controlled_approval.raw_prompt_evidence_id =
         approval_evidence.evidence_id
      OR controlled_approval.raw_output_evidence_id =
         approval_evidence.evidence_id
    WHERE approved.record_id = OLD.record_id
      AND NEW.approval_status = 'approved'
      AND NEW.integrity_status = 'valid'
      AND approval_evidence.integrity_status = 'valid'
      AND approval_evidence.evidence_kind NOT IN (
          'controlled_prompt', 'controlled_output'
      )
      AND controlled_approval.record_id IS NULL
      AND (
          SELECT COUNT(*)
          FROM record_evidence_links AS support_count
          WHERE support_count.record_id = approved.record_id
            AND support_count.relationship = 'supports'
      ) = 1
      AND candidate.record_family = 'episodic_memory'
      AND candidate.record_type = 'lesson_candidate'
      AND candidate.lifecycle_state = 'reviewed'
      AND candidate.approval_status = 'pending'
      AND candidate.integrity_status = 'valid'
      AND candidate.project_scope_id = NEW.project_scope_id
      AND NOT EXISTS (
          SELECT 1
           FROM approved_lesson_transfer_tests AS transfer
           LEFT JOIN governed_evaluation_record_anchors AS evaluation
             ON evaluation.evaluation_record_id = transfer.evaluation_record_id
           LEFT JOIN evidence_items AS provenance
             ON provenance.evidence_id = evaluation.provenance_evidence_id
           LEFT JOIN controlled_resilience_evidence AS controlled_provenance
             ON controlled_provenance.raw_prompt_evidence_id =
                provenance.evidence_id
             OR controlled_provenance.raw_output_evidence_id =
                provenance.evidence_id
           WHERE transfer.record_id = approved.record_id
             AND (
                 evaluation.evaluation_record_id IS NULL
                 OR evaluation.evaluation_kind <> 'capability_evaluation'
                 OR evaluation.project_scope_id <> NEW.project_scope_id
                 OR evaluation.current_state <> 'claimed'
                 OR provenance.evidence_id IS NULL
                 OR provenance.integrity_status <> 'valid'
                 OR provenance.evidence_kind IN (
                     'model_output', 'controlled_prompt', 'controlled_output'
                 )
                 OR controlled_provenance.record_id IS NOT NULL
             )
      )
      AND EXISTS (
          SELECT 1 FROM approved_lesson_transfer_tests
          WHERE record_id = approved.record_id
      )
      AND EXISTS (
          SELECT 1 FROM record_evidence_links
          WHERE record_id = approved.record_id
      )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'approved lesson activation requires exact approval and relationship'
    );
END;


CREATE TRIGGER developmental_records_identity_guard
BEFORE UPDATE OF record_family, record_type, schema_version,
                 construct_scope_id, project_scope_id, subject_entity_id,
                 session_id, task_id, authority_class, certainty_class,
                 sensitivity_class, privacy_class, retention_class,
                 training_eligibility, created_at, created_by_entity_id,
                 created_by_runtime_id, effective_from, effective_until,
                 review_due_at, supersedes_record_id, superseded_by_record_id,
                 previous_version_id, source_kind, provenance_summary,
                 retrieval_policy_json, deletion_policy_json,
                 agent_write_policy, content_hash
ON records
WHEN EXISTS (
    SELECT 1 FROM lesson_candidates
    WHERE record_id = OLD.record_id
    UNION ALL
    SELECT 1 FROM approved_lessons
    WHERE record_id = OLD.record_id
    UNION ALL
    SELECT 1 FROM failure_patterns
    WHERE record_id = OLD.record_id
    UNION ALL
    SELECT 1 FROM success_patterns
    WHERE record_id = OLD.record_id
)
BEGIN
    SELECT RAISE(ABORT, 'developmental record identity and content are immutable');
END;

CREATE TRIGGER lesson_candidates_immutable
BEFORE UPDATE ON lesson_candidates
BEGIN
    SELECT RAISE(ABORT, 'lesson candidate payload is immutable');
END;

CREATE TRIGGER lesson_candidates_no_delete
BEFORE DELETE ON lesson_candidates
BEGIN
    SELECT RAISE(ABORT, 'lesson candidate payload cannot be deleted');
END;

CREATE TRIGGER approved_lessons_immutable
BEFORE UPDATE ON approved_lessons
BEGIN
    SELECT RAISE(ABORT, 'approved lesson payload is immutable');
END;

CREATE TRIGGER approved_lessons_no_delete
BEFORE DELETE ON approved_lessons
BEGIN
    SELECT RAISE(ABORT, 'approved lesson payload cannot be deleted');
END;

CREATE TRIGGER failure_patterns_immutable
BEFORE UPDATE ON failure_patterns
BEGIN
    SELECT RAISE(ABORT, 'failure pattern payload is immutable');
END;

CREATE TRIGGER failure_patterns_no_delete
BEFORE DELETE ON failure_patterns
BEGIN
    SELECT RAISE(ABORT, 'failure pattern payload cannot be deleted');
END;

CREATE TRIGGER success_patterns_immutable
BEFORE UPDATE ON success_patterns
BEGIN
    SELECT RAISE(ABORT, 'success pattern payload is immutable');
END;

CREATE TRIGGER success_patterns_no_delete
BEFORE DELETE ON success_patterns
BEGIN
    SELECT RAISE(ABORT, 'success pattern payload cannot be deleted');
END;


CREATE TRIGGER lesson_candidate_source_episodes_immutable
BEFORE UPDATE ON lesson_candidate_source_episodes
BEGIN
    SELECT RAISE(ABORT, 'candidate episode lineage is immutable');
END;

CREATE TRIGGER lesson_candidate_source_episodes_no_delete
BEFORE DELETE ON lesson_candidate_source_episodes
BEGIN
    SELECT RAISE(ABORT, 'candidate episode lineage cannot be deleted');
END;

CREATE TRIGGER lesson_candidate_source_corrections_immutable
BEFORE UPDATE ON lesson_candidate_source_corrections
BEGIN
    SELECT RAISE(ABORT, 'candidate correction lineage is immutable');
END;

CREATE TRIGGER lesson_candidate_source_corrections_no_delete
BEFORE DELETE ON lesson_candidate_source_corrections
BEGIN
    SELECT RAISE(ABORT, 'candidate correction lineage cannot be deleted');
END;

CREATE TRIGGER lesson_candidate_limitations_append_guard
BEFORE INSERT ON lesson_candidate_limitations
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
)
BEGIN
    SELECT RAISE(ABORT, 'candidate limitations are finalized');
END;

CREATE TRIGGER lesson_candidate_limitations_immutable
BEFORE UPDATE ON lesson_candidate_limitations
BEGIN
    SELECT RAISE(ABORT, 'candidate limitations are immutable');
END;

CREATE TRIGGER lesson_candidate_limitations_no_delete
BEFORE DELETE ON lesson_candidate_limitations
BEGIN
    SELECT RAISE(ABORT, 'candidate limitations cannot be deleted');
END;

CREATE TRIGGER approved_lesson_source_episodes_immutable
BEFORE UPDATE ON approved_lesson_source_episodes
BEGIN
    SELECT RAISE(ABORT, 'approved lesson episode lineage is immutable');
END;

CREATE TRIGGER approved_lesson_source_episodes_no_delete
BEFORE DELETE ON approved_lesson_source_episodes
BEGIN
    SELECT RAISE(ABORT, 'approved lesson episode lineage cannot be deleted');
END;

CREATE TRIGGER approved_lesson_source_corrections_immutable
BEFORE UPDATE ON approved_lesson_source_corrections
BEGIN
    SELECT RAISE(ABORT, 'approved lesson correction lineage is immutable');
END;

CREATE TRIGGER approved_lesson_source_corrections_no_delete
BEFORE DELETE ON approved_lesson_source_corrections
BEGIN
    SELECT RAISE(ABORT, 'approved lesson correction lineage cannot be deleted');
END;

CREATE TRIGGER approved_lesson_application_conditions_append_guard
BEFORE INSERT ON approved_lesson_application_conditions
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
)
BEGIN
    SELECT RAISE(ABORT, 'approved lesson application conditions are finalized');
END;

CREATE TRIGGER approved_lesson_application_conditions_immutable
BEFORE UPDATE ON approved_lesson_application_conditions
BEGIN
    SELECT RAISE(ABORT, 'approved lesson application conditions are immutable');
END;

CREATE TRIGGER approved_lesson_application_conditions_no_delete
BEFORE DELETE ON approved_lesson_application_conditions
BEGIN
    SELECT RAISE(ABORT, 'approved lesson application conditions cannot be deleted');
END;

CREATE TRIGGER approved_lesson_non_application_conditions_append_guard
BEFORE INSERT ON approved_lesson_non_application_conditions
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
)
BEGIN
    SELECT RAISE(ABORT, 'approved lesson non-application conditions are finalized');
END;

CREATE TRIGGER approved_lesson_non_application_conditions_immutable
BEFORE UPDATE ON approved_lesson_non_application_conditions
BEGIN
    SELECT RAISE(ABORT, 'approved lesson non-application conditions are immutable');
END;

CREATE TRIGGER approved_lesson_non_application_conditions_no_delete
BEFORE DELETE ON approved_lesson_non_application_conditions
BEGIN
    SELECT RAISE(ABORT, 'approved lesson non-application conditions cannot be deleted');
END;

CREATE TRIGGER approved_lesson_transfer_tests_immutable
BEFORE UPDATE ON approved_lesson_transfer_tests
BEGIN
    SELECT RAISE(ABORT, 'approved lesson transfer tests are immutable');
END;

CREATE TRIGGER approved_lesson_transfer_tests_no_delete
BEFORE DELETE ON approved_lesson_transfer_tests
BEGIN
    SELECT RAISE(ABORT, 'approved lesson transfer tests cannot be deleted');
END;

CREATE TRIGGER failure_pattern_episodes_immutable
BEFORE UPDATE ON failure_pattern_episodes
BEGIN
    SELECT RAISE(ABORT, 'failure pattern episode lineage is immutable');
END;

CREATE TRIGGER failure_pattern_episodes_no_delete
BEFORE DELETE ON failure_pattern_episodes
BEGIN
    SELECT RAISE(ABORT, 'failure pattern episode lineage cannot be deleted');
END;

CREATE TRIGGER success_pattern_episodes_immutable
BEFORE UPDATE ON success_pattern_episodes
BEGIN
    SELECT RAISE(ABORT, 'success pattern episode lineage is immutable');
END;

CREATE TRIGGER success_pattern_episodes_no_delete
BEFORE DELETE ON success_pattern_episodes
BEGIN
    SELECT RAISE(ABORT, 'success pattern episode lineage cannot be deleted');
END;

CREATE TRIGGER success_pattern_transfer_scopes_append_guard
BEFORE INSERT ON success_pattern_transfer_scopes
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
)
BEGIN
    SELECT RAISE(ABORT, 'success pattern transfer scopes are finalized');
END;

CREATE TRIGGER success_pattern_transfer_scopes_immutable
BEFORE UPDATE ON success_pattern_transfer_scopes
BEGIN
    SELECT RAISE(ABORT, 'success pattern transfer scopes are immutable');
END;

CREATE TRIGGER success_pattern_transfer_scopes_no_delete
BEFORE DELETE ON success_pattern_transfer_scopes
BEGIN
    SELECT RAISE(ABORT, 'success pattern transfer scopes cannot be deleted');
END;
