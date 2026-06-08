-- 深圳市建筑工程消耗量标准 2024 - 独立解析表族
-- 不依赖旧 quota2024_* 表。

CREATE TABLE IF NOT EXISTS bs2024_documents (
    id              SERIAL PRIMARY KEY,
    standard_code   VARCHAR(64) NOT NULL,
    name            TEXT NOT NULL,
    region          VARCHAR(64),
    source_file     TEXT NOT NULL,
    source_sha256   VARCHAR(64) NOT NULL UNIQUE,
    page_count      INTEGER NOT NULL,
    publish_date    DATE,
    effective_date  DATE,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bs2024_parse_runs (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES bs2024_documents(id) ON DELETE CASCADE,
    status          VARCHAR(24) NOT NULL DEFAULT 'running',
    ocr_engine      VARCHAR(64) NOT NULL,
    dpi             INTEGER NOT NULL,
    page_start      INTEGER NOT NULL,
    page_end        INTEGER NOT NULL,
    stats_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_bs2024_runs_document ON bs2024_parse_runs(document_id);

CREATE TABLE IF NOT EXISTS bs2024_pages (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES bs2024_documents(id) ON DELETE CASCADE,
    run_id          INTEGER REFERENCES bs2024_parse_runs(id) ON DELETE SET NULL,
    page_no         INTEGER NOT NULL,
    page_type       VARCHAR(32) NOT NULL,
    chapter_no      INTEGER,
    chapter_title   TEXT,
    section_type    VARCHAR(32),
    section_code    VARCHAR(32),
    title           TEXT,
    ocr_text        TEXT,
    content_md      TEXT,
    raw_ocr_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence      NUMERIC(6,4),
    warning_count   INTEGER NOT NULL DEFAULT 0,
    parsed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, page_no)
);
CREATE INDEX IF NOT EXISTS idx_bs2024_pages_document_page ON bs2024_pages(document_id, page_no);
CREATE INDEX IF NOT EXISTS idx_bs2024_pages_type ON bs2024_pages(document_id, page_type);

CREATE TABLE IF NOT EXISTS bs2024_chapters (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES bs2024_documents(id) ON DELETE CASCADE,
    chapter_no      INTEGER NOT NULL,
    code            VARCHAR(32),
    title           TEXT NOT NULL,
    page_start      INTEGER,
    page_end        INTEGER,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    UNIQUE (document_id, chapter_no)
);
CREATE INDEX IF NOT EXISTS idx_bs2024_chapters_document ON bs2024_chapters(document_id);

CREATE TABLE IF NOT EXISTS bs2024_sections (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES bs2024_documents(id) ON DELETE CASCADE,
    chapter_id      INTEGER NOT NULL REFERENCES bs2024_chapters(id) ON DELETE CASCADE,
    section_type    VARCHAR(32) NOT NULL, -- intro | rules | items | directory | other
    section_code    VARCHAR(32),
    title           TEXT NOT NULL,
    content_md      TEXT,
    page_start      INTEGER,
    page_end        INTEGER,
    sort_order      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bs2024_sections_chapter ON bs2024_sections(chapter_id);
CREATE INDEX IF NOT EXISTS idx_bs2024_sections_type ON bs2024_sections(document_id, section_type);
CREATE UNIQUE INDEX IF NOT EXISTS uq_bs2024_sections_identity
    ON bs2024_sections(chapter_id, section_type, COALESCE(section_code, ''));

CREATE TABLE IF NOT EXISTS bs2024_item_groups (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES bs2024_documents(id) ON DELETE CASCADE,
    section_id      INTEGER NOT NULL REFERENCES bs2024_sections(id) ON DELETE CASCADE,
    group_code      VARCHAR(64),
    group_name      TEXT NOT NULL,
    page_start      INTEGER,
    page_end        INTEGER,
    sort_order      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bs2024_groups_section ON bs2024_item_groups(section_id);

CREATE TABLE IF NOT EXISTS bs2024_items (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES bs2024_documents(id) ON DELETE CASCADE,
    group_id        INTEGER NOT NULL REFERENCES bs2024_item_groups(id) ON DELETE CASCADE,
    item_no         INTEGER,
    item_name       TEXT NOT NULL,
    work_content    TEXT,
    unit            VARCHAR(64),
    page_no         INTEGER,
    raw_row_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    sort_order      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bs2024_items_group ON bs2024_items(group_id);
CREATE INDEX IF NOT EXISTS idx_bs2024_items_name ON bs2024_items USING gin (to_tsvector('simple', item_name));

CREATE TABLE IF NOT EXISTS bs2024_subitems (
    id                  SERIAL PRIMARY KEY,
    document_id         INTEGER NOT NULL REFERENCES bs2024_documents(id) ON DELETE CASCADE,
    item_id             INTEGER NOT NULL REFERENCES bs2024_items(id) ON DELETE CASCADE,
    subitem_code        VARCHAR(64) NOT NULL,
    subitem_name        TEXT,
    variant_desc        TEXT,
    unit                VARCHAR(64),
    name_path_json      JSONB NOT NULL DEFAULT '[]'::jsonb,
    total_unit_price    NUMERIC(14,4),
    unit_price          NUMERIC(14,4),
    labor_cost          NUMERIC(14,4),
    material_cost       NUMERIC(14,4),
    machine_cost        NUMERIC(14,4),
    management_fee      NUMERIC(14,4),
    profit              NUMERIC(14,4),
    safety_fee          NUMERIC(14,4),
    statutory_fee       NUMERIC(14,4),
    tax                 NUMERIC(14,4),
    page_no             INTEGER,
    confidence          NUMERIC(6,4),
    sort_order          INTEGER NOT NULL DEFAULT 0,
    UNIQUE (document_id, subitem_code)
);
CREATE INDEX IF NOT EXISTS idx_bs2024_subitems_item ON bs2024_subitems(item_id);
CREATE INDEX IF NOT EXISTS idx_bs2024_subitems_code ON bs2024_subitems(subitem_code);

CREATE TABLE IF NOT EXISTS bs2024_resources (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES bs2024_documents(id) ON DELETE CASCADE,
    subitem_id      INTEGER NOT NULL REFERENCES bs2024_subitems(id) ON DELETE CASCADE,
    resource_type   VARCHAR(16) NOT NULL,
    resource_name   TEXT NOT NULL,
    unit            VARCHAR(64),
    quantity        NUMERIC(18,6),
    ref_price       NUMERIC(14,4),
    page_no         INTEGER,
    sort_order      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bs2024_resources_subitem ON bs2024_resources(subitem_id);
CREATE INDEX IF NOT EXISTS idx_bs2024_resources_name ON bs2024_resources USING gin (to_tsvector('simple', resource_name));

CREATE TABLE IF NOT EXISTS bs2024_parse_issues (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES bs2024_documents(id) ON DELETE CASCADE,
    run_id          INTEGER REFERENCES bs2024_parse_runs(id) ON DELETE SET NULL,
    page_no         INTEGER,
    severity        VARCHAR(16) NOT NULL,
    issue_type      VARCHAR(64) NOT NULL,
    message         TEXT NOT NULL,
    context_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bs2024_issues_document ON bs2024_parse_issues(document_id);
CREATE INDEX IF NOT EXISTS idx_bs2024_issues_page ON bs2024_parse_issues(document_id, page_no);
