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

def exec_check_item_code(conn, item_code: str) -> dict:
    """
    工具：编码检索 — 查询清单编码对应的标准清单名称
    item_code 去末3位 → tqdk_tqdzm.zmbh → 返回标准名称
    """
    base_code = item_code.strip().replace(' ', '')
    if len(base_code) >= 3:
        base_code = base_code[:-3]

    with conn.cursor() as cur:
        cur.execute(
            "SELECT zmmc FROM tqdk_tqdzm WHERE zmbh = %s LIMIT 5",
            (base_code,)
        )
        rows = cur.fetchall()

    standard_names = list({r[0] for r in rows if r[0]})

    return {
        "item_code": item_code,
        "base_code": base_code,
        "standard_names": standard_names,
        "found": len(standard_names) > 0,
    }


_TOOL_CHECK_ITEM_CODE = {
    "type": "function",
    "function": {
        "name": "check_item_code",
        "description": (
            "编码检索工具：根据清单编码查询国标清单中的标准名称。"
            "将编码去掉末尾3位流水号得到基准编码，"
            "在清单编码表中查询标准清单名称，用于一致性审查。"
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "item_code": {
                    "type": "string",
                    "description": "工程清单编码（如 010101001003，后三位是流水号）",
                }
            },
            "required": ["item_code"],
            "additionalProperties": False,
        },
    },
}




_TOOL_GET_QUOTA_CANDIDATES = {
    "type": "function",
    "function": {
        "name": "get_quota_candidates",
        "description": (
            "根据工程清单编码查询国标定额库中的候选定额子目集合。"
            "将编码去掉末尾3位流水号得到9位基准编码，"
            "然后查询该编码在国标清单库中对应的定额候选。"
            "返回所有候选定额的编号、名称、计量单位、工作内容等信息。"
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "item_code": {
                    "type": "string",
                    "description": "工程清单编码（12位数字，如 010102002004）",
                }
            },
            "required": ["item_code"],
            "additionalProperties": False,
        },
    },
}


# ─── 提示词构建 ─────────────────────────────────────────
def build_system_prompt() -> str:
    """第一轮系统提示词：清单编码一致性审查"""
    return """你是专业的建筑工程造价工程师，精通以下标准与规范：
- 各专业的工程量清单计价标准
- 各专业的定额消耗量标准

【当前任务】
进行清单编码一致性审查。审查工程清单项的清单编码与清单名称是否一致。

【重要要求】
- 全程使用中文进行推理和分析，包括思维链过程
- 推理过程（thinking/reasoning）必须使用中文输出，不得使用英文

【审查流程】
1. 你将接收清单项的编码
2. 调用"编码检索工具"查询该编码对应的标准清单名称
3. 将标准清单名称与工程清单名称进行比对
4. 给出一致性结论（一致/不一致/存疑）和理由说明
"""


# ─── AI 流式推理（按步骤填充）────────────────────────────────────────
def stream_pricing_item(boq_item: dict, system_prompt: str, conn):
    """
    第一轮对话：清单编码一致性审查

    流程：
    1. 第一次调用 AI → 获取工具调用参数 → 执行编码检索工具
    2. 第二次调用 AI（带工具结果）→ 对比名称 → 给出结论

    yield ("reasoning_token", str)        # AI 推理过程
    yield ("code_check", dict)            # 工具执行结果
    yield ("judgment", dict)              # AI 最终结论
    """
    from openai import OpenAI
    import os

    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        timeout=120.0,
    )

    # ── Round 1.1: 第一次调用 AI 获取编码检索工具参数 ─────────────────────────
    user_msg = f"""请对以下清单项进行编码一致性审查：

- 清单编码：{boq_item['item_code']}
- 清单名称：{boq_item['item_name']}
- 计量单位：{boq_item['unit']}
- 清单特征：{boq_item['item_description'] or '无'}

【第一步】请调用"编码检索工具"查询该编码对应的标准清单名称。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    stream1 = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=messages,
        tools=[_TOOL_CHECK_ITEM_CODE],
        tool_choice={"type": "function", "function": {"name": "check_item_code"}},
        max_tokens=2000,
        stream=True,
    )

    # 收集 Round 1.1 的 reasoning tokens 和 tool_call
    tool_call_id = ""
    tool_call_args = ""
    for chunk in stream1:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        # 推理 token
        if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
            yield ("reasoning_token", delta.reasoning_content)

        # 工具调用
        if delta.tool_calls:
            for tc in delta.tool_calls:
                if tc.id:
                    tool_call_id = tc.id
                if tc.function and tc.function.arguments:
                    tool_call_args += tc.function.arguments

    # 执行编码检索工具
    try:
        call_input = json.loads(tool_call_args)
        code_check_result = exec_check_item_code(conn, call_input.get("item_code", ""))
    except Exception as e:
        code_check_result = {
            "item_code": boq_item['item_code'],
            "base_code": "",
            "standard_names": [],
            "found": False,
            "error": str(e),
        }

    yield ("code_check", code_check_result)

    # ── Round 1.2: 第二次调用 AI 进行名称比对和结论 ───────────────────────────
    standard_names_str = ", ".join(code_check_result.get("standard_names", [])) or "（未找到标准名称）"

    messages.append({
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": tool_call_id,
            "type": "function",
            "function": {"name": "check_item_code", "arguments": tool_call_args},
        }],
    })
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(code_check_result, ensure_ascii=False),
    })

    # 第二轮系统提示词（补充）
    user_msg_round2 = f"""现在你已经获取到标准清单名称。请完成以下任务：

【第二步】比对以下两个名称是否一致，并给出结论：
- 工程清单名称：{boq_item['item_name']}
- 标准清单名称：{standard_names_str}

请输出：
1. 是否一致（一致/不一致/存疑）
2. 详细理由说明"""

    messages.append({"role": "user", "content": user_msg_round2})

    stream2 = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=messages,
        max_tokens=2000,
        stream=True,
    )

    # 收集 Round 1.2 的 reasoning 和最终结论
    final_reasoning = ""
    for chunk in stream2:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
            yield ("reasoning_token", delta.reasoning_content)

        if delta.content:
            final_reasoning += delta.content

    # 解析最终结论（简单判断：包含"一致"则为 True）
    is_consistent = "一致" in final_reasoning and "不一致" not in final_reasoning

    yield ("judgment", {
        "is_consistent": is_consistent,
        "reasoning": final_reasoning,
    })



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

            sp = build_system_prompt()
            yield f"data: {json.dumps({'type':'item_info','item':boq_item}, ensure_ascii=False)}\n\n"

            final_results = []
            for event_type, data in stream_pricing_item(boq_item, sp, conn):
                if event_type == "reasoning_token":
                    yield f"data: {json.dumps({'type':'reasoning_token','token':data}, ensure_ascii=False)}\n\n"
                elif event_type == "code_check":
                    yield f"data: {json.dumps({'type':'code_check',**data}, ensure_ascii=False)}\n\n"
                elif event_type == "judgment":
                    yield f"data: {json.dumps({'type':'judgment',**data}, ensure_ascii=False)}\n\n"

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
