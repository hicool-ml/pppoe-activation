# dashboard.py
from flask import Flask, jsonify, render_template, request, make_response, redirect, url_for, session
from models import SessionLocal, ActivationLog, NetworkConfig, AdminUser, Config, init_db
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

# ========== 启动时创建表和默认管理员 ==========
import secrets
from datetime import datetime
with app.app_context():
    init_db()
    session_db = SessionLocal()
    try:
        if session_db.query(AdminUser).count() == 0:
            # 使用pbkdf2_hmc加密（与init_db.py一致）
            salt = secrets.token_hex(16)
            pwd_hash = hashlib.pbkdf2_hmac(
                'sha256',
                'admin123'.encode(),
                salt.encode(),
                100000
            ).hex()
            admin = AdminUser(username='admin', password_hash=pwd_hash, salt=salt, role='admin', created_at=str(datetime.now()))
            session_db.add(admin)
            session_db.commit()
            print("✅ 默认管理员创建成功：admin / admin123")
    finally:
        session_db.close()

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

@app.route('/', methods=['GET'])
def index():
    # 根路径重定向到登录页面
    return redirect('/login')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # 使用pbkdf2_hmac加密（与init_db.py一致）
        session_db = SessionLocal()
        try:
            user = session_db.query(AdminUser).filter_by(username=username).first()
            if user:
                pwd_hash = hashlib.pbkdf2_hmac(
                    'sha256',
                    password.encode(),
                    user.salt.encode() if hasattr(user, 'salt') else b'',
                    100000
                ).hex()
                if pwd_hash == user.password_hash:
                    session['admin'] = user.username
                    session['admin_role'] = user.role  # 保存用户角色
                    return redirect('/dashboard')
        finally:
            session_db.close()

        return render_template('admin/login.html', error="用户名或密码错误")
    return render_template('admin/login.html')


@app.route('/logout')
def logout():
    session.pop('admin', None)
    session.pop('admin_role', None)
    return redirect('/login')


@app.route('/logs')
def admin_logs():
    if 'admin' not in session:
        return redirect('/login')

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
        
        # 获取当前用户角色
        current_role = session.get('admin_role')
        
        return render_template('admin/logs.html', logs=pagination, ISP_DISPLAY=ISP_DISPLAY, ISP_COLORS=ISP_COLORS, current_role=current_role)
    finally:
        db.close()


@app.route('/api/logs')
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
        'data_path': '/opt/pppoe-activation/data',
        'logs_path': '/opt/pppoe-activation/logs',
        'db_path': '/opt/pppoe-activation/instance/database.db',
        'instance_path': '/opt/pppoe-activation/instance',
        'app_port': 8080,
        'admin_port': 8081,
        'tz': 'Asia/Shanghai',
        'net_mode': 'physical',
        'vlan_id': ''
    }
    
    # 从NetworkConfig表读取网络配置
    try:
        session_db = SessionLocal()
        net_config = session_db.query(NetworkConfig).first()
        if net_config:
            config['net_mode'] = net_config.net_mode
            config['vlan_id'] = net_config.vlan_id or ''
            
            # 根据网络模式生成接口列表
            if net_config.net_mode == 'vlan' and net_config.vlan_id and net_config.base_interface:
                # VLAN 模式：返回所有 VLAN 子接口列表
                vlan_ids = net_config.vlan_id.split(',')
                vlan_interfaces = []
                for vlan_id in vlan_ids:
                    vlan_id = vlan_id.strip()
                    if vlan_id:
                        vlan_interfaces.append(f"{net_config.base_interface}.{vlan_id}")
                config['interfaces'] = vlan_interfaces
            elif net_config.base_interface:
                # 物理模式：返回物理网卡
                config['interfaces'] = [net_config.base_interface]
        session_db.close()
    except Exception as e:
        print(f"从NetworkConfig表读取网络配置失败: {e}")
    
    # 从Config表读取其他配置
    try:
        session_db = SessionLocal()
        configs = session_db.query(Config).all()
        for c in configs:
            if c.name == 'DATA_PATH':
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
        session_db.close()
    except Exception as e:
        print(f"从Config表读取配置失败: {e}")
    
    return config


