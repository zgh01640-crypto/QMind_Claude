from decimal import Decimal
import json

from dotenv import load_dotenv

from db.connection import get_connection


DOC = 25


def d(value):
    return None if value is None else Decimal(str(value))


costs = {
    48: (2117.73, 1748.41, 1270.58, 188.74, 0, 205.83, 83.26, 71.34, 228.70, 69.28),
    49: (638.11, 519.91, 422.84, 3.81, 0, 68.50, 24.76, 21.21, 76.11, 20.88),
    50: (1854.98, 1523.70, 1157.87, 105.70, 0, 187.57, 72.56, 62.17, 208.42, 60.69),
    51: (573.12, 466.91, 380.05, 3.06, 0, 61.57, 22.23, 19.05, 68.41, 18.75),
    52: (164.77, 139.94, 76.26, 44.67, 0, 12.35, 6.66, 5.71, 13.73, 5.39),
    53: (235.15, 199.17, 111.99, 59.56, 0, 18.14, 9.48, 8.13, 20.16, 7.69),
    54: (5181.66, 4387.22, 2477.27, 1299.71, 0, 401.32, 208.92, 179.00, 445.91, 169.53),
    55: (671.11, 548.67, 433.90, 18.35, 0, 70.29, 26.13, 22.39, 78.10, 21.95),
    56: (592.44, 483.60, 387.33, 10.49, 0, 62.75, 23.03, 19.73, 69.72, 19.39),
    57: (234.86, 191.49, 154.87, 2.41, 0, 25.09, 9.12, 7.81, 27.88, 7.68),
    58: (541.96, 442.55, 353.42, 10.81, 0, 57.25, 21.07, 18.06, 63.62, 17.73),
    59: (5665.06, 4733.55, 3072.37, 938.05, 0, 497.72, 225.41, 193.13, 553.03, 185.35),
    60: (8007.35, 6741.91, 4046.60, 1718.72, 0, 655.55, 321.04, 275.07, 728.39, 261.98),
    61: (9823.95, 8278.24, 4925.23, 2160.92, 0, 797.89, 394.20, 337.75, 886.54, 321.42),
    62: (13374.58, 11270.00, 6706.55, 2940.32, 0, 1086.46, 536.67, 459.82, 1207.18, 437.58),
}

specs = {
    48: ("7.3.2", "里脚手架", "民用建筑 / 基本层H(m) / H=3.6", "100m²", 235),
    49: ("7.3.2", "里脚手架", "民用建筑 / 每增1.2", "100m²", 235),
    50: ("7.3.2", "里脚手架", "工业建筑 / 基本层H(m) / H=3.6", "100m²", 235),
    51: ("7.3.2", "里脚手架", "工业建筑 / 每增1.2", "100m²", 235),
    52: ("7.3.3", "满堂脚手架", "搭拆及使用 / 层高H(m) / 0<H≤6", "10m³", 236),
    53: ("7.3.3", "满堂脚手架", "搭拆及使用 / 层高H(m) / H>6", "10m³", 236),
    54: ("7.3.4", "电梯井架", None, "100m³", 237),
    55: ("7.3.5", "活动脚手架", "墙砌筑或装饰", "100m²", 238),
    56: ("7.3.5", "活动脚手架", "独立柱装饰", "100m²", 238),
    57: ("7.3.5", "活动脚手架", "柱、墙混凝土浇捣", "100m²", 238),
    58: ("7.3.5", "活动脚手架", "天棚面装饰及修整", "100m²", 238),
    59: ("7.3.6", "烟囱、水塔脚手架", "直径D(m) / D≤5 / 搭设高度H(m) / 0<H≤10", "座", 239),
    60: ("7.3.6", "烟囱、水塔脚手架", "直径D(m) / D≤5 / 搭设高度H(m) / 10<H≤15", "座", 239),
    61: ("7.3.6", "烟囱、水塔脚手架", "直径D(m) / D≤5 / 搭设高度H(m) / 15<H≤20", "座", 239),
    62: ("7.3.6", "烟囱、水塔脚手架", "直径D(m) / D≤5 / 搭设高度H(m) / 20<H≤25", "座", 239),
}

