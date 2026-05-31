"""
将 measure_parser 解析结果写入 PostgreSQL。
表：measure_standards, measure_sections, measure_items
"""
import os
import psycopg2
from psycopg2.extras import execute_values


def apply_schema(conn):
    schema_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema_measure.sql')
    with open(schema_path, encoding='utf-8') as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def load(conn, source_file: str, standard_name: str,
         sections: list[dict], items: list[dict]) -> int:
    """
    返回 standard_id。
    若同名标准已存在，先清除旧数据再重新写入。
    """
    with conn.cursor() as cur:
        # 检查已存在
        cur.execute("SELECT id FROM measure_standards WHERE name = %s", (standard_name,))
        row = cur.fetchone()
        if row:
            std_id = row[0]
            cur.execute("DELETE FROM measure_items   WHERE standard_id = %s", (std_id,))
            cur.execute("DELETE FROM measure_sections WHERE standard_id = %s", (std_id,))
            cur.execute("UPDATE measure_standards SET source_file=%s, imported_at=NOW() WHERE id=%s",
                        (source_file, std_id))
        else:
            cur.execute(
                "INSERT INTO measure_standards(name, source_file) VALUES(%s,%s) RETURNING id",
                (standard_name, source_file)
            )
            std_id = cur.fetchone()[0]

        # ── 写入节（先 level=1，再 level=2）─────────────────────────────────
        code_to_id: dict[str, int] = {}

        for sec in sections:
            parent_id = code_to_id.get(sec['parent_code']) if sec['parent_code'] else None
            sort_order = _sort_key(sec['code'])
            cur.execute(
                """INSERT INTO measure_sections(standard_id, code, name, level, parent_id, sort_order)
                   VALUES(%s,%s,%s,%s,%s,%s) RETURNING id""",
                (std_id, sec['code'], sec['name'], sec['level'], parent_id, sort_order)
            )
            code_to_id[sec['code']] = cur.fetchone()[0]

        # ── 批量写入清单项目 ──────────────────────────────────────────────────
        if items:
            rows = []
            for it in items:
                sec_id = code_to_id.get(it['section_code']) if it['section_code'] else None
                rows.append((
                    std_id, sec_id,
                    it['item_code'], it['item_name'],
                    it['item_features'], it['unit'],
                    it['calc_rule'], it['work_content'],
                ))
            execute_values(cur, """
                INSERT INTO measure_items
                    (standard_id, section_id, item_code, item_name,
                     item_features, unit, calc_rule, work_content)
                VALUES %s
                ON CONFLICT (standard_id, item_code) DO UPDATE SET
                    item_name     = EXCLUDED.item_name,
                    item_features = EXCLUDED.item_features,
                    unit          = EXCLUDED.unit,
                    calc_rule     = EXCLUDED.calc_rule,
                    work_content  = EXCLUDED.work_content
            """, rows)

    conn.commit()
    return std_id


def _sort_key(code: str) -> int:
    """将节编码转为整数排序键，如 A→1, A.1→101, B.3→203"""
    if not code:
        return 0
    parts = code.split('.')
    letter = parts[0]
    num = int(parts[1]) if len(parts) > 1 else 0
    return (ord(letter) - ord('A') + 1) * 100 + num
