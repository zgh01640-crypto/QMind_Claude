-- SQLite-shaped smart pricing knowledge base tables.
-- Table and column names mirror the SQLite source, lower-cased for PostgreSQL.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

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

CREATE TABLE IF NOT EXISTS tlibs (
    id                  BIGINT NOT NULL,
    mc                  TEXT,
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_rowid        BIGINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_file_sha256, source_rowid),
    UNIQUE (id)
);
CREATE INDEX IF NOT EXISTS idx_tlibs_mc ON tlibs(mc);

CREATE TABLE IF NOT EXISTS tqdk_tzjmc (
    qdkid               BIGINT,
    id                  BIGINT,
    pid                 BIGINT,
    zjmc                TEXT,
    zjsm                TEXT,
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_rowid        BIGINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_file_sha256, source_rowid),
    UNIQUE (qdkid, id)
);
CREATE INDEX IF NOT EXISTS idx_tqdk_tzjmc_parent ON tqdk_tzjmc(qdkid, pid);
CREATE INDEX IF NOT EXISTS idx_tqdk_tzjmc_name ON tqdk_tzjmc USING gin (to_tsvector('simple', COALESCE(zjmc, '')));

CREATE TABLE IF NOT EXISTS tdek_tzjmc (
    dekid               BIGINT,
    id                  BIGINT,
    pid                 BIGINT,
    zjmc                TEXT,
    zjsm                TEXT,
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_rowid        BIGINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_file_sha256, source_rowid),
    UNIQUE (dekid, id)
);
CREATE INDEX IF NOT EXISTS idx_tdek_tzjmc_parent ON tdek_tzjmc(dekid, pid);
CREATE INDEX IF NOT EXISTS idx_tdek_tzjmc_name ON tdek_tzjmc USING gin (to_tsvector('simple', COALESCE(zjmc, '')));

CREATE TABLE IF NOT EXISTS tqdk_tqdzm (
    qdkid               BIGINT,
    id                  BIGINT,
    zmbh                VARCHAR(64),
    zmmc                TEXT,
    dw                  VARCHAR(64),
    zjh                 BIGINT,
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_rowid        BIGINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_file_sha256, source_rowid),
    UNIQUE (qdkid, id)
);
CREATE INDEX IF NOT EXISTS idx_tqdk_tqdzm_code ON tqdk_tqdzm(zmbh);
CREATE INDEX IF NOT EXISTS idx_tqdk_tqdzm_chapter ON tqdk_tqdzm(qdkid, zjh);
CREATE INDEX IF NOT EXISTS idx_tqdk_tqdzm_name ON tqdk_tqdzm USING gin (to_tsvector('simple', COALESCE(zmmc, '')));

