# init_db.py - 兼容 Flask 2.3+ 的数据库初始化脚本
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import hashlib
import secrets
import os
from config import DATABASE_PATH  # 👈 从 config.py 读取固定路径

# 初始化 Flask 和数据库
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DATABASE_PATH}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 定义模型
class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    salt = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='admin')  # 添加role字段
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Activation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    role = db.Column(db.String(100))
    isp = db.Column(db.String(100))
    username = db.Column(db.String(100), nullable=False)
    success = db.Column(db.Boolean, nullable=False)
    ip = db.Column(db.String(45))
    mac = db.Column(db.String(17))
    error_code = db.Column(db.String(20))
    error_message = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

def create_database():
    """创建数据库文件和表，并添加默认管理员"""
    # 删除旧数据库（如果存在）
    if os.path.exists(DATABASE_PATH):
        print("⚠️ 发现旧数据库，正在删除...")
        os.remove(DATABASE_PATH)

    # 创建所有表
    with app.app_context():
        db.create_all()
        print("✅ 数据库表已创建")

        # 创建默认管理员账号 admin / admin123
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            'admin123'.encode(),
            salt.encode(),
            100000
        ).hex()

        admin = AdminUser(username='admin', password_hash=pwd_hash, salt=salt)
        db.session.add(admin)
        db.session.commit()
        print("✅ 默认管理员账号已创建: admin / admin123")
    
    # 修改数据库文件权限为666
    if os.path.exists(DATABASE_PATH):
        os.chmod(DATABASE_PATH, 0o666)
        print(f"✅ 数据库文件权限已修改为666")
        # 修改文件所有者为ppp（如果可能）
        try:
            import pwd
            import grp
            ppp_uid = pwd.getpwnam('ppp').pw_uid
            ppp_gid = grp.getgrnam('ppp').gr_gid
            os.chown(DATABASE_PATH, ppp_uid, ppp_gid)
            print(f"✅ 数据库文件所有者已修改为ppp:ppp")
        except Exception as e:
            print(f"⚠️ 无法修改文件所有者: {e}")
    
    print(f"\n🎉 数据库 '{DATABASE_PATH}' 已成功生成！")

if __name__ == '__main__':
    create_database()
