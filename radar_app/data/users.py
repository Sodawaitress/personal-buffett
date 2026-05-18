"""User and push settings queries."""

from datetime import datetime, timezone

from radar_app.data.core import get_conn


def create_user(email, password_hash=None, display_name=None, avatar_url=None, role="member"):
    with get_conn() as c:
        count = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if count == 0:
            role = "admin"
        c.execute(
            """
            INSERT INTO users(email, password_hash, display_name, avatar_url, role)
            VALUES (:email,:pw,:name,:avatar,:role)
            ON CONFLICT(email) DO NOTHING
            """,
            {"email": email, "pw": password_hash, "name": display_name, "avatar": avatar_url, "role": role},
        )


def get_user_by_email(email):
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE email=:email", {"email": email}).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id):
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=:id", {"id": user_id}).fetchone()
        return dict(row) if row else None


def user_exists(email):
    with get_conn() as c:
        return bool(c.execute("SELECT 1 FROM users WHERE email=:email", {"email": email}).fetchone())


def update_user_settings(user_id, region=None, locale=None):
    fields = {}
    if region is not None:
        fields["region"] = region
    if locale is not None:
        fields["locale"] = locale
    if not fields:
        return
    set_clause = ", ".join(f"{k}=:{k}" for k in fields)
    params = {**fields, "id": user_id}
    with get_conn() as c:
        c.execute(f"UPDATE users SET {set_clause} WHERE id=:id", params)


def update_last_login(user_id):
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as c:
        c.execute("UPDATE users SET last_login=:now WHERE id=:id", {"now": now, "id": user_id})


def get_or_create_oauth_user(provider, provider_id, email, display_name, avatar_url):
    with get_conn() as c:
        row = c.execute(
            """
            SELECT u.* FROM users u
            JOIN user_oauth o ON o.user_id = u.id
            WHERE o.provider=:provider AND o.provider_id=:pid
            """,
            {"provider": provider, "pid": provider_id},
        ).fetchone()
        if row:
            return dict(row)

        row = c.execute("SELECT * FROM users WHERE email=:email", {"email": email}).fetchone()
        if row:
            user_id = row["id"]
            c.execute(
                "INSERT INTO user_oauth(user_id,provider,provider_id) VALUES(:uid,:provider,:pid) ON CONFLICT DO NOTHING",
                {"uid": user_id, "provider": provider, "pid": provider_id},
            )
            c.execute(
                "UPDATE users SET display_name=:name, avatar_url=:avatar WHERE id=:id",
                {"name": display_name, "avatar": avatar_url, "id": user_id},
            )
            return dict(c.execute("SELECT * FROM users WHERE id=:id", {"id": user_id}).fetchone())

        count = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        role = "admin" if count == 0 else "member"
        new_row = c.execute(
            "INSERT INTO users(email, display_name, avatar_url, role) VALUES(:email,:name,:avatar,:role) RETURNING id",
            {"email": email, "name": display_name, "avatar": avatar_url, "role": role},
        ).fetchone()
        user_id = new_row["id"]
        c.execute(
            "INSERT INTO user_oauth(user_id,provider,provider_id) VALUES(:uid,:provider,:pid)",
            {"uid": user_id, "provider": provider, "pid": provider_id},
        )
        return dict(c.execute("SELECT * FROM users WHERE id=:id", {"id": user_id}).fetchone())


def list_users():
    with get_conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM users ORDER BY created_at")]


def complete_onboarding(user_id):
    with get_conn() as c:
        c.execute("UPDATE users SET onboarding_done=1 WHERE id=:id", {"id": user_id})


def get_push_settings(user_id):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM user_push_settings WHERE user_id=:uid", {"uid": user_id}
        ).fetchone()
        return dict(row) if row else {}


def upsert_push_settings(user_id, **kwargs):
    current = get_push_settings(user_id)
    if not current:
        with get_conn() as c:
            c.execute(
                "INSERT INTO user_push_settings(user_id) VALUES(:uid) ON CONFLICT DO NOTHING",
                {"uid": user_id},
            )
    if not kwargs:
        return
    set_clause = ", ".join(f"{k}=:{k}" for k in kwargs)
    params = {**kwargs, "uid": user_id}
    with get_conn() as c:
        c.execute(f"UPDATE user_push_settings SET {set_clause} WHERE user_id=:uid", params)
