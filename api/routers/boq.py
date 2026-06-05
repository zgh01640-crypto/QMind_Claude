import os
import tempfile
import threading

from fastapi import APIRouter, Query, HTTPException, UploadFile, File as FastAPIFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json
from db.connection import get_connection
from api.schemas import (
    BoqProject, BoqSection, BoqItem, BoqItemList,
    BoqMatchResult, BoqSummaryItem, BoqResourceSummary, QuotaResource,
    BoqMatchRun, CompareResult, CompareRunInfo, CompareQuota, CompareBoqItem, CompareSummary,
)
from importer.boq_matcher import build_system_prompt, match_boq_item, stream_match_boq_item, _build_user_msg

router = APIRouter()


# ── 上传 BOQ ──────────────────────────────────────────────────────────────────

@router.post("/boq/upload", response_model=BoqProject)
def upload_boq(file: UploadFile = FastAPIFile(...), force: bool = False):
    """上传 .xlsx 文件，解析并入库，返回 BoqProject。"""
    from importer.boq_parser import parse_boq_workbook
    from importer import boq_loader

    filename = file.filename or "upload.xlsx"
    conn = get_connection()
    try:
        boq_loader.init_schema(conn)

        # 检查同名文件是否已存在
        existing_id = boq_loader.get_project_by_source(conn, filename)
        if existing_id and not force:
            raise HTTPException(
                status_code=409,
                detail=f"文件 '{filename}' 已存在（project_id={existing_id}），如需覆盖请传 force=true",
            )
        if existing_id and force:
            boq_loader.delete_project(conn, existing_id)

        # 写临时文件
        suffix = os.path.splitext(filename)[1] or ".xlsx"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file.file.read())
            tmp_path = tmp.name

        try:
            project_info, sections, items = parse_boq_workbook(tmp_path)
        finally:
            os.unlink(tmp_path)

        project_id = boq_loader.insert_project(
            conn,
            project_info["project_name"],
            project_info.get("bid_section"),
            filename,
            None,  # tag
        )
        seq_to_id = boq_loader.insert_sections(conn, project_id, sections)
        item_count = boq_loader.insert_items(conn, project_id, items, seq_to_id)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, project_name, bid_section, source_file, tag, imported_at FROM boq_projects WHERE id = %s",
                (project_id,),
            )
            row = cur.fetchone()

        return BoqProject(
            id=row[0], project_name=row[1], bid_section=row[2],
            source_file=row[3], tag=row[4], imported_at=row[5],
            item_count=item_count,
        )
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ── 项目 / 分部 / 清单项 ──────────────────────────────────────────────────────

@router.get("/boq/projects", response_model=list[BoqProject])
def get_boq_projects():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.project_name, p.bid_section, p.source_file,
                       p.tag, p.imported_at, COUNT(i.id) AS item_count
                FROM boq_projects p
                LEFT JOIN boq_items i ON i.project_id = p.id
                GROUP BY p.id
                ORDER BY p.imported_at DESC
            """)
            rows = cur.fetchall()
        return [
            BoqProject(
                id=r[0], project_name=r[1], bid_section=r[2],
                source_file=r[3], tag=r[4], imported_at=r[5], item_count=r[6],
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/boq/sections", response_model=list[BoqSection])
def get_boq_sections(project_id: int = Query(...)):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, seq, section_name
                FROM boq_sections
                WHERE project_id = %s
                ORDER BY seq
            """, (project_id,))
            rows = cur.fetchall()
        return [BoqSection(id=r[0], seq=r[1], section_name=r[2]) for r in rows]
    finally:
        conn.close()


@router.get("/boq/items", response_model=BoqItemList)
def get_boq_items(
    project_id: int = Query(...),
    section_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    conn = get_connection()
    try:
        conditions = ["i.project_id = %s"]
        params: list = [project_id]

        if section_id:
            conditions.append("i.section_id = %s")
            params.append(section_id)
        if search:
            conditions.append("(i.item_code ILIKE %s OR i.item_name ILIKE %s OR i.item_description ILIKE %s)")
            params.extend([f"%{search}%"] * 3)

        where = " AND ".join(conditions)
        offset = (page - 1) * page_size

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM boq_items i WHERE {where}", params)
            total = cur.fetchone()[0]

            cur.execute(f"""
                SELECT i.id, i.section_id, s.section_name,
                       i.item_seq, i.item_code, i.item_name,
                       i.item_description, i.unit, i.quantity,
                       i.unit_price, i.total_price, i.provisional_price
                FROM boq_items i
                LEFT JOIN boq_sections s ON s.id = i.section_id
                WHERE {where}
                ORDER BY i.item_seq
                LIMIT %s OFFSET %s
            """, params + [page_size, offset])
            rows = cur.fetchall()

        items = [
            BoqItem(
                id=r[0], section_id=r[1], section_name=r[2],
                item_seq=r[3], item_code=r[4], item_name=r[5],
                item_description=r[6], unit=r[7],
                quantity=float(r[8]) if r[8] is not None else None,
                unit_price=float(r[9]) if r[9] is not None else None,
                total_price=float(r[10]) if r[10] is not None else None,
                provisional_price=float(r[11]) if r[11] is not None else None,
            )
            for r in rows
        ]
        return BoqItemList(total=total, items=items)
    finally:
        conn.close()


@router.get("/boq/all-items", response_model=list[BoqItem])
def get_all_boq_items(project_id: int = Query(...)):
    """返回项目下全部清单项（含分部名），用于树形视图。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT i.id, i.section_id, s.section_name,
                       i.item_seq, i.item_code, i.item_name,
                       i.item_description, i.unit, i.quantity,
                       i.unit_price, i.total_price, i.provisional_price
                FROM boq_items i
                LEFT JOIN boq_sections s ON s.id = i.section_id
                WHERE i.project_id = %s
                ORDER BY i.item_seq
            """, (project_id,))
            rows = cur.fetchall()
        return [
            BoqItem(
                id=r[0], section_id=r[1], section_name=r[2],
                item_seq=r[3], item_code=r[4], item_name=r[5],
                item_description=r[6], unit=r[7],
                quantity=float(r[8]) if r[8] is not None else None,
                unit_price=float(r[9]) if r[9] is not None else None,
                total_price=float(r[10]) if r[10] is not None else None,
                provisional_price=float(r[11]) if r[11] is not None else None,
            )
            for r in rows
        ]
    finally:
        conn.close()


