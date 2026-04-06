"""
Personal Buffett · NZ Stock Profiles
Buffett-style moat analysis for top NZX companies
"""

NZ_PROFILES = {
    "FPH.NZ": {
        "name":       "Fisher & Paykel Healthcare",
        "sector":     "Healthcare",
        "grade":      "A",
        "emoji":      "🏆",
        "moat":       "Proprietary respiratory tech + hospital switching costs. Hospitals don't switch once staff are trained on FPH gear.",
        "roe_note":   "Consistently 20–30% ROE. Rare in NZ.",
        "story":      "The quiet giant of NZ manufacturing. Every ICU on earth has FPH equipment. Buffett would love this — customers literally cannot easily switch.",
        "watch":      ["US hospital capex cycle", "NZD/USD", "R&D pipeline", "Gross margin"],
        "key_risk":   "High valuation (PE 40+). One bad product cycle hurts.",
    },
    "MFT.NZ": {
        "name":       "Mainfreight",
        "sector":     "Logistics",
        "grade":      "A",
        "emoji":      "🏆",
        "moat":       "Culture + scale network. Don Braid built a logistics business that genuinely treats drivers like owners. Competitors can't copy culture.",
        "roe_note":   "ROE 25–35%. Compound machine.",
        "story":      "Buffett's favourite kind of business: boring industry, exceptional management, impossible to replicate culture. Started in Auckland, now global.",
        "watch":      ["Global freight volumes", "Asian expansion", "Management succession"],
        "key_risk":   "Global recession kills freight volumes hard and fast.",
    },
    "AIA.NZ": {
        "name":       "Auckland Airport",
        "sector":     "Infrastructure",
        "grade":      "B+",
        "emoji":      "✅",
        "moat":       "Literal monopoly. One airport for 1.7M people. You cannot build a competing airport.",
        "roe_note":   "Steady 8–12% ROE, inflates with expansion capex.",
        "story":      "Buffett bought Burlington Northern railroad for the same reason — toll-road economics. AIA is NZ's toll gate to the world.",
        "watch":      ["Tourist arrivals", "China-NZ travel recovery", "Aeronautical pricing reviews"],
        "key_risk":   "Regulatory risk on landing fees. Heavy capex for terminal expansion.",
    },
    "SPK.NZ": {
        "name":       "Spark",
        "sector":     "Telecom",
        "grade":      "B",
        "emoji":      "✅",
        "moat":       "Scale + spectrum licences. Telecoms are sticky — people rarely switch providers.",
        "roe_note":   "ROE 20–25% but declining slowly with 5G investment.",
        "story":      "Like a utility but with dividends. Not exciting, but reliable. Buffett bought AT&T type businesses for income.",
        "watch":      ["5G rollout costs", "Broadband competition", "Dividend sustainability"],
        "key_risk":   "Structural decline in voice revenue, price competition from 2degrees.",
    },
    "RYM.NZ": {
        "name":       "Ryman Healthcare",
        "sector":     "Property / Healthcare",
        "grade":      "C+",
        "emoji":      "🟡",
        "moat":       "Integrated retirement model is hard to copy. But they over-expanded into Australia and debt is now a problem.",
        "roe_note":   "ROE collapsed from 15% to near zero. Debt-heavy.",
        "story":      "Great business concept, wrong execution. NZ ageing population is a tailwind. But $2B+ debt load means every interest rate hike hurts badly.",
        "watch":      ["Debt reduction progress", "Australian operations", "NZ property prices"],
        "key_risk":   "Balance sheet is the risk. If rates stay high, this is a prolonged recovery.",
    },
    "MEL.NZ": {
        "name":       "Meridian Energy",
        "sector":     "Energy",
        "grade":      "B",
        "emoji":      "✅",
        "moat":       "100% renewable hydro assets. Government-owned lakes. Cannot be replicated.",
        "roe_note":   "ROE 12–18%, stable. High dividend yield.",
        "story":      "Owns some of NZ's biggest hydro lakes. The water flows, the power generates, the dividends arrive. Simple business, durable cashflow.",
        "watch":      ["Lake inflows (La Niña vs El Niño)", "Electricity demand from data centres", "Aluminium smelter contract"],
        "key_risk":   "Drought year kills generation. NZ$-denominated earnings, limited growth.",
    },
    "WHS.NZ": {
        "name":       "The Warehouse Group",
        "sector":     "Retail",
        "grade":      "C",
        "emoji":      "⚠️",
        "moat":       "Brand recognition but no real moat. Retail is brutal.",
        "roe_note":   "ROE 10–15% but volatile. Dividend cuts in bad years.",
        "story":      "The 'red sheds' are NZ retail staple but Amazon and online retailers are the existential threat. Buffett sold his retail holdings for this reason.",
        "watch":      ["Online competition", "Consumer spending in NZ", "Cost inflation"],
        "key_risk":   "Secular decline in big-box retail globally.",
    },
    "FBU.NZ": {
        "name":       "Fletcher Building",
        "sector":     "Construction",
        "grade":      "C",
        "emoji":      "⚠️",
        "moat":       "Scale in NZ construction but low barriers to entry. Cyclical.",
        "roe_note":   "Highly variable ROE (5–15%). Had major losses on Australian projects.",
        "story":      "A cautionary tale. Gruesome business in Buffett's language — construction requires constant capital, has thin margins, is cyclical and contract-dependent.",
        "watch":      ["NZ housing consents", "Infrastructure pipeline", "Management track record"],
        "key_risk":   "Fixed-price contracts. One bad project wipes years of profit.",
    },
    "NPH.NZ": {
        "name":       "Napier Port",
        "sector":     "Infrastructure",
        "grade":      "B",
        "emoji":      "✅",
        "moat":       "Regional monopoly port for Hawke's Bay/Gisborne freight. Exports apples, logs, horticulture.",
        "roe_note":   "ROE 8–12%, stable. Cyclone Gabrielle disruption was one-off.",
        "story":      "Small but beautiful — regional monopoly serving NZ's fruit bowl. Climate risk from Hawke's Bay flooding is the wild card.",
        "watch":      ["Log export volumes", "Horticulture season", "Cyclone recovery"],
        "key_risk":   "Natural disaster exposure. Concentrated regional economy.",
    },
    "PCT.NZ": {
        "name":       "Precinct Properties",
        "sector":     "Property",
        "grade":      "B-",
        "emoji":      "🟡",
        "moat":       "Premium CBD office locations in Auckland/Wellington. Hard to replicate.",
        "roe_note":   "REIT-style returns 6–9%. Interest rate sensitive.",
        "story":      "Owns the best office towers in NZ cities. Work-from-home is the risk. Premium tenants tend to be stickier than suburban office.",
        "watch":      ["Office occupancy rates", "Interest rates", "Downtown Auckland development"],
        "key_risk":   "WFH structural shift. High debt typical of REITs.",
    },
}

