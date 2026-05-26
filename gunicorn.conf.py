import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
workers = 1
threads = 4
timeout = 180
graceful_timeout = 300  # let background pipeline threads finish before forced shutdown
