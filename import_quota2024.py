"""
消耗量标准 2024 导入脚本

从 PDF 文件用 Claude API 进行 OCR，三阶段导入：
1. 边界检测 - 确定章节和节类型
2. 文本提取 - 提取说明和规则
3. 表格提取 - 提取子目构成表

用法:
    python import_quota2024.py [--pdf PATH] [--force] [--start-page N] [--end-page N]
"""

import sys
import json
import time
import argparse
from pathlib import Path
from typing import Optional
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import os

# PyMuPDF 渲染
try:
    import fitz
except ImportError:
    print("[ERROR] PyMuPDF not installed. Run: pip install pymupdf")
    sys.exit(1)

from importer.quota2024_parser import (
    Quota2024Parser,
    PageMap,
    GroupBlock,
    SubItem,
    ResourceRow,
)

# ============ 数据库连接 ============

def get_connection():
    """获取数据库连接"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5433)),
        database=os.getenv('DB_NAME', 'qmind'),
        user=os.getenv('DB_USER', 'qmind'),
        password=os.getenv('DB_PASSWORD', 'qmind')
    )


# ============ PDF 渲染 ============

def render_page(doc: fitz.Document, page_no: int, dpi: int = 150) -> Optional[bytes]:
    """
    将 PDF 页面渲染为 PNG 字节

    Args:
        doc: PyMuPDF 文档对象
        page_no: 页码（1-based）
        dpi: 渲染分辨率

    Returns:
        PNG 字节，或 None 如果失败
    """
    try:
        page = doc[page_no - 1]  # 0-indexed
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_bytes = pix.tobytes("png")
        return img_bytes
    except Exception as e:
        print(f"[ERROR] 页面 {page_no} 渲染失败: {e}")
        return None


# ============ 检查点管理 ============

@dataclass
class CheckpointData:
    """断点数据"""
    standard_id: int
    phase: str  # "boundary" | "text" | "table"
    completed_pages: set[int]
    sections: dict = None  # section_id -> section_type
    last_update: str = None

    def to_dict(self):
        return {
            'standard_id': self.standard_id,
            'phase': self.phase,
            'completed_pages': list(self.completed_pages),
            'sections': self.sections,
            'last_update': self.last_update
        }

    @staticmethod
    def from_dict(data):
        ckp = CheckpointData(
            standard_id=data['standard_id'],
            phase=data['phase'],
            completed_pages=set(data.get('completed_pages', [])),
            sections=data.get('sections', {}),
            last_update=data.get('last_update')
        )
        return ckp


class CheckpointManager:
    """管理断点文件"""

    def __init__(self, checkpoint_dir: Path, pdf_path: Path):
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        # 用 PDF 文件名生成检查点文件名
        self.checkpoint_file = self.checkpoint_dir / f"{pdf_path.stem}.checkpoint.json"

    def load(self) -> Optional[CheckpointData]:
        """加载已有的检查点"""
        if not self.checkpoint_file.exists():
            return None
        try:
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return CheckpointData.from_dict(data)
        except Exception as e:
            print(f"[WARN] 加载检查点失败: {e}")
            return None

    def save(self, ckp: CheckpointData):
        """保存检查点"""
        try:
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(ckp.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ERROR] 保存检查点失败: {e}")


from dataclasses import dataclass


# ============ 数据库操作 ============

def get_or_create_standard(conn, standard_code: str, name: str, region: str, source_file: str) -> int:
    """获取或创建标准记录"""
    with conn.cursor() as cur:
        # 尝试获取
        cur.execute("SELECT id FROM quota2024_standards WHERE standard_code = %s", (standard_code,))
        row = cur.fetchone()
        if row:
            return row[0]

        # 创建新的
        cur.execute(
            """
            INSERT INTO quota2024_standards (standard_code, name, region, source_file, base_date)
            VALUES (%s, %s, %s, %s, CURRENT_DATE)
            RETURNING id
            """,
            (standard_code, name, region, source_file)
        )
        conn.commit()
        return cur.fetchone()[0]


def delete_standard(conn, standard_id: int):
    """删除标准及其所有相关数据（级联删除）"""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM quota2024_standards WHERE id = %s", (standard_id,))
        conn.commit()


def insert_chapter(conn, standard_id: int, chapter_no: int, code: str, name: str) -> int:
    """插入章"""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO quota2024_chapters (standard_id, chapter_no, code, name, sort_order)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (standard_id, chapter_no, code, name, chapter_no)
        )
        conn.commit()
        return cur.fetchone()[0]


def insert_section(conn, chapter_id: int, section_type: str, section_code: str,
                  title: str, content_md: Optional[str], page_start: int, page_end: int) -> int:
    """插入节"""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO quota2024_sections
              (chapter_id, section_type, section_code, title, content_md, page_start, page_end)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (chapter_id, section_type, section_code, title, content_md, page_start, page_end)
        )
        conn.commit()
        return cur.fetchone()[0]


def insert_groups_and_items(conn, section_id: int, groups: list[GroupBlock]):
    """批量插入分组、项目、子目和工料机"""
    conn_cursor = conn.cursor()

    for group_idx, group in enumerate(groups):
        # 插入分组
        conn_cursor.execute(
            """
            INSERT INTO quota2024_groups (section_id, group_code, group_name, sort_order)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (section_id, group.group_code, group.group_name, group_idx)
        )
        group_id = conn_cursor.fetchone()[0]

        # 插入项目和子目
        for item_idx, item in enumerate(group.items):
            conn_cursor.execute(
                """
                INSERT INTO quota2024_items (group_id, item_no, item_name, work_content, unit, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (group_id, item.item_no, item.item_name, item.work_content, item.unit, item_idx)
            )
            item_id = conn_cursor.fetchone()[0]

            # 插入子目（子项）
            if item.subitems:
                subitem_rows = []
                for sub_idx, subitem in enumerate(item.subitems):
                    subitem_rows.append((
                        item_id, subitem.subitem_code, subitem.subitem_name, subitem.variant_desc,
                        subitem.total_unit_price, subitem.unit_price,
                        subitem.labor_cost, subitem.material_cost, subitem.machine_cost,
                        subitem.management_fee, subitem.profit, subitem.safety_fee,
                        subitem.statutory_fee, subitem.tax, sub_idx
                    ))

                psycopg2.extras.execute_values(
                    conn_cursor,
                    """
                    INSERT INTO quota2024_subitems
                      (item_id, subitem_code, subitem_name, variant_desc,
                       total_unit_price, unit_price,
                       labor_cost, material_cost, machine_cost,
                       management_fee, profit, safety_fee, statutory_fee, tax, sort_order)
                    VALUES %s
                    """,
                    subitem_rows
                )

            # 插入工料机
            if item.resources:
                for res_idx, resource in enumerate(item.resources):
                    # 对每个有消耗量的子目插入一条工料机记录
                    for subitem_code, quantity in resource.quantities.items():
                        # 先获取子目 ID
                        conn_cursor.execute(
                            "SELECT id FROM quota2024_subitems WHERE subitem_code = %s",
                            (subitem_code,)
                        )
                        result = conn_cursor.fetchone()
                        if result:
                            subitem_id = result[0]
                            conn_cursor.execute(
                                """
                                INSERT INTO quota2024_resources
                                  (subitem_id, resource_type, resource_name, unit, quantity, ref_price, sort_order)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                """,
                                (subitem_id, resource.resource_type, resource.resource_name,
                                 resource.unit, quantity, resource.ref_price, res_idx)
                            )

    conn.commit()
    conn_cursor.close()


# ============ 导入流程 ============

def phase_boundary_detection(pdf_path: Path, doc: fitz.Document, parser: Quota2024Parser,
                           ckp_mgr: CheckpointManager, start_page: int, end_page: int) -> list[PageMap]:
    """
    第一阶段：边界检测

    返回按页号映射的 PageMap 列表
    """
    print("\n=== 第一阶段：边界检测 ===")

    ckp = ckp_mgr.load()
    completed = ckp.completed_pages if ckp and ckp.phase == 'boundary' else set()

    page_maps = {}

    # 分批处理（每批 5 页）
    batch_size = 5
    for batch_start in range(start_page, end_page + 1, batch_size):
        batch_end = min(batch_start + batch_size - 1, end_page)

        for page_no in range(batch_start, batch_end + 1):
            if page_no in completed:
                print(f"  [SKIP] 页 {page_no} 已处理")
                continue

            print(f"  [PAGE {page_no}] 渲染中...")
            img_bytes = render_page(doc, page_no)
            if not img_bytes:
                continue

            print(f"  [PAGE {page_no}] 检测中...")
            pm = parser.detect_boundaries(img_bytes, page_no)
            if pm:
                page_maps[page_no] = pm
                print(f"    ✓ 章 {pm.chapter_no} | 节 {pm.section_type} ({pm.section_code})")
            else:
                print(f"    ✗ 检测失败")

            completed.add(page_no)

            # 每页保存一次检查点
            ckp_data = CheckpointData(
                standard_id=0,  # 稍后填充
                phase='boundary',
                completed_pages=completed
            )
            ckp_mgr.save(ckp_data)
            time.sleep(0.5)  # 避免 API 速率限制

    return page_maps


def phase_text_extraction(pdf_path: Path, doc: fitz.Document, parser: Quota2024Parser,
                         page_maps: dict[int, PageMap], conn,
                         ckp_mgr: CheckpointManager) -> dict[int, int]:
    """
    第二阶段：文本提取（说明和规则）

    返回 section_id 映射
    """
    print("\n=== 第二阶段：文本提取 ===")

    section_map = {}  # page_no -> section_id
    standard_id = None
    chapter_ids = {}  # chapter_no -> chapter_id

    for page_no in sorted(page_maps.keys()):
        pm = page_maps[page_no]

        if pm.section_type != 'intro' and pm.section_type != 'rules':
            continue

        print(f"  [PAGE {page_no}] {pm.chapter_no}.{pm.section_code} - {pm.title} 提取中...")

        # 创建或获取章
        if pm.chapter_no not in chapter_ids:
            chapter_ids[pm.chapter_no] = insert_chapter(
                conn, standard_id, pm.chapter_no, str(pm.chapter_no), pm.chapter_name
            )

        chapter_id = chapter_ids[pm.chapter_no]

        # 渲染页面
        img_bytes = render_page(doc, page_no)
        if not img_bytes:
            continue

        # 提取文本
        text = parser.extract_text(img_bytes)
        if text:
            section_id = insert_section(
                conn, chapter_id, pm.section_type, pm.section_code, pm.title,
                text, page_no, page_no
            )
            section_map[page_no] = section_id
            print(f"    ✓ 提取成功")
        else:
            print(f"    ✗ 提取失败")

        time.sleep(0.5)

    return section_map


def phase_table_extraction(pdf_path: Path, doc: fitz.Document, parser: Quota2024Parser,
                          page_maps: dict[int, PageMap], conn,
                          ckp_mgr: CheckpointManager):
    """
    第三阶段：表格提取（子目构成表）
    """
    print("\n=== 第三阶段：表格提取 ===")

    standard_id = None
    chapter_ids = {}

    # 按章节分组页码
    sections_pages = {}  # (chapter_no, section_code) -> [page_nos]
    for page_no in sorted(page_maps.keys()):
        pm = page_maps[page_no]
        if pm.section_type != 'items':
            continue

        key = (pm.chapter_no, pm.section_code)
        if key not in sections_pages:
            sections_pages[key] = []
        sections_pages[key].append(page_no)

    # 处理每个节
    for (chapter_no, section_code), page_list in sections_pages.items():
        print(f"  [章 {chapter_no}.{section_code}] 处理 {len(page_list)} 页...")

        # 获取章 ID
        if chapter_no not in chapter_ids:
            pm_sample = page_maps[page_list[0]]
            chapter_ids[chapter_no] = insert_chapter(
                conn, standard_id, chapter_no, str(chapter_no), pm_sample.chapter_name
            )

        chapter_id = chapter_ids[chapter_no]

        # 创建节（section）
        pm_first = page_maps[page_list[0]]
        section_id = insert_section(
            conn, chapter_id, 'items', section_code, pm_first.title,
            None, page_list[0], page_list[-1]
        )

        # 逐页提取表格
        all_groups = []
        for page_no in page_list:
            print(f"    [PAGE {page_no}] 表格提取中...")

            img_bytes = render_page(doc, page_no)
            if not img_bytes:
                continue

            groups = parser.extract_table(img_bytes)
            if groups:
                all_groups.extend(groups)
                print(f"      ✓ 提取 {len(groups)} 个分组")
            else:
                print(f"      ✗ 提取失败")

            time.sleep(0.5)

        # 批量插入
        if all_groups:
            insert_groups_and_items(conn, section_id, all_groups)
            print(f"    ✓ 已保存 {len(all_groups)} 个分组")


# ============ 主入口 ============

def main():
    load_dotenv()

    parser_args = argparse.ArgumentParser(description='消耗量标准 2024 导入')
    parser_args.add_argument('--pdf', default='mydoc/深圳市建筑消耗量标准2024.pdf',
                            help='PDF 文件路径')
    parser_args.add_argument('--force', action='store_true', help='强制重新导入（删除已有数据）')
    parser_args.add_argument('--start-page', type=int, default=1, help='起始页')
    parser_args.add_argument('--end-page', type=int, default=None, help='结束页（默认为最后一页）')
    parser_args.add_argument('--checkpoint-dir', default='.checkpoints', help='检查点目录')

    args = parser_args.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"[ERROR] PDF 文件不存在: {pdf_path}")
        sys.exit(1)

    # 打开 PDF
    print(f"打开 PDF: {pdf_path}")
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    end_page = args.end_page or total_pages
    print(f"总页数: {total_pages}")

    # 初始化
    conn = get_connection()
    parser = Quota2024Parser()
    ckp_mgr = CheckpointManager(Path(args.checkpoint_dir), pdf_path)

    # 标准元数据
    standard_code = "SJG 171-2024"
    standard_name = "深圳市建筑工程消耗量标准"
    region = "深圳市"

    # 检查是否需要重新导入
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM quota2024_standards WHERE standard_code = %s", (standard_code,))
        existing = cur.fetchone()

    if existing and args.force:
        print(f"[INFO] 删除已有数据...")
        standard_id = existing[0]
        delete_standard(conn, standard_id)

    # 获取或创建标准
    standard_id = get_or_create_standard(conn, standard_code, standard_name, region, str(pdf_path))
    print(f"标准 ID: {standard_id}")

    # 三阶段处理
    try:
        page_maps = phase_boundary_detection(pdf_path, doc, parser, ckp_mgr, args.start_page, end_page)
        print(f"\n✓ 边界检测完成，共 {len(page_maps)} 页")

        phase_text_extraction(pdf_path, doc, parser, page_maps, conn, ckp_mgr)
        print(f"\n✓ 文本提取完成")

        phase_table_extraction(pdf_path, doc, parser, page_maps, conn, ckp_mgr)
        print(f"\n✓ 表格提取完成")

        print("\n✓ 导入完成！")

    finally:
        doc.close()
        conn.close()


if __name__ == '__main__':
    main()
