#!/usr/bin/env python3
"""
最小化测试：验证 DeepSeek 思考模式 + 工具调用
目标：
1. 第一轮：启用思考 + 工具，让模型自动调用工具
2. 第二轮：传回 reasoning_content，继续对话
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# ─── 定义工具 ────────────────────────────────────────────
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                },
                "required": ["location"]
            }
        }
    }
]

def get_weather(location: str, unit: str = "celsius") -> dict:
    """模拟天气查询工具"""
    return {
        "location": location,
        "temperature": 25,
        "unit": unit,
        "condition": "sunny",
        "humidity": 60
    }

print("=" * 80)
print("测试 1: 思考模式 + 工具调用（第一轮）")
print("=" * 80)

# 第一轮：启用思考和工具
messages = [
    {"role": "user", "content": "纽约现在天气怎样？"}
]

response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=messages,
    tools=tools,
    stream=False,
    extra_body={"thinking": {"type": "enabled"}},
    reasoning_effort="high"
)

print("\n【第一轮 API 响应】")
print(f"完成原因: {response.choices[0].finish_reason}")

assistant_msg = response.choices[0].message
print(f"\n思考内容 (reasoning_content):")
if hasattr(assistant_msg, 'reasoning_content') and assistant_msg.reasoning_content:
    print(f"  {assistant_msg.reasoning_content[:200]}...")
else:
    print("  (无)")

print(f"\n普通回复 (content):")
if assistant_msg.content:
    print(f"  {assistant_msg.content}")
else:
    print("  (无)")

print(f"\n工具调用 (tool_calls):")
if assistant_msg.tool_calls:
    for tc in assistant_msg.tool_calls:
        print(f"  - 工具: {tc.function.name}")
        print(f"    参数: {tc.function.arguments}")
        tool_call_id = tc.id
else:
    print("  (无)")
    tool_call_id = None

# 保存第一轮的回复（包含 reasoning_content）
first_turn_assistant = {
    "role": "assistant",
    "content": assistant_msg.content,
    "reasoning_content": assistant_msg.reasoning_content if hasattr(assistant_msg, 'reasoning_content') else "",
    "tool_calls": [
        {
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments}
        }
        for tc in (assistant_msg.tool_calls or [])
    ] if assistant_msg.tool_calls else None
}

print("\n【第一轮保存的 assistant 消息】")
print(json.dumps(first_turn_assistant, ensure_ascii=False, indent=2))

# 如果有工具调用，执行工具
if assistant_msg.tool_calls:
    print("\n" + "=" * 80)
    print("执行工具...")
    print("=" * 80)

    # 构建工具执行结果
    tool_results = []
    for tc in assistant_msg.tool_calls:
        func_name = tc.function.name
        args = json.loads(tc.function.arguments)

        print(f"\n执行 {func_name}({args})")
        if func_name == "get_weather":
            result = get_weather(**args)
        else:
            result = {"error": f"Unknown function: {func_name}"}

        print(f"结果: {json.dumps(result, ensure_ascii=False)}")

        tool_results.append({
            "tool_call_id": tc.id,
            "result": result
        })

    # ─── 第二轮：回传 reasoning_content，继续对话 ────────────────────────
    print("\n" + "=" * 80)
    print("测试 2: 思考模式 + 工具结果（第二轮，须回传 reasoning_content）")
    print("=" * 80)

    # 构建第二轮的 messages
    messages = [
        {"role": "user", "content": "纽约现在天气怎样？"},
        first_turn_assistant,  # 第一轮的 assistant 回复（含 reasoning_content）
    ]

    # 添加工具结果
    for tr in tool_results:
        messages.append({
            "role": "tool",
            "tool_call_id": tr["tool_call_id"],
            "content": json.dumps(tr["result"], ensure_ascii=False)
        })

    # 用户继续提问
    messages.append({
        "role": "user",
        "content": "根据查询结果，给我一个穿衣建议"
    })

    print("\n【第二轮 messages 结构】")
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        has_reasoning = "reasoning_content" in msg
        print(f"  [{i}] role={role}, has_reasoning={has_reasoning}")

    # 第二轮请求
    response2 = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=messages,
        stream=False,
        extra_body={"thinking": {"type": "enabled"}},
        reasoning_effort="high"
    )

    print("\n【第二轮 API 响应】")
    print(f"完成原因: {response2.choices[0].finish_reason}")

    assistant_msg2 = response2.choices[0].message
    print(f"\n思考内容 (reasoning_content):")
    if hasattr(assistant_msg2, 'reasoning_content') and assistant_msg2.reasoning_content:
        print(f"  {assistant_msg2.reasoning_content[:200]}...")
    else:
        print("  (无)")

    print(f"\n最终回复 (content):")
    if assistant_msg2.content:
        print(f"  {assistant_msg2.content}")
    else:
        print("  (无)")

    print("\n✅ 思考模式 + 工具调用测试完成")
else:
    print("\n⚠️ 第一轮没有调用工具，测试不完整")
