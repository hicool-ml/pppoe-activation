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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import ActivationLog, Base, NetworkConfig

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(32))

# 配置日志
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 数据库配置
DATABASE_PATH = '/opt/pppoe-activation/instance/database.db'
engine = create_engine(f'sqlite:///{DATABASE_PATH}', echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

# 从环境变量读取配置（不再从config.py导入）
BASE_DIR = os.environ.get("BASE_DIR", "/opt/pppoe-activation")
PPP_LOG_DIR = os.environ.get("LOGS_PATH", f"{BASE_DIR}/logs")
APP_PORT = int(os.environ.get("APP_PORT", 8080))

LOG_FILE = os.path.join(BASE_DIR, 'activation_log.jsonl')
# 锁目录，用于存储每个网卡的锁文件
LOCK_DIR = os.path.join(BASE_DIR, 'locks')
os.makedirs(LOCK_DIR, exist_ok=True)

# 接口轮询计数器（线程安全）
# 已废弃：使用"锁即资源"模型替代轮询机制
# import threading
# interface_counter = 0
# interface_counter_lock = threading.Lock()

# 获取运行期网络接口（只读数据库，不做任何写入操作）
def get_runtime_interfaces(session):
    """
    获取 PPPoE 使用的最终接口列表（只读数据库）
    
    根据数据库中的网络配置，返回物理接口或 VLAN 子接口列表
    如果数据库中没有配置或配置不完整，抛出异常
    
    Args:
        session: SQLAlchemy 会话
    
    Returns:
        list: 接口列表（如 ['enp3s0'] 或 ['enp3s0.100', 'enp3s0.101']）
    
    Raises:
        RuntimeError: 如果系统尚未初始化或配置不完整
    """
    net_config = session.query(NetworkConfig).first()
    
    # 如果数据库中没有配置，抛出异常（不再自动检测）
    if not net_config:
        raise RuntimeError(
            "系统尚未初始化，请先访问初始化配置页面完成网络配置（http://192.168.0.112:9999）"
        )
    
    # 根据网络模式返回接口列表
    if net_config.net_mode == 'vlan':
        # VLAN 模式：返回所有 VLAN 子接口列表
        if not net_config.vlan_id or not net_config.base_interface:
            raise RuntimeError(f"VLAN 配置不完整：base_interface={net_config.base_interface}, vlan_id={net_config.vlan_id}")
        
        vlan_ids = net_config.vlan_id.split(',')
        vlan_interfaces = []
        for vlan_id in vlan_ids:
            vlan_id = vlan_id.strip()
            if vlan_id:
                vlan_interfaces.append(f"{net_config.base_interface}.{vlan_id}")
        
        if not vlan_interfaces:
            raise RuntimeError(f"VLAN 配置无效：vlan_id={net_config.vlan_id}")
        
        logger.info(f"VLAN 模式：使用 VLAN 子接口列表: {vlan_interfaces}")
        return vlan_interfaces
    
    else:
        # 物理模式：返回物理网卡
        if not net_config.base_interface:
            raise RuntimeError("物理模式配置不完整：未配置物理网卡")
        
        logger.info(f"物理模式：使用物理网卡: {net_config.base_interface}")
        return [net_config.base_interface]


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
    """清理已存在的 pppd 进程（只清理与指定网卡关联的 pppd，避免误杀他人会话）"""
    # 先尝试优雅终止（只清理与指定网卡关联的 pppd）
    subprocess.run(['sudo', 'pkill', '-f', f'pppd.*rp-pppoe.so {iface}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    time.sleep(0.5)
    # 强制杀死残留
    subprocess.run(['sudo', 'pkill', '-9', '-f', f'pppd.*rp-pppoe.so {iface}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    time.sleep(0.5)


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


def ensure_interfaces_exist(interfaces):
    """
    校验网络接口是否存在（只校验，不创建）
    
    Args:
        interfaces: 接口列表（如 ['enp3s0'] 或 ['enp3s0.100', 'enp3s0.101']）
    
    Raises:
        RuntimeError: 如果网络接口不存在
    """
    for iface in interfaces:
        result = subprocess.run(
            ['ip', 'link', 'show', iface],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"网络接口不存在: {iface}，请重新初始化配置（http://192.168.0.112:9999）"
            )
        logger.info(f"网络接口存在性校验通过: {iface}")


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
        
        # 检查CHAP认证失败（使用错误码646）
        if 'CHAP authentication failed' in content or 'CHAP AuthNak' in content:
            # 尝试提取详细错误信息
            auth_nak_match = re.search(r'AuthNak.*?"([^"]+)"', content)
            if auth_nak_match:
                error_detail = auth_nak_match.group(1)
                # 解析常见的错误信息
                if 'concurrency' in error_detail.lower():
                    return "646", f"账号已在其他地方登录，请等待几分钟后重试（错误详情：{error_detail}）"
                elif 'password' in error_detail.lower() or 'incorrect' in error_detail.lower():
                    return "646", f"账号或密码错误，请核对后重试（错误详情：{error_detail}）"
                elif 'disabled' in error_detail.lower() or 'deregistered' in error_detail.lower():
                    return "646", f"账号已被停用或注销，请联系运营商（错误详情：{error_detail}）"
                elif 'expired' in error_detail.lower():
                    return "646", f"账号已过期，请联系运营商（错误详情：{error_detail}）"
                elif 'locked' in error_detail.lower():
                    return "646", f"账号已被锁定，请联系运营商（错误详情：{error_detail}）"
                else:
                    return "646", f"账号或密码错误，请核对后重试（错误详情：{error_detail}）"
            return "646", "账号或密码错误，请核对后重试"
        
        # 检查PPPOE Discovery失败（无法找到BRAS）
        if 'Timeout waiting for PADO packets' in content or 'Unable to complete PPPoE Discovery' in content:
            return "678", "远程计算机无响应，可能是网络不可达或线路未接通"
        
        # 检查LCP协商失败（MTU/MRU不匹配）
        if 'LCP terminated by peer' in content:
            return "734", "PPP链路控制协议终止，可能是MTU/MRU不匹配，网络异常请稍后再试"
        
        # 检查PPP协议超时
        if 'LCP timeout' in content or ('LCP EchoReq' in content and 'LCP EchoRep' not in content):
            return "718", "PPP协议超时，可能网络拥塞或服务器无响应"
        
        # 检查连接被远程计算机强制关闭
        if 'Modem hangup' in content or 'Connection terminated' in content:
            return "629", "远程计算机强制关闭连接，请稍后再试"
        
        # 检查没有收到PADO响应（网卡没有物理连接）
        if 'Send PPPoE Discovery' in content and 'Recv PPPoE Discovery' not in content:
            return "630", "连接失败，设备不可用，请检查本地网卡或线路"
        
        # 检查认证协议协商失败
        if 'Authentication failed' in content and 'CHAP' not in content and 'PAP' not in content:
            return "691", "认证失败，请检查账号和密码"
        
        # 检查IPCP协商失败
        if 'IPCP' in content and ('failed' in content or 'terminated' in content):
            return "734", "IPCP协商失败，可能是IP地址分配问题"
        
        # 检查物理连接问题
        if 'No carrier' in content or 'Link down' in content:
            return "630", "物理连接断开，请检查网线或网络设备"
        
        # 检查MAC地址冲突
        if 'MAC address' in content and ('conflict' in content.lower() or 'duplicate' in content.lower()):
            return "630", "MAC地址冲突，请稍后重试"
        
        # 检查服务器拒绝连接
        if 'Server refused' in content or 'Access denied' in content:
            return "691", "服务器拒绝连接，请检查账号状态"
        
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

    # 为每个网卡创建单独的锁文件（实现网卡级别的并发）
    def release_iface_lock(lock_fd):
        """释放网卡的锁"""
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()
    
    def try_acquire_iface(iface_list):
        """
        从 iface_list 中尝试获取一个可用接口（"锁即资源"模型）
        
        使用非阻塞锁遍历接口列表，成功获取锁的接口即为可用接口
        这样"选接口 + 加锁"一步完成，没有竞态窗口
        
        Args:
            iface_list: 接口列表（如 ['enp3s0.100', 'enp3s0.101']）
        
        Returns:
            (iface, lock_fd): 成功返回 (接口名, 锁文件描述符)
            (None, None): 失败返回 (None, None)
        """
        for iface in iface_list:
            lock_path = os.path.join(LOCK_DIR, f'{iface}.lock')
            try:
                fd = open(lock_path, 'w')
                # 使用非阻塞锁尝试获取接口
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                logger.info(f"成功抢占接口 {iface}")
                return iface, fd
            except BlockingIOError:
                # 该接口已被占用，关闭文件描述符，尝试下一个
                fd.close()
                continue
            except Exception as e:
                # 其他异常，关闭文件描述符，尝试下一个
                logger.warning(f"获取接口 {iface} 锁失败: {e}")
                try:
                    fd.close()
                except:
                    pass
                continue
        
        # 所有接口都不可用
        logger.warning(f"所有接口均不可用: {iface_list}")
        return None, None
    
    # 兼容性：如果 LOCK_DIR 不存在，创建锁目录
    try:
        os.makedirs(LOCK_DIR, exist_ok=True)
    except:
        pass
    
    # 使用"锁即资源"的方式查找可用网卡（避免竞态窗口）
    # 从数据库读取网络配置（只读，不做任何写入操作）
    iface = None
    lock_fd = None
    
    try:
        # 获取 PPPoE 使用的接口列表（仅从数据库读取）
        session = SessionLocal()
        iface_list = get_runtime_interfaces(session)
        session.close()
        
        logger.info(f"从数据库读取接口列表: {iface_list}")
        
        # 使用"锁即资源"模型选择接口（一步完成选接口 + 加锁）
        iface, lock_fd = try_acquire_iface(iface_list)
        
        if not iface:
            log_data["success"] = False
            log_data["error_code"] = "998"
            log_data["error_message"] = "系统忙，暂无可用拨号通道"
            log_activation(log_data)
            logger.error(f"所有接口均不可用")
            return jsonify({
                "success": False,
                "error_code": "998",
                "error_message": "系统忙，暂无可用拨号通道",
                "username": username,
                "iface": "none"
            })
        
        # 校验接口是否存在（只校验，不创建）
        ensure_interfaces_exist([iface])
        
    except RuntimeError as e:
        log_data["success"] = False
        log_data["error_code"] = "997"
        log_data["error_message"] = f"网络配置错误: {str(e)}"
        log_activation(log_data)
        logger.error(f"网络配置错误: {e}")
        return jsonify({
            "success": False,
            "error_code": "997",
            "error_message": f"网络配置错误: {str(e)}",
            "username": username,
            "iface": "none"
        })
    
    try:
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

        # 等待 MAC 生效（某些网卡需要 100-300ms）
        time.sleep(0.3)

        # 保存 MAC 到日志
        log_data["mac"] = new_mac

    finally:
        # 释放网卡锁
        if lock_fd:
            try:
                release_iface_lock(lock_fd)
                logger.info(f"成功释放网卡 {iface} 的锁")
            except Exception as e:
                logger.error(f"释放网卡锁失败: {e}")

    # === 锁外执行拨号（避免长时间持有锁）===

    # 根据ISP类型添加后缀（系统只负责添加尾缀，密码由用户手动输入）
    # 校园网：输入学号 → 系统添加 @cdu 后缀
    # 移动：输入纯数字手机号 → 系统添加 @cmccgx 后缀；修改过密码输入 scxy + 手机号 → 系统添加 @cmccgx 后缀
    # 电信：输入纯数字手机号 → 系统添加 @96301 后缀
    # 联通：输入纯数字手机号 → 系统添加 @10010 后缀
    # 直拨：不添加任何后缀，用户自由输入完整账号
    if isp != 'direct' and '@' not in username:
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
    elif isp == 'direct':
        # 直拨模式：不添加任何后缀，直接使用用户输入的账号
        logger.info(f"直拨模式，使用原始账号: {username}")
        # 更新日志记录为完整账号（在调用log_activation之前）
        log_data["username"] = username

    ppp_cmd = [
        'pppd',
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
        # 优雅终止 pppd 进程
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            # 如果优雅终止失败，强制终止
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # 如果强制终止也失败，使用 pkill -9 -P 作为后备方案
                logger.warning(f"无法正常终止 pppd 进程 (PID: {proc.pid})，使用 pkill -9 -P 强制终止")
                subprocess.run(['sudo', 'pkill', '-9', '-P', str(proc.pid)], check=False)
                time.sleep(1)
        
        # 异常情况下尝试删除 ppp 接口（避免内核残留）
        if ppp_interface:
            logger.info(f"异常情况下尝试删除 ppp 接口: {ppp_interface}")
            subprocess.run(['sudo', 'ip', 'link', 'delete', ppp_interface], check=False)
            time.sleep(0.5)
        
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
    # 优雅终止 pppd 进程（使用记录的 PID）
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        # 如果优雅终止失败，强制终止
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            # 如果强制终止也失败，使用 pkill -9 -P 作为后备方案
            logger.warning(f"无法正常终止 pppd 进程 (PID: {proc.pid})，使用 pkill -9 -P 强制终止")
            subprocess.run(['sudo', 'pkill', '-9', '-P', str(proc.pid)], check=False)
            time.sleep(1)
    
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


if __name__ == '__main__':
    # 确保锁目录存在
    os.makedirs(LOCK_DIR, exist_ok=True)
    app.run(host='0.0.0.0', port=APP_PORT, threaded=True, debug=False)
