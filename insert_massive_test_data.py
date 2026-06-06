"""
插入海量完整测试数据到数据库 - 接近真实 PDF 结构
基于 SJG 171-2024 的实际定额分布
"""

import psycopg2
import sys
import io

# 修复编码
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

conn = psycopg2.connect(
    host='localhost',
    port=5433,
    database='qmind',
    user='qmind',
    password='qmind'
)

cur = conn.cursor()

try:
    # 获取标准
    cur.execute("SELECT id FROM quota2024_standards WHERE standard_code = 'SJG 171-2024'")
    result = cur.fetchone()
    standard_id = result[0] if result else None

    if not standard_id:
        raise Exception("标准不存在")

    # 清空数据
    cur.execute("DELETE FROM quota2024_groups WHERE section_id IN (SELECT id FROM quota2024_sections WHERE chapter_id IN (SELECT id FROM quota2024_chapters WHERE standard_id = %s AND chapter_no > 0))", (standard_id,))
    cur.execute("DELETE FROM quota2024_sections WHERE chapter_id IN (SELECT id FROM quota2024_chapters WHERE standard_id = %s AND chapter_no > 0)", (standard_id,))
    cur.execute("DELETE FROM quota2024_chapters WHERE standard_id = %s AND chapter_no > 0", (standard_id,))
    conn.commit()

    print(f"使用标准 ID: {standard_id}")

    # 真实的定额结构数据
    chapters_data = [
        (1, "砌筑工程", [
            ("1.3.1", "砖砌体", [
                ("实心砖", "m³", [
                    ("010001-1", "实心砖240×115×53", "干混砌筑砂浆"),
                    ("010001-2", "实心砖240×115×53", "湿拌砌筑砂浆"),
                    ("010001-3", "实心砖240×115×53", "现场搅拌砂浆"),
                ]),
                ("多孔砖", "m³", [
                    ("010002-1", "多孔砖190×190×190", "干混砌筑砂浆"),
                    ("010002-2", "多孔砖190×190×190", "湿拌砌筑砂浆"),
                    ("010002-3", "多孔砖240×115×190", "干混砌筑砂浆"),
                    ("010002-4", "多孔砖240×115×190", "湿拌砌筑砂浆"),
                ]),
            ]),
            ("1.3.2", "砌筑砂浆", [
                ("砂浆配合", "m³", [
                    ("010101-1", "混合砂浆M5", "各类基础"),
                    ("010101-2", "混合砂浆M7.5", "一般砌体"),
                    ("010101-3", "混合砂浆M10", "承重砌体"),
                    ("010101-4", "混合砂浆M15", "高强度要求"),
                ]),
            ]),
            ("1.3.3", "砌体加固", [
                ("植筋加固", "处", [
                    ("010201-1", "中等植筋", "普通混凝土"),
                    ("010201-2", "长植筋", "深加工要求"),
                ]),
                ("钢筋网加固", "m²", [
                    ("010202-1", "8网", "墙体加固"),
                    ("010202-2", "10网", "柱体加固"),
                ]),
            ]),
        ]),
        (2, "混凝土及钢筋混凝土工程", [
            ("2.3.1", "现浇预拌混凝土", [
                ("垫层混凝土", "10m³", [
                    ("020001-1", "垫层C15", "毛石垫层"),
                    ("020001-2", "垫层C20", "细石垫层"),
                    ("020001-3", "垫层C25", "防水垫层"),
                ]),
                ("基础混凝土", "10m³", [
                    ("020002-1", "基础C25", "独立基础"),
                    ("020002-2", "基础C30", "条形基础"),
                    ("020002-3", "基础C35", "筏形基础"),
                    ("020002-4", "基础C30", "地梁混凝土"),
                ]),
                ("梁混凝土", "10m³", [
                    ("020003-1", "梁C25", "一级建筑"),
                    ("020003-2", "梁C30", "二级建筑"),
                    ("020003-3", "梁C35", "高层建筑"),
                ]),
                ("板混凝土", "10m³", [
                    ("020004-1", "板C25", "普通楼板"),
                    ("020004-2", "板C30", "预应力板"),
                    ("020004-3", "板C35", "重载楼板"),
                ]),
                ("柱混凝土", "10m³", [
                    ("020005-1", "柱C30", "普通柱"),
                    ("020005-2", "柱C35", "高强度柱"),
                    ("020005-3", "柱C40", "超高层柱"),
                ]),
            ]),
            ("2.3.2", "钢筋工程", [
                ("钢筋制作", "t", [
                    ("020101-1", "直径12mm", "HPB300"),
                    ("020101-2", "直径16mm", "HRB400"),
                    ("020101-3", "直径20mm", "HRB400"),
                    ("020101-4", "直径25mm", "HRB500"),
                ]),
                ("钢筋安装", "t", [
                    ("020102-1", "基础钢筋", "绑扎安装"),
                    ("020102-2", "梁钢筋", "焊接安装"),
                    ("020102-3", "板钢筋", "绑扎安装"),
                ]),
            ]),
            ("2.3.3", "预制构件", [
                ("预制梁", "m", [
                    ("020201-1", "预制梁250×600", "普通型"),
                    ("020201-2", "预制梁280×700", "加强型"),
                ]),
                ("预制板", "m²", [
                    ("020202-1", "预制板150", "实心板"),
                    ("020202-2", "预制板180", "空心板"),
                ]),
            ]),
        ]),
        (3, "木结构工程", [
            ("3.3.1", "木构件", [
                ("梁构件", "m³", [
                    ("030001-1", "主梁200×300", "松木"),
                    ("030001-2", "主梁250×350", "硬木"),
                ]),
                ("柱构件", "m³", [
                    ("030002-1", "木柱150×150", "普通"),
                    ("030002-2", "木柱200×200", "强度梅"),
                ]),
            ]),
            ("3.3.2", "木制品", [
                ("木板安装", "m²", [
                    ("030101-1", "楼板安装", "20mm厚"),
                    ("030101-2", "屋面板安装", "30mm厚"),
                ]),
            ]),
        ]),
        (4, "屋面及防水工程", [
            ("4.3.1", "防水卷材", [
                ("SBS卷材", "m²", [
                    ("040001-1", "I型SBS", "2.5mm厚"),
                    ("040001-2", "II型SBS", "3mm厚"),
                    ("040001-3", "III型SBS", "4mm厚"),
                ]),
                ("APP卷材", "m²", [
                    ("040002-1", "I型APP", "2.5mm厚"),
                    ("040002-2", "II型APP", "3.5mm厚"),
                ]),
            ]),
            ("4.3.2", "防水涂料", [
                ("聚氨酯涂料", "m²", [
                    ("040101-1", "双组分PU", "厚度2mm"),
                    ("040101-2", "单组分PU", "厚度1.5mm"),
                ]),
            ]),
        ]),
    ]

    total_chapters = 0
    total_sections = 0
    total_groups = 0
    total_items = 0
    total_subitems = 0

    for chapter_no, chapter_name, groups in chapters_data:
        # 创建章
        cur.execute("""
            INSERT INTO quota2024_chapters (standard_id, chapter_no, code, name, sort_order)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (standard_id, chapter_no, str(chapter_no), chapter_name, chapter_no))
        chapter_id = cur.fetchone()[0]
        total_chapters += 1
        print(f"\n✓ 章 {chapter_no}: {chapter_name}")

        # 创建说明节
        intro_content = f"""## {chapter_no}.1 {chapter_name}说明

本章适用于 {chapter_name} 工程。

### 适用范围
根据工程特点分为以下几类：
- 基础工程
- 主体工程
- 装饰工程

### 计价原则

| 项目等级 | 说明 | 系数 |
|--------|------|------|
| 一级 | 普通工程 | 1.0 |
| 二级 | 复杂工程 | 1.1 |
| 三级 | 特殊工程 | 1.2 |
"""

        cur.execute("""
            INSERT INTO quota2024_sections (chapter_id, section_type, section_code, title, content_md, page_start, page_end)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (chapter_id, 'intro', f'{chapter_no}.1', '说明', intro_content, 1, 10))
        total_sections += 1

        # 创建规则节
        rules_content = f"""## {chapter_no}.2 {chapter_name}工程量计算规则

### 计算原则
按设计图示尺寸以实际数量计算。

### 超高增加费
高度超过20m时，按如下系数计算：

| 高度范围(m) | 增加系数 |
|------------|--------|
| 20-30 | 1.05 |
| 30-50 | 1.10 |
| >50 | 1.15 |
"""

        cur.execute("""
            INSERT INTO quota2024_sections (chapter_id, section_type, section_code, title, content_md, page_start, page_end)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (chapter_id, 'rules', f'{chapter_no}.2', '工程量计算规则', rules_content, 11, 25))
        total_sections += 1

        # 创建子目构成表节
        cur.execute("""
            INSERT INTO quota2024_sections (chapter_id, section_type, section_code, title, content_md, page_start, page_end)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (chapter_id, 'items', f'{chapter_no}.3', '子目构成表', None, 26, 100))
        items_section_id = cur.fetchone()[0]
        total_sections += 1

        # 创建分组和项目
        for group_code, group_name, items in groups:
            cur.execute("""
                INSERT INTO quota2024_groups (section_id, group_code, group_name, sort_order)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (items_section_id, group_code, group_name, int(group_code.split('.')[-1])))
            group_id = cur.fetchone()[0]
            total_groups += 1

            for item_idx, (item_name, unit, subitems) in enumerate(items, 1):
                cur.execute("""
                    INSERT INTO quota2024_items (group_id, item_no, item_name, work_content, unit, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (group_id, item_idx, item_name, f"包括{item_name}的完整施工内容", unit, item_idx))
                item_id = cur.fetchone()[0]
                total_items += 1

                # 创建子目
                for sub_idx, (subitem_code, subitem_name, variant_desc) in enumerate(subitems, 1):
                    base_price = 200 + sub_idx * 100
                    total_price = base_price * 1.2
                    unit_price = base_price
                    labor = base_price * 0.3
                    material = base_price * 0.5
                    machine = base_price * 0.1
                    mgmt = base_price * 0.05
                    profit = base_price * 0.03
                    safety = base_price * 0.02
                    stat_fee = base_price * 0.01
                    tax = total_price - unit_price

                    cur.execute("""
                        INSERT INTO quota2024_subitems
                        (item_id, subitem_code, subitem_name, variant_desc,
                         total_unit_price, unit_price,
                         labor_cost, material_cost, machine_cost,
                         management_fee, profit, safety_fee, statutory_fee, tax, sort_order)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (item_id, subitem_code, subitem_name, variant_desc,
                          total_price, unit_price, labor, material, machine,
                          mgmt, profit, safety, stat_fee, tax, sub_idx - 1))
                    subitem_id = cur.fetchone()[0]
                    total_subitems += 1

                    # 创建工料机
                    resources_data = [
                        ('人工', '普通工', '工', 0.8),
                        ('人工', '技工', '工', 0.3),
                        ('材料', '主要材料', '吨', 0.5 * sub_idx),
                        ('材料', '辅助材料', '吨', 0.2 * sub_idx),
                        ('机械', '主要机械', '台班', 0.1 * sub_idx),
                    ]

                    ref_prices = {
                        '普通工': 100,
                        '技工': 150,
                        '主要材料': 400 * sub_idx,
                        '辅助材料': 100 * sub_idx,
                        '主要机械': 800 * sub_idx,
                    }

                    for res_type, res_name, unit_res, qty in resources_data:
                        cur.execute("""
                            INSERT INTO quota2024_resources
                            (subitem_id, resource_type, resource_name, unit, quantity, ref_price, sort_order)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (subitem_id, res_type, res_name, unit_res, qty, ref_prices.get(res_name, 0), 0))

    conn.commit()

    print(f"\n✅ 海量完整测试数据插入完成！")
    print(f"\n数据摘要：")
    print(f"  - 章数: {total_chapters}")
    print(f"  - 节数: {total_sections}")
    print(f"  - 分组数: {total_groups}")
    print(f"  - 项目数: {total_items}")
    print(f"  - 子目数: {total_subitems}")

    cur.execute("SELECT COUNT(*) FROM quota2024_resources")
    total_resources = cur.fetchone()[0]
    print(f"  - 工料机数: {total_resources}")

except Exception as e:
    conn.rollback()
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    cur.close()
    conn.close()
