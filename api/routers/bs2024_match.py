"""
新工程管理：基于 bs2024_* 定额库的套定额路由。

架构：
- 清单数据：boq_projects / boq_sections / boq_items（只读复用）
- 定额来源：bs2024_subitems + bs2024_* 表族
- 结果存储：bs2024_match_runs + bs2024_quota_matches（新建，独立于旧 boq_quota_matches）
- AI 引擎：DeepSeek v4-pro（thinking + tool_calls），与 boq_matcher.py 保持一致
"""

import os
import json
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from db.connection import get_connection
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()


# ── Schema 初始化 ─────────────────────────────────────────────────────────────

def _ensure_schema(conn):
    """确保 bs2024_match_runs / bs2024_quota_matches 表已存在。"""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bs2024_match_runs (
                id            SERIAL PRIMARY KEY,
                project_id    INT NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE,
                chapter_id    INT NOT NULL REFERENCES bs2024_chapters(id),
                chapter_name  VARCHAR(200),
                run_name      VARCHAR(200),
                status        VARCHAR(20) DEFAULT 'running',
                total_items   INT DEFAULT 0,
                matched_items INT DEFAULT 0,
                created_at    TIMESTAMP DEFAULT NOW(),
                finished_at   TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bs2024_quota_matches (
                id                 SERIAL PRIMARY KEY,
                run_id             INT NOT NULL REFERENCES bs2024_match_runs(id) ON DELETE CASCADE,
                boq_item_id        INT NOT NULL REFERENCES boq_items(id) ON DELETE CASCADE,
                subitem_id         INT NOT NULL REFERENCES bs2024_subitems(id),
                subitem_code       VARCHAR(50),
                work_procedure     VARCHAR(200),
                qty_factor         NUMERIC(10,4) DEFAULT 1.0,
                factor_explanation TEXT,
                ai_reasoning       TEXT,
                reasoning_chain    TEXT,
                confidence         VARCHAR(10),
                missing_info       TEXT,
                status             VARCHAR(20) DEFAULT 'ai',
                created_at         TIMESTAMP DEFAULT NOW(),
                UNIQUE (run_id, boq_item_id, subitem_id)
            )
        """)
    conn.commit()


# ── 定额上下文构建（KV Cache 核心）────────────────────────────────────────────

_ROLE_DESC_BS2024 = """你是专业的建筑工程造价工程师，精通深圳市建筑工程消耗量标准（SJG 171-2024）。
你的任务是将招标工程量清单（BOQ）中的清单项与{chapter_name}专业定额子目进行匹配（套定额）。
【重要】请全程使用中文进行推理和分析。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【推理步骤】

Step 1: 解析清单项目特征，识别材料品种/规格/施工工艺
Step 2: 将项目特征拆解为 1-3 条施工工序
Step 3: 对每条工序从定额子目列表中找最匹配的子目
Step 4: 计算 qty_factor（纯单位换算）
  清单m³ ÷ 定额10m³ = 0.1
  清单m³ ÷ 定额100m³ = 0.01
  清单m² ÷ 定额100m² = 0.01
  清单m ÷ 定额100m = 0.01
  单位相同 = 1.0
Step 5: 调用 submit_matches 输出结果

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【变体选择优先级】

1. 材料品种/规格完全匹配
2. 施工工艺匹配（湿拌 vs 干混；泵送 vs 非泵送）
3. 尺寸规格区间覆盖清单值
4. 单位相同或可换算

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【置信度标准】

- high：项目特征完整，与定额完全对应
- medium：主要特征匹配，但有次要特征未明确
- low：关键特征缺失，只能猜测

medium/low 时 missing_info 必须说明缺少哪些特征。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【返回空数组的情形】

- 该清单项不属于 {chapter_name} 专业范围
- 所有候选定额置信度均为 low 且工作内容匹配度低
- 清单单位无法与定额换算"""

_MATCH_TOOL_BS2024 = {
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
                            "subitem_id": {
                                "type": "integer",
                                "description": "定额子目ID（必须是子目列表中存在的ID）"
                            },
                            "subitem_code": {
                                "type": "string",
                                "description": "定额子目编码（如 010001-1）"
                            },
                            "qty_factor": {
                                "type": "number",
                                "description": "单位换算系数：清单单位÷定额单位，如m³÷10m³=0.1，单位相同=1.0"
                            },
                            "work_procedure": {
                                "type": "string",
                                "description": "此定额子目对应的施工工序名称"
                            },
                            "factor_explanation": {
                                "type": "string",
                                "description": "qty_factor 换算说明（如：清单m³÷定额10m³=0.1）"
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "选择该定额的理由（2-3句）"
                            },
                            "confidence": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                                "description": "匹配置信度"
                            },
                            "missing_info": {
                                "type": "string",
                                "description": "confidence 为 medium/low 时说明缺少哪些特征；high 时填空字符串"
                            },
                        },
                        "required": ["subitem_id", "subitem_code", "qty_factor", "work_procedure",
                                     "factor_explanation", "reasoning", "confidence", "missing_info"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["matches"],
            "additionalProperties": False,
        },
    },
}


def build_bs2024_system_prompt(conn, chapter_ids: int | list[int]) -> tuple[str, str]:
    """
    构建含专业定额上下文的 system prompt。
    支持单个或多个 chapter_id，多个时合并所有专业的说明和子目。
    返回 (chapter_name, system_prompt)
    """
    if isinstance(chapter_ids, int):
        chapter_ids = [chapter_ids]

    with conn.cursor() as cur:
        placeholders = ','.join(['%s'] * len(chapter_ids))

        # chapter titles
        cur.execute(f"SELECT id, title FROM bs2024_chapters WHERE id IN ({placeholders}) ORDER BY chapter_no", chapter_ids)
        chapters_rows = cur.fetchall()
        if not chapters_rows:
            raise ValueError(f"chapter_ids={chapter_ids} 不存在")
        chapter_name = " + ".join(r[1] for r in chapters_rows)

        # intro + rules content_md（所有章节合并）
        cur.execute(f"""
            SELECT c.title, s.section_type, s.content_md
            FROM bs2024_sections s
            JOIN bs2024_chapters c ON c.id = s.chapter_id
            WHERE s.chapter_id IN ({placeholders}) AND s.section_type IN ('intro', 'rules')
            ORDER BY c.chapter_no, s.section_type
        """, chapter_ids)
        sections_rows = cur.fetchall()

        # subitems（所有章节合并）
        cur.execute(f"""
            SELECT sub.id, sub.subitem_code, sub.name_path_json, sub.unit, sub.total_unit_price,
                   i.work_content
            FROM bs2024_sections sec
            JOIN bs2024_item_groups g ON g.section_id = sec.id
            JOIN bs2024_items i ON i.group_id = g.id
            JOIN bs2024_subitems sub ON sub.item_id = i.id
            WHERE sec.chapter_id IN ({placeholders}) AND sec.section_type = 'items'
            ORDER BY sec.chapter_id, sub.sort_order, sub.subitem_code
        """, chapter_ids)
        subitems = cur.fetchall()

    # 按章节分组拼接说明和规则
    from collections import defaultdict
    sec_by_chapter: dict[str, dict] = defaultdict(dict)
    for ch_title, sec_type, content_md in sections_rows:
        sec_by_chapter[ch_title][sec_type] = content_md or ""

    knowledge_blocks = []
    for _, ch_title in chapters_rows:
        secs = sec_by_chapter.get(ch_title, {})
        block = f"### {ch_title}"
        if secs.get("intro"):
            block += f"\n#### 专业说明\n{secs['intro']}"
        if secs.get("rules"):
            block += f"\n#### 工程量计算规则\n{secs['rules']}"
        knowledge_blocks.append(block)

    # 子目列表
    lines = []
    for sid, code, path_json, unit, price, work in subitems:
        if isinstance(path_json, list):
            path_str = " > ".join(path_json)
        else:
            try:
                path_str = " > ".join(json.loads(path_json))
            except Exception:
                path_str = str(path_json)
        price_str = f"{float(price):.2f}" if price is not None else "—"
        work_str = (work or "")[:80]
        lines.append(f"[ID:{sid}|{code}] {path_str} | 单位:{unit or '—'} | 全费用:{price_str} | {work_str}")

    subitem_text = "\n".join(lines)
    role = _ROLE_DESC_BS2024.replace("{chapter_name}", chapter_name)

    prompt = f"""{role}

## 专业定额知识库

{"".join(chr(10) + b for b in knowledge_blocks)}

## 定额子目列表（{chapter_name}，共 {len(subitems)} 条）

{subitem_text}

---（以上定额上下文结束）---"""

    return chapter_name, prompt


def _build_boq_user_msg(boq_item: dict) -> str:
    return f"""## 待套定额的清单项

- 项目编码：{boq_item.get('item_code', '')}
- 项目名称：{boq_item.get('item_name', '')}
- 计量单位：{boq_item.get('unit', '')}
- 工程量：{boq_item.get('quantity', '')}
- 项目特征描述：
{boq_item.get('item_description') or '（无）'}

请按推理步骤分析，调用 submit_matches 函数返回匹配结果。"""


def stream_match_bs2024_item(boq_item: dict, system_prompt: str):
    """
    流式匹配单条清单项。
    yield ("reasoning_token", str) 或 ("result", list[dict])
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
            {"role": "user",   "content": _build_boq_user_msg(boq_item)},
        ],
        tools=[_MATCH_TOOL_BS2024],
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

    results = []
    if tool_call_args:
        try:
            raw = json.loads(tool_call_args)
            results = raw.get("matches", [])
        except (json.JSONDecodeError, KeyError):
            pass

    yield ("result", results)


