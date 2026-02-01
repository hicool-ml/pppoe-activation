#!/usr/bin/env python3
"""检查数据库中的管理员用户"""
import sqlite3
import os

db_path = 'instance/database.db'
if not os.path.exists(db_path):
    print(f'数据库文件不存在: {db_path}')
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 查询所有表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print('数据库中的表:')
for table in tables:
    print(f'  - {table[0]}')

print()

# 查询admin_users表
if any('admin_users' in t for t in tables):
    cursor.execute('SELECT username, role, created_at FROM admin_users')
    admins = cursor.fetchall()
    print('管理员用户:')
    for admin in admins:
        print(f'  用户名: {admin[0]}, 角色: {admin[1]}, 创建时间: {admin[2]}')
else:
    print('admin_users表不存在')

conn.close()
