# app.py - 已验证拨号功能，补全日志字段
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import subprocess
import os
import random
import string
import time
import json
import re
import fcntl
import logging
from config import BASE_DIR, PPP_LOG_DIR, APP_PORT
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import ActivationLog, Base

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = 'pppoe-activation-secret-key-change-in-production'

# 配置日志
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 数据库配置
DATABASE_PATH = '/opt/pppoe-activation/instance/database.db'
engine = create_engine(f'sqlite:///{DATABASE_PATH}', echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

LOG_FILE = os.path.join(BASE_DIR, 'activation_log.jsonl')
LOCK_FILE = os.path.join(BASE_DIR, 'activation.lock')  # 全局锁文件
CONFIG_FILE = '/opt/pppoe-activation/config.py'
ENV_FILE = '/opt/pppoe-activation/.env'
INIT_FLAG_FILE = '/opt/pppoe-activation/.initialized'

# 从数据库读取网络接口配置
def get_network_interfaces_from_db():
    """从数据库读取网络接口配置"""
    try:
        from flask_sqlalchemy import SQLAlchemy
        db_app = Flask(__name__)
        db_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////opt/pppoe-activation/instance/database.db'
        db_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        db = SQLAlchemy(db_app)
        
        class Config(db.Model):
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50), unique=True)
            value = db.Column(db.String(500))
        
        with db_app.app_context():
            config = Config.query.filter_by(name='NETWORK_INTERFACES').first()
            if config and config.value:
                interfaces = config.value.split()
                logger.info(f"从数据库读取网络接口配置: {interfaces}")
                return interfaces
    except Exception as e:
        logger.error(f"从数据库读取网络接口配置失败: {e}")
    
    # 如果数据库读取失败，使用config.py中的配置
    from config import NETWORK_INTERFACES as CONFIG_INTERFACES
    logger.info(f"使用config.py中的网络接口配置: {CONFIG_INTERFACES}")
    return CONFIG_INTERFACES

# 获取网络接口配置
NETWORK_INTERFACES = get_network_interfaces_from_db()


def log_activation(data):
    """记录激活日志到数据库"""
    try:
        session = SessionLocal()
        log_entry = ActivationLog(
            name=data.get('name'),
            role=data.get('role'),
            isp=data.get('isp'),
            username=data.get('username'),
            success=data.get('success', False),
            ip=data.get('ip'),
            mac=data.get('mac'),
            error_code=data.get('error_code'),
            error_message=data.get('error_message'),
            timestamp=data.get('timestamp', time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()))
        )
        session.add(log_entry)
        session.commit()
        logger.info(f"日志已写入数据库: {data.get('username')} - {data.get('success', False)}")
    except Exception as e:
        logger.error(f"写入数据库失败: {e}")
        # 如果数据库写入失败，回滚事务
        session.rollback()
    finally:
        session.close()


def random_mac():
    """生成随机私有MAC地址 (以 02 开头)"""
    return "02:%02x:%02x:%02x:%02x:%02x" % (
        random.randint(0x00, 0x7f),
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff)
    )


def set_interface_mac(iface, mac):
    """设置网卡 MAC 地址"""
    try:
        subprocess.run(['sudo', '/opt/pppoe-activation/mac_set.sh', iface, mac], check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"设置 MAC 失败: {e}")
        return False


def clear_ppp_interface(iface):
    """清理已存在的 pppd 进程"""
    subprocess.run(f"sudo pkill -f 'pppd.*{iface}'", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)


def get_ip_from_interface(iface):
    """获取接口分配的IP地址"""
    try:
        res = subprocess.run(f"ip addr show {iface}", shell=True, capture_output=True, text=True)
        ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', res.stdout)
        return ip_match.group(1) if ip_match else None
    except Exception as e:
        logger.error(f"获取IP失败: {e}")
        return None


def check_interface_carrier(iface):
    """检查网卡是否有物理连接（carrier状态）"""
    try:
        # 检查/sys/class/net/<iface>/carrier文件
        carrier_path = f"/sys/class/net/{iface}/carrier"
        if os.path.exists(carrier_path):
            with open(carrier_path, 'r') as f:
                carrier = f.read().strip()
                result = carrier == '1'
                logger.info(f"网卡 {iface} carrier状态: {carrier} ({'有连接' if result else '无连接'})")
                return result
        else:
            logger.warning(f"无法检查网卡 {iface} 的carrier状态")
            return True  # 如果无法检查，假设有连接
    except Exception as e:
        logger.error(f"检查网卡 {iface} carrier状态失败: {e}")
        return True  # 如果检查失败，假设有连接


