from fastapi import APIRouter
from db.connection import get_connection
from api.schemas import Category

router = APIRouter()


@router.get("/categories", response_model=list[Category])
def get_categories():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, sheet_index, sheet_name, category_group
                FROM price_categories
                ORDER BY sheet_index
            """)
            rows = cur.fetchall()
        return [
            Category(id=r[0], sheet_index=r[1], sheet_name=r[2],
                     category_group=r[3] or "")
            for r in rows
        ]
    finally:
        conn.close()
