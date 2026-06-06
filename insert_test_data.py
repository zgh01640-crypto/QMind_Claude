"""
插入测试数据到数据库 - 用于演示前端功能
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
    # 1. 获取或创建标准
    cur.execute("SELECT id FROM quota2024_standards WHERE standard_code = 'SJG 171-2024'")
    result = cur.fetchone()
    if result:
        standard_id = result[0]
        print(f"✓ 使用现有标准 ID: {standard_id}")
        # 清空现有数据
        cur.execute("DELETE FROM quota2024_groups WHERE section_id IN (SELECT id FROM quota2024_sections WHERE chapter_id IN (SELECT id FROM quota2024_chapters WHERE standard_id = %s AND chapter_no > 0))", (standard_id,))
        cur.execute("DELETE FROM quota2024_sections WHERE chapter_id IN (SELECT id FROM quota2024_chapters WHERE standard_id = %s AND chapter_no > 0)", (standard_id,))
        cur.execute("DELETE FROM quota2024_chapters WHERE standard_id = %s AND chapter_no > 0", (standard_id,))
        conn.commit()
    else:
        cur.execute("""
            INSERT INTO quota2024_standards (standard_code, name, region, base_date, source_file)
            VALUES ('SJG 171-2024', '深圳市建筑工程消耗量标准', '深圳市', '2024-12-20', 'mydoc/深圳市建筑消耗量标准2024.pdf')
            RETURNING id
        """)
        standard_id = cur.fetchone()[0]
        conn.commit()
        print(f"✓ 创建标准 ID: {standard_id}")

    # 2. 创建章
    chapters = [
        (0, "0", "总则"),
        (1, "1", "砌筑工程"),
        (2, "2", "混凝土及钢筋混凝土工程"),
    ]

    chapter_ids = {}
    for chapter_no, code, name in chapters:
        cur.execute("""
            INSERT INTO quota2024_chapters (standard_id, chapter_no, code, name, sort_order)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (standard_id, chapter_no, code, name, chapter_no))
        chapter_ids[chapter_no] = cur.fetchone()[0]
        print(f"  ✓ 创建章 {chapter_no}: {name}")

    # 3. 为第2章创建三个节
    chapter_2_id = chapter_ids[2]

    section_ids = {}

    # 说明 (intro)
    cur.execute("""
        INSERT INTO quota2024_sections (chapter_id, section_type, section_code, title, content_md, page_start, page_end)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (chapter_2_id, 'intro', '2.1', '说明', """
## 2.1 混凝土工程说明

### 2.1.1 适用范围
本节适用于建筑工程中的现浇混凝土工程。

### 2.1.2 混凝土强度等级
- C20: 普通住宅
- C25: 一般建筑
- C30: 重要建筑
- C35: 特殊工程

### 2.1.3 施工工艺
| 工艺阶段 | 说明 |
|--------|------|
| 模板制作 | 使用木模或钢模 |
| 混凝土浇筑 | 分层浇筑，连续施工 |
| 养护 | 7天以上养护 |
""", 34, 39))
    section_ids['intro'] = cur.fetchone()[0]
    print(f"  ✓ 创建说明节")

    # 工程量计算规则 (rules)
    cur.execute("""
        INSERT INTO quota2024_sections (chapter_id, section_type, section_code, title, content_md, page_start, page_end)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (chapter_2_id, 'rules', '2.2', '工程量计算规则', """
## 2.2 混凝土工程量计算规则

### 2.2.1 现浇混凝土计算
按设计图示尺寸以体积计算。

#### 2.2.1.1 柱子
- 按柱截面与高度计算
- 扣除梁、板所占面积

#### 2.2.1.2 梁
- 按梁截面与跨距计算
- 与柱交接处按柱尺寸计算

### 2.2.2 超厚混凝土增加费
厚度大于1000mm时，按如下系数计算：

| 厚度范围(mm) | 增加系数 |
|-------------|--------|
| 1000-1500 | 1.05 |
| 1500-2000 | 1.10 |
| >2000 | 1.15 |
""", 40, 50))
    section_ids['rules'] = cur.fetchone()[0]
    print(f"  ✓ 创建规则节")

    # 子目构成表 (items)
    cur.execute("""
        INSERT INTO quota2024_sections (chapter_id, section_type, section_code, title, content_md, page_start, page_end)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (chapter_2_id, 'items', '2.3', '子目构成表', None, 51, 90))
    section_ids['items'] = cur.fetchone()[0]
    print(f"  ✓ 创建子目节")

    # 4. 创建分组
    cur.execute("""
        INSERT INTO quota2024_groups (section_id, group_code, group_name, sort_order)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (section_ids['items'], '2.3.1', '现浇预拌混凝土', 0))
    group_id = cur.fetchone()[0]
    print(f"  ✓ 创建分组 2.3.1")

    # 5. 创建项目
    cur.execute("""
        INSERT INTO quota2024_items (group_id, item_no, item_name, work_content, unit, sort_order)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (group_id, 1, '泵送现浇混凝土', '包括混凝土运输、泵送、浇筑、振捣、找平等工作', '10m³', 0))
    item_id = cur.fetchone()[0]
    print(f"  ✓ 创建项目1: 泵送现浇混凝土")

    # 6. 创建子目
    subitems_data = [
        ('010002-1', '垫层', 'C20', 350.00, 280.00, 80.00, 150.00, 20.00, 15.00, 10.00, 3.00, 2.00, 3.00),
        ('010002-2', '基础', 'C25', 420.00, 330.00, 100.00, 180.00, 25.00, 20.00, 12.00, 4.00, 2.50, 4.50),
        ('010002-3', '梁板', 'C30', 480.00, 380.00, 120.00, 200.00, 30.00, 22.00, 14.00, 5.00, 3.00, 6.00),
    ]

    subitem_ids = {}
    for code, name, desc, total_price, unit_price, labor, material, machine, mgmt, profit, safety, stat_fee, tax in subitems_data:
        cur.execute("""
            INSERT INTO quota2024_subitems
            (item_id, subitem_code, subitem_name, variant_desc,
             total_unit_price, unit_price,
             labor_cost, material_cost, machine_cost,
             management_fee, profit, safety_fee, statutory_fee, tax, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (item_id, code, name, desc, total_price, unit_price,
              labor, material, machine, mgmt, profit, safety, stat_fee, tax, len(subitem_ids)))
        subitem_ids[code] = cur.fetchone()[0]
        print(f"    ✓ 创建子目 {code}")

    # 7. 创建工料机
    resources_data = [
        ('010002-1', '人工', '普通工', '工', 0.5),
        ('010002-1', '人工', '技工', '工', 0.2),
        ('010002-1', '材料', '水泥', '吨', 0.4),
        ('010002-1', '材料', '砂', '方', 0.6),
        ('010002-1', '材料', '石子', '方', 1.0),
        ('010002-1', '机械', '混凝土搅拌车', '台班', 0.05),
        ('010002-1', '机械', '混凝土泵', '台班', 0.08),
    ]

    for subitem_code, res_type, res_name, unit, qty in resources_data:
        subitem_id = subitem_ids[subitem_code]

        # 查询参考价格
        ref_prices = {
            '普通工': 100,
            '技工': 150,
            '水泥': 400,
            '砂': 80,
            '石子': 50,
            '混凝土搅拌车': 800,
            '混凝土泵': 1200,
        }

        cur.execute("""
            INSERT INTO quota2024_resources
            (subitem_id, resource_type, resource_name, unit, quantity, ref_price, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (subitem_id, res_type, res_name, unit, qty, ref_prices.get(res_name, 0), 0))
        print(f"      ✓ 创建工料机: {res_type} - {res_name}")

    conn.commit()
    print("\n✓ 测试数据插入完成！")

except Exception as e:
    conn.rollback()
    print(f"✗ 错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    cur.close()
    conn.close()
