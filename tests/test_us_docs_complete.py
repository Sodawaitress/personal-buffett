"""US-165：提交里出现的 US 编号，必须在 PRODUCT.md 里有条目。

CLAUDE.md 有条强制规矩：「遇到新需求或新问题时，必须先写 User Story，再动代码」。
2026-08-24 复核发现 **US-153 / 155 / 162 / 163 有代码有提交，但 PRODUCT.md 漏了**
—— 规矩靠自觉守不住，所以用测试守。

只查 US-149 及之后的：那之后才开始用「实现状态」这套约定，
之前的历史条目不追溯。
"""
import os
import re
import subprocess

ROOT = os.path.join(os.path.dirname(__file__), '..')
FIRST_TRACKED = 149


def _documented():
    with open(os.path.join(ROOT, 'PRODUCT.md')) as f:
        return {int(n) for n in re.findall(r'^## US-(\d+)', f.read(), re.M)}


def _in_commits():
    try:
        out = subprocess.run(
            ["git", "log", "--format=%s", "-400"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        ).stdout
    except Exception:
        return set()          # 没有 git（打包环境）就跳过，不让测试假红
    return {int(n) for n in re.findall(r'\bUS-(\d+)\b', out)}


def test_every_committed_us_has_a_product_md_entry():
    committed = {n for n in _in_commits() if n >= FIRST_TRACKED}
    if not committed:
        return                # 无 git 历史，跳过
    missing = sorted(committed - _documented())
    assert not missing, (
        f"这些 US 有提交但 PRODUCT.md 没条目: {missing}\n"
        f"CLAUDE.md 要求先写 US 再动代码 —— 补上 `## US-<n> · <标题>` 一节。"
    )


def test_tracked_us_have_status_line():
    """US-149 之后的条目都要有「实现状态」行，否则没法一眼看出做完没做完。"""
    with open(os.path.join(ROOT, 'PRODUCT.md')) as f:
        text = f.read()
    blocks = re.split(r'\n## (US-(\d+)[^\n]*)\n', text)
    missing = []
    for i in range(1, len(blocks), 3):
        title, num, body = blocks[i], int(blocks[i + 1]), blocks[i + 2]
        if num < FIRST_TRACKED:
            continue
        if '实现状态' not in body[:600]:
            missing.append(title[:40])
    assert not missing, f"这些条目缺「实现状态」行: {missing}"


def test_us141_margin_of_safety_marked_done():
    """回归：US-141（安全边际）实现完了但 AC 一直没勾、状态行也没写，
    看起来像没做。它是用户家人提的需求，状态必须准确。"""
    with open(os.path.join(ROOT, 'PRODUCT.md')) as f:
        text = f.read()
    i = text.index('## US-141')
    section = text[i:text.index('\n## ', i + 10)]
    assert '实现状态' in section
    assert '✅' in section
    assert '- [ ]' not in section, "US-141 的 AC 应该全部勾上（实测已确认三条都满足）"
