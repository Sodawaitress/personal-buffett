"""
GitHub Actions 冷启动脚本。
仅在 DB 无用户时执行：创建默认推送用户，并从 config.WATCHLIST 导入自选股。

使用方式（workflow 里传环境变量）：
  BOOTSTRAP_USER_EMAIL   推送用户 email（默认 pipeline@radar.local）
  BOOTSTRAP_WECOM_KEY    该用户的 Server酱 sendkey（默认取 SERVERCHAN_KEY）
"""

import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
try:
    from scripts._bootstrap import bootstrap_paths
    bootstrap_paths()
except Exception:
    pass

import db
from scripts.config import WATCHLIST, HK_WATCHLIST

db.init_db()

with db.get_conn() as c:
    count = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if count > 0:
        print(f"DB already has {count} user(s) — skipping bootstrap")
        sys.exit(0)

email   = os.environ.get("BOOTSTRAP_USER_EMAIL", "pipeline@radar.local")
webhook = os.environ.get("BOOTSTRAP_WECOM_KEY") or os.environ.get("SERVERCHAN_KEY", "")

print(f"Bootstrapping DB: user={email}, webhook={'set' if webhook else 'empty'}")

with db.get_conn() as c:
    row = c.execute(
        "INSERT INTO users(email, display_name, role) VALUES(:email,'日报用户','member') RETURNING id",
        {"email": email},
    ).fetchone()
    user_id = row["id"]
    c.execute(
        "INSERT INTO user_push_settings(user_id, notify_daily, wecom_webhook) VALUES(:uid,1,:wh)",
        {"uid": user_id, "wh": webhook},
    )

for name, code, _ in WATCHLIST:
    db.add_user_stock(user_id, code, name, "cn")
    print(f"  + {name} ({code}) [cn]")

for name, code, _ in HK_WATCHLIST:
    db.add_user_stock(user_id, code, name, "hk")
    print(f"  + {name} ({code}) [hk]")

print(f"Bootstrap complete: user_id={user_id}, "
      f"{len(WATCHLIST)} A股 + {len(HK_WATCHLIST)} 港股")
