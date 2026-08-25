from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from routers import pricing_task  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
