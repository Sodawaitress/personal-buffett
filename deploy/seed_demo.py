#!/usr/bin/env python3
"""
Seed a fresh demo SQLite database.
Called at container startup — idempotent (safe to run multiple times).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radar_app.data.core import DATABASE_URL, init_db, _migrate, get_conn

print(f"[seed_demo] target DB: {DATABASE_URL}")
init_db()
_migrate()
print("[seed_demo] schema ready")

# ── Demo stocks ───────────────────────────────────────────────────────────────

STOCKS = [
    ("AAPL",    "Apple Inc.",         "us", "Technology",  "USD"),
    ("NVDA",    "Nvidia Corporation", "us", "Technology",  "USD"),
    ("DUOL",    "Duolingo Inc.",      "us", "Technology",  "USD"),
    ("LULU",    "Lululemon Athletica","us", "Consumer",    "USD"),
    ("SPOT",    "Spotify Technology", "us", "Technology",  "USD"),
    ("XRO.NZ",  "Xero Limited",       "nz", "Technology",  "NZD"),
    ("ETSY",    "Etsy Inc.",          "us", "Consumer",    "USD"),
]

PRICES = {
    "AAPL":   dict(price=211.45, change_pct=1.12,  market_cap=3_250_000_000_000, pe_ratio=31.5, pb_ratio=48.0),
    "NVDA":   dict(price=112.80, change_pct=2.34,  market_cap=2_760_000_000_000, pe_ratio=36.0, pb_ratio=42.0),
    "DUOL":   dict(price=238.60, change_pct=-0.85, market_cap=9_800_000_000,     pe_ratio=None, pb_ratio=18.0),
    "LULU":   dict(price=252.30, change_pct=0.42,  market_cap=32_100_000_000,    pe_ratio=24.0, pb_ratio=14.0),
    "SPOT":   dict(price=328.50, change_pct=1.67,  market_cap=62_800_000_000,    pe_ratio=52.0, pb_ratio=12.0),
    "XRO.NZ": dict(price=148.20, change_pct=0.93,  market_cap=23_400_000_000,    pe_ratio=78.0, pb_ratio=14.0),
    "ETSY":   dict(price=51.40,  change_pct=-1.23, market_cap=6_200_000_000,     pe_ratio=19.0, pb_ratio=6.0),
}

FUNDAMENTALS = {
    "AAPL": dict(
        pe_current=31.5, pb_current=48.0,
        annual_json=json.dumps([
            {"year": 2024, "roe": 147.0, "net_margin": 26.4, "debt_ratio": 320.0, "revenue_growth": 2.0},
            {"year": 2023, "roe": 171.9, "net_margin": 25.3, "debt_ratio": 340.0, "revenue_growth": -2.8},
            {"year": 2022, "roe": 196.9, "net_margin": 25.3, "debt_ratio": 280.0, "revenue_growth": 7.8},
        ]),
    ),
    "NVDA": dict(
        pe_current=36.0, pb_current=42.0,
        annual_json=json.dumps([
            {"year": 2024, "roe": 122.0, "net_margin": 55.0, "debt_ratio": 42.0, "revenue_growth": 122.0},
            {"year": 2023, "roe": 91.0,  "net_margin": 16.2, "debt_ratio": 48.0, "revenue_growth": 0.2},
            {"year": 2022, "roe": 43.8,  "net_margin": 36.2, "debt_ratio": 52.0, "revenue_growth": 61.4},
        ]),
    ),
    "DUOL": dict(
        pe_current=None, pb_current=18.0,
        annual_json=json.dumps([
            {"year": 2024, "roe": 8.2,  "net_margin": 4.8,  "debt_ratio": 18.0, "revenue_growth": 41.0},
            {"year": 2023, "roe": -5.1, "net_margin": -6.2, "debt_ratio": 22.0, "revenue_growth": 44.0},
            {"year": 2022, "roe": -28.0,"net_margin": -22.0,"debt_ratio": 28.0, "revenue_growth": 50.0},
        ]),
    ),
    "LULU": dict(
        pe_current=24.0, pb_current=14.0,
        annual_json=json.dumps([
            {"year": 2024, "roe": 58.0, "net_margin": 16.4, "debt_ratio": 28.0, "revenue_growth": 16.0},
            {"year": 2023, "roe": 63.2, "net_margin": 15.8, "debt_ratio": 25.0, "revenue_growth": 30.0},
            {"year": 2022, "roe": 55.0, "net_margin": 15.2, "debt_ratio": 22.0, "revenue_growth": 29.0},
        ]),
    ),
    "SPOT": dict(
        pe_current=52.0, pb_current=12.0,
        annual_json=json.dumps([
            {"year": 2024, "roe": 22.0, "net_margin": 3.2,  "debt_ratio": 55.0, "revenue_growth": 19.0},
            {"year": 2023, "roe": -18.0,"net_margin": -4.1, "debt_ratio": 60.0, "revenue_growth": 13.0},
            {"year": 2022, "roe": -28.0,"net_margin": -7.8, "debt_ratio": 62.0, "revenue_growth": 21.0},
        ]),
    ),
    "XRO.NZ": dict(
        pe_current=78.0, pb_current=14.0,
        annual_json=json.dumps([
            {"year": 2024, "roe": 18.2, "net_margin": 9.8,  "debt_ratio": 32.0, "revenue_growth": 22.0},
            {"year": 2023, "roe": 4.2,  "net_margin": 2.1,  "debt_ratio": 35.0, "revenue_growth": 28.0},
            {"year": 2022, "roe": -8.4, "net_margin": -8.2, "debt_ratio": 38.0, "revenue_growth": 31.0},
        ]),
    ),
    "ETSY": dict(
        pe_current=19.0, pb_current=6.0,
        annual_json=json.dumps([
            {"year": 2024, "roe": 28.0, "net_margin": 10.2, "debt_ratio": 88.0, "revenue_growth": 3.0},
            {"year": 2023, "roe": 32.0, "net_margin": 10.8, "debt_ratio": 85.0, "revenue_growth": -1.0},
            {"year": 2022, "roe": 38.0, "net_margin": 13.2, "debt_ratio": 80.0, "revenue_growth": 10.0},
        ]),
    ),
}

# ── Pre-written Buffett letters ───────────────────────────────────────────────

ANALYSES = {
    "AAPL": {
        "grade": "A",
        "conclusion": "Hold",
        "moat": "32/35: Ecosystem lock-in and brand are among the strongest moats in modern capitalism",
        "management": "26/30: Aggressive buybacks have retired 40%+ of shares over a decade",
        "valuation": "10/15: P/E 31× is a slight premium; services-mix shift justifies re-rating",
        "fund_flow_summary": "Safety 18/20: $170B in cash and marketable securities",
        "framework_used": "buffett",
        "quant_score": 84,
        "reasoning": "Best-in-class consumer franchise; hold at current valuation, add on corrections.",
        "letter_html": """Berkshire owns roughly 5.6% of Apple, and I'll tell you exactly why: this is the most powerful consumer franchise on Earth. When you buy an iPhone, you don't just buy a phone — you buy into an ecosystem of apps, payments, health data, and social identity that is extraordinarily expensive to leave. Switching costs that aren't written anywhere in the annual report are the most durable kind.

