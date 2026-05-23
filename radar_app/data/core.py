"""Database core connection and schema helpers."""

import os
from contextlib import contextmanager
from datetime import timedelta, timezone

from sqlalchemy import create_engine, event, text

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_DEFAULT_SQLITE = os.path.join(PROJECT_ROOT, "data", "radar.db")

# Set DATABASE_URL in env to point at Cloud SQL PostgreSQL in production.
# Local default: SQLite at data/radar.db
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{_DEFAULT_SQLITE}")
DB_PATH = _DEFAULT_SQLITE  # kept for scripts that log the path
CN_TZ = timezone(timedelta(hours=8))

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        kw = {}
        if DATABASE_URL.startswith("sqlite"):
            kw["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(DATABASE_URL, **kw)
        if DATABASE_URL.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _set_pragmas(dbapi_conn, _):
                dbapi_conn.execute("PRAGMA foreign_keys = ON")
    return _engine


@contextmanager
def get_conn():
    """Auto-committing connection context manager.

    Within a Flask request, reuses one connection from Flask g (US-85).
    Outside a request (scripts, tests), opens a fresh transaction each call.
    SQL must use named :param style (not positional ?).
    Rows support dict(row) and row["key"].
    """
    try:
        from flask import g, has_request_context
        _in_req = has_request_context()
    except Exception:
        _in_req = False

    if _in_req:
        if "_pbc_conn" not in g:
            g._pbc_conn = get_engine().connect()
        conn = g._pbc_conn
        try:
            yield _ConnWrapper(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    else:
        with get_engine().begin() as _raw:
            yield _ConnWrapper(_raw)


def teardown_request_conn(e=None):
    """Close the per-request DB connection — call from app.teardown_appcontext."""
    try:
        from flask import g
        conn = g.pop("_pbc_conn", None)
        if conn is not None:
            conn.close()
    except Exception:
        pass


class _ConnWrapper:
    """Makes SQLAlchemy rows dict-like without changing every call site."""

    def __init__(self, conn):
        self._c = conn

    def execute(self, query, params=None):
        stmt = text(query) if isinstance(query, str) else query
        result = self._c.execute(stmt) if params is None else self._c.execute(stmt, params)
        return result.mappings()

    def executemany(self, query, seq_of_params):
        stmt = text(query) if isinstance(query, str) else query
        return self._c.execute(stmt, list(seq_of_params))


def init_db():
    if DATABASE_URL.startswith("sqlite"):
        os.makedirs(os.path.dirname(_DEFAULT_SQLITE) or ".", exist_ok=True)
    # Split on ";" so this works for both SQLite and PostgreSQL.
    # executescript() is SQLite-only; statement-by-statement is universal.
    stmts = [s.strip() for s in _SCHEMA_SQL.split(";") if s.strip()]
    with get_engine().begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))


