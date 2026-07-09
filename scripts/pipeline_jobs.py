import json as _json
import threading
import time
from datetime import datetime, timezone, timedelta

import db

from scripts.pipeline_analysis import _analyze_earnings_quality, _run_analysis, _run_layer2
from scripts.pipeline_fetch import (
    _fetch_1a_quote,
    _fetch_1b_financials,
    _fetch_1c1_news,
    _fetch_1c2_capital,
    _fetch_1c3_technicals,
)

CN_TZ = timezone(timedelta(hours=8))

T_PRICE = 20
T_NEWS = 30
T_BASIC = 30
T_FINANCE = 45
T_AI = 180

_CACHE_TTL = {
    "price": 15,
    "news": 0,
    "fund_flow": 0,
    "fundamentals": 7 * 24 * 60,
    "advanced": 24 * 60,
    "technicals": 24 * 60,
    "signals": 24 * 60,
}


def _run_with_timeout(fn, args, label: str, log, timeout: int = T_BASIC):
    # daemon 线程 + join(timeout)：超时就真的抛下它继续（daemon 不阻塞进程退出）。
    # 旧写法用 `with ThreadPoolExecutor`，超时后 __exit__ 的 shutdown(wait=True) 仍会等卡死的
    # 网络线程 → 软超时形同虚设，云端遇无 socket 超时的 AKShare 调用会永久挂起。
    err = {}

    def _worker():
        try:
            fn(*args)
        except Exception as e:
            err["e"] = e

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        log(f"  ⏱ {label} 超时（>{timeout}s），跳过（后台线程已抛下）")
    elif "e" in err:
        log(f"  ⚠️ {label} 失败: {err['e']}")


def _is_cn_trading_day(date_cn: str) -> bool:
    """True if date_cn (YYYY-MM-DD) is a weekday (Mon–Fri).
    Skips public holiday detection — false positives on holidays are acceptable
    (we'll re-fetch and get yesterday's data, which is harmless)."""
    try:
        from datetime import date
        d = date.fromisoformat(date_cn)
        return d.weekday() < 5  # 0=Mon … 4=Fri
    except Exception:
        return True


def _data_age_minutes(code: str, step: str) -> float:
    now_utc = datetime.now(timezone.utc)
    today_cn = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    price_cutoff = (now_utc - timedelta(minutes=15)).isoformat()
    try:
        with db.get_conn() as c:
            if step == "price":
                count = c.execute(
                    "SELECT COUNT(*) AS n FROM stock_prices WHERE code=:code AND fetched_at > :cutoff",
                    {"code": code, "cutoff": price_cutoff},
                ).fetchone()["n"]
                return 0 if count > 0 else float("inf")
            if step == "news":
                count = c.execute(
                    "SELECT COUNT(*) AS n FROM stock_news WHERE code=:code AND fetched_date=:today",
                    {"code": code, "today": today_cn},
                ).fetchone()["n"]
                if count >= 3:
                    return 0
                # Non-trading days rarely have breaking news; treat yesterday's data as fresh
                if not _is_cn_trading_day(today_cn):
                    return 0
                return float("inf")
            if step == "fund_flow":
                row = c.execute(
                    "SELECT date FROM stock_fund_flow WHERE code=:code ORDER BY date DESC LIMIT 1",
                    {"code": code},
                ).fetchone()
                if row and row["date"] == today_cn:
                    return 0
                # No fund flow on weekends/holidays — last trading day's data is fine
                if not _is_cn_trading_day(today_cn):
                    return 0
                return float("inf")
            if step in ("fundamentals", "advanced", "technicals", "signals"):
                row = c.execute(
                    "SELECT updated_at, annual_json FROM stock_fundamentals WHERE code=:code", {"code": code}
                ).fetchone()
                if not row or not row["updated_at"]:
                    return float("inf")
                # Treat empty annual data as always stale so next run retries the fetch
                annual = (row["annual_json"] or "").strip()
                if annual in ("", "[]", "null"):
                    return float("inf")
                try:
                    dt = datetime.fromisoformat(row["updated_at"])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return (now_utc - dt).total_seconds() / 60
                except Exception:
                    return float("inf")
    except Exception:
        pass
    return float("inf")


