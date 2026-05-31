#!/usr/bin/env python3
"""
深圳建设工程信息价 Excel 导入工具

用法:
  python import_price.py <excel_path> [--force] [--db-url <url>]

选项:
  --force       若该期数据已存在，先删除再重新导入
  --db-url URL  覆盖 .env 中的 DATABASE_URL
"""

import argparse
import os
import sys

# 确保项目根目录在 sys.path 中，使 db/importer 包可以被找到
sys.path.insert(0, os.path.dirname(__file__))

from db.connection import get_connection, apply_schema
from importer.parser import parse_filename, parse_workbook
from importer.loader import (
    get_existing_period,
    create_period,
    delete_period,
    upsert_categories,
    insert_items,
)


def main():
    parser = argparse.ArgumentParser(description="导入深圳信息价 Excel 数据到 PostgreSQL")
    parser.add_argument("excel_path", help="Excel 文件路径，如 2026-04-0深圳信息价.xlsx")
    parser.add_argument("--force", action="store_true", help="若该期已存在则删除后重新导入")
    parser.add_argument("--db-url", help="覆盖 DATABASE_URL 环境变量")
    args = parser.parse_args()

    excel_path = os.path.abspath(args.excel_path)
    if not os.path.exists(excel_path):
        sys.exit(f"错误: 文件不存在: {excel_path}")

    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url

    # 解析文件名获取期次信息
    try:
        year, month, version = parse_filename(excel_path)
    except ValueError as e:
        sys.exit(f"错误: {e}")

    print(f"正在导入: {year}年{month}月 第{version}版")
    print(f"文件: {os.path.basename(excel_path)}")

    # 建立数据库连接并初始化 schema
    try:
        conn = get_connection()
    except Exception as e:
        sys.exit(f"数据库连接失败: {e}")

    apply_schema(conn)

    # 检查是否已存在该期数据
    existing_id = get_existing_period(conn, year, month, version)
    if existing_id is not None:
        if not args.force:
            conn.close()
            sys.exit(
                f"错误: {year}年{month}月第{version}版数据已存在 (period_id={existing_id})。\n"
                "使用 --force 参数可强制覆盖。"
            )
        print(f"--force 模式: 删除已有数据 (period_id={existing_id})...")
        delete_period(conn, existing_id)

    # 解析 Excel
    print("正在解析 Excel 文件...")
    sheets_meta, items = parse_workbook(excel_path)
    print(f"  解析完成: {len(sheets_meta)} 个分类，{len(items)} 条记录")

    # 写入数据库
    period_id = create_period(conn, year, month, version, os.path.basename(excel_path))
    category_map = upsert_categories(conn, sheets_meta)
    inserted = insert_items(conn, period_id, items, category_map)

    conn.close()

    print()
    print("=" * 50)
    print(f"导入完成: {year}年{month}月 第{version}版")
    print(f"  period_id : {period_id}")
    print(f"  分类数量  : {len(sheets_meta)}")
    print(f"  数据条数  : {inserted}")
    print("=" * 50)


if __name__ == "__main__":
    main()
