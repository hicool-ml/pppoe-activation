#!/usr/bin/env python3
"""重置root用户的密码"""
import sqlite3
import hashlib
import secrets

db_path = 'instance/database.db'

# 新密码
new_password = 'root123'  # 可以修改为其他密码

# 生成salt和密码哈希
salt = secrets.token_hex(16)
pwd_hash = hashlib.pbkdf2_hmac(
    'sha256',
    new_password.encode(),
    salt.encode(),
    100000
).hex()

print(f'正在重置root用户的密码...')
print(f'新密码: {new_password}')
print(f'Salt: {salt}')
print(f'密码哈希: {pwd_hash}')

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 更新root用户的密码
cursor.execute('UPDATE admin_users SET password_hash=?, salt=? WHERE username=?', (pwd_hash, salt, 'root'))
conn.commit()

# 验证更新
cursor.execute('SELECT username, role FROM admin_users WHERE username=?', ('root',))
user = cursor.fetchone()
if user:
    print(f'✅ 密码重置成功！用户名: {user[0]}, 角色: {user[1]}')
    print(f'✅ 请使用用户名 root 和密码 {new_password} 登录')
else:
    print('❌ 未找到root用户')

conn.close()
