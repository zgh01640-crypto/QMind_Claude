from decimal import Decimal
import json

from dotenv import load_dotenv

from db.connection import get_connection


DOC = 25


def d(value):
    return None if value is None else Decimal(str(value))


COSTS = {
    47: (86.24, 70.20, 57.54, 0, 0, 9.32, 3.34, 2.86, 10.36, 2.82),
    48: (34.63, 28.19, 23.11, 0, 0, 3.74, 1.34, 1.15, 4.16, 1.13),
    49: (99.18, 80.73, 66.17, 0, 0, 10.72, 3.84, 3.29, 11.91, 3.25),
    50: (41.56, 33.83, 27.73, 0, 0, 4.49, 1.61, 1.38, 4.99, 1.36),
    51: (36.19, 29.45, 24.14, 0, 0, 3.91, 1.40, 1.20, 4.35, 1.19),
    52: (6.88, 5.60, 4.59, 0, 0, .74, .27, .23, .83, .22),
    53: (43.43, 35.35, 28.98, 0, 0, 4.69, 1.68, 1.44, 5.22, 1.42),
    54: (8.24, 6.71, 5.50, 0, 0, .89, .32, .27, .99, .27),
    55: (58.18, 47.36, 38.81, 0, 0, 6.29, 2.26, 1.93, 6.99, 1.90),
    56: (11.07, 9.01, 7.38, 0, 0, 1.20, .43, .37, 1.33, .36),
    57: (141.48, 119.83, 67.39, 0, 35.24, 11.49, 5.71, 4.89, 12.13, 4.63),
    58: (3.96, 3.68, 0, 0, 3.44, .06, .18, .15, 0, .13),
    59: (161.25, 136.45, 77.51, 0, 39.25, 13.19, 6.50, 5.57, 13.95, 5.28),
    60: (4.26, 3.97, 0, 0, 3.72, .06, .19, .16, 0, .13),
}


SPECS = {
    47: ("9.3.5", "玻璃", "厚度T(mm) / 0<T≤20 / 运距L(m) / 0<L≤50", "100m²", 264),
    48: ("9.3.5", "玻璃", "厚度T(mm) / 0<T≤20 / 运距L(m) / L>50 / 每增100以内", "100m²", 264),
    49: ("9.3.5", "玻璃", "厚度T(mm) / T>20 / 运距L(m) / 0<L≤50", "100m²", 264),
    50: ("9.3.5", "玻璃", "厚度T(mm) / T>20 / 运距L(m) / L>50 / 每增100以内", "100m²", 264),
    51: ("9.3.5", "瓷质线条", "线条 / 运距L(m) / 0<L≤50", "100m", 265),
    52: ("9.3.5", "瓷质线条", "线条 / 运距L(m) / L>50 / 每增100以内", "100m", 265),
    53: ("9.3.5", "石膏线条", "线条 / 运距L(m) / 0<L≤50", "100m", 265),
    54: ("9.3.5", "石膏线条", "线条 / 运距L(m) / L>50 / 每增100以内", "100m", 265),
    55: ("9.3.5", "铸铁排污管", "运距L(m) / 0<L≤50", "100m", 266),
    56: ("9.3.5", "铸铁排污管", "运距L(m) / L>50 / 每增100以内", "100m", 266),
    57: ("9.3.6", "钢筋", "运距L(m) / 0<L≤1000", "t", 267),
    58: ("9.3.6", "钢筋", "运距L(m) / 每增500以内", "t", 267),
    59: ("9.3.6", "成型钢筋", "运距L(m) / 0<L≤1000", "t", 267),
    60: ("9.3.6", "成型钢筋", "运距L(m) / 每增500以内", "t", 267),
}


