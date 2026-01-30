#!/usr/bin/env python3
"""
初始化配置脚本
在首次启动时，通过 Web 界面配置网卡和持久化存储路径

注意：这是一个独立的初始化脚本，不应该依赖 app.py
"""

import os
import sys
import json
import subprocess
import hashlib
import secrets
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import NetworkConfig, AdminUser

app = Flask(__name__)
app.secret_key = 'your-super-secret-key-change-it-please'  # 请修改！


# =============================
# 登录/登出
# =============================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """超级管理员登录"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # 使用pbkdf2_hmac加密
        session_db = SessionLocal()
        try:
            user = session_db.query(AdminUser).filter_by(username=username).first()
            if user and user.role == 'super':  # 只允许super角色登录
                pwd_hash = hashlib.pbkdf2_hmac(
                    'sha256',
                    password.encode(),
                    user.salt.encode() if hasattr(user, 'salt') else b'',
                    100000
                ).hex()
                if pwd_hash == user.password_hash:
                    session['super_admin'] = user.username
                    return redirect('/')
        finally:
            session_db.close()

        return render_template('admin/login.html', error="用户名或密码错误或权限不足")
    return render_template('admin/login.html')


@app.route('/logout')
def logout():
    """登出"""
    session.pop('super_admin', None)
    return redirect('/login')


def require_super_admin(f):
    """装饰器：要求超级管理员权限"""
    def wrapper(*args, **kwargs):
        if 'super_admin' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# 独立的数据库会话工厂（不依赖 app.py）
DB_PATH = '/opt/pppoe-activation/instance/database.db'
engine = create_engine(f'sqlite:///{DB_PATH}')
SessionLocal = sessionmaker(bind=engine)

# 配置文件路径
CONFIG_FILE = '/opt/pppoe-activation/config.py'
ENV_FILE = '/opt/pppoe-activation/.env'
INIT_FLAG_FILE = '/opt/pppoe-activation/.initialized'


def get_available_interfaces():
    """获取可用的网络接口"""
    try:
        # 使用 ip -j addr show 一次性获取所有接口信息（JSON 格式）
        result = subprocess.run(['ip', '-j', 'addr', 'show'], capture_output=True, text=True, check=True)
        import json
        interfaces_data = json.loads(result.stdout)
        
        interfaces = []
        for iface_data in interfaces_data:
            # 跳过回环接口、Docker 接口和网桥接口
            iface_name = iface_data.get('ifname', '')
            if iface_name in ['lo', 'docker0'] or iface_name.startswith('docker') or iface_name.startswith('br-'):
                continue
            
            # 获取接口状态
            status = 'UP' if iface_data.get('operstate') == 'UP' else 'DOWN'
            
            # 获取 IPv4 地址
            ip_address = None
            for addr_info in iface_data.get('addr_info', []):
                if addr_info.get('family') == 'inet':
                    ip_address = addr_info.get('local')
                    break
            
            # 构建接口信息
            interfaces.append({
                'name': iface_name,
                'status': status,
                'ip': ip_address,
                'ip_type': 'DHCP/静态' if ip_address else '无IP'
            })
        
        return sorted(interfaces, key=lambda x: x['name'])
    except Exception as e:
        print(f"获取网卡列表失败: {e}")
        return []


def get_current_config():
    """
    获取当前配置
    
    配置源职责划分：
    - config.py: 初始化默认值（只读）
    - .env: Docker 运行参数（端口、路径）
    - 数据库: 所有运行期配置（网络 / VLAN / 接口选择）
    
    优先级：数据库 > .env > config.py
    """
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
    
    # 1. 读取 config.py（初始化默认值，只读）
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            for line in f:
                if 'NETWORK_INTERFACES' in line and '=' in line:
                    try:
                        interfaces_str = line.split('=')[1].strip()
                        if interfaces_str.startswith('['):
                            interfaces_str = interfaces_str[1:-1]
                        config['interfaces'] = [iface.strip().strip("'\"") for iface in interfaces_str.split(',')]
                    except:
                        pass
    
    # 2. 读取 .env（Docker 运行参数）
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key == 'DATA_PATH':
                        config['data_path'] = value
                    elif key == 'LOGS_PATH':
                        config['logs_path'] = value
                    elif key == 'DB_PATH':
                        config['db_path'] = value
                    elif key == 'INSTANCE_PATH':
                        config['instance_path'] = value
                    elif key == 'APP_PORT':
                        config['app_port'] = int(value)
                    elif key == 'ADMIN_PORT':
                        config['admin_port'] = int(value)
                    elif key == 'TZ':
                        config['tz'] = value
    
    # 3. 从数据库读取网络配置（所有运行期配置，优先级最高）
    try:
        session = SessionLocal()
        net_config = session.query(NetworkConfig).first()
        if net_config:
            config['net_mode'] = net_config.net_mode
            config['vlan_id'] = net_config.vlan_id or ''
            
            # 根据网络模式生成接口列表
            if net_config.net_mode == 'vlan' and net_config.vlan_id and net_config.base_interface:
                # VLAN 模式：只返回 VLAN 子接口列表
                vlan_ids = net_config.vlan_id.split(',')
                vlan_interfaces = []
                for vlan_id in vlan_ids:
                    vlan_id = vlan_id.strip()
                    if vlan_id:
                        vlan_interfaces.append(f"{net_config.base_interface}.{vlan_id}")
                config['interfaces'] = vlan_interfaces
                print(f"VLAN 模式：生成的 VLAN 子接口列表: {vlan_interfaces}")
            elif net_config.base_interface:
                # 物理模式：返回物理网卡
                config['interfaces'] = [net_config.base_interface]
        session.close()
    except Exception as e:
        print(f"从数据库读取网络配置失败: {e}")
    
    return config


