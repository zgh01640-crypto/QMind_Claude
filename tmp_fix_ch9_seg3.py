from decimal import Decimal
import json

from dotenv import load_dotenv

from db.connection import get_connection


DOC = 25


def d(value):
    return None if value is None else Decimal(str(value))


COSTS = {
    27: (72.38, 58.93, 48.30, 0, 0, 7.82, 2.81, 2.40, 8.69, 2.36),
    28: (10.20, 8.30, 6.80, 0, 0, 1.10, .40, .34, 1.22, .34),
    29: (54.29, 44.19, 36.22, 0, 0, 5.87, 2.10, 1.80, 6.52, 1.78),
    30: (10.20, 8.30, 6.80, 0, 0, 1.10, .40, .34, 1.22, .34),
    31: (40.71, 33.14, 27.16, 0, 0, 4.40, 1.58, 1.35, 4.89, 1.33),
    32: (10.20, 8.30, 6.80, 0, 0, 1.10, .40, .34, 1.22, .34),
    33: (34.62, 28.18, 23.10, 0, 0, 3.74, 1.34, 1.15, 4.16, 1.13),
    34: (10.20, 8.30, 6.80, 0, 0, 1.10, .40, .34, 1.22, .34),
    35: (90.47, 73.65, 60.36, 0, 0, 9.78, 3.51, 3.00, 10.86, 2.96),
    36: (10.20, 8.30, 6.80, 0, 0, 1.10, .40, .34, 1.22, .34),
    37: (63.35, 51.57, 42.26, 0, 0, 6.85, 2.46, 2.10, 7.61, 2.07),
    38: (10.20, 8.30, 6.80, 0, 0, 1.10, .40, .34, 1.22, .34),
    39: (126.66, 103.10, 84.50, 0, 0, 13.69, 4.91, 4.21, 15.21, 4.14),
    40: (23.50, 19.13, 15.68, 0, 0, 2.54, .91, .78, 2.82, .77),
    41: (95.01, 77.33, 63.38, 0, 0, 10.27, 3.68, 3.16, 11.41, 3.11),
    42: (23.50, 19.13, 15.68, 0, 0, 2.54, .91, .78, 2.82, .77),
    43: (80.73, 65.72, 53.86, 0, 0, 8.73, 3.13, 2.68, 9.69, 2.64),
    44: (20.00, 16.29, 13.35, 0, 0, 2.16, .78, .66, 2.40, .65),
    45: (65.42, 53.25, 43.64, 0, 0, 7.07, 2.54, 2.17, 7.86, 2.14),
    46: (16.00, 13.02, 10.67, 0, 0, 1.73, .62, .53, 1.92, .53),
}


SPECS = {
    27: ("9.3.4", "灰砂砖", "运距L(m) / 0<L≤50", "m³", 259),
    28: ("9.3.4", "灰砂砖", "运距L(m) / L>50 / 每增100以内", "m³", 259),
    29: ("9.3.4", "空心石渣砖", "运距L(m) / 0<L≤50", "m³", 259),
    30: ("9.3.4", "空心石渣砖", "运距L(m) / L>50 / 每增100以内", "m³", 259),
    31: ("9.3.4", "轻质混凝土砌块", "运距L(m) / 0<L≤50", "m³", 260),
    32: ("9.3.4", "轻质混凝土砌块", "运距L(m) / L>50 / 每增100以内", "m³", 260),
    33: ("9.3.4", "轻质空心砌块", "运距L(m) / 0<L≤50", "m³", 260),
    34: ("9.3.4", "轻质空心砌块", "运距L(m) / L>50 / 每增100以内", "m³", 260),
    35: ("9.3.4", "大阶砖、石材（块材）", "运距L(m) / 0<L≤50", "m³", 261),
    36: ("9.3.4", "大阶砖、石材（块材）", "运距L(m) / L>50 / 每增100以内", "m³", 261),
    37: ("9.3.4", "水泥花砖", "运距L(m) / 0<L≤50", "m³", 261),
    38: ("9.3.4", "水泥花砖", "运距L(m) / L>50 / 每增100以内", "m³", 261),
    39: ("9.3.5", "石材（板材）", "运距L(m) / 0<L≤50", "100m²", 262),
    40: ("9.3.5", "石材（板材）", "运距L(m) / L>50 / 每增100以内", "100m²", 262),
    41: ("9.3.5", "地面瓷砖", "运距L(m) / 0<L≤50", "100m²", 262),
    42: ("9.3.5", "地面瓷砖", "运距L(m) / L>50 / 每增100以内", "100m²", 262),
    43: ("9.3.5", "墙面瓷砖", "运距L(m) / 0<L≤50", "100m²", 263),
    44: ("9.3.5", "墙面瓷砖", "运距L(m) / L>50 / 每增100以内", "100m²", 263),
    45: ("9.3.5", "马赛克", "运距L(m) / 0<L≤50", "100m²", 263),
    46: ("9.3.5", "马赛克", "运距L(m) / L>50 / 每增100以内", "100m²", 263),
}


GROUPS = {
    "9.3.4": ("砌筑块材人力车二次运输", 259, 261, 4, "010009-27"),
    "9.3.5": ("其他材料人力车二次运输", 262, 263, 5, "010009-39"),
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
        cur.execute("UPDATE bs2024_chapters SET page_end=263 WHERE id=%s", (chapter_id,))
        cur.execute("UPDATE bs2024_sections SET page_end=263 WHERE id=%s", (section_id,))

        group_ids = {}
        item_ids = {}
        work = "材料的装车、运输、卸车、堆放整理。"
        for code, (name, start, end, order, first_code) in GROUPS.items():
            cur.execute(
                """
                SELECT id FROM bs2024_item_groups
                WHERE document_id=%s AND group_code=%s ORDER BY id LIMIT 1
                """,
                (DOC, code),
            )
            row = cur.fetchone()
            if row:
                group_id = row[0]
                cur.execute(
                    """
                    UPDATE bs2024_item_groups SET section_id=%s,group_name=%s,
                      page_start=%s,page_end=%s,sort_order=%s WHERE id=%s
                    """,
                    (section_id, name, start, end, order, group_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_item_groups
                      (document_id,section_id,group_code,group_name,
                       page_start,page_end,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
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
                    VALUES (%s,%s,1,%s,%s,%s,1) RETURNING id
                    """,
                    (DOC, group_id, name, work, start),
                )
                item_id = cur.fetchone()[0]
            item_ids[code] = item_id

        for number in range(27, 47):
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
                WHERE document_id=%s AND subitem_code=%s RETURNING id
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
            WHERE document_id=%s AND page_no BETWEEN 259 AND 263
            """,
            (DOC,),
        )
        cur.execute(
            """
            DELETE FROM bs2024_items i WHERE i.document_id=%s
              AND NOT EXISTS (SELECT 1 FROM bs2024_subitems s WHERE s.item_id=i.id)
            """,
            (DOC,),
        )
        cur.execute(
            """
            DELETE FROM bs2024_item_groups g WHERE g.document_id=%s
              AND NOT EXISTS (SELECT 1 FROM bs2024_items i WHERE i.group_id=g.id)
            """,
            (DOC,),
        )
    conn.commit()
finally:
    conn.close()

print("Corrected Chapter 9 subitems 010009-27 through 010009-46.")
