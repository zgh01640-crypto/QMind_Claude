"""Read-only API for structured standard appendix reference prices."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db.connection import get_connection


router = APIRouter()


class StandardReferencePrice(BaseModel):
    id: int
    document_id: int
    appendix_code: str
    sequence_no: int
    resource_type: str
    name: str
    unit: str
    price: float
    source_page_no: int
    source_page_id: int | None = None
    confidence: float | None = None
    raw_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class StandardReferencePriceList(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[StandardReferencePrice]


class StandardReferencePriceFilterOptions(BaseModel):
    total: int
    material_count: int
    machine_count: int
    units: list[str]


SELECT_COLUMNS = """
    id, document_id, appendix_code, sequence_no, resource_type, name, unit,
    price, source_page_no, source_page_id, confidence, raw_json,
    created_at, updated_at
"""


def serialize(row) -> StandardReferencePrice:
    return StandardReferencePrice(
        id=row[0],
        document_id=row[1],
        appendix_code=row[2],
        sequence_no=row[3],
        resource_type=row[4],
        name=row[5],
        unit=row[6],
        price=float(row[7]),
        source_page_no=row[8],
        source_page_id=row[9],
        confidence=float(row[10]) if row[10] is not None else None,
        raw_json=row[11] or {},
        created_at=row[12],
        updated_at=row[13],
    )


@router.get(
    "/standard-reference-prices/by-sequence/{sequence_no}",
    response_model=StandardReferencePrice,
)
def get_reference_price_by_sequence(
    sequence_no: int,
    document_id: int = Query(...),
    appendix_code: str = Query(..., min_length=1, max_length=32),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {SELECT_COLUMNS}
                FROM standard_reference_prices
                WHERE document_id=%s AND appendix_code=%s AND sequence_no=%s
                """,
                (document_id, appendix_code, sequence_no),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="reference price not found")
        return serialize(row)
    finally:
        conn.close()


@router.get(
    "/standard-reference-prices/filter-options",
    response_model=StandardReferencePriceFilterOptions,
)
def get_reference_price_filter_options(
    document_id: int = Query(...),
    appendix_code: str = Query("A", min_length=1, max_length=32),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE resource_type='材料'),
                       COUNT(*) FILTER (WHERE resource_type='机械')
                FROM standard_reference_prices
                WHERE document_id=%s AND appendix_code=%s
                """,
                (document_id, appendix_code),
            )
            total, material_count, machine_count = cur.fetchone()
            cur.execute(
                """
                SELECT DISTINCT unit
                FROM standard_reference_prices
                WHERE document_id=%s AND appendix_code=%s
                ORDER BY unit
                """,
                (document_id, appendix_code),
            )
            units = [row[0] for row in cur.fetchall()]
        return StandardReferencePriceFilterOptions(
            total=total,
            material_count=material_count,
            machine_count=machine_count,
            units=units,
        )
    finally:
        conn.close()


@router.get("/standard-reference-prices/{price_id}", response_model=StandardReferencePrice)
def get_reference_price(price_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {SELECT_COLUMNS} FROM standard_reference_prices WHERE id=%s",
                (price_id,),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="reference price not found")
        return serialize(row)
    finally:
        conn.close()


@router.get("/standard-reference-prices", response_model=StandardReferencePriceList)
def list_reference_prices(
    document_id: int | None = None,
    appendix_code: str | None = Query(None, max_length=32),
    q: str | None = Query(None, max_length=200),
    unit: str | None = Query(None, max_length=64),
    resource_type: str | None = Query(None, pattern="^(材料|机械)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    clauses: list[str] = []
    params: list[Any] = []
    if document_id is not None:
        clauses.append("document_id=%s")
        params.append(document_id)
    if appendix_code:
        clauses.append("appendix_code=%s")
        params.append(appendix_code)
    if q:
        clauses.append("name ILIKE %s")
        params.append(f"%{q.strip()}%")
    if unit:
        clauses.append("unit=%s")
        params.append(unit)
    if resource_type:
        clauses.append("resource_type=%s")
        params.append(resource_type)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    offset = (page - 1) * page_size

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM standard_reference_prices {where_sql}",
                params,
            )
            total = cur.fetchone()[0]
            cur.execute(
                f"""
                SELECT {SELECT_COLUMNS}
                FROM standard_reference_prices
                {where_sql}
                ORDER BY document_id, appendix_code, sequence_no
                LIMIT %s OFFSET %s
                """,
                params + [page_size, offset],
            )
            rows = cur.fetchall()
        return StandardReferencePriceList(
            total=total,
            page=page,
            page_size=page_size,
            items=[serialize(row) for row in rows],
        )
    finally:
        conn.close()
