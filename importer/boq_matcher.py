"""
AI 套定额核心逻辑（KV Cache + Thinking + Tool calls）。

架构：
- system prompt = 角色设定 + 专业规则 + few-shot 示例 + 全量定额（固定不变，触发 KV Cache）
- user message = 每条清单项（每次变化）
- 模型：deepseek-v4-pro，thinking 模式，tool_choice="auto"
- 一次调用同时得到：reasoning_content（思维链）+ tool_calls（结构化匹配）
"""

import os
import json
from dataclasses import dataclass
from typing import Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_ROLE_DESC = """你是专业的建筑工程造价工程师，精通深圳市建筑工程消耗量标准（SJG 171-2024）。
你的任务是将招标工程量清单（BOQ）中的清单项与定额子目进行匹配（套定额）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【必须按以下步骤推理，不得跳过】

Step 1: 判断清单所属工种类别
  土方 / 砌筑 / 混凝土 / 钢筋 / 模板 / 屋面防水 / 脚手架 / 垂直运输 / 装饰 / 其他

Step 2: 检查定额库是否有对应章节
  当前定额库章节：__CHAPTER_LIST__
  → 若工种不在上述章节（如装饰等），直接返回空数组

Step 3: 将清单项目特征还原为施工工序序列（1-3条工序）

Step 4: 对每条工序，从定额库中找最匹配的子目和变体

Step 5: 计算 qty_factor（纯单位换算）
  清单m3 ÷ 定额10m3 = 0.1
  清单m3 ÷ 定额100m3 = 0.01
  清单m2 ÷ 定额100m2 = 0.01
  清单m ÷ 定额100m = 0.01
  清单t ÷ 定额t = 1.0（单位相同）
  其他单位相同 = 1.0

Step 6: 输出结果，调用 submit_matches

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【工序分解与组合定额规则】

■ 必须组合多条定额的情形：
  - 钢筋工程：含"制作、安装"描述 → 必须同时选制作子目 + 安装子目（两条）
  - 模板工程：支模高度 > 3.6m → 模板面积子目 + 对应高度的支撑架子目（两条）
  - 箍筋制作与安装：同上，制作与安装各一条

■ 只需一条定额的情形：
  - 砌体工程（砌块墙、砖墙、毛石墙等）
  - 混凝土浇筑（基础、柱、梁、板、楼梯等）
  - 屋面防水、保温工程
  - 脚手架、垂直运输等措施项目

■ 工序分解示例：
  "现浇构件钢筋（HRB400，φ8，非箍筋，制作安装）"
    → 工序①：带肋钢筋制作（直径≤10mm）  → 工序②：带肋钢筋安装

  "砌块墙（蒸压加气混凝土A7.5/B07，湿拌砂浆Ma5.0，H≤3.6m）"
    → 工序①：加气混凝土砌块墙砌筑（单一工序）

  "柱面模板（矩形柱，木模，支模高度3.6<H≤4.8m）"
    → 工序①：矩形柱模板安拆  → 工序②：梁板模板支撑架（3.6<H≤5m）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【变体选择优先级】

1. 材料品种/规格完全匹配（蒸压加气混凝土 vs 普通混凝土空心砌块）
2. 施工工艺匹配（湿拌砌筑砂浆 vs 干混砌筑砂浆；泵送 vs 非泵送）
3. 尺寸规格区间覆盖清单值（H≤3.6m、100＜T≤200、直径φ8属于≤10）
4. 单位相同或可换算

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【返回空数组的情形（宁缺毋滥）】

- 定额库无对应章节（土方、装饰等）
- 所有候选定额的置信度均为 low 且工作内容匹配度低
- 清单单位与定额单位无法换算（如"项"）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【参考示例——请严格对齐以下匹配模式】

▶ 示例1：单工序清单（砌筑）
  清单：砌块墙，m3，A7.5/B07蒸压加气混凝土，Ma5.0预拌砌筑砂浆，H≤3.6m
  正确输出：
    matches: [
      {quota_item_id: 514, qty_factor: 0.1, confidence: "high",
       work_procedure: "加气混凝土砌块墙砌筑",
       factor_explanation: "清单m3÷定额10m3=0.1",
       reasoning: "清单为蒸压加气混凝土砌块，砂浆为Ma5.0预拌砌筑砂浆属湿拌体系，与定额010001-34（湿拌砌筑砂浆）完全匹配"}
    ]

▶ 示例2：必须组合的钢筋工程（制作+安装）
  清单：现浇构件钢筋，t，HRB400带肋钢筋，φ8以内，非箍筋，制作安装
  正确输出：
    matches: [
      {quota_item_id: 593, qty_factor: 1.0, confidence: "high",
       work_procedure: "带肋钢筋制作",
       factor_explanation: "清单t=定额t，qty_factor=1.0",
       reasoning: "HRB400带肋钢筋，直径φ8属于直径≤10mm区间，非箍筋，制作工序"},
      {quota_item_id: 594, qty_factor: 1.0, confidence: "high",
       work_procedure: "带肋钢筋安装",
       factor_explanation: "清单t=定额t，qty_factor=1.0",
       reasoning: "制作对应的安装工序，必须组合"}
    ]

▶ 示例3：定额库无对应章节
  清单：外墙涂料，m2，水性外墙乳胶漆两遍
  正确输出：matches: []  （原因：当前定额库无装饰工程章节）

▶ 示例4：模板需组合支撑架
  清单：柱面模板，m2，矩形柱，木模，支模高度3.6<H≤4.8m
  正确输出：
    matches: [
      {quota_item_id: <矩形柱模板ID>, qty_factor: 0.01, confidence: "high",
       work_procedure: "矩形柱模板安拆",
       factor_explanation: "清单m2÷定额100m2=0.01"},
      {quota_item_id: <支撑架3.6-5m ID>, qty_factor: 1.0, confidence: "high",
       work_procedure: "模板支撑架搭拆",
       factor_explanation: "清单m3=定额m3，qty_factor=1.0"}
    ]"""


