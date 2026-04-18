#!/usr/bin/env python3
"""Personal Buffett · Flask app with Google OAuth + email/password"""

import sys, os, re, subprocess, traceback
sys.path.insert(0, os.path.dirname(__file__))

import json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_bcrypt import Bcrypt
from authlib.integrations.flask_client import OAuth
import db
from scripts.config import CN_TZ, BUFFETT_PROFILES
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
from nz_profiles import NZ_PROFILES, NZ_SECTORS
from nz_fetch import (fetch_all_nz_quotes, fetch_nz_quote,
                      fetch_nz_news, fetch_nz_market_news, fetch_nzx50,
                      fetch_rbnz_news)
from macro_fetch import fetch_fomc_news
from pipeline import start_pipeline
from portfolio_brief import generate_portfolio_brief
import stock_search as _stock_search  # 触发 A股列表后台预热

# ── i18n ──────────────────────────────────────────────
_I18N_DIR = os.path.join(os.path.dirname(__file__), "i18n")
_i18n_cache = {}

def _load_strings(locale):
    if locale not in _i18n_cache:
        path = os.path.join(_I18N_DIR, f"{locale}.json")
        fallback = os.path.join(_I18N_DIR, "en.json")
        with open(path if os.path.exists(path) else fallback) as f:
            _i18n_cache[locale] = json.load(f)
    return _i18n_cache[locale]

MARKET_CURRENCY = {"cn": "¥", "nz": "NZ$", "hk": "HK$", "us": "$", "kr": "₩", "au": "A$"}

def _detect_market(code):
    if code.endswith(".NZ"):   return "nz"
    if code.endswith(".HK"):   return "hk"
    if code.endswith(".KS") or code.endswith(".KQ"): return "kr"
    if code.endswith(".AX"):   return "au"
    if re.match(r"^\d{5}$", code): return "hk"
    if re.match(r"^\d{6}$", code): return "cn"
    return "us"

app    = Flask(__name__)
bcrypt = Bcrypt(app)
oauth  = OAuth(app)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "personal-buffett-2024-xK9m")

# 确保 DB 表在应用启动时就创建好（gunicorn import 时执行）
with app.app_context():
    db.init_db()
    db._migrate()

@app.context_processor
def inject_i18n():
    locale = session.get("locale", "en")
    return {
        "t":               _load_strings(locale),
        "locale":          locale,
        "user_region":     session.get("region", "nz"),
        "market_currency": MARKET_CURRENCY,
    }

# ── Google OAuth ──────────────────────────────────────
# Fill in after getting credentials from Google Cloud Console
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

google = oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def _validate_password(pw):
    if len(pw) < 8:              return "At least 8 characters."
    if not re.search(r"[A-Z]", pw): return "Add an uppercase letter."
    if not re.search(r"[a-z]", pw): return "Add a lowercase letter."
    if not re.search(r"\d", pw):    return "Add a number."
    return None


# ── Google OAuth routes ───────────────────────────────
@app.route("/auth/google")
def google_login():
    redirect_uri = url_for("google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/auth/google/callback")
def google_callback():
    try:
        token    = google.authorize_access_token()
        userinfo = token.get("userinfo") or google.userinfo()
        g_id     = userinfo["sub"]
        email    = userinfo["email"]
        name     = userinfo.get("name", email.split("@")[0])
        avatar   = userinfo.get("picture", "")

        db.init_db()
        user = db.get_or_create_oauth_user("google", g_id, email, name, avatar)
        session["user_id"]      = user["id"]
        session["display_name"] = user.get("display_name") or name
        session["avatar_url"]   = user.get("avatar_url") or avatar
        session["role"]         = user.get("role", "member")
        return redirect(url_for("index"))
    except Exception as e:
        flash(f"Google sign-in failed: {e}", "danger")
        return redirect(url_for("login"))


# ── Email auth ────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))

    errors = {}
    form   = {}

    if request.method == "POST":
        form  = request.form.to_dict()
        email = form.get("email", "").strip().lower()
        pw    = form.get("password", "")
        user  = db.get_user_by_email(email)
        if not user or not user.get("password_hash"):
            errors["email"] = "No account found with this email."
        elif not bcrypt.check_password_hash(user["password_hash"], pw):
            errors["password"] = "Incorrect password."
        else:
            _set_session(user)
            return redirect(url_for("index"))

    return render_template("login.html", errors=errors, form=form,
                           google_enabled=bool(GOOGLE_CLIENT_ID))


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("index"))

    errors = {}
    form   = {}

    if request.method == "POST":
        form  = request.form.to_dict()
        email = form.get("email", "").strip().lower()
        pw    = form.get("password", "")
        pw2   = form.get("confirm_password", "")

        if not email or "@" not in email:
            errors["email"] = "Enter a valid email address."
        elif db.user_exists(email=email):
            errors["email"] = "An account with this email already exists."

        pw_err = _validate_password(pw)
        if pw_err:             errors["password"] = pw_err
        elif pw != pw2:        errors["confirm_password"] = "Passwords don't match."

        if not errors:
            pw_hash = bcrypt.generate_password_hash(pw).decode("utf-8")
            db.create_user(email=email, password_hash=pw_hash,
                           display_name=email.split("@")[0])
            user = db.get_user_by_email(email)
            _set_session(user)
            return redirect(url_for("index"))

    return render_template("register.html", errors=errors, form=form,
                           google_enabled=bool(GOOGLE_CLIENT_ID))


def _set_session(user):
    session["user_id"]      = user["id"]
    session["display_name"] = user.get("display_name") or user.get("email","").split("@")[0]
    session["avatar_url"]   = user.get("avatar_url", "")
    session["locale"]       = user.get("locale", "en")
    session["region"]       = user.get("region", "nz")
    session["role"]         = user.get("role", "member")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Public Homepage ────────────────────────────────────
@app.route("/home")
def home():
    nzx50   = fetch_nzx50()
    quotes  = fetch_all_nz_quotes()
    news    = fetch_nz_market_news()
    # Top movers
    movers  = sorted(quotes.values(), key=lambda x: abs(x.get("change", 0)), reverse=True)[:4]
    # A-grade picks
    picks   = [t for t, p in NZ_PROFILES.items() if p["grade"] == "A"]
    pick_quotes = {t: quotes.get(t, {}) for t in picks}
    return render_template("home.html",
        nzx50=nzx50, movers=movers, news=news,
        sectors=NZ_SECTORS, picks=picks,
        pick_quotes=pick_quotes, profiles=NZ_PROFILES,
        logged_in="user_id" in session,
    )


# ── US-66: 财务指标通俗解读 ───────────────────────────────