# ── 匹配运行记录 ──────────────────────────────────────────────────────────────

@router.get("/boq/runs", response_model=list[BoqMatchRun])
def get_boq_runs(project_id: int = Query(...)):
    """获取项目的所有匹配运行记录，按创建时间倒序。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.id, r.project_id, r.standard_id, s.standard_code,
                       r.status, r.total_items, r.matched_items,
                       r.created_at, r.finished_at, r.run_name, r.standard_ids
                FROM boq_match_runs r
                LEFT JOIN quota_standards s ON s.id = r.standard_id
                WHERE r.project_id = %s
                ORDER BY r.created_at DESC
            """, (project_id,))
            rows = cur.fetchall()
        return [
            BoqMatchRun(
                id=r[0], project_id=r[1], standard_id=r[2] or 0,
                standard_code=r[3], status=r[4],
                total_items=r[5], matched_items=r[6],
                created_at=r[7], finished_at=r[8],
                run_name=r[9], standard_ids=r[10],
            )
            for r in rows
        ]
    finally:
        conn.close()


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def _ensure_match_schema(conn):
    schema_path = os.path.join(os.path.dirname(__file__), '..', '..', 'db', 'schema_boq.sql')
    with open(schema_path, encoding='utf-8') as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def _run_match_for_item(conn, boq_item_id: int, standard_id: int, system_prompt: str, run_id) -> list[BoqMatchResult]:
    """对单条清单项运行 AI 匹配，保存结果到 DB，返回匹配列表。"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, item_code, item_name, item_description, unit, quantity, project_id
            FROM boq_items WHERE id = %s
        """, (boq_item_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="清单项不存在")

    boq_item = {
        "id": row[0], "item_code": row[1], "item_name": row[2],
        "item_description": row[3], "unit": row[4],
        "quantity": float(row[5]) if row[5] else None,
        "project_id": row[6],
    }
    project_id = boq_item["project_id"]

    matches = match_boq_item(boq_item, system_prompt)

    with conn.cursor() as cur:
        if run_id is None:
            # 单条匹配：沿用旧逻辑，删除旧 AI 建议后 upsert
            cur.execute("""
                DELETE FROM boq_quota_matches
                WHERE boq_item_id = %s AND status = 'ai'
            """, (boq_item_id,))

            results = []
            for m in matches:
                cur.execute("""
                    SELECT item_code, item_name, variant_desc, unit
                    FROM quota_items WHERE id = %s
                """, (m.quota_item_id,))
                q = cur.fetchone()
                if not q:
                    continue

                cur.execute("""
                    INSERT INTO boq_quota_matches
                        (project_id, boq_item_id, quota_item_id, standard_id,
                         qty_factor, ai_reasoning, reasoning_chain, confidence, status,
                         work_procedure, factor_explanation)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ai', %s, %s)
                    ON CONFLICT (boq_item_id, quota_item_id)
                    DO UPDATE SET
                        qty_factor = EXCLUDED.qty_factor,
                        ai_reasoning = EXCLUDED.ai_reasoning,
                        reasoning_chain = EXCLUDED.reasoning_chain,
                        confidence = EXCLUDED.confidence,
                        work_procedure = EXCLUDED.work_procedure,
                        factor_explanation = EXCLUDED.factor_explanation,
                        status = 'ai',
                        created_at = NOW()
                    RETURNING id
                """, (project_id, boq_item_id, m.quota_item_id, standard_id,
                      m.qty_factor, m.reasoning, m.reasoning_chain, m.confidence,
                      m.work_procedure, m.factor_explanation))
                match_id = cur.fetchone()[0]
                results.append(BoqMatchResult(
                    id=match_id,
                    boq_item_id=boq_item_id,
                    quota_item_id=m.quota_item_id,
                    quota_item_code=q[0],
                    quota_item_name=q[1],
                    quota_variant_desc=q[2],
                    quota_unit=q[3],
                    qty_factor=m.qty_factor,
                    ai_reasoning=m.reasoning,
                    reasoning_chain=m.reasoning_chain,
                    confidence=m.confidence,
                    status="ai",
                    work_procedure=m.work_procedure,
                    factor_explanation=m.factor_explanation,
                ))
        else:
            # 批量匹配：带 run_id，直接 INSERT，不做 upsert
            results = []
            for m in matches:
                cur.execute("""
                    SELECT item_code, item_name, variant_desc, unit
                    FROM quota_items WHERE id = %s
                """, (m.quota_item_id,))
                q = cur.fetchone()
                if not q:
                    continue

                cur.execute("""
                    INSERT INTO boq_quota_matches
                        (project_id, boq_item_id, quota_item_id, standard_id,
                         qty_factor, ai_reasoning, reasoning_chain, confidence, status, run_id,
                         work_procedure, factor_explanation)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ai', %s, %s, %s)
                    ON CONFLICT (run_id, boq_item_id, quota_item_id) DO NOTHING
                    RETURNING id
                """, (project_id, boq_item_id, m.quota_item_id, standard_id,
                      m.qty_factor, m.reasoning, m.reasoning_chain, m.confidence, run_id,
                      m.work_procedure, m.factor_explanation))
                row = cur.fetchone()
                if not row:
                    continue
                match_id = row[0]
                results.append(BoqMatchResult(
                    id=match_id,
                    boq_item_id=boq_item_id,
                    quota_item_id=m.quota_item_id,
                    quota_item_code=q[0],
                    quota_item_name=q[1],
                    quota_variant_desc=q[2],
                    quota_unit=q[3],
                    qty_factor=m.qty_factor,
                    ai_reasoning=m.reasoning,
                    reasoning_chain=m.reasoning_chain,
                    confidence=m.confidence,
                    status="ai",
                ))

    conn.commit()
    return results


