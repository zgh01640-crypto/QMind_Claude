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
    66: (14930.62, 12440.57, 8299.90, 2201.99, 1.66, 1344.61, 592.41, 507.58, 1493.98, 488.49),
    67: (12288.83, 10217.30, 6958.89, 1642.84, 1.66, 1127.37, 486.54, 416.87, 1252.60, 402.06),
    68: (12998.08, 10867.58, 7010.24, 2203.04, 1.12, 1135.68, 517.50, 443.40, 1261.84, 425.26),
    69: (11772.02, 9931.37, 5835.02, 2676.47, 1.66, 945.30, 472.92, 405.20, 1050.30, 385.15),
    70: (15044.44, 12488.24, 8635.88, 1857.53, 1.12, 1399.03, 594.68, 509.52, 1554.46, 492.22),
    71: (20680.30, 17167.78, 11863.71, 2539.56, 24.68, 1922.32, 817.51, 700.45, 2135.47, 676.60),
    72: (18613.17, 15440.52, 10742.77, 2220.47, 1.66, 1740.36, 735.26, 629.97, 1933.70, 608.98),
    73: (21904.47, 18130.41, 12876.07, 2303.93, 1.12, 2085.94, 863.35, 739.72, 2317.69, 716.65),
    74: (8524.97, 7079.12, 4878.41, 1072.17, 1.12, 790.32, 337.10, 288.83, 878.11, 278.91),
    75: (7802.45, 6489.59, 4404.50, 1061.39, 1.12, 713.55, 309.03, 264.78, 792.81, 255.27),
    76: (12828.68, 10628.95, 7479.74, 1430.21, 1.12, 1211.74, 506.14, 433.66, 1346.35, 419.72),
    77: (6841.71, 5757.08, 3477.24, 1441.52, .84, 563.33, 274.15, 234.89, 625.90, 223.84),
    78: (10414.16, 8750.36, 5366.99, 2074.70, 22.18, 869.81, 416.68, 357.01, 966.06, 340.73),
    79: (10764.74, 9083.79, 5322.96, 2464.26, 1.66, 862.35, 432.56, 370.62, 958.13, 352.20),
    80: (9194.48, 7739.14, 4659.80, 1954.78, 1.12, 754.91, 368.53, 315.76, 838.76, 300.82),
    81: (9217.32, 7748.18, 4730.23, 1875.65, 6.93, 766.41, 368.96, 316.13, 851.44, 301.57),
    82: (12077.76, 10048.55, 6800.43, 1630.89, 36.47, 1102.26, 478.50, 409.98, 1224.08, 395.15),
}

defs = {
    66: (1, "水塔、倒锥水塔水箱模板", "水塔塔身模板", "筒式", 202),
    67: (1, "水塔、倒锥水塔水箱模板", "水塔塔身模板", "柱式", 202),
    68: (1, "水塔、倒锥水塔水箱模板", "水塔塔底塔顶模板", None, 202),
    69: (1, "水塔、倒锥水塔水箱模板", "塔箱水槽内外壁模板", None, 203),
    70: (1, "水塔、倒锥水塔水箱模板", "塔箱回廊平台模板", None, 203),
    71: (1, "水塔、倒锥水塔水箱模板", "倒锥壳水塔水箱", "容量C(t) / 0<C≤300", 204),
    72: (1, "水塔、倒锥水塔水箱模板", "倒锥壳水塔水箱", "容量C(t) / 300<C≤400", 204),
    73: (1, "水塔、倒锥水塔水箱模板", "倒锥壳水塔水箱", "容量C(t) / 400<C≤500", 204),
    74: (2, "贮水（油）池模板", "平池底模板", None, 205),
    75: (2, "贮水（油）池模板", "坡池底模板", None, 205),
    76: (2, "贮水（油）池模板", "沉淀池壁基梁模板", None, 205),
    77: (2, "贮水（油）池模板", "矩形池壁模板", None, 206),
    78: (2, "贮水（油）池模板", "圆形池壁模板", None, 206),
    79: (2, "贮水（油）池模板", "池中柱模板", None, 206),
    80: (2, "贮水（油）池模板", "带梁池盖模板", None, 207),
    81: (2, "贮水（油）池模板", "无梁池盖模板", None, 207),
    82: (2, "贮水（油）池模板", "沉淀池水槽模板", None, 207),
}

