#!/bin/bash
#
# PPPOE 激活系统 - 离线部署脚本
# 适用于完全离线环境的部署
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# 打印标题
print_title() {
    echo ""
    echo "========================================="
    echo "$1"
    echo "========================================="
    echo ""
}

# 检查是否为 root 用户
check_root() {
    if [ "$EUID" -ne 0 ]; then 
        print_error "请使用 root 权限运行此脚本"
        print_info "使用方法: sudo $0"
        exit 1
    fi
}

# 检查 Docker 是否已安装
check_docker() {
    if command -v docker &> /dev/null; then
        print_success "Docker 已安装: $(docker --version)"
        return 0
    else
        print_warning "Docker 未安装"
        return 1
    fi
}

# 检查 /dev/ppp 设备
check_ppp_device() {
    print_title "检查 PPP 设备"
    
    if [[ -c /dev/ppp ]]; then
        print_success "/dev/ppp 设备存在"
        ls -l /dev/ppp
    else
        print_warning "/dev/ppp 设备不存在，尝试创建..."
        
        # 尝试加载 PPP 内核模块
        print_info "加载 PPP 内核模块..."
        modprobe ppp_async 2>/dev/null || true
        modprobe ppp_generic 2>/dev/null || true
        
        # 检查是否成功
        if [[ -c /dev/ppp ]]; then
            print_success "PPP 内核模块加载成功"
            ls -l /dev/ppp
        else
            # 尝试手动创建设备
            print_info "尝试手动创建 /dev/ppp 设备..."
            if mknod /dev/ppp c 108 0 2>/dev/null; then
                chmod 666 /dev/ppp
                print_success "/dev/ppp 设备创建成功"
                ls -l /dev/ppp
            else
                print_error "/dev/ppp 设备创建失败"
                print_warning "pppd 拨号可能无法工作，请手动创建设备"
                print_info "手动创建命令："
                print_info "  sudo mknod /dev/ppp c 108 0"
                print_info "  sudo chmod 666 /dev/ppp"
            fi
        fi
    fi
}

# 安装 Docker
install_docker() {
    print_title "安装 Docker"
    
    if [ -d "docker-packages" ]; then
        print_info "正在安装 Docker DEB 包..."
        cd docker-packages
        dpkg -i *.deb || apt-get install -f -y
        cd ..
        print_success "Docker 安装完成！"
    else
        print_error "未找到 Docker 安装包 (docker-packages/)"
        print_info "请准备 Docker 安装包或手动安装 Docker"
        exit 1
    fi
}

# 启动 Docker 服务
start_docker() {
    print_title "启动 Docker 服务"
    
    print_info "启动 Docker 服务..."
    systemctl start docker
    
    print_info "设置 Docker 开机自启..."
    systemctl enable docker
    
    print_success "Docker 服务已启动并设置为开机自启"
}

# 导入 Docker 镜像
import_docker_image() {
    print_title "导入 Docker 镜像"
    
    if [ -f "pppoe-activation-image.tar" ]; then
        print_info "正在导入 Docker 镜像..."
        docker load -i pppoe-activation-image.tar
        print_success "Docker 镜像导入完成！"
        
        print_info "查看导入的镜像："
        docker images | grep pppoe-activation
    else
        print_error "未找到 Docker 镜像文件 (pppoe-activation-image.tar)"
        exit 1
    fi
}

# 解压源代码
extract_source() {
    print_title "解压源代码"
    
    if [ -f "pppoe-activation-source.tar.gz" ]; then
        print_info "正在解压源代码..."
        tar -xzf pppoe-activation-source.tar.gz
        
        if [ -d "pppoe-activation" ]; then
            cd pppoe-activation
            print_success "源代码解压完成！"
        else
            print_error "源代码解压失败"
            exit 1
        fi
    else
        print_error "未找到源代码文件 (pppoe-activation-source.tar.gz)"
        exit 1
    fi
}

# 创建持久化目录
create_persistent_dirs() {
    print_title "创建持久化目录"
    
    print_info "创建持久化目录..."
    mkdir -p logs data instance
    
    print_info "设置目录权限..."
    chmod -R 777 logs data instance
    
    print_success "持久化目录创建完成："
    print_info "  - logs/      (日志目录)"
    print_info "  - data/      (数据目录)"
    print_info "  - instance/  (数据库目录)"
}

