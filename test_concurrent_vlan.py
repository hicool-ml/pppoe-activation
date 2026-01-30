#!/usr/bin/env python3
"""
并发拨号测试脚本
测试多个VLAN子接口的并发拨号功能
"""

import requests
import threading
import time
from datetime import datetime

# 配置
BASE_URL = "http://192.168.0.112:80"
USERNAME = "18608001027"
PASSWORD = "Cdu@1027"
ISP = "cdu"
NUM_REQUESTS = 50  # 并发请求数（50并发压力测试）

# 结果存储
results = []
lock = threading.Lock()

def activate_account(index):
    """执行单次激活"""
    try:
        start_time = time.time()
        
        payload = {
            "name": f"测试用户{index}",
            "role": "student",
            "isp": ISP,
            "username": USERNAME,
            "password": PASSWORD
        }
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 线程 {index}: 开始拨号...")
        
        response = requests.post(
            f"{BASE_URL}/activate",
            json=payload,
            timeout=30
        )
        
        elapsed_time = time.time() - start_time
        result = response.json()
        
        # 记录结果
        with lock:
            results.append({
                "thread": index,
                "success": result.get("success", False),
                "error_code": result.get("error_code"),
                "error_message": result.get("error_message"),
                "iface": result.get("iface"),
                "ip": result.get("ip"),
                "mac": result.get("mac"),
                "elapsed_time": elapsed_time,
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        
        if result.get("success"):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 线程 {index}: ✅ 成功! 接口={result.get('iface')}, IP={result.get('ip')}, 耗时={elapsed_time:.2f}s")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 线程 {index}: ❌ 失败! 错误码={result.get('error_code')}, 错误信息={result.get('error_message')}, 耗时={elapsed_time:.2f}s")
        
        return result
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        error_msg = str(e)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 线程 {index}: ⚠️ 异常! {error_msg}, 耗时={elapsed_time:.2f}s")
        
        with lock:
            results.append({
                "thread": index,
                "success": False,
                "error_code": "EXCEPTION",
                "error_message": error_msg,
                "iface": None,
                "ip": None,
                "mac": None,
                "elapsed_time": elapsed_time,
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return None

def main():
    print("=" * 60)
    print("PPPoE 并发拨号测试")
    print("=" * 60)
    print(f"目标URL: {BASE_URL}")
    print(f"账号: {USERNAME}@{ISP}")
    print(f"并发数: {NUM_REQUESTS}")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    # 创建线程
    threads = []
    
    # 启动并发测试
    start_time = time.time()
    
    for i in range(NUM_REQUESTS):
        thread = threading.Thread(target=activate_account, args=(i+1,))
        threads.append(thread)
        thread.start()
        # 移除延迟，实现真正的并发启动
    
    # 等待所有线程完成
    for thread in threads:
        thread.join()
    
    total_time = time.time() - start_time
    
    # 统计结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count
    
    print(f"总请求数: {len(results)}")
    print(f"成功数: {success_count}")
    print(f"失败数: {fail_count}")
    print(f"成功率: {success_count/len(results)*100:.1f}%")
    print(f"总耗时: {total_time:.2f}s")
    
    if success_count > 0:
        success_results = [r for r in results if r["success"]]
        avg_time = sum(r["elapsed_time"] for r in success_results) / len(success_results)
        print(f"平均耗时: {avg_time:.2f}s")
    
    # 显示详细结果
    print("\n" + "-" * 60)
    print("详细结果:")
    print("-" * 60)
    
    for r in results:
        status = "✅ 成功" if r["success"] else "❌ 失败"
        print(f"线程 {r['thread']}: {status}")
        print(f"  接口: {r.get('iface', 'N/A')}")
        print(f"  IP: {r.get('ip', 'N/A')}")
        print(f"  MAC: {r.get('mac', 'N/A')}")
        print(f"  耗时: {r['elapsed_time']:.2f}s")
        if not r["success"]:
            print(f"  错误码: {r.get('error_code', 'N/A')}")
            print(f"  错误信息: {r.get('error_message', 'N/A')}")
        print()
    
    # 接口分布统计
    print("=" * 60)
    print("接口分布统计:")
    print("=" * 60)
    
    iface_stats = {}
    for r in results:
        iface = r.get('iface', 'unknown')
        if iface not in iface_stats:
            iface_stats[iface] = {"success": 0, "fail": 0}
        if r["success"]:
            iface_stats[iface]["success"] += 1
        else:
            iface_stats[iface]["fail"] += 1
    
    for iface, stats in iface_stats.items():
        total = stats["success"] + stats["fail"]
        print(f"{iface}: 成功={stats['success']}, 失败={stats['fail']}, 总计={total}")

if __name__ == "__main__":
    main()
