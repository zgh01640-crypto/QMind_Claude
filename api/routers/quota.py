from fastapi import APIRouter, Query
from typing import Optional
from db.connection import get_connection
from api.schemas import QuotaStandard, QuotaChapter, QuotaItem, QuotaItemList, QuotaResource

router = APIRouter()


@router.get("/quota/standards", response_model=list[QuotaStandard])
def get_quota_standards():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.id, s.standard_code, s.name, s.region, s.base_date, s.source_file,
                       s.imported_at, COUNT(i.id) AS item_count
                FROM quota_standards s
                LEFT JOIN quota_items i ON i.standard_id = s.id
                GROUP BY s.id
                ORDER BY s.imported_at DESC
            """)
            rows = cur.fetchall()
        return [
            QuotaStandard(
                id=r[0], standard_code=r[1], name=r[2], region=r[3],
                base_date=r[4], source_file=r[5], imported_at=r[6], item_count=r[7],
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/quota/chapters", response_model=list[QuotaChapter])
def get_quota_chapters(standard_id: int = Query(...)):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, code, name, level, parent_id, sort_order
                FROM quota_chapters
                WHERE standard_id = %s
                ORDER BY sort_order
            """, (standard_id,))
            rows = cur.fetchall()
        return [
            QuotaChapter(id=r[0], code=r[1], name=r[2], level=r[3],
                         parent_id=r[4], sort_order=r[5])
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/quota/items", response_model=QuotaItemList)
def get_quota_items(
    standard_id: int = Query(...),
    chapter_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    conn = get_connection()
    try:
        conditions = ["i.standard_id = %s"]
        params: list = [standard_id]

        if chapter_id:
            conditions.append("i.chapter_id = %s")
            params.append(chapter_id)
        if search:
            conditions.append("(i.item_code ILIKE %s OR i.item_name ILIKE %s OR i.variant_desc ILIKE %s)")
            params.extend([f"%{search}%"] * 3)

        where = " AND ".join(conditions)
        offset = (page - 1) * page_size

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM quota_items i WHERE {where}", params)
            total = cur.fetchone()[0]

            cur.execute(f"""
                SELECT i.id, i.chapter_id, c.name AS chapter_name,
                       i.item_code, i.item_name, i.variant_desc, i.unit,
                       i.work_content, i.total_unit_price, i.unit_price,
                       i.labor_cost, i.material_cost, i.machine_cost,
                       i.management_fee, i.profit, i.safety_fee,
                       i.statutory_fee, i.tax, i.source_row
                FROM quota_items i
                LEFT JOIN quota_chapters c ON c.id = i.chapter_id
                WHERE {where}
                ORDER BY SPLIT_PART(i.item_code, '-', 1),
                         CAST(SPLIT_PART(i.item_code, '-', 2) AS INTEGER),
                         i.id
                LIMIT %s OFFSET %s
            """, params + [page_size, offset])
            item_rows = cur.fetchall()

            # 批量加载本页工料机
            item_ids = [r[0] for r in item_rows]
            resources_map: dict[int, list] = {iid: [] for iid in item_ids}
            if item_ids:
                placeholders = ','.join(['%s'] * len(item_ids))
                cur.execute(f"""
                    SELECT id, item_id, resource_type, resource_name, unit, quantity, ref_price
                    FROM quota_resources
                    WHERE item_id IN ({placeholders})
                    ORDER BY item_id, resource_type, id
                """, item_ids)
                for rr in cur.fetchall():
                    resources_map[rr[1]].append(QuotaResource(
                        id=rr[0], resource_type=rr[2], resource_name=rr[3],
                        unit=rr[4],
                        quantity=float(rr[5]) if rr[5] is not None else None,
                        ref_price=float(rr[6]) if rr[6] is not None else None,
                    ))

        items = [
            QuotaItem(
                id=r[0], chapter_id=r[1], chapter_name=r[2],
                item_code=r[3], item_name=r[4], variant_desc=r[5], unit=r[6],
                work_content=r[7],
                total_unit_price=float(r[8]) if r[8] is not None else None,
                unit_price=float(r[9]) if r[9] is not None else None,
                labor_cost=float(r[10]) if r[10] is not None else None,
                material_cost=float(r[11]) if r[11] is not None else None,
                machine_cost=float(r[12]) if r[12] is not None else None,
                management_fee=float(r[13]) if r[13] is not None else None,
                profit=float(r[14]) if r[14] is not None else None,
                safety_fee=float(r[15]) if r[15] is not None else None,
                statutory_fee=float(r[16]) if r[16] is not None else None,
                tax=float(r[17]) if r[17] is not None else None,
                source_row=r[18],
                resources=resources_map.get(r[0], []),
            )
            for r in item_rows
        ]
        return QuotaItemList(total=total, items=items)
    finally:
        conn.close()


@router.get("/quota/all-items", response_model=list[QuotaItem])
def get_all_quota_items(standard_id: int = Query(...)):
    """返回标准下的全部子目（含工料机），用于树形视图，不分页。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT i.id, i.chapter_id, c.name AS chapter_name,
                       i.item_code, i.item_name, i.variant_desc, i.unit,
                       i.work_content, i.total_unit_price, i.unit_price,
                       i.labor_cost, i.material_cost, i.machine_cost,
                       i.management_fee, i.profit, i.safety_fee,
                       i.statutory_fee, i.tax, i.source_row
                FROM quota_items i
                LEFT JOIN quota_chapters c ON c.id = i.chapter_id
                WHERE i.standard_id = %s
                ORDER BY SPLIT_PART(i.item_code, '-', 1),
                         CAST(SPLIT_PART(i.item_code, '-', 2) AS INTEGER)
            """, (standard_id,))
            item_rows = cur.fetchall()

            item_ids = [r[0] for r in item_rows]
            resources_map: dict[int, list] = {iid: [] for iid in item_ids}
            if item_ids:
                placeholders = ','.join(['%s'] * len(item_ids))
                cur.execute(f"""
                    SELECT id, item_id, resource_type, resource_name, unit, quantity, ref_price
                    FROM quota_resources
                    WHERE item_id IN ({placeholders})
                    ORDER BY item_id, resource_type, id
                """, item_ids)
                for rr in cur.fetchall():
                    resources_map[rr[1]].append(QuotaResource(
                        id=rr[0], resource_type=rr[2], resource_name=rr[3],
                        unit=rr[4],
                        quantity=float(rr[5]) if rr[5] is not None else None,
                        ref_price=float(rr[6]) if rr[6] is not None else None,
                    ))

        return [
            QuotaItem(
                id=r[0], chapter_id=r[1], chapter_name=r[2],
                item_code=r[3], item_name=r[4], variant_desc=r[5], unit=r[6],
                work_content=r[7],
                total_unit_price=float(r[8]) if r[8] is not None else None,
                unit_price=float(r[9]) if r[9] is not None else None,
                labor_cost=float(r[10]) if r[10] is not None else None,
                material_cost=float(r[11]) if r[11] is not None else None,
                machine_cost=float(r[12]) if r[12] is not None else None,
                management_fee=float(r[13]) if r[13] is not None else None,
                profit=float(r[14]) if r[14] is not None else None,
                safety_fee=float(r[15]) if r[15] is not None else None,
                statutory_fee=float(r[16]) if r[16] is not None else None,
                tax=float(r[17]) if r[17] is not None else None,
                source_row=r[18],
                resources=resources_map.get(r[0], []),
            )
            for r in item_rows
        ]
    finally:
        conn.close()
