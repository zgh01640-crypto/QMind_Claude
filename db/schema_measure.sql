-- 工程量计算标准（国标清单）
-- 文档：房屋建筑与装饰工程工程量计算标准.docx
-- 层级：标准 → 附录（分部工程）→ 节 → 清单项目表（含多条子项）

CREATE TABLE IF NOT EXISTS measure_standards (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL,
    source_file  TEXT,
    imported_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 章节树：支持 附录(level=1) → 节(level=2) 两层
CREATE TABLE IF NOT EXISTS measure_sections (
    id          SERIAL PRIMARY KEY,
    standard_id INTEGER NOT NULL REFERENCES measure_standards(id) ON DELETE CASCADE,
    code        TEXT,                -- 编号，如 "A", "A.1", "A.2"
    name        TEXT NOT NULL,       -- 名称，如 "土石方工程", "单独土石方"
    level       INTEGER NOT NULL,    -- 1=附录章, 2=节
    parent_id   INTEGER REFERENCES measure_sections(id),
    sort_order  INTEGER NOT NULL DEFAULT 0
);

-- 清单项目：对应表格中每一行（一个9位编码即一个项目）
CREATE TABLE IF NOT EXISTS measure_items (
    id              SERIAL PRIMARY KEY,
    standard_id     INTEGER NOT NULL REFERENCES measure_standards(id) ON DELETE CASCADE,
    section_id      INTEGER REFERENCES measure_sections(id),
    -- 编码与名称
    item_code       TEXT NOT NULL,   -- 9位编码，如 010101001
    item_name       TEXT NOT NULL,   -- 项目名称，如 "挖单独土方"
    -- 规格信息
    item_features   TEXT,            -- 项目特征（多行合并）
    unit            TEXT,            -- 计量单位
    calc_rule       TEXT,            -- 工程量计算规则
    work_content    TEXT             -- 工作内容
);

CREATE UNIQUE INDEX IF NOT EXISTS measure_items_code_std
    ON measure_items(standard_id, item_code);

CREATE INDEX IF NOT EXISTS measure_items_section
    ON measure_items(section_id);

CREATE INDEX IF NOT EXISTS measure_sections_standard
    ON measure_sections(standard_id, level);
