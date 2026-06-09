from decimal import Decimal
import json
import re

from dotenv import load_dotenv

from db.connection import get_connection


DOC = 25


def clean_ocr(text):
    replacements = {
        "1 脚手架工程": "7 脚手架工程",
        "说 ^明": "说明",
        "脚于架": "脚手架",
        "肘间": "时间",
        "不娈": "不变",
        "娈化": "变化",
        "I.Sm": "1.5m",
        "1.Sm": "1.5m",
        "1.Sn": "1.5m",
        "3.Gm": "3.6m",
        "0.Gm": "0.6m",
        "Gm": "6m",
        "13.Sm": "13.5m",
        "1.2m³时": "1.2m时",
        "1.5m³": "1.5m",
        "3.6n": "3.6m",
        "3.5n": "3.5m",
        "I6m": "16m",
        "肘": "时",
        "凹人": "凹入",
        "连粱": "连梁",
        "外脚手架。里脚手架。满堂脚手架": "外脚手架、里脚手架、满堂脚手架",
        "双排。单排及多排": "双排、单排及多排",
        "阳台。凸窗": "阳台、凸窗",
        "门窗洞口。空圈": "门窗洞口、空圈",
        "楼梯间。设备房": "楼梯间、设备房",
        "100m? . 10天": "100m²·10天",
        "10m³ 10天": "10m·10天",
        "\"合 .天\"": "“台·天”",
        "\"台。次\"": "“台·次”",
        "\"台 。次\"": "“台·次”",
        "47.2 工程量计算规则": "7.2 工程量计算规则",
        "600。装饰工程": "60%、装饰工程",
        "工期 14": "工期 / 4",
        "爽以": "乘以",
        "IGm": "16m",
        "I.Sm": "1.5m",
        "ISm": "1.5m",
        "1.5皿": "1.5m",
        "1.2m³": "1.2m",
        "工程量按": "工程量按",
        "中3.2": "φ3.2",
        "卫4303": "E4303",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"(?m)^\s*(207|208|209|210|211)\s*$", "", text)
    text = re.sub(r"[。_](?=\s|$)", "。", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def markdown(title, texts):
    body = "\n\n".join(clean_ocr(text) for text in texts)
    body = re.sub(r"(?m)^(7\.[12](?:\.\d+)?)\s+", r"### \1 ", body)
    body = re.sub(r"(?m)^(\d+)\s+(?=\S)", r"\1. ", body)
    return f"## {title}\n\n{body}"


load_dotenv(".env")
conn = get_connection()
try:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT page_no,ocr_text FROM bs2024_pages WHERE document_id=%s AND page_no BETWEEN 214 AND 218 ORDER BY page_no",
            (DOC,),
        )
        page_text = {page: text or "" for page, text in cur.fetchall()}
        intro_md = markdown("7.1 说明", [page_text[n] for n in range(214, 217)])
        intro_md = intro_md.replace(
            "图7.1.7 建筑工程地上部分脚手架使用情祝示意图",
            "图 7.1.7 建筑工程地上部分脚手架使用情况示意图\n\n"
            "> 图示比例：主体施工至封顶占 60%，封顶至开始拆架占 10%，开始拆架至拆架结束占 30%。",
        )
        rules_md = markdown("7.2 工程量计算规则", [page_text[n] for n in range(217, 219)])
        rules_md = rules_md.replace(
            "里脚手架增加层 =(层高 -3.6m 11.2m (7.2.5)",
            "里脚手架增加层 =（层高 - 3.6m）/ 1.2m　（7.2.5）",
        )

        cur.execute(
            "SELECT id FROM bs2024_chapters WHERE document_id=%s AND chapter_no=7 ORDER BY id LIMIT 1",
            (DOC,),
        )
        row = cur.fetchone()
        if row:
            chapter_id = row[0]
            cur.execute(
                "UPDATE bs2024_chapters SET code='7',title='脚手架工程',page_start=214,page_end=243,sort_order=7 WHERE id=%s",
                (chapter_id,),
            )
        else:
            cur.execute(
                """
                INSERT INTO bs2024_chapters
                  (document_id,chapter_no,code,title,page_start,page_end,sort_order)
                VALUES (%s,7,'7','脚手架工程',214,243,7) RETURNING id
                """,
                (DOC,),
            )
            chapter_id = cur.fetchone()[0]

        sections = {}
        for section_type, code, title, content, start, end, order in (
            ("intro", "7.1", "说明", intro_md, 214, 216, 1),
            ("rules", "7.2", "工程量计算规则", rules_md, 217, 218, 2),
            ("items", "7.3", "子目构成表", None, 219, 243, 3),
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
                section_id = row[0]
                cur.execute(
                    """
                    UPDATE bs2024_sections SET section_type=%s,title=%s,content_md=%s,
                      page_start=%s,page_end=%s,sort_order=%s WHERE id=%s
                    """,
                    (section_type, title, content, start, end, order, section_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO bs2024_sections
                      (document_id,chapter_id,section_type,section_code,title,content_md,page_start,page_end,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (DOC, chapter_id, section_type, code, title, content, start, end, order),
                )
                section_id = cur.fetchone()[0]
            sections[code] = section_id

        cur.execute(
            """
            SELECT id FROM bs2024_item_groups
            WHERE document_id=%s AND section_id=%s AND group_code='7.3.1'
            ORDER BY id LIMIT 1
            """,
            (DOC, sections["7.3"]),
        )
        row = cur.fetchone()
        if row:
            group_id = row[0]
            cur.execute(
                "UPDATE bs2024_item_groups SET group_name='外脚手架',page_start=219,page_end=219,sort_order=1 WHERE id=%s",
                (group_id,),
            )
        else:
            cur.execute(
                """
                INSERT INTO bs2024_item_groups
                  (document_id,section_id,group_code,group_name,page_start,page_end,sort_order)
                VALUES (%s,%s,'7.3.1','外脚手架',219,219,1) RETURNING id
                """,
                (DOC, sections["7.3"]),
            )
            group_id = cur.fetchone()[0]

        cur.execute(
            """
            SELECT i.id FROM bs2024_items i JOIN bs2024_subitems s ON s.item_id=i.id
            WHERE s.document_id=%s AND s.subitem_code='010007-1' ORDER BY i.id LIMIT 1
            """,
            (DOC,),
        )
        row = cur.fetchone()
        work = "安底座、立杆、接杆及上部挑出承托、连墙件、型钢支撑、卸料平台等搭设和拆除全过程，脚手架拆除后的材料整理、刷油、堆放及场内运输。"
        if row:
            item_id = row[0]
            cur.execute(
                """
                UPDATE bs2024_items SET group_id=%s,item_no=1,item_name='扣件式钢管外脚手架',
                  work_content=%s,unit=NULL,page_no=219,sort_order=1 WHERE id=%s
                """,
                (group_id, work, item_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO bs2024_items
                  (document_id,group_id,item_no,item_name,work_content,page_no,sort_order)
                VALUES (%s,%s,1,'扣件式钢管外脚手架',%s,219,1) RETURNING id
                """,
                (DOC, group_id, work),
            )
            item_id = cur.fetchone()[0]

        costs = {
            1: ("0<H≤24", (5050.25, 4150.88, 3137.67, 306.90, .34, 508.31, 197.66, 169.36, 564.78, 165.23)),
            2: ("24<H≤50", (5996.45, 4968.30, 3495.85, 667.61, 1.89, 566.36, 236.59, 202.71, 629.25, 196.19)),
            3: ("H>50", (6939.10, 5779.64, 3870.16, 1003.10, 4.13, 627.03, 275.22, 235.81, 696.63, 227.02)),
        }
        ordinary = {1: 294.78, 2: 372.62, 3: 416.74}
        skilled = {1: 2842.89, 2: 3123.23, 3: 3453.42}
        material_rows = {
            "镀锌铁丝（综合）": ("kg", (5.473, 15.520, 27.168), 6.05),
            "工字钢（综合）": ("t", (.029, .078, .112), 4671),
            "电焊条 E4303 φ3.2": ("kg", (.025, .146, .325), 8.62),
            "防锈漆 红色": ("kg", (7.170, 10.120, 15.211), 16.23),
            "油漆溶剂油": ("kg", (.629, 1.065, 1.601), 11.33),
            "其他材料费": ("%", (5, 5, 5), 1),
        }
        machine_rows = {
            "交流电焊机 容量E(kV·A) E=30": ("台班", (.002, .011, .024), 172.10),
        }

        for number in (1, 2, 3):
            variant, values = costs[number]
            code = f"010007-{number}"
            path = ["外脚手架", "扣件式钢管外脚手架", "扣件式钢管双排脚手架", "搭拆", "搭设高度H(m)", variant]
            cur.execute(
                """
                UPDATE bs2024_subitems SET item_id=%s,subitem_name='扣件式钢管双排脚手架',
                  variant_desc=%s,unit='100m²',name_path_json=%s::jsonb,
                  total_unit_price=%s,unit_price=%s,labor_cost=%s,material_cost=%s,
                  machine_cost=%s,management_fee=%s,profit=%s,safety_fee=%s,
                  statutory_fee=%s,tax=%s,page_no=219,confidence=1,sort_order=%s
                WHERE document_id=%s AND subitem_code=%s RETURNING id
                """,
                (item_id, f"搭拆 / 搭设高度H(m) / {variant}", json.dumps(path, ensure_ascii=False),
                 *[Decimal(str(v)) for v in values], number, DOC, code),
            )
            subitem_id = cur.fetchone()[0]
            cur.execute("DELETE FROM bs2024_resources WHERE subitem_id=%s", (subitem_id,))
            rows = [
                ("人工", "普通人工费", "元", ordinary[number], None),
                ("人工", "技工人工费", "元", skilled[number], None),
            ]
            for name, (unit, quantities, price) in material_rows.items():
                rows.append(("材料", name, unit, quantities[number - 1], price))
            for name, (unit, quantities, price) in machine_rows.items():
                rows.append(("机械", name, unit, quantities[number - 1], price))
            for order, row in enumerate(rows, 1):
                cur.execute(
                    """
                    INSERT INTO bs2024_resources
                      (document_id,subitem_id,resource_type,resource_name,unit,quantity,ref_price,page_no,sort_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,219,%s)
                    """,
                    (DOC, subitem_id, *row, order),
                )

        cur.execute(
            "UPDATE bs2024_pages SET chapter_no=7,chapter_title='脚手架工程' WHERE document_id=%s AND page_no BETWEEN 214 AND 219",
            (DOC,),
        )
        cur.execute(
            "UPDATE bs2024_chapters SET page_end=33 WHERE document_id=%s AND chapter_no=1",
            (DOC,),
        )
        cur.execute(
            "DELETE FROM bs2024_chapters WHERE document_id=%s AND chapter_no=47",
            (DOC,),
        )
        cur.execute(
            """
            DELETE FROM bs2024_sections
            WHERE document_id=%s AND section_code LIKE '7.%%' AND chapter_id<>%s
            """,
            (DOC, chapter_id),
        )
        cur.execute(
            """
            DELETE FROM bs2024_sections s WHERE s.document_id=%s AND s.chapter_id=%s
              AND s.section_code NOT IN ('7.1','7.2','7.3')
            """,
            (DOC, chapter_id),
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

print("Corrected Chapter 7 pages 214-219 and subitems 010007-1 through 010007-3.")
