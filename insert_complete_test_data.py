"""
插入完整测试数据到数据库 - 演示多章节完整结构
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
    # 获取现有标准
    cur.execute("SELECT id FROM quota2024_standards WHERE standard_code = 'SJG 171-2024'")
    result = cur.fetchone()
    standard_id = result[0] if result else None

    if not standard_id:
        raise Exception("标准不存在，请先运行 insert_test_data.py")

    # 清空所有相关数据
    cur.execute("DELETE FROM quota2024_groups WHERE section_id IN (SELECT id FROM quota2024_sections WHERE chapter_id IN (SELECT id FROM quota2024_chapters WHERE standard_id = %s AND chapter_no > 0))", (standard_id,))
    cur.execute("DELETE FROM quota2024_sections WHERE chapter_id IN (SELECT id FROM quota2024_chapters WHERE standard_id = %s AND chapter_no > 0)", (standard_id,))
    cur.execute("DELETE FROM quota2024_chapters WHERE standard_id = %s AND chapter_no > 0", (standard_id,))
    conn.commit()

    print(f"使用标准 ID: {standard_id}")

    # 定义章节数据
    chapters_data = [
        (1, "1", "砌筑工程"),
        (2, "2", "混凝土及钢筋混凝土工程"),
        (3, "3", "木结构工程"),
    ]

    chapter_ids = {}

    # 为每个章创建完整的节和数据
    for chapter_no, code, chapter_name in chapters_data:
        # 创建章
        cur.execute("""
            INSERT INTO quota2024_chapters (standard_id, chapter_no, code, name, sort_order)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (standard_id, chapter_no, code, chapter_name, chapter_no))
        chapter_id = cur.fetchone()[0]
        chapter_ids[chapter_no] = chapter_id
        print(f"\n✓ 创建章 {chapter_no}: {chapter_name}")

        # 创建说明节
        intro_content = f"""
## {chapter_no}.1 {chapter_name}说明

### {chapter_no}.1.1 适用范围
本章适用于 {chapter_name} 工程。

### {chapter_no}.1.2 工程分类
根据工程特点分为以下几类：
- 基础工程
- 主体工程
- 装饰工程

### {chapter_no}.1.3 计价规则

| 项目等级 | 说明 | 系数 |
|--------|------|------|
| 一级 | 普通工程 | 1.0 |
| 二级 | 复杂工程 | 1.1 |
| 三级 | 特殊工程 | 1.2 |

### {chapter_no}.1.4 施工要求
- 严格按照设计要求施工
- 确保质量符合规范
- 做好成品保护工作
"""

        cur.execute("""
            INSERT INTO quota2024_sections (chapter_id, section_type, section_code, title, content_md, page_start, page_end)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (chapter_id, 'intro', f'{chapter_no}.1', '说明', intro_content, 1, 10))
        intro_section_id = cur.fetchone()[0]
        print(f"  ✓ 创建说明节 {chapter_no}.1")

        # 创建规则节
        rules_content = f"""
## {chapter_no}.2 {chapter_name}工程量计算规则

### {chapter_no}.2.1 计算原则
按设计图示尺寸以实际数量计算。

### {chapter_no}.2.2 工程项目
"""
        if chapter_no == 1:
            rules_content += """
#### {}.2.2.1 砖砌体
- 按厚度、长度、高度计算体积
- 扣除门窗洞口

#### {}.2.2.2 砂浆
- 按砌体体积计算
- 每立方米砌体需砂浆量：0.25~0.35m³
""".format(chapter_no, chapter_no)
        elif chapter_no == 2:
            rules_content += """
#### {}.2.2.1 现浇混凝土
- 按构件尺寸计算体积
- 不扣除钢筋体积

#### {}.2.2.2 模板
- 按接触面积计算
- 支撑费用另计
""".format(chapter_no, chapter_no)
        else:
            rules_content += """
#### {}.2.2.1 木构件
- 按设计规格计算数量
- 损耗率按10%计

#### {}.2.2.2 木制品
- 按实际安装数量计算
""".format(chapter_no, chapter_no)

        rules_content += """

### {}.2.3 超高增加费
高度超过20m时，按如下系数计算：

| 高度范围(m) | 增加系数 |
|------------|--------|
| 20-30 | 1.05 |
| 30-50 | 1.10 |
| >50 | 1.15 |
""".format(chapter_no)

        cur.execute("""
            INSERT INTO quota2024_sections (chapter_id, section_type, section_code, title, content_md, page_start, page_end)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (chapter_id, 'rules', f'{chapter_no}.2', '工程量计算规则', rules_content, 11, 25))
        rules_section_id = cur.fetchone()[0]
        print(f"  ✓ 创建规则节 {chapter_no}.2")

        # 创建子目构成表节
        cur.execute("""
            INSERT INTO quota2024_sections (chapter_id, section_type, section_code, title, content_md, page_start, page_end)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (chapter_id, 'items', f'{chapter_no}.3', '子目构成表', None, 26, 50))
        items_section_id = cur.fetchone()[0]
        print(f"  ✓ 创建子目节 {chapter_no}.3")

        # 为每个章创建2个分组，每个分组2个项目
        for group_no in range(1, 3):
            group_code = f'{chapter_no}.3.{group_no}'

            if chapter_no == 1 and group_no == 1:
                group_name = "砖砌体"
            elif chapter_no == 1 and group_no == 2:
                group_name = "砌筑砂浆"
            elif chapter_no == 2 and group_no == 1:
                group_name = "现浇混凝土"
            elif chapter_no == 2 and group_no == 2:
                group_name = "预制构件"
            else:
                group_name = f"分组{group_no}"

            cur.execute("""
                INSERT INTO quota2024_groups (section_id, group_code, group_name, sort_order)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (items_section_id, group_code, group_name, group_no))
            group_id = cur.fetchone()[0]
            print(f"    ✓ 创建分组 {group_code}")

            # 为每个分组创建2个项目
            for item_no in range(1, 3):
                item_name = f"{group_name}项目{item_no}"
                work_content = f"包括{group_name}的完整施工内容"

                if chapter_no == 1:
                    unit = "m³"
                elif chapter_no == 2:
                    unit = "10m³"
                else:
                    unit = "m"

                cur.execute("""
                    INSERT INTO quota2024_items (group_id, item_no, item_name, work_content, unit, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (group_id, item_no, item_name, work_content, unit, item_no))
                item_id = cur.fetchone()[0]

                # 为每个项目创建3个子目
                for sub_no in range(1, 4):
                    base_code = (chapter_no + 1) * 10000 + group_no * 100 + item_no * 10 + sub_no
                    subitem_code = f"{base_code:06d}-{sub_no}"
                    subitem_name = f"类型{sub_no}"
                    variant_desc = f"规格{sub_no}"

                    # 动态生成价格
                    base_price = 200 + sub_no * 100
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
                          mgmt, profit, safety, stat_fee, tax, sub_no - 1))
                    subitem_id = cur.fetchone()[0]

                    # 创建工料机资源
                    resources_data = [
                        ('人工', '普通工', '工', 0.8),
                        ('人工', '技工', '工', 0.3),
                        ('材料', '主要材料', '吨', 0.5 * sub_no),
                        ('材料', '辅助材料', '吨', 0.2 * sub_no),
                        ('机械', '主要机械', '台班', 0.1 * sub_no),
                    ]

                    ref_prices = {
                        '普通工': 100,
                        '技工': 150,
                        '主要材料': 400 * sub_no,
                        '辅助材料': 100 * sub_no,
                        '主要机械': 800 * sub_no,
                    }

                    for res_type, res_name, unit_res, qty in resources_data:
                        cur.execute("""
                            INSERT INTO quota2024_resources
                            (subitem_id, resource_type, resource_name, unit, quantity, ref_price, sort_order)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (subitem_id, res_type, res_name, unit_res, qty,
                              ref_prices.get(res_name, 0), 0))

                print(f"      ✓ 创建项目 {item_no} 含3个子目和工料机")

    conn.commit()
    print("\n✅ 完整测试数据插入完成！")
    print("\n数据摘要：")
    cur.execute("SELECT COUNT(*) FROM quota2024_chapters WHERE standard_id = %s", (standard_id,))
    print(f"  - 章数: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM quota2024_sections WHERE chapter_id IN (SELECT id FROM quota2024_chapters WHERE standard_id = %s)", (standard_id,))
    print(f"  - 节数: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM quota2024_groups")
    print(f"  - 分组数: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM quota2024_items")
    print(f"  - 项目数: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM quota2024_subitems")
    print(f"  - 子目数: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM quota2024_resources")
    print(f"  - 工料机数: {cur.fetchone()[0]}")

except Exception as e:
    conn.rollback()
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    cur.close()
    conn.close()
