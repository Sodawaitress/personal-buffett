import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
workers = 1
threads = 8  # 留余量：别让几个慢请求就把 /healthz 也饿死（2026-11-20 事故）
timeout = 180
graceful_timeout = 300  # let background pipeline threads finish before forced shutdown
