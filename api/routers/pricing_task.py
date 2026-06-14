"""单条组价路由.

当前阶段完成“套定额闭环”：任务入库、单条运行入库、AI 结果候选校验、
人工确认/拒绝、人工对比工程评测。不在本阶段计算综合单价。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any, Iterable, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field
from psycopg2.extras import Json

router = APIRouter()


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _sse(data: dict[str, Any]) -> str:
    return f"data: {_json_dumps(data)}\n\n"


def _base_code(item_code: str | None) -> str:
    code = (item_code or "").strip().replace(" ", "")
    return code[:-3] if len(code) > 9 else code


def _ensure_schema(conn):
    """Idempotent schema for the pricing-task workflow."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pricing_tasks (
                id                  SERIAL PRIMARY KEY,
                name                TEXT NOT NULL,
                boq_project_id      INTEGER NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE,
                quota_library_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
                manual_project_id   INTEGER REFERENCES manual_boq_projects(id) ON DELETE SET NULL,
                legacy_local_id     TEXT UNIQUE,
                status              VARCHAR(16) NOT NULL DEFAULT 'active',
                created_at          TIMESTAMP DEFAULT NOW(),
                updated_at          TIMESTAMP DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pricing_task_runs (
                id                  SERIAL PRIMARY KEY,
                task_id             INTEGER REFERENCES pricing_tasks(id) ON DELETE CASCADE,
                boq_item_id         INTEGER NOT NULL REFERENCES boq_items(id) ON DELETE CASCADE,
                boq_project_id      INTEGER NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE,
                status              VARCHAR(16) NOT NULL DEFAULT 'running',
                reasoning_text      TEXT,
                code_check          JSONB,
                feature_check       JSONB,
                work_procedures     JSONB,
                quota_candidates    JSONB,
                quota_match         JSONB,
                evaluation          JSONB,
                error_message       TEXT,
                created_at          TIMESTAMP DEFAULT NOW(),
                finished_at         TIMESTAMP
            )
            """
        )
        cur.execute(
            """
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
            """
        )
        cur.execute("ALTER TABLE pricing_task_results ADD COLUMN IF NOT EXISTS task_id INTEGER")
        cur.execute("ALTER TABLE pricing_task_results ADD COLUMN IF NOT EXISTS run_id INTEGER")
        cur.execute("ALTER TABLE pricing_task_results ADD COLUMN IF NOT EXISTS match_reason TEXT")
        cur.execute("ALTER TABLE pricing_task_results ADD COLUMN IF NOT EXISTS evaluation JSONB")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pricing_tasks_project ON pricing_tasks(boq_project_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ptr_boq_item ON pricing_task_results(boq_item_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ptr_run ON pricing_task_results(run_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ptr_task ON pricing_task_results(task_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pricing_task_runs_task_item ON pricing_task_runs(task_id, boq_item_id)")
    conn.commit()


class PricingTaskCreate(BaseModel):
    name: str
    boq_project_id: int
    quota_library_ids: list[int] = Field(default_factory=list)
    manual_project_id: Optional[int] = None
    legacy_local_id: Optional[str] = None


class PricingTaskImportItem(BaseModel):
    id: str
    name: str
    project_id: int
    manual_project_id: Optional[int] = None
    chapter_ids: list[int] = Field(default_factory=list)


class PricingTaskImportRequest(BaseModel):
    tasks: list[PricingTaskImportItem]


class RunRequest(BaseModel):
    boq_item_id: int


class ConfirmRunRequest(BaseModel):
    results: Optional[list[dict[str, Any]]] = None


_TOOL_SUBMIT_FEATURE_ANALYSIS = {
    "type": "function",
    "function": {
        "name": "submit_feature_analysis",
        "description": "提交项目特征完整性分析结果，说明当前项目特征描述是否足以支撑套定额，并列出缺失的必要特征。",
        "parameters": {
            "type": "object",
            "properties": {
                "is_complete": {"type": "boolean", "description": "项目特征描述是否完整充分，可满足套定额要求"},
                "missing_features": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "缺少的必要特征信息列表，若完整则为空数组",
                },
                "analysis": {"type": "string", "description": "简短分析说明"},
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
        "parameters": {
            "type": "object",
            "properties": {
                "procedures": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "按顺序排列的标准工序名称列表",
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
        "description": "提交套定额结果。只能从候选定额中按 dekid/dezmid 选择，不允许编造候选外子目。",
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
                            "dekid": {"type": "integer", "description": "候选定额库 ID"},
                            "dezmid": {"type": "integer", "description": "候选定额子目 ID"},
                            "qty_factor": {"type": "number", "description": "工程量系数，一般为1"},
                            "confidence": {"type": "string", "enum": ["high", "medium", "low"], "description": "匹配置信度"},
                            "match_reason": {"type": "string", "description": "选取该定额的简要理由"},
                        },
                        "required": ["dekid", "dezmid", "qty_factor", "confidence", "match_reason"],
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

_TOOL_CHECK_ITEM_CODE = {
    "type": "function",
    "function": {
        "name": "check_item_code",
        "description": "根据工程量清单编码和清单名称，查询标准清单名称并判断编码与名称是否一致。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "item_code": {"type": "string", "description": "工程量清单编码"},
                "item_name": {"type": "string", "description": "工程量清单名称"},
            },
            "required": ["item_code", "item_name"],
            "additionalProperties": False,
        },
    },
}


def _client(thinking: bool = True) -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
    base_url = "https://api.deepseek.com" if thinking else "https://api.deepseek.com/beta"
    return OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)


def _model() -> str:
    return os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")


def exec_check_item_code(conn, item_code: str, item_name: str) -> dict[str, Any]:
    base_code = _base_code(item_code)
    with conn.cursor() as cur:
        cur.execute("SELECT zmmc FROM tqdk_tqdzm WHERE zmbh = %s LIMIT 5", (base_code,))
        rows = cur.fetchall()
    standard_names = sorted({r[0] for r in rows if r[0]})
    standard_name = standard_names[0] if standard_names else ""
    boq = (item_name or "").strip()
    std = standard_name.strip()
    return {
        "item_code": item_code,
        "item_name": item_name,
        "base_code": base_code,
        "standard_name": standard_name,
        "standard_names": standard_names,
        "found": bool(standard_names),
        "is_consistent": bool(std) and (boq == std or boq in std or std in boq),
    }


def exec_fetch_standard_work_procedure(conn, item_code: str) -> dict[str, Any]:
    base_code = _base_code(item_code)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT zmbh, zmmc, appendix_code, appendix_name, procedure_text, source_rowid
            FROM tqdk_tqdgx
            WHERE zmbh = %s
            ORDER BY source_rowid
            LIMIT 1
            """,
            (base_code,),
        )
        row = cur.fetchone()
    if not row:
        return {
            "item_code": item_code,
            "base_code": base_code,
            "found": False,
            "procedure_text": "",
            "procedures": [],
        }
    return {
        "item_code": item_code,
        "base_code": base_code,
        "found": True,
        "zmbh": row[0],
        "zmmc": row[1],
        "appendix_code": row[2],
        "appendix_name": row[3],
        "procedure_text": row[4] or "",
        "procedures": [row[4]] if row[4] else [],
        "source_rowid": row[5],
    }


