from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from psycopg2.extras import Json, execute_values

from db.connection import get_connection
from db.pricing_kb_schema_contract import SQLiteSchemaContractError, schema_contract_diff
from db.pricing_kb_versions import apply_version_schema
from import_pricing_kb import (
    SQLITE_TABLES,
    import_source_table,
    postgres_table_digest,
    source_table_digest,
    sqlite_connect,
)


KNOWN_TABLES = tuple(SQLITE_TABLES)
DEPENDENCIES = {
    "TQDK_TQDZY": {"TLibs", "TQDK_TQDZM", "TDEK_TDEZM"},
    "TQDK_TQDZY_SPECIAL": {"TLibs", "TQDK_TQDZM", "TDEK_TDEZM"},
    "TDEK_TZMGC": {"TLibs", "TDEK_TDEZM"},
    "TDEK_TZNHS": {"TLibs", "TDEK_TDEZM"},
    "TDEK_TZHHS": {"TLibs", "TDEK_TDEZM"},
    "TQDK_TZJMC": {"TLibs"},
    "TDEK_TZJMC": {"TLibs"},
    "TQDK_TQDZM": {"TLibs"},
    "TQDK_TQDXMTZ": {"TLibs", "TQDK_TQDZM"},
    "TDEK_TDEZM": {"TLibs"},
}


def require_admin(request: Request):
    """兼容旧导入路由；管理员身份已统一由应用会话验证。"""
    from api.auth import require_admin as require_application_admin
    return require_application_admin(request)


