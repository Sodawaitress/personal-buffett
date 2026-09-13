"""US-213：让 CI 上的测试**真的跑**，而不是跳过。

**背景**：CI 在最近 200 次运行里**一次都没绿过**。6 条测试读「用户 1 的自选股」，
本地那个 `data/radar.db` 有数据所以过，CI 上是空库所以必然红。

于是 CI 变成了一个永远红的灯 —— 没人看，看了也不信。
我自己这两周每次推代码都只跑本地，宣布「652 条全过」，**从没看过 CI**。

> **一个永远红的 CI 比没有 CI 更糟：它制造了有安全网的假象。**

**修法不是让它们 skip。** skip 掉就等于这 6 条在 CI 上从不执行 ——
那和删掉它们没有区别，而且更隐蔽（报告里显示的是「skipped」不是「missing」）。
这一周反复栽的「空转的绿」就是这个形态。

正确做法是**给空库播一份最小数据集**，让这些测试在任何环境下都真的执行。

**只在库完全是空的时候播种** —— 绝不碰任何已有数据。
本地有真实数据 → 用真实数据（行为和现在完全一样）；
CI 空库 → 播 25 只，测试照常跑。
"""
import pytest

_SEED_N = 25            # 那几条测试要求 ≥20 只才算「样本够」


def _is_truly_empty(db) -> bool:
    """空 = 一只股票都没有。有任何数据就不碰，避免污染真实库。"""
    try:
        from sqlalchemy import text
        with db.get_engine().begin() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM stocks")).scalar()
        return not n
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def _seed_minimal_dataset():
    """CI 上播最小数据集。本地有数据时什么都不做。"""
    from radar_app.data import core as db
    db.init_db()
    if not _is_truly_empty(db):
        return                      # 有真实数据，原样使用

    from sqlalchemy import text
    codes = [f"{600000 + i:06d}" for i in range(_SEED_N)]
    try:
        with db.get_engine().begin() as conn:
            # ⚠️ 列名要和真实 schema 对得上。第一版写了 `name`，
            # 而 users 表里是 `display_name` —— 结果 **652 条全部 error**：
            # session 级 autouse fixture 一挂，整个套件就没了。
            # 播种代码本身也是代码，也会写错。
            conn.execute(text(
                "INSERT INTO users (id, email, display_name, locale) "
                "VALUES (1, :e, :n, 'zh')"),
                {"e": "ci@test.invalid", "n": "CI"})
            for i, c in enumerate(codes):
                conn.execute(text(
                    "INSERT INTO stocks (code, name, market) "
                    "VALUES (:c, :n, 'cn')"),
                    {"c": c, "n": f"测试股{i}"})
                conn.execute(text(
                    "INSERT INTO user_watchlist (user_id, stock_code, status) "
                    "VALUES (1, :c, :s)"),
                    {"c": c, "s": "holding" if i % 3 == 0 else "watching"})
                conn.execute(text(
                    "INSERT INTO stock_prices (code, price, change_pct) "
                    "VALUES (:c, :p, :g)"),
                    {"c": c, "p": 10.0 + i, "g": (i % 7) - 3})
    except Exception as e:
        # 报人话。一堆 SQLAlchemy 栈会让人以为是被测代码坏了，
        # 而实际上坏的是这份夹具。
        raise RuntimeError(
            f"CI 最小数据集播种失败（tests/conftest.py）：{type(e).__name__}: {e}\n"
            "→ 多半是 INSERT 的列名和 radar_app/data/core.py 的 schema 对不上。"
        ) from e