# ── 套定额端点 ────────────────────────────────────────────────────────────────

class MatchItemRequest(BaseModel):
    boq_item_id: int
    standard_id: int


class MatchProjectRequest(BaseModel):
    project_id: int
    standard_id: int = 0           # 向后兼容（单标准时使用）
    standard_ids: list[int] = []   # 多标准时使用，为空则回退到 standard_id
    run_name: str = ""


@router.post("/boq/match-item", response_model=list[BoqMatchResult])
def match_item(req: MatchItemRequest):
    """对单条清单项触发 AI 匹配。"""
    conn = get_connection()
    try:
        _ensure_match_schema(conn)
        sp = build_system_prompt(conn, req.standard_id)
        return _run_match_for_item(conn, req.boq_item_id, req.standard_id, sp, run_id=None)
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/boq/match-project")
def match_project(req: MatchProjectRequest):
    """批量套定额：立即返回 run_id，后台线程执行，前端轮询进度。"""
    conn = get_connection()
    try:
        _ensure_match_schema(conn)

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM boq_items WHERE project_id = %s", (req.project_id,))
            total = cur.fetchone()[0]
            cur.execute("SELECT standard_code FROM quota_standards WHERE id = %s", (req.standard_id,))
            sc_row = cur.fetchone()
        standard_code = sc_row[0] if sc_row else None

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO boq_match_runs
                    (project_id, standard_id, standard_code, status, total_items, matched_items)
                VALUES (%s, %s, %s, 'running', %s, 0)
                RETURNING id
            """, (req.project_id, req.standard_id, standard_code, total))
            run_id = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    def run_in_background():
        bg_conn = get_connection()
        try:
            sp = build_system_prompt(bg_conn, req.standard_id)
            with bg_conn.cursor() as cur:
                cur.execute("""
                    SELECT id, item_name FROM boq_items
                    WHERE project_id = %s ORDER BY item_seq
                """, (req.project_id,))
                items = cur.fetchall()

            matched_count = 0
            for item_id, item_name in items:
                try:
                    result = _run_match_for_item(bg_conn, item_id, req.standard_id, sp, run_id=run_id)
                    matched_count += len(result)
                except Exception as e:
                    # 单条失败记录日志但继续，不阻塞整个批次
                    import sys
                    print(f"[match_run {run_id}] 跳过 item {item_id} ({item_name}): {e}", file=sys.stderr)
                    # 回滚本条可能的脏事务
                    try:
                        bg_conn.rollback()
                    except Exception:
                        pass
                # 每条完成后实时更新进度
                try:
                    with bg_conn.cursor() as cur:
                        cur.execute(
                            "UPDATE boq_match_runs SET matched_items = %s WHERE id = %s",
                            (matched_count, run_id)
                        )
                    bg_conn.commit()
                except Exception:
                    pass

            with bg_conn.cursor() as cur:
                cur.execute("""
                    UPDATE boq_match_runs
                    SET status = 'done', matched_items = %s, finished_at = NOW()
                    WHERE id = %s
                """, (matched_count, run_id))
            bg_conn.commit()
        except Exception as e:
            import sys
            print(f"[match_run {run_id}] 整体异常: {e}", file=sys.stderr)
            try:
                with bg_conn.cursor() as cur:
                    cur.execute(
                        "UPDATE boq_match_runs SET status = 'error', finished_at = NOW() WHERE id = %s",
                        (run_id,)
                    )
                bg_conn.commit()
            except Exception:
                pass
        finally:
            bg_conn.close()

    threading.Thread(target=run_in_background, daemon=True).start()
    return {"run_id": run_id, "status": "running", "total": total}


# ── 匹配结果 CRUD ─────────────────────────────────────────────────────────────

@router.get("/boq/matches", response_model=list[BoqMatchResult])
def get_boq_matches(run_id: int = Query(...)):
    """获取指定 run 的所有匹配结果（含定额完整信息和工料机）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT m.id, m.boq_item_id, m.quota_item_id,
                       m.qty_factor, m.ai_reasoning, m.reasoning_chain,
                       m.confidence, m.status, m.confirmed_at,
                       m.work_procedure, m.factor_explanation,
                       q.item_code, q.item_name, q.variant_desc, q.unit,
                       q.work_content,
                       q.total_unit_price, q.unit_price,
                       q.labor_cost, q.material_cost, q.machine_cost,
                       q.management_fee, q.profit,
                       q.safety_fee, q.statutory_fee, q.tax
                FROM boq_quota_matches m
                JOIN quota_items q ON q.id = m.quota_item_id
                WHERE m.run_id = %s
                ORDER BY m.boq_item_id, m.id
            """, (run_id,))
            rows = cur.fetchall()

            # 批量加载工料机
            quota_ids = list({r[2] for r in rows})
            resources_map: dict[int, list] = {qid: [] for qid in quota_ids}
            if quota_ids:
                placeholders = ','.join(['%s'] * len(quota_ids))
                cur.execute(f"""
                    SELECT id, item_id, resource_type, resource_name, unit, quantity, ref_price
                    FROM quota_resources
                    WHERE item_id IN ({placeholders})
                    ORDER BY item_id, resource_type, id
                """, quota_ids)
                for rr in cur.fetchall():
                    resources_map[rr[1]].append(QuotaResource(
                        id=rr[0], resource_type=rr[2], resource_name=rr[3],
                        unit=rr[4],
                        quantity=float(rr[5]) if rr[5] is not None else None,
                        ref_price=float(rr[6]) if rr[6] is not None else None,
                    ))

        def _f(v):
            return float(v) if v is not None else None

        return [
            BoqMatchResult(
                id=r[0], boq_item_id=r[1], quota_item_id=r[2],
                qty_factor=float(r[3]),
                ai_reasoning=r[4], reasoning_chain=r[5],
                confidence=r[6], status=r[7], confirmed_at=r[8],
                work_procedure=r[9], factor_explanation=r[10],
                quota_item_code=r[11], quota_item_name=r[12],
                quota_variant_desc=r[13], quota_unit=r[14],
                quota_work_content=r[15],
                quota_total_unit_price=_f(r[16]), quota_unit_price=_f(r[17]),
                quota_labor_cost=_f(r[18]), quota_material_cost=_f(r[19]),
                quota_machine_cost=_f(r[20]), quota_management_fee=_f(r[21]),
                quota_profit=_f(r[22]), quota_safety_fee=_f(r[23]),
                quota_statutory_fee=_f(r[24]), quota_tax=_f(r[25]),
                quota_resources=resources_map.get(r[2], []),
            )
            for r in rows
        ]
    finally:
        conn.close()


class UpdateMatchRequest(BaseModel):
    status: str  # confirmed / rejected / ai


@router.put("/boq/matches/{match_id}", response_model=BoqMatchResult)
def update_match(match_id: int, req: UpdateMatchRequest):
    """确认或拒绝一条匹配。"""
    if req.status not in ("confirmed", "rejected", "ai"):
        raise HTTPException(status_code=400, detail="status 只能是 confirmed / rejected / ai")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE boq_quota_matches
                SET status = %s,
                    confirmed_at = CASE WHEN %s = 'confirmed' THEN NOW() ELSE NULL END
                WHERE id = %s
                RETURNING id, boq_item_id, quota_item_id, qty_factor,
                          ai_reasoning, reasoning_chain, confidence, status, confirmed_at
            """, (req.status, req.status, match_id))
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="匹配记录不存在")
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("""
                SELECT item_code, item_name, variant_desc, unit, work_content,
                       total_unit_price, unit_price,
                       labor_cost, material_cost, machine_cost,
                       management_fee, profit, safety_fee, statutory_fee, tax
                FROM quota_items WHERE id = %s
            """, (row[2],))
            q = cur.fetchone()
            cur.execute("""
                SELECT id, resource_type, resource_name, unit, quantity, ref_price
                FROM quota_resources WHERE item_id = %s ORDER BY resource_type, id
            """, (row[2],))
            resources = [
                QuotaResource(id=rr[0], resource_type=rr[1], resource_name=rr[2],
                              unit=rr[3],
                              quantity=float(rr[4]) if rr[4] is not None else None,
                              ref_price=float(rr[5]) if rr[5] is not None else None)
                for rr in cur.fetchall()
            ]

        def _f(v): return float(v) if v is not None else None

        return BoqMatchResult(
            id=row[0], boq_item_id=row[1], quota_item_id=row[2],
            qty_factor=float(row[3]),
            ai_reasoning=row[4], reasoning_chain=row[5],
            confidence=row[6], status=row[7], confirmed_at=row[8],
            quota_item_code=q[0], quota_item_name=q[1],
            quota_variant_desc=q[2], quota_unit=q[3], quota_work_content=q[4],
            quota_total_unit_price=_f(q[5]), quota_unit_price=_f(q[6]),
            quota_labor_cost=_f(q[7]), quota_material_cost=_f(q[8]),
            quota_machine_cost=_f(q[9]), quota_management_fee=_f(q[10]),
            quota_profit=_f(q[11]), quota_safety_fee=_f(q[12]),
            quota_statutory_fee=_f(q[13]), quota_tax=_f(q[14]),
            quota_resources=resources,
        )
    finally:
        conn.close()