groups = {
    "7.3.2": ("里脚手架", 235, 235, 2),
    "7.3.3": ("满堂脚手架", 236, 236, 3),
    "7.3.4": ("电梯井架", 237, 237, 4),
    "7.3.5": ("活动脚手架", 238, 238, 5),
    "7.3.6": ("构筑物脚手架", 239, 239, 6),
}

labor = {
    48: (132.21, 1138.37), 49: (31.87, 390.97), 50: (91.18, 1066.69), 51: (22.30, 357.75),
    52: (5.21, 51.24, 19.81), 53: (7.03, 78.48, 26.48),
    54: (338.16, 2139.11),
    55: (37.54, 396.36), 56: (33.49, 353.84), 57: (13.38, 141.49), 58: (30.57, 322.85),
    59: (679.50, 2392.87), 60: (894.96, 3151.64), 61: (1089.29, 3835.94), 62: (1483.27, 5223.28),
}


def materials(number):
    if 48 <= number <= 51:
        i = number - 48
        return [
            ("脚手架钢管", "kg", (2.500, .600, 1.750, .480)[i], 4.74),
            ("脚手架扣件（综合）含对接口、直角扣、活动扣等", "个", (.520, .130, .364, .104)[i], 7.18),
            ("冲压钢脚手板", "m²", (1.533, None, .843, None)[i], 108.79),
            ("其他材料费", "%", (3.5, 1, 3, 1)[i], 1),
        ]
    if number in (52, 53):
        i = number - 52
        return [
            ("承插型盘扣式钢管脚手架（成套）", "kg", (6.691, 8.922)[i], 6.61),
            ("其他材料费", "%", 1, 1),
        ]
    if number == 54:
        return [
            ("防锈漆 红色", "kg", 2.282, 16.23),
            ("油漆溶剂油", "kg", .322, 11.33),
            ("脚手架钢管", "kg", 225.567, 4.74),
            ("底座", "个", .389, 17.90),
            ("脚手架扣件（综合）含对接口、直角扣、活动扣等", "个", 6.871, 7.18),
            ("冲压钢脚手板", "m²", .713, 108.79),
            ("其他材料费", "%", 4.5, 1),
        ]
    if 55 <= number <= 58:
        i = number - 55
        return [
            ("水平架（脚手架专用）", "m²", (.079, .035, .006, .032)[i], 18),
            ("交叉支撑（脚手架专用）", "副", (.175, .078, .013, .110)[i], 12),
            ("连接棒", "个", (.153, .117, .020, .107)[i], 8.40),
            ("钢管架", "m²", (.179, .160, .027, .146)[i], 21),
            ("底座", "个", (.153, .078, .013, .128)[i], 17.90),
            ("冲压钢脚手板", "m²", (.059, .026, .010, .021)[i], 108.79),
            ("其他材料费", "%", 3.5, 1),
        ]
    i = number - 59
    return [
        ("挡脚板（钢笆网）", "m²", (.608, .913, 1.217, 1.521)[i], 9.50),
        ("松杂直边板", "m³", (.197, .396, .451, .506)[i], 1602.51),
        ("防锈漆 红色", "kg", (5.620, 10.010, 13.410, 17.260)[i], 16.23),
        ("油漆溶剂油", "kg", (.630, 1.130, 1.510, 1.940)[i], 11.33),
        ("脚手架钢管", "kg", (70.057, 124.769, 166.422, 271.319)[i], 4.74),
        ("底座", "个", 1.120, 17.90),
        ("脚手架扣件（综合）含对接口、直角扣、活动扣等", "个", (14.800, 25.840, 34.960, 46.170)[i], 7.18),
        ("钢笆子（钢架板）", "m²", (1.622, 2.433, 3.244, 4.056)[i], 12),
        ("其他材料费", "%", 4.5, 1),
    ]


