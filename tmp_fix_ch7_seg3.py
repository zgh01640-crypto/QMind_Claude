from decimal import Decimal
import json

from dotenv import load_dotenv

from db.connection import get_connection


DOC = 25


def d(value):
    return None if value is None else Decimal(str(value))


costs = {
    19: (4527.50, 3708.46, 2886.66, 177.23, .34, 467.64, 176.59, 151.31, 519.60, 148.13),
    20: (5369.86, 4434.35, 3216.19, 482.48, 3.44, 521.08, 211.16, 180.92, 578.91, 175.68),
    21: (6158.62, 5108.06, 3559.19, 724.84, 4.13, 576.66, 243.24, 208.41, 640.65, 201.50),
    22: (669.97, 548.90, 426.39, 27.29, 0, 69.08, 26.14, 22.40, 76.75, 21.92),
    23: (782.15, 644.97, 473.78, 60.40, 3.27, 76.81, 30.71, 26.31, 85.28, 25.59),
    24: (906.69, 752.51, 521.14, 107.45, 3.61, 84.48, 35.83, 30.70, 93.81, 29.67),
    25: (212.12, 184.36, 73.87, 89.74, 0, 11.97, 8.78, 7.52, 13.30, 6.94),
    26: (251.05, 217.41, 92.00, 100.16, 0, 14.90, 10.35, 8.87, 16.56, 8.21),
    27: (283.41, 245.04, 106.09, 110.09, 0, 17.19, 11.67, 10.00, 19.10, 9.27),
    28: (77.75, 66.66, 32.37, 25.88, 0, 5.24, 3.17, 2.72, 5.83, 2.54),
    29: (90.02, 76.94, 38.83, 28.16, 0, 6.29, 3.66, 3.14, 6.99, 2.95),
    30: (104.51, 89.07, 46.61, 30.67, 0, 7.55, 4.24, 3.63, 8.39, 3.42),
    31: (2341.45, 1907.42, 1553.33, 11.62, 0, 251.64, 90.83, 77.82, 279.60, 76.61),
    32: (3207.65, 2614.25, 2121.11, 25.03, 0, 343.62, 124.49, 106.66, 381.80, 104.94),
    33: (4105.61, 3345.53, 2718.09, 27.80, 0, 440.33, 159.31, 136.50, 489.26, 134.32),
}

labor = {
    19: (271.20, 2615.46), 20: (342.81, 2873.38), 21: (383.40, 3175.79),
    22: (36.88, 389.51), 23: (40.98, 432.80), 24: (45.08, 476.06),
    25: (11.08, 62.79), 26: (11.46, 80.54), 27: (11.73, 94.36),
    28: (2.80, 29.57), 29: (3.36, 35.47), 30: (4.03, 42.58),
    31: (134.32, 1419.01), 32: (183.43, 1937.68), 33: (235.04, 2483.05),
}

variants = {
    19: ("承插型盘扣式钢管双排脚手架", "搭拆 / 搭设高度H(m) / 0<H≤24", "100m²", 225),
    20: ("承插型盘扣式钢管双排脚手架", "搭拆 / 搭设高度H(m) / 24<H≤50", "100m²", 225),
    21: ("承插型盘扣式钢管双排脚手架", "搭拆 / 搭设高度H(m) / H>50", "100m²", 225),
    22: ("承插型盘扣式钢管双排脚手架", "搭拆 / 每增加一排立杆 / 搭设高度H(m) / 0<H≤24", "100m²", 226),
    23: ("承插型盘扣式钢管双排脚手架", "搭拆 / 每增加一排立杆 / 搭设高度H(m) / 24<H≤50", "100m²", 226),
    24: ("承插型盘扣式钢管双排脚手架", "搭拆 / 每增加一排立杆 / 搭设高度H(m) / H>50", "100m²", 226),
    25: ("承插型盘扣式钢管双排脚手架", "使用 / 搭设高度H(m) / 0<H≤24", "100m²·10天", 227),
    26: ("承插型盘扣式钢管双排脚手架", "使用 / 搭设高度H(m) / 24<H≤50", "100m²·10天", 227),
    27: ("承插型盘扣式钢管双排脚手架", "使用 / 搭设高度H(m) / H>50", "100m²·10天", 227),
    28: ("承插型盘扣式钢管双排脚手架", "使用 / 每增加一排立杆 / 搭设高度H(m) / 0<H≤24", "100m²·10天", 228),
    29: ("承插型盘扣式钢管双排脚手架", "使用 / 每增加一排立杆 / 搭设高度H(m) / 24<H≤50", "100m²·10天", 228),
    30: ("承插型盘扣式钢管双排脚手架", "使用 / 每增加一排立杆 / 搭设高度H(m) / H>50", "100m²·10天", 228),
    31: ("承插型盘扣式钢管单排脚手架", "搭拆 / 搭设高度H(m) / 0<H≤6", "100m²", 229),
    32: ("承插型盘扣式钢管单排脚手架", "搭拆 / 搭设高度H(m) / 6<H≤14", "100m²", 229),
    33: ("承插型盘扣式钢管单排脚手架", "搭拆 / 搭设高度H(m) / 14<H≤24", "100m²", 229),
}


