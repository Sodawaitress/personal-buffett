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
        else:
            # Neon(serverless PG）：scale-to-zero 会断闲置连接，复用死连接→SSL SYSCALL 500。
            # pre_ping 用前探活 + recycle 定期回收，避免间歇性报错。
            kw["pool_pre_ping"] = True
            kw["pool_recycle"] = 300
        _engine = create_engine(DATABASE_URL, **kw)
        if DATABASE_URL.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _set_pragmas(dbapi_conn, _):
                dbapi_conn.execute("PRAGMA foreign_keys = ON")
                dbapi_conn.execute("PRAGMA journal_mode = WAL")   # 读写并发，precursor 扫描不阻塞登录
                dbapi_conn.execute("PRAGMA busy_timeout = 15000") # 等锁最多 15 秒再报错
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


def _dialect_sql(sql: str) -> str:
    """把 SQLite 专用 DDL 转成当前方言可用（PG）。SQLite 保持原样。"""
    if DATABASE_URL.startswith("sqlite"):
        return sql
    # PostgreSQL：INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
    return sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")


# US-207：DDL 必须串行化。
#
# 2026-09-02 pipeline 的 market 一棒挂在 Postgres 死锁上：
#     [SQL: CREATE INDEX IF NOT EXISTS idx_precursor_history_code ...]
#     Process 25788 waits for ShareLock on relation 24992
#     Process 26949 waits for RowExclusiveLock on relation 24957
#
# 原因很朴素：`init_db()` 每次发 59 条 DDL，仓里有 28 处在调它
# （每个 svc_*.py 启动都调，Fly 上的 web 应用启动也调）。
# DDL 拿的是重锁，两个进程一交叉，锁的获取顺序就反了 —— 死锁。
#
# 「幂等」只保证**结果**一样，不保证**并发安全**。
# CREATE TABLE IF NOT EXISTS 重复跑不会出错，但两个进程同时跑会互相锁死。
#
# 顾问锁是 Postgres 上处理并发迁移的标准做法：拿不到就等，
# 拿到的那个跑完再放。SQLite 是单写者，不需要。
_DDL_LOCK_KEY = 0x5042435F44444C   # 'PBC_DDL'


@contextmanager
def _ddl_lock():
    """把 DDL 串起来。锁必须挂在**一条一直开着的连接**上 ——
    `engine.begin()` 每条语句一个事务，会话一结束锁就没了。"""
    eng = get_engine()
    if eng.dialect.name != "postgresql":
        yield
        return
    conn = eng.connect()
    try:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _DDL_LOCK_KEY})
        conn.commit()
        yield
    finally:
        try:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _DDL_LOCK_KEY})
            conn.commit()
        except Exception:
            pass
        conn.close()


