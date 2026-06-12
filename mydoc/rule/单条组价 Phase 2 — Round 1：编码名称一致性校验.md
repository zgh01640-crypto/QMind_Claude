# 单条组价 Phase 2 — Round 1：编码名称一致性校验

## Context

框架已完成（任务列表 + 左侧清单 + 右侧占位区）。  

本阶段只做 **Step 1 工具调用**：点击「套定额」后，AI 调用 `check_item_code` 工具，后端查 `tqdk_tqdzm` 取标准名称，将工程清单名称和标准名称一起返回给模型做一致性判定。

Round 2（套定额匹配）后续另行添加。

---

## 一、编码去流水号逻辑（后端）

BOQ `item_code` 为 **12位数字**（如 `010102002004`），末尾3位是流水号，去掉后得到 **9位基准编码**（`010102002`）用于查 `tqdk_tqdzm.zmbh`：

```python
def strip_serial(item_code: str) -> str:

    """010102002004 → 010102002"""

    code = item_code.strip().replace(' ', '')

    if len(code) >= 3:

        return code[:-3]

    return code



def exec_check_item_code(conn, item_code: str, item_name: str) -> dict:

    base_code = strip_serial(item_code)

    with conn.cursor() as cur:

        cur.execute("SELECT zmmc FROM tqdk_tqdzm WHERE zmbh = %s LIMIT 5", (base_code,))

        rows = cur.fetchall()

    standard_names = list({r[0] for r in rows if r[0]})

    return {

        "item_code": item_code,

        "base_code": base_code,

        "item_name": item_name,

        "standard_names": standard_names,

        "found": len(standard_names) > 0,

    }
```

---

## 二、工具定义 `check_item_code`（`api/routers/bs2024_match.py`）

```python
_CHECK_CODE_TOOL = {

    "type": "function",

    "function": {

        "name": "check_item_code",

        "description": (

            "根据工程清单编码查询国标清单标准库，返回标准名称，"

            "用于核验工程清单名称与标准名称是否一致。"

            "取原始编码去掉末尾3位流水号，得到9位基准编码，精确匹配 tqdk_tqdzm.zmbh。"

        ),

        "strict": True,

        "parameters": {

            "type": "object",

            "properties": {

                "item_code": {"type": "string", "description": "原始12位编码，如 010102002004"}

            },

            "required": ["item_code"],

            "additionalProperties": False,

        },

    },

}
```

---

## 三、单条流式函数（只做 Round 1）

新增 `stream_match_bs2024_item_step1`，不复用现有 `stream_match_bs2024_item`（后者是单轮直接 submit_matches）：

```python
def stream_match_bs2024_item_step1(boq_item: dict, system_prompt: str, conn):

    """

    只做 Round 1：强制调用 check_item_code，执行 DB 查询，将结果 yield 出来。

    yield ("reasoning_token", str)

    yield ("code_check", dict)

    """

    client = OpenAI(api_key=..., base_url=..., timeout=60.0)

    messages = [

        {"role": "system", "content": system_prompt},

        {"role": "user",   "content": _build_boq_user_msg(boq_item)},

    ]

    stream = client.chat.completions.create(

        model=model,

        messages=messages,

        tools=[_CHECK_CODE_TOOL],

        tool_choice={"type": "function", "function": {"name": "check_item_code"}},

        extra_body={"thinking": {"type": "enabled"}},

        reasoning_effort="high",

        max_tokens=2000,

        stream=True,

    )



    tool_call_args = ""

    for chunk in stream:

        if not chunk.choices:

            continue

        delta = chunk.choices[0].delta

        rc = getattr(delta, "reasoning_content", None)

        if rc:

            yield ("reasoning_token", rc)

        if delta.tool_calls:

            for tc in delta.tool_calls:

                if tc.function and tc.function.arguments:

                    tool_call_args += tc.function.arguments



    try:

        call_input = json.loads(tool_call_args)

        result = exec_check_item_code(conn, call_input.get("item_code", ""), boq_item.get("item_name", ""))

    except Exception:

        result = {"item_code": "", "base_code": "", "item_name": "", "standard_names": [], "found": False}



    yield ("code_check", result)
```

