"""
将解析结果写入数据库（quota_* 表）。
复用 db/connection.py 的 get_connection()。
"""

import os
from typing import List, Optional, Dict
import psycopg2
import psycopg2.extras

from importer.quota_parser import ChapterInfo, QuotaItem


def init_schema(conn):
    schema_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema_quota.sql')
    with open(schema_path, encoding='utf-8') as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def get_or_create_standard(conn, standard_code: str, name: str, base_date, source_file: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM quota_standards WHERE standard_code = %s",
            (standard_code,)
        )
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            """INSERT INTO quota_standards (standard_code, name, base_date, source_file)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (standard_code, name, base_date, source_file)
        )
        sid = cur.fetchone()[0]
    conn.commit()
    return sid


def delete_standard(conn, standard_id: int):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM quota_standards WHERE id = %s", (standard_id,))
    conn.commit()


def insert_chapters(conn, standard_id: int, chapters: List[ChapterInfo]) -> Dict[str, int]:
    """插入章节，返回 code→id 映射（code 可能为空字符串）"""
    code_to_id: Dict[str, int] = {}

    # 按 level 和 sort_order 排序，先插父级
    sorted_chapters = sorted(chapters, key=lambda c: (c.level, c.sort_order))

    with conn.cursor() as cur:
        for ch in sorted_chapters:
            # 确定父节点：找 level-1 的最近祖先
            parent_id = None
            if ch.level > 1 and ch.code:
                # 从 code 推断父 code：去掉最后一段
                parts = ch.code.rsplit('.', 1)
                if len(parts) == 2:
                    parent_code = parts[0]
                    parent_id = code_to_id.get(parent_code)

            cur.execute(
                """INSERT INTO quota_chapters
                   (standard_id, code, name, parent_id, level, sort_order)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (standard_id, ch.code or None, ch.name, parent_id, ch.level, ch.sort_order)
            )
            cid = cur.fetchone()[0]
            if ch.code:
                code_to_id[ch.code] = cid
    conn.commit()
    return code_to_id


def insert_items(conn, standard_id: int, items: List[QuotaItem], chapter_map: Dict[str, int]):
    """批量插入子目和工料机"""
    item_rows = []
    for it in items:
        chapter_id = chapter_map.get(it.chapter_code) if it.chapter_code else None
        item_rows.append((
            standard_id,
            chapter_id,
            it.item_code,
            it.item_name,
            it.variant_desc,
            it.unit,
            it.work_content,
            it.total_unit_price,
            it.unit_price,
            it.labor_cost,
            it.material_cost,
            it.machine_cost,
            it.management_fee,
            it.profit,
            it.safety_fee,
            it.statutory_fee,
            it.tax,
            it.source_row,
        ))

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO quota_items
               (standard_id, chapter_id, item_code, item_name, variant_desc, unit,
                work_content, total_unit_price, unit_price, labor_cost, material_cost,
                machine_cost, management_fee, profit, safety_fee, statutory_fee, tax, source_row)
               VALUES %s""",
            item_rows,
        )
        # 按插入顺序取回 id（source_row 可能重复，用 ctid 排序保证顺序）
        cur.execute(
            "SELECT id FROM quota_items WHERE standard_id = %s ORDER BY id",
            (standard_id,)
        )
        inserted_ids = [r[0] for r in cur.fetchall()]

    conn.commit()

    # 插入工料机
    resource_rows = []
    for item_id, it in zip(inserted_ids, items):
        for res in it.resources:
            resource_rows.append((
                item_id,
                res.resource_type,
                res.resource_name,
                res.unit,
                res.quantity,
                res.ref_price,
            ))

    if resource_rows:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO quota_resources
                   (item_id, resource_type, resource_name, unit, quantity, ref_price)
                   VALUES %s""",
                resource_rows,
            )
        conn.commit()

    return len(inserted_ids), len(resource_rows)