APPENDIX_MD = """# 附录 A 材料、机械台班参考价格表

## 表 A 材料、机械台班参考价格表

| 序号 | 名称 | 单位 | 价格（元） |
|---:|---|:---:|---:|
| 1 | 加气混凝土砌块（5.0MPa） | m³ | 317.00 |
| 2 | 普通混凝土空心砌块 390×190×90（5.0MPa） | 千块 | 2480.00 |
| 3 | 普通混凝土空心砌块 390×190×140（5.0MPa） | 千块 | 3550.00 |
| 4 | 普通混凝土空心砌块 390×190×190（5.0MPa） | 千块 | 4470.00 |
| 5 | 普通混凝土实心砖 240×115×53（10.0MPa） | 千块 | 850.00 |
| 6 | 蒸压加气混凝土高精砌块 | m³ | 380.00 |
| 7 | 普通预拌混凝土 C10 骨料最大粒径31.5 | m³ | 486.40 |
| 8 | 普通预拌混凝土 C15 骨料最大粒径31.5 | m³ | 511.74 |
| 9 | 普通预拌混凝土 C20 骨料最大粒径31.5 | m³ | 526.90 |
| 10 | 普通预拌混凝土 C30 骨料最大粒径31.5 | m³ | 573.41 |
| 11 | 泵送预拌混凝土 C10 骨料最大粒径31.5 | m³ | 493.85 |
| 12 | 泵送预拌混凝土 C25 骨料最大粒径31.5 | m³ | 568.38 |
| 13 | 泵送预拌混凝土 C30 骨料最大粒径31.5 | m³ | 582.85 |
| 14 | 细石混凝土 C20 | m³ | 546.90 |
| 15 | 热轧光圆钢筋 HPB300 Φ8～Φ10 盘卷 | t | 4311.00 |
| 16 | 热轧光圆钢筋 HPB300 Φ>10 | t | 4803.00 |
| 17 | 热轧带肋钢筋 HRB400E Φ8～Φ10 盘卷 | t | 4311.00 |
| 18 | 热轧带肋钢筋 HRB400E Φ10 | t | 4321.00 |
| 19 | 热轧带肋钢筋 HRB400E Φ12 | t | 4215.00 |
| 20 | 热轧带肋钢筋 HRB400E Φ14 | t | 4175.00 |
| 21 | 热轧带肋钢筋 HRB400E Φ16 | t | 4134.00 |
| 22 | 热轧带肋钢筋 HRB400E Φ18 | t | 4082.00 |
| 23 | 热轧带肋钢筋 HRB400E Φ20 | t | 4100.00 |
| 24 | 热轧带肋钢筋 HRB400E Φ22 | t | 4107.00 |
| 25 | 热轧带肋钢筋 HRB400E Φ25 | t | 4133.00 |
| 26 | 热轧带肋钢筋 HRB400E Φ10～Φ25 | t | 4116.00 |
| 27 | 热轧带肋钢筋 HRB400E Φ28～Φ32 | t | 4234.00 |
| 28 | 热轧带肋钢筋 HRB400E Φ36～Φ40 | t | 4404.00 |
| 29 | 钢筋网片（成品）Φ6@200×200 | t | 6051.00 |
| 30 | 冷轧带肋钢筋 定长12m | t | 6285.00 |
| 31 | 直螺纹连接套筒 Φ≤25 | 个 | 2.48 |
| 32 | 直螺纹连接套筒 Φ≤32 | 个 | 3.83 |
| 33 | 直螺纹连接套筒 32<Φ≤45 | 个 | 7.35 |
"""


