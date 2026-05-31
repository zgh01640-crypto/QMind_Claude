-- 每次导入的期次元数据
CREATE TABLE IF NOT EXISTS price_periods (
    id          SERIAL PRIMARY KEY,
    year        INT NOT NULL,
    month       INT NOT NULL,
    version     INT NOT NULL DEFAULT 0,
    source_file VARCHAR(255),
    imported_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (year, month, version)
);

-- Sheet 分类表（首次导入时自动填充）
CREATE TABLE IF NOT EXISTS price_categories (
    id             SERIAL PRIMARY KEY,
    sheet_index    INT NOT NULL,
    sheet_name     VARCHAR(150) NOT NULL,
    category_group TEXT,
    UNIQUE (sheet_index, sheet_name)
);

-- 主价格数据表
CREATE TABLE IF NOT EXISTS price_items (
    id                  SERIAL PRIMARY KEY,
    period_id           INT NOT NULL REFERENCES price_periods(id) ON DELETE CASCADE,
    category_id         INT NOT NULL REFERENCES price_categories(id),
    sequence_no         INT,
    material_code       VARCHAR(50),
    material_name       VARCHAR(255) NOT NULL,
    specification       VARCHAR(200),
    unit                VARCHAR(30),
    price_yuan          NUMERIC(12,2),
    coefficient         NUMERIC(10,4),
    calculation_formula VARCHAR(500),
    remarks             VARCHAR(500)
);

CREATE INDEX IF NOT EXISTS idx_price_items_period ON price_items(period_id);
CREATE INDEX IF NOT EXISTS idx_price_items_name   ON price_items(material_name);
CREATE INDEX IF NOT EXISTS idx_price_items_code   ON price_items(material_code);