def _is_stale(code: str, step: str, force: bool) -> bool:
    if force:
        return True
    age = _data_age_minutes(code, step)
    return age > _CACHE_TTL[step]


def run_fetch_layers(code: str, market: str, log, force: bool = True):
    """只抓数据（1a 行情 / 1c1 新闻 / 1b 财务 / 分类 / 1c2 资金 / 1c3 技术面），不跑 AI。
    run_pipeline 与 fetch-svc 共用，保证两条路径抓取行为一致。"""

    def _maybe_run(step, fn, args, label, timeout):
        if _is_stale(code, step, force):
            _run_with_timeout(fn, args, label, log, timeout)
        else:
            log(f"  ⏭ {label} 缓存新鲜，跳过")

    _maybe_run("price", _fetch_1a_quote, [code, market, log], "1a·行情", T_PRICE)
    _maybe_run("news", _fetch_1c1_news, [code, market, log], "1c1·新闻", T_NEWS)
    _maybe_run("fundamentals", _fetch_1b_financials, [code, market, log], "1b·财务", T_FINANCE)

    try:
        from scripts.classifier import classify_stock

        meta = classify_stock(code)
        log(f"  ✦ 重新分类: {meta.get('company_type')} / tier={meta.get('market_tier')}")
    except Exception as _ce:
        log(f"  ⚠️ 重新分类失败: {_ce}")

    _maybe_run("fund_flow", _fetch_1c2_capital, [code, market, log], "1c2·资金信号", T_BASIC)
    _maybe_run("technicals", _fetch_1c3_technicals, [code, market, log], "1c3·技术面", T_PRICE)


def run_pipeline(job_id: int, code: str, market: str, user_id: int = None, force: bool = True):
    logs = []

    def log(msg):
        logs.append(msg)
        snippet = "\n".join(logs)[-500:]
        db.update_job(job_id, status="running", log=snippet)

    try:
        db.update_job(job_id, status="running")
        mode = "全量" if force else "缓存优先"
        log(f"▶ pipeline 开始: {code} ({market}) [{mode}]")

        run_fetch_layers(code, market, log, force)
        _run_with_timeout(_run_analysis, [code, market, log, user_id], "AI分析", log, T_AI)

        log("✅ 完成")
        db.update_job(job_id, status="done", log="\n".join(logs))

        if user_id:
            try:
                grades = db.check_poor_rating_streak(code, user_id)
                if grades:
                    db.create_notification(user_id, code, grades)
                    log(f"  ⚠️ 差评预警：连续6次 {grades}")
            except Exception as _ne:
                log(f"  ⚠️ 差评预警检查失败: {_ne}")
    except Exception as e:
        db.update_job(job_id, status="failed", error=str(e), log="\n".join(logs))


def start_pipeline(user_id: int, code: str, market: str) -> int:
    job_id = db.create_job(user_id, code, "add_stock")
    t = threading.Thread(target=run_pipeline, args=(job_id, code, market, user_id), daemon=True)
    t.start()
    return job_id