---

## 四、SSE 端点（`POST /api/bs2024-match/match-item-stream`）

新建此端点（目前不存在），只处理 step1：

```python
@router.post("/bs2024-match/match-item-stream")

def bs2024_match_item_stream(req: SingleMatchRequest):

    def generate():

        conn = get_connection()

        try:

            # 1. 读清单项

            with conn.cursor() as cur:

                cur.execute("SELECT id,item_code,item_name,item_description,unit,quantity FROM boq_items WHERE id=%s", (req.boq_item_id,))

                row = cur.fetchone()

            if not row:

                yield f"data: {json.dumps({'type':'error','error':'清单项不存在'})}\n\n"; return

            boq_item = {"id":row[0],"item_code":row[1],"item_name":row[2],"item_description":row[3],"unit":row[4],"quantity":float(row[5]) if row[5] else None}



            # 2. 构建提示词（复用现有 build_bs2024_system_prompt）

            chapter_name, sp = build_bs2024_system_prompt(conn, req.chapter_ids)

            user_msg = _build_boq_user_msg(boq_item)



            # 3. item_info 事件

            yield f"data: {json.dumps({'type':'item_info','item':boq_item,'system_prompt':sp[:2000],'system_prompt_len':len(sp),'user_message':user_msg,'chapter_name':chapter_name},ensure_ascii=False)}\n\n"



            # 4. Round 1 流式推理

            for event_type, data in stream_match_bs2024_item_step1(boq_item, sp, conn):

                if event_type == "reasoning_token":

                    yield f"data: {json.dumps({'type':'reasoning_token','token':data},ensure_ascii=False)}\n\n"

                elif event_type == "code_check":

                    yield f"data: {json.dumps({'type':'code_check',**data},ensure_ascii=False)}\n\n"



            yield f"data: {json.dumps({'type':'done'})}\n\n"

        except Exception as e:

            yield f"data: {json.dumps({'type':'error','error':str(e)})}\n\n"

        finally:

            conn.close()



    return StreamingResponse(generate(), media_type="text/event-stream")
```

`SingleMatchRequest`：

```python
class SingleMatchRequest(BaseModel):

    boq_item_id: int

    chapter_ids: list[int]

    manual_project_id: Optional[int] = None
```

---

## 五、前端（`web/lib/api.ts` + `[tid]/page.tsx`）

### `web/lib/api.ts` — 新增类型和函数

```typescript
export type BS2024MatchEvent =

  | { type: 'item_info'; item: BoqItem; system_prompt: string; system_prompt_len: number; user_message: string; chapter_name: string }

  | { type: 'reasoning_token'; token: string }

  | { type: 'code_check'; item_code: string; base_code: string; item_name: string; standard_names: string[]; found: boolean }

  | { type: 'done' }

  | { type: 'error'; error: string }



export async function streamBS2024MatchItem(

  boq_item_id: number, chapter_ids: number[], manual_project_id: number | null,

  onEvent: (e: BS2024MatchEvent) => void,

): Promise<void> {

  // 标准 SSE 读取（复用 streamDebugMatch 的同模式）

}
```

### `web/app/pricing-task/[tid]/page.tsx` — 右侧面板

用 `RightState` 替换现有占位区，展示：

```
┌─ Step 1 编码核查 ─────────────────────────────────┐

│  原始编码：010102002004                            │

│  基准编码：010102002  （去掉末尾3位）               │

│  工程清单名称：砖基础                              │

│  标准名称：砖基础   ✅ 一致 / ⚠️ 不一致             │

│  (found=false 时显示"标准库未找到该编码")           │

└───────────────────────────────────────────────────┘
```

推理过程在 Step 1 卡片上方实时显示（`reasoning_token` 追加）。

---

## 六、要修改的文件

| 文件 | 改动 |

|---|---|

| `api/routers/bs2024_match.py` | 新增 `strip_serial()`、`exec_check_item_code()`、`_CHECK_CODE_TOOL`、`stream_match_bs2024_item_step1()`、`SingleMatchRequest`、`POST /bs2024-match/match-item-stream` |

