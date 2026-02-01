#!/usr/bin/env python3
"""检查数据库中的管理员用户"""
import sys
import os

# 添加项目路径到sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from models import SessionLocal, AdminUser
    
    # 查询所有管理员用户
    session = SessionLocal()
    try:
        admins = session.query(AdminUser).all()
        
        print("数据库中的管理员用户:")
        print("=" * 80)
        for admin in admins:
            print(f"用户名: {admin.username}")
            print(f"角色: {admin.role}")
            print(f"创建时间: {admin.created_at}")
            print(f"Salt: {admin.salt[:20]}..." if admin.salt else "Salt: None")
            print(f"密码哈希: {admin.password_hash[:20]}..." if admin.password_hash else "密码哈希: None")
            print("-" * 80)
        
        if not admins:
            print("数据库中没有管理员用户！")
    finally:
        session.close()
        
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
