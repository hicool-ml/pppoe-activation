# dashboard.py
from flask import Flask, jsonify, render_template, request, make_response, redirect, url_for, session
from models import SessionLocal, ActivationLog, init_db
from sync import sync_logs
from config import ADMIN_PORT
import logging
import csv
from io import StringIO
from datetime import datetime
import hashlib
from flask_sqlalchemy import SQLAlchemy
import subprocess
import json
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='web/static', template_folder='templates')
app.secret_key = 'your-super-secret-key-change-it-please'  # 请修改！

# ========== 数据库配置 ==========
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////opt/pppoe-activation/instance/database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ========== 数据库模型 ==========
class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(64))  # SHA256
    salt = db.Column(db.String(120))  # 添加salt字段
    role = db.Column(db.String(20), default='admin')  # admin 或 super
    created_at = db.Column(db.DateTime, default=db.func.now())

class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    value = db.Column(db.String(500))
    updated_at = db.Column(db.DateTime, default=db.func.now())

# ========== 启动时创建表和默认管理员 ==========
import secrets
with app.app_context():
    db.create_all()
    if AdminUser.query.count() == 0:
        # 使用pbkdf2_hmc加密（与init_db.py一致）
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
        print("✅ 默认管理员创建成功：admin / admin123")

# ISP 显示映射
ISP_DISPLAY = {
    'cdu': '校园网',
    'cmccgx': '中国移动',
    '96301': '中国电信',
    '10010': '中国联通'
}

# CSV 导出ISP显示映射
CSV_ISP_DISPLAY = {
    'cdu': '校园网',
    'cmccgx': '中国移动',
    '10010': '中国联通',
    '96301': '中国电信'
}

# ISP 颜色映射
ISP_COLORS = {
    '校园网': '#4B5563',
    '中国移动': '#FF4500',
    '中国电信': '#1E90FF',
    '中国联通': '#32CD32'
}

# =============================
# 管理员登录/登出
# =============================

@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # 使用pbkdf2_hmac加密（与init_db.py一致）
        user = AdminUser.query.filter_by(username=username).first()
        if user:
            pwd_hash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode(),
                user.salt.encode() if hasattr(user, 'salt') else b'',
                100000
            ).hex()
            if pwd_hash == user.password_hash:
                session['admin'] = user.username
                return redirect('/admin')
        
        return render_template('admin/login.html', error="用户名或密码错误")
    return render_template('admin/login.html')


@app.route('/admin/logout')
def logout():
    session.pop('admin', None)
    return redirect('/admin/login')


@app.route('/admin')
def admin_dashboard():
    if 'admin' not in session:
        return redirect('/admin/login')
    
    db = SessionLocal()
    try:
        total = db.query(ActivationLog).count()
        success = db.query(ActivationLog).filter_by(success=True).count()
        failure = total - success
        success_rate = f"{success / total * 100:.1f}%" if total else "0%"
        # 按 ISP 统计成功数
        stats = {}
        for isp_key, isp_name in ISP_DISPLAY.items():
            count = db.query(ActivationLog).filter_by(isp=isp_key, success=True).count()
            stats[isp_name] = count
        
        return render_template('admin/dashboard.html',
                              total=total, success=success,
                              failure=failure, success_rate=success_rate,
                              stats=stats, isp_colors=ISP_COLORS)
    finally:
        db.close()


@app.route('/admin/logs')
def admin_logs():
    if 'admin' not in session:
        return redirect('/admin/login')
    
    db = SessionLocal()
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        query = db.query(ActivationLog).order_by(ActivationLog.id.desc())
        total = query.count()
        offset = (page - 1) * per_page
        logs = query.offset(offset).limit(per_page).all()
        
        # 创建一个简单的Pagination对象
        class Pagination:
            def __init__(self, items, page, per_page, total):
                self.items = items
                self.page = page
                self.per_page = per_page
                self.total = total
                self.pages = (total + per_page - 1) // per_page if total > 0 else 1
                self.has_prev = page > 1
                self.has_next = page < self.pages
                self.prev_num = page - 1 if self.has_prev else None
                self.next_num = page + 1 if self.has_next else None
        
        pagination = Pagination(logs, page, per_page, total)
        return render_template('admin/logs.html', logs=pagination, ISP_DISPLAY=ISP_DISPLAY, ISP_COLORS=ISP_COLORS)
    finally:
        db.close()


@app.route('/admin/api/logs')
def api_logs():
    if 'admin' not in session:
        return jsonify({"error": "未登录"}), 401
    
    db = SessionLocal()
    try:
        logs = db.query(ActivationLog).order_by(ActivationLog.id.desc()).limit(100).all()
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
            'error_message': log.error_message,
            'timestamp': log.timestamp
        } for log in logs])
    finally:
        db.close()


