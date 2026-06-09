from decimal import Decimal
import json

from dotenv import load_dotenv

from db.connection import get_connection


DOC = 25


def d(value):
    return None if value is None else Decimal(str(value))


costs = {
    34: (130.12, 116.25, 27.03, 79.30, 0, 4.38, 5.54, 4.74, 4.87, 4.26),
    35: (155.72, 137.93, 39.21, 85.80, 0, 6.35, 6.57, 5.63, 7.06, 5.10),
    36: (187.72, 164.92, 55.18, 92.95, 0, 8.94, 7.85, 6.73, 9.93, 6.14),
    37: (12980.44, 10566.49, 8656.45, 4.53, 0, 1402.34, 503.17, 431.11, 1558.16, 424.68),
    38: (1442.28, 1174.06, 961.83, .50, 0, 155.82, 55.91, 47.90, 173.13, 47.19),
    39: (15320.81, 12471.39, 10218.49, 3.62, 0, 1655.40, 593.88, 508.83, 1839.33, 501.26),
    40: (1702.32, 1385.71, 1135.39, .40, 0, 183.93, 65.99, 56.54, 204.37, 55.70),
    41: (6010.23, 5254.58, 1914.54, 750.12, 1997.19, 342.51, 250.22, 214.39, 344.62, 196.64),
    42: (762.74, 660.96, 276.99, 82.14, 221.89, 48.47, 31.47, 26.97, 49.86, 24.95),
    43: (4968.38, 4362.53, 1473.91, 412.56, 1997.19, 271.13, 207.74, 177.99, 265.30, 162.56),
    44: (640.34, 556.50, 223.18, 45.18, 221.89, 39.75, 26.50, 22.71, 40.17, 20.96),
    45: (928.51, 755.80, 619.46, 0, 0, 100.35, 35.99, 30.84, 111.50, 30.37),
    46: (1580.17, 1286.23, 1054.20, 0, 0, 170.78, 61.25, 52.48, 189.76, 51.70),
    47: (293.92, 241.21, 184.71, 15.09, 0, 29.92, 11.49, 9.84, 33.25, 9.62),
}

specs = {
    34: (2, "承插型盘扣式钢管外脚手架", "承插型盘扣式钢管单排脚手架", "使用 / 搭设高度H(m) / 0<H≤6", "100m²·10天", 230),
    35: (2, "承插型盘扣式钢管外脚手架", "承插型盘扣式钢管单排脚手架", "使用 / 搭设高度H(m) / 6<H≤14", "100m²·10天", 230),
    36: (2, "承插型盘扣式钢管外脚手架", "承插型盘扣式钢管单排脚手架", "使用 / 搭设高度H(m) / 14<H≤24", "100m²·10天", 230),
    37: (3, "电动整体提升式脚手架", "电动整体提升式脚手架", "搭拆 / 全钢结构 / 架高H(m) / H=13.5", "10m", 231),
    38: (3, "电动整体提升式脚手架", "电动整体提升式脚手架", "搭拆 / 全钢结构 / 架高H(m) / 每增1.5", "10m", 231),
    39: (3, "电动整体提升式脚手架", "电动整体提升式脚手架", "搭拆 / 钢管组合 / 架高H(m) / H=13.5", "10m", 231),
    40: (3, "电动整体提升式脚手架", "电动整体提升式脚手架", "搭拆 / 钢管组合 / 架高H(m) / 每增1.5", "10m", 231),
    41: (3, "电动整体提升式脚手架", "电动整体提升式脚手架", "使用 / 全钢结构 / 架高H(m) / H=13.5", "10m·10天", 232),
    42: (3, "电动整体提升式脚手架", "电动整体提升式脚手架", "使用 / 全钢结构 / 架高H(m) / 每增1.5", "10m·10天", 232),
    43: (3, "电动整体提升式脚手架", "电动整体提升式脚手架", "使用 / 钢管组合 / 架高H(m) / H=13.5", "10m·10天", 232),
    44: (3, "电动整体提升式脚手架", "电动整体提升式脚手架", "使用 / 钢管组合 / 架高H(m) / 每增1.5", "10m·10天", 232),
    45: (4, "电动吊篮式脚手架搭拆与使用", "电动吊篮式脚手架", "搭拆 / 作业高度H(m) / 0<H≤200.5", "台·次", 233),
    46: (4, "电动吊篮式脚手架搭拆与使用", "电动吊篮式脚手架", "搭拆 / 作业高度H(m) / 200.5<H≤300.5", "台·次", 233),
    47: (4, "电动吊篮式脚手架搭拆与使用", "电动吊篮式脚手架", "使用", "台·天", 234),
}


