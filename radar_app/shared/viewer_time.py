"""US-224：显示给人看的时间，按看的人所在地区换时区。

存储和 A 股交易日逻辑一律仍按北京时间（CN_TZ）—— 这里只管「显示」。
时区跟所在地区（region）走，不跟语言走：在新西兰读中文的人，看到的也该是新西兰时间。

没有请求上下文（定时任务、脚本）或没设地区时，退回北京时间，行为和以前完全一样。
"""

from datetime import datetime

from radar_app.shared.runtime import CN_TZ

REGION_TZ = {
    "nz": "Pacific/Auckland",
    "cn": "Asia/Shanghai",
    "hk": "Asia/Hong_Kong",
    "tw": "Asia/Taipei",
    "au": "Australia/Sydney",
    "kr": "Asia/Seoul",
    "us": "America/New_York",
}


def _session_region():
    try:
        from flask import has_request_context, session
        if has_request_context():
            return session.get("region")
    except Exception:
        pass
    return None


def viewer_tz(region=None):
    """region → tzinfo。缺省读当前会话；未知地区或时区库缺失 → 北京时间。"""
    name = REGION_TZ.get(region or _session_region() or "")
    if not name:
        return CN_TZ
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return CN_TZ


def viewer_now(region=None):
    return datetime.now(viewer_tz(region))


def viewer_now_label(region=None):
    return viewer_now(region).strftime("%Y-%m-%d %H:%M")


def tz_abbr(region=None):
    """NZDT / NZST / CST …（夏令时自动切换）。"""
    return viewer_now(region).tzname() or "CST"


def to_viewer(dt, region=None):
    """把一个存储时间换到看的人的时区。不带时区的按北京时间理解（库里的惯例）。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CN_TZ)
    return dt.astimezone(viewer_tz(region))
