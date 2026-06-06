#!/usr/bin/env python3
"""快速执行 SQL 文件的辅助脚本"""
import sys
import io
import psycopg2
from dotenv import load_dotenv
import os

# 设置标准输出编码为 UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

def get_connection():
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5433)),
        database=os.getenv('DB_NAME', 'qmind'),
        user=os.getenv('DB_USER', 'qmind'),
        password=os.getenv('DB_PASSWORD', 'qmind')
    )
    return conn

def run_sql_file(filepath):
    """读取并执行 SQL 文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        sql = f.read()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print(f"[OK] Executed {filepath}")
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python run_sql.py <sql_file>")
        sys.exit(1)
    run_sql_file(sys.argv[1])