def ensure_vlan_interface(base, vlan_id):
    """
    确保 VLAN 子接口存在
    
    Args:
        base: 基础物理接口（如 enp3s0）
        vlan_id: VLAN ID（如 100）
    
    Returns:
        str: VLAN 子接口名（如 enp3s0.100）
    """
    vlan_if = f"{base}.{vlan_id}"
    
    try:
        # 检查 VLAN 子接口是否已存在
        result = subprocess.run(['ip', 'link', 'show', vlan_if], 
                              capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            print(f"VLAN 子接口 {vlan_if} 已存在")
        else:
            # 创建 VLAN 子接口
            print(f"创建 VLAN 子接口: {vlan_if}")
            subprocess.run(
                ['ip', 'link', 'add', 'link', base, 'name', vlan_if, 'type', 'vlan', 'id', str(vlan_id)],
                check=True,
                stderr=subprocess.PIPE
            )
            print(f"VLAN 子接口 {vlan_if} 创建成功")
        
        # 确保 VLAN 子接口处于 UP 状态
        subprocess.run(['ip', 'link', 'set', vlan_if, 'up'], check=True)
        print(f"VLAN 子接口 {vlan_if} 已设置为 UP 状态")
        
        return vlan_if
    except subprocess.CalledProcessError as e:
        print(f"创建/配置 VLAN 子接口失败: {e}")
        if e.stderr:
            print(f"错误详情: {e.stderr.decode('utf-8', errors='ignore')}")
        raise RuntimeError(f"创建 VLAN 子接口失败: {str(e)}")


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
    """保存配置"""
    # 后端校验：VLAN ID 必须在 1-4094 之间
    net_mode = data.get('net_mode', 'physical')
    interfaces = data.get('interfaces', [])
    
    if net_mode == "vlan":
        # VLAN 模式：用户选择物理网卡 + 指定 VLAN ID
        # 系统自动创建所有 VLAN 子接口，并自动选择所有 VLAN 子接口参与拨号
        
        vlan_id_str = data.get('vlan_id', '').strip()
        if not vlan_id_str:
            raise ValueError("VLAN 模式需要指定 VLAN ID")
        
        # 解析 VLAN ID（支持范围和逗号分隔格式）
        try:
            vlan_ids = parse_vlan_ids(vlan_id_str)
            if not vlan_ids:
                raise ValueError("未找到有效的 VLAN ID")
        except ValueError as e:
            raise e
        
        # 确定物理网卡
        base_interface = None
        if interfaces:
            # 从用户选择的接口中确定物理网卡
            first_interface = interfaces[0]
            if '.' in first_interface:
                # 如果是 VLAN 子接口，提取物理网卡部分
                base_interface = first_interface.split('.')[0]
            else:
                # 如果是物理网卡，直接使用
                base_interface = first_interface
        else:
            raise ValueError("VLAN 模式需要选择至少一个物理网卡")
        
        # 保存为逗号分隔的字符串
        data['vlan_id'] = ','.join(map(str, vlan_ids))
        # 保存物理网卡到 base_interface
        data['base_interface'] = base_interface
        
        print(f"VLAN 模式：物理网卡={base_interface}, VLAN ID={data['vlan_id']}")
    else:
        # 物理模式：直接使用用户选择的接口
        data['vlan_id'] = None
        data['base_interface'] = interfaces[0] if interfaces else 'eth0'
        print(f"物理模式：物理网卡={data['base_interface']}")
    
    # 保存 config.py
    config_content = f"""# PPPOE 激活系统配置文件
# 自动生成于 {subprocess.run(['date'], capture_output=True, text=True).stdout.strip()}

BASE_DIR = '/opt/pppoe-activation'

# SQLite 数据库绝对路径（固定）
DATABASE_PATH = '/opt/pppoe-activation/instance/database.db'

# 网卡配置（用户配置）
# 注意：NETWORK_INTERFACES 仅用于初始化默认值展示，不参与运行期逻辑
# 运行期网络配置请参考数据库中的 NetworkConfig 表
NETWORK_INTERFACES = {json.dumps(interfaces if interfaces else ['eth0'])}

# 日志目录
PPP_LOG_DIR = f'{{BASE_DIR}}/logs'

# 服务端口配置
APP_PORT = {data.get('app_port', 8080)}
ADMIN_PORT = {data.get('admin_port', 8081)}
"""

    with open(CONFIG_FILE, 'w') as f:
        f.write(config_content)
    
    # 保存 .env
    env_content = f"""# PPPOE 激活系统 Docker 环境变量配置
# 自动生成于 {subprocess.run(['date'], capture_output=True, text=True).stdout.strip()}

# 应用端口配置
APP_PORT={data.get('app_port', 8080)}
ADMIN_PORT={data.get('admin_port', 8081)}

# 网卡配置（使用空格分隔多个网卡）
# 注意：NETWORK_INTERFACES 仅用于 docker-compose 兼容性，主程序不得读取
# 运行期网络配置请参考数据库中的 NetworkConfig 表
NETWORK_INTERFACES={' '.join(interfaces if interfaces else ['eth0'])}

# 时区配置
TZ={data.get('tz', 'Asia/Shanghai')}

# 数据持久化路径配置
DATA_PATH={data.get('data_path', './data')}
LOGS_PATH={data.get('logs_path', './logs')}
DB_PATH={data.get('db_path', './instance/database.db')}
INSTANCE_PATH={data.get('instance_path', './instance')}

# 网络模式配置
NET_MODE={data.get('net_mode', 'physical')}
VLAN_ID={data.get('vlan_id', '')}
"""

    with open(ENV_FILE, 'w') as f:
        f.write(env_content)
    
    # 保存网络配置到数据库（唯一网络配置源）
    try:
        session = SessionLocal()
        net_config = session.query(NetworkConfig).first()
        if not net_config:
            net_config = NetworkConfig()
        
        net_config.net_mode = data.get('net_mode', 'physical')
        net_config.base_interface = data.get('base_interface', 'eth0')
        net_config.vlan_id = data.get('vlan_id') or None
        session.add(net_config)
        session.commit()
        print(f"网络配置已保存到数据库: net_mode={net_config.net_mode}, base_interface={net_config.base_interface}, vlan_id={net_config.vlan_id}")
        
        # 如果是 VLAN 模式，创建所有 VLAN 子接口
        if net_config.net_mode == "vlan" and net_config.vlan_id:
            # 先删除旧的 VLAN 子接口（避免重复）
            try:
                # 获取所有 VLAN 子接口
                result = subprocess.run(['ip', '-j', 'link', 'show'], capture_output=True, text=True, check=True)
                interfaces_data = json.loads(result.stdout)
                
                for iface_data in interfaces_data:
                    ifname = iface_data.get('ifname', '')
                    # 检查是否为 VLAN 子接口（格式：base_interface.vlan_id）
                    if '.' in ifname and ifname.startswith(net_config.base_interface):
                        # 删除旧的 VLAN 子接口
                        subprocess.run(['ip', 'link', 'delete', ifname], check=False)
                        print(f"删除旧的 VLAN 子接口: {ifname}")
            except Exception as e:
                print(f"删除旧的 VLAN 子接口失败: {e}")
            
            # 获取所有 VLAN ID（用于创建子接口）
            vlan_ids = net_config.vlan_id.split(',')
            if vlan_ids:
                created_count = 0
                for vlan_id_str in vlan_ids:
                    vlan_id_str = vlan_id_str.strip()
                    if not vlan_id_str:
                        continue
                    try:
                        ensure_vlan_interface(net_config.base_interface, vlan_id_str)
                        print(f"VLAN 子接口已创建: {net_config.base_interface}.{vlan_id_str}")
                        created_count += 1
                    except Exception as e:
                        print(f"创建 VLAN 子接口 {net_config.base_interface}.{vlan_id_str} 失败: {e}")
                        # 不影响配置保存，只是记录错误
                print(f"共创建了 {created_count} 个 VLAN 子接口")
        else:
            # 如果是物理接口模式，删除所有 VLAN 子接口
            try:
                # 获取所有 VLAN 子接口
                result = subprocess.run(['ip', '-j', 'link', 'show'], capture_output=True, text=True, check=True)
                interfaces_data = json.loads(result.stdout)
                
                deleted_count = 0
                for iface_data in interfaces_data:
                    ifname = iface_data.get('ifname', '')
                    # 检查是否为 VLAN 子接口（包含 '.' 的接口）
                    if '.' in ifname:
                        # 删除 VLAN 子接口
                        subprocess.run(['ip', 'link', 'delete', ifname], check=False)
                        print(f"删除 VLAN 子接口: {ifname}")
                        deleted_count += 1
                
                if deleted_count > 0:
                    print(f"共删除了 {deleted_count} 个 VLAN 子接口（切换到物理接口模式）")
            except Exception as e:
                print(f"删除 VLAN 子接口失败: {e}")
        
        session.close()
    except Exception as e:
        print(f"保存网络配置到数据库失败: {e}")
        raise
    
    # 创建初始化标记
    with open(INIT_FLAG_FILE, 'w') as f:
        f.write('initialized')
    
    # 立即重启主应用容器
    try:
        result = subprocess.run(['docker', 'restart', 'pppoe-activation'], 
                              capture_output=True, text=True, timeout=10)
        print(f"主应用容器重启命令已执行: {result.stdout}")
    except Exception as e:
        print(f"重启主应用容器失败: {e}")

    return True


@app.route('/')
@require_super_admin
def index():
    """配置页面"""
    available_interfaces = get_available_interfaces()
    current_config = get_current_config()
    # 添加is_super标志（因为9999端口只允许super角色访问，所以始终为True）
    current_config['is_super'] = True
    return render_template('init_config.html',
                       available_interfaces=available_interfaces,
                       current_config=current_config)


@app.route('/api/interfaces')
@require_super_admin
def api_interfaces():
    """获取可用网卡列表"""
    interfaces = get_available_interfaces()
    return jsonify({'interfaces': interfaces})


@app.route('/api/config', methods=['GET', 'POST'])
@require_super_admin
def api_config():
    """获取或保存配置"""
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


@app.route('/api/restart-status')
@require_super_admin
def restart_status():
    """获取重启状态"""
    try:
        result = subprocess.run(['docker', 'ps', '-a', '--format', '{{.Status}}', 'pppoe-activation'],
                              capture_output=True, text=True)
        status = result.stdout.strip()
        return jsonify({'status': status})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/save', methods=['POST'])
@require_super_admin
def save():
    """保存配置并重启"""
    try:
        data = {
            'interfaces': request.form.getlist('interfaces'),
            'data_path': request.form.get('data_path', './data'),
            'logs_path': request.form.get('logs_path', './logs'),
            'db_path': request.form.get('db_path', './instance/database.db'),
            'instance_path': request.form.get('instance_path', './instance'),
            'app_port': int(request.form.get('app_port', 80)),
            'admin_port': int(request.form.get('admin_port', 80)),
            'tz': request.form.get('tz', 'Asia/Shanghai'),
            'net_mode': request.form.get('net_mode', 'physical'),
            'vlan_id': request.form.get('vlan_id', '')
        }
        
        print(f"接收到配置数据: net_mode={data['net_mode']}, vlan_id='{data['vlan_id']}'")
        
        save_config(data)
        
        return render_template('init_success.html', config=data)
    except Exception as e:
        print(f"保存配置失败: {e}")
        import traceback
        traceback.print_exc()
        available_interfaces = get_available_interfaces()
        current_config = get_current_config()
        # 添加is_super标志（因为9999端口只允许super角色访问，所以始终为True）
        current_config['is_super'] = True
        return render_template('init_config.html',
                           available_interfaces=available_interfaces,
                           current_config=current_config,
                           error=str(e))


if __name__ == '__main__':
    # 创建root超级管理员（如果不存在）
    session_db = SessionLocal()
    try:
        root_user = session_db.query(AdminUser).filter_by(username='root').first()
        if not root_user:
            # 创建root超级管理员
            salt = secrets.token_hex(16)
            pwd_hash = hashlib.pbkdf2_hmac(
                'sha256',
                'root123'.encode(),
                salt.encode(),
                100000
            ).hex()
            root_user = AdminUser(username='root', password_hash=pwd_hash, salt=salt, role='super')
            session_db.add(root_user)
            session_db.commit()
            print("✅ 默认超级管理员创建成功：root / root123")
        else:
            # 确保root用户是super角色
            if root_user.role != 'super':
                root_user.role = 'super'
                session_db.commit()
                print("✅ root用户已升级为超级管理员")
    except Exception as e:
        print(f"❌ 创建root超级管理员失败: {e}")
    finally:
        session_db.close()
    
    # 不再检查是否已初始化，持续运行配置服务
    print("配置服务启动中...")
    print("请在浏览器中访问 http://localhost:9999 进行配置")
    print("超级管理员账号：root / root123")
    app.run(host='0.0.0.0', port=9999, debug=False)
