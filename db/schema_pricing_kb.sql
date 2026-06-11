-- Smart pricing knowledge base imported from SQLite.
-- This schema is independent from authoritative quota tables.

CREATE TABLE IF NOT EXISTS pricing_kb_import_runs (
    id                  BIGSERIAL PRIMARY KEY,
    source_file         TEXT NOT NULL,
    source_file_sha256  VARCHAR(64) NOT NULL,
    status              VARCHAR(24) NOT NULL DEFAULT 'running',
    stats_json          JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_import_runs_source
    ON pricing_kb_import_runs(source_file_sha256, created_at DESC);

CREATE TABLE IF NOT EXISTS pricing_kb_libraries (
    id                  BIGSERIAL PRIMARY KEY,
    source_library_id   BIGINT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_table        VARCHAR(64) NOT NULL DEFAULT 'TLibs',
    raw_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_libraries_name
    ON pricing_kb_libraries USING gin (to_tsvector('simple', name));

CREATE TABLE IF NOT EXISTS pricing_kb_chapters (
    id                  BIGSERIAL PRIMARY KEY,
    library_id          BIGINT NOT NULL REFERENCES pricing_kb_libraries(id) ON DELETE CASCADE,
    library_kind        VARCHAR(16) NOT NULL, -- boq | quota
    source_library_id   BIGINT NOT NULL,
    source_record_id    BIGINT NOT NULL,
    parent_source_id    BIGINT,
    parent_id           BIGINT REFERENCES pricing_kb_chapters(id) ON DELETE SET NULL,
    name                TEXT NOT NULL,
    description         TEXT,
    is_virtual          BOOLEAN NOT NULL DEFAULT FALSE,
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_table        VARCHAR(64) NOT NULL,
    raw_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (library_id, source_record_id, library_kind)
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_chapters_library
    ON pricing_kb_chapters(library_id, library_kind);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_chapters_parent
    ON pricing_kb_chapters(parent_id);

CREATE TABLE IF NOT EXISTS pricing_kb_boq_items (
    id                  BIGSERIAL PRIMARY KEY,
    library_id          BIGINT NOT NULL REFERENCES pricing_kb_libraries(id) ON DELETE CASCADE,
    chapter_id          BIGINT REFERENCES pricing_kb_chapters(id) ON DELETE SET NULL,
    source_library_id   BIGINT NOT NULL,
    source_record_id    BIGINT NOT NULL,
    code                VARCHAR(64),
    name                TEXT NOT NULL,
    unit                VARCHAR(64),
    source_chapter_id   BIGINT,
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_table        VARCHAR(64) NOT NULL DEFAULT 'TQDK_TQDZM',
    raw_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (library_id, source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_boq_items_code
    ON pricing_kb_boq_items(code);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_boq_items_name
    ON pricing_kb_boq_items USING gin (to_tsvector('simple', name));

CREATE TABLE IF NOT EXISTS pricing_kb_quota_items (
    id                  BIGSERIAL PRIMARY KEY,
    library_id          BIGINT NOT NULL REFERENCES pricing_kb_libraries(id) ON DELETE CASCADE,
    chapter_id          BIGINT REFERENCES pricing_kb_chapters(id) ON DELETE SET NULL,
    source_library_id   BIGINT NOT NULL,
    source_record_id    BIGINT NOT NULL,
    code                VARCHAR(64),
    name                TEXT NOT NULL,
    unit                VARCHAR(64),
    work_content        TEXT,
    source_chapter_id   BIGINT,
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_table        VARCHAR(64) NOT NULL DEFAULT 'TDEK_TDEZM',
    raw_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (library_id, source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_quota_items_code
    ON pricing_kb_quota_items(code);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_quota_items_name
    ON pricing_kb_quota_items USING gin (to_tsvector('simple', name));

CREATE TABLE IF NOT EXISTS pricing_kb_quota_resources (
    id                  BIGSERIAL PRIMARY KEY,
    quota_item_id       BIGINT NOT NULL REFERENCES pricing_kb_quota_items(id) ON DELETE CASCADE,
    source_library_id   BIGINT NOT NULL,
    source_record_id    BIGINT NOT NULL,
    resource_code       VARCHAR(64),
    resource_name       TEXT NOT NULL,
    unit                VARCHAR(64),
    quantity            NUMERIC(20,6),
    resource_type_code  INTEGER,
    resource_type       VARCHAR(32),
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_table        VARCHAR(64) NOT NULL DEFAULT 'TDEK_TZMGC',
    raw_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (quota_item_id, source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_resources_item
    ON pricing_kb_quota_resources(quota_item_id);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_resources_name
    ON pricing_kb_quota_resources USING gin (to_tsvector('simple', resource_name));

CREATE TABLE IF NOT EXISTS pricing_kb_conversion_rules (
    id                  BIGSERIAL PRIMARY KEY,
    quota_item_id       BIGINT NOT NULL REFERENCES pricing_kb_quota_items(id) ON DELETE CASCADE,
    source_library_id   BIGINT NOT NULL,
    source_record_id    BIGINT NOT NULL,
    rule_type           VARCHAR(24) NOT NULL, -- conversion | input_prompt
    prompt              TEXT,
    description         TEXT,
    group_no            INTEGER,
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_table        VARCHAR(64) NOT NULL,
    raw_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_table, source_library_id, source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_conversion_item
    ON pricing_kb_conversion_rules(quota_item_id);

CREATE TABLE IF NOT EXISTS pricing_kb_boq_quota_candidates (
    id                      BIGSERIAL PRIMARY KEY,
    boq_item_id             BIGINT NOT NULL REFERENCES pricing_kb_boq_items(id) ON DELETE CASCADE,
    quota_item_id           BIGINT NOT NULL REFERENCES pricing_kb_quota_items(id) ON DELETE CASCADE,
    source_library_id       BIGINT NOT NULL,
    source_record_id        BIGINT NOT NULL,
    source_quota_library_id BIGINT NOT NULL,
    source_file_sha256      VARCHAR(64) NOT NULL,
    source_table            VARCHAR(64) NOT NULL DEFAULT 'TQDK_TQDZY',
    raw_json                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_table, source_library_id, source_record_id)
);
ALTER TABLE pricing_kb_boq_quota_candidates
    ADD COLUMN IF NOT EXISTS source_record_id BIGINT;

DO $$
DECLARE
    constraint_name text;
BEGIN
    SELECT c.conname INTO constraint_name
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'public'
      AND t.relname = 'pricing_kb_boq_quota_candidates'
      AND c.contype = 'u'
      AND pg_get_constraintdef(c.oid) LIKE '%boq_item_id%'
      AND pg_get_constraintdef(c.oid) LIKE '%quota_item_id%'
      AND pg_get_constraintdef(c.oid) LIKE '%source_library_id%'
    LIMIT 1;

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE pricing_kb_boq_quota_candidates DROP CONSTRAINT %I', constraint_name);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_pricing_kb_candidates_source_row
    ON pricing_kb_boq_quota_candidates(source_table, source_library_id, source_record_id);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_candidates_boq
    ON pricing_kb_boq_quota_candidates(boq_item_id);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_candidates_quota
    ON pricing_kb_boq_quota_candidates(quota_item_id);

CREATE TABLE IF NOT EXISTS pricing_kb_target_links (
    id                  BIGSERIAL PRIMARY KEY,
    quota_item_id       BIGINT NOT NULL REFERENCES pricing_kb_quota_items(id) ON DELETE CASCADE,
    target_table        VARCHAR(64) NOT NULL,
    target_item_id      BIGINT,
    link_status         VARCHAR(24) NOT NULL,
    link_method         VARCHAR(64) NOT NULL,
    similarity_score    NUMERIC(8,4),
    review_message      TEXT,
    source_file_sha256  VARCHAR(64) NOT NULL,
    raw_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (quota_item_id, target_table)
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_target_links_status
    ON pricing_kb_target_links(link_status);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_target_links_target
    ON pricing_kb_target_links(target_table, target_item_id);

CREATE TABLE IF NOT EXISTS pricing_kb_import_issues (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              BIGINT REFERENCES pricing_kb_import_runs(id) ON DELETE CASCADE,
    source_file_sha256  VARCHAR(64) NOT NULL,
    severity            VARCHAR(16) NOT NULL,
    issue_type          VARCHAR(64) NOT NULL,
    message             TEXT NOT NULL,
    source_table        VARCHAR(64),
    source_library_id   BIGINT,
    source_record_id    BIGINT,
    context_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_issues_run
    ON pricing_kb_import_issues(run_id);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_issues_source
    ON pricing_kb_import_issues(source_file_sha256, issue_type);