def material_rows(number):
    index = (number - 1) % 3
    if 19 <= number <= 21:
        rows = [
            ("镀锌铁丝（综合）", "kg", (5.473, 15.520, 27.168), 6.05),
            ("电焊条 E4303 φ3.2", "kg", (.025, .146, .325), 8.62),
            ("工字钢（综合）", "t", (.029, .078, .112), 4671.00),
            ("其他材料费", "%", (5, 5, 5), 1.00),
        ]
    elif 22 <= number <= 24:
        rows = [
            ("镀锌铁丝（综合）", "kg", (.650, .684, .739), 6.05),
            ("电焊条 E4303 φ3.2", "kg", (None, .024, .026), 8.62),
            ("工字钢（综合）", "t", (.005, .012, .022), 4671.00),
        ]
    elif 25 <= number <= 27:
        rows = [
            ("承插型盘扣式钢管脚手架（成套）（租赁10天）", "kg", (1445.130, 1612.806, 1772.806), .06),
            ("其他材料费", "%", (3.5, 3.5, 3.5), 1.00),
        ]
    elif 28 <= number <= 30:
        rows = [
            ("承插型盘扣式钢管脚手架（成套）（租赁10天）", "kg", (431.267, 469.351, 511.243), .06),
        ]
    else:
        rows = [
            ("镀锌铁丝（综合）", "kg", (1.830, 3.940, 4.210), 6.05),
            ("电焊条 E4303 φ3.2", "kg", (None, None, .117), 8.62),
            ("其他材料费", "%", (5, 5, 5), 1.00),
        ]
    return [(name, unit, quantities[index], price) for name, unit, quantities, price in rows]


load_dotenv(".env")
conn = get_connection()
try:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM bs2024_item_groups
            WHERE document_id=%s AND group_code='7.3.1'
            ORDER BY id LIMIT 1
            """,
            (DOC,),
        )
        group_id = cur.fetchone()[0]
        cur.execute(
            """
            SELECT i.id FROM bs2024_items i JOIN bs2024_subitems s ON s.item_id=i.id
            WHERE s.document_id=%s AND s.subitem_code='010007-19'
            ORDER BY i.id LIMIT 1
            """,
            (DOC,),
        )
        row = cur.fetchone()
        work = "安底座、立杆、接杆及上部挑出承托、连墙件、型钢支撑、卸料平台等搭设和拆除全过程，脚手架拆除后的材料整理、刷油、堆放及场内运输。"
        if row:
            item_id = row[0]
            cur.execute(
                """
                UPDATE bs2024_items SET group_id=%s,item_no=2,
                  item_name='承插型盘扣式钢管外脚手架',work_content=%s,
                  unit=NULL,page_no=225,sort_order=2 WHERE id=%s
                """,
                (group_id, work, item_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO bs2024_items
                  (document_id,group_id,item_no,item_name,work_content,page_no,sort_order)
                VALUES (%s,%s,2,'承插型盘扣式钢管外脚手架',%s,225,2)
                RETURNING id
                """,
                (DOC, group_id, work),
            )
            item_id = cur.fetchone()[0]

        for number in range(19, 34):
            subitem_name, variant, unit, page = variants[number]
            path = ["外脚手架", "承插型盘扣式钢管外脚手架", subitem_name, *variant.split(" / ")]
            code = f"010007-{number}"
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
                    item_id, subitem_name, variant, unit,
                    json.dumps(path, ensure_ascii=False),
                    *[d(value) for value in costs[number]],
                    page, number, DOC, code,
                ),
            )
            subitem_id = cur.fetchone()[0]
            cur.execute("DELETE FROM bs2024_resources WHERE subitem_id=%s", (subitem_id,))
            resources = [
                ("人工", "普通人工费", "元", labor[number][0], None),
                ("人工", "技工人工费", "元", labor[number][1], None),
            ]
            resources.extend(
                ("材料", name, resource_unit, quantity, price)
                for name, resource_unit, quantity, price in material_rows(number)
            )
            if 19 <= number <= 24:
                quantities = {
                    19: .002, 20: .020, 21: .024,
                    22: None, 23: .019, 24: .021,
                }
                resources.append(
                    ("机械", "交流电焊机 容量E(kV·A) E=30", "台班", quantities[number], 172.10)
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
            UPDATE bs2024_item_groups SET page_end=229
            WHERE document_id=%s AND id=%s
            """,
            (DOC, group_id),
        )
        cur.execute(
            """
            UPDATE bs2024_pages SET chapter_no=7,chapter_title='脚手架工程',
              section_code='7.3',section_type='items'
            WHERE document_id=%s AND page_no BETWEEN 225 AND 229
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

print("Corrected Chapter 7 subitems 010007-19 through 010007-33.")
