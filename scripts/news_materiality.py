"""
US-118 量化层：重大新闻材料度（无 LLM）。

RavenPack 式漏斗：相关度 → 新颖度去重 → 市场反应(异常收益/量能) → 材料度分。
数据只用 stock_prices(change_pct/volume) + stock_news(title/source/publish_time)。
v1 无独立指数：用同市场股票当日均值近似大盘去 β（简化事件研究）；v2 接真指数。
"""
import math
import re
from datetime import date, datetime, timedelta

from radar_app.data.core import get_conn

# ── 事件类型关键词（多标签，各带权重 0–1）────────────────────────────
_EVENT_KEYWORDS = {
    "sanction_natsec": (["制裁", "国家安全", "实体清单", "涉军", "1260h", "出口管制", "关税", "232",
                          "限制政策", "封锁", "禁令", "脱钩", "欧美限制", "加征",
                          "sanction", "entity list", "national security", "tariff", "export control",
                          "restrict", "blacklist", "decoupl"], 1.0),
    "distress":        (["停产", "减产", "停工", "亏损", "资产减值", "计提", "债务违约", "违约", "破产",
                          "重整失败", "重大诉讼", "被起诉", "查封", "冻结", "halt", "default", "impairment", "lawsuit"], 1.0),
    "regulation":      (["监管", "立案", "调查", "处罚", "问询", "退市", "证监会", "regulat", "probe", "investigation"], 0.9),
    "mna":             (["并购", "收购", "重组", "要约", "控制权", "merger", "acquisition", "takeover"], 0.85),
    "earnings":        (["业绩", "预告", "预增", "预减", "扭亏", "财报", "净利", "营收", "earnings", "guidance", "profit"], 0.7),
    "unlock":          (["解禁", "限售", "减持", "增持", "回购", "unlock", "lockup", "buyback"], 0.6),
    "operational":     (["中标", "订单", "投产", "合同", "扩产", "涨价", "降价", "contract", "order", "capacity"], 0.55),
    "pledge":          (["质押", "解押", "pledge"], 0.4),
}
# 低价值（拉低而非过滤，避免误杀）
_NOISE_KEYWORDS = ["评级", "研报", "目标价", "推荐", "买入评级", "rating", "price target", "analyst"]

_CN_STOPWORDS = set("的了和与及或在为对将把被于之股公司集团有限")


def _norm_title(title: str) -> str:
    """标题归一化：去标点/空格/常见后缀，用于近似去重。"""
    t = re.sub(r"[\s\W_]+", "", (title or "").lower())
    return t


def _token_set(title: str) -> set:
    """粗分词集合（中文按字 + 英文按词），去停用词，用于 Jaccard。"""
    t = (title or "").lower()
    words = re.findall(r"[a-z0-9]+", t)
    chars = [c for c in re.sub(r"[^一-鿿]", "", t) if c not in _CN_STOPWORDS]
    return set(words) | set(chars)


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b)


# ── 价格序列 & 市场反应 ──────────────────────────────────────────────

_series_cache: dict = {}

def _trading_idx(series, date_str: str):
    """返回 series 中第一个 >= date_str 的下标（周末/节假日新闻映射到下一交易日）。"""
    for i, (d, _, _) in enumerate(series):
        if d >= date_str:
            return i
    return None


def _price_series(code: str):
    """返回按日期升序的 [(date_str, change_pct, volume)]（去重同日取最新，带缓存）。"""
    if code in _series_cache:
        return _series_cache[code]
    with get_conn() as c:
        rows = c.execute(
            "SELECT fetched_at, change_pct, volume FROM stock_prices "
            "WHERE code=:code ORDER BY fetched_at ASC",
            {"code": code},
        ).fetchall()
    series, seen = [], {}
    for r in rows:
        d = str(r["fetched_at"])[:10]
        seen[d] = (r["change_pct"], r["volume"])
    for d in sorted(seen):
        chg, vol = seen[d]
        series.append((d, chg, vol))
    _series_cache[code] = series
    return series


_market_cache: dict = {}

def _market_mean_change(market: str, date_str: str) -> float:
    """同市场所有股票当日 change_pct 均值，近似大盘（去 β 用）。"""
    key = (market, date_str)
    if key in _market_cache:
        return _market_cache[key]
    with get_conn() as c:
        row = c.execute(
            "SELECT AVG(p.change_pct) m, COUNT(*) n FROM stock_prices p "
            "JOIN stocks s ON s.code=p.code "
            "WHERE s.market=:mkt AND CAST(p.fetched_at AS TEXT) LIKE :d AND p.change_pct IS NOT NULL",
            {"mkt": market, "d": date_str + "%"},
        ).fetchone()
    mean = float(row["m"]) if row and row["m"] is not None and (row["n"] or 0) >= 5 else 0.0
    _market_cache[key] = mean
    return mean


def abnormal_return_z(code: str, date_str: str, market: str = "cn"):
    """
    简化事件研究：AR = 当日 change_pct − 同市场均值(近似大盘)；
    z = AR / 该股近 20 日 change_pct 标准差。返回 (ar, z)。数据不足返回 (None, None)。
    """
    series = _price_series(code)
    idx = _trading_idx(series, date_str)  # 周末新闻映射到下一交易日
    if idx is None or idx < 5:
        return None, None
    own = series[idx][1]
    if own is None:
        return None, None
    hist = [chg for _, chg, _ in series[max(0, idx - 20):idx] if chg is not None]
    if len(hist) < 5:
        return None, None
    mkt = _market_mean_change(market, series[idx][0])
    ar = own - mkt
    mean = sum(hist) / len(hist)
    var = sum((x - mean) ** 2 for x in hist) / len(hist)
    std = math.sqrt(var) or 1.0
    return round(ar, 3), round(ar / std, 2)


