# models.py
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import sys
import os

# 确保能导入上级目录的 config.py
sys.path.append('/opt/pppoe-activation')
from config import DATABASE_PATH

# 使用你原有的数据库路径
engine = create_engine(f'sqlite:///{DATABASE_PATH}', echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ActivationLog(Base):
    __tablename__ = 'activation_logs'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50))
    role = Column(String(20))
    isp = Column(String(20))
    username = Column(String(100))
    success = Column(Boolean)
    ip = Column(String(20))
    mac = Column(String(20))
    error_code = Column(String(10))
    error_message = Column(String(200))
    timestamp = Column(String(30))


class NetworkConfig(Base):
    """网络配置表（运行时配置）"""
    __tablename__ = 'network_config'
    
    id = Column(Integer, primary_key=True, index=True)
    net_mode = Column(String(20), default='physical')  # physical | vlan
    base_interface = Column(String(20))  # enp3s0
    vlan_id = Column(String(100), nullable=True)  # 100 或 100,101,102（可为空）
    created_at = Column(String(30))  # 创建时间
    updated_at = Column(String(30))  # 更新时间
    
    def effective_interface(self) -> str:
        """
        计算 PPPoE 实际使用的接口名
        
        Returns:
            str: 最终接口名（如 enp3s0 或 enp3s0.100）
        """
        if self.net_mode == "vlan" and self.vlan_id:
            # 如果有多个 VLAN ID（逗号分隔），返回第一个
            vlan_ids = str(self.vlan_id).split(',')
            return f"{self.base_interface}.{vlan_ids[0]}"
        return self.base_interface
    
    def vlan_id_list(self) -> list:
        """
        获取 VLAN ID 列表
        
        Returns:
            list: VLAN ID 列表（例如：[100, 101, 102]）
        """
        if not self.vlan_id:
            return []
        
        # 解析 VLAN ID 字符串（支持逗号分隔）
        vlan_ids = []
        for part in str(self.vlan_id).split(','):
            part = part.strip()
            if part:
                try:
                    vlan_ids.append(int(part))
                except ValueError:
                    pass
        
        return vlan_ids


class Config(Base):
    """系统配置表"""
    __tablename__ = 'config'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)  # 配置项名称
    value = Column(String(500))  # 配置项值


class AdminUser(Base):
    """管理员用户表"""
    __tablename__ = 'admin_users'
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(64))  # SHA256
    salt = Column(String(120))  # salt字段
    role = Column(String(20), default='admin')  # admin 或 super
    created_at = Column(String(30))  # 创建时间


def init_db():
    """创建表（如果不存在）"""
    Base.metadata.create_all(bind=engine)
