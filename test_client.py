#!/usr/bin/env python
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

print(f"Current dir: {os.getcwd()}")
api_key = os.getenv("DEEPSEEK_API_KEY")
print(f"API Key found: {bool(api_key)}")

if api_key:
    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=5.0,
    )
    print("✅ OpenAI client created successfully")
else:
    print("❌ DEEPSEEK_API_KEY not set")
