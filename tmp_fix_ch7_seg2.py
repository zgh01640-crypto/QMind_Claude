from decimal import Decimal
import json

from dotenv import load_dotenv

from db.connection import get_connection


DOC = 25


def d(value):
    return None if value is None else Decimal(str(value))


costs = {
    4: (742.10, 609.53, 463.47, 41.95, 0, 75.08, 29.03, 24.87, 83.42, 24.28),
    5: (861.34, 711.44, 514.97, 75.84, 3.27, 83.48, 33.88, 29.03, 92.69, 28.18),
    6: (993.46, 825.33, 566.47, 124.12, 3.61, 91.83, 39.30, 33.67, 101.96, 32.50),
    7: (227.78, 198.91, 73.87, 103.60, 0, 11.97, 9.47, 8.12, 13.30, 7.45),
    8: (268.14, 233.29, 92.00, 115.28, 0, 14.90, 11.11, 9.52, 16.56, 8.77),
    9: (302.48, 262.76, 106.09, 126.97, 0, 17.19, 12.51, 10.72, 19.10, 9.90),
    10: (84.44, 72.87, 32.37, 31.79, 0, 5.24, 3.47, 2.97, 5.83, 2.77),
    11: (97.19, 83.61, 38.83, 34.51, 0, 6.29, 3.98, 3.41, 6.99, 3.18),
    12: (112.16, 96.18, 46.61, 37.44, 0, 7.55, 4.58, 3.92, 8.39, 3.67),
    13: (2564.61, 2091.46, 1688.40, 29.95, 0, 273.52, 99.59, 85.33, 303.91, 83.91),
    14: (3538.93, 2890.22, 2305.55, 73.54, 0, 373.50, 137.63, 117.92, 415.00, 115.79),
    15: (4521.46, 3691.13, 2954.45, 82.29, 0, 478.62, 175.77, 150.60, 531.80, 147.93),
    16: (139.92, 125.36, 27.03, 87.98, 0, 4.38, 5.97, 5.11, 4.87, 4.58),
    17: (167.03, 148.44, 39.21, 95.81, 0, 6.35, 7.07, 6.06, 7.06, 5.47),
    18: (200.69, 176.98, 55.18, 104.43, 0, 8.94, 8.43, 7.22, 9.93, 6.56),
}

labor = {
    4: (40.09, 423.38), 5: (44.54, 470.43), 6: (49.00, 517.47),
    7: (11.08, 62.79), 8: (11.46, 80.54), 9: (11.73, 94.36),
    10: (2.80, 29.57), 11: (3.36, 35.47), 12: (4.03, 42.58),
    13: (146.00, 1542.40), 14: (199.38, 2106.17), 15: (255.48, 2698.97),
    16: (8.20, 18.83), 17: (9.84, 29.37), 18: (11.80, 43.38),
}

variants = {
    4: ("扣件式钢管双排脚手架", "搭拆 / 每增加一排立杆 / 搭设高度H(m) / 0<H≤24", "100m²", 220),
    5: ("扣件式钢管双排脚手架", "搭拆 / 每增加一排立杆 / 搭设高度H(m) / 24<H≤50", "100m²", 220),
    6: ("扣件式钢管双排脚手架", "搭拆 / 每增加一排立杆 / 搭设高度H(m) / H>50", "100m²", 220),
    7: ("扣件式钢管双排脚手架", "使用 / 搭设高度H(m) / 0<H≤24", "100m²·10天", 221),
    8: ("扣件式钢管双排脚手架", "使用 / 搭设高度H(m) / 24<H≤50", "100m²·10天", 221),
    9: ("扣件式钢管双排脚手架", "使用 / 搭设高度H(m) / H>50", "100m²·10天", 221),
    10: ("扣件式钢管双排脚手架", "使用 / 每增加一排立杆 / 搭设高度H(m) / 0<H≤24", "100m²·10天", 222),
    11: ("扣件式钢管双排脚手架", "使用 / 每增加一排立杆 / 搭设高度H(m) / 24<H≤50", "100m²·10天", 222),
    12: ("扣件式钢管双排脚手架", "使用 / 每增加一排立杆 / 搭设高度H(m) / H>50", "100m²·10天", 222),
    13: ("扣件式钢管单排脚手架", "搭拆 / 搭设高度H(m) / 0<H≤6", "100m²", 223),
    14: ("扣件式钢管单排脚手架", "搭拆 / 搭设高度H(m) / 6<H≤14", "100m²", 223),
    15: ("扣件式钢管单排脚手架", "搭拆 / 搭设高度H(m) / 14<H≤24", "100m²", 223),
    16: ("扣件式钢管单排脚手架", "使用 / 搭设高度H(m) / 0<H≤6", "100m²·10天", 224),
    17: ("扣件式钢管单排脚手架", "使用 / 搭设高度H(m) / 6<H≤14", "100m²·10天", 224),
    18: ("扣件式钢管单排脚手架", "使用 / 搭设高度H(m) / 14<H≤24", "100m²·10天", 224),
}


