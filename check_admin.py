from flask_sqlalchemy import SQLAlchemy
from flask import Flask
import sys

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////opt/pppoe-activation/instance/database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(64))
    salt = db.Column(db.String(120))
    role = db.Column(db.String(20))
    created_at = db.Column(db.DateTime)

with app.app_context():
    users = AdminUser.query.all()
    print('管理员账号列表:')
    for u in users:
        print(f'用户名: {u.username}, Salt: {u.salt}, Role: {u.role}')