# =============================
# 系统配置端点
# =============================

def get_available_interfaces():
    """获取可用的网络接口"""
    try:
        # 获取网卡状态
        result = subprocess.run(['ip', 'link', 'show'], capture_output=True, text=True)
        interfaces = []
        for line in result.stdout.split('\n'):
            if ': ' in line and not line.strip().startswith('lo'):
                # 提取接口名称
                iface = line.split(':')[1].strip().split('@')[0]
                if iface and not iface.startswith('docker') and not iface.startswith('br-'):
                    # 检查网卡状态
                    status = 'DOWN'
                    if ',UP,' in line or ',UP ' in line:
                        status = 'UP'
                    elif ',LOWER_UP,' in line or ',LOWER_UP ' in line:
                        status = 'UP'
                    interfaces.append({'name': iface, 'status': status})
        
        # 获取网卡 IP 地址
        result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True)
        ip_dict = {}
        current_iface = None
        for line in result.stdout.split('\n'):
            if ': ' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    iface_num = parts[0].strip()
                    if iface_num.isdigit():
                        # 查找接口名称
                        for i in range(len(result.stdout.split('\n'))):
                            if result.stdout.split('\n')[i].strip().startswith(f"{iface_num}: "):
                                match = result.stdout.split('\n')[i].strip().split(f"{iface_num}: ")[1].split()[0]
                                current_iface = match
                                break
        
        # 获取每个网卡的 IP 地址
        for iface in interfaces:
            # 获取网卡的 IP 地址
            ip_result = subprocess.run(['ip', 'addr', 'show', iface['name']], capture_output=True, text=True)
            ip_address = None
            for line in ip_result.stdout.split('\n'):
                if 'inet ' in line and 'inet6' not in line:
                    # 提取 IP 地址
                    ip_match = line.split('inet ')[1].split()[0]
                    if '/' in ip_match:
                        ip_address = ip_match.split('/')[0]
                    else:
                        ip_address = ip_match
                    break
            
            # 如果有 IP 地址，显示为 DHCP/静态
            if ip_address:
                iface['ip'] = ip_address
                iface['ip_type'] = 'DHCP/静态'
            else:
                iface['ip'] = None
                iface['ip_type'] = '无IP'
        
        return sorted(interfaces, key=lambda x: x['name'])
    except Exception as e:
        print(f"获取网卡列表失败: {e}")
        return []


def get_current_config():
    """获取当前配置"""
    config = {
        'interfaces': [],
        'data_path': './data',
        'logs_path': './logs',
        'db_path': './instance/database.db',
        'instance_path': './instance',
        'app_port': 8080,
        'admin_port': 8081,
        'tz': 'Asia/Shanghai'
    }
    
    # 从数据库读取配置
    try:
        configs = Config.query.all()
        for c in configs:
            if c.name == 'NETWORK_INTERFACES':
                config['interfaces'] = c.value.split() if c.value else []
            elif c.name == 'DATA_PATH':
                config['data_path'] = c.value
            elif c.name == 'LOGS_PATH':
                config['logs_path'] = c.value
            elif c.name == 'DB_PATH':
                config['db_path'] = c.value
            elif c.name == 'INSTANCE_PATH':
                config['instance_path'] = c.value
            elif c.name == 'APP_PORT':
                config['app_port'] = int(c.value) if c.value else 8080
            elif c.name == 'ADMIN_PORT':
                config['admin_port'] = int(c.value) if c.value else 8081
            elif c.name == 'TZ':
                config['tz'] = c.value
    except Exception as e:
        print(f"从数据库读取配置失败: {e}")
    
    return config


def save_config(data):
    """保存配置到数据库"""
    try:
        # 保存网络接口配置
        interfaces = data.get('interfaces', [])
        config = Config.query.filter_by(name='NETWORK_INTERFACES').first()
        if config:
            config.value = ' '.join(interfaces)
        else:
            config = Config(name='NETWORK_INTERFACES', value=' '.join(interfaces))
            db.session.add(config)
        
        # 保存应用端口配置
        for key, value in [('APP_PORT', data.get('app_port', 8080)), ('ADMIN_PORT', data.get('admin_port', 8081))]:
            config = Config.query.filter_by(name=key).first()
            if config:
                config.value = str(value)
            else:
                config = Config(name=key, value=str(value))
                db.session.add(config)
        
        # 保存时区配置
        tz = data.get('tz', 'Asia/Shanghai')
        config = Config.query.filter_by(name='TZ').first()
        if config:
            config.value = tz
        else:
            config = Config(name='TZ', value=tz)
            db.session.add(config)
        
        # 保存数据持久化路径配置
        for key, value in [('DATA_PATH', data.get('data_path', './data')), 
                             ('LOGS_PATH', data.get('logs_path', './logs')),
                             ('DB_PATH', data.get('db_path', './database.db')),
                             ('INSTANCE_PATH', data.get('instance_path', './instance'))]:
            config = Config.query.filter_by(name=key).first()
            if config:
                config.value = value
            else:
                config = Config(name=key, value=value)
                db.session.add(config)
        
        db.session.commit()
        print("✅ 配置已保存到数据库")
        return True
    except Exception as e:
        print(f"❌ 保存配置失败: {e}")
        return False


