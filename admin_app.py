import os
from datetime import datetime, timedelta
import json
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ---------- 数据库模型 ----------
class AdminUser(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

class OperationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    operator = db.Column(db.String(50))
    action = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class DialRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_type = db.Column(db.String(50))
    operator = db.Column(db.String(50))
    account = db.Column(db.String(50))
    activate_time = db.Column(db.DateTime)
    success = db.Column(db.Boolean)

# ---------- 登录管理 ----------
@login_manager.user_loader
def load_user(user_id):
    return AdminUser.query.get(int(user_id))

# ---------- 初始化数据库 ----------
def init_db():
    if not os.path.exists('database.db'):
        db.create_all()
        if not AdminUser.query.filter_by(username='admin').first():
            admin = AdminUser(username='admin', password_hash=generate_password_hash('admin123'))
            db.session.add(admin)
            db.session.commit()
        print("Database initialized with default admin.")

init_db()

# ---------- 路由 ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = AdminUser.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        flash("用户名或密码错误")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    # 默认显示当天拨号记录
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    records = DialRecord.query.filter(DialRecord.activate_time >= today,
                                      DialRecord.activate_time < tomorrow).all()
    # 统计总数柱状图
    df = pd.DataFrame([{
        'hour': r.activate_time.hour,
        'operator': r.operator
    } for r in records])
    img = None
    if not df.empty:
        plt.figure(figsize=(8,4))
        total = df.groupby('hour').size()
        total.plot(kind='bar', color='lightblue', label='总数')
        for op in df['operator'].unique():
            df[df['operator']==op].groupby('hour').size().plot(marker='o', label=op)
        plt.xlabel('小时')
        plt.ylabel('数量')
        plt.legend()
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png')
        buf.seek(0)
        img = base64.b64encode(buf.read()).decode('ascii')
        plt.close()
    return render_template('index.html', img_data=img)

@app.route('/users')
@login_required
def users():
    admins = AdminUser.query.all()
    return render_template('users.html', admins=admins)

@app.route('/logs')
@login_required
def logs():
    logs = OperationLog.query.order_by(OperationLog.timestamp.desc()).all()
    return render_template('logs.html', logs=logs)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081, debug=True)
