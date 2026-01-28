# admin_app.py
import os
import subprocess
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
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////opt/pppoe-activation/instance/database.db'
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
    if not os.path.exists('/opt/pppoe-activation/instance/database.db'):
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

@app.route('/save', methods=['GET', 'POST'])
@login_required
def save():
    """保存配置接口"""
    if request.method == 'POST':
        try:
            data = {
                'interfaces': request.form.getlist('interfaces'),
                'data_path': request.form.get('data_path', './data'),
                'logs_path': request.form.get('logs_path', './logs'),
                'db_path': request.form.get('db_path', './instance/database.db'),
                'instance_path': request.form.get('instance_path', './instance'),
                'app_port': int(request.form.get('app_port', 80)),
                'admin_port': int(request.form.get('admin_port', 8081)),
                'tz': request.form.get('tz', 'Asia/Shanghai')
            }
            
            # 保存到config.py
            config_content = f"""# PPPoE 激活系统配置文件
# 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

BASE_DIR = '/opt/pppoe-activation'

# SQLite 数据库绝对路径（固定）
# 使用 /app/instance 目录，该目录已挂载到宿主机
DATABASE_PATH = '/opt/pppoe-activation/instance/database.db'

# 网卡配置（用户配置）
NETWORK_INTERFACES = {json.dumps(data.get('interfaces', ['enp3s0', 'enp4s0', 'enp5s0', 'enp6s0'])}

# 日志目录
PPP_LOG_DIR = f'{{BASE_DIR}}/logs'

# 服务端口配置
APP_PORT = {data.get('app_port', 80)}
ADMIN_PORT = {data.get('admin_port', 8081)}
"""
            
            with open('/opt/pppoe-activation/config.py', 'w') as f:
                f.write(config_content)
            
            # 保存到.env
            env_content = f"""# PPPoE 激活系统 Docker 环境变量配置
# 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# 应用端口配置
APP_PORT={data.get('app_port', 80)}
ADMIN_PORT={data.get('admin_port', 8081)}

# 网卡配置（使用空格分隔多个网卡）
NETWORK_INTERFACES={' '.join(data.get('interfaces', ['enp3s0', 'enp4s0', 'enp5s0', 'enp6s0']))}

# 时区配置
TZ={data.get('tz', 'Asia/Shanghai')}

# 数据持久化路径配置
DATA_PATH={data.get('data_path', './data')}
LOGS_PATH={data.get('logs_path', './logs')}
DB_PATH={data.get('db_path', './instance/database.db')}
INSTANCE_PATH={data.get('instance_path', './instance')}
"""
            
            with open('/opt/pppoe-activation/.env', 'w') as f:
                f.write(env_content)
            
            # 重启主应用容器
            try:
                result = subprocess.run(['docker', 'restart', 'pppoe-activation'],
                                      capture_output=True, text=True, timeout=10)
                flash('配置保存成功，正在重启主应用容器...', 'success')
            except Exception as e:
                flash(f'配置保存成功，但重启容器失败: {str(e)}', 'warning')
            
            return redirect(url_for('save'))
        
        # GET请求，返回当前配置
        # 读取当前配置
        current_config = {
            'interfaces': [],
            'data_path': '/opt/pppoe-activation/data',
            'logs_path': '/opt/pppoe-activation/logs',
            'db_path': '/opt/pppoe-activation/instance/database.db',
            'instance_path': '/opt/pppoe-activation/instance',
            'app_port': 80,
            'admin_port': 8081,
            'tz': 'Asia/Shanghai'
        }
        
        # 从config.py读取网络接口
        try:
            with open('/opt/pppoe-activation/config.py', 'r') as f:
                for line in f:
                    if 'NETWORK_INTERFACES' in line and '=' in line:
                        try:
                            interfaces_str = line.split('=')[1].strip()
                            if interfaces_str.startswith('['):
                                interfaces_str = interfaces_str[1:-1]
                            current_config['interfaces'] = [iface.strip().strip("'\"") for iface in interfaces_str.split(',')]
                        except:
                            pass
        except:
            pass
        
        return render_template('admin_list.html', current_config=current_config)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081, debug=True)
