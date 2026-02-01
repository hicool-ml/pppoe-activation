#!/usr/bin/env python3
"""验证root用户的密码"""
import sqlite3
import hashlib

db_path = 'instance/database.db'

# 测试密码
test_password = 'root123'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 查询root用户的信息
cursor.execute('SELECT username, password_hash, salt, role FROM admin_users WHERE username=?', ('root',))
user = cursor.fetchone()

if user:
    username, stored_hash, salt, role = user
    print(f'用户名: {username}')
    print(f'角色: {role}')
    print(f'Salt: {salt}')
    print(f'存储的密码哈希: {stored_hash}')
    print()
    
    # 计算测试密码的哈希
    if salt:
        computed_hash = hashlib.pbkdf2_hmac(
            'sha256',
            test_password.encode(),
            salt.encode(),
            100000
        ).hex()
    else:
        # 如果没有salt，直接使用SHA256
        computed_hash = hashlib.sha256(test_password.encode()).hexdigest()
    
    print(f'计算的密码哈希: {computed_hash}')
    print()
    
    if computed_hash == stored_hash:
        print(f'✅ 密码匹配！用户 {username} 可以使用密码 {test_password} 登录')
    else:
        print(f'❌ 密码不匹配！')
        print(f'存储的哈希: {stored_hash}')
        print(f'计算的哈希: {computed_hash}')
else:
    print('❌ 未找到root用户')

conn.close()