def parse_vlan_ids(vlan_id_str):
    """
    解析 VLAN ID 字符串，支持多种格式
    
    支持的格式：
    1. 单个 VLAN ID：2000
    2. 逗号分隔的多个 VLAN ID：2000,2001,2002
    3. VLAN ID 范围：2000-2005
    4. 混合格式：2000,2002-2005,2007
    
    Args:
        vlan_id_str: VLAN ID 字符串
    
    Returns:
        list: VLAN ID 列表
    
    Raises:
        ValueError: 如果格式不正确或 VLAN ID 超出范围
    """
    vlan_ids = []
    
    # 按逗号分隔
    parts = vlan_id_str.split(',')
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # 检查是否为范围格式（例如：2000-2005）
        if '-' in part:
            try:
                start, end = part.split('-')
                start = int(start.strip())
                end = int(end.strip())
                
                if start < 1 or start > 4094:
                    raise ValueError(f"VLAN ID {start} 超出范围（1-4094）")
                if end < 1 or end > 4094:
                    raise ValueError(f"VLAN ID {end} 超出范围（1-4094）")
                
                if start > end:
                    raise ValueError(f"VLAN 范围 {start}-{end} 无效（起始值大于结束值）")
                
                # 添加范围内的所有 VLAN ID
                vlan_ids.extend(range(start, end + 1))
            except ValueError as e:
                if "invalid literal" in str(e):
                    raise ValueError(f"VLAN ID 范围格式不正确：{part}（正确格式：2000-2005）")
                raise
        else:
            # 单个 VLAN ID
            try:
                vlan_id = int(part)
                if vlan_id < 1 or vlan_id > 4094:
                    raise ValueError(f"VLAN ID {vlan_id} 超出范围（1-4094）")
                vlan_ids.append(vlan_id)
            except ValueError as e:
                if "invalid literal" in str(e):
                    raise ValueError(f"VLAN ID 格式不正确：{part}（必须为数字）")
                raise
    
    # 去重并排序
    vlan_ids = sorted(list(set(vlan_ids)))
    
    return vlan_ids


def save_config(data):
    """保存配置到数据库"""
    try:
        # 保存网络配置到NetworkConfig表
        net_mode = data.get('net_mode', 'physical')
        interfaces = data.get('interfaces', [])
        
        if net_mode == "vlan":
            # VLAN 模式：用户选择物理网卡 + 指定 VLAN ID
            vlan_id_str = data.get('vlan_id', '').strip()
            if not vlan_id_str:
                raise ValueError("VLAN 模式需要指定 VLAN ID")
            
            # 解析 VLAN ID（支持范围和逗号分隔格式）
            vlan_ids = parse_vlan_ids(vlan_id_str)
            if not vlan_ids:
                raise ValueError("未找到有效的 VLAN ID")
            
            # 确定物理网卡
            base_interface = None
            if interfaces:
                first_interface = interfaces[0]
                if '.' in first_interface:
                    base_interface = first_interface.split('.')[0]
                else:
                    base_interface = first_interface
            else:
                raise ValueError("VLAN 模式需要选择至少一个物理网卡")
            
            # 保存为逗号分隔的字符串
            vlan_id_str = ','.join(map(str, vlan_ids))
            
            # 保存到NetworkConfig表
            net_config = NetworkConfig.query.first()
            if not net_config:
                net_config = NetworkConfig()
            
            net_config.net_mode = net_mode
            net_config.base_interface = base_interface
            net_config.vlan_id = vlan_id_str
            db.session.add(net_config)
            
            print(f"VLAN 模式：物理网卡={base_interface}, VLAN ID={vlan_id_str}")
        else:
            # 物理模式
            net_config = NetworkConfig.query.first()
            if not net_config:
                net_config = NetworkConfig()
            
            net_config.net_mode = net_mode
            net_config.base_interface = interfaces[0] if interfaces else 'eth0'
            net_config.vlan_id = None
            db.session.add(net_config)
            
            print(f"物理模式：物理网卡={net_config.base_interface}")
        
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
                             ('DB_PATH', data.get('db_path', './instance/database.db')),
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


@app.route('/config')
def config_page():
    """配置页面（只读）"""
    if 'admin' not in session:
        return redirect('/login')

    current_config = get_current_config()
    current_role = session.get('admin_role')
    
    # 如果是super角色，重定向到9999端口
    if current_role == 'super':
        return redirect('http://192.168.0.112:9999')
    
    # 使用只读模板显示配置
    return render_template('configlist.html',
                       current_config=current_config,
                       current_role=current_role)


@app.route('/api/interfaces')
def api_interfaces():
    """获取可用网卡列表"""
    if 'admin' not in session:
        return jsonify({'error': '未登录'}), 401

    interfaces = get_available_interfaces()
    return jsonify({'interfaces': interfaces})


@app.route('/api/config', methods=['GET', 'POST'])
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


@app.route('/save', methods=['GET', 'POST'])
def save():
    """保存配置"""
    if 'admin' not in session:
        return redirect('/login')
    
    # 只有super角色才能保存配置
    if session.get('admin_role') != 'super':
        return render_template('init_config.html',
                           available_interfaces=get_available_interfaces(),
                           current_config=get_current_config(),
                           error='权限不足，只有超级管理员才能修改配置')

    if request.method == 'POST':
        try:
            data = {
                'interfaces': request.form.getlist('interfaces'),
                'data_path': request.form.get('data_path', './data'),
                'logs_path': request.form.get('logs_path', './logs'),
                'db_path': request.form.get('db_path', './instance/database.db'),
                'instance_path': request.form.get('instance_path', './instance'),
                'app_port': int(request.form.get('app_port', 8080)),
                'admin_port': int(request.form.get('admin_port', 8081)),
                'tz': request.form.get('tz', 'Asia/Shanghai'),
                'net_mode': request.form.get('net_mode', 'physical'),
                'vlan_id': request.form.get('vlan_id', '')
            }

            save_config(data)

            return render_template('init_success.html', config=data)
        except Exception as e:
            return render_template('init_config.html',
                               available_interfaces=get_available_interfaces(),
                               current_config=get_current_config(),
                               error=str(e))
    else:
        # GET请求，返回保存成功页面
        return render_template('init_success.html')


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
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'admin' not in session:
        return redirect('/login')

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

        # 统计成功和失败次数
        success_count = 0
        failure_count = 0
        for log in logs:
            if log.success:
                success_count += 1
            else:
                failure_count += 1

        period = "最近记录"
    finally:
        db.close()

    # 获取当前用户角色
    current_role = session.get('admin_role')
    
    return render_template('dashboard.html', period=period, count_by_day=count_by_day, isp_count=isp_count, success_count=success_count, failure_count=failure_count, current_role=current_role)


