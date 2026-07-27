CREATE TABLE episodes (
    record_id TEXT PRIMARY KEY,
    episode_kind TEXT NOT NULL CHECK (
        episode_kind IN (
            'task', 'conversation', 'evaluation',
            'failure', 'correction', 'experiment'
        )
    ),
    summary TEXT NOT NULL CHECK (trim(summary) <> ''),
    outcome TEXT NOT NULL CHECK (
        outcome IN ('completed', 'partial', 'failed', 'stopped', 'rejected')
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT
);

CREATE TABLE episode_input_evidence (
    record_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    evidence_order INTEGER NOT NULL CHECK (evidence_order >= 0),
    PRIMARY KEY (record_id, evidence_id),
    UNIQUE (record_id, evidence_order),
    FOREIGN KEY (record_id) REFERENCES episodes(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT
);

CREATE TABLE episode_output_evidence (
    record_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    evidence_order INTEGER NOT NULL CHECK (evidence_order >= 0),
    PRIMARY KEY (record_id, evidence_id),
    UNIQUE (record_id, evidence_order),
    FOREIGN KEY (record_id) REFERENCES episodes(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT
);

CREATE TABLE episode_evaluation_anchors (
    record_id TEXT NOT NULL,
    evaluation_record_id TEXT NOT NULL,
    evaluation_order INTEGER NOT NULL CHECK (evaluation_order >= 0),
    PRIMARY KEY (record_id, evaluation_record_id),
    UNIQUE (record_id, evaluation_order),
    FOREIGN KEY (record_id) REFERENCES episodes(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (evaluation_record_id)
        REFERENCES governed_evaluation_record_anchors(evaluation_record_id)
        ON DELETE RESTRICT
);

CREATE TABLE corrections (
    record_id TEXT PRIMARY KEY,
    target_episode_id TEXT NOT NULL,
    target_output_evidence_id TEXT NOT NULL,
    problem_statement TEXT NOT NULL CHECK (trim(problem_statement) <> ''),
    corrected_interpretation TEXT NOT NULL CHECK (
        trim(corrected_interpretation) <> ''
    ),
    correction_category TEXT NOT NULL CHECK (trim(correction_category) <> ''),
    issued_by_entity_id TEXT NOT NULL,
    issuer_class TEXT NOT NULL CHECK (
        issuer_class IN ('nolan', 'byte', 'nolan_byte', 'approved_evaluator')
    ),
    severity TEXT NOT NULL CHECK (
        severity IN ('minor', 'material', 'critical')
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (target_episode_id)
        REFERENCES episodes(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (target_output_evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT,
    FOREIGN KEY (issued_by_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT
);

CREATE TABLE correction_supporting_evidence (
    record_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    evidence_order INTEGER NOT NULL CHECK (evidence_order >= 0),
    PRIMARY KEY (record_id, evidence_id),
    UNIQUE (record_id, evidence_order),
    FOREIGN KEY (record_id) REFERENCES corrections(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT
);

CREATE INDEX episode_input_evidence_item
ON episode_input_evidence(evidence_id);

CREATE INDEX episode_output_evidence_item
ON episode_output_evidence(evidence_id);

CREATE INDEX episode_evaluation_anchor
ON episode_evaluation_anchors(evaluation_record_id);

CREATE INDEX corrections_target
ON corrections(target_episode_id, target_output_evidence_id);

CREATE INDEX corrections_issuer
ON corrections(issued_by_entity_id, issuer_class);

CREATE INDEX correction_supporting_evidence_item
ON correction_supporting_evidence(evidence_id);

CREATE TRIGGER episodes_insert_guard
BEFORE INSERT ON episodes
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS record
    JOIN sessions AS session ON session.session_id = record.session_id
    LEFT JOIN tasks AS task ON task.task_id = record.task_id
    WHERE record.record_id = NEW.record_id
      AND record.record_family = 'episodic_memory'
      AND record.record_type = 'episode'
      AND record.project_scope_id IS NOT NULL
      AND record.session_id IS NOT NULL
      AND record.lifecycle_state = 'observed'
      AND record.approval_status = 'pending'
      AND record.agent_write_policy = 'prohibited'
      AND record.integrity_status = 'valid'
      AND record.sensitivity_class IN ('public', 'internal')
      AND record.privacy_class = 'none'
      AND record.training_eligibility <> 'approved'
      AND session.active_project_scope = record.project_scope_id
      AND (
          (
              record.task_id IS NOT NULL
              AND task.session_id = record.session_id
              AND task.project_scope_id = record.project_scope_id
              AND task.status IN ('completed', 'stopped', 'failed')
              AND task.completed_at IS NOT NULL
              AND record.created_at >= task.completed_at
              AND (
                  record.effective_from IS NULL
                  OR record.effective_from >= task.completed_at
              )
              AND (
                  (NEW.outcome = 'completed' AND task.status = 'completed')
                  OR (NEW.outcome = 'failed' AND task.status = 'failed')
                  OR (NEW.outcome = 'stopped' AND task.status = 'stopped')
                  OR (
                      NEW.outcome = 'partial'
                      AND task.status IN ('stopped', 'failed')
                  )
                  OR (
                      NEW.outcome = 'rejected'
                      AND task.status = 'stopped'
                      AND EXISTS (
                          SELECT 1 FROM task_stop_events AS stop
                          WHERE stop.task_id = task.task_id
                            AND stop.governance_forced_stop = 1
                      )
                  )
              )
          )
          OR
          (
              record.task_id IS NULL
              AND session.session_status IN ('closed', 'aborted')
              AND session.closed_at IS NOT NULL
              AND record.created_at >= session.closed_at
              AND (
                  record.effective_from IS NULL
                  OR record.effective_from >= session.closed_at
              )
              AND (
                  (NEW.outcome = 'completed' AND session.session_status = 'closed')
                  OR (
                      NEW.outcome IN ('stopped', 'partial')
                      AND session.session_status = 'aborted'
                  )
              )
          )
      )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'episode requires exact terminal same-project occurrence proof'
    );
END;

CREATE TRIGGER corrections_insert_guard
BEFORE INSERT ON corrections
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS correction_record
    JOIN records AS episode_record
      ON episode_record.record_id = NEW.target_episode_id
    JOIN episodes AS episode ON episode.record_id = episode_record.record_id
    JOIN episode_output_evidence AS output
      ON output.record_id = episode.record_id
     AND output.evidence_id = NEW.target_output_evidence_id
    JOIN evidence_items AS target_evidence
      ON target_evidence.evidence_id = output.evidence_id
    JOIN entities AS issuer ON issuer.entity_id = NEW.issued_by_entity_id
    WHERE correction_record.record_id = NEW.record_id
      AND correction_record.record_family = 'episodic_memory'
      AND correction_record.record_type = 'correction'
      AND correction_record.project_scope_id IS NOT NULL
      AND correction_record.lifecycle_state = 'reviewed'
      AND correction_record.approval_status = 'pending'
      AND correction_record.agent_write_policy = 'prohibited'
      AND correction_record.integrity_status = 'valid'
      AND correction_record.sensitivity_class IN ('public', 'internal')
      AND correction_record.privacy_class = 'none'
      AND correction_record.training_eligibility <> 'approved'
      AND episode_record.record_family = 'episodic_memory'
      AND episode_record.record_type = 'episode'
      AND episode_record.project_scope_id = correction_record.project_scope_id
      AND episode_record.lifecycle_state NOT IN ('revoked', 'deleted')
      AND target_evidence.integrity_status = 'valid'
      AND issuer.status = 'active'
      AND NEW.issuer_class <> 'approved_evaluator'
)
BEGIN
    SELECT RAISE(
        ABORT,
        'correction requires an active issuer and exact same-project episode output'
    );
END;

CREATE TRIGGER episode_input_evidence_insert_guard
BEFORE INSERT ON episode_input_evidence
WHEN NEW.evidence_order <> (
    SELECT COUNT(*) FROM episode_input_evidence WHERE record_id = NEW.record_id
)
OR EXISTS (
    SELECT 1 FROM episode_output_evidence
    WHERE record_id = NEW.record_id AND evidence_id = NEW.evidence_id
)
OR NOT EXISTS (
    SELECT 1
    FROM evidence_items AS evidence
    JOIN records AS record ON record.record_id = NEW.record_id
    WHERE evidence.evidence_id = NEW.evidence_id
      AND evidence.integrity_status = 'valid'
      AND evidence.evidence_kind NOT IN (
          'controlled_prompt', 'controlled_output'
      )
      AND evidence.sensitivity_class = record.sensitivity_class
      AND evidence.privacy_class = record.privacy_class
)
OR EXISTS (
    SELECT 1
    FROM record_evidence_links AS link
    JOIN records AS linked_record ON linked_record.record_id = link.record_id
    JOIN records AS episode_record ON episode_record.record_id = NEW.record_id
    WHERE link.evidence_id = NEW.evidence_id
      AND linked_record.project_scope_id IS NOT NULL
      AND linked_record.project_scope_id <> episode_record.project_scope_id
)
OR EXISTS (
    SELECT 1 FROM controlled_resilience_evidence
    WHERE raw_prompt_evidence_id = NEW.evidence_id
       OR raw_output_evidence_id = NEW.evidence_id
)
BEGIN
    SELECT RAISE(
        ABORT,
        'episode input evidence violates order, boundary, integrity, or isolation'
    );
END;

CREATE TRIGGER episode_output_evidence_insert_guard
BEFORE INSERT ON episode_output_evidence
WHEN NEW.evidence_order <> (
    SELECT COUNT(*) FROM episode_output_evidence WHERE record_id = NEW.record_id
)
OR EXISTS (
    SELECT 1 FROM episode_input_evidence
    WHERE record_id = NEW.record_id AND evidence_id = NEW.evidence_id
)
OR NOT EXISTS (
    SELECT 1
    FROM evidence_items AS evidence
    JOIN records AS record ON record.record_id = NEW.record_id
    WHERE evidence.evidence_id = NEW.evidence_id
      AND evidence.integrity_status = 'valid'
      AND evidence.evidence_kind NOT IN (
          'controlled_prompt', 'controlled_output'
      )
      AND evidence.sensitivity_class = record.sensitivity_class
      AND evidence.privacy_class = record.privacy_class
)
OR EXISTS (
    SELECT 1
    FROM record_evidence_links AS link
    JOIN records AS linked_record ON linked_record.record_id = link.record_id
    JOIN records AS episode_record ON episode_record.record_id = NEW.record_id
    WHERE link.evidence_id = NEW.evidence_id
      AND linked_record.project_scope_id IS NOT NULL
      AND linked_record.project_scope_id <> episode_record.project_scope_id
)
OR EXISTS (
    SELECT 1 FROM controlled_resilience_evidence
    WHERE raw_prompt_evidence_id = NEW.evidence_id
       OR raw_output_evidence_id = NEW.evidence_id
)
BEGIN
    SELECT RAISE(
        ABORT,
        'episode output evidence violates order, boundary, integrity, or isolation'
    );
END;

CREATE TRIGGER episode_evaluation_anchors_insert_guard
BEFORE INSERT ON episode_evaluation_anchors
WHEN NEW.evaluation_order <> (
    SELECT COUNT(*) FROM episode_evaluation_anchors
    WHERE record_id = NEW.record_id
)
OR NOT EXISTS (
    SELECT 1
    FROM governed_evaluation_record_anchors AS anchor
    JOIN records AS record ON record.record_id = NEW.record_id
    WHERE anchor.evaluation_record_id = NEW.evaluation_record_id
      AND anchor.project_scope_id = record.project_scope_id
      AND anchor.current_state = 'claimed'
)
BEGIN
    SELECT RAISE(
        ABORT,
        'episode evaluation anchor must be ordered, claimed, and same-project'
    );
END;

CREATE TRIGGER correction_supporting_evidence_insert_guard
BEFORE INSERT ON correction_supporting_evidence
WHEN NEW.evidence_order <> (
    SELECT COUNT(*) FROM correction_supporting_evidence
    WHERE record_id = NEW.record_id
)
OR NEW.evidence_id = (
    SELECT target_output_evidence_id
    FROM corrections WHERE record_id = NEW.record_id
)
OR NOT EXISTS (
    SELECT 1
    FROM evidence_items AS evidence
    JOIN records AS record ON record.record_id = NEW.record_id
    WHERE evidence.evidence_id = NEW.evidence_id
      AND evidence.integrity_status = 'valid'
      AND evidence.evidence_kind NOT IN (
          'controlled_prompt', 'controlled_output'
      )
      AND evidence.sensitivity_class = record.sensitivity_class
      AND evidence.privacy_class = record.privacy_class
)
OR EXISTS (
    SELECT 1
    FROM record_evidence_links AS link
    JOIN records AS linked_record ON linked_record.record_id = link.record_id
    JOIN records AS correction_record
      ON correction_record.record_id = NEW.record_id
    WHERE link.evidence_id = NEW.evidence_id
      AND linked_record.project_scope_id IS NOT NULL
      AND linked_record.project_scope_id <> correction_record.project_scope_id
)
OR EXISTS (
    SELECT 1 FROM controlled_resilience_evidence
    WHERE raw_prompt_evidence_id = NEW.evidence_id
       OR raw_output_evidence_id = NEW.evidence_id
)
BEGIN
    SELECT RAISE(
        ABORT,
        'correction support violates order, separation, boundary, or isolation'
    );
END;

CREATE TRIGGER c2_record_evidence_link_insert_guard
BEFORE INSERT ON record_evidence_links
WHEN EXISTS (
    SELECT 1 FROM records
    WHERE record_id = NEW.record_id
      AND record_family = 'episodic_memory'
      AND record_type IN ('episode', 'correction')
)
AND NOT (
    (
        NEW.relationship = 'derived_from'
        AND (
            EXISTS (
                SELECT 1 FROM episode_input_evidence
                WHERE record_id = NEW.record_id
                  AND evidence_id = NEW.evidence_id
            )
            OR EXISTS (
                SELECT 1 FROM corrections
                WHERE record_id = NEW.record_id
                  AND target_output_evidence_id = NEW.evidence_id
            )
        )
    )
    OR (
        NEW.relationship = 'produced_as'
        AND EXISTS (
            SELECT 1 FROM episode_output_evidence
            WHERE record_id = NEW.record_id
              AND evidence_id = NEW.evidence_id
        )
    )
    OR (
        NEW.relationship = 'supports'
        AND EXISTS (
            SELECT 1 FROM correction_supporting_evidence
            WHERE record_id = NEW.record_id
              AND evidence_id = NEW.evidence_id
        )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'C2 evidence link is additional or has the wrong relationship');
END;

CREATE TRIGGER c2_evidence_cross_project_reuse_guard
BEFORE INSERT ON record_evidence_links
WHEN EXISTS (
    SELECT 1
    FROM records AS destination
    JOIN records AS owner
      ON owner.project_scope_id <> destination.project_scope_id
    WHERE destination.record_id = NEW.record_id
      AND destination.project_scope_id IS NOT NULL
      AND (
          EXISTS (
              SELECT 1 FROM episode_input_evidence AS child
              WHERE child.evidence_id = NEW.evidence_id
                AND child.record_id = owner.record_id
          )
          OR EXISTS (
              SELECT 1 FROM episode_output_evidence AS child
              WHERE child.evidence_id = NEW.evidence_id
                AND child.record_id = owner.record_id
          )
          OR EXISTS (
              SELECT 1 FROM correction_supporting_evidence AS child
              WHERE child.evidence_id = NEW.evidence_id
                AND child.record_id = owner.record_id
          )
          OR EXISTS (
              SELECT 1 FROM corrections AS correction
              WHERE correction.target_output_evidence_id = NEW.evidence_id
                AND correction.record_id = owner.record_id
          )
      )
)
BEGIN
    SELECT RAISE(ABORT, 'C2 evidence cannot be reused across project scope');
END;

CREATE TRIGGER c2_corrects_relationship_insert_guard
BEFORE INSERT ON record_relationships
WHEN NEW.relationship_type = 'corrects'
AND (
    EXISTS (
        SELECT 1 FROM records
        WHERE record_id = NEW.source_record_id
          AND record_family = 'episodic_memory'
          AND record_type = 'correction'
    )
    OR EXISTS (
        SELECT 1 FROM records
        WHERE record_id = NEW.target_record_id
          AND record_family = 'episodic_memory'
          AND record_type = 'correction'
    )
)
AND NOT EXISTS (
    SELECT 1
    FROM corrections AS correction
    JOIN records AS source ON source.record_id = correction.record_id
    JOIN records AS target ON target.record_id = correction.target_episode_id
    WHERE correction.record_id = NEW.source_record_id
      AND correction.target_episode_id = NEW.target_record_id
      AND source.project_scope_id = target.project_scope_id
)
BEGIN
    SELECT RAISE(ABORT, 'corrects relationship must use the exact C2 direction and target');
END;

CREATE TRIGGER c2_episode_payload_finalization_guard
BEFORE INSERT ON episodes
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
    UNION ALL
    SELECT 1 FROM memory_record_approval_transitions
    WHERE record_id = NEW.record_id
    LIMIT 1
)
BEGIN
    SELECT RAISE(ABORT, 'episode payload cannot be inserted after initial-state finalization');
END;

CREATE TRIGGER c2_correction_payload_finalization_guard
BEFORE INSERT ON corrections
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
    UNION ALL
    SELECT 1 FROM memory_record_approval_transitions
    WHERE record_id = NEW.record_id
    LIMIT 1
)
BEGIN
    SELECT RAISE(ABORT, 'correction payload cannot be inserted after initial-state finalization');
END;

CREATE TRIGGER c2_episode_input_evidence_finalization_guard
BEFORE INSERT ON episode_input_evidence
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
    UNION ALL
    SELECT 1 FROM memory_record_approval_transitions
    WHERE record_id = NEW.record_id
    LIMIT 1
)
BEGIN
    SELECT RAISE(ABORT, 'episode input lineage is sealed after initial-state finalization');
END;

CREATE TRIGGER c2_episode_output_evidence_finalization_guard
BEFORE INSERT ON episode_output_evidence
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
    UNION ALL
    SELECT 1 FROM memory_record_approval_transitions
    WHERE record_id = NEW.record_id
    LIMIT 1
)
BEGIN
    SELECT RAISE(ABORT, 'episode output lineage is sealed after initial-state finalization');
END;

CREATE TRIGGER c2_episode_evaluation_anchor_finalization_guard
BEFORE INSERT ON episode_evaluation_anchors
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
    UNION ALL
    SELECT 1 FROM memory_record_approval_transitions
    WHERE record_id = NEW.record_id
    LIMIT 1
)
BEGIN
    SELECT RAISE(ABORT, 'episode evaluation lineage is sealed after initial-state finalization');
END;

CREATE TRIGGER c2_correction_support_finalization_guard
BEFORE INSERT ON correction_supporting_evidence
WHEN EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
    UNION ALL
    SELECT 1 FROM memory_record_approval_transitions
    WHERE record_id = NEW.record_id
    LIMIT 1
)
BEGIN
    SELECT RAISE(ABORT, 'correction supporting lineage is sealed after initial-state finalization');
END;

CREATE TRIGGER c2_record_evidence_link_finalization_guard
BEFORE INSERT ON record_evidence_links
WHEN EXISTS (
    SELECT 1 FROM records
    WHERE record_id = NEW.record_id
      AND record_family = 'episodic_memory'
      AND record_type IN ('episode', 'correction')
)
AND EXISTS (
    SELECT 1 FROM memory_record_lifecycle_transitions
    WHERE record_id = NEW.record_id
    UNION ALL
    SELECT 1 FROM memory_record_approval_transitions
    WHERE record_id = NEW.record_id
    LIMIT 1
)
BEGIN
    SELECT RAISE(ABORT, 'C2 evidence links are sealed after initial-state finalization');
END;

CREATE TRIGGER c2_records_core_immutable
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
WHEN OLD.record_family = 'episodic_memory'
AND OLD.record_type IN ('episode', 'correction')
BEGIN
    SELECT RAISE(ABORT, 'C2 record envelope identity and content are immutable');
END;

CREATE TRIGGER c2_record_evidence_links_immutable
BEFORE UPDATE ON record_evidence_links
WHEN EXISTS (
    SELECT 1 FROM records
    WHERE record_id IN (OLD.record_id, NEW.record_id)
      AND record_family = 'episodic_memory'
      AND record_type IN ('episode', 'correction')
)
BEGIN
    SELECT RAISE(ABORT, 'C2 evidence links are immutable in both directions');
END;

CREATE TRIGGER c2_record_evidence_links_no_delete
BEFORE DELETE ON record_evidence_links
WHEN EXISTS (
    SELECT 1 FROM records
    WHERE record_id = OLD.record_id
      AND record_family = 'episodic_memory'
      AND record_type IN ('episode', 'correction')
)
BEGIN
    SELECT RAISE(ABORT, 'C2 evidence links cannot be deleted');
END;

CREATE TRIGGER c2_output_evidence_immutable
BEFORE UPDATE ON evidence_items
WHEN EXISTS (
    SELECT 1 FROM episode_output_evidence
    WHERE evidence_id = OLD.evidence_id
)
BEGIN
    SELECT RAISE(ABORT, 'episode output evidence is immutable');
END;

CREATE TRIGGER c2_output_evidence_no_delete
BEFORE DELETE ON evidence_items
WHEN EXISTS (
    SELECT 1 FROM episode_output_evidence
    WHERE evidence_id = OLD.evidence_id
)
BEGIN
    SELECT RAISE(ABORT, 'episode output evidence cannot be deleted');
END;

CREATE TRIGGER c2_inline_evidence_content_no_delete
BEFORE DELETE ON evidence_inline_text
WHEN EXISTS (
    SELECT 1 FROM episode_input_evidence
    WHERE evidence_id = OLD.evidence_id
    UNION ALL
    SELECT 1 FROM episode_output_evidence
    WHERE evidence_id = OLD.evidence_id
    UNION ALL
    SELECT 1 FROM correction_supporting_evidence
    WHERE evidence_id = OLD.evidence_id
    UNION ALL
    SELECT 1 FROM corrections
    WHERE target_output_evidence_id = OLD.evidence_id
    LIMIT 1
)
BEGIN
    SELECT RAISE(ABORT, 'C2 inline evidence content cannot be deleted');
END;

CREATE TRIGGER c2_active_evidence_mutation_guard
BEFORE UPDATE ON evidence_items
WHEN EXISTS (
    SELECT 1
    FROM records AS record
    WHERE record.lifecycle_state = 'active'
      AND (
          EXISTS (
              SELECT 1 FROM episode_input_evidence AS child
              WHERE child.record_id = record.record_id
                AND child.evidence_id = OLD.evidence_id
          )
          OR EXISTS (
              SELECT 1 FROM correction_supporting_evidence AS child
              WHERE child.record_id = record.record_id
                AND child.evidence_id = OLD.evidence_id
          )
          OR EXISTS (
              SELECT 1 FROM corrections AS correction
              WHERE correction.record_id = record.record_id
                AND correction.target_output_evidence_id = OLD.evidence_id
          )
      )
)
BEGIN
    SELECT RAISE(ABORT, 'active C2 evidence boundary and integrity are immutable');
END;

CREATE TRIGGER episodes_immutable
BEFORE UPDATE ON episodes
BEGIN
    SELECT RAISE(ABORT, 'episode payloads are immutable');
END;

CREATE TRIGGER episodes_no_delete
BEFORE DELETE ON episodes
BEGIN
    SELECT RAISE(ABORT, 'episode payloads cannot be deleted');
END;

CREATE TRIGGER episode_input_evidence_immutable
BEFORE UPDATE ON episode_input_evidence
BEGIN
    SELECT RAISE(ABORT, 'episode input lineage is immutable');
END;

CREATE TRIGGER episode_input_evidence_no_delete
BEFORE DELETE ON episode_input_evidence
BEGIN
    SELECT RAISE(ABORT, 'episode input lineage cannot be deleted');
END;

CREATE TRIGGER episode_output_evidence_immutable
BEFORE UPDATE ON episode_output_evidence
BEGIN
    SELECT RAISE(ABORT, 'episode output lineage is immutable');
END;

CREATE TRIGGER episode_output_evidence_no_delete
BEFORE DELETE ON episode_output_evidence
BEGIN
    SELECT RAISE(ABORT, 'episode output lineage cannot be deleted');
END;

CREATE TRIGGER episode_evaluation_anchors_immutable
BEFORE UPDATE ON episode_evaluation_anchors
BEGIN
    SELECT RAISE(ABORT, 'episode evaluation lineage is immutable');
END;

CREATE TRIGGER episode_evaluation_anchors_no_delete
BEFORE DELETE ON episode_evaluation_anchors
BEGIN
    SELECT RAISE(ABORT, 'episode evaluation lineage cannot be deleted');
END;

CREATE TRIGGER corrections_immutable
BEFORE UPDATE ON corrections
BEGIN
    SELECT RAISE(ABORT, 'correction payloads are immutable');
END;

CREATE TRIGGER corrections_no_delete
BEFORE DELETE ON corrections
BEGIN
    SELECT RAISE(ABORT, 'correction payloads cannot be deleted');
END;

CREATE TRIGGER correction_supporting_evidence_immutable
BEFORE UPDATE ON correction_supporting_evidence
BEGIN
    SELECT RAISE(ABORT, 'correction support lineage is immutable');
END;

CREATE TRIGGER correction_supporting_evidence_no_delete
BEFORE DELETE ON correction_supporting_evidence
BEGIN
    SELECT RAISE(ABORT, 'correction support lineage cannot be deleted');
END;

CREATE TRIGGER c2_episode_activation_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN OLD.record_family = 'episodic_memory'
AND OLD.record_type = 'episode'
AND NEW.lifecycle_state = 'active'
AND OLD.lifecycle_state <> 'active'
AND (
    NEW.approval_status <> 'approved'
    OR NOT EXISTS (
        SELECT 1
        FROM memory_record_approval_transitions AS transition
        JOIN memory_approval_grants AS grant_record
          ON grant_record.grant_id = transition.approval_grant_id
         AND grant_record.record_id = OLD.record_id
         AND grant_record.consumed_at IS NOT NULL
         AND grant_record.consumed_by_transition_id = transition.transition_id
        JOIN authority_records AS authority
          ON authority.authority_record_id = grant_record.authority_record_id
        JOIN memory_record_approval_authorities AS permitted
          ON permitted.record_family = OLD.record_family
         AND permitted.record_type = OLD.record_type
         AND permitted.authority_class = authority.authority_class
        JOIN evidence_items AS evidence
          ON evidence.evidence_id = grant_record.evidence_id
        WHERE transition.record_id = OLD.record_id
          AND transition.to_status = 'approved'
          AND authority.status = 'active'
          AND authority.effect = 'allow'
          AND evidence.integrity_status = 'valid'
          AND NOT EXISTS (
              SELECT 1 FROM authority_revocations AS revocation
              WHERE revocation.authority_record_id = authority.authority_record_id
          )
    )
    OR NOT EXISTS (
        SELECT 1 FROM episodes WHERE record_id = OLD.record_id
    )
    OR NOT EXISTS (
        SELECT 1 FROM episode_input_evidence WHERE record_id = OLD.record_id
        UNION ALL
        SELECT 1 FROM episode_output_evidence WHERE record_id = OLD.record_id
    )
    OR EXISTS (
        SELECT 1
        FROM episode_input_evidence AS child
        LEFT JOIN record_evidence_links AS link
          ON link.record_id = child.record_id
         AND link.evidence_id = child.evidence_id
         AND link.relationship = 'derived_from'
        WHERE child.record_id = OLD.record_id
          AND link.record_id IS NULL
    )
    OR EXISTS (
        SELECT 1
        FROM episode_output_evidence AS child
        LEFT JOIN record_evidence_links AS link
          ON link.record_id = child.record_id
         AND link.evidence_id = child.evidence_id
         AND link.relationship = 'produced_as'
        WHERE child.record_id = OLD.record_id
          AND link.record_id IS NULL
    )
    OR (
        SELECT COUNT(*) FROM record_evidence_links
        WHERE record_id = OLD.record_id
    ) <> (
        SELECT COUNT(*) FROM episode_input_evidence
        WHERE record_id = OLD.record_id
    ) + (
        SELECT COUNT(*) FROM episode_output_evidence
        WHERE record_id = OLD.record_id
    )
    OR EXISTS (
        SELECT 1
        FROM episode_evaluation_anchors AS child
        LEFT JOIN governed_evaluation_record_anchors AS anchor
          ON anchor.evaluation_record_id = child.evaluation_record_id
         AND anchor.project_scope_id = OLD.project_scope_id
         AND anchor.current_state = 'claimed'
        WHERE child.record_id = OLD.record_id
          AND anchor.evaluation_record_id IS NULL
    )
    OR EXISTS (
        SELECT 1
        FROM (
            SELECT evidence_id FROM episode_input_evidence
            WHERE record_id = OLD.record_id
            UNION ALL
            SELECT evidence_id FROM episode_output_evidence
            WHERE record_id = OLD.record_id
        ) AS child
        LEFT JOIN evidence_items AS evidence
          ON evidence.evidence_id = child.evidence_id
        WHERE evidence.evidence_id IS NULL
           OR evidence.integrity_status <> 'valid'
           OR evidence.evidence_kind IN (
               'controlled_prompt', 'controlled_output'
           )
           OR evidence.sensitivity_class <> OLD.sensitivity_class
           OR evidence.privacy_class <> OLD.privacy_class
           OR EXISTS (
               SELECT 1 FROM controlled_resilience_evidence AS controlled
               WHERE controlled.raw_prompt_evidence_id = child.evidence_id
                  OR controlled.raw_output_evidence_id = child.evidence_id
           )
           OR EXISTS (
               SELECT 1
               FROM record_evidence_links AS other_link
               JOIN records AS other_record
                 ON other_record.record_id = other_link.record_id
               WHERE other_link.evidence_id = child.evidence_id
                 AND other_record.project_scope_id IS NOT NULL
                 AND other_record.project_scope_id <> OLD.project_scope_id
           )
    )
    OR NOT EXISTS (
        SELECT 1
        FROM episodes AS episode
        JOIN sessions AS session ON session.session_id = OLD.session_id
        LEFT JOIN tasks AS task ON task.task_id = OLD.task_id
        WHERE episode.record_id = OLD.record_id
          AND session.active_project_scope = OLD.project_scope_id
          AND (
              (
                  OLD.task_id IS NOT NULL
                  AND task.session_id = OLD.session_id
                  AND task.project_scope_id = OLD.project_scope_id
                  AND task.status IN ('completed', 'stopped', 'failed')
                  AND task.completed_at IS NOT NULL
                  AND OLD.created_at >= task.completed_at
                  AND (
                      (episode.outcome = 'completed' AND task.status = 'completed')
                      OR (episode.outcome = 'failed' AND task.status = 'failed')
                      OR (episode.outcome = 'stopped' AND task.status = 'stopped')
                      OR (
                          episode.outcome = 'partial'
                          AND task.status IN ('stopped', 'failed')
                      )
                      OR (
                          episode.outcome = 'rejected'
                          AND task.status = 'stopped'
                          AND EXISTS (
                              SELECT 1 FROM task_stop_events AS stop
                              WHERE stop.task_id = task.task_id
                                AND stop.governance_forced_stop = 1
                          )
                      )
                  )
              )
              OR (
                  OLD.task_id IS NULL
                  AND session.session_status IN ('closed', 'aborted')
                  AND session.closed_at IS NOT NULL
                  AND OLD.created_at >= session.closed_at
                  AND (
                      (
                          episode.outcome = 'completed'
                          AND session.session_status = 'closed'
                      )
                      OR (
                          episode.outcome IN ('stopped', 'partial')
                          AND session.session_status = 'aborted'
                      )
                  )
              )
          )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'active episode requires exact approved C2 lineage');
END;

CREATE TRIGGER c2_correction_activation_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN OLD.record_family = 'episodic_memory'
AND OLD.record_type = 'correction'
AND NEW.lifecycle_state = 'active'
AND OLD.lifecycle_state <> 'active'
AND (
    NEW.approval_status <> 'approved'
    OR NOT EXISTS (
        SELECT 1
        FROM memory_record_approval_transitions AS transition
        JOIN memory_approval_grants AS grant_record
          ON grant_record.grant_id = transition.approval_grant_id
         AND grant_record.record_id = OLD.record_id
         AND grant_record.consumed_at IS NOT NULL
         AND grant_record.consumed_by_transition_id = transition.transition_id
        JOIN authority_records AS authority
          ON authority.authority_record_id = grant_record.authority_record_id
        JOIN memory_record_approval_authorities AS permitted
          ON permitted.record_family = OLD.record_family
         AND permitted.record_type = OLD.record_type
         AND permitted.authority_class = authority.authority_class
        JOIN evidence_items AS evidence
          ON evidence.evidence_id = grant_record.evidence_id
        WHERE transition.record_id = OLD.record_id
          AND transition.to_status = 'approved'
          AND authority.status = 'active'
          AND authority.effect = 'allow'
          AND evidence.integrity_status = 'valid'
          AND NOT EXISTS (
              SELECT 1 FROM authority_revocations AS revocation
              WHERE revocation.authority_record_id = authority.authority_record_id
          )
    )
    OR NOT EXISTS (
        SELECT 1
        FROM corrections AS correction
        JOIN records AS episode_record
          ON episode_record.record_id = correction.target_episode_id
        JOIN episode_output_evidence AS output
          ON output.record_id = correction.target_episode_id
         AND output.evidence_id = correction.target_output_evidence_id
        JOIN evidence_items AS target_evidence
          ON target_evidence.evidence_id = correction.target_output_evidence_id
        JOIN entities AS issuer
          ON issuer.entity_id = correction.issued_by_entity_id
        WHERE correction.record_id = OLD.record_id
          AND episode_record.project_scope_id = OLD.project_scope_id
          AND episode_record.lifecycle_state NOT IN ('revoked', 'deleted')
          AND target_evidence.integrity_status = 'valid'
          AND target_evidence.evidence_kind NOT IN (
              'controlled_prompt', 'controlled_output'
          )
          AND target_evidence.sensitivity_class = OLD.sensitivity_class
          AND target_evidence.privacy_class = OLD.privacy_class
          AND issuer.status = 'active'
    )
    OR NOT EXISTS (
        SELECT 1 FROM correction_supporting_evidence
        WHERE record_id = OLD.record_id
    )
    OR EXISTS (
        SELECT 1
        FROM correction_supporting_evidence AS child
        LEFT JOIN evidence_items AS evidence
          ON evidence.evidence_id = child.evidence_id
        WHERE child.record_id = OLD.record_id
          AND (
              evidence.evidence_id IS NULL
              OR evidence.integrity_status <> 'valid'
              OR evidence.evidence_kind IN (
                  'controlled_prompt', 'controlled_output'
              )
              OR evidence.sensitivity_class <> OLD.sensitivity_class
              OR evidence.privacy_class <> OLD.privacy_class
              OR EXISTS (
                  SELECT 1 FROM controlled_resilience_evidence AS controlled
                  WHERE controlled.raw_prompt_evidence_id = child.evidence_id
                     OR controlled.raw_output_evidence_id = child.evidence_id
              )
              OR EXISTS (
                  SELECT 1
                  FROM record_evidence_links AS other_link
                  JOIN records AS other_record
                    ON other_record.record_id = other_link.record_id
                  WHERE other_link.evidence_id = child.evidence_id
                    AND other_record.project_scope_id IS NOT NULL
                    AND other_record.project_scope_id <> OLD.project_scope_id
              )
          )
    )
    OR NOT EXISTS (
        SELECT 1
        FROM corrections AS correction
        JOIN record_evidence_links AS link
          ON link.record_id = correction.record_id
         AND link.evidence_id = correction.target_output_evidence_id
         AND link.relationship = 'derived_from'
        WHERE correction.record_id = OLD.record_id
    )
    OR EXISTS (
        SELECT 1
        FROM correction_supporting_evidence AS child
        LEFT JOIN record_evidence_links AS link
          ON link.record_id = child.record_id
         AND link.evidence_id = child.evidence_id
         AND link.relationship = 'supports'
        WHERE child.record_id = OLD.record_id
          AND link.record_id IS NULL
    )
    OR (
        SELECT COUNT(*) FROM record_evidence_links
        WHERE record_id = OLD.record_id
    ) <> 1 + (
        SELECT COUNT(*) FROM correction_supporting_evidence
        WHERE record_id = OLD.record_id
    )
    OR (
        SELECT COUNT(*)
        FROM record_relationships
        WHERE relationship_type = 'corrects'
          AND (
              source_record_id = OLD.record_id
              OR target_record_id = OLD.record_id
          )
    ) <> 1
    OR NOT EXISTS (
        SELECT 1
        FROM corrections AS correction
        JOIN record_relationships AS relationship
          ON relationship.source_record_id = correction.record_id
         AND relationship.target_record_id = correction.target_episode_id
         AND relationship.relationship_type = 'corrects'
        JOIN memory_relationship_grants AS grant_record
          ON grant_record.grant_id = relationship.relationship_grant_id
         AND grant_record.relationship_id = relationship.relationship_id
         AND grant_record.relationship_type = 'corrects'
         AND grant_record.source_record_id = correction.record_id
         AND grant_record.target_record_id = correction.target_episode_id
         AND grant_record.consumed_at IS NOT NULL
         AND grant_record.consumed_by_relationship_id = relationship.relationship_id
        JOIN authority_records AS authority
          ON authority.authority_record_id = grant_record.authority_record_id
         AND authority.status = 'active'
         AND authority.effect = 'allow'
        JOIN evidence_items AS grant_evidence
          ON grant_evidence.evidence_id = grant_record.evidence_id
         AND grant_evidence.integrity_status = 'valid'
        WHERE correction.record_id = OLD.record_id
          AND NOT EXISTS (
              SELECT 1 FROM authority_revocations AS revocation
              WHERE revocation.authority_record_id = authority.authority_record_id
          )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'active correction requires exact approval, lineage, and grant');
END;
