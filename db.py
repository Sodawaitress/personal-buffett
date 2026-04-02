"""
股票雷达 · 数据库层
SQLite — 持久化行情、新闻、基本面、报告
"""
import sqlite3, json, hashlib, os
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "radar.db")
CN_TZ   = timezone(timedelta(hours=8))

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            google_id     TEXT UNIQUE,
            display_name  TEXT,
            avatar_url    TEXT,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS user_watchlists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code        TEXT NOT NULL,
            name        TEXT NOT NULL,
            description TEXT DEFAULT '',
            added_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, code)
        );

        CREATE TABLE IF NOT EXISTS stocks (
            code        TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            description TEXT DEFAULT '',
            added_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS quotes (
            code        TEXT,
            date        TEXT,
            price       REAL,
            change_pct  REAL,
            amount      REAL,
            PRIMARY KEY (code, date)
        );

        CREATE TABLE IF NOT EXISTS news (
            id          TEXT PRIMARY KEY,
            code        TEXT,
            title       TEXT,
            source      TEXT,
            link        TEXT,
            publish_time TEXT,
            fetched_date TEXT
        );

        CREATE TABLE IF NOT EXISTS intl_news (
            id          TEXT PRIMARY KEY,
            scope       TEXT,   -- stock code or '_sector'
            title       TEXT,
            label       TEXT,
            link        TEXT,
            source      TEXT,
            fetched_date TEXT
        );

        CREATE TABLE IF NOT EXISTS fund_flow (
            code        TEXT,
            date        TEXT,
            main_net    REAL,
            main_ratio  REAL,
            PRIMARY KEY (code, date)
        );

        CREATE TABLE IF NOT EXISTS fundamentals (
            code        TEXT PRIMARY KEY,
            data        TEXT,   -- JSON
            updated_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS reports (
            date        TEXT PRIMARY KEY,
            html        TEXT,
            md          TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        """)

# ── 用户 ──────────────────────────────────────────────
def create_user(email, password_hash=None, google_id=None, display_name=None, avatar_url=None):
    with get_conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO users(email,password_hash,google_id,display_name,avatar_url) VALUES(?,?,?,?,?)",
            (email, password_hash, google_id, display_name, avatar_url)
        )

def get_user_by_email(email):
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(row) if row else None

def get_or_create_google_user(google_id, email, display_name, avatar_url):
    """Find or create a user from Google OAuth. Returns user dict."""
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE google_id=?", (google_id,)).fetchone()
        if row:
            return dict(row)
        # Link to existing email account if exists
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if row:
            c.execute("UPDATE users SET google_id=?,display_name=?,avatar_url=? WHERE id=?",
                      (google_id, display_name, avatar_url, row["id"]))
            return dict(c.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone())
        # New user
        c.execute(
            "INSERT INTO users(email,google_id,display_name,avatar_url) VALUES(?,?,?,?)",
            (email, google_id, display_name, avatar_url)
        )
        row = c.execute("SELECT * FROM users WHERE google_id=?", (google_id,)).fetchone()
        return dict(row)

def get_user_by_id(user_id):
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

def user_exists(email=None):
    with get_conn() as c:
        if email:
            return bool(c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone())
    return False

# ── 个人自选股 ─────────────────────────────────────────
def get_user_watchlist(user_id):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM user_watchlists WHERE user_id=? ORDER BY added_at",
            (user_id,))]

def add_user_stock(user_id, code, name, description=""):
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO user_watchlists(user_id,code,name,description) VALUES(?,?,?,?)",
                  (user_id, code, name, description))
        # Also ensure global stocks table has this entry (for shared data)
        c.execute("INSERT OR IGNORE INTO stocks(code,name,description) VALUES(?,?,?)",
                  (code, name, description))

def remove_user_stock(user_id, code):
    with get_conn() as c:
        c.execute("DELETE FROM user_watchlists WHERE user_id=? AND code=?", (user_id, code))

# ── 自选股 ────────────────────────────────────────────
def get_watchlist():
    with get_conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM stocks ORDER BY added_at")]

def add_stock(code, name, description=""):
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO stocks(code,name,description) VALUES(?,?,?)",
                  (code, name, description))

def remove_stock(code):
    with get_conn() as c:
        c.execute("DELETE FROM stocks WHERE code=?", (code,))

# ── 行情 ──────────────────────────────────────────────
def upsert_quote(code, date, price, change_pct, amount):
    with get_conn() as c:
        c.execute("""INSERT OR REPLACE INTO quotes(code,date,price,change_pct,amount)
                     VALUES(?,?,?,?,?)""", (code, date, price, change_pct, amount))

def get_quotes(date=None):
    with get_conn() as c:
        if date:
            return [dict(r) for r in
                    c.execute("SELECT * FROM quotes WHERE date=?", (date,))]
        return [dict(r) for r in c.execute(
            "SELECT q.*, s.name FROM quotes q JOIN stocks s USING(code) "
            "WHERE q.date=(SELECT MAX(date) FROM quotes) ORDER BY change_pct DESC")]

def get_quote_history(code, days=30):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM quotes WHERE code=? ORDER BY date DESC LIMIT ?",
            (code, days))]

# ── 新闻（去重）────────────────────────────────────────
def news_id(title, source, date):
    return hashlib.md5(f"{title}{source}{date}".encode()).hexdigest()

def upsert_news(code, title, source, link, publish_time, fetched_date):
    nid = news_id(title, source, publish_time[:10] if publish_time else "")
    with get_conn() as c:
        c.execute("""INSERT OR IGNORE INTO news(id,code,title,source,link,publish_time,fetched_date)
                     VALUES(?,?,?,?,?,?,?)""",
                  (nid, code, title, source, link, publish_time, fetched_date))
    return nid

def get_news(code, days=3):
    cutoff = (datetime.now(CN_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM news WHERE code=? AND fetched_date>=? ORDER BY publish_time DESC LIMIT 10",
            (code, cutoff))]

# ── 国际新闻（去重）───────────────────────────────────
def upsert_intl_news(scope, title, label, link, source, fetched_date):
    nid = hashlib.md5(f"{title}{link}".encode()).hexdigest()
    with get_conn() as c:
        c.execute("""INSERT OR IGNORE INTO intl_news(id,scope,title,label,link,source,fetched_date)
                     VALUES(?,?,?,?,?,?,?)""",
                  (nid, scope, title, label, link, source, fetched_date))

def get_intl_news(scope, days=3):
    cutoff = (datetime.now(CN_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM intl_news WHERE scope=? AND fetched_date>=? ORDER BY fetched_date DESC LIMIT 6",
            (scope, cutoff))]

# ── 主力资金 ──────────────────────────────────────────
def upsert_fund_flow(code, date, main_net, main_ratio):
    with get_conn() as c:
        c.execute("""INSERT OR REPLACE INTO fund_flow(code,date,main_net,main_ratio)
                     VALUES(?,?,?,?)""", (code, date, main_net, main_ratio))

def get_fund_flow(code):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM fund_flow WHERE code=? ORDER BY date DESC LIMIT 1",
            (code,)).fetchone()
        return dict(row) if row else {}

# ── 基本面（缓存）─────────────────────────────────────
def upsert_fundamentals(code, data_dict):
    with get_conn() as c:
        c.execute("""INSERT OR REPLACE INTO fundamentals(code,data,updated_at)
                     VALUES(?,?,datetime('now'))""",
                  (code, json.dumps(data_dict, ensure_ascii=False)))

def get_fundamentals(code):
    with get_conn() as c:
        row = c.execute("SELECT * FROM fundamentals WHERE code=?", (code,)).fetchone()
        if row:
            return json.loads(row["data"])
        return {}

def fundamentals_stale(code, days=7):
    """基本面数据是否超过N天未更新"""
    with get_conn() as c:
        row = c.execute("SELECT updated_at FROM fundamentals WHERE code=?", (code,)).fetchone()
        if not row:
            return True
        updated = datetime.fromisoformat(row["updated_at"])
        return (datetime.utcnow() - updated).days >= days

# ── 报告 ──────────────────────────────────────────────
def save_report(date, html, md):
    with get_conn() as c:
        c.execute("INSERT OR REPLACE INTO reports(date,html,md) VALUES(?,?,?)",
                  (date, html, md))

def get_report(date=None):
    with get_conn() as c:
        if date:
            row = c.execute("SELECT * FROM reports WHERE date=?", (date,)).fetchone()
        else:
            row = c.execute("SELECT * FROM reports ORDER BY date DESC LIMIT 1").fetchone()
        return dict(row) if row else None

def list_reports(limit=30):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT date, created_at FROM reports ORDER BY date DESC LIMIT ?", (limit,))]

if __name__ == "__main__":
    init_db()
    print(f"DB initialized: {DB_PATH}")
