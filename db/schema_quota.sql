-- 消耗量标准版本表
CREATE TABLE IF NOT EXISTS quota_standards (
    id            SERIAL PRIMARY KEY,
    standard_code VARCHAR(50) NOT NULL,
    name          VARCHAR(200) NOT NULL,
    base_date     DATE,
    source_file   VARCHAR(255),
    imported_at   TIMESTAMP DEFAULT NOW(),
    UNIQUE (standard_code)
);

-- 章节层级表（章→节→子节）
CREATE TABLE IF NOT EXISTS quota_chapters (
    id          SERIAL PRIMARY KEY,
    standard_id INT NOT NULL REFERENCES quota_standards(id) ON DELETE CASCADE,
    code        VARCHAR(20),
    name        TEXT NOT NULL,
    parent_id   INT REFERENCES quota_chapters(id),
    level       SMALLINT NOT NULL DEFAULT 1,
    sort_order  INT NOT NULL DEFAULT 0
);

-- 子目主表（每变体存一行）
CREATE TABLE IF NOT EXISTS quota_items (
    id               SERIAL PRIMARY KEY,
    standard_id      INT NOT NULL REFERENCES quota_standards(id) ON DELETE CASCADE,
    chapter_id       INT REFERENCES quota_chapters(id),
    item_code        VARCHAR(30) NOT NULL,
    item_name        TEXT NOT NULL,
    variant_desc     TEXT,
    unit             VARCHAR(30),
    work_content     TEXT,
    total_unit_price NUMERIC(14,4),
    unit_price       NUMERIC(14,4),
    labor_cost       NUMERIC(14,4),
    material_cost    NUMERIC(14,4),
    machine_cost     NUMERIC(14,4),
    management_fee   NUMERIC(14,4),
    profit           NUMERIC(14,4),
    safety_fee       NUMERIC(14,4),
    statutory_fee    NUMERIC(14,4),
    tax              NUMERIC(14,4),
    source_row       INT
);

-- 工料机消耗量表
CREATE TABLE IF NOT EXISTS quota_resources (
    id            SERIAL PRIMARY KEY,
    item_id       INT NOT NULL REFERENCES quota_items(id) ON DELETE CASCADE,
    resource_type VARCHAR(10) NOT NULL,
    resource_name TEXT NOT NULL,
    unit          VARCHAR(30),
    quantity      NUMERIC(14,6),
    ref_price     NUMERIC(14,4)
);

CREATE INDEX IF NOT EXISTS idx_quota_items_standard ON quota_items(standard_id);
CREATE INDEX IF NOT EXISTS idx_quota_items_code     ON quota_items(item_code);
CREATE INDEX IF NOT EXISTS idx_quota_items_chapter  ON quota_items(chapter_id);
CREATE INDEX IF NOT EXISTS idx_quota_resources_item ON quota_resources(item_id);
