#!/usr/bin/env python
"""
导入《房屋建筑与装饰工程工程量计算标准》DOCX 到数据库。

用法：
  python import_measure.py <docx文件路径>
  python import_measure.py  # 使用默认路径
"""
import sys
import os

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(__file__))

from importer.measure_parser import parse_docx
from importer.measure_loader import apply_schema, load
from db.connection import get_connection

DEFAULT_FILE = r'mydoc\房屋建筑与装饰工程工程量计算标准.docx'
STANDARD_NAME = '房屋建筑与装饰工程工程量计算标准'


def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FILE
    if not os.path.exists(filepath):
        print(f'[错误] 文件不存在: {filepath}')
        sys.exit(1)

    print(f'[1/3] 解析文档: {filepath}')
    sections, items = parse_docx(filepath)
    print(f'      解析完成: {len(sections)} 个节, {len(items)} 个清单项目')

    print('[2/3] 连接数据库并建表…')
    conn = get_connection()
    try:
        apply_schema(conn)
        print('[3/3] 写入数据库…')
        std_id = load(conn, os.path.basename(filepath), STANDARD_NAME, sections, items)
        print(f'      完成！standard_id={std_id}, '
              f'{len(sections)} 节, {len(items)} 条清单项目')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
