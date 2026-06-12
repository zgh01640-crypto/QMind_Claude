"""单条组价路由"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import json

router = APIRouter()

def _ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS pricing_task_results(id SERIAL PRIMARY KEY, boq_item_id INTEGER NOT NULL, boq_project_id INTEGER NOT NULL, dezmid BIGINT NOT NULL, dekid BIGINT NOT NULL, subitem_code VARCHAR(64), subitem_name TEXT, qty_factor NUMERIC(20,6) DEFAULT 1, work_procedure TEXT, confidence VARCHAR(16), missing_info TEXT, ai_reasoning TEXT, status VARCHAR(16) DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())""")
        conn.commit()

def exec_check_item_code(conn, item_code: str, item_name: str) -> dict:
    base_code = item_code.strip()[:-3] if len(item_code.strip()) > 3 else item_code.strip()
    with conn.cursor() as cur:
        cur.execute("SELECT zmmc FROM tqdk_tqdzm WHERE zmbh = %s LIMIT 5", (base_code,))
        rows = cur.fetchall()
    standard_names = list({r[0] for r in rows if r[0]})
    standard_name = standard_names[0] if standard_names else ""
    boq = item_name.strip()
    std = standard_name.strip()
    is_consistent = bool(std) and (boq == std or boq in std or std in boq)
    return {
        "item_code": item_code,
        "item_name": item_name,
        "base_code": base_code,
        "standard_name": standard_name,
        "found": bool(standard_names),
        "is_consistent": is_consistent,
    }

_TOOL_CHECK_ITEM_CODE = {
    "type": "function",
    "function": {
        "name": "check_item_code",
        "description": "根据工程量清单编码和清单名称，查询标准清单名称并判断编码与名称是否一致。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "item_code": {"type": "string", "description": "工程量清单编码，例如：010402001006"},
                "item_name": {"type": "string", "description": "工程量清单名称，例如：砌砖墙"},
            },
            "required": ["item_code", "item_name"],
            "additionalProperties": False,
        },
    },
}

def build_system_prompt() -> str:
    return (
        "你是专业的建筑工程造价工程师，精通以下标准与规范：\n"
        "各专业工程量清单计价标准\n"
        "各专业工程消耗量标准\n"
        "任务：将招标工程量清单中的清单项与定额子目进行匹配（即『套定额』），完成必要的换算及综合单价计算。\n"
        "要求：全程使用中文进行推理和分析，包括思维链过程。"
    )

def stream_pricing_item(boq_item: dict, system_prompt: str, conn):
    from openai import OpenAI
    import os, sys
    print("[stream] start", file=sys.stderr, flush=True)
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        yield ("error", "DEEPSEEK_API_KEY not set")
        return
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=120.0)
    try:
        user_msg = (
            f"请对以下工程量清单项进行编码一致性检查：\n\n"
            f"清单编码：{boq_item['item_code']}\n"
            f"清单名称：{boq_item['item_name']}\n"
            f"项目特征：{boq_item.get('item_description') or '无'}\n"
            f"计量单位：{boq_item.get('unit') or '无'}\n"
            f"工程量：{boq_item.get('quantity') or '无'}\n\n"
            f"请调用工具查询该清单编码对应的标准清单名称。"
        )
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}]
        print("[stream] round1", file=sys.stderr, flush=True)
        yield ("reasoning_token", "[Round 1] Querying API...\n")
        stream1 = client.chat.completions.create(model="deepseek-v4-pro", messages=messages, tools=[_TOOL_CHECK_ITEM_CODE], reasoning_effort="high", extra_body={"thinking": {"type": "enabled"}}, max_tokens=8000, stream=True)
        tool_call_args = ""
        for chunk in stream1:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                yield ("reasoning_token", delta.reasoning_content)
            if delta.content:
                yield ("reasoning_token", delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.function and tc.function.arguments:
                        tool_call_args += tc.function.arguments
        print("[stream] exec_tool", file=sys.stderr, flush=True)
        try:
            call_input = json.loads(tool_call_args)
            code_check_result = exec_check_item_code(
                conn,
                call_input.get("item_code", ""),
                call_input.get("item_name", ""),
            )
        except Exception as e:
            code_check_result = {"item_code": boq_item['item_code'], "item_name": boq_item['item_name'], "base_code": "", "standard_name": "", "found": False, "is_consistent": False, "error": str(e)}
        yield ("code_check", code_check_result)
        print("[stream] done", file=sys.stderr, flush=True)
        yield ("judgment", {
            "is_consistent": code_check_result["is_consistent"],
            "reasoning": f"标准清单名称：{code_check_result['standard_name'] or '未找到'}",
        })
    except Exception as e:
        import traceback
        print(f"[stream] error: {str(e)}", file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        yield ("error", str(e))

@router.post("/pricing-task/match-item-stream")
def pricing_task_match_item_stream(req: dict):
    from db.connection import get_connection
    def generate():
        conn = get_connection()
        try:
            _ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT id, item_code, item_name, item_description, unit, quantity, project_id FROM boq_items WHERE id = %s", (req.get("boq_item_id"),))
                row = cur.fetchone()
            if not row:
                yield f"data: {json.dumps({'type':'error','error':'Item not found'})}\n\n"
                return
            boq_item = {"id": row[0], "item_code": row[1], "item_name": row[2], "item_description": row[3], "unit": row[4], "quantity": float(row[5]) if row[5] else None, "project_id": row[6]}
            sp = build_system_prompt()
            yield f"data: {json.dumps({'type':'item_info','item':boq_item}, ensure_ascii=False)}\n\n"
            import sys
            print("[SSE] calling stream", file=sys.stderr, flush=True)
            for event_type, data in stream_pricing_item(boq_item, sp, conn):
                print(f"[SSE] {event_type}", file=sys.stderr, flush=True)
                if event_type == "reasoning_token":
                    yield f"data: {json.dumps({'type':'reasoning_token','token':data}, ensure_ascii=False)}\n\n"
                elif event_type == "code_check":
                    yield f"data: {json.dumps({'type':'code_check',**data}, ensure_ascii=False)}\n\n"
                elif event_type == "judgment":
                    yield f"data: {json.dumps({'type':'judgment',**data}, ensure_ascii=False)}\n\n"
                elif event_type == "error":
                    yield f"data: {json.dumps({'type':'error','error':data}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type':'done'})}\n\n"
        except Exception as e:
            import traceback
            print(f"[SSE] error: {str(e)}", file=sys.stderr, flush=True)
            print(traceback.format_exc(), file=sys.stderr, flush=True)
            yield f"data: {json.dumps({'type':'error','error':str(e)})}\n\n"
        finally:
            conn.close()
    return StreamingResponse(generate(), media_type="text/event-stream")

