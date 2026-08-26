"""新版单条组价：独立任务/运行/结果表，试验合并式第五步。"""

from __future__ import annotations

import math
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
from time import perf_counter
from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from psycopg2.extras import Json

from api.auth import CurrentUser, current_user, require_project_owner
from api.routers import pricing_task as core
from api.services.model_profiles import bind_default_profile_iterator
from db.pricing_kb_versions import resolve_version_id

router = APIRouter(prefix="/pricing-task-v2")


def _require_task_owner(conn, user: CurrentUser, task_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT owner_user_id FROM pricing_task_v2_tasks WHERE id=%s AND status<>'deleted'", (task_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="新版单条组价任务不存在")
    if row[0] is None or int(row[0]) != int(user.id):
        raise HTTPException(status_code=403, detail="无权访问该新版单条组价任务")


def _require_run_owner(conn, user: CurrentUser, run_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT task_id FROM pricing_task_v2_runs WHERE id=%s", (run_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="新版运行记录不存在")
    _require_task_owner(conn, user, int(row[0]))


def _task_payload(row: Any) -> dict[str, Any]:
    return {
        "id": int(row[0]), "name": row[1], "boq_project_id": int(row[2]), "project_id": int(row[2]),
        "project_name": row[3], "manual_project_id": row[4], "manual_project_name": row[5],
        "quota_library_ids": list(row[6] or []), "quota_library_names": list(row[7] or []),
        "created_at": row[8], "latest_run_count": int(row[9] or 0), "accuracy_report": row[10],
        "kb_version_id": int(row[11]) if row[11] is not None else None,
        "consistency_rate": float(row[12]) if row[12] is not None else None,
        "pipeline": "combined_quota_match",
    }


def _task_select(where: str) -> str:
    return f"""
        SELECT t.id,t.name,t.boq_project_id,p.project_name,t.manual_project_id,mp.project_name,
               t.quota_library_ids,
               COALESCE(array_agg(l.mc ORDER BY l.id) FILTER (WHERE l.id IS NOT NULL),'{{}}'),
               t.created_at,(SELECT COUNT(*) FROM pricing_task_v2_runs r WHERE r.task_id=t.id),
               t.accuracy_report,t.kb_version_id,
               (SELECT ROUND(SUM(COALESCE((x.evaluation->>'hit_count')::numeric,0)) /
                    NULLIF(SUM(COALESCE((x.evaluation->>'manual_count')::numeric,0)),0),4)
                  FROM (SELECT DISTINCT ON (r.boq_item_id) r.evaluation FROM pricing_task_v2_runs r
                        WHERE r.task_id=t.id AND r.evaluation IS NOT NULL
                        ORDER BY r.boq_item_id,r.created_at DESC,r.id DESC) x)
        FROM pricing_task_v2_tasks t
        JOIN boq_projects p ON p.id=t.boq_project_id
        LEFT JOIN manual_boq_projects mp ON mp.id=t.manual_project_id
        LEFT JOIN LATERAL jsonb_array_elements_text(t.quota_library_ids) q(value) ON TRUE
        LEFT JOIN tlibs l ON l.kb_version_id=pricing_kb_data_version(t.kb_version_id,'TLibs') AND l.id=q.value::bigint
        WHERE {where}
        GROUP BY t.id,p.project_name,mp.project_name
    """


@router.get("/tasks")
def list_tasks(user: CurrentUser = Depends(current_user)):
    from db.connection import get_connection
    conn = get_connection()
    try:
        core._ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(_task_select("t.owner_user_id=%s AND t.status<>'deleted'") + " ORDER BY t.created_at DESC", (user.id,))
            return [_task_payload(row) for row in cur.fetchall()]
    finally:
        conn.close()


@router.post("/tasks")
def create_task(body: core.PricingTaskCreate, user: CurrentUser = Depends(current_user)):
    from db.connection import get_connection
    conn = get_connection()
    try:
        core._ensure_schema(conn)
        require_project_owner(conn, user, body.boq_project_id)
        kb_version_id = resolve_version_id(conn, body.kb_version_id)
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO pricing_task_v2_tasks
                (name,boq_project_id,quota_library_ids,manual_project_id,kb_version_id,owner_user_id)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                (body.name.strip(), body.boq_project_id, Json(body.quota_library_ids), body.manual_project_id, kb_version_id, user.id))
            task_id = int(cur.fetchone()[0])
        conn.commit()
        return {"id": task_id}
    finally:
        conn.close()


@router.get("/tasks/{task_id}")
def get_task(task_id: int, user: CurrentUser = Depends(current_user)):
    from db.connection import get_connection
    conn = get_connection()
    try:
        core._ensure_schema(conn); _require_task_owner(conn, user, task_id)
        with conn.cursor() as cur:
            cur.execute(_task_select("t.id=%s AND t.status<>'deleted'"), (task_id,))
            row = cur.fetchone()
        if not row:
            raise HTTPException(404, "新版单条组价任务不存在")
        return _task_payload(row)
    finally:
        conn.close()


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, user: CurrentUser = Depends(current_user)):
    from db.connection import get_connection
    conn = get_connection()
    try:
        core._ensure_schema(conn); _require_task_owner(conn, user, task_id)
        with conn.cursor() as cur:
            cur.execute("UPDATE pricing_task_v2_tasks SET status='deleted',updated_at=NOW() WHERE id=%s", (task_id,))
        conn.commit()
    finally:
        conn.close()


