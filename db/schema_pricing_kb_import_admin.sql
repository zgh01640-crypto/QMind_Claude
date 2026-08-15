-- Admin-managed uploads, import jobs, table lineage, and raw unknown tables.

ALTER TABLE pricing_kb_versions ADD COLUMN IF NOT EXISTS parent_version_id BIGINT REFERENCES pricing_kb_versions(id);
ALTER TABLE pricing_kb_versions ADD COLUMN IF NOT EXISTS manifest_sha256 VARCHAR(64);
ALTER TABLE pricing_kb_versions DROP CONSTRAINT IF EXISTS pricing_kb_versions_source_file_sha256_key;
CREATE INDEX IF NOT EXISTS idx_pricing_kb_versions_source_hash ON pricing_kb_versions(source_file_sha256);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pricing_kb_versions_manifest
    ON pricing_kb_versions(manifest_sha256) WHERE manifest_sha256 IS NOT NULL;

ALTER TABLE tlibs DROP CONSTRAINT IF EXISTS tlibs_source_file_sha256_source_rowid_key;
ALTER TABLE tqdk_tzjmc DROP CONSTRAINT IF EXISTS tqdk_tzjmc_source_file_sha256_source_rowid_key;
ALTER TABLE tdek_tzjmc DROP CONSTRAINT IF EXISTS tdek_tzjmc_source_file_sha256_source_rowid_key;
ALTER TABLE tqdk_tqdzm DROP CONSTRAINT IF EXISTS tqdk_tqdzm_source_file_sha256_source_rowid_key;
ALTER TABLE tdek_tdezm DROP CONSTRAINT IF EXISTS tdek_tdezm_source_file_sha256_source_rowid_key;
ALTER TABLE tdek_tzmgc DROP CONSTRAINT IF EXISTS tdek_tzmgc_source_file_sha256_source_rowid_key;
ALTER TABLE tdek_tznhs DROP CONSTRAINT IF EXISTS tdek_tznhs_source_file_sha256_source_rowid_key;
ALTER TABLE tdek_tzhhs DROP CONSTRAINT IF EXISTS tdek_tzhhs_source_file_sha256_source_rowid_key;
ALTER TABLE tqdk_tqdzy DROP CONSTRAINT IF EXISTS tqdk_tqdzy_source_file_sha256_source_rowid_key;
ALTER TABLE tqdk_tqdzy_special DROP CONSTRAINT IF EXISTS tqdk_tqdzy_special_source_file_sha256_source_rowid_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_tlibs_version_row ON tlibs(kb_version_id,source_rowid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tqdk_tzjmc_version_row ON tqdk_tzjmc(kb_version_id,source_rowid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tdek_tzjmc_version_row ON tdek_tzjmc(kb_version_id,source_rowid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tqdk_tqdzm_version_row ON tqdk_tqdzm(kb_version_id,source_rowid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tdek_tdezm_version_row ON tdek_tdezm(kb_version_id,source_rowid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tdek_tzmgc_version_row ON tdek_tzmgc(kb_version_id,source_rowid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tdek_tznhs_version_row ON tdek_tznhs(kb_version_id,source_rowid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tdek_tzhhs_version_row ON tdek_tzhhs(kb_version_id,source_rowid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tqdk_tqdzy_version_row ON tqdk_tqdzy(kb_version_id,source_rowid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tqdk_tqdzy_special_version_row ON tqdk_tqdzy_special(kb_version_id,source_rowid);

CREATE TABLE IF NOT EXISTS pricing_kb_uploads (
    id BIGSERIAL PRIMARY KEY,
    original_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    file_sha256 VARCHAR(64) NOT NULL UNIQUE,
    size_bytes BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('inspected','failed')),
    quick_check TEXT,
    schema_signature VARCHAR(64),
    inspection_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pricing_kb_import_profiles (
    profile_id VARCHAR(64) PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    selected_tables JSONB NOT NULL,
    required_tables JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pricing_kb_import_jobs (
    id BIGSERIAL PRIMARY KEY,
    upload_id BIGINT NOT NULL REFERENCES pricing_kb_uploads(id),
    profile_id VARCHAR(64) REFERENCES pricing_kb_import_profiles(profile_id),
    parent_version_id BIGINT REFERENCES pricing_kb_versions(id),
    version_id BIGINT REFERENCES pricing_kb_versions(id),
    config_json JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','validated','failed','cancel_requested','cancelled')),
    current_table TEXT,
    completed_tables INTEGER NOT NULL DEFAULT 0,
    total_tables INTEGER NOT NULL DEFAULT 0,
    processed_rows BIGINT NOT NULL DEFAULT 0,
    progress_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_import_jobs_claim
    ON pricing_kb_import_jobs(status, lease_expires_at, created_at);

CREATE TABLE IF NOT EXISTS pricing_kb_version_tables (
    version_id BIGINT NOT NULL REFERENCES pricing_kb_versions(id) ON DELETE CASCADE,
    source_table VARCHAR(128) NOT NULL,
    data_version_id BIGINT NOT NULL REFERENCES pricing_kb_versions(id),
    upload_id BIGINT REFERENCES pricing_kb_uploads(id),
    source_file_sha256 VARCHAR(64),
    schema_signature VARCHAR(64),
    storage_kind VARCHAR(16) NOT NULL CHECK (storage_kind IN ('typed','raw')),
    is_inherited BOOLEAN NOT NULL DEFAULT FALSE,
    row_count BIGINT NOT NULL DEFAULT 0,
    validation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY(version_id, source_table)
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_version_tables_data
    ON pricing_kb_version_tables(data_version_id, source_table);

CREATE TABLE IF NOT EXISTS pricing_kb_raw_tables (
    version_id BIGINT NOT NULL REFERENCES pricing_kb_versions(id) ON DELETE CASCADE,
    source_table VARCHAR(128) NOT NULL,
    columns_json JSONB NOT NULL,
    schema_signature VARCHAR(64) NOT NULL,
    row_count BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY(version_id, source_table)
);

CREATE TABLE IF NOT EXISTS pricing_kb_raw_rows (
    version_id BIGINT NOT NULL REFERENCES pricing_kb_versions(id) ON DELETE CASCADE,
    source_table VARCHAR(128) NOT NULL,
    source_rowid BIGINT NOT NULL,
    raw_json JSONB NOT NULL,
    PRIMARY KEY(version_id, source_table, source_rowid)
);
CREATE INDEX IF NOT EXISTS idx_pricing_kb_raw_rows_table
    ON pricing_kb_raw_rows(version_id, source_table, source_rowid);

INSERT INTO pricing_kb_import_profiles(profile_id,name,description,selected_tables,required_tables,is_system)
VALUES
 ('full-pricing','完整组价库','九张核心清单、定额和规则表',
  '["TLibs","TQDK_TZJMC","TDEK_TZJMC","TQDK_TQDZM","TDEK_TDEZM","TDEK_TZMGC","TDEK_TZNHS","TDEK_TZHHS","TQDK_TQDZY","TQDK_TQDZY_SPECIAL"]',
  '["TLibs","TQDK_TQDZM","TDEK_TDEZM","TQDK_TQDZY"]',TRUE),
 ('quota-update','定额更新','定额目录、章节、子目、资源和规则',
  '["TLibs","TDEK_TZJMC","TDEK_TDEZM","TDEK_TZMGC","TDEK_TZNHS","TDEK_TZHHS"]',
  '["TLibs","TDEK_TDEZM"]',TRUE),
 ('boq-update','清单更新','清单目录、章节、子目和候选关系',
  '["TLibs","TQDK_TZJMC","TQDK_TQDZM","TQDK_TQDZY","TQDK_TQDZY_SPECIAL","TDEK_TDEZM"]',
  '["TLibs","TQDK_TQDZM","TQDK_TQDZY","TDEK_TDEZM"]',TRUE)
ON CONFLICT (profile_id) DO UPDATE
SET selected_tables=EXCLUDED.selected_tables,
    required_tables=EXCLUDED.required_tables,
    updated_at=NOW()
WHERE pricing_kb_import_profiles.is_system=TRUE;

-- Existing complete versions own all their source tables.
INSERT INTO pricing_kb_version_tables(
    version_id, source_table, data_version_id, source_file_sha256, storage_kind, is_inherited, row_count
)
SELECT v.id, table_name, v.id, v.source_file_sha256, 'typed', FALSE, 0
FROM pricing_kb_versions v
CROSS JOIN unnest(ARRAY[
 'TLibs','TQDK_TZJMC','TDEK_TZJMC','TQDK_TQDZM','TDEK_TDEZM',
 'TDEK_TZMGC','TDEK_TZNHS','TDEK_TZHHS','TQDK_TQDZY','TQDK_TQDZY_SPECIAL'
]) table_name
ON CONFLICT (version_id, source_table) DO NOTHING;

-- Legacy replace modes could move only some physical tables to a newer version
-- without changing the active release pointer. Reconstruct those table owners
-- from the rows that actually exist instead of assuming every release is full.
DO $$
DECLARE
    source_name TEXT;
    physical_name TEXT;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pricing_kb_version_migrations
        WHERE migration_key='table-lineage-from-physical-rows-v1'
    ) THEN
        FOREACH source_name IN ARRAY ARRAY[
            'TLibs','TQDK_TZJMC','TDEK_TZJMC','TQDK_TQDZM','TDEK_TDEZM',
            'TDEK_TZMGC','TDEK_TZNHS','TDEK_TZHHS','TQDK_TQDZY','TQDK_TQDZY_SPECIAL'
        ] LOOP
            physical_name := lower(source_name);
            EXECUTE format($sql$
                WITH owners AS (
                    SELECT kb_version_id, COUNT(*)::BIGINT AS row_count
                    FROM %I
                    WHERE kb_version_id IS NOT NULL
                    GROUP BY kb_version_id
                ), resolved AS (
                    SELECT mapping.version_id,
                           COALESCE(
                               (SELECT MAX(owner.kb_version_id)
                                FROM owners owner
                                WHERE owner.kb_version_id <= mapping.version_id),
                               (SELECT MIN(owner.kb_version_id)
                                FROM owners owner
                                WHERE owner.kb_version_id > mapping.version_id)
                           ) AS data_version_id
                    FROM pricing_kb_version_tables mapping
                    JOIN pricing_kb_versions version ON version.id=mapping.version_id
                    WHERE mapping.source_table=%L
                      AND version.manifest_sha256 IS NULL
                )
                UPDATE pricing_kb_version_tables mapping
                SET data_version_id=resolved.data_version_id,
                    is_inherited=(resolved.data_version_id <> mapping.version_id),
                    row_count=owner.row_count
                FROM resolved
                JOIN owners owner ON owner.kb_version_id=resolved.data_version_id
                WHERE mapping.version_id=resolved.version_id
                  AND mapping.source_table=%L
            $sql$, physical_name, source_name, source_name);
        END LOOP;

        INSERT INTO pricing_kb_version_migrations(migration_key)
        VALUES ('table-lineage-from-physical-rows-v1');
    END IF;
END $$;

CREATE OR REPLACE FUNCTION pricing_kb_data_version(release_id BIGINT, table_name TEXT)
RETURNS BIGINT LANGUAGE SQL STABLE AS $$
    SELECT COALESCE(
      (SELECT data_version_id FROM pricing_kb_version_tables
       WHERE version_id=release_id AND upper(source_table)=upper(table_name)),
      release_id
    )
$$;

CREATE OR REPLACE VIEW active_tlibs AS
SELECT t.* FROM tlibs t JOIN pricing_kb_active_version a ON TRUE
WHERE t.kb_version_id=pricing_kb_data_version(a.kb_version_id,'TLibs');
CREATE OR REPLACE VIEW active_tqdk_tzjmc AS
SELECT t.* FROM tqdk_tzjmc t JOIN pricing_kb_active_version a ON TRUE
WHERE t.kb_version_id=pricing_kb_data_version(a.kb_version_id,'TQDK_TZJMC');
CREATE OR REPLACE VIEW active_tdek_tzjmc AS
SELECT t.* FROM tdek_tzjmc t JOIN pricing_kb_active_version a ON TRUE
WHERE t.kb_version_id=pricing_kb_data_version(a.kb_version_id,'TDEK_TZJMC');
CREATE OR REPLACE VIEW active_tqdk_tqdzm AS
SELECT t.* FROM tqdk_tqdzm t JOIN pricing_kb_active_version a ON TRUE
WHERE t.kb_version_id=pricing_kb_data_version(a.kb_version_id,'TQDK_TQDZM');
CREATE OR REPLACE VIEW active_tdek_tdezm AS
SELECT t.* FROM tdek_tdezm t JOIN pricing_kb_active_version a ON TRUE
WHERE t.kb_version_id=pricing_kb_data_version(a.kb_version_id,'TDEK_TDEZM');
CREATE OR REPLACE VIEW active_tdek_tzmgc AS
SELECT t.* FROM tdek_tzmgc t JOIN pricing_kb_active_version a ON TRUE
WHERE t.kb_version_id=pricing_kb_data_version(a.kb_version_id,'TDEK_TZMGC');
CREATE OR REPLACE VIEW active_tdek_tznhs AS
SELECT t.* FROM tdek_tznhs t JOIN pricing_kb_active_version a ON TRUE
WHERE t.kb_version_id=pricing_kb_data_version(a.kb_version_id,'TDEK_TZNHS');
CREATE OR REPLACE VIEW active_tdek_tzhhs AS
SELECT t.* FROM tdek_tzhhs t JOIN pricing_kb_active_version a ON TRUE
WHERE t.kb_version_id=pricing_kb_data_version(a.kb_version_id,'TDEK_TZHHS');
CREATE OR REPLACE VIEW active_tqdk_tqdzy AS
SELECT t.* FROM tqdk_tqdzy t JOIN pricing_kb_active_version a ON TRUE
WHERE t.kb_version_id=pricing_kb_data_version(a.kb_version_id,'TQDK_TQDZY');
CREATE OR REPLACE VIEW active_tqdk_tqdzy_special AS
SELECT t.* FROM tqdk_tqdzy_special t JOIN pricing_kb_active_version a ON TRUE
WHERE t.kb_version_id=pricing_kb_data_version(a.kb_version_id,'TQDK_TQDZY_SPECIAL');
