from decimal import Decimal
import json

from dotenv import load_dotenv

from db.connection import get_connection


DOC = 25


def d(value):
    return None if value is None else Decimal(str(value))


def r(kind, name, unit, quantity, price):
    return kind, name, unit, d(quantity), d(price)


costs = {
    53: (12760.83, 10686.41, 6782.85, 2290.50, 5.27, 1098.91, 508.88, 436.01, 1220.91, 417.50),
    54: (12467.39, 10366.06, 7058.25, 1665.40, 5.27, 1143.52, 493.62, 422.94, 1270.49, 407.90),
    55: (12169.08, 10140.10, 6761.79, 1799.77, 0.27, 1095.41, 482.86, 413.72, 1217.12, 398.14),
    56: (11909.43, 9867.91, 6940.33, 1333.07, 0.27, 1124.34, 469.90, 402.61, 1249.26, 389.65),
    57: (17620.27, 14855.96, 8787.24, 3910.13, 27.19, 1423.97, 707.43, 606.12, 1581.70, 576.49),
    58: (1661.40, 1352.36, 1108.40, 0, 0, 179.56, 64.40, 55.18, 199.51, 54.35),
    59: (1827.55, 1487.60, 1219.24, 0, 0, 197.52, 70.84, 60.69, 219.46, 59.80),
    60: (2284.45, 1859.51, 1524.06, 0, 0, 246.90, 88.55, 75.87, 274.33, 74.74),
    61: (2512.88, 2045.45, 1676.46, 0, 0, 271.59, 97.40, 83.45, 301.76, 82.22),
    62: (87.92, 71.56, 58.65, 0, 0, 9.50, 3.41, 2.92, 10.56, 2.88),
    63: (3233.11, 2631.71, 2156.96, 0, 0, 349.43, 125.32, 107.37, 388.25, 105.78),
    64: (58.48, 54.34, 0, 51.75, 0, 0, 2.59, 2.22, 0, 1.92),
    65: (1219.21, 1025.46, 622.32, 253.49, 0, 100.82, 48.83, 41.84, 112.02, 39.89),
}

defs = {
    53: ("其他构件模板", "独立过梁", "木模板", "100m²", 196),
    54: ("其他构件模板", "独立过梁", "钢模板", "100m²", 196),
    55: ("其他构件模板", "电缆沟、地沟", "木模板", "100m²", 197),
    56: ("其他构件模板", "挡水坎", "木模板", "100m²", 197),
    57: ("其他构件模板", "小型构件", "木模板", "100m²", 197),
    58: ("模板支撑架", "梁、板模板支撑架 / 搭拆 / 支模高度H(m)", "0<H≤3.6", "100m³", 198),
    59: ("模板支撑架", "梁、板模板支撑架 / 搭拆 / 支模高度H(m)", "3.6<H≤5.0", "100m³", 198),
    60: ("模板支撑架", "梁、板模板支撑架 / 搭拆 / 支模高度H(m)", "5<H≤8.0", "100m³", 198),
    61: ("模板支撑架", "梁、板模板支撑架 / 搭拆 / 支模高度H(m)", "8<H≤10", "100m³", 199),
    62: ("模板支撑架", "梁、板模板支撑架 / 搭拆 / 支模高度H(m)", "H>10 / 每增1m", "100m³", 199),
    63: ("模板支撑架", "楼梯模板支撑架", "搭拆", "100m²", 199),
    64: ("模板支撑架", "模板支撑架", "使用", "t·10天", 200),
    65: ("水平安全兜网", "水平安全兜网", None, "100m²", 201),
}

ordinary = {
    53: 858.24, 54: 983.95, 55: 682.27, 56: 659.10, 57: 1124.18,
    58: 222.52, 59: 244.77, 60: 305.97, 61: 336.57, 62: 11.78,
    63: 320.44, 64: None, 65: 137.64,
}
skilled = {
    53: 5924.61, 54: 6074.30, 55: 6079.52, 56: 6281.23, 57: 7663.06,
    58: 885.88, 59: 974.47, 60: 1218.09, 61: 1339.89, 62: 46.87,
    63: 1836.52, 64: None, 65: 484.68,
}

red = lambda q: r("材料", "涂胶建筑模板（红板）1 830×915×15", "张", q, 54)
steel = lambda q: r("材料", "钢模板", "kg", q, 6.79)
support = lambda q: r("材料", "支撑钢管及扣件（模板支撑专用）", "kg", q, 5)
wood = lambda q: r("材料", "松杂枋板材（周转材）", "m³", q, 2016)
wire = lambda q: r("材料", "镀锌铁丝（综合）", "kg", q, 6.05)
clip = lambda q: r("材料", "零星卡具", "kg", q, 6.5)
nail = lambda q: r("材料", "铁钉（综合）", "kg", q, 6.37)
release = lambda q: r("材料", "脱模剂", "kg", q, 8.4)
other = lambda q: r("材料", "其他材料费", "%", q, 1)
saw = lambda q: r("机械", "木工圆锯机 直径D(mm) D=500", "台班", q, 30.14)

resources = {
    53: [red(20.902), wood(.436), nail(24.160), release(10), other(2), saw(.175)],
    54: [wood(.436), nail(1.528), release(10), steel(73.800), wire(12.040), clip(12.020), other(2.5), saw(.175)],
    55: [red(20.902), support(19.587), wood(.090), wire(24.490), clip(1.510), nail(17.960), release(10), other(2), saw(.009)],
    56: [red(20.902), wood(.045), nail(.550), release(10), other(2), saw(.009)],
    57: [red(31.354), wood(1.005), nail(4.750), release(10), other(2), saw(.902)],
    58: [],
    59: [],
    60: [],
    61: [],
    62: [],
    63: [],
    64: [r("材料", "承插型盘扣式钢管支架（租赁10天）", "kg", 1000, 0.05), other(3.5)],
    65: [r("材料", "安全兜网", "m²", 35.330, 7), other(2.5)],
}

