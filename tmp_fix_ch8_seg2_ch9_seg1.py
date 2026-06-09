from decimal import Decimal
import json

from dotenv import load_dotenv

from db.connection import get_connection


DOC = 25


def d(value):
    return None if value is None else Decimal(str(value))


INTRO_MD = """## 9.1 说明

### 9.1.1

本章包括金属材料人力车二次运输、木质材料人力车二次运输、散粒材料人力车二次运输、砌筑块材人力车二次运输、其他材料人力车二次运输以及机动翻斗车场内运输钢筋六部分，适用于建筑、装饰工程中的建筑材料二次运输费的计算。

### 9.1.2

建筑材料二次运输费用的计算适用于由于施工环境或者施工场地条件的限制，建筑材料进场时不能直接运至工地仓库、施工现场材料堆放点（现场加工地点），需要转运而重复发生的装卸、运输。

### 9.1.3

除钢筋的场内运输设置了机动翻斗车运输的子目外，本章常用材料的二次运输子目均按人力车运输的方式编制，未考虑自卸汽车的二次运输，发生时应另行计算。

### 9.1.4

本章仅列出建筑物施工过程中常见材料二次运输的子目，如与实际不同时，应按材料的外形特征以及密度近似的原则选择子目执行。
"""


RULES_MD = """## 9.2 工程量计算规则

### 9.2.1

建筑材料二次运输的距离应按装车地点至材料堆放场地中心的距离计算，材料堆放点搬迁时二次运输的距离应按新旧两个材料堆放点中心之间的间距计算。

### 9.2.2

金属材料人力车二次运输的工程量应按金属材料的重量以吨计算。

### 9.2.3

方板材、圆木等原木类材料人力车二次运输的工程量，应按木质材料的体积以立方米计算；胶合板类的复合板材二次运输工程量应按板材面积以平方米计算。

### 9.2.4

散粒材料人力车二次运输子目中，水泥、石灰二次运输的工程量应按重量以吨计算；砂及碎石应按松散体积以立方米计算。

### 9.2.5

砌筑块材人力车二次运输的工程量应按块材的外形体积以立方米计算。

### 9.2.6

其他材料人力车二次运输子目中，板材类材料二次运输的工程量应按板材的面积以平方米计算；线条类材料二次运输的工程量应按线条长度以米计算。

### 9.2.7

机动翻斗车场内运输钢筋的工程量应按钢筋重量以吨计算。
"""


COSTS = {
    1: (56.23, 45.77, 37.51, 0, 0, 6.08, 2.18, 1.87, 6.75, 1.84),
    2: (10.15, 8.25, 6.76, 0, 0, 1.10, .39, .34, 1.22, .34),
    3: (61.85, 50.34, 41.26, 0, 0, 6.68, 2.40, 2.05, 7.43, 2.03),
    4: (9.90, 8.06, 6.61, 0, 0, 1.07, .38, .33, 1.19, .32),
    5: (71.13, 57.90, 47.45, 0, 0, 7.69, 2.76, 2.36, 8.54, 2.33),
    6: (8.87, 7.22, 5.92, 0, 0, .96, .34, .29, 1.07, .29),
    7: (123.67, 100.67, 82.51, 0, 0, 13.37, 4.79, 4.11, 14.85, 4.04),
    8: (33.40, 27.18, 22.28, 0, 0, 3.61, 1.29, 1.11, 4.01, 1.10),
}


SPECS = {
    1: ("圆（方）钢、钢管", "各种规格 / 运距L(m) / 0<L≤50", 252),
    2: ("圆（方）钢、钢管", "各种规格 / 运距L(m) / L>50 / 每增100以内", 252),
    3: ("工、槽、角、扁钢", "各种规格 / 运距L(m) / 0<L≤50", 252),
    4: ("工、槽、角、扁钢", "各种规格 / 运距L(m) / L>50 / 每增100以内", 252),
    5: ("成型钢筋", "运距L(m) / 0<L≤50", 253),
    6: ("成型钢筋", "运距L(m) / L>50 / 每增100以内", 253),
    7: ("金属窗", "各种规格 / 运距L(m) / 0<L≤50", 253),
    8: ("金属窗", "各种规格 / 运距L(m) / L>50 / 每增100以内", 253),
}


