CREATE TABLE evaluation_candidates (
    candidate_id TEXT PRIMARY KEY,
    candidate_origin TEXT NOT NULL CHECK (
        candidate_origin IN (
            'operator_supplied', 'public_metadata', 'synthetic_mock'
        )
    ),
    lifecycle_state TEXT NOT NULL CHECK (
        lifecycle_state IN ('registered', 'withheld', 'ineligible', 'retired')
    ),
    admission_state TEXT NOT NULL CHECK (
        admission_state IN (
            'not_assessed', 'evaluation_pending', 'not_admitted', 'ineligible'
        )
    ),
    model_family TEXT NOT NULL,
    model_revision TEXT NOT NULL,
    quantization TEXT,
    artifact_format TEXT NOT NULL,
    licence_identifier TEXT NOT NULL,
    provenance_json TEXT NOT NULL CHECK (json_valid(provenance_json)),
    compatibility_json TEXT NOT NULL CHECK (json_valid(compatibility_json)),
    registered_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_hash TEXT NOT NULL UNIQUE CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    UNIQUE (candidate_id, content_hash),
    CHECK (length(candidate_id) = 36),
    CHECK (length(model_family) > 0),
    CHECK (length(model_revision) > 0),
    CHECK (length(artifact_format) > 0),
    CHECK (length(licence_identifier) > 0)
);

CREATE TABLE evaluation_fixture_sets (
    fixture_set_id TEXT NOT NULL,
    fixture_set_version TEXT NOT NULL,
    evaluation_suite_id TEXT NOT NULL,
    evaluation_suite_version TEXT NOT NULL,
    provenance_json TEXT NOT NULL CHECK (json_valid(provenance_json)),
    registered_at TEXT NOT NULL,
    manifest_json TEXT NOT NULL CHECK (json_valid(manifest_json)),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    PRIMARY KEY (fixture_set_id, fixture_set_version),
    UNIQUE (fixture_set_id, fixture_set_version, content_hash),
    UNIQUE (
        fixture_set_id, fixture_set_version, evaluation_suite_id,
        evaluation_suite_version, content_hash
    ),
    CHECK (length(fixture_set_id) = 36),
    CHECK (length(evaluation_suite_id) = 36)
);

CREATE TABLE evaluation_fixtures (
    fixture_id TEXT PRIMARY KEY,
    fixture_family_id TEXT NOT NULL,
    fixture_version TEXT NOT NULL,
    fixture_set_id TEXT NOT NULL,
    fixture_set_version TEXT NOT NULL,
    fixture_set_hash TEXT NOT NULL,
    evaluation_suite_id TEXT NOT NULL,
    evaluation_suite_version TEXT NOT NULL,
    fixture_ordinal INTEGER NOT NULL CHECK (fixture_ordinal >= 0),
    source_name TEXT NOT NULL,
    sensitivity TEXT NOT NULL CHECK (
        sensitivity IN ('public', 'internal', 'restricted_synthetic')
    ),
    provenance_json TEXT NOT NULL CHECK (json_valid(provenance_json)),
    fixture_json TEXT NOT NULL CHECK (json_valid(fixture_json)),
    byte_length INTEGER NOT NULL CHECK (byte_length > 0),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    registered_at TEXT NOT NULL,
    UNIQUE (fixture_set_id, fixture_set_version, fixture_ordinal),
    UNIQUE (fixture_set_id, fixture_set_version, source_name),
    UNIQUE (fixture_set_id, fixture_set_version, content_hash),
    UNIQUE (fixture_family_id, fixture_version),
    FOREIGN KEY (
        fixture_set_id, fixture_set_version, evaluation_suite_id,
        evaluation_suite_version, fixture_set_hash
    ) REFERENCES evaluation_fixture_sets (
        fixture_set_id, fixture_set_version, evaluation_suite_id,
        evaluation_suite_version, content_hash
    ),
    CHECK (length(fixture_id) = 36),
    CHECK (length(fixture_family_id) = 36),
    CHECK (length(evaluation_suite_id) = 36),
    CHECK (source_name GLOB '*.json'),
    CHECK (instr(source_name, '\\') = 0),
    CHECK (instr(source_name, '..') = 0)
);

