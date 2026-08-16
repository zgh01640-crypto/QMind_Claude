"""Serialize idempotent schema migrations across API processes."""

from __future__ import annotations


# ASCII-ish marker for "QMINDSCH". PostgreSQL advisory locks are cluster-wide,
# so every schema initializer must use the same key and lock ordering.
SCHEMA_ADVISORY_LOCK_ID = 5858419290781467464


def acquire_schema_transaction_lock(conn) -> None:
    """Hold the shared schema lock until the current transaction ends."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (SCHEMA_ADVISORY_LOCK_ID,),
        )
