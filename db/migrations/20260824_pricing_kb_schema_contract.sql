-- Business-field parity with 智能组价系统库-海吉星练习8.6.db.
-- Run through `python -m db.migrate_pricing_kb` during a maintenance window.

ALTER TABLE tlibs ADD COLUMN IF NOT EXISTS isqdk BOOLEAN;

ALTER TABLE tqdk_tqdzm ADD COLUMN IF NOT EXISTS gznr TEXT;
ALTER TABLE tqdk_tqdzm ADD COLUMN IF NOT EXISTS locked BOOLEAN;

ALTER TABLE tqdk_tqdxmtz ADD COLUMN IF NOT EXISTS id BIGINT;

ALTER TABLE tdek_tzmgc ADD COLUMN IF NOT EXISTS dj DOUBLE PRECISION;
ALTER TABLE tdek_tzmgc ADD COLUMN IF NOT EXISTS zycl BOOLEAN;
ALTER TABLE tdek_tzmgc ADD COLUMN IF NOT EXISTS id BIGINT;

ALTER TABLE tdek_tznhs ADD COLUMN IF NOT EXISTS id BIGINT;
ALTER TABLE tqdk_tqdzy ADD COLUMN IF NOT EXISTS id BIGINT;

-- PostgreSQL prevents a type change while the active-version view references
-- the columns. The view is recreated immediately after the conversion.
DROP VIEW IF EXISTS active_tqdk_tqdxmtz;

DO $$
DECLARE
    invalid_zytz TEXT;
    invalid_bctz TEXT;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='tqdk_tqdxmtz'
          AND column_name='zytz' AND data_type IN ('text', 'character varying')
    ) THEN
        RETURN;
    END IF;

    SELECT zytz INTO invalid_zytz
    FROM tqdk_tqdxmtz
    WHERE zytz IS NOT NULL
      AND lower(btrim(zytz)) NOT IN ('-1', '0', '1', 'true', 'false')
    LIMIT 1;
    IF invalid_zytz IS NOT NULL THEN
        RAISE EXCEPTION 'cannot convert tqdk_tqdxmtz.zytz value to BOOLEAN: %', invalid_zytz;
    END IF;

    SELECT bctz INTO invalid_bctz
    FROM tqdk_tqdxmtz
    WHERE bctz IS NOT NULL
      AND lower(btrim(bctz)) NOT IN ('-1', '0', '1', 'true', 'false')
    LIMIT 1;
    IF invalid_bctz IS NOT NULL THEN
        RAISE EXCEPTION 'cannot convert tqdk_tqdxmtz.bctz value to BOOLEAN: %', invalid_bctz;
    END IF;

    ALTER TABLE tqdk_tqdxmtz
        ALTER COLUMN zytz TYPE BOOLEAN
        USING CASE
            WHEN zytz IS NULL THEN NULL
            WHEN lower(btrim(zytz)) IN ('-1', '1', 'true') THEN TRUE
            ELSE FALSE
        END;
    ALTER TABLE tqdk_tqdxmtz
        ALTER COLUMN bctz TYPE BOOLEAN
        USING CASE
            WHEN bctz IS NULL THEN NULL
            WHEN lower(btrim(bctz)) IN ('-1', '1', 'true') THEN TRUE
            ELSE FALSE
        END;
END $$;

CREATE OR REPLACE VIEW active_tqdk_tqdxmtz AS
SELECT t.* FROM tqdk_tqdxmtz t JOIN pricing_kb_active_version a ON TRUE
WHERE t.kb_version_id=pricing_kb_data_version(a.kb_version_id,'TQDK_TQDXMTZ');