def _compute_metric_hints(lat, signals, pe_current, price, locale='zh'):
    """
    US-66: 为每个财务指标生成一句人话解读。
    返回 {metric: {'text': str, 'level': 'good'|'ok'|'warn'}}
    纯规则引擎，无 LLM，不报错。
    """
    hints = {}
    zh = (locale == 'zh')

    def _num(v):
        """解析 '18.2%' / '35.97x ⚠' / 数字 → float，失败返回 None"""
        if v is None or v == '—' or v == '':
            return None
        try:
            if isinstance(v, (int, float)):
                return float(v)
            cleaned = str(v).replace('%', '').replace('x', '').replace('⚠', '').strip()
            return float(cleaned)
        except Exception:
            return None

    # ── PE ──────────────────────────────────────────────
    pe_v = _num(pe_current) or _num((price or {}).get('pe_ratio'))
    if pe_v is not None:
        n = round(abs(pe_v))
        if pe_v < 0:
            hints['pe'] = {'text': '亏了！PE 这个数没意义' if zh else 'Losing money · PE meaningless', 'level': 'warn'}
        elif pe_v < 15:
            hints['pe'] = {'text': f'现在买入的话，大约 {n} 年能回本 · 不贵' if zh else f'At this price, ~{n} yrs to earn back · Cheap', 'level': 'good'}
        elif pe_v < 25:
            hints['pe'] = {'text': f'现在买入的话，大约 {n} 年能回本 · 价格合理' if zh else f'At this price, ~{n} yrs to earn back · Fair', 'level': 'ok'}
        elif pe_v < 40:
            hints['pe'] = {'text': f'现在买入的话，{n} 年回本 · 市场认为它还会继续增长' if zh else f'~{n} yrs to earn back · Market expects continued growth', 'level': 'ok'}
        else:
            hints['pe'] = {'text': f'现在买入的话，要 {n} 年才能回本 · 在赌它高速增长' if zh else f'~{n} yrs to earn back · Betting on fast growth ⚠', 'level': 'warn'}

    # ── ROE ─────────────────────────────────────────────
    roe_v = _num((lat or {}).get('roe'))
    if roe_v is not None:
        n = round(abs(roe_v))
        if roe_v < 0:
            hints['roe'] = {'text': '亏了！' if zh else 'Losing money!', 'level': 'warn'}
        elif roe_v < 5:
            hints['roe'] = {'text': f'每100块本金才赚 {n} 块，还不如存银行' if zh else f'Earns just {n}¢ per $1 · Worse than savings', 'level': 'warn'}
        elif roe_v < 10:
            hints['roe'] = {'text': f'每100块本金每年赚 {n} 块 · 一般' if zh else f'Earns {n}¢ per $1 · Average', 'level': 'ok'}
        elif roe_v < 20:
            hints['roe'] = {'text': f'每100块本金每年赚 {n} 块 · 不错，很多公司到不了这个' if zh else f'Earns {n}¢ per $1 · Good, most companies don\'t reach this', 'level': 'ok'}
        else:
            hints['roe'] = {'text': f'每100块本金每年能赚 {n} 块 · 很能赚' if zh else f'Earns {n}¢ per $1 · Excellent', 'level': 'good'}

    # ── 净利润率 ─────────────────────────────────────────
    nm_v = _num((lat or {}).get('net_margin'))
    if nm_v is not None:
        n = round(abs(nm_v))
        if nm_v < 0:
            hints['net_margin'] = {'text': '亏了！' if zh else 'Losing money!', 'level': 'warn'}
        elif nm_v < 5:
            hints['net_margin'] = {'text': f'卖100块东西才留 {n} 块，一出问题就垮' if zh else f'Keeps just {n}¢ per $1 · One bad quarter could break it', 'level': 'warn'}
        elif nm_v < 10:
            hints['net_margin'] = {'text': f'卖100块东西只留 {n} 块 · 辛苦钱，每笔赚得少' if zh else f'Keeps {n}¢ per $1 · Tight, every deal counts', 'level': 'ok'}
        elif nm_v < 20:
            hints['net_margin'] = {'text': f'卖100块东西能留 {n} 块 · 不错，大多数行业达不到' if zh else f'Keeps {n}¢ per $1 · Good, hard to reach in most industries', 'level': 'ok'}
        else:
            hints['net_margin'] = {'text': f'卖100块东西能留 {n} 块 · 挣钱轻松' if zh else f'Keeps {n}¢ per $1 · Very profitable', 'level': 'good'}

    # ── 负债率 / D/E ─────────────────────────────────────
    dr = (lat or {}).get('debt_ratio')
    dr_note = (lat or {}).get('debt_ratio_note')
    dr_v = _num(dr)
    if dr_v is not None:
        is_de = bool(dr_note)  # 非A股用 D/E ratio
        if is_de:
            if dr_v <= 1:
                hints['debt_ratio'] = {'text': '借的钱比自己的少 · 稳健' if zh else 'Debt less than equity · Solid', 'level': 'good'}
            elif dr_v <= 3:
                hints['debt_ratio'] = {'text': '借了一些钱，还在可控范围内' if zh else 'Moderate borrowing · Manageable', 'level': 'ok'}
            else:
                hints['debt_ratio'] = {'text': '借的钱太多，一出问题就垮' if zh else 'Heavy debt · One crack and it collapses', 'level': 'warn'}
        else:
            if dr_v < 40:
                hints['debt_ratio'] = {'text': f'公司 {round(dr_v)}% 的钱是自己的，借来的少' if zh else f'{round(dr_v)}% debt-funded · Low borrowing', 'level': 'good'}
            elif dr_v < 70:
                hints['debt_ratio'] = {'text': 'A股上市公司里超过一半都这样' if zh else 'Over half of A-share listed companies are in this range', 'level': 'ok'}
            elif dr_v < 90:
                hints['debt_ratio'] = {'text': '借了很多钱，要看公司能不能按时还' if zh else 'Heavy debt · Watch if it can repay on time', 'level': 'warn'}
            else:
                hints['debt_ratio'] = {'text': '几乎全靠借钱撑着，一出问题就垮' if zh else 'Nearly all debt-funded · One crack and it collapses', 'level': 'warn'}

    # ── ROIC ────────────────────────────────────────────
    roic_v = _num((signals or {}).get('roic_latest'))
    if roic_v is not None:
        n = round(roic_v)
        if roic_v < 8:
            hints['roic'] = {'text': f'每投入100块才赚 {n} 块，不如直接买沪深300' if zh else f'Returns only {n}¢ per $1 · Index fund beats this', 'level': 'warn'}
        elif roic_v < 15:
            hints['roic'] = {'text': f'每投入100块每年能赚回 {n} 块 · 还行' if zh else f'Returns {n}¢ per $1 · Acceptable', 'level': 'ok'}
        else:
            hints['roic'] = {'text': f'每投入100块每年能赚回 {n} 块 · 很划算' if zh else f'Returns {n}¢ per $1 · Great', 'level': 'good'}

    # ── FCF ─────────────────────────────────────────────
    fcf_v = _num((signals or {}).get('fcf_quality_avg'))
    if fcf_v is not None:
        if fcf_v >= 0.8:
            hints['fcf'] = {'text': '账面利润是真的，钱真的进了口袋' if zh else 'Profits are real cash · Healthy', 'level': 'good'}
        elif fcf_v >= 0.3:
            hints['fcf'] = {'text': '利润基本有现金支撑 · 尚可' if zh else 'Profits mostly cash-backed · Acceptable', 'level': 'ok'}
        else:
            hints['fcf'] = {'text': '账面有利润，但钱还没进口袋，要留意' if zh else 'Paper profits only · Cash hasn\'t arrived yet', 'level': 'warn'}

    return hints


