#!/usr/bin/env python3
"""
导入人工套定额的工程量清单（含子定额）Excel。

Excel格式：单Sheet，支持按表头识别字段，也兼容旧版固定列格式。
行类型：分部标题 | BOQ清单项 | 定额/借用子目行 | 汇总行（跳过）

用法：
  python import_manual_boq.py <excel_path> [--tag TAG] [--force]
"""

import argparse
import os
import re
import sys

import openpyxl
from dotenv import load_dotenv

from db.connection import get_connection

load_dotenv()

_QUOTA_CODE_RE = re.compile(r'^\d{6}[-\d+*.\s]+')  # 简单码: 120001-11；公式: 120001-214+...
_SIMPLE_CODE_RE = re.compile(r'^\d{6}-\d+$')        # 纯简单码，可查 quota_items


def _clean(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        return v if v else None
    return v


def _to_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _is_skip_row(c3: str | None) -> bool:
    if not c3:
        return False
    keywords = ['小计', '合计', '本页', '分部分项工程', '其中']
    return any(kw in c3 for kw in keywords)


_HEADER_ALIASES = {
    'seq': {'序号'},
    'row_type': {'类', '类型', '行类型'},
    'code': {'子目编号', '子目编码', '项目编码', '项目代码'},
    'name': {'子目名称', '项目名称'},
    'description': {'项目特征', '项目规格', '项目描述'},
    'quantity': {'工程量', '数量'},
    'unit': {'单位', '计量单位'},
    'unit_price': {'综合单价', '单价'},
    'total_price': {'合价', '合计', '总价'},
}


def _normalize_header(value) -> str:
    return re.sub(r'\s+', '', str(value or '')).strip()


def _detect_columns(ws) -> tuple[int | None, dict[str, int]]:
    """在前10行中查找表头，返回表头行号和零基列索引。"""
    for row_number, row in enumerate(
        ws.iter_rows(min_row=1, max_row=min(ws.max_row, 10), values_only=True),
        start=1,
    ):
        columns: dict[str, int] = {}
        for index, value in enumerate(row):
            header = _normalize_header(value)
            for field, aliases in _HEADER_ALIASES.items():
                if header in aliases and field not in columns:
                    columns[field] = index
        if {'seq', 'code', 'name'}.issubset(columns):
            return row_number, columns
    return None, {}


def _column_value(row, columns: dict[str, int], field: str):
    index = columns.get(field)
    if index is None or index >= len(row):
        return None
    return _clean(row[index])


def parse_workbook(path: str) -> dict:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active

    # 提取工程名称和标段；页面传入的工程名仍具有最高优先级。
    project_name = '未命名工程'
    bid_section = None
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 10), values_only=True):
        for value in row:
            text = str(value).strip() if value is not None else ''
            if text.startswith('工程名称'):
                project_name = re.sub(r'^工程名称[：:]\s*', '', text) or project_name
            elif text.startswith('标段'):
                bid_section = re.sub(r'^标段[：:]\s*', '', text) or None

    header_row, columns = _detect_columns(ws)
    if header_row is None:
        # 兼容没有可识别表头的历史8列模板。
        header_row = 3
        columns = {
            'seq': 0, 'code': 1, 'name': 2, 'description': 3,
            'unit': 4, 'quantity': 5, 'unit_price': 6, 'total_price': 7,
        }

    sections = []
    items = []
    quotas = []  # list of (item_index, quota_dict)

    current_section_seq = 0
    current_section_name = None
    current_item_index = None  # index into items[]

    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        seq_value = _column_value(row, columns, 'seq')
        row_type = str(_column_value(row, columns, 'row_type') or '').strip()
        code = _column_value(row, columns, 'code')
        name = _column_value(row, columns, 'name')
        description = _column_value(row, columns, 'description')
        unit = _column_value(row, columns, 'unit')
        quantity = _column_value(row, columns, 'quantity')
        unit_price = _column_value(row, columns, 'unit_price')
        total_price = _column_value(row, columns, 'total_price')
        name_str = str(name) if name is not None else ''

        # 汇总行 → 跳过
        if _is_skip_row(name_str):
            continue

        # 新模板用“类”明确区分；旧模板继续用序号判断清单项。
        try:
            seq = int(seq_value)
            is_boq = row_type == '清' or not row_type
        except (TypeError, ValueError):
            seq = None
            is_boq = False

        if is_boq and seq is not None and code is not None:
            current_item_index = len(items)
            items.append({
                'section_name': current_section_name,
                'item_seq': seq,
                'item_code': str(code),
                'item_name': name_str or None,
                'item_description': str(description) if description is not None else None,
                'unit': str(unit) if unit is not None else None,
                'quantity': _to_float(quantity),
                'unit_price': _to_float(unit_price),
                'total_price': _to_float(total_price),
            })
            continue

        # 新模板中的“定/借”等子目，以及旧模板中序号为空且编码非空的子目。
        is_quota = row_type not in {'', '部', '清'} or (not row_type and seq_value is None)
        if is_quota and code is not None and current_item_index is not None:
            code_str = str(code).strip()
            quotas.append({
                'item_index': current_item_index,
                'quota_code': code_str,
                'quota_name': name_str or None,
                'quota_unit': str(unit) if unit is not None else None,
                'quantity': _to_float(quantity),
                'unit_price': _to_float(unit_price),
                'total_price': _to_float(total_price),
            })
            continue

        # 新模板“部”行，或旧模板中序号/编码为空的分部标题。
        is_section = row_type == '部' or (not row_type and seq_value is None and code is None)
        if is_section and name_str:
            current_section_seq += 1
            current_section_name = name_str
            sections.append({'seq': current_section_seq, 'section_name': name_str})

    return {
        'project_name': project_name,
        'bid_section': bid_section,
        'sections': sections,
        'items': items,
        'quotas': quotas,
    }