def detect_pppoe_error(log_file):
    """检测PPPOE拨号错误，返回错误码和错误消息"""
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查PAP认证失败，提取详细错误信息
        if 'PAP authentication failed' in content or 'PAP AuthNak' in content:
            # 尝试提取详细错误信息
            auth_nak_match = re.search(r'AuthNak.*?"([^"]+)"', content)
            if auth_nak_match:
                error_detail = auth_nak_match.group(1)
                # 解析常见的错误信息
                if 'concurrency' in error_detail.lower():
                    return "691", f"账号已在其他地方登录，请等待几分钟后重试（错误详情：{error_detail}）"
                elif 'password' in error_detail.lower() or 'incorrect' in error_detail.lower():
                    return "691", f"账号或密码错误，请核对后重试（错误详情：{error_detail}）"
                elif 'disabled' in error_detail.lower() or 'deregistered' in error_detail.lower():
                    return "691", f"账号已被停用或注销，请联系运营商（错误详情：{error_detail}）"
                elif 'expired' in error_detail.lower():
                    return "691", f"账号已过期，请联系运营商（错误详情：{error_detail}）"
                elif 'locked' in error_detail.lower():
                    return "691", f"账号已被锁定，请联系运营商（错误详情：{error_detail}）"
                else:
                    return "691", f"账号或密码错误，请核对后重试（错误详情：{error_detail}）"
            return "691", "账号或密码错误，请核对后重试"
        
        # 检查PPPOE Discovery失败（无法找到BRAS）
        if 'Timeout waiting for PADO packets' in content or 'Unable to complete PPPoE Discovery' in content:
            return "678", "远程计算机无响应，可能是网络不可达或线路未接通"
        
        # 检查LCP协商失败
        if 'LCP terminated by peer' in content:
            return "734", "PPP链路控制协议终止，网络异常请稍后再试"
        
        # 检查PPP协议超时
        if 'LCP timeout' in content or ('LCP EchoReq' in content and 'LCP EchoRep' not in content):
            return "718", "PPP协议超时，可能网络拥塞或服务器无响应"
        
        # 检查连接被远程计算机强制关闭
        if 'Modem hangup' in content or 'Connection terminated' in content:
            return "629", "远程计算机强制关闭连接，请稍后再试"
        
        # 检查没有收到PADO响应（网卡没有物理连接）
        if 'Send PPPoE Discovery' in content and 'Recv PPPoE Discovery' not in content:
            return "630", "连接失败，设备不可用，请检查本地网卡或线路"
        
        # 检查CHAP认证失败
        if 'CHAP authentication failed' in content or 'CHAP AuthNak' in content:
            # 尝试提取详细错误信息
            auth_nak_match = re.search(r'AuthNak.*?"([^"]+)"', content)
            if auth_nak_match:
                error_detail = auth_nak_match.group(1)
                # 解析常见的错误信息
                if 'concurrency' in error_detail.lower():
                    return "691", f"账号已在其他地方登录，请等待几分钟后重试（错误详情：{error_detail}）"
                elif 'password' in error_detail.lower() or 'incorrect' in error_detail.lower():
                    return "691", f"账号或密码错误，请核对后重试（错误详情：{error_detail}）"
                elif 'disabled' in error_detail.lower() or 'deregistered' in error_detail.lower():
                    return "691", f"账号已被停用或注销，请联系运营商（错误详情：{error_detail}）"
                elif 'expired' in error_detail.lower():
                    return "691", f"账号已过期，请联系运营商（错误详情：{error_detail}）"
                elif 'locked' in error_detail.lower():
                    return "691", f"账号已被锁定，请联系运营商（错误详情：{error_detail}）"
                else:
                    return "691", f"账号或密码错误，请核对后重试（错误详情：{error_detail}）"
            return "691", "账号或密码错误，请核对后重试"
        
        # 默认返回未获取到IP地址
        return "815", "连接失败，未获取到IP地址"
    except Exception as e:
        logger.error(f"检测PPPOE错误失败: {e}")
        return "815", "连接失败，未获取到IP地址"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/activate', methods=['POST'])
