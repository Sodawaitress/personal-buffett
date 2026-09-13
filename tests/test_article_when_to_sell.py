"""US-212：《什么时候该卖》专栏。

用户问「我们的文章那篇怎么持有怎么卖的是不是还没发出去」—— 确实没写过。
之前只在对话里讲了，**从没落到网站上**。

这篇守的不是文笔，是**三条不许被简化掉的诚实**：

1. Morningstar 那个「差 1.2 个百分点」被 CFA Institute 用同一份数据
   算成 0.10%，小十倍。**只引对自己有利的一半本身就是错误。**
2. 「让盈利多跑」在美股靠动量效应撑着，**A 股是反转，那条依据不在**。
3. 去偏实验的结论是**知道治不好**（3 个月后效果消失，且收益没变好）——
   这条对文章自己不利，但必须写。
"""
import re

from radar_app.research.articles import get_article, list_articles

SLUG = "when-to-sell-2026"


def _html():
    a = get_article(SLUG)
    return open("templates/" + a["template"], encoding="utf-8").read()


def test_article_is_registered_and_newest():
    a = get_article(SLUG)
    assert a, "文章没注册，专栏页上看不到"
    assert list_articles()[0]["slug"] == SLUG, "不是最新一篇，会被压在下面"


def test_keeps_the_rebuttal_to_morningstar():
    """引用一个被质疑的数字时必须带上质疑。"""
    h = _html()
    assert "1.2 个百分点" in h
    assert "0.10%" in h, "只引了 Morningstar，没引 CFA 的反驳"
    assert "还在吵" in h or "没有定论" in h


def test_ashare_section_is_not_a_translation_of_the_us_one():
    """A 股那一节必须自己有结论，而且要说明「让盈利多跑」在这里没依据。"""
    h = _html()
    assert "反转" in h and "动量" in h
    assert "那条依据不在" in h, "没有明说美股那条结论在 A 股不成立"
    # 成本差异是 A 股结论反转的关键
    assert "0.056%" in h and "免征" in h


def test_admits_that_knowing_does_not_fix_it():
    """对文章自己不利，但必须写 —— 否则它就变成了一篇「读完就好了」的鸡汤。"""
    h = _html()
    assert "3 个月后" in h
    assert "收益没有变好" in h or "收益反而" in h


def test_the_takeaway_rule_is_present():
    h = _html()
    assert "我卖它，是因为" in h
    assert "那就不要卖" in h


def test_no_personalisation():
    """US-187 的教训：这个站不止一位用户在看，困惑本来就是普世的。
    不许出现「你妈妈」「小刚」这类具体的人。"""
    h = _html()
    for bad in ("妈妈", "小刚", "周宇"):
        assert bad not in h, f"文章被写成针对特定某个人的了: {bad}"


def test_renders_without_template_errors():
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("templates"))
    h = env.get_template(get_article(SLUG)["template"]).render()
    assert len(h) > 8000
    assert not re.search(r"{%[^%]*$", h), "有未闭合的 Jinja 标签"
    assert "</html>" in h


# ── US-214：每一项研究必须标出它是哪个市场的 ──────────────────────────

def test_every_study_says_which_market_it_came_from():
    """用户看到「交易越多赚得越少」那一节就问「这个是美国的研究吧」。

    问得对 —— 一到四节全是美股数据，但读起来像普世结论。
    **这正是本站反复在修的那族错误：把一个语境的事实用到另一个语境。**

    守法：每一个知识点标题（`kl-term`）要么带国别徽章，
    要么是纯解释性的（不含具体研究和数字）。
    """
    import re
    h = _html()
    terms = re.findall(r'<div class="kl-term">(.*?)</div>', h, re.S)
    assert len(terms) >= 8, f"知识点数量不对: {len(terms)}"
    unflagged = [t for t in terms if "flag flag-" not in t]
    # 只有「为什么会这样」「给卖的动作上结构」这两条是纯解释，没有数据来源
    assert len(unflagged) <= 2, (
        "这些知识点引了研究却没标市场:\n  " +
        "\n  ".join(re.sub(r"<[^>]+>", "", t).strip() for t in unflagged))


def test_has_chinese_counterpart_for_the_trading_frequency_claim():
    """「交易越多赚得越少」不能只有美股证据 —— 这条恰好两边都测过，
    而且中国的结论更极端。有就必须写上，否则读者会合理地怀疑整篇。"""
    h = _html()
    assert "廖理" in h or "五道口" in h, "缺中国的过度交易研究"
    assert "深交所" in h, "缺深交所全样本的实证"
    assert "次日收益显著负相关" in h, "缺中国散户净买入与次日收益的关系"


def test_top_banner_warns_about_transferring_us_results():
    h = _html()
    assert "不要默认适用于 A 股" in h, "顶部没有提醒读者注意市场差异"


def test_flags_are_visually_distinguishable():
    """三种徽章要有各自的样式，否则标了等于没标。"""
    h = _html()
    for cls in ("flag-us", "flag-cn", "flag-both"):
        assert f".{cls}{{" in h.replace(" ", ""), f"{cls} 没有样式定义"
