#!/usr/bin/env python3
"""
私人巴菲特 · 管理员命令行工具
用法：python3 admin.py <command> [args]

Commands:
  users                                 列出所有用户
  watchlist <email>                     查看某用户全部自选股
  set <email> <code> <status> [opts]    设置持有状态
      status: holding | watching | sold
      --price <float>   买入/卖出价格
      --date  <YYYY-MM-DD>  买入/卖出日期
  add <email> <code> [name]             添加股票到 watching
  remove <email> <code>                 从自选股移除
  notify <email> on|off                 开关每日推送
  push-key <email> <serverchan_key>     设置 Server酱 推送 key
  test-push <email>                     发送测试消息验证 Server酱 key
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import argparse
import db

# ── 工具函数 ──────────────────────────────────────────

def _get_user_or_die(email: str):
    u = db.get_user_by_email(email)
    if not u:
        print(f"❌ 用户不存在: {email}")
        sys.exit(1)
    return u

def _fmt_row(items: list, widths: list) -> str:
    return "  ".join(str(v)[:w].ljust(w) for v, w in zip(items, widths))

def _print_table(headers, widths, rows):
    print(_fmt_row(headers, widths))
    print(_fmt_row(["─" * w for w in widths], widths))
    for row in rows:
        print(_fmt_row(row, widths))

# ── 命令实现 ──────────────────────────────────────────

def cmd_users():
    users = db.list_users()
    if not users:
        print("（暂无用户）")
        return
    headers = ["ID", "邮箱", "昵称", "角色", "注册时间"]
    widths  = [4, 36, 16, 8, 19]
    rows = [
        [u["id"], u["email"], u.get("display_name","—"),
         u.get("role","—"), (u.get("created_at","")[:19])]
        for u in users
    ]
    _print_table(headers, widths, rows)
    print(f"\n共 {len(users)} 名用户")


def cmd_watchlist(email: str):
    u  = _get_user_or_die(email)
    wl = db.get_user_watchlist(u["id"])
    if not wl:
        print(f"（{email} 自选股为空）")
        return

    print(f"\n用户：{email} （{u.get('display_name','')}) — {len(wl)} 只股票\n")
    headers = ["代码", "名称", "市场", "状态", "买入价", "买入日期", "备注"]
    widths  = [10, 14, 4, 8, 8, 12, 20]
    rows = [
        [w["stock_code"],
         w.get("name_cn") or w.get("name","—"),
         w.get("market","—"),
         w.get("status","—"),
         f"¥{w['buy_price']:.2f}" if w.get("buy_price") else "—",
         w.get("buy_date","—") or "—",
         w.get("notes","") or ""]
        for w in wl
    ]
    _print_table(headers, widths, rows)

    # 推送设置
    ps = db.get_push_settings(u["id"])
    if ps:
        nd = "开" if ps.get("notify_daily") else "关"
        key = ps.get("wecom_webhook","")
        key_disp = (key[:8]+"…") if key else "（未设置）"
        print(f"\n每日推送：{nd}  Server酱 key：{key_disp}")


def cmd_set(email: str, code: str, status: str,
            price: float = None, date: str = None):
    u = _get_user_or_die(email)
    wl = db.get_user_watchlist(u["id"])
    codes = [w["stock_code"] for w in wl]
    if code not in codes:
        print(f"❌ {code} 不在 {email} 的自选股中")
        sys.exit(1)

    if status not in ("holding", "watching", "sold"):
        print("❌ status 必须是 holding / watching / sold")
        sys.exit(1)

    buy_price = sell_price = None
    buy_date  = sell_date  = None
    if status == "holding":
        buy_price = price
        buy_date  = date
    elif status == "sold":
        sell_price = price
        sell_date  = date

    print(f"→ 将 {code} 状态设为 [{status}]", end="")
    if price: print(f"  价格 {price}", end="")
    if date:  print(f"  日期 {date}", end="")
    print()

    db.set_stock_status(u["id"], code, status,
                        buy_price=buy_price, buy_date=buy_date,
                        sell_price=sell_price, sell_date=sell_date)
    print(f"✅ 已更新")


def cmd_add(email: str, code: str, name: str = None):
    u = _get_user_or_die(email)
    import re
    def detect_market(c):
        if c.endswith(".KS"): return "kr"
        if c.endswith(".NZ"): return "nz"
        if c.endswith(".HK"): return "hk"
        if re.match(r"^\d{5}$", c): return "hk"
        if re.match(r"^\d{6}$", c): return "cn"
        return "us"

    market = detect_market(code)
    display_name = name or code
    print(f"→ 添加 {code}（{display_name}）到 {email} 的自选股...")
    db.add_user_stock(u["id"], code, display_name, market)
    print(f"✅ 已添加（status=watching）")


def cmd_remove(email: str, code: str):
    u = _get_user_or_die(email)
    print(f"→ 从 {email} 自选股移除 {code}...")
    db.remove_user_stock(u["id"], code)
    print(f"✅ 已移除")


def cmd_notify(email: str, onoff: str):
    u = _get_user_or_die(email)
    enabled = 1 if onoff.lower() in ("on", "1", "yes", "true", "开") else 0
    db.upsert_push_settings(u["id"], notify_daily=enabled)
    state = "开启" if enabled else "关闭"
    print(f"✅ {email} 每日推送已{state}")


def cmd_push_key(email: str, key: str):
    u = _get_user_or_die(email)
    db.upsert_push_settings(u["id"], wecom_webhook=key)
    masked = key[:8] + "…" if len(key) > 8 else key
    print(f"✅ {email} Server酱 key 已设置为 {masked}")


def cmd_test_push(email: str):
    u = _get_user_or_die(email)
    ps = db.get_push_settings(u["id"])
    key = (ps or {}).get("wecom_webhook", "")
    if not key:
        print(f"❌ {email} 未设置 Server酱 key，请先运行：python3 admin.py push-key {email} <key>")
        sys.exit(1)

    import ssl, json, urllib.request
    title = "私人巴菲特 · 测试推送"
    desp  = f"✅ 推送配置正常\n\n用户：{email}\n时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    payload = json.dumps({"title": title, "desp": desp}).encode()
    url = f"https://sctapi.ftqq.com/{key}.send"
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            resp = json.loads(r.read().decode())
            errno = resp.get("data", {}).get("errno", resp.get("code", -1))
            if errno == 0:
                print(f"✅ 测试消息已发送到微信，请查收")
            else:
                print(f"⚠️ Server酱 返回: {resp}")
    except Exception as e:
        print(f"❌ 发送失败: {e}")


# ── 主入口 ────────────────────────────────────────────

def main():
    db.init_db()

    parser = argparse.ArgumentParser(
        description="私人巴菲特 · 管理员工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("users", help="列出所有用户")

    p_wl = sub.add_parser("watchlist", help="查看用户自选股")
    p_wl.add_argument("email")

    p_set = sub.add_parser("set", help="设置股票状态")
    p_set.add_argument("email")
    p_set.add_argument("code")
    p_set.add_argument("status", choices=["holding","watching","sold"])
    p_set.add_argument("--price", type=float, default=None)
    p_set.add_argument("--date",  type=str,   default=None)

    p_add = sub.add_parser("add", help="添加股票")
    p_add.add_argument("email")
    p_add.add_argument("code")
    p_add.add_argument("name", nargs="?", default=None)

    p_rm = sub.add_parser("remove", help="移除股票")
    p_rm.add_argument("email")
    p_rm.add_argument("code")

    p_nt = sub.add_parser("notify", help="开关每日推送")
    p_nt.add_argument("email")
    p_nt.add_argument("onoff", choices=["on","off","开","关","1","0"])

    p_pk = sub.add_parser("push-key", help="设置 Server酱 key")
    p_pk.add_argument("email")
    p_pk.add_argument("key")

    p_tp = sub.add_parser("test-push", help="发送测试消息验证 Server酱 key")
    p_tp.add_argument("email")

    args = parser.parse_args()

    if args.cmd == "users":
        cmd_users()
    elif args.cmd == "watchlist":
        cmd_watchlist(args.email)
    elif args.cmd == "set":
        cmd_set(args.email, args.code, args.status,
                price=args.price, date=args.date)
    elif args.cmd == "add":
        cmd_add(args.email, args.code, args.name)
    elif args.cmd == "remove":
        cmd_remove(args.email, args.code)
    elif args.cmd == "notify":
        cmd_notify(args.email, args.onoff)
    elif args.cmd == "push-key":
        cmd_push_key(args.email, args.key)
    elif args.cmd == "test-push":
        cmd_test_push(args.email)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
