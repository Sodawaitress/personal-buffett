"""US-222：股灾系列第一篇《股灾两周：政府出了三招，市场怎么读》。

这篇守的规矩：

1. 评论员（王剑）**只在核实过的地方出现**。他说错的数字（外汇存款准备金
   率说成 5%，实际 6%）、口径不对的比较（8000 亿额度）、传闻，一律不进文章。
2. 事实都对过：交易所日线、统计局 PMI、三部门座谈会出席名单。
3. 匿名消息源要说明是匿名的。
"""
import re

from radar_app.research.articles import get_article, list_articles

SLUG = "stock-crash-2026-01"


def _html():
    a = get_article(SLUG)
    return open("templates/" + a["template"], encoding="utf-8").read()


def test_article_is_registered_and_newest():
    a = get_article(SLUG)
    assert a, "文章没注册，专栏页上看不到"
    assert list_articles()[0]["slug"] == SLUG, "不是最新一篇，会被压在下面"


def test_commentator_errors_and_rumours_stay_out():
    """王剑说错的、没核实的、传闻，都不许进文章。"""
    h = _html()
    # 「外汇存款准备金」：他把 6% 说成 5%，整条不进文章（不能只禁「5%」—— 会误伤「1.25%」）
    for bad in ("外汇存款准备金", "8000 亿", "8000亿", "何立峰", "丁向群", "骗局", "割韭菜",
                "国家队进场"):
        assert bad not in h, f"未核实或错误的内容进了文章: {bad}"
    assert h.count("王剑") == 1, "王剑只该出现在核实过的那一处（会议规格）"


def test_state_team_only_appears_as_verified_floor_support():
    """「国家队」可以出现，但只能是我们用上交所 ETF 份额查过的那个结论：
    沪深300/上证50 ETF 下跌日（11-03）申购最多、大涨日减半 → 托底，不是拉升。
    王剑那句没看数据的「国家队进场」不许进来。"""
    h = _html()
    if "国家队" in h:
        i = h.index("国家队")
        near = h[i - 200:i + 300]
        assert "托底" in near and "11 月 3 日" in near, "提到国家队，却没带上 ETF 份额的证据"


def test_verified_facts_match_the_record():
    h = _html()
    assert "49.3" in h                      # 统计局 10 月 PMI
    assert "1.25% 降到 1%" in h              # 再贷款利率
    assert "77 块" in h and "94 块" in h      # 创业板 10 月 −23.02%，上证 −6.33%
    assert "5 月 7 日" in h and "副职" in h and "正职" in h   # 2025-05-07 国新办发布会


def test_rally_cause_matches_intraday_data():
    """11-05 两次更正（1 分钟线 + 周边市场 + ETF 份额）：
    - 美国结果 12:35 出来，A 股 13:01 开盘只跳了 1 个点又回吐；
    - 真正拉升从 13:30 开始，那时美股期货、韩国都没对应急动；
    - 13:15 是媒体照搬的时点，分钟线上那是低点。
    不许把大涨主要归给「政策落地」，也不许再把它主要归给美国；
    不许用早期报道的「24 家 / 400 亿」。"""
    h = _html()
    assert "1 点半" in h and "美国" in h
    assert "1000 亿" in h
    assert "公开数据看不出来" in h, "最猛那一段的推手没查清，要老实说"
    for bad in ("24 家", "400 亿", "宣布了，不等于落地了",
                "1 点 15 分", "火是从美国点着的", "导火索是美国"):
        assert bad not in h, f"已更正的说法又回来了: {bad}"
    assert "11 月 5 日更新" in h, "改了已发布的文章，要告诉读者"


def test_anonymous_source_is_labelled():
    h = _html()
    assert "金融时报" in h and "匿名消息源" in h


def test_no_personalisation():
    """站上不止一位读者：不许出现具体的人。"""
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
