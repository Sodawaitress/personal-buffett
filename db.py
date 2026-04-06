"""
私人巴菲特 · 数据库层
新 schema v2 — 按 PRODUCT.md 三、数据库设计
"""
import sqlite3, json, hashlib, os
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "radar.db")
CN_TZ   = timezone(timedelta(hours=8))

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as c:
        c.executescript("""
        -- 用户
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            email           TEXT UNIQUE NOT NULL,
            password_hash   TEXT,
            display_name    TEXT,
            avatar_url      TEXT,
            locale          TEXT DEFAULT 'en',
            region          TEXT DEFAULT 'nz',
            role            TEXT DEFAULT 'member',
            onboarding_done INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now')),
            last_login      TEXT
        );

        CREATE TABLE IF NOT EXISTS user_oauth (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
            provider    TEXT,
            provider_id TEXT,
            UNIQUE(provider, provider_id)
        );

        CREATE TABLE IF NOT EXISTS user_push_settings (
            user_id           INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            discord_webhook   TEXT,
            wecom_webhook     TEXT,
            bear_enabled      INTEGER DEFAULT 0,
            email_enabled     INTEGER DEFAULT 0,
            notify_daily      INTEGER DEFAULT 1,
            notify_weekly     INTEGER DEFAULT 1,
            notify_monthly    INTEGER DEFAULT 1,
            notify_quarterly  INTEGER DEFAULT 1,
            notify_on_add     INTEGER DEFAULT 1,
            daily_time_cst    TEXT DEFAULT '08:00'
        );

        -- 股票
        CREATE TABLE IF NOT EXISTS stocks (
            code         TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            name_cn      TEXT,
            market       TEXT,
            exchange     TEXT,
            sector       TEXT,
            currency     TEXT,
            last_fetched TEXT
        );

        CREATE TABLE IF NOT EXISTS user_watchlist (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
            stock_code  TEXT REFERENCES stocks(code) ON DELETE CASCADE,
            added_at    TEXT DEFAULT (datetime('now')),
            notes       TEXT,
            status      TEXT DEFAULT 'watching',
            buy_date    TEXT,
            buy_price   REAL,
            sell_date   TEXT,
            sell_price  REAL,
            entry_grade TEXT,
            UNIQUE(user_id, stock_code)
        );

        CREATE TABLE IF NOT EXISTS stock_prices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT REFERENCES stocks(code),
            price       REAL,
            change_pct  REAL,
            volume      REAL,
            market_cap  REAL,
            pe_ratio    REAL,
            pb_ratio    REAL,
            fetched_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS stock_fund_flow (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT,
            date        TEXT,
            main_net    REAL,
            main_ratio  REAL,
            UNIQUE(code, date)
        );

        -- 新闻与分析
        CREATE TABLE IF NOT EXISTS stock_news (
            id           TEXT PRIMARY KEY,
            code         TEXT REFERENCES stocks(code),
            title        TEXT,
            link         TEXT,
            source       TEXT,
            sentiment    REAL,
            publish_time TEXT,
            fetched_date TEXT
        );

        CREATE TABLE IF NOT EXISTS analysis_results (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            code                 TEXT REFERENCES stocks(code),
            period               TEXT,
            analysis_date        TEXT,
            moat                 TEXT,
            management           TEXT,
            valuation            TEXT,
            fund_flow_summary    TEXT,
            behavioral           TEXT,
            tbtf                 TEXT,
            macro_sensitivity    TEXT,
            conclusion           TEXT,
            grade                TEXT,
            reasoning            TEXT,
            letter_html          TEXT,
            raw_output           TEXT,
            feat_price_momentum  REAL,
            feat_sentiment_avg   REAL,
            feat_fund_flow_net   REAL,
            feat_pe_vs_hist      REAL,
            feat_fear_greed      INTEGER,
            label_7d_return      REAL,
            label_30d_return     REAL,
            UNIQUE(code, period, analysis_date)
        );

        CREATE TABLE IF NOT EXISTS reports (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_date TEXT,
            period        TEXT DEFAULT 'daily',
            html          TEXT,
            md            TEXT,
            created_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(analysis_date, period)
        );

        -- 系统数据
        CREATE TABLE IF NOT EXISTS market_data (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            data_type  TEXT,
            payload    TEXT,
            fetched_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS market_news (
            id           TEXT PRIMARY KEY,
            region       TEXT,
            category     TEXT,
            title        TEXT,
            link         TEXT,
            source       TEXT,
            publish_time TEXT,
            fetched_date TEXT
        );

        -- 基本面财务快照（每次 pipeline 运行后更新）
        CREATE TABLE IF NOT EXISTS stock_fundamentals (
            code             TEXT PRIMARY KEY,
            annual_json      TEXT,    -- JSON: [{year, roe, net_margin, debt_ratio, profit_growth}]
            pe_current       REAL,
            pe_percentile_5y INTEGER,
            pb_current       REAL,
            pb_percentile_5y INTEGER,
            signals_json     TEXT,    -- JSON: {pledge_ratio, margin_balance, margin_change_pct, inst_*, fcf_quality_avg}
            updated_at       TEXT DEFAULT (datetime('now'))
        );

        -- Pipeline 任务追踪
        CREATE TABLE IF NOT EXISTS pipeline_jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER REFERENCES users(id),
            code        TEXT,
            job_type    TEXT,
            status      TEXT DEFAULT 'pending',
            log         TEXT,
            started_at  TEXT,
            finished_at TEXT,
            error       TEXT
        );
        """)


