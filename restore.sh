#!/bin/bash

# PPPOE 激活系统完整恢复脚本
# 版本: 1.0.0
# 功能：从备份恢复源代码、Docker镜像、数据库和日志

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

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# 显示使用方法
show_usage() {
    echo "使用方法:"
    echo "  $0 <备份目录>"
    echo ""
    echo "示例:"
    echo "  $0 /tmp/pppoe-backup-20260201_120000"
    echo ""
    exit 1
}

# 检查参数
if [[ $# -lt 1 ]]; then
    show_usage
fi

BACKUP_DIR="$1"

# 检查备份目录是否存在
if [[ ! -d "${BACKUP_DIR}" ]]; then
    log_error "备份目录不存在: ${BACKUP_DIR}"
    exit 1
fi

# 获取当前目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log_info "=========================================="
log_info "PPPOE 激活系统完整恢复"
log_info "=========================================="
log_info "恢复时间: $(date)"
log_info "备份目录: ${BACKUP_DIR}"
log_info "目标目录: ${SCRIPT_DIR}"
echo ""

# 确认操作
log_warning "警告：此操作将覆盖当前目录中的文件！"
read -p "是否继续？(yes/no) " -r
echo
if [[ ! $REPLY == "yes" ]]; then
    log_info "恢复操作已取消"
    exit 0
fi

# 停止容器
log_info "停止容器..."
if docker ps -a | grep -q "pppoe-activation"; then
    docker stop pppoe-activation
    log_success "容器已停止"
else
    log_info "容器未运行，跳过"
fi
echo ""

# 1. 恢复源代码
log_info "恢复源代码..."
if [[ -f "${BACKUP_DIR}/pppoe-activation-source.tar.gz" ]]; then
    tar -xzf "${BACKUP_DIR}/pppoe-activation-source.tar.gz" -C "${SCRIPT_DIR}"
    log_success "源代码恢复完成"
else
    log_error "源代码备份文件不存在，跳过"
fi
echo ""

# 2. 恢复数据库
log_info "恢复数据库..."
if [[ -f "${BACKUP_DIR}/pppoe-activation-database.tar.gz" ]]; then
    tar -xzf "${BACKUP_DIR}/pppoe-activation-database.tar.gz" -C "${SCRIPT_DIR}"
    log_success "数据库恢复完成"
else
    log_warning "数据库备份文件不存在，跳过"
fi
echo ""

# 3. 恢复日志
log_info "恢复日志..."
if [[ -f "${BACKUP_DIR}/pppoe-activation-logs.tar.gz" ]]; then
    tar -xzf "${BACKUP_DIR}/pppoe-activation-logs.tar.gz" -C "${SCRIPT_DIR}"
    log_success "日志恢复完成"
else
    log_warning "日志备份文件不存在，跳过"
fi
echo ""

# 4. 恢复运行时数据
log_info "恢复运行时数据..."
if [[ -f "${BACKUP_DIR}/pppoe-activation-data.tar.gz" ]]; then
    tar -xzf "${BACKUP_DIR}/pppoe-activation-data.tar.gz" -C "${SCRIPT_DIR}"
    log_success "运行时数据恢复完成"
else
    log_info "运行时数据备份文件不存在，跳过"
fi
echo ""

# 5. 恢复 Docker 镜像
log_info "恢复 Docker 镜像..."
if [[ -f "${BACKUP_DIR}/pppoe-activation-image.tar" ]]; then
    docker load -i "${BACKUP_DIR}/pppoe-activation-image.tar"
    log_success "Docker镜像恢复完成"
else
    log_warning "Docker镜像备份文件不存在，跳过"
fi
echo ""

# 6. 恢复环境配置文件
log_info "恢复环境配置文件..."
if [[ -f "${BACKUP_DIR}/.env.backup" ]]; then
    cp "${BACKUP_DIR}/.env.backup" "${SCRIPT_DIR}/.env"
    log_success "环境配置文件恢复完成"
else
    log_info "环境配置文件备份不存在，跳过"
fi
echo ""

# 7. 设置文件权限
log_info "设置文件权限..."
chmod +x "${SCRIPT_DIR}/backup.sh" 2>/dev/null || true
chmod +x "${SCRIPT_DIR}/restore.sh" 2>/dev/null || true
chmod +x "${SCRIPT_DIR}/docker-entrypoint.sh" 2>/dev/null || true
log_success "文件权限设置完成"
echo ""

# 8. 删除旧容器
log_info "删除旧容器..."
if docker ps -a | grep -q "pppoe-activation"; then
    docker rm pppoe-activation
    log_success "旧容器已删除"
else
    log_info "旧容器不存在，跳过"
fi
echo ""

# 9. 启动容器
log_info "启动容器..."
docker run -d --name pppoe-activation --restart=unless-stopped \
    --device=/dev/ppp \
    --cap-add=NET_ADMIN \
    -p 80:80 \
    -p 8081:8081 \
    -p 9999:9999 \
    -v "${SCRIPT_DIR}/logs:/opt/pppoe-activation/logs" \
    -v "${SCRIPT_DIR}/data:/opt/pppoe-activation/data" \
    -v "${SCRIPT_DIR}/instance:/opt/pppoe-activation/instance" \
    --network=host \
    pppoe-activation:latest
log_success "容器已启动"
echo ""

# 10. 等待容器启动
log_info "等待容器启动..."
sleep 5
echo ""

# 11. 检查容器状态
log_info "检查容器状态..."
if docker ps | grep -q "pppoe-activation"; then
    log_success "容器运行正常"
    docker ps | grep pppoe-activation
else
    log_error "容器启动失败"
    log_info "查看容器日志: docker logs pppoe-activation"
fi
echo ""

log_info "=========================================="
log_success "恢复完成！"
log_info "=========================================="
log_info "访问地址："
log_info "  用户激活页面: http://localhost:80"
log_info "  管理后台页面: http://localhost:8081"
log_info "  配置管理页面: http://localhost:9999"
echo ""
log_info "查看容器日志: docker logs -f pppoe-activation"
echo ""
