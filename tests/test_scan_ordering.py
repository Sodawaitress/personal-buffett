"""US-174：搭车的次序决定谁被饿死。

## 事故

`/api/trigger-scan` 一个后台线程里串着三件事，原次序：

    前兆扫描（209 只 A股，75+ 分钟） → 内部人 → 东财行业映射（约 2 分钟）

而 `expire_stale_jobs` 在 **120 分钟**判死未完成的 job。2026-08-22 之后
连续三次超时（#1735 / #1742 / #1743），于是**排在第三的行业映射一次都没轮到**：

    东财已映射 263 只 · 按日新增：
        2026-08-22  263 只        ← 之后再没动过

自选股行业覆盖率因此死死卡在 60%，用户要的「行业筛选按钮」做不了。

## 我一开始归因错了

我把映射停摆归因于 US-169 的**链路断裂**。断链是真的，但只是一半 ——
08-25 整链修好并跑通（digest → success），**映射依然没恢复**，
因为它在这里被饿死。**两个独立的原因，各自都足以让它停摆。**

修好一个就宣布问题解决，是这次差点犯的错。

## 两条改动

1. **次序按「谁最容易被饿死」排，不按重要性排**：便宜的活先跑，
   最贵的那件去承担超时风险，而不是拖垮全部。
2. **进度写进 job.log**：原来三件事的 print 全打到 stdout（Fly 日志），
   `job.log` 里只有开头一行。查超时原因时翻到的日志**总共 26 个字符** ——
   跑了两小时，什么也说明不了。没有可见性就没有诊断。
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _run_body():
    src = open(os.path.join(ROOT, 'radar_app', 'system', 'routes.py'),
               encoding='utf-8').read()
    start = src.index('        def _run():')
    end = src.index('        threading.Thread(target=_run', start)
    return src[start:end]


def _order():
    """三件事在 _run 里的出场次序。"""
    body = _run_body()
    marks = {
        'industry': body.find('refresh_map_em'),
        'insider':  body.find('run_insider_refresh'),
        'precursor': body.find('run_precursor_scan'),
    }
    assert all(v > 0 for v in marks.values()), marks
    return [k for k, _ in sorted(marks.items(), key=lambda kv: kv[1])]


def test_cheap_jobs_run_before_the_expensive_one():
    """前兆扫描按小时算，行业映射约 2 分钟。贵的排最后，
    它超时时前两件已经落库了。"""
    order = _order()
    assert order[-1] == 'precursor', f"前兆扫描必须排最后，实际次序 {order}"


def test_industry_mapping_is_not_last():
    """它就是因为排最后被饿死的 —— 连续三次超时，一次都没轮到。"""
    order = _order()
    assert order.index('industry') < order.index('precursor')


def test_progress_is_written_to_job_log():
    """跑两小时、日志 26 个字符，等于没有诊断能力。"""
    body = _run_body()
    assert 'def _note(' in body
    assert 'log=' in body, "进度必须写进 job.log，不能只 print 到 stdout"
    # 三件事都要留痕，否则还是查不出卡在哪
    for kw in ('行业映射', '内部人', '前兆扫描'):
        assert kw in body, f"{kw} 没有写进度"


def test_log_is_truncated_so_it_cannot_blow_up_the_row():
    body = _run_body()
    assert re.search(r'\[-\d{3,}:\]', body), "job.log 要截断，否则长跑会把行撑爆"


def test_each_step_failure_is_isolated():
    """一件挂掉不能带走另外两件 —— 这三件本来就互不依赖。"""
    body = _run_body()
    assert body.count('except Exception as e:') >= 3, \
        "三件事各自要有独立的 try/except"


def test_failures_are_surfaced_not_swallowed():
    """refresh_map_em 返回 failed 字典而不是抛异常 —— 只看 job 状态会误判成功。
    2026-08-22 我就据此误判过一次「三段全成功」。"""
    body = _run_body()
    assert "mp.get(\"boards\")" in body or "mp.get('boards')" in body, \
        "板块列表拉不到必须进 errors，否则静默失败"


def test_job_expiry_is_longer_than_a_normal_scan():
    """前兆扫描实测 75+ 分钟且随自选股增长。判死阈值要留余量，
    否则正常跑完的扫描会被当成僵尸杀掉。"""
    src = open(os.path.join(ROOT, 'radar_app', 'data', 'jobs.py'),
               encoding='utf-8').read()
    m = re.search(r'def expire_stale_jobs\(max_age_minutes=(\d+)\)', src)
    assert m, "找不到 expire_stale_jobs"
    assert int(m.group(1)) >= 120