The numbers tell the story clearly. ROE over 147% — yes, that's buyback-inflated, but the underlying business earns a 26.4% net margin on $395B of revenue. Services has grown to nearly 25% of revenue at near-80% gross margins. The business is getting structurally better even as hardware growth slows.

The thing I watch most carefully: China, which represents about 17% of revenue, is both a manufacturing dependency and a market under genuine geopolitical pressure. The India pivot is real but years away from maturity.

At P/E 31.5×, Apple is no longer the screaming bargain it was in 2019. But when you own a business this good, the right question is almost always: what would cause me to sell, not when do I add more?

My verdict: Hold. The franchise earns its valuation premium. I'd add aggressively on any broad market correction that pushes it below P/E 25×.

— Warren Buffett (Personal Edition)""",
    },
    "NVDA": {
        "grade": "B+",
        "conclusion": "Hold",
        "moat": "28/35: CUDA software ecosystem creates switching costs that pure hardware cannot",
        "management": "24/30: Jensen Huang has built one of the great capital-allocation track records in tech",
        "valuation": "8/15: P/E 36× prices in perfection — leaves no room for execution stumbles",
        "fund_flow_summary": "Safety 16/20: Net cash positive; data centre capex from customers funds Nvidia's growth",
        "framework_used": "growth_tech",
        "quant_score": 78,
        "reasoning": "Real AI infrastructure moat; expensive but the cycle has years to run.",
        "letter_html": """I spent decades avoiding semiconductor companies. Too cyclical, too capital-intensive, too dependent on the next process node. Then Nvidia came along and did something I hadn't seen before: they turned a commodity chip into a platform.

CUDA — Nvidia's programming language for GPUs — was released in 2006. Today, hundreds of thousands of researchers, engineers, and developers have built their careers around it. That's not a hardware advantage. That's a switching cost you can't buy or copy.

