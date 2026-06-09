from decimal import Decimal
import json

from dotenv import load_dotenv

from db.connection import get_connection


DOC = 25


def d(value):
    return Decimal(str(value))


costs = {
    83: (11133.54, 9205.78, 6599.42, 1066.42, 31.95, 1069.62, 438.37, 375.60, 1187.90, 364.26),
    84: (16139.84, 13451.46, 8952.80, 2397.96, 9.64, 1450.51, 640.55, 548.82, 1611.50, 528.06),
    85: (16133.23, 13776.46, 7038.11, 4923.16, 18.69, 1140.48, 656.02, 562.08, 1266.86, 527.83),
    86: (11386.49, 9494.67, 6288.38, 1719.21, 15.97, 1018.98, 452.13, 387.38, 1131.91, 372.53),
    87: (26759.53, 22188.08, 15503.80, 2629.86, 478.47, 2519.37, 1056.58, 905.27, 2790.68, 875.50),
    88: (26630.80, 22154.96, 15003.49, 3266.28, 393.25, 2436.94, 1055.00, 903.92, 2700.63, 871.29),
    89: (22340.11, 18649.70, 12214.37, 3168.90, 393.25, 1985.10, 888.08, 760.91, 2198.59, 730.91),
    90: (19971.05, 16639.82, 11105.17, 2723.42, 216.32, 1802.54, 792.37, 678.90, 1998.93, 653.40),
    91: (16460.02, 13693.21, 9275.58, 2092.82, 167.39, 1505.36, 652.06, 558.68, 1669.60, 538.53),
    92: (14763.97, 12287.73, 8288.17, 1947.23, 122.53, 1344.67, 585.13, 501.34, 1491.87, 483.03),
    93: (11382.46, 9507.42, 6193.01, 1760.41, 96.44, 1004.83, 452.73, 387.90, 1114.74, 372.40),
    94: (16119.49, 13404.13, 9117.12, 2041.63, 128.04, 1479.05, 638.29, 546.89, 1641.08, 527.39),
    95: (41366.12, 34260.00, 24193.98, 3597.59, 902.95, 3934.05, 1631.43, 1397.81, 4354.92, 1353.39),
    96: (35737.53, 29629.09, 20724.07, 3335.66, 788.36, 3370.07, 1410.91, 1208.87, 3730.33, 1169.24),
    97: (31781.85, 26363.37, 18350.15, 3063.53, 710.06, 2984.23, 1255.40, 1075.63, 3303.03, 1039.82),
    98: (20297.67, 17619.34, 7196.57, 6452.31, 1934.26, 1197.18, 839.02, 718.87, 1295.38, 664.08),
    99: (18098.01, 15500.44, 7627.92, 5396.13, 494.54, 1243.73, 738.12, 632.42, 1373.03, 592.12),
}

labor = {
    83: (1158.75, 5440.67), 84: (1571.96, 7380.84), 85: (1235.77, 5802.34), 86: (1104.14, 5184.24),
    87: (2722.21, 12781.59), 88: (2634.36, 12369.13), 89: (2144.64, 10069.73), 90: (1949.89, 9155.28),
    91: (1628.63, 7646.95), 92: (1455.27, 6832.90), 93: (1087.38, 5105.63), 94: (1600.81, 7516.31),
    95: (4248.05, 19945.93), 96: (3638.79, 17085.28), 97: (3221.97, 15128.18),
    98: (1263.60, 5932.97), 99: (746.89, 6881.03),
}

defs = {
    83: ("6.3.2", 3, "贮仓模板", "矩形贮仓壁模板", None, "100m²", 208),
    84: ("6.3.2", 3, "贮仓模板", "圆形贮仓壁模板", None, "100m²", 208),
    85: ("6.3.2", 3, "贮仓模板", "圆形贮仓隔层板模板", None, "100m²", 208),
    86: ("6.3.2", 3, "贮仓模板", "圆形贮仓顶板模板", None, "100m²", 208),
    87: ("6.3.2", 4, "烟囱、贮仓、水塔滑模", "烟囱液压滑升钢模", "筒身高度H(m) / 0<H≤60", "10m³", 209),
    88: ("6.3.2", 4, "烟囱、贮仓、水塔滑模", "烟囱液压滑升钢模", "筒身高度H(m) / 50<H≤80", "10m³", 209),
    89: ("6.3.2", 4, "烟囱、贮仓、水塔滑模", "烟囱液压滑升钢模", "筒身高度H(m) / 80<H≤100", "10m³", 209),
    90: ("6.3.2", 4, "烟囱、贮仓、水塔滑模", "烟囱液压滑升钢模", "筒身高度H(m) / 100<H≤120", "10m³", 209),
    91: ("6.3.2", 4, "烟囱、贮仓、水塔滑模", "烟囱液压滑升钢模", "筒身高度H(m) / 120<H≤150", "10m³", 210),
    92: ("6.3.2", 4, "烟囱、贮仓、水塔滑模", "烟囱液压滑升钢模", "筒身高度H(m) / 150<H≤180", "10m³", 210),
    93: ("6.3.2", 4, "烟囱、贮仓、水塔滑模", "烟囱液压滑升钢模", "筒身高度H(m) / 180<H≤210", "10m³", 210),
    94: ("6.3.2", 4, "烟囱、贮仓、水塔滑模", "贮仓", "高度H(m) / 0<H≤30", "10m³", 210),
    95: ("6.3.2", 4, "烟囱、贮仓、水塔滑模", "倒锥壳水塔塔身液压滑升钢模", "筒身高度H(m) / 0<H≤20", "10m³", 211),
    96: ("6.3.2", 4, "烟囱、贮仓、水塔滑模", "倒锥壳水塔塔身液压滑升钢模", "筒身高度H(m) / 20<H≤25", "10m³", 211),
    97: ("6.3.2", 4, "烟囱、贮仓、水塔滑模", "倒锥壳水塔塔身液压滑升钢模", "筒身高度H(m) / 25<H≤30", "10m³", 211),
    98: ("6.3.2", 5, "钢滑模制作", "钢滑模", "制作", "t", 212),
    99: ("6.3.3", 1, "爬模", "爬模", None, "100m²", 213),
}

