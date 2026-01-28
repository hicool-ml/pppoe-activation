# PPPOE 激活系统配置文件
# 自动生成于 Tue Jan 20 07:31:12 CST 2026

BASE_DIR = '/opt/pppoe-activation'

# SQLite 数据库绝对路径（固定）
DATABASE_PATH = '/opt/pppoe-activation/instance/database.db'

# 网卡配置（用户配置）
NETWORK_INTERFACES = ["enp3s0", "enp4s0", "enp5s0", "enp6s0"]

# 日志目录
PPP_LOG_DIR = f'{BASE_DIR}/logs'

# 服务端口配置
APP_PORT = 80
ADMIN_PORT = 8081
