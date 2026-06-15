"""单条组价路由.

当前阶段完成“套定额闭环”：任务入库、单条运行入库、AI 结果候选校验、
人工确认/拒绝、人工对比工程评测。不在本阶段计算综合单价。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from time import perf_counter
from typing import Any, Iterable, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field
from psycopg2.extras import Json

router = APIRouter()


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _parse_json_content(content: str | None) -> dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("JSON result must be an object")
    return parsed


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
                conversion_check    JSONB,
                step_timings        JSONB,
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
        cur.execute("ALTER TABLE pricing_task_results ADD COLUMN IF NOT EXISTS conversion_confirmed BOOLEAN NOT NULL DEFAULT FALSE")
        cur.execute("ALTER TABLE pricing_task_results ADD COLUMN IF NOT EXISTS conversion_note TEXT")
        cur.execute("ALTER TABLE pricing_task_results ADD COLUMN IF NOT EXISTS conversion_confirmed_at TIMESTAMP")
        cur.execute("ALTER TABLE pricing_task_results ADD COLUMN IF NOT EXISTS conversion_resources JSONB")
        cur.execute("ALTER TABLE pricing_task_results ADD COLUMN IF NOT EXISTS conversion_resource_changes JSONB")
        cur.execute("ALTER TABLE pricing_task_runs ADD COLUMN IF NOT EXISTS conversion_check JSONB")
        cur.execute("ALTER TABLE pricing_task_runs ADD COLUMN IF NOT EXISTS step_timings JSONB")
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


class ConversionConfirmRequest(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


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


_TOOL_SUBMIT_CONVERSION_CHECK = {
    "type": "function",
    "function": {
        "name": "submit_conversion_check",
        "description": "提交确认定额的换算判断建议。只给建议，不修改已确认定额和工程量系数。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dekid": {"type": "integer"},
                            "dezmid": {"type": "integer"},
                            "quota_code": {"type": "string"},
                            "quota_name": {"type": "string"},
                            "needs_conversion": {"type": "boolean"},
                            "suggested_qty_factor": {"type": "number"},
                            "reason": {"type": "string"},
                            "difference_points": {"type": "array", "items": {"type": "string"}},
                            "conversion_category": {
                                "type": "string",
                                "enum": ["material", "process", "measurement", "none", "unknown"],
                            },
                            "conversion_type": {
                                "type": "string",
                                "enum": ["强度换算", "厚度换算", "配合比换算", "材料种类换算", "定额子目借用", "部位调整", "系数调整", "单位换算", "none", "unknown"],
                            },
                            "basis": {"type": "string"},
                            "suggested_action": {"type": "string"},
                            "requires_manual_review": {"type": "boolean"},
                            "matched_rules": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "prompt": {"type": "string"},
                                        "description": {"type": "string"},
                                        "group_no": {"type": "integer"},
                                    },
                                    "required": ["prompt", "description", "group_no"],
                                    "additionalProperties": False,
                                },
                            },
                            "resource_adjustments": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "action": {
                                            "type": "string",
                                            "enum": ["replace", "update_quantity", "add", "remove"],
                                        },
                                        "source_code": {"type": "string"},
                                        "source_name": {"type": "string"},
                                        "target_code": {"type": "string"},
                                        "target_name": {"type": "string"},
                                        "target_unit": {"type": "string"},
                                        "resource_type": {"type": "integer"},
                                        "original_quantity": {"type": "number"},
                                        "suggested_quantity": {"type": "number"},
                                        "reason": {"type": "string"},
                                        "requires_manual_review": {"type": "boolean"},
                                    },
                                    "required": [
                                        "action",
                                        "source_code",
                                        "source_name",
                                        "target_code",
                                        "target_name",
                                        "target_unit",
                                        "resource_type",
                                        "original_quantity",
                                        "suggested_quantity",
                                        "reason",
                                        "requires_manual_review",
                                    ],
                                    "additionalProperties": False,
                                },
                            },
                            "missing_inputs": {"type": "array", "items": {"type": "string"}},
                            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        },
                        "required": [
                            "dekid",
                            "dezmid",
                            "quota_code",
                            "quota_name",
                            "needs_conversion",
                            "suggested_qty_factor",
                            "reason",
                            "difference_points",
                            "conversion_category",
                            "conversion_type",
                            "basis",
                            "suggested_action",
                            "requires_manual_review",
                            "matched_rules",
                            "resource_adjustments",
                            "missing_inputs",
                            "confidence",
                        ],
                        "additionalProperties": False,
                    },
                },
                "issues": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["items", "issues"],
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


CONVERSION_RULE_GUIDE = """
第七步定额换算通用规则：
1. 强度换算（material）：设计强度 vs 定额默认强度，例如 C25 混凝土 → C30 混凝土。
2. 厚度换算（material）：设计厚度 vs 定额默认厚度，例如 12mm → 15mm。
3. 配合比换算（material）：设计砂浆/混凝土配合比 vs 定额默认配合比，例如 1:2 → 1:3。
4. 材料种类换算（material）：设计材料 vs 定额默认材料，例如普通水泥 → 白水泥。
5. 定额子目借用（process）：无更适用专用子目时，借用相似工艺子目。
6. 部位调整（process）：设计部位 vs 定额部位不一致，例如外墙不能直接套内墙子目。
7. 系数调整（process）：按定额说明或规范，对人工/材料/机械乘系数，例如高空、洞内、洞库等。
8. 单位换算（measurement）：清单单位 vs 定额单位不一致，例如 m3、m2、t、kg、10m 与 m。