| `web/lib/api.ts` | 新增 `BS2024MatchEvent`、`streamBS2024MatchItem()` |

| `web/app/pricing-task/[tid]/page.tsx` | 右侧面板：`RightState` 状态 + 推理流 + Step 1 校验结果卡片，「套定额」按钮接入 `streamBS2024MatchItem` |

不涉及 DB Schema 变更。`bs2024_match` 路由已在 `api/main.py` 注册，无需额外操作。

---

## 七、验证

1. `POST /api/bs2024-match/match-item-stream` 返回 SSE 流，顺序：`item_info` → `reasoning_token`(×N) → `code_check` → `done`

2. `code_check.base_code` = `item_code` 去掉末尾3位

3. `code_check.standard_names` 非空（tqdk_tqdzm 有数据时）

4. 前端右侧 Step 1 卡片显示工程清单名称和标准名称

## Context

Phase 1 框架已完成（任务列表 + 左侧清单 + 右侧占位区）。  

本阶段实现推理 Step 1：AI 在套定额前，先通过工具调用核查"清单编码与清单名称是否一致"，将标准库名称一并提供给模型做判定，再继续后续匹配。

**设计核心**：两轮 AI 调用（Two-round Tool Use）

- **Round 1**：AI 调用 `check_item_code` 工具 → 后端查 tqdk_tqdzm 取标准名称 → 返回两个名称给 AI

- **Round 2**：AI 得知编码-名称一致性后 → 调用 `submit_matches` 完成套定额

---

## 一、编码去流水号逻辑（后端）

BOQ `item_code` 格式为 **12位数字**（如 `010102002004`），末尾3位是流水号，去掉后得到 **9位基准编码**（`010102002`）用于查 `tqdk_tqdzm.zmbh`：

```python
def strip_serial(item_code: str) -> str:

    """

    去掉清单编码末尾3位流水号，返回9位基准编码。

    输入示例：010102002004 → 输出：010102002

    """

    code = item_code.strip().replace(' ', '')

    if len(code) >= 3:

        return code[:-3]   # 去掉末尾3位

    return code
```

工具执行函数：查 `tqdk_tqdzm` 返回工程清单名称（来自 `boq_items.item_name`）和标准名称（来自 `tqdk_tqdzm.zmmc`）：

```python
def exec_check_item_code(conn, item_code: str, item_name: str) -> dict:

    """

    执行 check_item_code 工具。

    返回: {

        "item_code": str,          # 原始编码

        "base_code": str,          # 去掉末尾3位后的9位编码

        "item_name": str,          # 工程清单名称（来自 boq_items）

        "standard_names": [str],   # tqdk_tqdzm.zmmc 查到的标准名称

        "found": bool,

    }

    """

    base_code = strip_serial(item_code)

    with conn.cursor() as cur:

        cur.execute("""

            SELECT zmmc FROM tqdk_tqdzm

            WHERE zmbh = %s

            LIMIT 5

        """, (base_code,))

        rows = cur.fetchall()

    standard_names = list({r[0] for r in rows if r[0]})

    return {

        "item_code": item_code,

        "base_code": base_code,

        "item_name": item_name,

        "standard_names": standard_names,

        "found": len(standard_names) > 0,

    }
```

---

## 二、新增工具定义 `check_item_code`（`api/routers/bs2024_match.py`）

```python
_CHECK_CODE_TOOL = {

    "type": "function",

    "function": {

        "name": "check_item_code",

        "description": (

            "根据工程清单编码查询国标清单标准库，返回标准名称，"

            "用于核验工程清单名称与标准名称是否一致。"

            "编码规则：取原始编码去掉末尾3位流水号得到9位基准编码，再去 tqdk_tqdzm 精确匹配 zmbh。"

        ),

        "strict": True,

        "parameters": {

            "type": "object",

            "properties": {

                "item_code": {

                    "type": "string",

                    "description": "工程清单项目编码（原始12位值，如 010102002004）"

                }

            },

            "required": ["item_code"],

            "additionalProperties": False,

        },

    },

}
```

