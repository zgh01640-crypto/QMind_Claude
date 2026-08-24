"""SQLite business-table schema contract for the pricing knowledge base."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


# This is the approved schema of 智能组价系统库-海吉星练习8.6.db (version 19).
# SQLite type declarations are intentionally retained here so source drift is
# visible before a typed PostgreSQL import starts.
SQLITE_SCHEMA_CONTRACT: dict[str, tuple[tuple[str, str, bool], ...]] = {
    "TLibs": (("ID", "LARGEINT", False), ("MC", "VARCHAR2(200)", False), ("isQDK", "BOOLEAN", False)),
    "TQDK_TZJMC": (("QDKID", "LARGEINT", False), ("ID", "INTEGER", False), ("PID", "INTEGER", False), ("ZJMC", "VARCHAR2(100)", False), ("ZJSM", "VARCHAR2(5000)", False)),
    "TDEK_TZJMC": (("DEKID", "INTEGER", False), ("ID", "INTEGER", False), ("PID", "INTEGER", False), ("ZJMC", "VARCHAR2(200)", False), ("ZJSM", "VARCHAR2(5000)", False)),
    "TQDK_TQDZM": (("QDKID", "LARGEINT", False), ("ID", "INTEGER", False), ("ZMBH", "VARCHAR2(20)", False), ("ZMMC", "VARCHAR2(200)", False), ("DW", "VARCHAR2(20)", False), ("ZJH", "INTEGER", False), ("GZNR", "TEXT(1000)", False), ("Locked", "BOOLEAN", False)),
    "TQDK_TQDXMTZ": (("QDKID", "INT64", False), ("QDZMID", "INT64", False), ("TZMC", "VARCHAR2(200)", False), ("DEFAULTTZMS", "TEXT(200)", False), ("ZYTZ", "BOOLEAN", False), ("BCTZ", "BOOLEAN", False), ("ID", "INT64", False), ("REMARK", "VARCHAR2(300)", False)),
    "TDEK_TDEZM": (("DEKID", "INTEGER", False), ("ID", "INTEGER", False), ("ZMBH", "VARCHAR2(20)", False), ("ZMMC", "VARCHAR2(200)", False), ("DW", "VARCHAR2(20)", False), ("GZNR", "VARCHAR2(500)", False), ("ZJH", "INTEGER", False), ("DJ", "DOUBLE", False), ("RGF", "DOUBLE", False), ("CLF", "DOUBLE", False), ("JXF", "DOUBLE", False), ("ZCF", "DOUBLE", False), ("SBF", "DOUBLE", False), ("GLF", "DOUBLE", False), ("LR", "DOUBLE", False), ("AQWMSGF", "DOUBLE", False), ("QTCSF", "DOUBLE", False), ("GF", "DOUBLE", False), ("SJ", "DOUBLE", False)),
    "TDEK_TZMGC": (("DEKID", "INTEGER", False), ("DEZMID", "INTEGER", False), ("ZMBH", "VARCHAR2(20)", False), ("ZMMC", "VARCHAR2(200)", False), ("DW", "VARCHAR2(20)", False), ("GCL", "DOUBLE", False), ("LX", "INT", False), ("DJ", "DOUBLE", False), ("ZYCL", "BOOLEAN", False), ("ID", "INT64", False)),
    "TDEK_TZNHS": (("DEKID", "INTEGER", False), ("DEZMID", "INTEGER", False), ("TSXX", "VARCHAR2(150)", False), ("HSSM", "VARCHAR2(1000)", False), ("GROUPNO", "INT", False), ("ID", "INT64", False)),
    "TDEK_TZHHS": (("DEKID", "INTEGER", False), ("DEZMID", "INTEGER", False), ("TSXX", "VARCHAR2(100)", False), ("ZMBH", "VARCHAR2(20)", False), ("JCZ", "DOUBLE", False), ("ZJDW", "DOUBLE", False)),
    "TQDK_TQDZY": (("ID", "INT64", False), ("QDKID", "LARGEINT", False), ("QDZMID", "INTEGER", False), ("DEKID", "INTEGER", False), ("DEZMID", "INTEGER", False), ("ZMBH", "VARCHAR2(20)", False), ("ZMMC", "VARCHAR2(200)", False), ("DW", "VARCHAR2(20)", False)),
    "TQDK_TQDZY_SPECIAL": (("ID", "INT64", False), ("PID", "INT64", False), ("QDKID", "INT64", False), ("QDZMID", "INT64", False), ("DEKID", "INT64", False), ("DEZMID", "INT64", False), ("ZMBH", "VARCHAR2(20)", False), ("ZMMC", "TEXT(500)", False), ("DW", "VARCHAR2(20)", False)),
}


def _normalized_type(value: str) -> str:
    return "".join(value.upper().split())


def _column_tuple(column: Mapping[str, Any]) -> tuple[str, str, bool]:
    return (str(column.get("name", "")), _normalized_type(str(column.get("type", ""))), bool(column.get("not_null")))


def schema_contract_diff(
    tables: Iterable[Mapping[str, Any]], *, table_names: Iterable[str] | None = None
) -> dict[str, Any]:
    """Return a JSON-ready diff for every governed SQLite table.

    Unrecognised SQLite tables are intentionally out of scope. The governed
    tables must match the approved source exactly, including field order.
    """
    actual_by_table = {str(table.get("name")): table for table in tables}
    differences: dict[str, Any] = {}
    governed_names = tuple(table_names) if table_names is not None else tuple(SQLITE_SCHEMA_CONTRACT)
    for table_name in governed_names:
        expected = SQLITE_SCHEMA_CONTRACT[table_name]
        actual_table = actual_by_table.get(table_name)
        expected_json = [
            {"name": name, "type": field_type, "not_null": not_null}
            for name, field_type, not_null in expected
        ]
        if actual_table is None:
            differences[table_name] = {"missing_table": True, "expected": expected_json, "actual": []}
            continue
        actual = [_column_tuple(column) for column in actual_table.get("columns", [])]
        expected_normalized = [(name, _normalized_type(field_type), not_null) for name, field_type, not_null in expected]
        if actual != expected_normalized:
            differences[table_name] = {
                "missing_table": False,
                "expected": expected_json,
                "actual": [
                    {"name": name, "type": field_type, "not_null": not_null}
                    for name, field_type, not_null in actual
                ],
            }
    return differences


class SQLiteSchemaContractError(ValueError):
    def __init__(self, diff: dict[str, Any]):
        self.diff = diff
        super().__init__(f"SQLite knowledge-base schema contract mismatch: {diff}")
