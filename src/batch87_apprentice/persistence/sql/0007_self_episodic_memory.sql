CREATE TABLE governed_evaluation_record_anchors (
    evaluation_record_id TEXT PRIMARY KEY,
    evaluation_kind TEXT NOT NULL CHECK (
        evaluation_kind IN ('capability_evaluation', 'maturity_evaluation')
    ),
    project_scope_id TEXT NOT NULL,
    provenance_evidence_id TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    provenance_summary TEXT NOT NULL CHECK (trim(provenance_summary) <> ''),
    current_state TEXT NOT NULL CHECK (
        current_state IN ('registered', 'claimed', 'invalid', 'retired')
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (provenance_evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT
);

CREATE TABLE governed_evaluation_anchor_state_history (
    transition_id TEXT PRIMARY KEY,
    evaluation_record_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    from_state TEXT CHECK (
        from_state IS NULL
        OR from_state IN ('registered', 'claimed', 'invalid', 'retired')
    ),
    to_state TEXT NOT NULL CHECK (
        to_state IN ('registered', 'claimed', 'invalid', 'retired')
    ),
    changed_at TEXT NOT NULL,
    changed_by_principal TEXT NOT NULL CHECK (
        changed_by_principal IN (
            'operator', 'validated_system', 'codex_development_harness'
        )
    ),
    changed_by_entity_id TEXT,
    transition_evidence_id TEXT NOT NULL,
    reason_code TEXT NOT NULL CHECK (trim(reason_code) <> ''),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    UNIQUE (evaluation_record_id, sequence_number),
    FOREIGN KEY (evaluation_record_id)
        REFERENCES governed_evaluation_record_anchors(evaluation_record_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (changed_by_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (transition_evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT,
    CHECK (
        (changed_by_principal = 'operator' AND changed_by_entity_id IS NOT NULL)
        OR changed_by_principal = 'validated_system'
        OR (
            changed_by_principal = 'codex_development_harness'
            AND changed_by_entity_id IS NULL
        )
    )
);

CREATE INDEX governed_evaluation_anchors_project_state
ON governed_evaluation_record_anchors (
    project_scope_id, evaluation_kind, current_state
);

CREATE INDEX governed_evaluation_anchor_history_order
ON governed_evaluation_anchor_state_history (
    evaluation_record_id, sequence_number
);

CREATE TABLE developmental_policy_kinds (
    policy_kind TEXT PRIMARY KEY CHECK (
        policy_kind IN ('capability_stability', 'maturity_progression')
    ),
    status TEXT NOT NULL CHECK (status = 'active')
);

INSERT INTO developmental_policy_kinds (policy_kind, status) VALUES
    ('capability_stability', 'active'),
    ('maturity_progression', 'active');

CREATE TABLE developmental_policy_versions (
    developmental_policy_id TEXT PRIMARY KEY,
    policy_kind TEXT NOT NULL,
    version TEXT NOT NULL CHECK (trim(version) <> ''),
    project_scope_id TEXT NOT NULL,
    configuration_json TEXT NOT NULL CHECK (
        json_valid(configuration_json)
        AND json_type(configuration_json) = 'object'
    ),
    authority_record_id TEXT NOT NULL,
    approval_evidence_id TEXT NOT NULL,
    approved_by_entity_id TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_until TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('approved', 'revoked', 'retired')
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    UNIQUE (policy_kind, version),
    FOREIGN KEY (policy_kind)
        REFERENCES developmental_policy_kinds(policy_kind) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (authority_record_id)
        REFERENCES authority_records(authority_record_id) ON DELETE RESTRICT,
    FOREIGN KEY (approval_evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT,
    FOREIGN KEY (approved_by_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    CHECK (effective_from >= approved_at),
    CHECK (effective_until IS NULL OR effective_until >= effective_from)
);

CREATE INDEX developmental_policy_versions_scope_time
ON developmental_policy_versions (
    project_scope_id, policy_kind, effective_from, effective_until
);

CREATE TABLE trusted_runtime_attestors (
    trusted_attestor_id TEXT PRIMARY KEY,
    attestor_entity_id TEXT NOT NULL,
    project_scope_id TEXT NOT NULL,
    attestation_environment TEXT NOT NULL CHECK (
        attestation_environment IN ('production', 'synthetic_validation')
    ),
    authority_record_id TEXT NOT NULL,
    approval_evidence_id TEXT NOT NULL,
    registered_by_principal TEXT NOT NULL CHECK (
        registered_by_principal = 'operator'
    ),
    registered_by_entity_id TEXT NOT NULL,
    approved_by_entity_id TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_until TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('active', 'revoked', 'retired')
    ),
    supersedes_trusted_attestor_id TEXT UNIQUE,
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (attestor_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (authority_record_id)
        REFERENCES authority_records(authority_record_id) ON DELETE RESTRICT,
    FOREIGN KEY (approval_evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT,
    FOREIGN KEY (registered_by_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (approved_by_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (supersedes_trusted_attestor_id)
        REFERENCES trusted_runtime_attestors(trusted_attestor_id)
        ON DELETE RESTRICT,
    CHECK (effective_from >= approved_at),
    CHECK (effective_until IS NULL OR effective_until >= effective_from),
    CHECK (
        supersedes_trusted_attestor_id IS NULL
        OR supersedes_trusted_attestor_id <> trusted_attestor_id
    )
);

CREATE INDEX trusted_runtime_attestors_scope_environment
ON trusted_runtime_attestors (
    project_scope_id, attestation_environment, attestor_entity_id,
    effective_from, effective_until
);

CREATE TABLE runtime_substrate_attestations (
    substrate_attestation_evidence_id TEXT PRIMARY KEY,
    trusted_attestor_id TEXT NOT NULL,
    attestor_entity_id TEXT NOT NULL,
    project_scope_id TEXT NOT NULL,
    agent_entity_id TEXT NOT NULL,
    runtime_instance_id TEXT NOT NULL,
    attestation_environment TEXT NOT NULL CHECK (
        attestation_environment IN ('production', 'synthetic_validation')
    ),
    base_model TEXT NOT NULL CHECK (trim(base_model) <> ''),
    model_revision TEXT NOT NULL CHECK (trim(model_revision) <> ''),
    runtime_provider TEXT NOT NULL CHECK (trim(runtime_provider) <> ''),
    quantisation TEXT,
    context_limit INTEGER NOT NULL CHECK (context_limit > 0),
    active_adapter TEXT,
    runtime_started_at TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    changed_by_principal TEXT NOT NULL CHECK (
        changed_by_principal IN (
            'validated_system', 'codex_development_harness'
        )
    ),
    changed_by_entity_id TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (substrate_attestation_evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT,
    FOREIGN KEY (trusted_attestor_id)
        REFERENCES trusted_runtime_attestors(trusted_attestor_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (attestor_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (agent_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (runtime_instance_id)
        REFERENCES runtime_instances(runtime_instance_id) ON DELETE RESTRICT,
    FOREIGN KEY (changed_by_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    CHECK (quantisation IS NULL OR trim(quantisation) <> ''),
    CHECK (active_adapter IS NULL OR trim(active_adapter) <> ''),
    CHECK (captured_at >= runtime_started_at),
    CHECK (changed_by_entity_id = attestor_entity_id),
    CHECK (
        (
            attestation_environment = 'production'
            AND changed_by_principal = 'validated_system'
        )
        OR (
            attestation_environment = 'synthetic_validation'
            AND changed_by_principal = 'codex_development_harness'
        )
    )
);

CREATE INDEX runtime_substrate_attestations_scope_runtime
ON runtime_substrate_attestations (
    project_scope_id, runtime_instance_id, attestation_environment, captured_at
);

CREATE TABLE runtime_identities (
    record_id TEXT PRIMARY KEY,
    agent_entity_id TEXT NOT NULL,
    base_model TEXT NOT NULL CHECK (trim(base_model) <> ''),
    model_revision TEXT NOT NULL CHECK (trim(model_revision) <> ''),
    runtime_provider TEXT NOT NULL CHECK (trim(runtime_provider) <> ''),
    quantisation TEXT,
    context_limit INTEGER NOT NULL CHECK (context_limit > 0),
    active_adapter TEXT,
    runtime_started_at TEXT NOT NULL,
    runtime_instance_id TEXT NOT NULL,
    substrate_attestor_entity_id TEXT NOT NULL,
    substrate_attestation_evidence_id TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (agent_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (runtime_instance_id)
        REFERENCES runtime_instances(runtime_instance_id) ON DELETE RESTRICT,
    FOREIGN KEY (substrate_attestor_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (substrate_attestation_evidence_id)
        REFERENCES runtime_substrate_attestations(
            substrate_attestation_evidence_id
        ) ON DELETE RESTRICT,
    UNIQUE (substrate_attestation_evidence_id),
    CHECK (quantisation IS NULL OR trim(quantisation) <> ''),
    CHECK (active_adapter IS NULL OR trim(active_adapter) <> '')
);

CREATE INDEX runtime_identities_agent_runtime
ON runtime_identities (agent_entity_id, runtime_instance_id);

CREATE TABLE capability_observations (
    record_id TEXT PRIMARY KEY,
    capability_name TEXT NOT NULL CHECK (trim(capability_name) <> ''),
    capability_key TEXT NOT NULL CHECK (trim(capability_key) <> ''),
    observation_type TEXT NOT NULL CHECK (
        observation_type IN ('strength', 'weakness', 'unknown')
    ),
    evidence_summary TEXT NOT NULL CHECK (trim(evidence_summary) <> ''),
    sample_size INTEGER NOT NULL CHECK (sample_size > 0),
    stability TEXT NOT NULL CHECK (
        stability IN ('unconfirmed', 'emerging', 'repeated', 'stable')
    ),
    developmental_policy_id TEXT,
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (developmental_policy_id)
        REFERENCES developmental_policy_versions(developmental_policy_id)
        ON DELETE RESTRICT,
    CHECK (
        stability = 'unconfirmed' OR developmental_policy_id IS NOT NULL
    )
);

CREATE INDEX capability_observations_identity
ON capability_observations (capability_key, record_id);

CREATE TABLE capability_observation_evaluations (
    record_id TEXT NOT NULL,
    evaluation_record_id TEXT NOT NULL,
    evaluation_order INTEGER NOT NULL CHECK (evaluation_order >= 0),
    PRIMARY KEY (record_id, evaluation_record_id),
    UNIQUE (record_id, evaluation_order),
    FOREIGN KEY (record_id)
        REFERENCES capability_observations(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (evaluation_record_id)
        REFERENCES governed_evaluation_record_anchors(evaluation_record_id)
        ON DELETE RESTRICT
);

CREATE INDEX capability_observation_evaluations_anchor
ON capability_observation_evaluations (evaluation_record_id);

CREATE TABLE maturity_states (
    record_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL CHECK (
        stage IN (
            'uninitialised', 'oriented', 'apprentice-observer',
            'apprentice-analyst', 'apprentice-proposer',
            'supervised-specialist', 'maturity-review-eligible'
        )
    ),
    entered_at TEXT NOT NULL,
    restrictions_json TEXT NOT NULL CHECK (
        json_valid(restrictions_json)
        AND json_type(restrictions_json) = 'array'
    ),
    next_gate TEXT NOT NULL CHECK (trim(next_gate) <> ''),
    agent_entity_id TEXT NOT NULL,
    developmental_policy_id TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (agent_entity_id)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    FOREIGN KEY (developmental_policy_id)
        REFERENCES developmental_policy_versions(developmental_policy_id)
        ON DELETE RESTRICT
);

CREATE INDEX maturity_states_agent
ON maturity_states (agent_entity_id, record_id);

CREATE TABLE maturity_state_basis_evaluations (
    record_id TEXT NOT NULL,
    evaluation_record_id TEXT NOT NULL,
    evaluation_order INTEGER NOT NULL CHECK (evaluation_order >= 0),
    PRIMARY KEY (record_id, evaluation_record_id),
    UNIQUE (record_id, evaluation_order),
    FOREIGN KEY (record_id)
        REFERENCES maturity_states(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (evaluation_record_id)
        REFERENCES governed_evaluation_record_anchors(evaluation_record_id)
        ON DELETE RESTRICT
);

CREATE INDEX maturity_state_basis_evaluations_anchor
ON maturity_state_basis_evaluations (evaluation_record_id);

CREATE TRIGGER memory_record_types_no_post_seed_insert
BEFORE INSERT ON memory_record_types
BEGIN
    SELECT RAISE(ABORT, 'memory record types are migration-seeded only');
END;

CREATE TRIGGER memory_approval_authorities_no_post_seed_insert
BEFORE INSERT ON memory_record_approval_authorities
BEGIN
    SELECT RAISE(ABORT, 'memory approval authorities are migration-seeded only');
END;

CREATE TRIGGER developmental_policy_kinds_no_insert
BEFORE INSERT ON developmental_policy_kinds
BEGIN
    SELECT RAISE(ABORT, 'developmental policy kinds are migration-seeded only');
END;

CREATE TRIGGER developmental_policy_kinds_immutable
BEFORE UPDATE ON developmental_policy_kinds
BEGIN
    SELECT RAISE(ABORT, 'developmental policy kinds are immutable');
END;

CREATE TRIGGER developmental_policy_kinds_no_delete
BEFORE DELETE ON developmental_policy_kinds
BEGIN
    SELECT RAISE(ABORT, 'developmental policy kinds cannot be deleted');
END;

CREATE TRIGGER governed_evaluation_anchor_insert_guard
BEFORE INSERT ON governed_evaluation_record_anchors
WHEN NEW.current_state <> 'registered'
OR NOT EXISTS (
    SELECT 1
    FROM scopes
    WHERE scope_id = NEW.project_scope_id
      AND scope_kind = 'project'
      AND status = 'active'
)
OR NOT EXISTS (
    SELECT 1
    FROM evidence_items
    WHERE evidence_id = NEW.provenance_evidence_id
      AND integrity_status = 'valid'
      AND evidence_kind NOT IN (
          'model_output', 'controlled_prompt', 'controlled_output'
      )
)
OR EXISTS (
    SELECT 1
    FROM controlled_resilience_evidence
    WHERE raw_prompt_evidence_id = NEW.provenance_evidence_id
       OR raw_output_evidence_id = NEW.provenance_evidence_id
)
OR EXISTS (
    SELECT 1
    FROM record_evidence_links AS link
    JOIN records AS record ON record.record_id = link.record_id
    WHERE link.evidence_id = NEW.provenance_evidence_id
      AND record.record_family = 'evaluation_evidence'
      AND record.record_type = 'controlled_governance_resilience_run'
)
BEGIN
    SELECT RAISE(
        ABORT,
        'evaluation anchor requires active project scope and valid non-controlled provenance'
    );
END;

CREATE TRIGGER governed_evaluation_anchor_history_guard
BEFORE INSERT ON governed_evaluation_anchor_state_history
WHEN NOT EXISTS (
    SELECT 1
    FROM evidence_items
    WHERE evidence_id = NEW.transition_evidence_id
      AND integrity_status = 'valid'
      AND evidence_kind NOT IN (
          'model_output', 'controlled_prompt', 'controlled_output'
      )
)
OR EXISTS (
    SELECT 1
    FROM controlled_resilience_evidence
    WHERE raw_prompt_evidence_id = NEW.transition_evidence_id
       OR raw_output_evidence_id = NEW.transition_evidence_id
)
OR (
    NOT EXISTS (
        SELECT 1
        FROM governed_evaluation_anchor_state_history
        WHERE evaluation_record_id = NEW.evaluation_record_id
    )
    AND (
        NEW.sequence_number <> 0
        OR NEW.from_state IS NOT NULL
        OR NEW.to_state <> 'registered'
        OR NEW.transition_evidence_id <> (
            SELECT provenance_evidence_id
            FROM governed_evaluation_record_anchors
            WHERE evaluation_record_id = NEW.evaluation_record_id
        )
    )
)
OR (
    EXISTS (
        SELECT 1
        FROM governed_evaluation_anchor_state_history
        WHERE evaluation_record_id = NEW.evaluation_record_id
    )
    AND (
        NEW.sequence_number <> (
            SELECT MAX(sequence_number) + 1
            FROM governed_evaluation_anchor_state_history
            WHERE evaluation_record_id = NEW.evaluation_record_id
        )
        OR NEW.from_state <> (
            SELECT current_state
            FROM governed_evaluation_record_anchors
            WHERE evaluation_record_id = NEW.evaluation_record_id
        )
        OR (
            NEW.from_state = 'registered'
            AND NEW.to_state NOT IN ('claimed', 'invalid', 'retired')
        )
        OR (
            NEW.from_state = 'claimed'
            AND NEW.to_state NOT IN ('invalid', 'retired')
        )
        OR (
            NEW.from_state = 'invalid'
            AND NEW.to_state <> 'retired'
        )
        OR NEW.from_state = 'retired'
    )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'evaluation anchor transition lacks valid evidence or append-only ordering'
    );
END;

CREATE TRIGGER governed_evaluation_anchor_state_update_guard
BEFORE UPDATE OF current_state ON governed_evaluation_record_anchors
WHEN NEW.current_state <> OLD.current_state
AND NOT EXISTS (
    SELECT 1
    FROM governed_evaluation_anchor_state_history
    WHERE evaluation_record_id = OLD.evaluation_record_id
      AND from_state = OLD.current_state
      AND to_state = NEW.current_state
      AND sequence_number = (
          SELECT MAX(sequence_number)
          FROM governed_evaluation_anchor_state_history
          WHERE evaluation_record_id = OLD.evaluation_record_id
      )
)
BEGIN
    SELECT RAISE(ABORT, 'evaluation anchor state requires an append-only transition');
END;

CREATE TRIGGER governed_evaluation_anchor_core_immutable
BEFORE UPDATE OF
    evaluation_record_id, evaluation_kind, project_scope_id,
    provenance_evidence_id, registered_at, provenance_summary,
    canonical_json, content_hash
ON governed_evaluation_record_anchors
BEGIN
    SELECT RAISE(ABORT, 'evaluation anchor identity and content are immutable');
END;

CREATE TRIGGER governed_evaluation_anchor_no_delete
BEFORE DELETE ON governed_evaluation_record_anchors
BEGIN
    SELECT RAISE(ABORT, 'evaluation anchors cannot be deleted');
END;

CREATE TRIGGER governed_evaluation_anchor_history_immutable
BEFORE UPDATE ON governed_evaluation_anchor_state_history
BEGIN
    SELECT RAISE(ABORT, 'evaluation anchor history is immutable');
END;

CREATE TRIGGER governed_evaluation_anchor_history_no_delete
BEFORE DELETE ON governed_evaluation_anchor_state_history
BEGIN
    SELECT RAISE(ABORT, 'evaluation anchor history cannot be deleted');
END;

CREATE TRIGGER developmental_policy_configuration_guard
BEFORE INSERT ON developmental_policy_versions
WHEN NEW.status <> 'approved'
OR (
    NEW.policy_kind = 'capability_stability'
    AND (
        json_type(
            NEW.configuration_json,
            '$.allow_registered_for_unconfirmed'
        ) NOT IN ('true', 'false')
        OR json_type(
            NEW.configuration_json,
            '$.stability_requirements'
        ) <> 'object'
        OR EXISTS (
            SELECT 1
            FROM (
                SELECT 'emerging' AS stability
                UNION ALL SELECT 'repeated'
                UNION ALL SELECT 'stable'
            ) AS required
            WHERE json_type(
                NEW.configuration_json,
                '$.stability_requirements.' || required.stability
                    || '.minimum_claimed_evaluations'
            ) <> 'integer'
            OR json_extract(
                NEW.configuration_json,
                '$.stability_requirements.' || required.stability
                    || '.minimum_claimed_evaluations'
            ) < 2
            OR json_type(
                NEW.configuration_json,
                '$.stability_requirements.' || required.stability
                    || '.minimum_sample_size'
            ) <> 'integer'
            OR json_extract(
                NEW.configuration_json,
                '$.stability_requirements.' || required.stability
                    || '.minimum_sample_size'
            ) < 1
        )
    )
)
OR (
    NEW.policy_kind = 'maturity_progression'
    AND (
        json_type(NEW.configuration_json, '$.stage_transitions') <> 'array'
        OR json_array_length(
            json_extract(NEW.configuration_json, '$.stage_transitions')
        ) < 1
        OR EXISTS (
            SELECT 1
            FROM json_each(
                NEW.configuration_json,
                '$.stage_transitions'
            ) AS transition
            WHERE json_type(transition.value, '$.to_stage') <> 'text'
               OR json_extract(transition.value, '$.to_stage') NOT IN (
                   'uninitialised', 'oriented', 'apprentice-observer',
                   'apprentice-analyst', 'apprentice-proposer',
                   'supervised-specialist', 'maturity-review-eligible'
               )
               OR (
                   json_type(transition.value, '$.from_stage') <> 'null'
                   AND json_extract(transition.value, '$.from_stage') NOT IN (
                       'uninitialised', 'oriented', 'apprentice-observer',
                       'apprentice-analyst', 'apprentice-proposer',
                       'supervised-specialist', 'maturity-review-eligible'
                   )
               )
               OR json_extract(transition.value, '$.from_stage')
                    IS json_extract(transition.value, '$.to_stage')
               OR json_type(
                    transition.value,
                    '$.minimum_claimed_evaluations'
               ) <> 'integer'
               OR json_extract(
                    transition.value,
                    '$.minimum_claimed_evaluations'
               ) < 1
        )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'developmental policy configuration is invalid');
END;

CREATE TRIGGER developmental_policy_authority_guard
BEFORE INSERT ON developmental_policy_versions
WHEN NOT EXISTS (
    SELECT 1
    FROM authority_records AS authority
    JOIN authority_record_evidence AS link
      ON link.authority_record_id = authority.authority_record_id
    JOIN evidence_items AS evidence
      ON evidence.evidence_id = link.evidence_id
    WHERE authority.authority_record_id = NEW.authority_record_id
      AND authority.authority_class = 'nolan_byte_approved'
      AND authority.effect = 'allow'
      AND authority.status = 'active'
      AND authority.project_scope_id = NEW.project_scope_id
      AND authority.issuer_entity_id = NEW.approved_by_entity_id
      AND authority.effective_from <= NEW.approved_at
      AND (
          authority.effective_until IS NULL
          OR authority.effective_until >= NEW.approved_at
      )
      AND link.evidence_id = NEW.approval_evidence_id
      AND evidence.integrity_status = 'valid'
      AND evidence.evidence_kind NOT IN (
          'model_output', 'controlled_prompt', 'controlled_output'
      )
)
OR EXISTS (
    SELECT 1
    FROM authority_revocations
    WHERE authority_record_id = NEW.authority_record_id
      AND revoked_at <= NEW.approved_at
)
OR EXISTS (
    SELECT 1
    FROM controlled_resilience_evidence
    WHERE raw_prompt_evidence_id = NEW.approval_evidence_id
       OR raw_output_evidence_id = NEW.approval_evidence_id
)
BEGIN
    SELECT RAISE(
        ABORT,
        'developmental policy requires exact active Nolan-Byte authority evidence'
    );
END;

CREATE TRIGGER developmental_policy_versions_immutable
BEFORE UPDATE ON developmental_policy_versions
BEGIN
    SELECT RAISE(ABORT, 'developmental policy versions are immutable');
END;

CREATE TRIGGER developmental_policy_versions_no_delete
BEFORE DELETE ON developmental_policy_versions
BEGIN
    SELECT RAISE(ABORT, 'developmental policy versions cannot be deleted');
END;

CREATE TRIGGER trusted_runtime_attestor_contract_guard
BEFORE INSERT ON trusted_runtime_attestors
WHEN NOT EXISTS (
    SELECT 1
    FROM entities AS attestor
    JOIN scopes AS project ON project.scope_id = NEW.project_scope_id
    JOIN entities AS registrar
      ON registrar.entity_id = NEW.registered_by_entity_id
    JOIN entities AS approver
      ON approver.entity_id = NEW.approved_by_entity_id
    JOIN authority_records AS authority
      ON authority.authority_record_id = NEW.authority_record_id
    JOIN authority_record_evidence AS link
      ON link.authority_record_id = authority.authority_record_id
     AND link.evidence_id = NEW.approval_evidence_id
    JOIN evidence_items AS evidence
      ON evidence.evidence_id = link.evidence_id
    LEFT JOIN authority_revocations AS revocation
      ON revocation.authority_record_id = authority.authority_record_id
     AND revocation.revoked_at <= NEW.approved_at
    WHERE attestor.entity_id = NEW.attestor_entity_id
      AND attestor.entity_kind IN ('system', 'component')
      AND attestor.status = 'active'
      AND project.scope_kind = 'project'
      AND project.status = 'active'
      AND NEW.registered_by_principal = 'operator'
      AND registrar.entity_kind = 'person'
      AND registrar.status = 'active'
      AND approver.entity_kind = 'person'
      AND approver.status = 'active'
      AND authority.authority_class = 'nolan_byte_approved'
      AND authority.effect = 'allow'
      AND authority.status = 'active'
      AND authority.project_scope_id = NEW.project_scope_id
      AND authority.issuer_entity_id = NEW.approved_by_entity_id
      AND authority.effective_from <= NEW.approved_at
      AND (
          authority.effective_until IS NULL
          OR authority.effective_until >= NEW.approved_at
      )
      AND revocation.authority_record_id IS NULL
      AND evidence.integrity_status = 'valid'
      AND evidence.evidence_kind NOT IN (
          'model_output', 'controlled_prompt', 'controlled_output'
      )
)
OR EXISTS (
    SELECT 1
    FROM controlled_resilience_evidence
    WHERE raw_prompt_evidence_id = NEW.approval_evidence_id
       OR raw_output_evidence_id = NEW.approval_evidence_id
)
OR EXISTS (
    SELECT 1
    FROM record_evidence_links AS link
    JOIN records AS record ON record.record_id = link.record_id
    WHERE link.evidence_id = NEW.approval_evidence_id
      AND record.record_family = 'evaluation_evidence'
      AND record.record_type = 'controlled_governance_resilience_run'
)
OR (
    NEW.supersedes_trusted_attestor_id IS NULL
    AND (
        NEW.status <> 'active'
        OR EXISTS (
            SELECT 1
            FROM trusted_runtime_attestors AS existing
            WHERE existing.attestor_entity_id = NEW.attestor_entity_id
              AND existing.project_scope_id = NEW.project_scope_id
              AND existing.attestation_environment =
                  NEW.attestation_environment
        )
    )
)
OR (
    NEW.supersedes_trusted_attestor_id IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM trusted_runtime_attestors AS prior
        WHERE prior.trusted_attestor_id =
              NEW.supersedes_trusted_attestor_id
          AND prior.attestor_entity_id = NEW.attestor_entity_id
          AND prior.project_scope_id = NEW.project_scope_id
          AND prior.attestation_environment = NEW.attestation_environment
          AND prior.effective_from <= NEW.effective_from
          AND NOT EXISTS (
              SELECT 1
              FROM trusted_runtime_attestors AS later
              WHERE later.supersedes_trusted_attestor_id =
                    prior.trusted_attestor_id
          )
    )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'trusted runtime attestor requires operator registration and exact Nolan-Byte approval'
    );
END;

CREATE TRIGGER runtime_substrate_attestation_contract_guard
BEFORE INSERT ON runtime_substrate_attestations
WHEN NOT EXISTS (
    SELECT 1
    FROM trusted_runtime_attestors AS trusted
    JOIN entities AS attestor
      ON attestor.entity_id = trusted.attestor_entity_id
    JOIN scopes AS project ON project.scope_id = trusted.project_scope_id
    JOIN entities AS agent ON agent.entity_id = NEW.agent_entity_id
    JOIN runtime_instances AS runtime
      ON runtime.runtime_instance_id = NEW.runtime_instance_id
    JOIN evidence_items AS evidence
      ON evidence.evidence_id = NEW.substrate_attestation_evidence_id
    JOIN evidence_inline_text AS inline
      ON inline.evidence_id = evidence.evidence_id
    JOIN authority_records AS authority
      ON authority.authority_record_id = trusted.authority_record_id
    JOIN authority_record_evidence AS authority_link
      ON authority_link.authority_record_id = authority.authority_record_id
     AND authority_link.evidence_id = trusted.approval_evidence_id
    LEFT JOIN authority_revocations AS revocation
      ON revocation.authority_record_id = authority.authority_record_id
     AND revocation.revoked_at <= NEW.captured_at
    WHERE trusted.trusted_attestor_id = NEW.trusted_attestor_id
      AND trusted.attestor_entity_id = NEW.attestor_entity_id
      AND trusted.project_scope_id = NEW.project_scope_id
      AND trusted.attestation_environment = NEW.attestation_environment
      AND trusted.status = 'active'
      AND trusted.effective_from <= NEW.captured_at
      AND (
          trusted.effective_until IS NULL
          OR trusted.effective_until >= NEW.captured_at
      )
      AND NOT EXISTS (
          SELECT 1
          FROM trusted_runtime_attestors AS later
          WHERE later.supersedes_trusted_attestor_id =
                trusted.trusted_attestor_id
            AND later.effective_from <= NEW.captured_at
      )
      AND attestor.entity_kind IN ('system', 'component')
      AND attestor.status = 'active'
      AND project.scope_kind = 'project'
      AND project.status = 'active'
      AND agent.entity_kind = 'agent'
      AND agent.status = 'active'
      AND runtime.status = 'running'
      AND runtime.stopped_at IS NULL
      AND runtime.started_at = NEW.runtime_started_at
      AND evidence.evidence_kind = 'system_event'
      AND evidence.storage_kind = 'inline_text'
      AND evidence.integrity_status = 'valid'
      AND evidence.captured_by_entity = NEW.attestor_entity_id
      AND evidence.captured_at = NEW.captured_at
      AND inline.encoding = 'utf-8'
      AND inline.content = NEW.canonical_json
      AND authority.authority_class = 'nolan_byte_approved'
      AND authority.effect = 'allow'
      AND authority.status = 'active'
      AND authority.project_scope_id = NEW.project_scope_id
      AND authority.issuer_entity_id = trusted.approved_by_entity_id
      AND authority.effective_from <= NEW.captured_at
      AND (
          authority.effective_until IS NULL
          OR authority.effective_until >= NEW.captured_at
      )
      AND revocation.authority_record_id IS NULL
)
OR lower(trim(NEW.base_model)) IN (
    'unknown', 'none', 'null', 'n/a', 'na', 'placeholder', 'planned',
    'future', 'previous', 'tbd', 'unset', 'not_applicable', 'not-applicable'
)
OR lower(trim(NEW.model_revision)) IN (
    'unknown', 'none', 'null', 'n/a', 'na', 'placeholder', 'planned',
    'future', 'previous', 'tbd', 'unset', 'not_applicable', 'not-applicable'
)
OR lower(trim(NEW.runtime_provider)) IN (
    'unknown', 'none', 'null', 'n/a', 'na', 'placeholder', 'planned',
    'future', 'previous', 'tbd', 'unset', 'not_applicable', 'not-applicable'
)
BEGIN
    SELECT RAISE(
        ABORT,
        'runtime substrate attestation requires exact governed ingestion'
    );
END;

CREATE TRIGGER factual_self_record_evidence_guard
BEFORE INSERT ON record_evidence_links
WHEN EXISTS (
    SELECT 1
    FROM records
    WHERE record_id = NEW.record_id
      AND record_family = 'self_model'
      AND record_type IN (
          'runtime_identity', 'capability_observation', 'maturity_state'
      )
)
AND (
    EXISTS (
        SELECT 1
        FROM evidence_items
        WHERE evidence_id = NEW.evidence_id
          AND evidence_kind IN ('controlled_prompt', 'controlled_output')
    )
    OR EXISTS (
        SELECT 1
        FROM controlled_resilience_evidence
        WHERE raw_prompt_evidence_id = NEW.evidence_id
           OR raw_output_evidence_id = NEW.evidence_id
    )
    OR EXISTS (
        SELECT 1
        FROM record_evidence_links AS existing_link
        JOIN records AS existing_record
          ON existing_record.record_id = existing_link.record_id
        WHERE existing_link.evidence_id = NEW.evidence_id
          AND existing_record.record_family = 'evaluation_evidence'
          AND existing_record.record_type =
              'controlled_governance_resilience_run'
    )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'controlled-resilience evidence cannot enter factual self memory'
    );
END;

CREATE TRIGGER runtime_identity_evidence_link_contract_guard
BEFORE INSERT ON record_evidence_links
WHEN EXISTS (
    SELECT 1
    FROM records
    WHERE record_id = NEW.record_id
      AND record_family = 'self_model'
      AND record_type = 'runtime_identity'
)
AND (
    NEW.relationship <> 'supports'
    OR NOT EXISTS (
        SELECT 1
        FROM runtime_identities AS identity
        WHERE identity.record_id = NEW.record_id
          AND identity.substrate_attestation_evidence_id = NEW.evidence_id
    )
    OR EXISTS (
        SELECT 1
        FROM record_evidence_links AS existing
        WHERE existing.record_id = NEW.record_id
    )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'runtime identity requires exactly one supporting attestation evidence link'
    );
END;

CREATE TRIGGER runtime_identity_contract_guard
BEFORE INSERT ON runtime_identities
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS record
    JOIN entities AS agent ON agent.entity_id = NEW.agent_entity_id
    JOIN scopes AS project ON project.scope_id = record.project_scope_id
    JOIN runtime_instances AS runtime
      ON runtime.runtime_instance_id = NEW.runtime_instance_id
    WHERE record.record_id = NEW.record_id
      AND record.record_family = 'self_model'
      AND record.record_type = 'runtime_identity'
      AND record.lifecycle_state = 'observed'
      AND record.approval_status = 'not_required'
      AND record.authority_class = 'validated_system_evidence'
      AND record.agent_write_policy = 'prohibited'
      AND record.source_kind = 'runtime_event'
      AND record.integrity_status = 'valid'
      AND record.subject_entity_id = NEW.agent_entity_id
      AND record.created_by_runtime_id = NEW.runtime_instance_id
      AND agent.entity_kind = 'agent'
      AND agent.status = 'active'
      AND project.scope_kind = 'project'
      AND project.status = 'active'
      AND runtime.status = 'running'
      AND runtime.stopped_at IS NULL
      AND runtime.started_at = NEW.runtime_started_at
)
OR lower(trim(NEW.base_model)) IN (
    'unknown', 'none', 'null', 'n/a', 'na', 'placeholder', 'planned',
    'future', 'previous', 'tbd', 'unset', 'not_applicable', 'not-applicable'
)
OR lower(trim(NEW.model_revision)) IN (
    'unknown', 'none', 'null', 'n/a', 'na', 'placeholder', 'planned',
    'future', 'previous', 'tbd', 'unset', 'not_applicable', 'not-applicable'
)
OR lower(trim(NEW.runtime_provider)) IN (
    'unknown', 'none', 'null', 'n/a', 'na', 'placeholder', 'planned',
    'future', 'previous', 'tbd', 'unset', 'not_applicable', 'not-applicable'
)
OR NOT EXISTS (
    SELECT 1
    FROM runtime_substrate_attestations AS attestation
    JOIN trusted_runtime_attestors AS trusted
      ON trusted.trusted_attestor_id = attestation.trusted_attestor_id
    JOIN evidence_items AS evidence
      ON evidence.evidence_id =
         attestation.substrate_attestation_evidence_id
    JOIN evidence_inline_text AS inline
      ON inline.evidence_id = evidence.evidence_id
    JOIN records AS record ON record.record_id = NEW.record_id
    JOIN authority_records AS authority
      ON authority.authority_record_id = trusted.authority_record_id
    LEFT JOIN authority_revocations AS revocation
      ON revocation.authority_record_id = authority.authority_record_id
     AND revocation.revoked_at <= record.created_at
    WHERE attestation.substrate_attestation_evidence_id =
          NEW.substrate_attestation_evidence_id
      AND attestation.attestation_environment = 'production'
      AND attestation.changed_by_principal = 'validated_system'
      AND attestation.changed_by_entity_id =
          attestation.attestor_entity_id
      AND attestation.attestor_entity_id =
          NEW.substrate_attestor_entity_id
      AND attestation.project_scope_id = record.project_scope_id
      AND attestation.agent_entity_id = NEW.agent_entity_id
      AND attestation.runtime_instance_id = NEW.runtime_instance_id
      AND attestation.base_model = NEW.base_model
      AND attestation.model_revision = NEW.model_revision
      AND attestation.runtime_provider = NEW.runtime_provider
      AND attestation.quantisation IS NEW.quantisation
      AND attestation.context_limit = NEW.context_limit
      AND attestation.active_adapter IS NEW.active_adapter
      AND attestation.runtime_started_at = NEW.runtime_started_at
      AND attestation.captured_at >= NEW.runtime_started_at
      AND attestation.captured_at <= record.created_at
      AND trusted.attestor_entity_id =
          NEW.substrate_attestor_entity_id
      AND trusted.project_scope_id = record.project_scope_id
      AND trusted.attestation_environment = 'production'
      AND trusted.status = 'active'
      AND trusted.effective_from <= record.created_at
      AND (
          trusted.effective_until IS NULL
          OR trusted.effective_until >= record.created_at
      )
      AND NOT EXISTS (
          SELECT 1
          FROM trusted_runtime_attestors AS later
          WHERE later.supersedes_trusted_attestor_id =
                trusted.trusted_attestor_id
            AND later.effective_from <= record.created_at
      )
      AND evidence.evidence_kind = 'system_event'
      AND evidence.integrity_status = 'valid'
      AND evidence.storage_kind = 'inline_text'
      AND evidence.captured_by_entity =
          NEW.substrate_attestor_entity_id
      AND evidence.captured_at = attestation.captured_at
      AND inline.encoding = 'utf-8'
      AND inline.content = attestation.canonical_json
      AND authority.authority_class = 'nolan_byte_approved'
      AND authority.effect = 'allow'
      AND authority.status = 'active'
      AND authority.project_scope_id = record.project_scope_id
      AND authority.issuer_entity_id = trusted.approved_by_entity_id
      AND authority.effective_from <= record.created_at
      AND (
          authority.effective_until IS NULL
          OR authority.effective_until >= record.created_at
      )
      AND revocation.authority_record_id IS NULL
)
BEGIN
    SELECT RAISE(
        ABORT,
        'runtime identity requires exact running substrate attestation'
    );
END;

CREATE TRIGGER capability_observation_contract_guard
BEFORE INSERT ON capability_observations
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS record
    JOIN entities AS agent ON agent.entity_id = record.subject_entity_id
    JOIN scopes AS project ON project.scope_id = record.project_scope_id
    WHERE record.record_id = NEW.record_id
      AND record.record_family = 'self_model'
      AND record.record_type = 'capability_observation'
      AND record.lifecycle_state = 'candidate'
      AND record.approval_status = 'pending'
      AND record.agent_write_policy = 'candidate_only'
      AND record.integrity_status = 'valid'
      AND agent.entity_kind = 'agent'
      AND agent.status = 'active'
      AND project.scope_kind = 'project'
      AND project.status = 'active'
)
OR (
    NEW.developmental_policy_id IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM developmental_policy_versions AS policy
        JOIN records AS record ON record.record_id = NEW.record_id
        WHERE policy.developmental_policy_id = NEW.developmental_policy_id
          AND policy.policy_kind = 'capability_stability'
          AND policy.project_scope_id = record.project_scope_id
    )
)
BEGIN
    SELECT RAISE(ABORT, 'capability observation violates its C1 contract');
END;

CREATE TRIGGER capability_observation_evaluation_guard
BEFORE INSERT ON capability_observation_evaluations
WHEN NEW.evaluation_order <> (
    SELECT COUNT(*)
    FROM capability_observation_evaluations
    WHERE record_id = NEW.record_id
)
OR NOT EXISTS (
    SELECT 1
    FROM capability_observations AS capability
    JOIN records AS record ON record.record_id = capability.record_id
    JOIN governed_evaluation_record_anchors AS anchor
      ON anchor.evaluation_record_id = NEW.evaluation_record_id
    WHERE capability.record_id = NEW.record_id
      AND anchor.evaluation_kind = 'capability_evaluation'
      AND anchor.project_scope_id = record.project_scope_id
      AND anchor.current_state IN ('registered', 'claimed')
)
BEGIN
    SELECT RAISE(
        ABORT,
        'capability evaluation link is out of order, wrong-kind, or cross-project'
    );
END;

CREATE TRIGGER maturity_state_contract_guard
BEFORE INSERT ON maturity_states
WHEN NOT EXISTS (
    SELECT 1
    FROM records AS record
    JOIN entities AS agent ON agent.entity_id = NEW.agent_entity_id
    JOIN scopes AS project ON project.scope_id = record.project_scope_id
    JOIN developmental_policy_versions AS policy
      ON policy.developmental_policy_id = NEW.developmental_policy_id
    WHERE record.record_id = NEW.record_id
      AND record.record_family = 'self_model'
      AND record.record_type = 'maturity_state'
      AND record.lifecycle_state = 'reviewed'
      AND record.approval_status = 'pending'
      AND record.agent_write_policy = 'prohibited'
      AND record.integrity_status = 'valid'
      AND record.subject_entity_id = NEW.agent_entity_id
      AND agent.entity_kind = 'agent'
      AND agent.status = 'active'
      AND project.scope_kind = 'project'
      AND project.status = 'active'
      AND policy.policy_kind = 'maturity_progression'
      AND policy.project_scope_id = record.project_scope_id
)
BEGIN
    SELECT RAISE(ABORT, 'maturity state violates its C1 contract');
END;

CREATE TRIGGER maturity_state_basis_guard
BEFORE INSERT ON maturity_state_basis_evaluations
WHEN NEW.evaluation_order <> (
    SELECT COUNT(*)
    FROM maturity_state_basis_evaluations
    WHERE record_id = NEW.record_id
)
OR NOT EXISTS (
    SELECT 1
    FROM maturity_states AS maturity
    JOIN records AS record ON record.record_id = maturity.record_id
    JOIN governed_evaluation_record_anchors AS anchor
      ON anchor.evaluation_record_id = NEW.evaluation_record_id
    WHERE maturity.record_id = NEW.record_id
      AND anchor.evaluation_kind = 'maturity_evaluation'
      AND anchor.project_scope_id = record.project_scope_id
      AND anchor.current_state IN ('registered', 'claimed')
)
BEGIN
    SELECT RAISE(
        ABORT,
        'maturity basis link is out of order, wrong-kind, or cross-project'
    );
END;

CREATE TRIGGER factual_self_activation_approval_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN NEW.record_family = 'self_model'
AND NEW.record_type IN ('capability_observation', 'maturity_state')
AND NEW.lifecycle_state = 'active'
AND OLD.lifecycle_state <> 'active'
AND NOT EXISTS (
    SELECT 1
    FROM memory_record_approval_transitions AS transition
    JOIN authority_records AS authority
      ON authority.authority_record_id = transition.authority_record_id
    LEFT JOIN authority_revocations AS revocation
      ON revocation.authority_record_id = authority.authority_record_id
     AND revocation.revoked_at <= (
         SELECT changed_at
         FROM memory_record_lifecycle_transitions
         WHERE record_id = NEW.record_id
           AND to_state = 'active'
         ORDER BY sequence_number DESC
         LIMIT 1
     )
    WHERE transition.record_id = NEW.record_id
      AND transition.to_status = 'approved'
      AND authority.authority_class = 'nolan_byte_approved'
      AND authority.effect = 'allow'
      AND authority.status = 'active'
      AND authority.project_scope_id = NEW.project_scope_id
      AND revocation.authority_record_id IS NULL
    ORDER BY transition.sequence_number DESC
    LIMIT 1
)
BEGIN
    SELECT RAISE(
        ABORT,
        'factual self activation requires current Nolan-Byte approval'
    );
END;

CREATE TRIGGER runtime_identity_activation_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN NEW.record_family = 'self_model'
AND NEW.record_type = 'runtime_identity'
AND NEW.lifecycle_state = 'active'
AND OLD.lifecycle_state <> 'active'
AND (
    NOT EXISTS (
        SELECT 1
        FROM runtime_identities AS identity
        JOIN runtime_instances AS runtime
          ON runtime.runtime_instance_id = identity.runtime_instance_id
        JOIN runtime_substrate_attestations AS attestation
          ON attestation.substrate_attestation_evidence_id =
             identity.substrate_attestation_evidence_id
        JOIN trusted_runtime_attestors AS trusted
          ON trusted.trusted_attestor_id =
             attestation.trusted_attestor_id
        JOIN record_evidence_links AS link
          ON link.record_id = identity.record_id
         AND link.evidence_id = identity.substrate_attestation_evidence_id
         AND link.relationship = 'supports'
        WHERE identity.record_id = NEW.record_id
          AND (
              SELECT COUNT(*)
              FROM record_evidence_links AS exact_link
              WHERE exact_link.record_id = identity.record_id
          ) = 1
          AND runtime.status = 'running'
          AND runtime.stopped_at IS NULL
          AND attestation.attestation_environment = 'production'
          AND attestation.changed_by_principal = 'validated_system'
          AND attestation.changed_by_entity_id =
              identity.substrate_attestor_entity_id
          AND attestation.attestor_entity_id =
              identity.substrate_attestor_entity_id
          AND attestation.project_scope_id = NEW.project_scope_id
          AND attestation.agent_entity_id = identity.agent_entity_id
          AND attestation.runtime_instance_id =
              identity.runtime_instance_id
          AND attestation.base_model = identity.base_model
          AND attestation.model_revision = identity.model_revision
          AND attestation.runtime_provider = identity.runtime_provider
          AND attestation.quantisation IS identity.quantisation
          AND attestation.context_limit = identity.context_limit
          AND attestation.active_adapter IS identity.active_adapter
          AND attestation.runtime_started_at =
              identity.runtime_started_at
          AND trusted.attestor_entity_id =
              identity.substrate_attestor_entity_id
          AND trusted.project_scope_id = NEW.project_scope_id
          AND trusted.attestation_environment = 'production'
          AND trusted.status = 'active'
          AND trusted.effective_from <= NEW.created_at
          AND (
              trusted.effective_until IS NULL
              OR trusted.effective_until >= NEW.created_at
          )
          AND NOT EXISTS (
              SELECT 1
              FROM trusted_runtime_attestors AS later
              WHERE later.supersedes_trusted_attestor_id =
                    trusted.trusted_attestor_id
                AND later.effective_from <= NEW.created_at
          )
    )
    OR EXISTS (
        SELECT 1
        FROM runtime_identities AS candidate
        JOIN runtime_identities AS existing
          ON existing.agent_entity_id = candidate.agent_entity_id
        JOIN records AS existing_record
          ON existing_record.record_id = existing.record_id
        WHERE candidate.record_id = NEW.record_id
          AND existing.record_id <> NEW.record_id
          AND existing_record.project_scope_id = NEW.project_scope_id
          AND existing_record.lifecycle_state = 'active'
    )
    OR (
        NEW.supersedes_record_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1
            FROM runtime_identities AS candidate
            JOIN runtime_identities AS prior
              ON prior.record_id = NEW.supersedes_record_id
            JOIN records AS prior_record
              ON prior_record.record_id = prior.record_id
            JOIN record_relationships AS relationship
              ON relationship.source_record_id = NEW.record_id
             AND relationship.target_record_id = prior.record_id
             AND relationship.relationship_type = 'supersedes'
             AND relationship.relationship_grant_id IS NOT NULL
            WHERE candidate.record_id = NEW.record_id
              AND candidate.agent_entity_id = prior.agent_entity_id
              AND prior_record.project_scope_id = NEW.project_scope_id
              AND prior_record.lifecycle_state = 'superseded'
        )
    )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'runtime identity activation is false, duplicate, or silently replaces state'
    );
END;

CREATE TRIGGER capability_observation_activation_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN NEW.record_family = 'self_model'
AND NEW.record_type = 'capability_observation'
AND NEW.lifecycle_state = 'active'
AND OLD.lifecycle_state <> 'active'
AND (
    NOT EXISTS (
        SELECT 1 FROM capability_observations
        WHERE record_id = NEW.record_id
    )
    OR (
        SELECT COUNT(*)
        FROM capability_observation_evaluations
        WHERE record_id = NEW.record_id
    ) <> (
        SELECT sample_size
        FROM capability_observations
        WHERE record_id = NEW.record_id
    )
    OR EXISTS (
        SELECT 1
        FROM capability_observation_evaluations AS link
        JOIN governed_evaluation_record_anchors AS anchor
          ON anchor.evaluation_record_id = link.evaluation_record_id
        WHERE link.record_id = NEW.record_id
          AND anchor.current_state IN ('invalid', 'retired')
    )
    OR (
        (
            SELECT stability FROM capability_observations
            WHERE record_id = NEW.record_id
        ) = 'unconfirmed'
        AND EXISTS (
            SELECT 1
            FROM capability_observation_evaluations AS link
            JOIN governed_evaluation_record_anchors AS anchor
              ON anchor.evaluation_record_id = link.evaluation_record_id
            WHERE link.record_id = NEW.record_id
              AND anchor.current_state = 'registered'
        )
        AND NOT EXISTS (
            SELECT 1
            FROM capability_observations AS capability
            JOIN developmental_policy_versions AS policy
              ON policy.developmental_policy_id =
                 capability.developmental_policy_id
            WHERE capability.record_id = NEW.record_id
              AND policy.policy_kind = 'capability_stability'
              AND policy.status = 'approved'
              AND json_extract(
                  policy.configuration_json,
                  '$.allow_registered_for_unconfirmed'
              ) = 1
        )
    )
    OR (
        (
            SELECT stability FROM capability_observations
            WHERE record_id = NEW.record_id
        ) IN ('emerging', 'repeated', 'stable')
        AND (
            EXISTS (
                SELECT 1
                FROM capability_observation_evaluations AS link
                JOIN governed_evaluation_record_anchors AS anchor
                  ON anchor.evaluation_record_id = link.evaluation_record_id
                WHERE link.record_id = NEW.record_id
                  AND anchor.current_state <> 'claimed'
            )
            OR (
                SELECT COUNT(*)
                FROM capability_observation_evaluations
                WHERE record_id = NEW.record_id
            ) < 2
            OR NOT EXISTS (
                SELECT 1
                FROM capability_observations AS capability
                JOIN developmental_policy_versions AS policy
                  ON policy.developmental_policy_id =
                     capability.developmental_policy_id
                JOIN authority_records AS authority
                  ON authority.authority_record_id =
                     policy.authority_record_id
                LEFT JOIN authority_revocations AS revocation
                  ON revocation.authority_record_id =
                     authority.authority_record_id
                 AND revocation.revoked_at <= (
                     SELECT changed_at
                     FROM memory_record_lifecycle_transitions
                     WHERE record_id = NEW.record_id
                       AND to_state = 'active'
                     ORDER BY sequence_number DESC
                     LIMIT 1
                 )
                WHERE capability.record_id = NEW.record_id
                  AND policy.policy_kind = 'capability_stability'
                  AND policy.project_scope_id = NEW.project_scope_id
                  AND policy.status = 'approved'
                  AND policy.effective_from <= (
                      SELECT changed_at
                      FROM memory_record_lifecycle_transitions
                      WHERE record_id = NEW.record_id
                        AND to_state = 'active'
                      ORDER BY sequence_number DESC
                      LIMIT 1
                  )
                  AND (
                      policy.effective_until IS NULL
                      OR policy.effective_until >= (
                          SELECT changed_at
                          FROM memory_record_lifecycle_transitions
                          WHERE record_id = NEW.record_id
                            AND to_state = 'active'
                          ORDER BY sequence_number DESC
                          LIMIT 1
                      )
                  )
                  AND authority.status = 'active'
                  AND authority.effect = 'allow'
                  AND authority.authority_class = 'nolan_byte_approved'
                  AND revocation.authority_record_id IS NULL
                  AND capability.sample_size >= json_extract(
                      policy.configuration_json,
                      '$.stability_requirements.'
                          || capability.stability
                          || '.minimum_sample_size'
                  )
                  AND (
                      SELECT COUNT(*)
                      FROM capability_observation_evaluations AS basis
                      JOIN governed_evaluation_record_anchors AS anchor
                        ON anchor.evaluation_record_id =
                           basis.evaluation_record_id
                      WHERE basis.record_id = capability.record_id
                        AND anchor.current_state = 'claimed'
                  ) >= json_extract(
                      policy.configuration_json,
                      '$.stability_requirements.'
                          || capability.stability
                          || '.minimum_claimed_evaluations'
                  )
            )
        )
    )
    OR NOT EXISTS (
        SELECT 1
        FROM record_evidence_links AS link
        JOIN evidence_items AS evidence
          ON evidence.evidence_id = link.evidence_id
        WHERE link.record_id = NEW.record_id
          AND evidence.integrity_status = 'valid'
          AND evidence.evidence_kind NOT IN (
              'model_output', 'controlled_prompt', 'controlled_output'
          )
    )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'capability activation lacks exact evidence, policy, or stability support'
    );
END;

CREATE TRIGGER maturity_state_activation_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN NEW.record_family = 'self_model'
AND NEW.record_type = 'maturity_state'
AND NEW.lifecycle_state = 'active'
AND OLD.lifecycle_state <> 'active'
AND (
    NOT EXISTS (
        SELECT 1
        FROM maturity_states
        WHERE record_id = NEW.record_id
          AND stage IN (
              'uninitialised', 'oriented',
              'apprentice-observer', 'apprentice-analyst'
          )
          AND entered_at = (
              SELECT changed_at
              FROM memory_record_lifecycle_transitions
              WHERE record_id = NEW.record_id
                AND to_state = 'active'
              ORDER BY sequence_number DESC
              LIMIT 1
          )
    )
    OR NOT EXISTS (
        SELECT 1
        FROM maturity_state_basis_evaluations
        WHERE record_id = NEW.record_id
    )
    OR EXISTS (
        SELECT 1
        FROM maturity_state_basis_evaluations AS basis
        JOIN governed_evaluation_record_anchors AS anchor
          ON anchor.evaluation_record_id = basis.evaluation_record_id
        WHERE basis.record_id = NEW.record_id
          AND anchor.current_state <> 'claimed'
    )
    OR NOT EXISTS (
        SELECT 1
        FROM maturity_states AS maturity
        JOIN developmental_policy_versions AS policy
          ON policy.developmental_policy_id =
             maturity.developmental_policy_id
        JOIN authority_records AS authority
          ON authority.authority_record_id = policy.authority_record_id
        JOIN json_each(
            policy.configuration_json,
            '$.stage_transitions'
        ) AS transition
        LEFT JOIN authority_revocations AS revocation
          ON revocation.authority_record_id = authority.authority_record_id
         AND revocation.revoked_at <= maturity.entered_at
        WHERE maturity.record_id = NEW.record_id
          AND policy.policy_kind = 'maturity_progression'
          AND policy.project_scope_id = NEW.project_scope_id
          AND policy.status = 'approved'
          AND policy.effective_from <= maturity.entered_at
          AND (
              policy.effective_until IS NULL
              OR policy.effective_until >= maturity.entered_at
          )
          AND authority.status = 'active'
          AND authority.effect = 'allow'
          AND authority.authority_class = 'nolan_byte_approved'
          AND revocation.authority_record_id IS NULL
          AND json_extract(transition.value, '$.to_stage') = maturity.stage
          AND (
              (
                  NEW.supersedes_record_id IS NULL
                  AND json_type(transition.value, '$.from_stage') = 'null'
              )
              OR (
                  NEW.supersedes_record_id IS NOT NULL
                  AND json_extract(transition.value, '$.from_stage') = (
                      SELECT prior.stage
                      FROM maturity_states AS prior
                      WHERE prior.record_id = NEW.supersedes_record_id
                  )
              )
          )
          AND (
              SELECT COUNT(*)
              FROM maturity_state_basis_evaluations AS claimed_basis
              JOIN governed_evaluation_record_anchors AS anchor
                ON anchor.evaluation_record_id =
                   claimed_basis.evaluation_record_id
              WHERE claimed_basis.record_id = maturity.record_id
                AND anchor.current_state = 'claimed'
          ) >= json_extract(
              transition.value,
              '$.minimum_claimed_evaluations'
          )
    )
    OR EXISTS (
        SELECT 1
        FROM maturity_states AS candidate
        JOIN maturity_states AS existing
          ON existing.agent_entity_id = candidate.agent_entity_id
        JOIN records AS existing_record
          ON existing_record.record_id = existing.record_id
        WHERE candidate.record_id = NEW.record_id
          AND existing.record_id <> NEW.record_id
          AND existing_record.project_scope_id = NEW.project_scope_id
          AND existing_record.lifecycle_state = 'active'
    )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'maturity activation lacks allowed stage, claimed basis, policy, or exact progression'
    );
END;

CREATE TRIGGER factual_self_superseded_transition_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN NEW.record_family = 'self_model'
AND NEW.record_type IN (
    'runtime_identity', 'capability_observation', 'maturity_state'
)
AND NEW.lifecycle_state = 'superseded'
AND OLD.lifecycle_state <> 'superseded'
AND NOT EXISTS (
    SELECT 1
    FROM record_relationships AS relationship
    JOIN records AS replacement
      ON replacement.record_id = relationship.source_record_id
    WHERE relationship.target_record_id = NEW.record_id
      AND relationship.relationship_type = 'supersedes'
      AND relationship.relationship_grant_id IS NOT NULL
      AND replacement.record_family = NEW.record_family
      AND replacement.record_type = NEW.record_type
      AND replacement.project_scope_id = NEW.project_scope_id
      AND replacement.lifecycle_state = 'approved'
      AND replacement.approval_status IN ('approved', 'not_required')
      AND replacement.integrity_status = 'valid'
      AND replacement.supersedes_record_id = NEW.record_id
)
BEGIN
    SELECT RAISE(
        ABORT,
        'factual self supersession requires one exact approved replacement'
    );
END;

CREATE TRIGGER capability_observation_active_uniqueness_guard
BEFORE UPDATE OF lifecycle_state ON records
WHEN NEW.record_family = 'self_model'
AND NEW.record_type = 'capability_observation'
AND NEW.lifecycle_state = 'active'
AND OLD.lifecycle_state <> 'active'
AND EXISTS (
    SELECT 1
    FROM capability_observations AS candidate
    JOIN capability_observations AS existing
      ON existing.capability_key = candidate.capability_key
    JOIN records AS existing_record
      ON existing_record.record_id = existing.record_id
    WHERE candidate.record_id = NEW.record_id
      AND existing.record_id <> NEW.record_id
      AND existing_record.project_scope_id = NEW.project_scope_id
      AND existing_record.subject_entity_id = NEW.subject_entity_id
      AND existing_record.lifecycle_state = 'active'
)
BEGIN
    SELECT RAISE(
        ABORT,
        'existing active capability observation must be superseded first'
    );
END;

CREATE TRIGGER factual_self_superseded_by_guard
BEFORE UPDATE OF superseded_by_record_id ON records
WHEN NEW.record_family = 'self_model'
AND NEW.record_type IN (
    'runtime_identity', 'capability_observation', 'maturity_state'
)
AND NEW.superseded_by_record_id IS NOT OLD.superseded_by_record_id
AND NOT EXISTS (
    SELECT 1
    FROM record_relationships
    WHERE source_record_id = NEW.superseded_by_record_id
      AND target_record_id = NEW.record_id
      AND relationship_type = 'supersedes'
      AND relationship_grant_id IS NOT NULL
)
BEGIN
    SELECT RAISE(
        ABORT,
        'superseded_by_record_id requires the exact governed relationship'
    );
END;

CREATE TRIGGER factual_self_records_core_immutable
BEFORE UPDATE OF
    record_id, record_family, record_type, schema_version,
    construct_scope_id, project_scope_id, subject_entity_id,
    session_id, task_id, authority_class, certainty_class,
    sensitivity_class, privacy_class, retention_class,
    training_eligibility, created_at, created_by_entity_id,
    created_by_runtime_id, effective_from, effective_until,
    review_due_at, supersedes_record_id, previous_version_id,
    source_kind, provenance_summary, retrieval_policy_json,
    deletion_policy_json, agent_write_policy, content_hash
ON records
WHEN OLD.record_family = 'self_model'
AND OLD.record_type IN (
    'runtime_identity', 'capability_observation', 'maturity_state'
)
BEGIN
    SELECT RAISE(ABORT, 'factual self envelope content and lineage are immutable');
END;

CREATE TRIGGER factual_self_records_no_delete
BEFORE DELETE ON records
WHEN OLD.record_family = 'self_model'
AND OLD.record_type IN (
    'runtime_identity', 'capability_observation', 'maturity_state'
)
BEGIN
    SELECT RAISE(ABORT, 'factual self records cannot be deleted');
END;

CREATE TRIGGER trusted_runtime_attestors_immutable
BEFORE UPDATE ON trusted_runtime_attestors
BEGIN
    SELECT RAISE(ABORT, 'trusted runtime attestor versions are immutable');
END;

CREATE TRIGGER trusted_runtime_attestors_no_delete
BEFORE DELETE ON trusted_runtime_attestors
BEGIN
    SELECT RAISE(ABORT, 'trusted runtime attestor versions cannot be deleted');
END;

CREATE TRIGGER runtime_substrate_attestations_immutable
BEFORE UPDATE ON runtime_substrate_attestations
BEGIN
    SELECT RAISE(ABORT, 'runtime substrate attestations are immutable');
END;

CREATE TRIGGER runtime_substrate_attestations_no_delete
BEFORE DELETE ON runtime_substrate_attestations
BEGIN
    SELECT RAISE(ABORT, 'runtime substrate attestations cannot be deleted');
END;

CREATE TRIGGER runtime_attestation_evidence_immutable
BEFORE UPDATE ON evidence_items
WHEN EXISTS (
    SELECT 1
    FROM runtime_substrate_attestations
    WHERE substrate_attestation_evidence_id = OLD.evidence_id
)
BEGIN
    SELECT RAISE(ABORT, 'runtime attestation evidence is immutable');
END;

CREATE TRIGGER runtime_attestation_evidence_no_delete
BEFORE DELETE ON evidence_items
WHEN EXISTS (
    SELECT 1
    FROM runtime_substrate_attestations
    WHERE substrate_attestation_evidence_id = OLD.evidence_id
)
BEGIN
    SELECT RAISE(ABORT, 'runtime attestation evidence cannot be deleted');
END;

CREATE TRIGGER runtime_attestation_inline_no_delete
BEFORE DELETE ON evidence_inline_text
WHEN EXISTS (
    SELECT 1
    FROM runtime_substrate_attestations
    WHERE substrate_attestation_evidence_id = OLD.evidence_id
)
BEGIN
    SELECT RAISE(ABORT, 'runtime attestation inline content cannot be deleted');
END;

CREATE TRIGGER runtime_identity_evidence_links_immutable
BEFORE UPDATE ON record_evidence_links
WHEN EXISTS (
    SELECT 1
    FROM records
    WHERE record_id = OLD.record_id
      AND record_family = 'self_model'
      AND record_type = 'runtime_identity'
)
OR EXISTS (
    SELECT 1
    FROM records
    WHERE record_id = NEW.record_id
      AND record_family = 'self_model'
      AND record_type = 'runtime_identity'
)
BEGIN
    SELECT RAISE(
        ABORT,
        'runtime identity evidence links are immutable'
    );
END;

CREATE TRIGGER runtime_identity_evidence_links_no_delete
BEFORE DELETE ON record_evidence_links
WHEN EXISTS (
    SELECT 1
    FROM records
    WHERE record_id = OLD.record_id
      AND record_family = 'self_model'
      AND record_type = 'runtime_identity'
)
BEGIN
    SELECT RAISE(
        ABORT,
        'runtime identity evidence links cannot be deleted'
    );
END;

CREATE TRIGGER runtime_identities_immutable
BEFORE UPDATE ON runtime_identities
BEGIN
    SELECT RAISE(ABORT, 'runtime identity payloads are immutable');
END;

CREATE TRIGGER runtime_identities_no_delete
BEFORE DELETE ON runtime_identities
BEGIN
    SELECT RAISE(ABORT, 'runtime identity payloads cannot be deleted');
END;

CREATE TRIGGER capability_observations_immutable
BEFORE UPDATE ON capability_observations
BEGIN
    SELECT RAISE(ABORT, 'capability observation payloads are immutable');
END;

CREATE TRIGGER capability_observations_no_delete
BEFORE DELETE ON capability_observations
BEGIN
    SELECT RAISE(ABORT, 'capability observation payloads cannot be deleted');
END;

CREATE TRIGGER capability_observation_evaluations_immutable
BEFORE UPDATE ON capability_observation_evaluations
BEGIN
    SELECT RAISE(ABORT, 'capability evaluation lineage is immutable');
END;

CREATE TRIGGER capability_observation_evaluations_no_delete
BEFORE DELETE ON capability_observation_evaluations
BEGIN
    SELECT RAISE(ABORT, 'capability evaluation lineage cannot be deleted');
END;

CREATE TRIGGER maturity_states_immutable
BEFORE UPDATE ON maturity_states
BEGIN
    SELECT RAISE(ABORT, 'maturity state payloads are immutable');
END;

CREATE TRIGGER maturity_states_no_delete
BEFORE DELETE ON maturity_states
BEGIN
    SELECT RAISE(ABORT, 'maturity state payloads cannot be deleted');
END;

CREATE TRIGGER maturity_state_basis_evaluations_immutable
BEFORE UPDATE ON maturity_state_basis_evaluations
BEGIN
    SELECT RAISE(ABORT, 'maturity evaluation basis is immutable');
END;

CREATE TRIGGER maturity_state_basis_evaluations_no_delete
BEFORE DELETE ON maturity_state_basis_evaluations
BEGIN
    SELECT RAISE(ABORT, 'maturity evaluation basis cannot be deleted');
END;
