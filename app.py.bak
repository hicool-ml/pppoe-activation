# app.py - 已验证拨号功能，补全日志字段
from flask import Flask, request, jsonify, render_template, redirect, url_for
import subprocess
import os
import random
import string
import time
import json
import re
import fcntl
from config import BASE_DIR, NETWORK_INTERFACES, PPP_LOG_DIR, APP_PORT

app = Flask(__name__, static_folder='static', template_folder='templates')

LOG_FILE = os.path.join(BASE_DIR, 'activation_log.jsonl')
LOCK_FILE = os.path.join(BASE_DIR, 'activation.lock')  # 全局锁文件
CONFIG_FILE = '/opt/pppoe-activation/config.py'
ENV_FILE = '/opt/pppoe-activation/.env'
INIT_FLAG_FILE = '/opt/pppoe-activation/.initialized'


def log_activation(data):
    """记录激活日志"""
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


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
        print(f"[ERROR] 设置 MAC 失败: {e}")
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
        print(f"[ERROR] 获取IP失败: {e}")
        return None


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

            # 查找空闲网卡
            available_iface = None
            for iface in NETWORK_INTERFACES:
                if iface not in used_interfaces:
                    available_iface = iface
                    break

            if not available_iface:
                log_data["success"] = False
                log_data["error_code"] = "998"
                log_data["error_message"] = "系统忙，请稍后再试！"
                log_activation(log_data)
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
        # 读取日志，找 "Using interface pppX"
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
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
        log_data["success"] = False
        log_data["error_code"] = "815"
        log_data["error_message"] = "连接失败，未获取到IP地址"
        log_activation(log_data)
        return jsonify({
            "success": False,
            "error_code": "815",
            "error_message": "连接失败，未获取到IP地址",
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
        'app_port': APP_PORT,
        'admin_port': 8081,
        'tz': 'Asia/Shanghai'
    }
    
    # 读取 config.py
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
    
    # 读取 .env
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
    
    return config


def save_config(data):
    """保存配置"""
    # 保存 config.py
    config_content = f"""# PPPOE 激活系统配置文件
# 自动生成于 {subprocess.run(['date'], capture_output=True, text=True).stdout.strip()}

BASE_DIR = '/opt/pppoe-activation'

# SQLite 数据库绝对路径（固定）
# 使用 /app/instance 目录，该目录已挂载到宿主机
DATABASE_PATH = '/app/instance/database.db'

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
DB_PATH={data.get('db_path', './database.db')}
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
        print(f"主应用容器重启命令已执行: {result.stdout}")
    except Exception as e:
        print(f"重启主应用容器失败: {e}")

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


@app.route('/save', methods=['POST'])
def save():
    """保存配置并重启"""
    try:
        data = {
            'interfaces': request.form.getlist('interfaces'),
            'data_path': request.form.get('data_path', './data'),
            'logs_path': request.form.get('logs_path', './logs'),
            'db_path': request.form.get('db_path', './database.db'),
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
