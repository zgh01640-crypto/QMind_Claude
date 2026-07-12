import unittest
from pathlib import Path

from import_pricing_kb import SQLITE_TABLES, inspect_sqlite, sha256_file, sqlite_schema_signature


class PricingKnowledgeVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources = list(Path("mydoc").glob("*.db"))
        if not sources:
            raise unittest.SkipTest("No pricing knowledge .db source is available")
        cls.source = sources[0]

    def test_source_is_complete_and_readable(self):
        report = inspect_sqlite(self.source)
        self.assertEqual("ok", report["quick_check"])
        for key in (
            "libraries", "boq_chapters", "boq_items", "quota_chapters",
            "quota_items", "quota_resources", "conversion_rules",
            "input_prompts", "candidates",
        ):
            self.assertGreaterEqual(report[key], 0, key)

    def test_hash_and_schema_signature_are_stable(self):
        self.assertEqual(sha256_file(self.source), sha256_file(self.source))
        self.assertEqual(
            sqlite_schema_signature(self.source),
            sqlite_schema_signature(self.source),
        )

    def test_all_nine_source_tables_are_versioned(self):
        self.assertEqual(9, len(SQLITE_TABLES))
        schema = Path("db/schema_pricing_kb_versions.sql").read_text(encoding="utf-8")
        for _, (table, _, _) in SQLITE_TABLES.items():
            self.assertIn(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS kb_version_id", schema)


if __name__ == "__main__":
    unittest.main()
