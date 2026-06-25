"""单条组价路由.

当前阶段完成“套定额闭环”：任务入库、单条运行入库、AI 结果候选校验、
人工确认/拒绝、人工对比工程评测。不在本阶段计算综合单价。
"""

from __future__ import annotations

import json
import os
import re
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
    parsed = _parse_json_object(text)
    if not isinstance(parsed, dict):
        raise ValueError("JSON result must be an object")
    return parsed


def _parse_json_object(text: str | None) -> dict[str, Any]:
    value = (text or "").strip()
    if not value:
        raise ValueError("empty JSON content")
    decoder = json.JSONDecoder()
    parsed, _ = decoder.raw_decode(value)
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
                accuracy_report     JSONB,
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
                coefficient_check   JSONB,
                accuracy_report     JSONB,
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
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pricing_task_batches (
                id                  SERIAL PRIMARY KEY,
                name                TEXT NOT NULL,
                boq_project_id      INTEGER NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE,
                quota_library_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
                manual_project_id   INTEGER REFERENCES manual_boq_projects(id) ON DELETE SET NULL,
                status              VARCHAR(16) NOT NULL DEFAULT 'active',
                selected_count      INTEGER NOT NULL DEFAULT 0,
                completed_count     INTEGER NOT NULL DEFAULT 0,
                failed_count        INTEGER NOT NULL DEFAULT 0,
                started_at          TIMESTAMP,
                finished_at         TIMESTAMP,
                created_at          TIMESTAMP DEFAULT NOW(),
                updated_at          TIMESTAMP DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pricing_task_batch_item_runs (
                id                  SERIAL PRIMARY KEY,
                batch_id            INTEGER NOT NULL REFERENCES pricing_task_batches(id) ON DELETE CASCADE,
                boq_item_id         INTEGER NOT NULL REFERENCES boq_items(id) ON DELETE CASCADE,
                boq_project_id      INTEGER NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE,
                status              VARCHAR(16) NOT NULL DEFAULT 'idle',
                reasoning_text      TEXT,
                code_check          JSONB,
                feature_check       JSONB,
                work_procedures     JSONB,
                quota_candidates    JSONB,
                quota_match         JSONB,
                evaluation          JSONB,
                confirmed_results   JSONB,
                conversion_check    JSONB,
                coefficient_check   JSONB,
                step_timings        JSONB,
                error_message       TEXT,
                created_at          TIMESTAMP DEFAULT NOW(),
                started_at          TIMESTAMP,
                finished_at         TIMESTAMP,
                UNIQUE(batch_id, boq_item_id)
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
        cur.execute("ALTER TABLE pricing_tasks ADD COLUMN IF NOT EXISTS accuracy_report JSONB")
        cur.execute("ALTER TABLE pricing_task_runs ADD COLUMN IF NOT EXISTS conversion_check JSONB")
        cur.execute("ALTER TABLE pricing_task_runs ADD COLUMN IF NOT EXISTS coefficient_check JSONB")
        cur.execute("ALTER TABLE pricing_task_runs ADD COLUMN IF NOT EXISTS accuracy_report JSONB")
        cur.execute("ALTER TABLE pricing_task_runs ADD COLUMN IF NOT EXISTS step_timings JSONB")
        cur.execute("ALTER TABLE pricing_task_batches ADD COLUMN IF NOT EXISTS selected_count INTEGER NOT NULL DEFAULT 0")
        cur.execute("ALTER TABLE pricing_task_batches ADD COLUMN IF NOT EXISTS completed_count INTEGER NOT NULL DEFAULT 0")
        cur.execute("ALTER TABLE pricing_task_batches ADD COLUMN IF NOT EXISTS failed_count INTEGER NOT NULL DEFAULT 0")
        cur.execute("ALTER TABLE pricing_task_batches ADD COLUMN IF NOT EXISTS started_at TIMESTAMP")
        cur.execute("ALTER TABLE pricing_task_batches ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP")
        cur.execute("ALTER TABLE pricing_task_batch_item_runs ADD COLUMN IF NOT EXISTS confirmed_results JSONB")
        cur.execute("ALTER TABLE pricing_task_batch_item_runs ADD COLUMN IF NOT EXISTS coefficient_check JSONB")
        cur.execute("ALTER TABLE pricing_task_batch_item_runs ADD COLUMN IF NOT EXISTS step_timings JSONB")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pricing_tasks_project ON pricing_tasks(boq_project_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ptr_boq_item ON pricing_task_results(boq_item_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ptr_run ON pricing_task_results(run_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ptr_task ON pricing_task_results(task_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pricing_task_runs_task_item ON pricing_task_runs(task_id, boq_item_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pricing_task_batches_project ON pricing_task_batches(boq_project_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ptbir_batch ON pricing_task_batch_item_runs(batch_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ptbir_batch_item ON pricing_task_batch_item_runs(batch_id, boq_item_id)")
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


class PricingTaskBatchCreate(BaseModel):
    name: str
    boq_project_id: int
    quota_library_ids: list[int] = Field(default_factory=list)
    manual_project_id: Optional[int] = None


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
                "normalized_description": {
                    "type": "string",
                    "description": "补全综合考虑后的完整项目特征文本；没有补全时返回原项目特征或空字符串",
                },
                "default_fills": {
                    "type": "array",
                    "description": "按 tqdk_tzhkl 默认值完成的综合考虑项目特征补全明细",
                    "items": {
                        "type": "object",
                        "properties": {
                            "feature_name": {"type": "string"},
                            "original_value": {"type": "string"},
                            "default_value": {"type": "string"},
                            "source_code": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["feature_name", "original_value", "default_value", "source_code", "reason"],
                        "additionalProperties": False,
                    },
                },
                "description_updated": {"type": "boolean", "description": "后端是否已将补全后的项目特征回写到清单"},
            },
            "required": ["is_complete", "missing_features", "analysis", "normalized_description", "default_fills", "description_updated"],
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
        "description": "提交确认定额的组合定额换算结果。只给组合定额次数建议，不修改已确认定额和工程量系数。",
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
                            "reason": {"type": "string"},
                            "requires_manual_review": {"type": "boolean"},
                            "adjustment_rules": {
                                "type": "array",
                                "description": "按 tdek_tzhhs 查询到的组合定额换算规则及项目特征匹配结果。每条规则单独判断，不合并。",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "rule_index": {"type": "integer"},
                                        "prompt": {"type": "string"},
                                        "base_value": {"type": "number"},
                                        "increment_unit": {"type": "number"},
                                        "combo_dezmid": {"type": "integer"},
                                        "combo_code": {"type": "string"},
                                        "combo_name": {"type": "string"},
                                        "combo_unit": {"type": "string"},
                                        "combo_work_content": {"type": "string"},
                                        "matched": {"type": "boolean"},
                                        "matched_feature": {"type": "string"},
                                        "feature_value": {"type": "number"},
                                        "calculated_times": {"type": "number"},
                                        "reason": {"type": "string"},
                                        "requires_manual_review": {"type": "boolean"},
                                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                                    },
                                    "required": [
                                        "rule_index",
                                        "prompt",
                                        "base_value",
                                        "increment_unit",
                                        "combo_dezmid",
                                        "combo_code",
                                        "combo_name",
                                        "combo_unit",
                                        "combo_work_content",
                                        "matched",
                                        "matched_feature",
                                        "feature_value",
                                        "calculated_times",
                                        "reason",
                                        "requires_manual_review",
                                        "confidence",
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
                            "reason",
                            "requires_manual_review",
                            "adjustment_rules",
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


_TOOL_SUBMIT_COEFFICIENT_CHECK = {
    "type": "function",
    "function": {
        "name": "submit_coefficient_check",
        "description": "提交第七步系数换算判断结果。只保存和展示系数，不改写工料机含量。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "quota_key": {"type": "string"},
                            "source_type": {"type": "string", "enum": ["base", "combo"]},
                            "dekid": {"type": "integer"},
                            "dezmid": {"type": "integer"},
                            "quota_code": {"type": "string"},
                            "quota_name": {"type": "string"},
                            "coefficient_rules": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "rule_index": {"type": "integer"},
                                        "tsxx": {"type": "string"},
                                        "hssm": {"type": "string"},
                                        "group_no": {"type": "integer"},
                                        "matched": {"type": "boolean"},
                                        "matched_feature": {"type": "string"},
                                        "feature_value": {"type": "string"},
                                        "factor": {"type": "number"},
                                        "target_resource_types": {
                                            "type": "array",
                                            "items": {"type": "string", "enum": ["1", "2", "3", "all"]},
                                        },
                                        "reason": {"type": "string"},
                                        "requires_manual_review": {"type": "boolean"},
                                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                                    },
                                    "required": [
                                        "rule_index",
                                        "tsxx",
                                        "hssm",
                                        "group_no",
                                        "matched",
                                        "matched_feature",
                                        "feature_value",
                                        "factor",
                                        "target_resource_types",
                                        "reason",
                                        "requires_manual_review",
                                        "confidence",
                                    ],
                                    "additionalProperties": False,
                                },
                            },
                            "missing_inputs": {"type": "array", "items": {"type": "string"}},
                            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        },
                        "required": [
                            "quota_key",
                            "source_type",
                            "dekid",
                            "dezmid",
                            "quota_code",
                            "quota_name",
                            "coefficient_rules",
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


def _load_feature_default_candidates(conn, base_code: str) -> list[dict[str, Any]]:
    if not base_code:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT f.zmbh, f.feature_name, f.feature_value, f.default_value, f.source_rowid
            FROM tqdk_tzhkl f
            WHERE f.zmbh = %s
              AND trim(COALESCE(f.feature_value, '')) = '综合考虑'
              AND trim(COALESCE(f.default_value, '')) <> ''
            ORDER BY f.source_rowid, f.feature_name
            """,
            (base_code,),
        )
        rows = cur.fetchall()
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        feature_name = str(row[1] or "").strip()
        default_value = str(row[3] or "").strip()
        key = (feature_name, default_value)
        if not feature_name or not default_value or key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "source_code": row[0] or base_code,
                "feature_name": feature_name,
                "feature_value": row[2] or "",
                "default_value": default_value,
                "source_rowid": row[4],
            }
        )
    return candidates


def _normalize_feature_analysis_result(
    raw: dict[str, Any],
    original_description: str | None,
    base_code: str,
    default_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    original_text = (original_description or "").strip()
    candidate_by_key = {
        (str(item.get("feature_name") or "").strip(), str(item.get("default_value") or "").strip())
        for item in default_candidates
    }
    fills = []
    raw_fills = raw.get("default_fills", []) if isinstance(raw, dict) and "综合考虑" in original_text else []
    for fill in raw_fills:
        if not isinstance(fill, dict):
            continue
        feature_name = str(fill.get("feature_name") or "").strip()
        default_value = str(fill.get("default_value") or "").strip()
        if not feature_name or not default_value:
            continue
        if candidate_by_key and (feature_name, default_value) not in candidate_by_key:
            continue
        fills.append(
            {
                "feature_name": feature_name,
                "original_value": str(fill.get("original_value") or "综合考虑").strip() or "综合考虑",
                "default_value": default_value,
                "source_code": str(fill.get("source_code") or base_code).strip() or base_code,
                "reason": str(fill.get("reason") or "").strip(),
            }
        )
    normalized_description = str(raw.get("normalized_description") or "").strip() if isinstance(raw, dict) else ""
    if fills and (not normalized_description or "综合考虑" in normalized_description):
        normalized_description = original_text
        for fill in fills:
            default_value = fill["default_value"]
            feature_name = fill["feature_name"]
            pattern = re.compile(rf"({re.escape(feature_name)}\s*[:：]\s*)综合考虑")
            if pattern.search(normalized_description):
                normalized_description = pattern.sub(lambda match: f"{match.group(1)}{default_value}", normalized_description)
    if not fills:
        normalized_description = original_text
    return {
        "is_complete": bool(raw.get("is_complete")) if isinstance(raw, dict) else False,
        "missing_features": [str(v) for v in raw.get("missing_features", []) if str(v).strip()] if isinstance(raw, dict) else [],
        "analysis": str(raw.get("analysis") or "").strip() if isinstance(raw, dict) else "",
        "normalized_description": normalized_description,
        "default_fills": fills,
        "description_updated": False,
        "default_candidates": default_candidates,
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


COMBO_ADJUSTMENT_RULE_GUIDE = """
第七步组合定额换算规则：
1. 规则来源只使用 tdek_tzhhs。
2. 每条已确认定额可能有 0-N 条组合规则；每条组合规则必须单独判断，不允许合并。
3. 只判断项目特征中的数量特征是否与 tdek_tzhhs.tsxx、组合定额 zmmc 的增减指标匹配。
4. 匹配时提取项目特征值，由后端按 (特征值 - jcz) / zjdw 计算组合定额次数；小数保留，负数截为 0。
5. 缺少数量特征、单位明显不一致或 zjdw 无效时，不计算次数，标记人工复核。
6. 组合定额费用为 0 的说明型规则也要展示和解释，但不得臆造工料机调整。
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
            return _parse_json_object(call.function.arguments)
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


def _run_submit_coefficient_check(messages: list[dict[str, Any]]) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            resp = _client(thinking=False).chat.completions.create(
                model=_model(),
                messages=messages,
                tools=[_TOOL_SUBMIT_COEFFICIENT_CHECK],
                tool_choice={"type": "function", "function": {"name": "submit_coefficient_check"}},
                extra_body={"thinking": {"type": "disabled"}},
                max_tokens=8000,
                stream=False,
            )
            msg = resp.choices[0].message
            if not msg.tool_calls:
                raise ValueError(f"AI did not call submit_coefficient_check: {msg.content!r}")
            call = msg.tool_calls[0]
            if call.function.name != "submit_coefficient_check":
                raise ValueError(f"unexpected tool call {call.function.name!r}")
            return _parse_json_object(call.function.arguments)
        except Exception as exc:
            last_error = exc
            print(f"[pricing-task] submit coefficient check error attempt={attempt + 1}: {exc}", file=sys.stderr, flush=True)
    try:
        json_messages = [
            *messages,
            {
                "role": "user",
                "content": (
                    "工具参数生成失败。请改用 JSON Output，仅输出一个合法 JSON 对象，不要使用 Markdown。"
                    "JSON 顶层必须包含 items 和 issues，字段结构与 submit_coefficient_check 完全一致。"
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
        print(f"[pricing-task] coefficient JSON fallback error: {exc}", file=sys.stderr, flush=True)
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


def _normalize_accuracy_report(raw: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    def text(key: str, default: str = "") -> str:
        return str(raw.get(key) or default).strip()

    def text_list(key: str, limit: int = 8) -> list[str]:
        value = raw.get(key)
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value[:limit] if str(item).strip()]

    hit_count = int(evaluation.get("hit_count") or 0)
    missed_count = int(evaluation.get("missed_count") or 0)
    extra_count = int(evaluation.get("extra_count") or 0)
    manual_count = int(evaluation.get("manual_count") or 0)
    ai_count = int(evaluation.get("ai_count") or 0)
    accuracy_rate = round(hit_count / manual_count, 4) if manual_count else None

    level = text("accuracy_level", "待复核")
    if level not in {"高", "中", "低", "待复核"}:
        level = "待复核"

    return {
        "summary": text("summary", "暂无分析摘要。"),
        "accuracy_level": level,
        "accuracy_rate": accuracy_rate,
        "metrics": {
            "hit_count": hit_count,
            "missed_count": missed_count,
            "extra_count": extra_count,
            "manual_count": manual_count,
            "ai_count": ai_count,
        },
        "key_findings": text_list("key_findings"),
        "matched_analysis": text("matched_analysis"),
        "missed_analysis": text("missed_analysis"),
        "extra_analysis": text("extra_analysis"),
        "business_recommendations": text_list("business_recommendations"),
        "conclusion": text("conclusion"),
        "generated_at": datetime.now().isoformat(),
    }


def _generate_accuracy_report(
    boq_item: dict[str, Any],
    quota_match: dict[str, Any],
    evaluation: dict[str, Any],
    conversion_check: dict[str, Any] | None,
    coefficient_check: dict[str, Any] | None,
) -> dict[str, Any]:
    matches = quota_match.get("matches", []) if isinstance(quota_match, dict) else []
    payload = {
        "清单": {
            "编码": boq_item.get("item_code"),
            "名称": boq_item.get("item_name"),
            "项目特征": boq_item.get("item_description"),
            "单位": boq_item.get("unit"),
            "工程量": boq_item.get("quantity"),
        },
        "智能组价定额": [
            {
                "编码": item.get("zmbh"),
                "名称": item.get("zmmc"),
                "单位": item.get("dw"),
                "系数": item.get("qty_factor"),
                "置信度": item.get("confidence"),
                "理由": item.get("match_reason"),
            }
            for item in matches
        ],
        "人工对比工程定额": evaluation.get("manual_quotas", []),
        "对比统计": {
            "命中": evaluation.get("hit_codes", []),
            "遗漏": evaluation.get("missed_codes", []),
            "额外": evaluation.get("extra_codes", []),
            "hit_count": evaluation.get("hit_count", 0),
            "missed_count": evaluation.get("missed_count", 0),
            "extra_count": evaluation.get("extra_count", 0),
            "manual_count": evaluation.get("manual_count", 0),
            "ai_count": evaluation.get("ai_count", 0),
        },
        "组合换算": conversion_check or {},
        "系数换算": coefficient_check or {},
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是资深造价复核专家。请对智能组价结果与人工对比工程套定额结果做准确性分析。"
                "只基于输入数据，不编造不存在的定额。重点判断命中、遗漏、额外定额的业务原因，"
                "说明智能组价结果是否可采纳、哪些地方需要人工复核。请输出合法 JSON。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请按以下 JSON 结构输出："
                "{summary, accuracy_level, key_findings, matched_analysis, missed_analysis, "
                "extra_analysis, business_recommendations, conclusion}。"
                "accuracy_level 只能是 高/中/低/待复核；key_findings 和 business_recommendations 为字符串数组。"
                f"\n\n输入数据：\n{_json_dumps(payload)}"
            ),
        },
    ]
    resp = _client(thinking=False).chat.completions.create(
        model=_model(),
        messages=messages,
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}},
        max_tokens=4000,
        stream=False,
    )
    raw = _parse_json_content(resp.choices[0].message.content)
    return _normalize_accuracy_report(raw, evaluation)


def _normalize_task_accuracy_report(raw: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    def text(key: str, default: str = "") -> str:
        value = raw.get(key)
        if isinstance(value, list):
            return "；".join(str(item).strip() for item in value if str(item).strip())
        return str(value or default).strip()

    def text_list(key: str, limit: int = 12) -> list[str]:
        value = raw.get(key)
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value[:limit] if str(item).strip()]

    level = text("accuracy_level", "待复核")
    if level not in {"高", "中", "低", "待复核"}:
        level = "待复核"
    return {
        "summary": text("summary", "暂无分析摘要。"),
        "accuracy_level": level,
        "accuracy_rate": metrics.get("hit_rate"),
        "metrics": metrics,
        "key_findings": text_list("key_findings"),
        "matched_analysis": text("matched_analysis"),
        "missed_analysis": text("missed_analysis"),
        "extra_analysis": text("extra_analysis"),
        "risk_items": text_list("risk_items"),
        "representative_examples": text_list("representative_examples"),
        "business_recommendations": text_list("business_recommendations"),
        "conclusion": text("conclusion"),
        "generated_at": datetime.now().isoformat(),
    }


def _generate_task_accuracy_report(task: dict[str, Any], items: list[dict[str, Any]], metrics: dict[str, Any]) -> dict[str, Any]:
    compact_items = []
    for item in items:
        evaluation = item.get("evaluation") or {}
        quota_match = item.get("quota_match") or {}
        compact_items.append(
            {
                "清单编码": item.get("item_code"),
                "清单名称": item.get("item_name"),
                "项目特征": item.get("item_description"),
                "智能定额": [
                    {
                        "编码": match.get("zmbh"),
                        "名称": match.get("zmmc"),
                        "置信度": match.get("confidence"),
                        "理由": match.get("match_reason"),
                    }
                    for match in (quota_match.get("matches", []) if isinstance(quota_match, dict) else [])
                ],
                "人工定额": evaluation.get("manual_quotas", []) if isinstance(evaluation, dict) else [],
                "命中": evaluation.get("hit_codes", []) if isinstance(evaluation, dict) else [],
                "遗漏": evaluation.get("missed_codes", []) if isinstance(evaluation, dict) else [],
                "额外": evaluation.get("extra_codes", []) if isinstance(evaluation, dict) else [],
                "组合换算": item.get("conversion_check") or {},
                "系数换算": item.get("coefficient_check") or {},
            }
        )
    payload = {
        "任务": task,
        "总体指标": metrics,
        "清单明细": compact_items,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是资深造价复核专家。请对一个组价任务下全部清单的智能组价结果与人工对比工程结果做整体准确性分析。"
                "只基于输入数据，不编造定额。重点分析整体命中率、遗漏定额原因、额外定额原因、风险清单类型，"
                "并给出哪些结果可采纳、哪些需要人工复核。请输出合法 JSON。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请按以下 JSON 结构输出："
                "{summary, accuracy_level, key_findings, matched_analysis, missed_analysis, extra_analysis, "
                "risk_items, representative_examples, business_recommendations, conclusion}。"
                "accuracy_level 只能是 高/中/低/待复核；其余数组字段输出字符串数组。"
                f"\n\n输入数据：\n{_json_dumps(payload)}"
            ),
        },
    ]
    resp = _client(thinking=False).chat.completions.create(
        model=_model(),
        messages=messages,
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}},
        max_tokens=6000,
        stream=False,
    )
    raw = _parse_json_content(resp.choices[0].message.content)
    return _normalize_task_accuracy_report(raw, metrics)


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
                SELECT h.tsxx, h.zmbh, h.jcz, h.zjdw,
                       combo.id, combo.zmmc, combo.dw, combo.gznr,
                       combo.rgf, combo.clf, combo.jxf
                FROM tdek_tzhhs h
                LEFT JOIN tdek_tdezm combo ON combo.dekid = h.dekid AND combo.zmbh = h.zmbh
                WHERE h.dekid=%s AND h.dezmid=%s
                ORDER BY h.source_rowid
                """,
                (dekid, dezmid),
            )
            adjustment_rules = []
            for idx, r in enumerate(cur.fetchall(), start=1):
                combo_dezmid = int(r[4]) if r[4] is not None else 0
                combo_resources = []
                if combo_dezmid:
                    cur.execute(
                        """
                        SELECT zmbh, zmmc, dw, gcl, lx
                        FROM tdek_tzmgc
                        WHERE dekid=%s AND dezmid=%s
                        ORDER BY lx NULLS LAST, source_rowid
                        """,
                        (dekid, combo_dezmid),
                    )
                    combo_resources = [
                        {
                            "code": rr[0] or "",
                            "name": rr[1] or "",
                            "unit": rr[2] or "",
                            "quantity": float(rr[3]) if rr[3] is not None else None,
                            "type": int(rr[4]) if rr[4] is not None else None,
                        }
                        for rr in cur.fetchall()
                    ]
                adjustment_rules.append(
                    {
                        "rule_index": idx,
                        "prompt": r[0] or "",
                        "combo_code": r[1] or "",
                        "base_value": float(r[2]) if r[2] is not None else 0,
                        "increment_unit": float(r[3]) if r[3] is not None else 0,
                        "combo_dezmid": combo_dezmid,
                        "combo_name": r[5] or "",
                        "combo_unit": r[6] or "",
                        "combo_work_content": r[7] or "",
                        "combo_labor_cost": float(r[8]) if r[8] is not None else 0,
                        "combo_material_cost": float(r[9]) if r[9] is not None else 0,
                        "combo_machine_cost": float(r[10]) if r[10] is not None else 0,
                        "combo_resources": combo_resources,
                    }
                )
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
                    "adjustment_rules": adjustment_rules,
                }
            )
    return boq_item, items


def _confirmed_items_from_matches(conn, matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        for match in matches:
            try:
                dekid = int(match.get("dekid") or 0)
                dezmid = int(match.get("dezmid") or 0)
            except Exception:
                continue
            if not dekid or not dezmid:
                continue
            cur.execute(
                """
                SELECT q.zmbh, q.zmmc, q.dw, q.gznr, l.mc
                FROM tdek_tdezm q
                LEFT JOIN tlibs l ON l.id = q.dekid
                WHERE q.dekid=%s AND q.id=%s
                """,
                (dekid, dezmid),
            )
            qrow = cur.fetchone()
            if not qrow:
                continue
            cur.execute(
                """
                SELECT h.tsxx, h.zmbh, h.jcz, h.zjdw,
                       combo.id, combo.zmmc, combo.dw, combo.gznr,
                       combo.rgf, combo.clf, combo.jxf
                FROM tdek_tzhhs h
                LEFT JOIN tdek_tdezm combo ON combo.dekid = h.dekid AND combo.zmbh = h.zmbh
                WHERE h.dekid=%s AND h.dezmid=%s
                ORDER BY h.source_rowid
                """,
                (dekid, dezmid),
            )
            adjustment_rules = []
            for idx, rule_row in enumerate(cur.fetchall(), start=1):
                combo_dezmid = int(rule_row[4]) if rule_row[4] is not None else 0
                combo_resources = _load_combo_resources(conn, dekid, combo_dezmid, rule_row[1] or "") if combo_dezmid or rule_row[1] else []
                adjustment_rules.append(
                    {
                        "rule_index": idx,
                        "prompt": rule_row[0] or "",
                        "combo_code": rule_row[1] or "",
                        "base_value": float(rule_row[2]) if rule_row[2] is not None else 0,
                        "increment_unit": float(rule_row[3]) if rule_row[3] is not None else 0,
                        "combo_dezmid": combo_dezmid,
                        "combo_name": rule_row[5] or "",
                        "combo_unit": rule_row[6] or "",
                        "combo_work_content": rule_row[7] or "",
                        "combo_labor_cost": float(rule_row[8]) if rule_row[8] is not None else 0,
                        "combo_material_cost": float(rule_row[9]) if rule_row[9] is not None else 0,
                        "combo_machine_cost": float(rule_row[10]) if rule_row[10] is not None else 0,
                        "combo_resources": combo_resources,
                    }
                )
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
                    "quota_code": qrow[0] or match.get("zmbh") or "",
                    "quota_name": qrow[1] or match.get("zmmc") or "",
                    "current_qty_factor": float(match.get("qty_factor") or 1),
                    "confidence": match.get("confidence") or "",
                    "match_reason": match.get("match_reason") or "",
                    "unit": qrow[2] or "",
                    "work_content": qrow[3] or "",
                    "library_name": qrow[4] or match.get("library_name") or "",
                    "resources": resources,
                    "adjustment_rules": adjustment_rules,
                }
            )
    return items


def _confirmed_results_from_matches(conn, matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "dekid": item["dekid"],
            "dezmid": item["dezmid"],
            "subitem_code": item["quota_code"],
            "subitem_name": item["quota_name"],
            "qty_factor": item.get("current_qty_factor", 1),
            "status": "confirmed",
            "conversion_confirmed": False,
            "conversion_note": "",
            "conversion_confirmed_at": None,
            "conversion_resources": item.get("resources", []),
            "conversion_resource_changes": [],
        }
        for item in _confirmed_items_from_matches(conn, matches)
    ]


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        parsed = float(value)
        if parsed != parsed:
            return None
        return parsed
    except Exception:
        return None


_FULLWIDTH_TRANS = str.maketrans(
    "０１２３４５６７８９．，：（）＞＜＋－",
    "0123456789.,:()><+-",
)

_UNIT_ALIASES: dict[str, list[str]] = {
    "km": ["km", "公里", "千米"],
    "m": ["m", "米"],
    "mm": ["mm", "毫米"],
    "cm": ["cm", "厘米"],
    "t": ["t", "吨"],
    "kg": ["kg", "千克", "公斤"],
    "层": ["层"],
    "芯": ["芯"],
    "孔": ["孔"],
    "次": ["次"],
    "根": ["根"],
    "组": ["组"],
    "台": ["台"],
}

_FEATURE_KEYWORDS = [
    "运距",
    "厚度",
    "高度",
    "深度",
    "孔深",
    "宽度",
    "长度",
    "距离",
    "重量",
    "功率",
    "层数",
    "芯数",
]


def _normalize_feature_text(value: Any) -> str:
    return str(value or "").translate(_FULLWIDTH_TRANS).replace("ＫＭ", "KM").replace("ｋｍ", "km")


def _rule_unit_aliases(rule: dict[str, Any]) -> list[str]:
    text = _normalize_feature_text(
        " ".join(
            [
                str(rule.get("prompt") or ""),
                str(rule.get("combo_name") or ""),
                str(rule.get("combo_unit") or ""),
            ]
        )
    ).lower()
    aliases: list[str] = []
    for canonical, values in _UNIT_ALIASES.items():
        if canonical.lower() in text or any(alias.lower() in text for alias in values):
            aliases.extend(values)
    if not aliases and "每增运" in text:
        aliases.extend(_UNIT_ALIASES["km"])
    return sorted(set(aliases), key=len, reverse=True)


def _rule_keywords(rule: dict[str, Any]) -> list[str]:
    text = _normalize_feature_text(f"{rule.get('prompt') or ''} {rule.get('combo_name') or ''}")
    keywords = [keyword for keyword in _FEATURE_KEYWORDS if keyword in text]
    if not keywords and "每增运" in text:
        keywords.append("运距")
    return keywords


def _infer_feature_value_from_boq(boq_item: dict[str, Any] | None, rule: dict[str, Any]) -> dict[str, Any] | None:
    if not boq_item:
        return None
    text = _normalize_feature_text(
        "\n".join(
            [
                str(boq_item.get("item_description") or ""),
                str(boq_item.get("item_name") or ""),
            ]
        )
    )
    unit_aliases = _rule_unit_aliases(rule)
    if not text or not unit_aliases:
        return None

    alias_pattern = "|".join(re.escape(alias) for alias in unit_aliases)
    pattern = re.compile(rf"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>{alias_pattern})", re.IGNORECASE)
    keywords = _rule_keywords(rule)
    candidates: list[tuple[int, float, str, str]] = []
    for match in pattern.finditer(text):
        value = _float_or_none(match.group("value"))
        if value is None:
            continue
        start = max(0, match.start() - 24)
        end = min(len(text), match.end() + 24)
        snippet = text[start:end].strip()
        score = 10
        for keyword in keywords:
            keyword_pos = text.rfind(keyword, max(0, match.start() - 30), match.end())
            if keyword_pos >= 0:
                score += 20 - min(19, abs(match.start() - keyword_pos))
        candidates.append((score, value, match.group("unit"), snippet))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, feature_value, unit, snippet = candidates[0]
    keyword_text = "、".join(keywords) if keywords else "数量特征"
    return {
        "feature_value": feature_value,
        "matched_feature": snippet,
        "reason": f"从项目特征识别到{keyword_text}{feature_value:g}{unit}，匹配组合定额增减指标。",
    }


def _normalize_adjustment_rules(
    raw_item: dict[str, Any] | None,
    confirmed: dict[str, Any],
    boq_item: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    raw_rules = raw_item.get("adjustment_rules", []) if isinstance(raw_item, dict) else []
    raw_by_index: dict[int, dict[str, Any]] = {}
    raw_by_code: dict[str, dict[str, Any]] = {}
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            continue
        try:
            raw_by_index[int(raw_rule.get("rule_index") or 0)] = raw_rule
        except Exception:
            pass
        combo_code = str(raw_rule.get("combo_code") or "").strip()
        if combo_code:
            raw_by_code[combo_code] = raw_rule

    normalized: list[dict[str, Any]] = []
    for rule in confirmed.get("adjustment_rules", []):
        rule_index = int(rule.get("rule_index") or 0)
        combo_code = str(rule.get("combo_code") or "")
        raw_rule = raw_by_index.get(rule_index) or raw_by_code.get(combo_code) or {}
        matched = bool(raw_rule.get("matched"))
        feature_value = _float_or_none(raw_rule.get("feature_value"))
        base_value = _float_or_none(rule.get("base_value")) or 0.0
        increment_unit = _float_or_none(rule.get("increment_unit")) or 0.0
        calculated_times: float | None = None
        reason = str(raw_rule.get("reason") or "")
        requires_manual_review = bool(raw_rule.get("requires_manual_review"))
        matched_feature = str(raw_rule.get("matched_feature") or "")
        confidence = raw_rule.get("confidence") if raw_rule.get("confidence") in {"high", "medium", "low"} else "low"

        inferred = _infer_feature_value_from_boq(boq_item, rule)
        if inferred and (feature_value is None or not matched):
            matched = True
            feature_value = inferred["feature_value"]
            matched_feature = matched_feature or str(inferred["matched_feature"])
            reason = str(inferred["reason"])
            requires_manual_review = False
            confidence = "high"

        if matched and feature_value is not None and increment_unit > 0:
            calculated_times = (feature_value - base_value) / increment_unit
            if calculated_times < 0:
                calculated_times = 0.0
                reason = reason or "特征值低于基础值，未生成追加次数。"
            else:
                formula_reason = f"按 ({feature_value:g} - {base_value:g}) / {increment_unit:g} = {calculated_times:g} 计算组合定额次数。"
                reason = f"{reason} {formula_reason}".strip() if reason else formula_reason
        elif matched:
            matched = False
            requires_manual_review = True
            reason = reason or "缺少可计算的项目特征值或增减单位无效，需人工复核。"
        else:
            reason = reason or "项目特征未匹配该组合定额的数量增减指标。"

        normalized.append(
            {
                "rule_index": rule_index,
                "prompt": str(rule.get("prompt") or raw_rule.get("prompt") or ""),
                "base_value": base_value,
                "increment_unit": increment_unit,
                "combo_dezmid": int(rule.get("combo_dezmid") or raw_rule.get("combo_dezmid") or 0),
                "combo_code": combo_code or str(raw_rule.get("combo_code") or ""),
                "combo_name": str(rule.get("combo_name") or raw_rule.get("combo_name") or ""),
                "combo_unit": str(rule.get("combo_unit") or raw_rule.get("combo_unit") or ""),
                "combo_work_content": str(rule.get("combo_work_content") or raw_rule.get("combo_work_content") or ""),
                "combo_labor_cost": _float_or_none(rule.get("combo_labor_cost")) or 0,
                "combo_material_cost": _float_or_none(rule.get("combo_material_cost")) or 0,
                "combo_machine_cost": _float_or_none(rule.get("combo_machine_cost")) or 0,
                "combo_resources": [
                    {
                        "code": str(resource.get("code") or ""),
                        "name": str(resource.get("name") or ""),
                        "unit": str(resource.get("unit") or ""),
                        "quantity": resource.get("quantity"),
                        "type": resource.get("type"),
                    }
                    for resource in rule.get("combo_resources", [])
                    if isinstance(resource, dict)
                ],
                "matched": matched,
                "matched_feature": matched_feature,
                "feature_value": feature_value,
                "calculated_times": calculated_times,
                "reason": reason,
                "requires_manual_review": requires_manual_review,
                "confidence": confidence,
            }
        )
    return normalized


def _default_conversion_check(
    items: list[dict[str, Any]],
    issue: str | None = None,
    boq_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "items": [
            {
                "dekid": item["dekid"],
                "dezmid": item["dezmid"],
                "quota_code": item["quota_code"],
                "quota_name": item["quota_name"],
                "needs_conversion": False,
                "reason": "未查询到组合定额规则，默认不建议换算。" if not item.get("adjustment_rules") else "未完成组合定额规则分析。",
                "requires_manual_review": bool(item.get("adjustment_rules")),
                "resources": item.get("resources", []),
                "adjustment_rules": _normalize_adjustment_rules(None, item, boq_item),
                "missing_inputs": [],
                "confidence": "medium",
            }
            for item in items
        ],
        "issues": [issue] if issue else [],
    }


def _normalize_conversion_check(
    raw: dict[str, Any],
    confirmed_items: list[dict[str, Any]],
    boq_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
            normalized.extend(_default_conversion_check([confirmed], boq_item=boq_item)["items"])
            continue
        confidence = item.get("confidence") if item.get("confidence") in {"high", "medium", "low"} else "low"
        adjustment_rules = _normalize_adjustment_rules(item, confirmed, boq_item)
        has_calculated_adjustment = any(
            bool(rule.get("matched")) and (_float_or_none(rule.get("calculated_times")) or 0) > 0
            for rule in adjustment_rules
        )
        normalized.append(
            {
                "dekid": confirmed["dekid"],
                "dezmid": confirmed["dezmid"],
                "quota_code": confirmed["quota_code"],
                "quota_name": confirmed["quota_name"],
                "needs_conversion": bool(item.get("needs_conversion")) or has_calculated_adjustment,
                "reason": str(item.get("reason") or ""),
                "requires_manual_review": bool(
                    item.get("requires_manual_review")
                    or any(rule.get("requires_manual_review") for rule in adjustment_rules)
                ),
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
                "adjustment_rules": adjustment_rules,
                "missing_inputs": [str(v) for v in item.get("missing_inputs", []) if v],
                "confidence": confidence,
            }
        )
    return {"items": normalized, "issues": [str(v) for v in raw.get("issues", []) if v]}


def _load_combo_resources(conn, dekid: int, combo_dezmid: int | None, combo_code: str | None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        dezmid = combo_dezmid or 0
        if not dezmid and combo_code:
            cur.execute(
                """
                SELECT id
                FROM tdek_tdezm
                WHERE dekid=%s AND zmbh=%s
                LIMIT 1
                """,
                (dekid, combo_code),
            )
            row = cur.fetchone()
            dezmid = int(row[0]) if row else 0
        if not dezmid:
            return []
        cur.execute(
            """
            SELECT zmbh, zmmc, dw, gcl, lx
            FROM tdek_tzmgc
            WHERE dekid=%s AND dezmid=%s
            ORDER BY lx NULLS LAST, source_rowid
            """,
            (dekid, dezmid),
        )
        return [
            {
                "code": r[0] or "",
                "name": r[1] or "",
                "unit": r[2] or "",
                "quantity": float(r[3]) if r[3] is not None else None,
                "type": int(r[4]) if r[4] is not None else None,
            }
            for r in cur.fetchall()
        ]


def _hydrate_conversion_combo_resources(conn, conversion_check: Any) -> Any:
    if not isinstance(conversion_check, dict):
        return conversion_check
    for item in conversion_check.get("items", []):
        if not isinstance(item, dict):
            continue
        try:
            dekid = int(item.get("dekid") or 0)
        except Exception:
            dekid = 0
        if not dekid:
            continue
        for rule in item.get("adjustment_rules", []) or []:
            if not isinstance(rule, dict) or rule.get("combo_resources"):
                continue
            try:
                combo_dezmid = int(rule.get("combo_dezmid") or 0)
            except Exception:
                combo_dezmid = 0
            rule["combo_resources"] = _load_combo_resources(
                conn,
                dekid,
                combo_dezmid,
                str(rule.get("combo_code") or ""),
            )
    return conversion_check


def _load_coefficient_rules(conn, dekid: int, dezmid: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tsxx, hssm, COALESCE(groupno, 0)
            FROM tdek_tznhs
            WHERE dekid=%s AND dezmid=%s
            ORDER BY groupno NULLS LAST, source_rowid
            """,
            (dekid, dezmid),
        )
        return [
            {
                "rule_index": idx,
                "tsxx": r[0] or "",
                "hssm": r[1] or "",
                "group_no": int(r[2] or 0),
            }
            for idx, r in enumerate(cur.fetchall(), start=1)
        ]


def _parse_factor_from_text(text: str) -> float:
    match = re.search(r"系数\s*([0-9]+(?:\.[0-9]+)?)", text or "")
    return float(match.group(1)) if match else 1.0


def _target_types_from_text(text: str) -> list[str]:
    value = text or ""
    if "子目乘以系数" in value or "相应子目乘以系数" in value:
        return ["all"]
    targets: list[str] = []
    if "人工" in value:
        targets.append("1")
    if "材料" in value:
        targets.append("2")
    if "机械" in value:
        targets.append("3")
    return targets or ["all"]


def _coefficient_context(conn, run_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    boq_item, confirmed_items = _confirmed_conversion_context(conn, run_id)
    with conn.cursor() as cur:
        cur.execute("SELECT conversion_check FROM pricing_task_runs WHERE id=%s", (run_id,))
        row = cur.fetchone()
    conversion_check = _hydrate_conversion_combo_resources(conn, row[0] if row else None) or {}
    return boq_item, _coefficient_items_from_context(conn, confirmed_items, conversion_check)


def _coefficient_items_from_context(
    conn,
    confirmed_items: list[dict[str, Any]],
    conversion_check: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in confirmed_items:
        coefficient_rules = _load_coefficient_rules(conn, int(item["dekid"]), int(item["dezmid"]))
        items.append(
            {
                "quota_key": f"base:{item['dekid']}:{item['dezmid']}",
                "source_type": "base",
                "dekid": item["dekid"],
                "dezmid": item["dezmid"],
                "quota_code": item["quota_code"],
                "quota_name": item["quota_name"],
                "resources": item.get("resources", []),
                "coefficient_rules": coefficient_rules,
            }
        )

    conversion_data = _hydrate_conversion_combo_resources(conn, conversion_check or {}) or {}
    for base_item in conversion_data.get("items", []) if isinstance(conversion_data, dict) else []:
        if not isinstance(base_item, dict):
            continue
        dekid = int(base_item.get("dekid") or 0)
        for rule in base_item.get("adjustment_rules", []) or []:
            if not isinstance(rule, dict):
                continue
            combo_dezmid = int(rule.get("combo_dezmid") or 0)
            if not dekid or not combo_dezmid:
                continue
            coefficient_rules = _load_coefficient_rules(conn, dekid, combo_dezmid)
            items.append(
                {
                    "quota_key": f"combo:{dekid}:{combo_dezmid}:{rule.get('combo_code') or ''}",
                    "source_type": "combo",
                    "dekid": dekid,
                    "dezmid": combo_dezmid,
                    "quota_code": str(rule.get("combo_code") or ""),
                    "quota_name": str(rule.get("combo_name") or ""),
                    "resources": rule.get("combo_resources") or [],
                    "combo_times": rule.get("calculated_times"),
                    "base_quota_code": base_item.get("quota_code") or "",
                    "coefficient_rules": coefficient_rules,
                }
            )
    return items


def _default_coefficient_check(items: list[dict[str, Any]], issue: str | None = None) -> dict[str, Any]:
    return {
        "items": [
            {
                "quota_key": item["quota_key"],
                "source_type": item["source_type"],
                "dekid": item["dekid"],
                "dezmid": item["dezmid"],
                "quota_code": item["quota_code"],
                "quota_name": item["quota_name"],
                "resources": item.get("resources", []),
                "coefficient_rules": [
                    {
                        **rule,
                        "matched": False,
                        "matched_feature": "",
                        "feature_value": "",
                        "factor": _parse_factor_from_text(rule.get("hssm", "")),
                        "target_resource_types": _target_types_from_text(rule.get("hssm", "")),
                        "reason": "待识别项目特征是否触发该系数换算说明。",
                        "requires_manual_review": False,
                        "confidence": "medium",
                    }
                    for rule in item.get("coefficient_rules", [])
                ],
                "missing_inputs": [],
                "confidence": "medium",
            }
            for item in items
        ],
        "issues": [issue] if issue else [],
    }


def _normalize_coefficient_check(raw: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    raw_by_key = {str(item.get("quota_key") or ""): item for item in raw.get("items", []) if isinstance(item, dict)}
    normalized_items = []
    for item in items:
        raw_item = raw_by_key.get(item["quota_key"]) or {}
        raw_rules = raw_item.get("coefficient_rules", []) if isinstance(raw_item, dict) else []
        raw_by_index: dict[int, dict[str, Any]] = {}
        for raw_rule in raw_rules:
            if not isinstance(raw_rule, dict):
                continue
            try:
                raw_by_index[int(raw_rule.get("rule_index") or 0)] = raw_rule
            except Exception:
                pass
        rules = []
        for rule in item.get("coefficient_rules", []):
            raw_rule = raw_by_index.get(int(rule.get("rule_index") or 0), {})
            hssm = str(rule.get("hssm") or raw_rule.get("hssm") or "")
            matched = bool(raw_rule.get("matched"))
            factor = _float_or_none(raw_rule.get("factor")) or _parse_factor_from_text(hssm)
            target_types = raw_rule.get("target_resource_types")
            if not isinstance(target_types, list) or not target_types:
                target_types = _target_types_from_text(hssm)
            target_types = [str(v) for v in target_types if str(v) in {"1", "2", "3", "all"}] or _target_types_from_text(hssm)
            rules.append(
                {
                    "rule_index": int(rule.get("rule_index") or 0),
                    "tsxx": str(rule.get("tsxx") or raw_rule.get("tsxx") or ""),
                    "hssm": hssm,
                    "group_no": int(rule.get("group_no") or raw_rule.get("group_no") or 0),
                    "matched": matched,
                    "matched_feature": str(raw_rule.get("matched_feature") or ""),
                    "feature_value": str(raw_rule.get("feature_value") or ""),
                    "factor": factor,
                    "target_resource_types": target_types,
                    "reason": str(raw_rule.get("reason") or ("项目特征未触发该系数换算说明。" if not matched else "")),
                    "requires_manual_review": bool(raw_rule.get("requires_manual_review")),
                    "confidence": raw_rule.get("confidence") if raw_rule.get("confidence") in {"high", "medium", "low"} else "low",
                }
            )
        normalized_items.append(
            {
                "quota_key": item["quota_key"],
                "source_type": item["source_type"],
                "dekid": item["dekid"],
                "dezmid": item["dezmid"],
                "quota_code": item["quota_code"],
                "quota_name": item["quota_name"],
                "resources": item.get("resources", []),
                "coefficient_rules": rules,
                "missing_inputs": [str(v) for v in raw_item.get("missing_inputs", []) if v] if isinstance(raw_item, dict) else [],
                "confidence": raw_item.get("confidence") if isinstance(raw_item, dict) and raw_item.get("confidence") in {"high", "medium", "low"} else "medium",
            }
        )
    return {"items": normalized_items, "issues": [str(v) for v in raw.get("issues", []) if v]}


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
            "coefficient_check",
            "step_timings",
        } else value)
    values.append(run_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE pricing_task_runs SET {', '.join(assignments)} WHERE id = %s", values)
    conn.commit()


def _json_value(value: Any) -> Any:
    return Json(value, dumps=_json_dumps)


def _update_batch_item_run(conn, item_run_id: int, **fields: Any) -> None:
    if not fields:
        return
    json_fields = {
        "code_check",
        "feature_check",
        "work_procedures",
        "quota_candidates",
        "quota_match",
        "evaluation",
        "confirmed_results",
        "conversion_check",
        "coefficient_check",
        "step_timings",
    }
    assignments = []
    values = []
    for key, value in fields.items():
        assignments.append(f"{key} = %s")
        values.append(_json_value(value) if key in json_fields else value)
    values.append(item_run_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE pricing_task_batch_item_runs SET {', '.join(assignments)} WHERE id = %s", values)
    conn.commit()


def _load_batch_step_timings(conn, item_run_id: int) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT step_timings FROM pricing_task_batch_item_runs WHERE id=%s", (item_run_id,))
        row = cur.fetchone()
    return dict(row[0] or {}) if row else {}


def _finish_batch_step_timing(
    conn,
    item_run_id: int,
    timings: dict[str, Any],
    step_no: int,
    name: str,
    started_at: datetime,
    started_perf: float,
) -> dict[str, Any]:
    timing = _finish_step_timing(conn, None, timings, step_no, name, started_at, started_perf)
    _update_batch_item_run(conn, item_run_id, step_timings=timings)
    return timing


def _load_step_timings(conn, run_id: int) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT step_timings FROM pricing_task_runs WHERE id=%s", (run_id,))
        row = cur.fetchone()
    return dict(row[0] or {}) if row else {}


def _finish_step_timing(
    conn,
    run_id: int | None,
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
    if run_id is not None:
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
    run_id: int | None,
    *,
    persist_run: bool = True,
    update_item_description: bool = True,
) -> Iterable[tuple[str, Any]]:
    system_prompt = build_system_prompt()
    step_timings: dict[str, Any] = {}

    step_started_at = datetime.now()
    step_started_perf = perf_counter()
    code_check = exec_check_item_code(conn, boq_item["item_code"], boq_item["item_name"])
    yield ("code_check", code_check)
    yield ("judgment", {"is_consistent": code_check["is_consistent"], "reasoning": f"标准清单名称：{code_check['standard_name'] or '未找到'}"})
    if persist_run and run_id is not None:
        _update_run(conn, run_id, code_check=code_check)
    yield ("step_timing", _finish_step_timing(conn, run_id, step_timings, 1, "编码核查", step_started_at, step_started_perf))

    step_started_at = datetime.now()
    step_started_perf = perf_counter()
    feature_default_candidates = _load_feature_default_candidates(conn, code_check.get("base_code") or _base_code(boq_item["item_code"]))
    feature_default_text = _json_dumps(feature_default_candidates) if feature_default_candidates else "[]"
    messages_r2 = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"请分析以下工程量清单项的项目特征描述是否完整充分，能否满足套定额要求：\n\n"
                f"清单编码：{boq_item['item_code']}\n清单名称：{boq_item['item_name']}\n"
                f"项目特征：{boq_item.get('item_description') or '（未填写）'}\n计量单位：{boq_item.get('unit') or '无'}\n\n"
                f"【综合考虑默认值候选，来源 tqdk_tzhkl】\n{feature_default_text}\n\n"
                f"如果项目特征中存在“综合考虑”，请只从上述候选中选择明确匹配的 feature_name/default_value，"
                f"把对应“特征名: 综合考虑”替换为“特征名: 默认值”，生成 normalized_description。"
                f"不要覆盖已有明确特征值；无法明确匹配时不要补全。\n"
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
    feature_result = _normalize_feature_analysis_result(
        feature_result,
        boq_item.get("item_description"),
        code_check.get("base_code") or _base_code(boq_item["item_code"]),
        feature_default_candidates,
    )
    normalized_description = str(feature_result.get("normalized_description") or "").strip()
    if feature_result.get("default_fills") and normalized_description and normalized_description != (boq_item.get("item_description") or "").strip():
        with conn.cursor() as cur:
            if update_item_description:
                cur.execute("UPDATE boq_items SET item_description = %s WHERE id = %s", (normalized_description, boq_item["id"]))
                conn.commit()
        boq_item["item_description"] = normalized_description
        feature_result["description_updated"] = bool(update_item_description)
    yield ("feature_check", feature_result)
    if persist_run and run_id is not None:
        _update_run(conn, run_id, feature_check=feature_result)
    yield ("step_timing", _finish_step_timing(conn, run_id, step_timings, 2, "项目特征", step_started_at, step_started_perf))

    step_started_at = datetime.now()
    step_started_perf = perf_counter()
    candidates_data = exec_fetch_quota_candidates(conn, boq_item["item_code"], quota_library_ids)
    yield ("quota_candidates", candidates_data)
    if persist_run and run_id is not None:
        _update_run(conn, run_id, quota_candidates=candidates_data)
    yield ("step_timing", _finish_step_timing(conn, run_id, step_timings, 3, "定额候选", step_started_at, step_started_perf))

    step_started_at = datetime.now()
    step_started_perf = perf_counter()
    candidates = candidates_data["candidates"]
    candidate_text = "\n".join(
        f"[{i + 1}] dekid={c['dekid']} dezmid={c['dezmid']} 编码={c['zmbh']} 名称={c['zmmc']} 单位={c['dw']} "
        f"库={c['library_name']} 章节={c.get('chapter_name') or ''}"
        + (f"\n    工作内容：{c['gznr']}" if c.get("gznr") else "")
        for i, c in enumerate(candidates)
    ) or "（无候选定额）"
    messages_r5_analysis = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"请先对候选定额进行套定额分析，不要调用工具，不要输出 JSON。\n"
                f"请说明候选取舍、工程量系数、置信度依据和模糊问题，最后给出建议选择的 dekid/dezmid。\n\n"
                f"套定额原则：基于清单项目特征、候选定额名称和工作内容进行匹配分析和判断。\n\n"
                f"【清单项】\n编码：{boq_item['item_code']}\n名称：{boq_item['item_name']}\n"
                f"项目特征：{boq_item.get('item_description') or '（未填写）'}\n单位：{boq_item.get('unit') or '无'}\n"
                f"【编码核查】{_json_dumps(code_check)}\n"
                f"【项目特征分析】{_json_dumps(feature_result)}\n"
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
                f"套定额原则：用清单项目特征信息、候选定额名称和工作内容进行匹配分析和判断。\n\n"
                f"【清单项】\n编码：{boq_item['item_code']}\n名称：{boq_item['item_name']}\n"
                f"项目特征：{boq_item.get('item_description') or '（未填写）'}\n单位：{boq_item.get('unit') or '无'}\n"
                f"【编码核查】{_json_dumps(code_check)}\n"
                f"【项目特征分析】{_json_dumps(feature_result)}\n"
                f"【第五轮A套定额分析】\n{quota_analysis or '（无分析文本）'}\n\n"
                f"【候选定额子目（共 {candidates_data['total']} 条）】\n{candidate_text}\n"
            ),
        },
    ]
    raw_match = _run_submit_match(messages_r5_submit) if candidates else {"matches": [], "issues": ["未找到候选定额子目"]}
    match_result = _normalize_matches(raw_match, candidates)
    if persist_run and run_id is not None:
        _update_run(conn, run_id, quota_match=match_result)
    yield ("quota_match", match_result)
    yield ("step_timing", _finish_step_timing(conn, run_id, step_timings, 4, "套定额结果", step_started_at, step_started_perf))

    step_started_at = datetime.now()
    step_started_perf = perf_counter()
    manual = _manual_quotas(conn, manual_project_id, boq_item.get("item_code"))
    evaluation = _evaluate(match_result["matches"], manual)
    if persist_run and run_id is not None:
        _update_run(conn, run_id, evaluation=evaluation)
        _save_pending_results(conn, task_id, run_id, boq_item, match_result, evaluation)
    yield ("evaluation", evaluation)
    yield ("step_timing", _finish_step_timing(conn, run_id, step_timings, 5, "人工对比", step_started_at, step_started_perf))


def _row_to_task(row) -> dict[str, Any]:
    ids = row[6] or []
    return {
        "id": row[0],
        "name": row[1],
        "boq_project_id": row[2],
        "project_id": row[2],
        "project_name": row[3],
        "manual_project_id": row[4],
        "manual_project_name": row[5],
        "quota_library_ids": ids,
        "quota_library_names": row[7] or [],
        "legacy_local_id": row[8],
        "created_at": row[9],
        "latest_run_count": row[10],
        "accuracy_report": row[11] if len(row) > 11 else None,
    }


def _row_to_batch(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "boq_project_id": row[2],
        "project_id": row[2],
        "project_name": row[3],
        "manual_project_id": row[4],
        "manual_project_name": row[5],
        "quota_library_ids": row[6] or [],
        "quota_library_names": row[7] or [],
        "status": row[8],
        "selected_count": row[9] or 0,
        "completed_count": row[10] or 0,
        "failed_count": row[11] or 0,
        "created_at": row[12],
        "started_at": row[13],
        "finished_at": row[14],
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
                SELECT t.id, t.name, t.boq_project_id, p.project_name, t.manual_project_id, mp.project_name AS manual_project_name,
                       t.quota_library_ids, COALESCE(array_agg(l.mc ORDER BY l.id) FILTER (WHERE l.id IS NOT NULL), '{}') AS library_names,
                       t.legacy_local_id, t.created_at,
                       (SELECT COUNT(*) FROM pricing_task_runs r WHERE r.task_id=t.id) AS run_count
                       , t.accuracy_report
                FROM pricing_tasks t
                JOIN boq_projects p ON p.id = t.boq_project_id
                LEFT JOIN manual_boq_projects mp ON mp.id = t.manual_project_id
                LEFT JOIN LATERAL jsonb_array_elements_text(t.quota_library_ids) lib_id(value) ON TRUE
                LEFT JOIN tlibs l ON l.id = lib_id.value::bigint
                WHERE t.status <> 'deleted'
                GROUP BY t.id, p.project_name, mp.project_name
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
                SELECT t.id, t.name, t.boq_project_id, p.project_name, t.manual_project_id, mp.project_name AS manual_project_name,
                       t.quota_library_ids, COALESCE(array_agg(l.mc ORDER BY l.id) FILTER (WHERE l.id IS NOT NULL), '{}') AS library_names,
                       t.legacy_local_id, t.created_at,
                       (SELECT COUNT(*) FROM pricing_task_runs r WHERE r.task_id=t.id) AS run_count
                       , t.accuracy_report
                FROM pricing_tasks t
                JOIN boq_projects p ON p.id = t.boq_project_id
                LEFT JOIN manual_boq_projects mp ON mp.id = t.manual_project_id
                LEFT JOIN LATERAL jsonb_array_elements_text(t.quota_library_ids) lib_id(value) ON TRUE
                LEFT JOIN tlibs l ON l.id = lib_id.value::bigint
                WHERE t.id=%s AND t.status <> 'deleted'
                GROUP BY t.id, p.project_name, mp.project_name
                """,
                (task_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="task not found")
            return _row_to_task(row)
    finally:
        conn.close()


def _batch_select_sql() -> str:
    return """
        SELECT b.id, b.name, b.boq_project_id, p.project_name,
               b.manual_project_id, mp.project_name AS manual_project_name,
               b.quota_library_ids,
               COALESCE(array_agg(l.mc ORDER BY l.id) FILTER (WHERE l.id IS NOT NULL), '{}') AS library_names,
               b.status, b.selected_count, b.completed_count, b.failed_count,
               b.created_at, b.started_at, b.finished_at
        FROM pricing_task_batches b
        JOIN boq_projects p ON p.id = b.boq_project_id
        LEFT JOIN manual_boq_projects mp ON mp.id = b.manual_project_id
        LEFT JOIN LATERAL jsonb_array_elements_text(b.quota_library_ids) lib_id(value) ON TRUE
        LEFT JOIN tlibs l ON l.id = lib_id.value::bigint
    """


@router.get("/pricing-task-batches")
def list_pricing_task_batches():
    from db.connection import get_connection

    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                _batch_select_sql()
                + """
                WHERE b.status <> 'deleted'
                GROUP BY b.id, p.project_name, mp.project_name
                ORDER BY b.created_at DESC
                """
            )
            return [_row_to_batch(row) for row in cur.fetchall()]
    finally:
        conn.close()


@router.post("/pricing-task-batches")
def create_pricing_task_batch(body: PricingTaskBatchCreate):
    from db.connection import get_connection

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="batch name required")
    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM boq_projects WHERE id=%s", (body.boq_project_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="BOQ project not found")
            if body.manual_project_id:
                cur.execute("SELECT id FROM manual_boq_projects WHERE id=%s", (body.manual_project_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="manual project not found")
            cur.execute(
                """
                INSERT INTO pricing_task_batches(name, boq_project_id, quota_library_ids, manual_project_id)
                VALUES (%s, %s, %s::jsonb, %s)
                RETURNING id
                """,
                (name, body.boq_project_id, json.dumps(body.quota_library_ids or []), body.manual_project_id),
            )
            batch_id = cur.fetchone()[0]
        conn.commit()
        return {"id": batch_id}
    finally:
        conn.close()


@router.get("/pricing-task-batches/{batch_id}")
def get_pricing_task_batch(batch_id: int):
    from db.connection import get_connection

    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                _batch_select_sql()
                + """
                WHERE b.id=%s AND b.status <> 'deleted'
                GROUP BY b.id, p.project_name, mp.project_name
                """,
                (batch_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="batch not found")
            return _row_to_batch(row)
    finally:
        conn.close()


@router.delete("/pricing-task-batches/{batch_id}", status_code=204)
def delete_pricing_task_batch(batch_id: int):
    from db.connection import get_connection

    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("UPDATE pricing_task_batches SET status='deleted', updated_at=NOW() WHERE id=%s", (batch_id,))
        conn.commit()
    finally:
        conn.close()


@router.get("/pricing-task-batches/{batch_id}/items")
def get_pricing_task_batch_items(batch_id: int):
    from db.connection import get_connection

    conn = get_connection()
    try:
        _ensure_schema(conn)
        batch = get_pricing_task_batch(batch_id)
        project_id = int(batch["boq_project_id"])
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, item_code, item_name, item_description, unit, quantity, item_seq
                FROM boq_items
                WHERE project_id=%s
                ORDER BY item_seq NULLS LAST, id
                """,
                (project_id,),
            )
            items = [
                {
                    "id": r[0],
                    "item_code": r[1],
                    "item_name": r[2],
                    "item_description": r[3],
                    "unit": r[4],
                    "quantity": float(r[5]) if r[5] is not None else None,
                    "item_seq": r[6],
                    "project_id": project_id,
                }
                for r in cur.fetchall()
            ]
            cur.execute(
                """
                SELECT boq_item_id, id, status, code_check, feature_check, work_procedures,
                       quota_candidates, quota_match, evaluation, conversion_check,
                       coefficient_check, step_timings, error_message, created_at, finished_at,
                       reasoning_text, confirmed_results
                FROM pricing_task_batch_item_runs
                WHERE batch_id=%s
                ORDER BY created_at DESC, id DESC
                """,
                (batch_id,),
            )
            seen: set[int] = set()
            runs = []
            for r in cur.fetchall():
                item_id = int(r[0])
                if item_id in seen:
                    continue
                seen.add(item_id)
                runs.append(
                    {
                        "boq_item_id": item_id,
                        "run": {
                            "id": r[1],
                            "status": r[2],
                            "code_check": r[3],
                            "feature_check": r[4],
                            "work_procedures": r[5],
                            "quota_candidates": r[6],
                            "quota_match": r[7],
                            "evaluation": r[8],
                            "conversion_check": _hydrate_conversion_combo_resources(conn, r[9]),
                            "coefficient_check": r[10],
                            "step_timings": r[11],
                            "error_message": r[12],
                            "created_at": r[13],
                            "finished_at": r[14],
                            "reasoning_text": r[15],
                            "confirmed_results": r[16] or [],
                        },
                    }
                )
        return {"batch": batch, "items": items, "runs": runs}
    finally:
        conn.close()


def _load_batch_and_item(conn, batch_id: int, boq_item_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, boq_project_id, quota_library_ids, manual_project_id, status
            FROM pricing_task_batches
            WHERE id=%s AND status <> 'deleted'
            """,
            (batch_id,),
        )
        batch_row = cur.fetchone()
        if not batch_row:
            raise HTTPException(status_code=404, detail="batch not found")
        cur.execute(
            """
            SELECT id, item_code, item_name, item_description, unit, quantity, project_id
            FROM boq_items
            WHERE id=%s AND project_id=%s
            """,
            (boq_item_id, batch_row[2]),
        )
        item_row = cur.fetchone()
        if not item_row:
            raise HTTPException(status_code=404, detail="item not found in batch project")
    return (
        {
            "id": batch_row[0],
            "name": batch_row[1],
            "boq_project_id": batch_row[2],
            "quota_library_ids": batch_row[3] or [],
            "manual_project_id": batch_row[4],
            "status": batch_row[5],
        },
        {
            "id": item_row[0],
            "item_code": item_row[1],
            "item_name": item_row[2],
            "item_description": item_row[3],
            "unit": item_row[4],
            "quantity": float(item_row[5]) if item_row[5] is not None else None,
            "project_id": item_row[6],
        },
    )


def _create_or_reset_batch_item_run(conn, batch_id: int, boq_item: dict[str, Any]) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pricing_task_batch_item_runs(
                batch_id, boq_item_id, boq_project_id, status, started_at,
                reasoning_text, code_check, feature_check, work_procedures,
                quota_candidates, quota_match, evaluation, confirmed_results,
                conversion_check, coefficient_check, step_timings, error_message, finished_at
            )
            VALUES (%s, %s, %s, 'running', NOW(), '', NULL, NULL, NULL, NULL, NULL, NULL, '[]'::jsonb, NULL, NULL, '{}'::jsonb, NULL, NULL)
            ON CONFLICT (batch_id, boq_item_id) DO UPDATE SET
                status='running',
                started_at=NOW(),
                finished_at=NULL,
                reasoning_text='',
                code_check=NULL,
                feature_check=NULL,
                work_procedures=NULL,
                quota_candidates=NULL,
                quota_match=NULL,
                evaluation=NULL,
                confirmed_results='[]'::jsonb,
                conversion_check=NULL,
                coefficient_check=NULL,
                step_timings='{}'::jsonb,
                error_message=NULL
            RETURNING id
            """,
            (batch_id, boq_item["id"], boq_item["project_id"]),
        )
        item_run_id = cur.fetchone()[0]
        cur.execute(
            """
            UPDATE pricing_task_batches
            SET status='running',
                started_at=COALESCE(started_at, NOW()),
                selected_count=(SELECT COUNT(*) FROM pricing_task_batch_item_runs WHERE batch_id=%s),
                updated_at=NOW()
            WHERE id=%s
            """,
            (batch_id, batch_id),
        )
    conn.commit()
    return int(item_run_id)


def _refresh_batch_counts(conn, batch_id: int, finish_if_idle: bool = False) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE pricing_task_batches b
            SET selected_count = stats.total_count,
                completed_count = stats.completed_count,
                failed_count = stats.failed_count,
                status = CASE
                    WHEN %s AND stats.running_count = 0 THEN 'completed'
                    ELSE b.status
                END,
                finished_at = CASE
                    WHEN %s AND stats.running_count = 0 THEN COALESCE(b.finished_at, NOW())
                    ELSE b.finished_at
                END,
                updated_at = NOW()
            FROM (
                SELECT COUNT(*) AS total_count,
                       COUNT(*) FILTER (WHERE status IN ('confirmed', 'no_match', 'completed')) AS completed_count,
                       COUNT(*) FILTER (WHERE status = 'failed') AS failed_count,
                       COUNT(*) FILTER (WHERE status = 'running') AS running_count
                FROM pricing_task_batch_item_runs
                WHERE batch_id=%s
            ) stats
            WHERE b.id=%s
            """,
            (finish_if_idle, finish_if_idle, batch_id, batch_id),
        )
    conn.commit()


def _load_batch_item_run_context(conn, item_run_id: int) -> tuple[int, dict[str, Any], dict[str, Any], dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.id, r.batch_id, r.status, r.quota_match, r.confirmed_results,
                   r.conversion_check, i.id, i.item_code, i.item_name, i.item_description,
                   i.unit, i.quantity, i.project_id
            FROM pricing_task_batch_item_runs r
            JOIN boq_items i ON i.id = r.boq_item_id
            WHERE r.id=%s
            """,
            (item_run_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="batch item run not found")
    batch_id = int(row[1])
    batch_run = {
        "id": row[0],
        "batch_id": batch_id,
        "status": row[2],
        "quota_match": row[3] or {},
        "confirmed_results": row[4] or [],
        "conversion_check": row[5],
    }
    boq_item = {
        "run_id": row[0],
        "status": row[2],
        "id": row[6],
        "item_code": row[7],
        "item_name": row[8],
        "item_description": row[9] or "",
        "unit": row[10] or "",
        "quantity": float(row[11]) if row[11] is not None else None,
        "project_id": row[12],
    }
    matches = batch_run["quota_match"].get("matches", []) if isinstance(batch_run["quota_match"], dict) else []
    confirmed_items = _confirmed_items_from_matches(conn, matches)
    return batch_id, batch_run, boq_item, {"items": confirmed_items}


@router.post("/pricing-task-batches/{batch_id}/items/{boq_item_id}/run-stream")
def pricing_task_batch_run_item_stream(batch_id: int, boq_item_id: int):
    from db.connection import get_connection

    def generate():
        conn = get_connection()
        item_run_id = None
        try:
            _ensure_schema(conn)
            batch, boq_item = _load_batch_and_item(conn, batch_id, boq_item_id)
            item_run_id = _create_or_reset_batch_item_run(conn, batch_id, boq_item)
            yield _sse({"type": "run_started", "run_id": item_run_id})
            yield _sse({"type": "item_info", "item": boq_item})
            fields: dict[str, Any] = {}
            reasoning_text_parts: list[str] = []
            had_error = False
            for event_type, data in _stream_pricing_item(
                conn,
                boq_item,
                batch["quota_library_ids"],
                batch["manual_project_id"],
                None,
                None,
                persist_run=False,
                update_item_description=False,
            ):
                if event_type == "reasoning_token":
                    reasoning_text_parts.append(data)
                    yield _sse({"type": "reasoning_token", "token": data})
                elif event_type == "error":
                    had_error = True
                    yield _sse({"type": "error", "error": data})
                else:
                    if event_type == "code_check":
                        fields["code_check"] = data
                    elif event_type == "feature_check":
                        fields["feature_check"] = data
                    elif event_type == "quota_candidates":
                        fields["quota_candidates"] = data
                    elif event_type == "quota_match":
                        fields["quota_match"] = data
                    elif event_type == "evaluation":
                        fields["evaluation"] = data
                    elif event_type == "step_timing":
                        timings = dict(fields.get("step_timings") or {})
                        timings[str(data["step_no"])] = data
                        fields["step_timings"] = timings
                    yield _sse({"type": event_type, **data} if event_type != "evaluation" else {"type": "evaluation", "evaluation": data})
            quota_match = fields.get("quota_match") or {}
            matches = quota_match.get("matches", []) if isinstance(quota_match, dict) else []
            confirmed_results = _confirmed_results_from_matches(conn, matches)
            final_status = "no_match" if not matches else "completed"
            if had_error:
                final_status = "failed"
            _update_batch_item_run(
                conn,
                item_run_id,
                **fields,
                confirmed_results=confirmed_results,
                reasoning_text="".join(reasoning_text_parts),
                status=final_status,
                finished_at=datetime.now(),
            )
            _refresh_batch_counts(conn, batch_id, finish_if_idle=True)
            yield _sse({"type": "done", "run_id": item_run_id})
        except Exception as exc:
            if item_run_id:
                _update_batch_item_run(conn, item_run_id, status="failed", error_message=str(exc), finished_at=datetime.now())
                _refresh_batch_counts(conn, batch_id, finish_if_idle=True)
            print(f"[pricing-task] batch SSE error: {exc}", file=sys.stderr, flush=True)
            yield _sse({"type": "error", "error": str(exc)})
        finally:
            conn.close()

    return StreamingResponse(generate(), media_type="text/event-stream")


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
                       quota_match, evaluation, conversion_check, coefficient_check,
                       step_timings, error_message, created_at, finished_at, reasoning_text
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
                "conversion_check": _hydrate_conversion_combo_resources(conn, r[8]),
                "coefficient_check": r[9],
                "step_timings": r[10],
                "error_message": r[11],
                "created_at": r[12],
                "finished_at": r[13],
                "reasoning_text": r[14],
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
                       quota_candidates, quota_match, evaluation, conversion_check, coefficient_check,
                       step_timings, error_message, created_at, finished_at, reasoning_text
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
                    "conversion_check": _hydrate_conversion_combo_resources(conn, r[9]),
                    "coefficient_check": r[10],
                    "step_timings": r[11],
                    "error_message": r[12],
                    "created_at": r[13],
                    "finished_at": r[14],
                    "reasoning_text": r[15],
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


@router.post("/pricing-tasks/{task_id}/accuracy-report")
def generate_pricing_task_accuracy_report(task_id: int):
    from db.connection import get_connection

    conn = get_connection()
    try:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.id, t.name, t.boq_project_id, p.project_name, t.manual_project_id, mp.project_name
                FROM pricing_tasks t
                JOIN boq_projects p ON p.id = t.boq_project_id
                LEFT JOIN manual_boq_projects mp ON mp.id = t.manual_project_id
                WHERE t.id=%s AND t.status <> 'deleted'
                """,
                (task_id,),
            )
            task_row = cur.fetchone()
            if not task_row:
                raise HTTPException(status_code=404, detail="task not found")
            cur.execute(
                """
                SELECT DISTINCT ON (r.boq_item_id)
                       r.id, r.boq_item_id, r.quota_match, r.evaluation, r.conversion_check, r.coefficient_check,
                       i.item_code, i.item_name, i.item_description, i.unit, i.quantity
                FROM pricing_task_runs r
                JOIN boq_items i ON i.id = r.boq_item_id
                WHERE r.task_id=%s
                ORDER BY r.boq_item_id, r.created_at DESC, r.id DESC
                """,
                (task_id,),
            )
            rows = cur.fetchall()
        task = {
            "id": task_row[0],
            "name": task_row[1],
            "boq_project_id": task_row[2],
            "project_name": task_row[3],
            "manual_project_id": task_row[4],
            "manual_project_name": task_row[5],
        }
        items = []
        metrics = {
            "total_items": len(rows),
            "evaluated_item_count": 0,
            "exact_item_count": 0,
            "hit_count": 0,
            "missed_count": 0,
            "extra_count": 0,
            "manual_count": 0,
            "ai_count": 0,
            "hit_rate": None,
        }
        for row in rows:
            quota_match = row[2] if isinstance(row[2], dict) else {}
            evaluation = row[3] if isinstance(row[3], dict) else {}
            if "manual_quotas" in evaluation:
                metrics["evaluated_item_count"] += 1
                metrics["hit_count"] += int(evaluation.get("hit_count") or 0)
                metrics["missed_count"] += int(evaluation.get("missed_count") or 0)
                metrics["extra_count"] += int(evaluation.get("extra_count") or 0)
                metrics["manual_count"] += int(evaluation.get("manual_count") or 0)
                metrics["ai_count"] += int(evaluation.get("ai_count") or 0)
                if int(evaluation.get("manual_count") or 0) > 0 and int(evaluation.get("missed_count") or 0) == 0 and int(evaluation.get("extra_count") or 0) == 0:
                    metrics["exact_item_count"] += 1
            items.append(
                {
                    "run_id": row[0],
                    "boq_item_id": row[1],
                    "quota_match": quota_match,
                    "evaluation": evaluation,
                    "conversion_check": _hydrate_conversion_combo_resources(conn, row[4]) if isinstance(row[4], dict) else row[4],
                    "coefficient_check": row[5] if isinstance(row[5], dict) else row[5],
                    "item_code": row[6],
                    "item_name": row[7],
                    "item_description": row[8] or "",
                    "unit": row[9] or "",
                    "quantity": float(row[10]) if row[10] is not None else None,
                }
            )
        if metrics["evaluated_item_count"] == 0:
            raise HTTPException(status_code=400, detail="task has no evaluated pricing runs")
        if metrics["manual_count"] == 0:
            raise HTTPException(status_code=400, detail="task has no manual comparison data")
        metrics["hit_rate"] = round(metrics["hit_count"] / metrics["manual_count"], 4) if metrics["manual_count"] else None
        report = _generate_task_accuracy_report(task, items, metrics)
        with conn.cursor() as cur:
            cur.execute("UPDATE pricing_tasks SET accuracy_report=%s, updated_at=NOW() WHERE id=%s", (Json(report, dumps=_json_dumps), task_id))
        conn.commit()
        return report
    finally:
        conn.close()


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
                result = {"items": [], "issues": ["未找到已确认定额，无法进行组合换算。"]}
                yield _sse({"type": "combo_adjustment_rules", "items": []})
                _update_run(conn, run_id, conversion_check=result)
                yield _sse({"type": "conversion_check", "conversion_check": result})
                yield _sse({"type": "step_timing", **_finish_step_timing(conn, run_id, step_timings, 6, "组合换算", step_started_at, step_started_perf)})
                yield _sse({"type": "done", "run_id": run_id})
                return

            input_payload = {
                "boq_item": boq_item,
                "confirmed_quotas": confirmed_items,
                "combo_adjustment_rule_guide": COMBO_ADJUSTMENT_RULE_GUIDE,
            }
            context_text = _json_dumps(input_payload)
            system_prompt = build_system_prompt()
            combo_preview = _default_conversion_check(confirmed_items)
            yield _sse({"type": "combo_adjustment_rules", "items": combo_preview["items"]})
            if not any(item.get("adjustment_rules") for item in confirmed_items):
                result = _default_conversion_check(
                    confirmed_items,
                    "已确认定额均未查询到 tdek_tzhhs 组合定额规则。",
                    boq_item=boq_item,
                )
                _update_run(conn, run_id, conversion_check=result)
                yield _sse({"type": "conversion_check", "conversion_check": result})
                yield _sse({"type": "step_timing", **_finish_step_timing(conn, run_id, step_timings, 6, "组合换算", step_started_at, step_started_perf)})
                yield _sse({"type": "done", "run_id": run_id})
                return
            analysis_prompt = (
                "请对已人工确认的定额进行第六轮组合定额换算分析。先进行分析，不要调用工具，不要输出 JSON。\n"
                "本轮只允许使用输入中的 adjustment_rules（来自 tdek_tzhhs 并关联 tdek_tdezm）。\n"
                "请逐条基础定额、逐条组合规则判断：项目特征中是否存在与 prompt、combo_name 增减指标匹配的数量特征。\n"
                "若匹配，请提取数量特征原文和数值；不要自行输出材料替换、工料机调整或工程量系数调整。\n"
                "第六轮结果只作为组合定额次数建议，不允许修改已确认定额，也不要改写工程量系数。\n\n"
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
                "请严格调用 submit_conversion_check 提交第六轮结构化换算建议。\n"
                "必须覆盖每一条已确认定额。\n"
                "每个 item 的 adjustment_rules 必须覆盖输入中该定额的每一条组合规则；rule_index 必须与输入保持一致。\n"
                "只判断项目特征数量特征是否匹配 prompt/combo_name 的增减指标；匹配时 matched=true，并填写 matched_feature 和 feature_value。\n"
                "calculated_times 可按 (feature_value - base_value) / increment_unit 先填写，但后端会重新计算；小数保留，负数按 0 理解。\n"
                "不匹配时 matched=false，feature_value 和 calculated_times 填 0，并说明原因。\n"
                "不要输出工料机调整、材料替换、工程量系数调整或其他非组合定额规则。\n"
                "reason 写整体判断说明，missing_inputs 写缺失的数量特征或单位信息。\n"
                "confidence 只能是 high、medium、low。\n\n"
                f"【第六轮分析】\n{conversion_analysis or '（无分析文本）'}\n\n"
                f"【输入数据】\n{context_text}"
            )
            raw_result = _run_submit_conversion_check(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": submit_prompt},
                ]
            )
            result = _normalize_conversion_check(raw_result, confirmed_items, boq_item)
            _update_run(conn, run_id, conversion_check=result)
            yield _sse({"type": "conversion_check", "conversion_check": result})
            yield _sse({"type": "step_timing", **_finish_step_timing(conn, run_id, step_timings, 6, "组合换算", step_started_at, step_started_perf)})
            yield _sse({"type": "done", "run_id": run_id})
        except HTTPException as exc:
            yield _sse({"type": "error", "error": str(exc.detail)})
        except Exception as exc:
            print(f"[pricing-task] conversion check SSE error: {exc}", file=sys.stderr, flush=True)
            yield _sse({"type": "error", "error": str(exc)})
        finally:
            conn.close()

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/pricing-task-runs/{run_id}/coefficient-check-stream")
def pricing_task_coefficient_check_stream(run_id: int):
    from db.connection import get_connection

    def generate():
        conn = get_connection()
        try:
            _ensure_schema(conn)
            step_timings = _load_step_timings(conn, run_id)
            step_started_at = datetime.now()
            step_started_perf = perf_counter()
            boq_item, items = _coefficient_context(conn, run_id)
            yield _sse({"type": "coefficient_check_start", "run_id": run_id, "total": len(items)})
            preview = _default_coefficient_check(items)
            yield _sse({"type": "coefficient_rules", "items": preview["items"]})

            if not items:
                result = {"items": [], "issues": ["未找到已确认定额，无法进行系数换算。"]}
                _update_run(conn, run_id, coefficient_check=result)
                yield _sse({"type": "coefficient_check", "coefficient_check": result})
                yield _sse({"type": "step_timing", **_finish_step_timing(conn, run_id, step_timings, 7, "系数换算", step_started_at, step_started_perf)})
                yield _sse({"type": "done", "run_id": run_id})
                return

            if not any(item.get("coefficient_rules") for item in items):
                result = _default_coefficient_check(items, "所有定额均未查询到 tdek_tznhs 系数换算说明。")
                _update_run(conn, run_id, coefficient_check=result)
                yield _sse({"type": "coefficient_check", "coefficient_check": result})
                yield _sse({"type": "step_timing", **_finish_step_timing(conn, run_id, step_timings, 7, "系数换算", step_started_at, step_started_perf)})
                yield _sse({"type": "done", "run_id": run_id})
                return

            input_payload = {
                "boq_item": boq_item,
                "quotas": items,
                "rule_source": "tdek_tznhs.hssm",
                "target_resource_type_guide": {
                    "1": "人工费/人工消耗量",
                    "2": "材料费/材料消耗量",
                    "3": "机械费/机械消耗量",
                    "all": "子目或相应子目整体乘以系数",
                },
                "output_note": "本轮只保存系数和作用对象，不计算调整后含量。",
            }
            context_text = _json_dumps(input_payload)
            system_prompt = build_system_prompt()
            analysis_prompt = (
                "请进行第七轮系数换算分析。先分析，不要调用工具，不要输出 JSON。\n"
                "规则来源只允许使用输入中的 coefficient_rules（tdek_tznhs.hssm）。\n"
                "请逐条判断项目特征是否触发 hssm；触发时提取命中特征、特征值、系数和作用对象。\n"
                "作用对象按说明判断：人工费=1，材料费=2，机械消耗量/机械费=3，子目乘以系数/相应子目乘以系数=all。\n"
                "本轮不计算调整后含量，只说明哪些工料机行应显示乘以的系数。\n\n"
                f"【输入数据】\n{context_text}"
            )
            try:
                analysis = ""
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
                        analysis = data

                submit_prompt = (
                    "请严格调用 submit_coefficient_check 提交第七轮结构化系数换算判断。\n"
                    "必须覆盖输入中的每一条定额、每一条 coefficient_rules；rule_index 必须保持一致。\n"
                    "matched=true 时填写 matched_feature、feature_value、factor、target_resource_types 和 reason。\n"
                    "factor 从 hssm 中的“系数X”提取；如果未命中，matched=false，factor 仍填写 hssm 中可识别的系数或 1。\n"
                    "target_resource_types 只能使用 1、2、3、all；不要输出调整后数量。\n\n"
                    f"【第七轮分析】\n{analysis or '（无分析文本）'}\n\n"
                    f"【输入数据】\n{context_text}"
                )
                raw_result = _run_submit_coefficient_check(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": submit_prompt},
                    ]
                )
                result = _normalize_coefficient_check(raw_result, items)
            except Exception as exc:
                print(f"[pricing-task] coefficient model result fallback: {exc}", file=sys.stderr, flush=True)
                result = _default_coefficient_check(
                    items,
                    f"模型结构化输出解析失败，已保留系数换算说明待人工复核：{exc}",
                )
            _update_run(conn, run_id, coefficient_check=result)
            yield _sse({"type": "coefficient_check", "coefficient_check": result})
            yield _sse({"type": "step_timing", **_finish_step_timing(conn, run_id, step_timings, 7, "系数换算", step_started_at, step_started_perf)})
            yield _sse({"type": "done", "run_id": run_id})
        except HTTPException as exc:
            yield _sse({"type": "error", "error": str(exc.detail)})
        except Exception as exc:
            print(f"[pricing-task] coefficient check SSE error: {exc}", file=sys.stderr, flush=True)
            yield _sse({"type": "error", "error": str(exc)})
        finally:
            conn.close()

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/pricing-task-batch-item-runs/{item_run_id}/conversion-check-stream")
def pricing_task_batch_conversion_check_stream(item_run_id: int):
    from db.connection import get_connection

    def generate():
        conn = get_connection()
        try:
            _ensure_schema(conn)
            batch_id, batch_run, boq_item, context = _load_batch_item_run_context(conn, item_run_id)
            confirmed_items = context["items"]
            step_timings = _load_batch_step_timings(conn, item_run_id)
            step_started_at = datetime.now()
            step_started_perf = perf_counter()
            yield _sse({"type": "conversion_check_start", "run_id": item_run_id, "total": len(confirmed_items)})

            if not confirmed_items:
                result = {"items": [], "issues": ["未找到批量确认定额，无法进行组合换算。"]}
                yield _sse({"type": "combo_adjustment_rules", "items": []})
                _update_batch_item_run(conn, item_run_id, conversion_check=result)
                yield _sse({"type": "conversion_check", "conversion_check": result})
                yield _sse({"type": "step_timing", **_finish_batch_step_timing(conn, item_run_id, step_timings, 6, "组合换算", step_started_at, step_started_perf)})
                yield _sse({"type": "done", "run_id": item_run_id})
                return

            input_payload = {
                "boq_item": boq_item,
                "confirmed_quotas": confirmed_items,
                "combo_adjustment_rule_guide": COMBO_ADJUSTMENT_RULE_GUIDE,
            }
            context_text = _json_dumps(input_payload)
            system_prompt = build_system_prompt()
            combo_preview = _default_conversion_check(confirmed_items)
            yield _sse({"type": "combo_adjustment_rules", "items": combo_preview["items"]})
            if not any(item.get("adjustment_rules") for item in confirmed_items):
                result = _default_conversion_check(
                    confirmed_items,
                    "已确认定额均未查询到 tdek_tzhhs 组合定额规则。",
                    boq_item=boq_item,
                )
                _update_batch_item_run(conn, item_run_id, conversion_check=result)
                yield _sse({"type": "conversion_check", "conversion_check": result})
                yield _sse({"type": "step_timing", **_finish_batch_step_timing(conn, item_run_id, step_timings, 6, "组合换算", step_started_at, step_started_perf)})
                yield _sse({"type": "done", "run_id": item_run_id})
                return

            analysis_prompt = (
                "请对已确认的批量定额进行第六轮组合定额换算分析。先进行分析，不要调用工具，不要输出 JSON。\n"
                "本轮只允许使用输入中的 adjustment_rules（来自 tdek_tzhhs 并关联 tdek_tdezm）。\n"
                "请逐条基础定额、逐条组合规则判断：项目特征中是否存在与 prompt、combo_name 增减指标匹配的数量特征。\n"
                "若匹配，请提取数量特征原文和数值；不要自行输出材料替换、工料机调整或工程量系数调整。\n\n"
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
                "请严格调用 submit_conversion_check 提交第六轮结构化换算建议。\n"
                "必须覆盖每一条已确认定额。\n"
                "每个 item 的 adjustment_rules 必须覆盖输入中该定额的每一条组合规则；rule_index 必须与输入保持一致。\n"
                "只判断项目特征数量特征是否匹配 prompt/combo_name 的增减指标；匹配时 matched=true，并填写 matched_feature 和 feature_value。\n"
                "不匹配时 matched=false，feature_value 和 calculated_times 填 0，并说明原因。\n\n"
                f"【第六轮分析】\n{conversion_analysis or '（无分析文本）'}\n\n"
                f"【输入数据】\n{context_text}"
            )
            raw_result = _run_submit_conversion_check(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": submit_prompt},
                ]
            )
            result = _normalize_conversion_check(raw_result, confirmed_items, boq_item)
            _update_batch_item_run(conn, item_run_id, conversion_check=result)
            yield _sse({"type": "conversion_check", "conversion_check": result})
            yield _sse({"type": "step_timing", **_finish_batch_step_timing(conn, item_run_id, step_timings, 6, "组合换算", step_started_at, step_started_perf)})
            yield _sse({"type": "done", "run_id": item_run_id})
        except HTTPException as exc:
            yield _sse({"type": "error", "error": str(exc.detail)})
        except Exception as exc:
            print(f"[pricing-task] batch conversion check SSE error: {exc}", file=sys.stderr, flush=True)
            yield _sse({"type": "error", "error": str(exc)})
        finally:
            conn.close()

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/pricing-task-batch-item-runs/{item_run_id}/coefficient-check-stream")
def pricing_task_batch_coefficient_check_stream(item_run_id: int):
    from db.connection import get_connection

    def generate():
        conn = get_connection()
        try:
            _ensure_schema(conn)
            batch_id, batch_run, boq_item, context = _load_batch_item_run_context(conn, item_run_id)
            conversion_check = _hydrate_conversion_combo_resources(conn, batch_run.get("conversion_check") or {}) or {}
            items = _coefficient_items_from_context(conn, context["items"], conversion_check)
            step_timings = _load_batch_step_timings(conn, item_run_id)
            step_started_at = datetime.now()
            step_started_perf = perf_counter()
            yield _sse({"type": "coefficient_check_start", "run_id": item_run_id, "total": len(items)})
            preview = _default_coefficient_check(items)
            yield _sse({"type": "coefficient_rules", "items": preview["items"]})

            if not items:
                result = {"items": [], "issues": ["未找到批量确认定额，无法进行系数换算。"]}
                _update_batch_item_run(conn, item_run_id, coefficient_check=result, status="confirmed", finished_at=datetime.now())
                _refresh_batch_counts(conn, batch_id, finish_if_idle=True)
                yield _sse({"type": "coefficient_check", "coefficient_check": result})
                yield _sse({"type": "step_timing", **_finish_batch_step_timing(conn, item_run_id, step_timings, 7, "系数换算", step_started_at, step_started_perf)})
                yield _sse({"type": "done", "run_id": item_run_id})
                return

            if not any(item.get("coefficient_rules") for item in items):
                result = _default_coefficient_check(items, "所有定额均未查询到 tdek_tznhs 系数换算说明。")
                _update_batch_item_run(conn, item_run_id, coefficient_check=result, status="confirmed", finished_at=datetime.now())
                _refresh_batch_counts(conn, batch_id, finish_if_idle=True)
                yield _sse({"type": "coefficient_check", "coefficient_check": result})
                yield _sse({"type": "step_timing", **_finish_batch_step_timing(conn, item_run_id, step_timings, 7, "系数换算", step_started_at, step_started_perf)})
                yield _sse({"type": "done", "run_id": item_run_id})
                return

            input_payload = {
                "boq_item": boq_item,
                "quotas": items,
                "rule_source": "tdek_tznhs.hssm",
                "target_resource_type_guide": {
                    "1": "人工费/人工消耗量",
                    "2": "材料费/材料消耗量",
                    "3": "机械费/机械消耗量",
                    "all": "子目或相应子目整体乘以系数",
                },
                "output_note": "本轮只保存系数和作用对象，不计算调整后含量。",
            }
            context_text = _json_dumps(input_payload)
            system_prompt = build_system_prompt()
            analysis_prompt = (
                "请进行第七轮系数换算分析。先分析，不要调用工具，不要输出 JSON。\n"
                "规则来源只允许使用输入中的 coefficient_rules（tdek_tznhs.hssm）。\n"
                "请逐条判断项目特征是否触发 hssm；触发时提取命中特征、特征值、系数和作用对象。\n"
                "本轮不计算调整后含量，只说明哪些工料机行应显示乘以的系数。\n\n"
                f"【输入数据】\n{context_text}"
            )
            try:
                analysis = ""
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
                        analysis = data

                submit_prompt = (
                    "请严格调用 submit_coefficient_check 提交第七轮结构化系数换算判断。\n"
                    "必须覆盖输入中的每一条定额、每一条 coefficient_rules；rule_index 必须保持一致。\n"
                    "matched=true 时填写 matched_feature、feature_value、factor、target_resource_types 和 reason。\n"
                    "target_resource_types 只能使用 1、2、3、all；不要输出调整后数量。\n\n"
                    f"【第七轮分析】\n{analysis or '（无分析文本）'}\n\n"
                    f"【输入数据】\n{context_text}"
                )
                raw_result = _run_submit_coefficient_check(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": submit_prompt},
                    ]
                )
                result = _normalize_coefficient_check(raw_result, items)
            except Exception as exc:
                print(f"[pricing-task] batch coefficient model result fallback: {exc}", file=sys.stderr, flush=True)
                result = _default_coefficient_check(
                    items,
                    f"模型结构化输出解析失败，已保留系数换算说明待人工复核：{exc}",
                )
            _update_batch_item_run(conn, item_run_id, coefficient_check=result, status="confirmed", finished_at=datetime.now())
            _refresh_batch_counts(conn, batch_id, finish_if_idle=True)
            yield _sse({"type": "coefficient_check", "coefficient_check": result})
            yield _sse({"type": "step_timing", **_finish_batch_step_timing(conn, item_run_id, step_timings, 7, "系数换算", step_started_at, step_started_perf)})
            yield _sse({"type": "done", "run_id": item_run_id})
        except HTTPException as exc:
            yield _sse({"type": "error", "error": str(exc.detail)})
        except Exception as exc:
            print(f"[pricing-task] batch coefficient check SSE error: {exc}", file=sys.stderr, flush=True)
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