load_dotenv(".env")
conn = get_connection()
try:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id,s.id FROM bs2024_chapters c
            JOIN bs2024_sections s ON s.chapter_id=c.id
            WHERE c.document_id=%s AND c.chapter_no=9 AND s.section_code='9.3'
            ORDER BY s.id LIMIT 1
            """,
            (DOC,),
        )
        chapter_id, section_id = cur.fetchone()
        cur.execute("UPDATE bs2024_chapters SET page_end=267 WHERE id=%s", (chapter_id,))
        cur.execute("UPDATE bs2024_sections SET page_end=267 WHERE id=%s", (section_id,))

        cur.execute(
            """
            UPDATE bs2024_item_groups SET page_end=266,sort_order=5
            WHERE document_id=%s AND group_code='9.3.5'
            """,
            (DOC,),
        )
        cur.execute(
            """
            SELECT id FROM bs2024_item_groups
            WHERE document_id=%s AND group_code='9.3.6' ORDER BY id LIMIT 1
            """,
            (DOC,),
        )
        row = cur.fetchone()
        if row:
            group6_id = row[0]
            cur.execute(
                """
                UPDATE bs2024_item_groups SET section_id=%s,
                  group_name='机动翻斗车场内运输钢筋',
                  page_start=267,page_end=267,sort_order=6 WHERE id=%s
                """,
                (section_id, group6_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO bs2024_item_groups
                  (document_id,section_id,group_code,group_name,page_start,page_end,sort_order)
                VALUES (%s,%s,'9.3.6','机动翻斗车场内运输钢筋',267,267,6)
                RETURNING id
                """,
                (DOC, section_id),
            )
            group6_id = cur.fetchone()[0]

        cur.execute(
            """
            SELECT id FROM bs2024_item_groups
            WHERE document_id=%s AND group_code='9.3.5' ORDER BY id LIMIT 1
            """,
            (DOC,),
        )
        group5_id = cur.fetchone()[0]
        item_ids = {}
        for code, group_id, name, first_code, page in (
            ("9.3.5", group5_id, "其他材料人力车二次运输", "010009-39", 262),
            ("9.3.6", group6_id, "机动翻斗车场内运输钢筋", "010009-57", 267),
        ):
            cur.execute(
                """
                SELECT i.id FROM bs2024_items i
                JOIN bs2024_subitems s ON s.item_id=i.id
                WHERE s.document_id=%s AND s.subitem_code=%s
                ORDER BY i.id LIMIT 1
                """,
                (DOC, first_code),
            )
            row = cur.fetchone()
            work = "材料的装车、运输、卸车、堆放整理。"
            if row:
                item_id = row[0]
                cur.execute(
                    """
                    UPDATE bs2024_items SET group_id=%s,item_no=1,item_name=%s,
                      work_content=%s,unit=NULL,page_no=%s,sort_order=1 WHERE id=%s
                    """,
                    (group_id, name, work, page, item_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_items
                      (document_id,group_id,item_no,item_name,work_content,page_no,sort_order)
                    VALUES (%s,%s,1,%s,%s,%s,1) RETURNING id
                    """,
                    (DOC, group_id, name, work, page),
                )
                item_id = cur.fetchone()[0]
            item_ids[code] = item_id

        group_names = {
            "9.3.5": "其他材料人力车二次运输",
            "9.3.6": "机动翻斗车场内运输钢筋",
        }
        for number in range(47, 61):
            group_code, name, variant, unit, page = SPECS[number]
            path = [group_names[group_code], name]
            path.extend(variant.split(" / "))
            cur.execute(
                """
                UPDATE bs2024_subitems SET item_id=%s,subitem_name=%s,
                  variant_desc=%s,unit=%s,name_path_json=%s::jsonb,
                  total_unit_price=%s,unit_price=%s,labor_cost=%s,
                  material_cost=%s,machine_cost=%s,management_fee=%s,
                  profit=%s,safety_fee=%s,statutory_fee=%s,tax=%s,
                  page_no=%s,confidence=1,sort_order=%s
                WHERE document_id=%s AND subitem_code=%s RETURNING id
                """,
                (
                    item_ids[group_code], name, variant, unit,
                    json.dumps(path, ensure_ascii=False),
                    *[d(value) for value in COSTS[number]],
                    page, number, DOC, f"010009-{number}",
                ),
            )
            subitem_id = cur.fetchone()[0]
            cur.execute("DELETE FROM bs2024_resources WHERE subitem_id=%s", (subitem_id,))
            resource_order = 1
            if COSTS[number][2]:
                cur.execute(
                    """
                    INSERT INTO bs2024_resources
                      (document_id,subitem_id,resource_type,resource_name,unit,
                       quantity,ref_price,page_no,sort_order)
                    VALUES (%s,%s,'人工','普通人工费','元',%s,NULL,%s,%s)
                    """,
                    (DOC, subitem_id, d(COSTS[number][2]), page, resource_order),
                )
                resource_order += 1
            if number >= 57:
                quantities = {57: .123, 58: .012, 59: .137, 60: .013}
                cur.execute(
                    """
                    INSERT INTO bs2024_resources
                      (document_id,subitem_id,resource_type,resource_name,unit,
                       quantity,ref_price,page_no,sort_order)
                    VALUES (%s,%s,'机械','机动翻斗车 装载质量M(t) M=1',
                      '台班',%s,286.47,%s,%s)
                    """,
                    (DOC, subitem_id, d(quantities[number]), page, resource_order),
                )

        cur.execute(
            """
            UPDATE bs2024_pages SET chapter_no=9,chapter_title='材料二次运输工程',
              section_code='9.3',section_type='items'
            WHERE document_id=%s AND page_no BETWEEN 264 AND 267
            """,
            (DOC,),
        )
        cur.execute(
            """
            UPDATE bs2024_pages SET page_type='other',chapter_no=NULL,
              chapter_title=NULL,section_type='other',section_code='A',
              title='附录A 材料、机械台班参考价格表',content_md=%s
            WHERE document_id=%s AND page_no=268
            """,
            (APPENDIX_MD, DOC),
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

print("Corrected Chapter 9 subitems 010009-47 through 010009-60 and Appendix A page 268.")
