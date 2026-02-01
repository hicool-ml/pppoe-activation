# PPPOE 激活系统

一个基于 Docker 的 PPPOE 拨号激活系统，支持多网卡并发拨号、VLAN 子接口，提供 Web 管理界面。

## 功能特性

- ✅ 多网卡并发拨号（使用"锁即资源"模型，无竞态条件）
- ✅ 支持 VLAN 子接口拨号（支持单个、范围、逗号分隔等多种格式）
- ✅ 自动 MAC 地址随机化
- ✅ Web 用户激活界面
- ✅ Web 管理后台（支持 ISP 类型区分和背景颜色显示）
- ✅ Web 配置界面（首次部署配置）
- ✅ 激活日志记录和查询
- ✅ 数据持久化存储
- ✅ Docker 一键部署
- ✅ 容器自动启动和重启
- ✅ 自动启用宿主机网卡
- ✅ 完整的备份和恢复脚本
- ✅ 支持多种 ISP 模式（校园网、中国移动、中国电信、中国联通、直拨）
- ✅ 使用标准端口 80，无需指定端口号

## 快速开始

### 方法 1：使用 Docker 直接部署（推荐）

```bash
# 1. 构建镜像
docker build -t pppoe-activation:latest .

# 2. 启动容器
docker run -d --name pppoe-activation \
  --restart=unless-stopped \
  --device=/dev/ppp \
  --cap-add=NET_ADMIN \
  -p 80:80 \
  -p 8081:8081 \
  -p 9999:9999 \
  -v $(pwd)/logs:/opt/pppoe-activation/logs \
  -v $(pwd)/data:/opt/pppoe-activation/data \
  -v $(pwd)/instance:/opt/pppoe-activation/instance \
  --network=host \
  pppoe-activation:latest

# 3. 访问配置页面进行初始化
# 打开浏览器访问 http://localhost:9999

# 4. 访问应用
# 用户激活页面：http://localhost/
# 管理后台页面：http://localhost:8081
```

### 方法 2：使用 Docker Compose

```bash
# 1. 启动服务
docker-compose up -d

# 2. 访问配置页面进行初始化
# 打开浏览器访问 http://localhost:9999

# 3. 访问应用
# 用户激活页面：http://localhost/
# 管理后台页面：http://localhost:8081
```

## 配置说明

### 网络模式配置

系统支持两种网络模式：

**1. 普通模式**：直接使用物理网卡
- 适用场景：单网卡或多网卡直接拨号
- 配置方法：在配置页面选择"普通模式"，选择基础网卡

**2. VLAN 模式**：使用 VLAN 子接口
- 适用场景：需要通过 VLAN 子接口拨号
- 配置方法：在配置页面选择"VLAN 模式"，选择基础网卡和 VLAN ID

VLAN ID 支持多种格式：
- 单个 VLAN：`2000`
- 多个 VLAN（逗号分隔）：`2000,2001,2002`
- VLAN 范围：`2000-2005`
- 混合格式：`2000,2001,2005-2010,2015`

查看可用网卡：
```bash
ip link show
```

### 端口配置

默认使用标准端口 80，无需指定端口号：

| 服务 | 端口 | 说明 |
|------|------|------|
| 用户激活页面 | 80 | 主应用服务 |
| 管理后台页面 | 8081 | 管理后台 |
| 配置管理页面 | 9999 | 初始化配置 |

访问地址：
- 用户激活页面：http://localhost/ 或 http://ip/
- 管理后台页面：http://localhost:8081 或 http://ip:8081
- 配置管理页面：http://localhost:9999 或 http://ip:9999

### ISP 模式配置

系统支持多种 ISP 模式，每种模式有不同的账号前缀/后缀规则：

- **校园网**：账号格式 `prefix@username`
- **中国移动**：账号格式 `prefix@username`
- **中国电信**：账号格式 `prefix@username`
- **中国联通**：账号格式 `prefix@username`
- **直拨**：自由输入完整账号，不添加任何前缀/后缀

### 持久化存储配置

```bash
# Docker 运行参数
-v $(pwd)/logs:/opt/pppoe-activation/logs       # 日志目录
-v $(pwd)/data:/opt/pppoe-activation/data       # 数据目录
-v $(pwd)/instance:/opt/pppoe-activation/instance # 数据库目录
```

## 备份和恢复

### 自动备份

系统提供了完整的备份和恢复脚本：

**备份**：
```bash
./backup.sh
```

备份内容：
- 源代码（所有 Python 文件、配置、模板）
- 数据库（管理员账号、网络配置、激活日志）
- 日志文件（所有拨号日志）
- Docker 镜像（完整容器镜像）
- 环境配置（.env文件）

**恢复**：
```bash
./restore.sh /tmp/pppoe-backup-20260201_120000
```

详细说明请查看 [`BACKUP_README.md`](BACKUP_README.md:1)。

## 项目结构

