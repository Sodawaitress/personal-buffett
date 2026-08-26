"""US-131/B1 胚胎期公告信号（🥚）。

数据源 = 巨潮资讯网 cninfo（证监会指定 A 股披露平台，Fly 悉尼可达，替被墙的东财）。
信号：中标 / 重大合同 / 扩产投产 = 业务在变、财报还没体现 = 胚胎期前兆。纯官方数据，非硬编码。
"""

# 关键词 → (事件类型, 命中词校验)——业务前兆类公告
_EMBRYO_KEYWORDS = {
    "中标":     ("tender_win",   ("中标", "中选")),
    "重大合同":  ("big_contract", ("合同", "协议", "订单")),
    "投产":     ("capacity",     ("投产", "扩产", "产能", "达产")),
}

import json
import urllib.parse
import urllib.request
from datetime import date, timedelta

_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded",
}


def _fmt_ts(ms):
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _query(searchkey, se_date, page, column, retries=3):
    body = urllib.parse.urlencode({
        "pageNum": page, "pageSize": 30, "column": column, "tabName": "fulltext",
        "stock": "", "searchkey": searchkey, "secid": "", "plate": "",
        "category": "", "trade": "", "seDate": se_date,
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }).encode()
    import time
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(_URL, data=body, headers=_HEADERS)
            return json.loads(urllib.request.urlopen(req, timeout=20).read())
        except Exception as e:   # 巨潮/Fly 偶发 DNS/超时 → 重试，别静默放弃
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def fetch_recent_tenders(days=30, max_pages=25):
    """近 N 天全市场胚胎期公告(中标/合同/扩产) → {code: [{code,name,title,date,url,etype}]}。
    巨潮按发布时间倒序返回；不传 seDate（"~"格式巨潮不认→空），改代码里按日期过滤+提前停。"""
    cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    out = {}
    seen = set()
    for keyword, (etype, must) in _EMBRYO_KEYWORDS.items():
        for column in ("szse", "sse"):
            for page in range(1, max_pages + 1):
                try:
                    j = _query(keyword, "", page, column)
                except Exception:
                    break
                anns = j.get("announcements") or []
                if not anns:
                    break
                oldest = "9999"
                for a in anns:
                    d = _fmt_ts(a.get("announcementTime"))
                    oldest = min(oldest, d) if d else oldest
                    if d and d < cutoff:
                        continue
                    code = str(a.get("secCode") or "").zfill(6)
                    if not code or not code.isdigit():
                        continue
                    title = (a.get("announcementTitle") or "").replace("<em>", "").replace("</em>", "")
                    if not any(w in title for w in must):
                        continue
                    key = (code, d, title)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.setdefault(code, []).append({
                        "code": code, "name": a.get("secName"), "title": title, "date": d,
                        "url": "http://static.cninfo.com.cn/" + (a.get("adjunctUrl") or ""),
                        "etype": etype,
                    })
                if oldest < cutoff or page >= int(j.get("totalpages") or page):
                    break
    return out


def tenders_for(codes, days=30):
    """只返回给定自选股里近期有中标的：{code: [...]}。"""
    codes = {str(c).zfill(6) for c in codes}
    m = fetch_recent_tenders(days=days)
    return {c: v for c, v in m.items() if c in codes and v}


def run_tender_refresh(codes, days=30):
    """抓自选股近期中标 → 存 stock_events(source='cninfo_tender')。供每日 job / 胚胎期引擎读。"""
    from scripts.catalyst_calendar import save_catalyst_events
    # 只保留 stocks 表里已跟踪的（stock_events 有外键约束）
    try:
        from radar_app.data.core import get_conn
        with get_conn() as c:
            tracked = {r["code"] for r in c.execute("SELECT code FROM stocks").fetchall()}
        codes = [c for c in codes if str(c).zfill(6) in tracked]
    except Exception:
        pass
    hit = tenders_for(codes, days=days)

    # US-183：存下来时就把「这单占年营收多少」算好。
    #
    # 用户妈妈问「能不能看订单量」—— 方向对，但「快」争不来（公告一出所有人
    # 同时看到）。能争的是**「谁先看懂」**：同样一笔 1.2 亿的订单，
    # 对营收 10 亿的公司是 12%（大事），对营收 1000 亿的是 0.12%（噪音）。
    # 差一百倍，而绝大多数人不会当场去算。
    import db as _db
    from scripts.order_size import size_up

    def _annual(code):
        try:
            return (_db.get_fundamentals(code) or {}).get("annual") or []
        except Exception:
            return []

    events = []
    for code, tenders in hit.items():
        ann = _annual(code)
        for t in tenders[:3]:   # 每股最多存3条最新
            detail = {"url": t["url"], "name": t["name"]}
            try:
                sz = size_up(t["title"], ann)
            except Exception:
                sz = {}
            if sz:
                # 标题没写金额时 size_up 返回空 —— 那就只存标题，不编数
                detail["order_size"] = sz
            events.append({
                "code": code,
                "event_type": t.get("etype", "tender_win"),
                "event_date": t["date"],
                "summary": t["title"] + (f"（{sz['text']}）" if sz else ""),
                "detail": detail,
            })
    n = save_catalyst_events(events, source="cninfo_tender") if events else 0
    return {"codes_with_tender": len(hit), "events_saved": n}