@app.route('/admin_list')
def admin_list():
    """管理员管理"""
    if 'admin' not in session:
        return redirect('/login')

    session_db = SessionLocal()
    try:
        admins = session_db.query(AdminUser).all()
        # 添加当前用户角色到模板上下文
        current_role = session.get('admin_role')
        
        # 如果当前用户是admin角色，过滤掉super角色的用户
        if current_role == 'admin':
            admins = [a for a in admins if a.role != 'super']
        
        return render_template('admin_list.html', admins=admins, current_role=current_role)
    finally:
        session_db.close()


@app.route('/admin_add', methods=['POST'])
def admin_add():
    """添加管理员"""
    if 'admin' not in session:
        return redirect('/login')
    
    # 只有super角色才能添加管理员
    if session.get('admin_role') != 'super':
        session_db = SessionLocal()
        try:
            admins = session_db.query(AdminUser).all()
            return render_template('admin_list.html', admins=admins, error='权限不足，只有超级管理员才能添加管理员')
        finally:
            session_db.close()

    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role', 'admin')

    session_db = SessionLocal()
    try:
        if session_db.query(AdminUser).filter_by(username=username).first():
            admins = session_db.query(AdminUser).all()
            return render_template('admin_list.html', admins=admins, error='用户名已存在')

        # 使用pbkdf2_hmac加密（与init_db.py一致）
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode(),
            salt.encode(),
            100000
        ).hex()
        admin = AdminUser(username=username, password_hash=pwd_hash, salt=salt, role=role, created_at=str(datetime.now()))
        session_db.add(admin)
        session_db.commit()

        return redirect(url_for('admin_list'))
    finally:
        session_db.close()


@app.route('/admin_delete', methods=['POST'])
def admin_delete():
    """删除管理员"""
    if 'admin' not in session:
        return redirect('/login')
    
    username = request.form.get('username')
    current_role = session.get('admin_role')
    
    # admin角色不能删除super用户
    if current_role != 'super':
        session_db = SessionLocal()
        try:
            target_user = session_db.query(AdminUser).filter_by(username=username).first()
            if target_user and target_user.role == 'super':
                admins = session_db.query(AdminUser).all()
                return render_template('admin_list.html', admins=admins, error='权限不足，不能删除超级管理员')
        finally:
            session_db.close()

    session_db = SessionLocal()
    try:
        admin = session_db.query(AdminUser).filter_by(username=username).first()
        if admin:
            session_db.delete(admin)
            session_db.commit()

        return redirect(url_for('admin_list'))
    finally:
        session_db.close()


@app.route('/change_password', methods=['GET', 'POST'])
def admin_change_password():
    """修改管理员密码"""
    if 'admin' not in session:
        return redirect('/login')

    # 获取要修改密码的用户名（从URL参数获取）
    target_username = request.args.get('username')
    current_username = session.get('admin')
    current_role = session.get('admin_role')

    # 如果没有指定用户名，默认修改当前用户的密码
    if not target_username:
        target_username = current_username

    # 只有super角色可以修改其他用户的密码，admin角色只能修改自己的密码
    if current_role != 'super' and target_username != current_username:
        return render_template('admin/change_password.html', error='权限不足，只能修改自己的密码', username=current_username)

    # 获取目标用户
    session_db = SessionLocal()
    try:
        target_user = session_db.query(AdminUser).filter_by(username=target_username).first()
        if not target_user:
            return render_template('admin/change_password.html', error='用户不存在')

        if request.method == 'POST':
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            # 验证新密码
            if new_password != confirm_password:
                return render_template('admin/change_password.html', error='两次输入的密码不一致', username=target_username)

            if len(new_password) < 6:
                return render_template('admin/change_password.html', error='密码长度不能少于6位', username=target_username)

            # 更新密码
            new_salt = secrets.token_hex(16)
            new_pwd_hash = hashlib.pbkdf2_hmac(
                'sha256',
                new_password.encode(),
                new_salt.encode(),
                100000
            ).hex()

            target_user.password_hash = new_pwd_hash
            target_user.salt = new_salt
            session_db.commit()

            return render_template('admin/change_password.html', success='密码修改成功', username=target_username)

        return render_template('admin/change_password.html', username=target_username)
    finally:
        session_db.close()


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
