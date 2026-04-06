# Personal Buffett — AI-Powered Value Investing Assistant

A private stock analysis web app built for my mum — a retail A-share investor in China
who needed something that speaks Buffett, not Bloomberg.

The app pulls real-time market data, runs it through a Warren Buffett-inspired analysis
framework, and delivers a daily "letter from Buffett" for each stock in her watchlist.

---

## What It Does

- **Daily stock pipeline** — fetches price, news, fund flow, and financials for each
  watchlist stock, then runs a Buffett-framework LLM analysis via Groq (free Llama 3)
- **Buffett letter** — personalised analysis letter per stock: moat assessment, capital
  allocation quality, valuation vs history, and a clear buy/hold/reduce/sell conclusion
- **Wall Street-grade signals** — ROIC trend, Owner Earnings, retained earnings efficiency,
  major-shareholder pledge ratio, margin balance, institutional holdings
- **Watchlist management** — add/remove stocks, sort by grade, filter by market/conclusion
- **Prediction tracking** — every analysis is a prediction; 7/30-day returns are
  back-filled automatically so you can see where the model is right and wrong
- **Multi-market** — A-shares (via AKShare + Sina), NZX (via yfinance), US stocks

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Flask 3 + Flask-Bcrypt |
| Database | SQLite (via db.py, schema-compatible with PostgreSQL migration) |
| A-share data | AKShare + Sina Finance API |
| NZ/US data | yfinance |
| News | RSS feeds (Sina, NZ Herald/RNZ/Stuff, RBNZ) |
| LLM analysis | Groq API — Llama 3.3 70B (free tier, 30 RPM) |
| Auth | Email/password + Google OAuth 2.0 (Authlib) |
| Automation | macOS launchd (daily pipeline + backfill) |
| Frontend | Bootstrap 5 + Chart.js + custom NYT-style CSS |

---

## Local Setup

### Prerequisites

- Python 3.11+
- pip

### Steps

```bash
# 1. Clone or download the project
git clone <repo-url>
cd stock-radar

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment variables
cp .env.example .env
# Edit .env and fill in at minimum: FLASK_SECRET_KEY and GROQ_API_KEY

# 4. Initialise the database
python3 db.py

# 5. Run the app
python3 app.py
# Open http://localhost:5001
```

### Getting a Groq API Key (required for analysis)

1. Sign up at https://console.groq.com — it's free
2. Create an API key
3. Add it to your `.env` as `GROQ_API_KEY=your_key_here`

### Google OAuth (optional)

1. Go to https://console.cloud.google.com/apis/credentials
2. Create an OAuth 2.0 Client ID (Web application)
3. Add `http://localhost:5001/auth/google/callback` as an authorised redirect URI
4. Copy the client ID and secret into `.env`

---

## Running the Pipeline Manually

```bash
# Run the full daily pipeline (fetch data + run analysis)
python3 scripts/stock_pipeline.py

# Back-fill prediction returns (finds analyses >7d old, adds actual return %)
python3 scripts/backfill_returns.py

# Back-fill with dry run (prints without writing)
python3 scripts/backfill_returns.py --dry-run
```

---

## Project Structure

```
stock-radar/
├── app.py                  Flask application (routes, auth, API)
├── db.py                   Database layer (SQLite, all queries)
├── requirements.txt
├── .env.example            Environment variable template
├── scripts/
│   ├── config.py           Watchlist, API keys, Buffett profiles
│   ├── stock_fetch.py      A-share data (price, news, financials, signals)
│   ├── pipeline.py         Per-stock analysis pipeline orchestrator
│   ├── stock_pipeline.py   Daily batch runner (all watchlist stocks)
│   ├── buffett_analyst.py  LLM prompt engineering + Groq API calls
│   ├── nz_fetch.py         NZX / RBNZ data
│   ├── macro_fetch.py      Macro data (FOMC, Fear & Greed)
│   ├── backfill_returns.py Prediction accuracy back-fill
│   └── periodic_digest.py  Weekly/monthly/quarterly digest generator
├── templates/              Jinja2 HTML templates
├── static/style.css        NYT-inspired stylesheet
└── i18n/                   English + Chinese string tables
```

---

## Security Notes

- All API keys are loaded from `.env` via `python-dotenv` — never hardcoded
- `.env` and `data/` (SQLite DB) are in `.gitignore`
- Passwords are hashed with bcrypt (Flask-Bcrypt)
- Sessions use Flask's signed cookie with `FLASK_SECRET_KEY`

---

## Design Philosophy

Built around three questions Warren Buffett asks about every business:

1. **Is this a great business?** (GREAT / GOOD / GRUESOME classification)
2. **Is the moat widening or narrowing?** (ROE/margin trend, competitive signals)
3. **Is the price reasonable?** (PE/PB vs 5-year history)

The LLM doesn't replace judgment — it synthesises data into a readable letter that
surfaces the most important signal for each stock on each day.