work = {
    3: "模板及支架制作、安装、拆除、整理堆放、运输，清理模板粘结物及模内杂物，刷隔离剂，封堵孔洞等。",
    4: "安装、拆除钢平台、模板、液压及供电通信设备，中间改模、激光对中、设置安全网，模板拆除后清洗、刷油、堆放及场内运输。",
    5: "钢柱校正、划线号料、剪断、平直、钻孔、刨边、煨弯、焊接、刷防锈漆、成品搬运、整理堆放。",
}

load_dotenv(".env")
conn = get_connection()
try:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id FROM bs2024_sections s JOIN bs2024_chapters c ON c.id=s.chapter_id
            WHERE c.document_id=%s AND c.chapter_no=6 AND s.section_code='6.3'
            ORDER BY s.id LIMIT 1
            """,
            (DOC,),
        )
        section_id = cur.fetchone()[0]

        groups = {}
        for code, name, start, end, order in (
            ("6.3.2", "现浇混凝土构筑物模板", 202, 212, 2),
            ("6.3.3", "爬模", 213, 213, 3),
        ):
            cur.execute(
                "SELECT id FROM bs2024_item_groups WHERE document_id=%s AND section_id=%s AND group_code=%s ORDER BY id LIMIT 1",
                (DOC, section_id, code),
            )
            row = cur.fetchone()
            if row:
                group_id = row[0]
                cur.execute(
                    "UPDATE bs2024_item_groups SET group_name=%s,page_start=%s,page_end=%s,sort_order=%s WHERE id=%s",
                    (name, start, end, order, group_id),
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
                group_id = cur.fetchone()[0]
            groups[code] = group_id

        item_ids = {}
        item_specs = {
            ("6.3.2", 3): ("贮仓模板", 208),
            ("6.3.2", 4): ("烟囱、贮仓、水塔滑模", 209),
            ("6.3.2", 5): ("钢滑模制作", 212),
            ("6.3.3", 1): ("爬模", 213),
        }
        for key, (name, page) in item_specs.items():
            group_code, item_no = key
            cur.execute(
                "SELECT id FROM bs2024_items WHERE document_id=%s AND group_id=%s AND item_no=%s ORDER BY id LIMIT 1",
                (DOC, groups[group_code], item_no),
            )
            row = cur.fetchone()
            content = work.get(item_no) if group_code == "6.3.2" else (
                "模板及其紧固系统制作、安装、拆除、整理堆放及场内运输，爬升架体系统制作、安装，液压系统及电气控制系统设计、安装，平台维护。"
            )
            if row:
                item_id = row[0]
                cur.execute(
                    "UPDATE bs2024_items SET item_name=%s,work_content=%s,page_no=%s,sort_order=%s WHERE id=%s",
                    (name, content, page, item_no, item_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_items
                      (document_id,group_id,item_no,item_name,work_content,page_no,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (DOC, groups[group_code], item_no, name, content, page, item_no),
                )
                item_id = cur.fetchone()[0]
            item_ids[key] = item_id

        for number in range(83, 100):
            group_code, item_no, item_name, sub_name, variant, unit, page = defs[number]
            group_name = "现浇混凝土构筑物模板" if group_code == "6.3.2" else "爬模"
            path = [group_name, item_name]
            if sub_name != item_name:
                path.append(sub_name)
            if variant:
                path.extend(variant.split(" / "))
            cur.execute(
                """
                UPDATE bs2024_subitems SET item_id=%s,subitem_name=%s,variant_desc=%s,unit=%s,
                  name_path_json=%s::jsonb,total_unit_price=%s,unit_price=%s,labor_cost=%s,
                  material_cost=%s,machine_cost=%s,management_fee=%s,profit=%s,safety_fee=%s,
                  statutory_fee=%s,tax=%s,page_no=%s,confidence=1,sort_order=%s
                WHERE document_id=%s AND subitem_code=%s
                RETURNING id
                """,
                (item_ids[(group_code, item_no)], sub_name, variant, unit,
                 json.dumps(path, ensure_ascii=False), *[d(v) for v in costs[number]],
                 page, number, DOC, f"010006-{number}"),
            )
            sid = cur.fetchone()[0]
            cur.execute(
                "DELETE FROM bs2024_resources WHERE subitem_id=%s AND resource_type=%s",
                (sid, "人工"),
            )
            for order, (name, quantity) in enumerate(
                (("普通人工费", labor[number][0]), ("技工人工费", labor[number][1])), 1
            ):
                cur.execute(
                    """
                    INSERT INTO bs2024_resources
                      (document_id,subitem_id,resource_type,resource_name,unit,quantity,ref_price,page_no,sort_order)
                    VALUES (%s,%s,'人工',%s,'元',%s,NULL,%s,%s)
                    """,
                    (DOC, sid, name, d(quantity), page, order),
                )

        cur.execute(
            "UPDATE bs2024_pages SET chapter_no=6,chapter_title='模板工程' WHERE document_id=%s AND page_no BETWEEN 208 AND 213",
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

print("Corrected Chapter 6 subitems 010006-83 through 010006-99.")