@router.delete("/boq/matches/{match_id}")
def delete_match(match_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM boq_quota_matches WHERE id = %s RETURNING id", (match_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="匹配记录不存在")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ── 汇总计算 ──────────────────────────────────────────────────────────────────

@router.get("/boq/summary")
def get_boq_summary(run_id: int = Query(...)):
    """汇总综合单价 + 工料机总量（按 run_id 筛选）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    i.id, i.item_seq, i.item_code, i.item_name, i.unit, i.quantity,
                    COUNT(m.id) AS match_count,
                    BOOL_AND(m.status = 'confirmed') AS all_confirmed,
                    SUM(COALESCE(q.total_unit_price, 0) * m.qty_factor) AS sum_unit_price
                FROM boq_quota_matches m
                JOIN boq_items i ON i.id = m.boq_item_id
                LEFT JOIN quota_items q ON q.id = m.quota_item_id
                WHERE m.run_id = %s
                GROUP BY i.id
                ORDER BY i.item_seq
            """, (run_id,))
            item_rows = cur.fetchall()

        summary_items = []
        for r in item_rows:
            qty = float(r[5]) if r[5] else None
            sum_up = float(r[8]) if r[8] else None
            match_count = int(r[6]) if r[6] else 0
            all_confirmed = bool(r[7]) if match_count > 0 else False
            match_status = "none" if match_count == 0 else ("all_confirmed" if all_confirmed else "partial")
            total = round(sum_up * qty, 2) if (sum_up and qty) else None
            summary_items.append(BoqSummaryItem(
                boq_item_id=r[0], item_seq=r[1], item_code=r[2],
                item_name=r[3], unit=r[4], quantity=qty,
                unit_price=round(sum_up, 4) if sum_up else None,
                total_price=total,
                match_count=match_count,
                match_status=match_status,
            ))

        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    r.resource_type, r.resource_name, r.unit,
                    SUM(r.quantity * m.qty_factor * i.quantity) AS total_qty
                FROM boq_quota_matches m
                JOIN boq_items i ON i.id = m.boq_item_id
                JOIN quota_resources r ON r.item_id = m.quota_item_id
                WHERE m.run_id = %s
                GROUP BY r.resource_type, r.resource_name, r.unit
                ORDER BY r.resource_type, r.resource_name
            """, (run_id,))
            res_rows = cur.fetchall()

        resource_summary = [
            BoqResourceSummary(
                resource_type=r[0], resource_name=r[1], unit=r[2],
                total_quantity=round(float(r[3]), 4),
            )
            for r in res_rows
        ]

        return {"items": summary_items, "resources": resource_summary}
    finally:
        conn.close()


# ── 定额比较端点 ──────────────────────────────────────────────────────────────

def _compare_run_info(conn, id: int, src_type: str) -> tuple:
    """返回 (run_id, run_name, standard_code, project_id, project_name)。"""
    with conn.cursor() as cur:
        if src_type == "manual":
            cur.execute(
                "SELECT id, project_name FROM manual_boq_projects WHERE id = %s", (id,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"人工套定额工程 {id} 不存在")
            return (id, None, "人工套定额", row[0], row[1])
        else:
            cur.execute("""
                SELECT r.id, r.run_name, r.standard_code, p.id, p.project_name
                FROM boq_match_runs r JOIN boq_projects p ON p.id = r.project_id
                WHERE r.id = %s
            """, (id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"批次 {id} 不存在")
            return row


def _compare_fetch_matches(conn, id: int, src_type: str) -> list:
    """返回行列表，每行: (item_code, item_name, unit, quantity,
                          quota_code, quota_name, quota_item_id,
                          qty_factor, confidence, work_procedure)"""
    with conn.cursor() as cur:
        if src_type == "manual":
            cur.execute("""
                SELECT i.item_code, i.item_name, i.unit, i.quantity,
                       COALESCE(mq.quota_code, ''), COALESCE(mq.quota_name, ''),
                       mq.quota_item_id,
                       mq.qty_factor, NULL, NULL
                FROM manual_boq_items i
                JOIN manual_boq_quotas mq ON mq.boq_item_id = i.id
                WHERE i.project_id = %s AND i.item_code IS NOT NULL
                      AND mq.quota_code IS NOT NULL AND mq.quota_code != ''
                ORDER BY i.item_seq, i.item_code, mq.id
            """, (id,))
        else:
            cur.execute("""
                SELECT i.item_code, i.item_name, i.unit, i.quantity,
                       q.item_code, q.item_name, m.quota_item_id,
                       m.qty_factor, m.confidence, m.work_procedure
                FROM boq_quota_matches m
                JOIN boq_items i ON i.id = m.boq_item_id
                JOIN quota_items q ON q.id = m.quota_item_id
                WHERE m.run_id = %s AND m.status != 'rejected'
                ORDER BY i.item_seq, i.item_code, m.id
            """, (id,))
        return cur.fetchall()


@router.get("/boq/compare", response_model=CompareResult)
def compare_runs(
    run_a: int = Query(...),
    run_b: int = Query(...),
    run_a_type: str = Query("run"),   # "run" | "manual"
    run_b_type: str = Query("run"),
):
    """对比两个套定额来源（AI批次 或 人工套定额工程），返回逐清单项的定额对比。"""
    conn = get_connection()
    try:
        ra = _compare_run_info(conn, run_a, run_a_type)
        rb = _compare_run_info(conn, run_b, run_b_type)

        def group_by_code(rows):
            result: dict = {}
            for row in rows:
                code = row[0]
                if code not in result:
                    result[code] = {
                        "item_name": row[1], "unit": row[2],
                        "quantity": float(row[3]) if row[3] else None,
                        "quotas": [],
                    }
                result[code]["quotas"].append({
                    "quota_item_id": row[6],
                    "quota_item_code": row[4],
                    "quota_item_name": row[5],
                    "qty_factor": float(row[7]) if row[7] is not None else 1.0,
                    "confidence": row[8],
                    "work_procedure": row[9],
                })
            return result

        map_a = group_by_code(_compare_fetch_matches(conn, run_a, run_a_type))
        map_b = group_by_code(_compare_fetch_matches(conn, run_b, run_b_type))

        all_codes = sorted(set(map_a.keys()) | set(map_b.keys()))
        items = []
        consistent_count = only_a = only_b = both_empty = 0

        for code in all_codes:
            a = map_a.get(code, {"item_name": "", "unit": None, "quantity": None, "quotas": []})
            b = map_b.get(code, {"item_name": "", "unit": None, "quantity": None, "quotas": []})
            codes_a = sorted(q["quota_item_code"] for q in a["quotas"])
            codes_b = sorted(q["quota_item_code"] for q in b["quotas"])
            consistent = bool(codes_a) and bool(codes_b) and codes_a == codes_b

            if consistent:
                consistent_count += 1
            elif not codes_a and not codes_b:
                both_empty += 1
            elif codes_a and not codes_b:
                only_a += 1
            elif not codes_a and codes_b:
                only_b += 1

            items.append(CompareBoqItem(
                item_code=code,
                item_name=a["item_name"] or b["item_name"],
                unit=a["unit"] or b["unit"],
                quantity=a["quantity"] or b["quantity"],
                quotas_a=[CompareQuota(**q) for q in a["quotas"]],
                quotas_b=[CompareQuota(**q) for q in b["quotas"]],
                consistent=consistent,
            ))

        different = len(items) - consistent_count - only_a - only_b - both_empty
        return CompareResult(
            run_a=CompareRunInfo(run_id=ra[0], run_name=ra[1], standard_code=ra[2], project_id=ra[3], project_name=ra[4]),
            run_b=CompareRunInfo(run_id=rb[0], run_name=rb[1], standard_code=rb[2], project_id=rb[3], project_name=rb[4]),
            items=items,
            summary=CompareSummary(
                total=len(items),
                consistent=consistent_count,
                different=different,
                only_a=only_a,
                only_b=only_b,
                both_empty=both_empty,
            ),
        )
    finally:
        conn.close()


# ── 流式套定额端点 ─────────────────────────────────────────────────────────────

@router.post("/boq/match-project-stream")
def match_project_stream(req: MatchProjectRequest):
    """
    流式套定额：SSE 实时推送每条清单项的 AI 推理过程，同时写库。
    前端保持连接可看实时推理；切换页面后连接中断，但数据已写库，不影响结果。
    """
    def generate():
        conn = get_connection()
        run_id = None
        try:
            _ensure_match_schema(conn)

            # 解析 standard_ids
            std_ids = req.standard_ids if req.standard_ids else ([req.standard_id] if req.standard_id else [])
            if not std_ids:
                yield f"data: {json.dumps({'type':'run_error','error':'未选择定额标准'})}\n\n"
                return

            # 获取清单项
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, item_code, item_name, item_description, unit, quantity
                    FROM boq_items WHERE project_id = %s ORDER BY item_seq
                """, (req.project_id,))
                items = cur.fetchall()

                # 获取 standard_code（多标准时拼接）
                placeholders = ','.join(['%s'] * len(std_ids))
                cur.execute(f"SELECT standard_code FROM quota_standards WHERE id IN ({placeholders}) ORDER BY id", std_ids)
                codes = [r[0] for r in cur.fetchall() if r[0]]
            standard_code = ' + '.join(codes) if codes else None
            total = len(items)

            # 创建 run 记录
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO boq_match_runs
                        (project_id, standard_id, standard_ids, standard_code,
                         run_name, status, total_items, matched_items)
                    VALUES (%s, %s, %s, %s, %s, 'running', %s, 0) RETURNING id
                """, (req.project_id,
                      std_ids[0],
                      json.dumps(std_ids),
                      standard_code,
                      req.run_name or None,
                      total))
                run_id = cur.fetchone()[0]
            conn.commit()

            yield f"data: {json.dumps({'type':'run_start','run_id':run_id,'total':total}, ensure_ascii=False)}\n\n"

            # 构建 system_prompt（含全量定额，触发 KV Cache）
            sp = build_system_prompt(conn, std_ids)

            matched_count = 0
            for idx, (item_id, item_code, item_name, item_desc, unit, quantity) in enumerate(items):
                boq_item = {
                    "id": item_id, "item_code": item_code, "item_name": item_name,
                    "item_description": item_desc, "unit": unit,
                    "quantity": float(quantity) if quantity else None,
                    "project_id": req.project_id,
                }

                yield f"data: {json.dumps({'type':'item_start','index':idx+1,'total':total,'boq_item_id':item_id,'item_name':item_name}, ensure_ascii=False)}\n\n"

                # 流式推理，同时拼接 tool_call 结果
                raw_results = []
                try:
                    for event_type, data in stream_match_boq_item(boq_item, sp):
                        if event_type == "reasoning_token":
                            yield f"data: {json.dumps({'type':'reasoning_token','token':data}, ensure_ascii=False)}\n\n"
                        elif event_type == "result":
                            raw_results = data
                except Exception as e:
                    yield f"data: {json.dumps({'type':'item_error','boq_item_id':item_id,'error':str(e)}, ensure_ascii=False)}\n\n"

                # 写库（补全定额编码/名称）
                saved_matches = []
                with conn.cursor() as cur:
                    for m in raw_results:
                        cur.execute("SELECT item_code, item_name, variant_desc, unit, standard_id FROM quota_items WHERE id = %s", (m.quota_item_id,))
                        q = cur.fetchone()
                        if not q:
                            continue
                        match_std_id = q[4]  # 定额子目所属的标准
                        cur.execute("""
                            INSERT INTO boq_quota_matches
                                (project_id, boq_item_id, quota_item_id, standard_id,
                                 qty_factor, ai_reasoning, reasoning_chain, confidence, status, run_id,
                                 work_procedure, factor_explanation)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ai', %s, %s, %s)
                            ON CONFLICT (run_id, boq_item_id, quota_item_id) DO NOTHING
                            RETURNING id
                        """, (req.project_id, item_id, m.quota_item_id, match_std_id,
                              m.qty_factor, m.reasoning, m.reasoning_chain, m.confidence, run_id,
                              m.work_procedure, m.factor_explanation))
                        row = cur.fetchone()
                        if row:
                            matched_count += 1
                            saved_matches.append({
                                "quota_item_id": m.quota_item_id,
                                "quota_item_code": q[0],
                                "quota_item_name": q[1],
                                "quota_variant_desc": q[2],
                                "quota_unit": q[3],
                                "qty_factor": m.qty_factor,
                                "confidence": m.confidence,
                                "reasoning": m.reasoning,
                            })

                    # 更新进度
                    cur.execute(
                        "UPDATE boq_match_runs SET matched_items = %s WHERE id = %s",
                        (matched_count, run_id)
                    )
                conn.commit()

                yield f"data: {json.dumps({'type':'item_done','boq_item_id':item_id,'matches':saved_matches}, ensure_ascii=False)}\n\n"

            # 完成
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE boq_match_runs SET status='done', matched_items=%s, finished_at=NOW() WHERE id=%s
                """, (matched_count, run_id))
            conn.commit()
            yield f"data: {json.dumps({'type':'run_done','run_id':run_id,'total':total,'matched':matched_count}, ensure_ascii=False)}\n\n"

        except Exception as e:
            try:
                if run_id:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE boq_match_runs SET status='error', finished_at=NOW() WHERE id=%s", (run_id,))
                    conn.commit()
            except Exception:
                pass
            yield f"data: {json.dumps({'type':'run_error','error':str(e)}, ensure_ascii=False)}\n\n"
        finally:
            conn.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 调试批次 CRUD ────────────────────────────────────────────────────────────

