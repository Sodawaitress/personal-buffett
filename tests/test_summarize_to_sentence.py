"""US-152：摘要必须断在句子边界，不能停在半句上。

08-14 快照实测：210 只股票里 71 只的 reasoning 停在半句，其中 44 只长度
正好是 200 —— 就是 `letter_text[:200]` 这个硬切。妈妈在卡片上读到的是
「…在技术行业中的竞争优势。\n\n基于以上，」这种断头话（AAPL 实例）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.buffett_utils import summarize_to_sentence

# 08-14 快照里 AAPL 的真实 reasoning 开头（被切在「基于以上，」）
AAPL_REAL = (
    "苹果公司的估值确实令人感到有些惊讶，当前的PB倍数达到43.6x，远远高于行业平均水平。"
    "然而，作为一名价值投资者，我更关注公司的根本性质和长期增长潜力。"
    "苹果公司在技术行业中拥有强大的品牌和生态系统，能够为其产品和服务提供稳定的收入来源。"
    "尽管近期的新闻中提到了苹果公司的下调和损失，但我认为这并不是公司长期前景的决定性因素。"
    "苹果公司的研发投入和创新能力将继续推动其在市场中的竞争优势。"
    "基于以上，我给出持有的评级。"
)


def test_never_ends_mid_sentence():
    out = summarize_to_sentence(AAPL_REAL)
    assert out[-1] in "。！？!?…", f"结尾是半句: ...{out[-30:]}"


def test_respects_limit():
    assert len(summarize_to_sentence(AAPL_REAL)) <= 200


def test_short_text_untouched():
    s = "公司底子好，估值合理。"
    assert summarize_to_sentence(s) == s


def test_empty_and_none():
    assert summarize_to_sentence("") == ""
    assert summarize_to_sentence(None) == ""


def test_cuts_at_last_full_sentence():
    text = "第一句话。" + "第二句话。" + "第三句非常长" * 40
    out = summarize_to_sentence(text, limit=20)
    assert out == "第一句话。第二句话。"


def test_long_sentence_falls_back_to_ellipsis():
    """limit 内一个句号都没有 → 硬切但加省略号，显式表示没说完。"""
    out = summarize_to_sentence("没有句号的超长句子" * 50, limit=30)
    assert len(out) <= 31
    assert out.endswith("…")


def test_early_period_does_not_leave_stub():
    """句号太靠前时不该只留一句残摘要，宁可硬切加省略号。"""
    out = summarize_to_sentence("短。" + "后面是很长的一句没有标点的内容" * 20, limit=100)
    assert out != "短。"
    assert out.endswith("…")


def test_english_punctuation():
    out = summarize_to_sentence("First one. Second one. " + "x" * 300, limit=30)
    assert out.endswith(".")
    assert "Second one." in out


def test_no_trailing_whitespace():
    out = summarize_to_sentence("一句话。   \n\n  后面还有很多内容" * 30, limit=50)
    assert out == out.strip()
