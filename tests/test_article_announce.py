"""US-215：发布 ≠ 送达。

站上 7 篇专栏，**一篇都没通知过读者**。微信推送只在
`output/daily_push.txt` 变动时触发（wechat-push.yml 的 `paths:` 只有它），
而 daily_push 从来没提过文章。

用户问「文章发了吗」，答案是：上线了，但没发出去。
这和 US-212「讲过 ≠ 发出去」是同一件事更深一层。

修法不开第二条推送通道（US-150：并行通道 = 读者收到重复推送），
而是把「哪几篇没通知过」算好塞进快照 —— 沿用 US-166 的判断：
**本仓所有沉默失败都证明「靠自觉」不成立。**
"""
from radar_app.research import articles as A


def test_wechat_push_still_has_exactly_one_trigger_path():
    """不许为了推文章再开一条推送通道 —— 那会让读者收到重复推送。"""
    s = open(".github/workflows/wechat-push.yml", encoding="utf-8").read()
    assert s.count("output/daily_push.txt") >= 1
    assert "research" not in s, "文章推送被做成了第二条通道"


def test_snapshot_carries_unannounced_articles():
    """算好塞进快照，不靠 Routine 每天记得翻。"""
    from scripts.daily_digest import _unannounced_articles
    out = _unannounced_articles()
    assert isinstance(out, list)
    for a in out:
        assert {"slug", "title", "url"} <= set(a), a
        assert a["url"].startswith("/research/")


def test_announced_ones_drop_out(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "ANNOUNCED_PATH", str(tmp_path / "ann.txt"))
    first = A.unannounced(limit=99)
    assert first, "一篇都没有？"
    A.mark_announced([first[0]["slug"]])
    after = A.unannounced(limit=99)
    assert len(after) == len(first) - 1
    assert first[0]["slug"] not in [a["slug"] for a in after]


def test_marking_is_idempotent(tmp_path, monkeypatch):
    """重复 mark 不该把文件撑大 —— 它会被每天调用。"""
    monkeypatch.setattr(A, "ANNOUNCED_PATH", str(tmp_path / "ann.txt"))
    assert A.mark_announced(["x"]) == 1
    assert A.mark_announced(["x"]) == 0


def test_batch_is_capped():
    """攒了一堆时不刷屏。"""
    assert A._MAX_PER_PUSH <= 3
    assert len(A.unannounced()) <= A._MAX_PER_PUSH


def test_routine_is_told_what_to_do_with_it():
    doc = open("CLAUDE_ROUTINE.md", encoding="utf-8").read()
    assert "new_articles" in doc, "Routine 不知道这个字段存在"
    assert "mark_announced" in doc, "Routine 不知道提完要记一笔"
    assert "发布 ≠ 送达" in doc
