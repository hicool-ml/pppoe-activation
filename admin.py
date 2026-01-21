# admin.py
from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
import hashlib
import os

# ========== 初始化 ==========
app = Flask(__name__, static_folder='web/static', template_folder='web/templates')
app.secret_key = 'your-super-secret-key-change-it-please'  # 请修改！

# ========== 数据库配置 ==========
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ========== 数据库模型 ==========
class Activation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    role = db.Column(db.String(50))
    isp = db.Column(db.String(20))
    username = db.Column(db.String(100), index=True)
    success = db.Column(db.Boolean)
    ip = db.Column(db.String(15))
    mac = db.Column(db.String(17))
    error_code = db.Column(db.String(10))
    error_message = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=db.func.now())

class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(64))  # SHA256
    created_at = db.Column(db.DateTime, default=db.func.now())

# ========== 启动时创建表和默认管理员 ==========
with app.app_context():
    db.create_all()

    # 如果没有管理员，创建默认账号
    if AdminUser.query.count() == 0:
        pwd_hash = hashlib.sha256('admin123'.encode()).hexdigest()
        admin = AdminUser(username='admin', password_hash=pwd_hash)
        db.session.add(admin)
        db.session.commit()
        print("✅ 默认管理员创建成功：admin / admin123")

# ISP 显示映射
ISP_DISPLAY = {
    'cdu': '校园网',
    'cmccgx': '中国移动',
    '96301': '中国电信',
    '10010': '中国联通'
}

ISP_COLORS = {
    '校园网': '#4B5563',
    '中国移动': '#FF4500',
    '中国电信': '#1E90FF',
    '中国联通': '#32CD32'
}

# ========== 路由 ==========
@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        user = AdminUser.query.filter_by(username=username, password_hash=pwd_hash).first()
        if user:
            session['admin'] = user.username
            return redirect('/admin')
        return render_template('admin/login.html', error="用户名或密码错误")
    return render_template('admin/login.html')

@app.route('/admin/logout')
def logout():
    session.pop('admin', None)
    return redirect('/admin/login')

@app.route('/admin')
def dashboard():
    if 'admin' not in session:
        return redirect('/admin/login')
    total = Activation.query.count()
    success = Activation.query.filter_by(success=True).count()
    failure = total - success
    success_rate = f"{success / total * 100:.1f}%" if total else "0%"
    # 按 ISP 统计成功数
    stats = {}
    for isp_key, isp_name in ISP_DISPLAY.items():
        count = Activation.query.filter_by(isp=isp_key, success=True).count()
        stats[isp_name] = count
    return render_template('admin/dashboard.html',
                         total=total, success=success,
                         failure=failure, success_rate=success_rate,
                         stats=stats, isp_colors=ISP_COLORS)

@app.route('/admin/logs')
def logs():
    if 'admin' not in session:
        return redirect('/admin/login')
    page = request.args.get('page', 1, type=int)
    pagination = Activation.query.order_by(Activation.id.desc()).paginate(
        page=page, per_page=50, error_out=False)
    return render_template('admin/logs.html', logs=pagination)

# ========== API 接口 ==========
@app.route('/api/logs')
def api_logs():
    if 'admin' not in session:
        return jsonify({"error": "未登录"}), 401
    logs = Activation.query.order_by(Activation.id.desc()).limit(100).all()
    return jsonify([{
        'id': log.id,
        'name': log.name,
        'role': log.role,
        'isp': log.isp,
        'username': log.username,
        'success': log.success,
        'ip': log.ip,
        'mac': log.mac,
        'error_code': log.error_code,
        'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for log in logs])

# ========== 运行 ==========
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081, debug=False)