class DebugBatchCreate(BaseModel):
    name: str
    boq_project_id: int
    manual_project_id: Optional[int] = None
    standard_ids: list[int]

class DebugBatchRename(BaseModel):
    name: str


@router.get("/debug-batches")
def list_debug_batches():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT db.id, db.name, db.boq_project_id, bp.project_name,
                       db.manual_project_id, db.standard_ids, db.created_at,
                       COUNT(dir.id) AS result_count
                FROM debug_batches db
                JOIN boq_projects bp ON bp.id = db.boq_project_id
                LEFT JOIN debug_item_results dir ON dir.batch_id = db.id
                GROUP BY db.id, db.name, db.boq_project_id, bp.project_name,
                         db.manual_project_id, db.standard_ids, db.created_at
                ORDER BY db.created_at DESC
            """)
            rows = cur.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r[0], "name": r[1],
                "boq_project_id": r[2], "project_name": r[3],
                "manual_project_id": r[4],
                "standard_ids": json.loads(r[5]),
                "created_at": r[6].isoformat() if r[6] else None,
                "result_count": r[7],
            })
        return result
    finally:
        conn.close()


@router.post("/debug-batches", status_code=201)
def create_debug_batch(body: DebugBatchCreate):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO debug_batches (name, boq_project_id, manual_project_id, standard_ids)
                VALUES (%s, %s, %s, %s) RETURNING id, created_at
            """, (body.name, body.boq_project_id, body.manual_project_id,
                  json.dumps(body.standard_ids)))
            row = cur.fetchone()
            conn.commit()
        return {"id": row[0], "created_at": row[1].isoformat()}
    finally:
        conn.close()


