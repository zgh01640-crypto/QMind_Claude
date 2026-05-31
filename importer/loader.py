from typing import Dict, List, Optional
import psycopg2.extras

from .parser import SheetMeta, PriceItem


def get_existing_period(conn, year: int, month: int, version: int) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM price_periods WHERE year=%s AND month=%s AND version=%s",
            (year, month, version),
        )
        row = cur.fetchone()
        return row[0] if row else None


def create_period(conn, year: int, month: int, version: int, filename: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO price_periods (year, month, version, source_file) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (year, month, version, filename),
        )
        period_id = cur.fetchone()[0]
    conn.commit()
    return period_id


def delete_period(conn, period_id: int):
    # CASCADE will remove price_items automatically
    with conn.cursor() as cur:
        cur.execute("DELETE FROM price_periods WHERE id = %s", (period_id,))
    conn.commit()


def upsert_categories(conn, sheets_meta: List[SheetMeta]) -> Dict[int, int]:
    """Insert or update categories, return {sheet_index: category_id}."""
    mapping: Dict[int, int] = {}
    with conn.cursor() as cur:
        for meta in sheets_meta:
            cur.execute(
                """
                INSERT INTO price_categories (sheet_index, sheet_name, category_group)
                VALUES (%s, %s, %s)
                ON CONFLICT (sheet_index, sheet_name)
                DO UPDATE SET category_group = EXCLUDED.category_group
                RETURNING id
                """,
                (meta.sheet_index, meta.sheet_name, meta.category_group),
            )
            mapping[meta.sheet_index] = cur.fetchone()[0]
    conn.commit()
    return mapping


def insert_items(
    conn,
    period_id: int,
    items: List[PriceItem],
    category_map: Dict[int, int],
) -> int:
    rows = [
        (
            period_id,
            category_map[item.sheet_index],
            item.sequence_no,
            item.material_code,
            item.material_name,
            item.specification,
            item.unit,
            item.price_yuan,
            item.coefficient,
            item.calculation_formula,
            item.remarks,
        )
        for item in items
        if item.sheet_index in category_map
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO price_items
                (period_id, category_id, sequence_no, material_code, material_name,
                 specification, unit, price_yuan, coefficient, calculation_formula, remarks)
            VALUES %s
            """,
            rows,
            page_size=500,
        )
    conn.commit()
    return len(rows)
