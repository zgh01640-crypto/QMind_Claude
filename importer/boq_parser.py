"""
解析 E.1 分部分项工程项目清单计价表 Excel。

返回:
  project_info: dict  {project_name, bid_section}
  sections: list[dict]  [{seq, section_name}]
  items: list[dict]  [{item_seq, item_code, item_name, item_description,
                        unit, quantity, unit_price, total_price, provisional_price,
                        section_seq}]  # section_seq 与 sections 的 seq 对应
"""

import re
import openpyxl


_SKIP_PATTERNS = re.compile(r'^(本页小计|合计|分部小计)$')

_HEADER_ALIASES = {
    'seq': {'序号'},
    'row_type': {'类', '类型', '行类型'},
    'code': {'子目编号', '子目编码', '项目编码', '项目代码'},
    'name': {'子目名称', '项目名称'},
    'description': {'项目特征', '项目规格', '项目描述'},
    'unit': {'单位', '计量单位'},
    'quantity': {'工程量', '数量'},
    'unit_price': {'综合单价', '单价'},
    'total_price': {'合价', '合计', '总价'},
    'provisional_price': {'暂估价'},
}


def _normalize_header(value) -> str:
    return re.sub(r'\s+', '', str(value or '')).strip()


def _detect_columns(ws) -> tuple[int, dict[str, int]]:
    """Return the header row and zero-based indexes for recognized columns."""
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

    # Historical fallback: four title/header rows followed by fixed BOQ columns.
    return 4, {
        'seq': 0, 'code': 1, 'name': 2, 'description': 3,
        'unit': 4, 'quantity': 5, 'unit_price': 6,
        'total_price': 7, 'provisional_price': 8,
    }


def _column_value(row, columns: dict[str, int], field: str):
    index = columns.get(field)
    if index is None or index >= len(row):
        return None
    return row[index]


def _parse_project_info(ws):
    """从第1、2行提取工程名和标段。"""
    row2 = [ws.cell(2, c).value for c in range(1, ws.max_column + 1)]
    project_name = ''
    bid_section = ''
    for cell_val in row2:
        if cell_val is None:
            continue
        s = str(cell_val).strip()
        if s.startswith('工程名称'):
            project_name = re.sub(r'^工程名称[：:]\s*', '', s)
        elif s.startswith('标段'):
            bid_section = re.sub(r'^标段[：:]\s*', '', s)
    return {'project_name': project_name, 'bid_section': bid_section}


def _is_section_row(row):
    """分部行：序号为空，第3列有内容，第2/4/5/6列均为空。"""
    seq, code, name, desc, unit, qty = row[0], row[1], row[2], row[3], row[4], row[5]
    if seq is not None and str(seq).strip():
        return False
    if not name or not str(name).strip():
        return False
    if code or desc or unit or (qty is not None and str(qty).strip()):
        return False
    return True


def _is_item_row(row):
    """清单行：序号为整数或可转为整数的字符串，有项目编码。"""
    seq, code = row[0], row[1]
    if seq is None or code is None:
        return False
    try:
        int(str(seq).strip())
    except (ValueError, AttributeError):
        return False
    return bool(str(code).strip())


def _to_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def parse_boq_workbook(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active

    project_info = _parse_project_info(ws)

    sections = []
    items = []
    current_section_seq = 0
    section_seq_counter = 0
    header_row, columns = _detect_columns(ws)

    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        seq = _column_value(row, columns, 'seq')
        row_type = str(_column_value(row, columns, 'row_type') or '').strip()
        code = _column_value(row, columns, 'code')
        name = _column_value(row, columns, 'name')
        desc = _column_value(row, columns, 'description')
        unit = _column_value(row, columns, 'unit')
        qty = _column_value(row, columns, 'quantity')
        unit_price = _column_value(row, columns, 'unit_price')
        total_price = _column_value(row, columns, 'total_price')
        prov_price = _column_value(row, columns, 'provisional_price')

        name_s = str(name).strip() if name else ''

        # 跳过小计/合计
        if name_s and _SKIP_PATTERNS.match(name_s):
            continue
        # 跳过序号列是"本页小计"/"合计"
        if seq and _SKIP_PATTERNS.match(str(seq).strip()):
            continue

        row_data = [seq, code, name, desc, unit, qty]

        # The typed export uses 部/清/定/借. Normal project import retains
        # sections and BOQ rows only; quota rows belong to manual import.
        is_section = row_type == '部' or (not row_type and _is_section_row(row_data))
        is_item = row_type == '清' or (not row_type and _is_item_row(row_data))

        if is_section:
            section_seq_counter += 1
            sections.append({'seq': section_seq_counter, 'section_name': name_s})
            current_section_seq = section_seq_counter
        elif is_item and _is_item_row(row_data):
            items.append({
                'item_seq': int(str(seq).strip()),
                'item_code': str(code).strip(),
                'item_name': str(name).strip(),
                'item_description': str(desc).strip() if desc else None,
                'unit': str(unit).strip() if unit else None,
                'quantity': _to_float(qty),
                'unit_price': _to_float(unit_price),
                'total_price': _to_float(total_price),
                'provisional_price': _to_float(prov_price),
                'section_seq': current_section_seq,
            })

    return project_info, sections, items