The numbers from 2024 are almost surreal: revenue growth of 122%, net margin of 55%, ROE of 122%. I've seen good businesses in my time. I've rarely seen a business accelerate like this at this scale. Every major cloud provider, every AI lab, every enterprise building a model runs on Nvidia's infrastructure.

The risk I'd be honest about: this level of growth attracts competition like nothing else. AMD is credible. Google and Amazon are designing their own chips. Intel is trying. But changing the deep infrastructure of AI training is not a weekend project — Nvidia's installed base gives them a five-year head start at minimum.

The valuation at P/E 36× is the only thing keeping me from conviction buying. When the AI capital expenditure cycle eventually normalises — and it will — the earnings multiple will compress even if earnings don't fall.

My verdict: Hold what you own. I wouldn't add aggressively at this price. But I also wouldn't bet against Jensen Huang.

— Warren Buffett (Personal Edition)""",
    },
    "DUOL": {
        "grade": "B",
        "conclusion": "Watch",
        "moat": "20/35: Habit formation and gamification create sticky daily users, but no hard lock-in",
        "management": "22/30: Luis von Ahn built the product right; now proving he can build the business",
        "valuation": "7/15: No P/E yet; P/S of ~12× assumes the monetisation story plays out perfectly",
        "fund_flow_summary": "Safety 14/20: Recently turned profitable; balance sheet clean with no debt",
        "framework_used": "growth_tech",
        "quant_score": 62,
        "reasoning": "Genuine engagement moat; watch for monetisation proof before adding at this price.",
        "letter_html": """Every morning, 40 million people open an app featuring a green owl with a slightly judgmental expression. Some of them are genuinely learning Spanish. All of them are feeding a habit loop that Duolingo has engineered with rare precision.

Luis von Ahn is one of the most thoughtful product builders I've come across. He sold reCAPTCHA to Google and used the proceeds to fund a genuinely good idea: make language learning free, fun, and addictive. The DAU/MAU ratio of 32% is the kind of engagement metric that serious consumer businesses dream about.

Here's my honest hesitation. Engagement is not the same as pricing power. Duolingo's average revenue per user is still low — most users are on the free tier. The subscription conversion is improving, but slowly. And the language learning market, while large, is filled with motivated competitors: Rosetta Stone, Babbel, and increasingly, AI tutors that can hold a genuine conversation.

What I'm watching for: can Duolingo raise prices without losing users? Can the new AI features — personalised conversation practice — create a tier of the product that users will actually pay $30 a month for? If yes, the economics change dramatically. If not, this is a great free product with a mediocre business model.

The recent turn to profitability is encouraging. But at a revenue multiple of 12×, the market is pricing in the optimistic scenario.

My verdict: Watch. I admire what they've built. I'd want to see two more quarters of subscription ARPU growth before I'd be comfortable owning it at this price.

— Warren Buffett (Personal Edition)""",
    },
    "LULU": {
        "grade": "B+",
        "conclusion": "Hold",
        "moat": "26/35: Community flywheel and premium positioning create real brand pricing power",
        "management": "23/30: Calvin McDonald has navigated the post-pandemic slowdown without destroying the brand",
        "valuation": "9/15: P/E 24× is reasonable for a premium consumer brand with this return profile",
        "fund_flow_summary": "Safety 17/20: Net cash, no debt, consistent free cash flow generation",
        "framework_used": "mature_value",
        "quant_score": 74,
        "reasoning": "Real brand moat with premium pricing power; fair value at current P/E.",
        "letter_html": """Charlie once told me that the most underrated moat in consumer goods is one you can feel in your hands. Lululemon makes products that people describe the same way they describe Apple products: you don't realise how much better it is until you try it, and then you can't go back.

I was sceptical for years. A yoga pants company? At these margins? But the numbers kept telling a story I had to respect. ROE of 58%. Net margins of 16%. Revenue growth of 16% on a base of $10B. This is not a fashion company hoping to catch a trend — it's a brand that has built a genuine community around a lifestyle.

The ambassador programme — local yoga instructors, athletes, community leaders who represent the brand — is not a marketing expense. It's a distribution network and a trust signal that takes years to build and can't be bought. This is the moat.

The men's business is the next chapter. Men now represent nearly a quarter of revenue and growing faster than women's. If Lululemon can do for men what it did for women — make them loyal to a premium-priced product they feel good wearing — the addressable market doubles.

The risk I watch: aspirational brands are fragile. One major misstep in product quality or brand perception can unravel years of equity. The 2023 sheerness scandal was contained, but it was a warning.

My verdict: Hold. At P/E 24×, this is a fair price for a business this good. I'd add on any broad consumer slowdown that pushes it toward P/E 18×.

