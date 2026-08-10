#!/usr/bin/env python3
"""fetch-svc（US-121）：只抓数据，不跑 LLM。

遍历全部自选股，逐只跑 1a–1c3 抓取层（复用 run_fetch_layers），写入 DB。
带时间预算：超 FETCH_BUDGET_MIN 分钟即停，剩余下次续（已抓的靠缓存新鲜度快速跳过）。
整轮用 service_run 记账，失败/提前停都留痕。

独立于 analyze-svc：本服务挂了不影响已有分析/推送；本服务成功则价格永远新鲜。
"""
import os
import sys
import time

try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

import db
from scripts.pipeline_jobs import run_fetch_layers

BUDGET_MIN = float(os.environ.get("FETCH_BUDGET_MIN", "40"))
# 默认尊重缓存 TTL：财务 7 天 / 技术面 24h 直接跳过，同日已抓的新闻·资金也跳过，
# 让预算内多轮续跑真正靠缓存变快。整库重建时设 FORCE_FETCH=1 强制全量重抓。
FORCE = os.environ.get("FORCE_FETCH", "0") == "1"
# 每只之间温柔停顿，避免对东财突发请求触发海外封 IP（US-122，prior art 反面教训）。
GAP_SEC = float(os.environ.get("FETCH_GAP_SEC", "1.5"))


def _yahoo_symbol(code: str, market: str) -> str:
    """A股 → 6位.SS/.SZ；其余市场 code 本身就是 yahoo 代码（NVDA / 0700.HK / CYM.NZ）。"""
    if market != "cn":
        return code
    pure = code.split(".")[0]
    return f"{pure}.{'SS' if pure.startswith(('5', '6', '9')) else 'SZ'}"


def _bulk_prices(codes: list) -> int:
    """批量刷当日价格（US-140）——逐只 1a 层每只 ~30s，208 只根本跑不完一轮，
    当日价格覆盖率只有 38%，把 daily_digest 的 50% 熔断卡死 → 快照冻了 14 天。

    价格是唯一「全量覆盖」才有意义的数据（快照/熔断按覆盖率判断），所以单独
    拎出来走批量接口：A股一次新浪请求拿全部，其余市场一次 yfinance 批量下载。
    深度层（财务/技术面/资金）仍按预算逐只轮转，不变。
    """
    by_market = {}
    for code in codes:
        stock = db.get_stock(code)
        if stock:
            by_market.setdefault(stock.get("market", "nz"), []).append(code)

    saved = 0

    # ── A股：一次新浪批量（云端整批失败时 fetch_quotes 内部会退 yfinance）──
    cn = by_market.get("cn", [])
    if cn:
        from scripts.stock_fetch import fetch_quotes

        try:
            quotes = fetch_quotes([(db.get_stock(c).get("name", c), c) for c in cn])
            for code, q in quotes.items():
                if q.get("price"):
                    db.upsert_price(code, q["price"], change_pct=q.get("change"),
                                    volume=q.get("amount"))
                    saved += 1
            print(f"  ✅ A股批量行情：{saved}/{len(cn)} 只")
        except Exception as e:
            print(f"  ⚠️ A股批量行情失败: {e}")

    # ── 其余市场：一次 yfinance 批量下载（美/港/NZ/澳/韩）──
    intl = [(c, m) for m, lst in by_market.items() if m != "cn" for c in lst]
    if intl:
        try:
            import yfinance as yf

            sym_map = {_yahoo_symbol(c, m): c for c, m in intl}
            df = yf.download(list(sym_map), period="5d", group_by="ticker",
                             progress=False, threads=True, auto_adjust=True)
            ok = 0
            for sym, code in sym_map.items():
                try:
                    hist = df[sym].dropna(subset=["Close"]) if len(sym_map) > 1 else df.dropna(subset=["Close"])
                    if not len(hist):
                        continue
                    price = round(float(hist.iloc[-1]["Close"]), 2)
                    prev = round(float(hist.iloc[-2]["Close"]), 2) if len(hist) >= 2 else None
                    chg = round((price - prev) / prev * 100, 2) if prev else None
                    db.upsert_price(code, price, change_pct=chg)
                    ok += 1
                except Exception:
                    continue
            saved += ok
            print(f"  ✅ 海外批量行情：{ok}/{len(intl)} 只")
        except Exception as e:
            print(f"  ⚠️ 海外批量行情失败: {e}")

    return saved


def main():
    db.init_db()  # 幂等，确保 service_runs 等表在 Neon 上存在
    codes = db.fetch_priority_codes()  # 持仓→观察→已卖出，同级按 staleness 轮转（US-122）
    mode = "全量强抓" if FORCE else "缓存优先(续跑)"
    print(f"📡 fetch-svc 启动：{len(codes)} 只自选股，预算 {BUDGET_MIN} 分钟，{mode}")
    done = 0

    with db.service_run("fetch-svc") as run:
        # 先批量把当日价格全覆盖（快照熔断只看价格覆盖率），再花预算逐只挖深度层
        print("💹 批量行情（全覆盖）…")
        try:
            n = _bulk_prices(codes)
            print(f"✅ 批量行情完成：{n}/{len(codes)} 只有当日价格")
            run.tick(n)
        except Exception as e:
            print(f"⚠️ 批量行情整体失败（不挡逐只抓取）: {e}")

        # 逐只深度层的预算在批量之后才起算（US-139 同款教训）
        deadline = time.time() + BUDGET_MIN * 60
        for code in codes:
            if time.time() > deadline:
                run.stopped_early = True
                print(f"⏱ 达 {BUDGET_MIN} 分钟预算，提前停止（已 {done} 只，剩余下次续）")
                break

            stock = db.get_stock(code)
            if not stock:
                continue
            market = stock.get("market", "nz")

            def log(msg):
                print(f"  {msg}")

            print(f"▶ {code} ({market})")
            ran = 0
            try:
                ran = run_fetch_layers(code, market, log, force=FORCE)
                done += 1
                run.tick()
            except Exception as e:
                print(f"  ⚠️ {code} 抓取失败（跳过）: {e}")
            # gap 只为防东财突发封 IP → 仅当 A股且这轮真跑了层（非全缓存命中）才睡，
            # 否则同日第二轮全缓存时会白白空睡几分钟，拖垮轮转
            if GAP_SEC > 0 and market == "cn" and ran > 0:
                time.sleep(GAP_SEC)

    print(f"✅ fetch-svc 完成：{done}/{len(codes)} 只")


if __name__ == "__main__":
    main()
