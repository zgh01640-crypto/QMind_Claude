from decimal import Decimal
import json

from dotenv import load_dotenv

from db.connection import get_connection


DOC = 25


def d(value):
    return None if value is None else Decimal(str(value))


COSTS = {
    9: (142.22, 115.77, 94.89, 0, 0, 15.37, 5.51, 4.72, 17.08, 4.65),
    10: (36.72, 29.89, 24.50, 0, 0, 3.97, 1.42, 1.22, 4.41, 1.20),
    11: (67.47, 54.92, 45.01, 0, 0, 7.29, 2.62, 2.24, 8.10, 2.21),
    12: (14.83, 12.08, 9.90, 0, 0, 1.60, .58, .49, 1.78, .48),
    13: (87.70, 71.39, 58.51, 0, 0, 9.48, 3.40, 2.91, 10.53, 2.87),
    14: (16.67, 13.57, 11.12, 0, 0, 1.80, .65, .55, 2.00, .55),
    15: (84.33, 68.64, 56.26, 0, 0, 9.11, 3.27, 2.80, 10.13, 2.76),
    16: (16.84, 13.71, 11.24, 0, 0, 1.82, .65, .56, 2.02, .55),
    17: (96.99, 78.95, 64.71, 0, 0, 10.48, 3.76, 3.22, 11.65, 3.17),
    18: (20.38, 16.58, 13.59, 0, 0, 2.20, .79, .68, 2.45, .67),
    19: (37.86, 30.81, 25.25, 0, 0, 4.09, 1.47, 1.26, 4.55, 1.24),
    20: (8.34, 6.79, 5.57, 0, 0, .90, .32, .28, 1.00, .27),
    21: (58.29, 47.45, 38.89, 0, 0, 6.30, 2.26, 1.94, 7.00, 1.90),
    22: (12.82, 10.44, 8.55, 0, 0, 1.39, .50, .43, 1.54, .41),
    23: (46.33, 37.72, 30.91, 0, 0, 5.01, 1.80, 1.54, 5.56, 1.51),
    24: (10.20, 8.30, 6.80, 0, 0, 1.10, .40, .34, 1.22, .34),
    25: (57.89, 47.13, 38.63, 0, 0, 6.26, 2.24, 1.92, 6.95, 1.89),
    26: (10.20, 8.30, 6.80, 0, 0, 1.10, .40, .34, 1.22, .34),
}


SPECS = {
    9: ("9.3.1", "金属门", "各种规格 / 运距L(m) / 0<L≤50", "t", 254),
    10: ("9.3.1", "金属门", "各种规格 / 运距L(m) / L>50 / 每增100以内", "t", 254),
    11: ("9.3.2", "胶合板", "运距L(m) / 0<L≤50", "100m²", 255),
    12: ("9.3.2", "胶合板", "运距L(m) / L>50 / 每增100以内", "100m²", 255),
    13: ("9.3.2", "门窗套料", "运距L(m) / 0<L≤50", "m³", 255),
    14: ("9.3.2", "门窗套料", "运距L(m) / L>50 / 每增100以内", "m³", 255),
    15: ("9.3.2", "枋板材", "运距L(m) / 0<L≤50", "m³", 256),
    16: ("9.3.2", "枋板材", "运距L(m) / L>50 / 每增100以内", "m³", 256),
    17: ("9.3.2", "圆木", "运距L(m) / 0<L≤50", "m³", 256),
    18: ("9.3.2", "圆木", "运距L(m) / L>50 / 每增100以内", "m³", 256),
    19: ("9.3.3", "水泥", "运距L(m) / 0<L≤50", "t", 257),
    20: ("9.3.3", "水泥", "运距L(m) / L>50 / 每增100以内", "t", 257),
    21: ("9.3.3", "石灰", "运距L(m) / 0<L≤50", "t", 257),
    22: ("9.3.3", "石灰", "运距L(m) / L>50 / 每增100以内", "t", 257),
    23: ("9.3.3", "砂", "运距L(m) / 0<L≤50", "m³", 258),
    24: ("9.3.3", "砂", "运距L(m) / L>50 / 每增100以内", "m³", 258),
    25: ("9.3.3", "碎石", "运距L(m) / 0<L≤50", "m³", 258),
    26: ("9.3.3", "碎石", "运距L(m) / L>50 / 每增100以内", "m³", 258),
}


GROUPS = {
    "9.3.1": ("金属材料人力车二次运输", 252, 254, 1, "010009-1"),
    "9.3.2": ("木质材料人力车二次运输", 255, 256, 2, "010009-11"),
    "9.3.3": ("散粒材料人力车二次运输", 257, 258, 3, "010009-19"),
}


