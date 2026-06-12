"""单条组价路由"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import json

router = APIRouter()

def _ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS pricing_task_results(id SERIAL PRIMARY KEY, boq_item_id INTEGER NOT NULL, boq_project_id INTEGER NOT NULL, dezmid BIGINT NOT NULL, dekid BIGINT NOT NULL, subitem_code VARCHAR(64), subitem_name TEXT, qty_factor NUMERIC(20,6) DEFAULT 1, work_procedure TEXT, confidence VARCHAR(16), missing_info TEXT, ai_reasoning TEXT, status VARCHAR(16) DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())""")
        conn.commit()

def exec_check_item_code(conn, item_code: str) -> dict:
    base_code = item_code.strip()[-9:] if len(item_code.strip()) >= 3 else item_code.strip()
    with conn.cursor() as cur:
        cur.execute("SELECT zmmc FROM tqdk_tqdzm WHERE zmbh = %s LIMIT 5", (base_code,))
        rows = cur.fetchall()
    standard_names = list({r[0] for r in rows if r[0]})
    return {"item_code": item_code, "base_code": base_code, "standard_names": standard_names, "found": len(standard_names) > 0}

_TOOL_CHECK_ITEM_CODE = {"type": "function", "function": {"name": "check_item_code", "description": "Check item code", "strict": True, "parameters": {"type": "object", "properties": {"item_code": {"type": "string"}}, "required": ["item_code"], "additionalProperties": False}}}

def build_system_prompt() -> str:
    return "Review BOQ items and compare with standard names."

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
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Code:{boq_item['item_code']} Name:{boq_item['item_name']}"}]
        print("[stream] round1", file=sys.stderr, flush=True)
        yield ("reasoning_token", "[Round 1] Querying API...\n")
        stream1 = client.chat.completions.create(model="deepseek-v4-pro", messages=messages, tools=[_TOOL_CHECK_ITEM_CODE], tool_choice={"type": "function", "function": {"name": "check_item_code"}}, reasoning_effort="high", extra_body={"thinking": {"type": "enabled"}}, max_tokens=8000, stream=True)
        tool_call_id, tool_call_args, reasoning_content, content = "", "", "", ""
        for chunk in stream1:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                reasoning_content += delta.reasoning_content
                yield ("reasoning_token", delta.reasoning_content)
            if delta.content:
                content += delta.content
                yield ("reasoning_token", delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.id:
                        tool_call_id = tc.id
                    if tc.function and tc.function.arguments:
                        tool_call_args += tc.function.arguments
        print("[stream] exec_tool", file=sys.stderr, flush=True)
        try:
            call_input = json.loads(tool_call_args)
            code_check_result = exec_check_item_code(conn, call_input.get("item_code", ""))
        except Exception as e:
            code_check_result = {"item_code": boq_item['item_code'], "base_code": "", "standard_names": [], "found": False, "error": str(e)}
        yield ("code_check", code_check_result)
        standard_names_str = ", ".join(code_check_result.get("standard_names", [])) or "not found"
        assistant_message = {"role": "assistant", "content": content, "reasoning_content": reasoning_content, "tool_calls": [{"id": tool_call_id, "type": "function", "function": {"name": "check_item_code", "arguments": tool_call_args}}] if tool_call_id else None}
        messages.append(assistant_message)
        messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(code_check_result, ensure_ascii=False)})
        messages.append({"role": "user", "content": f"Compare: BOQ={boq_item['item_name']}, Standard={standard_names_str}"})
        print("[stream] round2", file=sys.stderr, flush=True)
        yield ("reasoning_token", "\n[Round 2] Comparing...\n")
        stream2 = client.chat.completions.create(model="deepseek-v4-pro", messages=messages, reasoning_effort="high", extra_body={"thinking": {"type": "enabled"}}, max_tokens=8000, stream=True)
        final_reasoning = ""
        for chunk in stream2:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                yield ("reasoning_token", delta.reasoning_content)
            if delta.content:
                yield ("reasoning_token", delta.content)
                final_reasoning += delta.content
        print("[stream] done", file=sys.stderr, flush=True)
        is_consistent = "consistent" in final_reasoning.lower() or "一致" in final_reasoning
        yield ("judgment", {"is_consistent": is_consistent, "reasoning": final_reasoning})
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