@dataclass
class MatchResult:
    quota_item_id: int
    quota_item_code: str
    quota_item_name: str
    quota_variant_desc: Optional[str]
    quota_unit: Optional[str]
    qty_factor: float
    reasoning: str            # 简短理由（来自 tool call）
    reasoning_chain: str      # 完整思维链（来自 reasoning_content）
    confidence: str           # high / medium / low
    work_procedure: str = ""  # 施工工序名称
    factor_explanation: str = ""  # qty_factor 换算说明
    cache_hit_tokens: int = 0


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
                                "description": "单位换算系数：清单单位÷定额单位，如m3÷10m3=0.1，m2÷100m2=0.01，单位相同=1.0"
                            },
                            "work_procedure": {
                                "type": "string",
                                "description": "此定额子目对应的施工工序名称（如：加气混凝土砌块墙砌筑、带肋钢筋制作、矩形柱模板安拆等）"
                            },
                            "factor_explanation": {
                                "type": "string",
                                "description": "qty_factor 换算说明（如：清单m3÷定额10m3=0.1；清单t=定额t=1.0）"
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "选择该定额的理由，说明项目特征与定额的对应关系（2-3句）"
                            },
                            "confidence": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                                "description": "匹配置信度：high=特征完全吻合，medium=基本符合，low=勉强对应"
                            },
                        },
                        "required": ["quota_item_id", "qty_factor", "work_procedure",
                                     "factor_explanation", "reasoning", "confidence"],
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
    章节列表从数据库动态获取，支持多套定额标准。
    """
    with conn.cursor() as cur:
        # 获取章节列表
        cur.execute("""
            SELECT code, name FROM quota_chapters
            WHERE standard_id = %s ORDER BY sort_order
        """, (standard_id,))
        chapters = cur.fetchall()

        # 获取全量子目
        cur.execute("""
            SELECT id, item_code, item_name, variant_desc, unit, work_content
            FROM quota_items
            WHERE standard_id = %s
            ORDER BY item_code
        """, (standard_id,))
        rows = cur.fetchall()

    # 动态生成章节说明
    chapter_lines = " / ".join(f"{name}({code})" for code, name in chapters)

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

    # 把动态章节注入到 _ROLE_DESC 的占位符
    role_desc = _ROLE_DESC.replace("__CHAPTER_LIST__", chapter_lines)

    return f"""{role_desc}

## 定额子目库（共 {len(rows)} 条）

{quota_json}"""


# ── 公共 user message 构造 ─────────────────────────────────────────────────

def _build_user_msg(boq_item: dict) -> str:
    return f"""## 待套定额的清单项

- 项目编码：{boq_item.get('item_code', '')}
- 项目名称：{boq_item.get('item_name', '')}
- 计量单位：{boq_item.get('unit', '')}
- 工程量：{boq_item.get('quantity', '')}
- 项目特征描述：
{boq_item.get('item_description') or '（无）'}

请按推理步骤分析，调用 submit_matches 函数返回结果。"""


def _parse_matches(raw_matches: list, reasoning_chain: str, cache_hit: int) -> list[MatchResult]:
    results = []
    for m in raw_matches:
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
            reasoning_chain=reasoning_chain,
            confidence=m.get("confidence", "medium"),
            work_procedure=m.get("work_procedure", ""),
            factor_explanation=m.get("factor_explanation", ""),
            cache_hit_tokens=cache_hit,
        ))
    return results


# ── AI 匹配（单次调用）────────────────────────────────────────────────────────

def match_boq_item(boq_item: dict, system_prompt: str) -> list[MatchResult]:
    """
    对单条 BOQ 清单项套定额（同步版本）。

    boq_item: {id, item_code, item_name, item_description, unit, quantity}
    system_prompt: build_system_prompt() 构建的含全量定额的 prompt
    返回 list[MatchResult]，可能为空。
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/beta")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": _build_user_msg(boq_item)},
        ],
        tools=[_MATCH_TOOL],
        tool_choice="auto",
        extra_body={"thinking": {"type": "enabled"}},
        reasoning_effort="high",
        max_tokens=8000,
    )

    msg = response.choices[0].message
    reasoning_chain = getattr(msg, "reasoning_content", "") or ""
    cache_hit = getattr(response.usage, "prompt_cache_hit_tokens", 0) or 0

    if not msg.tool_calls:
        return []

    for tc in msg.tool_calls:
        if tc.function.name == "submit_matches":
            try:
                raw = json.loads(tc.function.arguments)
                return _parse_matches(raw.get("matches", []), reasoning_chain, cache_hit)
            except (json.JSONDecodeError, KeyError):
                return []

    return []


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

    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": _build_user_msg(boq_item)},
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

        rc = getattr(delta, "reasoning_content", None)
        if rc:
            full_reasoning_parts.append(rc)
            yield ("reasoning_token", rc)

        if delta.tool_calls:
            for tc in delta.tool_calls:
                if tc.function and tc.function.arguments:
                    tool_call_args += tc.function.arguments

    full_reasoning = "".join(full_reasoning_parts)
    results: list[MatchResult] = []

    if tool_call_args:
        try:
            raw = json.loads(tool_call_args)
            results = _parse_matches(raw.get("matches", []), full_reasoning, 0)
        except (json.JSONDecodeError, KeyError):
            pass

    yield ("result", results)
