-- 新工程管理：基于 bs2024_* 定额库的套定额结果表
-- 清单数据来源：boq_projects / boq_sections / boq_items（只读复用）
-- 定额来源：bs2024_subitems（bs2024_* 表族）

CREATE TABLE IF NOT EXISTS bs2024_match_runs (
    id            SERIAL PRIMARY KEY,
    project_id    INT NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE,
    chapter_id    INT NOT NULL REFERENCES bs2024_chapters(id),
    chapter_name  VARCHAR(200),
    run_name      VARCHAR(200),
    status        VARCHAR(20) DEFAULT 'running',
    total_items   INT DEFAULT 0,
    matched_items INT DEFAULT 0,
    created_at    TIMESTAMP DEFAULT NOW(),
    finished_at   TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bs2024_match_runs_project ON bs2024_match_runs(project_id);

CREATE TABLE IF NOT EXISTS bs2024_quota_matches (
    id                 SERIAL PRIMARY KEY,
    run_id             INT NOT NULL REFERENCES bs2024_match_runs(id) ON DELETE CASCADE,
    boq_item_id        INT NOT NULL REFERENCES boq_items(id) ON DELETE CASCADE,
    subitem_id         INT NOT NULL REFERENCES bs2024_subitems(id),
    subitem_code       VARCHAR(50),
    work_procedure     VARCHAR(200),
    qty_factor         NUMERIC(10,4) DEFAULT 1.0,
    factor_explanation TEXT,
    ai_reasoning       TEXT,
    reasoning_chain    TEXT,
    confidence         VARCHAR(10),
    missing_info       TEXT,
    status             VARCHAR(20) DEFAULT 'ai',
    created_at         TIMESTAMP DEFAULT NOW(),
    UNIQUE (run_id, boq_item_id, subitem_id)
);

CREATE INDEX IF NOT EXISTS idx_bs2024_quota_matches_run ON bs2024_quota_matches(run_id);
CREATE INDEX IF NOT EXISTS idx_bs2024_quota_matches_boq ON bs2024_quota_matches(boq_item_id);