CREATE TABLE evaluation_configurations (
    configuration_id TEXT PRIMARY KEY,
    configuration_family_id TEXT NOT NULL,
    configuration_version TEXT NOT NULL,
    evaluation_suite_id TEXT NOT NULL,
    evaluation_suite_version TEXT NOT NULL,
    fixture_set_id TEXT NOT NULL,
    fixture_set_version TEXT NOT NULL,
    fixture_set_hash TEXT NOT NULL,
    timeout_ms INTEGER NOT NULL CHECK (timeout_ms > 0),
    repetitions INTEGER NOT NULL CHECK (repetitions > 0),
    conditions_json TEXT NOT NULL CHECK (json_valid(conditions_json)),
    resource_limits_json TEXT NOT NULL CHECK (json_valid(resource_limits_json)),
    score_schema_json TEXT NOT NULL CHECK (json_valid(score_schema_json)),
    critical_failure_schema_json TEXT NOT NULL CHECK (
        json_valid(critical_failure_schema_json)
    ),
    registered_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_hash TEXT NOT NULL UNIQUE CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (
        fixture_set_id, fixture_set_version, evaluation_suite_id,
        evaluation_suite_version, fixture_set_hash
    ) REFERENCES evaluation_fixture_sets (
        fixture_set_id, fixture_set_version, evaluation_suite_id,
        evaluation_suite_version, content_hash
    ),
    UNIQUE (configuration_id, content_hash),
    UNIQUE (configuration_family_id, configuration_version),
    CHECK (length(configuration_id) = 36),
    CHECK (length(configuration_family_id) = 36),
    CHECK (length(evaluation_suite_id) = 36)
);

CREATE TABLE evaluation_plans (
    plan_id TEXT PRIMARY KEY,
    plan_family_id TEXT NOT NULL,
    plan_version TEXT NOT NULL,
    configuration_id TEXT NOT NULL,
    configuration_hash TEXT NOT NULL,
    fixture_set_id TEXT NOT NULL,
    fixture_set_version TEXT NOT NULL,
    fixture_set_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_hash TEXT NOT NULL UNIQUE CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (configuration_id, configuration_hash)
        REFERENCES evaluation_configurations (configuration_id, content_hash),
    FOREIGN KEY (fixture_set_id, fixture_set_version, fixture_set_hash)
        REFERENCES evaluation_fixture_sets (
            fixture_set_id, fixture_set_version, content_hash
        ),
    UNIQUE (plan_id, content_hash),
    UNIQUE (plan_family_id, plan_version),
    CHECK (length(plan_id) = 36),
    CHECK (length(plan_family_id) = 36)
);

CREATE TABLE evaluation_plan_candidates (
    plan_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    candidate_hash TEXT NOT NULL,
    blind_candidate_id TEXT NOT NULL,
    PRIMARY KEY (plan_id, candidate_id),
    UNIQUE (plan_id, blind_candidate_id),
    FOREIGN KEY (plan_id, plan_hash)
        REFERENCES evaluation_plans (plan_id, content_hash),
    FOREIGN KEY (candidate_id, candidate_hash)
        REFERENCES evaluation_candidates (candidate_id, content_hash),
    CHECK (blind_candidate_id GLOB 'blind_[0-9a-f]*'),
    CHECK (length(blind_candidate_id) = 30)
);

CREATE TABLE evaluation_runs (
    run_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    condition_label TEXT NOT NULL CHECK (
        condition_label IN ('enabled', 'withheld', 'over_transfer')
    ),
    blind_candidate_id TEXT NOT NULL,
    fixture_id TEXT NOT NULL,
    repetition_index INTEGER NOT NULL CHECK (repetition_index >= 0),
    run_ordinal INTEGER NOT NULL CHECK (run_ordinal >= 0),
    ablation_metadata_json TEXT NOT NULL CHECK (
        json_valid(ablation_metadata_json)
    ),
    planned_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_hash TEXT NOT NULL UNIQUE CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (plan_id, plan_hash)
        REFERENCES evaluation_plans (plan_id, content_hash),
    FOREIGN KEY (plan_id, blind_candidate_id)
        REFERENCES evaluation_plan_candidates (plan_id, blind_candidate_id),
    FOREIGN KEY (fixture_id) REFERENCES evaluation_fixtures (fixture_id),
    UNIQUE (plan_id, run_ordinal),
    UNIQUE (
        plan_id, blind_candidate_id, fixture_id, condition_id,
        repetition_index
    ),
    UNIQUE (run_id, content_hash),
    CHECK (length(run_id) = 36),
    CHECK (length(condition_id) = 36)
);

