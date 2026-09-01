from pathlib import Path

from openpyxl import Workbook

from importer.boq_parser import parse_boq_workbook


def _save_workbook(path: Path, headers: list[str], values: list[object]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    sheet.append([None] * len(headers))
    sheet.append([None] * len(headers))
    sheet.append([None] * len(headers))
    sheet.append(values)
    workbook.save(path)


def test_parser_detects_quantity_before_unit(tmp_path):
    path = tmp_path / "quantity-first.xlsx"
    _save_workbook(
        path,
        ["序号", "子目编号", "子目名称", "项目特征", "工程量", "单位"],
        [1, "030109001001", "水泵", "测试特征", 2.5, "台"],
    )

    _, _, items = parse_boq_workbook(path)

    assert items[0]["unit"] == "台"
    assert items[0]["quantity"] == 2.5


def test_parser_keeps_unit_before_quantity(tmp_path):
    path = tmp_path / "unit-first.xlsx"
    _save_workbook(
        path,
        ["序号", "项目编码", "项目名称", "项目特征", "单位", "工程量"],
        [1, "030109001001", "水泵", "测试特征", "套", 3],
    )

    _, _, items = parse_boq_workbook(path)

    assert items[0]["unit"] == "套"
    assert items[0]["quantity"] == 3.0


def test_parser_handles_typed_export_and_ignores_quota_rows(tmp_path):
    path = tmp_path / "typed-export.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["序号", "类", "子目编号", "子目名称", "项目特征", "工程量表达式", "工程量", "单位"])
    sheet.append([None] * 8)
    sheet.append([None, "部", None, "整个工程", None, None, None, None])
    sheet.append([1, "清", "030109001001", "水泵", "测试特征", None, 2, "台"])
    sheet.append([None, "定", "030106-17", "多级离心泵", None, "Q", 2, "台"])
    sheet.append([None, "借", "040402-278换", "借用子目", None, None, 4, "个"])
    sheet.append([2, "清", "030109001002", "消防泵", "另一特征", None, 3, "套"])
    workbook.save(path)

    _, sections, items = parse_boq_workbook(path)

    assert sections == [{"seq": 1, "section_name": "整个工程"}]
    assert len(items) == 2
    assert items[0] == {
        "item_seq": 1,
        "item_code": "030109001001",
        "item_name": "水泵",
        "item_description": "测试特征",
        "unit": "台",
        "quantity": 2.0,
        "unit_price": None,
        "total_price": None,
        "provisional_price": None,
        "section_seq": 1,
    }
    assert items[1]["item_code"] == "030109001002"
    assert items[1]["unit"] == "套"
    assert items[1]["quantity"] == 3.0
