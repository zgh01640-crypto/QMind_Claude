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
from db.pricing_kb_versions import apply_version_schema


SCHEMA_PATH = Path(__file__).parent / "db" / "schema_pricing_kb_original.sql"
DEFAULT_SOURCE = Path("mydoc") / "智能组价系统库.db"


SQLITE_TABLES = {
    "TLibs": ("tlibs", ["id", "mc"], "SELECT rowid, ID, MC FROM TLibs"),
    "TQDK_TZJMC": ("tqdk_tzjmc", ["qdkid", "id", "pid", "zjmc", "zjsm"], "SELECT rowid, QDKID, ID, PID, ZJMC, ZJSM FROM TQDK_TZJMC"),
    "TDEK_TZJMC": ("tdek_tzjmc", ["dekid", "id", "pid", "zjmc", "zjsm"], "SELECT rowid, DEKID, ID, PID, ZJMC, ZJSM FROM TDEK_TZJMC"),
    "TQDK_TQDZM": ("tqdk_tqdzm", ["qdkid", "id", "zmbh", "zmmc", "dw", "zjh"], "SELECT rowid, QDKID, ID, ZMBH, ZMMC, DW, ZJH FROM TQDK_TQDZM"),
    "TDEK_TDEZM": (
        "tdek_tdezm",
        ["dekid", "id", "zmbh", "zmmc", "dw", "gznr", "zjh", "dj", "rgf", "clf", "jxf", "zcf", "sbf", "glf", "lr", "aqwmsgf", "qtcsf", "gf", "sj"],
        "SELECT rowid, DEKID, ID, ZMBH, ZMMC, DW, GZNR, ZJH, DJ, RGF, CLF, JXF, ZCF, SBF, GLF, LR, AQWMSGF, QTCSF, GF, SJ FROM TDEK_TDEZM",
    ),
    "TDEK_TZMGC": ("tdek_tzmgc", ["dekid", "dezmid", "zmbh", "zmmc", "dw", "gcl", "lx"], "SELECT rowid, DEKID, DEZMID, ZMBH, ZMMC, DW, GCL, LX FROM TDEK_TZMGC"),
    "TDEK_TZNHS": ("tdek_tznhs", ["dekid", "dezmid", "tsxx", "hssm", "groupno"], "SELECT rowid, DEKID, DEZMID, TSXX, HSSM, GROUPNO FROM TDEK_TZNHS"),
    "TDEK_TZHHS": (
        "tdek_tzhhs",
        ["dekid", "dezmid", "tsxx", "zmbh", "jcz", "zjdw"],
        "SELECT rowid, DEKID, DEZMID, TSXX, ZMBH, JCZ, ZJDW FROM TDEK_TZHHS",
    ),
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

QUOTA_COST_COLUMNS = [
    "dj", "rgf", "clf", "jxf", "zcf", "sbf",
    "glf", "lr", "aqwmsgf", "qtcsf", "gf", "sj",
]


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


def sqlite_schema_signature(source: Path) -> str:
    conn = sqlite_connect(source)
    try:
        schema: dict[str, list[tuple[str, str, int]]] = {}
        cur = conn.cursor()
        for table in SQLITE_TABLES:
            schema[table] = [
                (str(row[1]), str(row[2]), int(row[3]))
                for row in cur.execute(f"PRAGMA table_info({table})")
            ]
        payload = json.dumps(schema, ensure_ascii=True, sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
    finally:
        conn.close()


def validate_sqlite_relations(source: Path) -> dict[str, int]:
    conn = sqlite_connect(source)
    try:
        cur = conn.cursor()
        def keys(query: str) -> tuple[set[tuple[Any, ...]], int]:
            seen: set[tuple[Any, ...]] = set()
            duplicates = 0
            for row in cur.execute(query):
                key = tuple(row)
                if key in seen:
                    duplicates += 1
                else:
                    seen.add(key)
            return seen, duplicates

        _, duplicate_libraries = keys("SELECT ID FROM TLibs")
        _, duplicate_boq_chapters = keys("SELECT QDKID,ID FROM TQDK_TZJMC")
        _, duplicate_quota_chapters = keys("SELECT DEKID,ID FROM TDEK_TZJMC")
        boq_items, duplicate_boq_items = keys("SELECT QDKID,ID FROM TQDK_TQDZM")
        quota_items, duplicate_quota_items = keys("SELECT DEKID,ID FROM TDEK_TDEZM")

        orphan_candidate_boq = 0
        orphan_candidate_quota = 0
        for row in cur.execute("SELECT QDKID,QDZMID,DEKID,DEZMID FROM TQDK_TQDZY"):
            orphan_candidate_boq += (row[0], row[1]) not in boq_items
            orphan_candidate_quota += (row[2], row[3]) not in quota_items

        def orphan_count(query: str) -> int:
            return sum(tuple(row) not in quota_items for row in cur.execute(query))

        return {
            "duplicate_libraries": duplicate_libraries,
            "duplicate_boq_chapters": duplicate_boq_chapters,
            "duplicate_quota_chapters": duplicate_quota_chapters,
            "duplicate_boq_items": duplicate_boq_items,
            "duplicate_quota_items": duplicate_quota_items,
            "orphan_candidate_boq": orphan_candidate_boq,
            "orphan_candidate_quota": orphan_candidate_quota,
            "orphan_resources": orphan_count("SELECT DEKID,DEZMID FROM TDEK_TZMGC"),
            "orphan_conversion_rules": orphan_count("SELECT DEKID,DEZMID FROM TDEK_TZHHS"),
            "orphan_coefficient_rules": orphan_count("SELECT DEKID,DEZMID FROM TDEK_TZNHS"),
        }
    finally:
        conn.close()


def apply_schema(pg) -> None:
    with pg.cursor() as cur:
        cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    pg.commit()
    apply_version_schema(pg)


def begin_version(pg, source: Path, source_hash: str, inspection: dict[str, Any]) -> tuple[int, bool]:
    """Return the immutable version id and whether it needs importing."""
    with pg.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('pricing_kb_import'))")
        cur.execute(
            "SELECT id, status FROM pricing_kb_versions WHERE source_file_sha256=%s FOR UPDATE",
            (source_hash,),
        )
        row = cur.fetchone()
        if row and row[1] in {"validated", "active", "retired"}:
            return int(row[0]), False
        if row:
            version_id = int(row[0])
            cur.execute(
                """
                UPDATE pricing_kb_versions
                SET source_file=%s, status='importing', schema_signature=%s,
                    table_counts=%s::jsonb, validation_report='{}'::jsonb,
                    error_message=NULL, updated_at=NOW()
                WHERE id=%s
                """,
                (
                    str(source),
                    sqlite_schema_signature(source),
                    json.dumps(inspection, ensure_ascii=False),
                    version_id,
                ),
            )
            return version_id, True
        cur.execute(
            """
            INSERT INTO pricing_kb_versions(
                source_file, source_file_sha256, status, schema_signature, table_counts
            )
            VALUES (%s, %s, 'importing', %s, %s::jsonb)
            RETURNING id
            """,
            (
                str(source),
                source_hash,
                sqlite_schema_signature(source),
                json.dumps(inspection, ensure_ascii=False),
            ),
        )
        return int(cur.fetchone()[0]), True


def clear_version_rows(pg, version_id: int) -> None:
    with pg.cursor() as cur:
        for table in [
            "tqdk_tqdzy", "tdek_tzhhs", "tdek_tznhs", "tdek_tzmgc",
            "tdek_tdezm", "tqdk_tqdzm", "tdek_tzjmc", "tqdk_tzjmc", "tlibs",
        ]:
            cur.execute(f"DELETE FROM {table} WHERE kb_version_id=%s", (version_id,))


def insert_run(pg, source: Path, source_hash: str, version_id: int) -> int:
    with pg.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pricing_kb_import_runs (source_file, source_file_sha256, kb_version_id, status)
            VALUES (%s, %s, %s, 'running')
            RETURNING id
            """,
            (str(source), source_hash, version_id),
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
    raise RuntimeError("Imported knowledge-base versions are immutable and cannot be cleared")


def clear_import_issues(pg, source_hash: str) -> None:
    with pg.cursor() as cur:
        cur.execute("DELETE FROM pricing_kb_import_issues WHERE source_file_sha256=%s", (source_hash,))


def remove_combo_quota_candidates(pg, version_id: int) -> int:
    """Remove candidate relations that point to combo-only quota items."""
    with pg.cursor() as cur:
        cur.execute(
            """
            DELETE FROM tqdk_tqdzy cand
            USING tdek_tdezm q
            WHERE q.dekid = cand.dekid
              AND q.id = cand.dezmid
              AND q.kb_version_id = cand.kb_version_id
              AND cand.kb_version_id = %s
              AND EXISTS (
                  SELECT 1
                  FROM tdek_tzhhs h
                  WHERE h.dekid = q.dekid
                    AND h.zmbh = q.zmbh
                    AND h.kb_version_id = q.kb_version_id
              )
            """,
            (version_id,),
        )
        return int(cur.rowcount)


def import_source_table(
    sqlite_cur: sqlite3.Cursor,
    pg,
    version_id: int,
    source_hash: str,
    source_table: str,
) -> int:
    pg_table, pg_columns, select_sql = SQLITE_TABLES[source_table]
    all_columns = pg_columns + ["kb_version_id", "source_file_sha256", "source_rowid"]
    insert_sql = f"""
        INSERT INTO {pg_table} ({", ".join(all_columns)})
        VALUES %s
        ON CONFLICT (source_file_sha256, source_rowid) DO NOTHING
    """

    total = 0
    source_columns = {
        str(row[1]).upper()
        for row in sqlite_cur.execute(f"PRAGMA table_info({source_table})")
    }
    select_columns = [
        col.upper() if col.upper() in source_columns else f"NULL AS {col.upper()}"
        for col in pg_columns
    ]
    sqlite_cur.execute(f"SELECT rowid, {', '.join(select_columns)} FROM {source_table}")
    while True:
        rows = sqlite_cur.fetchmany(10000)
        if not rows:
            break
        values = []
        for row in rows:
            values.append(
                tuple(row[col.upper()] for col in pg_columns)
                + (version_id, source_hash, row["rowid"])
            )
        with pg.cursor() as cur:
            execute_values(cur, insert_sql, values, page_size=10000)
        total += len(rows)
    return total


def load_replacement_staging(
    sqlite_cur: sqlite3.Cursor,
    pg,
    source_hash: str,
    source_table: str,
    staging_table: str,
) -> int:
    _, pg_columns, _ = SQLITE_TABLES[source_table]
    all_columns = pg_columns + ["source_file_sha256", "source_rowid"]
    source_columns = {
        str(row[1]).upper()
        for row in sqlite_cur.execute(f"PRAGMA table_info({source_table})")
    }
    missing = [col for col in pg_columns if col.upper() not in source_columns]
    if missing:
        raise RuntimeError(f"{source_table} is missing required columns: {', '.join(missing)}")
    sqlite_cur.execute(
        f"SELECT rowid, {', '.join(col.upper() for col in pg_columns)} FROM {source_table}"
    )
    insert_sql = f"""
        INSERT INTO {staging_table} ({", ".join(all_columns)})
        VALUES %s
    """
    total = 0
    while True:
        rows = sqlite_cur.fetchmany(10000)
        if not rows:
            break
        values = [
            tuple(row[col.upper()] for col in pg_columns) + (source_hash, row["rowid"])
            for row in rows
        ]
        with pg.cursor() as cur:
            execute_values(cur, insert_sql, values, page_size=10000)
        total += len(rows)
    return total


def validate_replacement_staging(pg, expected_quota: int, expected_prompts: int) -> dict[str, int]:
    with pg.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM staging_tdek_tdezm")
        quota_count = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM staging_tdek_tzhhs")
        prompt_count = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT dekid, id
                FROM staging_tdek_tdezm
                GROUP BY dekid, id
                HAVING COUNT(*) > 1
            ) duplicates
            """
        )
        duplicate_quota_keys = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT COUNT(*)
            FROM staging_tdek_tzhhs h
            LEFT JOIN staging_tdek_tdezm q
              ON q.dekid=h.dekid AND q.id=h.dezmid
            WHERE q.id IS NULL
            """
        )
        missing_prompt_items = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT COUNT(*)
            FROM staging_tdek_tzhhs h
            WHERE NOT EXISTS (
                SELECT 1
                FROM staging_tdek_tdezm q
                WHERE q.dekid=h.dekid AND q.zmbh=h.zmbh
            )
            """
        )
        missing_adjustment_codes = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT COUNT(*)
            FROM staging_tdek_tdezm
            WHERE dj IS NULL OR rgf IS NULL OR clf IS NULL OR jxf IS NULL
               OR zcf IS NULL OR sbf IS NULL OR glf IS NULL OR lr IS NULL
               OR aqwmsgf IS NULL OR qtcsf IS NULL OR gf IS NULL OR sj IS NULL
            """
        )
        null_cost_rows = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT COUNT(*)
            FROM staging_tdek_tdezm
            WHERE ABS(
                dj - (rgf + clf + jxf + zcf + sbf + glf + lr
                      + aqwmsgf + qtcsf + gf + sj)
            ) > 0.02
            """
        )
        cost_mismatch_rows = int(cur.fetchone()[0])

    validation = {
        "quota_count": quota_count,
        "prompt_count": prompt_count,
        "duplicate_quota_keys": duplicate_quota_keys,
        "missing_prompt_items": missing_prompt_items,
        "missing_adjustment_codes": missing_adjustment_codes,
        "null_cost_rows": null_cost_rows,
        "cost_mismatch_rows": cost_mismatch_rows,
    }
    if quota_count != expected_quota or prompt_count != expected_prompts:
        raise RuntimeError(f"replacement count mismatch: {validation}")
    if any(validation[key] for key in validation if key not in {"quota_count", "prompt_count"}):
        raise RuntimeError(f"replacement validation failed: {validation}")
    return validation


