#!/usr/bin/env python3
# init_admin.py - 初始化后台管理员数据库

import sqlite3
import bcrypt
import getpass
import os
from datetime import datetime

DB_PATH = "/opt/pppoe-activation/instance/database.db"

def connect_db():
    return sqlite3.connect(DB_PATH)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def init_db():
    """删除旧 admin 表并创建新表"""
    conn = connect_db()
    c = conn.cursor()

    # 删除旧表
    c.execute("DROP TABLE IF EXISTS admin")
    c.execute("DROP TABLE IF EXISTS operation_log")

    # 创建 admin 表
    c.execute("""
    CREATE TABLE admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'super',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 创建后台操作日志表
    c.execute("""
    CREATE TABLE operation_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        action TEXT NOT NULL,
        target TEXT,
        result TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(admin_id) REFERENCES admin(id)
    )
    """)

    conn.commit()
    conn.close()
    print("[OK] 数据库初始化完成，admin 表和操作日志表已创建。")

def add_admin(username: str, password: str, role="super", admin_id=None):
    """添加管理员账号"""
    conn = connect_db()
    c = conn.cursor()
    pw_hash = hash_password(password)
    try:
        c.execute("INSERT INTO admin (username, password_hash, role) VALUES (?, ?, ?)",
                  (username, pw_hash, role))
        conn.commit()
        new_id = c.lastrowid
        result = "success"
        print(f"[OK] 管理员 {username} 创建成功。")
    except sqlite3.IntegrityError:
        result = "fail: username exists"
        print(f"[ERROR] 管理员 {username} 已存在。")
        new_id = None

    # 写操作日志
    if admin_id is not None:
        c.execute("INSERT INTO operation_log (admin_id, action, target, result) VALUES (?, ?, ?, ?)",
                  (admin_id, "create_admin", username, result))
        conn.commit()

    conn.close()
    return new_id

def delete_admin(username: str, admin_id=None):
    """删除管理员账号"""
    conn = connect_db()
    c = conn.cursor()
    c.execute("DELETE FROM admin WHERE username=?", (username,))
    affected = c.rowcount
    conn.commit()

    result = "success" if affected else "fail: not found"
    print(f"[INFO] 删除管理员 {username}: {result}")

    # 写操作日志
    if admin_id is not None:
        c.execute("INSERT INTO operation_log (admin_id, action, target, result) VALUES (?, ?, ?, ?)",
                  (admin_id, "delete_admin", username, result))
        conn.commit()

    conn.close()
    return affected

def change_password(username: str, new_password: str, admin_id=None):
    """修改管理员密码"""
    conn = connect_db()
    c = conn.cursor()
    pw_hash = hash_password(new_password)
    c.execute("UPDATE admin SET password_hash=? WHERE username=?", (pw_hash, username))
    affected = c.rowcount
    conn.commit()
    result = "success" if affected else "fail: not found"
    print(f"[INFO] 修改管理员 {username} 密码: {result}")

    if admin_id is not None:
        c.execute("INSERT INTO operation_log (admin_id, action, target, result) VALUES (?, ?, ?, ?)",
                  (admin_id, "change_password", username, result))
        conn.commit()
    conn.close()
    return affected

def main():
    if not os.path.exists(DB_PATH):
        open(DB_PATH, 'a').close()

    init_db()

    print("\n=== 初始化超级管理员 ===")
    username = input("请输入超级管理员用户名: ").strip()
    while True:
        password = getpass.getpass("请输入密码: ").strip()
        password2 = getpass.getpass("请再次输入密码: ").strip()
        if password != password2:
            print("[ERROR] 两次输入密码不一致，请重新输入")
        elif len(password) < 6:
            print("[ERROR] 密码至少6位")
        else:
            break

    add_admin(username, password)
    print("[OK] 超级管理员创建完成，可以登录后台管理系统。")

if __name__ == "__main__":
    main()
