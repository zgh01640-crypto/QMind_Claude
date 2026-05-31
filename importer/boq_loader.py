"""
将解析结果写入数据库的 boq_* 表。
"""

import os


def init_schema(conn):
    schema_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema_boq.sql')
    with open(schema_path, encoding='utf-8') as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def get_project_by_source(conn, source_file):
    with conn.cursor() as cur:
        cur.execute('SELECT id FROM boq_projects WHERE source_file = %s', (source_file,))
        row = cur.fetchone()
    return row[0] if row else None


def delete_project(conn, project_id):
    with conn.cursor() as cur:
        cur.execute('DELETE FROM boq_projects WHERE id = %s', (project_id,))
    conn.commit()


def insert_project(conn, project_name, bid_section, source_file, tag):
    with conn.cursor() as cur:
        cur.execute(
            '''INSERT INTO boq_projects (project_name, bid_section, source_file, tag)
               VALUES (%s, %s, %s, %s) RETURNING id''',
            (project_name, bid_section, source_file, tag),
        )
        project_id = cur.fetchone()[0]
    conn.commit()
    return project_id


def insert_sections(conn, project_id, sections):
    """返回 {section_seq: section_id} 映射。"""
    seq_to_id = {}
    with conn.cursor() as cur:
        for s in sections:
            cur.execute(
                '''INSERT INTO boq_sections (project_id, seq, section_name)
                   VALUES (%s, %s, %s) RETURNING id''',
                (project_id, s['seq'], s['section_name']),
            )
            seq_to_id[s['seq']] = cur.fetchone()[0]
    conn.commit()
    return seq_to_id


def insert_items(conn, project_id, items, seq_to_section_id):
    with conn.cursor() as cur:
        for item in items:
            section_id = seq_to_section_id.get(item['section_seq'])
            cur.execute(
                '''INSERT INTO boq_items
                   (project_id, section_id, item_seq, item_code, item_name,
                    item_description, unit, quantity, unit_price, total_price, provisional_price)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                (
                    project_id, section_id,
                    item['item_seq'], item['item_code'], item['item_name'],
                    item['item_description'], item['unit'], item['quantity'],
                    item['unit_price'], item['total_price'], item['provisional_price'],
                ),
            )
    conn.commit()
    return len(items)
