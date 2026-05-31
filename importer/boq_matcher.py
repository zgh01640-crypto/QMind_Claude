"""
AI 套定额核心逻辑（KV Cache + Thinking + Tool calls）。

架构：
- system prompt = 角色设定 + 全量定额（固定不变，触发 KV Cache）
- user message = 每条清单项（每次变化）
- 模型：deepseek-v4-pro，thinking 模式，tool_choice="auto"
- 一次调用同时得到：reasoning_content（思维链）+ tool_calls（结构化匹配）
"""

import os
import json
from dataclasses import dataclass, field
from typing import Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_ROLE_DESC = """你是专业的建筑工程造价工程师，精通深圳市建筑工程消耗量标准（SJG 171-2024）。
你的任务是将招标工程量清单（BOQ）中的清单项与定额子目进行匹配（套定额）。

匹配规则：
1. 重点解读清单项的"项目特征描述"，从中提取材料规格、施工工艺、高度/深度区间等关键信息
2. 一条清单项可以对应多条定额子目（组合定额），也可以不套（返回空数组）
3. 必须考虑单位是否兼容，不兼容则填写换算系数
4. 优先选择与项目特征最吻合的定额变体（同名定额往往有多个变体）
5. 置信度：high=特征完全吻合，medium=基本符合，low=勉强对应
6. 只从下方定额库中选择，不要编造不存在的定额 ID"""


@dataclass
class MatchResult:
    quota_item_id: int
    quota_item_code: str
    quota_item_name: str
    quota_variant_desc: Optional[str]
    quota_unit: Optional[str]
    qty_factor: float
    reasoning: str           # 简短理由（来自 tool call）
    reasoning_chain: str     # 完整思维链（来自 reasoning_content）
    confidence: str          # high / medium / low
    cache_hit_tokens: int = 0  # 命中缓存的 token 数（用于监控）


_MATCH_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_matches",
        "description": "提交清单项套定额的匹配结果",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "matches": {
                    "type": "array",
                    "description": "匹配的定额子目列表，若无合适定额则返回空数组",
                    "items": {
                        "type": "object",
                        "properties": {
                            "quota_item_id": {
                                "type": "integer",
                                "description": "定额子目ID（必须是定额库中存在的ID）"
                            },
                            "qty_factor": {
                                "type": "number",
                                "description": "工程量换算系数，单位相同时为1.0"
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "选择该定额的理由，重点说明项目特征与定额的对应关系（2-3句）"
                            },
                            "confidence": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                                "description": "匹配置信度"
                            },
                        },
                        "required": ["quota_item_id", "qty_factor", "reasoning", "confidence"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["matches"],
            "additionalProperties": False,
        },
    },
}


# ── System prompt 构建（KV Cache 核心）──────────────────────────────────────

def build_system_prompt(conn, standard_id: int) -> str:
    """
    构建含全量定额的 system prompt。
    同一 standard_id 内容完全固定，DeepSeek 会自动缓存此前缀。
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, item_code, item_name, variant_desc, unit, work_content
            FROM quota_items
            WHERE standard_id = %s
            ORDER BY item_code
        """, (standard_id,))
        rows = cur.fetchall()

    quota_list = [
        {
            "id": r[0],
            "code": r[1],
            "name": r[2],
            "variant": r[3] or "",
            "unit": r[4] or "",
            "work_content": (r[5] or "")[:120],
        }
        for r in rows
    ]
    quota_json = json.dumps(quota_list, ensure_ascii=False, separators=(',', ':'))

    return f"""{_ROLE_DESC}

## 定额子目库（共 {len(rows)} 条，SJG 171-2024）

{quota_json}"""


# ── AI 匹配（单次调用）────────────────────────────────────────────────────────

def match_boq_item(boq_item: dict, system_prompt: str) -> list[MatchResult]:
    """
    对单条 BOQ 清单项套定额。

    boq_item: {id, item_code, item_name, item_description, unit, quantity}
    system_prompt: build_system_prompt() 构建的含全量定额的 prompt

    返回 list[MatchResult]，可能为空（定额库无对应子目时）。
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/beta")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)

    user_msg = f"""## 待套定额的清单项

