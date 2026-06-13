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

_TOOL_SUBMIT_FEATURE_ANALYSIS = {
    "type": "function",
    "function": {
        "name": "submit_feature_analysis",
        "description": "提交项目特征完整性分析结果，说明当前项目特征描述是否足以支撑套定额，并列出缺失的必要特征。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "is_complete": {"type": "boolean", "description": "项目特征描述是否完整充分，可满足套定额要求"},
                "missing_features": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "缺少的必要特征信息列表，若完整则为空数组",
                },
                "analysis": {"type": "string", "description": "简短分析说明（1-2句）"},
            },
            "required": ["is_complete", "missing_features", "analysis"],
            "additionalProperties": False,
        },
    },
}

_TOOL_SUBMIT_WORK_PROCEDURES = {
    "type": "function",
    "function": {
        "name": "submit_work_procedures",
        "description": "提交该清单项的标准施工工序拆解结果，按施工顺序列出每道工序名称。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "procedures": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "按顺序排列的标准工序名称列表，例如：[\"制作\", \"安装\", \"除锈\"]",
                },
            },
            "required": ["procedures"],
            "additionalProperties": False,
        },
    },
}

_TOOL_SUBMIT_QUOTA_MATCH = {
    "type": "function",
    "function": {
        "name": "submit_quota_match",
        "description": "提交套定额结果，包括从候选定额中选出的匹配子目列表，以及影响套定额的模糊问题。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "matches": {
                    "type": "array",
                    "description": "匹配的定额子目列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "zmbh": {"type": "string", "description": "定额子目编码"},
                            "zmmc": {"type": "string", "description": "定额子目名称"},
                            "qty_factor": {"type": "number", "description": "工程量系数，一般为1，换算时填具体值"},
                            "confidence": {"type": "string", "enum": ["high", "medium", "low"], "description": "匹配置信度"},
                            "match_reason": {"type": "string", "description": "选取该定额的简要理由"},
                        },
                        "required": ["zmbh", "zmmc", "qty_factor", "confidence", "match_reason"],
                        "additionalProperties": False,
                    },
                },
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "影响套定额的模糊或不清楚的问题，若无则为空数组",
                },
            },
            "required": ["matches", "issues"],
            "additionalProperties": False,
        },
    },
}

_TOOL_FETCH_QUOTA_CANDIDATES = {
    "type": "function",
    "function": {
        "name": "fetch_quota_candidates",
        "description": "根据工程量清单编码，查询该清单项对应的定额候选子目列表。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "item_code": {"type": "string", "description": "工程量清单编码，例如：010402001006"},
            },
            "required": ["item_code"],
            "additionalProperties": False,
        },
    },
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

