from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.pricing_kb_schema_contract import SQLITE_SCHEMA_CONTRACT, schema_contract_diff  # noqa: E402
from import_pricing_kb import BOOLEAN_COLUMNS, SQLITE_TABLES, normalize_sqlite_boolean  # noqa: E402


def contract_tables():
    return [
        {
            "name": table_name,
            "columns": [
                {"name": name, "type": field_type, "not_null": not_null}
                for name, field_type, not_null in columns
            ],
        }
        for table_name, columns in SQLITE_SCHEMA_CONTRACT.items()
    ]


class PricingKbSchemaContractTests(unittest.TestCase):
    def test_approved_schema_matches_contract(self):
        self.assertEqual(schema_contract_diff(contract_tables()), {})

    def test_missing_and_unexpected_columns_are_reported(self):
        tables = contract_tables()
        for table in tables:
            if table["name"] == "TDEK_TZMGC":
                table["columns"] = table["columns"][:-1] + [
                    {"name": "EXTRA", "type": "TEXT", "not_null": False}
                ]
        diff = schema_contract_diff(tables)
        self.assertIn("TDEK_TZMGC", diff)
        self.assertEqual(diff["TDEK_TZMGC"]["expected"][-1]["name"], "ID")
        self.assertEqual(diff["TDEK_TZMGC"]["actual"][-1]["name"], "EXTRA")

    def test_boolean_normalization_is_strict(self):
        for value in (-1, 1, "-1", "1", True, "true"):
            self.assertTrue(normalize_sqlite_boolean(value, source_table="TDEK_TZMGC", column="zycl", source_rowid=1))
        for value in (0, "0", False, "false"):
            self.assertFalse(normalize_sqlite_boolean(value, source_table="TDEK_TZMGC", column="zycl", source_rowid=1))
        self.assertIsNone(normalize_sqlite_boolean(None, source_table="TDEK_TZMGC", column="zycl", source_rowid=1))
        with self.assertRaisesRegex(ValueError, "source_rowid=9"):
            normalize_sqlite_boolean("yes", source_table="TDEK_TZMGC", column="zycl", source_rowid=9)

    def test_all_contract_columns_are_imported(self):
        for source_table, expected_columns in SQLITE_SCHEMA_CONTRACT.items():
            mapped_columns = SQLITE_TABLES[source_table][1]
            self.assertEqual([name.lower() for name, _, _ in expected_columns], mapped_columns)
        self.assertEqual(BOOLEAN_COLUMNS["TDEK_TZMGC"], {"zycl"})


if __name__ == "__main__":
    unittest.main()
