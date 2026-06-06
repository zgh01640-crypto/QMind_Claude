"""
消耗量标准 2024 API 路由
"""

from fastapi import APIRouter, Query
from typing import Optional
from db.connection import get_connection
from pydantic import BaseModel
from datetime import datetime, date

router = APIRouter()


# ============ Pydantic 模型 ============

class Quota2024Standard(BaseModel):
    id: int
    standard_code: str
    name: str
    region: Optional[str] = None
    base_date: Optional[date] = None
    source_file: Optional[str] = None
    imported_at: datetime


class Quota2024Chapter(BaseModel):
    id: int
    chapter_no: int
    code: Optional[str] = None
    name: str
    sort_order: int


class Quota2024Section(BaseModel):
    id: int
    section_type: str  # 'intro' | 'rules' | 'items'
    section_code: Optional[str] = None
    title: str
    content_md: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None


class Quota2024Resource(BaseModel):
    id: int
    resource_type: str
    resource_name: str
    unit: Optional[str] = None
    quantity: Optional[float] = None
    ref_price: Optional[float] = None


class Quota2024SubItem(BaseModel):
    id: int
    subitem_code: str
    subitem_name: Optional[str] = None
    variant_desc: Optional[str] = None
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
    resources: list[Quota2024Resource] = []


class Quota2024Item(BaseModel):
    id: int
    item_no: Optional[int] = None
    item_name: str
    work_content: Optional[str] = None
    unit: Optional[str] = None
    subitems: list[Quota2024SubItem] = []


class Quota2024Group(BaseModel):
    id: int
    group_code: Optional[str] = None
    group_name: str
    sort_order: int
    items: list[Quota2024Item] = []


class Quota2024ChapterDetail(BaseModel):
    chapter: Quota2024Chapter
    sections: list[Quota2024Section]


# ============ 路由 ============