_SCHEMA_SQL = """
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
            trade_block          TEXT,
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
            annual_json      TEXT,
            pe_current       REAL,
            pe_percentile_5y INTEGER,
            pb_current       REAL,
            pb_percentile_5y INTEGER,
            signals_json     TEXT,
            updated_at       TEXT DEFAULT (datetime('now'))
        );

        -- 组合每日简报（per-user LLM 合成）
        CREATE TABLE IF NOT EXISTS portfolio_analysis (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER REFERENCES users(id),
            analysis_date   TEXT,
            macro_headline  TEXT,
            buffett_summary TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, analysis_date)
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

        -- 公司分类元数据（US-46）
        CREATE TABLE IF NOT EXISTS stock_meta (
            code               TEXT PRIMARY KEY REFERENCES stocks(code),
            company_type       TEXT,
            industry           TEXT,
            market_tier        TEXT,
            st_status          TEXT,
            st_since           TEXT,
            name_history_json  TEXT,
            ipo_date           TEXT,
            total_shares       REAL,
            float_shares       REAL,
            last_classified    TEXT,
            manual_override    INTEGER DEFAULT 0,
            updated_at         TEXT DEFAULT (datetime('now'))
        );

        -- 股票事件数据层（US-49）
        CREATE TABLE IF NOT EXISTS stock_events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            code         TEXT REFERENCES stocks(code),
            event_type   TEXT NOT NULL,
            event_date   TEXT,
            summary      TEXT,
            detail_json  TEXT,
            source       TEXT DEFAULT 'manual',
            created_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_stock_events_code ON stock_events(code);

        -- 机构雷达：北向资金历史（计算5/10日趋势）
        CREATE TABLE IF NOT EXISTS northbound_history (
            date       TEXT PRIMARY KEY,
            total_net  REAL,
            fetched_at TEXT DEFAULT (datetime('now'))
        );

        -- 机构雷达：大宗交易近期记录
        CREATE TABLE IF NOT EXISTS block_trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT,
            trade_date  TEXT,
            premium_pct REAL,
            amount_mn   REAL,
            fetched_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(code, trade_date, amount_mn)
        );

        -- 机构雷达：高管增减持
        CREATE TABLE IF NOT EXISTS insider_changes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT,
            holder_name TEXT,
            role        TEXT,
            change_type TEXT,
            shares      REAL,
            avg_price   REAL,
            change_date TEXT,
            fetched_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(code, holder_name, change_date, change_type)
        );

        -- 机构雷达：季度信号（股东人数）
        CREATE TABLE IF NOT EXISTS inst_quarterly (
            code            TEXT,
            quarter         TEXT,
            shareholder_cnt INTEGER,
            sh_pct_change   REAL,
            updated_at      TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (code, quarter)
        );

        -- 用户通知（US-65 差评预警）
        CREATE TABLE IF NOT EXISTS user_notifications (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER REFERENCES users(id),
            code          TEXT,
            type          TEXT,
            message       TEXT,
            created_at    TEXT DEFAULT (datetime('now')),
            snoozed_until TEXT,
            dismissed_at  TEXT
        );

        -- 数据质量日志（US-48）
        CREATE TABLE IF NOT EXISTS data_quality_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            code       TEXT,
            field      TEXT,
            value      TEXT,
            flag       TEXT,
            reason     TEXT,
            logged_at  TEXT DEFAULT (datetime('now'))
        );

        -- 用户提问箱（US-67）
        CREATE TABLE IF NOT EXISTS user_questions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            question   TEXT,
            answer     TEXT,
            asked_at   TEXT DEFAULT (datetime('now'))
        );

        -- 机构前兆信号每日缓存（US-69）
        CREATE TABLE IF NOT EXISTS stock_precursor_cache (
            code        TEXT NOT NULL,
            fetched_at  TEXT NOT NULL,
            survey_json TEXT,
            short_json  TEXT,
            partic_json TEXT,
            score       REAL DEFAULT 0,
            is_active   INTEGER DEFAULT 0,
            PRIMARY KEY (code, fetched_at)
        );

        -- 机构调研事件永久记录（防止 AKShare 滚动窗口丢数据）
        CREATE TABLE IF NOT EXISTS survey_events (
            code        TEXT NOT NULL,
            event_date  TEXT NOT NULL,
            n_inst      INTEGER,
            is_specific INTEGER DEFAULT 0,
            source      TEXT,
            PRIMARY KEY (code, event_date)
        );
        CREATE INDEX IF NOT EXISTS idx_survey_events_code ON survey_events(code, event_date);

        -- 用户信号预测记录（US-75 预言家日报）
        CREATE TABLE IF NOT EXISTS signal_predictions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER REFERENCES users(id) ON DELETE CASCADE,
            code              TEXT REFERENCES stocks(code),
            created_at        TEXT DEFAULT (datetime('now')),
            direction         TEXT NOT NULL,
            note              TEXT,
            signal_snapshot   TEXT,
            resolved_at       TEXT,
            actual_return_5d  REAL,
            actual_return_10d REAL,
            correct           INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_signal_pred_user ON signal_predictions(user_id, code);

        -- 前兆信号每日历史快照（US-92 预测追踪数据基础）
        CREATE TABLE IF NOT EXISTS precursor_history (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            code               TEXT NOT NULL,
            snapshot_date      DATE NOT NULL,
            survey_json        TEXT,
            short_json         TEXT,
            participation_json TEXT,
            price_change_pct   REAL,
            created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(code, snapshot_date)
        );
        CREATE INDEX IF NOT EXISTS idx_precursor_history_code ON precursor_history(code, snapshot_date);
"""


def _migrate():
    new_cols = [
        ("user_watchlist", "status", "TEXT DEFAULT 'watching'"),
        ("user_watchlist", "buy_date", "TEXT"),
        ("user_watchlist", "buy_price", "REAL"),
        ("user_watchlist", "sell_date", "TEXT"),
        ("user_watchlist", "sell_price", "REAL"),
        ("user_watchlist", "entry_grade", "TEXT"),
        ("analysis_results", "framework_used", "TEXT"),
        ("analysis_results", "quant_score", "INTEGER"),
        ("analysis_results", "quant_components", "TEXT"),
        ("analysis_results", "data_incomplete", "INTEGER DEFAULT 0"),
        ("stocks", "asset_type", "TEXT DEFAULT '股票'"),
        ("user_watchlist",    "removed_at",        "TIMESTAMP"),
        ("signal_predictions", "signal_type",       "TEXT"),
        ("signal_predictions", "predicted_outcome", "TEXT"),
    ]
    # Each ALTER TABLE gets its own transaction so one failure doesn't abort the rest
    # (PostgreSQL aborts the whole transaction on error; SQLite does not).
    engine = get_engine()
    for table, col, typedef in new_cols:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}"))
        except Exception:
            pass

    fund_keywords = ["ETF联接", "ETF", "指数", "LOF", "联接A", "联接C", "联接E"]
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(
                "SELECT code, name FROM stocks WHERE asset_type IS NULL OR asset_type='股票'"
            )).mappings().all()
            for row in rows:
                if any(kw in (row["name"] or "") for kw in fund_keywords):
                    conn.execute(
                        text("UPDATE stocks SET asset_type='场外基金' WHERE code=:code"),
                        {"code": row["code"]},
                    )
    except Exception:
        pass