CREATE TABLE evaluation_results (
    result_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    run_hash TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (
        outcome IN (
            'completed', 'critical_failure', 'incomplete', 'invalid',
            'interrupted'
        )
    ),
    evidence_origin TEXT NOT NULL CHECK (
        evidence_origin IN ('synthetic_mock', 'recorded_observation')
    ),
    scores_json TEXT NOT NULL CHECK (json_valid(scores_json)),
    critical_failures_json TEXT NOT NULL CHECK (
        json_valid(critical_failures_json)
    ),
    runtime_observed_json TEXT NOT NULL CHECK (
        json_valid(runtime_observed_json)
    ),
    candidate_reported_metadata_json TEXT NOT NULL CHECK (
        json_valid(candidate_reported_metadata_json)
    ),
    replay_metadata_json TEXT NOT NULL CHECK (json_valid(replay_metadata_json)),
    observed_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_hash TEXT NOT NULL UNIQUE CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (run_id, run_hash)
        REFERENCES evaluation_runs (run_id, content_hash),
    CHECK (length(result_id) = 36)
);

CREATE TABLE evaluation_run_state_transitions (
    transition_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence IN (0, 1)),
    from_state TEXT CHECK (
        from_state IS NULL OR from_state IN (
            'planned', 'completed', 'critical_failure', 'incomplete',
            'invalid', 'interrupted'
        )
    ),
    to_state TEXT NOT NULL CHECK (
        to_state IN (
            'planned', 'completed', 'critical_failure', 'incomplete',
            'invalid', 'interrupted'
        )
    ),
    occurred_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_hash TEXT NOT NULL UNIQUE CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    UNIQUE (run_id, sequence),
    FOREIGN KEY (run_id) REFERENCES evaluation_runs (run_id),
    CHECK (length(transition_id) = 36)
);

CREATE INDEX evaluation_candidates_origin_state
    ON evaluation_candidates (candidate_origin, lifecycle_state, admission_state);
CREATE INDEX evaluation_configurations_suite
    ON evaluation_configurations (
        evaluation_suite_id, evaluation_suite_version,
        fixture_set_id, fixture_set_version
    );
CREATE INDEX evaluation_fixtures_set_order
    ON evaluation_fixtures (
        fixture_set_id, fixture_set_version, fixture_ordinal
    );
CREATE INDEX evaluation_runs_plan_order
    ON evaluation_runs (plan_id, run_ordinal);
CREATE INDEX evaluation_runs_condition
    ON evaluation_runs (plan_id, condition_label, condition_id);
CREATE INDEX evaluation_runs_blinded_candidate
    ON evaluation_runs (plan_id, blind_candidate_id, run_ordinal);
CREATE INDEX evaluation_results_outcome
    ON evaluation_results (outcome, run_id);

CREATE TRIGGER evaluation_results_validate_run
BEFORE INSERT ON evaluation_results
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM evaluation_run_state_transitions AS transition
        WHERE transition.run_id = NEW.run_id
          AND transition.sequence = 0
          AND transition.from_state IS NULL
          AND transition.to_state = 'planned'
    ) THEN RAISE(ABORT, 'evaluation result requires planned run') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1
        FROM evaluation_run_state_transitions AS transition
        WHERE transition.run_id = NEW.run_id
          AND transition.sequence = 1
    ) THEN RAISE(ABORT, 'evaluation run is already terminal') END;
END;

CREATE TRIGGER evaluation_run_transitions_validate
BEFORE INSERT ON evaluation_run_state_transitions
BEGIN
    SELECT CASE WHEN NEW.sequence = 0 AND (
        NEW.from_state IS NOT NULL OR NEW.to_state <> 'planned'
    ) THEN RAISE(ABORT, 'initial evaluation transition is invalid') END;
    SELECT CASE WHEN NEW.sequence = 1 AND (
        NEW.from_state <> 'planned' OR NEW.to_state = 'planned'
    ) THEN RAISE(ABORT, 'terminal evaluation transition is invalid') END;
    SELECT CASE WHEN NEW.sequence = 1 AND NOT EXISTS (
        SELECT 1
        FROM evaluation_run_state_transitions AS previous
        WHERE previous.run_id = NEW.run_id
          AND previous.sequence = 0
          AND previous.to_state = 'planned'
    ) THEN RAISE(ABORT, 'terminal evaluation transition lacks parent') END;
    SELECT CASE WHEN NEW.sequence = 1 AND NOT EXISTS (
        SELECT 1
        FROM evaluation_results AS result
        WHERE result.run_id = NEW.run_id
          AND result.outcome = NEW.to_state
    ) THEN RAISE(ABORT, 'terminal transition conflicts with result') END;
