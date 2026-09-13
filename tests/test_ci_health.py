"""US-213：CI 不许再悄悄变红。

**这条守的是流程，不是代码。**

CI 在最近 200 次运行里**一次都没绿过**。而我这两周每次推代码只跑本地、
宣布「652 条全过」，**一次都没看过 CI**。

> 一个永远红的 CI 比没有 CI 更糟 —— 它制造了有安全网的假象。

红的原因很朴素：6 条测试读「用户 1 的自选股」，本地 `data/radar.db` 有数据
所以过，CI 上是空库所以必然红。

**修法不是 skip。** skip 掉等于这 6 条在 CI 上从不执行，
和删掉没区别而且更隐蔽（报告显示「skipped」不是「missing」）。
这一周反复栽的「空转的绿」就是这个形态。
"""
import subprocess
import sys
from pathlib import Path


def test_conftest_seeds_only_when_truly_empty():
    """播种绝不能碰有数据的库 —— 否则本地真实数据会被测试污染。"""
    src = Path("tests/conftest.py").read_text(encoding="utf-8")
    assert "_is_truly_empty" in src
    assert "if not _is_truly_empty(db):" in src and "return" in src


def test_seeding_failure_reports_in_plain_words():
    """session 级 autouse fixture 一挂，整个套件就没了（实测 652 条全 error）。
    那时候看到的是一堆 SQLAlchemy 栈，会让人以为被测代码坏了。"""
    src = Path("tests/conftest.py").read_text(encoding="utf-8")
    assert "RuntimeError" in src and "播种失败" in src


def test_suite_passes_on_a_blank_database():
    """**直接验证**：拿一个全新的空库跑整套测试。

    这条比任何静态检查都有力 —— 它就是 CI 的环境。
    如果将来有人再加一条依赖本地数据的测试，这里会先红。
    """
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        env = {**os.environ,
               "DATABASE_URL": f"sqlite:///{Path(d) / 'blank.db'}"}
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "-x",
             "--ignore=tests/test_search.py",
             "--ignore=tests/test_ci_health.py",      # 别递归调用自己
             "-p", "no:cacheprovider"],
            capture_output=True, text=True, env=env, timeout=900)
        assert r.returncode == 0, (
            "空库上跑不过 —— CI 会红。\n"
            + r.stdout[-3000:])