items = {
    "其他构件模板": (8, 194, "模板及支架制作、安装、拆除、整理堆放、运输，清理模板粘结物及模内杂物，刷隔离剂，封堵孔洞、修补孔眼等。"),
    "模板支撑架": (9, 198, "安底座、立杆、接杆及上部挑出承托等的搭设全部过程，施工期间的加固维修和更新换料，拆除后的材料整理、刷油、绑扎、堆放及场内运输。"),
    "水平安全兜网": (10, 201, "材料传递、安装与绑扎、拆卸、整理、堆放及场内运输，施工期间的加固维修及更新。"),
}


load_dotenv(".env")
conn = get_connection()
try:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT g.id FROM bs2024_item_groups g
            JOIN bs2024_sections s ON s.id=g.section_id
            JOIN bs2024_chapters c ON c.id=s.chapter_id
            WHERE c.document_id=%s AND c.chapter_no=6 AND g.group_code='6.3.1'
            ORDER BY g.id LIMIT 1
            """,
            (DOC,),
        )
        group_id = cur.fetchone()[0]
        cur.execute("UPDATE bs2024_item_groups SET page_end=201 WHERE id=%s", (group_id,))

        item_ids = {}
        for item_name, (item_no, page_no, work) in items.items():
            cur.execute(
                """
                SELECT i.id FROM bs2024_items i
                WHERE i.document_id=%s AND i.group_id=%s AND i.item_no=%s
                ORDER BY i.id LIMIT 1
                """,
                (DOC, group_id, item_no),
            )
            row = cur.fetchone()
            if row:
                item_id = row[0]
                cur.execute(
                    """
                    UPDATE bs2024_items SET group_id=%s,item_no=%s,item_name=%s,
                      work_content=%s,page_no=%s,sort_order=%s WHERE id=%s
                    """,
                    (group_id, item_no, item_name, work, page_no, item_no, item_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_items
                      (document_id,group_id,item_no,item_name,work_content,page_no,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (DOC, group_id, item_no, item_name, work, page_no, item_no),
                )
                item_id = cur.fetchone()[0]
            item_ids[item_name] = item_id

        for number in range(53, 66):
            item_name, sub_name, variant, unit, page = defs[number]
            path = ["现浇混凝土建筑物模板", item_name, *sub_name.split(" / ")]
            if variant:
                path.extend(variant.split(" / "))
            cur.execute(
                """
                INSERT INTO bs2024_subitems
                  (document_id,item_id,subitem_code,subitem_name,variant_desc,unit,
                   name_path_json,total_unit_price,unit_price,labor_cost,material_cost,
                   machine_cost,management_fee,profit,safety_fee,statutory_fee,tax,
                   page_no,confidence,sort_order)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s)
                ON CONFLICT (document_id,subitem_code) DO UPDATE SET
                  item_id=EXCLUDED.item_id,subitem_name=EXCLUDED.subitem_name,
                  variant_desc=EXCLUDED.variant_desc,unit=EXCLUDED.unit,
                  name_path_json=EXCLUDED.name_path_json,
                  total_unit_price=EXCLUDED.total_unit_price,unit_price=EXCLUDED.unit_price,
                  labor_cost=EXCLUDED.labor_cost,material_cost=EXCLUDED.material_cost,
                  machine_cost=EXCLUDED.machine_cost,management_fee=EXCLUDED.management_fee,
                  profit=EXCLUDED.profit,safety_fee=EXCLUDED.safety_fee,
                  statutory_fee=EXCLUDED.statutory_fee,tax=EXCLUDED.tax,
                  page_no=EXCLUDED.page_no,confidence=1,sort_order=EXCLUDED.sort_order
                RETURNING id
                """,
                (DOC, item_ids[item_name], f"010006-{number}", sub_name, variant, unit,
                 json.dumps(path, ensure_ascii=False), *[d(v) for v in costs[number]],
                 page, number),
            )
            sid = cur.fetchone()[0]
            cur.execute("DELETE FROM bs2024_resources WHERE subitem_id=%s", (sid,))
            rows = []
            if ordinary[number] is not None:
                rows.append(r("人工", "普通人工费", "元", ordinary[number], None))
            if skilled[number] is not None:
                rows.append(r("人工", "技工人工费", "元", skilled[number], None))
            rows.extend(resources[number])
            for order, row in enumerate(rows, 1):
                cur.execute(
                    """
                    INSERT INTO bs2024_resources
                      (document_id,subitem_id,resource_type,resource_name,unit,
                       quantity,ref_price,page_no,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (DOC, sid, *row, page, order),
                )

        cur.execute(
            "UPDATE bs2024_pages SET chapter_no=6,chapter_title='模板工程' "
            "WHERE document_id=%s AND page_no BETWEEN 196 AND 201",
            (DOC,),
        )
        cur.execute(
            """
            DELETE FROM bs2024_items i
            WHERE i.document_id=%s AND i.group_id=%s
              AND NOT EXISTS (SELECT 1 FROM bs2024_subitems s WHERE s.item_id=i.id)
            """,
            (DOC, group_id),
        )
    conn.commit()
finally:
    conn.close()

print("Corrected Chapter 6 subitems 010006-53 through 010006-65.")
