from decimal import Decimal
import json

from dotenv import load_dotenv

from db.connection import get_connection


DOC = 25


def d(value):
    return None if value is None else Decimal(str(value))


INTRO_MD = """## 8.1 说明

### 8.1.1

本章垂直运输子目按垂直运输机械类型划分，包括汽车式起重机、履带式起重机、塔式起重机、施工电梯。

### 8.1.2

本章子目已考虑正常使用期间内所需机上操作人员以及配合人工、电力或燃油消耗等费用；未包括垂直运输机械的租赁费、场外运输、安拆、轨道铺拆等费用，且塔吊基础、电梯基础、塔吊及电梯与建筑物连接的费用应另行计算。

### 8.1.3

汽车式起重机人工费已考虑1个高级技工和1个技工，履带式起重机和塔式起重机子目人工费已考虑1个高级技工和2个技工，施工电梯子目人工费已考虑2个技工。

### 8.1.4

本章子目中人工费按一台垂直运输机械一天工作8小时考虑。若实际工作时间不满8小时，相应人工费应根据经审定的施工方案进行调整；实际工作时间不足4小时，按4小时计算。

### 8.1.5

本章子目中已综合取定一台机械工作8小时所消耗的电力或燃油费用。若实际消耗的电力、燃油费用与子目不同时，应按实际调整。

### 8.1.6

本章子目中未列出相关垂直运输机械的台班消耗量及台班价格，计算垂直运输费时，应根据经审定的施工组织设计和施工技术措施方案，综合确定垂直运输机械的型号、臂长、高度以及台班数量，并根据相应的市场租赁价格计算每台·天的台班租赁费用。结算时，应按实际使用的垂直运输机械的型号、臂长、高度以及台班数量，进行垂直运输机械数量及租赁费用的调整。

### 8.1.7

钢结构工程施工中如采用整体顶升系统的，应按经审定的施工组织设计和专项施工技术措施方案另行计算。
"""


RULES_MD = """## 8.2 工程量计算规则

### 8.2.1

汽车式起重机、履带式起重机、塔式起重机、施工电梯的工程量应按垂直运输机械台数与使用天数的乘积，以“台·天”计算。

### 8.2.2

同一项目中不同型号的垂直运输机械的使用天数、租赁价格不同时，应分别计算。

### 8.2.3

垂直运输机械（汽车式起重机、履带式起重机、塔式起重机、施工电梯）的台数按经审定的施工组织设计文件计算；无施工组织设计文件或者施工组织设计文件中未明确的，应根据项目需求和进度安排确定相应垂直运输机械的台数，结算时，应按实际使用台数调整。

### 8.2.4

垂直运输机械（汽车式起重机、履带式起重机、塔式起重机、施工电梯）的使用天数应按经审定的施工组织设计文件计算；无施工组织设计文件或者施工组织设计文件中未明确的，汽车式起重机、履带式起重机、塔式起重机、施工电梯等垂直运输机械的使用天数可根据合同工期、项目实际情况等综合考虑。结算时，应按各垂直运输机械的实际使用天数调整。
"""


costs = {
    1: (1181.04, 1022.13, 436.51, 466.24, 0, 70.71, 48.67, 41.70, 78.57, 38.64),
    2: (2720.87, 2421.24, 621.23, 1584.07, 0, 100.64, 115.30, 98.79, 111.82, 89.02),
    3: (1205.02, 1012.47, 621.23, 242.39, 0, 100.64, 48.21, 41.31, 111.82, 39.42),
    4: (3427.00, 3077.50, 621.23, 2209.08, 0, 100.64, 146.55, 125.56, 111.82, 112.12),
}

specs = {
    1: ("8.3.1", "汽车式起重机", "汽车式起重机", None, 246),
    2: ("8.3.2", "履带式起重机", "履带式起重机", None, 247),
    3: ("8.3.3", "塔式起重机", "塔式起重机", None, 248),
    4: ("8.3.3", "塔式起重机", "动臂式塔吊", None, 248),
}

