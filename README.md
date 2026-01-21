# PPPOE 激活系统

一个基于 Docker 的 PPPOE 拨号激活系统，支持多网卡并发拨号，提供 Web 管理界面。

## 功能特性

- ✅ 多网卡并发拨号
- ✅ 自动 MAC 地址随机化
- ✅ Web 用户激活界面
- ✅ Web 管理后台
- ✅ 激活日志记录
- ✅ 数据持久化存储
- ✅ Docker 一键部署
- ✅ Web 配置界面（首次部署）
- ✅ 使用标准端口 80，无需指定端口号

## 快速开始

### 方法 1：使用 Web 配置界面（推荐）

```bash
# 1. 启动初始化配置服务
docker-compose --profile init up -d init-config

# 2. 打开浏览器访问 http://localhost:9999

# 3. 在 Web 界面中选择网卡和配置持久化存储路径

# 4. 配置完成后，重启服务
docker-compose restart

# 5. 访问应用（无需指定端口号）
# 用户激活页面：http://localhost/
# 管理后台页面：http://localhost/dashboard
```

### 方法 2：直接配置

```bash
# 1. 复制配置文件
cp config.example.py config.py
cp .env.example .env

# 2. 编辑配置文件
nano config.py  # 修改网卡配置
nano .env       # 修改环境变量

# 3. 启动服务
docker-compose up -d
```

## 配置说明

### 网卡配置

根据实际硬件设备修改网卡名称：

```python
# config.py
NETWORK_INTERFACES = ['eth0', 'eth1', 'eth2', 'eth3']
```

查看可用网卡：
```bash
ip link show
```

### 端口配置

默认使用标准端口 80，无需指定端口号：

```bash
# .env
APP_PORT=80      # 用户激活服务端口（默认）
ADMIN_PORT=80    # 管理后台端口（默认）
```

访问地址：
- 用户激活页面：http://ip/ 或 http://ip/
- 管理后台页面：http://ip/dashboard 或 http://ip/dashboard

### 持久化存储配置

```bash
# .env
DATA_PATH=./data           # 数据目录
LOGS_PATH=./logs           # 日志目录
DB_PATH=./database.db      # 数据库文件
INSTANCE_PATH=./instance   # 实例目录
```

## 文档

- [`部署指南.md`](部署指南.md:1) - 详细的部署指南
- [`Docker优化说明.md`](Docker优化说明.md:1) - Docker 镜像优化说明
- [`持久化存储配置说明.md`](持久化存储配置说明.md:1) - 持久化存储配置说明

## 项目结构

```
pppoe-activation/
├── app.py                      # 主应用（用户激活服务）
├── dashboard.py                # 管理后台
├── models.py                  # 数据库模型
├── config.py                  # 配置文件
├── sync.py                    # 日志同步
├── mac_set.sh                 # MAC地址设置脚本
├── docker-entrypoint.sh       # Docker启动脚本
├── init_config.py            # 初始化配置服务
├── init_db.py                # 数据库初始化
├── Dockerfile                 # Docker构建文件
├── docker-compose.yml         # Docker Compose配置
├── requirements.txt           # Python依赖（完整版）
├── requirements.minimal.txt   # Python依赖（精简版）
├── .env.example             # 环境变量示例
├── config.example.py        # 配置文件示例
├── templates/               # HTML模板
│   ├── init_config.html    # 初始化配置页面
│   ├── init_success.html   # 配置成功页面
│   └── ...
└── web/                    # Web资源
    ├── static/            # 静态资源
    └── templates/        # 管理后台模板
```

## 常用命令

### 启动服务

```bash
docker-compose up -d
```

### 停止服务

```bash
docker-compose down
```

### 重启服务

```bash
docker-compose restart
```

### 查看日志

```bash
docker-compose logs -f
```

### 重新构建

```bash
docker-compose build
docker-compose up -d --build
```

## 默认账号

- 用户名：`admin`
- 密码：`admin123`

**重要**：首次登录后请立即修改密码！

## 技术栈

- 后端：Python 3.12 + Flask
- 数据库：SQLite
- 容器：Docker + Docker Compose
- 前端：HTML + Bootstrap + jQuery

## 系统要求

- Docker 20.10+
- Docker Compose 1.29+
- Linux 系统（推荐 Ubuntu 20.04+）
- 至少一个网络接口用于 PPPOE 拨号
- 至少 2GB 可用内存
- 至少 10GB 可用磁盘空间

## 优化说明

本项目已经过 Docker 镜像优化，预计镜像大小从 1GB 减少到 200-250MB（减少 75-80%）。

主要优化点：
- 使用 `python:3.12-slim` 替代 `ubuntu:24.04`
- 移除不必要的系统依赖
- 使用精简版 Python 依赖（移除数据可视化库）
- 优化层缓存
- 清理所有缓存
- 完善的 `.dockerignore` 规则

详见 [`Docker优化说明.md`](Docker优化说明.md:1)。

## 故障排查

### 容器无法启动

```bash
# 查看日志
docker-compose logs

# 检查配置文件
cat config.py
cat .env
```

### 无法访问 Web 界面

```bash
# 检查容器状态
docker ps

# 检查端口映射
docker port pppoe-activation

# 检查防火墙
sudo ufw status
```

### 网卡不存在

```bash
# 在容器内查看可用网卡
docker exec pppoe-activation ip link show

# 更新配置文件
nano config.py
docker-compose restart
```

更多故障排查方法，请查看 [`部署指南.md`](部署指南.md:1)。

## 许可证

本项目仅供学习和研究使用。

## 贡献

欢迎提交 Issue 和 Pull Request。

## 联系方式

如有问题，请提交 Issue。
