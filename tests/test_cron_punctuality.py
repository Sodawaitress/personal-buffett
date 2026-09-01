"""US-206：流水线准点率必须可测。

用户观察：「每日五选的时间似乎在数据真的更新完前面，就导致每日五选的延迟」。

实测确认（2026-08-25 → 09-01，6 次 schedule 触发）：

    08-25 +18分   08-26 +20分
    08-27 +641分  08-28 +711分   08-31 +447分   09-01 +297分

`createdAt` 就是 18:04 —— **不是排队，是 schedule 事件本身晚了 11 小时**。
6 次里 4 次流水线结束时间晚于 Routine 的触发时间（13:2x UTC），
那几天的五选必然读到前一天的快照。

Routine 的 Gate 一直诚实地报告了这件事（提交信息里写着「pipeline 相位错位」
「双Gate FAIL 服务器数据未刷新」），但处理方式是**跳过**——
于是同一个原因连着犯了一个月。
"""
import re

import pytest


def test_pipeline_cron_avoids_the_top_of_the_hour():
    """整点是 GitHub Actions 上最拥挤的 cron 槽位，官方文档明确建议避开。
    这条守的是「别改回去」—— 分钟数是有理由的，不是随手写的。
    """
    txt = open(".github/workflows/pipeline.yml", encoding="utf-8").read()
    m = re.search(r"cron:\s*'(\d+)\s+(\d+)\s", txt)
    assert m, "pipeline 没有 cron 了？"
    minute, hour = int(m.group(1)), int(m.group(2))
    assert minute != 0, "cron 回到了整点 —— 那是最拥挤的槽位"
    # A股 07:00 UTC 收盘，必须在收盘之后
    assert hour * 60 + minute >= 7 * 60, "cron 早于 A股收盘，会抓到盘中数据"


def test_pipeline_finishes_before_the_routine_reads_it():
    """相位约束：流水线跑满约 4 小时，Routine 在 13:2x UTC 读。
    cron + 4h 必须留出余量，否则五选结构性地读旧数据。
    """
    txt = open(".github/workflows/pipeline.yml", encoding="utf-8").read()
    m = re.search(r"cron:\s*'(\d+)\s+(\d+)\s", txt)
    start = int(m.group(2)) * 60 + int(m.group(1))
    ROUTINE = 13 * 60 + 20      # Routine 实测触发时间
    PIPELINE_MINUTES = 240      # 实测 207-263 分钟
    assert start + PIPELINE_MINUTES < ROUTINE, (
        f"cron {start//60:02d}:{start%60:02d} + 4h 跑完已经过了 Routine 的 13:20，"
        "五选会结构性地读到前一天数据")


def test_report_reads_cron_from_the_file_not_hardcoded():
    """准点率脚本必须从 workflow 文件里读 cron —— 写死的话，
    改了时间之后它会拿旧基准算迟到，报出一堆假的准点。
    """
    import inspect

    from scripts import cron_punctuality as c
    src = inspect.getsource(c._scheduled_minute)
    assert "open(" in src and "cron" in src, "cron 时间是写死的"


def test_routine_doc_tells_it_to_repair_not_just_skip():
    """Gate FAIL 时只记录不修，等于让同一个原因反复犯。
    Routine 文档里必须写明修复动作。"""
    doc = open("CLAUDE_ROUTINE.md", encoding="utf-8").read()
    assert "gh workflow run pipeline.yml" in doc, \
        "Routine 没有被告知 Gate FAIL 时要去拉起上游"
    assert "cron_punctuality" in doc, "Routine 不知道怎么验收准点率"
