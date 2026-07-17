#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读取 ChromaDB 底层 SQLite 内容"""
import sqlite3
import os

DB_PATH = r"d:\Projects\YukiV6\core\yuki_memory\chroma.sqlite3"

def main():
    if not os.path.exists(DB_PATH):
        print(f"文件不存在: {DB_PATH}")
        return

    size = os.path.getsize(DB_PATH)
    print(f"文件路径: {DB_PATH}")
    print(f"文件大小: {size} bytes ({size/1024:.1f} KB)")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 列出所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"\n=== 数据表 ({len(tables)}) ===")
    for (table,) in tables:
        print(f"  - {table}")

    # 查看每张表的内容
    for (table,) in tables:
        print(f"\n=== {table} ===")
        cursor.execute(f"PRAGMA table_info({table});")
        columns = cursor.fetchall()
        print(f"字段: {[col[1] for col in columns]}")

        cursor.execute(f"SELECT COUNT(*) FROM {table};")
        count = cursor.fetchone()[0]
        print(f"行数: {count}")

        if count > 0:
            cursor.execute(f"SELECT * FROM {table} LIMIT 5;")
            rows = cursor.fetchall()
            for row in rows:
                print(f"  {row}")

    conn.close()

if __name__ == "__main__":
    main()
