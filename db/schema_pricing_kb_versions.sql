-- Immutable versions for SQLite knowledge-base imports.

CREATE TABLE IF NOT EXISTS pricing_kb_versions (
    id                  BIGSERIAL PRIMARY KEY,
    source_file         TEXT NOT NULL,
    source_file_sha256  VARCHAR(64) NOT NULL UNIQUE,
    status              VARCHAR(16) NOT NULL DEFAULT 'importing'
                        CHECK (status IN ('importing', 'validated', 'active', 'retired', 'failed')),
    schema_signature    VARCHAR(64),
    table_counts        JSONB NOT NULL DEFAULT '{}'::jsonb,
    validation_report   JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message       TEXT,
    imported_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    validated_at        TIMESTAMPTZ,
    published_at        TIMESTAMPTZ,
    published_by        TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_versions_status
    ON pricing_kb_versions(status, imported_at DESC);

CREATE TABLE IF NOT EXISTS pricing_kb_active_version (
    singleton           BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    kb_version_id       BIGINT NOT NULL REFERENCES pricing_kb_versions(id),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by          TEXT
);

CREATE TABLE IF NOT EXISTS pricing_kb_version_migrations (
    migration_key       VARCHAR(64) PRIMARY KEY,
    completed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE pricing_kb_import_runs ADD COLUMN IF NOT EXISTS kb_version_id BIGINT;
ALTER TABLE pricing_kb_import_issues ADD COLUMN IF NOT EXISTS kb_version_id BIGINT;

-- Register data imported before version support was introduced.
INSERT INTO pricing_kb_versions (
    source_file, source_file_sha256, status, imported_at, validated_at
)
SELECT DISTINCT ON (source_file_sha256)
       source_file, source_file_sha256, 'validated',
       COALESCE(finished_at, created_at), COALESCE(finished_at, created_at)
FROM pricing_kb_import_runs
WHERE status = 'done'
ORDER BY source_file_sha256, COALESCE(finished_at, created_at) DESC
ON CONFLICT (source_file_sha256) DO NOTHING;

-- Every imported source row belongs to exactly one immutable version.
ALTER TABLE tlibs ADD COLUMN IF NOT EXISTS kb_version_id BIGINT;
ALTER TABLE tqdk_tzjmc ADD COLUMN IF NOT EXISTS kb_version_id BIGINT;
ALTER TABLE tdek_tzjmc ADD COLUMN IF NOT EXISTS kb_version_id BIGINT;
ALTER TABLE tqdk_tqdzm ADD COLUMN IF NOT EXISTS kb_version_id BIGINT;
ALTER TABLE tdek_tdezm ADD COLUMN IF NOT EXISTS kb_version_id BIGINT;
ALTER TABLE tdek_tzmgc ADD COLUMN IF NOT EXISTS kb_version_id BIGINT;
ALTER TABLE tdek_tznhs ADD COLUMN IF NOT EXISTS kb_version_id BIGINT;
ALTER TABLE tdek_tzhhs ADD COLUMN IF NOT EXISTS kb_version_id BIGINT;
ALTER TABLE tqdk_tqdzy ADD COLUMN IF NOT EXISTS kb_version_id BIGINT;

-- Some early imports may have rows without a matching import-run record.
INSERT INTO pricing_kb_versions (source_file, source_file_sha256, status, validated_at)
SELECT 'legacy:' || source_file_sha256, source_file_sha256, 'validated', NOW()
FROM (
    SELECT source_file_sha256 FROM tlibs
    UNION SELECT source_file_sha256 FROM tqdk_tzjmc
    UNION SELECT source_file_sha256 FROM tdek_tzjmc
    UNION SELECT source_file_sha256 FROM tqdk_tqdzm
    UNION SELECT source_file_sha256 FROM tdek_tdezm
    UNION SELECT source_file_sha256 FROM tdek_tzmgc
    UNION SELECT source_file_sha256 FROM tdek_tznhs
    UNION SELECT source_file_sha256 FROM tdek_tzhhs
    UNION SELECT source_file_sha256 FROM tqdk_tqdzy
) sources
WHERE source_file_sha256 IS NOT NULL
ON CONFLICT (source_file_sha256) DO NOTHING;

UPDATE tlibs t SET kb_version_id=v.id FROM pricing_kb_versions v
 WHERE t.kb_version_id IS NULL AND v.source_file_sha256=t.source_file_sha256;
UPDATE tqdk_tzjmc t SET kb_version_id=v.id FROM pricing_kb_versions v
 WHERE t.kb_version_id IS NULL AND v.source_file_sha256=t.source_file_sha256;
UPDATE tdek_tzjmc t SET kb_version_id=v.id FROM pricing_kb_versions v
 WHERE t.kb_version_id IS NULL AND v.source_file_sha256=t.source_file_sha256;
UPDATE tqdk_tqdzm t SET kb_version_id=v.id FROM pricing_kb_versions v
 WHERE t.kb_version_id IS NULL AND v.source_file_sha256=t.source_file_sha256;
UPDATE tdek_tdezm t SET kb_version_id=v.id FROM pricing_kb_versions v
 WHERE t.kb_version_id IS NULL AND v.source_file_sha256=t.source_file_sha256;
UPDATE tdek_tzmgc t SET kb_version_id=v.id FROM pricing_kb_versions v
 WHERE t.kb_version_id IS NULL AND v.source_file_sha256=t.source_file_sha256;
UPDATE tdek_tznhs t SET kb_version_id=v.id FROM pricing_kb_versions v
 WHERE t.kb_version_id IS NULL AND v.source_file_sha256=t.source_file_sha256;
UPDATE tdek_tzhhs t SET kb_version_id=v.id FROM pricing_kb_versions v
 WHERE t.kb_version_id IS NULL AND v.source_file_sha256=t.source_file_sha256;
UPDATE tqdk_tqdzy t SET kb_version_id=v.id FROM pricing_kb_versions v
 WHERE t.kb_version_id IS NULL AND v.source_file_sha256=t.source_file_sha256;

-- Preserve current behavior when upgrading an already populated installation.
INSERT INTO pricing_kb_active_version(singleton, kb_version_id, updated_by)
SELECT TRUE, t.kb_version_id, 'legacy-migration'
FROM tlibs t
WHERE t.kb_version_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM pricing_kb_version_migrations
      WHERE migration_key='baseline-active-initialized'
  )
ORDER BY t.updated_at DESC
LIMIT 1
ON CONFLICT (singleton) DO NOTHING;
UPDATE pricing_kb_versions v
SET status='active', published_at=COALESCE(published_at, NOW()),
    published_by=COALESCE(published_by, 'legacy-migration'), updated_at=NOW()
FROM pricing_kb_active_version a
WHERE v.id=a.kb_version_id AND v.status='validated';
INSERT INTO pricing_kb_version_migrations(migration_key)
VALUES ('baseline-active-initialized')
ON CONFLICT (migration_key) DO NOTHING;

-- Old business-key constraints prevented the same IDs from existing in two versions.
ALTER TABLE tlibs DROP CONSTRAINT IF EXISTS tlibs_id_key;
ALTER TABLE tqdk_tzjmc DROP CONSTRAINT IF EXISTS tqdk_tzjmc_qdkid_id_key;
ALTER TABLE tdek_tzjmc DROP CONSTRAINT IF EXISTS tdek_tzjmc_dekid_id_key;
ALTER TABLE tqdk_tqdzm DROP CONSTRAINT IF EXISTS tqdk_tqdzm_qdkid_id_key;
ALTER TABLE tdek_tdezm DROP CONSTRAINT IF EXISTS tdek_tdezm_dekid_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_tlibs_version_id
    ON tlibs(kb_version_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tqdk_tzjmc_version_item
    ON tqdk_tzjmc(kb_version_id, qdkid, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tdek_tzjmc_version_item
    ON tdek_tzjmc(kb_version_id, dekid, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tqdk_tqdzm_version_item
    ON tqdk_tqdzm(kb_version_id, qdkid, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tdek_tdezm_version_item
    ON tdek_tdezm(kb_version_id, dekid, id);

CREATE INDEX IF NOT EXISTS idx_tqdk_tzjmc_version_parent
    ON tqdk_tzjmc(kb_version_id, qdkid, pid);
CREATE INDEX IF NOT EXISTS idx_tdek_tzjmc_version_parent
    ON tdek_tzjmc(kb_version_id, dekid, pid);
CREATE INDEX IF NOT EXISTS idx_tqdk_tqdzm_version_chapter
    ON tqdk_tqdzm(kb_version_id, qdkid, zjh);
CREATE INDEX IF NOT EXISTS idx_tqdk_tqdzm_version_code
    ON tqdk_tqdzm(kb_version_id, zmbh);
CREATE INDEX IF NOT EXISTS idx_tdek_tdezm_version_chapter
    ON tdek_tdezm(kb_version_id, dekid, zjh);
CREATE INDEX IF NOT EXISTS idx_tdek_tdezm_version_code
    ON tdek_tdezm(kb_version_id, zmbh);
CREATE INDEX IF NOT EXISTS idx_tdek_tzmgc_version_item
    ON tdek_tzmgc(kb_version_id, dekid, dezmid);
CREATE INDEX IF NOT EXISTS idx_tdek_tzhhs_version_item
    ON tdek_tzhhs(kb_version_id, dekid, dezmid);
CREATE INDEX IF NOT EXISTS idx_tdek_tzhhs_version_code
    ON tdek_tzhhs(kb_version_id, dekid, zmbh);
CREATE INDEX IF NOT EXISTS idx_tdek_tznhs_version_item
    ON tdek_tznhs(kb_version_id, dekid, dezmid);
CREATE INDEX IF NOT EXISTS idx_tqdk_tqdzy_version_boq
    ON tqdk_tqdzy(kb_version_id, qdkid, qdzmid);
CREATE INDEX IF NOT EXISTS idx_tqdk_tqdzy_version_quota
    ON tqdk_tqdzy(kb_version_id, dekid, dezmid);

-- Existing read-only APIs use these views and always see the published version.
CREATE OR REPLACE VIEW active_tlibs AS
SELECT t.* FROM tlibs t JOIN pricing_kb_active_version a ON a.kb_version_id=t.kb_version_id;
CREATE OR REPLACE VIEW active_tqdk_tzjmc AS
SELECT t.* FROM tqdk_tzjmc t JOIN pricing_kb_active_version a ON a.kb_version_id=t.kb_version_id;
CREATE OR REPLACE VIEW active_tdek_tzjmc AS
SELECT t.* FROM tdek_tzjmc t JOIN pricing_kb_active_version a ON a.kb_version_id=t.kb_version_id;
CREATE OR REPLACE VIEW active_tqdk_tqdzm AS
SELECT t.* FROM tqdk_tqdzm t JOIN pricing_kb_active_version a ON a.kb_version_id=t.kb_version_id;
CREATE OR REPLACE VIEW active_tdek_tdezm AS
SELECT t.* FROM tdek_tdezm t JOIN pricing_kb_active_version a ON a.kb_version_id=t.kb_version_id;
CREATE OR REPLACE VIEW active_tdek_tzmgc AS
SELECT t.* FROM tdek_tzmgc t JOIN pricing_kb_active_version a ON a.kb_version_id=t.kb_version_id;
CREATE OR REPLACE VIEW active_tdek_tznhs AS
SELECT t.* FROM tdek_tznhs t JOIN pricing_kb_active_version a ON a.kb_version_id=t.kb_version_id;
CREATE OR REPLACE VIEW active_tdek_tzhhs AS
SELECT t.* FROM tdek_tzhhs t JOIN pricing_kb_active_version a ON a.kb_version_id=t.kb_version_id;
CREATE OR REPLACE VIEW active_tqdk_tqdzy AS
SELECT t.* FROM tqdk_tqdzy t JOIN pricing_kb_active_version a ON a.kb_version_id=t.kb_version_id;
