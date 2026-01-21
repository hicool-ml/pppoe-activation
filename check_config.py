#!/usr/bin/env python3
import sys
sys.path.insert(0, '/opt/pppoe-activation')

from dashboard import Config, db, app

with app.app_context():
    configs = Config.query.all()
    print(f'配置数量: {len(configs)}')
    for c in configs:
        print(f'{c.name}: {c.value}')