resources = {
    1: [
        ("人工", "技工人工费", "元", 184.71, None),
        ("人工", "高级技工人工费", "元", 251.80, None),
        ("材料", "柴油", "kg", 51.920, 8.98),
        ("机械", "起重机租赁费", "台·天", 1, None),
    ],
    2: [
        ("人工", "技工人工费", "元", 369.43, None),
        ("人工", "高级技工人工费", "元", 251.80, None),
        ("材料", "柴油", "kg", 176.400, 8.98),
        ("机械", "起重机租赁费", "台·天", 1, None),
    ],
    3: [
        ("人工", "技工人工费", "元", 369.43, None),
        ("人工", "高级技工人工费", "元", 251.80, None),
        ("材料", "电", "kW·h", 295.600, .82),
        ("机械", "起重机租赁费", "台·天", 1, None),
    ],
    4: [
        ("人工", "技工人工费", "元", 369.43, None),
        ("人工", "高级技工人工费", "元", 251.80, None),
        ("材料", "柴油", "kg", 246.000, 8.98),
        ("机械", "起重机租赁费", "台·天", 1, None),
    ],
}


load_dotenv(".env")
conn = get_connection()
try:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM bs2024_chapters WHERE document_id=%s AND chapter_no=8 ORDER BY id LIMIT 1",
            (DOC,),
        )
        row = cur.fetchone()
        if row:
            chapter_id = row[0]
            cur.execute(
                """
                UPDATE bs2024_chapters SET code='8',title='垂直运输工程',
                  page_start=244,page_end=248,sort_order=8 WHERE id=%s
                """,
                (chapter_id,),
            )
        else:
            cur.execute(
                """
                INSERT INTO bs2024_chapters
                  (document_id,chapter_no,code,title,page_start,page_end,sort_order)
                VALUES (%s,8,'8','垂直运输工程',244,248,8) RETURNING id
                """,
                (DOC,),
            )
            chapter_id = cur.fetchone()[0]

        sections = {}
        for section_type, code, title, content, start, end, order in (
            ("intro", "8.1", "说明", INTRO_MD, 244, 244, 1),
            ("rules", "8.2", "工程量计算规则", RULES_MD, 245, 245, 2),
            ("items", "8.3", "子目构成表", None, 246, 248, 3),
        ):
            cur.execute(
                """
                SELECT id FROM bs2024_sections
                WHERE document_id=%s AND chapter_id=%s AND section_code=%s
                ORDER BY id LIMIT 1
                """,
                (DOC, chapter_id, code),
            )
            row = cur.fetchone()
            if row:
                sid = row[0]
                cur.execute(
                    """
                    UPDATE bs2024_sections SET section_type=%s,title=%s,content_md=%s,
                      page_start=%s,page_end=%s,sort_order=%s WHERE id=%s
                    """,
                    (section_type, title, content, start, end, order, sid),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_sections
                      (document_id,chapter_id,section_type,section_code,title,content_md,
                       page_start,page_end,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (DOC, chapter_id, section_type, code, title, content, start, end, order),
                )
                sid = cur.fetchone()[0]
            sections[code] = sid

        group_ids = {}
        for code, name, page, order in (
            ("8.3.1", "汽车式起重机", 246, 1),
            ("8.3.2", "履带式起重机", 247, 2),
            ("8.3.3", "塔式起重机", 248, 3),
        ):
            cur.execute(
                "SELECT id FROM bs2024_item_groups WHERE document_id=%s AND group_code=%s ORDER BY id LIMIT 1",
                (DOC, code),
            )
            row = cur.fetchone()
            if row:
                gid = row[0]
                cur.execute(
                    """
                    UPDATE bs2024_item_groups SET section_id=%s,group_name=%s,
                      page_start=%s,page_end=%s,sort_order=%s WHERE id=%s
                    """,
                    (sections["8.3"], name, page, page, order, gid),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_item_groups
                      (document_id,section_id,group_code,group_name,page_start,page_end,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (DOC, sections["8.3"], code, name, page, page, order),
                )
                gid = cur.fetchone()[0]
            group_ids[code] = gid

        item_ids = {}
        for code, group_name, page, order in (
            ("8.3.1", "汽车式起重机", 246, 1),
            ("8.3.2", "履带式起重机", 247, 1),
            ("8.3.3", "塔式起重机", 248, 1),
        ):
            first_code = {"8.3.1": "010008-1", "8.3.2": "010008-2", "8.3.3": "010008-3"}[code]
            cur.execute(
                """
                SELECT i.id FROM bs2024_items i JOIN bs2024_subitems s ON s.item_id=i.id
                WHERE s.document_id=%s AND s.subitem_code=%s ORDER BY i.id LIMIT 1
                """,
                (DOC, first_code),
            )
            row = cur.fetchone()
            work = "每台起重机每天完成全部工程所需要的垂直运输全部操作过程。"
            if row:
                iid = row[0]
                cur.execute(
                    """
                    UPDATE bs2024_items SET group_id=%s,item_no=1,item_name=%s,
                      work_content=%s,unit=NULL,page_no=%s,sort_order=%s WHERE id=%s
                    """,
                    (group_ids[code], group_name, work, page, order, iid),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_items
                      (document_id,group_id,item_no,item_name,work_content,page_no,sort_order)
                    VALUES (%s,%s,1,%s,%s,%s,%s) RETURNING id
                    """,
                    (DOC, group_ids[code], group_name, work, page, order),
                )
                iid = cur.fetchone()[0]
            item_ids[code] = iid

        for number in range(1, 5):
            group_code, group_name, subitem_name, variant, page = specs[number]
            path = [group_name, subitem_name]
            cur.execute(
                """
                UPDATE bs2024_subitems SET item_id=%s,subitem_name=%s,variant_desc=%s,
                  unit='台·天',name_path_json=%s::jsonb,total_unit_price=%s,
                  unit_price=%s,labor_cost=%s,material_cost=%s,machine_cost=%s,
                  management_fee=%s,profit=%s,safety_fee=%s,statutory_fee=%s,tax=%s,
                  page_no=%s,confidence=1,sort_order=%s
                WHERE document_id=%s AND subitem_code=%s RETURNING id
                """,
                (
                    item_ids[group_code], subitem_name, variant,
                    json.dumps(path, ensure_ascii=False),
                    *[d(value) for value in costs[number]],
                    page, number, DOC, f"010008-{number}",
                ),
            )
            sid = cur.fetchone()[0]
            cur.execute("DELETE FROM bs2024_resources WHERE subitem_id=%s", (sid,))
            for order, resource in enumerate(resources[number], 1):
                cur.execute(
                    """
                    INSERT INTO bs2024_resources
                      (document_id,subitem_id,resource_type,resource_name,unit,
                       quantity,ref_price,page_no,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (DOC, sid, *resource[:3], d(resource[3]), d(resource[4]), page, order),
                )

        cur.execute(
            """
            UPDATE bs2024_pages SET chapter_no=8,chapter_title='垂直运输工程'
            WHERE document_id=%s AND page_no BETWEEN 244 AND 248
            """,
            (DOC,),
        )
        cur.execute(
            """
            DELETE FROM bs2024_sections
            WHERE document_id=%s AND section_code LIKE '8.%%' AND chapter_id<>%s
            """,
            (DOC, chapter_id),
        )
        cur.execute(
            "DELETE FROM bs2024_items i WHERE i.document_id=%s AND NOT EXISTS (SELECT 1 FROM bs2024_subitems s WHERE s.item_id=i.id)",
            (DOC,),
        )
        cur.execute(
            "DELETE FROM bs2024_item_groups g WHERE g.document_id=%s AND NOT EXISTS (SELECT 1 FROM bs2024_items i WHERE i.group_id=g.id)",
            (DOC,),
        )
    conn.commit()
finally:
    conn.close()

print("Corrected Chapter 8 pages 244-248 and subitems 010008-1 through 010008-4.")
