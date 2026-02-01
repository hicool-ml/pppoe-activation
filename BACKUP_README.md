# PPPOE 激活系统备份和恢复指南

## 概述

本指南说明如何使用备份和恢复脚本来保护您的 PPPOE 激活系统数据和配置。

## 备份脚本

### 功能

备份脚本会创建以下内容的完整备份：

1. **源代码** - 所有 Python 文件、配置文件、模板等
2. **数据库** - 管理员账号、网络配置、激活日志
3. **日志文件** - 所有拨号日志
4. **运行时数据** - data/ 目录（如果有）
5. **Docker 镜像** - 完整的容器镜像
6. **环境配置** - .env 文件

### 使用方法

```bash
# 在项目目录下运行
./backup.sh
```

### 备份输出

备份脚本会创建一个带时间戳的备份目录：

```
/tmp/pppoe-backup-20260201_120000/
├── pppoe-activation-source.tar.gz      # 源代码
├── pppoe-activation-database.tar.gz     # 数据库
├── pppoe-activation-logs.tar.gz         # 日志
├── pppoe-activation-data.tar.gz         # 运行时数据
├── pppoe-activation-image.tar           # Docker镜像
├── .env.backup                          # 环境配置
└── backup-manifest.txt                  # 备份清单
```

### 可选：创建单个压缩包

脚本运行后会询问是否创建单个压缩包：

```bash
是否创建单个压缩包？(y/n) y
```

选择 `y` 会创建：

```
/tmp/pppoe-backup-20260201_120000.tar.gz
```

这个压缩包包含所有备份文件，便于传输和存储。

## 恢复脚本

### 功能

恢复脚本会从备份目录恢复所有内容，并自动启动容器。

### 使用方法

```bash
# 方法1：从备份目录恢复
./restore.sh /tmp/pppoe-backup-20260201_120000

# 方法2：从压缩包恢复
# 先解压
cd /tmp
tar -xzf pppoe-backup-20260201_120000.tar.gz
# 然后恢复
./restore.sh /tmp/pppoe-backup-20260201_120000
```

### 恢复过程

恢复脚本会执行以下操作：

1. 停止并删除旧容器
2. 恢复源代码
3. 恢复数据库
4. 恢复日志
5. 恢复运行时数据
6. 恢复 Docker 镜像
7. 恢复环境配置
8. 启动新容器

### 安全确认

恢复脚本会要求您确认操作：

```
警告：此操作将覆盖当前目录中的文件！
是否继续？(yes/no) 
```

输入 `yes` 才会继续恢复。

## 完整备份和恢复流程

### 场景1：日常备份

```bash
# 1. 运行备份脚本
./backup.sh

# 2. 选择创建压缩包
是否创建单个压缩包？(y/n) y

# 3. 将压缩包复制到安全位置
cp /tmp/pppoe-backup-20260201_120000.tar.gz /path/to/backup/
```

### 场景2：系统故障恢复

```bash
# 1. 解压备份包
cd /tmp
tar -xzf pppoe-backup-20260201_120000.tar.gz

# 2. 运行恢复脚本
cd /home/cdu/pppoe_Activation
./restore.sh /tmp/pppoe-backup-20260201_120000

# 3. 等待容器启动
# 4. 访问系统验证
```

### 场景3：迁移到新服务器

```bash
# 在旧服务器上：
./backup.sh
# 选择创建压缩包

# 将压缩包传输到新服务器
scp /tmp/pppoe-backup-20260201_120000.tar.gz user@new-server:/tmp/

# 在新服务器上：
cd /tmp
tar -xzf pppoe-backup-20260201_120000.tar.gz
mkdir -p /home/cdu/pppoe_Activation
cd /home/cdu/pppoe_Activation
../restore.sh /tmp/pppoe-backup-20260201_120000
```

## 备份策略建议

### 定期备份

建议每天运行一次备份脚本：

```bash
# 添加到 crontab
0 2 * * * cd /home/cdu/pppoe_Activation && ./backup.sh
```

### 备份保留

建议保留最近7天的备份：

```bash
# 清理旧备份（保留最近7天）
find /tmp -name "pppoe-backup-*" -type d -mtime +7 -exec rm -rf {} \;
find /tmp -name "pppoe-backup-*.tar.gz" -mtime +7 -delete
```

### 异地备份

建议将备份复制到异地存储：

```bash
# 复制到 NAS
cp /tmp/pppoe-backup-20260201_120000.tar.gz /path/to/nas/

# 或使用 rsync
rsync -avz /tmp/pppoe-backup-20260201_120000.tar.gz user@backup-server:/path/to/backup/
```

## 故障排除

### 备份失败

如果备份脚本失败，请检查：

1. 磁盘空间是否充足
2. Docker 镜像是否存在
3. 文件权限是否正确

### 恢复失败

如果恢复脚本失败，请检查：

1. 备份文件是否完整
2. Docker 服务是否运行
3. 端口是否被占用

### 容器无法启动

如果容器恢复后无法启动，请查看日志：

```bash
docker logs pppoe-activation
```

## 注意事项

1. **备份前停止重要操作**：备份时最好停止正在进行的拨号操作
2. **定期测试恢复**：定期测试恢复流程确保备份可用
3. **保护备份文件**：备份包含敏感信息，请妥善保管
4. **监控磁盘空间**：备份会占用大量磁盘空间，请定期清理

## 联系支持

如果遇到问题，请查看备份清单文件：

```bash
cat /tmp/pppoe-backup-20260201_120000/backup-manifest.txt
```
