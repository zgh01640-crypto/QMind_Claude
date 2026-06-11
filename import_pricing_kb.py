"""Import the smart-pricing SQLite knowledge base as lower-case source tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from psycopg2.extras import execute_values

from db.connection import get_connection


SCHEMA_PATH = Path(__file__).parent / "db" / "schema_pricing_kb_original.sql"
DEFAULT_SOURCE = Path("mydoc") / "智能组价系统库.db"


SQLITE_TABLES = {
    "TLibs": ("tlibs", ["id", "mc"], "SELECT rowid, ID, MC FROM TLibs"),
    "TQDK_TZJMC": ("tqdk_tzjmc", ["qdkid", "id", "pid", "zjmc", "zjsm"], "SELECT rowid, QDKID, ID, PID, ZJMC, ZJSM FROM TQDK_TZJMC"),
    "TDEK_TZJMC": ("tdek_tzjmc", ["dekid", "id", "pid", "zjmc", "zjsm"], "SELECT rowid, DEKID, ID, PID, ZJMC, ZJSM FROM TDEK_TZJMC"),
    "TQDK_TQDZM": ("tqdk_tqdzm", ["qdkid", "id", "zmbh", "zmmc", "dw", "zjh"], "SELECT rowid, QDKID, ID, ZMBH, ZMMC, DW, ZJH FROM TQDK_TQDZM"),
    "TDEK_TDEZM": ("tdek_tdezm", ["dekid", "id", "zmbh", "zmmc", "dw", "gznr", "zjh"], "SELECT rowid, DEKID, ID, ZMBH, ZMMC, DW, GZNR, ZJH FROM TDEK_TDEZM"),
    "TDEK_TZMGC": ("tdek_tzmgc", ["dekid", "dezmid", "zmbh", "zmmc", "dw", "gcl", "lx"], "SELECT rowid, DEKID, DEZMID, ZMBH, ZMMC, DW, GCL, LX FROM TDEK_TZMGC"),
    "TDEK_TZNHS": ("tdek_tznhs", ["dekid", "dezmid", "tsxx", "hssm", "groupno"], "SELECT rowid, DEKID, DEZMID, TSXX, HSSM, GROUPNO FROM TDEK_TZNHS"),
    "TDEK_TZHHS": ("tdek_tzhhs", ["dekid", "dezmid", "tsxx"], "SELECT rowid, DEKID, DEZMID, TSXX FROM TDEK_TZHHS"),
    "TQDK_TQDZY": ("tqdk_tqdzy", ["qdkid", "qdzmid", "dekid", "dezmid", "zmbh", "zmmc", "dw"], "SELECT rowid, QDKID, QDZMID, DEKID, DEZMID, ZMBH, ZMMC, DW FROM TQDK_TQDZY"),
}


RESOURCE_TYPES = {
    1: "人工",
    2: "材料",
    3: "机械",
    4: "特殊材料",
    6: "设备",
    22: "使用费",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sqlite_connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def sqlite_count(cur: sqlite3.Cursor, table: str) -> int:
    return int(cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def inspect_sqlite(source: Path) -> dict[str, Any]:
    conn = sqlite_connect(source)
    try:
        cur = conn.cursor()
        quick_check = cur.execute("PRAGMA quick_check").fetchone()[0]
        return {
            "quick_check": quick_check,
            "libraries": sqlite_count(cur, "TLibs"),
            "boq_chapters": sqlite_count(cur, "TQDK_TZJMC"),
            "boq_items": sqlite_count(cur, "TQDK_TQDZM"),
            "quota_chapters": sqlite_count(cur, "TDEK_TZJMC"),
            "quota_items": sqlite_count(cur, "TDEK_TDEZM"),
            "quota_resources": sqlite_count(cur, "TDEK_TZMGC"),
            "conversion_rules": sqlite_count(cur, "TDEK_TZNHS"),
            "input_prompts": sqlite_count(cur, "TDEK_TZHHS"),
            "candidates": sqlite_count(cur, "TQDK_TQDZY"),
        }
    finally:
        conn.close()


def apply_schema(pg) -> None:
    with pg.cursor() as cur:
        cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def insert_run(pg, source: Path, source_hash: str) -> int:
    with pg.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pricing_kb_import_runs (source_file, source_file_sha256, status)
            VALUES (%s, %s, 'running')
            RETURNING id
            """,
            (str(source), source_hash),
        )
        return int(cur.fetchone()[0])


def finalize_run(pg, run_id: int, status: str, stats: dict[str, Any], error: str | None = None) -> None:
    with pg.cursor() as cur:
        cur.execute(
            """
            UPDATE pricing_kb_import_runs
            SET status=%s, stats_json=%s::jsonb, error_message=%s, finished_at=NOW()
            WHERE id=%s
            """,
            (status, json.dumps(stats, ensure_ascii=False), error, run_id),
        )


