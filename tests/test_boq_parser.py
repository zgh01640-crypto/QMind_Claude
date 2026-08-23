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