# ── API 端点 ──────────────────────────────────────────────────────────────────

@router.get("/bs2024-match/chapters")
def get_chapters():
    """可用专业列表（来自 bs2024_chapters）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.id, c.chapter_no, c.title,
                       COUNT(sub.id) as subitem_count
                FROM bs2024_chapters c
                JOIN bs2024_sections sec ON sec.chapter_id = c.id AND sec.section_type = 'items'
                JOIN bs2024_item_groups g ON g.section_id = sec.id
                JOIN bs2024_items i ON i.group_id = g.id
                JOIN bs2024_subitems sub ON sub.item_id = i.id
                GROUP BY c.id, c.chapter_no, c.title
                ORDER BY c.chapter_no
            """)
            rows = cur.fetchall()
        return [{"id": r[0], "chapter_no": r[1], "title": r[2], "subitem_count": r[3]} for r in rows]
    finally:
        conn.close()


@router.get("/bs2024-match/runs")
def get_runs(project_id: int = Query(...)):
    """工程的历史套定额批次列表。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, chapter_id, chapter_name, run_name, status,
                       total_items, matched_items, created_at, finished_at
                FROM bs2024_match_runs
                WHERE project_id = %s
                ORDER BY created_at DESC
            """, (project_id,))
            rows = cur.fetchall()
        return [
            {
                "id": r[0], "chapter_id": r[1], "chapter_name": r[2],
                "run_name": r[3], "status": r[4],
                "total_items": r[5], "matched_items": r[6],
                "created_at": r[7].isoformat() if r[7] else None,
                "finished_at": r[8].isoformat() if r[8] else None,
            }
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/bs2024-match/runs/{run_id}/matches")
def get_run_matches(run_id: int):
    """批次匹配结果（含子目信息）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT m.id, m.boq_item_id,
                       bi.item_code, bi.item_name, bi.unit AS boq_unit, bi.quantity,
                       bi.item_description,
                       m.subitem_id, m.subitem_code, m.work_procedure,
                       m.qty_factor, m.factor_explanation, m.ai_reasoning,
                       m.confidence, m.missing_info, m.status,
                       sub.total_unit_price, sub.unit AS quota_unit,
                       sub.name_path_json
                FROM bs2024_quota_matches m
                JOIN boq_items bi ON bi.id = m.boq_item_id
                JOIN bs2024_subitems sub ON sub.id = m.subitem_id
                WHERE m.run_id = %s
                ORDER BY bi.item_seq, m.id
            """, (run_id,))
            rows = cur.fetchall()

        result = {}
        for r in rows:
            bid = r[1]
            if bid not in result:
                result[bid] = {
                    "boq_item_id": bid,
                    "item_code": r[2], "item_name": r[3],
                    "boq_unit": r[4], "quantity": float(r[5]) if r[5] else None,
                    "item_description": r[6] or "",
                    "matches": [],
                }
            path_json = r[18]
            if isinstance(path_json, list):
                path_str = " > ".join(path_json)
            else:
                try:
                    path_str = " > ".join(json.loads(path_json))
                except Exception:
                    path_str = str(path_json)

            result[bid]["matches"].append({
                "match_id": r[0],
                "subitem_id": r[7], "subitem_code": r[8],
                "name_path": path_str,
                "work_procedure": r[9],
                "qty_factor": float(r[10]) if r[10] else 1.0,
                "factor_explanation": r[11],
                "ai_reasoning": r[12],
                "confidence": r[13], "missing_info": r[14],
                "status": r[15],
                "total_unit_price": float(r[16]) if r[16] else None,
                "quota_unit": r[17],
            })

        return list(result.values())
    finally:
        conn.close()


