from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.pricing_kb_versions import version_to_dict  # noqa: E402


class PricingKbVersionNoteTests(unittest.TestCase):
    def test_version_payload_includes_change_note(self):
        row = (
            8,
            "pricing.db",
            "abc123",
            "validated",
            None,
            {},
            {},
            None,
            "2026-08-16T10:00:00",
            None,
            None,
            None,
            False,
            7,
            "manifest",
            "补充安装工程定额",
        )

        result = version_to_dict(row)

        self.assertEqual(result["change_note"], "补充安装工程定额")

    def test_legacy_version_payload_defaults_note_to_none(self):
        row = (8, "pricing.db", "abc123", "validated", None, {}, {}, None, None, None, None, None, False)

        result = version_to_dict(row)

        self.assertIsNone(result["change_note"])


if __name__ == "__main__":
    unittest.main()
