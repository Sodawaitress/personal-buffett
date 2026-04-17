"""System-level service helpers."""

from datetime import datetime
import json
import os
import ssl
import subprocess
import sys
import urllib.request

import db
from radar_app.shared.runtime import CN_TZ


def build_report_context(date=None, period="daily"):
    report = db.get_report(date, period=period) or db.get_report(date, period="daily")
    if not report:
        return None
    reports = (
        db.list_reports(limit=10, period="daily")
        + db.list_reports(limit=5, period="weekly")
        + db.list_reports(limit=3, period="monthly")
        + db.list_reports(limit=2, period="quarterly")
    )
    reports.sort(key=lambda item: item["date"], reverse=True)
    return {
        "report": report,
        "reports": reports,
        "now": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    }


def build_accuracy_context():
    return {
        "stats": db.get_accuracy_stats(),
        "now": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
    }


def run_script(root_path, script_name, *args, timeout):
    script = os.path.join(root_path, "scripts", script_name)
    try:
        result = subprocess.run(
            [sys.executable, script, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(str(exc)) from exc
    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout[-3000:],
        "stderr": result.stderr[-500:],
    }


def update_locale_preference(user_id, region, locale):
    if user_id:
        db.update_user_settings(user_id, region, locale)


def save_general_settings(user_id, region, locale):
    db.update_user_settings(user_id, region, locale)


def save_push_settings(user_id, notify_daily, webhook):
    db.upsert_push_settings(
        user_id,
        notify_daily=notify_daily,
        wecom_webhook=webhook or None,
    )


def send_push_test(user_id):
    push_settings = db.get_push_settings(user_id)
    key = (push_settings or {}).get("wecom_webhook", "")
    if not key:
        return "danger", "请先填写 Server酱 SendKey。"

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        payload = json.dumps(
            {
                "title": "股票雷达 · 推送测试",
                "desp": "推送配置正常 ✅ 你会在每个交易日 15:30 收到今日日报。",
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
            return "success", "测试消息已发送，请查收微信。"
        return "danger", f"Server酱 返回错误：{resp}"
    except Exception as e:
        return "danger", f"发送失败：{e}"


def get_settings_context(user_id):
    return {"push_settings": db.get_push_settings(user_id) or {}}