load_dotenv(".env")
conn = get_connection()
try:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id,s.id FROM bs2024_chapters c
            JOIN bs2024_sections s ON s.chapter_id=c.id
            WHERE c.document_id=%s AND c.chapter_no=9 AND s.section_code='9.3'
            ORDER BY s.id LIMIT 1
            """,
            (DOC,),
        )
        chapter_id, section_id = cur.fetchone()
        cur.execute(
            "UPDATE bs2024_chapters SET title='材料二次运输工程',page_end=258 WHERE id=%s",
            (chapter_id,),
        )
        cur.execute(
            "UPDATE bs2024_sections SET page_end=258 WHERE id=%s",
            (section_id,),
        )

        group_ids = {}
        item_ids = {}
        work = "材料的装车、运输、卸车、堆放整理。"
        for code, (name, start, end, order, first_code) in GROUPS.items():
            cur.execute(
                """
                SELECT id FROM bs2024_item_groups
                WHERE document_id=%s AND group_code=%s
                ORDER BY id LIMIT 1
                """,
                (DOC, code),
            )
            row = cur.fetchone()
            if row:
                group_id = row[0]
                cur.execute(
                    """
                    UPDATE bs2024_item_groups SET section_id=%s,group_name=%s,
                      page_start=%s,page_end=%s,sort_order=%s
                    WHERE id=%s
                    """,
                    (section_id, name, start, end, order, group_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_item_groups
                      (document_id,section_id,group_code,group_name,
                       page_start,page_end,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (DOC, section_id, code, name, start, end, order),
                )
                group_id = cur.fetchone()[0]
            group_ids[code] = group_id

            cur.execute(
                """
                SELECT i.id FROM bs2024_items i
                JOIN bs2024_subitems s ON s.item_id=i.id
                WHERE s.document_id=%s AND s.subitem_code=%s
                ORDER BY i.id LIMIT 1
                """,
                (DOC, first_code),
            )
            row = cur.fetchone()
            if row:
                item_id = row[0]
                cur.execute(
                    """
                    UPDATE bs2024_items SET group_id=%s,item_no=1,item_name=%s,
                      work_content=%s,unit=NULL,page_no=%s,sort_order=1
                    WHERE id=%s
                    """,
                    (group_id, name, work, start, item_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_items
                      (document_id,group_id,item_no,item_name,work_content,page_no,sort_order)
                    VALUES (%s,%s,1,%s,%s,%s,1)
                    RETURNING id
                    """,
                    (DOC, group_id, name, work, start),
                )
                item_id = cur.fetchone()[0]
            item_ids[code] = item_id

        for number in range(9, 27):
            group_code, name, variant, unit, page = SPECS[number]
            path = [GROUPS[group_code][0], name]
            path.extend(variant.split(" / "))
            cur.execute(
                """
                UPDATE bs2024_subitems SET item_id=%s,subitem_name=%s,
                  variant_desc=%s,unit=%s,name_path_json=%s::jsonb,
                  total_unit_price=%s,unit_price=%s,labor_cost=%s,
                  material_cost=%s,machine_cost=%s,management_fee=%s,
                  profit=%s,safety_fee=%s,statutory_fee=%s,tax=%s,
                  page_no=%s,confidence=1,sort_order=%s
                WHERE document_id=%s AND subitem_code=%s
                RETURNING id
                """,
                (
                    item_ids[group_code], name, variant, unit,
                    json.dumps(path, ensure_ascii=False),
                    *[d(value) for value in COSTS[number]],
                    page, number, DOC, f"010009-{number}",
                ),
            )
            subitem_id = cur.fetchone()[0]
            cur.execute("DELETE FROM bs2024_resources WHERE subitem_id=%s", (subitem_id,))
            cur.execute(
                """
                INSERT INTO bs2024_resources
                  (document_id,subitem_id,resource_type,resource_name,unit,
                   quantity,ref_price,page_no,sort_order)
                VALUES (%s,%s,'人工','普通人工费','元',%s,NULL,%s,1)
                """,
                (DOC, subitem_id, d(COSTS[number][2]), page),
            )

        cur.execute(
            """
            UPDATE bs2024_pages SET chapter_no=9,chapter_title='材料二次运输工程',
              section_code='9.3',section_type='items'
            WHERE document_id=%s AND page_no BETWEEN 254 AND 258
            """,
            (DOC,),
        )
        cur.execute(
            """
            DELETE FROM bs2024_items i
            WHERE i.document_id=%s
              AND NOT EXISTS (SELECT 1 FROM bs2024_subitems s WHERE s.item_id=i.id)
            """,
            (DOC,),
        )
        cur.execute(
            """
            DELETE FROM bs2024_item_groups g
            WHERE g.document_id=%s
              AND NOT EXISTS (SELECT 1 FROM bs2024_items i WHERE i.group_id=g.id)
            """,
            (DOC,),
        )
    conn.commit()
finally:
    conn.close()

print("Corrected Chapter 9 subitems 010009-9 through 010009-26.")