判定要求：
- 逐条对比项目特征、定额工作内容、工料机显示，列出差异点。
- 定额库换算说明（tdek_tznhs/tdek_tzhhs）优先级最高，命中时必须写入 matched_rules 和 basis。
- 没有定额库换算说明时，不允许编造依据；如仍认为存在差异，只能给换算建议并标记 requires_manual_review=true。
- 第七步只输出建议，不修改已确认定额、工程量系数或工料机。
""".strip()


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


def _run_submit_conversion_check(messages: list[dict[str, Any]]) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            resp = _client(thinking=False).chat.completions.create(
                model=_model(),
                messages=messages,
                tools=[_TOOL_SUBMIT_CONVERSION_CHECK],
                tool_choice={"type": "function", "function": {"name": "submit_conversion_check"}},
                extra_body={"thinking": {"type": "disabled"}},
                max_tokens=8000,
                stream=False,
            )
            msg = resp.choices[0].message
            if not msg.tool_calls:
                raise ValueError(f"AI did not call submit_conversion_check: {msg.content!r}")
            call = msg.tool_calls[0]
            if call.function.name != "submit_conversion_check":
                raise ValueError(f"unexpected tool call {call.function.name!r}")
            return json.loads(call.function.arguments)
        except Exception as exc:
            last_error = exc
            print(f"[pricing-task] submit conversion check error attempt={attempt + 1}: {exc}", file=sys.stderr, flush=True)
    try:
        json_messages = [
            *messages,
            {
                "role": "user",
                "content": (
                    "工具参数生成失败。请改用 JSON Output，仅输出一个合法 JSON 对象，不要使用 Markdown。"
                    "JSON 顶层必须包含 items 和 issues，字段结构与 submit_conversion_check 完全一致。"
                ),
            },
        ]
        resp = _client(thinking=False).chat.completions.create(
            model=_model(),
            messages=json_messages,
            response_format={"type": "json_object"},
            extra_body={"thinking": {"type": "disabled"}},
            max_tokens=8000,
            stream=False,
        )
        return _parse_json_content(resp.choices[0].message.content)
    except Exception as exc:
        print(f"[pricing-task] conversion JSON fallback error: {exc}", file=sys.stderr, flush=True)
        raise exc from last_error


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


def _confirmed_conversion_context(conn, run_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.id, r.status, i.item_code, i.item_name, i.item_description, i.unit
            FROM pricing_task_runs r
            JOIN boq_items i ON i.id = r.boq_item_id
            WHERE r.id = %s
            """,
            (run_id,),
        )
        run_row = cur.fetchone()
        if not run_row:
            raise HTTPException(status_code=404, detail="run not found")
        if run_row[1] != "confirmed":
            raise HTTPException(status_code=400, detail="run must be confirmed before conversion check")
        boq_item = {
            "run_id": run_row[0],
            "status": run_row[1],
            "item_code": run_row[2],
            "item_name": run_row[3],
            "item_description": run_row[4] or "",
            "unit": run_row[5] or "",
        }
        cur.execute(
            """
            SELECT r.dekid, r.dezmid, r.subitem_code, r.subitem_name, r.qty_factor,
                   r.confidence, r.match_reason, q.dw, q.gznr, l.mc
            FROM pricing_task_results r
            LEFT JOIN tdek_tdezm q ON q.dekid = r.dekid AND q.id = r.dezmid
            LEFT JOIN tlibs l ON l.id = r.dekid
            WHERE r.run_id = %s AND r.status = 'confirmed'
            ORDER BY r.id
            """,
            (run_id,),
        )
        result_rows = cur.fetchall()
        items: list[dict[str, Any]] = []
        for row in result_rows:
            dekid = int(row[0])
            dezmid = int(row[1])
            cur.execute(
                """
                SELECT tsxx, hssm, COALESCE(groupno, 0)
                FROM tdek_tznhs
                WHERE dekid=%s AND dezmid=%s
                ORDER BY groupno NULLS LAST, source_rowid
                """,
                (dekid, dezmid),
            )
            conversion_rules = [
                {"prompt": r[0] or "", "description": r[1] or "", "group_no": int(r[2] or 0)}
                for r in cur.fetchall()
            ]
            cur.execute(
                """
                SELECT tsxx
                FROM tdek_tzhhs
                WHERE dekid=%s AND dezmid=%s
                ORDER BY source_rowid
                """,
                (dekid, dezmid),
            )
            input_prompts = [r[0] for r in cur.fetchall() if r[0]]
            cur.execute(
                """
                SELECT zmbh, zmmc, dw, gcl, lx
                FROM tdek_tzmgc
                WHERE dekid=%s AND dezmid=%s
                ORDER BY lx NULLS LAST, source_rowid
                """,
                (dekid, dezmid),
            )
            resources = [
                {
                    "code": r[0] or "",
                    "name": r[1] or "",
                    "unit": r[2] or "",
                    "quantity": float(r[3]) if r[3] is not None else None,
                    "type": int(r[4]) if r[4] is not None else None,
                }
                for r in cur.fetchall()
            ]
            items.append(
                {
                    "dekid": dekid,
                    "dezmid": dezmid,
                    "quota_code": row[2] or "",
                    "quota_name": row[3] or "",
                    "current_qty_factor": float(row[4]) if row[4] is not None else 1.0,
                    "confidence": row[5] or "",
                    "match_reason": row[6] or "",
                    "unit": row[7] or "",
                    "work_content": row[8] or "",
                    "library_name": row[9] or "",
                    "resources": resources,
                    "conversion_rules": conversion_rules,
                    "input_prompts": input_prompts,
                }
            )
    return boq_item, items


