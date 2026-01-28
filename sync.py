# /opt/pppoe-activation/sync.py
import json
import os
from datetime import datetime
from models import SessionLocal, ActivationLog, init_db
from config import BASE_DIR

SOURCE_LOG_FILE = f'{BASE_DIR}/activation_log.jsonl'

def sync_logs(latest_only=False):
    """
    同步日志到数据库。
    注意：为兼容 dashboard.py 调用，保留 latest_only 参数，但实际忽略它。
    始终全量读取日志文件，并通过 (username, timestamp) 去重。
    """
    print(f"🔄 开始同步日志: {SOURCE_LOG_FILE} (latest_only={latest_only}, 实际忽略)")

    if not os.path.exists(SOURCE_LOG_FILE):
        print("📭 日志文件不存在")
        return

    init_db()
    session = SessionLocal()
    try:
        existing = set(session.query(ActivationLog.username, ActivationLog.timestamp).all())
        added = 0

        with open(SOURCE_LOG_FILE, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    supported_fields = {
                        'name', 'role', 'isp', 'username', 'success',
                        'ip', 'mac', 'error_code', 'error_message', 'timestamp'
                    }
                    clean_data = {k: data.get(k) for k in supported_fields}

                    if clean_data['timestamp'] is None:
                        clean_data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    if clean_data['name'] is None:
                        clean_data['name'] = '未知用户'
                    if clean_data['role'] is None:
                        clean_data['role'] = '未知'
                    if clean_data['isp'] is None:
                        clean_data['isp'] = 'unknown'
                    if clean_data['success'] is None:
                        clean_data['success'] = False
                    if clean_data['error_code'] is None:
                        clean_data['error_code'] = '999'
                    if clean_data['error_message'] is None:
                        clean_data['error_message'] = '日志格式不完整'

                    key = (clean_data['username'], clean_data['timestamp'])
                    if key not in existing:
                        log = ActivationLog(**clean_data)
                        session.add(log)
                        existing.add(key)
                        added += 1

                except Exception as e:
                    print(f"⚠️ 第 {line_num} 行解析失败: {e}")
                    continue

        session.commit()
        print(f"✅ 同步完成，新增 {added} 条记录")

    except Exception as e:
        print(f"❌ 同步失败: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == '__main__':
    sync_logs()
