"""User and push settings queries."""

from radar_app.data.core import get_conn


def create_user(email, password_hash=None, display_name=None, avatar_url=None, role="member"):
    with get_conn() as c:
        count = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            role = "admin"
        c.execute(
            """
            INSERT OR IGNORE INTO users(email, password_hash, display_name, avatar_url, role)
            VALUES (?,?,?,?,?)
        """,
            (email, password_hash, display_name, avatar_url, role),
        )


def get_user_by_email(email):
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id):
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def user_exists(email):
    with get_conn() as c:
        return bool(c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone())


def update_user_settings(user_id, region=None, locale=None):
    fields, vals = [], []
    if region is not None:
        fields.append("region=?")
        vals.append(region)
    if locale is not None:
        fields.append("locale=?")
        vals.append(locale)
    if not fields:
        return
    vals.append(user_id)
    with get_conn() as c:
        c.execute(f"UPDATE users SET {','.join(fields)} WHERE id=?", vals)


def update_last_login(user_id):
    with get_conn() as c:
        c.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user_id,))


def get_or_create_oauth_user(provider, provider_id, email, display_name, avatar_url):
    with get_conn() as c:
        row = c.execute(
            """
            SELECT u.* FROM users u
            JOIN user_oauth o ON o.user_id = u.id
            WHERE o.provider=? AND o.provider_id=?
        """,
            (provider, provider_id),
        ).fetchone()
        if row:
            return dict(row)

        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if row:
            user_id = row["id"]
            c.execute(
                "INSERT OR IGNORE INTO user_oauth(user_id,provider,provider_id) VALUES(?,?,?)",
                (user_id, provider, provider_id),
            )
            c.execute(
                "UPDATE users SET display_name=?,avatar_url=? WHERE id=?",
                (display_name, avatar_url, user_id),
            )
            return dict(c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())

        count = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        role = "admin" if count == 0 else "member"
        c.execute(
            """
            INSERT INTO users(email, display_name, avatar_url, role)
            VALUES (?,?,?,?)
        """,
            (email, display_name, avatar_url, role),
        )
        user_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute(
            "INSERT INTO user_oauth(user_id,provider,provider_id) VALUES(?,?,?)",
            (user_id, provider, provider_id),
        )
        return dict(c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


def list_users():
    with get_conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM users ORDER BY created_at")]


def complete_onboarding(user_id):
    with get_conn() as c:
        c.execute("UPDATE users SET onboarding_done=1 WHERE id=?", (user_id,))


def get_push_settings(user_id):
    with get_conn() as c:
        row = c.execute("SELECT * FROM user_push_settings WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else {}


def upsert_push_settings(user_id, **kwargs):
    current = get_push_settings(user_id)
    if not current:
        with get_conn() as c:
            c.execute("INSERT INTO user_push_settings(user_id) VALUES(?)", (user_id,))
    if not kwargs:
        return
    fields = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [user_id]
    with get_conn() as c:
        c.execute(f"UPDATE user_push_settings SET {fields} WHERE user_id=?", vals)