def activate():
    data = request.get_json()
    name = data.get('name')
    role = data.get('role')
    isp = data.get('isp')
    username = data.get('username')
    password = data.get('password')

    # === 统一日志结构 ===
    log_data = {
        "name": name,
        "role": role,
        "isp": isp,
        "username": username,
        "success": False,
        "ip": None,
        "mac": None,
        "error_code": "999",
        "error_message": "参数缺失",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
        "iface": None
    }

    if not all([name, role, isp, username, password]):
        log_activation(log_data)
        return jsonify({
            "success": False,
            "error_code": "999",
            "error_message": "参数缺失",
            "username": username
        })

    # 更新日志（参数完整）
    log_data["error_code"] = None
    log_data["error_message"] = None

    # 打开锁文件，用于进程间同步
    with open(LOCK_FILE, 'w') as lock_fd:
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)  # 排他锁

            # 检查当前正在使用的网卡
            used_interfaces = set()
            for line in os.popen("ps aux | grep pppd").readlines():
                for iface in NETWORK_INTERFACES:
                    if f"pppd" in line and iface in line:
                        used_interfaces.add(iface)
            
            logger.info(f"正在使用的网卡: {list(used_interfaces)}")
            logger.info(f"配置的网卡: {NETWORK_INTERFACES}")
            
            # 查找空闲且有物理连接的网卡
            available_iface = None
            for iface in NETWORK_INTERFACES:
                if iface not in used_interfaces:
                    # 检查网卡是否有物理连接
                    carrier = check_interface_carrier(iface)
                    logger.info(f"网卡 {iface} carrier状态: {carrier}")
                    if carrier:
                        available_iface = iface
                        break
                    else:
                        logger.warning(f"网卡 {iface} 没有物理连接，跳过")
            
            logger.info(f"找到的空闲网卡: {available_iface}")

            if not available_iface:
                log_data["success"] = False
                log_data["error_code"] = "998"
                log_data["error_message"] = "系统忙，请稍后再试！"
                log_activation(log_data)
                logger.error(f"没有可用的网卡")
                return jsonify({
                    "success": False,
                    "error_code": "998",
                    "error_message": "系统忙，请稍后再试！",
                    "username": username,
                    "iface": "none"
                })

            iface = available_iface
            timestamp = int(time.time())
            log_file = os.path.join(PPP_LOG_DIR, f"pppoe_{timestamp}_{iface}.log")
            open(log_file, 'w').close()

            # 清理旧连接（在锁内执行，防止并发冲突）
            clear_ppp_interface(iface)

            # 更改 MAC
            new_mac = random_mac()
            if not set_interface_mac(iface, new_mac):
                log_data["success"] = False
                log_data["mac"] = new_mac
                log_data["error_code"] = "MAC_FAIL"
                log_data["error_message"] = "MAC地址设置失败"
                log_activation(log_data)
                return jsonify({
                    "success": False,
                    "error_code": "MAC_FAIL",
                    "error_message": "MAC地址设置失败",
                    "username": username,
                    "iface": iface
                })

            # 保存 MAC 到日志
            log_data["mac"] = new_mac

        finally:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)  # 释放锁

    # === 锁外执行拨号（避免长时间持有锁）===

    # 根据ISP类型添加后缀（系统只负责添加尾缀，密码由用户手动输入）
    # 校园网：输入学号 → 系统添加 @cdu 后缀
    # 移动：输入纯数字手机号 → 系统添加 @cmccgx 后缀；修改过密码输入 scxy + 手机号 → 系统添加 @cmccgx 后缀
    # 电信：输入纯数字手机号 → 系统添加 @96301 后缀
    # 联通：输入纯数字手机号 → 系统添加 @10010 后缀
    if '@' not in username:
        # 检查是否为纯数字
        if username.isdigit():
            # 根据ISP类型添加后缀
            if isp == 'cmccgx':
                # 移动用户
                username = f"{username}@cmccgx"
                logger.info(f"移动用户，添加@cmccgx后缀: {username}")
            elif isp == '96301':
                # 电信用户
                username = f"{username}@96301"
                logger.info(f"电信用户，添加@96301后缀: {username}")
            elif isp == '10010':
                # 联通用户
                username = f"{username}@10010"
                logger.info(f"联通用户，添加@10010后缀: {username}")
            else:
                # 校园网用户（默认）
                username = f"{username}@cdu"
                logger.info(f"校园网用户，添加@cdu后缀: {username}")
        elif username.startswith('scxy'):
            # 修改过密码的移动用户，添加@cmccgx后缀
            username = f"{username}@cmccgx"
            logger.info(f"修改过密码的移动用户，添加@cmccgx后缀: {username}")
        
        # 更新日志记录为完整账号（在调用log_activation之前）
        log_data["username"] = username

    ppp_cmd = [
        'sudo', 'pppd',
        'plugin', 'rp-pppoe.so', iface,
        'user', username,
        'password', password,
        'mtu', '1492', 'mru', '1492',
        'noauth',
        'usepeerdns',
        'nodetach',
        'logfile', log_file,
        'debug'
    ]

    try:
        proc = subprocess.Popen(ppp_cmd)
    except Exception as e:
        log_data["success"] = False
        log_data["error_code"] = "START_FAIL"
        log_data["error_message"] = f"启动失败: {str(e)}"
        log_activation(log_data)
        return jsonify({
            "success": False,
            "error_code": "START_FAIL",
            "error_message": f"启动失败: {str(e)}",
            "username": username,
            "iface": iface,
            "mac": new_mac
        })

    # 等待获取IP
    ip = None
    ppp_interface = None  # 记录实际使用的 ppp 接口名
    for _ in range(20):
        time.sleep(1)
        # 读取日志，找 "Using interface pppX" 和各种错误
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # 检查是否获取到IP
                match = re.search(r'Using interface (ppp\d+)', content)
                if match:
                    ppp_interface = match.group(1)
                    ip = get_ip_from_interface(ppp_interface)
                    if ip:
                        break
        except:
            continue

    if not ip:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except:
            pass
        # 检测错误类型
        error_code, error_message = detect_pppoe_error(log_file)
        logger.info(f"检测到错误: {error_code} - {error_message}")
        log_data["success"] = False
        log_data["error_code"] = error_code
        log_data["error_message"] = error_message
        log_activation(log_data)
        return jsonify({
            "success": False,
            "error_code": error_code,
            "error_message": error_message,
            "username": username,
            "iface": iface,
            "mac": new_mac
        })

    # ✅ 成功获取IP，现在准备挂断
    # 先尝试优雅终止 pppd 进程（通过网卡名）
    subprocess.run(['sudo', 'pkill', '-f', f'pppd.*{iface}'], check=False)
    time.sleep(1)
    # 强制杀死残留
    subprocess.run(['sudo', 'pkill', '-9', '-f', f'pppd.*{iface}'], check=False)
    time.sleep(1)

    # 额外保险：如果知道 ppp 接口名，也可以尝试关闭它（非必须）
    if ppp_interface:
        # 确保内核释放虚拟接口（有时需要）
        subprocess.run(['sudo', 'ip', 'link', 'delete', ppp_interface], check=False)

    # ✅ 成功：补全所有字段
    log_data["success"] = True
    log_data["ip"] = ip
    log_data["error_code"] = None
    log_data["error_message"] = None

    # 写入日志
    log_activation(log_data)

    # 返回响应（可精简）
    return jsonify({
        "success": True,
        "username": username,
        "iface": iface,
        "mac": new_mac,
        "ip": ip,
        "log": "拨号成功，已自动挂断"
    })