load_dotenv(".env")
conn = get_connection()
try:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM bs2024_chapters
            WHERE document_id=%s AND chapter_no=8
            ORDER BY id LIMIT 1
            """,
            (DOC,),
        )
        chapter8_id = cur.fetchone()[0]
        cur.execute(
            """
            UPDATE bs2024_chapters SET code='8',title='垂直运输工程',
              page_start=244,page_end=249,sort_order=8
            WHERE id=%s
            """,
            (chapter8_id,),
        )
        cur.execute(
            """
            SELECT id FROM bs2024_sections
            WHERE document_id=%s AND chapter_id=%s AND section_code='8.3'
            ORDER BY id LIMIT 1
            """,
            (DOC, chapter8_id),
        )
        section8_id = cur.fetchone()[0]
        cur.execute(
            "UPDATE bs2024_sections SET page_end=249 WHERE id=%s",
            (section8_id,),
        )

        cur.execute(
            """
            SELECT id FROM bs2024_item_groups
            WHERE document_id=%s AND group_code='8.3.4'
            ORDER BY id LIMIT 1
            """,
            (DOC,),
        )
        row = cur.fetchone()
        if row:
            group8_id = row[0]
            cur.execute(
                """
                UPDATE bs2024_item_groups SET section_id=%s,
                  group_name='施工电梯',page_start=249,page_end=249,sort_order=4
                WHERE id=%s
                """,
                (section8_id, group8_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO bs2024_item_groups
                  (document_id,section_id,group_code,group_name,page_start,page_end,sort_order)
                VALUES (%s,%s,'8.3.4','施工电梯',249,249,4)
                RETURNING id
                """,
                (DOC, section8_id),
            )
            group8_id = cur.fetchone()[0]

        cur.execute(
            """
            SELECT i.id FROM bs2024_items i
            JOIN bs2024_subitems s ON s.item_id=i.id
            WHERE s.document_id=%s AND s.subitem_code='010008-5'
            ORDER BY i.id LIMIT 1
            """,
            (DOC,),
        )
        row = cur.fetchone()
        work8 = "每台电梯每天完成全部工程所需要的垂直运输全部操作过程。"
        if row:
            item8_id = row[0]
            cur.execute(
                """
                UPDATE bs2024_items SET group_id=%s,item_no=1,item_name='施工电梯',
                  work_content=%s,unit=NULL,page_no=249,sort_order=1
                WHERE id=%s
                """,
                (group8_id, work8, item8_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO bs2024_items
                  (document_id,group_id,item_no,item_name,work_content,page_no,sort_order)
                VALUES (%s,%s,1,'施工电梯',%s,249,1)
                RETURNING id
                """,
                (DOC, group8_id, work8),
            )
            item8_id = cur.fetchone()[0]

        cur.execute(
            """
            UPDATE bs2024_subitems SET item_id=%s,subitem_name='施工电梯',
              variant_desc=NULL,unit='台·天',name_path_json=%s::jsonb,
              total_unit_price=709.34,unit_price=595.34,labor_cost=369.43,
              material_cost=137.71,machine_cost=0,management_fee=59.85,
              profit=28.35,safety_fee=24.29,statutory_fee=66.50,tax=23.21,
              page_no=249,confidence=1,sort_order=5
            WHERE document_id=%s AND subitem_code='010008-5'
            RETURNING id
            """,
            (item8_id, json.dumps(["施工电梯"], ensure_ascii=False), DOC),
        )
        subitem8_id = cur.fetchone()[0]
        cur.execute("DELETE FROM bs2024_resources WHERE subitem_id=%s", (subitem8_id,))
        for order, row in enumerate(
            (
                ("人工", "技工人工费", "元", 369.43, None),
                ("材料", "电", "kW·h", 167.940, .82),
                ("机械", "施工电梯租赁费", "台·天", 1, None),
            ),
            1,
        ):
            cur.execute(
                """
                INSERT INTO bs2024_resources
                  (document_id,subitem_id,resource_type,resource_name,unit,
                   quantity,ref_price,page_no,sort_order)
                VALUES (%s,%s,%s,%s,%s,%s,%s,249,%s)
                """,
                (DOC, subitem8_id, *row[:3], d(row[3]), d(row[4]), order),
            )

        cur.execute(
            """
            SELECT id FROM bs2024_chapters
            WHERE document_id=%s AND chapter_no=9
            ORDER BY id LIMIT 1
            """,
            (DOC,),
        )
        row = cur.fetchone()
        if row:
            chapter9_id = row[0]
            cur.execute(
                """
                UPDATE bs2024_chapters SET code='9',title='材料二次运输工程',
                  page_start=250,page_end=253,sort_order=9
                WHERE id=%s
                """,
                (chapter9_id,),
            )
        else:
            cur.execute(
                """
                INSERT INTO bs2024_chapters
                  (document_id,chapter_no,code,title,page_start,page_end,sort_order)
                VALUES (%s,9,'9','材料二次运输工程',250,253,9)
                RETURNING id
                """,
                (DOC,),
            )
            chapter9_id = cur.fetchone()[0]

        sections = {}
        for section_type, code, title, content, start, end, order in (
            ("intro", "9.1", "说明", INTRO_MD, 250, 250, 1),
            ("rules", "9.2", "工程量计算规则", RULES_MD, 251, 251, 2),
            ("items", "9.3", "子目构成表", None, 252, 253, 3),
        ):
            cur.execute(
                """
                SELECT id FROM bs2024_sections
                WHERE document_id=%s AND chapter_id=%s AND section_code=%s
                ORDER BY id LIMIT 1
                """,
                (DOC, chapter9_id, code),
            )
            row = cur.fetchone()
            if row:
                section_id = row[0]
                cur.execute(
                    """
                    UPDATE bs2024_sections SET section_type=%s,title=%s,
                      content_md=%s,page_start=%s,page_end=%s,sort_order=%s
                    WHERE id=%s
                    """,
                    (section_type, title, content, start, end, order, section_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_sections
                      (document_id,chapter_id,section_type,section_code,title,
                       content_md,page_start,page_end,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        DOC, chapter9_id, section_type, code, title,
                        content, start, end, order,
                    ),
                )
                section_id = cur.fetchone()[0]
            sections[code] = section_id

        cur.execute(
            """
            SELECT id FROM bs2024_item_groups
            WHERE document_id=%s AND group_code='9.3.1'
            ORDER BY id LIMIT 1
            """,
            (DOC,),
        )
        row = cur.fetchone()
        if row:
            group9_id = row[0]
            cur.execute(
                """
                UPDATE bs2024_item_groups SET section_id=%s,
                  group_name='金属材料人力车二次运输',
                  page_start=252,page_end=253,sort_order=1
                WHERE id=%s
                """,
                (sections["9.3"], group9_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO bs2024_item_groups
                  (document_id,section_id,group_code,group_name,page_start,page_end,sort_order)
                VALUES (%s,%s,'9.3.1','金属材料人力车二次运输',252,253,1)
                RETURNING id
                """,
                (DOC, sections["9.3"]),
            )
            group9_id = cur.fetchone()[0]

        cur.execute(
            """
            SELECT i.id FROM bs2024_items i
            JOIN bs2024_subitems s ON s.item_id=i.id
            WHERE s.document_id=%s AND s.subitem_code='010009-1'
            ORDER BY i.id LIMIT 1
            """,
            (DOC,),
        )
        row = cur.fetchone()
        work9 = "材料的装车、运输、卸车、堆放整理。"
        if row:
            item9_id = row[0]
            cur.execute(
                """
                UPDATE bs2024_items SET group_id=%s,item_no=1,
                  item_name='金属材料人力车二次运输',work_content=%s,
                  unit=NULL,page_no=252,sort_order=1
                WHERE id=%s
                """,
                (group9_id, work9, item9_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO bs2024_items
                  (document_id,group_id,item_no,item_name,work_content,page_no,sort_order)
                VALUES (%s,%s,1,'金属材料人力车二次运输',%s,252,1)
                RETURNING id
                """,
                (DOC, group9_id, work9),
            )
            item9_id = cur.fetchone()[0]

        for number in range(1, 9):
            subitem_name, variant, page = SPECS[number]
            path = ["金属材料人力车二次运输", subitem_name]
            path.extend(variant.split(" / "))
            cur.execute(
                """
                UPDATE bs2024_subitems SET item_id=%s,subitem_name=%s,
                  variant_desc=%s,unit='t',name_path_json=%s::jsonb,
                  total_unit_price=%s,unit_price=%s,labor_cost=%s,
                  material_cost=%s,machine_cost=%s,management_fee=%s,
                  profit=%s,safety_fee=%s,statutory_fee=%s,tax=%s,
                  page_no=%s,confidence=1,sort_order=%s
                WHERE document_id=%s AND subitem_code=%s
                RETURNING id
                """,
                (
                    item9_id, subitem_name, variant,
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
            UPDATE bs2024_pages SET chapter_no=8,chapter_title='垂直运输工程',
              section_code='8.3',section_type='items'
            WHERE document_id=%s AND page_no=249
            """,
            (DOC,),
        )
        cur.execute(
            """
            UPDATE bs2024_pages SET chapter_no=9,chapter_title='材料二次运输工程',
              section_code=CASE
                WHEN page_no=250 THEN '9.1'
                WHEN page_no=251 THEN '9.2'
                ELSE '9.3'
              END,
              section_type=CASE
                WHEN page_no=250 THEN 'intro'
                WHEN page_no=251 THEN 'rules'
                ELSE 'items'
              END
            WHERE document_id=%s AND page_no BETWEEN 250 AND 253
            """,
            (DOC,),
        )
        cur.execute(
            """
            DELETE FROM bs2024_sections
            WHERE document_id=%s AND section_code LIKE '9.%%' AND chapter_id<>%s
            """,
            (DOC, chapter9_id),
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

print("Corrected Chapter 8 page 249 and Chapter 9 pages 250-253.")
