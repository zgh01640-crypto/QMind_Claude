from pathlib import Path

from openpyxl import Workbook

from import_manual_boq import parse_workbook


def _save(path: Path, rows: list[list[object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_typed_manual_template_maps_items_sections_and_quotas(tmp_path):
    path = tmp_path / "typed-manual.xlsx"
    _save(path, [
        ["序号", "类", "子目编号", "子目名称", "项目特征", "工程量表达式", "工程量", "单位"],
        [None] * 8,
        [None, "部", None, "整个工程", None, None, None, None],
        [1, "清", "030109001001", "水泵", "测试特征", None, 2, "台"],
        [None, "定", "030106-17", "多级离心泵", None, "Q", 2, "台"],
        [None, "借", "040402-278换", "借用子目", None, None, 4, "个"],
    ])

    data = parse_workbook(path)

    assert data["sections"] == [{"seq": 1, "section_name": "整个工程"}]
    assert data["items"][0] == {
        "section_name": "整个工程",
        "item_seq": 1,
        "item_code": "030109001001",
        "item_name": "水泵",
        "item_description": "测试特征",
        "unit": "台",
        "quantity": 2.0,
        "unit_price": None,
        "total_price": None,
    }
    assert [quota["quota_code"] for quota in data["quotas"]] == ["030106-17", "040402-278换"]
    assert data["quotas"][0]["quota_unit"] == "台"
    assert data["quotas"][0]["quantity"] == 2.0


def test_legacy_manual_template_detects_quantity_before_unit(tmp_path):
    path = tmp_path / "legacy-manual.xlsx"
    _save(path, [
        ["序号", "子目编号", "子目名称", "项目特征", "工程量", "单位"],
        [None] * 6,
        [None, None, "整个工程", None, None, None],
        [1, "030109001001", "水泵", "测试特征", 3, "套"],
        [None, "030106-17", "多级离心泵", None, 3, "套"],
    ])

    data = parse_workbook(path)

    assert data["items"][0]["item_code"] == "030109001001"
    assert data["items"][0]["unit"] == "套"
    assert data["items"][0]["quantity"] == 3.0
    assert data["quotas"][0]["quota_code"] == "030106-17"
    assert data["quotas"][0]["quota_unit"] == "套"
    assert data["quotas"][0]["quantity"] == 3.0
