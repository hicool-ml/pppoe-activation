# PPPOE 激活系统 Docker 镜像（优化版）
# 版本: 2.0.0
# 更新日期: 2025-12-19
# 优化目标：减少镜像大小，加快构建速度，不打包历史数据

# 使用更小的 Python slim 基础镜像（约120MB）
FROM python:3.12-slim

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置非交互式安装
ENV DEBIAN_FRONTEND=noninteractive

# 安装系统依赖（只安装必需的）
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 网络工具
    pppoe \
    iproute2 \
    # 进程管理
    procps \
    # 必需工具
    curl \
    sudo \
    # 内核模块管理
    kmod \
    # 清理缓存
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* \
    # 加载PPPOE内核模块
    && modprobe pppoe pppox pppoa pppoe_mppe pppoe_async pppoe_synctty 2>/dev/null || true \
    && echo "PPPOE内核模块已加载"

# 创建应用用户
RUN useradd -m -s /bin/bash ppp && \
    usermod -a -G adm,dip,plugdev ppp

# 创建应用目录
WORKDIR /opt/pppoe-activation

# 优化：先复制依赖文件，利用 Docker 层缓存
COPY requirements.minimal.txt requirements.txt

# 安装 Python 依赖（使用精简版，移除数据可视化库）
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制应用文件（排除 .dockerignore 中指定的文件）
COPY . .

# 设置文件权限
RUN chown -R ppp:ppp /opt/pppoe-activation && \
    chmod +x /opt/pppoe-activation/mac_set.sh

# 创建必要的目录（用于外部挂载）
RUN mkdir -p /opt/pppoe-activation/logs && \
    mkdir -p /opt/pppoe-activation/logs/archive && \
    mkdir -p /opt/pppoe-activation/data && \
    mkdir -p /opt/pppoe-activation/instance && \
    chown -R ppp:ppp /opt/pppoe-activation/logs /opt/pppoe-activation/data /opt/pppoe-activation/instance

# 配置 sudo 权限
RUN echo "ppp ALL=(ALL) NOPASSWD: /usr/sbin/pppd" >> /etc/sudoers.d/pppoe-user && \
    echo "ppp ALL=(ALL) NOPASSWD: /bin/ip" >> /etc/sudoers.d/pppoe-user && \
    echo "ppp ALL=(ALL) NOPASSWD: /usr/bin/pkill" >> /etc/sudoers.d/pppoe-user && \
    echo "ppp ALL=(ALL) NOPASSWD: /opt/pppoe-activation/mac_set.sh" >> /etc/sudoers.d/pppoe-user && \
    chmod 440 /etc/sudoers.d/pppoe-user

# 暴露端口
EXPOSE 8080 8081

# 启动脚本
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 设置健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=40s \
    CMD curl -f http://localhost:80/ || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
