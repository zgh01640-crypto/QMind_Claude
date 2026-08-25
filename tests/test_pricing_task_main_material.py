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
