#!/usr/bin/env python3
import requests
import json

url = 'http://127.0.0.1:8000/api/pricing-task/match-item-stream'
payload = {'boq_item_id': 1}

print('Sending POST request to:', url)
print('Payload:', json.dumps(payload))

try:
    response = requests.post(url, json=payload, stream=True, timeout=60)
    print(f'Status: {response.status_code}')
    print(f'Content-Type: {response.headers.get("content-type")}')
    print('\nStreaming response:')

    all_events = []
    for line in response.iter_lines():
        if line:
            decoded = line.decode('utf-8', errors='replace')
            all_events.append(decoded)

    print(f'Total lines received: {len(all_events)}\n')

    # 显示所有非 reasoning_token 的事件
    print('Events received:')
    for i, event in enumerate(all_events):
        if 'reasoning_token' not in event:
            print(f'[{i}] {event[:300]}')
        elif i < 3 or i >= len(all_events) - 3:
            print(f'[{i}] {event[:300]}')

    # 计数
    reasoning_tokens = sum(1 for e in all_events if 'reasoning_token' in e)
    code_checks = sum(1 for e in all_events if 'code_check' in e)
    judgments = sum(1 for e in all_events if 'judgment' in e)
    done_events = sum(1 for e in all_events if '"type":"done"' in e or '"type": "done"' in e)

    print(f'\nSummary:')
    print(f'  - reasoning_token events: {reasoning_tokens}')
    print(f'  - code_check events: {code_checks}')
    print(f'  - judgment events: {judgments}')
    print(f'  - done events: {done_events}')

except Exception as e:
    import traceback
    print(f'Error: {e}')
    traceback.print_exc()