— Warren Buffett (Personal Edition)""",
    },
    "SPOT": {
        "grade": "B",
        "conclusion": "Hold",
        "moat": "22/35: Distribution scale and discovery algorithm create sticky habits, but content costs are structural",
        "management": "21/30: Daniel Ek has proven he can run the business at scale; the path to profitability was long but real",
        "valuation": "8/15: P/E 52× reflects a business finally at the right side of unit economics",
        "fund_flow_summary": "Safety 13/20: Recently profitable; debt manageable; podcast writedowns behind them",
        "framework_used": "growth_tech",
        "quant_score": 66,
        "reasoning": "Won the streaming wars; now proving the economics work. P/E 52× prices in continued margin expansion.",
        "letter_html": """There's a version of Spotify that I would have never invested in: a music streaming business paying 70% of revenue back to the labels, growing fast but structurally unprofitable, burning cash on podcast acquisitions that didn't work. That company existed from 2008 to about 2022.

The Spotify I'm watching now is different.

Daniel Ek spent fifteen years building the distribution. 675 million users. 250 million paying subscribers. The single largest music discovery platform in human history. The labels need Spotify as much as Spotify needs them. That leverage, quietly accumulated, is now being used. Gross margins have expanded from 25% to 29% in two years. Small numbers, but the direction matters enormously in a business this size.

The audiobooks expansion is the most interesting bet. Books have 40%+ gross margins. If Spotify can convert even 10% of their user base to audiobook consumption — using the same seamless interface they've built for music — the economics of the whole business change.

What concerns me: the podcast strategy cost them billions in writedowns and executive departures. Exclusive content is a cost, not a moat. The right model is the one Apple learned the hard way — own the platform, not the content.

My verdict: Hold. The unit economics are finally working. But P/E 52× leaves no room for another strategic mistake. I'd want to see 30%+ gross margins before getting excited about adding.

— Warren Buffett (Personal Edition)""",
    },
    "XRO.NZ": {
        "grade": "B+",
        "conclusion": "Hold",
        "moat": "27/35: High switching costs in accounting software — once your books are in Xero, moving is genuinely painful",
        "management": "24/30: Sukhinder Singh Cassidy has refocused Xero on profitability without sacrificing product investment",
        "valuation": "8/15: P/E 78× is a premium, but SaaS with 95%+ retention deserves a premium multiple",
        "fund_flow_summary": "Safety 15/20: Recently profitable; strong recurring revenue base; NZD currency risk for global investors",
        "framework_used": "growth_tech",
        "quant_score": 71,
        "reasoning": "High-switching-cost SaaS with genuine global ambitions; expensive but the retention justifies a premium.",
        "letter_html": """Wellington, New Zealand is not where you expect a global software company to be born. But Rod Drury built Xero there, and in doing so, he proved something important: the best software moats aren't built in Silicon Valley — they're built in the daily habits of small business owners who have neither the time nor the inclination to switch accounting platforms.

The switching cost here is genuine and measurable. The average Xero customer has five years of financial history in the platform. Their accountant is connected. Their payroll runs through it. Their bank feeds automatically. To leave, you don't just cancel a subscription — you rebuild your financial infrastructure. That friction is the moat.

The numbers bear this out. Net revenue retention above 100%. Gross margins of 85%. A subscription base that has compounded at 20%+ for a decade. These are the metrics of a business with genuine pricing power, not a growth company hoping to find it someday.

The global expansion story — particularly the UK and US — is real but slow. The US accounting software market is dominated by Intuit's QuickBooks, which has a twenty-year head start. Xero is winning the accountant channel, but it will take time. Patience is required.

P/E 78× is the honest objection. For a NZ-listed stock, you're also taking on currency risk. But when I find a business with retention this good, I'm willing to pay for quality.

My verdict: Hold. I wouldn't add at this valuation, but I wouldn't sell a business with these retention metrics either. Watch for US growth acceleration as the key re-rating catalyst.

— Warren Buffett (Personal Edition)""",
    },
    "ETSY": {
        "grade": "B-",
        "conclusion": "Watch",
        "moat": "18/35: Two-sided marketplace with creative community, but Amazon and Temu are eroding the price-value wedge",
        "management": "19/30: Josh Silverman has managed costs well but faces structural headwinds he cannot fully control",
        "valuation": "10/15: P/E 19× looks cheap — but only if the margin compression has found a floor",
        "fund_flow_summary": "Safety 12/20: High debt from buybacks; free cash flow positive but declining",
        "framework_used": "mature_value",
        "quant_score": 54,
        "reasoning": "Real community moat but under pressure; cheap-looking valuation reflects genuine execution risk.",
        "letter_html": """Etsy is built on an idea that should be impervious to competition: people want things made by other people, not factories. A handmade ceramic mug with a story behind it is not the same product as the same mug made in Shenzhen. This is not a niche — it's a fundamental human preference that has existed since the first market day in the first village.