def upload_root() -> Path:
    root = Path(os.getenv("PRICING_KB_UPLOAD_DIR", ".data/pricing-kb-uploads")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _quoted_table(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def inspect_sqlite(path: Path) -> dict[str, Any]:
    conn = sqlite_connect(path)
    try:
        cur = conn.cursor()
        quick_check = str(cur.execute("PRAGMA quick_check").fetchone()[0])
        tables = []
        for row in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall():
            name = str(row[0])
            columns = [
                {"name": str(c[1]), "type": str(c[2] or ""), "not_null": bool(c[3]), "pk": bool(c[5])}
                for c in cur.execute(f"PRAGMA table_info({_quoted_table(name)})").fetchall()
            ]
            count = int(cur.execute(f"SELECT COUNT(*) FROM {_quoted_table(name)}").fetchone()[0])
            signature = hashlib.sha256(
                json.dumps(columns, ensure_ascii=True, sort_keys=True).encode()
            ).hexdigest()
            tables.append({
                "name": name,
                "known": name in SQLITE_TABLES,
                "row_count": count,
                "column_count": len(columns),
                "columns": columns,
                "schema_signature": signature,
                "dependencies": sorted(DEPENDENCIES.get(name, set())),
            })
        signature = hashlib.sha256(
            json.dumps(tables, ensure_ascii=True, sort_keys=True).encode()
        ).hexdigest()
        schema_diff = schema_contract_diff(tables)
        return {
            "quick_check": quick_check,
            "schema_signature": signature,
            "tables": tables,
            "schema_diff": schema_diff,
            "contract_valid": not schema_diff,
            "out_of_scope_tables": sorted(
                table["name"] for table in tables if not table["known"]
            ),
        }
    finally:
        conn.close()


def expand_dependencies(selected: set[str], available: set[str]) -> set[str]:
    expanded = set(selected)
    changed = True
    while changed:
        changed = False
        for table in tuple(expanded):
            for dependency in DEPENDENCIES.get(table, set()):
                if dependency in available and dependency not in expanded:
                    expanded.add(dependency)
                    changed = True
    return expanded


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"$type": "blob", "base64": base64.b64encode(value).decode("ascii")}
    return value


def _job_cancelled(conn, job_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM pricing_kb_import_jobs WHERE id=%s", (job_id,))
        row = cur.fetchone()
    return bool(row and row[0] == "cancel_requested")


def _progress(conn, job_id: int, table: str, completed: int, rows: int, detail: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE pricing_kb_import_jobs
            SET current_table=%s, completed_tables=%s, processed_rows=%s,
                progress_json=%s, lease_expires_at=NOW()+INTERVAL '2 minutes', updated_at=NOW()
            WHERE id=%s
            """,
            (table, completed, rows, Json(detail), job_id),
        )
    conn.commit()


def _validate_effective_version(conn, version_id: int) -> dict[str, int]:
    def dv(table: str) -> int:
        with conn.cursor() as cur:
            cur.execute("SELECT pricing_kb_data_version(%s,%s)", (version_id, table))
            return int(cur.fetchone()[0])

    versions = {table: dv(table) for table in KNOWN_TABLES}
    checks = {
        "orphan_candidate_boq": (
            """SELECT COUNT(*) FROM tqdk_tqdzy c WHERE c.kb_version_id=%s AND NOT EXISTS
               (SELECT 1 FROM tqdk_tqdzm b WHERE b.kb_version_id=%s AND b.qdkid=c.qdkid AND b.id=c.qdzmid)""",
            (versions["TQDK_TQDZY"], versions["TQDK_TQDZM"]),
        ),
        "orphan_candidate_quota": (
            """SELECT COUNT(*) FROM tqdk_tqdzy c WHERE c.kb_version_id=%s AND NOT EXISTS
               (SELECT 1 FROM tdek_tdezm q WHERE q.kb_version_id=%s AND q.dekid=c.dekid AND q.id=c.dezmid)""",
            (versions["TQDK_TQDZY"], versions["TDEK_TDEZM"]),
        ),
        "orphan_special_candidate_boq": (
            """SELECT COUNT(*) FROM tqdk_tqdzy_special c WHERE c.kb_version_id=%s
               AND c.dekid IS NOT NULL AND c.dezmid IS NOT NULL AND NOT EXISTS
               (SELECT 1 FROM tqdk_tqdzm b WHERE b.kb_version_id=%s AND b.qdkid=c.qdkid AND b.id=c.qdzmid)""",
            (versions["TQDK_TQDZY_SPECIAL"], versions["TQDK_TQDZM"]),
        ),
        "orphan_special_candidate_quota": (
            """SELECT COUNT(*) FROM tqdk_tqdzy_special c WHERE c.kb_version_id=%s
               AND c.dekid IS NOT NULL AND c.dezmid IS NOT NULL AND NOT EXISTS
               (SELECT 1 FROM tdek_tdezm q WHERE q.kb_version_id=%s AND q.dekid=c.dekid AND q.id=c.dezmid)""",
            (versions["TQDK_TQDZY_SPECIAL"], versions["TDEK_TDEZM"]),
        ),
        "orphan_resources": (
            """SELECT COUNT(*) FROM tdek_tzmgc r WHERE r.kb_version_id=%s AND NOT EXISTS
               (SELECT 1 FROM tdek_tdezm q WHERE q.kb_version_id=%s AND q.dekid=r.dekid AND q.id=r.dezmid)""",
            (versions["TDEK_TZMGC"], versions["TDEK_TDEZM"]),
        ),
        "orphan_conversion_rules": (
            """SELECT COUNT(*) FROM tdek_tzhhs r WHERE r.kb_version_id=%s AND NOT EXISTS
               (SELECT 1 FROM tdek_tdezm q WHERE q.kb_version_id=%s AND q.dekid=r.dekid AND q.id=r.dezmid)""",
            (versions["TDEK_TZHHS"], versions["TDEK_TDEZM"]),
        ),
        "orphan_coefficient_rules": (
            """SELECT COUNT(*) FROM tdek_tznhs r WHERE r.kb_version_id=%s AND NOT EXISTS
               (SELECT 1 FROM tdek_tdezm q WHERE q.kb_version_id=%s AND q.dekid=r.dekid AND q.id=r.dezmid)""",
            (versions["TDEK_TZNHS"], versions["TDEK_TDEZM"]),
        ),
    }
    result = {}
    with conn.cursor() as cur:
        for name, (query, params) in checks.items():
            cur.execute(query, params)
            result[name] = int(cur.fetchone()[0])
    return result


def _process_job(conn, job: tuple[Any, ...]) -> int:
    job_id, upload_id, parent_id, config, change_note, stored_path, source_hash, inspection = job
    selected = set(config.get("selected_tables") or [])
    unknown = {k for k, v in (config.get("unknown_tables") or {}).items() if v == "raw"}
    schema_diff = inspection.get("schema_diff") or {}
    if schema_diff:
        raise SQLiteSchemaContractError(schema_diff)
    manifest_payload = {
        "parent_version_id": parent_id,
        "source_file_sha256": source_hash,
        "selected_tables": sorted(selected),
        "unknown_tables": sorted(unknown),
        "adapter_version": "pricing-kb-import-v2-schema-contract",
    }
    manifest = hashlib.sha256(json.dumps(manifest_payload, sort_keys=True).encode()).hexdigest()
    with conn.cursor() as cur:
        cur.execute("SELECT id,status FROM pricing_kb_versions WHERE manifest_sha256=%s", (manifest,))
        existing = cur.fetchone()
        if existing and existing[1] in {"validated", "active", "retired"}:
            cur.execute(
                "UPDATE pricing_kb_versions SET change_note=COALESCE(change_note,%s),updated_at=NOW() WHERE id=%s",
                (change_note, existing[0]),
            )
            cur.execute(
                """UPDATE pricing_kb_import_jobs SET version_id=%s,status='validated',current_table=NULL,
                   completed_tables=total_tables,processed_rows=0,finished_at=NOW(),updated_at=NOW() WHERE id=%s""",
                (existing[0], job_id),
            )
            conn.commit()
            return int(existing[0])
        if existing:
            version_id = int(existing[0])
            for pg_table, _, _ in SQLITE_TABLES.values():
                cur.execute(f"DELETE FROM {pg_table} WHERE kb_version_id=%s", (version_id,))
            cur.execute("DELETE FROM pricing_kb_raw_rows WHERE version_id=%s", (version_id,))
            cur.execute("DELETE FROM pricing_kb_raw_tables WHERE version_id=%s", (version_id,))
            cur.execute("DELETE FROM pricing_kb_version_tables WHERE version_id=%s", (version_id,))
            cur.execute(
                """UPDATE pricing_kb_versions
                   SET status='importing',error_message=NULL,change_note=%s,updated_at=NOW()
                   WHERE id=%s""",
                (change_note, version_id),
            )
        else:
            cur.execute(
                """INSERT INTO pricing_kb_versions(source_file,source_file_sha256,status,schema_signature,
                   table_counts,parent_version_id,manifest_sha256,change_note)
                   VALUES(%s,%s,'importing',%s,%s,%s,%s,%s) RETURNING id""",
                (stored_path, source_hash, inspection.get("schema_signature"), Json(inspection), parent_id, manifest, change_note),
            )
            version_id = int(cur.fetchone()[0])
        cur.execute("UPDATE pricing_kb_import_jobs SET version_id=%s WHERE id=%s", (version_id, job_id))
    conn.commit()

    table_meta = {t["name"]: t for t in inspection.get("tables", [])}
    sqlite_conn = sqlite_connect(Path(stored_path))
    completed = 0
    processed_rows = 0
    integrity: dict[str, Any] = {}
    try:
        sqlite_cur = sqlite_conn.cursor()
        for table in sorted(selected):
            if _job_cancelled(conn, job_id):
                raise InterruptedError("cancel requested")
            count = import_source_table(sqlite_cur, conn, version_id, source_hash, table)
            source_count, source_digest = source_table_digest(sqlite_cur, table)
            stored_count, stored_digest = postgres_table_digest(conn, version_id, table)
            table_integrity = {
                "source_rows": source_count,
                "stored_rows": stored_count,
                "source_digest": source_digest,
                "stored_digest": stored_digest,
                "ok": source_count == stored_count and source_digest == stored_digest,
            }
            integrity[table] = table_integrity
            if not table_integrity["ok"]:
                raise RuntimeError(f"typed import integrity validation failed for {table}: {table_integrity}")
            processed_rows += count
            completed += 1
            _progress(conn, job_id, table, completed, processed_rows, {"last_table_rows": count})

        for table in sorted(unknown):
            if _job_cancelled(conn, job_id):
                raise InterruptedError("cancel requested")
            meta = table_meta[table]
            sqlite_cur.execute(f"SELECT rowid AS __qmind_rowid__,* FROM {_quoted_table(table)}")
            names = [item[0] for item in sqlite_cur.description]
            total = 0
            while True:
                rows = sqlite_cur.fetchmany(2000)
                if not rows:
                    break
                values = []
                for row in rows:
                    payload = {name: _json_value(row[idx]) for idx, name in enumerate(names) if name != "__qmind_rowid__"}
                    values.append((version_id, table, int(row[0]), Json(payload)))
                with conn.cursor() as cur:
                    execute_values(cur, """INSERT INTO pricing_kb_raw_rows(version_id,source_table,source_rowid,raw_json)
                        VALUES %s ON CONFLICT(version_id,source_table,source_rowid) DO NOTHING""", values)
                total += len(rows)
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO pricing_kb_raw_tables(version_id,source_table,columns_json,schema_signature,row_count)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT(version_id,source_table) DO UPDATE
                    SET columns_json=EXCLUDED.columns_json,schema_signature=EXCLUDED.schema_signature,row_count=EXCLUDED.row_count""",
                    (version_id, table, Json(meta["columns"]), meta["schema_signature"], total))
            conn.commit()
            processed_rows += total
            completed += 1
            _progress(conn, job_id, table, completed, processed_rows, {"last_table_rows": total})

        # Refresh planner statistics for every typed knowledge table.  A release
        # may inherit physical rows from an older version, and those inherited
        # tables are still queried immediately after activation.
        with conn.cursor() as cur:
            for pg_table in sorted({SQLITE_TABLES[table][0] for table in KNOWN_TABLES}):
                cur.execute(f"ANALYZE {pg_table}")
        conn.commit()

        with conn.cursor() as cur:
            parent_mapping: dict[str, int] = {}
            if parent_id:
                cur.execute("SELECT source_table,data_version_id FROM pricing_kb_version_tables WHERE version_id=%s", (parent_id,))
                parent_mapping = {str(r[0]): int(r[1]) for r in cur.fetchall()}
            for table in KNOWN_TABLES:
                data_version = version_id if table in selected else parent_mapping.get(table, parent_id or version_id)
                meta = table_meta.get(table, {})
                cur.execute("""INSERT INTO pricing_kb_version_tables(version_id,source_table,data_version_id,upload_id,
                    source_file_sha256,schema_signature,storage_kind,is_inherited,row_count)
                    VALUES(%s,%s,%s,%s,%s,%s,'typed',%s,%s)""",
                    (version_id, table, data_version, upload_id, source_hash if table in selected else None,
                     meta.get("schema_signature"), table not in selected, meta.get("row_count", 0) if table in selected else 0))
            for table in unknown:
                meta = table_meta[table]
                cur.execute("""INSERT INTO pricing_kb_version_tables(version_id,source_table,data_version_id,upload_id,
                    source_file_sha256,schema_signature,storage_kind,is_inherited,row_count)
                    VALUES(%s,%s,%s,%s,%s,%s,'raw',FALSE,%s)""",
                    (version_id, table, version_id, upload_id, source_hash, meta["schema_signature"], meta["row_count"]))
        conn.commit()
        validation = _validate_effective_version(conn, version_id)
        if any(validation.values()):
            raise RuntimeError(f"effective version validation failed: {validation}")
        validation_report = {
            "relations": validation,
            "schema_contract": {"valid": True, "schema_diff": {}},
            "integrity": integrity,
        }
        with conn.cursor() as cur:
            cur.execute("""UPDATE pricing_kb_versions SET status='validated',validation_report=%s,
                validated_at=NOW(),updated_at=NOW() WHERE id=%s""", (Json(validation_report), version_id))
            cur.execute("""UPDATE pricing_kb_import_jobs SET status='validated',current_table=NULL,
                completed_tables=total_tables,finished_at=NOW(),updated_at=NOW() WHERE id=%s""", (job_id,))
        conn.commit()
        return version_id
    finally:
        sqlite_conn.close()


def run_next_job(worker_id: str | None = None) -> int | None:
    owner = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    conn = get_connection()
    job_id = None
    version_id = None
    lock_acquired = False
    conn.pin()
    try:
        apply_version_schema(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(hashtext('pricing_kb_import'))")
            lock_acquired = bool(cur.fetchone()[0])
            if not lock_acquired:
                conn.rollback()
                return None
            cur.execute("""
                SELECT j.id,j.upload_id,j.parent_version_id,j.config_json,j.change_note,
                       u.stored_path,u.file_sha256,u.inspection_json
                FROM pricing_kb_import_jobs j JOIN pricing_kb_uploads u ON u.id=j.upload_id
                WHERE j.status='queued' OR (j.status='running' AND j.lease_expires_at<NOW())
                ORDER BY j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 1
            """)
            job = cur.fetchone()
            if not job:
                conn.rollback()
                return None
            job_id = int(job[0])
            cur.execute("""UPDATE pricing_kb_import_jobs SET status='running',lease_owner=%s,
                lease_expires_at=NOW()+INTERVAL '2 minutes',attempts=attempts+1,
                started_at=COALESCE(started_at,NOW()),updated_at=NOW() WHERE id=%s""", (owner, job_id))
        conn.commit()
        version_id = _process_job(conn, job)
        return job_id
    except InterruptedError:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("UPDATE pricing_kb_import_jobs SET status='cancelled',finished_at=NOW(),updated_at=NOW() WHERE id=%s", (job_id,))
            cur.execute("""UPDATE pricing_kb_versions SET status='failed',error_message='cancelled'
                WHERE id=(SELECT version_id FROM pricing_kb_import_jobs WHERE id=%s)""", (job_id,))
        conn.commit()
        return job_id
    except Exception as exc:
        conn.rollback()
        if job_id:
            with conn.cursor() as cur:
                cur.execute("UPDATE pricing_kb_import_jobs SET status='failed',error_message=%s,finished_at=NOW(),updated_at=NOW() WHERE id=%s", (str(exc), job_id))
                cur.execute("UPDATE pricing_kb_versions SET status='failed',error_message=%s,updated_at=NOW() WHERE id=(SELECT version_id FROM pricing_kb_import_jobs WHERE id=%s)", (str(exc), job_id))
            conn.commit()
        raise
    finally:
        if lock_acquired and not conn.closed:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(hashtext('pricing_kb_import'))")
                conn.commit()
            except Exception:
                conn.rollback()
        conn.unpin()
        conn.close()
