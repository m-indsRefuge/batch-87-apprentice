CREATE TABLE retrieval_requests (
    retrieval_request_id TEXT PRIMARY KEY,
    contract_version TEXT NOT NULL CHECK (contract_version = '1.0.0'),
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_scope_id TEXT NOT NULL,
    task_context_finalization_id TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK (trim(purpose) <> ''),
    requested_sections_json TEXT NOT NULL CHECK (
        requested_sections_json =
            '["task","authority","policy","evidence","memory"]'
        AND json_valid(requested_sections_json)
        AND json_type(requested_sections_json) = 'array'
    ),
    requested_at TEXT NOT NULL,
    requested_by_principal TEXT NOT NULL CHECK (
        requested_by_principal IN ('operator', 'codex_development_harness')
    ),
    ranking_strategy TEXT NOT NULL CHECK (
        ranking_strategy = 'deterministic_fallback_v1'
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
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (task_context_finalization_id)
        REFERENCES task_context_finalizations(finalization_id)
        ON DELETE RESTRICT
);

CREATE TABLE retrieval_manifests (
    retrieval_manifest_id TEXT PRIMARY KEY,
    retrieval_request_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_scope_id TEXT NOT NULL,
    task_context_finalization_id TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK (
        length(request_hash) = 64
        AND request_hash NOT GLOB '*[^0-9a-f]*'
    ),
    task_memory_projection_hash TEXT NOT NULL CHECK (
        length(task_memory_projection_hash) = 64
        AND task_memory_projection_hash NOT GLOB '*[^0-9a-f]*'
    ),
    task_memory_projection_json TEXT NOT NULL CHECK (
        json_valid(task_memory_projection_json)
        AND json_type(task_memory_projection_json) = 'object'
    ),
    finalization_hash TEXT NOT NULL CHECK (
        length(finalization_hash) = 64
        AND finalization_hash NOT GLOB '*[^0-9a-f]*'
    ),
    ranking_strategy TEXT NOT NULL CHECK (
        ranking_strategy = 'deterministic_fallback_v1'
    ),
    status TEXT NOT NULL CHECK (status IN ('accepted', 'rejected')),
    created_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (retrieval_request_id)
        REFERENCES retrieval_requests(retrieval_request_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (task_context_finalization_id)
        REFERENCES task_context_finalizations(finalization_id)
        ON DELETE RESTRICT
);

CREATE TABLE retrieval_manifest_entries (
    entry_id TEXT PRIMARY KEY,
    retrieval_manifest_id TEXT NOT NULL,
    context_item_id TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK (
        source_kind IN ('memory_record', 'evidence', 'governance_rule')
    ),
    source_id TEXT NOT NULL,
    source_memory_record_id TEXT,
    source_evidence_id TEXT,
    source_governance_rule_id TEXT,
    source_content_hash TEXT NOT NULL CHECK (
        length(source_content_hash) = 64
        AND source_content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    required INTEGER NOT NULL CHECK (required IN (0, 1)),
    target_section TEXT NOT NULL CHECK (
        target_section IN ('policy', 'evidence', 'memory')
    ),
    eligibility_status TEXT NOT NULL CHECK (
        eligibility_status IN ('eligible', 'ineligible')
    ),
    eligibility_reasons_json TEXT NOT NULL CHECK (
        json_valid(eligibility_reasons_json)
        AND json_type(eligibility_reasons_json) = 'array'
    ),
    eligibility_decision_hash TEXT NOT NULL CHECK (
        length(eligibility_decision_hash) = 64
        AND eligibility_decision_hash NOT GLOB '*[^0-9a-f]*'
    ),
    materialization_status TEXT NOT NULL CHECK (
        materialization_status IN (
            'materialized', 'not_attempted', 'unavailable',
            'prohibited', 'invalid'
        )
    ),
    materialization_reasons_json TEXT NOT NULL CHECK (
        json_valid(materialization_reasons_json)
        AND json_type(materialization_reasons_json) = 'array'
    ),
    materialized_content_hash TEXT CHECK (
        materialized_content_hash IS NULL
        OR (
            length(materialized_content_hash) = 64
            AND materialized_content_hash NOT GLOB '*[^0-9a-f]*'
        )
    ),
    rank_components_json TEXT CHECK (
        rank_components_json IS NULL
        OR (
            json_valid(rank_components_json)
            AND json_type(rank_components_json) = 'object'
        )
    ),
    rank_explanation_json TEXT NOT NULL CHECK (
        json_valid(rank_explanation_json)
        AND json_type(rank_explanation_json) = 'array'
    ),
    final_rank INTEGER CHECK (final_rank IS NULL OR final_rank >= 0),
    disposition TEXT NOT NULL CHECK (
        disposition IN ('included', 'excluded')
    ),
    disposition_reason TEXT NOT NULL CHECK (trim(disposition_reason) <> ''),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    UNIQUE (retrieval_manifest_id, context_item_id),
    UNIQUE (retrieval_manifest_id, source_kind, source_id),
    UNIQUE (retrieval_manifest_id, final_rank),
    FOREIGN KEY (retrieval_manifest_id)
        REFERENCES retrieval_manifests(retrieval_manifest_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (context_item_id)
        REFERENCES task_context_items(context_item_id) ON DELETE RESTRICT,
    FOREIGN KEY (source_memory_record_id)
        REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (source_evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT,
    FOREIGN KEY (source_governance_rule_id)
        REFERENCES governance_rules(governance_rule_id) ON DELETE RESTRICT,
    CHECK (
        (
            source_kind = 'memory_record'
            AND source_memory_record_id = source_id
            AND source_evidence_id IS NULL
            AND source_governance_rule_id IS NULL
        )
        OR
        (
            source_kind = 'evidence'
            AND source_memory_record_id IS NULL
            AND source_evidence_id = source_id
            AND source_governance_rule_id IS NULL
        )
        OR
        (
            source_kind = 'governance_rule'
            AND source_memory_record_id IS NULL
            AND source_evidence_id IS NULL
            AND source_governance_rule_id = source_id
        )
    ),
    CHECK (
        (
            disposition = 'included'
            AND eligibility_status = 'eligible'
            AND materialization_status = 'materialized'
            AND materialized_content_hash IS NOT NULL
            AND rank_components_json IS NOT NULL
            AND final_rank IS NOT NULL
            AND rank_explanation_json <> '[]'
        )
        OR
        (
            disposition = 'excluded'
            AND materialized_content_hash IS NULL
            AND final_rank IS NULL
            AND rank_components_json IS NULL
            AND rank_explanation_json = '[]'
        )
    )
);

CREATE TABLE context_packages (
    context_package_id TEXT PRIMARY KEY,
    contract_version TEXT NOT NULL CHECK (contract_version = '1.0.0'),
    retrieval_request_id TEXT NOT NULL UNIQUE,
    retrieval_manifest_id TEXT NOT NULL UNIQUE,
    retrieval_manifest_hash TEXT NOT NULL CHECK (
        length(retrieval_manifest_hash) = 64
        AND retrieval_manifest_hash NOT GLOB '*[^0-9a-f]*'
    ),
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_scope_id TEXT NOT NULL,
    task_context_finalization_id TEXT NOT NULL,
    task_memory_projection_hash TEXT NOT NULL CHECK (
        length(task_memory_projection_hash) = 64
        AND task_memory_projection_hash NOT GLOB '*[^0-9a-f]*'
    ),
    status TEXT NOT NULL CHECK (
        status IN (
            'accepted', 'rejected_contamination',
            'rejected_required_source', 'rejected_integrity'
        )
    ),
    contamination_status TEXT NOT NULL CHECK (
        contamination_status IN ('clean', 'contaminated')
    ),
    created_at TEXT NOT NULL,
    authoritative_task_hash TEXT NOT NULL CHECK (
        length(authoritative_task_hash) = 64
        AND authoritative_task_hash NOT GLOB '*[^0-9a-f]*'
    ),
    authoritative_authority_hash TEXT NOT NULL CHECK (
        length(authoritative_authority_hash) = 64
        AND authoritative_authority_hash NOT GLOB '*[^0-9a-f]*'
    ),
    sections_json TEXT NOT NULL CHECK (
        json_valid(sections_json) AND json_type(sections_json) = 'object'
    ),
    recovery_of_context_package_id TEXT,
    recovery_relationship_hash TEXT CHECK (
        recovery_relationship_hash IS NULL
        OR (
            length(recovery_relationship_hash) = 64
            AND recovery_relationship_hash NOT GLOB '*[^0-9a-f]*'
        )
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (retrieval_request_id)
        REFERENCES retrieval_requests(retrieval_request_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (retrieval_manifest_id)
        REFERENCES retrieval_manifests(retrieval_manifest_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (task_context_finalization_id)
        REFERENCES task_context_finalizations(finalization_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (recovery_of_context_package_id)
        REFERENCES context_packages(context_package_id) ON DELETE RESTRICT,
    CHECK (
        (
            recovery_of_context_package_id IS NULL
            AND recovery_relationship_hash IS NULL
        )
        OR (
            recovery_of_context_package_id IS NOT NULL
            AND recovery_of_context_package_id <> context_package_id
            AND recovery_relationship_hash IS NOT NULL
        )
    ),
    CHECK (
        (
            status = 'accepted'
            AND contamination_status = 'clean'
        )
        OR status <> 'accepted'
    ),
    CHECK (
        (
            status = 'rejected_contamination'
            AND contamination_status = 'contaminated'
        )
        OR status <> 'rejected_contamination'
    )
);

CREATE TABLE ordered_context_manifest_entries (
    ordered_entry_id TEXT PRIMARY KEY,
    context_package_id TEXT NOT NULL,
    section TEXT NOT NULL CHECK (
        section IN ('task', 'authority', 'policy', 'evidence', 'memory')
    ),
    section_order INTEGER NOT NULL CHECK (section_order BETWEEN 0 AND 4),
    entry_order INTEGER NOT NULL CHECK (entry_order >= 0),
    source_kind TEXT NOT NULL CHECK (
        source_kind IN (
            'authoritative_i2_task', 'authoritative_i2_authority',
            'memory_record', 'evidence', 'governance_rule'
        )
    ),
    source_id TEXT NOT NULL,
    source_content_hash TEXT NOT NULL CHECK (
        length(source_content_hash) = 64
        AND source_content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    retrieval_manifest_entry_id TEXT,
    entry_canonical_json TEXT NOT NULL CHECK (
        json_valid(entry_canonical_json)
        AND json_type(entry_canonical_json) = 'object'
    ),
    entry_canonical_hash TEXT NOT NULL CHECK (
        length(entry_canonical_hash) = 64
        AND entry_canonical_hash NOT GLOB '*[^0-9a-f]*'
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    UNIQUE (context_package_id, section, entry_order),
    UNIQUE (context_package_id, source_kind, source_id),
    UNIQUE (context_package_id, retrieval_manifest_entry_id),
    FOREIGN KEY (context_package_id)
        REFERENCES context_packages(context_package_id) ON DELETE RESTRICT,
    FOREIGN KEY (retrieval_manifest_entry_id)
        REFERENCES retrieval_manifest_entries(entry_id) ON DELETE RESTRICT,
    CHECK (
        section_order = CASE section
            WHEN 'task' THEN 0
            WHEN 'authority' THEN 1
            WHEN 'policy' THEN 2
            WHEN 'evidence' THEN 3
            WHEN 'memory' THEN 4
        END
    ),
    CHECK (
        (
            source_kind IN (
                'authoritative_i2_task', 'authoritative_i2_authority'
            )
            AND retrieval_manifest_entry_id IS NULL
        )
        OR
        (
            source_kind IN ('memory_record', 'evidence', 'governance_rule')
            AND retrieval_manifest_entry_id IS NOT NULL
        )
    )
);

CREATE TABLE context_contamination_findings (
    finding_id TEXT PRIMARY KEY,
    context_package_id TEXT NOT NULL,
    finding_order INTEGER NOT NULL CHECK (finding_order >= 0),
    reason_code TEXT NOT NULL CHECK (trim(reason_code) <> ''),
    source_kind TEXT,
    source_id TEXT,
    detail TEXT NOT NULL CHECK (trim(detail) <> ''),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    UNIQUE (context_package_id, finding_order),
    FOREIGN KEY (context_package_id)
        REFERENCES context_packages(context_package_id) ON DELETE RESTRICT,
    CHECK (
        (source_kind IS NULL AND source_id IS NULL)
        OR (source_kind IS NOT NULL AND source_id IS NOT NULL)
    )
);

CREATE TABLE context_recovery_relationships (
    recovery_context_package_id TEXT PRIMARY KEY,
    rejected_context_package_id TEXT NOT NULL,
    recovery_reason TEXT NOT NULL CHECK (trim(recovery_reason) <> ''),
    excluded_source_ids_json TEXT NOT NULL CHECK (
        json_valid(excluded_source_ids_json)
        AND json_type(excluded_source_ids_json) = 'array'
        AND excluded_source_ids_json <> '[]'
    ),
    preserved_findings_json TEXT NOT NULL CHECK (
        json_valid(preserved_findings_json)
        AND json_type(preserved_findings_json) = 'array'
        AND preserved_findings_json <> '[]'
    ),
    created_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (recovery_context_package_id)
        REFERENCES context_packages(context_package_id) ON DELETE RESTRICT,
    FOREIGN KEY (rejected_context_package_id)
        REFERENCES context_packages(context_package_id) ON DELETE RESTRICT,
    CHECK (recovery_context_package_id <> rejected_context_package_id)
);

CREATE INDEX retrieval_requests_task
ON retrieval_requests(task_id, requested_at);

CREATE INDEX retrieval_manifests_task_status
ON retrieval_manifests(task_id, status);

CREATE INDEX retrieval_manifest_entries_manifest_rank
ON retrieval_manifest_entries(retrieval_manifest_id, final_rank);

CREATE INDEX retrieval_manifest_entries_source
ON retrieval_manifest_entries(source_kind, source_id);

CREATE INDEX context_packages_task_status
ON context_packages(task_id, status);

CREATE INDEX ordered_context_entries_package_order
ON ordered_context_manifest_entries(
    context_package_id, section_order, entry_order
);

CREATE INDEX contamination_findings_package
ON context_contamination_findings(context_package_id, finding_order);

CREATE TRIGGER retrieval_requests_insert_guard
BEFORE INSERT ON retrieval_requests
WHEN NOT EXISTS (
    SELECT 1
    FROM tasks AS task
    JOIN sessions AS session_record
      ON session_record.session_id = task.session_id
    JOIN task_context_finalizations AS finalization
      ON finalization.finalization_id = NEW.task_context_finalization_id
     AND finalization.task_id = task.task_id
    WHERE task.task_id = NEW.task_id
      AND task.session_id = NEW.session_id
      AND task.project_scope_id = NEW.project_scope_id
      AND session_record.session_id = NEW.session_id
      AND session_record.active_project_scope = NEW.project_scope_id
      AND task.status = 'active'
      AND session_record.session_status IN ('open', 'paused')
      AND finalization.session_id = NEW.session_id
      AND finalization.project_scope_id = NEW.project_scope_id
)
BEGIN
    SELECT RAISE(
        ABORT,
        'retrieval request violates active task, session, project or finalization'
    );
END;

CREATE TRIGGER retrieval_manifests_insert_guard
BEFORE INSERT ON retrieval_manifests
WHEN NOT EXISTS (
    SELECT 1
    FROM retrieval_requests AS request
    JOIN task_context_finalizations AS finalization
      ON finalization.finalization_id = request.task_context_finalization_id
    WHERE request.retrieval_request_id = NEW.retrieval_request_id
      AND request.task_id = NEW.task_id
      AND request.session_id = NEW.session_id
      AND request.project_scope_id = NEW.project_scope_id
      AND request.task_context_finalization_id =
          NEW.task_context_finalization_id
      AND request.content_hash = NEW.request_hash
      AND request.ranking_strategy = NEW.ranking_strategy
      AND finalization.content_hash = NEW.finalization_hash
)
BEGIN
    SELECT RAISE(
        ABORT,
        'retrieval manifest differs from request or finalization'
    );
END;

CREATE TRIGGER retrieval_manifest_entries_insert_guard
BEFORE INSERT ON retrieval_manifest_entries
WHEN NOT EXISTS (
    SELECT 1
    FROM retrieval_manifests AS manifest
    JOIN task_context_items AS item
      ON item.context_item_id = NEW.context_item_id
    WHERE manifest.retrieval_manifest_id = NEW.retrieval_manifest_id
      AND item.task_id = manifest.task_id
      AND item.source_kind = NEW.source_kind
      AND item.content_hash = NEW.source_content_hash
      AND item.required = NEW.required
      AND (
          (
              NEW.source_kind = 'memory_record'
              AND item.source_memory_record_id = NEW.source_id
              AND NEW.target_section = 'memory'
          )
          OR
          (
              NEW.source_kind = 'evidence'
              AND item.source_evidence_id = NEW.source_id
              AND NEW.target_section = 'evidence'
          )
          OR
          (
              NEW.source_kind = 'governance_rule'
              AND item.source_governance_rule_id = NEW.source_id
              AND NEW.target_section = 'policy'
          )
      )
      AND (
          NEW.source_kind <> 'evidence'
          OR NEW.disposition <> 'included'
          OR EXISTS (
              SELECT 1
              FROM governance_decision_evidence AS evidence_relationship
              JOIN governance_decisions AS evidence_decision
                ON evidence_decision.governance_decision_id =
                   evidence_relationship.governance_decision_id
              WHERE evidence_relationship.required_evidence_id = NEW.source_id
                AND evidence_relationship.resolved_evidence_id = NEW.source_id
                AND evidence_relationship.validation_status = 'available'
                AND evidence_decision.task_id = manifest.task_id
                AND evidence_decision.project_scope_id =
                    manifest.project_scope_id
          )
      )
      AND NOT (
          manifest.status = 'accepted'
          AND NEW.required = 1
          AND NEW.disposition = 'excluded'
      )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'retrieval manifest entry violates finalized candidate or status'
    );
END;

CREATE TRIGGER context_packages_insert_guard
BEFORE INSERT ON context_packages
WHEN NOT EXISTS (
    SELECT 1
    FROM retrieval_requests AS request
    JOIN retrieval_manifests AS manifest
      ON manifest.retrieval_manifest_id = NEW.retrieval_manifest_id
    WHERE request.retrieval_request_id = NEW.retrieval_request_id
      AND manifest.retrieval_request_id = request.retrieval_request_id
      AND request.task_id = NEW.task_id
      AND request.session_id = NEW.session_id
      AND request.project_scope_id = NEW.project_scope_id
      AND request.task_context_finalization_id =
          NEW.task_context_finalization_id
      AND manifest.content_hash = NEW.retrieval_manifest_hash
      AND manifest.task_memory_projection_hash =
          NEW.task_memory_projection_hash
      AND (
          (
              NEW.status = 'accepted'
              AND manifest.status = 'accepted'
          )
          OR
          (
              NEW.status <> 'accepted'
              AND manifest.status = 'rejected'
          )
      )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'context package differs from request or retrieval manifest'
    );
END;

CREATE TRIGGER ordered_context_entries_insert_guard
BEFORE INSERT ON ordered_context_manifest_entries
WHEN (
    NEW.retrieval_manifest_entry_id IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM context_packages AS package
        JOIN retrieval_manifest_entries AS entry
          ON entry.entry_id = NEW.retrieval_manifest_entry_id
        WHERE package.context_package_id = NEW.context_package_id
          AND entry.retrieval_manifest_id = package.retrieval_manifest_id
          AND (
              package.status = 'rejected_contamination'
              OR (
                  entry.disposition = 'included'
                  AND entry.source_kind = NEW.source_kind
                  AND entry.source_id = NEW.source_id
                  AND entry.source_content_hash = NEW.source_content_hash
                  AND entry.target_section = NEW.section
                  AND entry.materialized_content_hash =
                      NEW.entry_canonical_hash
              )
          )
    )
)
OR (
    NEW.source_kind = 'authoritative_i2_task'
    AND NOT EXISTS (
        SELECT 1
        FROM context_packages AS package
        JOIN retrieval_manifests AS manifest
          ON manifest.retrieval_manifest_id = package.retrieval_manifest_id
        WHERE package.context_package_id = NEW.context_package_id
          AND package.task_id = NEW.source_id
          AND json_extract(
              manifest.task_memory_projection_json,
              '$.authoritative_i2.task.task_id'
          ) = NEW.source_id
          AND NEW.section = 'task'
          AND NEW.entry_order = 0
          AND NEW.source_content_hash = package.authoritative_task_hash
          AND NEW.entry_canonical_hash = package.authoritative_task_hash
    )
)
OR (
    NEW.source_kind = 'authoritative_i2_authority'
    AND NOT EXISTS (
        SELECT 1
        FROM context_packages AS package
        JOIN retrieval_manifests AS manifest
          ON manifest.retrieval_manifest_id = package.retrieval_manifest_id
        JOIN governance_decisions AS decision_record
          ON decision_record.governance_decision_id = json_extract(
              manifest.task_memory_projection_json,
              '$.authoritative_i2.decision.governance_decision_id'
          )
         AND decision_record.task_id = package.task_id
        WHERE package.context_package_id = NEW.context_package_id
          AND decision_record.governance_decision_id = NEW.source_id
          AND NEW.section = 'authority'
          AND NEW.entry_order = 0
          AND NEW.source_content_hash = package.authoritative_authority_hash
          AND NEW.entry_canonical_hash =
              package.authoritative_authority_hash
    )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'ordered context entry lacks exact included or authoritative source'
    );
END;

CREATE TRIGGER context_contamination_findings_insert_guard
BEFORE INSERT ON context_contamination_findings
WHEN NOT EXISTS (
    SELECT 1 FROM context_packages
    WHERE context_package_id = NEW.context_package_id
      AND status = 'rejected_contamination'
      AND contamination_status = 'contaminated'
)
BEGIN
    SELECT RAISE(
        ABORT,
        'contamination finding requires a contaminated rejected package'
    );
END;

CREATE TRIGGER context_recovery_relationships_insert_guard
BEFORE INSERT ON context_recovery_relationships
WHEN NOT EXISTS (
    SELECT 1
    FROM context_packages AS recovery
    JOIN context_packages AS rejected
      ON rejected.context_package_id = NEW.rejected_context_package_id
    WHERE recovery.context_package_id = NEW.recovery_context_package_id
      AND recovery.recovery_of_context_package_id =
          rejected.context_package_id
      AND rejected.status = 'rejected_contamination'
      AND recovery.task_id = rejected.task_id
      AND recovery.session_id = rejected.session_id
      AND recovery.project_scope_id = rejected.project_scope_id
       AND recovery.task_context_finalization_id =
           rejected.task_context_finalization_id
       AND recovery.recovery_relationship_hash = NEW.content_hash
)
BEGIN
    SELECT RAISE(
        ABORT,
        'recovery relationship violates rejected-package binding'
    );
END;

CREATE TRIGGER retrieval_requests_immutable
BEFORE UPDATE ON retrieval_requests
BEGIN
    SELECT RAISE(ABORT, 'retrieval requests are immutable');
END;

CREATE TRIGGER retrieval_requests_no_delete
BEFORE DELETE ON retrieval_requests
BEGIN
    SELECT RAISE(ABORT, 'retrieval requests cannot be deleted');
END;

CREATE TRIGGER retrieval_manifests_immutable
BEFORE UPDATE ON retrieval_manifests
BEGIN
    SELECT RAISE(ABORT, 'retrieval manifests are immutable');
END;

CREATE TRIGGER retrieval_manifests_no_delete
BEFORE DELETE ON retrieval_manifests
BEGIN
    SELECT RAISE(ABORT, 'retrieval manifests cannot be deleted');
END;

CREATE TRIGGER retrieval_manifest_entries_immutable
BEFORE UPDATE ON retrieval_manifest_entries
BEGIN
    SELECT RAISE(ABORT, 'retrieval manifest entries are immutable');
END;

CREATE TRIGGER retrieval_manifest_entries_no_delete
BEFORE DELETE ON retrieval_manifest_entries
BEGIN
    SELECT RAISE(ABORT, 'retrieval manifest entries cannot be deleted');
END;

CREATE TRIGGER context_packages_immutable
BEFORE UPDATE ON context_packages
BEGIN
    SELECT RAISE(ABORT, 'context packages are immutable');
END;

CREATE TRIGGER context_packages_no_delete
BEFORE DELETE ON context_packages
BEGIN
    SELECT RAISE(ABORT, 'context packages cannot be deleted');
END;

CREATE TRIGGER ordered_context_entries_immutable
BEFORE UPDATE ON ordered_context_manifest_entries
BEGIN
    SELECT RAISE(ABORT, 'ordered context entries are immutable');
END;

CREATE TRIGGER ordered_context_entries_no_delete
BEFORE DELETE ON ordered_context_manifest_entries
BEGIN
    SELECT RAISE(ABORT, 'ordered context entries cannot be deleted');
END;

CREATE TRIGGER context_contamination_findings_immutable
BEFORE UPDATE ON context_contamination_findings
BEGIN
    SELECT RAISE(ABORT, 'contamination findings are immutable');
END;

CREATE TRIGGER context_contamination_findings_no_delete
BEFORE DELETE ON context_contamination_findings
BEGIN
    SELECT RAISE(ABORT, 'contamination findings cannot be deleted');
END;

CREATE TRIGGER context_recovery_relationships_immutable
BEFORE UPDATE ON context_recovery_relationships
BEGIN
    SELECT RAISE(ABORT, 'recovery relationships are immutable');
END;

CREATE TRIGGER context_recovery_relationships_no_delete
BEFORE DELETE ON context_recovery_relationships
BEGIN
    SELECT RAISE(ABORT, 'recovery relationships cannot be deleted');
END;