def exec_fetch_quota_candidates(conn, item_code: str) -> dict:
    base_code = item_code.strip()[:-3] if len(item_code.strip()) > 3 else item_code.strip()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT q.id, q.dekid, q.zmbh, q.zmmc, q.dw, q.gznr
            FROM tqdk_tqdzm zm
            JOIN tqdk_tqdzy cand ON cand.qdkid = zm.qdkid AND cand.qdzmid = zm.id
            JOIN tdek_tdezm q ON q.dekid = cand.dekid AND q.id = cand.dezmid
            WHERE zm.zmbh = %s
            LIMIT 50
        """, (base_code,))
        rows = cur.fetchall()
    candidates = [
        {"id": r[0], "dekid": r[1], "zmbh": r[2], "zmmc": r[3], "dw": r[4], "gznr": r[5] or ""}
        for r in rows
    ]
    return {"item_code": item_code, "base_code": base_code, "candidates": candidates, "total": len(candidates)}

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
        # Round 1 — 工程量清单项进行编码一致性检查
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
        # Round 2 — 全新对话，不需携带 Round 1 的 reasoning_content
        print("[stream] round2", file=sys.stderr, flush=True)
        user_msg_r2 = (
            f"请分析以下工程量清单项的项目特征描述是否完整充分，能否满足套定额要求：\n\n"
            f"清单编码：{boq_item['item_code']}\n"
            f"清单名称：{boq_item['item_name']}\n"
            f"项目特征：{boq_item.get('item_description') or '（未填写）'}\n"
            f"计量单位：{boq_item.get('unit') or '无'}\n\n"
            f"请调用工具提交你的分析结果，列出缺少的必要特征信息。"
        )
        messages_r2 = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg_r2},
        ]
        stream2 = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=messages_r2,
            tools=[_TOOL_SUBMIT_FEATURE_ANALYSIS],
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
            max_tokens=4000,
            stream=True,
        )
        tool_args_r2 = ""
        for chunk in stream2:
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
                        tool_args_r2 += tc.function.arguments
        feature_result = json.loads(tool_args_r2)
        print("[stream] round2_done", file=sys.stderr, flush=True)
        yield ("feature_check", feature_result)
        # Round 3 — 标准工序拆解，全新独立对话
        print("[stream] round3", file=sys.stderr, flush=True)
        user_msg_r3 = (
            f"请根据以下工程量清单项的名称和项目特征，拆解出完成该清单项所需的标准施工工序，按施工顺序列出：\n\n"
            f"清单名称：{boq_item['item_name']}\n"
            f"项目特征：{boq_item.get('item_description') or '（未填写）'}\n\n"
            f"请调用工具提交工序拆解结果。"
        )
        messages_r3 = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg_r3},
        ]
        stream3 = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=messages_r3,
            tools=[_TOOL_SUBMIT_WORK_PROCEDURES],
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
            max_tokens=4000,
            stream=True,
        )
        tool_args_r3 = ""
        for chunk in stream3:
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
                        tool_args_r3 += tc.function.arguments
        procedures_result = json.loads(tool_args_r3)
        print("[stream] round3_done", file=sys.stderr, flush=True)
        yield ("work_procedures", procedures_result)
        # Round 4 — 定额候选查询，AI调用工具，Python执行DB查询
        print("[stream] round4", file=sys.stderr, flush=True)
        user_msg_r4 = (
            f"请调用工具查询以下清单项的定额候选子目：\n\n"
            f"清单编码：{boq_item['item_code']}\n"
            f"清单名称：{boq_item['item_name']}\n\n"
            f"请调用工具获取定额候选数据。"
        )
        messages_r4 = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg_r4}]
        stream4 = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=messages_r4,
            tools=[_TOOL_FETCH_QUOTA_CANDIDATES],
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
            max_tokens=2000,
            stream=True,
        )
        tool_args_r4 = ""
        for chunk in stream4:
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
                        tool_args_r4 += tc.function.arguments
        call_input_r4 = json.loads(tool_args_r4)
        candidates_data = exec_fetch_quota_candidates(conn, call_input_r4.get("item_code", boq_item["item_code"]))
        print("[stream] round4_done", file=sys.stderr, flush=True)
        yield ("quota_candidates", candidates_data)
        # Round 5 — 套定额匹配，候选列表直接嵌入提示词
        print("[stream] round5", file=sys.stderr, flush=True)
        candidates_text = "\n".join(
            f"  [{i+1}] 编码：{c['zmbh']}  名称：{c['zmmc']}  单位：{c['dw']}"
            + (f"\n      施工内容：{c['gznr']}" if c['gznr'] else "")
            for i, c in enumerate(candidates_data["candidates"])
        ) or "（无候选定额）"
        circle_nums = '①②③④⑤⑥⑦⑧⑨⑩'
        procedures_text = " → ".join(
            f"{circle_nums[i] if i < len(circle_nums) else str(i+1)}{p}"
            for i, p in enumerate(procedures_result.get("procedures", []))
        )
        user_msg_r5 = (
            f"请根据以下信息，从候选定额子目中选出最匹配的定额，完成套定额。\n\n"
            f"【清单项信息】\n"
            f"清单名称：{boq_item['item_name']}\n"
            f"项目特征：{boq_item.get('item_description') or '（未填写）'}\n"
            f"计量单位：{boq_item.get('unit') or '无'}\n\n"
            f"【标准施工工序】\n{procedures_text or '（未获取）'}\n\n"
            f"【候选定额子目（共 {candidates_data['total']} 条）】\n{candidates_text}\n\n"
            f"请调用工具提交套定额结果，选出匹配的定额子目并说明理由，同时列出影响套定额的模糊问题。"
        )
        messages_r5 = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg_r5}]
        # Round 5 非流式，不启用 thinking（thinking tokens 会吃掉 max_tokens 导致 JSON 截断）
        resp5 = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=messages_r5,
            tools=[_TOOL_SUBMIT_QUOTA_MATCH],
            tool_choice={"type": "function", "function": {"name": "submit_quota_match"}},
            max_tokens=8000,
            stream=False,
        )
        msg5 = resp5.choices[0].message
        finish5 = resp5.choices[0].finish_reason
        print(f"[stream] round5_finish_reason: {finish5}", file=sys.stderr, flush=True)
        if hasattr(msg5, 'reasoning_content') and msg5.reasoning_content:
            yield ("reasoning_token", msg5.reasoning_content)
        if not msg5.tool_calls:
            raise ValueError(f"Round 5: AI did not call tool (finish_reason={finish5}, content={msg5.content!r})")
        raw_args = msg5.tool_calls[0].function.arguments
        print(f"[stream] round5_args_len: {len(raw_args)}", file=sys.stderr, flush=True)
        try:
            match_result = json.loads(raw_args)
        except Exception as e:
            print(f"[stream] round5_json_error raw: {raw_args[:600]}", file=sys.stderr, flush=True)
            raise
        print("[stream] round5_done", file=sys.stderr, flush=True)
        yield ("quota_match", match_result)
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
                elif event_type == "feature_check":
                    yield f"data: {json.dumps({'type':'feature_check',**data}, ensure_ascii=False)}\n\n"
                elif event_type == "work_procedures":
                    yield f"data: {json.dumps({'type':'work_procedures',**data}, ensure_ascii=False)}\n\n"
                elif event_type == "quota_candidates":
                    yield f"data: {json.dumps({'type':'quota_candidates',**data}, ensure_ascii=False)}\n\n"
                elif event_type == "quota_match":
                    yield f"data: {json.dumps({'type':'quota_match',**data}, ensure_ascii=False)}\n\n"
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

