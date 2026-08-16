#!/usr/bin/env python3
"""US-157：行业数据源可达性探针 —— 在真实运行环境里测，不靠猜。

为什么要有它：US-157 的设计取决于「哪些源从哪里能抓到」。我此前是从新西兰
本地测出「东财抓不到」，但**本地不等于 GHA runner，也不等于 Fly 悉尼**。
拿本地结论定架构，会和上一轮拿本地 DB 判停更一样错。

同一份脚本要能在三个地方跑，输出可比的矩阵：
    本地(NZ)        python -m scripts.probe_datasource_reach
    GHA(美国)       probe-svc.yml
    Fly(悉尼)       /api/probe-datasources

每个探针都有独立超时，任何异常都记下来继续，绝不让一个源挂掉整张表。
"""
import argparse
import json
import os
import platform
import socket
import sys
import time
from datetime import datetime

TIMEOUT = 25


def _t(fn, *a, **kw):
    """跑一个探针，返回 (ok, 耗时秒, 摘要)。异常一律吞掉记录。"""
    t0 = time.time()
    try:
        val = fn(*a, **kw)
        dt = round(time.time() - t0, 1)
        if val is None:
            return False, dt, "返回 None"
        if hasattr(val, "empty"):          # pandas DataFrame
            if val.empty:
                return False, dt, "空 DataFrame"
            return True, dt, f"{len(val)} 行 · 列={list(val.columns)[:4]}"
        if isinstance(val, (list, dict)):
            return (bool(val), dt,
                    f"{type(val).__name__} len={len(val)}" if val else "空")
        return True, dt, str(val)[:80]
    except Exception as e:
        return False, round(time.time() - t0, 1), f"{type(e).__name__}: {str(e)[:110]}"


# ── 探针定义：(分组, 名称, 可调用) ───────────────────────────────

def _probes():
    import requests

    def http(url, headers=None, **kw):
        def go():
            h = {"User-Agent": "Mozilla/5.0"}
            h.update(headers or {})
            r = requests.get(url, timeout=TIMEOUT, headers=h, **kw)
            r.raise_for_status()
            body = r.text
            return f"HTTP {r.status_code} · {len(body)}B · {body[:60]!r}"
        return go

    out = []

    # ① 裸 HTTP：绕开 akshare，分清「网络不通」还是「akshare 解析变了」
    out += [
        ("裸HTTP", "东财 push2 行情",
         http("https://push2.eastmoney.com/api/qt/clist/get"
              "?pn=1&pz=5&fs=m:90+t:2&fields=f12,f14,f3")),
        ("裸HTTP", "东财 板块列表",
         http("https://push2.eastmoney.com/api/qt/clist/get"
              "?pn=1&pz=100&fs=m:90+t:2&fields=f12,f14,f3")),
        ("裸HTTP", "东财 板块日K(BK0447)",
         http("https://push2his.eastmoney.com/api/qt/stock/kline/get"
              "?secid=90.BK0447&klt=101&fqt=1&lmt=30"
              "&fields1=f1,f2,f3&fields2=f51,f52,f53")),
        ("裸HTTP", "新浪 行情",
         http("https://hq.sinajs.cn/list=sh600519",
              headers={"Referer": "https://finance.sina.com.cn",
                       "User-Agent": "Mozilla/5.0"})),
        ("裸HTTP", "腾讯 行情",
         http("https://qt.gtimg.cn/q=sh600519")),
        ("裸HTTP", "同花顺 板块",
         http("https://q.10jqka.com.cn/thshy/")),
    ]

    # ② akshare：项目当前依赖的路径
    def ak_probe(fname, **kw):
        def go():
            import akshare as ak
            return getattr(ak, fname)(**kw)
        return go

    out += [
        ("akshare", "stock_board_industry_name_em", ak_probe("stock_board_industry_name_em")),
        ("akshare", "stock_board_industry_hist_em",
         ak_probe("stock_board_industry_hist_em", symbol="半导体",
                  start_date="20260701", end_date="20260815",
                  period="日k", adjust="")),
        ("akshare", "stock_board_industry_name_ths", ak_probe("stock_board_industry_name_ths")),
        ("akshare", "stock_individual_info_em", ak_probe("stock_individual_info_em", symbol="600519")),
        ("akshare", "stock_zh_a_spot_em", ak_probe("stock_zh_a_spot_em")),
        ("akshare", "stock_sector_spot", ak_probe("stock_sector_spot", indicator="新浪行业")),
    ]

    # ③ 备选库：baostock（自建服务器，不走东财）
    def bs_industry():
        import baostock as bs
        lg = bs.login()
        if lg.error_code != "0":
            raise RuntimeError(f"login {lg.error_code} {lg.error_msg}")
        try:
            rs = bs.query_stock_industry()
            if rs.error_code != "0":
                raise RuntimeError(f"query {rs.error_code} {rs.error_msg}")
            rows = []
            while rs.next() and len(rows) < 5:
                rows.append(rs.get_row_data())
            return rows
        finally:
            bs.logout()

    out.append(("baostock", "query_stock_industry", bs_industry))

    # ④ yfinance：非A股的行业/板块兜底
    def yf_sector():
        import yfinance as yf
        info = yf.Ticker("AAPL").info
        return {k: info.get(k) for k in ("sector", "industry") if info.get(k)}

    out.append(("yfinance", "AAPL sector/industry", yf_sector))

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--where", default=os.environ.get("PROBE_WHERE", "unknown"),
                    help="local / gha / fly")
    args = ap.parse_args()

    env = {
        "where": args.where,
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "at": datetime.utcnow().isoformat() + "Z",
    }
    try:
        import requests
        env["egress_ip"] = requests.get("https://api.ipify.org", timeout=10).text
    except Exception as e:
        env["egress_ip"] = f"?({type(e).__name__})"

    results = []
    for group, name, fn in _probes():
        ok, dt, detail = _t(fn)
        results.append({"group": group, "name": name, "ok": ok,
                        "seconds": dt, "detail": detail})
        if not args.json:
            print(f"  {'✅' if ok else '❌'} [{group:8}] {name:32} {dt:5.1f}s  {detail}")
            sys.stdout.flush()

    payload = {"env": env, "results": results}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        ok_n = sum(1 for r in results if r["ok"])
        print(f"\n环境: {args.where} · 出口IP {env['egress_ip']}")
        print(f"可达 {ok_n}/{len(results)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