# ── Individual Stock Page ──────────────────────────────
@app.route("/stock/<path:code>/fundamentals")
@login_required
def stock_fundamentals(code):
    return redirect(url_for("stock_page", code=code.upper()) + "#tab-archive")


@app.route("/stock/<path:code>")
@login_required
def stock_page(code):
    code  = code.upper()
    stock = db.get_stock(code)
    if not stock:
        flash("Stock not found. Add it to your watchlist first.", "warning")
        return redirect(url_for("index"))

    market   = stock.get("market", "us")
    price    = db.get_latest_price(code)
    news     = db.get_stock_news(code, days=7)
    analysis = db.get_latest_analysis(code, period="daily")
    history  = db.get_analysis_history(code, period="daily", limit=20)
    prices   = db.get_price_history(code, days=30)
    ff         = db.get_fund_flow(code) if market == "cn" else {}
    ff_hist    = db.get_fund_flow_history(code, days=60) if market == "cn" else []
    north_bound= db.get_north_bound() if market == "cn" else {}
    fund     = db.get_fundamentals(code)  # 所有市场都支持
    signals  = fund.get("signals", {}) if fund else {}
    annual   = fund.get("annual",  []) if fund else []
    pe_current       = fund.get("pe_current")       if fund else None
    pe_percentile_5y = fund.get("pe_percentile_5y") if fund else None
    pb_current       = fund.get("pb_current")       if fund else None
    pb_percentile_5y = fund.get("pb_percentile_5y") if fund else None

    # 对非A股数据，格式化百分比为模板期望的格式
    if signals and not annual:
        # 转换财务指标为百分比字符串
        if "roe" in signals and isinstance(signals["roe"], (int, float)):
            signals["roe"] = f"{signals['roe']*100:.1f}%"
        if "roa" in signals and isinstance(signals["roa"], (int, float)):
            signals["roa"] = f"{signals['roa']*100:.1f}%"
        if "gross_margin" in signals and isinstance(signals["gross_margin"], (int, float)):
            signals["gross_margin"] = f"{signals['gross_margin']*100:.1f}%"
        if "profit_margin" in signals and isinstance(signals["profit_margin"], (int, float)):
            # 添加 net_margin 别名（模板期望这个字段）
            signals["net_margin"] = f"{signals['profit_margin']*100:.1f}%"
            signals["profit_margin"] = signals["net_margin"]
        if "debt_to_equity" in signals and isinstance(signals["debt_to_equity"], (int, float)):
            de = signals["debt_to_equity"]
            if de > 5:
                # D/E ratio 大于5时明确标注，避免误读为负债率百分比
                signals["debt_ratio"] = f"{de:.2f}x ⚠"
                signals["debt_ratio_note"] = "D/E ratio（非负债率%），数值偏高"
            else:
                signals["debt_ratio"] = f"{de:.2f}x"
                signals["debt_ratio_note"] = "D/E ratio（非负债率%）"
        # 为非A股添加 year 字段（使用分析日期）
        if analysis and "analysis_date" in analysis:
            signals["year"] = analysis["analysis_date"][:4]
        else:
            signals["year"] = datetime.now(CN_TZ).strftime("%Y")

        # 对非A股，创建一个 "虚拟年度" 记录放入 annual 数组，这样模板就能统一处理
        virtual_annual = {
            "year": signals.get("year", "—"),
            "roe": signals.get("roe", "—"),
            "net_margin": signals.get("net_margin", "—"),
            "debt_ratio": signals.get("debt_ratio", "—"),
            "debt_ratio_note": signals.get("debt_ratio_note"),
            "profit_growth": "—",
        }
        annual = [virtual_annual]

    # pending pipeline job?
    with db.get_conn() as c:
        j = c.execute("""
            SELECT id, status FROM pipeline_jobs
            WHERE code=? AND status IN ('pending','running') AND started_at > datetime('now','-15 minutes')
            ORDER BY id DESC LIMIT 1
        """, (code,)).fetchone()
        pending_job = dict(j) if j else None

    in_wl = any(r.get("stock_code") == code
                for r in db.get_user_watchlist(session["user_id"]))

    meta   = db.get_stock_meta(code)
    events = db.get_stock_events(code)

    # 预计算操作参数（纯数学，复用上方已查的 fund/signals）
    from scripts.pipeline import _compute_trading_params
    trading_params = _compute_trading_params(price, signals, market=market)

    # 数据新鲜度：价格 / 财务 / 分析 三个时间戳
    now_utc = datetime.now(timezone.utc)

    def _age_label(ts_str: str | None) -> str:
        """把时间戳字符串转为「X 分钟前 / X 小时前 / X 天前」。"""
        if not ts_str:
            return "—"
        try:
            dt = datetime.fromisoformat(str(ts_str))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            diff = now_utc - dt
            m = int(diff.total_seconds() / 60)
            if m < 1:   return "刚刚"
            if m < 60:  return f"{m} 分钟前"
            if m < 1440: return f"{m // 60} 小时前"
            return f"{m // 1440} 天前"
        except Exception:
            # 可能是纯日期字符串 "2026-04-15"
            try:
                d = datetime.strptime(str(ts_str)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                days = (now_utc - d).days
                if days == 0: return "今天"
                if days == 1: return "昨天"
                return f"{days} 天前"
            except Exception:
                return "—"

    def _age_minutes(ts_str) -> float:
        """返回时间戳距今分钟数，无法解析返回 inf。"""
        if not ts_str:
            return float('inf')
        try:
            dt = datetime.fromisoformat(str(ts_str))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (now_utc - dt).total_seconds() / 60
        except Exception:
            try:
                d = datetime.strptime(str(ts_str)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                return (now_utc - d).total_seconds() / 60
            except Exception:
                return float('inf')

    data_freshness = {
        "price":    _age_label(price.get("fetched_at") if price else None),
        "finance":  _age_label(fund.get("updated_at")  if fund  else None),
        "analysis": _age_label(analysis.get("analysis_date") if analysis else None),
    }
    # stale: 价格>3天, 财务>7天, 分析>3天
    _price_age    = _age_minutes(price.get("fetched_at")            if price    else None)
    _finance_age  = _age_minutes(fund.get("updated_at")             if fund     else None)
    _analysis_age = _age_minutes(analysis.get("analysis_date")      if analysis else None)
    data_freshness_stale = {
        "price":    _price_age    > 3 * 1440,
        "finance":  _finance_age  > 7 * 1440,
        "analysis": _analysis_age > 3 * 1440,
    }

    lat_for_hints = annual[0] if annual else signals
    metric_hints  = _compute_metric_hints(
        lat_for_hints, signals, pe_current, price,
        locale=session.get("locale", "zh"),
    )

    return render_template("stock.html",
        stock=stock, price=price, news=news,
        analysis=analysis, history=history, prices=prices,
        fund_flow=ff, ff_hist=ff_hist, north_bound=north_bound,
        signals=signals, annual=annual,
        pe_current=pe_current, pe_percentile_5y=pe_percentile_5y,
        pb_current=pb_current, pb_percentile_5y=pb_percentile_5y,
        pending_job=pending_job, in_watchlist=in_wl,
        market=market, meta=meta, events=events,
        currency=MARKET_CURRENCY.get(market, "$"),
        now=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
        trading_params=trading_params,
        data_freshness=data_freshness,
        data_freshness_stale=data_freshness_stale,
        metric_hints=metric_hints,
    )


# ── Dashboard ─────────────────────────────────────────
@app.route("/")
@login_required
def index():
    db.init_db()
    db._migrate()
    region    = session.get("region", "nz")
    # 首页只展示 holding + watching（不含已卖出）
    watchlist = [w for w in db.get_user_watchlist(session["user_id"])
                 if w.get("status", "watching") != "sold"]
    quote_map = {q["code"]: q for q in db.get_quotes()}
    reports   = db.list_reports(limit=10)
    latest    = db.get_report()

    # ── 自选股：从 DB 读价格 + 最新分析结果 ──────────────
    stocks = []
    for row in watchlist:
        code   = row.get("stock_code") or row.get("code")
        market = row.get("market") or _detect_market(code)
        name   = row.get("name", code)

        price_row = db.get_latest_price(code)
        analysis  = db.get_latest_analysis(code, period="daily")
        ff        = db.get_fund_flow(code) if market == "cn" else {}

        # 检查是否有正在跑的 pipeline
        pending_job = None
        with db.get_conn() as c:
            j = c.execute("""
                SELECT id, status FROM pipeline_jobs
                WHERE code=? AND status IN ('pending','running') AND started_at > datetime('now','-15 minutes')
                ORDER BY id DESC LIMIT 1
            """, (code,)).fetchone()
            if j:
                pending_job = dict(j)

        stocks.append({
            "code":       code,
            "name":       name,
            "market":     market,
            "currency":   MARKET_CURRENCY.get(market, "$"),
            "price":      price_row.get("price"),
            "change_pct": price_row.get("change_pct"),
            "grade":      analysis.get("grade", "—") if analysis else "—",
            "conclusion": analysis.get("conclusion", "") if analysis else "",
            "reasoning":  (analysis.get("reasoning","") or "")[:120] if analysis else "",
            "has_letter": bool(analysis and analysis.get("letter_html")),
            "main_net":   ff.get("main_net") if ff else None,
            "pending_job":pending_job,
            "analysis_date": analysis.get("analysis_date","") if analysis else "",
        })

    local_stocks = [s for s in stocks if s["market"] == region]
    intl_stocks  = [s for s in stocks if s["market"] != region]

    # ── 持仓警示等级（规则引擎，无需 LLM）────────────────
    def _compute_alert(s):
        grade = (s.get("grade") or "—").replace("+","").replace("-","")
        if grade in ("C","D"):
            return "warn", f"评级{s.get('grade','—')}，基本面需关注"
        net = s.get("main_net")
        if net is not None and net < -0.5:
            return "warn", f"主力净流出 {net:.2f}亿，资金出逃"
        conc = s.get("conclusion") or ""
        if conc in ("卖出","减持"):
            return "warn", f"结论「{conc}」，关注执行时机"
        r = (s.get("reasoning") or "")[:45]
        return "ok", (r + "…") if r else "持续关注"

    for s in stocks:
        s["alert_level"], s["alert_reason"] = _compute_alert(s)

    # ── 加载今日组合简报 ──────────────────────────────────
    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    portfolio_brief = db.get_portfolio_brief(session["user_id"], date=today)
    # 将 brief 的 created_at（SQLite UTC）转为 CST 显示
    if portfolio_brief and portfolio_brief.get("created_at"):
        try:
            from datetime import timedelta
            _utc = datetime.strptime(portfolio_brief["created_at"][:16], "%Y-%m-%d %H:%M")
            portfolio_brief = dict(portfolio_brief)
            portfolio_brief["created_at_cst"] = (_utc + timedelta(hours=8)).strftime("%H:%M")
        except Exception:
            portfolio_brief = dict(portfolio_brief)
            portfolio_brief["created_at_cst"] = ""

    # ── Market pulse（轻量，只拉 NZX50）─────────────────
    market = {}
    try:
        market["nzx50"]      = fetch_nzx50()
        market["nz_sectors"] = NZ_SECTORS
    except Exception:
        pass
    # 宏观数据从 DB 最新快照读（不实时爬，刷新按钮才更新）
    try:
        snap = db.get_market_snapshot()
        if snap:
            mdata = snap.get("data", {})
            for k in ("fear_greed", "cny_usd", "cn_indices", "commodities"):
                if mdata.get(k):
                    market[k] = mdata[k]
    except Exception:
        pass

    # ── 本地新闻（NZ Herald + RBNZ）─────────────────────
    local_news = []
    try:
        for n in fetch_nz_market_news()[:8]:
            local_news.append({**n, "section": "Market"})
    except Exception:
        pass
    try:
        for n in fetch_rbnz_news(limit=3):
            local_news.append({**n, "section": "RBNZ"})
    except Exception:
        pass

    # ── 国际新闻（DB里的股票新闻 + FOMC）────────────────
    intl_news = []
    try:
        cn_codes = [s["code"] for s in stocks if s["market"] in ("cn","hk")]
        seen = set()
        for code in cn_codes[:15]:
            stock_info = db.get_stock(code)
            sname = stock_info.get("name", code) if stock_info else code
            for n in db.get_stock_news(code, days=3):
                key = n.get("title","")[:40]
                if key and key not in seen:
                    seen.add(key)
                    intl_news.append({
                        "title":   n.get("title",""),
                        "link":    n.get("link",""),
                        "source":  n.get("source", sname),
                        "time":    n.get("publish_time",""),
                        "section": sname,
                    })
        intl_news.sort(key=lambda x: x.get("time",""), reverse=True)
        intl_news = intl_news[:10]
    except Exception:
        pass
    try:
        for n in fetch_fomc_news(limit=2):
            intl_news.append({**n, "section": "FOMC"})
    except Exception:
        pass
    # Fear & Greed + CNY 插到国际新闻开头
    fg  = market.get("fear_greed", {})
    cny = market.get("cny_usd", {})
    if fg and fg.get("score") is not None:
        intl_news.insert(0, {
            "title":   f"CNN Fear & Greed: {fg['score']} — {fg.get('label','')}. {fg.get('buffett','')}",
            "link": "", "source": "CNN Markets", "time": "", "section": "Macro",
        })
    if cny and cny.get("rate"):
        intl_news.insert(1, {
            "title":   f"USD/CNY {cny['rate']} — {cny.get('direction','')}",
            "link": "", "source": "汇率", "time": "", "section": "Macro",
        })

    weekly_report    = db.get_report(period="weekly")
    monthly_report   = db.get_report(period="monthly")
    quarterly_report = db.get_report(period="quarterly")

    return render_template("index.html",
        stocks=stocks,
        local_stocks=local_stocks, intl_stocks=intl_stocks,
        local_news=local_news,     intl_news=intl_news,
        reports=reports,           latest_report=latest,
        weekly_report=weekly_report,
        monthly_report=monthly_report,
        quarterly_report=quarterly_report,
        market=market,
        portfolio_brief=portfolio_brief,
        now=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    )


# ── Daily Brief Page ──────────────────────────────────
@app.route("/brief")
@login_required
def brief_page():
    db.init_db(); db._migrate()
    user_id  = session["user_id"]
    watchlist = [w for w in db.get_user_watchlist(user_id)
                 if w.get("status", "watching") != "sold"]

    stocks = []
    for row in watchlist:
        code   = row.get("stock_code") or row.get("code")
        market = row.get("market") or _detect_market(code)
        a  = db.get_latest_analysis(code, period="daily")
        ff = db.get_fund_flow(code) if market == "cn" else {}
        stocks.append({
            "code":       code,
            "name":       row.get("name", code),
            "market":     market,
            "currency":   MARKET_CURRENCY.get(market, "$"),
            "grade":      a.get("grade", "—") if a else "—",
            "conclusion": a.get("conclusion", "") if a else "",
            "reasoning":  (a.get("reasoning","") or "")[:80] if a else "",
            "main_net":   ff.get("main_net") if ff else None,
        })

    def _compute_alert(s):
        grade = (s.get("grade") or "—").replace("+","").replace("-","")
        if grade in ("C","D"):
            return "warn", f"Grade {s['grade']} — review fundamentals"
        net = s.get("main_net")
        if net is not None and net < -0.5:
            return "warn", f"Institutional outflow {net:.2f}B"
        conc = s.get("conclusion","")
        if conc in ("卖出","减持","Sell","Reduce"):
            return "warn", conc
        r = (s.get("reasoning") or "")[:60]
        return "ok", (r+"…") if r else "No issues"

    for s in stocks:
        s["alert_level"], s["alert_reason"] = _compute_alert(s)

    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    portfolio_brief = db.get_portfolio_brief(user_id, date=today)
    if portfolio_brief and portfolio_brief.get("created_at"):
        try:
            from datetime import timedelta
            _utc = datetime.strptime(portfolio_brief["created_at"][:16], "%Y-%m-%d %H:%M")
            portfolio_brief = dict(portfolio_brief)
            portfolio_brief["created_at_cst"] = (_utc + timedelta(hours=8)).strftime("%H:%M")
        except Exception:
            portfolio_brief = dict(portfolio_brief)
            portfolio_brief["created_at_cst"] = ""

    snap = db.get_market_snapshot()
    market = snap.get("data", {}) if snap else {}

    return render_template("brief.html",
        stocks=stocks,
        portfolio_brief=portfolio_brief,
        market=market,
        now=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    )


# ── Watchlist Page ────────────────────────────────────
@app.route("/watchlist")
@login_required
def watchlist_page():
    db.init_db()
    db._migrate()  # 确保 user_watchlist 所有列都存在（status/buy_price 等）
    watchlist = db.get_user_watchlist(session["user_id"])
    stocks = []
    for row in watchlist:
        code   = row.get("stock_code") or row.get("code")
        market = row.get("market") or _detect_market(code)
        name   = row.get("name", code)
        price_row = db.get_latest_price(code)
        analysis  = db.get_latest_analysis(code, period="daily")
        with db.get_conn() as c:
            j = c.execute("""SELECT id,status FROM pipeline_jobs
                WHERE code=? AND status IN ('pending','running') AND started_at > datetime('now','-15 minutes')
                ORDER BY id DESC LIMIT 1""", (code,)).fetchone()
            pending_job = dict(j) if j else None
        grade = analysis.get("grade", "") if analysis else ""
        _GRADE_ORDER = {"A":1,"B+":2,"B":3,"B-":4,"C+":5,"C":6,"D":7}
        _CONC_ORDER  = {"买入":1,"持有":2,"观察":3,"减持":4,"卖出":5}
        # signals data for richer card
        fund = db.get_fundamentals(code) if market == "cn" else {}
        sigs = fund.get("signals", {}) if fund else {}
        stocks.append({
            "code": code, "name": name, "market": market,
            "currency": MARKET_CURRENCY.get(market, "$"),
            "price": price_row.get("price"),
            "change_pct": price_row.get("change_pct"),
            "grade": grade or "—",
            "grade_sort": _GRADE_ORDER.get(grade, 99),
            "conclusion": analysis.get("conclusion", "") if analysis else "",
            "conclusion_sort": _CONC_ORDER.get(analysis.get("conclusion","") if analysis else "", 99),
            "reasoning": (analysis.get("reasoning","") or "")[:120] if analysis else "",
            "has_letter": bool(analysis and analysis.get("letter_html")),
            "pending_job": pending_job,
            "analysis_date": analysis.get("analysis_date","") if analysis else "",
            "moat_direction": sigs.get("moat_direction", ""),
            "roic_latest":    sigs.get("roic_latest"),
            "fcf_quality":    sigs.get("fcf_quality_avg"),
            # 状态字段
            "status":      row.get("status", "watching"),
            "buy_date":    row.get("buy_date"),
            "buy_price":   row.get("buy_price"),
            "sell_date":   row.get("sell_date"),
            "sell_price":  row.get("sell_price"),
            "entry_grade": row.get("entry_grade"),
        })

    holding  = [s for s in stocks if s["status"] == "holding"]
    watching = [s for s in stocks if s["status"] == "watching"]
    sold     = [s for s in stocks if s["status"] == "sold"]

    notifications = db.get_active_notifications(session["user_id"])

    return render_template("watchlist.html",
        stocks=stocks, holding=holding, watching=watching, sold=sold,
        notifications=notifications,
        now=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
        now_date=datetime.now(CN_TZ).strftime("%Y-%m-%d"))


# ── 通知操作（US-65）──────────────────────────────────
@app.route("/api/notification/<int:notif_id>/snooze", methods=["POST"])
@login_required
def notification_snooze(notif_id):
    db.snooze_notification(notif_id, session["user_id"])
    return jsonify({"ok": True})

@app.route("/api/notification/<int:notif_id>/dismiss", methods=["POST"])
@login_required
def notification_dismiss(notif_id):
    db.dismiss_notification(notif_id, session["user_id"])
    return jsonify({"ok": True})


# ── Watchlist Actions ──────────────────────────────────
@app.route("/add", methods=["POST"])
@login_required
def add_stock():
    code   = request.form.get("code", "").strip().upper()
    name   = request.form.get("name", "").strip()
    notes  = request.form.get("desc", "").strip()
    market = request.form.get("market", "").strip()
    if not code or not name:
        flash("Stock code and name are required.", "warning")
        return redirect(url_for("index"))

    if not market:
        market = _detect_market(code)
    if market == "nz" and not code.endswith(".NZ"):
        code += ".NZ"

    db.add_user_stock(session["user_id"], code, name, market, notes=notes)

    # 分类公司类型（US-46）
    try:
        from scripts.classifier import classify_stock
        classify_stock(code)
    except Exception:
        pass

    # 触发后台分析 pipeline
    job_id = start_pipeline(session["user_id"], code, market)
    flash(f"{name} ({code}) 已添加，巴菲特正在分析中…", "success")
    return redirect(url_for("watchlist_page"))


@app.route("/remove/<code>", methods=["POST"])
@login_required
def remove_stock(code):
    db.remove_user_stock(session["user_id"], code)
    return redirect(url_for("watchlist_page"))


# ── 状态移动 API ───────────────────────────────────────
@app.route("/api/stock/<code>/status", methods=["POST"])
@login_required
def update_stock_status(code):
    """移动卡片到 watching / holding / sold，记录日期和价格。"""
    data      = request.get_json() or {}
    status    = data.get("status")
    if status not in ("watching", "holding", "sold"):
        return jsonify({"error": "invalid status"}), 400

    buy_date   = data.get("buy_date")
    buy_price  = data.get("buy_price")
    sell_date  = data.get("sell_date")
    sell_price = data.get("sell_price")

    # 自动快照当前巴菲特评级（移入持有时）
    entry_grade = None
    if status == "holding":
        analysis = db.get_latest_analysis(code, period="daily")
        if analysis:
            entry_grade = analysis.get("grade")

    db.update_stock_status(
        session["user_id"], code, status,
        buy_date=buy_date, buy_price=float(buy_price) if buy_price else None,
        sell_date=sell_date, sell_price=float(sell_price) if sell_price else None,
        entry_grade=entry_grade,
    )
    return jsonify({"ok": True, "entry_grade": entry_grade})


VALID_EVENT_TYPES = {
    "st_trigger", "st_lifted", "restructuring_announced", "restructuring_vote",
    "restructuring_approved", "rights_issue", "bonus_share", "name_change",
    "delist_warning", "delist_final", "major_shareholder_change",
    "scheme_risk",  # 第三方用该股票作传销/积分/直销载体的风险警告
}

@app.route("/api/stock/<path:code>/events", methods=["POST"])
@login_required
def add_stock_event(code):
    """手动录入一条股票事件（admin only）。"""
    if session.get("role") != "admin":
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    event_type = data.get("event_type", "")
    if event_type not in VALID_EVENT_TYPES:
        return jsonify({"error": f"invalid event_type: {event_type}"}), 400
    summary = (data.get("summary") or "").strip()
    if not summary:
        return jsonify({"error": "summary required"}), 400
    db.add_stock_event(
        code=code.upper(),
        event_type=event_type,
        event_date=data.get("event_date") or "",
        summary=summary,
        detail=data.get("detail"),
    )
    return jsonify({"ok": True})


# ── 算账面板 ──────────────────────────────────────────
@app.route("/watchlist/performance")
@login_required
def performance_page():
    rows     = db.get_performance_data(session["user_id"])
    quote_map = {q["code"]: q for q in db.get_quotes()}
    today    = datetime.now(CN_TZ).date()

    holdings = []
    sold     = []
    for r in rows:
        code      = r["code"]
        q         = quote_map.get(code, {})
        cur_price = q.get("price")
        market    = r.get("market", "cn")
        currency  = MARKET_CURRENCY.get(market, "$")

        # 持有天数
        ref_date  = r.get("buy_date") or r.get("added_at", "")[:10]
        try:
            from datetime import date as _date
            d0   = _date.fromisoformat(ref_date)
            days = (today - d0).days
        except Exception:
            days = None

        entry = r.get("buy_price") or (q.get("price") if not r.get("buy_date") else None)

        perf = {
            **r,
            "currency":    currency,
            "cur_price":   cur_price,
            "days_held":   days,
            "entry_price": entry,
            "return_pct":  None,
            "annualized":  None,
        }

        if entry and entry > 0:
            if r["status"] == "sold" and r.get("sell_price"):
                exit_p = r["sell_price"]
                ret    = (exit_p - entry) / entry * 100
            elif r["status"] == "holding" and cur_price:
                exit_p = cur_price
                ret    = (exit_p - entry) / entry * 100
            else:
                ret = None

            if ret is not None:
                perf["return_pct"] = ret
                if days and days > 0:
                    perf["annualized"] = ((1 + ret / 100) ** (365 / days) - 1) * 100

        if r["status"] == "holding":
            holdings.append(perf)
        else:
            sold.append(perf)

    # 胜率 & 评级准确率
    stats = _calc_performance_stats(holdings + sold)

    return render_template("performance.html",
        holdings=holdings, sold=sold, stats=stats,
        now=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"))


def _calc_performance_stats(rows):
    """计算胜率和评级准确率。"""
    with_return = [r for r in rows if r.get("return_pct") is not None]
    if not with_return:
        return {}

    winners    = [r for r in with_return if r["return_pct"] > 0]
    win_rate   = len(winners) / len(with_return) * 100

    # 评级准确率：买入时 B+ 以上的股票，实际结果是否为正
    graded     = [r for r in with_return if r.get("entry_grade") in ("A","B+","B")]
    grade_wins = [r for r in graded if r["return_pct"] > 0]
    grade_acc  = len(grade_wins) / len(graded) * 100 if graded else None

    avg_return = sum(r["return_pct"] for r in with_return) / len(with_return)

    return {
        "total":      len(with_return),
        "win_rate":   win_rate,
        "avg_return": avg_return,
        "grade_acc":  grade_acc,
        "grade_n":    len(graded),
    }


# ── Reports ───────────────────────────────────────────
@app.route("/report")
@app.route("/report/<date>")
@login_required
def report(date=None):
    period = request.args.get("period", "daily")
    row = db.get_report(date, period=period)
    if not row:
        # fallback: try daily
        row = db.get_report(date, period="daily")
    if not row:
        flash("No report available yet.", "info")
        return redirect(url_for("index"))
    all_reports = (db.list_reports(limit=10, period="daily") +
                   db.list_reports(limit=5, period="weekly") +
                   db.list_reports(limit=3, period="monthly") +
                   db.list_reports(limit=2, period="quarterly"))
    all_reports.sort(key=lambda r: r["date"], reverse=True)
    return render_template("report.html",
        report=row, reports=all_reports,
        now=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    )


# ── Accuracy / US-24 ─────────────────────────────────
@app.route("/report/accuracy")
@login_required
def accuracy():
    stats = db.get_accuracy_stats()
    return render_template("accuracy.html",
        stats=stats,
        now=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    )


# ── Fetch ─────────────────────────────────────────────
@app.route("/fetch", methods=["POST"])
@login_required
def fetch():
    script = os.path.join(os.path.dirname(__file__), "scripts", "stock_pipeline.py")
    try:
        result = subprocess.run([sys.executable, script],
            capture_output=True, text=True, timeout=180)
        return jsonify({"ok": result.returncode == 0,
                        "stdout": result.stdout[-3000:],
                        "stderr": result.stderr[-500:]})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "stdout": "", "stderr": "Timed out (180s)"})


# ── Run periodic digest on demand ─────────────────────
@app.route("/run-digest", methods=["POST"])
@login_required
def run_digest():
    mode = request.form.get("mode", "weekly")
    if mode not in ("weekly", "monthly", "quarterly"):
        flash("Invalid mode.", "warning")
        return redirect(url_for("index"))
    script = os.path.join(os.path.dirname(__file__), "scripts", "periodic_digest.py")
    try:
        result = subprocess.run([sys.executable, script, mode],
            capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            flash(f"{mode.capitalize()} digest generated.", "success")
        else:
            flash(f"Error: {result.stderr[-200:]}", "danger")
    except subprocess.TimeoutExpired:
        flash("Timed out (5 min).", "danger")
    return redirect(url_for("index"))


# ── Language toggle (works logged-in or out) ──────────
@app.route("/set-locale", methods=["POST"])
def set_locale():
    locale = request.form.get("locale", "en")
    if locale not in ("en", "zh"):
        locale = "en"
    session["locale"] = locale
    if session.get("user_id"):
        region = session.get("region", "nz")
        db.update_user_settings(session["user_id"], region, locale)
    _i18n_cache.clear()
    return redirect(request.referrer or url_for("index"))


# ── Settings ──────────────────────────────────────────
@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    uid = session["user_id"]
    if request.method == "POST":
        action = request.form.get("action", "general")

        if action == "general":
            region = request.form.get("region", "nz")
            locale = request.form.get("locale", "en")
            db.update_user_settings(uid, region, locale)
            session["region"] = region
            session["locale"] = locale
            _i18n_cache.clear()
            flash("Settings saved.", "success")

        elif action == "push":
            notify_daily = 1 if request.form.get("notify_daily") else 0
            wecom_key    = request.form.get("wecom_webhook", "").strip()
            db.upsert_push_settings(uid,
                notify_daily=notify_daily,
                wecom_webhook=wecom_key or None)
            flash("推送设置已保存。", "success")

        elif action == "test_push":
            ps  = db.get_push_settings(uid)
            key = (ps or {}).get("wecom_webhook", "")
            if not key:
                flash("请先填写 Server酱 SendKey。", "danger")
            else:
                import ssl, json, urllib.request
                try:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    payload = json.dumps({
                        "title": "股票雷达 · 推送测试",
                        "desp":  "推送配置正常 ✅ 你会在每个交易日 15:30 收到今日日报。"
                    }).encode()
                    req = urllib.request.Request(
                        f"https://sctapi.ftqq.com/{key}.send",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    )
                    with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
                        resp = json.loads(r.read().decode())
                    errno = resp.get("data", {}).get("errno", resp.get("code", -1))
                    if errno == 0:
                        flash("测试消息已发送，请查收微信。", "success")
                    else:
                        flash(f"Server酱 返回错误：{resp}", "danger")
                except Exception as e:
                    flash(f"发送失败：{e}", "danger")

        return redirect(url_for("settings"))

    push_settings = db.get_push_settings(uid) or {}
    return render_template("settings.html", push_settings=push_settings)


# ── API ───────────────────────────────────────────────
@app.route("/api/news/<code>")
@login_required
def api_news(code):
    return jsonify(db.get_news(code, days=7))


@app.route("/api/letter/<code>")
@login_required
def api_letter(code):
    analysis = db.get_latest_analysis(code, period="daily")
    if not analysis:
        return jsonify({"letter": None})
    return jsonify({
        "letter":      analysis.get("letter_html", ""),
        "grade":       analysis.get("grade"),
        "conclusion":  analysis.get("conclusion"),
        "date":        analysis.get("analysis_date"),
    })


@app.route("/api/analyze/<code>", methods=["POST"])
@login_required
def api_analyze(code):
    """全量 pipeline：重爬所有数据 + 重跑 LLM"""
    stock = db.get_stock(code)
    if not stock:
        return jsonify({"error": "stock not found"}), 404
    job_id = start_pipeline(session["user_id"], code, stock["market"])
    return jsonify({"job_id": job_id})


@app.route("/api/analyze-only/<code>", methods=["POST"])
@login_required
def api_analyze_only(code):
    """US-61：只跑定量评级（Layer 2，无 Groq），~3s"""
    from scripts.pipeline import start_quant_only
    stock = db.get_stock(code)
    if not stock:
        return jsonify({"error": "stock not found"}), 404
    job_id = start_quant_only(session["user_id"], code, stock["market"])
    return jsonify({"job_id": job_id})


@app.route("/api/generate-letter/<code>", methods=["POST"])
@login_required
def api_generate_letter(code):
    """US-61：只生成巴菲特股东信（Layer 3 Groq），~30s"""
    from scripts.pipeline import start_letter_only
    stock = db.get_stock(code)
    if not stock:
        return jsonify({"error": "stock not found"}), 404
    job_id = start_letter_only(session["user_id"], code, stock["market"])
    return jsonify({"job_id": job_id})


@app.route("/api/refresh-news/<code>", methods=["POST"])
@login_required
def api_refresh_news(code):
    """US-45：只更新新闻，1小时内重复触发返回缓存"""
    from scripts.pipeline import start_news_update
    stock = db.get_stock(code)
    if not stock:
        return jsonify({"error": "stock not found"}), 404
    job_id = start_news_update(session["user_id"], code, stock["market"])
    return jsonify({"job_id": job_id})


@app.route("/api/job/<int:job_id>")
@login_required
def api_job(job_id):
    """前端轮询 pipeline 状态"""
    job = db.get_job(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    analysis = {}
    if job["status"] == "done" and job.get("code"):
        result = db.get_latest_analysis(job["code"])
        if result:
            analysis = {
                "grade":      result.get("grade"),
                "conclusion": result.get("conclusion"),
                "reasoning":  result.get("reasoning","")[:150],
                "letter":     result.get("letter_html",""),
            }
    return jsonify({
        "status":   job["status"],
        "code":     job.get("code"),
        "log":      job.get("log",""),
        "error":    job.get("error"),
        "analysis": analysis,
    })


@app.route("/api/job/<int:job_id>/cancel", methods=["POST"])
@login_required
def api_job_cancel(job_id):
    """强制将 running/pending 的 job 标记为 done，让前端停止轮询。"""
    job = db.get_job(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    if job["status"] in ("running", "pending"):
        db.update_job(job_id, status="done", log=(job.get("log") or "") + "\n⚠️ 用户手动取消")
    return jsonify({"status": "cancelled"})


@app.route("/api/analyze-batch", methods=["POST"])
@login_required
def api_analyze_batch():
    """US-12：批量触发选中股票各自的 pipeline"""
    codes = request.json.get("codes", [])
    if not codes:
        return jsonify({"error": "no codes"}), 400
    job_ids = []
    for code in codes[:20]:  # 最多20只防止滥用
        stock = db.get_stock(code)
        if not stock:
            continue
        job_id = start_pipeline(session["user_id"], code, stock["market"])
        job_ids.append({"code": code, "job_id": job_id})
    return jsonify({"job_ids": job_ids})


@app.route("/api/rerun-all", methods=["POST"])
@login_required
def api_rerun_all():
    """Admin only：后台重跑所有自选股的完整 pipeline，顺序执行，1只/次避免Groq限速。"""
    if session.get("role") != "admin":
        return jsonify({"error": "forbidden"}), 403

    import threading
    from scripts.pipeline import run_pipeline

    def _run():
        codes = db.all_watched_codes()
        import time
        for code in codes:
            stock = db.get_stock(code)
            if not stock:
                continue
            job_id = db.create_job(user_id=None, code=code, job_type="rerun_all")
            run_pipeline(job_id, code, stock.get("market", "cn"), force=False)
            time.sleep(5)  # 给 Groq token 配额留恢复时间

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    count = len(db.all_watched_codes())
    # 每只股票：数据拉取 ~20s + LLM ~10s + sleep 5s = ~35s；Groq 限流时加 65s
    return jsonify({"ok": True, "message": f"已启动，共 {count} 只股票，顺利约 {count * 35 // 60} 分钟，限流时最多 {count * 100 // 60} 分钟"})


@app.route("/admin/users")
@login_required
def admin_users():
    if session.get("role") != "admin":
        return "Forbidden", 403
    users = db.list_users()
    # 附上每个用户的推送设置
    for u in users:
        u["push"] = db.get_push_settings(u["id"]) or {}
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/<int:target_uid>", methods=["GET", "POST"])
@login_required
def admin_user_detail(target_uid):
    if session.get("role") != "admin":
        return "Forbidden", 403

    target = db.get_user_by_id(target_uid)
    if not target:
        return "User not found", 404

    if request.method == "POST":
        action = request.form.get("action")

        if action == "push":
            notify_daily = 1 if request.form.get("notify_daily") else 0
            wecom_key    = request.form.get("wecom_webhook", "").strip()
            db.upsert_push_settings(target_uid,
                notify_daily=notify_daily,
                wecom_webhook=wecom_key or None)
            flash(f"已更新 {target['email']} 的推送设置。", "success")

        elif action == "test_push":
            ps  = db.get_push_settings(target_uid)
            key = (ps or {}).get("wecom_webhook", "")
            if not key:
                flash("该用户未设置 Server酱 key。", "danger")
            else:
                import ssl, json, urllib.request
                try:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    payload = json.dumps({
                        "title": "股票雷达 · 推送测试",
                        "desp":  f"管理员测试推送 ✅\n用户：{target['email']}"
                    }).encode()
                    req = urllib.request.Request(
                        f"https://sctapi.ftqq.com/{key}.send",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    )
                    with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
                        resp = json.loads(r.read().decode())
                    errno = resp.get("data", {}).get("errno", resp.get("code", -1))
                    if errno == 0:
                        flash("测试消息已发送。", "success")
                    else:
                        flash(f"Server酱 返回：{resp}", "danger")
                except Exception as e:
                    flash(f"发送失败：{e}", "danger")

        return redirect(url_for("admin_user_detail", target_uid=target_uid))

    push    = db.get_push_settings(target_uid) or {}
    wl      = db.get_user_watchlist(target_uid) or []
    return render_template("admin_user_detail.html",
                           target=target, push=push, watchlist=wl)


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True}), 200


# ── TEMPORARY DEBUG — remove after diagnosis ──────────
@app.errorhandler(500)
def debug_500(e):
    tb = traceback.format_exc()
    return f"<pre style='white-space:pre-wrap;word-break:break-all'>{tb}</pre>", 500


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/api/generate-brief", methods=["POST"])
@login_required
def api_generate_brief():
    """手动触发组合日报 LLM 合成，存入 portfolio_analysis 表。"""
    user_id = session["user_id"]
    watchlist = db.get_user_watchlist(user_id)
    stocks_data = []
    for row in watchlist:
        code   = row.get("stock_code") or row.get("code")
        market = row.get("market") or _detect_market(code)
        a  = db.get_latest_analysis(code, period="daily")
        ff = db.get_fund_flow(code) if market == "cn" else {}
        if a:
            stocks_data.append({
                "code":       code,
                "name":       row.get("name", code),
                "grade":      a.get("grade"),
                "conclusion": a.get("conclusion"),
                "reasoning":  a.get("reasoning"),
                "moat":       a.get("moat"),
                "behavioral": a.get("behavioral"),
                "main_net":   ff.get("main_net") if ff else None,
            })

    snap = db.get_market_snapshot()
    market_data = snap.get("data", {}) if snap else {}
    locale = session.get("locale", "zh")

    try:
        macro, summary = generate_portfolio_brief(stocks_data, market_data, locale=locale)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    db.save_portfolio_brief(user_id, today, macro, summary)
    return jsonify({"ok": True, "macro": macro, "summary": summary})


@app.route("/api/search")
@login_required
def api_search():
    """股票模糊搜索：AKShare(A股) + yfinance(其他)"""
    q = request.args.get("q", "").strip()
    if len(q) < 1:
        return jsonify([])
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
    import stock_search as _ss
    # 如果 A股数据还在后台加载中（且查询像 A股），告知前端
    has_cn = any('\u4e00' <= c <= '\u9fff' for c in q) or q.isdigit()
    if has_cn and _ss._CN_LOADING and _ss._CN_CACHE is None:
        return jsonify({"loading": True})
    return jsonify(_ss.search(q, limit=10))


if __name__ == "__main__":
    db.init_db()
    db.expire_stale_jobs()
    port = int(os.environ.get("PORT", 5001))
    print(f"🚀 Personal Buffett → http://127.0.0.1:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