@router.get("/quota2024/standards", response_model=list[Quota2024Standard])
def get_quota2024_standards():
    """获取所有标准"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, standard_code, name, region, base_date, source_file, imported_at
                FROM quota2024_standards
                ORDER BY imported_at DESC
            """)
            rows = cur.fetchall()

        return [
            Quota2024Standard(
                id=r[0], standard_code=r[1], name=r[2], region=r[3],
                base_date=r[4], source_file=r[5], imported_at=r[6]
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/quota2024/chapters", response_model=list[Quota2024Chapter])
def get_quota2024_chapters(standard_id: int = Query(...)):
    """获取标准的所有章"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, chapter_no, code, name, sort_order
                FROM quota2024_chapters
                WHERE standard_id = %s
                ORDER BY chapter_no
            """, (standard_id,))
            rows = cur.fetchall()

        return [
            Quota2024Chapter(
                id=r[0], chapter_no=r[1], code=r[2], name=r[3], sort_order=r[4]
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/quota2024/chapters/{chapter_id}/sections", response_model=Quota2024ChapterDetail)
def get_quota2024_chapter_sections(chapter_id: int):
    """获取章的详细信息及其三个节"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 获取章信息
            cur.execute("""
                SELECT id, chapter_no, code, name, sort_order
                FROM quota2024_chapters
                WHERE id = %s
            """, (chapter_id,))
            chapter_row = cur.fetchone()
            if not chapter_row:
                return {"error": "Chapter not found"}

            chapter = Quota2024Chapter(
                id=chapter_row[0], chapter_no=chapter_row[1],
                code=chapter_row[2], name=chapter_row[3], sort_order=chapter_row[4]
            )

            # 获取三个节
            cur.execute("""
                SELECT id, section_type, section_code, title, content_md, page_start, page_end
                FROM quota2024_sections
                WHERE chapter_id = %s
                ORDER BY section_type
            """, (chapter_id,))
            section_rows = cur.fetchall()

            sections = [
                Quota2024Section(
                    id=r[0], section_type=r[1], section_code=r[2], title=r[3],
                    content_md=r[4], page_start=r[5], page_end=r[6]
                )
                for r in section_rows
            ]

        return Quota2024ChapterDetail(chapter=chapter, sections=sections)
    finally:
        conn.close()


@router.get("/quota2024/sections/{section_id}/groups", response_model=list[Quota2024Group])
def get_quota2024_groups(section_id: int):
    """获取节内的分组列表"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, group_code, group_name, sort_order
                FROM quota2024_groups
                WHERE section_id = %s
                ORDER BY sort_order
            """, (section_id,))
            rows = cur.fetchall()

        return [
            Quota2024Group(
                id=r[0], group_code=r[1], group_name=r[2], sort_order=r[3]
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/quota2024/groups/{group_id}/items", response_model=Quota2024Group)
def get_quota2024_items(group_id: int):
    """
    获取分组内的项目及其子目和工料机

    避免 N+1 查询：先加载所有子目，再批量加载工料机
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 获取分组信息
            cur.execute("""
                SELECT id, group_code, group_name, sort_order
                FROM quota2024_groups
                WHERE id = %s
            """, (group_id,))
            group_row = cur.fetchone()
            if not group_row:
                return {"error": "Group not found"}

            group = Quota2024Group(
                id=group_row[0], group_code=group_row[1],
                group_name=group_row[2], sort_order=group_row[3]
            )

            # 获取项目
            cur.execute("""
                SELECT id, item_no, item_name, work_content, unit
                FROM quota2024_items
                WHERE group_id = %s
                ORDER BY sort_order
            """, (group_id,))
            item_rows = cur.fetchall()

            items = []
            all_subitem_ids = []  # 收集所有子目 ID

            for item_row in item_rows:
                item_id = item_row[0]

                # 获取该项的子目
                cur.execute("""
                    SELECT id, subitem_code, subitem_name, variant_desc,
                           total_unit_price, unit_price,
                           labor_cost, material_cost, machine_cost,
                           management_fee, profit, safety_fee, statutory_fee, tax
                    FROM quota2024_subitems
                    WHERE item_id = %s
                    ORDER BY sort_order
                """, (item_id,))
                subitem_rows = cur.fetchall()

                subitems = []
                for sub_row in subitem_rows:
                    subitem_id = sub_row[0]
                    all_subitem_ids.append(subitem_id)

                    subitems.append(Quota2024SubItem(
                        id=subitem_id,
                        subitem_code=sub_row[1],
                        subitem_name=sub_row[2],
                        variant_desc=sub_row[3],
                        total_unit_price=sub_row[4],
                        unit_price=sub_row[5],
                        labor_cost=sub_row[6],
                        material_cost=sub_row[7],
                        machine_cost=sub_row[8],
                        management_fee=sub_row[9],
                        profit=sub_row[10],
                        safety_fee=sub_row[11],
                        statutory_fee=sub_row[12],
                        tax=sub_row[13]
                    ))

                items.append(Quota2024Item(
                    id=item_id,
                    item_no=item_row[1],
                    item_name=item_row[2],
                    work_content=item_row[3],
                    unit=item_row[4],
                    subitems=subitems
                ))

            # 批量加载所有子目的工料机
            if all_subitem_ids:
                placeholders = ','.join(['%s'] * len(all_subitem_ids))
                cur.execute(f"""
                    SELECT id, subitem_id, resource_type, resource_name, unit, quantity, ref_price
                    FROM quota2024_resources
                    WHERE subitem_id IN ({placeholders})
                    ORDER BY subitem_id, sort_order
                """, all_subitem_ids)
                resource_rows = cur.fetchall()

                # 构建子目ID -> 资源列表的映射
                resources_map = {}
                for res_row in resource_rows:
                    subitem_id = res_row[1]
                    if subitem_id not in resources_map:
                        resources_map[subitem_id] = []
                    resources_map[subitem_id].append(Quota2024Resource(
                        id=res_row[0],
                        resource_type=res_row[2],
                        resource_name=res_row[3],
                        unit=res_row[4],
                        quantity=res_row[5],
                        ref_price=res_row[6]
                    ))

                # 绑定资源到子目
                for item in items:
                    for subitem in item.subitems:
                        subitem.resources = resources_map.get(subitem.id, [])

            group.items = items
            return group

    finally:
        conn.close()


@router.get("/quota2024/subitems/{subitem_id}", response_model=Quota2024SubItem)
def get_quota2024_subitem(subitem_id: int):
    """获取单个子目及其工料机"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 获取子目
            cur.execute("""
                SELECT id, subitem_code, subitem_name, variant_desc,
                       total_unit_price, unit_price,
                       labor_cost, material_cost, machine_cost,
                       management_fee, profit, safety_fee, statutory_fee, tax
                FROM quota2024_subitems
                WHERE id = %s
            """, (subitem_id,))
            row = cur.fetchone()
            if not row:
                return {"error": "SubItem not found"}

            subitem = Quota2024SubItem(
                id=row[0],
                subitem_code=row[1],
                subitem_name=row[2],
                variant_desc=row[3],
                total_unit_price=row[4],
                unit_price=row[5],
                labor_cost=row[6],
                material_cost=row[7],
                machine_cost=row[8],
                management_fee=row[9],
                profit=row[10],
                safety_fee=row[11],
                statutory_fee=row[12],
                tax=row[13]
            )

            # 获取工料机
            cur.execute("""
                SELECT id, resource_type, resource_name, unit, quantity, ref_price
                FROM quota2024_resources
                WHERE subitem_id = %s
                ORDER BY sort_order
            """, (subitem_id,))
            resource_rows = cur.fetchall()

            subitem.resources = [
                Quota2024Resource(
                    id=r[0],
                    resource_type=r[1],
                    resource_name=r[2],
                    unit=r[3],
                    quantity=r[4],
                    ref_price=r[5]
                )
                for r in resource_rows
            ]

            return subitem

    finally:
        conn.close()


@router.get("/quota2024/search")
def search_quota2024(q: str = Query(...), standard_id: int = Query(...)):
    """
    搜索子目编码和名称
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, subitem_code, item_name, variant_desc
                FROM quota2024_subitems
                JOIN quota2024_items ON quota2024_subitems.item_id = quota2024_items.id
                JOIN quota2024_groups ON quota2024_items.group_id = quota2024_groups.id
                JOIN quota2024_sections ON quota2024_groups.section_id = quota2024_sections.id
                JOIN quota2024_chapters ON quota2024_sections.chapter_id = quota2024_chapters.id
                WHERE quota2024_chapters.standard_id = %s
                  AND (quota2024_subitems.subitem_code ILIKE %s
                       OR quota2024_subitems.subitem_name ILIKE %s
                       OR quota2024_items.item_name ILIKE %s)
                LIMIT 50
            """, (standard_id, f"%{q}%", f"%{q}%", f"%{q}%"))
            rows = cur.fetchall()

        return [
            {
                "id": r[0],
                "code": r[1],
                "item_name": r[2],
                "variant_desc": r[3]
            }
            for r in rows
        ]

    finally:
        conn.close()
