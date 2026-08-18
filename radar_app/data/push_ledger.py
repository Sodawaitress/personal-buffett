"""US-160：推送台账 —— 只在「有变化」时打扰。

「今天该注意的」原本每天内容几乎一样，因为五个板块里有四个取的是
**当前状态**而不是**今日事件**：

    早期预警  get_stock_events 无任何日期过滤 → 同一条永远重复
    机构领先  get_signal_conclusion = 当前结论 → 结论不变就天天播
    机构脚印  latest_dir = 当前趋势 → 趋势持续就天天播
    催化剂    未来 7 天内的事件 → 同一件事连播 7 天
    评级变化  这个是真事件（但 45% 的股票不是每天分析，变化会跨天残留）

而系统此前**完全没有任何推送去重机制**。

这里的模型：
    item_key   = 身份 —— "这是哪一件事"（如 lead:600519）
    state_hash = 内容 —— "这件事现在什么样"（结论文本的哈希）

只有「身份首次出现」或「身份还在但状态变了」才值得再打扰一次。
状态没变的项不消失，而是折叠成一行「另有 N 项与上次相同」，
这样用户知道系统还活着，而不是以为它死了。
"""

import hashlib

from radar_app.data.core import get_conn


def state_hash(*parts) -> str:
    """把一个条目的内容压成指纹。None 与空串等价，避免无意义的「变化」。"""
    payload = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:16]


def filter_changed(user_id: int, items: list) -> tuple:
    """items = [(item_key, state_hash, payload), ...]

    返回 (changed, unchanged_count)。
    **只读**，不写台账 —— 写入要等推送真的发出去（见 commit_pushed），
    否则推送失败时这些条目会被永久吞掉。
    """
    if not items:
        return [], 0
    # 全取该用户的台账再在内存里比对：条目数最多几百，比 IN 子句展开省事，
    # 也避开 SQLAlchemy text() 不自动展开元组参数的坑。
    with get_conn() as c:
        rows = c.execute(
            "SELECT item_key, state_hash FROM push_ledger WHERE user_id = :uid",
            {"uid": user_id},
        ).fetchall()
    seen = {r["item_key"]: r["state_hash"] for r in rows}

    changed, unchanged = [], 0
    for key, sh, payload in items:
        if seen.get(key) != sh:
            changed.append((key, sh, payload))
        else:
            unchanged += 1
    return changed, unchanged


def commit_pushed(user_id: int, items: list) -> None:
    """推送成功之后才记账。items = [(item_key, state_hash, _), ...]"""
    if not items:
        return
    with get_conn() as c:
        for key, sh, _ in items:
            c.execute(
                """
                INSERT INTO push_ledger(user_id, item_key, state_hash)
                VALUES(:uid, :k, :sh)
                ON CONFLICT(user_id, item_key) DO UPDATE SET
                    state_hash = excluded.state_hash,
                    last_pushed = CURRENT_TIMESTAMP
                """,
                {"uid": user_id, "k": key, "sh": sh},
            )


def purge_stale(user_id: int, days: int = 90) -> int:
    """清理很久没再出现的条目，防止台账无限增长。

    90 天后同一件事若再出现，会被当成新事件重推一次 —— 这是可接受的：
    一件事沉寂三个月后重现，本来就值得再说一次。
    """
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as c:
        c.execute(
            "DELETE FROM push_ledger WHERE user_id = :uid AND last_pushed < :cutoff",
            {"uid": user_id, "cutoff": cutoff},
        )