def exec_fetch_quota_candidates(conn, item_code: str, quota_library_ids: list[int] | None = None) -> dict[str, Any]:
    base_code = _base_code(item_code)
    params: list[Any] = [base_code]
    library_filter = ""
    if quota_library_ids:
        library_filter = "AND q.dekid = ANY(%s)"
        params.append(quota_library_ids)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT q.id, q.dekid, l.mc, q.zmbh, q.zmmc, q.dw, q.gznr, c.zjmc
            FROM tqdk_tqdzm zm
            JOIN tqdk_tqdzy cand ON cand.qdkid = zm.qdkid AND cand.qdzmid = zm.id
            JOIN tdek_tdezm q ON q.dekid = cand.dekid AND q.id = cand.dezmid
            JOIN tlibs l ON l.id = q.dekid
            LEFT JOIN tdek_tzjmc c ON c.dekid = q.dekid AND c.id = q.zjh
            WHERE zm.zmbh = %s
              {library_filter}
            ORDER BY q.dekid, q.zmbh NULLS LAST, q.id
            LIMIT 80
            """,
            params,
        )
        rows = cur.fetchall()
    candidates = [
        {
            "id": int(r[0]),
            "dezmid": int(r[0]),
            "dekid": int(r[1]),
            "library_name": r[2],
            "zmbh": r[3],
            "zmmc": r[4],
            "dw": r[5],
            "gznr": r[6] or "",
            "chapter_name": r[7],
        }
        for r in rows
    ]
    return {
        "item_code": item_code,
        "base_code": base_code,
        "quota_library_ids": quota_library_ids or [],
        "candidates": candidates,
        "total": len(candidates),
    }


def build_system_prompt() -> str:
    return (
        "你是专业的建筑工程造价工程师，任务是将招标工程量清单中的清单项与定额子目进行匹配（套定额）。\n"
        "必须基于后端提供的候选定额进行选择，不得编造候选外定额。\n"
        "工程量系数只表示清单工程量与定额单位之间的纯换算关系。\n"
        "置信度：high 表示特征与定额充分匹配；medium 表示主要特征匹配但仍有疑问；low 表示关键特征缺失。\n"
        "请全程使用中文分析。"
    )


def _collect_stream_tool_args(stream, reasoning_parts: list[str]) -> str:
    args = ""
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            reasoning_parts.append(delta.reasoning_content)
        if getattr(delta, "content", None):
            reasoning_parts.append(delta.content)
        if delta.tool_calls:
            for tc in delta.tool_calls:
                if tc.function and tc.function.arguments:
                    args += tc.function.arguments
    return args


def _run_stream_tool(messages: list[dict[str, Any]], tool: dict[str, Any], max_tokens: int, reasoning_parts: list[str]) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            stream = _client(thinking=True).chat.completions.create(
                model=_model(),
                messages=messages,
                tools=[tool],
                reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}},
                max_tokens=max_tokens,
                stream=True,
            )
            raw = _collect_stream_tool_args(stream, reasoning_parts)
            return json.loads(raw)
        except Exception as exc:  # keep the current stage retry-local
            last_error = exc
            print(f"[pricing-task] stream tool error attempt={attempt + 1}: {exc}", file=sys.stderr, flush=True)
    raise last_error or RuntimeError("stream tool failed")


def _stream_tool_call(messages: list[dict[str, Any]], tool: dict[str, Any], max_tokens: int) -> Iterable[tuple[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(2):
        raw = ""
        try:
            stream = _client(thinking=True).chat.completions.create(
                model=_model(),
                messages=messages,
                tools=[tool],
                reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}},
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                token = ""
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    token += delta.reasoning_content
                if getattr(delta, "content", None):
                    token += delta.content
                if token:
                    yield ("reasoning_token", token)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.function and tc.function.arguments:
                            raw += tc.function.arguments
            yield ("tool_result", json.loads(raw))
            return
        except Exception as exc:
            last_error = exc
            print(f"[pricing-task] stream tool error attempt={attempt + 1}: {exc}", file=sys.stderr, flush=True)
    raise last_error or RuntimeError("stream tool failed")


def _stream_text_completion(messages: list[dict[str, Any]], max_tokens: int) -> Iterable[tuple[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(2):
        parts: list[str] = []
        try:
            stream = _client(thinking=True).chat.completions.create(
                model=_model(),
                messages=messages,
                reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}},
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                token = ""
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    token += delta.reasoning_content
                if getattr(delta, "content", None):
                    token += delta.content
                if token:
                    parts.append(token)
                    yield ("reasoning_token", token)
            yield ("text_result", "".join(parts))
            return
        except Exception as exc:
            last_error = exc
            print(f"[pricing-task] stream text error attempt={attempt + 1}: {exc}", file=sys.stderr, flush=True)
    raise last_error or RuntimeError("stream text failed")


def _run_submit_match(messages: list[dict[str, Any]]) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            resp = _client(thinking=False).chat.completions.create(
                model=_model(),
                messages=messages,
                tools=[_TOOL_SUBMIT_QUOTA_MATCH],
                tool_choice={"type": "function", "function": {"name": "submit_quota_match"}},
                extra_body={"thinking": {"type": "disabled"}},
                max_tokens=8000,
                stream=False,
            )
            msg = resp.choices[0].message
            if not msg.tool_calls:
                raise ValueError(f"AI did not call submit_quota_match: {msg.content!r}")
            call = msg.tool_calls[0]
            if call.function.name != "submit_quota_match":
                raise ValueError(f"unexpected tool call {call.function.name!r}")
            return json.loads(call.function.arguments)
        except Exception as exc:
            last_error = exc
            print(f"[pricing-task] submit match error attempt={attempt + 1}: {exc}", file=sys.stderr, flush=True)
    raise last_error or RuntimeError("submit match failed")


def _normalize_matches(raw_match: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_by_key = {(int(c["dekid"]), int(c["dezmid"])): c for c in candidates}
    normalized = []
    seen: set[tuple[int, int]] = set()
    for m in raw_match.get("matches", []):
        key = (int(m.get("dekid")), int(m.get("dezmid")))
        if key in seen:
            continue
        cand = candidate_by_key.get(key)
        if not cand:
            continue
        seen.add(key)
        confidence = m.get("confidence") if m.get("confidence") in {"high", "medium", "low"} else "low"
        try:
            qty_factor = float(m.get("qty_factor", 1) or 1)
        except Exception:
            qty_factor = 1.0
        normalized.append(
            {
                "dekid": cand["dekid"],
                "dezmid": cand["dezmid"],
                "zmbh": cand["zmbh"],
                "zmmc": cand["zmmc"],
                "dw": cand["dw"],
                "library_name": cand["library_name"],
                "chapter_name": cand.get("chapter_name"),
                "qty_factor": qty_factor,
                "confidence": confidence,
                "match_reason": m.get("match_reason") or "",
            }
        )
    return {"matches": normalized, "issues": raw_match.get("issues", [])}


def _manual_quotas(conn, manual_project_id: int | None, item_code: str | None) -> list[dict[str, Any]]:
    if not manual_project_id or not item_code:
        return []
    full_code = (item_code or "").strip().replace(" ", "")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT q.quota_code, q.quota_name, q.quota_unit, q.quantity, q.qty_factor
            FROM manual_boq_items i
            JOIN manual_boq_quotas q ON q.boq_item_id = i.id
            WHERE i.project_id = %s
              AND replace(trim(COALESCE(i.item_code, '')), ' ', '') = %s
            ORDER BY q.id
            """,
            (manual_project_id, full_code),
        )
        rows = cur.fetchall()
    return [
        {
            "quota_code": r[0],
            "quota_name": r[1],
            "quota_unit": r[2],
            "quantity": float(r[3]) if r[3] is not None else None,
            "qty_factor": float(r[4]) if r[4] is not None else None,
        }
        for r in rows
    ]


