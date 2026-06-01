"""Route audit for US-99 — classifies every Flask endpoint as SSR / JSON API / mixed.

Run from project root:
    python3 scripts/audit_routes.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("FLASK_ENV", "development")

from dotenv import load_dotenv
load_dotenv()

from radar_app import create_app

app = create_app()

SSR_PREFIXES = ("/stock/", "/watchlist", "/report", "/settings", "/admin",
                "/brief", "/about", "/demo", "/login", "/register", "/logout",
                "/google", "/remove/", "/add", "/healthz")

API_PREFIX = "/api/"


def _classify(rule):
    path = rule.rule
    if path.startswith(API_PREFIX):
        return "JSON API"
    if any(path.startswith(p) for p in SSR_PREFIXES) or path == "/":
        return "HTML SSR"
    return "mixed"


rows = []
with app.app_context():
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if rule.rule.startswith("/static"):
            continue
        methods = sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS"))
        rows.append((_classify(rule), rule.rule, " ".join(methods), rule.endpoint))

# Print table
COL = (10, 50, 20, 30)
header = f"{'TYPE':<{COL[0]}} {'PATH':<{COL[1]}} {'METHODS':<{COL[2]}} ENDPOINT"
print(header)
print("-" * sum(COL))
for cls, path, methods, ep in rows:
    print(f"{cls:<{COL[0]}} {path:<{COL[1]}} {methods:<{COL[2]}} {ep}")

print()
counts = {"JSON API": 0, "HTML SSR": 0, "mixed": 0}
for cls, *_ in rows:
    counts[cls] += 1
for k, v in counts.items():
    print(f"  {k}: {v}")
