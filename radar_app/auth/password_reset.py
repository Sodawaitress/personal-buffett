"""Password reset token management and email sending."""

import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from radar_app.data.core import get_conn


# ── Token helpers ─────────────────────────────────────────────────────────────

def create_reset_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    with get_conn() as c:
        c.execute(
            "INSERT INTO password_reset_tokens(user_id, token, expires_at) VALUES(:uid,:tok,:exp)",
            {"uid": user_id, "tok": token, "exp": expires_at},
        )
    return token


def consume_reset_token(token: str):
    """Return user_id if token is valid and unused, else None. Marks token as used."""
    with get_conn() as c:
        row = c.execute(
            "SELECT user_id, expires_at, used FROM password_reset_tokens WHERE token=:tok",
            {"tok": token},
        ).fetchone()
        if not row:
            return None
        if row["used"]:
            return None
        expires = datetime.fromisoformat(row["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            return None
        c.execute(
            "UPDATE password_reset_tokens SET used=1 WHERE token=:tok",
            {"tok": token},
        )
        return row["user_id"]


def count_recent_requests(user_id: int, hours: int = 1) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as c:
        return c.execute(
            "SELECT COUNT(*) AS n FROM password_reset_tokens WHERE user_id=:uid AND created_at>:cut",
            {"uid": user_id, "cut": cutoff},
        ).fetchone()["n"]


# ── Email sending ─────────────────────────────────────────────────────────────

def send_reset_email(to_email: str, reset_url: str) -> bool:
    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not gmail_user or not gmail_pass:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your SirenBuffet password"
    msg["From"] = f"SirenBuffet <{gmail_user}>"
    msg["To"] = to_email

    text_body = f"""\
You requested a password reset for your SirenBuffet account.

Click the link below to set a new password (expires in 15 minutes):
{reset_url}

If you didn't request this, you can safely ignore this email.
"""
    html_body = f"""\
<div style="font-family:Georgia,serif;max-width:480px;margin:40px auto;color:#1a1a1a">
  <h2 style="font-size:20px;margin-bottom:8px">Reset your password</h2>
  <p style="color:#555;font-size:14px">Click the button below to set a new password. This link expires in 15 minutes.</p>
  <a href="{reset_url}" style="display:inline-block;margin:20px 0;padding:12px 24px;background:#1a1a1a;color:#fff;text-decoration:none;border-radius:4px;font-size:14px">Reset Password</a>
  <p style="color:#999;font-size:12px">If you didn't request this, ignore this email. Your password won't change.</p>
  <hr style="border:none;border-top:1px solid #eee;margin-top:32px">
  <p style="color:#bbb;font-size:11px">SirenBuffet · 私人芭菲特工</p>
</div>
"""
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[email] send failed: {e}")
        return False