# NZX market sectors for homepage
NZ_SECTORS = [
    {"name": "Healthcare",    "emoji": "🏥", "desc": "FPH dominates. NZ's strongest global brand.", "color": "#3b82f6"},
    {"name": "Logistics",     "emoji": "🚚", "desc": "Mainfreight — a global compounder from Auckland.", "color": "#10b981"},
    {"name": "Infrastructure","emoji": "✈️", "desc": "Airports, ports, utilities. Monopoly economics.", "color": "#f59e0b"},
    {"name": "Energy",        "emoji": "💧", "desc": "100% renewable. Hydro lakes you can't replicate.", "color": "#8b5cf6"},
    {"name": "Property",      "emoji": "🏢", "desc": "REITs + retirement villages. Rate-sensitive.", "color": "#ef4444"},
]

# What Buffett would say about NZ as a market
NZ_MARKET_CONTEXT = """
New Zealand punches above its weight. It has:
- Rule of law and property rights (Buffett prerequisite #1)
- Small but high-quality companies with genuine moats
- A transparent, well-regulated market
- Two world-class businesses in FPH and Mainfreight
- Infrastructure monopolies (airports, ports) with pricing power

The challenge: the NZX is small (100 companies), illiquid, and NZD-denominated.
For a NZ-based investor, it's your home court advantage — you understand the businesses.
"""
