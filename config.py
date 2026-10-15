# PPPOE 激活系统配置文件
import os

# 自动生成于 Thu Sep 17 11:08:53 CST 2026

BASE_DIR = os.environ.get('PPPOE_BASE_DIR', '/opt/pppoe-activation')

# SQLite 数据库绝对路径（固定）
DATABASE_PATH = os.environ.get(
    'PPPOE_DATABASE_PATH',
    os.path.join(BASE_DIR, 'instance', 'database.db')
)

# 网卡配置（用户配置）
# 注意：NETWORK_INTERFACES 仅用于初始化默认值展示，不参与运行期逻辑
# 运行期网络配置请参考数据库中的 NetworkConfig 表
NETWORK_INTERFACES = ["ens64.2001", "ens64.2002", "ens64.2003", "ens64.2004", "ens64.2005"]

# 日志目录
PPP_LOG_DIR = os.environ.get('PPPOE_LOG_DIR', os.path.join(BASE_DIR, 'logs'))

# 服务端口配置
APP_PORT = int(os.environ.get('APP_PORT', '80'))
ADMIN_PORT = int(os.environ.get('ADMIN_PORT', '8081'))