labor = {
    66: (1457.32, 6842.58), 67: (1221.86, 5737.03), 68: (1230.88, 5779.36),
    69: (1024.53, 4810.49), 70: (1516.31, 7119.57),
    71: (2083.07, 9780.64), 72: (1886.25, 8856.52), 73: (2260.82, 10615.25),
    74: (856.57, 4021.84), 75: (773.35, 3631.15), 76: (1313.32, 6166.42),
    77: (610.54, 2866.70), 78: (942.36, 4424.63), 79: (934.62, 4388.34),
    80: (818.18, 3841.62), 81: (830.55, 3899.68), 82: (1194.04, 5606.39),
}

red = lambda q: r("材料", "涂胶建筑模板（红板）1 830×915×15", "张", q, 54)
wood = lambda q: r("材料", "松杂枋板材（周转材）", "m³", q, 2016)
wire = lambda q: r("材料", "镀锌铁丝（综合）", "kg", q, 6.05)
nail = lambda q: r("材料", "铁钉（综合）", "kg", q, 6.37)
iron = lambda q: r("材料", "铁件（综合）", "kg", q, 6.96)
rope = lambda q: r("材料", "钢丝绳", "kg", q, 11)
release = lambda q: r("材料", "脱模剂", "kg", q, 8.4)
other = lambda q: r("材料", "其他材料费", "%", q, 1)
saw = lambda q: r("机械", "木工圆锯机 直径D(mm) D=500", "台班", q, 30.14)

resources = {
    66: [red(5.279), wood(.477), nail(27.020), iron(91.240), release(10), other(3), saw(.055)],
    67: [red(4.891), wood(.533), nail(16.130), iron(10), release(10), other(3), saw(.055)],
    68: [red(6.098), wood(.516), wire(23.950), nail(37.320), iron(43.490), release(10), other(3), saw(.037)],
    69: [red(6.098), wood(.464), nail(34.700), iron(147.810), release(10), other(3), saw(.055)],
    70: [red(6.098), wood(.443), nail(78.030), release(10), other(3), saw(.037)],
    71: [red(8.271), wood(.587), rope(.750), nail(17), iron(91.240), release(10), other(3), saw(.819)],
    72: [red(8.271), wood(.536), rope(1.250), nail(13.090), iron(64.290), release(10), other(3), saw(.055)],
    73: [red(8.271), wood(.537), rope(1.260), nail(14.300), iron(74.520), release(10), other(3), saw(.037)],
    74: [red(5.082), wood(.249), nail(28.340), release(10), other(3), saw(.037)],
    75: [red(5.082), wood(.289), nail(14.040), release(10), other(3), saw(.037)],
    76: [red(5.082), wood(.448), nail(19.930), release(10), other(3), saw(.037)],
    77: [red(6.098), wood(.372), wire(6.100), nail(13.820), iron(17.970), release(10), other(2), saw(.028)],
    78: [red(6.098), wood(.428), wire(10.740), nail(15.740), iron(85.150), release(10), other(2), saw(.736)],
    79: [red(5.082), wood(.393), wire(53.830), nail(76.290), iron(65.170), release(10), other(2), saw(.055)],
    80: [red(4.790), wood(.464), nail(21.810), release(10), wire(38.630), iron(38.180), other(2), saw(.037)],
    81: [red(4.790), wood(.454), nail(42.020), release(10), wire(1.590), iron(43.630), other(2), saw(.230)],
    82: [red(6.098), wood(.547), nail(13.010), release(10), other(2), saw(1.210)],
}

