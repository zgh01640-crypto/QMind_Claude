from fastapi import APIRouter, Query
from typing import Optional
from db.connection import get_connection
from api.schemas import PriceItemList, PriceItem, TrendPoint

router = APIRouter()


@router.get("/items", response_model=PriceItemList)
def get_items(
    period_id: int = Query(..., description="期次 ID"),
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    conn = get_connection()
    try:
        conditions = ["period_id = %s"]
        params: list = [period_id]

        if category_id:
            conditions.append("category_id = %s")
            params.append(category_id)
        if search:
            conditions.append("(material_name ILIKE %s OR specification ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])

        where = " AND ".join(conditions)
        offset = (page - 1) * page_size

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM price_items WHERE {where}", params)
            total = cur.fetchone()[0]

            cur.execute(
                f"""
                SELECT id, sequence_no, material_code, material_name,
                       specification, unit, price_yuan, coefficient,
                       calculation_formula, remarks
                FROM price_items
                WHERE {where}
                ORDER BY id
                LIMIT %s OFFSET %s
                """,
                params + [page_size, offset],
            )
            rows = cur.fetchall()

        items = [
            PriceItem(
                id=r[0], sequence_no=r[1], material_code=r[2],
                material_name=r[3], specification=r[4], unit=r[5],
                price_yuan=float(r[6]) if r[6] is not None else None,
                coefficient=float(r[7]) if r[7] is not None else None,
                calculation_formula=r[8], remarks=r[9],
            )
            for r in rows
        ]
        return PriceItemList(total=total, items=items)
    finally:
        conn.close()


@router.get("/items/trend", response_model=list[TrendPoint])
def get_trend(
    material_name: str = Query(...),
    specification: Optional[str] = None,
):
    conn = get_connection()
    try:
        conditions = ["i.material_name = %s"]
        params: list = [material_name]

        if specification:
            conditions.append("i.specification = %s")
            params.append(specification)

        where = " AND ".join(conditions)

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT p.year, p.month, p.version, i.price_yuan
                FROM price_items i
                JOIN price_periods p ON i.period_id = p.id
                WHERE {where}
                ORDER BY p.year, p.month, p.version
                """,
                params,
            )
            rows = cur.fetchall()

        return [
            TrendPoint(
                year=r[0], month=r[1], version=r[2],
                price_yuan=float(r[3]) if r[3] is not None else None,
                label=f"{r[0]}年{r[1]:02d}月",
            )
            for r in rows
        ]
    finally:
        conn.close()
