"""API for the independent 2024 building consumption standard tables."""

from datetime import datetime, date
from typing import Optional, Any

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from db.connection import get_connection


router = APIRouter()


class BS2024Document(BaseModel):
    id: int
    standard_code: str
    name: str
    region: Optional[str] = None
    source_file: str
    source_sha256: str
    page_count: int
    publish_date: Optional[date] = None
    effective_date: Optional[date] = None
    imported_at: datetime
    latest_run_status: Optional[str] = None
    latest_run_stats: dict[str, Any] = {}
    chapter_count: int = 0
    subitem_count: int = 0
    issue_count: int = 0


class BS2024SectionNode(BaseModel):
    id: int
    section_type: str
    section_code: Optional[str] = None
    title: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None


class BS2024ChapterNode(BaseModel):
    id: int
    chapter_no: int
    code: Optional[str] = None
    title: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    sections: list[BS2024SectionNode] = []


class BS2024SectionDetail(BS2024SectionNode):
    document_id: int
    chapter_id: int
    content_md: Optional[str] = None


class BS2024Resource(BaseModel):
    id: int
    resource_type: str
    resource_name: str
    unit: Optional[str] = None
    quantity: Optional[float] = None
    ref_price: Optional[float] = None
    page_no: Optional[int] = None


class BS2024Subitem(BaseModel):
    id: int
    subitem_code: str
    subitem_name: Optional[str] = None
    variant_desc: Optional[str] = None
    unit: Optional[str] = None
    name_path: list[str] = []
    total_unit_price: Optional[float] = None
    unit_price: Optional[float] = None
    labor_cost: Optional[float] = None
    material_cost: Optional[float] = None
    machine_cost: Optional[float] = None
    management_fee: Optional[float] = None
    profit: Optional[float] = None
    safety_fee: Optional[float] = None
    statutory_fee: Optional[float] = None
    tax: Optional[float] = None
    page_no: Optional[int] = None
    confidence: Optional[float] = None
    resources: list[BS2024Resource] = []


class BS2024Item(BaseModel):
    id: int
    item_no: Optional[int] = None
    item_name: str
    work_content: Optional[str] = None
    unit: Optional[str] = None
    page_no: Optional[int] = None
    subitems: list[BS2024Subitem] = []


class BS2024Group(BaseModel):
    id: int
    group_code: Optional[str] = None
    group_name: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    sort_order: int
    item_count: int = 0
    items: list[BS2024Item] = []


class BS2024Issue(BaseModel):
    id: int
    page_no: Optional[int] = None
    severity: str
    issue_type: str
    message: str
    context_json: dict[str, Any] = {}
    created_at: datetime


@router.get("/building-standard-2024/documents", response_model=list[BS2024Document])
def list_documents():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT d.id, d.standard_code, d.name, d.region, d.source_file, d.source_sha256,
                       d.page_count, d.publish_date, d.effective_date, d.imported_at,
                       r.status, COALESCE(r.stats_json, '{}'::jsonb),
                       (SELECT COUNT(*) FROM bs2024_chapters c WHERE c.document_id = d.id) AS chapter_count,
                       (SELECT COUNT(*) FROM bs2024_subitems s WHERE s.document_id = d.id) AS subitem_count,
                       (SELECT COUNT(*) FROM bs2024_parse_issues i WHERE i.document_id = d.id) AS issue_count
                FROM bs2024_documents d
                LEFT JOIN LATERAL (
                    SELECT status, stats_json
                    FROM bs2024_parse_runs
                    WHERE document_id = d.id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) r ON TRUE
                ORDER BY d.imported_at DESC
            """)
            rows = cur.fetchall()
        return [
            BS2024Document(
                id=r[0], standard_code=r[1], name=r[2], region=r[3],
                source_file=r[4], source_sha256=r[5], page_count=r[6],
                publish_date=r[7], effective_date=r[8], imported_at=r[9],
                latest_run_status=r[10], latest_run_stats=r[11] or {},
                chapter_count=r[12], subitem_count=r[13], issue_count=r[14],
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/building-standard-2024/documents/{document_id}/tree", response_model=list[BS2024ChapterNode])
def get_tree(document_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, chapter_no, code, title, page_start, page_end
                FROM bs2024_chapters
                WHERE document_id = %s
                ORDER BY sort_order, chapter_no
            """, (document_id,))
            chapters = cur.fetchall()
            cur.execute("""
                SELECT id, chapter_id, section_type, section_code, title, page_start, page_end
                FROM bs2024_sections
                WHERE document_id = %s
                ORDER BY chapter_id, sort_order, page_start NULLS LAST
            """, (document_id,))
            sections = cur.fetchall()
        by_chapter: dict[int, list[BS2024SectionNode]] = {}
        for s in sections:
            by_chapter.setdefault(s[1], []).append(BS2024SectionNode(
                id=s[0], section_type=s[2], section_code=s[3], title=s[4],
                page_start=s[5], page_end=s[6],
            ))
        return [
            BS2024ChapterNode(
                id=c[0], chapter_no=c[1], code=c[2], title=c[3],
                page_start=c[4], page_end=c[5], sections=by_chapter.get(c[0], []),
            )
            for c in chapters
        ]
    finally:
        conn.close()


