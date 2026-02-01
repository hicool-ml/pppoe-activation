#!/bin/bash

# PPPOE 激活系统完整备份脚本
# 版本: 1.0.0
# 功能：备份源代码、Docker镜像、数据库和日志

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

# 获取当前目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 生成备份时间戳
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/tmp/pppoe-backup-${BACKUP_DATE}"

log_info "=========================================="
log_info "PPPOE 激活系统完整备份"
log_info "=========================================="
log_info "备份时间: $(date)"
log_info "备份目录: ${BACKUP_DIR}"
echo ""

# 创建备份目录
log_info "创建备份目录..."
mkdir -p "${BACKUP_DIR}"
log_success "备份目录创建成功"
echo ""

# 1. 备份源代码（排除数据库和日志）
log_info "备份源代码..."
tar -czf "${BACKUP_DIR}/pppoe-activation-source.tar.gz" \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='.pytest_cache' \
    --exclude='.coverage' \
    --exclude='htmlcov' \
    --exclude='.tox' \
    --exclude='*.log' \
    --exclude='logs' \
    --exclude='instance' \
    --exclude='data' \
    --exclude='database.db' \
    --exclude='activation_log.jsonl' \
    -C "${SCRIPT_DIR}" .
log_success "源代码备份完成"
echo ""

# 2. 备份数据库
log_info "备份数据库..."
if [[ -f "${SCRIPT_DIR}/instance/database.db" ]]; then
    tar -czf "${BACKUP_DIR}/pppoe-activation-database.tar.gz" \
        -C "${SCRIPT_DIR}" instance/
    log_success "数据库备份完成"
else
    log_error "数据库文件不存在，跳过数据库备份"
fi
echo ""

# 3. 备份日志
log_info "备份日志..."
if [[ -d "${SCRIPT_DIR}/logs" ]]; then
    tar -czf "${BACKUP_DIR}/pppoe-activation-logs.tar.gz" \
        -C "${SCRIPT_DIR}" logs/
    log_success "日志备份完成"
else
    log_error "日志目录不存在，跳过日志备份"
fi
echo ""

# 4. 备份运行时数据
log_info "备份运行时数据..."
if [[ -d "${SCRIPT_DIR}/data" ]]; then
    tar -czf "${BACKUP_DIR}/pppoe-activation-data.tar.gz" \
        -C "${SCRIPT_DIR}" data/
    log_success "运行时数据备份完成"
else
    log_info "运行时数据目录不存在，跳过"
fi
echo ""

# 5. 备份 Docker 镜像
log_info "备份 Docker 镜像..."
if docker images | grep -q "pppoe-activation"; then
    docker save pppoe-activation:latest -o "${BACKUP_DIR}/pppoe-activation-image.tar"
    log_success "Docker镜像备份完成"
else
    log_error "Docker镜像不存在，跳过镜像备份"
fi
echo ""

# 6. 备份环境配置文件
log_info "备份环境配置文件..."
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
    cp "${SCRIPT_DIR}/.env" "${BACKUP_DIR}/.env.backup"
    log_success "环境配置文件备份完成"
else
    log_info "环境配置文件不存在，跳过"
fi
echo ""

# 7. 生成备份清单
log_info "生成备份清单..."
cat > "${BACKUP_DIR}/backup-manifest.txt" << EOF
==========================================
PPPOE 激活系统备份清单
==========================================
备份时间: $(date)
备份目录: ${BACKUP_DIR}

备份文件列表:
$(ls -lh "${BACKUP_DIR}")

备份内容说明:
- pppoe-activation-source.tar.gz: 源代码（不含数据库和日志）
- pppoe-activation-database.tar.gz: 数据库（管理员账号、网络配置、激活日志）
- pppoe-activation-logs.tar.gz: 所有拨号日志
- pppoe-activation-data.tar.gz: 运行时数据
- pppoe-activation-image.tar: Docker镜像
- .env.backup: 环境配置文件

恢复方法:
1. 解压源代码: tar -xzf pppoe-activation-source.tar.gz
2. 恢复Docker镜像: docker load -i pppoe-activation-image.tar
3. 恢复数据库: tar -xzf pppoe-activation-database.tar.gz
4. 恢复日志: tar -xzf pppoe-activation-logs.tar.gz
5. 恢复数据: tar -xzf pppoe-activation-data.tar.gz
6. 启动容器: docker start pppoe-activation 或使用 docker run 命令

注意事项:
- 恢复前请先停止容器: docker stop pppoe-activation
- 确保恢复到正确的目录
- 检查文件权限是否正确
==========================================
EOF
log_success "备份清单生成完成"
echo ""

# 8. 计算备份大小
log_info "计算备份大小..."
BACKUP_SIZE=$(du -sh "${BACKUP_DIR}" | cut -f1)
log_success "备份总大小: ${BACKUP_SIZE}"
echo ""

# 9. 显示备份结果
log_info "=========================================="
log_success "备份完成！"
log_info "=========================================="
log_info "备份目录: ${BACKUP_DIR}"
log_info "备份大小: ${BACKUP_SIZE}"
echo ""
ls -lh "${BACKUP_DIR}"
echo ""
log_info "备份清单: ${BACKUP_DIR}/backup-manifest.txt"
echo ""
log_info "您可以将整个 ${BACKUP_DIR} 目录复制到安全的地方"
echo ""

# 10. 询问是否创建压缩包
read -p "是否创建单个压缩包？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "创建完整备份压缩包..."
    cd /tmp
    tar -czf "pppoe-backup-${BACKUP_DATE}.tar.gz" "pppoe-backup-${BACKUP_DATE}/"
    log_success "完整备份压缩包创建完成: /tmp/pppoe-backup-${BACKUP_DATE}.tar.gz"
    log_info "您可以删除原始备份目录以节省空间: rm -rf ${BACKUP_DIR}"
fi

echo ""
log_success "所有备份任务完成！"