# ══════════════════════════════════════════════════
# 用户
# ══════════════════════════════════════════════════

def create_user(email, password_hash=None, display_name=None, avatar_url=None, role="member"):
    with get_conn() as c:
        # 第一个注册的用户自动成为 admin
        count = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            role = "admin"
        c.execute("""
            INSERT OR IGNORE INTO users(email, password_hash, display_name, avatar_url, role)
            VALUES (?,?,?,?,?)
        """, (email, password_hash, display_name, avatar_url, role))

def get_user_by_email(email):
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id):
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

def user_exists(email):
    with get_conn() as c:
        return bool(c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone())

def update_user_settings(user_id, region=None, locale=None):
    fields, vals = [], []
    if region is not None:
        fields.append("region=?"); vals.append(region)
    if locale is not None:
        fields.append("locale=?"); vals.append(locale)
    if not fields:
        return
    vals.append(user_id)
    with get_conn() as c:
        c.execute(f"UPDATE users SET {','.join(fields)} WHERE id=?", vals)

def update_last_login(user_id):
    with get_conn() as c:
        c.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user_id,))

def get_or_create_oauth_user(provider, provider_id, email, display_name, avatar_url):
    """Find or create user from OAuth. Returns user dict."""
    with get_conn() as c:
        # 已有 OAuth 绑定
        row = c.execute("""
            SELECT u.* FROM users u
            JOIN user_oauth o ON o.user_id = u.id
            WHERE o.provider=? AND o.provider_id=?
        """, (provider, provider_id)).fetchone()
        if row:
            return dict(row)

        # 已有同 email 账号 → 绑定 OAuth
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if row:
            user_id = row["id"]
            c.execute("INSERT OR IGNORE INTO user_oauth(user_id,provider,provider_id) VALUES(?,?,?)",
                      (user_id, provider, provider_id))
            c.execute("UPDATE users SET display_name=?,avatar_url=? WHERE id=?",
                      (display_name, avatar_url, user_id))
            return dict(c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())

        # 新用户
        count = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        role  = "admin" if count == 0 else "member"
        c.execute("""
            INSERT INTO users(email, display_name, avatar_url, role)
            VALUES (?,?,?,?)
        """, (email, display_name, avatar_url, role))
        user_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute("INSERT INTO user_oauth(user_id,provider,provider_id) VALUES(?,?,?)",
                  (user_id, provider, provider_id))
        return dict(c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())

def list_users():
    with get_conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM users ORDER BY created_at")]

def complete_onboarding(user_id):
    with get_conn() as c:
        c.execute("UPDATE users SET onboarding_done=1 WHERE id=?", (user_id,))


# ══════════════════════════════════════════════════
# 推送设置
# ══════════════════════════════════════════════════