def _evaluate(matches: list[dict[str, Any]], manual_quotas: list[dict[str, Any]]) -> dict[str, Any]:
    ai_codes = {str(m.get("zmbh")).strip() for m in matches if m.get("zmbh")}
    manual_codes = {str(q.get("quota_code")).strip() for q in manual_quotas if q.get("quota_code")}

    # Manual exports may carry suffixes such as "换"; treat "010001-32" as hit
    # when a manual code is "010001-32换".
    hit_codes = sorted(ai_code for ai_code in ai_codes if any(ai_code in manual_code for manual_code in manual_codes))
    missed_codes = sorted(manual_code for manual_code in manual_codes if not any(ai_code in manual_code for ai_code in ai_codes))
    extra_codes = sorted(ai_code for ai_code in ai_codes if not any(ai_code in manual_code for manual_code in manual_codes))
    return {
        "manual_quotas": manual_quotas,
        "hit_codes": hit_codes,
        "missed_codes": missed_codes,
        "extra_codes": extra_codes,
        "hit_count": len(hit_codes),
        "missed_count": len(missed_codes),
        "extra_count": len(extra_codes),
        "manual_count": len(manual_codes),
        "ai_count": len(ai_codes),
    }


def _create_run(conn, task_id: int | None, boq_item: dict[str, Any]) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pricing_task_runs(task_id, boq_item_id, boq_project_id, status)
            VALUES (%s, %s, %s, 'running')
            RETURNING id
            """,
            (task_id, boq_item["id"], boq_item["project_id"]),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def _update_run(conn, run_id: int, **fields: Any) -> None:
    if not fields:
        return
    assignments = []
    values = []
    for key, value in fields.items():
        assignments.append(f"{key} = %s")
        values.append(Json(value, dumps=_json_dumps) if key in {
            "code_check", "feature_check", "work_procedures", "quota_candidates", "quota_match", "evaluation"
        } else value)
    values.append(run_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE pricing_task_runs SET {', '.join(assignments)} WHERE id = %s", values)
    conn.commit()


def _save_pending_results(
    conn,
    task_id: int | None,
    run_id: int,
    boq_item: dict[str, Any],
    match_result: dict[str, Any],
    evaluation: dict[str, Any],
) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM pricing_task_results WHERE run_id = %s", (run_id,))
        for m in match_result.get("matches", []):
            cur.execute(
                """
                INSERT INTO pricing_task_results(
                    task_id, run_id, boq_item_id, boq_project_id, dezmid, dekid,
                    subitem_code, subitem_name, qty_factor, confidence, ai_reasoning,
                    match_reason, status, evaluation
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s)
                """,
                (
                    task_id,
                    run_id,
                    boq_item["id"],
                    boq_item["project_id"],
                    m["dezmid"],
                    m["dekid"],
                    m.get("zmbh"),
                    m.get("zmmc"),
                    m.get("qty_factor", 1),
                    m.get("confidence"),
                    m.get("match_reason"),
                    m.get("match_reason"),
                    Json(evaluation, dumps=_json_dumps),
                ),
            )
    conn.commit()


def _stream_pricing_item(
    conn,
    boq_item: dict[str, Any],
    quota_library_ids: list[int],
    manual_project_id: int | None,
    task_id: int | None,
    run_id: int,
) -> Iterable[tuple[str, Any]]:
    system_prompt = build_system_prompt()

    code_check = exec_check_item_code(conn, boq_item["item_code"], boq_item["item_name"])
    yield ("code_check", code_check)
    yield ("judgment", {"is_consistent": code_check["is_consistent"], "reasoning": f"标准清单名称：{code_check['standard_name'] or '未找到'}"})
    _update_run(conn, run_id, code_check=code_check)

    messages_r2 = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"请分析以下工程量清单项的项目特征描述是否完整充分，能否满足套定额要求：\n\n"
                f"清单编码：{boq_item['item_code']}\n清单名称：{boq_item['item_name']}\n"
                f"项目特征：{boq_item.get('item_description') or '（未填写）'}\n计量单位：{boq_item.get('unit') or '无'}\n\n"
                f"请调用工具提交你的分析结果。"
            ),
        },
    ]
    feature_result: dict[str, Any] = {}
    for event_type, data in _stream_tool_call(messages_r2, _TOOL_SUBMIT_FEATURE_ANALYSIS, 4000):
        if event_type == "reasoning_token":
            yield ("reasoning_token", data)
        else:
            feature_result = data
    yield ("feature_check", feature_result)
    _update_run(conn, run_id, feature_check=feature_result)

    procedures_result = exec_fetch_standard_work_procedure(conn, boq_item["item_code"])
    yield ("work_procedures", procedures_result)
    _update_run(conn, run_id, work_procedures=procedures_result)

    candidates_data = exec_fetch_quota_candidates(conn, boq_item["item_code"], quota_library_ids)
    yield ("quota_candidates", candidates_data)
    _update_run(conn, run_id, quota_candidates=candidates_data)

    candidates = candidates_data["candidates"]
    candidate_text = "\n".join(
        f"[{i + 1}] dekid={c['dekid']} dezmid={c['dezmid']} 编码={c['zmbh']} 名称={c['zmmc']} 单位={c['dw']} "
        f"库={c['library_name']} 章节={c.get('chapter_name') or ''}"
        + (f"\n    工作内容：{c['gznr']}" if c.get("gznr") else "")
        for i, c in enumerate(candidates)
    ) or "（无候选定额）"
    procedures_text = procedures_result.get("procedure_text") or " → ".join(procedures_result.get("procedures", []))
    messages_r5_analysis = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"请先对候选定额进行套定额分析，不要调用工具，不要输出 JSON。\n"
                f"请说明候选取舍、工程量系数、置信度依据和模糊问题，最后给出建议选择的 dekid/dezmid。\n\n"
                f"套定额原则：原则上工序会对应一条或多条定额，请你注意拆解和判断。\n\n"
                f"【清单项】\n编码：{boq_item['item_code']}\n名称：{boq_item['item_name']}\n"
                f"项目特征：{boq_item.get('item_description') or '（未填写）'}\n单位：{boq_item.get('unit') or '无'}\n"
                f"【编码核查】{_json_dumps(code_check)}\n"
                f"【项目特征分析】{_json_dumps(feature_result)}\n"
                f"【标准施工工序】{procedures_text or '（未获取）'}\n\n"
                f"【候选定额子目（共 {candidates_data['total']} 条）】\n{candidate_text}\n"
            ),
        },
    ]
    quota_analysis = ""
    if candidates:
        yield ("reasoning_token", "\n\n[第五轮A：套定额分析]\n")
        for event_type, data in _stream_text_completion(messages_r5_analysis, 6000):
            if event_type == "reasoning_token":
                yield ("reasoning_token", data)
            else:
                quota_analysis = data

    messages_r5_submit = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"请根据以下套定额分析和候选定额，严格调用 submit_quota_match 提交最终结构化结果。\n"
                f"只能提交候选中的 dekid/dezmid，不允许编造候选外子目。\n\n"
                f"套定额原则：原则上工序会对应一条或多条定额，请你注意拆解和判断。\n\n"
                f"【清单项】\n编码：{boq_item['item_code']}\n名称：{boq_item['item_name']}\n"
                f"项目特征：{boq_item.get('item_description') or '（未填写）'}\n单位：{boq_item.get('unit') or '无'}\n"
                f"【编码核查】{_json_dumps(code_check)}\n"
                f"【项目特征分析】{_json_dumps(feature_result)}\n"
                f"【标准施工工序】{procedures_text or '（未获取）'}\n\n"
                f"【第五轮A套定额分析】\n{quota_analysis or '（无分析文本）'}\n\n"
                f"【候选定额子目（共 {candidates_data['total']} 条）】\n{candidate_text}\n"
            ),
        },
    ]
    raw_match = _run_submit_match(messages_r5_submit) if candidates else {"matches": [], "issues": ["未找到候选定额子目"]}
    match_result = _normalize_matches(raw_match, candidates)
    manual = _manual_quotas(conn, manual_project_id, boq_item.get("item_code"))
    evaluation = _evaluate(match_result["matches"], manual)
    _update_run(conn, run_id, quota_match=match_result, evaluation=evaluation)
    _save_pending_results(conn, task_id, run_id, boq_item, match_result, evaluation)
    yield ("quota_match", match_result)
    yield ("evaluation", evaluation)


def _row_to_task(row) -> dict[str, Any]:
    ids = row[5] or []
    return {
        "id": row[0],
        "name": row[1],
        "boq_project_id": row[2],
        "project_id": row[2],
        "project_name": row[3],
        "manual_project_id": row[4],
        "quota_library_ids": ids,
        "quota_library_names": row[6] or [],
        "legacy_local_id": row[7],
        "created_at": row[8],
        "latest_run_count": row[9],
    }


@router.get("/pricing-tasks")
def list_pricing_tasks():
    from db.connection import get_connection

    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.id, t.name, t.boq_project_id, p.project_name, t.manual_project_id,
                       t.quota_library_ids, COALESCE(array_agg(l.mc ORDER BY l.id) FILTER (WHERE l.id IS NOT NULL), '{}') AS library_names,
                       t.legacy_local_id, t.created_at,
                       (SELECT COUNT(*) FROM pricing_task_runs r WHERE r.task_id=t.id) AS run_count
                FROM pricing_tasks t
                JOIN boq_projects p ON p.id = t.boq_project_id
                LEFT JOIN LATERAL jsonb_array_elements_text(t.quota_library_ids) lib_id(value) ON TRUE
                LEFT JOIN tlibs l ON l.id = lib_id.value::bigint
                WHERE t.status <> 'deleted'
                GROUP BY t.id, p.project_name
                ORDER BY t.created_at DESC
                """
            )
            return [_row_to_task(row) for row in cur.fetchall()]
    finally:
        conn.close()