def init_db():
    if DATABASE_URL.startswith("sqlite"):
        os.makedirs(os.path.dirname(_DEFAULT_SQLITE) or ".", exist_ok=True)
    # Split on ";" so this works for both SQLite and PostgreSQL.
    # executescript() is SQLite-only; statement-by-statement is universal.
    stmts = [s.strip() for s in _SCHEMA_SQL.split(";") if s.strip()]
    with _ddl_lock():
        with get_engine().begin() as conn:
            for stmt in stmts:
                conn.execute(text(_dialect_sql(stmt)))


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
            created_at      TEXT DEFAULT (CURRENT_TIMESTAMP),
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
            added_at    TEXT DEFAULT (CURRENT_TIMESTAMP),
            notes       TEXT,
            status      TEXT DEFAULT 'watching',
            buy_date    TEXT,
            buy_price   REAL,
            sell_date   TEXT,
            sell_price  REAL,
            entry_grade TEXT,
            removed_at  TIMESTAMP,
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
            fetched_at  TEXT DEFAULT (CURRENT_TIMESTAMP)
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
            created_at    TEXT DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(analysis_date, period)
        );

        -- 系统数据
        CREATE TABLE IF NOT EXISTS market_data (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            data_type  TEXT,
            payload    TEXT,
            fetched_at TEXT DEFAULT (CURRENT_TIMESTAMP)
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
            updated_at       TEXT DEFAULT (CURRENT_TIMESTAMP)
        );

        -- 组合每日简报（per-user LLM 合成）
        CREATE TABLE IF NOT EXISTS portfolio_analysis (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER REFERENCES users(id),
            analysis_date   TEXT,
            macro_headline  TEXT,
            buffett_summary TEXT,
            created_at      TEXT DEFAULT (CURRENT_TIMESTAMP),
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
            updated_at         TEXT DEFAULT (CURRENT_TIMESTAMP)
        );

        -- 行业基准（US-116 v2：行业中性化 z-score，东财行业 PE/PB mean+std）
        CREATE TABLE IF NOT EXISTS industry_benchmarks (
            industry     TEXT,
            metric       TEXT,
            mean         REAL,
            std          REAL,
            n            INTEGER,
            updated_at   TEXT DEFAULT (CURRENT_TIMESTAMP),
            PRIMARY KEY (industry, metric)
        );

        -- 用户对公司类型的众包判断（US-116 第一页；过验证门再回填分类）
        CREATE TABLE IF NOT EXISTS stock_type_votes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            code         TEXT,
            company_type TEXT,
            created_at   TEXT DEFAULT (CURRENT_TIMESTAMP)
        );

        -- 全市场 ticker→东财行业 映射（US-116 v2，无外键，含未跟踪股）
        CREATE TABLE IF NOT EXISTS stock_industry_map (
            code         TEXT PRIMARY KEY,
            industry     TEXT,
            updated_at   TEXT DEFAULT (CURRENT_TIMESTAMP)
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
            created_at   TEXT DEFAULT (CURRENT_TIMESTAMP)
        );
        CREATE INDEX IF NOT EXISTS idx_stock_events_code ON stock_events(code);

        -- 机构雷达：北向资金历史（计算5/10日趋势）
        CREATE TABLE IF NOT EXISTS northbound_history (
            date       TEXT PRIMARY KEY,
            total_net  REAL,
            fetched_at TEXT DEFAULT (CURRENT_TIMESTAMP)
        );

        -- 机构雷达：大宗交易近期记录
        CREATE TABLE IF NOT EXISTS block_trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT,
            trade_date  TEXT,
            premium_pct REAL,
            amount_mn   REAL,
            fetched_at  TEXT DEFAULT (CURRENT_TIMESTAMP),
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
            fetched_at  TEXT DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(code, holder_name, change_date, change_type)
        );

        -- 机构雷达：季度信号（股东人数）
        CREATE TABLE IF NOT EXISTS inst_quarterly (
            code            TEXT,
            quarter         TEXT,
            shareholder_cnt INTEGER,
            sh_pct_change   REAL,
            updated_at      TEXT DEFAULT (CURRENT_TIMESTAMP),
            PRIMARY KEY (code, quarter)
        );

        -- 用户通知（US-65 差评预警）
        CREATE TABLE IF NOT EXISTS user_notifications (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER REFERENCES users(id),
            code          TEXT,
            type          TEXT,
            message       TEXT,
            created_at    TEXT DEFAULT (CURRENT_TIMESTAMP),
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
            logged_at  TEXT DEFAULT (CURRENT_TIMESTAMP)
        );

        -- 用户提问箱（US-67）
        CREATE TABLE IF NOT EXISTS user_questions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            question   TEXT,
            answer     TEXT,
            asked_at   TEXT DEFAULT (CURRENT_TIMESTAMP)
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
        -- US-192 五选台账：推荐当天落账，5/10/20 日由**代码**自动回填。
        -- 关键设计：Claude 只写 picks_open.json，回填全部由流水线算 ——
        -- 五选是 Claude 的判断，成绩单不能也由 Claude 写。
        CREATE TABLE IF NOT EXISTS pick_ledger (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            code          TEXT NOT NULL,
            name          TEXT,
            pick_date     TEXT NOT NULL,       -- 推荐日
            entry_price   REAL,                -- 推荐日收盘（落账时锁定）
            grade         TEXT,
            quant_score   REAL,
            advice        TEXT,
            reason_tags   TEXT,                -- 推荐理由分类（JSON 数组）
            -- 回填字段（全部由代码算，Claude 无权写）
            ret_5d        REAL, ret_10d  REAL, ret_20d  REAL,
            bench_5d      REAL, bench_10d REAL, bench_20d REAL,
            excess_5d     REAL, excess_10d REAL, excess_20d REAL,
            resolved_20d  INTEGER DEFAULT 0,
            updated_at    TEXT,
            UNIQUE(code, pick_date)
        );
        CREATE INDEX IF NOT EXISTS idx_pick_ledger_date ON pick_ledger(pick_date);

        CREATE TABLE IF NOT EXISTS signal_predictions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER REFERENCES users(id) ON DELETE CASCADE,
            code              TEXT REFERENCES stocks(code),
            created_at        TEXT DEFAULT (CURRENT_TIMESTAMP),
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

        CREATE TABLE IF NOT EXISTS analyst_consensus (
            code       TEXT PRIMARY KEY,
            fetched_at TEXT DEFAULT (CURRENT_TIMESTAMP),
            data_json  TEXT
        );

        CREATE TABLE IF NOT EXISTS industry_signals (
            industry_key TEXT PRIMARY KEY,
            fetched_at   TEXT DEFAULT (CURRENT_TIMESTAMP),
            signal_json  TEXT
        );

        -- US-158：行业当日表现的逐日留存。动量由这张表自己算，不依赖任何
        -- 外部历史接口 —— 东财的历史 K 线主机全被拒、同花顺翻页会导致封号
        -- （2026-08-16 实测两者皆亲历）。我们拥有这份时间序列。
        -- 唯一键 (date, sector_label) 保证幂等：同一天被多个服务重复捕获无害，
        -- 这正是「挂 5 个服务、任何一个跑起来都补上」的前提。
        -- US-160：推送台账。解决「每天推送内容几乎一样」。
        --
        -- 根因：「今天该注意的」五个板块里有四个取的是**当前状态**而非**今日事件**
        --   早期预警  get_stock_events 无任何日期过滤 → 同一条永远重复
        --   机构领先  get_signal_conclusion = 当前结论 → 不变就天天播
        --   机构脚印  latest_dir = 当前趋势 → 持续就天天播
        --   催化剂    未来 7 天内的事 → 同一件事连播 7 天
        -- 而系统此前**完全没有任何推送去重机制**。
        --
        -- item_key = 身份（这是"哪一件事"），state_hash = 内容（这件事"现在什么样"）。
        -- 只有身份首次出现、或身份不变但状态变了，才值得再打扰一次。
        CREATE TABLE IF NOT EXISTS push_ledger (
            user_id     INTEGER NOT NULL,
            item_key    TEXT NOT NULL,
            state_hash  TEXT NOT NULL,
            first_seen  TEXT DEFAULT (CURRENT_TIMESTAMP),
            last_pushed TEXT DEFAULT (CURRENT_TIMESTAMP),
            PRIMARY KEY (user_id, item_key)
        );

        CREATE TABLE IF NOT EXISTS industry_daily (
            date          TEXT NOT NULL,
            sector_label  TEXT NOT NULL,
            sector_name   TEXT,
            change_pct    REAL,
            company_count INTEGER,
            avg_price     REAL,
            captured_at   TEXT DEFAULT (CURRENT_TIMESTAMP),
            PRIMARY KEY (date, sector_label)
        );

        CREATE INDEX IF NOT EXISTS idx_industry_daily_label
            ON industry_daily(sector_label, date);

        -- US-97 自动供应链溯源
        CREATE TABLE IF NOT EXISTS supply_chain_links (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            downstream_code  TEXT NOT NULL,
            supplier_name    TEXT NOT NULL,
            supplier_ticker  TEXT,
            dependency_type  TEXT,
            chokepoint_score INTEGER DEFAULT 0,
            evidence_quote   TEXT,
            scanned_at       TEXT DEFAULT (CURRENT_TIMESTAMP),
            source           TEXT DEFAULT 'sec_10k'
        );
        CREATE INDEX IF NOT EXISTS idx_supply_chain_links_code
            ON supply_chain_links(downstream_code, chokepoint_score DESC);

        -- 供应链扫描日志：记录每次扫描完成时间和结果数，用于区分"扫描中"和"扫描完无结果"
        CREATE TABLE IF NOT EXISTS supply_chain_scan_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker       TEXT NOT NULL,
            scanned_at   TEXT DEFAULT (CURRENT_TIMESTAMP),
            result_count INTEGER DEFAULT 0,
            source       TEXT DEFAULT 'sec_10k',
            note         TEXT,
            UNIQUE(ticker)
        );

        -- US-106 跨境供应链三源融合：A股年报客户反查索引
        CREATE TABLE IF NOT EXISTS supply_chain_customer_index (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            a_share_code  TEXT NOT NULL,
            a_share_name  TEXT,
            customer_name TEXT NOT NULL,
            us_ticker     TEXT,
            revenue_pct   REAL,
            source        TEXT NOT NULL DEFAULT 'cninfo_annual',
            report_year   INTEGER,
            scanned_at    TEXT DEFAULT (CURRENT_TIMESTAMP),
            UNIQUE(a_share_code, customer_name, source)
        );
        CREATE INDEX IF NOT EXISTS idx_sc_customer_us_ticker
            ON supply_chain_customer_index(us_ticker);
        CREATE INDEX IF NOT EXISTS idx_sc_customer_a_share
            ON supply_chain_customer_index(a_share_code);

        -- US-112 未定价信号
        CREATE TABLE IF NOT EXISTS unpriced_signals (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code       TEXT NOT NULL,
            user_id          INTEGER NOT NULL,
            auto_score       INTEGER DEFAULT 0,
            trends_json      TEXT,
            reddit_json      TEXT,
            news_freq_json   TEXT,
            user_score       INTEGER DEFAULT 0,
            discovery_method TEXT,
            awareness_level  TEXT,
            physical_signals TEXT,
            insight_text     TEXT,
            insight_type     TEXT,
            insight_adj      INTEGER DEFAULT 0,
            insight_reason   TEXT,
            total_score      INTEGER DEFAULT 0,
            digest_label     TEXT,
            created_at       TEXT DEFAULT (CURRENT_TIMESTAMP),
            updated_at       TEXT DEFAULT (CURRENT_TIMESTAMP),
            actual_return_90d REAL,
            return_checked_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_unpriced_signals_code_user
            ON unpriced_signals(stock_code, user_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS market_polls (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_date  TEXT NOT NULL UNIQUE,
            question   TEXT NOT NULL DEFAULT '大盘今天涨还是跌？',
            up_votes   INTEGER DEFAULT 0,
            down_votes INTEGER DEFAULT 0,
            outcome    TEXT,
            clue_1     TEXT,
            clue_2     TEXT,
            clue_3     TEXT,
            created_at TEXT DEFAULT (CURRENT_TIMESTAMP)
        );

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            token      TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used       INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (CURRENT_TIMESTAMP)
        );

        -- Performance indices on high-frequency query columns
        CREATE INDEX IF NOT EXISTS idx_stock_prices_code_time
            ON stock_prices(code, fetched_at DESC);
        CREATE INDEX IF NOT EXISTS idx_stock_news_code_date
            ON stock_news(code, fetched_date DESC);
        CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_code
            ON pipeline_jobs(code, started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_watchlist_user_status
            ON user_watchlist(user_id, removed_at, status);

        -- US-114 价值发现工作流
        CREATE TABLE IF NOT EXISTS value_theses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            code            TEXT NOT NULL,
            earnings_ps     REAL,
            market_trend    TEXT,
            market_obs      TEXT,
            years_choice    INTEGER,
            pe_low          REAL,
            pe_high         REAL,
            fair_value_low  REAL,
            fair_value_high REAL,
            price_at_save   REAL,
            buy_thesis      TEXT,
            review_date     TEXT,
            created_at      TEXT DEFAULT (CURRENT_TIMESTAMP)
        );

        -- 城市生活成本参考（Numbeo, 30天 TTL）
        CREATE TABLE IF NOT EXISTS city_living_data (
            city_slug          TEXT PRIMARY KEY,
            city_name          TEXT NOT NULL,
            tier               TEXT NOT NULL,
            city_category      TEXT DEFAULT 'major',   -- 'major' | 'lifestyle'
            avg_monthly_salary REAL,
            avg_monthly_cost   REAL,
            source             TEXT DEFAULT 'numbeo',
            report_year        INTEGER,
            fetched_at         TEXT NOT NULL
        );

        -- US-121 微服务可观测性：每个服务每次运行记一行（append-only）
        CREATE TABLE IF NOT EXISTS service_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name    TEXT NOT NULL,
            started_at      TEXT NOT NULL,
            finished_at     TEXT,
            status          TEXT NOT NULL DEFAULT 'running',   -- running | done | failed
            duration_s      REAL,
            items_processed INTEGER DEFAULT 0,
            stopped_early   INTEGER DEFAULT 0,
            error           TEXT
        );
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
        # US-101 多跳 BOM 溯源
        ("supply_chain_links", "hop_depth",      "INTEGER DEFAULT 1"),
        ("supply_chain_links", "upstream_path",  "TEXT"),
        ("supply_chain_links", "tier1_code",     "TEXT"),
        # US-106 supply_chain_customer_index source confidence
        ("supply_chain_customer_index", "confidence", "INTEGER DEFAULT 80"),
        # US-107 地理个性化排序：供应商所属市场
        ("supply_chain_links", "supplier_market", "TEXT DEFAULT 'unknown'"),
        # US-104 公开博客层
        ("analysis_results",   "is_public",      "INTEGER DEFAULT 0"),
        # US-105 双城市 FIRE
        ("city_living_data",   "city_category",  "TEXT DEFAULT 'major'"),
        ("city_living_data",   "report_year",    "INTEGER"),
        # US-116 验证层：分类来源 auto/crowd/manual（配合 manual_override 防覆盖）
        ("stock_meta",         "type_source",    "TEXT DEFAULT 'auto'"),
        # US-142 内部人交易：小刚要的「减持比例」—— 两个分母都存，缺一个用户就没感觉
        ("insider_changes",    "ratio_total",    "REAL"),   # 占总股本 %
        ("insider_changes",    "ratio_own",      "REAL"),   # 占其本人持股 %
        ("insider_changes",    "reason",         "TEXT"),   # 竞价交易/大宗交易/股权激励…
        ("insider_changes",    "kind",           "TEXT"),   # routine / opportunistic
        # US-203：分位的**窗口长度**必须跟着分位一起存。
        # 列名叫 pe_percentile_5y，但那是 A 股的语境（百度给的就是近5年）；
        # 美股用 yfinance 只拿得到 4 期年度 EPS，实际窗口 3.5-4 年。
        # 同一列装两种窗口而不记录是哪种，就是把受限的观测讲成不受限的结论。
        ("stock_fundamentals", "pe_pct_window_years", "REAL"),
        ("stock_fundamentals", "pe_pct_range",        "TEXT"),   # "20.8-44.7" 供页面显示区间
        # US-208「颠不颠」：波动率是所有指标里**最难被修饰**的 ——
        # 它直接来自成交价格，不经过任何人的手。
        # vol_stable 存 0/1/NULL 三态：NULL = 历史不够长，判断不了。
        # 两态会把「不知道」讲成「脾气变了」（第一版就是这么错的）。
        ("stock_fundamentals", "vol_weekly",  "REAL"),
        ("stock_fundamentals", "vol_ratio",   "REAL"),
        ("stock_fundamentals", "vol_pct",     "INTEGER"),
        ("stock_fundamentals", "vol_stable",  "INTEGER"),
    ]
    # Each ALTER TABLE gets its own transaction so one failure doesn't abort the rest
    # (PostgreSQL aborts the whole transaction on error; SQLite does not).
    engine = get_engine()
    with _ddl_lock():                     # US-207：同一把锁，和 init_db 串在一起
        for table, col, typedef in new_cols:
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}"))
            except Exception:
                pass

    # Drop legacy table left over from pre-2026-04-13 code cleanup
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS historical_cases"))
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