def get_push_settings(user_id):
    with get_conn() as c:
        row = c.execute("SELECT * FROM user_push_settings WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else {}

def upsert_push_settings(user_id, **kwargs):
    current = get_push_settings(user_id)
    if not current:
        with get_conn() as c:
            c.execute("INSERT INTO user_push_settings(user_id) VALUES(?)", (user_id,))
    if not kwargs:
        return
    fields = ", ".join(f"{k}=?" for k in kwargs)
    vals   = list(kwargs.values()) + [user_id]
    with get_conn() as c:
        c.execute(f"UPDATE user_push_settings SET {fields} WHERE user_id=?", vals)


# ══════════════════════════════════════════════════
# 股票基础信息
# ══════════════════════════════════════════════════

def upsert_stock(code, name, market, name_cn=None, exchange=None, sector=None, currency=None):
    currency = currency or {"nz":"NZD","cn":"CNY","hk":"HKD","us":"USD"}.get(market,"USD")
    with get_conn() as c:
        c.execute("""
            INSERT INTO stocks(code,name,name_cn,market,exchange,sector,currency,last_fetched)
            VALUES(?,?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(code) DO UPDATE SET
              name=excluded.name, name_cn=COALESCE(excluded.name_cn,name_cn),
              market=excluded.market, exchange=COALESCE(excluded.exchange,exchange),
              sector=COALESCE(excluded.sector,sector),
              currency=excluded.currency, last_fetched=excluded.last_fetched
        """, (code, name, name_cn, market, exchange, sector, currency))

def get_stock(code):
    with get_conn() as c:
        row = c.execute("SELECT * FROM stocks WHERE code=?", (code,)).fetchone()
        return dict(row) if row else None


# ══════════════════════════════════════════════════
# 用户自选股
# ══════════════════════════════════════════════════

def get_user_watchlist(user_id):
    with get_conn() as c:
        return [dict(r) for r in c.execute("""
            SELECT w.*, s.name, s.name_cn, s.market, s.currency, s.sector
            FROM user_watchlist w
            JOIN stocks s ON s.code = w.stock_code
            WHERE w.user_id=?
            ORDER BY w.added_at
        """, (user_id,))]

def add_user_stock(user_id, code, name, market, notes="", name_cn=None,
                   exchange=None, sector=None, currency=None):
    upsert_stock(code, name, market, name_cn=name_cn, exchange=exchange,
                 sector=sector, currency=currency)
    with get_conn() as c:
        c.execute("""
            INSERT OR IGNORE INTO user_watchlist(user_id, stock_code, notes)
            VALUES(?,?,?)
        """, (user_id, code, notes))

def remove_user_stock(user_id, code):
    with get_conn() as c:
        c.execute("DELETE FROM user_watchlist WHERE user_id=? AND stock_code=?",
                  (user_id, code))

def all_watched_codes():
    """所有用户所有自选股的去重代码列表（pipeline 用）"""
    with get_conn() as c:
        return [r[0] for r in c.execute(
            "SELECT DISTINCT stock_code FROM user_watchlist")]


# ══════════════════════════════════════════════════
# 价格快照
# ══════════════════════════════════════════════════

def _guess_market(code):
    import re
    if code.endswith(".NZ"): return "nz"
    if code.endswith(".HK"): return "hk"
    if re.match(r"^\d{6}$", code): return "cn"
    return "us"

def upsert_price(code, price, change_pct=None, volume=None,
                 market_cap=None, pe_ratio=None, pb_ratio=None):
    # 外键约束：确保 stocks 表有此 code
    with get_conn() as c:
        c.execute("""
            INSERT OR IGNORE INTO stocks(code, name, market, currency)
            VALUES(?, ?, ?, 'CNY')
        """, (code, code, _guess_market(code)))
    with get_conn() as c:
        c.execute("""
            INSERT INTO stock_prices(code,price,change_pct,volume,market_cap,pe_ratio,pb_ratio)
            VALUES(?,?,?,?,?,?,?)
        """, (code, price, change_pct, volume, market_cap, pe_ratio, pb_ratio))

def get_latest_price(code):
    with get_conn() as c:
        row = c.execute("""
            SELECT * FROM stock_prices WHERE code=?
            ORDER BY fetched_at DESC LIMIT 1
        """, (code,)).fetchone()
        return dict(row) if row else {}

def get_price_history(code, days=30):
    with get_conn() as c:
        return [dict(r) for r in c.execute("""
            SELECT * FROM stock_prices WHERE code=?
            ORDER BY fetched_at DESC LIMIT ?
        """, (code, days))]


# ══════════════════════════════════════════════════
# 资金流向
# ══════════════════════════════════════════════════

def upsert_fund_flow(code, date, main_net, main_ratio):
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO stocks(code,name,market,currency) VALUES(?,?,?,'CNY')",
                  (code, code, _guess_market(code)))
        c.execute("""
            INSERT OR REPLACE INTO stock_fund_flow(code,date,main_net,main_ratio)
            VALUES(?,?,?,?)
        """, (code, date, main_net, main_ratio))