def material_rows(number):
    index = (number - 1) % 3
    if 4 <= number <= 6:
        rows = [
            ("镀锌铁丝（综合）", "kg", (0.650, 0.684, 0.739), 6.05),
            ("工字钢（综合）", "t", (0.005, 0.012, 0.022), 4671.00),
            ("电焊条 E4303 φ3.2", "kg", (None, 0.024, 0.026), 8.62),
            ("防锈漆 红色", "kg", (0.851, 0.896, 0.968), 16.23),
            ("油漆溶剂油", "kg", (0.075, 0.079, 0.085), 11.33),
        ]
    elif 7 <= number <= 9:
        rows = [
            ("底座（租赁10天）", "个", (13.890, 13.890, 13.890), 0.51),
            ("脚手架钢管 φ48×3.4mm×1～6m（租赁10天）", "kg", (1030.943, 1228.037, 1428.037), 0.05),
            ("扣件（含转扣接头、十字）（租赁10天）", "个", (121.527, 133.680, 144.374), 0.11),
            ("钢笆子（钢筋网脚手板）（租赁10天）", "kg", (434.742, 434.742, 434.742), 0.06),
            ("松杂直边板（租赁10天）", "m³", (0.050, 0.050, 0.050), 21.20),
            ("其他材料费", "%", (4.500, 4.500, 4.500), 1.00),
        ]
    elif 10 <= number <= 12:
        rows = [
            ("底座（租赁10天）", "个", (4.584, 4.584, 4.584), 0.51),
            ("脚手架钢管 φ48×3.4mm×1～6m（租赁10天）", "kg", (476.045, 523.650, 576.015), 0.05),
            ("扣件（含转扣接头、十字）（租赁10天）", "个", (31.597, 34.757, 37.537), 0.11),
            ("钢笆子（钢筋网脚手板）（租赁10天）", "kg", (34.780, 34.780, 34.780), 0.06),
            ("松杂直边板（租赁10天）", "m³", (0.004, 0.004, 0.004), 21.20),
            ("其他材料费", "%", (None, None, None), 1.00),
        ]
    elif 13 <= number <= 15:
        rows = [
            ("镀锌铁丝（综合）", "kg", (1.830, 3.940, 4.210), 6.05),
            ("电焊条 E4303 φ3.2", "kg", (None, None, 0.117), 8.62),
            ("防锈漆 红色", "kg", (1.005, 2.660, 2.988), 16.23),
            ("油漆溶剂油", "kg", (0.101, 0.267, 0.299), 11.33),
            ("其他材料费", "%", (5.000, 5.000, 5.000), 1.00),
        ]
    else:
        rows = [
            ("底座（租赁10天）", "个", (13.890, 13.890, 13.890), 0.51),
            ("扣件（含转扣接头、十字）（租赁10天）", "个", (86.810, 95.491, 105.040), 0.11),
            ("钢笆子（钢筋网脚手板）（租赁10天）", "kg", (434.742, 434.742, 434.742), 0.06),
            ("脚手架钢管 φ48×3.4mm×1～6m（租赁10天）", "kg", (808.377, 939.215, 1083.137), 0.05),
            ("松杂直边板（租赁10天）", "m³", (0.050, 0.050, 0.050), 21.20),
            ("其他材料费", "%", (4.500, 4.500, 4.500), 1.00),
        ]
    return [(name, unit, quantities[index], price) for name, unit, quantities, price in rows]


load_dotenv(".env")
conn = get_connection()
try:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id FROM bs2024_items i
            JOIN bs2024_subitems s ON s.item_id=i.id
            WHERE s.document_id=%s AND s.subitem_code='010007-1'
            ORDER BY i.id LIMIT 1
            """,
            (DOC,),
        )
        item_id = cur.fetchone()[0]
        cur.execute(
            """
            UPDATE bs2024_items SET item_no=1,item_name='扣件式钢管外脚手架',
              page_no=219,sort_order=1 WHERE id=%s
            """,
            (item_id,),
        )

        for number in range(4, 19):
            subitem_name, variant, unit, page = variants[number]
            path = ["外脚手架", "扣件式钢管外脚手架", subitem_name, *variant.split(" / ")]
            code = f"010007-{number}"
            cur.execute(
                """
                UPDATE bs2024_subitems SET item_id=%s,subitem_name=%s,variant_desc=%s,
                  unit=%s,name_path_json=%s::jsonb,total_unit_price=%s,unit_price=%s,
                  labor_cost=%s,material_cost=%s,machine_cost=%s,management_fee=%s,
                  profit=%s,safety_fee=%s,statutory_fee=%s,tax=%s,page_no=%s,
                  confidence=1,sort_order=%s
                WHERE document_id=%s AND subitem_code=%s
                RETURNING id
                """,
                (
                    item_id, subitem_name, variant, unit,
                    json.dumps(path, ensure_ascii=False),
                    *[d(value) for value in costs[number]],
                    page, number, DOC, code,
                ),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"Missing parsed subitem {code}")
            subitem_id = row[0]
            cur.execute("DELETE FROM bs2024_resources WHERE subitem_id=%s", (subitem_id,))
            resources = [
                ("人工", "普通人工费", "元", labor[number][0], None),
                ("人工", "技工人工费", "元", labor[number][1], None),
            ]
            resources.extend(
                ("材料", name, unit_name, quantity, price)
                for name, unit_name, quantity, price in material_rows(number)
            )
            if 4 <= number <= 6:
                resources.append(
                    (
                        "机械",
                        "交流电焊机 容量E(kV·A) E=30",
                        "台班",
                        (None, 0.019, 0.021)[number - 4],
                        172.10,
                    )
                )
            for order, resource in enumerate(resources, 1):
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
            """
            UPDATE bs2024_item_groups SET page_end=224
            WHERE document_id=%s AND group_code='7.3.1'
            """,
            (DOC,),
        )
        cur.execute(
            """
            UPDATE bs2024_pages SET chapter_no=7,chapter_title='脚手架工程',
              section_code='7.3',section_type='items'
            WHERE document_id=%s AND page_no BETWEEN 220 AND 224
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

print("Corrected Chapter 7 subitems 010007-4 through 010007-18.")
