from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import CurrentUser, current_user
from db.connection import get_connection

router = APIRouter()


def _target_user(user: CurrentUser, requested: int | None) -> int:
    if requested is not None and requested != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="只能查看自己的模型用量")
    return requested if requested is not None else user.id


def _filters(user_id: int, start: datetime | None, end: datetime | None,
             model_profile_id: int | None, business_type: str | None,
             status: str | None, task_id: int | None, batch_id: int | None) -> tuple[str, list[Any]]:
    clauses, values = ["user_id=%s"], [user_id]
    for sql, value in (
        ("created_at >= %s", start), ("created_at < %s", end),
        ("model_profile_id=%s", model_profile_id), ("business_type=%s", business_type),
        ("status=%s", status), ("task_id=%s", task_id), ("batch_id=%s", batch_id),
    ):
        if value is not None:
            clauses.append(sql)
            values.append(value)
    return " AND ".join(clauses), values


@router.get("/ai-usage/summary")
def usage_summary(
    start: datetime | None = None, end: datetime | None = None,
    model_profile_id: int | None = None, business_type: str | None = None,
    status: str | None = None, task_id: int | None = None, batch_id: int | None = None,
    user_id: int | None = None, user: CurrentUser = Depends(current_user),
):
    target = _target_user(user, user_id)
    where, values = _filters(target, start, end, model_profile_id, business_type, status, task_id, batch_id)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"""SELECT COUNT(*),COUNT(*) FILTER (WHERE usage_status='unknown'),
                COALESCE(SUM(input_tokens),0),COALESCE(SUM(cached_input_tokens),0),
                COALESCE(SUM(output_tokens),0),COALESCE(SUM(total_tokens),0),
                COALESCE(SUM(cost_yuan),0)
                FROM ai_usage_records WHERE {where}""", values)
            row = cur.fetchone()
            cur.execute(f"""SELECT model_profile_id,provider,model,COUNT(*),
                COALESCE(SUM(total_tokens),0),COALESCE(SUM(cost_yuan),0),
                COUNT(*) FILTER (WHERE usage_status='unknown')
                FROM ai_usage_records WHERE {where}
                GROUP BY model_profile_id,provider,model ORDER BY COALESCE(SUM(cost_yuan),0) DESC""", values)
            models = [{"model_profile_id": item[0], "provider": item[1], "model": item[2],
                       "call_count": item[3], "total_tokens": item[4], "known_cost_yuan": item[5],
                       "unknown_usage_count": item[6]} for item in cur.fetchall()]
    finally:
        conn.close()
    call_count, unknown = int(row[0]), int(row[1])
    return {"call_count": call_count, "unknown_usage_count": unknown,
            "coverage_rate": (call_count - unknown) / call_count if call_count else 1,
            "input_tokens": row[2], "cached_input_tokens": row[3], "output_tokens": row[4],
            "total_tokens": row[5], "known_cost_yuan": row[6], "models": models}


@router.get("/ai-usage/records")
def usage_records(
    start: datetime | None = None, end: datetime | None = None,
    model_profile_id: int | None = None, business_type: str | None = None,
    status: str | None = None, task_id: int | None = None, batch_id: int | None = None,
    user_id: int | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(current_user),
):
    target = _target_user(user, user_id)
    where, values = _filters(target, start, end, model_profile_id, business_type, status, task_id, batch_id)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM ai_usage_records WHERE {where}", values)
            total = int(cur.fetchone()[0])
            cur.execute(f"""SELECT id,model_profile_id,provider,model,business_type,operation,
                task_id,batch_id,run_id,item_run_id,execution_id,status,usage_status,input_tokens,
                cached_input_tokens,output_tokens,reasoning_tokens,total_tokens,cost_yuan,duration_ms,
                error_type,created_at,finished_at FROM ai_usage_records WHERE {where}
                ORDER BY id DESC LIMIT %s OFFSET %s""", [*values, page_size, (page - 1) * page_size])
            keys = ["id","model_profile_id","provider","model","business_type","operation","task_id",
                    "batch_id","run_id","item_run_id","execution_id","status","usage_status","input_tokens",
                    "cached_input_tokens","output_tokens","reasoning_tokens","total_tokens","cost_yuan",
                    "duration_ms","error_type","created_at","finished_at"]
            items = [dict(zip(keys, row)) for row in cur.fetchall()]
    finally:
        conn.close()
    return {"items": items, "page": page, "page_size": page_size, "total": total}