@router.get("/bs2024-match/subitems/{subitem_id}")
def get_subitem_detail(subitem_id: int):
    """子目详情：费用分解 + 工料机列表。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT sub.subitem_code, sub.name_path_json, sub.unit,
                       sub.total_unit_price, sub.unit_price,
                       sub.labor_cost, sub.material_cost, sub.machine_cost,
                       sub.management_fee, sub.profit, sub.safety_fee,
                       sub.statutory_fee, sub.tax,
                       i.work_content
                FROM bs2024_subitems sub
                JOIN bs2024_items i ON i.id = sub.item_id
                WHERE sub.id = %s
            """, (subitem_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "子目不存在")

            path_json = row[1]
            if isinstance(path_json, list):
                path_str = " > ".join(path_json)
            else:
                try:
                    path_str = " > ".join(json.loads(path_json))
                except Exception:
                    path_str = str(path_json)

            cur.execute("""
                SELECT resource_type, resource_name, unit, quantity, ref_price
                FROM bs2024_resources
                WHERE subitem_id = %s
                ORDER BY sort_order, resource_type
            """, (subitem_id,))
            resources = [
                {"resource_type": r[0], "resource_name": r[1],
                 "unit": r[2], "quantity": float(r[3]) if r[3] else None,
                 "ref_price": float(r[4]) if r[4] else None}
                for r in cur.fetchall()
            ]

        return {
            "subitem_code": row[0],
            "name_path": path_str,
            "unit": row[2],
            "total_unit_price": float(row[3]) if row[3] else None,
            "unit_price": float(row[4]) if row[4] else None,
            "labor_cost": float(row[5]) if row[5] else None,
            "material_cost": float(row[6]) if row[6] else None,
            "machine_cost": float(row[7]) if row[7] else None,
            "management_fee": float(row[8]) if row[8] else None,
            "profit": float(row[9]) if row[9] else None,
            "safety_fee": float(row[10]) if row[10] else None,
            "statutory_fee": float(row[11]) if row[11] else None,
            "tax": float(row[12]) if row[12] else None,
            "work_content": row[13] or "",
            "resources": resources,
        }
    finally:
        conn.close()


