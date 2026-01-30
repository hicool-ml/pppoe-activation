"""
网络接口准备层
提供物理网卡和 VLAN 子接口的统一抽象
"""

import subprocess
import logging

logger = logging.getLogger(__name__)


def iface_exists(ifname: str) -> bool:
    """
    检查网络接口是否存在
    
    Args:
        ifname: 接口名称（如 enp3s0, enp3s0.100）
    
    Returns:
        bool: 接口是否存在
    """
    try:
        result = subprocess.run(
            ["ip", "link", "show", ifname],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"检查接口 {ifname} 失败: {e}")
        return False


def create_vlan_iface(base: str, vlan_id: int) -> str:
    """
    创建 VLAN 子接口
    
    Args:
        base: 基础接口名称（如 enp3s0）
        vlan_id: VLAN ID（如 100）
    
    Returns:
        str: VLAN 接口名称（如 enp3s0.100）
    """
    vlan_if = f"{base}.{vlan_id}"
    
    # 如果接口已存在，直接返回
    if iface_exists(vlan_if):
        logger.info(f"VLAN 接口 {vlan_if} 已存在，跳过创建")
        return vlan_if
    
    try:
        # 创建 VLAN 接口
        subprocess.check_call(
            ["ip", "link", "add", "link", base, "name", vlan_if, "type", "vlan", "id", str(vlan_id)]
        )
        logger.info(f"成功创建 VLAN 接口: {vlan_if}")
        
        # 启用接口
        subprocess.check_call(
            ["ip", "link", "set", vlan_if, "up"]
        )
        logger.info(f"成功启用 VLAN 接口: {vlan_if}")
        
        return vlan_if
    except subprocess.CalledProcessError as e:
        logger.error(f"创建 VLAN 接口 {vlan_if} 失败: {e}")
        raise


def delete_vlan_iface(vlan_if: str) -> bool:
    """
    删除 VLAN 子接口
    
    Args:
        vlan_if: VLAN 接口名称（如 enp3s0.100）
    
    Returns:
        bool: 是否成功删除
    """
    try:
        if iface_exists(vlan_if):
            subprocess.check_call(
                ["ip", "link", "delete", vlan_if]
            )
            logger.info(f"成功删除 VLAN 接口: {vlan_if}")
            return True
        else:
            logger.warning(f"VLAN 接口 {vlan_if} 不存在，跳过删除")
            return False
    except subprocess.CalledProcessError as e:
        logger.error(f"删除 VLAN 接口 {vlan_if} 失败: {e}")
        return False


def prepare_interface(net_mode: str, base_interface: str, vlan_id: int = None) -> str:
    """
    准备网络接口（物理或VLAN）
    
    Args:
        net_mode: 网络模式（physical | vlan）
        base_interface: 基础接口名称
        vlan_id: VLAN ID（仅 vlan 模式使用）
    
    Returns:
        str: 准备好的接口名称
    
    Raises:
        ValueError: 未知网络模式或缺少必要参数
    """
    if net_mode == "physical":
        logger.info(f"使用物理接口模式: {base_interface}")
        return base_interface
    
    if net_mode == "vlan":
        if not vlan_id:
            raise ValueError("VLAN 模式下必须指定 VLAN ID")
        logger.info(f"使用 VLAN 模式: {base_interface}.{vlan_id}")
        return create_vlan_iface(base_interface, vlan_id)
    
    raise ValueError(f"未知的网络模式: {net_mode}")