@router.get("/building-standard-2024/sections/{section_id}", response_model=BS2024SectionDetail)
def get_section(section_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, document_id, chapter_id, section_type, section_code, title,
                       content_md, page_start, page_end
                FROM bs2024_sections
                WHERE id = %s
            """, (section_id,))
            r = cur.fetchone()
        if not r:
            raise HTTPException(404, "Section not found")
        return BS2024SectionDetail(
            id=r[0], document_id=r[1], chapter_id=r[2], section_type=r[3],
            section_code=r[4], title=r[5], content_md=r[6],
            page_start=r[7], page_end=r[8],
        )
    finally:
        conn.close()


@router.get("/building-standard-2024/groups", response_model=list[BS2024Group])
def list_groups(section_id: int = Query(...)):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT g.id, g.group_code, g.group_name, g.page_start, g.page_end,
                       g.sort_order, COUNT(i.id) AS item_count
                FROM bs2024_item_groups g
                LEFT JOIN bs2024_items i ON i.group_id = g.id
                WHERE g.section_id = %s
                GROUP BY g.id
                ORDER BY g.sort_order, g.id
            """, (section_id,))
            rows = cur.fetchall()
        return [
            BS2024Group(
                id=r[0], group_code=r[1], group_name=r[2], page_start=r[3],
                page_end=r[4], sort_order=r[5], item_count=r[6],
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/building-standard-2024/groups/{group_id}/items", response_model=BS2024Group)
def get_group_items(group_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, group_code, group_name, page_start, page_end, sort_order
                FROM bs2024_item_groups
                WHERE id = %s
            """, (group_id,))
            group_row = cur.fetchone()
            if not group_row:
                raise HTTPException(404, "Group not found")

            cur.execute("""
                SELECT id, item_no, item_name, work_content, unit, page_no
                FROM bs2024_items
                WHERE group_id = %s
                ORDER BY sort_order, id
            """, (group_id,))
            item_rows = cur.fetchall()
            item_ids = [r[0] for r in item_rows]

            subitems_by_item: dict[int, list[BS2024Subitem]] = {iid: [] for iid in item_ids}
            subitem_ids: list[int] = []
            if item_ids:
                placeholders = ",".join(["%s"] * len(item_ids))
                cur.execute(f"""
                    SELECT id, item_id, subitem_code, subitem_name, variant_desc, unit, name_path_json,
                           total_unit_price, unit_price, labor_cost, material_cost, machine_cost,
                           management_fee, profit, safety_fee, statutory_fee, tax,
                           page_no, confidence
                    FROM bs2024_subitems
                    WHERE item_id IN ({placeholders})
                    ORDER BY item_id, sort_order, id
                """, item_ids)
                for r in cur.fetchall():
                    subitem_ids.append(r[0])
                    subitems_by_item.setdefault(r[1], []).append(BS2024Subitem(
                        id=r[0], subitem_code=r[2], subitem_name=r[3], variant_desc=r[4],
                        unit=r[5], name_path=r[6] or [],
                        total_unit_price=r[7], unit_price=r[8], labor_cost=r[9],
                        material_cost=r[10], machine_cost=r[11], management_fee=r[12],
                        profit=r[13], safety_fee=r[14], statutory_fee=r[15], tax=r[16],
                        page_no=r[17], confidence=r[18],
                    ))

            resources_by_subitem: dict[int, list[BS2024Resource]] = {sid: [] for sid in subitem_ids}
            if subitem_ids:
                placeholders = ",".join(["%s"] * len(subitem_ids))
                cur.execute(f"""
                    SELECT id, subitem_id, resource_type, resource_name, unit,
                           quantity, ref_price, page_no
                    FROM bs2024_resources
                    WHERE subitem_id IN ({placeholders})
                    ORDER BY subitem_id, sort_order, id
                """, subitem_ids)
                for r in cur.fetchall():
                    resources_by_subitem.setdefault(r[1], []).append(BS2024Resource(
                        id=r[0], resource_type=r[2], resource_name=r[3], unit=r[4],
                        quantity=r[5], ref_price=r[6], page_no=r[7],
                    ))
            for subs in subitems_by_item.values():
                for sub in subs:
                    sub.resources = resources_by_subitem.get(sub.id, [])

        items = [
            BS2024Item(
                id=r[0], item_no=r[1], item_name=r[2], work_content=r[3],
                unit=r[4], page_no=r[5], subitems=subitems_by_item.get(r[0], []),
            )
            for r in item_rows
        ]
        return BS2024Group(
            id=group_row[0], group_code=group_row[1], group_name=group_row[2],
            page_start=group_row[3], page_end=group_row[4],
            sort_order=group_row[5], item_count=len(items), items=items,
        )
    finally:
        conn.close()


@router.get("/building-standard-2024/search")
def search(document_id: int = Query(...), q: str = Query(...), limit: int = Query(50, le=200)):
    conn = get_connection()
    if not isinstance(limit, int):
        limit = 50
    pattern = f"%{q}%"
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.id, s.subitem_code, COALESCE(s.subitem_name, i.item_name) AS name,
                       s.variant_desc, i.unit, g.group_code, g.group_name, c.chapter_no, c.title
                FROM bs2024_subitems s
                JOIN bs2024_items i ON i.id = s.item_id
                JOIN bs2024_item_groups g ON g.id = i.group_id
                JOIN bs2024_sections sec ON sec.id = g.section_id
                JOIN bs2024_chapters c ON c.id = sec.chapter_id
                WHERE s.document_id = %s
                  AND (
                    s.subitem_code ILIKE %s OR s.subitem_name ILIKE %s OR
                    s.variant_desc ILIKE %s OR i.item_name ILIKE %s OR
                    s.name_path_json::text ILIKE %s OR
                    EXISTS (
                      SELECT 1 FROM bs2024_resources r
                      WHERE r.subitem_id = s.id AND r.resource_name ILIKE %s
                    )
                  )
                ORDER BY s.subitem_code
                LIMIT %s
            """, (document_id, pattern, pattern, pattern, pattern, pattern, pattern, limit))
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "subitem_code": r[1],
                "name": r[2],
                "variant_desc": r[3],
                "unit": r[4],
                "group_code": r[5],
                "group_name": r[6],
                "chapter_no": r[7],
                "chapter_title": r[8],
            }
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/building-standard-2024/parse-issues", response_model=list[BS2024Issue])
def list_issues(document_id: int = Query(...), page_no: Optional[int] = None, limit: int = Query(200, le=1000)):
    conn = get_connection()
    if not isinstance(limit, int):
        limit = 200
    try:
        conditions = ["document_id = %s"]
        params: list[Any] = [document_id]
        if page_no is not None:
            conditions.append("page_no = %s")
            params.append(page_no)
        params.append(limit)
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, page_no, severity, issue_type, message, context_json, created_at
                FROM bs2024_parse_issues
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
            """, params)
            rows = cur.fetchall()
        return [
            BS2024Issue(
                id=r[0], page_no=r[1], severity=r[2], issue_type=r[3],
                message=r[4], context_json=r[5] or {}, created_at=r[6],
            )
            for r in rows
        ]
    finally:
        conn.close()
