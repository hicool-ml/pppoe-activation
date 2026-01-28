#!/bin/bash

# PPPOE 激活系统 Docker 容器启动脚本
# 版本: 2.0.0
# 更新日期: 2025-12-19

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
    
    # 设置默认值
    export APP_PORT=${APP_PORT:-80}
    export ADMIN_PORT=${ADMIN_PORT:-8081}
    export NETWORK_INTERFACES=${NETWORK_INTERFACES:-"eth0 eth1 eth2 eth3"}
    
    log_info "应用端口: $APP_PORT"
    log_info "管理端口: $ADMIN_PORT"
    log_info "网络接口: $NETWORK_INTERFACES"
}

# 生成配置文件
generate_config() {
    log_info "生成配置文件..."
    
    # 备份原配置文件
    if [[ -f /opt/pppoe-activation/config.py ]]; then
        cp /opt/pppoe-activation/config.py /opt/pppoe-activation/config.py.bak
    fi
    
    # 生成新的配置文件
    cat > /opt/pppoe-activation/config.py <<EOF
# PPPOE 激活系统配置文件
# Docker 容器自动生成于 $(date)

BASE_DIR = '/opt/pppoe-activation'

# SQLite 数据库绝对路径（固定）
DATABASE_PATH = '/opt/pppoe-activation/instance/database.db'

# 网络接口配置（用户配置）
NETWORK_INTERFACES = [
EOF

    # 添加网络接口到配置文件
    IFS=' ' read -ra INTERFACES <<< "$NETWORK_INTERFACES"
    FIRST=true
    for interface in "${INTERFACES[@]}"; do
        if [ "$FIRST" = true ]; then
            echo "    '$interface'" >> /opt/pppoe-activation/config.py
            FIRST=false
        else
            echo "    , '$interface'" >> /opt/pppoe-activation/config.py
        fi
    done
    echo "]" >> /opt/pppoe-activation/config.py

    # 添加其他配置
    cat >> /opt/pppoe-activation/config.py <<EOF

# 日志目录
PPP_LOG_DIR = f'{BASE_DIR}/logs'

# 服务端口配置
APP_PORT = $APP_PORT
ADMIN_PORT = $ADMIN_PORT
EOF
    
    # 保存 .env
    cat > /opt/pppoe-activation/.env <<EOF
# PPPOE 激活系统 Docker 环境变量配置
# Docker 容器自动生成于 $(date)

# 应用端口配置
APP_PORT=$APP_PORT
ADMIN_PORT=$ADMIN_PORT

# 网卡配置（使用空格分隔多个网卡）
NETWORK_INTERFACES=$NETWORK_INTERFACES

# 时区配置
TZ=${TZ:-Asia/Shanghai}

# 数据持久化路径配置
DATA_PATH=./data
LOGS_PATH=./logs
DB_PATH=./database.db
INSTANCE_PATH=./instance
EOF
    
    # 创建初始化标记
    touch /opt/pppoe-activation/.initialized
    
    log_success "配置文件生成完成"
}

# 配置网络接口
configure_network() {
    log_info "配置网络接口..."
    
    IFS=' ' read -ra INTERFACES <<< "$NETWORK_INTERFACES"
    for interface in "${INTERFACES[@]}"; do
        # 检查接口是否存在
        if ip link show "$interface" &>/dev/null; then
            # 检查接口状态
            if ip link show "$interface" | grep -q "state DOWN"; then
                log_warning "接口 $interface 状态为DOWN，跳过"
                continue
            fi
            
            # 启用接口
            if ip link set "$interface" up &>/dev/null; then
                log_info "接口 $interface 已启用"
            else
                log_error "无法启用接口 $interface"
            fi
        else
            log_warning "接口 $interface 不存在"
        fi
    done
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
    
    # 修改/dev/ppp设备权限，让所有用户可以访问
    if [[ -c /dev/ppp ]]; then
        chmod 666 /dev/ppp
        log_success "PPP设备权限已修改为666"
    else
        log_warning "PPP设备不存在"
    fi
}

# 启动服务
start_services() {
    log_info "启动服务..."
    
    # 启动用户激活服务
    log_info "启动用户激活服务 (端口 $APP_PORT)..."
    python3 app.py &
    APP_PID=$!
    
    # 启动管理后台服务（以root用户运行，确保可以访问数据库）
    log_info "启动管理后台服务 (端口 $ADMIN_PORT)..."
    python3 dashboard.py &
    ADMIN_PID=$!
    
    # 等待服务启动
    sleep 5
    
    # 检查服务状态
    if kill -0 $APP_PID 2>/dev/null; then
        log_success "用户激活服务启动成功 (PID: $APP_PID)"
    else
        log_error "用户激活服务启动失败"
        exit 1
    fi
    
    if kill -0 $ADMIN_PID 2>/dev/null; then
        log_success "管理后台服务启动成功 (PID: $ADMIN_PID)"
    else
        log_error "管理后台服务启动失败"
        exit 1
    fi
    
    # 保存 PID 到文件
    echo $APP_PID > /opt/pppoe-activation/app.pid
    echo $ADMIN_PID > /opt/pppoe-activation/admin.pid
}

# 信号处理
signal_handler() {
    log_info "接收到停止信号，正在关闭服务..."
    
    # 停止服务
    if [[ -f /opt/pppoe-activation/app.pid ]]; then
        APP_PID=$(cat /opt/pppoe-activation/app.pid)
        kill $APP_PID 2>/dev/null || true
        log_info "用户激活服务已停止"
    fi
    
    if [[ -f /opt/pppoe-activation/admin.pid ]]; then
        ADMIN_PID=$(cat /opt/pppoe-activation/admin.pid)
        kill $ADMIN_PID 2>/dev/null || true
        log_info "管理后台服务已停止"
    fi
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
    echo ""
    echo "📌 默认管理员账号："
    echo "   用户名: admin"
    echo "   密码: admin123"
    echo ""
    echo "📌 配置的网络接口："
    IFS=' ' read -ra INTERFACES <<< "$NETWORK_INTERFACES"
    for interface in "${INTERFACES[@]}"; do
        echo "   - $interface"
    done
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
    generate_config
    configure_network
    configure_ppp_device
    init_database
    start_services
    show_startup_info
    
    # 保持容器运行
    wait
}

# 执行主函数
main
