from decimal import Decimal
import json

from dotenv import load_dotenv

from db.connection import get_connection


DOC = 25


def d(value):
    return None if value is None else Decimal(str(value))


costs = {
    63: (22193.96, 18536.63, 12082.84, 3613.67, 0, 1957.42, 882.70, 756.29, 2174.91, 726.13),
    64: (33252.48, 27693.41, 18562.48, 4805.08, 0, 3007.12, 1318.73, 1129.89, 3341.25, 1087.93),
    65: (10872.93, 9198.77, 5239.56, 2672.36, 0, 848.81, 438.04, 375.31, 943.12, 355.73),
    66: (25435.34, 21554.56, 12050.92, 6524.98, 0, 1952.25, 1026.41, 879.43, 2169.17, 832.18),
    67: (54857.57, 46189.14, 27717.29, 11782.17, 0, 4490.20, 2199.48, 1884.52, 4989.11, 1794.80),
    68: (106972.03, 90068.63, 54048.65, 22975.12, 0, 8755.88, 4288.98, 3674.80, 9728.76, 3499.84),
    69: (2424.73, 2086.15, 967.46, 862.62, 0, 156.73, 99.34, 85.11, 174.14, 79.33),
    70: (197.05, 166.30, 97.28, 45.34, 0, 15.76, 7.92, 6.79, 17.51, 6.45),
    71: (1320.93, 1178.49, 284.12, 792.22, 0, 46.03, 56.12, 48.08, 51.14, 43.22),
    72: (3413.75, 3113.65, 340.95, 2569.20, 0, 55.23, 148.27, 127.04, 61.37, 111.69),
}

specs = {
    63: ("7.3.6", 1, "烟囱、水塔脚手架", "直径D(m) / D≤5 / 搭设高度H(m) / 25<H≤35", "座", 240),
    64: ("7.3.6", 1, "烟囱、水塔脚手架", "直径D(m) / D≤5 / 搭设高度H(m) / 35<H≤45", "座", 240),
    65: ("7.3.6", 1, "烟囱、水塔脚手架", "直径D(m) / 5<D≤8 / 搭设高度H(m) / 0<H≤20", "座", 240),
    66: ("7.3.6", 1, "烟囱、水塔脚手架", "直径D(m) / 5<D≤8 / 搭设高度H(m) / 20<H≤40", "座", 240),
    67: ("7.3.6", 1, "烟囱、水塔脚手架", "直径D(m) / 5<D≤8 / 搭设高度H(m) / 40<H≤60", "座", 241),
    68: ("7.3.6", 1, "烟囱、水塔脚手架", "直径D(m) / 5<D≤8 / 搭设高度H(m) / 60<H≤80", "座", 241),
    69: ("7.3.7", 1, "水平安全挡板", None, "100m²", 242),
    70: ("7.3.7", 1, "安全防护通道", None, "m³", 242),
    71: ("7.3.7", 2, "脚手架上挂安全立网", "绿色密目式阻燃安全网", "100m²", 243),
    72: ("7.3.7", 2, "脚手架上挂安全立网", "金属安全网", "100m²", 243),
}

labor = {
    63: (2672.32, 9410.52), 64: (4105.39, 14457.09),
    65: (1158.82, 4080.74), 66: (2665.26, 9385.66),
    67: (6130.13, 21587.16), 68: (11953.74, 42094.91),
    69: (213.97, 753.49), 70: (6.86, 90.42),
    71: (62.84, 221.28), 72: (75.41, 265.54),
}