CREATE TABLE IF NOT EXISTS tdek_tdezm (
    dekid               BIGINT,
    id                  BIGINT,
    zmbh                VARCHAR(64),
    zmmc                TEXT,
    dw                  VARCHAR(64),
    gznr                TEXT,
    zjh                 BIGINT,
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_rowid        BIGINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_file_sha256, source_rowid),
    UNIQUE (dekid, id)
);
ALTER TABLE tdek_tdezm ADD COLUMN IF NOT EXISTS dj NUMERIC(18,2);
ALTER TABLE tdek_tdezm ADD COLUMN IF NOT EXISTS rgf NUMERIC(18,2);
ALTER TABLE tdek_tdezm ADD COLUMN IF NOT EXISTS clf NUMERIC(18,2);
ALTER TABLE tdek_tdezm ADD COLUMN IF NOT EXISTS jxf NUMERIC(18,2);
ALTER TABLE tdek_tdezm ADD COLUMN IF NOT EXISTS zcf NUMERIC(18,2);
ALTER TABLE tdek_tdezm ADD COLUMN IF NOT EXISTS sbf NUMERIC(18,2);
ALTER TABLE tdek_tdezm ADD COLUMN IF NOT EXISTS glf NUMERIC(18,2);
ALTER TABLE tdek_tdezm ADD COLUMN IF NOT EXISTS lr NUMERIC(18,2);
ALTER TABLE tdek_tdezm ADD COLUMN IF NOT EXISTS aqwmsgf NUMERIC(18,2);
ALTER TABLE tdek_tdezm ADD COLUMN IF NOT EXISTS qtcsf NUMERIC(18,2);
ALTER TABLE tdek_tdezm ADD COLUMN IF NOT EXISTS gf NUMERIC(18,2);
ALTER TABLE tdek_tdezm ADD COLUMN IF NOT EXISTS sj NUMERIC(18,2);
CREATE INDEX IF NOT EXISTS idx_tdek_tdezm_code ON tdek_tdezm(zmbh);
CREATE INDEX IF NOT EXISTS idx_tdek_tdezm_chapter ON tdek_tdezm(dekid, zjh);
CREATE INDEX IF NOT EXISTS idx_tdek_tdezm_name ON tdek_tdezm USING gin (to_tsvector('simple', COALESCE(zmmc, '')));
CREATE INDEX IF NOT EXISTS idx_tdek_tdezm_code_trgm ON tdek_tdezm USING gin (COALESCE(zmbh, '') gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tdek_tdezm_name_trgm ON tdek_tdezm USING gin (COALESCE(zmmc, '') gin_trgm_ops);

CREATE TABLE IF NOT EXISTS tdek_tzmgc (
    dekid               BIGINT,
    dezmid              BIGINT,
    zmbh                VARCHAR(64),
    zmmc                TEXT,
    dw                  VARCHAR(64),
    gcl                 NUMERIC(20,6),
    lx                  INTEGER,
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_rowid        BIGINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_file_sha256, source_rowid)
);
CREATE INDEX IF NOT EXISTS idx_tdek_tzmgc_item ON tdek_tzmgc(dekid, dezmid);
CREATE INDEX IF NOT EXISTS idx_tdek_tzmgc_name ON tdek_tzmgc USING gin (to_tsvector('simple', COALESCE(zmmc, '')));

CREATE TABLE IF NOT EXISTS tdek_tznhs (
    dekid               BIGINT,
    dezmid              BIGINT,
    tsxx                TEXT,
    hssm                TEXT,
    groupno             INTEGER,
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_rowid        BIGINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_file_sha256, source_rowid)
);
CREATE INDEX IF NOT EXISTS idx_tdek_tznhs_item ON tdek_tznhs(dekid, dezmid);

CREATE TABLE IF NOT EXISTS tdek_tzhhs (
    dekid               BIGINT,
    dezmid              BIGINT,
    tsxx                TEXT,
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_rowid        BIGINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_file_sha256, source_rowid)
);
ALTER TABLE tdek_tzhhs ADD COLUMN IF NOT EXISTS zmbh VARCHAR(64);
ALTER TABLE tdek_tzhhs ADD COLUMN IF NOT EXISTS jcz NUMERIC(20,6);
ALTER TABLE tdek_tzhhs ADD COLUMN IF NOT EXISTS zjdw NUMERIC(20,6);
CREATE INDEX IF NOT EXISTS idx_tdek_tzhhs_item ON tdek_tzhhs(dekid, dezmid);
CREATE INDEX IF NOT EXISTS idx_tdek_tzhhs_adjustment_code ON tdek_tzhhs(dekid, zmbh);

CREATE TABLE IF NOT EXISTS tqdk_tqdzy (
    qdkid               BIGINT,
    qdzmid              BIGINT,
    dekid               BIGINT,
    dezmid              BIGINT,
    zmbh                VARCHAR(64),
    zmmc                TEXT,
    dw                  VARCHAR(64),
    source_file_sha256  VARCHAR(64) NOT NULL,
    source_rowid        BIGINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_file_sha256, source_rowid)
);
CREATE INDEX IF NOT EXISTS idx_tqdk_tqdzy_boq ON tqdk_tqdzy(qdkid, qdzmid);
CREATE INDEX IF NOT EXISTS idx_tqdk_tqdzy_quota ON tqdk_tqdzy(dekid, dezmid);

CREATE TABLE IF NOT EXISTS pricing_kb_original_target_links (
    id                  BIGSERIAL PRIMARY KEY,
    dekid               BIGINT NOT NULL,
    dezmid              BIGINT NOT NULL,
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
    UNIQUE (dekid, dezmid, target_table)
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_original_links_status
    ON pricing_kb_original_target_links(link_status);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_original_links_target
    ON pricing_kb_original_target_links(target_table, target_item_id);

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
