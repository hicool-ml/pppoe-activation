#!/usr/bin/env python3
# test_concurrent_2.py - 2线程并发测试脚本（针对VLAN子接口）
import requests
import time
import concurrent.futures

# 配置
BASE_URL = "http://127.0.0.1:80"
USERNAME = "W18608001027"
PASSWORD = "Cdu@1027"
ISP = "cdu"

def activate_account(request_id):
    """激活账号"""
    url = f"{BASE_URL}/activate"
    data = {
        "name": f"测试用户{request_id}",
        "role": "学生",
        "isp": ISP,
        "username": USERNAME,
        "password": PASSWORD
    }
    
    start_time = time.time()
    try:
        response = requests.post(url, json=data, timeout=10)
        elapsed_time = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            vlan_id = result.get("vlan_id")
            print(f"[请求 {request_id}] 成功 - VLAN ID: {vlan_id}, 耗时: {elapsed_time:.2f}秒")
            return True, vlan_id
        else:
            print(f"[请求 {request_id}] 失败 - HTTP {response.status_code}, 耗时: {elapsed_time:.2f}秒")
            return False, None
    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"[请求 {request_id}] 异常 - {e}, 耗时: {elapsed_time:.2f}秒")
        return False, None

def main():
    """主函数"""
    print(f"开始 2 并发测试（针对VLAN子接口）...")
    print(f"账号: {USERNAME}@{ISP}")
    print(f"密码: {PASSWORD}")
    print("-" * 60)
    
    # 进行多次测试，直到同时拨号成功
    test_count = 0
    max_tests = 10
    
    while test_count < max_tests:
        test_count += 1
        print(f"\n=== 测试 {test_count}/{max_tests} ===")
        
        # 使用 2 个并发请求
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(activate_account, i+1) for i in range(2)]
            
            # 等待所有请求完成
            results = []
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
        
        # 检查结果
        success_count = sum(1 for success, _ in results if success)
        vlan_ids = [vlan_id for _, vlan_id in results if vlan_id is not None]
        
        print(f"\n测试 {test_count} 结果：")
        print(f"成功数：{success_count}/2")
        print(f"VLAN ID：{vlan_ids}")
        
        # 如果两个请求都成功分配了不同的 VLAN，则测试成功
        if success_count == 2 and len(set(vlan_ids)) == 2:
            print(f"\n✅ 测试成功！2个请求同时拨号成功，分配了不同的VLAN：{vlan_ids}")
            break
        elif success_count == 2 and len(set(vlan_ids)) == 1:
            print(f"\n⚠️ 测试部分成功！2个请求都成功，但分配了相同的VLAN：{vlan_ids}")
        else:
            print(f"\n❌ 测试失败！只有{success_count}个请求成功")
    
    print("-" * 60)
    print(f"测试完成！")

if __name__ == "__main__":
    main()
