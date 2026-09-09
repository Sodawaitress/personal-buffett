"""US-211：无界的批处理迟早撞上某个超时，而撞上那天你只看得到「cancelled」。

2026-09-04 / 09-07 / 09-08 连续三天 pipeline 的 `digest` 被判 cancelled，
其余七棒全部 success。查下来：

    digest-svc 有 `timeout-minutes: 20`
    digest 实际跑 16:31→16:52 = 21 分钟
    快照 16:47 就提交了 —— **被杀的是提交之后那段**

所以从产物上完全看不出来：快照每天都在，只是台账回填从没跑完过。

根因在 `backfill()`：它把所有 `resolved_20d = 0` 的行全捞出来重跑，
而**结不掉的行永远留在集合里** —— 缺价格数据 → `all_done` 恒为 False
→ 每天重查一遍，直到永远。09-08 的日志里还在处理 2026-07-05 的推荐，
65 天前，早该在 20 个交易日内结清。
"""
import inspect

from scripts import pick_ledger


def test_backfill_is_bounded():
    """每轮有上限。无界批处理 = 迟早撞上某个超时。"""
    sig = inspect.signature(pick_ledger.backfill)
    assert "limit" in sig.parameters, "回填没有批次上限"
    assert sig.parameters["limit"].default, "上限没有默认值"
    src = inspect.getsource(pick_ledger.backfill)
    assert "LIMIT :n" in src, "SQL 里没有真的限量，参数只是摆设"


def test_stuck_rows_are_retired():
    """再等也等不到的行必须封存，否则它们每天都在拖慢整批。"""
    src = inspect.getsource(pick_ledger.backfill)
    assert "_GIVE_UP_DAYS" in src, "没有放弃机制，死行会永远累积"
    assert pick_ledger._GIVE_UP_DAYS >= 20, "宽限期短于 20 个交易日窗口，会误杀"


def test_oldest_first_so_progress_is_monotonic():
    """限量之后必须按最老的先处理 —— 否则每轮抓到的是同一批新行，
    老的永远轮不到，限量就变成了「永远只做前 N 个」。"""
    src = inspect.getsource(pick_ledger.backfill)
    assert "ORDER BY pick_date ASC" in src, "限量了但没排序，进度不单调"


def test_digest_no_longer_carries_the_full_backfill():
    """落账要快，回填可以慢。digest 里只留一小批兜底。"""
    src = inspect.getsource(__import__("scripts.svc_digest", fromlist=["x"]))
    assert "ledger_backfill(limit=" in src, "digest 里的回填还是无界的"


def test_backfill_svc_owns_the_slow_half():
    s = open(".github/workflows/backfill-svc.yml", encoding="utf-8").read()
    assert "pick_ledger" in s, "慢的那半没有搬到 backfill-svc"