@router.put("/bs2024-match/matches/{match_id}")
def update_match_status(match_id: int, body: dict):
    """确认/拒绝/重置一条匹配。body: {status: 'confirmed'|'rejected'|'ai'}"""
    status = body.get("status", "ai")
    if status not in ("confirmed", "rejected", "ai"):
        raise HTTPException(400, "status 必须为 confirmed/rejected/ai")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bs2024_quota_matches SET status=%s WHERE id=%s RETURNING id",
                (status, match_id)
            )
            if not cur.fetchone():
                raise HTTPException(404, "match 不存在")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ── 流式套定额端点 ────────────────────────────────────────────────────────────

class MatchRunRequest(BaseModel):
    project_id: int
    chapter_id: int = 0          # 兼容旧调用，新调用用 chapter_ids
    chapter_ids: list[int] = []  # 多专业支持
    item_ids: list[int] = []
    run_name: str = ""


@router.post("/bs2024-match/runs/stream")
def start_match_stream(req: MatchRunRequest):
    """批量套定额（SSE 流式）。"""

    def generate():
        conn = get_connection()
        run_id = None
        try:
            _ensure_schema(conn)

            # 确定章节 ID 列表（支持多选）
            cids = req.chapter_ids if req.chapter_ids else ([req.chapter_id] if req.chapter_id else [])
            if not cids:
                yield f"data: {json.dumps({'type':'run_error','error':'未选择定额专业'}, ensure_ascii=False)}\n\n"
                return

            # 构建专业上下文（KV Cache）
            try:
                chapter_name, system_prompt = build_bs2024_system_prompt(conn, cids)
            except ValueError as e:
                yield f"data: {json.dumps({'type':'run_error','error':str(e)}, ensure_ascii=False)}\n\n"
                return

            # 获取清单项
            with conn.cursor() as cur:
                if req.item_ids:
                    placeholders = ','.join(['%s'] * len(req.item_ids))
                    cur.execute(f"""
                        SELECT id, item_code, item_name, item_description, unit, quantity
                        FROM boq_items
                        WHERE project_id = %s AND id IN ({placeholders})
                        ORDER BY item_seq
                    """, [req.project_id] + req.item_ids)
                else:
                    cur.execute("""
                        SELECT id, item_code, item_name, item_description, unit, quantity
                        FROM boq_items WHERE project_id = %s ORDER BY item_seq
                    """, (req.project_id,))
                items = cur.fetchall()

            total = len(items)
            if total == 0:
                yield f"data: {json.dumps({'type':'run_error','error':'无清单项'}, ensure_ascii=False)}\n\n"
                return

            # 创建批次记录
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bs2024_match_runs
                        (project_id, chapter_id, chapter_ids, chapter_name, run_name, status, total_items, matched_items)
                    VALUES (%s, %s, %s, %s, %s, 'running', %s, 0) RETURNING id
                """, (req.project_id, cids[0], json.dumps(cids), chapter_name,
                      req.run_name or None, total))
                run_id = cur.fetchone()[0]
            conn.commit()

            yield f"data: {json.dumps({'type':'run_start','run_id':run_id,'total':total,'chapter_name':chapter_name}, ensure_ascii=False)}\n\n"

            matched_count = 0
            for idx, (item_id, item_code, item_name, item_desc, unit, quantity) in enumerate(items):
                boq_item = {
                    "id": item_id,
                    "item_code": item_code or "",
                    "item_name": item_name or "",
                    "item_description": item_desc or "",
                    "unit": unit or "",
                    "quantity": str(quantity) if quantity is not None else "",
                }

                yield f"data: {json.dumps({'type':'item_start','index':idx+1,'total':total,'boq_item_id':item_id,'item_name':item_name}, ensure_ascii=False)}\n\n"

                raw_results = []
                try:
                    for event_type, data in stream_match_bs2024_item(boq_item, system_prompt):
                        if event_type == "reasoning_token":
                            yield f"data: {json.dumps({'type':'reasoning_token','token':data}, ensure_ascii=False)}\n\n"
                        elif event_type == "result":
                            raw_results = data
                except Exception as e:
                    yield f"data: {json.dumps({'type':'item_error','boq_item_id':item_id,'error':str(e)}, ensure_ascii=False)}\n\n"
                    continue

                # 写入匹配结果
                saved_matches = []
                with conn.cursor() as cur:
                    for m in raw_results:
                        sid = m.get("subitem_id")
                        if not sid:
                            continue
                        # 验证 subitem_id 存在
                        cur.execute("SELECT id FROM bs2024_subitems WHERE id=%s", (sid,))
                        if not cur.fetchone():
                            continue
                        try:
                            cur.execute("""
                                INSERT INTO bs2024_quota_matches
                                    (run_id, boq_item_id, subitem_id, subitem_code,
                                     work_procedure, qty_factor, factor_explanation,
                                     ai_reasoning, confidence, missing_info, status)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ai')
                                ON CONFLICT (run_id, boq_item_id, subitem_id) DO NOTHING
                                RETURNING id
                            """, (
                                run_id, item_id, sid,
                                m.get("subitem_code", ""),
                                m.get("work_procedure", ""),
                                float(m.get("qty_factor", 1.0)),
                                m.get("factor_explanation", ""),
                                m.get("reasoning", ""),
                                m.get("confidence", "medium"),
                                m.get("missing_info", ""),
                            ))
                            if cur.fetchone():
                                saved_matches.append({
                                    "subitem_id": sid,
                                    "subitem_code": m.get("subitem_code", ""),
                                    "work_procedure": m.get("work_procedure", ""),
                                    "confidence": m.get("confidence", "medium"),
                                    "qty_factor": float(m.get("qty_factor", 1.0)),
                                })
                        except Exception:
                            conn.rollback()
                            continue

                    if saved_matches:
                        matched_count += 1
                    cur.execute(
                        "UPDATE bs2024_match_runs SET matched_items=%s WHERE id=%s",
                        (matched_count, run_id)
                    )
                conn.commit()

                yield f"data: {json.dumps({'type':'item_done','boq_item_id':item_id,'matches':saved_matches}, ensure_ascii=False)}\n\n"

            # 完成
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE bs2024_match_runs SET status='done', matched_items=%s, finished_at=NOW() WHERE id=%s",
                    (matched_count, run_id)
                )
            conn.commit()
            yield f"data: {json.dumps({'type':'run_done','run_id':run_id,'total':total,'matched':matched_count}, ensure_ascii=False)}\n\n"

        except Exception as e:
            if run_id:
                try:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE bs2024_match_runs SET status='error' WHERE id=%s", (run_id,))
                    conn.commit()
                except Exception:
                    pass
            yield f"data: {json.dumps({'type':'run_error','error':str(e)}, ensure_ascii=False)}\n\n"
        finally:
            conn.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
