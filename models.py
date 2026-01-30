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
    vlan_id = Column(Integer, nullable=True)  # 100（可为空）
    created_at = Column(String(30))  # 创建时间
    updated_at = Column(String(30))  # 更新时间
    
    def effective_interface(self) -> str:
        """
        计算 PPPoE 实际使用的接口名
        
        Returns:
            str: 最终接口名（如 enp3s0 或 enp3s0.100）
        """
        if self.net_mode == "vlan" and self.vlan_id:
            return f"{self.base_interface}.{self.vlan_id}"
        return self.base_interface

def init_db():
    """创建表（如果不存在）"""
    Base.metadata.create_all(bind=engine)
