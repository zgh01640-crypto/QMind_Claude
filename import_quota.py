#!/usr/bin/env python3
"""
导入深圳市建筑消耗量标准 Excel 到数据库。

用法:
  python import_quota.py <excel_path>
  python import_quota.py <excel_path> --force        # 覆盖已有版本
  python import_quota.py <excel_path> --db-url <url>
"""

import argparse
import os
import sys
import datetime

from dotenv import load_dotenv

from db.connection import get_connection
from importer.quota_parser import parse_quota_workbook
from importer.quota_loader import (
    init_schema, get_or_create_standard, delete_standard,
    insert_chapters, insert_items,
)

STANDARD_CODE = 'SJG 171-2024'
STANDARD_NAME = '建筑工程消耗量标准'
BASE_DATE = datetime.date(2023, 8, 1)


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description='导入建筑消耗量标准')
    parser.add_argument('excel_path', help='Excel 文件路径')
    parser.add_argument('--force', action='store_true', help='若已存在则先删除再重新导入')
    parser.add_argument('--db-url', help='数据库连接串（覆盖 .env）')
    args = parser.parse_args()

    if not os.path.isfile(args.excel_path):
        print(f'[错误] 文件不存在: {args.excel_path}', file=sys.stderr)
        sys.exit(1)

    if args.db_url:
        os.environ['DATABASE_URL'] = args.db_url

    conn = get_connection()
    try:
        print('初始化数据库 schema ...')
        init_schema(conn)

        # 检查是否已存在
        import psycopg2
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM quota_standards WHERE standard_code = %s", (STANDARD_CODE,))
            existing = cur.fetchone()

        if existing:
            if not args.force:
                print(f'[跳过] 标准 {STANDARD_CODE} 已存在（id={existing[0]}）。使用 --force 强制重新导入。')
                return
            print(f'[覆盖] 删除旧数据 (id={existing[0]}) ...')
            delete_standard(conn, existing[0])

        print(f'解析 {args.excel_path} ...')
        chapters, items = parse_quota_workbook(args.excel_path)
        print(f'  解析完成：{len(chapters)} 个章节，{len(items)} 条子目变体')

        source_file = os.path.basename(args.excel_path)
        std_id = get_or_create_standard(conn, STANDARD_CODE, STANDARD_NAME, BASE_DATE, source_file)
        print(f'  标准记录 id={std_id}')

        print('写入章节 ...')
        chapter_map = insert_chapters(conn, std_id, chapters)
        print(f'  写入 {len(chapter_map)} 个章节')

        print('写入子目和工料机 ...')
        n_items, n_res = insert_items(conn, std_id, items, chapter_map)
        print(f'  写入 {n_items} 条子目，{n_res} 条工料机记录')

        print('导入完成。')

    except Exception as e:
        conn.rollback()
        print(f'[错误] {e}', file=sys.stderr)
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