def get_fund_flow(code):
    with get_conn() as c:
        row = c.execute("""
            SELECT * FROM stock_fund_flow WHERE code=?
            ORDER BY date DESC LIMIT 1
        """, (code,)).fetchone()
        return dict(row) if row else {}

def upsert_fundamentals(code, annual, pe_current=None, pe_percentile_5y=None,
                        pb_current=None, pb_percentile_5y=None, signals=None):
    # Migrate: add signals_json column if missing (SQLite doesn't support IF NOT EXISTS on ALTER)
    try:
        with get_conn() as c:
            c.execute("ALTER TABLE stock_fundamentals ADD COLUMN signals_json TEXT")
    except Exception:
        pass  # column already exists

    with get_conn() as c:
        c.execute("""
            INSERT INTO stock_fundamentals
                (code, annual_json, pe_current, pe_percentile_5y, pb_current, pb_percentile_5y,
                 signals_json, updated_at)
            VALUES (?,?,?,?,?,?,?, datetime('now'))
            ON CONFLICT(code) DO UPDATE SET
                annual_json=excluded.annual_json,
                pe_current=excluded.pe_current,
                pe_percentile_5y=excluded.pe_percentile_5y,
                pb_current=excluded.pb_current,
                pb_percentile_5y=excluded.pb_percentile_5y,
                signals_json=COALESCE(excluded.signals_json, signals_json),
                updated_at=excluded.updated_at
        """, (code, json.dumps(annual, ensure_ascii=False),
              pe_current, pe_percentile_5y, pb_current, pb_percentile_5y,
              json.dumps(signals, ensure_ascii=False) if signals else None))

def upsert_signals(code, signals: dict):
    """合并更新信号字段（不覆盖已有 key，只更新/新增传入的 key）。"""
    try:
        with get_conn() as c:
            c.execute("ALTER TABLE stock_fundamentals ADD COLUMN signals_json TEXT")
    except Exception:
        pass
    with get_conn() as c:
        # 先读已有
        row = c.execute("SELECT signals_json FROM stock_fundamentals WHERE code=?", (code,)).fetchone()
        existing = {}
        if row and row[0]:
            try:
                existing = json.loads(row[0])
            except Exception:
                pass
        merged = {**existing, **signals}
        c.execute("""
            INSERT INTO stock_fundamentals(code, annual_json, signals_json, updated_at)
            VALUES (?, '[]', ?, datetime('now'))
            ON CONFLICT(code) DO UPDATE SET
                signals_json=excluded.signals_json,
                updated_at=excluded.updated_at
        """, (code, json.dumps(merged, ensure_ascii=False)))

def get_fundamentals(code):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM stock_fundamentals WHERE code=?", (code,)
        ).fetchone()
        if not row:
            return {}
        d = dict(row)
        try:
            d["annual"] = json.loads(d.get("annual_json") or "[]")
        except Exception:
            d["annual"] = []
        try:
            d["signals"] = json.loads(d.get("signals_json") or "{}")
        except Exception:
            d["signals"] = {}
        return d


def get_fund_flow_history(code, days=30):
    with get_conn() as c:
        return [dict(r) for r in c.execute("""
            SELECT date, main_net, main_ratio FROM stock_fund_flow
            WHERE code=?
            ORDER BY date ASC LIMIT ?
        """, (code, days))]


# ══════════════════════════════════════════════════
# 新闻
# ══════════════════════════════════════════════════