load_dotenv(".env")
conn = get_connection()
try:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id FROM bs2024_sections s JOIN bs2024_chapters c ON c.id=s.chapter_id
            WHERE c.document_id=%s AND c.chapter_no=7 AND s.section_code='7.3'
            ORDER BY s.id LIMIT 1
            """,
            (DOC,),
        )
        section_id = cur.fetchone()[0]
        group_ids = {}
        for code, (name, start, end, order) in groups.items():
            cur.execute(
                "SELECT id FROM bs2024_item_groups WHERE document_id=%s AND group_code=%s ORDER BY id LIMIT 1",
                (DOC, code),
            )
            row = cur.fetchone()
            if row:
                gid = row[0]
                cur.execute(
                    "UPDATE bs2024_item_groups SET section_id=%s,group_name=%s,page_start=%s,page_end=%s,sort_order=%s WHERE id=%s",
                    (section_id, name, start, end, order, gid),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_item_groups
                      (document_id,section_id,group_code,group_name,page_start,page_end,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (DOC, section_id, code, name, start, end, order),
                )
                gid = cur.fetchone()[0]
            group_ids[code] = gid

        item_ids = {}
        for code, (group_name, page, _, item_no) in {
            "7.3.2": ("里脚手架", 235, None, 1),
            "7.3.3": ("满堂脚手架", 236, None, 1),
            "7.3.4": ("电梯井架", 237, None, 1),
            "7.3.5": ("活动脚手架", 238, None, 1),
            "7.3.6": ("烟囱、水塔脚手架", 239, None, 1),
        }.items():
            first_code = {
                "7.3.2": "010007-48", "7.3.3": "010007-52", "7.3.4": "010007-54",
                "7.3.5": "010007-55", "7.3.6": "010007-59",
            }[code]
            cur.execute(
                """
                SELECT i.id FROM bs2024_items i JOIN bs2024_subitems s ON s.item_id=i.id
                WHERE s.document_id=%s AND s.subitem_code=%s ORDER BY i.id LIMIT 1
                """,
                (DOC, first_code),
            )
            row = cur.fetchone()
            work = "底座安装、搭设、拆除脚手架等全部操作过程，脚手架拆除后的材料整理、刷油、堆放及场内运输，施工期间的加固维修及更新换料、翻板子等。"
            if row:
                iid = row[0]
                cur.execute(
                    "UPDATE bs2024_items SET group_id=%s,item_no=%s,item_name=%s,work_content=%s,page_no=%s,sort_order=%s WHERE id=%s",
                    (group_ids[code], item_no, group_name, work, page, item_no, iid),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_items
                      (document_id,group_id,item_no,item_name,work_content,page_no,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (DOC, group_ids[code], item_no, group_name, work, page, item_no),
                )
                iid = cur.fetchone()[0]
            item_ids[code] = iid

        for number in range(48, 63):
            group_code, subitem_name, variant, unit, page = specs[number]
            path = [groups[group_code][0], subitem_name]
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
                    item_ids[group_code], subitem_name, variant, unit,
                    json.dumps(path, ensure_ascii=False),
                    *[d(value) for value in costs[number]],
                    page, number, DOC, f"010007-{number}",
                ),
            )
            sid = cur.fetchone()[0]
            cur.execute("DELETE FROM bs2024_resources WHERE subitem_id=%s", (sid,))
            labor_names = ("普通人工费", "技工人工费", "高级技工人工费")
            rows = [
                ("人工", labor_names[i], "元", quantity, None)
                for i, quantity in enumerate(labor[number])
            ]
            rows.extend(("材料", *row) for row in materials(number))
            for order, row in enumerate(rows, 1):
                cur.execute(
                    """
                    INSERT INTO bs2024_resources
                      (document_id,subitem_id,resource_type,resource_name,unit,
                       quantity,ref_price,page_no,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (DOC, sid, *row[:3], d(row[3]), d(row[4]), page, order),
                )

        cur.execute(
            """
            UPDATE bs2024_pages SET chapter_no=7,chapter_title='脚手架工程',
              section_code='7.3',section_type='items'
            WHERE document_id=%s AND page_no BETWEEN 235 AND 239
            """,
            (DOC,),
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

print("Corrected Chapter 7 subitems 010007-48 through 010007-62.")
