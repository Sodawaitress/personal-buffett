#!/usr/bin/env python3
"""market-svc（US-138）：被动市场信息流 —— 宏观快照 + 国际新闻 + 重大新闻扫描。

接手旧 monolith 里没人认领的三件事：
- 宏观快照（汇率/指数/大宗/恐慌贪婪/FOMC/挖掘机）→ 写 market_data
  monolith 只把它放内存 dict 喂报告，从不落库；报告删了(US-124)之后就纯浪费。
  这里改成落库 —— 首页 market snapshot 和 feat_fear_greed 读的正是这张表。
- 国际新闻 + 摩根大通（Google News RSS）→ market_news
- 重大新闻扫描（US-118）→ 即 US-121 表里「待接」的 material-svc，并入这里不单开

全程 Google News RSS + 少量 AKShare 宏观接口，与个股抓取无依赖，挂了不影响价格/分析/推送。
"""
import os

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

from datetime import datetime

import db
from scripts.config import CN_TZ

MATERIAL_DAYS = int(os.environ.get("MATERIAL_SCAN_DAYS", "3"))
MATERIAL_MAX_MIN = float(os.environ.get("MATERIAL_MAX_MIN", "20"))


def _run_macro(date_str: str) -> int:
    from scripts.macro_fetch import fetch_all_macro

    macro = fetch_all_macro()
    macro = {k: v for k, v in macro.items() if v}
    if not macro:
        print("  ⚠️ 宏观数据全空，跳过写库")
        return 0
    db.upsert_market_snapshot(date_str, "global", macro)
    print(f"  ✅ 宏观快照 {len(macro)} 项入库：{', '.join(macro)}")
    return len(macro)


def _run_intl_news(date_str: str) -> int:
    from scripts.stock_fetch import fetch_international_news, fetch_jpmorganchase_news

    saved = 0
    for scope, items in (fetch_international_news() or {}).items():
        for n in items:
            db.upsert_intl_news(scope, n["title"], n.get("label", ""),
                                n.get("link", ""), n.get("source", ""), date_str)
            saved += 1

    for n in fetch_jpmorganchase_news() or []:
        db.upsert_intl_news("jpm_news", n["title"], "摩根大通",
                            n.get("link", ""), n.get("source", "摩根大通"), date_str)
        saved += 1

    print(f"  ✅ 国际新闻 {saved} 条入库")
    return saved


def _run_material_scan() -> int:
    from scripts.material_news_scan import run_material_scan_all

    with db.get_conn() as c:
        rows = c.execute(
            "SELECT DISTINCT stock_code FROM user_watchlist WHERE status != 'sold'"
        ).fetchall()
    codes = [r["stock_code"] for r in rows if r["stock_code"]]
    if not codes:
        print("  · 无自选股，跳过重大新闻扫描")
        return 0

    res = run_material_scan_all(codes, days=MATERIAL_DAYS, max_minutes=MATERIAL_MAX_MIN)
    print(f"  ✅ 重大新闻：存 {res['saved']} 条（{res['material']} 重大）")
    return res["saved"]



def _capture_industry_daily(svc_name):
    """US-158：留存今天的行业表现。**故意挂在 5 个每日服务上**。

    新浪没有历史接口，漏掉的一天永远补不回来，而这个系统有连续 14 天不跑的
    前科。捕获只要 1 次 HTTP 调用、(date, sector_label) 唯一键幂等，
    所以宁可 5 个服务各捕获一次，也不接受「漏一天就是永久的洞」。
    永不抛：它是搭车的，不能拖垮宿主服务。
    """
    try:
        from scripts.industry_signals import capture_daily
        res = capture_daily()
        if res.get("skipped"):
            print(f"  ⚠️ [{svc_name}] 行业日线捕获失败（其余服务会再试）")
        else:
            print(f"  🏭 [{svc_name}] 行业日线已留存 {res['captured']} 个行业")
    except Exception as e:
        print(f"  ⚠️ [{svc_name}] 行业日线捕获异常: {type(e).__name__}: {e}")


def main():
    db.init_db()  # 幂等，确保 service_runs 等表在 Neon 上存在
    date_str = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    print(f"🌍 market-svc 启动 {date_str}")

    # 三块彼此独立：任一挂了不拖累其余（US-121 分开失败铁律）
    steps = (("宏观快照", lambda: _run_macro(date_str)),
             ("国际新闻", lambda: _run_intl_news(date_str)),
             ("重大新闻扫描", _run_material_scan))

    failed = []
    with db.service_run("market-svc") as run:
        _capture_industry_daily("market-svc")
        for label, fn in steps:
            print(f"  ▶ {label}…")
            try:
                fn()
                run.tick()
            except Exception as e:
                failed.append(label)
                print(f"  ⚠️ {label}失败（不影响其余）: {e}")

        # 跑完再抛：其余两块已各自落库，但 service_runs 要如实记 failed + 告警要响
        if failed:
            raise RuntimeError(f"{'/'.join(failed)} 失败")

    print("✅ market-svc 完成")


if __name__ == "__main__":
    main()