def run_quant_only(job_id: int, code: str, market: str, user_id: int = None):
    logs = []

    def log(msg):
        logs.append(msg)
        db.update_job(job_id, status="running", log="\n".join(logs)[-500:])

    try:
        db.update_job(job_id, status="running")
        log(f"▶ 定量评级（含数据刷新）: {code} ({market})")
        _run_with_timeout(_fetch_1a_quote, [code, market, log], "1a·行情", log, T_PRICE)

        if _is_stale(code, "news", force=False):
            _run_with_timeout(_fetch_1c1_news, [code, market, log], "1c1·新闻", log, T_NEWS)
        else:
            log("  ⏭ 新闻缓存新鲜，跳过")

        if _is_stale(code, "fund_flow", force=False):
            _run_with_timeout(_fetch_1c2_capital, [code, market, log], "1c2·资金信号", log, T_BASIC)
        else:
            log("  ⏭ 资金信号缓存新鲜，跳过")

        _run_with_timeout(_run_layer2, [code, market, log, user_id], "Layer2量化", log, T_AI)
        log("✅ 完成")
        db.update_job(job_id, status="done", log="\n".join(logs))
    except Exception as e:
        log(f"⚠️ {e}")
        db.update_job(job_id, status="failed", error=str(e), log="\n".join(logs))


def start_quant_only(user_id: int, code: str, market: str) -> int:
    job_id = db.create_job(user_id, code, "quant_only")
    t = threading.Thread(target=run_quant_only, args=(job_id, code, market, user_id), daemon=True)
    t.start()
    return job_id


def run_letter_only(job_id: int, code: str, market: str, user_id: int = None):
    logs = []

    def log(msg):
        logs.append(msg)
        db.update_job(job_id, status="running", log="\n".join(logs)[-500:])

    try:
        db.update_job(job_id, status="running")
        log(f"▶ 生成股东信: {code}")

        stored = db.get_latest_analysis(code)
        if not stored:
            log("⚠️ 无已有分析记录，请先运行「巴菲特怎么看」")
            db.update_job(job_id, status="failed", error="no analysis", log="\n".join(logs))
            return

        quant_components = {}
        try:
            quant_components = _json.loads(stored.get("quant_components") or "{}")
        except Exception:
            pass

        quant_result = {
            "grade": stored.get("grade", "C"),
            "conclusion": stored.get("conclusion", "持有"),
            "reasoning": stored.get("reasoning", ""),
            "score": stored.get("quant_score") or 0,
            "components": quant_components,
            "red_flags": [],
        }

        stock = db.get_stock(code)
        price = db.get_latest_price(code)
        fundamentals = db.get_fundamentals(code) or {}
        news = db.get_stock_news(code, days=7)
        events = db.get_stock_events(code, limit=10)
        meta = db.get_stock_meta(code)
        company_type = (meta or {}).get("company_type")
        fund_flow = db.get_fund_flow(code) if market == "cn" else {}

        _annual = []
        try:
            _annual = _json.loads(fundamentals.get("annual_json") or "[]")
        except Exception:
            pass

        _signals = fundamentals.get("signals", {})
        trading_params_raw = _signals.get("trading_params")
        trading_params = {}
        try:
            trading_params = _json.loads(trading_params_raw) if trading_params_raw else {}
        except Exception:
            pass

        from scripts.buffett_analyst import _analyze_news_signals, analyze_stock_v3

        news_signals = _analyze_news_signals(news)
        earnings_flags = _analyze_earnings_quality(_annual)

        entry_price, buy_date = None, None
        user_locale = "zh"
        if user_id:
            try:
                with db.get_conn() as c:
                    row = c.execute(
                        "SELECT u.locale, w.buy_price, w.buy_date "
                        "FROM users u "
                        "LEFT JOIN user_watchlist w ON w.user_id=u.id AND w.stock_code=:code "
                        "WHERE u.id=:uid",
                        {"code": code, "uid": user_id},
                    ).fetchone()
                    if row:
                        user_locale = row["locale"] or "zh"
                        if row["buy_price"]:
                            entry_price = float(row["buy_price"])
                            buy_date = row["buy_date"]
            except Exception:
                pass

        def _do_letter():
            result = analyze_stock_v3(
                code=code,
                name=(stock or {}).get("name", code),
                market=market,
                quant_result=quant_result,
                trading_params=trading_params,
                news=news,
                news_signals=news_signals,
                price=price,
                fund_flow=fund_flow,
                fundamentals=fundamentals,
                events=events,
                company_type=company_type,
                entry_price=entry_price,
                buy_date=buy_date,
                data_warnings=[],
                earnings_flags=earnings_flags,
                locale=user_locale,
            )
            if result and result.get("letter_html"):
                today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
                db.save_analysis(
                    code=code,
                    period="daily",
                    analysis_date=today,
                    grade=stored.get("grade"),
                    conclusion=stored.get("conclusion"),
                    reasoning=stored.get("reasoning"),
                    letter_html=result["letter_html"],
                    moat=result.get("moat") or stored.get("moat"),
                    management=result.get("management") or stored.get("management"),
                    valuation=result.get("valuation") or stored.get("valuation"),
                    fund_flow_summary=result.get("fund_flow_summary"),
                    behavioral=result.get("behavioral"),
                    macro_sensitivity=result.get("macro_sensitivity"),
                    quant_score=stored.get("quant_score"),
                    quant_components=stored.get("quant_components"),
                    framework_used=result.get("framework_used") or stored.get("framework_used"),
                    trade_block=result.get("trade_block"),
                )
                log(f"       股东信生成完成（{len(result['letter_html'])}字）")
            else:
                log("       ⚠️ Layer 3 无输出（Groq 限速或超时）")

        _run_with_timeout(_do_letter, [], "股东信生成", log, T_AI)
        db.update_job(job_id, status="done", log="\n".join(logs))
    except Exception as e:
        log(f"⚠️ {e}")
        db.update_job(job_id, status="failed", error=str(e), log="\n".join(logs))