def _lookup_quota_item_id(conn, code: str) -> int | None:
    if not _SIMPLE_CODE_RE.match(code):
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM quota_items WHERE item_code = %s LIMIT 1", (code,))
        row = cur.fetchone()
    return row[0] if row else None


def _ensure_import_schema_compatibility(conn) -> None:
    """Widen legacy unit columns before importing user-provided Excel text."""
    columns = {
        ("manual_boq_items", "unit"): "ALTER TABLE manual_boq_items ALTER COLUMN unit TYPE TEXT",
        ("manual_boq_quotas", "quota_unit"): "ALTER TABLE manual_boq_quotas ALTER COLUMN quota_unit TYPE TEXT",
    }
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='public'
              AND (table_name, column_name) IN (
                  ('manual_boq_items', 'unit'),
                  ('manual_boq_quotas', 'quota_unit')
              )
            """
        )
        types = {(table, column): data_type for table, column, data_type in cur.fetchall()}
        for key, statement in columns.items():
            if types.get(key) != "text":
                cur.execute(statement)
    conn.commit()


def import_to_db(
    conn, data: dict, source_file: str, tag: str | None, force: bool,
    project_name_override: str | None = None, allow_duplicate: bool = False, owner_user_id: int | None = None,
) -> int:
    _ensure_import_schema_compatibility(conn)
    project_name = (project_name_override or "").strip() or data["project_name"]

    # 如已存在同文件名工程则删除（force）或跳过
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM manual_boq_projects WHERE source_file = %s", (source_file,))
        existing = cur.fetchone()
    if existing and not allow_duplicate:
        if not force:
            print(f'[跳过] 工程 "{project_name}" 已存在（id={existing[0]}）。使用 --force 强制重新导入。')
            return existing[0]
        with conn.cursor() as cur:
            cur.execute("DELETE FROM manual_boq_projects WHERE id = %s", (existing[0],))
        print(f'[覆盖] 已删除旧记录 id={existing[0]}')

    # 插入工程
    item_count = len(data['items'])
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO manual_boq_projects
                (project_name, bid_section, source_file, tag, item_count, owner_user_id)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """, (project_name, data['bid_section'], source_file, tag, item_count, owner_user_id))
        project_id = cur.fetchone()[0]
    print(f'  工程 id={project_id}，{item_count} 条清单项')

    # 插入分部
    section_id_map = {}  # section_name → id
    with conn.cursor() as cur:
        for sec in data['sections']:
            cur.execute("""
                INSERT INTO manual_boq_sections (project_id, seq, section_name)
                VALUES (%s, %s, %s) RETURNING id
            """, (project_id, sec['seq'], sec['section_name']))
            section_id_map[sec['section_name']] = cur.fetchone()[0]
    print(f'  {len(section_id_map)} 个分部')

    # 插入清单项
    item_id_list = []
    with conn.cursor() as cur:
        for item in data['items']:
            sec_id = section_id_map.get(item['section_name']) if item['section_name'] else None
            cur.execute("""
                INSERT INTO manual_boq_items
                    (project_id, section_id, item_seq, item_code, item_name,
                     item_description, unit, quantity, unit_price, total_price)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """, (
                project_id, sec_id, item['item_seq'], item['item_code'],
                item['item_name'], item['item_description'], item['unit'],
                item['quantity'], item['unit_price'], item['total_price'],
            ))
            item_id_list.append(cur.fetchone()[0])
    # 插入定额子目
    n_quotas = 0
    n_linked = 0
    with conn.cursor() as cur:
        for q in data['quotas']:
            idx = q['item_index']
            if idx >= len(item_id_list):
                continue
            boq_item_id = item_id_list[idx]
            boq_qty = data['items'][idx]['quantity']

            qty_factor = None
            if q['quantity'] is not None and boq_qty and boq_qty != 0:
                qty_factor = q['quantity'] / boq_qty

            quota_item_id = _lookup_quota_item_id(conn, q['quota_code'])
            if quota_item_id:
                n_linked += 1

            cur.execute("""
                INSERT INTO manual_boq_quotas
                    (boq_item_id, quota_code, quota_name, quota_unit,
                     quantity, unit_price, total_price, qty_factor, quota_item_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                boq_item_id, q['quota_code'], q['quota_name'], q['quota_unit'],
                q['quantity'], q['unit_price'], q['total_price'],
                qty_factor, quota_item_id,
            ))
            n_quotas += 1
    conn.commit()
    print(f'  {n_quotas} 条定额子目，其中 {n_linked} 条成功链接到定额库')
    return project_id


def main():
    parser = argparse.ArgumentParser(description='导入人工套定额工程量清单')
    parser.add_argument('excel_path', help='Excel 文件路径')
    parser.add_argument('--original-name', default=None, help='原始文件名（API上传时使用）')
    parser.add_argument('--tag', default=None, help='工程标签')
    parser.add_argument('--force', action='store_true', help='若已存在则强制覆盖')
    parser.add_argument('--project-name', default=None, help='覆盖 Excel 中解析的工程名称')
    parser.add_argument('--allow-duplicate', action='store_true', help='允许同一源文件重复导入为新工程')
    args = parser.parse_args()

    if not os.path.isfile(args.excel_path):
        print(f'[错误] 文件不存在: {args.excel_path}', file=sys.stderr)
        sys.exit(1)

    print(f'解析 {args.excel_path} ...')
    data = parse_workbook(args.excel_path)
    print(f'  工程名：{data["project_name"]}')
    print(f'  {len(data["sections"])} 个分部，{len(data["items"])} 条清单项，{len(data["quotas"])} 条定额子目')

    source_file = args.original_name or os.path.basename(args.excel_path)
    conn = get_connection()
    try:
        print('写入数据库 ...')
        project_id = import_to_db(
            conn, data, source_file, args.tag, args.force,
            project_name_override=args.project_name,
            allow_duplicate=args.allow_duplicate,
            owner_user_id=int(os.environ["AUTH_OWNER_USER_ID"]) if os.environ.get("AUTH_OWNER_USER_ID") else None,
        )
        print(f'PROJECT_ID={project_id}')
        print('导入完成。')
    except Exception as e:
        conn.rollback()
        print(f'[错误] {e}', file=sys.stderr)
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
