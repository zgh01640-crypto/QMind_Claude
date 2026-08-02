from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any


SCHEMA_PATH = Path(__file__).with_name("schema_pricing_kb_versions.sql")
ADMIN_SCHEMA_PATH = Path(__file__).with_name("schema_pricing_kb_import_admin.sql")
_SCHEMA_LOCK = Lock()
_SCHEMA_APPLIED = False


def apply_version_schema(conn) -> None:
    global _SCHEMA_APPLIED
    if _SCHEMA_APPLIED:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_APPLIED:
            return
        with conn.cursor() as cur:
            cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
            cur.execute(ADMIN_SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
        _SCHEMA_APPLIED = True


def get_active_version_id(conn, *, required: bool = True) -> int | None:
    with conn.cursor() as cur:
        cur.execute("SELECT kb_version_id FROM pricing_kb_active_version WHERE singleton=TRUE")
        row = cur.fetchone()
    if row:
        return int(row[0])
    if required:
        raise RuntimeError("No active pricing knowledge-base version has been published")
    return None


def resolve_version_id(conn, requested: int | None) -> int:
    if requested is None:
        return int(get_active_version_id(conn))
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM pricing_kb_versions
            WHERE id=%s AND status IN ('validated', 'active', 'retired')
            """,
            (requested,),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError(f"Knowledge-base version is unavailable: {requested}")
    return int(row[0])


def version_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": int(row[0]),
        "source_file": row[1],
        "source_file_sha256": row[2],
        "status": row[3],
        "schema_signature": row[4],
        "table_counts": row[5] or {},
        "validation_report": row[6] or {},
        "error_message": row[7],
        "imported_at": row[8],
        "validated_at": row[9],
        "published_at": row[10],
        "published_by": row[11],
        "is_active": bool(row[12]),
        "parent_version_id": int(row[13]) if len(row) > 13 and row[13] is not None else None,
        "manifest_sha256": row[14] if len(row) > 14 else None,
    }
