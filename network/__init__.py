"""
网络接口准备层
提供物理网卡和 VLAN 子接口的统一抽象
"""

from .interface import (
    iface_exists,
    create_vlan_iface,
    prepare_interface,
    delete_vlan_iface
)

__all__ = [
    'iface_exists',
    'create_vlan_iface',
    'prepare_interface',
    'delete_vlan_iface'
]
