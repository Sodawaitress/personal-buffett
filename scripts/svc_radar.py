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

import db
from scripts.institutional_radar import _cn_codes, run_institutional_radar


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


def main():
    data = _build_market_data()
    print(f"🏦 radar-svc 启动：{len(data['quotes'])} 只 A股")
    with db.service_run("radar-svc") as run:
        section = run_institutional_radar(data)
        run.tick()
    print(f"✅ radar-svc 完成，雷达片段 {len(section or '')} 字符（前兆信号已写 DB）")


if __name__ == "__main__":
    main()
