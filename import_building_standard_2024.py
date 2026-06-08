#!/usr/bin/env python3
"""Import 深圳市建筑工程消耗量标准 2024 from PDF with local OCR.

No multimodal LLM is used. The importer is intentionally conservative: it saves
raw OCR/page data and records parse issues instead of hiding uncertainty.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import argparse
import io
import json
import os
import sys

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

try:
    import fitz
except ImportError:
    print("[ERROR] PyMuPDF is required. Install pymupdf.")
    sys.exit(1)

from importer.building_standard_2024_parser import (
    BuildingStandard2024Parser,
    ParsedGroup,
    ParsedPage,
    parsed_page_to_json,
    sha256_file,
)


if sys.platform == "win32" and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


ROOT = Path(__file__).resolve().parent
DEFAULT_PDF = ROOT / "mydoc" / "深圳市建筑消耗量标准2024.pdf"
SCHEMA_PATH = ROOT / "db" / "schema_building_standard_2024.sql"

CHAPTER_TITLES = {
    1: "土石方工程",
    2: "混凝土及钢筋混凝土工程",
    3: "砌筑工程",
    4: "屋面及防水工程",
    5: "防腐、隔热、保温工程",
    6: "模板工程",
    7: "脚手架工程",
    8: "垂直运输工程",
    9: "建筑物超高增加费",
}

# Keep a stable fallback independent of console/file encoding on Windows.
CANONICAL_CHAPTER_TITLES = {
    1: "\u571f\u77f3\u65b9\u5de5\u7a0b",
    2: "\u6df7\u51dd\u571f\u53ca\u94a2\u7b4b\u6df7\u51dd\u571f\u5de5\u7a0b",
    3: "\u6728\u7ed3\u6784\u5de5\u7a0b",
    4: "\u5c4b\u9762\u53ca\u9632\u6c34\u5de5\u7a0b",
    5: "\u9632\u8150\u3001\u4fdd\u6e29\u4e0e\u9694\u70ed\u5de5\u7a0b",
    6: "\u6a21\u677f\u5de5\u7a0b",
    7: "\u811a\u624b\u67b6\u5de5\u7a0b",
    8: "\u5782\u76f4\u8fd0\u8f93\u5de5\u7a0b",
    9: "\u5efa\u7b51\u7269\u8d85\u9ad8\u589e\u52a0\u8d39",
}


def get_connection():
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5433)),
        database=os.getenv("DB_NAME", "qmind"),
        user=os.getenv("DB_USER", "qmind"),
        password=os.getenv("DB_PASSWORD", "qmind"),
    )


def apply_schema(conn) -> None:
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute("""
            ALTER TABLE bs2024_subitems
            ADD COLUMN IF NOT EXISTS name_path_json JSONB NOT NULL DEFAULT '[]'::jsonb
        """)
    conn.commit()


def get_or_create_document(conn, pdf_path: Path, page_count: int, force: bool) -> int:
    source_hash = sha256_file(pdf_path)
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM bs2024_documents WHERE source_sha256 = %s", (source_hash,))
        row = cur.fetchone()
        if row and force:
            cur.execute("DELETE FROM bs2024_documents WHERE id = %s", (row[0],))
            conn.commit()
            row = None
        if row:
            return row[0]
        cur.execute(
            """
            INSERT INTO bs2024_documents
              (standard_code, name, region, source_file, source_sha256, page_count,
               publish_date, effective_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                "SJG 171-2024",
                "深圳市建筑工程消耗量标准",
                "深圳市",
                str(pdf_path),
                source_hash,
                page_count,
                "2024-10-14",
                "2024-12-20",
            ),
        )
        doc_id = cur.fetchone()[0]
    conn.commit()
    return doc_id


def create_run(conn, document_id: int, ocr_engine: str, dpi: int, page_start: int, page_end: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bs2024_parse_runs
              (document_id, status, ocr_engine, dpi, page_start, page_end)
            VALUES (%s, 'running', %s, %s, %s, %s)
            RETURNING id
            """,
            (document_id, ocr_engine, dpi, page_start, page_end),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def finish_run(conn, run_id: int, status: str, stats: dict[str, Any], error: Optional[str] = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bs2024_parse_runs
            SET status = %s, stats_json = %s, error_message = %s, finished_at = NOW()
            WHERE id = %s
            """,
            (status, json.dumps(stats, ensure_ascii=False), error, run_id),
        )
    conn.commit()