- 项目编码：{boq_item.get('item_code', '')}
- 项目名称：{boq_item.get('item_name', '')}
- 计量单位：{boq_item.get('unit', '')}
- 工程量：{boq_item.get('quantity', '')}
- 项目特征描述：
{boq_item.get('item_description') or '（无）'}

请仔细解读上述项目特征描述，从定额库中选出最合适的子目，调用 submit_matches 函数返回结果。"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_msg},
        ],
        tools=[_MATCH_TOOL],
        tool_choice="auto",   # thinking 模式不支持强制 function，必须 auto
        extra_body={"thinking": {"type": "enabled"}},
        reasoning_effort="high",
        max_tokens=8000,
    )

    msg = response.choices[0].message
    reasoning_chain = getattr(msg, "reasoning_content", "") or ""
    cache_hit = getattr(response.usage, "prompt_cache_hit_tokens", 0) or 0

    # 解析 tool_calls
    if not msg.tool_calls:
        return []

    results = []
    for tc in msg.tool_calls:
        if tc.function.name != "submit_matches":
            continue
        try:
            raw = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            continue

        for m in raw.get("matches", []):
            qid = m.get("quota_item_id")
            if not qid:
                continue
            results.append(MatchResult(
                quota_item_id=int(qid),
                quota_item_code="",       # 由调用方从 DB 填充
                quota_item_name="",
                quota_variant_desc=None,
                quota_unit=None,
                qty_factor=float(m.get("qty_factor", 1.0)),
                reasoning=m.get("reasoning", ""),
                reasoning_chain=reasoning_chain,
                confidence=m.get("confidence", "medium"),
                cache_hit_tokens=cache_hit,
            ))

    return results


# ── 流式版本（streaming + thinking + tool_calls）────────────────────────────

def stream_match_boq_item(boq_item: dict, system_prompt: str):
    """
    流式版本：逐 token yield reasoning 内容，流结束后 yield 结构化匹配结果。

    yield 格式：
      ("reasoning_token", str)        — 思维链片段（逐 token）
      ("result", list[MatchResult])   — 最终匹配列表（流结束时一次性）
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/beta")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)

    user_msg = f"""## 待套定额的清单项

- 项目编码：{boq_item.get('item_code', '')}
- 项目名称：{boq_item.get('item_name', '')}
- 计量单位：{boq_item.get('unit', '')}
- 工程量：{boq_item.get('quantity', '')}
- 项目特征描述：
{boq_item.get('item_description') or '（无）'}

请仔细解读上述项目特征描述，从定额库中选出最合适的子目，调用 submit_matches 函数返回结果。"""

    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_msg},
        ],
        tools=[_MATCH_TOOL],
        tool_choice="auto",
        extra_body={"thinking": {"type": "enabled"}},
        reasoning_effort="high",
        max_tokens=8000,
        stream=True,
    )

    full_reasoning_parts: list[str] = []
    tool_call_args = ""

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        # 流式 reasoning_content（thinking 思维链）
        rc = getattr(delta, "reasoning_content", None)
        if rc:
            full_reasoning_parts.append(rc)
            yield ("reasoning_token", rc)

        # 工具调用参数（流式拼接）
        if delta.tool_calls:
            for tc in delta.tool_calls:
                if tc.function and tc.function.arguments:
                    tool_call_args += tc.function.arguments

    # 流结束，解析工具调用
    full_reasoning = "".join(full_reasoning_parts)
    results: list[MatchResult] = []

    if tool_call_args:
        try:
            raw = json.loads(tool_call_args)
            for m in raw.get("matches", []):
                qid = m.get("quota_item_id")
                if not qid:
                    continue
                results.append(MatchResult(
                    quota_item_id=int(qid),
                    quota_item_code="",
                    quota_item_name="",
                    quota_variant_desc=None,
                    quota_unit=None,
                    qty_factor=float(m.get("qty_factor", 1.0)),
                    reasoning=m.get("reasoning", ""),
                    reasoning_chain=full_reasoning,
                    confidence=m.get("confidence", "medium"),
                    cache_hit_tokens=0,
                ))
        except (json.JSONDecodeError, KeyError):
            pass

    yield ("result", results)