@app.route('/admin/config')
def config_page():
    """配置页面"""
    if 'admin' not in session:
        return redirect('/admin/login')
    
    available_interfaces = get_available_interfaces()
    current_config = get_current_config()
    return render_template('init_config.html',
                       available_interfaces=available_interfaces,
                       current_config=current_config)


@app.route('/admin/api/interfaces')
def api_interfaces():
    """获取可用网卡列表"""
    if 'admin' not in session:
        return jsonify({'error': '未登录'}), 401
    
    interfaces = get_available_interfaces()
    return jsonify({'interfaces': interfaces})


@app.route('/admin/api/config', methods=['GET', 'POST'])
def api_config():
    """获取或保存配置"""
    if 'admin' not in session:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        config = get_current_config()
        return jsonify(config)
    elif request.method == 'POST':
        data = request.get_json()
        try:
            save_config(data)
            return jsonify({'success': True, 'message': '配置保存成功'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'配置保存失败: {str(e)}'}), 500


@app.route('/admin/save', methods=['POST'])
def save():
    """保存配置"""
    if 'admin' not in session:
        return redirect('/admin/login')
    
    try:
        data = {
            'interfaces': request.form.getlist('interfaces'),
            'data_path': request.form.get('data_path', './data'),
            'logs_path': request.form.get('logs_path', './logs'),
            'db_path': request.form.get('db_path', './database.db'),
            'instance_path': request.form.get('instance_path', './instance'),
            'app_port': int(request.form.get('app_port', 8080)),
            'admin_port': int(request.form.get('admin_port', 8081)),
            'tz': request.form.get('tz', 'Asia/Shanghai')
        }
        
        save_config(data)
        
        return render_template('init_success.html', config=data)
    except Exception as e:
        return render_template('init_config.html',
                           available_interfaces=get_available_interfaces(),
                           current_config=get_current_config(),
                           error=str(e))


# =============================
# 分页日志接口
# =============================
@app.route('/logs')
def get_logs():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page

    db = SessionLocal()
    try:
        total = db.query(ActivationLog).count()
        logs = db.query(ActivationLog).order_by(ActivationLog.timestamp.desc()).offset(offset).limit(per_page).all()
    except Exception as e:
        logger.error(f"Database error in /logs: {str(e)}")
        return jsonify({'error': 'Failed to fetch logs'}), 500
    finally:
        db.close()

    data = [{
        'name': log.name or '',
        'role': log.role or '',
        'isp': log.isp or '',
        'username': log.username or '',
        'success': log.success,
        'ip': log.ip or '',
        'mac': log.mac or '',
        'error_code': log.error_code or '',
        'error_message': log.error_message or '',
        'timestamp': log.timestamp or ''
    } for log in logs]

    return jsonify({
        'data': data,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    })


# =============================
# Dashboard 页面
# =============================
@app.route('/dashboard')
def dashboard():
    try:
        sync_logs(latest_only=True)
    except Exception as e:
        logger.error(f"自动同步失败: {e}")
    
    # 获取统计数据
    db = SessionLocal()
    try:
        # 按日期统计
        logs = db.query(ActivationLog).all()
        count_by_day = {}
        for log in logs:
            if log.timestamp:
                date = log.timestamp.split()[0] if ' ' in log.timestamp else log.timestamp
                if date not in count_by_day:
                    count_by_day[date] = 0
                count_by_day[date] += 1
        
        # 按ISP统计
        isp_count = {}
        for log in logs:
            isp = log.isp or 'Unknown'
            if isp not in isp_count:
                isp_count[isp] = 0
            isp_count[isp] += 1
        
        period = "最近记录"
    finally:
        db.close()
    
    return render_template('dashboard.html', period=period, count_by_day=count_by_day, isp_count=isp_count)


