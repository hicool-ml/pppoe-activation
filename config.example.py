# PPPOE 激活系统配置文件示例
# 复制此文件为 config.py 并根据实际情况修改

BASE_DIR = '/opt/pppoe-activation'

# SQLite 数据库绝对路径（固定）
# 使用 /app/instance 目录，该目录已挂载到宿主机
DATABASE_PATH = '/app/instance/database.db'

# 网卡配置
# 根据实际硬件设备修改网卡名称
# 常见网卡命名规则：
# - 传统命名：eth0, eth1, eth2, eth3
# - 一致性命名：enp3s0, enp4s0, enp5s0, enp6s0, enp7s0
# - USB网卡：enx开头的MAC地址
# 查看网卡命令：ip link show 或 ifconfig
NETWORK_INTERFACES = ['eth0', 'eth1', 'eth2', 'eth3']

# 日志目录
PPP_LOG_DIR = f'{BASE_DIR}/logs'