def materials(number):
    if 63 <= number <= 68:
        values = {
            63: (2.129, .727, 22.890, 2.580, 285.009, 1.120, 60.300, 5.678),
            64: (2.738, .970, 30.360, 3.420, 378.161, 1.120, 81.630, 7.300),
            65: (1.504, .558, 16.580, 1.867, 205.758, 1.385, 43.223, 4.011),
            66: (3.159, 1.717, 34.817, 3.921, 432.092, 2.908, 90.769, 8.424),
            67: (6.634, 2.459, 73.116, 8.233, 907.393, 6.107, 190.615, 17.690),
            68: (12.936, 4.795, 142.577, 16.054, 1769.416, 11.908, 371.699, 34.495),
        }[number]
        return [
            ("挡脚板（钢笆网）", "m²", values[0], 9.50),
            ("松杂直边板", "m³", values[1], 1602.51),
            ("防锈漆 红色", "kg", values[2], 16.23),
            ("油漆溶剂油", "kg", values[3], 11.33),
            ("脚手架钢管", "kg", values[4], 4.74),
            ("底座", "个", values[5], 17.90),
            ("脚手架扣件（综合）含对接口、直角扣、活动扣等", "个", values[6], 7.18),
            ("钢笆子（钢架板）", "m²", values[7], 12),
            ("其他材料费", "%", 4.5, 1),
        ]
    if number in (69, 70):
        i = number - 69
        return [
            ("松木胶合板 18mm 1号胶", "m²", (6.667, .122)[i], 75),
            ("脚手架钢管", "kg", (56.526, 6.970)[i], 4.74),
            ("脚手架扣件（综合）含对接口、直角扣、活动扣等", "个", (6.240, .319)[i], 7.18),
            ("底座", "个", (.710, .023)[i], 17.90),
            ("其他材料费", "%", (4.5, 1)[i], 1),
        ]
    if number == 71:
        return [
            ("金属安全网 周转材", "m²", None, 72),
            ("密目式阻燃安全网", "m²", 102, 7.69),
            ("其他材料费", "%", 1, 1),
        ]
    return [
        ("金属安全网 周转材", "m²", 35.330, 72),
        ("密目式阻燃安全网", "m²", None, 7.69),
        ("其他材料费", "%", 1, 1),
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
        for code, name, start, end, order in (
            ("7.3.6", "构筑物脚手架", 239, 241, 6),
            ("7.3.7", "安全防护措施", 242, 243, 7),
        ):
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
        item_defs = {
            ("7.3.6", 1): ("烟囱、水塔脚手架", "010007-59", 239),
            ("7.3.7", 1): ("防护架", "010007-69", 242),
            ("7.3.7", 2): ("安全立网", "010007-71", 243),
        }
        for key, (name, first_code, page) in item_defs.items():
            group_code, item_no = key
            cur.execute(
                """
                SELECT i.id FROM bs2024_items i JOIN bs2024_subitems s ON s.item_id=i.id
                WHERE s.document_id=%s AND s.subitem_code=%s ORDER BY i.id LIMIT 1
                """,
                (DOC, first_code),
            )
            row = cur.fetchone()
            work = (
                "搭设、拆除脚手架等全部操作过程，施工使用期间的维修、加固，"
                "材料整理、刷油、堆放及场内运输。"
            )
            if row:
                iid = row[0]
                cur.execute(
                    "UPDATE bs2024_items SET group_id=%s,item_no=%s,item_name=%s,work_content=%s,page_no=%s,sort_order=%s WHERE id=%s",
                    (group_ids[group_code], item_no, name, work, page, item_no, iid),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_items
                      (document_id,group_id,item_no,item_name,work_content,page_no,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (DOC, group_ids[group_code], item_no, name, work, page, item_no),
                )
                iid = cur.fetchone()[0]
            item_ids[key] = iid

        for number in range(63, 73):
            group_code, item_no, subitem_name, variant, unit, page = specs[number]
            group_name = "构筑物脚手架" if group_code == "7.3.6" else "安全防护措施"
            item_name = item_defs[(group_code, item_no)][0]
            path = [group_name, item_name, subitem_name]
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
                    item_ids[(group_code, item_no)], subitem_name, variant, unit,
                    json.dumps(path, ensure_ascii=False),
                    *[d(value) for value in costs[number]],
                    page, number, DOC, f"010007-{number}",
                ),
            )
            sid = cur.fetchone()[0]
            cur.execute("DELETE FROM bs2024_resources WHERE subitem_id=%s", (sid,))
            rows = [
                ("人工", "普通人工费", "元", labor[number][0], None),
                ("人工", "技工人工费", "元", labor[number][1], None),
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
            WHERE document_id=%s AND page_no BETWEEN 240 AND 243
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

print("Corrected Chapter 7 subitems 010007-63 through 010007-72.")