# =============================
# 配置服务端点
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
        logger.error(f"获取网卡列表失败: {e}")
        return []


def get_current_config():
    """获取当前配置"""
    config = {
        'interfaces': [],
        'data_path': './data',
        'logs_path': './logs',
        'db_path': './instance/database.db',
        'instance_path': './instance',
        'app_port': APP_PORT,
        'admin_port': 8081,
        'tz': 'Asia/Shanghai'
    }
    
    # 从数据库读取配置
    try:
        from flask_sqlalchemy import SQLAlchemy
        db_app = Flask(__name__)
        db_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////opt/pppoe-activation/instance/database.db'
        db_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        db = SQLAlchemy(db_app)
        
        class Config(db.Model):
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50), unique=True)
            value = db.Column(db.String(500))
        
        with db_app.app_context():
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
                    config['app_port'] = int(c.value) if c.value else APP_PORT
                elif c.name == 'ADMIN_PORT':
                    config['admin_port'] = int(c.value) if c.value else 8081
    except Exception as e:
        logger.error(f"从数据库读取配置失败: {e}")
    
    return config


def save_config(data):
    """保存配置"""
    # 保存网络接口配置到数据库
    interfaces = data.get('interfaces', [])
    from flask_sqlalchemy import SQLAlchemy
    db_app = Flask(__name__)
    db_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////opt/pppoe-activation/instance/database.db'
    db_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db = SQLAlchemy(db_app)
    
    class Config(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(50), unique=True)
        value = db.Column(db.String(500))
    
    with db_app.app_context():
        # 保存网络接口配置
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
        
        # 保存路径配置
        path_configs = [
            ('DATA_PATH', data.get('data_path', './data')),
            ('LOGS_PATH', data.get('logs_path', './logs')),
            ('DB_PATH', data.get('db_path', './instance/database.db')),
            ('INSTANCE_PATH', data.get('instance_path', './instance'))
        ]
        
        for key, value in path_configs:
            config = Config.query.filter_by(name=key).first()
            if config:
                config.value = value
            else:
                config = Config(name=key, value=value)
                db.session.add(config)
        
        db.session.commit()
        logger.info(f"配置已保存到数据库")
    
    # 保存 config.py
    config_content = f"""# PPPOE 激活系统配置文件
# 自动生成于 {subprocess.run(['date'], capture_output=True, text=True).stdout.strip()}

BASE_DIR = '/opt/pppoe-activation'

# SQLite 数据库绝对路径（固定）
DATABASE_PATH = '/opt/pppoe-activation/instance/database.db'

# 网卡配置（用户配置）
NETWORK_INTERFACES = {json.dumps(data.get('interfaces', ['eth0']))}

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
NETWORK_INTERFACES={' '.join(data.get('interfaces', ['eth0']))}

# 时区配置
TZ={data.get('tz', 'Asia/Shanghai')}

# 数据持久化路径配置
DATA_PATH={data.get('data_path', './data')}
LOGS_PATH={data.get('logs_path', './logs')}
DB_PATH={data.get('db_path', './instance/database.db')}
INSTANCE_PATH={data.get('instance_path', './instance')}
"""

    with open(ENV_FILE, 'w') as f:
        f.write(env_content)
    
    # 创建初始化标记
    with open(INIT_FLAG_FILE, 'w') as f:
        f.write('initialized')
    
    # 立即重启主应用容器
    try:
        result = subprocess.run(['docker', 'restart', 'pppoe-activation'], 
                              capture_output=True, text=True, timeout=10)
        logger.info(f"主应用容器重启命令已执行: {result.stdout}")
    except Exception as e:
        logger.error(f"重启主应用容器失败: {e}")

    return True


