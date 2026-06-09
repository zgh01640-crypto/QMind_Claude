-- Cross-standard reference prices parsed from appendices.

CREATE TABLE IF NOT EXISTS standard_reference_prices (
    id              BIGSERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES bs2024_documents(id) ON DELETE CASCADE,
    appendix_code   VARCHAR(32) NOT NULL,
    sequence_no     INTEGER NOT NULL,
    resource_type   VARCHAR(16) NOT NULL,
    name            TEXT NOT NULL,
    unit            VARCHAR(64) NOT NULL,
    price           NUMERIC(18,4) NOT NULL,
    source_page_no  INTEGER NOT NULL,
    source_page_id  INTEGER REFERENCES bs2024_pages(id) ON DELETE SET NULL,
    confidence      NUMERIC(6,4),
    raw_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_standard_reference_prices_sequence
        UNIQUE (document_id, appendix_code, sequence_no),
    CONSTRAINT ck_standard_reference_prices_sequence_positive CHECK (sequence_no > 0),
    CONSTRAINT ck_standard_reference_prices_price_positive CHECK (price > 0),
    CONSTRAINT ck_standard_reference_prices_resource_type
        CHECK (resource_type IN ('材料', '机械'))
);

CREATE INDEX IF NOT EXISTS idx_standard_reference_prices_document
    ON standard_reference_prices(document_id, appendix_code);
CREATE INDEX IF NOT EXISTS idx_standard_reference_prices_name
    ON standard_reference_prices USING gin (to_tsvector('simple', name));
CREATE INDEX IF NOT EXISTS idx_standard_reference_prices_unit
    ON standard_reference_prices(unit);
CREATE INDEX IF NOT EXISTS idx_standard_reference_prices_resource_type
    ON standard_reference_prices(resource_type);