---

## 三、工具执行函数（后端 DB 查询）

```python
def exec_check_item_code(conn, item_code: str) -> dict:

    """

    执行 check_item_code 工具：查 tqdk_tqdzm.zmbh，返回标准子目名称。

    返回: { "base_code": str, "standard_names": [str, ...], "found": bool }

    """

    base_code = strip_serial(item_code)

    with conn.cursor() as cur:

        # 先精确匹配，再前缀匹配

        cur.execute("""

            SELECT zmmc FROM tqdk_tqdzm

            WHERE zmbh = %s OR zmbh LIKE %s

            LIMIT 5

        """, (base_code, base_code + '%'))

        rows = cur.fetchall()

    standard_names = list({r[0] for r in rows if r[0]})

    return {

        "base_code": base_code,

        "standard_names": standard_names,

        "found": len(standard_names) > 0,

    }
```

---

## 四、两轮流式推理函数（核心变更）

替换现有 `stream_match_bs2024_item`（或新增 `stream_match_bs2024_item_v2`），支持两轮 Tool Use：

```python
def stream_match_bs2024_item_v2(boq_item: dict, system_prompt: str, conn):

    """

    两轮调用：

    Round 1 → check_item_code（验证编码名称）→ 执行 DB 查询 → 追加 tool result

    Round 2 → submit_matches（套定额匹配）

    yield ("reasoning_token", str)

    yield ("code_check", dict)   # Round 1 工具执行结果

    yield ("result", list)       # Round 2 submit_matches 结果

    """

    client = OpenAI(api_key=..., base_url=..., timeout=120.0)

    # ── Round 1：编码核查 ────────────────────────────────────────────

    messages = [

        {"role": "system", "content": system_prompt},

        {"role": "user",   "content": _build_boq_user_msg(boq_item)},

    ]

    stream1 = client.chat.completions.create(

        model=model,

        messages=messages,

        tools=[_CHECK_CODE_TOOL],

        tool_choice={"type": "function", "function": {"name": "check_item_code"}},

        extra_body={"thinking": {"type": "enabled"}},

        reasoning_effort="high",

        max_tokens=2000,

        stream=True,

    )

    # 收集 Round 1 的 reasoning tokens 和 tool_call

    tool_call_id, tool_call_args = "", ""

    assistant_tool_calls = []

    for chunk in stream1:

        if not chunk.choices:

            continue

        delta = chunk.choices[0].delta

        rc = getattr(delta, "reasoning_content", None)

        if rc:

            yield ("reasoning_token", rc)

        if delta.tool_calls:

            for tc in delta.tool_calls:

                if tc.id:

                    tool_call_id = tc.id

                if tc.function and tc.function.arguments:

                    tool_call_args += tc.function.arguments

    # 执行 DB 查询（传入 boq_item 的 item_name 用于返回给 AI）

    try:

        call_input = json.loads(tool_call_args)

        check_result = exec_check_item_code(

            conn,

            call_input.get("item_code", ""),

            boq_item.get("item_name", ""),

        )

    except Exception:

        check_result = {"item_code": "", "base_code": "", "item_name": "", "standard_names": [], "found": False}

    yield ("code_check", check_result)

    # ── Round 2：套定额匹配 ──────────────────────────────────────────

    messages += [

        {

            "role": "assistant",

            "content": None,

            "tool_calls": [{

                "id": tool_call_id,

                "type": "function",

                "function": {"name": "check_item_code", "arguments": tool_call_args},

            }],

        },

        {

            "role": "tool",

            "tool_call_id": tool_call_id,

            "content": json.dumps(check_result, ensure_ascii=False),

        },

    ]

    stream2 = client.chat.completions.create(

        model=model,

        messages=messages,

        tools=[_MATCH_TOOL_BS2024],

        tool_choice={"type": "function", "function": {"name": "submit_matches"}},

        extra_body={"thinking": {"type": "enabled"}},

        reasoning_effort="high",

        max_tokens=8000,

        stream=True,

    )

    tool_call_args2 = ""

    for chunk in stream2:

        if not chunk.choices:

            continue

        delta = chunk.choices[0].delta

        rc = getattr(delta, "reasoning_content", None)

        if rc:

            yield ("reasoning_token", rc)

        if delta.tool_calls:

            for tc in delta.tool_calls:

                if tc.function and tc.function.arguments:

                    tool_call_args2 += tc.function.arguments

    results = []

    if tool_call_args2:

        try:

            results = json.loads(tool_call_args2).get("matches", [])

        except Exception:

            pass

    yield ("result", results)
```

