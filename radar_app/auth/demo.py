"""Demo user — one-click read-only access, no registration required."""

_DEMO_EMAIL = "demo@personalbuffett.app"

_DEMO_STOCKS = [
    ("AAPL",   "Apple Inc.",                 "us"),
    ("NVDA",   "NVIDIA Corporation",         "us"),
    ("DUOL",   "Duolingo, Inc.",             "us"),
    ("LULU",   "Lululemon Athletica Inc.",   "us"),
    ("SPOT",   "Spotify Technology S.A.",    "us"),
    ("XRO.NZ", "Xero Limited",              "nz"),
    ("ETSY",   "Etsy, Inc.",                "us"),
]


def ensure_demo_user() -> dict:
    """Return the demo user dict, creating it and its watchlist if needed."""
    from radar_app.data.core import get_conn

    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE email=:email", {"email": _DEMO_EMAIL}).fetchone()
        if not row:
            c.execute(
                "INSERT INTO users(email, display_name, role, locale, region) "
                "VALUES (:email,:name,'member','en','nz') ON CONFLICT DO NOTHING",
                {"email": _DEMO_EMAIL, "name": "Demo"},
            )
            row = c.execute("SELECT * FROM users WHERE email=:email", {"email": _DEMO_EMAIL}).fetchone()

        user = dict(row)
        _seed_watchlist(c, user["id"])

    return user


def _seed_watchlist(c, user_id: int):
    demo_codes = {code for code, _, _ in _DEMO_STOCKS}

    # Upsert each demo stock — restores soft-deleted entries
    for code, name, market in _DEMO_STOCKS:
        c.execute(
            "INSERT INTO stocks(code, name, market) VALUES(:code,:name,:market) ON CONFLICT DO NOTHING",
            {"code": code, "name": name, "market": market},
        )
        c.execute(
            """
            INSERT INTO user_watchlist(user_id, stock_code, status)
            VALUES (:uid, :code, 'watching')
            ON CONFLICT(user_id, stock_code) DO UPDATE SET removed_at=NULL, status='watching'
            """,
            {"uid": user_id, "code": code},
        )

    # Remove anything the demo user picked up that isn't in the curated list
    placeholder = ",".join(f"'{c_}'" for c_ in demo_codes)
    c.execute(
        f"UPDATE user_watchlist SET removed_at=CURRENT_TIMESTAMP "
        f"WHERE user_id=:uid AND removed_at IS NULL AND stock_code NOT IN ({placeholder})",
        {"uid": user_id},
    )
