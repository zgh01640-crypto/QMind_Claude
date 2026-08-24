"""Maintenance-window entry point for pricing knowledge-base migrations."""

from __future__ import annotations

from db.connection import get_connection
from db.migrations import apply_pending_migrations


def main() -> None:
    conn = get_connection()
    try:
        applied = apply_pending_migrations(conn)
        print("Applied pricing knowledge-base migrations: " + (", ".join(applied) or "none"))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
