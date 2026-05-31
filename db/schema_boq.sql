-- 工程项目（每次导入一个文件对应一条记录）
CREATE TABLE IF NOT EXISTS boq_projects (
    id          SERIAL PRIMARY KEY,
    project_name VARCHAR(500) NOT NULL,
    bid_section  VARCHAR(500),
    source_file  VARCHAR(255),
    tag          VARCHAR(100),
    imported_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (source_file)
);

-- 分部（土石方工程、砌筑工程等）
CREATE TABLE IF NOT EXISTS boq_sections (
    id          SERIAL PRIMARY KEY,
    project_id  INT NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE,
    seq         INT,
    section_name VARCHAR(200) NOT NULL
);

-- 清单项
CREATE TABLE IF NOT EXISTS boq_items (
    id                  SERIAL PRIMARY KEY,
    project_id          INT NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE,
    section_id          INT REFERENCES boq_sections(id),
    item_seq            INT,
    item_code           VARCHAR(50),
    item_name           VARCHAR(200) NOT NULL,
    item_description    TEXT,
    unit                VARCHAR(30),
    quantity            NUMERIC(16, 4),
    unit_price          NUMERIC(16, 2),
    total_price         NUMERIC(16, 2),
    provisional_price   NUMERIC(16, 2)
);

CREATE INDEX IF NOT EXISTS idx_boq_items_project ON boq_items(project_id);
CREATE INDEX IF NOT EXISTS idx_boq_items_code    ON boq_items(item_code);
CREATE INDEX IF NOT EXISTS idx_boq_items_section ON boq_items(section_id);

-- AI 套定额匹配结果（一条清单项可对应多条定额子目）
CREATE TABLE IF NOT EXISTS boq_quota_matches (
    id              SERIAL PRIMARY KEY,
    project_id      INT NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE,
    boq_item_id     INT NOT NULL REFERENCES boq_items(id) ON DELETE CASCADE,
    quota_item_id   INT NOT NULL REFERENCES quota_items(id),
    standard_id     INT NOT NULL REFERENCES quota_standards(id),
    qty_factor      NUMERIC(10, 4) DEFAULT 1.0,
    ai_reasoning    TEXT,
    confidence      VARCHAR(10),
    status          VARCHAR(20) DEFAULT 'ai',
    confirmed_at    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (run_id, boq_item_id, quota_item_id)
);
CREATE INDEX IF NOT EXISTS idx_bqm_project  ON boq_quota_matches(project_id);
CREATE INDEX IF NOT EXISTS idx_bqm_boq_item ON boq_quota_matches(boq_item_id);

-- 追加 reasoning_chain 列（idempotent）
ALTER TABLE boq_quota_matches ADD COLUMN IF NOT EXISTS reasoning_chain TEXT;

-- 套定额批次记录
CREATE TABLE IF NOT EXISTS boq_match_runs (
    id            SERIAL PRIMARY KEY,
    project_id    INT NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE,
    standard_id   INT NOT NULL REFERENCES quota_standards(id),
    standard_code VARCHAR(50),
    status        VARCHAR(20) DEFAULT 'running',
    total_items   INT DEFAULT 0,
    matched_items INT DEFAULT 0,
    created_at    TIMESTAMP DEFAULT NOW(),
    finished_at   TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bmr_project ON boq_match_runs(project_id);

-- boq_quota_matches 追加 run_id
ALTER TABLE boq_quota_matches ADD COLUMN IF NOT EXISTS run_id INT REFERENCES boq_match_runs(id);
CREATE INDEX IF NOT EXISTS idx_bqm_run ON boq_quota_matches(run_id);
