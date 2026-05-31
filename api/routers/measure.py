from fastapi import APIRouter, Query
from typing import Optional
from db.connection import get_connection
from api.schemas import MeasureStandard, MeasureSection, MeasureItem, MeasureItemList

router = APIRouter()


@router.get("/measure/standards", response_model=list[MeasureStandard])
def get_measure_standards():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.id, s.name, s.source_file, s.imported_at,
                       COUNT(i.id) AS item_count
                FROM measure_standards s
                LEFT JOIN measure_items i ON i.standard_id = s.id
                GROUP BY s.id
                ORDER BY s.imported_at DESC
            """)
            rows = cur.fetchall()
        return [
            MeasureStandard(id=r[0], name=r[1], source_file=r[2],
                            imported_at=r[3], item_count=r[4])
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/measure/sections", response_model=list[MeasureSection])
def get_measure_sections(standard_id: int = Query(...)):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, code, name, level, parent_id, sort_order
                FROM measure_sections
                WHERE standard_id = %s
                ORDER BY sort_order
            """, (standard_id,))
            rows = cur.fetchall()
        return [
            MeasureSection(id=r[0], code=r[1], name=r[2], level=r[3],
                           parent_id=r[4], sort_order=r[5])
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/measure/items", response_model=MeasureItemList)
def get_measure_items(
    standard_id: int = Query(...),
    section_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    conn = get_connection()
    try:
        conditions = ["i.standard_id = %s"]
        params: list = [standard_id]

        if section_id:
            # 同时匹配该节及其子节
            conditions.append("""
                i.section_id IN (
                    SELECT id FROM measure_sections
                    WHERE id = %s OR parent_id = %s
                )
            """)
            params.extend([section_id, section_id])

        if search:
            conditions.append(
                "(i.item_code ILIKE %s OR i.item_name ILIKE %s OR i.item_features ILIKE %s)"
            )
            params.extend([f"%{search}%"] * 3)

        where = " AND ".join(conditions)
        offset = (page - 1) * page_size

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM measure_items i WHERE {where}", params)
            total = cur.fetchone()[0]

            cur.execute(f"""
                SELECT i.id, i.section_id, s.name AS section_name,
                       i.item_code, i.item_name, i.item_features,
                       i.unit, i.calc_rule, i.work_content
                FROM measure_items i
                LEFT JOIN measure_sections s ON s.id = i.section_id
                WHERE {where}
                ORDER BY i.item_code
                LIMIT %s OFFSET %s
            """, params + [page_size, offset])
            rows = cur.fetchall()

        items = [
            MeasureItem(
                id=r[0], section_id=r[1], section_name=r[2],
                item_code=r[3], item_name=r[4], item_features=r[5],
                unit=r[6], calc_rule=r[7], work_content=r[8],
            )
            for r in rows
        ]
        return MeasureItemList(total=total, items=items)
    finally:
        conn.close()


@router.get("/measure/all-items", response_model=list[MeasureItem])
def get_all_measure_items(standard_id: int = Query(...)):
    """返回标准下的全部清单项目，用于树形视图，不分页。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT i.id, i.section_id, s.name AS section_name,
                       i.item_code, i.item_name, i.item_features,
                       i.unit, i.calc_rule, i.work_content
                FROM measure_items i
                LEFT JOIN measure_sections s ON s.id = i.section_id
                WHERE i.standard_id = %s
                ORDER BY i.item_code
            """, (standard_id,))
            rows = cur.fetchall()
        return [
            MeasureItem(
                id=r[0], section_id=r[1], section_name=r[2],
                item_code=r[3], item_name=r[4], item_features=r[5],
                unit=r[6], calc_rule=r[7], work_content=r[8],
            )
            for r in rows
        ]
    finally:
        conn.close()
