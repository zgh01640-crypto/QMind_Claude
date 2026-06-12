"""
单条组价路由 — 重构版（与 bs2024_match.py 完全独立）
数据源：tqdk_* (国标清单) + tdek_* (定额)
AI 工具：按步骤逐步填充
"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json

router = APIRouter()


def _ensure_schema(conn):
    """初始化结果表"""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pricing_task_results (
                id              SERIAL PRIMARY KEY,
                boq_item_id     INTEGER NOT NULL,
                boq_project_id  INTEGER NOT NULL,
                dezmid          BIGINT NOT NULL,
                dekid           BIGINT NOT NULL,
                subitem_code    VARCHAR(64),
                subitem_name    TEXT,
                qty_factor      NUMERIC(20, 6) DEFAULT 1,
                work_procedure  TEXT,
                confidence      VARCHAR(16),
                missing_info    TEXT,
                ai_reasoning    TEXT,
                status          VARCHAR(16) DEFAULT 'pending',
                created_at      TIMESTAMP DEFAULT NOW(),
                updated_at      TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_ptr_boq_item ON pricing_task_results(boq_item_id)
        """)
        conn.commit()


# ─── 工具函数（按步骤填充）───────────────────────────────────────────
# 每个 AI 工具对应两部分：
#   1. Python 执行函数 exec_xxx(conn, ...) → dict
#   2. OpenAI 工具定义 _TOOL_XXX = {"type": "function", ...}

def exec_get_quota_candidates(conn, item_code: str) -> dict:
    """
    工具：根据清单编码查询候选定额子目集合
    item_code 去末3位 → tqdk_tqdzm.zmbh → tqdk_tqdzy → tdek_tdezm
    """
    # TODO: 实现查询逻辑
    pass

# _TOOL_GET_QUOTA_CANDIDATES = { ... }  # TODO


# ─── 提示词构建（按步骤填充）─────────────────────────────────────────
def build_system_prompt(conn, chapter_ids: list[int]) -> str:
    """新版系统提示词，结构待定"""
    # TODO
    return "（提示词占位）"


# ─── AI 流式推理（按步骤填充）────────────────────────────────────────
def stream_pricing_item(boq_item: dict, system_prompt: str, conn):
    """
    流式执行单条组价主流程
    yield ("reasoning_token", str)
    yield ("tool_call", dict)   # 工具调用结果
    yield ("result", list)      # 最终匹配结果
    """
    # TODO: 多轮工具调用逻辑
    yield ("reasoning_token", "（占位推理）")
    yield ("result", [])


# ─── SSE 端点 ────────────────────────────────────────────────────────

class SinglePricingRequest(BaseModel):
    boq_item_id: int
    chapter_ids: list[int]
    manual_project_id: Optional[int] = None


@router.post("/pricing-task/match-item-stream")
def pricing_task_match_item_stream(req: SinglePricingRequest):
    from db.connection import get_connection

    def generate():
        conn = get_connection()
        try:
            _ensure_schema(conn)

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, item_code, item_name, item_description, unit, quantity,"
                    " project_id FROM boq_items WHERE id = %s",
                    (req.boq_item_id,)
                )
                row = cur.fetchone()

            if not row:
                yield f"data: {json.dumps({'type':'error','error':'清单项不存在'})}\n\n"
                return

            boq_item = {
                "id": row[0], "item_code": row[1], "item_name": row[2],
                "item_description": row[3], "unit": row[4],
                "quantity": float(row[5]) if row[5] else None,
                "project_id": row[6],
            }

            sp = build_system_prompt(conn, req.chapter_ids)
            yield f"data: {json.dumps({'type':'item_info','item':boq_item}, ensure_ascii=False)}\n\n"

            final_results = []
            for event_type, data in stream_pricing_item(boq_item, sp, conn):
                if event_type == "reasoning_token":
                    yield f"data: {json.dumps({'type':'reasoning_token','token':data}, ensure_ascii=False)}\n\n"
                elif event_type == "tool_call":
                    yield f"data: {json.dumps({'type':'tool_call',**data}, ensure_ascii=False)}\n\n"
                elif event_type == "result":
                    final_results = data
                    yield f"data: {json.dumps({'type':'result','matches':data}, ensure_ascii=False)}\n\n"

            # 写库
            _save_results(conn, boq_item, final_results)

            yield f"data: {json.dumps({'type':'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type':'error','error':str(e)})}\n\n"
        finally:
            conn.close()

    return StreamingResponse(generate(), media_type="text/event-stream")


def _save_results(conn, boq_item: dict, matches: list):
    """将 AI 匹配结果写入 pricing_task_results"""
    # TODO: INSERT INTO pricing_task_results ...
    pass