def _default_conversion_check(items: list[dict[str, Any]], issue: str | None = None) -> dict[str, Any]:
    return {
        "items": [
            {
                "dekid": item["dekid"],
                "dezmid": item["dezmid"],
                "quota_code": item["quota_code"],
                "quota_name": item["quota_name"],
                "needs_conversion": False,
                "suggested_qty_factor": item.get("current_qty_factor") or 1.0,
                "reason": "未查询到换算说明，默认不建议换算。",
                "difference_points": [],
                "conversion_category": "none",
                "conversion_type": "none",
                "basis": "未查询到定额库换算说明。",
                "suggested_action": "不自动换算，必要时人工复核。",
                "requires_manual_review": bool(item.get("resources")),
                "matched_rules": [],
                "resource_adjustments": [],
                "resources": item.get("resources", []),
                "conversion_rules": item.get("conversion_rules", []),
                "input_prompts": item.get("input_prompts", []),
                "missing_inputs": [],
                "confidence": "medium",
            }
            for item in items
        ],
        "issues": [issue] if issue else [],
    }


def _normalize_conversion_check(raw: dict[str, Any], confirmed_items: list[dict[str, Any]]) -> dict[str, Any]:
    by_key = {(item["dekid"], item["dezmid"]): item for item in confirmed_items}
    raw_by_key = {}
    for item in raw.get("items", []):
        try:
            raw_by_key[(int(item.get("dekid")), int(item.get("dezmid")))] = item
        except Exception:
            continue
    normalized = []
    for key, confirmed in by_key.items():
        item = raw_by_key.get(key)
        if not item:
            normalized.extend(_default_conversion_check([confirmed])["items"])
            continue
        matched_rules = [
            {
                "prompt": str(rule.get("prompt") or ""),
                "description": str(rule.get("description") or ""),
                "group_no": int(rule.get("group_no") or 0),
            }
            for rule in item.get("matched_rules", [])
        ]
        confidence = item.get("confidence") if item.get("confidence") in {"high", "medium", "low"} else "low"
        try:
            suggested_qty_factor = float(item.get("suggested_qty_factor", confirmed.get("current_qty_factor") or 1.0) or 1.0)
        except Exception:
            suggested_qty_factor = confirmed.get("current_qty_factor") or 1.0
        category = item.get("conversion_category")
        if category not in {"material", "process", "measurement", "none", "unknown"}:
            category = "unknown"
        conversion_type = str(item.get("conversion_type") or "unknown")
        allowed_types = {"强度换算", "厚度换算", "配合比换算", "材料种类换算", "定额子目借用", "部位调整", "系数调整", "单位换算", "none", "unknown"}
        if conversion_type not in allowed_types:
            conversion_type = "unknown"
        has_matched_rules = bool(matched_rules)
        resource_by_code = {
            str(resource.get("code") or ""): resource
            for resource in confirmed.get("resources", [])
            if resource.get("code")
        }
        resource_adjustments = []
        for adjustment in item.get("resource_adjustments", []):
            if not isinstance(adjustment, dict):
                continue
            action = str(adjustment.get("action") or "")
            if action not in {"replace", "update_quantity", "add", "remove"}:
                continue
            source_code = str(adjustment.get("source_code") or "")
            source = resource_by_code.get(source_code)
            if action != "add" and not source:
                continue
            try:
                original_quantity = float(
                    adjustment.get(
                        "original_quantity",
                        source.get("quantity") if source else 0,
                    )
                    or 0
                )
                suggested_quantity = float(adjustment.get("suggested_quantity", original_quantity) or 0)
                resource_type = int(
                    adjustment.get(
                        "resource_type",
                        source.get("type") if source else 2,
                    )
                    or 2
                )
            except Exception:
                continue
            resource_adjustments.append(
                {
                    "action": action,
                    "source_code": source_code,
                    "source_name": str(adjustment.get("source_name") or (source.get("name") if source else "")),
                    "target_code": str(adjustment.get("target_code") or ""),
                    "target_name": str(adjustment.get("target_name") or ""),
                    "target_unit": str(adjustment.get("target_unit") or (source.get("unit") if source else "")),
                    "resource_type": resource_type,
                    "original_quantity": original_quantity,
                    "suggested_quantity": suggested_quantity,
                    "reason": str(adjustment.get("reason") or ""),
                    "requires_manual_review": bool(adjustment.get("requires_manual_review", True)),
                }
            )
        normalized.append(
            {
                "dekid": confirmed["dekid"],
                "dezmid": confirmed["dezmid"],
                "quota_code": confirmed["quota_code"],
                "quota_name": confirmed["quota_name"],
                "needs_conversion": bool(item.get("needs_conversion")),
                "suggested_qty_factor": suggested_qty_factor,
                "reason": str(item.get("reason") or ""),
                "difference_points": [str(v) for v in item.get("difference_points", []) if v],
                "conversion_category": category,
                "conversion_type": conversion_type,
                "basis": str(item.get("basis") or ("命中定额库换算说明。" if has_matched_rules else "未查询到定额库换算说明。")),
                "suggested_action": str(item.get("suggested_action") or ""),
                "requires_manual_review": bool(item.get("requires_manual_review") or (item.get("needs_conversion") and not has_matched_rules)),
                "matched_rules": matched_rules,
                "resource_adjustments": resource_adjustments,
                "resources": [
                    {
                        "code": str(resource.get("code") or ""),
                        "name": str(resource.get("name") or ""),
                        "unit": str(resource.get("unit") or ""),
                        "quantity": resource.get("quantity"),
                        "type": resource.get("type"),
                    }
                    for resource in confirmed.get("resources", [])
                ],
                "conversion_rules": [
                    {
                        "prompt": str(rule.get("prompt") or ""),
                        "description": str(rule.get("description") or ""),
                        "group_no": int(rule.get("group_no") or 0),
                    }
                    for rule in confirmed.get("conversion_rules", [])
                ],
                "input_prompts": [str(v) for v in confirmed.get("input_prompts", []) if v],
                "missing_inputs": [str(v) for v in item.get("missing_inputs", []) if v],
                "confidence": confidence,
            }
        )
    return {"items": normalized, "issues": [str(v) for v in raw.get("issues", []) if v]}


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
            "code_check",
            "feature_check",
            "work_procedures",
            "quota_candidates",
            "quota_match",
            "evaluation",
            "conversion_check",
            "step_timings",
        } else value)
    values.append(run_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE pricing_task_runs SET {', '.join(assignments)} WHERE id = %s", values)
    conn.commit()


def _load_step_timings(conn, run_id: int) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT step_timings FROM pricing_task_runs WHERE id=%s", (run_id,))
        row = cur.fetchone()
    return dict(row[0] or {}) if row else {}


def _finish_step_timing(
    conn,
    run_id: int,
    timings: dict[str, Any],
    step_no: int,
    name: str,
    started_at: datetime,
    started_perf: float,
) -> dict[str, Any]:
    finished_at = datetime.now()
    timing = {
        "step_no": step_no,
        "name": name,
        "duration_ms": int(round((perf_counter() - started_perf) * 1000)),
        "started_at": started_at.isoformat(timespec="milliseconds"),
        "finished_at": finished_at.isoformat(timespec="milliseconds"),
    }
    timings[str(step_no)] = timing
    _update_run(conn, run_id, step_timings=timings)
    return timing


def _load_confirmed_results(conn, run_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not run_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, dekid, dezmid, subitem_code, subitem_name, qty_factor, status,
                   conversion_confirmed, conversion_note, conversion_confirmed_at,
                   conversion_resources, conversion_resource_changes
            FROM pricing_task_results
            WHERE run_id = ANY(%s::int[]) AND status = 'confirmed'
            ORDER BY id
            """,
            (run_ids,),
        )
        rows = cur.fetchall()
    by_run: dict[int, list[dict[str, Any]]] = {run_id: [] for run_id in run_ids}
    for row in rows:
        by_run.setdefault(int(row[0]), []).append(
            {
                "dekid": int(row[1]),
                "dezmid": int(row[2]),
                "subitem_code": row[3] or "",
                "subitem_name": row[4] or "",
                "qty_factor": float(row[5]) if row[5] is not None else 1.0,
                "status": row[6],
                "conversion_confirmed": bool(row[7]),
                "conversion_note": row[8] or "",
                "conversion_confirmed_at": row[9],
                "conversion_resources": row[10] or [],
                "conversion_resource_changes": row[11] or [],
            }
        )
    return by_run


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
    step_timings: dict[str, Any] = {}

    step_started_at = datetime.now()
    step_started_perf = perf_counter()
    code_check = exec_check_item_code(conn, boq_item["item_code"], boq_item["item_name"])
    yield ("code_check", code_check)
    yield ("judgment", {"is_consistent": code_check["is_consistent"], "reasoning": f"标准清单名称：{code_check['standard_name'] or '未找到'}"})
    _update_run(conn, run_id, code_check=code_check)
    yield ("step_timing", _finish_step_timing(conn, run_id, step_timings, 1, "编码核查", step_started_at, step_started_perf))

    step_started_at = datetime.now()
    step_started_perf = perf_counter()
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
    yield ("step_timing", _finish_step_timing(conn, run_id, step_timings, 2, "项目特征", step_started_at, step_started_perf))

    step_started_at = datetime.now()
    step_started_perf = perf_counter()
    procedures_result = exec_fetch_standard_work_procedure(conn, boq_item["item_code"])
    yield ("work_procedures", procedures_result)
    _update_run(conn, run_id, work_procedures=procedures_result)
    yield ("step_timing", _finish_step_timing(conn, run_id, step_timings, 3, "标准工序", step_started_at, step_started_perf))

    step_started_at = datetime.now()
    step_started_perf = perf_counter()
    candidates_data = exec_fetch_quota_candidates(conn, boq_item["item_code"], quota_library_ids)
    yield ("quota_candidates", candidates_data)
    _update_run(conn, run_id, quota_candidates=candidates_data)
    yield ("step_timing", _finish_step_timing(conn, run_id, step_timings, 4, "定额候选", step_started_at, step_started_perf))

    step_started_at = datetime.now()
    step_started_perf = perf_counter()
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
                f"套定额原则：用清单项目特征信息+标准施工工序和候选定额名称+工作内容进行匹配分析和判断。\n\n"
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
    _update_run(conn, run_id, quota_match=match_result)
    yield ("quota_match", match_result)
    yield ("step_timing", _finish_step_timing(conn, run_id, step_timings, 5, "套定额结果", step_started_at, step_started_perf))

    step_started_at = datetime.now()
    step_started_perf = perf_counter()
    manual = _manual_quotas(conn, manual_project_id, boq_item.get("item_code"))
    evaluation = _evaluate(match_result["matches"], manual)
    _update_run(conn, run_id, evaluation=evaluation)
    _save_pending_results(conn, task_id, run_id, boq_item, match_result, evaluation)
    yield ("evaluation", evaluation)
    yield ("step_timing", _finish_step_timing(conn, run_id, step_timings, 6, "人工对比", step_started_at, step_started_perf))


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
                       quota_match, evaluation, conversion_check, step_timings, error_message, created_at, finished_at, reasoning_text
                FROM pricing_task_runs
                WHERE task_id=%s AND boq_item_id=%s
                ORDER BY created_at DESC
                """,
                (task_id, boq_item_id),
            )
            rows = cur.fetchall()
        confirmed_results = _load_confirmed_results(conn, [int(r[0]) for r in rows])
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
                "conversion_check": r[8],
                "step_timings": r[9],
                "error_message": r[10],
                "created_at": r[11],
                "finished_at": r[12],
                "reasoning_text": r[13],
                "confirmed_results": confirmed_results.get(int(r[0]), []),
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
                       quota_candidates, quota_match, evaluation, conversion_check, step_timings, error_message, created_at, finished_at,
                       reasoning_text
                FROM pricing_task_runs
                WHERE task_id=%s
                ORDER BY boq_item_id, created_at DESC, id DESC
                """,
                (task_id,),
            )
            rows = cur.fetchall()
        confirmed_results = _load_confirmed_results(conn, [int(r[1]) for r in rows])
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
                    "conversion_check": r[9],
                    "step_timings": r[10],
                    "error_message": r[11],
                    "created_at": r[12],
                    "finished_at": r[13],
                    "reasoning_text": r[14],
                    "confirmed_results": confirmed_results.get(int(r[1]), []),
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


@router.post("/pricing-task-runs/{run_id}/conversion-check-stream")
def pricing_task_conversion_check_stream(run_id: int):
    from db.connection import get_connection

    def generate():
        conn = get_connection()
        try:
            _ensure_schema(conn)
            step_timings = _load_step_timings(conn, run_id)
            step_started_at = datetime.now()
            step_started_perf = perf_counter()
            boq_item, confirmed_items = _confirmed_conversion_context(conn, run_id)
            yield _sse({"type": "conversion_check_start", "run_id": run_id, "total": len(confirmed_items)})

            if not confirmed_items:
                result = {"items": [], "issues": ["未找到已确认定额，无法进行换算判断。"]}
                _update_run(conn, run_id, conversion_check=result)
                yield _sse({"type": "conversion_check", "conversion_check": result})
                yield _sse({"type": "step_timing", **_finish_step_timing(conn, run_id, step_timings, 7, "换算判断", step_started_at, step_started_perf)})
                yield _sse({"type": "done", "run_id": run_id})
                return

            input_payload = {
                "boq_item": boq_item,
                "confirmed_quotas": confirmed_items,
                "conversion_rule_guide": CONVERSION_RULE_GUIDE,
            }
            context_text = _json_dumps(input_payload)
            system_prompt = build_system_prompt()
            analysis_prompt = (
                "请对已人工确认的定额进行第七轮换算判断。先进行分析，不要调用工具，不要输出 JSON。\n"
                "只允许根据项目特征、已确认定额、定额工作内容、工料机显示、定额库换算说明、实际值提示和通用换算规则判断是否建议换算。\n"
                "请逐条识别差异点，并按强度换算、厚度换算、配合比换算、材料种类换算、定额子目借用、部位调整、系数调整、单位换算进行分类。\n"
                "第七轮结果只作为换算建议，不允许修改已确认定额，也不要改写工程量系数。\n"
                "定额库换算说明优先级最高；未查询到定额库换算说明时，不允许编造依据，如仍建议换算必须明确需要人工复核。\n\n"
                f"【输入数据】\n{context_text}"
            )
            conversion_analysis = ""
            for event_type, data in _stream_text_completion(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": analysis_prompt},
                ],
                6000,
            ):
                if event_type == "reasoning_token":
                    yield _sse({"type": "reasoning_token", "token": data})
                elif event_type == "text_result":
                    conversion_analysis = data

            submit_prompt = (
                "请严格调用 submit_conversion_check 提交第七轮结构化换算建议。\n"
                "必须覆盖每一条已确认定额。\n"
                "difference_points 填写项目特征与定额工作内容/工料机显示的差异点；无差异填空数组。\n"
                "conversion_category 只能是 material、process、measurement、none、unknown。\n"
                "conversion_type 只能是强度换算、厚度换算、配合比换算、材料种类换算、定额子目借用、部位调整、系数调整、单位换算、none、unknown。\n"
                "resource_adjustments 用于提交具体工料机调整建议。发现材料名称、牌号、强度、规格、直径、厚度或配合比与项目特征不一致时，不能只写人工复核，必须填写对应调整项。\n"
                "replace 表示替换现有工料机；source_code/source_name 必须来自输入的 resources；target_name 必须按项目特征写出目标材料完整名称。库中无法确定目标编码时 target_code 填空字符串。\n"
                "目标材料名称必须忠实保留项目特征中的牌号、规格和直径原文，不得自行把 HRB300 改成 HRB400E、HPB300 或其他牌号。若项目特征疑似矛盾，应在 reason/issues 中提示，但 resource_adjustments.target_name 仍按项目特征原文生成。\n"
                "update_quantity 表示仅调整含量；add/remove 表示新增或删除工料机。未涉及工料机调整时 resource_adjustments 填空数组。\n"
                "original_quantity 使用原工料机含量；没有明确依据改变含量时 suggested_quantity 保持原值，并标记 requires_manual_review=true。\n"
                "basis 必须写明依据。命中定额库换算说明时引用说明；没有定额库依据时写明“未查询到定额库换算说明”。\n"
                "suggested_action 写清建议处理动作。requires_manual_review 表示是否需要人工复核。\n"
                "matched_rules 只能填写命中的换算说明；没有命中时填写空数组。\n"
                "没有定额库换算说明时，不允许伪造依据；如 needs_conversion=true，则 requires_manual_review 必须为 true。\n"
                "suggested_qty_factor 只是建议值，不代表写回，也不要修改已确认结果。\n"
                "confidence 只能是 high、medium、low。\n\n"
                f"【第七轮分析】\n{conversion_analysis or '（无分析文本）'}\n\n"
                f"【输入数据】\n{context_text}"
            )
            raw_result = _run_submit_conversion_check(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": submit_prompt},
                ]
            )
            result = _normalize_conversion_check(raw_result, confirmed_items)
            _update_run(conn, run_id, conversion_check=result)
            yield _sse({"type": "conversion_check", "conversion_check": result})
            yield _sse({"type": "step_timing", **_finish_step_timing(conn, run_id, step_timings, 7, "换算判断", step_started_at, step_started_perf)})
            yield _sse({"type": "done", "run_id": run_id})
        except HTTPException as exc:
            yield _sse({"type": "error", "error": str(exc.detail)})
        except Exception as exc:
            print(f"[pricing-task] conversion check SSE error: {exc}", file=sys.stderr, flush=True)
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


@router.post("/pricing-task-runs/{run_id}/conversion-confirm")
def confirm_pricing_task_conversion(run_id: int, body: ConversionConfirmRequest):
    from db.connection import get_connection

    if not body.items:
        raise HTTPException(status_code=400, detail="conversion items required")

    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM pricing_task_runs WHERE id=%s", (run_id,))
            run_row = cur.fetchone()
            if not run_row:
                raise HTTPException(status_code=404, detail="run not found")
            if run_row[0] != "confirmed":
                raise HTTPException(status_code=400, detail="run must be confirmed before conversion writeback")

            for item in body.items:
                try:
                    dekid = int(item.get("dekid"))
                    dezmid = int(item.get("dezmid"))
                except Exception as exc:
                    raise HTTPException(status_code=400, detail="invalid dekid/dezmid") from exc
                try:
                    qty_factor = float(item.get("confirmed_qty_factor", item.get("qty_factor", 1)) or 1)
                except Exception as exc:
                    raise HTTPException(status_code=400, detail="invalid confirmed_qty_factor") from exc
                if qty_factor <= 0:
                    raise HTTPException(status_code=400, detail="confirmed_qty_factor must be positive")

                resources = item.get("conversion_resources", item.get("resources", []))
                resource_changes = item.get("conversion_resource_changes", item.get("resource_changes", []))
                if not isinstance(resources, list):
                    raise HTTPException(status_code=400, detail="conversion_resources must be array")
                if not isinstance(resource_changes, list):
                    raise HTTPException(status_code=400, detail="conversion_resource_changes must be array")

                cur.execute(
                    """
                    UPDATE pricing_task_results
                    SET qty_factor=%s,
                        conversion_confirmed=TRUE,
                        conversion_note=%s,
                        conversion_confirmed_at=NOW(),
                        conversion_resources=%s,
                        conversion_resource_changes=%s,
                        updated_at=NOW()
                    WHERE run_id=%s AND dekid=%s AND dezmid=%s AND status='confirmed'
                    """,
                    (
                        qty_factor,
                        item.get("conversion_note", "") or "",
                        Json(resources, dumps=_json_dumps),
                        Json(resource_changes, dumps=_json_dumps),
                        run_id,
                        dekid,
                        dezmid,
                    ),
                )
                if cur.rowcount == 0:
                    raise HTTPException(status_code=400, detail=f"confirmed quota not found: {dekid}/{dezmid}")
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
