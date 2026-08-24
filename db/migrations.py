"""Explicit, recorded database migrations for pricing knowledge-base changes."""

from __future__ import annotations

from pathlib import Path

from db.schema_lock import acquire_schema_transaction_lock


MIGRATIONS = (
    ("20260824_pricing_kb_schema_contract", Path(__file__).with_name("migrations") / "20260824_pricing_kb_schema_contract.sql"),
)


def apply_pending_migrations(conn, *, lock_timeout_ms: int = 5_000) -> list[str]:
    """Apply ordered migrations once, failing safely when a table is busy."""
    applied: list[str] = []
    acquire_schema_transaction_lock(conn)
    with conn.cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS db_schema_migrations (
                migration_id VARCHAR(128) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""
        )
        cur.execute("SET LOCAL lock_timeout = %s", (f"{lock_timeout_ms}ms",))
        for migration_id, path in MIGRATIONS:
            cur.execute("SELECT 1 FROM db_schema_migrations WHERE migration_id=%s", (migration_id,))
            if cur.fetchone():
                continue
            cur.execute(path.read_text(encoding="utf-8"))
            cur.execute("INSERT INTO db_schema_migrations(migration_id) VALUES(%s)", (migration_id,))
            applied.append(migration_id)
    conn.commit()
    return applied
