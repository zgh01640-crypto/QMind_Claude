-- 人工套定额工程管理（独立表，不依赖 AI 匹配流程）

CREATE TABLE IF NOT EXISTS manual_boq_projects (
    id          SERIAL PRIMARY KEY,
    project_name VARCHAR(500) NOT NULL,
    bid_section  VARCHAR(500),
    source_file  VARCHAR(500),
    tag          VARCHAR(100),
    imported_at  TIMESTAMPTZ DEFAULT NOW(),
    item_count   INT
);

CREATE TABLE IF NOT EXISTS manual_boq_sections (
    id          SERIAL PRIMARY KEY,
    project_id  INT NOT NULL REFERENCES manual_boq_projects(id) ON DELETE CASCADE,
    seq         INT,
    section_name VARCHAR(300) NOT NULL
);

CREATE TABLE IF NOT EXISTS manual_boq_items (
    id               SERIAL PRIMARY KEY,
    project_id       INT NOT NULL REFERENCES manual_boq_projects(id) ON DELETE CASCADE,
    section_id       INT REFERENCES manual_boq_sections(id) ON DELETE SET NULL,
    item_seq         INT,
    item_code        VARCHAR(100),
    item_name        VARCHAR(500),
    item_description TEXT,
    unit             VARCHAR(50),
    quantity         NUMERIC(20,6),
    unit_price       NUMERIC(20,6),
    total_price      NUMERIC(20,6)
);

CREATE TABLE IF NOT EXISTS manual_boq_quotas (
    id            SERIAL PRIMARY KEY,
    boq_item_id   INT NOT NULL REFERENCES manual_boq_items(id) ON DELETE CASCADE,
    quota_code    VARCHAR(200),       -- 原始编码，可含公式如 120001-214+120001-215*25
    quota_name    VARCHAR(500),
    quota_unit    VARCHAR(50),
    quantity      NUMERIC(20,6),      -- Excel 中归一化数量
    unit_price    NUMERIC(20,6),
    total_price   NUMERIC(20,6),
    qty_factor    NUMERIC(20,8),      -- quantity / boq_item.quantity
    quota_item_id INT REFERENCES quota_items(id) ON DELETE SET NULL  -- 可选链接
);