The question I keep returning to is whether Etsy has protected this truth, or compromised it.

The 2020 pandemic was transformative for Etsy — revenue doubled as people discovered handmade goods and home crafts. The subsequent hangover has been brutal. Revenue has been roughly flat since 2021, and the seller base is seeing attrition as competition from overseas marketplaces intensifies. When a Temu listing for $4 shows up next to an Etsy listing for $28, the burden of proof shifts entirely to Etsy: why is this worth 7× more?

The creative community — the sellers who define the platform — is Etsy's most important asset and its most fragile one. When the platform gets cluttered with drop-shipped goods masquerading as handmade, the community notices. It erodes the trust that makes the premium price defensible.

What I'd want to see: aggressive enforcement of the handmade standards, even if it shrinks the product catalogue. Quality over quantity. That's the only way to preserve the moat.

At P/E 19×, the market is pricing in modest pessimism. The cash flow is positive. The brand is still real. But this is a business that needs to make some hard choices.

My verdict: Watch. The moat exists but is under pressure. I'd want to see seller quality metrics improve and revenue stabilise before adding at any price.

— Warren Buffett (Personal Edition)""",
    },
}

# ── Seed ─────────────────────────────────────────────────────────────────────

with get_conn() as c:
    # Stocks
    for code, name, market, sector, currency in STOCKS:
        c.execute(
            "INSERT INTO stocks(code,name,market,sector,currency) VALUES(:code,:name,:market,:sector,:currency) ON CONFLICT DO NOTHING",
            {"code": code, "name": name, "market": market, "sector": sector, "currency": currency},
        )

    # Prices
    for code, p in PRICES.items():
        c.execute(
            "INSERT INTO stock_prices(code,price,change_pct,market_cap,pe_ratio,pb_ratio) "
            "VALUES(:code,:price,:change_pct,:market_cap,:pe_ratio,:pb_ratio)",
            {"code": code, **p},
        )

    # Fundamentals
    for code, f in FUNDAMENTALS.items():
        c.execute(
            "INSERT INTO stock_fundamentals(code,pe_current,pb_current,annual_json) "
            "VALUES(:code,:pe,:pb,:annual) "
            "ON CONFLICT(code) DO UPDATE SET pe_current=excluded.pe_current, pb_current=excluded.pb_current, annual_json=excluded.annual_json",
            {"code": code, "pe": f["pe_current"], "pb": f["pb_current"], "annual": f["annual_json"]},
        )

    # Analysis
    from datetime import date
    today = date.today().isoformat()
    for code, a in ANALYSES.items():
        c.execute(
            "INSERT INTO analysis_results"
            "(code,period,analysis_date,grade,conclusion,reasoning,letter_html,"
            "moat,management,valuation,fund_flow_summary,framework_used,quant_score)"
            " VALUES(:code,'daily',:today,:grade,:conclusion,:reasoning,:letter_html,"
            ":moat,:management,:valuation,:fund_flow_summary,:framework_used,:quant_score)"
            " ON CONFLICT(code,period,analysis_date) DO UPDATE SET"
            " grade=excluded.grade, conclusion=excluded.conclusion, letter_html=excluded.letter_html",
            {"code": code, "today": today, **{k: a[k] for k in
             ("grade","conclusion","reasoning","letter_html","moat","management",
              "valuation","fund_flow_summary","framework_used","quant_score")}},
        )

    # Demo user
    existing = c.execute("SELECT id FROM users WHERE email='demo@personalbuffett.app'").fetchone()
    if not existing:
        c.execute(
            "INSERT INTO users(email,display_name,role,locale,region) "
            "VALUES('demo@personalbuffett.app','Demo','member','en','nz')",
        )
    demo_uid = c.execute(
        "SELECT id FROM users WHERE email='demo@personalbuffett.app'"
    ).fetchone()["id"]

    # Watchlist
    for code, name, market, *_ in STOCKS:
        c.execute(
            "INSERT INTO user_watchlist(user_id,stock_code,status) VALUES(:uid,:code,'watching') ON CONFLICT DO NOTHING",
            {"uid": demo_uid, "code": code},
        )

print(f"[seed_demo] seeded {len(STOCKS)} stocks, {len(ANALYSES)} analyses, demo user id={demo_uid}")