def start_letter_only(user_id: int, code: str, market: str) -> int:
    job_id = db.create_job(user_id, code, "letter_only")
    t = threading.Thread(target=run_letter_only, args=(job_id, code, market, user_id), daemon=True)
    t.start()
    return job_id


def run_analysis_only(job_id: int, code: str, market: str, user_id: int = None):
    run_quant_only(job_id, code, market, user_id)


def start_analysis_only(user_id: int, code: str, market: str) -> int:
    return start_quant_only(user_id, code, market)


def run_news_update(job_id: int, code: str, market: str, user_id: int = None):
    logs = []

    def log(msg):
        logs.append(msg)
        db.update_job(job_id, status="running", log="\n".join(logs)[-500:])

    try:
        db.update_job(job_id, status="running")
        log(f"▶ 更新新闻: {code}")
        _run_with_timeout(_fetch_1c1_news, [code, market, log], "1c1·新闻", log, T_NEWS)
        log("  重新计算量化评级（应用新新闻）…")
        _run_with_timeout(_run_layer2, [code, market, log, user_id], "Layer2量化", log, T_AI)
        log("✅ 新闻更新完成")
        db.update_job(job_id, status="done", log="\n".join(logs))
    except Exception as e:
        db.update_job(job_id, status="failed", error=str(e), log="\n".join(logs))


def start_news_update(user_id: int, code: str, market: str) -> int:
    job_id = db.create_job(user_id, code, "news_update")
    t = threading.Thread(target=run_news_update, args=(job_id, code, market, user_id), daemon=True)
    t.start()
    return job_id


def run_daily_all():
    codes = db.all_watched_codes()
    print(f"[daily] {len(codes)} 只股票")
    for code in codes:
        stock = db.get_stock(code)
        if not stock:
            continue
        market = stock.get("market", "nz")
        job_id = db.create_job(user_id=None, code=code, job_type="daily")
        run_pipeline(job_id, code, market)

        # 差评预警：分析完后逐用户检查连续 D 评级
        for uid in db.get_users_watching_code(code):
            try:
                grades = db.check_poor_rating_streak(code, uid)
                if grades:
                    db.create_notification(uid, code, grades)
                    print(f"  ⚠️ 差评预警 {code} user={uid}：连续{len(grades)}次 {grades[0]}")
            except Exception as e:
                print(f"  ⚠️ 差评预警检查失败 {code}/{uid}: {e}")

        time.sleep(1)