# 停止并删除旧容器
remove_old_container() {
    print_title "清理旧容器"
    
    if docker ps -a | grep -q pppoe-activation; then
        print_info "发现已存在的容器，正在删除..."
        docker stop pppoe-activation || true
        docker rm pppoe-activation || true
        print_success "旧容器已删除"
    else
        print_info "未发现旧容器"
    fi
}

# 启动容器
start_container() {
    print_title "启动容器"
    
    print_info "正在启动容器..."
    
    docker run -d --name pppoe-activation \
        --restart=unless-stopped \
        --device=/dev/ppp \
        --cap-add=NET_ADMIN \
        -p 80:80 \
        -p 8081:8081 \
        -p 9999:9999 \
        -v ${PWD}/logs:/opt/pppoe-activation/logs \
        -v ${PWD}/data:/opt/pppoe-activation/data \
        -v ${PWD}/instance:/opt/pppoe-activation/instance \
        --network=host \
        pppoe-activation:latest
    
    print_success "容器启动命令执行完成"
}

# 等待容器启动
wait_for_container() {
    print_title "等待容器启动"
    
    print_info "等待容器完全启动..."
    sleep 5
    
    if docker ps | grep -q pppoe-activation; then
        print_success "容器启动成功！"
    else
        print_error "容器启动失败"
        print_info "查看容器日志："
        docker logs pppoe-activation
        exit 1
    fi
}

# 检查容器状态
check_container_status() {
    print_title "检查容器状态"
    
    print_info "容器状态："
    docker ps | grep pppoe-activation
    
    print_info "容器健康状态："
    docker inspect --format='{{.State.Health.Status}}' pppoe-activation 2>/dev/null || echo "无健康检查"
    
    # 检查容器内的 /dev/ppp 设备
    print_info "检查容器内的 /dev/ppp 设备..."
    if docker exec pppoe-activation ls -l /dev/ppp 2>/dev/null; then
        print_success "容器内 /dev/ppp 设备存在"
    else
        print_error "容器内 /dev/ppp 设备不存在，pppd 拨号可能无法工作"
        print_warning "请确保容器启动时包含 --device=/dev/ppp 参数"
    fi
    
    # 检查容器内的 pppd 命令
    print_info "检查容器内的 pppd 命令..."
    if docker exec pppoe-activation which pppd >/dev/null 2>&1; then
        print_success "容器内 pppd 命令可用"
    else
        print_error "容器内 pppd 命令不可用"
    fi
}

# 显示访问信息
show_access_info() {
    print_title "部署完成"
    
    # 获取本机 IP
    LOCAL_IP=$(hostname -I | awk '{print $1}')
    
    echo ""
    print_success "PPPOE 激活系统部署完成！"
    echo ""
    echo "访问地址："
    echo "  用户激活页面: http://${LOCAL_IP}:80/"
    echo "  管理后台:     http://${LOCAL_IP}:8081/"
    echo "  配置管理:     http://${LOCAL_IP}:9999/"
    echo ""
    echo "默认账号："
    echo "  超级管理员: root / root123"
    echo "  普通管理员: admin / admin123"
    echo ""
    print_warning "重要提示："
    echo "  1. 请立即修改默认管理员密码"
    echo "  2. 请访问配置管理页面进行网络配置"
    echo "  3. 配置地址: http://${LOCAL_IP}:9999/"
    echo ""
}

# 主函数
main() {
    print_title "PPPOE 激活系统 - 离线部署"
    
    # 检查 root 权限
    check_root
    
    # 检查并安装 Docker
    if ! check_docker; then
        install_docker
    fi
    
    # 启动 Docker 服务
    start_docker
    
    # 检查 /dev/ppp 设备
    check_ppp_device
    
    # 导入 Docker 镜像
    import_docker_image
    
    # 解压源代码
    extract_source
    
    # 创建持久化目录
    create_persistent_dirs
    
    # 删除旧容器
    remove_old_container
    
    # 启动容器
    start_container
    
    # 等待容器启动
    wait_for_container
    
    # 检查容器状态
    check_container_status
    
    # 显示访问信息
    show_access_info
    
    print_success "离线部署完成！"
}

# 运行主函数
main