def resources(number):
    if number in (34, 35, 36):
        i = number - 34
        return [
            ("人工", "普通人工费", "元", (8.20, 9.84, 11.80)[i], None),
            ("人工", "技工人工费", "元", (18.83, 29.37, 43.38)[i], None),
            ("材料", "承插型盘扣式钢管脚手架（成套）（租赁10天）", "kg", (1277.078, 1381.748, 1496.886)[i], .06),
            ("材料", "其他材料费", "%", 3.5, 1),
        ]
    if 37 <= number <= 40:
        i = number - 37
        return [
            ("人工", "普通人工费", "元", (2138.04, 237.56, 2483.51, 275.95)[i], None),
            ("人工", "技工人工费", "元", (6518.41, 724.27, 7734.98, 859.44)[i], None),
            ("材料", "润滑油", "kg", (1.303, .145, 1.042, .116)[i], 3.36),
            ("材料", "其他材料费", "%", (3.5, 2, 3.5, 2)[i], 1),
        ]
    if 41 <= number <= 44:
        i = number - 41
        quantities = (31.250, 3.472, 31.250, 3.472)
        return [
            ("人工", "普通人工费", "元", (303.74, 105.39, 308.49, 79.06)[i], None),
            ("人工", "技工人工费", "元", (1610.80, 171.60, 1165.42, 144.12)[i], None),
            ("材料", "脚手架型钢架体（租赁10天）", "kg", (1858.333, 206.481, 1022.083, 113.565)[i], .39),
            ("材料", "其他材料费", "%", (3.5, 2, 3.5, 2)[i], 1),
            ("机械", "脚手架提升系统", "台班", quantities[i], 32.95),
            ("机械", "脚手架电气控制系统", "台班", quantities[i], 30.96),
        ]
    if number in (45, 46):
        i = number - 45
        return [
            ("人工", "普通人工费", "元", (369.43, 554.14)[i], None),
            ("人工", "技工人工费", "元", (250.03, 500.06)[i], None),
        ]
    return [
        ("人工", "技工人工费", "元", 184.71, None),
        ("材料", "电", "kW·h", 18.400, .82),
        ("机械", "电动吊篮租赁费", "台·天", 1, None),
    ]


load_dotenv(".env")
conn = get_connection()
try:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM bs2024_item_groups WHERE document_id=%s AND group_code='7.3.1' ORDER BY id LIMIT 1",
            (DOC,),
        )
        group_id = cur.fetchone()[0]

        item_ids = {}
        for item_no, item_name, page, work in (
            (2, "承插型盘扣式钢管外脚手架", 225, "安底座、立杆、接杆及上部挑出承托、连墙件、型钢支撑、卸料平台等搭设和拆除全过程，脚手架拆除后的材料整理、刷油、堆放及场内运输。"),
            (3, "电动整体提升式脚手架", 231, "架体、提升系统和电气控制系统的安装、拆卸、场内运输、运行调试、提升使用、检查与维护。"),
            (4, "电动吊篮式脚手架搭拆与使用", 233, "电动吊篮安装、调整、拆卸、安拆前后的场内运输堆放及升降使用。"),
        ):
            cur.execute(
                """
                SELECT i.id FROM bs2024_items i JOIN bs2024_subitems s ON s.item_id=i.id
                WHERE s.document_id=%s AND s.subitem_code=%s ORDER BY i.id LIMIT 1
                """,
                (DOC, {2: "010007-19", 3: "010007-37", 4: "010007-45"}[item_no]),
            )
            row = cur.fetchone()
            if row:
                item_id = row[0]
                cur.execute(
                    """
                    UPDATE bs2024_items SET group_id=%s,item_no=%s,item_name=%s,
                      work_content=%s,unit=NULL,page_no=%s,sort_order=%s WHERE id=%s
                    """,
                    (group_id, item_no, item_name, work, page, item_no, item_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_items
                      (document_id,group_id,item_no,item_name,work_content,page_no,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (DOC, group_id, item_no, item_name, work, page, item_no),
                )
                item_id = cur.fetchone()[0]
            item_ids[item_no] = item_id

        for number in range(34, 48):
            item_no, item_name, subitem_name, variant, unit, page = specs[number]
            path = ["外脚手架", item_name, subitem_name]
            if variant:
                path.extend(variant.split(" / "))
            cur.execute(
                """
                UPDATE bs2024_subitems SET item_id=%s,subitem_name=%s,variant_desc=%s,
                  unit=%s,name_path_json=%s::jsonb,total_unit_price=%s,unit_price=%s,
                  labor_cost=%s,material_cost=%s,machine_cost=%s,management_fee=%s,
                  profit=%s,safety_fee=%s,statutory_fee=%s,tax=%s,page_no=%s,
                  confidence=1,sort_order=%s
                WHERE document_id=%s AND subitem_code=%s RETURNING id
                """,
                (
                    item_ids[item_no], subitem_name, variant, unit,
                    json.dumps(path, ensure_ascii=False),
                    *[d(value) for value in costs[number]],
                    page, number, DOC, f"010007-{number}",
                ),
            )
            subitem_id = cur.fetchone()[0]
            cur.execute("DELETE FROM bs2024_resources WHERE subitem_id=%s", (subitem_id,))
            for order, resource in enumerate(resources(number), 1):
                cur.execute(
                    """
                    INSERT INTO bs2024_resources
                      (document_id,subitem_id,resource_type,resource_name,unit,
                       quantity,ref_price,page_no,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (DOC, subitem_id, *resource[:3], d(resource[3]), d(resource[4]), page, order),
                )

        cur.execute(
            "UPDATE bs2024_item_groups SET page_end=234 WHERE document_id=%s AND id=%s",
            (DOC, group_id),
        )
        cur.execute(
            """
            UPDATE bs2024_pages SET chapter_no=7,chapter_title='脚手架工程',
              section_code='7.3',section_type='items'
            WHERE document_id=%s AND page_no BETWEEN 230 AND 234
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

print("Corrected Chapter 7 subitems 010007-34 through 010007-47.")
