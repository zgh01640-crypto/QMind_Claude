-- 消耗量标准 2024 (SJG 171-2024) - 新表族
-- 完全隔离于现有 quota_* 表

CREATE TABLE IF NOT EXISTS quota2024_standards (
    id              SERIAL PRIMARY KEY,
    standard_code   VARCHAR(32) NOT NULL UNIQUE,   -- 如 "SJG 171-2024"
    name            TEXT NOT NULL,                 -- 如 "深圳市建筑工程消耗量标准"
    region          VARCHAR(64),                   -- "深圳市"
    base_date       DATE,
    source_file     TEXT,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quota2024_chapters (
    id              SERIAL PRIMARY KEY,
    standard_id     INTEGER NOT NULL REFERENCES quota2024_standards(id) ON DELETE CASCADE,
    chapter_no      INTEGER NOT NULL,              -- 0–9
    code            VARCHAR(16),                   -- 如 "2"
    name            TEXT NOT NULL,                 -- 如 "混凝土及钢筋混凝土工程"
    sort_order      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_quota2024_chapters_standard ON quota2024_chapters(standard_id);

CREATE TABLE IF NOT EXISTS quota2024_sections (
    id              SERIAL PRIMARY KEY,
    chapter_id      INTEGER NOT NULL REFERENCES quota2024_chapters(id) ON DELETE CASCADE,
    section_type    VARCHAR(16) NOT NULL,          -- 'intro' | 'rules' | 'items'
    section_code    VARCHAR(16),                   -- 如 "2.1", "2.2", "2.3"
    title           TEXT NOT NULL,                 -- 如 "说明", "工程量计算规则", "子目构成表"
    content_md      TEXT,                          -- Markdown 文本 (intro/rules用), NULL for items
    page_start      INTEGER,
    page_end        INTEGER
);
CREATE INDEX IF NOT EXISTS idx_quota2024_sections_chapter ON quota2024_sections(chapter_id);
CREATE INDEX IF NOT EXISTS idx_quota2024_sections_type ON quota2024_sections(chapter_id, section_type);

CREATE TABLE IF NOT EXISTS quota2024_groups (
    id              SERIAL PRIMARY KEY,
    section_id      INTEGER NOT NULL REFERENCES quota2024_sections(id) ON DELETE CASCADE,
    group_code      VARCHAR(32),                   -- 如 "2.3.1"
    group_name      TEXT NOT NULL,                 -- 如 "现浇预拌混凝土"
    sort_order      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_quota2024_groups_section ON quota2024_groups(section_id);

CREATE TABLE IF NOT EXISTS quota2024_items (
    id              SERIAL PRIMARY KEY,
    group_id        INTEGER NOT NULL REFERENCES quota2024_groups(id) ON DELETE CASCADE,
    item_no         INTEGER,                       -- 分组内序号，如 1, 2, 3
    item_name       TEXT NOT NULL,                 -- 如 "泵送现浇混凝土"
    work_content    TEXT,                          -- 工作内容完整文本
    unit            VARCHAR(32),                   -- 如 "10m³"
    sort_order      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_quota2024_items_group ON quota2024_items(group_id);

CREATE TABLE IF NOT EXISTS quota2024_subitems (
    id                  SERIAL PRIMARY KEY,
    item_id             INTEGER NOT NULL REFERENCES quota2024_items(id) ON DELETE CASCADE,
    subitem_code        VARCHAR(32) NOT NULL UNIQUE,  -- 如 "010002-1"
    subitem_name        TEXT,                         -- 子目名称 (如 "实心砖基础")
    variant_desc        TEXT,                         -- 变体描述 (如 "干混砌筑砂浆")
    sort_order          INTEGER NOT NULL DEFAULT 0,

    -- 全费用参考综合单价
    total_unit_price    NUMERIC(12,4),                -- 2023年8月全费用参考综合单价
    -- 参考综合单价
    unit_price          NUMERIC(12,4),                -- 2023年8月参考综合单价

    -- 全费用参考综合单价构成
    labor_cost          NUMERIC(12,4),                -- 人工费
    material_cost       NUMERIC(12,4),                -- 材料费
    machine_cost        NUMERIC(12,4),                -- 机械费
    management_fee      NUMERIC(12,4),                -- 管理费
    profit              NUMERIC(12,4),                -- 利润
    safety_fee          NUMERIC(12,4),                -- 安全文明施工措施费
    statutory_fee       NUMERIC(12,4),                -- 规费
    tax                 NUMERIC(12,4)                 -- 税金
);
CREATE INDEX IF NOT EXISTS idx_quota2024_subitems_item ON quota2024_subitems(item_id);

CREATE TABLE IF NOT EXISTS quota2024_resources (
    id              SERIAL PRIMARY KEY,
    subitem_id      INTEGER NOT NULL REFERENCES quota2024_subitems(id) ON DELETE CASCADE,
    resource_type   VARCHAR(8) NOT NULL,           -- '人工' | '材料' | '机械'
    resource_name   TEXT NOT NULL,                 -- 如 "普通混凝土实心砖 240×115×53 (10.0MPa)"
    unit            VARCHAR(32),                   -- 如 "千块", "m³", "台班"
    quantity        NUMERIC(14,6),                 -- 该子目消耗量
    ref_price       NUMERIC(12,4),                 -- 2023年8月工料机参考价格（元）
    sort_order      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_quota2024_resources_subitem ON quota2024_resources(subitem_id);
CREATE INDEX IF NOT EXISTS idx_quota2024_resources_type ON quota2024_resources(resource_type);