def clear_source(pg, source_hash: str) -> None:
    with pg.cursor() as cur:
        cur.execute("DELETE FROM pricing_kb_import_issues WHERE source_file_sha256=%s", (source_hash,))
        cur.execute("DELETE FROM pricing_kb_original_target_links WHERE source_file_sha256=%s", (source_hash,))
        for table in [
            "tqdk_tqdzy",
            "tdek_tzhhs",
            "tdek_tznhs",
            "tdek_tzmgc",
            "tdek_tdezm",
            "tqdk_tqdzm",
            "tdek_tzjmc",
            "tqdk_tzjmc",
            "tlibs",
        ]:
            cur.execute(f"DELETE FROM {table} WHERE source_file_sha256=%s", (source_hash,))


def clear_import_issues(pg, source_hash: str) -> None:
    with pg.cursor() as cur:
        cur.execute("DELETE FROM pricing_kb_import_issues WHERE source_file_sha256=%s", (source_hash,))


def import_source_table(sqlite_cur: sqlite3.Cursor, pg, source_hash: str, source_table: str) -> int:
    pg_table, pg_columns, select_sql = SQLITE_TABLES[source_table]
    all_columns = pg_columns + ["source_file_sha256", "source_rowid"]
    update_columns = [c for c in all_columns if c not in {"source_file_sha256", "source_rowid"}]
    update_sql = ", ".join([f"{c}=EXCLUDED.{c}" for c in update_columns] + ["updated_at=NOW()"])
    insert_sql = f"""
        INSERT INTO {pg_table} ({", ".join(all_columns)})
        VALUES %s
        ON CONFLICT (source_file_sha256, source_rowid) DO UPDATE SET {update_sql}
    """

    total = 0
    sqlite_cur.execute(select_sql)
    while True:
        rows = sqlite_cur.fetchmany(10000)
        if not rows:
            break
        values = []
        for row in rows:
            values.append(tuple(row[col.upper()] for col in pg_columns) + (source_hash, row["rowid"]))
        with pg.cursor() as cur:
            execute_values(cur, insert_sql, values, page_size=10000)
        total += len(rows)
    return total


