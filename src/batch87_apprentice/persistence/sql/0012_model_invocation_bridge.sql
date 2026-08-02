CREATE TABLE model_invocations (
    model_invocation_id TEXT PRIMARY KEY,
    reference_kind TEXT NOT NULL DEFAULT 'model_invocation'
        CHECK (reference_kind = 'model_invocation'),
    contract_version TEXT NOT NULL CHECK (contract_version = '1.0.0'),
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_scope_id TEXT NOT NULL,
    context_package_id TEXT NOT NULL,
    context_package_hash TEXT NOT NULL CHECK (
        length(context_package_hash) = 64
        AND context_package_hash NOT GLOB '*[^0-9a-f]*'
    ),
    retrieval_manifest_id TEXT NOT NULL,
    retrieval_manifest_hash TEXT NOT NULL CHECK (
        length(retrieval_manifest_hash) = 64
        AND retrieval_manifest_hash NOT GLOB '*[^0-9a-f]*'
    ),
    task_memory_projection_hash TEXT NOT NULL CHECK (
        length(task_memory_projection_hash) = 64
        AND task_memory_projection_hash NOT GLOB '*[^0-9a-f]*'
    ),
    task_context_finalization_id TEXT NOT NULL,
    task_context_finalization_hash TEXT NOT NULL CHECK (
        length(task_context_finalization_hash) = 64
        AND task_context_finalization_hash NOT GLOB '*[^0-9a-f]*'
    ),
    runtime_identity_id TEXT NOT NULL,
    runtime_identity_hash TEXT NOT NULL CHECK (
        length(runtime_identity_hash) = 64
        AND runtime_identity_hash NOT GLOB '*[^0-9a-f]*'
    ),
    provider_id TEXT NOT NULL CHECK (
        provider_id IN ('inactive', 'deterministic_mock')
    ),
    provider_descriptor_json TEXT NOT NULL CHECK (
        json_valid(provider_descriptor_json)
        AND json_type(provider_descriptor_json) = 'object'
    ),
    provider_descriptor_hash TEXT NOT NULL CHECK (
        length(provider_descriptor_hash) = 64
        AND provider_descriptor_hash NOT GLOB '*[^0-9a-f]*'
    ),
    provider_configuration_json TEXT NOT NULL CHECK (
        json_valid(provider_configuration_json)
        AND json_type(provider_configuration_json) = 'object'
    ),
    provider_configuration_hash TEXT NOT NULL CHECK (
        length(provider_configuration_hash) = 64
        AND provider_configuration_hash NOT GLOB '*[^0-9a-f]*'
    ),
    model_descriptor_json TEXT NOT NULL CHECK (
        json_valid(model_descriptor_json)
        AND json_type(model_descriptor_json) = 'object'
    ),
    model_descriptor_hash TEXT NOT NULL CHECK (
        length(model_descriptor_hash) = 64
        AND model_descriptor_hash NOT GLOB '*[^0-9a-f]*'
    ),
    inference_configuration_json TEXT NOT NULL CHECK (
        json_valid(inference_configuration_json)
        AND json_type(inference_configuration_json) = 'object'
    ),
    inference_configuration_hash TEXT NOT NULL CHECK (
        length(inference_configuration_hash) = 64
        AND inference_configuration_hash NOT GLOB '*[^0-9a-f]*'
    ),
    output_schema_id TEXT NOT NULL CHECK (trim(output_schema_id) <> ''),
    output_schema_hash TEXT NOT NULL CHECK (
        length(output_schema_hash) = 64
        AND output_schema_hash NOT GLOB '*[^0-9a-f]*'
    ),
    model_input_packet_json TEXT NOT NULL CHECK (
        json_valid(model_input_packet_json)
        AND json_type(model_input_packet_json) = 'object'
    ),
    model_input_packet_hash TEXT NOT NULL CHECK (
        length(model_input_packet_hash) = 64
        AND model_input_packet_hash NOT GLOB '*[^0-9a-f]*'
    ),
    submission_json TEXT NOT NULL CHECK (
        json_valid(submission_json) AND json_type(submission_json) = 'object'
    ),
    submission_hash TEXT NOT NULL CHECK (
        length(submission_hash) = 64
        AND submission_hash NOT GLOB '*[^0-9a-f]*'
    ),
    request_json TEXT NOT NULL CHECK (
        json_valid(request_json) AND json_type(request_json) = 'object'
    ),
    request_hash TEXT NOT NULL CHECK (
        length(request_hash) = 64
        AND request_hash NOT GLOB '*[^0-9a-f]*'
    ),
    retry_of_invocation_id TEXT,
    current_status TEXT NOT NULL CHECK (
        current_status IN (
            'prepared', 'in_progress', 'raw_output_captured',
            'provider_inactive', 'succeeded', 'provider_failed',
            'timed_out', 'invalid_response', 'stale_context', 'interrupted'
        )
    ),
    prepared_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    provider_call_attempt_id TEXT UNIQUE,
    runtime_principal TEXT NOT NULL CHECK (
        runtime_principal IN ('operator', 'codex_development_harness')
    ),
    provider_result_outcome TEXT CHECK (
        provider_result_outcome IS NULL
        OR provider_result_outcome IN (
            'output', 'provider_inactive', 'provider_failed', 'timed_out'
        )
    ),
    provider_result_json TEXT CHECK (
        provider_result_json IS NULL
        OR (
            json_valid(provider_result_json)
            AND json_type(provider_result_json) = 'object'
        )
    ),
    provider_result_hash TEXT CHECK (
        provider_result_hash IS NULL
        OR (
            length(provider_result_hash) = 64
            AND provider_result_hash NOT GLOB '*[^0-9a-f]*'
        )
    ),
    failure_classification TEXT,
    terminal_result_json TEXT CHECK (
        terminal_result_json IS NULL
        OR (
            json_valid(terminal_result_json)
            AND json_type(terminal_result_json) = 'object'
        )
    ),
    terminal_result_hash TEXT CHECK (
        terminal_result_hash IS NULL
        OR (
            length(terminal_result_hash) = 64
            AND terminal_result_hash NOT GLOB '*[^0-9a-f]*'
        )
    ),
    task_disposition TEXT CHECK (
        task_disposition IS NULL
        OR task_disposition IN (
            'completed', 'failed', 'deferred_human_review',
            'unchanged_terminal', 'not_applicable'
        )
    ),
    task_transition_id TEXT,
    FOREIGN KEY (model_invocation_id, reference_kind, project_scope_id)
        REFERENCES governed_reference_anchors(
            reference_id, reference_kind, project_scope_id
        ) ON DELETE RESTRICT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_scope_id)
        REFERENCES scopes(scope_id) ON DELETE RESTRICT,
    FOREIGN KEY (context_package_id)
        REFERENCES context_packages(context_package_id) ON DELETE RESTRICT,
    FOREIGN KEY (retrieval_manifest_id)
        REFERENCES retrieval_manifests(retrieval_manifest_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (task_context_finalization_id)
        REFERENCES task_context_finalizations(finalization_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (runtime_identity_id)
        REFERENCES runtime_identities(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (retry_of_invocation_id)
        REFERENCES model_invocations(model_invocation_id) ON DELETE RESTRICT,
    FOREIGN KEY (task_transition_id)
        REFERENCES task_state_transitions(transition_id) ON DELETE RESTRICT,
    CHECK (
        retry_of_invocation_id IS NULL
        OR retry_of_invocation_id <> model_invocation_id
    ),
    CHECK (
        (
            current_status = 'prepared'
            AND started_at IS NULL
            AND completed_at IS NULL
            AND provider_call_attempt_id IS NULL
            AND provider_result_hash IS NULL
            AND terminal_result_hash IS NULL
            AND task_disposition IS NULL
            AND task_transition_id IS NULL
        )
        OR (
            current_status IN ('in_progress', 'raw_output_captured')
            AND started_at IS NOT NULL
            AND completed_at IS NULL
            AND provider_call_attempt_id IS NOT NULL
            AND provider_result_hash IS NULL
            AND terminal_result_hash IS NULL
            AND task_disposition IS NULL
            AND task_transition_id IS NULL
        )
        OR (
            current_status = 'provider_inactive'
            AND started_at IS NULL
            AND provider_call_attempt_id IS NULL
            AND completed_at IS NOT NULL
            AND provider_result_hash IS NOT NULL
            AND terminal_result_hash IS NOT NULL
            AND task_disposition IS NOT NULL
        )
        OR (
            current_status IN (
                'succeeded', 'provider_failed', 'timed_out',
                'invalid_response', 'stale_context'
            )
            AND started_at IS NOT NULL
            AND provider_call_attempt_id IS NOT NULL
            AND completed_at IS NOT NULL
            AND provider_result_hash IS NOT NULL
            AND terminal_result_hash IS NOT NULL
            AND task_disposition IS NOT NULL
        )
        OR (
            current_status = 'interrupted'
            AND started_at IS NOT NULL
            AND provider_call_attempt_id IS NOT NULL
            AND completed_at IS NOT NULL
            AND terminal_result_hash IS NOT NULL
            AND task_disposition IS NOT NULL
            AND (
                (
                    provider_result_outcome IS NULL
                    AND provider_result_json IS NULL
                    AND provider_result_hash IS NULL
                )
                OR
                (
                    provider_result_outcome IS NOT NULL
                    AND provider_result_json IS NOT NULL
                    AND provider_result_hash IS NOT NULL
                )
            )
        )
    ),
    CHECK (
        (task_disposition IN ('completed', 'failed')
            AND task_transition_id IS NOT NULL)
        OR
        (task_disposition NOT IN ('completed', 'failed')
            AND task_transition_id IS NULL)
        OR
        (task_disposition IS NULL AND task_transition_id IS NULL)
    ),
    CHECK (
        (
            current_status IN (
                'prepared', 'in_progress', 'raw_output_captured', 'succeeded'
            )
            AND failure_classification IS NULL
        )
        OR
        (
            current_status IN (
                'provider_inactive', 'provider_failed', 'timed_out',
                'invalid_response', 'stale_context', 'interrupted'
            )
            AND failure_classification IS NOT NULL
            AND trim(failure_classification) <> ''
        )
    ),
    CHECK (started_at IS NULL OR started_at >= prepared_at),
    CHECK (completed_at IS NULL OR completed_at >= prepared_at),
    CHECK (
        completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at
    )
);

CREATE INDEX model_invocations_task_status
ON model_invocations(task_id, current_status, prepared_at);

CREATE INDEX model_invocations_context
ON model_invocations(context_package_id, prepared_at);

CREATE UNIQUE INDEX model_invocations_one_incomplete_per_task_context
ON model_invocations(task_id, context_package_id)
WHERE current_status IN ('prepared', 'in_progress', 'raw_output_captured');

CREATE TABLE model_invocation_state_transitions (
    transition_id TEXT PRIMARY KEY,
    model_invocation_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    from_status TEXT,
    to_status TEXT NOT NULL CHECK (
        to_status IN (
            'prepared', 'in_progress', 'raw_output_captured',
            'provider_inactive', 'succeeded', 'provider_failed',
            'timed_out', 'invalid_response', 'stale_context', 'interrupted'
        )
    ),
    reason_code TEXT NOT NULL CHECK (trim(reason_code) <> ''),
    changed_at TEXT NOT NULL,
    changed_by_principal TEXT NOT NULL CHECK (
        changed_by_principal IN ('operator', 'codex_development_harness')
    ),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    UNIQUE (model_invocation_id, sequence_number),
    FOREIGN KEY (model_invocation_id)
        REFERENCES model_invocations(model_invocation_id) ON DELETE RESTRICT,
    CHECK (
        (sequence_number = 0 AND from_status IS NULL AND to_status = 'prepared')
        OR
        (
            sequence_number > 0
            AND (
                (from_status = 'prepared'
                    AND to_status IN ('in_progress', 'provider_inactive'))
                OR
                (from_status = 'in_progress'
                    AND to_status IN (
                        'raw_output_captured', 'provider_failed', 'timed_out',
                        'stale_context', 'interrupted'
                    ))
                OR
                (from_status = 'raw_output_captured'
                    AND to_status IN (
                        'succeeded', 'provider_failed', 'timed_out',
                        'invalid_response', 'stale_context', 'interrupted'
                    ))
            )
        )
    )
);

CREATE TABLE model_raw_outputs (
    raw_output_id TEXT PRIMARY KEY,
    model_invocation_id TEXT NOT NULL UNIQUE,
    provider_call_attempt_id TEXT NOT NULL UNIQUE,
    raw_bytes BLOB NOT NULL CHECK (typeof(raw_bytes) = 'blob'),
    raw_byte_length INTEGER NOT NULL CHECK (raw_byte_length >= 0),
    raw_output_sha256 TEXT NOT NULL CHECK (
        length(raw_output_sha256) = 64
        AND raw_output_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    declared_encoding TEXT NOT NULL CHECK (trim(declared_encoding) <> ''),
    provider_result_json TEXT NOT NULL CHECK (
        json_valid(provider_result_json)
        AND json_type(provider_result_json) = 'object'
    ),
    provider_result_hash TEXT NOT NULL CHECK (
        length(provider_result_hash) = 64
        AND provider_result_hash NOT GLOB '*[^0-9a-f]*'
    ),
    captured_at TEXT NOT NULL,
    capture_canonical_json TEXT NOT NULL CHECK (
        json_valid(capture_canonical_json)
        AND json_type(capture_canonical_json) = 'object'
    ),
    capture_content_hash TEXT NOT NULL CHECK (
        length(capture_content_hash) = 64
        AND capture_content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (model_invocation_id)
        REFERENCES model_invocations(model_invocation_id) ON DELETE RESTRICT
);

CREATE TABLE model_outputs (
    model_output_id TEXT PRIMARY KEY,
    model_invocation_id TEXT NOT NULL UNIQUE,
    raw_output_id TEXT NOT NULL UNIQUE,
    raw_output_capture_hash TEXT NOT NULL CHECK (
        length(raw_output_capture_hash) = 64
        AND raw_output_capture_hash NOT GLOB '*[^0-9a-f]*'
    ),
    raw_output_sha256 TEXT NOT NULL CHECK (
        length(raw_output_sha256) = 64
        AND raw_output_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    utf8_decode_status TEXT NOT NULL CHECK (
        utf8_decode_status IN ('decoded', 'undecodable')
    ),
    decoded_text TEXT,
    decode_errors_json TEXT NOT NULL CHECK (
        json_valid(decode_errors_json)
        AND json_type(decode_errors_json) = 'array'
    ),
    parse_status TEXT NOT NULL CHECK (
        parse_status IN ('parsed', 'malformed_json', 'not_attempted')
    ),
    parse_errors_json TEXT NOT NULL CHECK (
        json_valid(parse_errors_json)
        AND json_type(parse_errors_json) = 'array'
    ),
    parsed_canonical_json TEXT CHECK (
        parsed_canonical_json IS NULL OR json_valid(parsed_canonical_json)
    ),
    parsed_output_hash TEXT CHECK (
        parsed_output_hash IS NULL
        OR (
            length(parsed_output_hash) = 64
            AND parsed_output_hash NOT GLOB '*[^0-9a-f]*'
        )
    ),
    output_schema_id TEXT NOT NULL CHECK (trim(output_schema_id) <> ''),
    output_schema_hash TEXT NOT NULL CHECK (
        length(output_schema_hash) = 64
        AND output_schema_hash NOT GLOB '*[^0-9a-f]*'
    ),
    schema_status TEXT NOT NULL CHECK (
        schema_status IN ('valid', 'invalid', 'not_attempted')
    ),
    schema_errors_json TEXT NOT NULL CHECK (
        json_valid(schema_errors_json)
        AND json_type(schema_errors_json) = 'array'
    ),
    schema_valid INTEGER NOT NULL CHECK (schema_valid IN (0, 1)),
    semantic_status TEXT NOT NULL CHECK (
        semantic_status IN ('valid', 'invalid', 'not_attempted')
    ),
    semantic_errors_json TEXT NOT NULL CHECK (
        json_valid(semantic_errors_json)
        AND json_type(semantic_errors_json) = 'array'
    ),
    semantic_valid INTEGER NOT NULL CHECK (semantic_valid IN (0, 1)),
    repair_attempted INTEGER NOT NULL DEFAULT 0 CHECK (repair_attempted = 0),
    repair_succeeded INTEGER NOT NULL DEFAULT 0 CHECK (repair_succeeded = 0),
    canonical_json TEXT NOT NULL CHECK (
        json_valid(canonical_json) AND json_type(canonical_json) = 'object'
    ),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (model_invocation_id)
        REFERENCES model_invocations(model_invocation_id) ON DELETE RESTRICT,
    FOREIGN KEY (raw_output_id)
        REFERENCES model_raw_outputs(raw_output_id) ON DELETE RESTRICT,
    CHECK (
        (utf8_decode_status = 'decoded' AND decoded_text IS NOT NULL)
        OR
        (utf8_decode_status = 'undecodable' AND decoded_text IS NULL)
    ),
    CHECK (
        (parse_status = 'parsed'
            AND parsed_canonical_json IS NOT NULL
            AND parsed_output_hash IS NOT NULL)
        OR
        (parse_status <> 'parsed'
            AND parsed_canonical_json IS NULL
            AND parsed_output_hash IS NULL)
    ),
    CHECK (
        schema_valid = CASE WHEN schema_status = 'valid' THEN 1 ELSE 0 END
    ),
    CHECK (
        semantic_valid = CASE WHEN semantic_status = 'valid' THEN 1 ELSE 0 END
    )
);

CREATE TRIGGER model_invocations_validate_bindings
BEFORE INSERT ON model_invocations
WHEN NOT EXISTS (
    SELECT 1
    FROM tasks AS task
    JOIN sessions AS session_record
      ON session_record.session_id = task.session_id
    JOIN context_packages AS package
      ON package.context_package_id = NEW.context_package_id
    JOIN retrieval_manifests AS manifest
      ON manifest.retrieval_manifest_id = NEW.retrieval_manifest_id
    JOIN task_context_finalizations AS finalization
      ON finalization.finalization_id = NEW.task_context_finalization_id
    JOIN records AS identity_record
      ON identity_record.record_id = NEW.runtime_identity_id
    JOIN runtime_identities AS identity
      ON identity.record_id = identity_record.record_id
    JOIN governed_reference_anchors AS anchor
      ON anchor.reference_id = NEW.model_invocation_id
     AND anchor.reference_kind = NEW.reference_kind
     AND anchor.project_scope_id = NEW.project_scope_id
    WHERE task.task_id = NEW.task_id
      AND task.session_id = NEW.session_id
      AND task.project_scope_id = NEW.project_scope_id
      AND session_record.active_project_scope = NEW.project_scope_id
      AND package.task_id = NEW.task_id
      AND package.session_id = NEW.session_id
      AND package.project_scope_id = NEW.project_scope_id
      AND package.retrieval_manifest_id = NEW.retrieval_manifest_id
      AND package.content_hash = NEW.context_package_hash
      AND package.retrieval_manifest_hash = NEW.retrieval_manifest_hash
      AND package.task_memory_projection_hash =
          NEW.task_memory_projection_hash
      AND package.task_context_finalization_id =
          NEW.task_context_finalization_id
      AND manifest.task_id = NEW.task_id
      AND manifest.session_id = NEW.session_id
      AND manifest.project_scope_id = NEW.project_scope_id
      AND manifest.content_hash = NEW.retrieval_manifest_hash
      AND finalization.task_id = NEW.task_id
      AND finalization.session_id = NEW.session_id
      AND finalization.project_scope_id = NEW.project_scope_id
      AND finalization.content_hash = NEW.task_context_finalization_hash
      AND identity_record.project_scope_id = NEW.project_scope_id
      AND identity_record.content_hash = NEW.runtime_identity_hash
      AND identity_record.lifecycle_state = 'active'
      AND identity_record.approval_status IN ('approved', 'not_required')
      AND identity_record.integrity_status = 'valid'
      AND anchor.lifecycle_state = 'registered'
      AND anchor.integrity_status = 'valid'
)
BEGIN
    SELECT RAISE(ABORT, 'model invocation bindings are invalid');
END;

CREATE TRIGGER model_invocation_transitions_validate_current_state
BEFORE INSERT ON model_invocation_state_transitions
WHEN (
    NEW.sequence_number = 0
    AND (
        NEW.from_status IS NOT NULL
        OR NEW.to_status <> 'prepared'
        OR (
            SELECT current_status
            FROM model_invocations
            WHERE model_invocation_id = NEW.model_invocation_id
        ) <> 'prepared'
        OR EXISTS (
            SELECT 1
            FROM model_invocation_state_transitions
            WHERE model_invocation_id = NEW.model_invocation_id
        )
    )
)
OR (
    NEW.sequence_number > 0
    AND (
        (
            SELECT current_status
            FROM model_invocations
            WHERE model_invocation_id = NEW.model_invocation_id
        ) <> NEW.from_status
        OR NEW.sequence_number <> COALESCE((
            SELECT MAX(sequence_number) + 1
            FROM model_invocation_state_transitions
            WHERE model_invocation_id = NEW.model_invocation_id
        ), 0)
        OR NEW.changed_at < COALESCE((
            SELECT changed_at
            FROM model_invocation_state_transitions
            WHERE model_invocation_id = NEW.model_invocation_id
            ORDER BY sequence_number DESC
            LIMIT 1
        ), NEW.changed_at)
    )
)
BEGIN
    SELECT RAISE(ABORT, 'invocation transition does not match current state');
END;

CREATE TRIGGER model_invocations_status_requires_transition
BEFORE UPDATE OF current_status ON model_invocations
WHEN NEW.current_status <> OLD.current_status
AND NOT EXISTS (
    SELECT 1
    FROM model_invocation_state_transitions AS transition
    WHERE transition.model_invocation_id = OLD.model_invocation_id
      AND transition.sequence_number = (
          SELECT MAX(sequence_number)
          FROM model_invocation_state_transitions
          WHERE model_invocation_id = OLD.model_invocation_id
      )
      AND transition.from_status = OLD.current_status
      AND transition.to_status = NEW.current_status
)
BEGIN
    SELECT RAISE(ABORT, 'invocation status change requires a recorded transition');
END;

CREATE TRIGGER model_invocations_core_immutable
BEFORE UPDATE OF
    model_invocation_id, reference_kind, contract_version, task_id, session_id,
    project_scope_id, context_package_id, context_package_hash,
    retrieval_manifest_id, retrieval_manifest_hash,
    task_memory_projection_hash, task_context_finalization_id,
    task_context_finalization_hash, runtime_identity_id, runtime_identity_hash,
    provider_id, provider_descriptor_json, provider_descriptor_hash,
    provider_configuration_json, provider_configuration_hash,
    model_descriptor_json, model_descriptor_hash,
    inference_configuration_json, inference_configuration_hash,
    output_schema_id, output_schema_hash, model_input_packet_json,
    model_input_packet_hash, submission_json, submission_hash, request_json,
    request_hash, retry_of_invocation_id, prepared_at, runtime_principal
ON model_invocations
BEGIN
    SELECT RAISE(ABORT, 'model invocation request and bindings are immutable');
END;

CREATE TRIGGER model_invocations_terminal_immutable
BEFORE UPDATE ON model_invocations
WHEN OLD.current_status IN (
    'provider_inactive', 'succeeded', 'provider_failed', 'timed_out',
    'invalid_response', 'stale_context', 'interrupted'
)
BEGIN
    SELECT RAISE(ABORT, 'terminal model invocation is immutable');
END;

CREATE TRIGGER model_invocations_projection_update_requires_transition
BEFORE UPDATE ON model_invocations
WHEN NEW.current_status = OLD.current_status
AND (
    NEW.started_at IS NOT OLD.started_at
    OR NEW.completed_at IS NOT OLD.completed_at
    OR NEW.provider_call_attempt_id IS NOT OLD.provider_call_attempt_id
    OR NEW.provider_result_outcome IS NOT OLD.provider_result_outcome
    OR NEW.provider_result_json IS NOT OLD.provider_result_json
    OR NEW.provider_result_hash IS NOT OLD.provider_result_hash
    OR NEW.failure_classification IS NOT OLD.failure_classification
    OR NEW.terminal_result_json IS NOT OLD.terminal_result_json
    OR NEW.terminal_result_hash IS NOT OLD.terminal_result_hash
    OR NEW.task_disposition IS NOT OLD.task_disposition
    OR NEW.task_transition_id IS NOT OLD.task_transition_id
)
BEGIN
    SELECT RAISE(ABORT, 'invocation projection update requires a transition');
END;

CREATE TRIGGER model_invocations_validate_terminal_projection
BEFORE UPDATE OF current_status ON model_invocations
WHEN NEW.current_status IN (
    'provider_inactive', 'succeeded', 'provider_failed', 'timed_out',
    'invalid_response', 'stale_context', 'interrupted'
)
AND (
    NEW.completed_at IS NULL
    OR NEW.terminal_result_json IS NULL
    OR NEW.terminal_result_hash IS NULL
    OR NEW.task_disposition IS NULL
    OR (
        NEW.current_status <> 'interrupted'
        AND (
            NEW.provider_result_json IS NULL
            OR NEW.provider_result_hash IS NULL
            OR NEW.provider_result_outcome IS NULL
        )
    )
    OR (
        NEW.current_status = 'interrupted'
        AND NOT (
            (
                NEW.provider_result_json IS NULL
                AND NEW.provider_result_hash IS NULL
                AND NEW.provider_result_outcome IS NULL
            )
            OR
            (
                NEW.provider_result_json IS NOT NULL
                AND NEW.provider_result_hash IS NOT NULL
                AND NEW.provider_result_outcome IS NOT NULL
            )
        )
    )
    OR (
        NEW.task_transition_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1
            FROM task_state_transitions
            WHERE transition_id = NEW.task_transition_id
              AND task_id = NEW.task_id
        )
    )
    OR (
        OLD.current_status = 'raw_output_captured'
        AND NOT EXISTS (
            SELECT 1
            FROM model_outputs
            WHERE model_invocation_id = NEW.model_invocation_id
        )
    )
    OR (
        NEW.current_status = 'succeeded'
        AND NOT EXISTS (
            SELECT 1
            FROM model_outputs
            WHERE model_invocation_id = NEW.model_invocation_id
              AND utf8_decode_status = 'decoded'
              AND parse_status = 'parsed'
              AND schema_valid = 1
              AND semantic_valid = 1
        )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'terminal invocation projection is incomplete');
END;

CREATE TRIGGER model_raw_outputs_validate_capture
BEFORE INSERT ON model_raw_outputs
WHEN NOT EXISTS (
    SELECT 1
    FROM model_invocations
    WHERE model_invocation_id = NEW.model_invocation_id
      AND current_status = 'in_progress'
      AND provider_call_attempt_id = NEW.provider_call_attempt_id
      AND started_at IS NOT NULL
      AND NEW.captured_at >= started_at
)
OR length(NEW.raw_bytes) <> NEW.raw_byte_length
BEGIN
    SELECT RAISE(ABORT, 'raw output capture binding is invalid');
END;

CREATE TRIGGER model_outputs_validate_binding
BEFORE INSERT ON model_outputs
WHEN NOT EXISTS (
    SELECT 1
    FROM model_invocations AS invocation
    JOIN model_raw_outputs AS raw
      ON raw.model_invocation_id = invocation.model_invocation_id
    WHERE invocation.model_invocation_id = NEW.model_invocation_id
      AND invocation.current_status = 'raw_output_captured'
      AND raw.raw_output_id = NEW.raw_output_id
      AND raw.capture_content_hash = NEW.raw_output_capture_hash
      AND raw.raw_output_sha256 = NEW.raw_output_sha256
      AND invocation.output_schema_id = NEW.output_schema_id
      AND invocation.output_schema_hash = NEW.output_schema_hash
)
BEGIN
    SELECT RAISE(ABORT, 'model output binding is invalid');
END;

DROP TRIGGER governed_reference_anchor_ownerless_claim;

CREATE TRIGGER governed_reference_anchor_ownerless_claim
BEFORE UPDATE OF lifecycle_state ON governed_reference_anchors
WHEN OLD.lifecycle_state <> 'claimed'
AND NEW.lifecycle_state = 'claimed'
AND (
    NEW.reference_kind <> 'model_invocation'
    OR NOT EXISTS (
        SELECT 1
        FROM model_invocations
        WHERE model_invocation_id = NEW.reference_id
          AND reference_kind = NEW.reference_kind
          AND project_scope_id = NEW.project_scope_id
    )
)
BEGIN
    SELECT RAISE(ABORT, 'claimed anchor requires a transactional operational owner');
END;

CREATE TRIGGER model_invocation_state_transitions_immutable
BEFORE UPDATE ON model_invocation_state_transitions
BEGIN
    SELECT RAISE(ABORT, 'invocation transitions are immutable');
END;

CREATE TRIGGER model_invocation_state_transitions_no_delete
BEFORE DELETE ON model_invocation_state_transitions
BEGIN
    SELECT RAISE(ABORT, 'invocation transitions cannot be deleted');
END;

CREATE TRIGGER model_raw_outputs_immutable
BEFORE UPDATE ON model_raw_outputs
BEGIN
    SELECT RAISE(ABORT, 'raw provider outputs are immutable');
END;

CREATE TRIGGER model_raw_outputs_no_delete
BEFORE DELETE ON model_raw_outputs
BEGIN
    SELECT RAISE(ABORT, 'raw provider outputs cannot be deleted');
END;

CREATE TRIGGER model_outputs_immutable
BEFORE UPDATE ON model_outputs
BEGIN
    SELECT RAISE(ABORT, 'model outputs are immutable');
END;

CREATE TRIGGER model_outputs_no_delete
BEFORE DELETE ON model_outputs
BEGIN
    SELECT RAISE(ABORT, 'model outputs cannot be deleted');
END;

CREATE TRIGGER model_invocations_no_delete
BEFORE DELETE ON model_invocations
BEGIN
    SELECT RAISE(ABORT, 'model invocations cannot be deleted');
END;
