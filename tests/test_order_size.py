"""US-183：订单有多大 —— 不比谁先看到，比谁先看懂。

## 用户妈妈的问题（2026-08-26）

> 「最关键的是我们得到的消息都是很滞后的，这个是很难改变的……
>  要花钱得到新消息，不花钱可能就很难得到第一手消息。
>  那我们得不到最新的消息，**有一个就是看他的订单量**，这个是不是可以？
>  他得到了订单量过后的反应，是不是也是极快地在股价上面表现呢」

**她的方向是对的，但「快」不是可以争的东西。**

中标/重大合同是**强制披露**的，公告一出所有人同时看到。拼速度，散户永远
输给盯盘的机构和程序；签约到公告那几天也补不上。

**但可以拼「谁先看懂」。**

公告写「中标 1.2 亿元」，绝大多数人不会当场去算这占公司年营收的百分之几：

    营收 10 亿的公司   → 12% 的年营收，**是大事**
    营收 1000 亿的公司 → 0.12%，**是噪音**

同一个数字，意义差一百倍。而这个换算我们做得起：营收在年报里，金额在标题里。

## 顺带查到的

`tender_signals.py` 只抓公告**标题**，从来没抓过**金额** —— 所以在这条之前，
系统只能说「这家公司中标了」，说不出「这单对它有多重要」。
生产上 `cninfo_tender` 只有 9 条（209 只 A股），本身也极稀疏。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.order_size import (extract_amount, latest_revenue,  # noqa: E402
                                size_up)

SMALL = [{"year": "2025", "revenue": 10.0}]      # 年营收 10 亿
BIG = [{"year": "2025", "revenue": 1000.0}]      # 年营收 1000 亿


# ── 金额抽取 ────────────────────────────────────────────

def test_reads_common_announcement_titles():
    assert abs(extract_amount("关于中标约1.2亿元项目的公告") - 1.2e8) < 1
    assert abs(extract_amount("关于中标人民币3.5亿元合同的公告") - 3.5e8) < 1
    assert abs(extract_amount("中标金额12,345.67万元") - 1.234567e8) < 100


def test_units_are_not_confused():
    """「万」和「亿」差一万倍，弄反就是灾难性误读。"""
    assert extract_amount("中标5000万元") == 5e7
    assert extract_amount("中标5000亿元") == 5e11
    assert extract_amount("中标1百万元") == 1e6


def test_no_amount_in_title_returns_none():
    """很多公告写「签订日常经营重大合同」，金额在正文里 —— 抓不到就说抓不到，
    **不猜**。这类占比不小，宁可不显示也不能编一个数。"""
    assert extract_amount("关于签订日常经营重大合同的公告") is None
    assert extract_amount("关于中标项目的公告") is None
    assert extract_amount("") is None
    assert extract_amount(None) is None


def test_percentage_in_title_is_not_mistaken_for_amount():
    """标题常写「…占最近一期营业收入的 3.5%」—— 那个 3.5 不是金额。"""
    a = extract_amount("中标金额1.2亿元，占最近一期营业收入的3.5%")
    assert abs(a - 1.2e8) < 1


# ── 核心：同一笔订单，两家公司意义差一百倍 ──────────────

def test_same_order_means_opposite_things_for_different_companies():
    t = "关于中标约1.2亿元项目的公告"
    s = size_up(t, SMALL)
    b = size_up(t, BIG)
    assert s["pct"] == 12.0 and s["tier"] == "material"
    assert b["pct"] < 1 and b["tier"] == "routine"
    assert "值得注意" in s["text"]
    assert "日常经营" in b["text"]


def test_very_large_order_is_flagged_as_big():
    s = size_up("关于中标约3亿元项目的公告", SMALL)
    assert s["tier"] == "big" and "相当大" in s["text"]


def test_returns_nothing_when_it_cannot_be_computed():
    """没金额、没营收 —— 一律返回空，**不编**。"""
    assert size_up("关于签订日常经营重大合同的公告", SMALL) == {}
    assert size_up("关于中标约1.2亿元项目的公告", []) == {}
    assert size_up("关于中标约1.2亿元项目的公告", [{"revenue": 0}]) == {}
    assert size_up("", SMALL) == {}


def test_revenue_reads_the_latest_complete_year():
    assert latest_revenue([{"revenue": 10.0}, {"revenue": 8.0}]) == 1e9
    assert latest_revenue([{"revenue": None}, {"revenue": 8.0}]) == 8e8
    assert latest_revenue([]) is None
    assert latest_revenue([{"revenue": "坏数据"}]) is None


def test_bilingual():
    """哥哥看英文版（US-148 的债不再新增）。"""
    en = size_up("关于中标约1.2亿元项目的公告", SMALL, locale="en")
    assert "revenue" in en["text"].lower()
    assert not any("一" <= ch <= "鿿" for ch in en["text"])


# ── 这条属于哪一层 ──────────────────────────────────────

def test_order_belongs_to_the_company_layer_not_the_money_layer():
    """订单是**真实的经营变化**，属于五层链最上面那层，
    不是「市场的钱」那种噪音。它的价值不在于领先几天，在于它是真的。

    （对照：成交量/委托量属于「市场的钱」，而且本身**无方向** ——
    放量可能是抢筹也可能是出货，那正是本仓反复栽的坑。）
    """
    from radar_app.data.signal_layers import LAYER_ORDER
    assert LAYER_ORDER[0] == "company"
