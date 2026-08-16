#!/usr/bin/env python3
"""radar-svc（US-121）：机构雷达 + 前兆信号。A股专属，AKShare 密集。

从 DB 读价格/资金（fetch-svc 已写）建 quotes/fund_flow，喂给 run_institutional_radar；
其价值在内部前兆信号抓取的 DB 副作用（precursor 缓存/历史，详情页读它）。
独立服务：AKShare 挂了/慢了只影响雷达，不拖累价格/分析/推送。
"""
import sys

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

import os

import db
from scripts.institutional_radar import _cn_codes, run_institutional_radar

# 前兆信号逐只打东财，与别的东财消费者撞车会慢一倍 → 自带预算，别被 timeout 掐（US-139）
BUDGET_MIN = float(os.environ.get("RADAR_BUDGET_MIN", "70"))


def _build_market_data() -> dict:
    """从 DB 组出 run_institutional_radar 需要的 quotes / fund_flow（映射 change_pct→change）。"""
    quotes, fund_flow = {}, {}
    for code in _cn_codes():
        p = db.get_latest_price(code)
        if p:
            stock = db.get_stock(code) or {}
            quotes[code] = {
                "price": p.get("price"),
                "change": p.get("change_pct"),
                "name": stock.get("name", code),
            }
        ff = db.get_fund_flow(code)
        if ff:
            fund_flow[code] = ff
    return {"quotes": quotes, "fund_flow": fund_flow}



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
    data = _build_market_data()
    print(f"🏦 radar-svc 启动：{len(data['quotes'])} 只 A股，预算 {BUDGET_MIN} 分钟")
    with db.service_run("radar-svc") as run:
        _capture_industry_daily("radar-svc")
        section = run_institutional_radar(data, budget_min=BUDGET_MIN)
        run.tick()

        # 催化剂日历（US-138 归位）：解禁/公告同为 A股 AKShare 事件流，与雷达同源
        print("  📅 催化剂日历…")
        try:
            from scripts.catalyst_calendar import run_catalyst_refresh

            cal = run_catalyst_refresh()
            print(f"  ✅ 催化剂：解禁 {cal.get('unlock', 0)} 条 / 公告 {cal.get('notice', 0)} 条")
            run.tick()
        except Exception as e:
            print(f"  ⚠️ 催化剂日历失败（不影响雷达）: {e}")

    print(f"✅ radar-svc 完成，雷达片段 {len(section or '')} 字符（前兆信号已写 DB）")


if __name__ == "__main__":
    main()
