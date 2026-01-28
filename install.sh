#!/bin/bash

# PPPOE 激活管理系统一键安装脚本
# 版本: v1.0
# 更新日期: 2025-12-09

set -e  # 遇错退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# 检查是否为 root 用户
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_error "请不要使用 root 用户运行此脚本"
        log_info "请使用普通用户运行，脚本会在需要时请求 sudo 权限"
        exit 1
    fi
}

# 检测操作系统
detect_os() {
    log_info "检测操作系统..."
    
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$NAME
        VER=$VERSION_ID
    else
        log_error "无法检测操作系统版本"
        exit 1
    fi
    
    log_info "检测到操作系统: $OS $VER"
    
    # 检查兼容性
    if [[ "$OS" == *"Ubuntu"* ]] || [[ "$OS" == *"Debian"* ]]; then
        PKG_MANAGER="apt"
        PKG_UPDATE="apt update"
        PKG_INSTALL="apt install -y"
    elif [[ "$OS" == *"CentOS"* ]] || [[ "$OS" == *"Red Hat"* ]] || [[ "$OS" == *"Rocky"* ]]; then
        PKG_MANAGER="yum"
        PKG_UPDATE="yum update -y"
        PKG_INSTALL="yum install -y"
    else
        log_error "不支持的操作系统: $OS"
        exit 1
    fi
    
    log_success "包管理器: $PKG_MANAGER"
}

