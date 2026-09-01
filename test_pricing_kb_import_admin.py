import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from api.services.pricing_kb_import_admin import (
    apply_known_feature_default_corrections,
    expand_dependencies,
    inspect_sqlite,
    require_admin,
)


class PricingKbImportAdminTests(unittest.TestCase):
    def test_import_corrects_known_pump_weight_default(self):
        class Cursor:
            rowcount = 1

            def __init__(self):
                self.sql = ""
                self.params = None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params):
                self.sql = sql
                self.params = params

        class Connection:
            def __init__(self):
                self.cursor_instance = Cursor()
                self.committed = False

            def cursor(self):
                return self.cursor_instance

            def commit(self):
                self.committed = True

        conn = Connection()

        self.assertEqual(1, apply_known_feature_default_corrections(conn, 25))
        self.assertEqual((25,), conn.cursor_instance.params)
        self.assertIn("设备重量W(t) 1＜W≤1.2", conn.cursor_instance.sql)
        self.assertIn("设备重量W(t) 0.4＜W≤0.6", conn.cursor_instance.sql)
        self.assertTrue(conn.committed)

    def test_inspection_classifies_known_and_unknown_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.db"
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE TLibs(ID INTEGER, MC TEXT)")
            conn.execute("CREATE TABLE TNEW_RULES(NAME TEXT, PAYLOAD BLOB)")
            conn.execute("INSERT INTO TNEW_RULES VALUES('demo', X'616263')")
            conn.commit()
            conn.close()
            report = inspect_sqlite(path)
        tables = {item["name"]: item for item in report["tables"]}
        self.assertEqual("ok", report["quick_check"])
        self.assertTrue(tables["TLibs"]["known"])
        self.assertFalse(tables["TNEW_RULES"]["known"])
        self.assertEqual(1, tables["TNEW_RULES"]["row_count"])

    def test_dependencies_are_added_only_when_available(self):
        selected = expand_dependencies(
            {"TQDK_TQDZY"},
            {"TQDK_TQDZY", "TLibs", "TQDK_TQDZM", "TDEK_TDEZM"},
        )
        self.assertEqual(
            {"TQDK_TQDZY", "TLibs", "TQDK_TQDZM", "TDEK_TDEZM"},
            selected,
        )

    def test_admin_token_uses_backend_configuration(self):
        with patch.dict(os.environ, {"PRICING_KB_ADMIN_TOKEN": "secret"}):
            require_admin("secret")
            with self.assertRaises(HTTPException) as raised:
                require_admin("wrong")
        self.assertEqual(403, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