WORK = "模板及支架制作、安装、拆除、整理堆放、运输，清理模板粘结物及模内杂物，刷隔离剂，封堵孔洞等。"

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
        cur.execute(
            "SELECT id FROM bs2024_item_groups WHERE document_id=%s AND section_id=%s AND group_code='6.3.2' ORDER BY id LIMIT 1",
            (DOC, section_id),
        )
        row = cur.fetchone()
        if row:
            group_id = row[0]
            cur.execute(
                "UPDATE bs2024_item_groups SET group_name='现浇混凝土构筑物模板',page_start=202,page_end=207,sort_order=2 WHERE id=%s",
                (group_id,),
            )
        else:
            cur.execute(
                """
                INSERT INTO bs2024_item_groups
                  (document_id,section_id,group_code,group_name,page_start,page_end,sort_order)
                VALUES (%s,%s,'6.3.2','现浇混凝土构筑物模板',202,207,2) RETURNING id
                """,
                (DOC, section_id),
            )
            group_id = cur.fetchone()[0]

        item_ids = {}
        for item_no, item_name, page in ((1, "水塔、倒锥水塔水箱模板", 202), (2, "贮水（油）池模板", 205)):
            cur.execute(
                "SELECT id FROM bs2024_items WHERE document_id=%s AND group_id=%s AND item_no=%s ORDER BY id LIMIT 1",
                (DOC, group_id, item_no),
            )
            row = cur.fetchone()
            if row:
                item_id = row[0]
                cur.execute(
                    "UPDATE bs2024_items SET item_name=%s,work_content=%s,page_no=%s,sort_order=%s WHERE id=%s",
                    (item_name, WORK, page, item_no, item_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_items
                      (document_id,group_id,item_no,item_name,work_content,page_no,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (DOC, group_id, item_no, item_name, WORK, page, item_no),
                )
                item_id = cur.fetchone()[0]
            item_ids[item_no] = item_id

        for number in range(66, 83):
            item_no, item_name, sub_name, variant, page = defs[number]
            path = ["现浇混凝土构筑物模板", item_name, sub_name]
            if variant:
                path.extend(variant.split(" / "))
            cur.execute(
                """
                INSERT INTO bs2024_subitems
                  (document_id,item_id,subitem_code,subitem_name,variant_desc,unit,name_path_json,
                   total_unit_price,unit_price,labor_cost,material_cost,machine_cost,management_fee,
                   profit,safety_fee,statutory_fee,tax,page_no,confidence,sort_order)
                VALUES (%s,%s,%s,%s,%s,'100m²',%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s)
                ON CONFLICT (document_id,subitem_code) DO UPDATE SET
                  item_id=EXCLUDED.item_id,subitem_name=EXCLUDED.subitem_name,
                  variant_desc=EXCLUDED.variant_desc,unit=EXCLUDED.unit,name_path_json=EXCLUDED.name_path_json,
                  total_unit_price=EXCLUDED.total_unit_price,unit_price=EXCLUDED.unit_price,
                  labor_cost=EXCLUDED.labor_cost,material_cost=EXCLUDED.material_cost,
                  machine_cost=EXCLUDED.machine_cost,management_fee=EXCLUDED.management_fee,
                  profit=EXCLUDED.profit,safety_fee=EXCLUDED.safety_fee,
                  statutory_fee=EXCLUDED.statutory_fee,tax=EXCLUDED.tax,
                  page_no=EXCLUDED.page_no,confidence=1,sort_order=EXCLUDED.sort_order
                RETURNING id
                """,
                (DOC, item_ids[item_no], f"010006-{number}", sub_name, variant,
                 json.dumps(path, ensure_ascii=False), *[d(v) for v in costs[number]], page, number),
            )
            sid = cur.fetchone()[0]
            cur.execute("DELETE FROM bs2024_resources WHERE subitem_id=%s", (sid,))
            rows = [
                r("人工", "普通人工费", "元", labor[number][0], None),
                r("人工", "技工人工费", "元", labor[number][1], None),
                *resources[number],
            ]
            for order, values in enumerate(rows, 1):
                cur.execute(
                    """
                    INSERT INTO bs2024_resources
                      (document_id,subitem_id,resource_type,resource_name,unit,quantity,ref_price,page_no,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (DOC, sid, *values, page, order),
                )

        cur.execute(
            "UPDATE bs2024_pages SET chapter_no=6,chapter_title='模板工程' WHERE document_id=%s AND page_no BETWEEN 202 AND 207",
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

print("Corrected Chapter 6 subitems 010006-66 through 010006-82.")
