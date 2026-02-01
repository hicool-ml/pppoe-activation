#!/usr/bin/env python3
"""检查数据库中的网络配置"""
import sys
sys.path.insert(0, '/opt/pppoe-activation')

from sqlalchemy import create_engine, text
import os

DATABASE_PATH = '/opt/pppoe-activation/data/database.db'
engine = create_engine(f'sqlite:///{DATABASE_PATH}')

with engine.connect() as conn:
    # 查看所有表
    result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    tables = [row[0] for row in result]
    print("数据库中的表:", tables)
    
    # 查询配置表
    if 'config' in tables:
        result = conn.execute(text("SELECT * FROM config"))
        print("\nConfig表内容:")
        for row in result:
            print(f"  {dict(row._asdict())}")
    
    if 'network_config' in tables:
        result = conn.execute(text("SELECT * FROM network_config"))
        print("\nNetwork_config表内容:")
        for row in result:
            data = dict(row._asdict())
            print(f"  id: {data.get('id')}")
            print(f"  net_mode: {data.get('net_mode')}")
            print(f"  base_interface: {data.get('base_interface')}")
            print(f"  vlan_id: {data.get('vlan_id')}")
            
            # 解析 VLAN ID 列表
            vlan_id_str = data.get('vlan_id', '')
            if vlan_id_str:
                vlan_ids = [int(x.strip()) for x in vlan_id_str.split(',') if x.strip().isdigit()]
                print(f"  解析后的VLAN IDs: {vlan_ids}")
                print(f"  VLAN数量: {len(vlan_ids)}")
                
                # 生成接口列表
                base_iface = data.get('base_interface', '')
                if base_iface:
                    interfaces = [f'{base_iface}.{vid}' for vid in vlan_ids]
                    print(f"  生成的接口列表: {interfaces}")
