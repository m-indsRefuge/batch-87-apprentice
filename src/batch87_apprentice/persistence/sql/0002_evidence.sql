CREATE TABLE evidence_items (
    evidence_id TEXT PRIMARY KEY,
    evidence_kind TEXT NOT NULL CHECK (
        evidence_kind IN (
            'document', 'code', 'log', 'test_report', 'human_statement',
            'model_output', 'system_event', 'external_source',
            'controlled_prompt', 'controlled_output'
        )
    ),
    storage_kind TEXT NOT NULL CHECK (
        storage_kind IN (
            'inline_text', 'local_file', 'repository_reference',
            'external_reference', 'generated_record'
        )
    ),
    storage_location TEXT,
    original_name TEXT,
    media_type TEXT,
    byte_length INTEGER CHECK (byte_length IS NULL OR byte_length >= 0),
    content_hash TEXT NOT NULL CHECK (
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    captured_at TEXT NOT NULL,
    captured_by_entity TEXT,
    integrity_status TEXT NOT NULL CHECK (
        integrity_status IN ('valid', 'mismatch', 'unavailable')
    ),
    redaction_status TEXT NOT NULL CHECK (
        redaction_status IN ('none', 'partial', 'full')
    ),
    sensitivity_class TEXT NOT NULL CHECK (
        sensitivity_class IN (
            'public', 'internal', 'confidential', 'restricted', 'secret'
        )
    ),
    privacy_class TEXT NOT NULL CHECK (
        privacy_class IN (
            'none', 'personal', 'sensitive_personal', 'credential',
            'legally_restricted', 'unknown'
        )
    ),
    FOREIGN KEY (captured_by_entity)
        REFERENCES entities(entity_id) ON DELETE RESTRICT,
    CHECK (
        storage_kind <> 'inline_text' OR storage_location IS NULL
    ),
    CHECK (
        storage_kind = 'inline_text'
        OR storage_location IS NOT NULL
        OR storage_kind = 'generated_record'
    )
);

CREATE TABLE evidence_inline_text (
    evidence_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    encoding TEXT NOT NULL CHECK (encoding = 'utf-8'),
    FOREIGN KEY (evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT
);

CREATE TABLE record_evidence_links (
    record_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    relationship TEXT NOT NULL CHECK (
        relationship IN (
            'derived_from', 'supports', 'contradicts', 'contextualises',
            'does_not_establish', 'produced_as', 'evaluated_against'
        )
    ),
    explanation TEXT,
    PRIMARY KEY (record_id, evidence_id, relationship),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT,
    FOREIGN KEY (evidence_id)
        REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT
);

CREATE INDEX record_evidence_links_record
ON record_evidence_links(record_id);

CREATE INDEX record_evidence_links_evidence
ON record_evidence_links(evidence_id);

CREATE TRIGGER evidence_inline_requires_inline_storage
BEFORE INSERT ON evidence_inline_text
WHEN (
    SELECT storage_kind
    FROM evidence_items
    WHERE evidence_id = NEW.evidence_id
) <> 'inline_text'
BEGIN
    SELECT RAISE(ABORT, 'inline content requires inline_text storage');
END;

CREATE TRIGGER evidence_inline_content_immutable
BEFORE UPDATE ON evidence_inline_text
BEGIN
    SELECT RAISE(ABORT, 'inline evidence content is immutable');
END;

CREATE TRIGGER evidence_core_immutable
BEFORE UPDATE OF evidence_id, evidence_kind, storage_kind, storage_location,
                 byte_length, content_hash, captured_at
ON evidence_items
BEGIN
    SELECT RAISE(ABORT, 'evidence identity and content metadata are immutable');
END;