---

## 五、SSE 端点更新（`POST /api/bs2024-match/match-item-stream`）

在 generate() 中追加 `code_check` 事件的 SSE 推送：

```python
for event_type, data in stream_match_bs2024_item_v2(boq_item, sp, conn):

    if event_type == "reasoning_token":

        yield f"data: {json.dumps({'type':'reasoning_token','token':data}, ensure_ascii=False)}\n\n"

    elif event_type == "code_check":

        yield f"data: {json.dumps({'type':'code_check',**data}, ensure_ascii=False)}\n\n"

    elif event_type == "result":

        yield f"data: {json.dumps({'type':'result','matches':data}, ensure_ascii=False)}\n\n"
```

新增 SSE 事件 `code_check`：

| 字段 | 含义 |

|---|---|

| `item_code` | 原始12位编码 |

| `base_code` | 去掉末尾3位后的9位基准编码 |

| `item_name` | 工程清单名称（来自 boq_items） |

| `standard_names` | tqdk_tqdzm.zmmc 查到的标准名称列表 |

| `found` | 是否在标准库中命中 |

---

## 六、前端类型与显示更新

### `web/lib/api.ts` — 新增事件类型

```typescript
export type BS2024MatchEvent =

  | { type: 'item_info'; ... }

  | { type: 'reasoning_token'; token: string }

  | { type: 'code_check'; item_code: string; base_code: string; item_name: string; standard_names: string[]; found: boolean }

  | { type: 'result'; matches: BS2024MatchResult[] }

  | { type: 'done' }

  | { type: 'error'; error: string }
```

### `web/app/pricing-task/[tid]/page.tsx` — 右侧面板

右侧面板展示新增 **Step 1 校验结果卡片**（在推理区上方）：

```
┌─ Step 1 编码核查 ──────────────────────────────────────┐

│  原始编码：010102002004                                 │

│  基准编码：010102002  （去掉末尾3位流水号）              │

│  工程清单名称：砖基础                                   │

│  标准名称：砖基础      ✅ 一致 / ⚠️ 不一致              │

└──────────────────────────────────────────────────────┘
```

- `found=false` 时显示"未在标准库中找到该编码"（橙色提示）

- `standard_names` 多条时全部显示（列表）

- 一致性判断由 AI 在 Round 2 的 reasoning 中说明，此处只展示工具执行的原始结果

---

## 七、要修改的文件

| 文件 | 改动 |

|---|---|

| `api/routers/bs2024_match.py` | 新增 `_CHECK_CODE_TOOL`、`strip_serial()`、`exec_check_item_code()`、`stream_match_bs2024_item_v2()`，更新 `match-item-stream` 端点使用 v2 函数 |

| `web/lib/api.ts` | `BS2024MatchEvent` 新增 `code_check` 类型 |

| `web/app/pricing-task/[tid]/page.tsx` | `RightState` 追加 `codeCheck` 字段，右侧面板新增 Step 1 校验结果卡片 |

不涉及 DB Schema 变更，不涉及新表创建。

---

## 八、验证

1. 后端：`POST /api/bs2024-match/match-item-stream`，SSE 流中出现顺序：

   `item_info` → `reasoning_token`(×N) → `code_check` → `reasoning_token`(×N) → `result` → `done`

2. `code_check` 事件中 `standard_names` 非空（数据库有匹配记录）

3. 前端右侧 Step 1 卡片显示：基准编码 + 标准名称 + 清单名称

4. 最终 `result.matches` 包含套定额匹配结果
