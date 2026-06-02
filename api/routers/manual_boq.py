from fastapi import APIRouter, HTTPException, UploadFile, File, Query
import tempfile
import os
import shutil
import subprocess
import sys

from db.connection import get_connection
from api import schemas

router = APIRouter()


@router.get("/manual-boq/projects", response_model=list[schemas.ManualBoqProject])
def list_projects():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, project_name, bid_section, source_file, tag, imported_at, item_count
                FROM manual_boq_projects ORDER BY imported_at DESC
            """)
            rows = cur.fetchall()
        return [schemas.ManualBoqProject(
            id=r[0], project_name=r[1], bid_section=r[2],
            source_file=r[3], tag=r[4], imported_at=r[5], item_count=r[6]
        ) for r in rows]
    finally:
        conn.close()


@router.post("/manual-boq/upload", response_model=schemas.ManualBoqProject)
async def upload_project(
    file: UploadFile = File(...),
    force: bool = Query(False),
    tag: str = Query(None),
):
    if not file.filename.endswith('.xlsx'):
        raise HTTPException(400, "仅支持 .xlsx 文件")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()

        # 调用导入脚本（传原始文件名作为 source_file 标识）
        cmd = [sys.executable, 'import_manual_boq.py', tmp.name, '--original-name', file.filename]
        if force:
            cmd.append('--force')
        if tag:
            cmd.extend(['--tag', tag])
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode != 0:
            raise HTTPException(500, result.stderr or "导入失败")

        # 返回最新插入的记录
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, project_name, bid_section, source_file, tag, imported_at, item_count
                    FROM manual_boq_projects ORDER BY imported_at DESC LIMIT 1
                """)
                r = cur.fetchone()
            if not r:
                raise HTTPException(500, "导入后未找到记录")
            return schemas.ManualBoqProject(
                id=r[0], project_name=r[1], bid_section=r[2],
                source_file=r[3], tag=r[4], imported_at=r[5], item_count=r[6]
            )
        finally:
            conn.close()
    finally:
        os.unlink(tmp.name)


@router.get("/manual-boq/projects/{project_id}", response_model=schemas.ManualBoqProjectDetail)
def get_project(project_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 工程基本信息
            cur.execute("""
                SELECT id, project_name, bid_section, source_file, tag, imported_at, item_count
                FROM manual_boq_projects WHERE id = %s
            """, (project_id,))
            pr = cur.fetchone()
        if not pr:
            raise HTTPException(404, "工程不存在")

        project = schemas.ManualBoqProject(
            id=pr[0], project_name=pr[1], bid_section=pr[2],
            source_file=pr[3], tag=pr[4], imported_at=pr[5], item_count=pr[6]
        )

        with conn.cursor() as cur:
            # 分部
            cur.execute("""
                SELECT id, seq, section_name FROM manual_boq_sections
                WHERE project_id = %s ORDER BY seq
            """, (project_id,))
            sections_raw = cur.fetchall()

            # 清单项（带分部名）
            cur.execute("""
                SELECT i.id, i.section_id, s.section_name, i.item_seq,
                       i.item_code, i.item_name, i.item_description,
                       i.unit, i.quantity, i.unit_price, i.total_price
                FROM manual_boq_items i
                LEFT JOIN manual_boq_sections s ON s.id = i.section_id
                WHERE i.project_id = %s ORDER BY i.section_id NULLS FIRST, i.item_seq
            """, (project_id,))
            items_raw = cur.fetchall()

            # 定额子目（含关联定额库信息）
            cur.execute("""
                SELECT q.id, q.boq_item_id, q.quota_code, q.quota_name, q.quota_unit,
                       q.quantity, q.unit_price, q.total_price, q.qty_factor, q.quota_item_id,
                       qi.total_unit_price, qi.unit_price AS qi_unit_price,
                       qi.labor_cost, qi.material_cost, qi.machine_cost,
                       qi.management_fee, qi.profit, qi.safety_fee, qi.statutory_fee, qi.tax,
                       qi.work_content, qi.variant_desc, qi.unit AS qi_unit
                FROM manual_boq_quotas q
                LEFT JOIN quota_items qi ON qi.id = q.quota_item_id
                WHERE q.boq_item_id IN (
                    SELECT id FROM manual_boq_items WHERE project_id = %s
                )
                ORDER BY q.boq_item_id, q.id
            """, (project_id,))
            quotas_raw = cur.fetchall()

        # 按 boq_item_id 聚合定额子目
        quotas_by_item: dict[int, list] = {}
        for r in quotas_raw:
            bid = r[1]
            quotas_by_item.setdefault(bid, []).append(schemas.ManualBoqQuota(
                id=r[0], boq_item_id=r[1],
                quota_code=r[2], quota_name=r[3], quota_unit=r[4],
                quantity=r[5], unit_price=r[6], total_price=r[7],
                qty_factor=r[8], quota_item_id=r[9],
                qi_total_unit_price=r[10], qi_unit_price=r[11],
                qi_labor_cost=r[12], qi_material_cost=r[13], qi_machine_cost=r[14],
                qi_management_fee=r[15], qi_profit=r[16],
                qi_safety_fee=r[17], qi_statutory_fee=r[18], qi_tax=r[19],
                qi_work_content=r[20], qi_variant_desc=r[21], qi_unit=r[22],
            ))

        # 构建 items
        items_out = [schemas.ManualBoqItem(
            id=r[0], section_id=r[1], section_name=r[2],
            item_seq=r[3], item_code=r[4], item_name=r[5],
            item_description=r[6], unit=r[7],
            quantity=float(r[8]) if r[8] is not None else None,
            unit_price=float(r[9]) if r[9] is not None else None,
            total_price=float(r[10]) if r[10] is not None else None,
            quotas=quotas_by_item.get(r[0], []),
        ) for r in items_raw]

        sections_out = [schemas.ManualBoqSection(
            id=r[0], seq=r[1], section_name=r[2]
        ) for r in sections_raw]

        return schemas.ManualBoqProjectDetail(
            project=project,
            sections=sections_out,
            items=items_out,
        )
    finally:
        conn.close()


@router.delete("/manual-boq/projects/{project_id}")
def delete_project(project_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM manual_boq_projects WHERE id = %s RETURNING id", (project_id,))
            if not cur.fetchone():
                raise HTTPException(404, "工程不存在")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