@app.route('/records')
def records():
    """查看拨号记录"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    db = SessionLocal()
    try:
        total = db.query(ActivationLog).count()
        logs = db.query(ActivationLog).order_by(ActivationLog.id.desc()).offset(offset).limit(per_page).all()
        
        data = [{
            'name': log.name or '',
            'username': log.username or '',
            'isp': log.isp or '',
            'success': log.success,
            'error_code': log.error_code or '',
            'activated_at': log.timestamp or '',
            'mac': log.mac or '',
            'ip': log.ip or ''
        } for log in logs]
    finally:
        db.close()
    
    return render_template('records.html', data=data, page=page, per_page=per_page, total=total)


@app.route('/admin_list')
def admin_list():
    """管理员管理"""
    if 'admin' not in session:
        return redirect('/admin/login')
    
    admins = AdminUser.query.all()
    return render_template('admin_list.html', admins=admins)


@app.route('/admin_add', methods=['POST'])
def admin_add():
    """添加管理员"""
    if 'admin' not in session:
        return redirect('/admin/login')
    
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role', 'admin')
    
    if AdminUser.query.filter_by(username=username).first():
        return render_template('admin_list.html', admins=AdminUser.query.all(), error='用户名已存在')
    
    # 使用pbkdf2_hmac加密（与init_db.py一致）
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode(),
        salt.encode(),
        100000
    ).hex()
    admin = AdminUser(username=username, password_hash=pwd_hash, salt=salt, role=role)
    db.session.add(admin)
    db.session.commit()
    
    return redirect(url_for('admin_list'))


@app.route('/admin_delete', methods=['POST'])
def admin_delete():
    """删除管理员"""
    if 'admin' not in session:
        return redirect('/admin/login')
    
    username = request.form.get('username')
    admin = AdminUser.query.filter_by(username=username).first()
    if admin:
        db.session.delete(admin)
        db.session.commit()
    
    return redirect(url_for('admin_list'))


# =============================
# 统计接口
# =============================
@app.route('/stats')
def get_stats():
    db = SessionLocal()
    try:
        logs = db.query(ActivationLog).all()
    except Exception as e:
        logger.error(f"Database error in /stats: {str(e)}")
        return jsonify([]), 500
    finally:
        db.close()

    stats = {}
    for log in logs:
        isp = log.isp or 'Unknown'
        if isp not in stats:
            stats[isp] = {"total": 0, "success": 0}
        stats[isp]["total"] +=1
        if log.success:
            stats[isp]["success"] += 1

    result = []
    for isp, data in stats.items():
        total = data["total"]
        success = data["success"]
        failure = total - success
        rate = f"{success / total * 100:.1f}%" if total > 0 else "0%"
        result.append({
            "isp": isp,
            "total": total,
            "success": success,
            "failure": failure,
            "rate": rate
        })
    result.sort(key=lambda x: x["total"], reverse=True)
    return jsonify(result)


# =============================
# CSV 导出接口
# =============================
@app.route('/export_csv')
def export_csv():
    db = SessionLocal()
    try:
        logs = db.query(ActivationLog).all()
    except Exception as e:
        logger.error(f"Database error when fetching logs for CSV export: {str(e)}")
        return jsonify({'error': 'Failed to fetch logs for export'}), 500
    finally:
        db.close()

    start_str = request.args.get('start')
    end_str = request.args.get('end')
    LOG_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
    PARAM_TIME_FORMAT = '%Y-%m-%dT%H:%M'
    filtered_logs = []

    for log in logs:
        if not log.timestamp or not isinstance(log.timestamp, str):
            continue
        try:
            log_time = datetime.strptime(log.timestamp.strip(), LOG_TIME_FORMAT)
        except ValueError:
            continue
        skip_log = False
        if start_str:
            try:
                start_time = datetime.strptime(start_str, PARAM_TIME_FORMAT)
                if log_time < start_time:
                    skip_log = True
            except ValueError:
                pass
        if not skip_log and end_str:
            try:
                end_time = datetime.strptime(end_str, PARAM_TIME_FORMAT)
                if log_time > end_time:
                    skip_log = True
            except ValueError:
                pass
        if not skip_log:
            filtered_logs.append(log)

    si = StringIO()
    si.write('\ufeff')
    cw = csv.writer(si)
    cw.writerow(['姓名', '角色', '运营商', '账号', '状态', 'IP地址', 'MAC地址', '时间戳', '错误码', '错误信息'])
    for log in filtered_logs:
        status = '成功' if log.success else '失败'
        cw.writerow([log.name or '', log.role or '', log.isp or '', log.username or '',
                     status, log.ip or '', log.mac or '', log.timestamp or '',
                     log.error_code or '', log.error_message or ''])
    output = make_response(si.getvalue())
    filename = f"pppoe_logs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv; charset=utf-8-sig"
    return output


# =============================
# 启动 Flask
# =============================
if __name__ == '__main__':
    try:
        init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
    app.run(host='0.0.0.0', port=ADMIN_PORT, debug=False)
