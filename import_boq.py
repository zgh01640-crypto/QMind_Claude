#!/usr/bin/env python3
"""
导入工程量清单（分部分项）Excel 到数据库。

用法:
  python import_boq.py <excel_path>
  python import_boq.py <excel_path> --tag 工程管理
  python import_boq.py <excel_path> --force        # 覆盖已有记录
  python import_boq.py <excel_path> --db-url <url>
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from db.connection import get_connection
from importer.boq_parser import parse_boq_workbook
from importer.boq_loader import (
    init_schema, get_project_by_source, delete_project,
    insert_project, insert_sections, insert_items,
)

DEFAULT_TAG = '工程管理'


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description='导入分部分项工程量清单')
    parser.add_argument('excel_path', help='Excel 文件路径')
    parser.add_argument('--tag', default=DEFAULT_TAG, help=f'标签（默认：{DEFAULT_TAG}）')
    parser.add_argument('--force', action='store_true', help='若已存在则先删除再重新导入')
    parser.add_argument('--db-url', help='数据库连接串（覆盖 .env）')
    args = parser.parse_args()

    if not os.path.isfile(args.excel_path):
        print(f'[错误] 文件不存在: {args.excel_path}', file=sys.stderr)
        sys.exit(1)

    if args.db_url:
        os.environ['DATABASE_URL'] = args.db_url

    source_file = os.path.basename(args.excel_path)

    conn = get_connection()
    try:
        print('初始化数据库 schema ...')
        init_schema(conn)

        existing_id = get_project_by_source(conn, source_file)
        if existing_id:
            if not args.force:
                print(f'[跳过] {source_file} 已存在（id={existing_id}）。使用 --force 强制重新导入。')
                return
            print(f'[覆盖] 删除旧数据 (id={existing_id}) ...')
            delete_project(conn, existing_id)

        print(f'解析 {args.excel_path} ...')
        project_info, sections, items = parse_boq_workbook(args.excel_path)
        print(f'  工程名称: {project_info["project_name"]}')
        print(f'  标段: {project_info["bid_section"]}')
        print(f'  解析完成: {len(sections)} 个分部，{len(items)} 条清单项')

        project_id = insert_project(
            conn,
            project_info['project_name'],
            project_info['bid_section'],
            source_file,
            args.tag,
        )
        print(f'  项目记录 id={project_id}')

        seq_to_section_id = insert_sections(conn, project_id, sections)
        print(f'  写入 {len(seq_to_section_id)} 个分部')

        n = insert_items(conn, project_id, items, seq_to_section_id)
        print(f'  写入 {n} 条清单项')

        print('导入完成。')

    except Exception as e:
        conn.rollback()
        print(f'[错误] {e}', file=sys.stderr)
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
