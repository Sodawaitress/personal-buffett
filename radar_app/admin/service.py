"""Admin service helpers."""

import json
import ssl
import urllib.request

import db


def list_users_with_push():
    users = db.list_users()
    for user in users:
        user["push"] = db.get_push_settings(user["id"]) or {}
    return users


def get_admin_user_context(target_uid):
    target = db.get_user_by_id(target_uid)
    if not target:
        return None
    return {
        "target": target,
        "push": db.get_push_settings(target_uid) or {},
        "watchlist": db.get_user_watchlist(target_uid) or [],
    }


def save_admin_push_settings(target_uid, notify_daily, wecom_key):
    db.upsert_push_settings(
        target_uid,
        notify_daily=notify_daily,
        wecom_webhook=wecom_key or None,
    )


def send_admin_push_test(target_uid):
    target = db.get_user_by_id(target_uid)
    if not target:
        return "danger", "User not found"

    push_settings = db.get_push_settings(target_uid)
    key = (push_settings or {}).get("wecom_webhook", "")
    if not key:
        return "danger", "该用户未设置 Server酱 key。"

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        payload = json.dumps(
            {
                "title": "股票雷达 · 推送测试",
                "desp": f"管理员测试推送 ✅\n用户：{target['email']}",
            }
        ).encode()
        req = urllib.request.Request(
            f"https://sctapi.ftqq.com/{key}.send",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            resp = json.loads(response.read().decode())
        errno = resp.get("data", {}).get("errno", resp.get("code", -1))
        if errno == 0:
            return "success", "测试消息已发送。"
        return "danger", f"Server酱 返回：{resp}"
    except Exception as e:
        return "danger", f"发送失败：{e}"