def page_exists(conn, document_id: int, page_no: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM bs2024_pages WHERE document_id = %s AND page_no = %s",
            (document_id, page_no),
        )
        return cur.fetchone() is not None


def delete_page_data(conn, document_id: int, page_no: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM bs2024_parse_issues WHERE document_id = %s AND page_no = %s", (document_id, page_no))
        cur.execute("DELETE FROM bs2024_pages WHERE document_id = %s AND page_no = %s", (document_id, page_no))
        # Structural rows are intentionally not page-cascade-only. Page reparse is normally done with --force.
    conn.commit()


def upsert_page(conn, document_id: int, run_id: int, page: ParsedPage) -> None:
    cls = page.classification
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bs2024_pages
              (document_id, run_id, page_no, page_type, chapter_no, chapter_title,
               section_type, section_code, title, ocr_text, content_md,
               raw_ocr_json, confidence, warning_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (document_id, page_no) DO UPDATE SET
              run_id = EXCLUDED.run_id,
              page_type = EXCLUDED.page_type,
              chapter_no = EXCLUDED.chapter_no,
              chapter_title = EXCLUDED.chapter_title,
              section_type = EXCLUDED.section_type,
              section_code = EXCLUDED.section_code,
              title = EXCLUDED.title,
              ocr_text = EXCLUDED.ocr_text,
              content_md = EXCLUDED.content_md,
              raw_ocr_json = EXCLUDED.raw_ocr_json,
              confidence = EXCLUDED.confidence,
              warning_count = EXCLUDED.warning_count,
              parsed_at = NOW()
            """,
            (
                document_id,
                run_id,
                page.page_no,
                cls.page_type,
                cls.chapter_no,
                cls.chapter_title,
                cls.section_type,
                cls.section_code,
                cls.title,
                page.ocr_text,
                page.content_md,
                json.dumps(page.raw_ocr, ensure_ascii=False),
                cls.confidence,
                len(page.issues),
            ),
        )
    conn.commit()


def get_or_create_chapter(conn, document_id: int, chapter_no: int, title: str, page_no: int) -> int:
    title = CANONICAL_CHAPTER_TITLES.get(chapter_no, title)
    if not title or title == "未识别章节":
        title = CHAPTER_TITLES.get(chapter_no, title or "未识别章节")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bs2024_chapters
              (document_id, chapter_no, code, title, page_start, page_end, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (document_id, chapter_no) DO UPDATE SET
              title = COALESCE(NULLIF(EXCLUDED.title, ''), bs2024_chapters.title),
              page_start = LEAST(COALESCE(bs2024_chapters.page_start, EXCLUDED.page_start), EXCLUDED.page_start),
              page_end = GREATEST(COALESCE(bs2024_chapters.page_end, EXCLUDED.page_end), EXCLUDED.page_end)
            RETURNING id
            """,
            (document_id, chapter_no, str(chapter_no), title, page_no, page_no, chapter_no),
        )
        chapter_id = cur.fetchone()[0]
    conn.commit()
    return chapter_id


def get_or_create_section(
    conn,
    document_id: int,
    chapter_id: int,
    section_type: str,
    section_code: Optional[str],
    title: str,
    content_md: Optional[str],
    page_no: int,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bs2024_sections
              (document_id, chapter_id, section_type, section_code, title, content_md,
               page_start, page_end, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chapter_id, section_type, COALESCE(section_code, '')) DO UPDATE SET
              title = COALESCE(NULLIF(EXCLUDED.title, ''), bs2024_sections.title),
              content_md = CASE
                WHEN EXCLUDED.content_md IS NULL OR EXCLUDED.content_md = '' THEN bs2024_sections.content_md
                WHEN bs2024_sections.content_md IS NULL OR bs2024_sections.content_md = '' THEN EXCLUDED.content_md
                ELSE bs2024_sections.content_md || E'\n\n---\n\n' || EXCLUDED.content_md
              END,
              page_start = LEAST(COALESCE(bs2024_sections.page_start, EXCLUDED.page_start), EXCLUDED.page_start),
              page_end = GREATEST(COALESCE(bs2024_sections.page_end, EXCLUDED.page_end), EXCLUDED.page_end)
            RETURNING id
            """,
            (
                document_id,
                chapter_id,
                section_type,
                section_code,
                title,
                content_md,
                page_no,
                page_no,
                _section_sort(section_type),
            ),
        )
        section_id = cur.fetchone()[0]
    conn.commit()
    return section_id


def _section_sort(section_type: str) -> int:
    return {"intro": 1, "rules": 2, "items": 3, "directory": 0}.get(section_type, 9)


def _placeholder_group_name(name: Optional[str]) -> bool:
    if not name:
        return True
    compact = "".join(str(name).split())
    return compact.startswith("子目编号") or compact.startswith("子日编号") or compact in {"子目", "编号"}


def _placeholder_item_name(name: Optional[str]) -> bool:
    if not name:
        return True
    compact = "".join(str(name).split())
    return compact.startswith("子目编号") or compact.startswith("子日编号") or compact in {"子目", "编号", "未识别项目"}


def build_clean_name_path(*parts: Optional[str]) -> list[str]:
    path: list[str] = []
    skip_needles = ["子目编号", "子日编号", "参考价格", "参考价恪"]
    for part in parts:
        if not part:
            continue
        cleaned = " ".join(str(part).split()).strip()
        compact = "".join(cleaned.split())
        if not compact or any(needle in compact for needle in skip_needles):
            continue
        if cleaned not in path:
            path.append(cleaned)
    return path


def seed_previous_context(conn, document_id: int, page_start: int) -> dict[str, Any]:
    """Seed continuation imports from the last parsed item page before page_start."""
    if page_start <= 1:
        return {}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
              c.chapter_no,
              c.title AS chapter_title,
              s.section_code,
              s.title AS section_title,
              g.group_code,
              g.group_name,
              i.item_name
            FROM bs2024_item_groups g
            JOIN bs2024_sections s ON s.id = g.section_id
            JOIN bs2024_chapters c ON c.id = s.chapter_id
            LEFT JOIN LATERAL (
              SELECT item_name
              FROM bs2024_items
              WHERE group_id = g.id AND page_no < %s
              ORDER BY page_no DESC, id DESC
              LIMIT 1
            ) i ON TRUE
            WHERE g.document_id = %s AND g.page_start < %s
            ORDER BY g.page_end DESC, g.id DESC
            LIMIT 1
            """,
            (page_start, document_id, page_start),
        )
        row = cur.fetchone()
    return dict(row or {})


def insert_groups(conn, document_id: int, section_id: int, page_no: int, groups: list[ParsedGroup]) -> Counter:
    counts: Counter = Counter()
    with conn.cursor() as cur:
        for group in groups:
            group_id = None
            if group.group_code:
                cur.execute(
                    """
                    SELECT id FROM bs2024_item_groups
                    WHERE document_id = %s AND section_id = %s AND group_code = %s
                    ORDER BY id
                    LIMIT 1
                    """,
                    (document_id, section_id, group.group_code),
                )
                row = cur.fetchone()
                if row:
                    group_id = row[0]
                    cur.execute(
                        """
                        UPDATE bs2024_item_groups
                        SET group_name = COALESCE(NULLIF(group_name, ''), %s),
                            page_start = LEAST(page_start, %s),
                            page_end = GREATEST(page_end, %s)
                        WHERE id = %s
                        """,
                        (group.group_name, page_no, page_no, group_id),
                    )
            if group_id is None:
                cur.execute(
                    """
                    INSERT INTO bs2024_item_groups
                      (document_id, section_id, group_code, group_name, page_start, page_end, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (document_id, section_id, group.group_code, group.group_name, page_no, page_no, group.sort_order),
                )
                group_id = cur.fetchone()[0]
                counts["groups"] += 1
            for item in group.items:
                cur.execute(
                    """
                    INSERT INTO bs2024_items
                      (document_id, group_id, item_no, item_name, work_content, unit,
                       page_no, raw_row_json, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        document_id,
                        group_id,
                        item.item_no,
                        item.item_name,
                        item.work_content,
                        item.unit,
                        page_no,
                        json.dumps(item.raw_row_json, ensure_ascii=False),
                        item.sort_order,
                    ),
                )
                item_id = cur.fetchone()[0]
                counts["items"] += 1
                subitem_id_by_code: dict[str, int] = {}
                for sub in item.subitems:
                    cur.execute(
                        """
                        INSERT INTO bs2024_subitems
                          (document_id, item_id, subitem_code, subitem_name, variant_desc, unit, name_path_json,
                           total_unit_price, unit_price, labor_cost, material_cost, machine_cost,
                           management_fee, profit, safety_fee, statutory_fee, tax,
                           page_no, confidence, sort_order)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (document_id, subitem_code) DO NOTHING
                        RETURNING id
                        """,
                        (
                            document_id,
                            item_id,
                            sub.subitem_code,
                            sub.subitem_name,
                            sub.variant_desc,
                            sub.unit or item.unit,
                            json.dumps(sub.name_path, ensure_ascii=False),
                            sub.total_unit_price,
                            sub.unit_price,
                            sub.labor_cost,
                            sub.material_cost,
                            sub.machine_cost,
                            sub.management_fee,
                            sub.profit,
                            sub.safety_fee,
                            sub.statutory_fee,
                            sub.tax,
                            page_no,
                            sub.confidence,
                            sub.sort_order,
                        ),
                    )
                    row = cur.fetchone()
                    if row:
                        subitem_id_by_code[sub.subitem_code] = row[0]
                        counts["subitems"] += 1
                for resource in item.resources:
                    for subitem_code, quantity in resource.quantities.items():
                        if quantity is None:
                            continue
                        subitem_id = subitem_id_by_code.get(subitem_code)
                        if not subitem_id:
                            continue
                        cur.execute(
                            """
                            INSERT INTO bs2024_resources
                              (document_id, subitem_id, resource_type, resource_name, unit,
                               quantity, ref_price, page_no, sort_order)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                document_id,
                                subitem_id,
                                resource.resource_type,
                                resource.resource_name,
                                resource.unit,
                                quantity,
                                resource.ref_price,
                                page_no,
                                resource.sort_order,
                            ),
                        )
                        counts["resources"] += 1
    conn.commit()
    return counts


def insert_issues(conn, document_id: int, run_id: int, page: ParsedPage) -> None:
    if not page.issues:
        return
    with conn.cursor() as cur:
        for issue in page.issues:
            cur.execute(
                """
                INSERT INTO bs2024_parse_issues
                  (document_id, run_id, page_no, severity, issue_type, message, context_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    document_id,
                    run_id,
                    page.page_no,
                    issue.get("severity", "warning"),
                    issue.get("issue_type", "unknown"),
                    issue.get("message", ""),
                    json.dumps(issue.get("context", {}), ensure_ascii=False),
                ),
            )
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="导入深圳市建筑工程消耗量标准 2024 PDF")
    parser.add_argument("--pdf", default=str(DEFAULT_PDF), help="PDF 文件路径")
    parser.add_argument("--force", action="store_true", help="删除同源文档后重新导入")
    parser.add_argument("--resume", action="store_true", help="跳过已解析页面")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--ocr-engine", choices=["auto", "paddle", "easyocr"], default="auto")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    page_start = max(1, args.start_page)
    page_end = min(args.end_page or total_pages, total_pages)

    conn = get_connection()
    try:
        apply_schema(conn)
        document_id = get_or_create_document(conn, pdf_path, total_pages, args.force)
        local_parser = BuildingStandard2024Parser(args.ocr_engine)
        run_id = create_run(conn, document_id, local_parser.ocr_engine_name, args.dpi, page_start, page_end)
        print(f"文档 ID: {document_id} | 运行 ID: {run_id} | OCR: {local_parser.ocr_engine_name}")
        print(f"页段: {page_start}-{page_end} / {total_pages}")

        stats: Counter = Counter()
        current_chapter_no: Optional[int] = None
        current_chapter_title = "未识别章节"
        current_items_section_code: Optional[str] = None
        current_items_section_title = "子目构成表"
        current_group_code: Optional[str] = None
        current_group_name: Optional[str] = None
        current_item_name: Optional[str] = None
        if not args.force:
            seed = seed_previous_context(conn, document_id, page_start)
            current_chapter_no = seed.get("chapter_no") or current_chapter_no
            current_chapter_title = seed.get("chapter_title") or current_chapter_title
            current_items_section_code = seed.get("section_code") or current_items_section_code
            current_items_section_title = seed.get("section_title") or current_items_section_title
            current_group_code = seed.get("group_code") or current_group_code
            current_group_name = seed.get("group_name") or current_group_name
            current_item_name = seed.get("item_name") or current_item_name
            if seed:
                print(
                    f"[CONTEXT] 继承上一段: 章节={current_chapter_no or '-'} "
                    f"分组={current_group_code or '-'} {current_group_name or ''}".strip()
                )

        for page_no in range(page_start, page_end + 1):
            if args.resume and page_exists(conn, document_id, page_no):
                print(f"[SKIP] 页 {page_no} 已存在")
                stats["skipped_pages"] += 1
                continue
            if not args.resume:
                delete_page_data(conn, document_id, page_no)

            print(f"[PAGE {page_no}] OCR/解析中...")
            parsed = local_parser.parse_page(doc, page_no, dpi=args.dpi)
            cls = parsed.classification
            if cls.chapter_no:
                if cls.chapter_no != current_chapter_no and not cls.chapter_title:
                    current_chapter_title = CANONICAL_CHAPTER_TITLES.get(
                        cls.chapter_no, current_chapter_title
                    )
                current_chapter_no = cls.chapter_no
            if cls.chapter_title:
                current_chapter_title = cls.chapter_title
            if cls.page_type == "items":
                if cls.section_code:
                    current_items_section_code = cls.section_code
                elif current_items_section_code:
                    cls.section_code = current_items_section_code
                if cls.title:
                    current_items_section_title = cls.title
                elif current_items_section_title:
                    cls.title = current_items_section_title
                for group in parsed.groups:
                    if group.group_code:
                        current_group_code = group.group_code
                    elif current_group_code:
                        group.group_code = current_group_code
                    if not _placeholder_group_name(group.group_name):
                        current_group_name = group.group_name
                    elif current_group_name:
                        group.group_name = current_group_name
                    for item in group.items:
                        if not _placeholder_item_name(item.item_name):
                            current_item_name = item.item_name
                        elif current_item_name:
                            item.item_name = current_item_name
                        for sub in item.subitems:
                            sub.name_path = build_clean_name_path(
                                group.group_name,
                                item.item_name,
                                sub.subitem_name,
                                sub.variant_desc,
                            )

            upsert_page(conn, document_id, run_id, parsed)
            insert_issues(conn, document_id, run_id, parsed)

            stats["pages"] += 1
            stats[f"page_type_{cls.page_type}"] += 1
            stats["issues"] += len(parsed.issues)

            if cls.page_type in {"intro", "rules", "items"}:
                chapter_no = cls.chapter_no or current_chapter_no or 0
                chapter_title = cls.chapter_title or current_chapter_title
                chapter_id = get_or_create_chapter(conn, document_id, chapter_no, chapter_title, page_no)
                section_id = get_or_create_section(
                    conn,
                    document_id,
                    chapter_id,
                    cls.section_type or cls.page_type,
                    cls.section_code,
                    cls.title or cls.page_type,
                    parsed.content_md,
                    page_no,
                )
                if parsed.groups:
                    stats.update(insert_groups(conn, document_id, section_id, page_no, parsed.groups))

            print(
                f"  -> {cls.page_type} | conf={cls.confidence:.2f} | "
                f"groups={len(parsed.groups)} | issues={len(parsed.issues)}"
            )

        finish_run(conn, run_id, "done", dict(stats))
        print("\n导入完成")
        for key, value in sorted(stats.items()):
            print(f"  {key}: {value}")
    except Exception as exc:
        try:
            finish_run(conn, locals().get("run_id", 0), "error", {}, str(exc))
        except Exception:
            pass
        raise
    finally:
        doc.close()
        conn.close()


if __name__ == "__main__":
    main()