def record_import_issues(pg, sqlite_cur: sqlite3.Cursor, source_hash: str, run_id: int) -> dict[str, int]:
    issues: list[tuple[Any, ...]] = []

    missing_boq = list(sqlite_cur.execute(
        """
        SELECT rowid, QDKID, ID, ZJH, ZMBH, ZMMC
        FROM TQDK_TQDZM i
        WHERE NOT EXISTS (
          SELECT 1 FROM TQDK_TZJMC c
          WHERE c.QDKID=i.QDKID AND c.ID=i.ZJH
        )
        """
    ))
    for row in missing_boq:
        issues.append((
            run_id, source_hash, "warning", "boq_item_missing_chapter",
            "TQDK_TQDZM record has no matching TQDK_TZJMC chapter",
            "TQDK_TQDZM", row["QDKID"], row["rowid"],
            json.dumps(dict(row), ensure_ascii=False),
        ))

    missing_quota = list(sqlite_cur.execute(
        """
        SELECT rowid, DEKID, ID, ZJH, ZMBH, ZMMC
        FROM TDEK_TDEZM i
        WHERE NOT EXISTS (
          SELECT 1 FROM TDEK_TZJMC c
          WHERE c.DEKID=i.DEKID AND c.ID=i.ZJH
        )
        """
    ))
    for row in missing_quota:
        issues.append((
            run_id, source_hash, "warning", "quota_item_missing_chapter",
            "TDEK_TDEZM record has no matching TDEK_TZJMC chapter",
            "TDEK_TDEZM", row["DEKID"], row["rowid"],
            json.dumps(dict(row), ensure_ascii=False),
        ))

    if issues:
        with pg.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO pricing_kb_import_issues
                    (run_id, source_file_sha256, severity, issue_type, message,
                     source_table, source_library_id, source_record_id, context_json)
                VALUES %s
                """,
                issues,
                page_size=1000,
            )

    return {
        "missing_boq_chapters": len(missing_boq),
        "missing_quota_chapters": len(missing_quota),
    }


def normalize_name(value: str | None) -> str:
    return "".join((value or "").split())


def normalize_unit(value: str | None) -> str:
    return (
        (value or "")
        .replace("m²", "m2")
        .replace("m³", "m3")
        .replace("㎡", "m2")
        .replace("m2", "m2")
        .replace("m3", "m3")
        .replace(" ", "")
        .lower()
    )


def link_targets(pg, source_hash: str) -> dict[str, int]:
    with pg.cursor() as cur:
        cur.execute("SELECT to_regclass('public.bs2024_subitems')")
        if cur.fetchone()[0] is None:
            return {"matched": 0, "review": 0, "unmatched": 0}
        cur.execute(
            """
            WITH target AS (
                SELECT DISTINCT ON (subitem_code)
                       id, subitem_code, COALESCE(subitem_name, '') AS subitem_name,
                       COALESCE(variant_desc, '') AS variant_desc, unit
                FROM bs2024_subitems
                ORDER BY subitem_code, document_id DESC, id DESC
            )
            SELECT k.dekid, k.id, k.zmbh, k.zmmc, k.dw,
                   b.id, b.subitem_name, b.variant_desc, b.unit
            FROM tdek_tdezm k
            LEFT JOIN target b ON b.subitem_code = k.zmbh
            WHERE k.dekid = 1020109
              AND k.source_file_sha256 = %s
            """,
            (source_hash,),
        )
        values = []
        counts = {"matched": 0, "review": 0, "unmatched": 0}
        for dekid, dezmid, code, name, unit, bid, sub_name, variant, b_unit in cur.fetchall():
            if bid is None:
                status = "unmatched"
                message = "No bs2024_subitems record with the same subitem code"
                score = 0
            else:
                target_name = " ".join(part for part in [sub_name, variant] if part).strip()
                name_ok = normalize_name(name) == normalize_name(target_name)
                unit_ok = normalize_unit(unit) == normalize_unit(b_unit)
                status = "matched" if name_ok and unit_ok else "review"
                message = "" if status == "matched" else f"name_ok={name_ok}; unit_ok={unit_ok}"
                score = 1 if status == "matched" else 0.5
            counts[status] += 1
            values.append((
                dekid, dezmid, "bs2024_subitems", bid, status, "code_exact",
                score, message, source_hash,
                json.dumps({"code": code, "kb_name": name, "kb_unit": unit}, ensure_ascii=False),
            ))
        if values:
            execute_values(
                cur,
                """
                INSERT INTO pricing_kb_original_target_links
                    (dekid, dezmid, target_table, target_item_id, link_status, link_method,
                     similarity_score, review_message, source_file_sha256, raw_json)
                VALUES %s
                ON CONFLICT (dekid, dezmid, target_table) DO UPDATE SET
                    target_item_id=EXCLUDED.target_item_id,
                    link_status=EXCLUDED.link_status,
                    link_method=EXCLUDED.link_method,
                    similarity_score=EXCLUDED.similarity_score,
                    review_message=EXCLUDED.review_message,
                    source_file_sha256=EXCLUDED.source_file_sha256,
                    raw_json=EXCLUDED.raw_json,
                    updated_at=NOW()
                """,
                values,
                page_size=5000,
            )
        return counts


def resolve_source(path: Path) -> Path:
    if path.exists():
        return path
    dbs = list(Path("mydoc").glob("*.db"))
    if len(dbs) == 1:
        return dbs[0]
    return path


def import_pricing_kb(source: Path, force: bool, report_only: bool, should_link: bool) -> dict[str, Any]:
    source = resolve_source(source).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    source_hash = sha256_file(source)
    inspection = inspect_sqlite(source)
    if inspection["quick_check"] != "ok":
        raise RuntimeError(f"SQLite quick_check failed: {inspection['quick_check']}")
    if report_only:
        return {"source": str(source), "source_file_sha256": source_hash, **inspection}

    load_dotenv(".env")
    sqlite_conn = sqlite_connect(source)
    pg = get_connection()
    run_id: int | None = None
    try:
        apply_schema(pg)
        if force:
            clear_source(pg, source_hash)
        else:
            clear_import_issues(pg, source_hash)
        run_id = insert_run(pg, source, source_hash)
        pg.commit()

        sqlite_cur = sqlite_conn.cursor()
        imported: dict[str, int] = {}
        for source_table in SQLITE_TABLES:
            pg_table = SQLITE_TABLES[source_table][0]
            imported[pg_table] = import_source_table(sqlite_cur, pg, source_hash, source_table)

        issue_counts = record_import_issues(pg, sqlite_cur, source_hash, run_id)
        link_counts = link_targets(pg, source_hash) if should_link else {"matched": 0, "review": 0, "unmatched": 0}

        stats = {
            "source_file_sha256": source_hash,
            **inspection,
            "imported_tables": imported,
            **issue_counts,
            "target_links": link_counts,
        }
        finalize_run(pg, run_id, "done", stats)
        pg.commit()
        return stats
    except Exception as exc:
        pg.rollback()
        if run_id is not None:
            try:
                finalize_run(pg, run_id, "error", {}, str(exc))
                pg.commit()
            except Exception:
                pg.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--link-targets", action="store_true", default=True)
    parser.add_argument("--no-link-targets", action="store_false", dest="link_targets")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    result = import_pricing_kb(
        source=args.source,
        force=args.force,
        report_only=args.report_only,
        should_link=args.link_targets,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
