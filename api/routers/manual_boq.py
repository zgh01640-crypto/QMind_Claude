from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Query, Form
import tempfile
import os
import shutil
import subprocess
import sys
import re
from pathlib import Path

from pydantic import BaseModel

from db.connection import get_connection
from api import schemas
from api.auth import CurrentUser, current_user, ensure_ownership_schema, require_project_owner

router = APIRouter()

IMPORT_MANUAL_BOQ_SCRIPT = Path(__file__).resolve().parents[2] / "import_manual_boq.py"


class ManualBoqProjectRename(BaseModel):
    project_name: str


@router.get("/manual-boq/projects", response_model=list[schemas.ManualBoqProject])
def list_projects(user: CurrentUser = Depends(current_user)):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT id, project_name, bid_section, source_file, tag, imported_at, item_count
                FROM manual_boq_projects
            """
            params = []
            if not user.is_admin:
                sql += " WHERE owner_user_id=%s"
                params.append(user.id)
            sql += " ORDER BY imported_at DESC"
            cur.execute(sql, params)
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
    project_name: str | None = Form(None),
    user: CurrentUser = Depends(current_user),
):
    if not file.filename.endswith('.xlsx'):
        raise HTTPException(400, "仅支持 .xlsx 文件")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()

        conn = get_connection()
        try:
            ensure_ownership_schema(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM manual_boq_projects WHERE source_file=%s", (file.filename,))
                existing = cur.fetchone()
            if existing:
                require_project_owner(conn, user, int(existing[0]), manual=True)
        finally:
            conn.close()
        # 使用源码根目录下的绝对路径，避免服务启动目录变化后找不到导入脚本。
        if not IMPORT_MANUAL_BOQ_SCRIPT.is_file():
            raise HTTPException(500, f"人工工程导入脚本缺失: {IMPORT_MANUAL_BOQ_SCRIPT}")
        cmd = [sys.executable, str(IMPORT_MANUAL_BOQ_SCRIPT), tmp.name, '--original-name', file.filename]
        if force:
            cmd.append('--force')
        else:
            cmd.append('--allow-duplicate')
        if tag:
            cmd.extend(['--tag', tag])
        if project_name and project_name.strip():
            cmd.extend(['--project-name', project_name.strip()])
        env = {**os.environ, 'AUTH_OWNER_USER_ID': str(user.id)}
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
        if result.returncode != 0:
            raise HTTPException(500, result.stderr or "导入失败")

        # 导入脚本返回本次插入的准确 ID，避免并发上传时取到其他工程。
        match = re.search(r'PROJECT_ID=(\d+)', result.stdout or '')
        if not match:
            raise HTTPException(500, '导入完成但未返回工程 ID')
        project_id = int(match.group(1))

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, project_name, bid_section, source_file, tag, imported_at, item_count
                    FROM manual_boq_projects WHERE id = %s
                """, (project_id,))
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
def get_project(project_id: int, user: CurrentUser = Depends(current_user)):
    conn = get_connection()
    try:
        ensure_ownership_schema(conn)
        require_project_owner(conn, user, project_id, manual=True)
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


@router.patch("/manual-boq/projects/{project_id}", response_model=schemas.ManualBoqProject)
def rename_project(project_id: int, body: ManualBoqProjectRename, user: CurrentUser = Depends(current_user)):
    project_name = body.project_name.strip()
    if not project_name:
        raise HTTPException(400, "工程名称不能为空")
    if len(project_name) > 500:
        raise HTTPException(400, "工程名称不能超过 500 个字符")

    conn = get_connection()
    try:
        ensure_ownership_schema(conn)
        require_project_owner(conn, user, project_id, manual=True)
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE manual_boq_projects
                SET project_name = %s
                WHERE id = %s
                RETURNING id, project_name, bid_section, source_file, tag, imported_at, item_count
            """, (project_name, project_id))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "工程不存在")
        conn.commit()
        return schemas.ManualBoqProject(
            id=r[0], project_name=r[1], bid_section=r[2],
            source_file=r[3], tag=r[4], imported_at=r[5], item_count=r[6]
        )
    finally:
        conn.close()


@router.delete("/manual-boq/projects/{project_id}")
def delete_project(project_id: int, user: CurrentUser = Depends(current_user)):
    conn = get_connection()
    try:
        ensure_ownership_schema(conn)
        require_project_owner(conn, user, project_id, manual=True)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM manual_boq_projects WHERE id = %s RETURNING id", (project_id,))
            if not cur.fetchone():
                raise HTTPException(404, "工程不存在")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
