"""US-121 微服务支撑层：运行记录（service_runs）+ 选择性分析规则（should_analyze）。

- 每个服务用 `service_run(name)` 上下文管理器包裹，无论成败都在 service_runs 记一行。
- `should_analyze` 决定某只股票今天是否值得花 LLM token 重新分析（省 TPM）。
"""
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from radar_app.data.core import CN_TZ, get_conn

__all__ = [
    "service_run", "get_last_run",
    "get_held_codes", "has_recent_material",
    "should_analyze", "select_codes_to_analyze",
]


def _now_iso() -> str:
    return datetime.now(CN_TZ).isoformat()


class _RunHandle:
    """service_run 上下文里回传给调用方，用来累加处理数 / 标记提前停止。"""

    def __init__(self):
        self.items_processed = 0
        self.stopped_early = False

    def tick(self, n: int = 1):
        self.items_processed += n


@contextmanager
def service_run(service_name: str):
    """包裹一次服务运行。用法：
        with service_run("analyze-svc") as run:
            ...
            run.tick()          # 每处理一只 +1
            run.stopped_early = True   # 达预算提前停
    异常会被记为 failed 后重新抛出。
    """
    start = _now_iso()
    with get_conn() as c:
        row = c.execute(
            """
            INSERT INTO service_runs(service_name, started_at, status)
            VALUES(:name, :start, 'running')
            RETURNING id
            """,
            {"name": service_name, "start": start},
        ).fetchone()
        run_id = row["id"]

    handle = _RunHandle()
    status, err = "done", None
    t0 = datetime.now(CN_TZ)
    try:
        yield handle
    except Exception as e:
        status, err = "failed", str(e)[:500]
        raise
    finally:
        dur = (datetime.now(CN_TZ) - t0).total_seconds()
        with get_conn() as c:
            c.execute(
                """
                UPDATE service_runs
                SET finished_at=:fin, status=:status, duration_s=:dur,
                    items_processed=:items, stopped_early=:early, error=:err
                WHERE id=:id
                """,
                {
                    "fin": _now_iso(), "status": status, "dur": dur,
                    "items": handle.items_processed,
                    "early": 1 if handle.stopped_early else 0,
                    "err": err, "id": run_id,
                },
            )


def get_last_run(service_name: str) -> dict:
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM service_runs WHERE service_name=:n ORDER BY id DESC LIMIT 1",
            {"n": service_name},
        ).fetchone()
        return dict(row) if row else {}


# ── 选择性分析规则 ────────────────────────────────────────────────

def get_held_codes() -> set:
    """所有用户当前持有（status='holding'）的股票代码。"""
    with get_conn() as c:
        rows = c.execute(
            "SELECT DISTINCT stock_code FROM user_watchlist "
            "WHERE status='holding' AND removed_at IS NULL"
        ).fetchall()
        return {r["stock_code"] for r in rows if r["stock_code"]}


def has_recent_material(code: str, days: int = 2) -> bool:
    """近 days 天内是否有重大新闻事件（material scan 写入 stock_events）。"""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with get_conn() as c:
        row = c.execute(
            "SELECT 1 FROM stock_events "
            "WHERE code=:c AND source='news_material' AND event_date >= :cut LIMIT 1",
            {"c": code, "cut": cutoff},
        ).fetchone()
        return row is not None


def _last_analysis_date(code: str) -> str | None:
    with get_conn() as c:
        row = c.execute(
            "SELECT analysis_date FROM analysis_results "
            "WHERE code=:c ORDER BY analysis_date DESC, id DESC LIMIT 1",
            {"c": code},
        ).fetchone()
        return row["analysis_date"] if row else None


def should_analyze(code: str, rotation_days: int = 3, held_codes: set = None) -> tuple[bool, str]:
    """今天是否值得花 LLM token 重新分析这只股票。返回 (bool, 原因)。
    满足任一即分析：①持仓股 ②近 2 天有重大新闻 ③从未分析或距上次 ≥ rotation_days 天（轮转）。
    否则读缓存跳过。held_codes 可预取传入避免逐只查库。
    """
    held = get_held_codes() if held_codes is None else held_codes
    if code in held:
        return True, "held"
    if has_recent_material(code):
        return True, "material"

    last = _last_analysis_date(code)
    if not last:
        return True, "never"
    try:
        last_d = date.fromisoformat(last[:10])
        if (date.today() - last_d).days >= rotation_days:
            return True, "rotation"
    except ValueError:
        return True, "bad_date"
    return False, "cached"


def select_codes_to_analyze(codes, rotation_days: int = 3) -> list:
    """批量筛选。返回 [(code, reason), ...] 只含要分析的。held_codes 只查一次。"""
    held = get_held_codes()
    out = []
    for code in codes:
        ok, reason = should_analyze(code, rotation_days, held_codes=held)
        if ok:
            out.append((code, reason))
    return out