END;

CREATE TRIGGER evaluation_candidates_immutable
BEFORE UPDATE ON evaluation_candidates
BEGIN
    SELECT RAISE(ABORT, 'evaluation candidate metadata is immutable');
END;
CREATE TRIGGER evaluation_candidates_no_delete
BEFORE DELETE ON evaluation_candidates
BEGIN
    SELECT RAISE(ABORT, 'evaluation candidate metadata cannot be deleted');
END;

CREATE TRIGGER evaluation_fixture_sets_immutable
BEFORE UPDATE ON evaluation_fixture_sets
BEGIN
    SELECT RAISE(ABORT, 'evaluation fixture set is immutable');
END;
CREATE TRIGGER evaluation_fixture_sets_no_delete
BEFORE DELETE ON evaluation_fixture_sets
BEGIN
    SELECT RAISE(ABORT, 'evaluation fixture set cannot be deleted');
END;

CREATE TRIGGER evaluation_fixtures_immutable
BEFORE UPDATE ON evaluation_fixtures
BEGIN
    SELECT RAISE(ABORT, 'evaluation fixture is immutable');
END;
CREATE TRIGGER evaluation_fixtures_no_delete
BEFORE DELETE ON evaluation_fixtures
BEGIN
    SELECT RAISE(ABORT, 'evaluation fixture cannot be deleted');
END;

CREATE TRIGGER evaluation_configurations_immutable
BEFORE UPDATE ON evaluation_configurations
BEGIN
    SELECT RAISE(ABORT, 'evaluation configuration is immutable');
END;
CREATE TRIGGER evaluation_configurations_no_delete
BEFORE DELETE ON evaluation_configurations
BEGIN
    SELECT RAISE(ABORT, 'evaluation configuration cannot be deleted');
END;

CREATE TRIGGER evaluation_plans_immutable
BEFORE UPDATE ON evaluation_plans
BEGIN
    SELECT RAISE(ABORT, 'evaluation plan is immutable');
END;
CREATE TRIGGER evaluation_plans_no_delete
BEFORE DELETE ON evaluation_plans
BEGIN
    SELECT RAISE(ABORT, 'evaluation plan cannot be deleted');
END;

CREATE TRIGGER evaluation_plan_candidates_immutable
BEFORE UPDATE ON evaluation_plan_candidates
BEGIN
    SELECT RAISE(ABORT, 'evaluation blinding binding is immutable');
END;
CREATE TRIGGER evaluation_plan_candidates_no_delete
BEFORE DELETE ON evaluation_plan_candidates
BEGIN
    SELECT RAISE(ABORT, 'evaluation blinding binding cannot be deleted');
END;

CREATE TRIGGER evaluation_runs_immutable
BEFORE UPDATE ON evaluation_runs
BEGIN
    SELECT RAISE(ABORT, 'evaluation run is immutable');
END;
CREATE TRIGGER evaluation_runs_no_delete
BEFORE DELETE ON evaluation_runs
BEGIN
    SELECT RAISE(ABORT, 'evaluation run cannot be deleted');
END;

CREATE TRIGGER evaluation_results_immutable
BEFORE UPDATE ON evaluation_results
BEGIN
    SELECT RAISE(ABORT, 'evaluation result evidence is immutable');
END;
CREATE TRIGGER evaluation_results_no_delete
BEFORE DELETE ON evaluation_results
BEGIN
    SELECT RAISE(ABORT, 'evaluation result evidence cannot be deleted');
END;

CREATE TRIGGER evaluation_run_state_transitions_immutable
BEFORE UPDATE ON evaluation_run_state_transitions
BEGIN
    SELECT RAISE(ABORT, 'evaluation run transition is immutable');
END;
CREATE TRIGGER evaluation_run_state_transitions_no_delete
BEFORE DELETE ON evaluation_run_state_transitions
BEGIN
    SELECT RAISE(ABORT, 'evaluation run transition cannot be deleted');
END;