def upsert_stock_news(code, title, source, link, publish_time, fetched_date):
    nid = hashlib.md5(f"{title}{link}".encode()).hexdigest()
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO stocks(code,name,market,currency) VALUES(?,?,?,'CNY')",
                  (code, code, _guess_market(code)))
        c.execute("""
            INSERT OR IGNORE INTO stock_news(id,code,title,link,source,publish_time,fetched_date)
            VALUES(?,?,?,?,?,?,?)
        """, (nid, code, title, link, source, publish_time, fetched_date))
    return nid

def get_stock_news(code, days=7):
    cutoff = (datetime.now(CN_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as c:
        return [dict(r) for r in c.execute("""
            SELECT * FROM stock_news
            WHERE code=? AND fetched_date>=?
            ORDER BY publish_time DESC LIMIT 20
        """, (code, cutoff))]

def upsert_market_news(region, category, title, link, source, publish_time, fetched_date):
    nid = hashlib.md5(f"{title}{link}".encode()).hexdigest()
    with get_conn() as c:
        c.execute("""
            INSERT OR IGNORE INTO market_news(id,region,category,title,link,source,publish_time,fetched_date)
            VALUES(?,?,?,?,?,?,?,?)
        """, (nid, region, category, title, link, source, publish_time, fetched_date))

def get_market_news(region, category=None, days=3):
    cutoff = (datetime.now(CN_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as c:
        if category:
            return [dict(r) for r in c.execute("""
                SELECT * FROM market_news
                WHERE region=? AND category=? AND fetched_date>=?
                ORDER BY publish_time DESC LIMIT 10
            """, (region, category, cutoff))]
        return [dict(r) for r in c.execute("""
            SELECT * FROM market_news
            WHERE region=? AND fetched_date>=?
            ORDER BY publish_time DESC LIMIT 20
        """, (region, cutoff))]


# ══════════════════════════════════════════════════
# 分析结果
# ══════════════════════════════════════════════════

def save_analysis(code, period, analysis_date, **kwargs):
    cols = ["code","period","analysis_date"] + list(kwargs.keys())
    vals = [code, period, analysis_date] + list(kwargs.values())
    placeholders = ",".join(["?"]*len(vals))
    update_fields = ",".join(f"{k}=excluded.{k}" for k in kwargs)
    with get_conn() as c:
        c.execute(f"""
            INSERT INTO analysis_results({",".join(cols)}) VALUES({placeholders})
            ON CONFLICT(code,period,analysis_date) DO UPDATE SET {update_fields}
        """, vals)

def get_latest_analysis(code, period="daily"):
    with get_conn() as c:
        row = c.execute("""
            SELECT * FROM analysis_results
            WHERE code=? AND period=?
            ORDER BY analysis_date DESC LIMIT 1
        """, (code, period)).fetchone()
        return dict(row) if row else {}

def get_analysis_history(code, period="daily", limit=10):
    with get_conn() as c:
        return [dict(r) for r in c.execute("""
            SELECT * FROM analysis_results
            WHERE code=? AND period=?
            ORDER BY analysis_date DESC LIMIT ?
        """, (code, period, limit))]

def get_news_range(code, days=7):
    """兼容旧代码，同 get_stock_news"""
    return get_stock_news(code, days=days)


# ══════════════════════════════════════════════════
# 报告（周/月/季）
# ══════════════════════════════════════════════════

def save_report(date, html, md, period="daily"):
    with get_conn() as c:
        c.execute("""
            INSERT INTO reports(analysis_date,period,html,md) VALUES(?,?,?,?)
            ON CONFLICT(analysis_date,period) DO UPDATE SET html=excluded.html, md=excluded.md
        """, (date, period, html, md))

def get_report(date=None, period="daily"):
    with get_conn() as c:
        if date:
            row = c.execute("""
                SELECT * FROM reports WHERE analysis_date=? AND period=?
            """, (date, period)).fetchone()
        else:
            row = c.execute("""
                SELECT * FROM reports WHERE period=? ORDER BY analysis_date DESC LIMIT 1
            """, (period,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["date"] = d.get("analysis_date")  # 兼容旧模板
        return d

def list_reports(limit=30, period=None):
    with get_conn() as c:
        if period:
            rows = c.execute("""
                SELECT analysis_date as date, period, created_at FROM reports
                WHERE period=? ORDER BY analysis_date DESC LIMIT ?
            """, (period, limit)).fetchall()
        else:
            rows = c.execute("""
                SELECT analysis_date as date, period, created_at FROM reports
                ORDER BY analysis_date DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ══════════════════════════════════════════════════
# 宏观数据快照
# ══════════════════════════════════════════════════

def save_market_data(data_type, payload_dict):
    with get_conn() as c:
        c.execute("""
            INSERT INTO market_data(data_type, payload) VALUES(?,?)
        """, (data_type, json.dumps(payload_dict, ensure_ascii=False)))

def get_latest_market_data(data_type):
    with get_conn() as c:
        row = c.execute("""
            SELECT * FROM market_data WHERE data_type=?
            ORDER BY fetched_at DESC LIMIT 1
        """, (data_type,)).fetchone()
        if not row:
            return {}
        return json.loads(row["payload"])

def get_market_snapshot(market=None, date=None):
    """兼容旧代码：返回合并的宏观快照"""
    types = ["nzx50","fear_greed","cny_usd","cn_indices","commodities"]
    result = {}
    for t in types:
        d = get_latest_market_data(t)
        if d:
            result[t] = d
    return {"data": result, "fetched_at": datetime.now(CN_TZ).isoformat()} if result else None


# ══════════════════════════════════════════════════
# Pipeline 任务
# ══════════════════════════════════════════════════

def create_job(user_id, code, job_type):
    with get_conn() as c:
        c.execute("""
            INSERT INTO pipeline_jobs(user_id,code,job_type,status,started_at)
            VALUES(?,?,?,'pending',datetime('now'))
        """, (user_id, code, job_type))
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]

def update_job(job_id, status, log=None, error=None):
    finished = "datetime('now')" if status in ("done","failed") else "NULL"
    with get_conn() as c:
        c.execute(f"""
            UPDATE pipeline_jobs
            SET status=?, log=COALESCE(?,log),
                error=COALESCE(?,error),
                finished_at=({finished})
            WHERE id=?
        """, (status, log, error, job_id))

def get_job(job_id):
    with get_conn() as c:
        row = c.execute("SELECT * FROM pipeline_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None


# ══════════════════════════════════════════════════
# 兼容旧代码的别名
# ══════════════════════════════════════════════════

def upsert_news(code, title, source, link, publish_time, fetched_date):
    return upsert_stock_news(code, title, source, link, publish_time, fetched_date)

def get_news(code, days=3):
    return get_stock_news(code, days=days)

def upsert_intl_news(scope, title, label, link, source, fetched_date):
    return upsert_market_news("global", scope, title, link, source, "", fetched_date)

def upsert_market_snapshot(date, market, data_dict):
    for k, v in data_dict.items():
        save_market_data(k, v)

def upsert_quote(code, date, price, change_pct, amount):
    upsert_price(code, price, change_pct=change_pct, volume=amount)

def get_quotes(date=None):
    codes = all_watched_codes()
    return [get_latest_price(c) for c in codes if get_latest_price(c)]

def get_accuracy_stats():
    """
    US-24: 返回预测准确率统计数据。
    判定规则：买入+涨>3%=正确, 买入+跌>3%=错误, 其余类似推导
    """
    THRESHOLD = 3.0
    with get_conn() as c:
        # 所有有标注的 daily 分析
        rows = c.execute("""
            SELECT ar.code, s.name, ar.analysis_date, ar.conclusion, ar.grade,
                   ar.label_7d_return, ar.label_30d_return, ar.reasoning
            FROM analysis_results ar
            JOIN stocks s ON s.code = ar.code
            WHERE ar.period='daily'
              AND (ar.label_7d_return IS NOT NULL OR ar.label_30d_return IS NOT NULL)
            ORDER BY ar.analysis_date DESC
        """).fetchall()

    def verdict(conclusion, actual_return):
        if actual_return is None:
            return None
        if conclusion in ("买入",):
            if actual_return > THRESHOLD:   return "correct"
            if actual_return < -THRESHOLD:  return "wrong"
            return "neutral"
        elif conclusion in ("减持", "卖出"):
            if actual_return < -THRESHOLD:  return "correct"
            if actual_return > THRESHOLD:   return "wrong"
            return "neutral"
        else:  # 持有
            if abs(actual_return) <= THRESHOLD: return "correct"
            return "neutral"

    by_type = {}
    recent_wrong = []

    for row in rows:
        d = dict(row)
        for horizon, col in [("7d", "label_7d_return"), ("30d", "label_30d_return")]:
            ret = d.get(col)
            key = f"{d['conclusion']}_{horizon}"
            if key not in by_type:
                by_type[key] = {"conclusion": d["conclusion"], "horizon": horizon,
                                "total": 0, "correct": 0, "wrong": 0, "neutral": 0}
            v = verdict(d["conclusion"], ret)
            if v:
                by_type[key]["total"] += 1
                by_type[key][v] += 1
                if v == "wrong" and horizon == "7d":
                    recent_wrong.append({
                        "code": d["code"],
                        "name": d["name"],
                        "date": d["analysis_date"],
                        "conclusion": d["conclusion"],
                        "return_7d": d["label_7d_return"],
                        "reasoning": (d["reasoning"] or "")[:80],
                    })

    # 计算准确率
    stats = []
    for key, s in by_type.items():
        acc = round(s["correct"] / s["total"] * 100) if s["total"] > 0 else None
        stats.append({**s, "accuracy_pct": acc, "key": key})
    stats.sort(key=lambda x: (x["conclusion"], x["horizon"]))

    return {
        "by_type": stats,
        "recent_wrong": recent_wrong[:10],
        "total_labelled": len(rows),
    }


def update_stock_status(user_id, code, status,
                        buy_date=None, buy_price=None,
                        sell_date=None, sell_price=None,
                        entry_grade=None):
    """移动卡片：更新持有状态 + 买入/卖出记录。"""
    fields = {"status": status}
    if status == "holding":
        if buy_date:    fields["buy_date"]    = buy_date
        if buy_price:   fields["buy_price"]   = buy_price
        if entry_grade: fields["entry_grade"] = entry_grade
        # 移入持有时清空卖出记录（重新买入场景）
        fields["sell_date"]  = None
        fields["sell_price"] = None
    elif status == "sold":
        if sell_date:  fields["sell_date"]  = sell_date
        if sell_price: fields["sell_price"] = sell_price
    elif status == "watching":
        # 移回观察区：清空所有交易记录
        fields.update({"buy_date": None, "buy_price": None,
                        "sell_date": None, "sell_price": None,
                        "entry_grade": None})
    set_clause = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as c:
        c.execute(
            f"UPDATE user_watchlist SET {set_clause} WHERE user_id=? AND stock_code=?",
            list(fields.values()) + [user_id, code]
        )


def get_performance_data(user_id):
    """返回用户持有/已卖出股票的绩效数据（不含纯观察）。"""
    with get_conn() as c:
        rows = c.execute("""
            SELECT w.stock_code AS code, s.name, s.market, w.status,
                   w.buy_date, w.buy_price, w.sell_date, w.sell_price,
                   w.entry_grade, w.added_at
            FROM user_watchlist w
            JOIN stocks s ON s.code = w.stock_code
            WHERE w.user_id=? AND w.status IN ('holding','sold')
            ORDER BY w.buy_date DESC NULLS LAST
        """, (user_id,)).fetchall()
    return [dict(r) for r in rows]


def _migrate():
    """向旧 DB 补加新字段（ALTER TABLE 幂等）。"""
    new_cols = [
        ("user_watchlist", "status",      "TEXT DEFAULT 'watching'"),
        ("user_watchlist", "buy_date",    "TEXT"),
        ("user_watchlist", "buy_price",   "REAL"),
        ("user_watchlist", "sell_date",   "TEXT"),
        ("user_watchlist", "sell_price",  "REAL"),
        ("user_watchlist", "entry_grade", "TEXT"),
    ]
    with get_conn() as c:
        for table, col, typedef in new_cols:
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            except Exception:
                pass  # 字段已存在，忽略


if __name__ == "__main__":
    init_db()
    print(f"DB ready: {DB_PATH}")