def replace_quota_tables(source: Path, should_link: bool) -> dict[str, Any]:
    raise RuntimeError(
        "--replace-quota-tables is disabled: import a new immutable version and publish it instead"
    )

    # Kept temporarily below for migration history; this path is intentionally unreachable.
    source = resolve_source(source).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    source_hash = sha256_file(source)
    inspection = inspect_sqlite(source)
    if inspection["quick_check"] != "ok":
        raise RuntimeError(f"SQLite quick_check failed: {inspection['quick_check']}")
    relation_validation = validate_sqlite_relations(source)

    load_dotenv(".env")
    sqlite_conn = sqlite_connect(source)
    pg = get_connection()
    run_id: int | None = None
    try:
        apply_schema(pg)
        run_id = insert_run(pg, source, source_hash)
        pg.commit()

        with pg.cursor() as cur:
            cur.execute("CREATE TEMP TABLE staging_tdek_tdezm (LIKE tdek_tdezm INCLUDING DEFAULTS) ON COMMIT DROP")
            cur.execute("CREATE TEMP TABLE staging_tdek_tzhhs (LIKE tdek_tzhhs INCLUDING DEFAULTS) ON COMMIT DROP")

        sqlite_cur = sqlite_conn.cursor()
        quota_count = load_replacement_staging(
            sqlite_cur, pg, source_hash, "TDEK_TDEZM", "staging_tdek_tdezm"
        )
        prompt_count = load_replacement_staging(
            sqlite_cur, pg, source_hash, "TDEK_TZHHS", "staging_tdek_tzhhs"
        )
        validation = validate_replacement_staging(
            pg,
            int(inspection["quota_items"]),
            int(inspection["input_prompts"]),
        )

        quota_columns = [
            "zmbh", "zmmc", "dw", "gznr", "zjh", *QUOTA_COST_COLUMNS,
            "source_file_sha256", "source_rowid",
        ]
        with pg.cursor() as cur:
            assignments = ", ".join(f"{col}=s.{col}" for col in quota_columns)
            cur.execute(
                f"""
                UPDATE tdek_tdezm t
                SET {assignments}, updated_at=NOW()
                FROM staging_tdek_tdezm s
                WHERE t.dekid=s.dekid AND t.id=s.id
                """
            )
            updated_quota = cur.rowcount
            cur.execute(
                """
                INSERT INTO tdek_tdezm
                    (dekid, id, zmbh, zmmc, dw, gznr, zjh,
                     dj, rgf, clf, jxf, zcf, sbf, glf, lr, aqwmsgf, qtcsf, gf, sj,
                     source_file_sha256, source_rowid)
                SELECT s.dekid, s.id, s.zmbh, s.zmmc, s.dw, s.gznr, s.zjh,
                       s.dj, s.rgf, s.clf, s.jxf, s.zcf, s.sbf, s.glf, s.lr,
                       s.aqwmsgf, s.qtcsf, s.gf, s.sj,
                       s.source_file_sha256, s.source_rowid
                FROM staging_tdek_tdezm s
                WHERE NOT EXISTS (
                    SELECT 1 FROM tdek_tdezm t
                    WHERE t.dekid=s.dekid AND t.id=s.id
                )
                """
            )
            inserted_quota = cur.rowcount
            cur.execute(
                """
                DELETE FROM tdek_tdezm t
                WHERE NOT EXISTS (
                    SELECT 1 FROM staging_tdek_tdezm s
                    WHERE s.dekid=t.dekid AND s.id=t.id
                )
                """
            )
            deleted_quota = cur.rowcount

            cur.execute("DELETE FROM tdek_tzhhs")
            deleted_prompts = cur.rowcount
            cur.execute(
                """
                INSERT INTO tdek_tzhhs
                    (dekid, dezmid, tsxx, zmbh, jcz, zjdw,
                     source_file_sha256, source_rowid)
                SELECT dekid, dezmid, tsxx, zmbh, jcz, zjdw,
                       source_file_sha256, source_rowid
                FROM staging_tdek_tzhhs
                """
            )
            inserted_prompts = cur.rowcount

        removed_combo_candidates = remove_combo_quota_candidates(pg)
        link_counts = link_targets(pg, source_hash) if should_link else {
            "matched": 0, "review": 0, "unmatched": 0
        }
        stats = {
            "mode": "replace_quota_tables",
            "source_file_sha256": source_hash,
            **inspection,
            "validation": validation,
            "tdek_tdezm": {
                "updated": updated_quota,
                "inserted": inserted_quota,
                "deleted": deleted_quota,
            },
            "tdek_tzhhs": {
                "deleted": deleted_prompts,
                "inserted": inserted_prompts,
            },
            "removed_combo_candidates": removed_combo_candidates,
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
    # The imported pricing knowledge base now stands alone. Do not link it to
    # bs2024_subitems, because that authoritative quota library is no longer
    # part of smart pricing.
    return {"matched": 0, "review": 0, "unmatched": 0}


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
    relation_validation = validate_sqlite_relations(source)
    if report_only:
        return {
            "source": str(source),
            "source_file_sha256": source_hash,
            **inspection,
            "relation_validation": relation_validation,
        }

    load_dotenv(".env")
    sqlite_conn = sqlite_connect(source)
    pg = get_connection()
    run_id: int | None = None
    version_id: int | None = None
    try:
        apply_schema(pg)
        with pg.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtext('pricing_kb_import'))")
        version_id, needs_import = begin_version(
            pg, source, source_hash, {**inspection, "relations": relation_validation}
        )
        if not needs_import:
            pg.rollback()
            return {
                "version_id": version_id,
                "source": str(source),
                "source_file_sha256": source_hash,
                "status": "already_imported",
                **inspection,
            }
        clear_version_rows(pg, version_id)
        clear_import_issues(pg, source_hash)
        run_id = insert_run(pg, source, source_hash, version_id)
        pg.commit()
        if any(relation_validation.values()):
            raise RuntimeError(
                f"knowledge-base relation validation failed: {relation_validation}"
            )

        sqlite_cur = sqlite_conn.cursor()
        imported: dict[str, int] = {}
        for source_table in SQLITE_TABLES:
            pg_table = SQLITE_TABLES[source_table][0]
            imported[pg_table] = import_source_table(
                sqlite_cur, pg, version_id, source_hash, source_table
            )

        removed_combo_candidates = remove_combo_quota_candidates(pg, version_id)
        issue_counts = record_import_issues(pg, sqlite_cur, source_hash, run_id)
        with pg.cursor() as cur:
            cur.execute(
                "UPDATE pricing_kb_import_issues SET kb_version_id=%s WHERE run_id=%s",
                (version_id, run_id),
            )
        link_counts = link_targets(pg, source_hash) if should_link else {"matched": 0, "review": 0, "unmatched": 0}

        stats = {
            "version_id": version_id,
            "source_file_sha256": source_hash,
            **inspection,
            "relation_validation": relation_validation,
            "imported_tables": imported,
            "removed_combo_candidates": removed_combo_candidates,
            **issue_counts,
            "target_links": link_counts,
        }
        finalize_run(pg, run_id, "done", stats)
        with pg.cursor() as cur:
            cur.execute(
                """
                UPDATE pricing_kb_versions
                SET status='validated', validation_report=%s::jsonb,
                    validated_at=NOW(), error_message=NULL, updated_at=NOW()
                WHERE id=%s
                """,
                (json.dumps(stats, ensure_ascii=False), version_id),
            )
            for table in [value[0] for value in SQLITE_TABLES.values()]:
                cur.execute(f"ANALYZE {table}")
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
        if version_id is not None:
            try:
                with pg.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE pricing_kb_versions
                        SET status='failed', error_message=%s, updated_at=NOW()
                        WHERE id=%s AND status='importing'
                        """,
                        (str(exc), version_id),
                    )
                pg.commit()
            except Exception:
                pg.rollback()
        raise
    finally:
        try:
            with pg.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtext('pricing_kb_import'))")
            pg.commit()
        except Exception:
            pg.rollback()
        sqlite_conn.close()
        pg.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--link-targets", action="store_true", default=True)
    parser.add_argument("--no-link-targets", action="store_false", dest="link_targets")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument(
        "--replace-quota-tables",
        action="store_true",
        help="Replace only TDEK_TDEZM and TDEK_TZHHS from the source database",
    )
    args = parser.parse_args()

    if args.replace_quota_tables:
        if args.report_only:
            source = resolve_source(args.source).resolve()
            result = {
                "source": str(source),
                "source_file_sha256": sha256_file(source),
                **inspect_sqlite(source),
            }
        else:
            result = replace_quota_tables(args.source, args.link_targets)
    else:
        result = import_pricing_kb(
            source=args.source,
            force=args.force,
            report_only=args.report_only,
            should_link=args.link_targets,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
