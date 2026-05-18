"""Public page routes extracted from the legacy app module."""

from flask import jsonify, redirect, render_template, url_for


def register_public_routes(app):
    @app.route('/healthz')
    def healthz():
        return jsonify({"ok": True}), 200

    @app.route('/home')
    def home():
        return redirect(url_for('index'))

    @app.route('/about')
    def about():
        return render_template('about.html')

    @app.route('/demo/story')
    def demo_story():
        from radar_app.data.core import get_conn

        STORY_META = {
            "AAPL":   {"name_zh": "苹果",       "color": "#9ca3af",
                       "tagline_en": "The most powerful consumer franchise on Earth.",
                       "tagline_zh": "当今世上最强大的消费者品牌"},
            "NVDA":   {"name_zh": "英伟达",      "color": "#10b981",
                       "tagline_en": "They turned a commodity chip into a platform.",
                       "tagline_zh": "把一块芯片变成了整个行业的基础设施"},
            "DUOL":   {"name_zh": "多邻国",      "color": "#84cc16",
                       "tagline_en": "Every morning, 40 million people open this app.",
                       "tagline_zh": "每天早晨，4000万人打开这只绿猫头鹰"},
            "LULU":   {"name_zh": "lululemon",  "color": "#a78bfa",
                       "tagline_en": "The most underrated moat is one you can feel.",
                       "tagline_zh": "最好的护城河，是你能亲手感受到的那种"},
            "SPOT":   {"name_zh": "Spotify",    "color": "#4ade80",
                       "tagline_en": "15 years building distribution. 675M people listening.",
                       "tagline_zh": "十五年建流量，六亿七千五百万人在听"},
            "XRO.NZ": {"name_zh": "Xero",       "color": "#38bdf8",
                       "tagline_en": "The best moats aren't built in Silicon Valley.",
                       "tagline_zh": "最好的软件护城河，不是在硅谷建成的"},
            "ETSY":   {"name_zh": "Etsy",       "color": "#fbbf24",
                       "tagline_en": "People want things made by people, not factories.",
                       "tagline_zh": "人们想要的，是人手做的东西"},
        }
        ORDER = ["AAPL", "NVDA", "DUOL", "LULU", "SPOT", "XRO.NZ", "ETSY"]
        codes_in = "','".join(ORDER)

        with get_conn() as conn:
            stocks_raw = {r["code"]: dict(r) for r in conn.execute(
                f"SELECT code,name,market,sector FROM stocks WHERE code IN ('{codes_in}')"
            ).fetchall()}
            prices_raw = {}
            for r in conn.execute(
                f"SELECT code,price,pe_ratio,market_cap FROM stock_prices WHERE code IN ('{codes_in}') ORDER BY id DESC"
            ).fetchall():
                prices_raw.setdefault(r["code"], dict(r))
            analyses_raw = {}
            for r in conn.execute(
                f"SELECT code,grade,conclusion,moat FROM analysis_results WHERE code IN ('{codes_in}') ORDER BY id DESC"
            ).fetchall():
                analyses_raw.setdefault(r["code"], dict(r))

        def fmt_cap(mc):
            if not mc:
                return None, "—"
            mc = float(mc)
            if mc >= 1e12:
                return (round(mc / 1e12, 2), "T"), f"${mc/1e12:.2f}T"
            if mc >= 1e9:
                return (round(mc / 1e9, 1), "B"), f"${mc/1e9:.1f}B"
            return None, "—"

        stocks = []
        for code in ORDER:
            meta = STORY_META.get(code, {})
            s = stocks_raw.get(code, {})
            p = prices_raw.get(code, {})
            a = analyses_raw.get(code, {})
            moat_raw = a.get("moat") or ""
            moat_score = moat_raw.split("/")[0].strip() if "/" in moat_raw else "—"
            pe = p.get("pe_ratio")
            mc_raw, mc_fmt = fmt_cap(p.get("market_cap"))
            moat_num = int(moat_score) if moat_score.isdigit() else None
            stocks.append({
                "code": code,
                "name": s.get("name", code),
                "name_zh": meta.get("name_zh", ""),
                "color": meta.get("color", "#888888"),
                "tagline_en": meta.get("tagline_en", ""),
                "tagline_zh": meta.get("tagline_zh", ""),
                "sector": s.get("sector", ""),
                "market": (s.get("market") or "us").upper(),
                "price": f"{float(p['price']):.2f}" if p.get("price") else "—",
                "pe": f"{pe:.0f}×" if pe else "—",
                "pe_num": round(pe) if pe else None,
                "market_cap": mc_fmt,
                "mc_num": mc_raw[0] if mc_raw else None,
                "mc_unit": mc_raw[1] if mc_raw else "",
                "mc_dec": 2 if mc_raw and mc_raw[1] == "T" else 1,
                "moat_score": moat_score,
                "moat_num": moat_num,
                "grade": a.get("grade", "—"),
                "conclusion": a.get("conclusion", ""),
            })

        return render_template("demo_story.html", stocks=stocks)