def volume_z(code: str, date_str: str):
    """当日成交量对近 20 日均量的 z 分。数据不足返回 None。"""
    series = _price_series(code)
    idx = _trading_idx(series, date_str)
    if idx is None or idx < 5:
        return None
    vol = series[idx][2]
    hist = [v for _, _, v in series[max(0, idx - 20):idx] if v]
    if vol is None or len(hist) < 5:
        return None
    mean = sum(hist) / len(hist)
    var = sum((v - mean) ** 2 for v in hist) / len(hist)
    std = math.sqrt(var) or 1.0
    return round((vol - mean) / std, 2)


# ── 漏斗：相关度 / 新颖度 / 事件量 / 事件类型 ─────────────────────────

def relevance(title: str, name: str, code: str) -> float:
    """新闻是否"关于"该股：标题含名称/代码 → 高相关；否则视为顺带提及。"""
    t = title or ""
    if code and code[:6] in t:
        return 1.0
    if name and (name in t or name[:2] in t):
        return 0.9
    return 0.3


def event_types(title: str):
    """多标签：返回命中的事件类型列表 [(type, weight)]。"""
    t = (title or "").lower()
    hits = []
    for etype, (kws, w) in _EVENT_KEYWORDS.items():
        if any(k.lower() in t for k in kws):
            hits.append((etype, w))
    return hits


def _is_noise(title: str) -> bool:
    t = (title or "").lower()
    return any(k.lower() in t for k in _NOISE_KEYWORDS) and not event_types(title)


def scan_material_news(code: str, name: str = "", market: str = "cn", days: int = 7):
    """
    对该股近 days 天新闻跑漏斗，返回材料度排序的重大事件列表。
    每项：{title, source, date, relevance, novelty(bool), aggregate_volume, event_types, ar, ar_z, vol_z, score, tier}
    """
    cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as c:
        if not name:
            nrow = c.execute("SELECT COALESCE(name_cn, name) nm FROM stocks WHERE code=:c", {"c": code}).fetchone()
            name = (nrow["nm"] if nrow else "") or ""
        rows = c.execute(
            "SELECT title, source, publish_time FROM stock_news "
            "WHERE code=:code AND COALESCE(publish_time, fetched_date) >= :cut "
            "ORDER BY COALESCE(publish_time, fetched_date) ASC",
            {"code": code, "cut": cutoff},
        ).fetchall()

    # 新颖度去重：同一事件(标题 Jaccard≥0.6)只留最早一条，其余源计入 aggregate_volume
    events = []  # 每个 = {title, source, date, sources:set, tokens}
    for r in rows:
        title = r["title"] or ""
        d = str(r["publish_time"] or "")[:10]
        toks = _token_set(title)
        matched = None
        for ev in events:
            if _jaccard(toks, ev["tokens"]) >= 0.6:
                matched = ev
                break
        if matched:
            matched["sources"].add(r["source"] or "")
        else:
            events.append({"title": title, "source": r["source"] or "", "date": d,
                           "sources": {r["source"] or ""}, "tokens": toks})

    results = []
    for ev in events:
        title = ev["title"]
        etypes = event_types(title)
        ew = max([w for _, w in etypes], default=0.3)
        rel = relevance(title, name, code)
        # 已在该股新闻源里=基线相关；纯噪音丢；低相关只在非高危事件时才丢
        if _is_noise(title):
            continue
        if rel < 0.5 and ew < 0.8:
            continue
        agg = len(ev["sources"])

        # ── 重要性 = 新闻本身的分量(前瞻，发布即可算)：事件类型主导 + 多源确认 ──
        # AR 不进分数（那是事后确认），只当"是否已被定价"的背景标签。
        raw = ew * 55 + min(agg - 1, 3) / 3.0 * 20 + 10
        score = round(100 * math.tanh(raw / 55), 1)
        tier = "material" if score >= 70 else ("watch" if score >= 40 else "drop")
        if tier == "drop":
            continue

        # ── AR 当背景标签：市场是否已反应 ──
        ar, ar_z = abnormal_return_z(code, ev["date"], market)
        vz = volume_z(code, ev["date"])
        if ar_z is None:
            market_status = "unknown"
        elif abs(ar_z) >= 1.0:
            market_status = "reacted"      # 已被定价，晚了
        elif abs(ar_z) < 0.5:
            market_status = "not_priced"   # 尚未反应 → 你早
        else:
            market_status = "mild"
        # 早期预警：重要 + 市场还没反应
        is_early = 1 if (tier == "material" and market_status == "not_priced") else 0

        results.append({
            "title": title, "source": ev["source"], "date": ev["date"],
            "relevance": rel, "aggregate_volume": agg,
            "event_types": [t for t, _ in etypes],
            "ar": ar, "ar_z": ar_z, "vol_z": vz,
            "market_status": market_status, "is_early": is_early,
            "score": score, "tier": tier,
        })

    # 排序：早期预警优先，再按重要性
    results.sort(key=lambda x: (x["is_early"], x["score"]), reverse=True)
    return results


if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "002460"
    for item in scan_material_news(code, days=30):
        print(f"[{item['tier']:8} {item['score']:5}] AR_z={item['ar_z']} vol_z={item['vol_z']} "
              f"src={item['aggregate_volume']} {item['event_types']} | {item['title'][:40]}")
