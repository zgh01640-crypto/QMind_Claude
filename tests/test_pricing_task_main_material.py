from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from routers import pricing_task  # noqa: E402


class SuccessorVersionCursor:
    def __init__(self):
        self.last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.last_sql = " ".join(str(sql).split())

    def fetchone(self):
        if "FROM pricing_kb_versions origin" in self.last_sql:
            return (20,)
        return None


class SuccessorVersionConnection:
    def cursor(self):
        return SuccessorVersionCursor()


class MainMaterialSnapshotTests(unittest.TestCase):
    def test_feature_material_name_is_preserved_verbatim(self):
        resources = [
            {"name": "法兰阀门 DN100 Z45T-10", "zycl": True},
            {"name": "其他材料费", "zycl": False},
        ]

        pricing_task._enrich_main_material_resources(
            resources,
            "1.类型:过滤活塞式遥控浮球阀\n2.规格:DN100\n3.材质:球墨铸铁",
        )

        self.assertEqual(resources[0]["name"], "法兰阀门 DN100 Z45T-10")
        self.assertEqual(resources[0]["main_material_name"], "过滤活塞式遥控浮球阀")
        self.assertEqual(resources[0]["main_material_specification"], "DN100")
        self.assertEqual(resources[0]["main_material_material"], "球墨铸铁")
        self.assertEqual(resources[0]["main_material_name_source"], "project_feature")

    def test_missing_feature_name_falls_back_to_quota_name(self):
        resources = [{"name": "法兰阀门 DN80 Z45T-10", "zycl": True}]

        pricing_task._enrich_main_material_resources(resources, "1.规格:DN80\n2.连接形式:法兰")

        self.assertEqual(resources[0]["main_material_name"], "法兰阀门 DN80 Z45T-10")
        self.assertEqual(resources[0]["main_material_name_source"], "quota")

    def test_multiple_main_materials_only_best_match_uses_feature_name(self):
        resources = [
            {"name": "螺纹闸板阀 DN25 Z15T-16", "zycl": True},
            {"name": "螺纹水表 DN25 LXS-C", "zycl": True},
        ]

        pricing_task._enrich_main_material_resources(
            resources, "1.类型：水表\n2.型号、规格：DN25"
        )

        self.assertEqual(resources[0]["main_material_name_source"], "quota")
        self.assertEqual(resources[1]["main_material_name"], "水表")
        self.assertEqual(resources[1]["main_material_specification"], "DN25")

    def test_material_value_containing_product_name_can_supply_name(self):
        resources = [{"name": "薄壁不锈钢管 DN100 δ=1.5mm", "zycl": True}]

        pricing_task._enrich_main_material_resources(
            resources, "1.材质：S31603薄壁不锈钢管\n2.规格：DN100"
        )

        self.assertEqual(resources[0]["main_material_name"], "S31603薄壁不锈钢管")
        self.assertEqual(resources[0]["main_material_material"], "S31603薄壁不锈钢管")

    def test_conversion_check_preserves_main_material_flag(self):
        confirmed_items = [
            {
                "dekid": 1020206,
                "dezmid": 7783,
                "quota_code": "030802-31",
                "quota_name": "法兰阀门安装",
                "resources": [
                    {
                        "code": "19210160",
                        "name": "法兰阀门 DN50 Z45T-10",
                        "unit": "个",
                        "quantity": 1.0,
                        "type": 2,
                        "zycl": True,
                    }
                ],
                "adjustment_rules": [],
            }
        ]

        result = pricing_task._normalize_conversion_check(
            {
                "items": [
                    {
                        "dekid": 1020206,
                        "dezmid": 7783,
                        "needs_conversion": False,
                    }
                ]
            },
            confirmed_items,
        )

        self.assertIs(result["items"][0]["resources"][0]["zycl"], True)

    def test_legacy_snapshot_gets_main_material_flag_from_source(self):
        resources = [
            {
                "code": "19210160",
                "name": "法兰阀门 DN50 Z45T-10",
                "unit": "个",
                "quantity": 1.0,
                "type": 2,
            }
        ]
        source_resources = [{**resources[0], "zycl": True}]

        pricing_task._hydrate_resource_main_material_flags(resources, source_resources)

        self.assertIs(resources[0]["zycl"], True)

    def test_legacy_version_uses_same_source_successor_for_display_only(self):
        legacy_resources = [{"code": "19210160", "zycl": None}]
        successor_resources = [{"code": "19210160", "zycl": True}]
        with patch.object(
            pricing_task,
            "_load_combo_resources",
            side_effect=[legacy_resources, successor_resources],
        ) as load_resources:
            result = pricing_task._load_resources_with_main_material_fallback(
                SuccessorVersionConnection(), 19, 1020206, 7783, None
            )

        self.assertEqual(result, successor_resources)
        self.assertEqual(load_resources.call_args_list[0].args[1], 19)
        self.assertEqual(load_resources.call_args_list[1].args[1], 20)


if __name__ == "__main__":
    unittest.main()
