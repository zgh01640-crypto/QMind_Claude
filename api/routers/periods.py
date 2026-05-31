from fastapi import APIRouter, HTTPException
from db.connection import get_connection
from api.schemas import Period

router = APIRouter()


@router.get("/periods", response_model=list[Period])
def get_periods():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.year, p.month, p.version, p.source_file,
                       p.imported_at, COUNT(i.id) AS item_count
                FROM price_periods p
                LEFT JOIN price_items i ON i.period_id = p.id
                GROUP BY p.id
                ORDER BY p.year DESC, p.month DESC, p.version DESC
            """)
            rows = cur.fetchall()
        return [
            Period(id=r[0], year=r[1], month=r[2], version=r[3],
                   source_file=r[4], imported_at=r[5], item_count=r[6])
            for r in rows
        ]
    finally:
        conn.close()


@router.delete("/periods/{period_id}")
def delete_period_route(period_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM price_periods WHERE id = %s RETURNING id", (period_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="期次不存在")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
