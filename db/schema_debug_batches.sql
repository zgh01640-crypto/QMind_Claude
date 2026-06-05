-- 调试批次
CREATE TABLE IF NOT EXISTS debug_batches (
    id                SERIAL PRIMARY KEY,
    name              VARCHAR(200) NOT NULL,
    boq_project_id    INT NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE,
    manual_project_id INT REFERENCES manual_boq_projects(id) ON DELETE SET NULL,
    standard_ids      TEXT NOT NULL,   -- JSON数组，如 "[1,2]"
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_db_project ON debug_batches(boq_project_id);

-- 每条清单项的推理结果（重跑时 UPSERT 覆盖）
CREATE TABLE IF NOT EXISTS debug_item_results (
    id          SERIAL PRIMARY KEY,
    batch_id    INT NOT NULL REFERENCES debug_batches(id) ON DELETE CASCADE,
    boq_item_id INT NOT NULL REFERENCES boq_items(id) ON DELETE CASCADE,
    reasoning_chain TEXT,
    result_json JSONB NOT NULL,   -- {matches:[...], missed:[...], manual_quotas:[...]}
    ran_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (batch_id, boq_item_id)
);

CREATE INDEX IF NOT EXISTS idx_dir_batch   ON debug_item_results(batch_id);
CREATE INDEX IF NOT EXISTS idx_dir_boq_item ON debug_item_results(boq_item_id);
