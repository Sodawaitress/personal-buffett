"""US-224：新西兰英文读者的界面。

① 涨跌色跟阅读语言走：中文红涨绿跌，英文绿涨红跌，只在一个地方定义。
   西方读者把红读成「亏」—— 颜色反了，结论就反了。
② 添加搜索：高亮的市场按钮必须是实际在搜的那个。
"""
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _rule(css, selector):
    """返回某个选择器的声明体（选择器必须唯一出现）。"""
    m = re.findall(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert len(m) == 1, f"{selector!r} 应恰好出现一次，实际 {len(m)}"
    return m[0]


# ── ① 涨跌色 ────────────────────────────────────────────

def test_tokens_defined_once_and_flip_for_english():
    css = _read("static/style.css")
    root = css[css.index(":root {"):css.index("}", css.index(":root {"))]
    assert re.search(r"--up:\s*var\(--red\)", root), "中文默认：红涨"
    assert re.search(r"--down:\s*var\(--green\)", root), "中文默认：绿跌"
    en = _rule(css, 'html[lang="en"]')
    assert re.search(r"--up:\s*var\(--green\)", en), "英文：绿涨"
    assert re.search(r"--down:\s*var\(--red\)", en), "英文：红跌"
    # 只在 style.css 定义，别处不许另起一套
    for rel in ("static/css/stock.css", "static/css/watchlist.css"):
        assert not re.search(r"--(up|down)\s*:", _read(rel)), f"{rel} 不应重新定义 --up/--down"


# 价格方向 / 盈亏 / 超额 / 同比 / 资金净额 —— 必须走变量
DIRECTION_RULES = {
    "static/style.css": [
        ".stock-change.up", ".stock-change.down",
        ".stock-change-big.up", ".stock-change-big.down",
    ],
    "static/css/stock.css": [
        ".data-table .up", ".data-table .down",
        ".signal-val.up", ".signal-val.down",
        ".srow-val.up", ".srow-val.down",
        ".inst-holder-change.up", ".inst-holder-change.down",
        ".pnl-pos", ".pnl-neg",
        ".industry-signal-change.up", ".industry-signal-change.down",
        ".obook-val.up", ".obook-val.down",
        ".pickhist-avg.up", ".pickhist-avg.down",
        ".pickhist-res .up", ".pickhist-res .down",
        ".pick-chg.up", ".pick-chg.down",
        ".pick-record .up", ".pick-record .down",
        ".picks-arch-e .up", ".picks-arch-e .down",
        ".svft-out-followed_up", ".svft-out-followed_down",
    ],
    "static/css/watchlist.css": [
        ".perf-stat-val.up", ".perf-stat-val.down",
        ".rank-badge-chg.up", ".rank-badge-chg.down",
    ],
}


def test_direction_rules_use_tokens_not_hardcoded_colours():
    for rel, sels in DIRECTION_RULES.items():
        css = _read(rel)
        for sel in sels:
            body = _rule(css, sel)
            want = "var(--down)" if sel.endswith(("down", "neg")) else "var(--up)"
            assert want in body, f"{rel} {sel} 应使用 {want}，实际：{body.strip()}"
            assert not re.search(r"#[0-9a-fA-F]{3,6}|var\(--(red|green)\)", body), \
                f"{rel} {sel} 不应写死红绿：{body.strip()}"


def test_non_direction_rules_do_not_borrow_updown_tokens():
    """「颠不颠」是波动警示，不是涨跌 —— 借用 --down 会在中文里变成绿色（=涨）。"""
    css = _read("static/css/stock.css")
    for sel in (".vol-wild .vol-story", ".pvol-wild", ".pvol-wild .pvol-head", ".pvol-div-num"):
        assert "var(--up)" not in _rule(css, sel) and "var(--down)" not in _rule(css, sel), sel


def test_base_template_sets_lang_from_locale():
    """变量靠 <html lang> 切换，base.html 必须按 locale 写 lang。"""
    assert '<html lang="{{ locale }}">' in _read("templates/base.html")


def test_rendered_lang_follows_session_locale():
    from radar_app import create_app
    app = create_app()
    for loc in ("en", "zh"):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["locale"] = loc
                s["region"] = "nz"
            html = c.get("/login").get_data(as_text=True)
            assert f'<html lang="{loc}">' in html, loc


# ── ② 添加搜索高亮 ──────────────────────────────────────

def test_add_search_highlight_synced_with_stored_type():
    """localStorage 记着上次的市场（如 cn）；模板按语言预设高亮（英文=Global）。
    不同步 → 亮着 Global、实际搜 A 股 → 「AIR.NZ」No results found。"""
    js = _read("templates/stock/_add_search.html")
    init = js[js.index("DOMContentLoaded"):]
    assert re.search(r"seg-btn\[data-type=\"' \+ _addType \+ '\"\]", init), \
        "页面加载时应按 _addType 找到对应按钮并高亮"


# ── ③ 导航「今日五选」 ─────────────────────────────────

def _logged_in_page(locale, path="/settings"):
    import uuid
    from radar_app import create_app
    from radar_app.data.users import create_user, get_user_by_email
    app = create_app()
    email = f"us224-{uuid.uuid4().hex[:8]}@example.test"
    create_user(email)
    uid = get_user_by_email(email)["id"]
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = uid
            s["locale"] = locale
            s["region"] = "nz"
            s["role"] = "member"
        r = c.get(path)
        assert r.status_code == 200, (path, r.status_code)
        return r.get_data(as_text=True)


def test_picks_nav_hidden_in_english_shown_in_chinese():
    """五选是 A 股、内容只有中文：英文界面不放入口；中文界面不变。"""
    en = _logged_in_page("en")
    zh = _logged_in_page("zh")
    # 先确认真的是登录态的导航，否则「没有 /picks」会空转通过
    assert 'href="/watchlist"' in en and 'href="/watchlist"' in zh
    assert 'href="/picks"' not in en
    assert "今日五选" not in en
    assert 'href="/picks"' in zh and "今日五选" in zh


# ── ④ 语言和所在地分开 ─────────────────────────────────

def test_switching_language_keeps_region():
    """切中文不许把 nz 改成 cn（原来会，而且切回英文不恢复）。"""
    from radar_app import create_app
    app = create_app()
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["locale"] = "en"
            s["region"] = "nz"
        c.post("/set-locale", data={"locale": "zh"})
        with c.session_transaction() as s:
            assert s["locale"] == "zh" and s["region"] == "nz"
        c.post("/set-locale", data={"locale": "en"})
        with c.session_transaction() as s:
            assert s["locale"] == "en" and s["region"] == "nz"
        with c.session_transaction() as s:
            s["region"] = "cn"
        c.post("/set-locale", data={"locale": "en"})
        with c.session_transaction() as s:
            assert s["region"] == "cn", "在中国读英文的人也不该被挪到 nz"


# ── ⑤ 语言切换：小地球 + 目标语言 ───────────────────────

def test_language_toggle_shows_target_language_with_globe():
    from radar_app import create_app
    app = create_app()
    for loc, label, target in (("en", "中文", "zh"), ("zh", "EN", "en")):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["locale"] = loc
                s["region"] = "nz"
            html = c.get("/login").get_data(as_text=True)
            i = html.index('class="lang-form"')
            form = html[i:html.index("</form>", i)]
            assert "bi-globe2" in form
            assert f'name="locale" value="{target}"' in form
            assert f'<span class="btn-lang-label" lang="{target}">{label}</span>' in form, \
                f"{loc} 页面应显示目标语言 {label}"
            assert 'aria-label="' in form and "[lang_switch_aria]" not in form


def test_toggle_label_hidden_on_phones_only():
    css = _read("static/style.css")
    i = css.index(".btn-lang-label { display: none; }")
    assert "@media (max-width: 600px)" in css[i - 80:i]


# ── ⑥ 显示时间跟所在地区走 ─────────────────────────────

def test_viewer_time_follows_region_and_falls_back_to_beijing():
    from datetime import datetime, timedelta
    from radar_app.shared.viewer_time import to_viewer, tz_abbr, viewer_now, viewer_tz
    from radar_app.shared.runtime import CN_TZ
    # 没请求上下文、没地区 → 北京时间（定时任务行为不变）
    assert viewer_tz() is CN_TZ
    assert viewer_tz("xx") is CN_TZ
    assert tz_abbr("nz") in ("NZDT", "NZST")
    assert tz_abbr("cn") == "CST"
    nz, cn = viewer_now("nz"), viewer_now("cn")
    diff = (nz.replace(tzinfo=None) - cn.replace(tzinfo=None)).total_seconds() / 3600
    assert round(diff) in (4, 5), "新西兰比北京快 4–5 小时"
    # 库里不带时区的时间按北京时间理解
    stored = datetime(2026, 11, 5, 20, 0)          # 北京 20:00
    assert to_viewer(stored, "nz").strftime("%m-%d %H:%M") == "11-06 01:00"   # NZDT +13
    assert to_viewer(stored, "cn").strftime("%H:%M") == "20:00"


def test_no_hardcoded_cst_labels_in_templates():
    for rel in ("templates/brief.html", "templates/report.html"):
        assert " CST<" not in _read(rel) and "}} CST" not in _read(rel), rel


def test_home_date_uses_viewer_region():
    from radar_app import create_app
    from radar_app.dashboard.presenter import now_label
    from radar_app.shared.viewer_time import viewer_now_label
    app = create_app()
    for region in ("nz", "cn"):
        with app.test_request_context():
            from flask import session
            session["region"] = region
            assert now_label()[:13] == viewer_now_label(region)[:13]


# ── ⑦ 金额 ─────────────────────────────────────────────

def test_compact_amount_zh_unchanged_en_uses_b_m():
    from radar_app.shared.market import compact_amount
    # 中文：和改之前逐字一样（原来是 "%.0f亿" / "%+.2f亿"）
    assert compact_amount(4.1e9) == "41亿"
    assert compact_amount(1.23e8, signed=True, zh_decimals=2) == "+1.23亿"
    assert compact_amount(-5e7, signed=True, zh_decimals=2) == "-0.50亿"
    # 英文：货币 + K/M/B/T
    assert compact_amount(4.1e9, "en", "NZ$") == "NZ$4.1B"
    assert compact_amount(8.5e8, "en", "NZ$") == "NZ$850M"
    assert compact_amount(3.0e12, "en", "US$") == "US$3T"
    assert compact_amount(1.23e8, "en", "¥", signed=True) == "+¥123M"
    assert compact_amount(-5e7, "en", "¥", signed=True) == "−¥50M"
    assert compact_amount(None, "en") == "—"


def test_us_currency_is_explicit():
    from radar_app.shared.market import MARKET_CURRENCY
    assert MARKET_CURRENCY["us"] == "US$" and MARKET_CURRENCY["nz"] == "NZ$"


def test_stock_head_has_no_hardcoded_yi_or_export_label():
    head = _read("templates/stock/_head.html")
    assert "亿" not in head and "导出分析包" not in head
    assert "compact_amount" in head
    assert "导出分析包" not in _read("static/js/stock-common.js")


def test_compact_amount_filter_registered():
    from radar_app import create_app
    app = create_app()
    assert "compact_amount" in app.jinja_env.filters


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ROOT)
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("✓", name)
