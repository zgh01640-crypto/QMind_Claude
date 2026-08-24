-- Versioned imports may legitimately reuse the same source file and row id.
ALTER TABLE tqdk_tqdxmtz
    DROP CONSTRAINT IF EXISTS tqdk_tqdxmtz_source_file_sha256_source_rowid_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_tqdk_tqdxmtz_version_row
    ON tqdk_tqdxmtz(kb_version_id, source_rowid);
