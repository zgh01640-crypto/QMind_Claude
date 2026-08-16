-- 应用账号、会话与业务数据所有权。所有语句均可重复执行。
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(64) NOT NULL UNIQUE,
    display_name    VARCHAR(120) NOT NULL,
    password_hash   TEXT NOT NULL,
    role            VARCHAR(16) NOT NULL CHECK (role IN ('admin', 'operator', 'reader')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      CHAR(64) NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_valid ON auth_sessions(token_hash, expires_at)
    WHERE revoked_at IS NULL;

DO $$ BEGIN
    IF to_regclass('boq_projects') IS NOT NULL THEN
        ALTER TABLE boq_projects ADD COLUMN IF NOT EXISTS owner_user_id INT REFERENCES users(id);
        CREATE INDEX IF NOT EXISTS idx_boq_projects_owner ON boq_projects(owner_user_id);
    END IF;
    IF to_regclass('manual_boq_projects') IS NOT NULL THEN
        ALTER TABLE manual_boq_projects ADD COLUMN IF NOT EXISTS owner_user_id INT REFERENCES users(id);
        CREATE INDEX IF NOT EXISTS idx_manual_boq_projects_owner ON manual_boq_projects(owner_user_id);
    END IF;
    IF to_regclass('pricing_tasks') IS NOT NULL THEN
        ALTER TABLE pricing_tasks ADD COLUMN IF NOT EXISTS owner_user_id INT REFERENCES users(id);
        CREATE INDEX IF NOT EXISTS idx_pricing_tasks_owner ON pricing_tasks(owner_user_id);
    END IF;
    IF to_regclass('pricing_task_batches') IS NOT NULL THEN
        ALTER TABLE pricing_task_batches ADD COLUMN IF NOT EXISTS owner_user_id INT REFERENCES users(id);
        CREATE INDEX IF NOT EXISTS idx_pricing_task_batches_owner ON pricing_task_batches(owner_user_id);
    END IF;
END $$;