@router.post("/pricing-tasks")
def create_pricing_task(body: PricingTaskCreate):
    from db.connection import get_connection

    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT project_name FROM boq_projects WHERE id=%s", (body.boq_project_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="BOQ project not found")
            if body.manual_project_id:
                cur.execute("SELECT id FROM manual_boq_projects WHERE id=%s", (body.manual_project_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="manual project not found")
            cur.execute(
                """
                INSERT INTO pricing_tasks(name, boq_project_id, quota_library_ids, manual_project_id, legacy_local_id)
                VALUES (%s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (legacy_local_id) DO UPDATE SET updated_at=NOW()
                RETURNING id
                """,
                (
                    body.name.strip(),
                    body.boq_project_id,
                    json.dumps(body.quota_library_ids or []),
                    body.manual_project_id,
                    body.legacy_local_id,
                ),
            )
            task_id = cur.fetchone()[0]
        conn.commit()
        return {"id": task_id}
    finally:
        conn.close()


@router.post("/pricing-tasks/import-local")
def import_local_tasks(body: PricingTaskImportRequest):
    from db.connection import get_connection

    conn = get_connection()
    imported = []
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            for item in body.tasks:
                cur.execute(
                    """
                    INSERT INTO pricing_tasks(name, boq_project_id, quota_library_ids, manual_project_id, legacy_local_id)
                    VALUES (%s, %s, '[]'::jsonb, %s, %s)
                    ON CONFLICT (legacy_local_id) DO UPDATE SET updated_at=NOW()
                    RETURNING id
                    """,
                    (item.name, item.project_id, item.manual_project_id, item.id),
                )
                imported.append({"legacy_local_id": item.id, "id": cur.fetchone()[0]})
        conn.commit()
        return {"imported": imported}
    finally:
        conn.close()


@router.get("/pricing-tasks/{task_id}")
def get_pricing_task(task_id: int):
    from db.connection import get_connection

    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.id, t.name, t.boq_project_id, p.project_name, t.manual_project_id,
                       t.quota_library_ids, COALESCE(array_agg(l.mc ORDER BY l.id) FILTER (WHERE l.id IS NOT NULL), '{}') AS library_names,
                       t.legacy_local_id, t.created_at,
                       (SELECT COUNT(*) FROM pricing_task_runs r WHERE r.task_id=t.id) AS run_count
                FROM pricing_tasks t
                JOIN boq_projects p ON p.id = t.boq_project_id
                LEFT JOIN LATERAL jsonb_array_elements_text(t.quota_library_ids) lib_id(value) ON TRUE
                LEFT JOIN tlibs l ON l.id = lib_id.value::bigint
                WHERE t.id=%s AND t.status <> 'deleted'
                GROUP BY t.id, p.project_name
                """,
                (task_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="task not found")
            return _row_to_task(row)
    finally:
        conn.close()


@router.get("/pricing-tasks/{task_id}/items/{boq_item_id}/runs")
def list_item_runs(task_id: int, boq_item_id: int):
    from db.connection import get_connection

    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, code_check, feature_check, work_procedures, quota_candidates,
                       quota_match, evaluation, error_message, created_at, finished_at, reasoning_text
                FROM pricing_task_runs
                WHERE task_id=%s AND boq_item_id=%s
                ORDER BY created_at DESC
                """,
                (task_id, boq_item_id),
            )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "status": r[1],
                "code_check": r[2],
                "feature_check": r[3],
                "work_procedures": r[4],
                "quota_candidates": r[5],
                "quota_match": r[6],
                "evaluation": r[7],
                "error_message": r[8],
                "created_at": r[9],
                "finished_at": r[10],
                "reasoning_text": r[11],
            }
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/pricing-tasks/{task_id}/runs/latest")
def list_latest_task_runs(task_id: int):
    from db.connection import get_connection

    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM pricing_tasks WHERE id=%s AND status <> 'deleted'", (task_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="task not found")
            cur.execute(
                """
                SELECT DISTINCT ON (boq_item_id)
                       boq_item_id, id, status, code_check, feature_check, work_procedures,
                       quota_candidates, quota_match, evaluation, error_message, created_at, finished_at,
                       reasoning_text
                FROM pricing_task_runs
                WHERE task_id=%s
                ORDER BY boq_item_id, created_at DESC, id DESC
                """,
                (task_id,),
            )
            rows = cur.fetchall()
        return [
            {
                "boq_item_id": r[0],
                "run": {
                    "id": r[1],
                    "status": r[2],
                    "code_check": r[3],
                    "feature_check": r[4],
                    "work_procedures": r[5],
                    "quota_candidates": r[6],
                    "quota_match": r[7],
                    "evaluation": r[8],
                    "error_message": r[9],
                    "created_at": r[10],
                    "finished_at": r[11],
                    "reasoning_text": r[12],
                },
            }
            for r in rows
        ]
    finally:
        conn.close()