# 检测网络接口
detect_network_interfaces() {
    log_info "检测网络接口..."
    
    # 获取所有以太网接口
    INTERFACES=($(ip link show | grep -E '^[0-9]+: en' | awk -F': ' '{print $2}' | grep -v '@'))
    
    if [[ ${#INTERFACES[@]} -lt 4 ]]; then
        log_warning "检测到的网络接口数量少于4个，可能影响系统功能"
        log_info "检测到的接口: ${INTERFACES[*]}"
    else
        log_success "检测到 ${#INTERFACES[@]} 个网络接口: ${INTERFACES[*]}"
    fi
    
    # 默认使用前4个接口
    DEFAULT_INTERFACES=("${INTERFACES[@]:0:4}")
}

# 检测 Python 版本
detect_python() {
    log_info "检测 Python 版本..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
        PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info[0])")
        PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info[1])")
        
        log_info "检测到 Python 版本: $PYTHON_VERSION"
        
        if [[ $PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -ge 8 ]]; then
            log_success "Python 版本符合要求 (>= 3.8)"
        else
            log_error "Python 版本过低，需要 3.8 或更高版本"
            exit 1
        fi
    else
        log_error "未找到 Python3"
        exit 1
    fi
}

# 安装系统依赖
install_system_deps() {
    log_info "安装系统依赖..."
    
    sudo $PKG_UPDATE
    sudo $PKG_INSTALL python3 python3-pip python3-venv sqlite3 pppoe systemd curl wget git
    
    log_success "系统依赖安装完成"
}

# 创建系统用户
create_user() {
    log_info "创建系统用户..."
    
    if ! id "ppp" &>/dev/null; then
        sudo useradd -m -s /bin/bash ppp
        sudo usermod -a -G adm,dip,plugdev ppp
        
        # 如果是 Ubuntu/Debian，添加到 sudo 组
        if [[ "$PKG_MANAGER" == "apt" ]]; then
            sudo usermod -a -G sudo ppp
        fi
        
        log_success "用户 ppp 创建成功"
    else
        log_info "用户 ppp 已存在"
    fi
}

# 配置 sudo 权限
configure_sudo() {
    log_info "配置 sudo 权限..."
    
    SUDO_FILE="/etc/sudoers.d/pppoe-user"
    
    sudo tee "$SUDO_FILE" > /dev/null <<EOF
# PPPoE 激活系统 sudo 权限
ppp ALL=(ALL) NOPASSWD: /usr/sbin/pppd
ppp ALL=(ALL) NOPASSWD: /bin/ip
ppp ALL=(ALL) NOPASSWD: /usr/bin/pkill
ppp ALL=(ALL) NOPASSWD: /opt/pppoe-activation/mac_set.sh
EOF
    
    log_success "sudo 权限配置完成"
}

# 创建项目目录
create_directories() {
    log_info "创建项目目录..."
    
    sudo mkdir -p /opt/pppoe-activation
    sudo mkdir -p /opt/pppoe-activation/logs
    sudo mkdir -p /opt/pppoe-activation/logs/archive
    
    sudo chown -R ppp:ppp /opt/pppoe-activation
    
    log_success "项目目录创建完成"
}

# 复制源代码
copy_source() {
    log_info "复制源代码..."
    
    # 获取脚本所在目录
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # 复制所有文件到目标目录
    sudo cp -r "$SCRIPT_DIR"/* /opt/pppoe-activation/
    sudo chown -R ppp:ppp /opt/pppoe-activation
    
    log_success "源代码复制完成"
}

# 创建虚拟环境
create_venv() {
    log_info "创建 Python 虚拟环境..."
    
    sudo -u ppp bash -c "cd /opt/pppoe-activation && python3 -m venv venv"
    
    log_success "虚拟环境创建完成"
}

# 安装 Python 依赖
install_python_deps() {
    log_info "安装 Python 依赖..."
    
    sudo -u ppp bash -c "cd /opt/pppoe-activation && source venv/bin/activate && pip install --upgrade pip"
    sudo -u ppp bash -c "cd /opt/pppoe-activation && source venv/bin/activate && pip install -r requirements.txt"
    
    log_success "Python 依赖安装完成"
}

# 配置网络接口
configure_network() {
    log_info "配置网络接口..."
    
    # 启用检测到的网络接口
    for interface in "${DEFAULT_INTERFACES[@]}"; do
        sudo ip link set "$interface" up 2>/dev/null || log_warning "无法启用接口 $interface"
    done
    
    log_success "网络接口配置完成"
}

# 生成配置文件
generate_config() {
    log_info "生成配置文件..."
    
    CONFIG_FILE="/opt/pppoe-activation/config.py"
    
    sudo tee "$CONFIG_FILE" > /dev/null <<EOF
# PPPOE 激活系统配置文件
# 自动生成于 $(date)

BASE_DIR = '/opt/pppoe-activation'

# SQLite 数据库路径
DATABASE_PATH = f'{BASE_DIR}/database.db'

# 网络接口配置
NETWORK_INTERFACES = [
EOF

    # 添加网络接口到配置文件
    for i in "${!DEFAULT_INTERFACES[@]}"; do
        interface="${DEFAULT_INTERFACES[$i]}"
        if [[ $i -eq $((${#DEFAULT_INTERFACES[@]} - 1)) ]]; then
            echo "    '$interface'" | sudo tee -a "$CONFIG_FILE" > /dev/null
        else
            echo "    '$interface'," | sudo tee -a "$CONFIG_FILE" > /dev/null
        fi
    done

    sudo tee -a "$CONFIG_FILE" > /dev/null <<EOF
]

# 日志目录
PPP_LOG_DIR = f'{BASE_DIR}/logs'

# 服务端口配置
APP_PORT = 8080
ADMIN_PORT = 8081
DASHBOARD_PORT = 8082
EOF
    
    sudo chown ppp:ppp "$CONFIG_FILE"
    
    log_success "配置文件生成完成"
    log_info "配置的网络接口: ${DEFAULT_INTERFACES[*]}"
}

# 初始化数据库
init_database() {
    log_info "初始化数据库..."
    
    sudo -u ppp bash -c "cd /opt/pppoe-activation && source venv/bin/activate && python3 init_db.py"
    
    log_success "数据库初始化完成"
}

# 设置脚本权限
set_permissions() {
    log_info "设置脚本权限..."
    
    sudo chmod +x /opt/pppoe-activation/mac_set.sh
    sudo chmod +x /opt/pppoe-activation/install_services.sh
    sudo chmod +x /opt/pppoe-activation/setup.sh
    
    log_success "脚本权限设置完成"
}

# 创建 systemd 服务
create_services() {
    log_info "创建 systemd 服务..."
    
    # 用户激活服务
    sudo tee /etc/systemd/system/pppoe-app.service > /dev/null <<EOF
[Unit]
Description=PPPoE 用户拨号服务
After=network.target

[Service]
Type=simple
User=ppp
Group=ppp
WorkingDirectory=/opt/pppoe-activation
ExecStart=/usr/bin/python3 /opt/pppoe-activation/app.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

    # 管理后台服务
    sudo tee /etc/systemd/system/pppoe-admin.service > /dev/null <<EOF
[Unit]
Description=PPPoE 管理员后台服务
After=network.target

[Service]
Type=simple
User=ppp
Group=ppp
WorkingDirectory=/opt/pppoe-activation
ExecStart=/bin/bash -c 'source venv/bin/activate && exec python3 admin.py'
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    
    log_success "systemd 服务创建完成"
}

# 启动服务
start_services() {
    log_info "启动服务..."
    
    sudo systemctl enable pppoe-app.service
    sudo systemctl enable pppoe-admin.service
    
    sudo systemctl start pppoe-app.service
    sudo systemctl start pppoe-admin.service
    
    log_success "服务启动完成"
}

# 配置防火墙
configure_firewall() {
    log_info "配置防火墙..."
    
    if command -v ufw &> /dev/null; then
        sudo ufw allow 8080/tcp
        sudo ufw allow 8081/tcp
        log_info "UFW 防火墙规则已添加"
    elif command -v firewall-cmd &> /dev/null; then
        sudo firewall-cmd --permanent --add-port=8080/tcp
        sudo firewall-cmd --permanent --add-port=8081/tcp
        sudo firewall-cmd --reload
        log_info "firewalld 防火墙规则已添加"
    else
        log_warning "未检测到防火墙管理工具，请手动配置防火墙开放 8080 和 8081 端口"
    fi
}

# 验证安装
verify_installation() {
    log_info "验证安装..."
    
    # 检查服务状态
    if systemctl is-active --quiet pppoe-app.service; then
        log_success "pppoe-app 服务运行正常"
    else
        log_error "pppoe-app 服务未运行"
        return 1
    fi
    
    if systemctl is-active --quiet pppoe-admin.service; then
        log_success "pppoe-admin 服务运行正常"
    else
        log_error "pppoe-admin 服务未运行"
        return 1
    fi
    
    # 检查端口监听
    if netstat -tlnp 2>/dev/null | grep -q ":8080"; then
        log_success "8080 端口监听正常"
    else
        log_error "8080 端口未监听"
        return 1
    fi
    
    if netstat -tlnp 2>/dev/null | grep -q ":8081"; then
        log_success "8081 端口监听正常"
    else
        log_error "8081 端口未监听"
        return 1
    fi
    
    log_success "安装验证完成"
}

# 显示安装结果
show_result() {
    echo ""
    echo "=========================================="
    echo "🎉 PPPOE 激活系统安装完成！"
    echo "=========================================="
    echo ""
    echo "📌 访问地址："
    echo "   用户激活页面: http://$(hostname -I | awk '{print $1}'):8080"
    echo "   管理后台页面: http://$(hostname -I | awk '{print $1}'):8081"
    echo ""
    echo "📌 默认管理员账号："
    echo "   用户名: admin"
    echo "   密码: admin123"
    echo ""
    echo "📌 配置的网络接口："
    for interface in "${DEFAULT_INTERFACES[@]}"; do
        echo "   - $interface"
    done
    echo ""
    echo "📌 服务管理命令："
    echo "   查看服务状态: sudo systemctl status pppoe-app.service"
    echo "   重启服务: sudo systemctl restart pppoe-app.service"
    echo "   查看日志: sudo journalctl -u pppoe-app.service -f"
    echo ""
    echo "📌 重要提示："
    echo "   1. 请立即修改默认管理员密码"
    echo "   2. 检查防火墙配置"
    echo "   3. 定期备份数据库"
    echo ""
}

# 主函数
main() {
    echo "=========================================="
    echo "🚀 PPPOE 激活系统一键安装脚本"
    echo "=========================================="
    echo ""
    
    check_root
    detect_os
    detect_python
    detect_network_interfaces
    
    echo ""
    log_info "即将开始安装，配置如下："
    log_info "操作系统: $OS $VER"
    log_info "Python 版本: $PYTHON_VERSION"
    log_info "网络接口: ${DEFAULT_INTERFACES[*]}"
    echo ""
    
    read -p "是否继续安装？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "安装已取消"
        exit 0
    fi
    
    install_system_deps
    create_user
    configure_sudo
    create_directories
    copy_source
    create_venv
    install_python_deps
    configure_network
    generate_config
    init_database
    set_permissions
    create_services
    start_services
    configure_firewall
    
    if verify_installation; then
        show_result
    else
        log_error "安装验证失败，请检查日志"
        exit 1
    fi
}

# 运行主函数
main "$@"