@app.route('/config')
def config_page():
    """配置页面"""
    available_interfaces = get_available_interfaces()
    current_config = get_current_config()
    return render_template('init_config.html',
                       available_interfaces=available_interfaces,
                       current_config=current_config)


@app.route('/api/interfaces')
def api_interfaces():
    """获取可用网卡列表"""
    interfaces = get_available_interfaces()
    return jsonify({'interfaces': interfaces})


@app.route('/api/config', methods=['GET', 'POST'])
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
def restart_status():
    """获取重启状态"""
    try:
        result = subprocess.run(['docker', 'ps', '-a', '--format', '{{.Status}}', 'pppoe-activation'],
                              capture_output=True, text=True)
        status = result.stdout.strip()
        return jsonify({'status': status})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/dial-logs')
def api_dial_logs():
    """获取最新的详细拨号日志（无需登录）"""
    try:
        # 查找最新的pppoe日志文件
        log_dir = PPP_LOG_DIR
        if not os.path.exists(log_dir):
            return jsonify({"error": "日志目录不存在"}), 404
        
        # 获取所有pppoe日志文件，按修改时间排序
        log_files = []
        for filename in os.listdir(log_dir):
            if filename.startswith('pppoe_') and filename.endswith('.log'):
                filepath = os.path.join(log_dir, filename)
                mtime = os.path.getmtime(filepath)
                log_files.append((mtime, filepath))
        
        if not log_files:
            return jsonify({"error": "暂无拨号日志"}), 404
        
        # 按修改时间倒序排序，取最新的
        log_files.sort(reverse=True, key=lambda x: x[0])
        latest_log_file = log_files[0][1]
        
        # 读取日志文件内容
        with open(latest_log_file, 'r', encoding='utf-8') as f:
            log_content = f.read()
        
        # 返回日志内容
        return jsonify({
            "success": True,
            "log_file": os.path.basename(latest_log_file),
            "log_content": log_content
        })
    except Exception as e:
        logger.error(f"获取拨号日志失败: {e}")
        return jsonify({"error": f'获取拨号日志失败: {str(e)}'}), 500


@app.route('/save', methods=['POST'])
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
            'tz': request.form.get('tz', 'Asia/Shanghai')
        }
        
        save_config(data)
        
        return render_template('init_success.html', config=data)
    except Exception as e:
        return render_template('init_config.html',
                           available_interfaces=get_available_interfaces(),
                           current_config=get_current_config(),
                           error=str(e))


if __name__ == '__main__':
    # 确保锁文件存在
    open(LOCK_FILE, 'a').close()
    app.run(host='0.0.0.0', port=APP_PORT, threaded=True, debug=False)
