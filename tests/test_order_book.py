"""US-186：在手订单 —— 不发中标公告的公司，订单藏在「合同负债」里。

## 从哪来的

用户妈妈问「能不能看订单量」。US-184 查明中标公告**只覆盖靠投标做生意的
行业**（电缆、电气设备、建筑工程、水务），而她持有的消费/医药/科技/锂电
结构上不发这种公告 —— 自选 118 只命中 0。

那这些公司的订单在哪？**在财报的「合同负债」科目里**：

    客户下单预付  → 合同负债增加
    交付确认收入  → 合同负债转成营收

实测依据：2022 年合同负债增长的公司里，**637 家在 2023 Q1 营收增长，
占 72.63%**。研究界确认「预收账款+合同负债」同比增速与利润增速正相关。

## 核心设计：光看增长不够，要和营收比

合同负债涨 50% 听起来好，但如果营收也涨 50%，那只是生意整体在长大。
真正有信息量的是**速度差**：`合同负债同比 − 营收同比`。

这条正是本仓反复栽的那个坑的反面 —— 一个数字单独看没有方向，
**要有参照物才有含义**。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.order_book import order_book_signal as sig  # noqa: E402

REV = 100e8      # 年营收 100 亿


# ── 核心：速度差才是信号 ────────────────────────────────

def test_orders_building_faster_than_revenue():
    """订单积累快过交付 → 这部分收入还没体现在报表上。"""
    r = sig(30e8, 55, 12, REV)
    assert r["tier"] == "building"
    assert r["gap"] == 43.0
    assert "还没体现" in r["text"]


def test_orders_draining():
    """在消化存量订单，新单没跟上 → 未来营收可能减速。"""
    r = sig(30e8, -20, 15, REV)
    assert r["tier"] == "draining"
    assert "可能减速" in r["text"]


def test_growing_together_is_not_a_signal():
    """合同负债和营收一起涨 = 生意整体在长大，**不含额外信息**。
    这是本条最要紧的一点：光看合同负债涨了多少会把它误读成利好。"""
    r = sig(30e8, 14, 12, REV)
    assert r["tier"] == "steady"
    assert "同步" in r["text"]


def test_both_shrinking_together_is_also_steady():
    r = sig(30e8, -12, -14, REV)
    assert r["tier"] == "steady"


# ── 量级不够就别下结论 ──────────────────────────────────

def test_tiny_order_book_gives_no_verdict():
    """合同负债只占营收 1% 的公司，它涨 200% 也说明不了什么。"""
    r = sig(1e8, 200, 5, REV)
    assert r["tier"] == "too_small"
    assert "说明不了" in r["text"]
    assert "gap" not in r or r.get("gap") is None


def test_threshold_is_three_percent_of_revenue():
    assert sig(2.9e8, 55, 12, REV)["tier"] == "too_small"
    assert sig(3.1e8, 55, 12, REV)["tier"] == "building"


# ── 不适用的行业 ────────────────────────────────────────

def test_banks_and_insurers_are_excluded():
    """合同负债在这些行业是完全另一回事（保险责任准备金等）。"""
    for ind in ("银行", "保险", "证券", "信托", "股份制银行"):
        assert sig(30e8, 55, 12, REV, industry=ind) == {}, ind


def test_normal_industry_passes():
    assert sig(30e8, 55, 12, REV, industry="电池")["tier"] == "building"


# ── 数据不全时不猜 ──────────────────────────────────────

def test_missing_inputs_return_nothing():
    assert sig(None, 55, 12, REV) == {}
    assert sig(30e8, None, 12, REV) == {}
    assert sig(30e8, 55, 12, None) == {}
    assert sig(30e8, 55, 12, 0) == {}
    assert sig("坏", "数", "据", REV) == {}


def test_missing_revenue_growth_says_so_instead_of_guessing():
    """没有营收同比就算不出速度差 —— 说清楚，不拿合同负债增速当结论。"""
    r = sig(30e8, 55, None, REV)
    assert r["tier"] == "unknown_gap"
    assert r["gap"] is None
    assert "看不出" in r["text"]


# ── 表达 ────────────────────────────────────────────────

def test_months_covered_is_the_intuitive_scale():
    """「相当于 3.6 个月的营收」比「占营收 30%」更好懂。"""
    r = sig(30e8, 55, 12, REV)
    assert r["months"] == 3.6
    assert "个月" in r["text"]


def test_bilingual():
    en = sig(30e8, 55, 12, REV, locale="en")
    assert "order book" in en["text"].lower()
    assert not any("一" <= ch <= "鿿" for ch in en["text"])


# ── 它属于哪一层 ────────────────────────────────────────

def test_belongs_to_the_company_layer():
    """真实经营变化，五层链最上面那层。价值不在领先几天，在于它是真的。
    代价是慢：季报频率，披露还滞后 1-2 个月。"""
    from radar_app.data.signal_layers import LAYER_ORDER
    assert LAYER_ORDER[0] == "company"


def test_near_zero_change_is_not_rendered_as_zero_percent():
    """宁德时代实测合同负债同比 **-0.43%** —— 四舍五入成「下降 0%」
    既是病句，又让人以为在跌。中英文都栽在同一处。"""
    r = sig(30e8, -0.43, 12, REV)
    assert "下降 0%" not in r["text"]
    assert "基本持平" in r["text"]
    en = sig(30e8, -0.43, 12, REV, locale="en")
    assert "down 0%" not in en["text"]
    assert "flat" in en["text"]


def test_template_does_not_print_minus_zero_percent():
    tpl = open(os.path.join(os.path.dirname(__file__), '..',
                            'templates', 'stock', 'signals.html'), encoding='utf-8').read()
    seg = tpl[tpl.index('class="obook-bars"'):]
    seg = seg[:seg.index('obook-note')]
    # 两行（在手订单同比 / 营收同比）各要有一处近零处理
    rows = [ln for ln in seg.splitlines() if 'obook-val' in ln]
    assert len(rows) == 2, f"应有两行同比，实际 {len(rows)}"
    for ln in rows:
        assert '基本持平' in ln, f"这一行没处理近零：{ln[:60]}"
    assert "'%+.0f'|format" in seg, "其余情况仍要显示具体数字"