```
pppoe-activation/
├── app.py                      # 主应用（用户激活服务）
├── dashboard.py                # 管理后台
├── init_config.py            # 初始化配置服务
├── models.py                  # 数据库模型
├── sync.py                    # 日志同步
├── backup.sh                  # 备份脚本
├── restore.sh                 # 恢复脚本
├── docker-entrypoint.sh       # Docker启动脚本（支持自动启用网卡）
├── init_db.py                # 数据库初始化
├── Dockerfile                 # Docker构建文件
├── docker-compose.yml         # Docker Compose配置
├── requirements.txt           # Python依赖
├── .env.example             # 环境变量示例
├── config.example.py        # 配置文件示例
├── BACKUP_README.md          # 备份和恢复指南
├── templates/               # HTML模板
│   ├── index.html          # 用户激活页面
│   ├── init_config.html    # 初始化配置页面
│   └── admin/              # 管理后台模板
│       ├── dashboard.html
│       ├── login.html
│       └── logs.html
└── web/                    # Web资源
    ├── static/            # 静态资源
    └── templates/        # 管理后台模板
```

## 常用命令

### 启动服务

```bash
# Docker 直接启动
docker start pppoe-activation

# Docker Compose 启动
docker-compose up -d
```

### 停止服务

```bash
# Docker 直接停止
docker stop pppoe-activation

# Docker Compose 停止
docker-compose down
```

### 重启服务

```bash
# Docker 直接重启
docker restart pppoe-activation

# Docker Compose 重启
docker-compose restart
```

### 查看日志

```bash
# 查看容器日志
docker logs -f pppoe-activation

# 查看拨号日志
ls -lt logs/
```

### 重新构建

```bash
# 重新构建镜像
docker build -t pppoe-activation:latest .

# 重新构建并启动
docker-compose up -d --build
```

## 默认账号

### 超级管理员

- 用户名：`root`
- 密码：`root123`
- 权限：最高权限，可以管理所有管理员和配置

### 普通管理员

- 用户名：`admin`
- 密码：`admin123`
- 权限：可以查看日志和管理激活记录

**重要**：首次登录后请立即修改密码！

## 技术栈

- 后端：Python 3.12 + Flask
- 数据库：SQLite
- 容器：Docker + Docker Compose
- 前端：HTML + Bootstrap + jQuery
- 并发模型：文件锁（fcntl.flock）实现"锁即资源"模型

## 系统要求

- Docker 20.10+
- Docker Compose 1.29+（可选）
- Linux 系统（推荐 Ubuntu 20.04+）
- 至少一个网络接口用于 PPPOE 拨号
- 至少 2GB 可用内存
- 至少 10GB 可用磁盘空间

## 核心特性说明

### 并发拨号模型

系统使用"锁即资源"（Lock as Resource）并发模型，通过非阻塞文件锁原子性地选择和锁定网络接口，完全消除竞态条件。

### 自动启用网卡

容器启动时会自动启用宿主机所有处于 DOWN 状态的物理网卡，确保 VLAN 子接口能够成功创建。

### 容器自动启动

容器配置了 `--restart=unless-stopped` 策略，会在宿主机重启后自动启动。

## 故障排查

### 容器无法启动

```bash
# 查看日志
docker logs pppoe-activation

# 检查网卡状态
ip link show

# 检查容器状态
docker ps -a
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

### VLAN 子接口创建失败

```bash
# 检查基础网卡状态
ip link show enp7s0

# 手动启动物理网卡
sudo ip link set enp7s0 up

# 检查容器是否有 NET_ADMIN 权限
docker inspect pppoe-activation | grep CapAdd
```

### 网卡不存在

```bash
# 在容器内查看可用网卡
docker exec pppoe-activation ip link show

# 重新配置网络
# 访问 http://localhost:9999 进行配置
```

## 文档

- [`BACKUP_README.md`](BACKUP_README.md:1) - 备份和恢复指南
- [`部署指南.md`](部署指南.md:1) - 详细的部署指南
- [`持久化存储配置说明.md`](持久化存储配置说明.md:1) - 持久化存储配置说明

## 更新日志

### v3.1.0 (2026-02-01)

- ✅ 添加完整备份和恢复脚本
- ✅ 添加自动启用网卡功能
- ✅ 修复容器重启后无法启动的问题
- ✅ 添加 ISP 背景颜色显示功能
- ✅ 修复登录页面 Tab 键焦点问题
- ✅ 添加"直拨"ISP模式（自由输入完整PPPoE账号）
- ✅ 容器配置自动重启策略

### v3.0.0 (2026-01-30)

- ✅ 实现正确的并发模型（"锁即资源"）
- ✅ 支持多种 VLAN ID 格式
- ✅ 添加超级管理员角色
- ✅ 优化并发拨号性能

## 许可证

本项目仅供学习和研究使用。

## 贡献

欢迎提交 Issue 和 Pull Request。

## 联系方式

如有问题，请提交 Issue。
