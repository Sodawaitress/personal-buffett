#!/usr/bin/env python3
"""
DB 迁移脚本：旧 radar.db → 新 schema（按 PRODUCT.md 三、数据库设计）
运行一次即可，之后用新 db.py。
"""
import sqlite3, shutil, os, json
from datetime import datetime

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
DB_PATH  = os.environ.get("RADAR_DB_PATH", os.path.join(PROJECT_ROOT, "data", "radar.db"))
BAK_PATH = DB_PATH + f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"

def backup():
    shutil.copy2(DB_PATH, BAK_PATH)
    print(f"✅ 备份完成 → {BAK_PATH}")

def migrate(old: sqlite3.Connection, new: sqlite3.Connection):
    # ── 迁移用户 ──────────────────────────────────────
    old_users = old.execute("SELECT * FROM users").fetchall()
    old_cols  = [d[0] for d in old.execute("SELECT * FROM users LIMIT 0").description]

    for row in old_users:
        u = dict(zip(old_cols, row))
        new.execute("""
            INSERT OR IGNORE INTO users
              (id, email, password_hash, display_name, avatar_url, locale, region, role,
               onboarding_done, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            u["id"], u["email"], u.get("password_hash"),
            u.get("display_name"), u.get("avatar_url"),
            u.get("locale", "en"), u.get("region", "nz"),
            "admin",   # 第一个用户是 admin
            1,         # 已完成 onboarding（老用户）
            u.get("created_at", datetime.now().isoformat()),
        ))
    print(f"  👤 迁移 {len(old_users)} 个用户")

    # ── 迁移 watchlist → stocks + user_watchlist ──────
    old_wl = old.execute("SELECT * FROM user_watchlists").fetchall()
    old_wl_cols = [d[0] for d in old.execute("SELECT * FROM user_watchlists LIMIT 0").description]

    for row in old_wl:
        w = dict(zip(old_wl_cols, row))
        code   = w["code"]
        market = w.get("market", "nz")

        # 写入 stocks 表（基础信息）
        new.execute("""
            INSERT OR IGNORE INTO stocks (code, name, market, currency, last_fetched)
            VALUES (?,?,?,?,?)
        """, (
            code, w["name"], market,
            {"nz":"NZD","cn":"CNY","hk":"HKD","us":"USD"}.get(market,"USD"),
            datetime.now().isoformat(),
        ))

        # 写入 user_watchlist
        new.execute("""
            INSERT OR IGNORE INTO user_watchlist (user_id, stock_code, added_at, notes)
            VALUES (?,?,?,?)
        """, (
            w["user_id"], code,
            w.get("added_at", datetime.now().isoformat()),
            w.get("description", ""),
        ))
    print(f"  📋 迁移 {len(old_wl)} 条 watchlist")

    # ── 迁移新闻 → stock_news ─────────────────────────
    old_news = old.execute("SELECT * FROM news").fetchall()
    old_news_cols = [d[0] for d in old.execute("SELECT * FROM news LIMIT 0").description]

    for row in old_news:
        n = dict(zip(old_news_cols, row))
        new.execute("""
            INSERT OR IGNORE INTO stock_news
              (id, code, title, link, source, publish_time, fetched_date)
            VALUES (?,?,?,?,?,?,?)
        """, (
            n["id"], n["code"], n.get("title",""), n.get("link",""),
            n.get("source",""), n.get("publish_time",""), n.get("fetched_date",""),
        ))
    print(f"  📰 迁移 {len(old_news)} 条股票新闻")

    # ── 迁移 intl_news → market_news ─────────────────
    old_intl = old.execute("SELECT * FROM intl_news").fetchall()
    old_intl_cols = [d[0] for d in old.execute("SELECT * FROM intl_news LIMIT 0").description]

    for row in old_intl:
        n = dict(zip(old_intl_cols, row))
        new.execute("""
            INSERT OR IGNORE INTO market_news
              (id, region, category, title, link, source, fetched_date)
            VALUES (?,?,?,?,?,?,?)
        """, (
            n["id"], "global", n.get("scope","macro"),
            n.get("title",""), n.get("link",""),
            n.get("source",""), n.get("fetched_date",""),
        ))
    print(f"  🌍 迁移 {len(old_intl)} 条市场新闻")

    # ── 迁移资金流 → stock_fund_flow ─────────────────
    old_ff = old.execute("SELECT * FROM fund_flow").fetchall()
    old_ff_cols = [d[0] for d in old.execute("SELECT * FROM fund_flow LIMIT 0").description]

    for row in old_ff:
        f = dict(zip(old_ff_cols, row))
        new.execute("""
            INSERT OR IGNORE INTO stock_fund_flow (code, date, main_net, main_ratio)
            VALUES (?,?,?,?)
        """, (f["code"], f["date"], f.get("main_net"), f.get("main_ratio")))
    print(f"  💰 迁移 {len(old_ff)} 条资金流数据")

    # ── 迁移 quotes → stock_prices ───────────────────
    old_q = old.execute("SELECT * FROM quotes").fetchall()
    old_q_cols = [d[0] for d in old.execute("SELECT * FROM quotes LIMIT 0").description]

    for row in old_q:
        q = dict(zip(old_q_cols, row))
        new.execute("""
            INSERT OR IGNORE INTO stock_prices (code, price, change_pct, volume, fetched_at)
            VALUES (?,?,?,?,?)
        """, (
            q["code"], q.get("price"), q.get("change_pct"),
            q.get("amount"), q.get("date", datetime.now().isoformat()),
        ))
    print(f"  📈 迁移 {len(old_q)} 条价格快照")

    # ── 迁移报告 → reports ───────────────────────────
    old_rpt = old.execute("SELECT * FROM reports").fetchall()
    old_rpt_cols = [d[0] for d in old.execute("SELECT * FROM reports LIMIT 0").description]

    for row in old_rpt:
        r = dict(zip(old_rpt_cols, row))
        new.execute("""
            INSERT OR IGNORE INTO reports (analysis_date, period, html, md, created_at)
            VALUES (?,?,?,?,?)
        """, (
            r.get("date"), r.get("period","daily"),
            r.get("html",""), r.get("md",""),
            r.get("created_at", datetime.now().isoformat()),
        ))
    print(f"  📄 迁移 {len(old_rpt)} 条报告")

    new.commit()
    print("\n✅ 迁移完成")


NEW_SCHEMA = """
-- ═══════════════════════════════════════════════
-- 用户与权限
-- ═══════════════════════════════════════════════

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

-- ═══════════════════════════════════════════════
-- 股票与持仓
-- ═══════════════════════════════════════════════

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

-- ═══════════════════════════════════════════════
-- 新闻与分析
-- ═══════════════════════════════════════════════

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
    -- 巴菲特++ 结构化字段
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
    -- ML Phase 1 特征（立即开始积累）
    feat_price_momentum  REAL,
    feat_sentiment_avg   REAL,
    feat_fund_flow_net   REAL,
    feat_pe_vs_hist      REAL,
    feat_fear_greed      INTEGER,
    -- ML 标签（N天后回填）
    label_7d_return      REAL,
    label_30d_return     REAL,
    UNIQUE(code, period, analysis_date)
);

-- 报告（周/月/季度摘要页）
CREATE TABLE IF NOT EXISTS reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_date TEXT,
    period        TEXT DEFAULT 'daily',
    html          TEXT,
    md            TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(analysis_date, period)
);

-- ═══════════════════════════════════════════════
-- 系统数据（与用户无关）
-- ═══════════════════════════════════════════════

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

-- ═══════════════════════════════════════════════
-- Pipeline 任务追踪
-- ═══════════════════════════════════════════════

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
"""

if __name__ == "__main__":
    print("🔄 私人巴菲特 · DB 迁移")
    print(f"   源库: {DB_PATH}")

    backup()

    old_conn = sqlite3.connect(DB_PATH)
    new_conn = sqlite3.connect(DB_PATH + ".new")

    print("\n📐 建立新 schema…")
    new_conn.executescript(NEW_SCHEMA)
    new_conn.commit()

    print("📦 迁移数据…")
    migrate(old_conn, new_conn)

    old_conn.close()
    new_conn.close()

    # 替换
    os.replace(DB_PATH + ".new", DB_PATH)
    print(f"\n✅ 新库已替换旧库: {DB_PATH}")
    print(f"   旧库备份: {BAK_PATH}")