@router.post("/pricing-tasks/{task_id}/items/{boq_item_id}/run-stream")
def pricing_task_run_item_stream(task_id: int, boq_item_id: int):
    from db.connection import get_connection

    def generate():
        conn = get_connection()
        run_id = None
        try:
            _ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT id, name, boq_project_id, quota_library_ids, manual_project_id FROM pricing_tasks WHERE id=%s", (task_id,))
                task = cur.fetchone()
                if not task:
                    yield _sse({"type": "error", "error": "task not found"})
                    return
                quota_library_ids = task[3] or []
                manual_project_id = task[4]
                cur.execute(
                    """
                    SELECT id, item_code, item_name, item_description, unit, quantity, project_id
                    FROM boq_items WHERE id = %s AND project_id = %s
                    """,
                    (boq_item_id, task[2]),
                )
                row = cur.fetchone()
            if not row:
                yield _sse({"type": "error", "error": "item not found in task project"})
                return
            boq_item = {
                "id": row[0],
                "item_code": row[1],
                "item_name": row[2],
                "item_description": row[3],
                "unit": row[4],
                "quantity": float(row[5]) if row[5] is not None else None,
                "project_id": row[6],
            }
            run_id = _create_run(conn, task_id, boq_item)
            yield _sse({"type": "run_started", "run_id": run_id})
            yield _sse({"type": "item_info", "item": boq_item})
            had_error = False
            reasoning_text_parts: list[str] = []
            for event_type, data in _stream_pricing_item(conn, boq_item, quota_library_ids, manual_project_id, task_id, run_id):
                if event_type == "reasoning_token":
                    reasoning_text_parts.append(data)
                    yield _sse({"type": "reasoning_token", "token": data})
                elif event_type == "error":
                    had_error = True
                    yield _sse({"type": "error", "error": data})
                else:
                    if event_type == "evaluation":
                        yield _sse({"type": "evaluation", "evaluation": data})
                    else:
                        yield _sse({"type": event_type, **data})
            if not had_error:
                _update_run(conn, run_id, status="completed", reasoning_text="".join(reasoning_text_parts), finished_at=datetime.now())
                yield _sse({"type": "done", "run_id": run_id})
        except Exception as exc:
            if run_id:
                _update_run(conn, run_id, status="failed", error_message=str(exc), finished_at=datetime.now())
            print(f"[pricing-task] SSE error: {exc}", file=sys.stderr, flush=True)
            yield _sse({"type": "error", "error": str(exc)})
        finally:
            conn.close()

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/pricing-task-runs/{run_id}/confirm")
def confirm_pricing_task_run(run_id: int, body: ConfirmRunRequest):
    from db.connection import get_connection

    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM pricing_task_runs WHERE id=%s", (run_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="run not found")
            if body.results is not None:
                cur.execute("DELETE FROM pricing_task_results WHERE run_id=%s", (run_id,))
                cur.execute(
                    "SELECT task_id, boq_item_id, boq_project_id FROM pricing_task_runs WHERE id=%s",
                    (run_id,),
                )
                task_id, boq_item_id, project_id = cur.fetchone()
                for m in body.results:
                    cur.execute(
                        """
                        SELECT zmbh, zmmc FROM tdek_tdezm WHERE dekid=%s AND id=%s
                        """,
                        (m["dekid"], m["dezmid"]),
                    )
                    qrow = cur.fetchone()
                    if not qrow:
                        raise HTTPException(status_code=400, detail="quota item not found")
                    cur.execute(
                        """
                        INSERT INTO pricing_task_results(
                            task_id, run_id, boq_item_id, boq_project_id, dekid, dezmid,
                            subitem_code, subitem_name, qty_factor, confidence, match_reason, ai_reasoning, status
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'confirmed')
                        """,
                        (
                            task_id,
                            run_id,
                            boq_item_id,
                            project_id,
                            m["dekid"],
                            m["dezmid"],
                            qrow[0],
                            qrow[1],
                            m.get("qty_factor", 1),
                            m.get("confidence", "medium"),
                            m.get("match_reason", ""),
                            m.get("match_reason", ""),
                        ),
                    )
            else:
                cur.execute("UPDATE pricing_task_results SET status='confirmed', updated_at=NOW() WHERE run_id=%s", (run_id,))
            cur.execute("UPDATE pricing_task_runs SET status='confirmed', finished_at=COALESCE(finished_at, NOW()) WHERE id=%s", (run_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/pricing-task-runs/{run_id}/reject")
def reject_pricing_task_run(run_id: int):
    from db.connection import get_connection

    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("UPDATE pricing_task_results SET status='rejected', updated_at=NOW() WHERE run_id=%s", (run_id,))
            cur.execute("UPDATE pricing_task_runs SET status='rejected', finished_at=COALESCE(finished_at, NOW()) WHERE id=%s", (run_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="run not found")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/pricing-task/match-item-stream")
def pricing_task_match_item_stream(req: dict[str, Any]):
    """Compatibility endpoint used by older frontend code."""
    from db.connection import get_connection

    def generate():
        conn = get_connection()
        run_id = None
        try:
            _ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, item_code, item_name, item_description, unit, quantity, project_id FROM boq_items WHERE id = %s",
                    (req.get("boq_item_id"),),
                )
                row = cur.fetchone()
            if not row:
                yield _sse({"type": "error", "error": "Item not found"})
                return
            boq_item = {
                "id": row[0],
                "item_code": row[1],
                "item_name": row[2],
                "item_description": row[3],
                "unit": row[4],
                "quantity": float(row[5]) if row[5] is not None else None,
                "project_id": row[6],
            }
            run_id = _create_run(conn, None, boq_item)
            yield _sse({"type": "run_started", "run_id": run_id})
            yield _sse({"type": "item_info", "item": boq_item})
            reasoning_text_parts: list[str] = []
            for event_type, data in _stream_pricing_item(conn, boq_item, req.get("quota_library_ids") or [], req.get("manual_project_id"), None, run_id):
                if event_type == "reasoning_token":
                    reasoning_text_parts.append(data)
                    yield _sse({"type": "reasoning_token", "token": data})
                else:
                    if event_type == "evaluation":
                        yield _sse({"type": "evaluation", "evaluation": data})
                    else:
                        yield _sse({"type": event_type, **data})
            _update_run(conn, run_id, status="completed", reasoning_text="".join(reasoning_text_parts), finished_at=datetime.now())
            yield _sse({"type": "done", "run_id": run_id})
        except Exception as exc:
            if run_id:
                _update_run(conn, run_id, status="failed", error_message=str(exc), finished_at=datetime.now())
            yield _sse({"type": "error", "error": str(exc)})
        finally:
            conn.close()

    return StreamingResponse(generate(), media_type="text/event-stream")
