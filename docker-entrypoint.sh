#!/bin/bash

# PPPOE 激活系统 Docker 容器启动脚本
# 版本: 3.0.0
# 职责：只启动主应用服务（app.py），其他服务独立运行

set -e
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查环境变量
check_env_vars() {
    log_info "检查环境变量..."
    
    # 检查数据库文件是否存在
    if [[ ! -f /opt/pppoe-activation/instance/database.db ]]; then
        log_info "数据库文件不存在，使用环境变量或默认值"
        export APP_PORT=${APP_PORT:-80}
        export ADMIN_PORT=${ADMIN_PORT:-8081}
        log_info "使用默认应用端口: $APP_PORT"
        log_info "管理端口: $ADMIN_PORT"
        return 0
    fi
    
    # 从数据库读取应用端口配置（优先读取大写的APP_PORT）
    DB_APP_PORT=$(python3 -c '
import sys
sys.path.insert(0, "/opt/pppoe-activation")
from sqlalchemy import create_engine, text
engine = create_engine("sqlite:////opt/pppoe-activation/instance/database.db")
with engine.connect() as conn:
    # 优先读取APP_PORT（大写）
    result = conn.execute(text("SELECT value FROM config WHERE name = '\''APP_PORT'\''"))
    row = result.fetchone()
    if row:
        print(row[0])
    else:
        # 如果没有APP_PORT，尝试读取app_port（小写）
        result = conn.execute(text("SELECT value FROM config WHERE name = '\''app_port'\''"))
        row = result.fetchone()
        if row:
            print(row[0])
        else:
            print("")
' 2>/dev/null || echo "")
    
    # 如果数据库中有配置，使用数据库配置；否则使用环境变量或默认值
    if [[ -n "$DB_APP_PORT" ]]; then
        export APP_PORT=$DB_APP_PORT
        log_info "从数据库读取应用端口: $APP_PORT"
    else
        export APP_PORT=${APP_PORT:-80}
        log_info "使用默认应用端口: $APP_PORT"
    fi
    
    export ADMIN_PORT=${ADMIN_PORT:-8081}
    log_info "管理端口: $ADMIN_PORT"
}

# 初始化数据库
init_database() {
    log_info "初始化数据库..."
    
    if [[ ! -f /opt/pppoe-activation/instance/database.db ]]; then
        cd /opt/pppoe-activation
        python3 init_db.py
        log_success "数据库初始化完成"
    else
        log_info "数据库已存在"
    fi
    
    # 修改数据库文件权限，让所有用户可以访问
    if [[ -f /opt/pppoe-activation/instance/database.db ]]; then
        chmod 666 /opt/pppoe-activation/instance/database.db
        log_info "数据库文件权限已修改为666"
    fi
}

# 配置PPP设备
configure_ppp_device() {
    log_info "配置PPP设备..."
    
    # 检查/dev/ppp设备是否存在
    if [[ -c /dev/ppp ]]; then
        chmod 666 /dev/ppp
        log_success "PPP设备权限已修改为666"
    else
        log_warning "PPP设备不存在，尝试创建..."
        # 创建PPP设备（主设备号108，次设备号0）
        if mknod /dev/ppp c 108 0 2>/dev/null; then
            chmod 666 /dev/ppp
            log_success "PPP设备创建成功并设置权限为666"
        else
            log_error "PPP设备创建失败，PPPoE拨号可能无法工作"
        fi
    fi
}

# 启用所有可用的物理网卡
enable_all_network_interfaces() {
    log_info "启用所有可用的物理网卡..."
    
    # 获取所有物理网卡（排除lo、docker、veth等虚拟网卡）
    ip -j link show | python3 -c "
import sys, json

interfaces_data = json.load(sys.stdin)
enabled_count = 0
skipped_count = 0

for iface_data in interfaces_data:
    ifname = iface_data.get('ifname', '')
    operstate = iface_data.get('operstate', 'UNKNOWN')
    link_type = iface_data.get('link_type', '')
    
    # 跳过虚拟网卡和特殊接口
    if ifname in ['lo', 'docker0', 'flannel', 'cni', 'tun', 'tap', 'veth']:
        skipped_count += 1
        continue
    
    # 跳过已包含点的接口（VLAN子接口、桥接等）
    if '.' in ifname:
        skipped_count += 1
        continue
    
    # 跳过非以太网接口
    if link_type not in ['ether', 'unknown']:
        skipped_count += 1
        continue
    
    # 如果网卡处于DOWN状态，尝试启用
    if operstate == 'DOWN' or operstate == 'UNKNOWN':
        import subprocess
        try:
            result = subprocess.run(['ip', 'link', 'set', ifname, 'up'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f'[SUCCESS] 启用网卡: {ifname}')
                enabled_count += 1
            else:
                print(f'[FAILED] 启用网卡 {ifname} 失败: {result.stderr.strip()}')
        except Exception as e:
            print(f'[ERROR] 启用网卡 {ifname} 异常: {str(e)}')
    else:
        print(f'[INFO] 网卡 {ifname} 已启动 ({operstate})')

print(f'[SUMMARY] 成功启用 {enabled_count} 个网卡，跳过 {skipped_count} 个接口')
" 2>&1 | while IFS= read -r line; do
        if [[ "$line" == *"[SUCCESS]"* ]]; then
            log_success "${line#'[SUCCESS] '}"
        elif [[ "$line" == *"[FAILED]"* ]]; then
            log_error "${line#'[FAILED] '}"
        elif [[ "$line" == *"[ERROR]"* ]]; then
            log_error "${line#'[ERROR] '}"
        elif [[ "$line" == *"[INFO]"* ]]; then
            log_info "${line#'[INFO] '}"
        elif [[ "$line" == *"[SUMMARY]"* ]]; then
            log_info "${line#'[SUMMARY] '}"
        fi
    done
}

# 配置VLAN接口（从数据库读取配置）
configure_vlan_interfaces() {
    log_info "配置VLAN接口..."
    
    # 检查数据库文件是否存在
    if [[ ! -f /opt/pppoe-activation/instance/database.db ]]; then
        log_info "数据库文件不存在，跳过VLAN配置"
        return 0
    fi
    
    # 从数据库读取VLAN配置
    VLAN_CONFIG=$(python3 -c "
import sys
sys.path.insert(0, '/opt/pppoe-activation')
from sqlalchemy import create_engine, text
engine = create_engine('sqlite:////opt/pppoe-activation/instance/database.db')
with engine.connect() as conn:
    result = conn.execute(text('SELECT net_mode, base_interface, vlan_id FROM network_config'))
    row = result.fetchone()
    if row:
        net_mode, base_interface, vlan_id = row
        if net_mode == 'vlan' and vlan_id and base_interface:
            print(f'{net_mode}|{base_interface}|{vlan_id}')
        else:
            print('')
    else:
        print('')
" 2>/dev/null || echo "")
    
    if [[ -n "$VLAN_CONFIG" ]]; then
        IFS='|' read -r net_mode base_interface vlan_id <<< "$VLAN_CONFIG"
        if [[ -n "$net_mode" && "$net_mode" == "vlan" && -n "$vlan_id" && -n "$base_interface" ]]; then
            # 先删除旧的 VLAN 子接口（避免重复）
            log_info "清理旧的 VLAN 子接口..."
            ip -j link show | python3 -c "
import sys, json
interfaces_data = json.load(sys.stdin)
for iface_data in interfaces_data:
    ifname = iface_data.get('ifname', '')
    # 检查是否为 VLAN 子接口（格式：base_interface.vlan_id）
    if '.' in ifname and ifname.startswith('$base_interface'):
        print(ifname)
" 2>/dev/null | while read -r old_vlan_if; do
                if [[ -n "$old_vlan_if" ]]; then
                    ip link delete "$old_vlan_if" 2>/dev/null && log_info "删除旧的 VLAN 子接口: $old_vlan_if" || true
                fi
            done
            
            log_info "创建VLAN子接口: $base_interface.$vlan_id"
            # 按逗号分隔VLAN ID
            IFS=',' read -ra VLAN_IDS <<< "$vlan_id"
            for vlan_id_str in "${VLAN_IDS[@]}"; do
                vlan_id_str=$(echo "$vlan_id_str" | xargs)
                if [[ -n "$vlan_id_str" ]]; then
                    vlan_if="${base_interface}.${vlan_id_str}"
                    # 检查VLAN子接口是否已存在
                    if ip link show "$vlan_if" &>/dev/null; then
                        log_info "VLAN子接口 $vlan_if 已存在"
                    else
                        # 创建VLAN子接口
                        if ip link add link "$base_interface" name "$vlan_if" type vlan id "$vlan_id_str" 2>/dev/null; then
                            ip link set "$vlan_if" up
                            log_success "VLAN子接口 $vlan_if 创建成功"
                        else
                            log_error "创建VLAN子接口 $vlan_if 失败"
                        fi
                    fi
                fi
            done
        fi
    else
        log_info "未找到VLAN配置"
    fi
    
    return 0
}

# 启动主服务
start_service() {
    log_info "启动主服务..."
    
    cd /opt/pppoe-activation
    
    # 启动配置管理服务（端口9999）
    log_info "启动配置管理服务 (端口 9999)..."
    python3 init_config.py &
    
    # 启动管理后台服务（端口8081）
    log_info "启动管理后台服务 (端口 8081)..."
    python3 dashboard.py &
    
    # 启动拨号服务（端口80，前台运行）
    log_info "启动拨号服务 (端口 $APP_PORT)..."
    # 以root用户身份运行app.py（需要绑定80端口）
    exec python3 app.py
}

# 信号处理
signal_handler() {
    log_info "接收到停止信号，正在关闭服务..."
    exit 0
}

# 设置信号处理
trap signal_handler SIGTERM SIGINT

# 显示启动信息
show_startup_info() {
    echo ""
    echo "=========================================="
    echo "🚀 PPPOE 激活系统已启动"
    echo "=========================================="
    echo ""
    echo "📌 访问地址："
    echo "   用户激活页面: http://localhost:$APP_PORT"
    echo "   管理后台页面: http://localhost:$ADMIN_PORT"
    echo "   配置管理页面: http://localhost:9999"
    echo ""
    echo "📌 默认管理员账号："
    echo "   用户名: admin"
    echo "   密码: admin123"
    echo ""
    echo "📌 容器信息："
    echo "   容器ID: $(hostname)"
    echo "   启动时间: $(date)"
    echo ""
    echo "📌 日志查看："
    echo "   docker logs -f $(hostname)"
    echo ""
}

# 主函数
main() {
    echo "=========================================="
    echo "🐳 PPPOE 激活系统 Docker 容器启动"
    echo "=========================================="
    echo ""
    
    check_env_vars
    init_database
    configure_ppp_device
    enable_all_network_interfaces
    configure_vlan_interfaces
    show_startup_info
    
    # 启动主服务（阻塞）
    start_service
}

# 执行主函数
main
