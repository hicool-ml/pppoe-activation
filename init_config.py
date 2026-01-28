#!/usr/bin/env python3
"""
初始化配置脚本
在首次启动时，通过 Web 界面配置网卡和持久化存储路径
"""

import os
import sys
import json
import subprocess
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)

# 配置文件路径
CONFIG_FILE = '/opt/pppoe-activation/config.py'
ENV_FILE = '/opt/pppoe-activation/.env'
INIT_FLAG_FILE = '/opt/pppoe-activation/.initialized'


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
        'app_port': 80,
        'admin_port': 80,
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
        print(f"主应用容器重启命令已执行: {result.stdout}")
    except Exception as e:
        print(f"重启主应用容器失败: {e}")

    return True


@app.route('/')
def index():
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
    # 检查是否已初始化
    if os.path.exists(INIT_FLAG_FILE):
        print("系统已初始化，请使用 docker-compose restart 重启服务")
        sys.exit(0)
    
    print("初始化配置服务启动中...")
    print("请在浏览器中访问 http://localhost:9999 进行配置")
    app.run(host='0.0.0.0', port=9999, debug=False)