@router.get("/debug-batches/{batch_id}")
def get_debug_batch(batch_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT db.id, db.name, db.boq_project_id, bp.project_name,
                       db.manual_project_id, db.standard_ids, db.created_at
                FROM debug_batches db
                JOIN boq_projects bp ON bp.id = db.boq_project_id
                WHERE db.id = %s
            """, (batch_id,))
            r = cur.fetchone()
        if not r:
            raise HTTPException(404, "批次不存在")
        # 解析 standard_ids → 查询定额标准名称
        std_ids = json.loads(r[5])
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, standard_code, name FROM quota_standards WHERE id = ANY(%s)
            """, (std_ids,))
            stds = [{"id": s[0], "standard_code": s[1], "name": s[2]} for s in cur.fetchall()]
        return {
            "id": r[0], "name": r[1],
            "boq_project_id": r[2], "project_name": r[3],
            "manual_project_id": r[4],
            "standard_ids": std_ids, "standards": stds,
            "created_at": r[6].isoformat() if r[6] else None,
        }
    finally:
        conn.close()


@router.patch("/debug-batches/{batch_id}")
def rename_debug_batch(batch_id: int, body: DebugBatchRename):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE debug_batches SET name=%s, updated_at=NOW()
                WHERE id=%s RETURNING id
            """, (body.name, batch_id))
            if not cur.fetchone():
                raise HTTPException(404, "批次不存在")
            conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/debug-batches/{batch_id}", status_code=204)
def delete_debug_batch(batch_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM debug_batches WHERE id=%s", (batch_id,))
            conn.commit()
    finally:
        conn.close()


@router.get("/debug-batches/{batch_id}/results")
def get_batch_results(batch_id: int):
    """返回该批次所有已保存的推理结果，key 为 boq_item_id（字符串）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT boq_item_id, reasoning_chain, result_json, ran_at
                FROM debug_item_results WHERE batch_id = %s
            """, (batch_id,))
            rows = cur.fetchall()
        out = {}
        for r in rows:
            out[str(r[0])] = {
                "reasoning_chain": r[1],
                "result": r[2],   # JSONB 已经是 dict
                "ran_at": r[3].isoformat() if r[3] else None,
            }
        return out
    finally:
        conn.close()


# ── 单条调试端点（流式推理 + 可选写库）────────────────────────────────────────

class DebugMatchRequest(BaseModel):
    boq_item_id: int
    standard_ids: list[int]
    manual_project_id: Optional[int] = None   # 提供则同步返回人工标准答案
    batch_id: Optional[int] = None            # 提供则推理完成后持久化结果


@router.post("/boq/match-item-debug")
def match_item_debug(req: DebugMatchRequest):
    """
    单条清单项调试套定额：流式推理，可附带人工标准答案对比。
    若提供 batch_id，推理完成后持久化结果到 debug_item_results。
    SSE 事件: item_info / reasoning_token / result / done / error
    """
    def generate():
        conn = get_connection()
        try:
            # ── 1. 获取清单项完整信息 ─────────────────────────────────────────
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, item_code, item_name, item_description, unit, quantity
                    FROM boq_items WHERE id = %s
                """, (req.boq_item_id,))
                row = cur.fetchone()
            if not row:
                yield f"data: {json.dumps({'type':'error','error':'清单项不存在'})}\n\n"
                return

            boq_item = {
                "id": row[0], "item_code": row[1], "item_name": row[2],
                "item_description": row[3], "unit": row[4],
                "quantity": float(row[5]) if row[5] else None,
            }

            # ── 2. 获取人工标准答案（按 item_code 匹配） ─────────────────────
            manual_quotas: list[dict] = []
            if req.manual_project_id and row[1]:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT mq.quota_code, mq.quota_name, mq.quota_unit,
                               mq.quantity, mq.qty_factor, mq.quota_item_id
                        FROM manual_boq_quotas mq
                        JOIN manual_boq_items mi ON mi.id = mq.boq_item_id
                        WHERE mi.project_id = %s AND mi.item_code = %s
                              AND mq.quota_code IS NOT NULL AND mq.quota_code != ''
                        ORDER BY mq.id
                    """, (req.manual_project_id, row[1]))
                    for r in cur.fetchall():
                        manual_quotas.append({
                            "quota_code": r[0],
                            "quota_name": r[1],
                            "quota_unit": r[2],
                            "quantity": float(r[3]) if r[3] else None,
                            "qty_factor": float(r[4]) if r[4] else None,
                            "quota_item_id": r[5],
                            "is_formula": bool(r[5] is None),  # 无法链接到库 = 公式或特殊码
                        })

            # ── 3. 구축 system prompt ────────────────────────────────────────
            if not req.standard_ids:
                yield f"data: {json.dumps({'type':'error','error':'未选择定额标准'})}\n\n"
                return
            sp = build_system_prompt(conn, req.standard_ids)
            user_msg = _build_user_msg(boq_item)

            yield f"data: {json.dumps({'type':'item_info','item':boq_item,'manual_quotas':manual_quotas,'system_prompt':sp[:2000],'system_prompt_len':len(sp),'user_message':user_msg}, ensure_ascii=False)}\n\n"

            # ── 4. 流式推理 ──────────────────────────────────────────────────
            raw_results = []
            full_reasoning = []
            for event_type, data in stream_match_boq_item(boq_item, sp):
                if event_type == "reasoning_token":
                    full_reasoning.append(data)
                    yield f"data: {json.dumps({'type':'reasoning_token','token':data}, ensure_ascii=False)}\n\n"
                elif event_type == "result":
                    raw_results = data

            # ── 5. 补全定额库信息，附加与人工标准的对比标记 ──────────────────
            manual_codes = {q["quota_code"] for q in manual_quotas}
            matches = []
            ai_codes: set[str] = set()

            with conn.cursor() as cur:
                for m in raw_results:
                    cur.execute("""
                        SELECT item_code, item_name, variant_desc, unit,
                               total_unit_price, labor_cost, material_cost, machine_cost
                        FROM quota_items WHERE id = %s
                    """, (m.quota_item_id,))
                    q = cur.fetchone()
                    if not q:
                        continue
                    ai_codes.add(q[0])
                    in_manual = q[0] in manual_codes
                    matches.append({
                        "quota_item_id": m.quota_item_id,
                        "quota_item_code": q[0],
                        "quota_item_name": q[1],
                        "quota_variant_desc": q[2],
                        "quota_unit": q[3],
                        "total_unit_price": float(q[4]) if q[4] else None,
                        "labor_cost": float(q[5]) if q[5] else None,
                        "material_cost": float(q[6]) if q[6] else None,
                        "machine_cost": float(q[7]) if q[7] else None,
                        "qty_factor": m.qty_factor,
                        "confidence": m.confidence,
                        "work_procedure": m.work_procedure,
                        "factor_explanation": m.factor_explanation,
                        "reasoning": m.reasoning,
                        "in_manual": in_manual,       # AI 匹配 + 人工也有 → ✅
                    })

            # 人工有但 AI 漏套的定额
            missed = [
                {**q, "missed_by_ai": True}
                for q in manual_quotas
                if q["quota_code"] not in ai_codes
            ]

            yield f"data: {json.dumps({'type':'result','matches':matches,'missed':missed}, ensure_ascii=False)}\n\n"

            # ── 6. 持久化（如果提供了 batch_id）────────────────────────────
            if req.batch_id:
                result_payload = {
                    "matches": matches,
                    "missed": missed,
                    "manual_quotas": manual_quotas,
                }
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO debug_item_results
                            (batch_id, boq_item_id, reasoning_chain, result_json, ran_at)
                        VALUES (%s, %s, %s, %s::jsonb, NOW())
                        ON CONFLICT (batch_id, boq_item_id) DO UPDATE
                            SET reasoning_chain = EXCLUDED.reasoning_chain,
                                result_json     = EXCLUDED.result_json,
                                ran_at          = EXCLUDED.ran_at
                    """, (req.batch_id, req.boq_item_id,
                          ''.join(full_reasoning),
                          json.dumps(result_payload, ensure_ascii=False)))
                    conn.commit()

            yield f"data: {json.dumps({'type':'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type':'error','error':str(e)}, ensure_ascii=False)}\n\n"
        finally:
            conn.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