def _update_run(conn, run_id: int, **fields: Any) -> None:
    if not fields:
        return
    json_fields = {"code_check","feature_check","chapter_rule_check","work_procedures","quota_candidates","quota_match","evaluation","conversion_check","coefficient_check","step_timings","accuracy_report"}
    values = [Json(value, dumps=core._json_dumps) if key in json_fields else value for key, value in fields.items()]
    values.append(run_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE pricing_task_v2_runs SET {','.join(f'{key}=%s' for key in fields)} WHERE id=%s", values)
    conn.commit()


def _finish_timing(conn, run_id: int, timings: dict[str, Any], no: int, name: str, started: datetime, perf: float) -> dict[str, Any]:
    finished = datetime.now()
    item = {"step_no": no, "name": name, "duration_ms": int(round((perf_counter()-perf)*1000)),
            "started_at": started.isoformat(timespec="milliseconds"), "finished_at": finished.isoformat(timespec="milliseconds")}
    timings[str(no)] = item; _update_run(conn, run_id, step_timings=timings)
    return item


def _normalize_matches_v2(raw: Any, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    issues = [str(v).strip() for v in raw.get("issues", []) if isinstance(v, (str, int, float)) and str(v).strip()] if isinstance(raw.get("issues", []), list) else []
    allowed = {(int(c["dekid"]), int(c["dezmid"])): c for c in candidates}
    seen: set[tuple[int, int]] = set(); matches = []
    source = raw.get("matches", []) if isinstance(raw.get("matches", []), list) else []
    for index, value in enumerate(source):
        if not isinstance(value, dict):
            issues.append(f"第{index+1}条匹配结果格式无效，已忽略"); continue
        try:
            key = (int(value.get("dekid")), int(value.get("dezmid")))
        except (TypeError, ValueError):
            issues.append(f"第{index+1}条匹配结果缺少有效定额ID，已忽略"); continue
        if key in seen:
            continue
        candidate = allowed.get(key)
        if not candidate:
            issues.append(f"模型提交了候选外定额 {key[0]}/{key[1]}，已忽略"); continue
        seen.add(key)
        try:
            factor = float(value.get("qty_factor", 1))
            if not math.isfinite(factor) or factor <= 0:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            factor = 1.0; issues.append(f"定额{candidate.get('zmbh') or key[1]}工程量系数无效，已按1.0处理并需人工复核")
        confidence = value.get("confidence") if value.get("confidence") in {"high","medium","low"} else "low"
        matches.append({"dekid": key[0], "dezmid": key[1], "zmbh": candidate.get("zmbh"), "zmmc": candidate.get("zmmc"),
                        "dw": candidate.get("dw"), "library_name": candidate.get("library_name"), "chapter_name": candidate.get("chapter_name"),
                        "qty_factor": factor, "confidence": confidence, "match_reason": str(value.get("match_reason") or "").strip()})
    return {"matches": matches, "issues": list(dict.fromkeys(issues))}


def _combined_match_messages(system_prompt: str, boq_item: dict[str, Any], code_check: dict[str, Any], feature_result: dict[str, Any], chapter_rule_check: dict[str, Any], candidates_data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = candidates_data["candidates"]
    candidate_text = "\n".join(
        f"[{i+1}] dekid={c['dekid']} dezmid={c['dezmid']} 编码={c['zmbh']} 名称={c['zmmc']} 单位={c['dw']} 库={c['library_name']} 章节={c.get('chapter_name') or ''} 来源={'、'.join(c.get('source_tables') or [])}"
        + (f"\n    工作内容：{c['gznr']}" if c.get("gznr") else "") for i,c in enumerate(candidates))
    prompt = (
        "请对候选定额完成分析后，调用 submit_quota_match 提交最终结构化结果。不得输出候选外定额。\n"
        "提交前必须检查：候选逐项取舍、名称与工作内容覆盖、单位及纯工程量换算系数、是否需组合多条定额、"
        "章节规则是否落实、置信度与待复核问题。工程量系数必须为有限正数。\n\n"
        f"【清单项】\n编码：{boq_item['item_code']}\n名称：{boq_item['item_name']}\n项目特征：{boq_item.get('item_description') or '（未填写）'}\n单位：{boq_item.get('unit') or '无'}\n"
        f"【编码核查】{core._json_dumps(code_check)}\n【项目特征分析】{core._json_dumps(feature_result)}\n"
        f"【章节规则校验】{core._json_dumps(chapter_rule_check)}\n【候选定额（共{candidates_data['total']}条）】\n{candidate_text}"
    )
    return [{"role":"system","content":system_prompt},{"role":"user","content":prompt}]


def _stream_combined_match(messages: list[dict[str, Any]]) -> Iterable[tuple[str, Any]]:
    """V2-only forced streaming tool call with the legacy non-stream fallback."""
    last_error: Exception | None = None
    for attempt in range(core._MODEL_CALL_ATTEMPTS):
        raw = ""
        try:
            stream = core._client(thinking=True).chat.completions.create(
                model=core._model(), messages=messages, tools=[core._TOOL_SUBMIT_QUOTA_MATCH],
                tool_choice=core._required_tool_choice(core._TOOL_SUBMIT_QUOTA_MATCH),
                reasoning_effort="high", extra_body={"thinking":{"type":"enabled"}},
                max_tokens=8000, stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                token = (getattr(delta,"reasoning_content",None) or "") + (getattr(delta,"content",None) or "")
                if token:
                    yield "reasoning_token", token
                for tool_call in (delta.tool_calls or []):
                    if tool_call.function and tool_call.function.arguments:
                        raw += tool_call.function.arguments
            yield "tool_result", core._parse_json_object(raw)
            return
        except Exception as exc:
            if isinstance(exc, core.ModelRateLimitError):
                raise
            last_error = exc
            core._wait_before_model_retry(attempt, "v2 combined quota match", exc)
    try:
        yield "tool_result", core._run_tool_fallback(messages, core._TOOL_SUBMIT_QUOTA_MATCH, 8000)
    except Exception as exc:
        raise exc from last_error


def _collect_combined_match(messages: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Collect the model's original reasoning while keeping tool arguments separate."""
    reasoning: list[str] = []
    tool_result: dict[str, Any] = {}
    for event, data in _stream_combined_match(messages):
        if event == "reasoning_token":
            reasoning.append(str(data))
        elif event == "tool_result":
            tool_result = data
    return "".join(reasoning), tool_result


def _save_pending(conn, task_id: int, run_id: int, boq_item: dict[str, Any], match_result: dict[str, Any], evaluation: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM pricing_task_v2_results WHERE run_id=%s", (run_id,))
        for m in match_result.get("matches", []):
            cur.execute("""INSERT INTO pricing_task_v2_results
                (task_id,run_id,boq_item_id,boq_project_id,dezmid,dekid,subitem_code,subitem_name,qty_factor,confidence,ai_reasoning,match_reason,status,evaluation)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s)""",
                (task_id,run_id,boq_item["id"],boq_item["project_id"],m["dezmid"],m["dekid"],m.get("zmbh"),m.get("zmmc"),m.get("qty_factor",1),m.get("confidence"),m.get("match_reason"),m.get("match_reason"),Json(evaluation,dumps=core._json_dumps)))
    conn.commit()


def _stream_pricing_item_v2(conn, boq_item: dict[str, Any], quota_library_ids: list[int], manual_project_id: int | None, task_id: int, run_id: int, kb_version_id: int) -> Iterable[tuple[str, Any]]:
    system_prompt = core.build_system_prompt(); timings: dict[str, Any] = {}
    started=datetime.now(); perf=perf_counter()
    code_check=core.exec_check_item_code(conn,boq_item["item_code"],boq_item["item_name"],kb_version_id)
    yield "code_check",code_check; yield "judgment",{"is_consistent":code_check["is_consistent"],"reasoning":f"标准清单名称：{code_check['standard_name'] or '未找到'}"}
    _update_run(conn,run_id,code_check=code_check); yield "step_timing",_finish_timing(conn,run_id,timings,1,"编码核查",started,perf)

    started=datetime.now(); perf=perf_counter()
    feature_context=core._load_feature_default_context(conn,code_check.get("base_code") or core._base_code(boq_item["item_code"]),kb_version_id)
    messages=[{"role":"system","content":system_prompt},{"role":"user","content":
        "Analyze whether this BOQ item's feature description is sufficient for quota matching.\n\n"
        f"BOQ code: {boq_item['item_code']}\nBOQ name: {boq_item['item_name']}\nOriginal features: {boq_item.get('item_description') or 'not provided'}\nUnit: {boq_item.get('unit') or 'not provided'}\n\n"
        f"[Standard feature schema from TQDK_TQDXMTZ]\n{core._json_dumps(feature_context['feature_schema'])}\n\n[Native default candidates from TQDK_TQDXMTZ.DEFAULTTZMS]\n{core._json_dumps(feature_context['default_candidates'])}\n\n"
        "Evaluate every supplied native default candidate. Select only comprehensive, vague, or missing features; never overwrite an explicit value or invent defaults."}]
    raw_feature={}
    for event,data in core._stream_tool_call(messages,core._TOOL_SUBMIT_FEATURE_ANALYSIS,4000):
        if event=="reasoning_token": yield event,data
        else: raw_feature=data
    feature=core._normalize_feature_analysis_result(raw_feature,boq_item.get("item_description"),code_check.get("base_code") or core._base_code(boq_item["item_code"]),feature_context)
    if feature.get("default_fills") and feature.get("effective_description"): boq_item["item_description"]=str(feature["effective_description"]).strip()
    yield "feature_check",feature; _update_run(conn,run_id,feature_check=feature); yield "step_timing",_finish_timing(conn,run_id,timings,2,"项目特征",started,perf)

    started=datetime.now(); perf=perf_counter()
    chapter_context=core._load_chapter_rule_context(conn,code_check.get("base_code") or core._base_code(boq_item["item_code"]),kb_version_id,int(boq_item["project_id"]))
    if chapter_context["available"]:
        rule_messages=[{"role":"system","content":system_prompt},{"role":"user","content":
            "请按章节说明逐条识别当前清单命中的规则，不得编造规则。\n\n"
            f"【清单项】{core._json_dumps(boq_item)}\n【章节说明】{core._json_dumps(chapter_context['chapters'])}\n【工程清单索引】{core._json_dumps(chapter_context['project_items'])}"}]
        raw_rules={}
        for event,data in core._stream_tool_call(rule_messages,core._TOOL_SUBMIT_CHAPTER_RULE_CHECK,5000):
            if event=="reasoning_token": yield event,data
            else: raw_rules=data
        chapter=core._normalize_chapter_rule_check(raw_rules,chapter_context)
    else:
        chapter=core._normalize_chapter_rule_check({},chapter_context); chapter["issues"]=["未找到该清单对应的章节说明规则"]
    yield "chapter_rule_check",chapter; _update_run(conn,run_id,chapter_rule_check=chapter); yield "step_timing",_finish_timing(conn,run_id,timings,3,"章节规则校验",started,perf)

    started=datetime.now(); perf=perf_counter()
    candidates_data=core.exec_fetch_quota_candidates(conn,boq_item["item_code"],kb_version_id,quota_library_ids)
    yield "quota_candidates",candidates_data; _update_run(conn,run_id,quota_candidates=candidates_data); yield "step_timing",_finish_timing(conn,run_id,timings,4,"定额候选",started,perf)

    started=datetime.now(); perf=perf_counter(); candidates=candidates_data["candidates"]
    raw_match={"matches":[],"issues":["未找到候选定额子目"]}
    if candidates:
        yield "quota_match_started", {"message": "正在进行套定额分析，完成后将一次性展示原始推理。"}
        step5_reasoning, raw_match = _collect_combined_match(_combined_match_messages(system_prompt,boq_item,code_check,feature,chapter,candidates_data))
        yield "quota_match_reasoning", {"text": step5_reasoning, "available": bool(step5_reasoning.strip())}
    else:
        yield "quota_match_reasoning", {"text": "未找到候选定额，本步未调用匹配模型。", "available": False}
    match=_normalize_matches_v2(raw_match,candidates)
    try: chapter["validation"]=core._validate_chapter_rules(chapter,match["matches"])
    except core.ModelRateLimitError: raise
    except Exception as exc: chapter["validation"]={"validations":[],"issues":[f"章节规则最终校验失败：{exc}"],"status":"manual_review"}
    yield "chapter_rule_check",chapter; _update_run(conn,run_id,chapter_rule_check=chapter,quota_match=match)
    yield "quota_match",match; yield "step_timing",_finish_timing(conn,run_id,timings,5,"套定额结果",started,perf)

    started=datetime.now(); perf=perf_counter(); manual=core._manual_quotas(conn,manual_project_id,boq_item.get("item_code")); evaluation=core._evaluate(match["matches"],manual)
    _update_run(conn,run_id,evaluation=evaluation); _save_pending(conn,task_id,run_id,boq_item,match,evaluation)
    yield "evaluation",evaluation; yield "step_timing",_finish_timing(conn,run_id,timings,6,"人工对比",started,perf)


def _run_payload(conn, row: Any) -> dict[str, Any]:
    run_id=int(row[0])
    with conn.cursor() as cur:
        cur.execute("""SELECT dekid,dezmid,subitem_code,subitem_name,qty_factor,status,conversion_confirmed,conversion_note,
                       conversion_confirmed_at,conversion_resources,conversion_resource_changes
                       FROM pricing_task_v2_results WHERE run_id=%s AND status='confirmed' ORDER BY id""",(run_id,))
        confirmed=[{"dekid":int(r[0]),"dezmid":int(r[1]),"subitem_code":r[2] or "","subitem_name":r[3] or "","qty_factor":float(r[4] or 1),"status":r[5],
                    "conversion_confirmed":bool(r[6]),"conversion_note":r[7] or "","conversion_confirmed_at":r[8],"conversion_resources":r[9] or [],"conversion_resource_changes":r[10] or []} for r in cur.fetchall()]
    return {"id":run_id,"status":row[1],"code_check":row[2],"feature_check":row[3],"chapter_rule_check":row[4],"work_procedures":row[5],
            "quota_candidates":row[6],"quota_match":row[7],"evaluation":row[8],"conversion_check":row[9],"coefficient_check":row[10],"step_timings":row[11],
            "error_message":row[12],"created_at":row[13],"finished_at":row[14],"reasoning_text":row[15],"confirmed_results":confirmed,"kb_version_id":int(row[16]) if row[16] else None}


_RUN_COLUMNS="id,status,code_check,feature_check,chapter_rule_check,work_procedures,quota_candidates,quota_match,evaluation,conversion_check,coefficient_check,step_timings,error_message,created_at,finished_at,reasoning_text,kb_version_id"


@router.get("/tasks/{task_id}/items/{boq_item_id}/runs")
def list_item_runs(task_id:int,boq_item_id:int,user:CurrentUser=Depends(current_user)):
    from db.connection import get_connection
    conn=get_connection()
    try:
        core._ensure_schema(conn);_require_task_owner(conn,user,task_id)
        with conn.cursor() as cur: cur.execute(f"SELECT {_RUN_COLUMNS} FROM pricing_task_v2_runs WHERE task_id=%s AND boq_item_id=%s ORDER BY created_at DESC",(task_id,boq_item_id));rows=cur.fetchall()
        return [_run_payload(conn,row) for row in rows]
    finally: conn.close()


@router.get("/tasks/{task_id}/runs/latest")
def latest_runs(task_id:int,user:CurrentUser=Depends(current_user)):
    from db.connection import get_connection
    conn=get_connection()
    try:
        core._ensure_schema(conn);_require_task_owner(conn,user,task_id)
        with conn.cursor() as cur:
            cur.execute(f"SELECT DISTINCT ON (boq_item_id) boq_item_id,{_RUN_COLUMNS} FROM pricing_task_v2_runs WHERE task_id=%s ORDER BY boq_item_id,created_at DESC,id DESC",(task_id,));rows=cur.fetchall()
        return [{"boq_item_id":int(row[0]),"run":_run_payload(conn,row[1:])} for row in rows]
    finally: conn.close()


@router.post("/tasks/{task_id}/items/{boq_item_id}/run-stream")
def run_item(task_id:int,boq_item_id:int,user:CurrentUser=Depends(current_user)):
    from db.connection import get_connection
    def generate():
        conn=get_connection();run_id=None
        try:
            core._ensure_schema(conn);_require_task_owner(conn,user,task_id)
            with conn.cursor() as cur:
                cur.execute("SELECT boq_project_id,quota_library_ids,manual_project_id,kb_version_id FROM pricing_task_v2_tasks WHERE id=%s",(task_id,));task=cur.fetchone()
                cur.execute("SELECT id,item_code,item_name,item_description,unit,quantity,project_id FROM boq_items WHERE id=%s AND project_id=%s",(boq_item_id,task[0]));row=cur.fetchone()
                if not row: raise HTTPException(404,"清单项不属于该新版任务工程")
                boq={"id":row[0],"item_code":row[1],"item_name":row[2],"item_description":row[3],"unit":row[4],"quantity":float(row[5]) if row[5] is not None else None,"project_id":row[6]}
                cur.execute("INSERT INTO pricing_task_v2_runs(task_id,boq_item_id,boq_project_id,kb_version_id,status) VALUES(%s,%s,%s,%s,'running') RETURNING id",(task_id,boq_item_id,task[0],task[3]));run_id=int(cur.fetchone()[0])
            conn.commit();yield core._sse({"type":"run_started","run_id":run_id,"kb_version_id":int(task[3])});yield core._sse({"type":"item_info","item":boq})
            reasoning=[]
            for event,data in _stream_pricing_item_v2(conn,boq,list(task[1] or []),task[2],task_id,run_id,int(task[3])):
                if event=="reasoning_token": reasoning.append(data);yield core._sse({"type":event,"token":data})
                elif event=="quota_match_reasoning":
                    text=str(data.get("text") or "")
                    display=text or "本次模型工具调用未返回可展示的原始推理信息。"
                    reasoning.append(f"\n\n【第五步：套定额分析】\n{display}\n")
                    yield core._sse({"type":event,"text":text,"available":bool(data.get("available"))})
                elif event=="evaluation": yield core._sse({"type":event,"evaluation":data})
                else: yield core._sse({"type":event,**data})
            _update_run(conn,run_id,status="completed",reasoning_text="".join(reasoning),finished_at=datetime.now());yield core._sse({"type":"done","run_id":run_id})
        except Exception as exc:
            message=core._user_facing_model_error(exc)
            if run_id:_update_run(conn,run_id,status="failed",error_message=message,finished_at=datetime.now())
            yield core._sse({"type":"error","error":message})
        finally:conn.close()
    return StreamingResponse(bind_default_profile_iterator(user.id,generate(),business_type="pricing_task_v2",task_id=task_id),media_type="text/event-stream",headers={"Cache-Control":"no-cache, no-store, no-transform","X-Accel-Buffering":"no","Connection":"keep-alive"})


@router.post("/runs/{run_id}/confirm")
def confirm_run(run_id:int,body:core.ConfirmRunRequest,user:CurrentUser=Depends(current_user)):
    from db.connection import get_connection
    conn=get_connection()
    try:
        core._ensure_schema(conn);_require_run_owner(conn,user,run_id)
        with conn.cursor() as cur:
            cur.execute("SELECT task_id,boq_item_id,boq_project_id,kb_version_id FROM pricing_task_v2_runs WHERE id=%s",(run_id,));run=cur.fetchone()
            if body.results is not None:
                cur.execute("DELETE FROM pricing_task_v2_results WHERE run_id=%s",(run_id,))
                for m in body.results:
                    cur.execute("SELECT zmbh,zmmc FROM tdek_tdezm WHERE kb_version_id=pricing_kb_data_version(%s,'TDEK_TDEZM') AND dekid=%s AND id=%s",(run[3],m["dekid"],m["dezmid"]));q=cur.fetchone()
                    if not q: raise HTTPException(400,"quota item not found")
                    cur.execute("""INSERT INTO pricing_task_v2_results(task_id,run_id,boq_item_id,boq_project_id,dekid,dezmid,subitem_code,subitem_name,qty_factor,confidence,match_reason,ai_reasoning,status)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'confirmed')""",(run[0],run_id,run[1],run[2],m["dekid"],m["dezmid"],q[0],q[1],m.get("qty_factor",1),m.get("confidence","medium"),m.get("match_reason",""),m.get("match_reason","")))
            else:cur.execute("UPDATE pricing_task_v2_results SET status='confirmed',updated_at=NOW() WHERE run_id=%s",(run_id,))
            cur.execute("UPDATE pricing_task_v2_runs SET status='confirmed',finished_at=COALESCE(finished_at,NOW()) WHERE id=%s",(run_id,))
        conn.commit();return {"ok":True}
    finally:conn.close()


@router.post("/runs/{run_id}/reject")
def reject_run(run_id:int,user:CurrentUser=Depends(current_user)):
    from db.connection import get_connection
    conn=get_connection()
    try:
        core._ensure_schema(conn);_require_run_owner(conn,user,run_id)
        with conn.cursor() as cur:
            cur.execute("UPDATE pricing_task_v2_results SET status='rejected',updated_at=NOW() WHERE run_id=%s",(run_id,));cur.execute("UPDATE pricing_task_v2_runs SET status='rejected',finished_at=COALESCE(finished_at,NOW()) WHERE id=%s",(run_id,))
        conn.commit();return {"ok":True}
    finally:conn.close()


def _confirmed_context(conn, run_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT r.status,r.kb_version_id,r.feature_check,i.item_code,i.item_name,i.item_description,i.unit
                       FROM pricing_task_v2_runs r JOIN boq_items i ON i.id=r.boq_item_id WHERE r.id=%s""",(run_id,))
        row=cur.fetchone()
        if not row: raise HTTPException(404,"新版运行记录不存在")
        if row[0] != "confirmed": raise HTTPException(400,"run must be confirmed before conversion check")
        feature=row[2] if isinstance(row[2],dict) else {};description=str(feature.get("effective_description") or row[5] or "")
        boq={"run_id":run_id,"status":row[0],"kb_version_id":int(row[1]),"item_code":row[3],"item_name":row[4],"item_description":description,"original_item_description":row[5] or "","unit":row[6] or ""}
        cur.execute("SELECT dekid,dezmid,subitem_code,subitem_name,qty_factor,confidence,match_reason FROM pricing_task_v2_results WHERE run_id=%s AND status='confirmed' ORDER BY id",(run_id,))
        matches=[{"dekid":int(r[0]),"dezmid":int(r[1]),"zmbh":r[2],"zmmc":r[3],"qty_factor":float(r[4] or 1),"confidence":r[5],"match_reason":r[6]} for r in cur.fetchall()]
    return boq,core._confirmed_items_from_matches(conn,matches,int(row[1]),description)


@router.post("/runs/{run_id}/conversion-check-stream")
def conversion_check(run_id:int,user:CurrentUser=Depends(current_user)):
    from db.connection import get_connection
    def generate():
        conn=get_connection()
        try:
            core._ensure_schema(conn);_require_run_owner(conn,user,run_id);boq,items=_confirmed_context(conn,run_id)
            with conn.cursor() as cur:cur.execute("SELECT step_timings FROM pricing_task_v2_runs WHERE id=%s",(run_id,));timings=dict((cur.fetchone() or [{}])[0] or {})
            started=datetime.now();perf=perf_counter();yield core._sse({"type":"conversion_check_start","run_id":run_id,"total":len(items)});result=None
            for event,payload in core._batch_conversion_business_events(items,boq):
                if event=="conversion_check":result=payload["conversion_check"]
                yield core._sse({"type":event,**payload})
            result=result or {"items":[],"issues":["组合换算未生成结果"]};_update_run(conn,run_id,conversion_check=result)
            yield core._sse({"type":"step_timing",**_finish_timing(conn,run_id,timings,7,"组合换算",started,perf)});yield core._sse({"type":"done","run_id":run_id})
        except Exception as exc:yield core._sse({"type":"error","error":str(getattr(exc,"detail",exc))})
        finally:conn.close()
    return StreamingResponse(bind_default_profile_iterator(user.id,generate(),business_type="pricing_task_v2_conversion",run_id=run_id),media_type="text/event-stream")


@router.post("/runs/{run_id}/coefficient-check-stream")
def coefficient_check(run_id:int,user:CurrentUser=Depends(current_user)):
    from db.connection import get_connection
    def generate():
        conn=get_connection()
        try:
            core._ensure_schema(conn);_require_run_owner(conn,user,run_id);boq,confirmed=_confirmed_context(conn,run_id)
            with conn.cursor() as cur:cur.execute("SELECT conversion_check,step_timings FROM pricing_task_v2_runs WHERE id=%s",(run_id,));row=cur.fetchone()
            items=core._coefficient_items_from_context(conn,confirmed,row[0] or {},int(boq["kb_version_id"]));timings=dict(row[1] or {});started=datetime.now();perf=perf_counter();yield core._sse({"type":"coefficient_check_start","run_id":run_id,"total":len(items)});result=None
            for event,payload in core._batch_coefficient_business_events(items,boq):
                if event=="coefficient_check":result=payload["coefficient_check"]
                yield core._sse({"type":event,**payload})
            result=result or {"items":[],"issues":["系数换算未生成结果"]};_update_run(conn,run_id,coefficient_check=result)
            yield core._sse({"type":"step_timing",**_finish_timing(conn,run_id,timings,8,"系数换算",started,perf)});yield core._sse({"type":"done","run_id":run_id})
        except Exception as exc:yield core._sse({"type":"error","error":str(getattr(exc,"detail",exc))})
        finally:conn.close()
    return StreamingResponse(bind_default_profile_iterator(user.id,generate(),business_type="pricing_task_v2_coefficient",run_id=run_id),media_type="text/event-stream")


@router.post("/runs/{run_id}/conversion-confirm")
def conversion_confirm(run_id:int,body:core.ConversionConfirmRequest,user:CurrentUser=Depends(current_user)):
    from db.connection import get_connection
    if not body.items:raise HTTPException(400,"conversion items required")
    conn=get_connection()
    try:
        core._ensure_schema(conn);_require_run_owner(conn,user,run_id)
        with conn.cursor() as cur:
            for item in body.items:
                try:dekid=int(item.get("dekid"));dezmid=int(item.get("dezmid"));factor=float(item.get("confirmed_qty_factor",item.get("qty_factor",1)))
                except Exception as exc:raise HTTPException(400,"invalid conversion item") from exc
                if not math.isfinite(factor) or factor<=0:raise HTTPException(400,"confirmed_qty_factor must be positive")
                resources=item.get("conversion_resources",item.get("resources",[]));changes=item.get("conversion_resource_changes",item.get("resource_changes",[]))
                cur.execute("""UPDATE pricing_task_v2_results SET qty_factor=%s,conversion_confirmed=TRUE,conversion_note=%s,conversion_confirmed_at=NOW(),conversion_resources=%s,conversion_resource_changes=%s,updated_at=NOW()
                    WHERE run_id=%s AND dekid=%s AND dezmid=%s AND status='confirmed'""",(factor,item.get("conversion_note","") or "",Json(resources,dumps=core._json_dumps),Json(changes,dumps=core._json_dumps),run_id,dekid,dezmid))
                if cur.rowcount==0:raise HTTPException(400,f"confirmed quota not found: {dekid}/{dezmid}")
        conn.commit();return {"ok":True}
    finally:conn.close()


def _detail_report(conn,task_id:int)->dict[str,Any]:
    with conn.cursor() as cur:
        cur.execute("""SELECT t.id,t.name,t.boq_project_id,p.project_name,t.manual_project_id,mp.project_name,t.quota_library_ids
                       FROM pricing_task_v2_tasks t JOIN boq_projects p ON p.id=t.boq_project_id LEFT JOIN manual_boq_projects mp ON mp.id=t.manual_project_id WHERE t.id=%s AND t.status<>'deleted'""",(task_id,));t=cur.fetchone()
        if not t:raise HTTPException(404,"新版任务不存在")
        cur.execute("""SELECT DISTINCT ON(r.boq_item_id) r.id,r.boq_item_id,r.status,r.code_check,r.feature_check,r.chapter_rule_check,r.quota_candidates,r.quota_match,r.evaluation,r.conversion_check,r.coefficient_check,r.step_timings,r.reasoning_text,r.created_at,r.finished_at,
                       i.item_code,i.item_name,i.item_description,i.unit,i.quantity,i.item_seq FROM pricing_task_v2_runs r JOIN boq_items i ON i.id=r.boq_item_id WHERE r.task_id=%s ORDER BY r.boq_item_id,r.created_at DESC,r.id DESC""",(task_id,));rows=cur.fetchall()
    task={"id":t[0],"name":t[1],"boq_project_id":t[2],"project_name":t[3],"manual_project_id":t[4],"manual_project_name":t[5],"quota_library_ids":t[6] or [],"report_kind":"single_v2"}
    return core._build_pricing_task_detail_report(conn,task,rows)


@router.get("/tasks/{task_id}/detail-report")
def detail_report(task_id:int,user:CurrentUser=Depends(current_user)):
    from db.connection import get_connection
    conn=get_connection()
    try:core._ensure_schema(conn);_require_task_owner(conn,user,task_id);return _detail_report(conn,task_id)
    finally:conn.close()


@router.get("/tasks/{task_id}/detail-report/export")
def export_detail_report(task_id:int,user:CurrentUser=Depends(current_user)):
    from db.connection import get_connection
    conn=get_connection()
    try:core._ensure_schema(conn);_require_task_owner(conn,user,task_id);report=_detail_report(conn,task_id)
    finally:conn.close()
    stream=core._build_pricing_task_detail_report_excel(report);name=str((report.get("task") or {}).get("name") or f"v2-{task_id}");safe=re.sub(r'[\\/:*?"<>|]+','_',name).strip() or f"v2-{task_id}"
    return StreamingResponse(stream,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f"attachment; filename*=UTF-8''{quote(f'新版单条组价明细报表-{safe}.xlsx')}"})


@router.post("/tasks/{task_id}/accuracy-report")
def accuracy_report(task_id:int,user:CurrentUser=Depends(current_user)):
    from db.connection import get_connection
    conn=get_connection()
    try:
        core._ensure_schema(conn);_require_task_owner(conn,user,task_id)
        with conn.cursor() as cur:
            cur.execute("SELECT t.id,t.name,t.boq_project_id,p.project_name,t.manual_project_id,mp.project_name FROM pricing_task_v2_tasks t JOIN boq_projects p ON p.id=t.boq_project_id LEFT JOIN manual_boq_projects mp ON mp.id=t.manual_project_id WHERE t.id=%s",(task_id,));t=cur.fetchone()
            cur.execute("""SELECT DISTINCT ON(r.boq_item_id) r.id,r.boq_item_id,r.quota_match,r.evaluation,r.conversion_check,r.coefficient_check,i.item_code,i.item_name,i.item_description,i.unit,i.quantity
                           FROM pricing_task_v2_runs r JOIN boq_items i ON i.id=r.boq_item_id WHERE r.task_id=%s ORDER BY r.boq_item_id,r.created_at DESC,r.id DESC""",(task_id,));rows=cur.fetchall()
        task={"id":t[0],"name":t[1],"boq_project_id":t[2],"project_name":t[3],"manual_project_id":t[4],"manual_project_name":t[5]};items=[];metrics={"total_items":len(rows),"evaluated_item_count":0,"exact_item_count":0,"hit_count":0,"missed_count":0,"extra_count":0,"manual_count":0,"ai_count":0,"hit_rate":None}
        for row in rows:
            match=row[2] if isinstance(row[2],dict) else {};evaluation=core._evaluate(match.get("matches",[]),core._manual_quotas(conn,t[4],row[6]))
            metrics["evaluated_item_count"]+=1
            for key in ("hit_count","missed_count","extra_count","manual_count","ai_count"):metrics[key]+=int(evaluation.get(key) or 0)
            if int(evaluation.get("manual_count") or 0)>0 and not int(evaluation.get("missed_count") or 0) and not int(evaluation.get("extra_count") or 0):metrics["exact_item_count"]+=1
            items.append({"run_id":row[0],"boq_item_id":row[1],"quota_match":match,"evaluation":evaluation,"conversion_check":row[4],"coefficient_check":row[5],"item_code":row[6],"item_name":row[7],"item_description":row[8] or "","unit":row[9] or "","quantity":float(row[10]) if row[10] is not None else None})
        if not metrics["evaluated_item_count"]:raise HTTPException(400,"task has no evaluated pricing runs")
        if not metrics["manual_count"]:raise HTTPException(400,"task has no manual comparison data")
        metrics["hit_rate"]=round(metrics["hit_count"]/metrics["manual_count"],4);report=core._generate_task_accuracy_report(task,items,metrics)
        with conn.cursor() as cur:cur.execute("UPDATE pricing_task_v2_tasks SET accuracy_report=%s,updated_at=NOW() WHERE id=%s",(Json(report,dumps=core._json_dumps),task_id))
        conn.commit();return report
    finally:conn.close()


def _manual_review_context(conn,run_id:int)->dict[str,Any]:
    with conn.cursor() as cur:
        cur.execute("""SELECT r.id,r.task_id,r.quota_match,t.manual_project_id,i.item_code,r.boq_item_id FROM pricing_task_v2_runs r JOIN pricing_task_v2_tasks t ON t.id=r.task_id JOIN boq_items i ON i.id=r.boq_item_id WHERE r.id=%s AND t.status<>'deleted' FOR UPDATE OF r""",(run_id,));row=cur.fetchone()
    if not row:raise HTTPException(404,"新版运行记录不存在")
    if not row[3]:raise HTTPException(400,"新版任务未配置人工对比工程")
    return {"run_id":int(row[0]),"task_id":int(row[1]),"quota_match":row[2] if isinstance(row[2],dict) else {},"manual_project_id":int(row[3]),"item_code":row[4],"boq_item_id":int(row[5])}


def _review_payload(row:Any)->dict[str,Any]:
    return {"id":int(row[0]),"source_type":"v2","source_run_id":int(row[1]),"manual_project_id":int(row[2]),"manual_item_id":int(row[3]),"before_manual_quotas":row[4] or [],"after_manual_quotas":row[5] or [],"before_evaluation":row[6] or {},"after_evaluation":row[7] or {},"retained_manual_quota_ids":row[8] or [],"accepted_ai_quotas":row[9] or [],"operator_name":row[10] or "系统","created_at":row[11]}


@router.get("/runs/{run_id}/manual-comparison-history")
def manual_history(run_id:int,user:CurrentUser=Depends(current_user)):
    from db.connection import get_connection
    conn=get_connection()
    try:
        core._ensure_schema(conn);_require_run_owner(conn,user,run_id)
        with conn.cursor() as cur:cur.execute("SELECT id,run_id,manual_project_id,manual_item_id,before_manual_quotas,after_manual_quotas,before_evaluation,after_evaluation,retained_manual_quota_ids,accepted_ai_quotas,operator_name,created_at FROM pricing_task_v2_manual_comparison_reviews WHERE run_id=%s ORDER BY created_at DESC,id DESC",(run_id,));return [_review_payload(row) for row in cur.fetchall()]
    finally:conn.close()


@router.put("/runs/{run_id}/manual-comparison")
def update_manual_comparison(run_id:int,body:core.ManualComparisonUpdateRequest,user:CurrentUser=Depends(current_user)):
    from db.connection import get_connection
    conn=get_connection()
    try:
        core._ensure_schema(conn);_require_run_owner(conn,user,run_id);context=_manual_review_context(conn,run_id);matches=context["quota_match"].get("matches",[]);ai={(int(x["dekid"]),int(x["dezmid"])):x for x in matches if x.get("dekid") is not None and x.get("dezmid") is not None};code=str(context["item_code"] or "").strip().replace(" ","")
        with conn.cursor() as cur:
            cur.execute("SELECT id,quantity FROM manual_boq_items WHERE project_id=%s AND replace(trim(COALESCE(item_code,'')),' ','')=%s ORDER BY id FOR UPDATE",(context["manual_project_id"],code));manual_items=cur.fetchall()
            if len(manual_items)!=1:raise HTTPException(404 if not manual_items else 409,"manual comparison item not found" if not manual_items else "duplicate item codes")
            manual_item_id,manual_quantity=manual_items[0];before=core._manual_quotas(conn,context["manual_project_id"],context["item_code"]);before_eval=core._evaluate(matches,before);by_id={int(x["id"]):x for x in before};retained={int(x) for x in body.retained_manual_quota_ids};requested={(x.dekid,x.dezmid) for x in body.accepted_ai_quotas}
            if retained-set(by_id):raise HTTPException(400,"manual quota does not belong to this item")
            if requested-set(ai):raise HTTPException(400,"AI quota does not belong to this run")
            locked={int(x["id"]) for x in before if any(str(a.get("zmbh") or "") and str(a.get("zmbh") or "") in str(x.get("quota_code") or "") for a in matches)}
            if not locked.issubset(retained):raise HTTPException(400,"consistent manual quotas must be retained")
            if retained:cur.execute("DELETE FROM manual_boq_quotas WHERE boq_item_id=%s AND NOT(id=ANY(%s))",(manual_item_id,list(retained)))
            else:cur.execute("DELETE FROM manual_boq_quotas WHERE boq_item_id=%s",(manual_item_id,))
            retained_codes=[str(by_id[x].get("quota_code") or "") for x in retained]
            for key in requested:
                item=ai[key];quota_code=str(item.get("zmbh") or "").strip()
                if not quota_code or any(quota_code in value for value in retained_codes):continue
                try:factor=Decimal(str(item.get("qty_factor",1)))
                except (InvalidOperation,ValueError) as exc:raise HTTPException(400,"invalid AI quota factor") from exc
                if not factor.is_finite() or factor<=0:raise HTTPException(400,"AI quota factor must be positive")
                quantity=Decimal(manual_quantity)*factor if manual_quantity is not None else None
                cur.execute("INSERT INTO manual_boq_quotas(boq_item_id,quota_code,quota_name,quota_unit,quantity,unit_price,total_price,qty_factor,quota_item_id) VALUES(%s,%s,%s,%s,%s,NULL,NULL,%s,NULL)",(manual_item_id,quota_code,item.get("zmmc"),item.get("dw"),quantity,factor));retained_codes.append(quota_code)
            after=core._manual_quotas(conn,context["manual_project_id"],context["item_code"]);after_eval=core._evaluate(matches,after)
            cur.execute("UPDATE pricing_task_v2_runs SET evaluation=%s,accuracy_report=NULL WHERE id=%s",(Json(after_eval,dumps=core._json_dumps),run_id));cur.execute("UPDATE pricing_task_v2_results SET evaluation=%s,updated_at=NOW() WHERE run_id=%s",(Json(after_eval,dumps=core._json_dumps),run_id));cur.execute("UPDATE pricing_task_v2_tasks SET accuracy_report=NULL,updated_at=NOW() WHERE id=%s",(context["task_id"],))
            accepted=[{"dekid":x[0],"dezmid":x[1]} for x in sorted(requested)];cur.execute("""INSERT INTO pricing_task_v2_manual_comparison_reviews(run_id,manual_project_id,manual_item_id,before_manual_quotas,after_manual_quotas,before_evaluation,after_evaluation,retained_manual_quota_ids,accepted_ai_quotas,operator_name)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'系统') RETURNING id,run_id,manual_project_id,manual_item_id,before_manual_quotas,after_manual_quotas,before_evaluation,after_evaluation,retained_manual_quota_ids,accepted_ai_quotas,operator_name,created_at""",(run_id,context["manual_project_id"],manual_item_id,Json(before,dumps=core._json_dumps),Json(after,dumps=core._json_dumps),Json(before_eval,dumps=core._json_dumps),Json(after_eval,dumps=core._json_dumps),Json(sorted(retained),dumps=core._json_dumps),Json(accepted,dumps=core._json_dumps)));review=_review_payload(cur.fetchone())
        conn.commit();return {"evaluation":after_eval,"manual_quotas":after,"review":review}
    except Exception:conn.rollback();raise
    finally:conn.close()
