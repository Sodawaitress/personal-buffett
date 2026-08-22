"""行业景气信号（US-158 重写，取代 US-95 的 company_type→板块 映射）。

## 它回答什么问题

「这只股票跌了 15%，是它自己出事了，还是整个行业都这样？」

- 股票跌 15% + 行业也跌 15% → 行业性的，可能是机会
- 股票跌 15% + 行业涨 5%  → **公司自己出事了**，要警惕

这是巴菲特框架「第一层·公司底」的校准项。**它只需要跨过 ±5% 这道门槛**
判顺风/逆风，不需要高精度指数 —— 这一点决定了下面所有取舍。

## 为什么是这个架构（2026-08-16 实测得出，不是拍脑袋）

原设计（US-95）把 `company_type`（商业形态：成熟价值/成长科技/困境反转）
当行业用，映射表只覆盖 3/9 种类型 → 74% 的股票拿不到信号；而且概念本身
就错：茅台和长江电力都是 `mature_value`，映射到同一个板块没有意义。

重写前逐个实测四个数据源（新西兰本地 + GHA 美国 runner 两地对照）：

| 能力 | 东财 | 同花顺 | 新浪 | baostock |
|---|---|---|---|---|
| 板块列表+当日涨跌（1 次调用） | ✅ 100个 | ✅ 90个 | ✅ 49个 | — |
| 成分股 | ✅ **完整（可翻页）** | ❌ 第1页且**会封号** | ✅ 完整 | ✅ 全市场 |
| 历史K线（可回溯自愈） | ❌ 全主机被拒 | ✅ | ❌ | ❌ |
| 分类粒度 | 细(100) | 细(90) | 粗(49) | 粗(84,证监会) |

关键实测结论：

1. **「东财只能从 Fly 悉尼访问」是错的**（这条假设写在 CLAUDE.md 和
   cron.yml 注释里）。GHA 美国 runner 与新西兰本地表现完全一致 ——
   是东财在拒绝这类客户端特征，与地理无关。
2. **能自愈的（同花顺历史）和能建映射的（新浪成分股）不是同一套分类体系**，
   板块名只有 15% 对得上（东财 100 个 vs 同花顺 90 个）。
3. 试过用成分股重合度自动桥接（避免人工维护映射表）：判别力确实有
   （东财半导体 ∩ 同花顺半导体 = 19 只，∩ 同花顺白酒 = 0 只），
   但当时两边取到的都是截断列表且排序不同，大板块出现两个「前 100 名」
   完全不相交。后来发现东财其实可以翻页（同花顺不行），但桥接本身
   已无必要——见下面的「两套体系并行」。
4. **抓 90 个同花顺板块的成分股页会被封号** —— 实测亲历。

所以：**两套体系并行，绝不桥接**（adata 多源模式的正确用法）。

| 源 | 板块数 | 成分股 | 覆盖 | 角色 |
|---|---|---|---|---|
| 东财 push2 | 100 | ✅ 完整（可翻页） | ~全市场 | **主源**，附带主力净流入 |
| 新浪行业 | 49 | ✅ 完整 | A股约 55% | 兜底（东财漏掉的） |

关键：每只股票**只归属一套体系**，动量也从同一套体系的序列算 ——
所以永远不需要在两套分类之间做名称映射，也就没有那 15% 名称重合的问题。

（东财翻页实测：半导体 BK1036 total=185，第1页 100 + 第2页 85 = 完整。
 同花顺翻页返回 401，这是两者的关键差别，此前误以为东财也翻不了页。）

## 动量怎么来：自己累积，因为我们承担不起「永久的洞」

新浪没有历史接口，所以动量由 `industry_daily` 逐日留存后自己算。
代价很实在：**要约 30 个交易日才完全成熟**，期间显式显示「已积累 N 天」，
绝不假装。

防洞设计（这个系统有连续 14 天不跑的前科）：
- 捕获只要 **1 次 HTTP 调用**，因此挂在 5 个每日服务上 = 5 次机会/天
- `(date, sector_label)` 唯一键 → 重复捕获幂等无害
- `find_gaps()` 用数据本身检测缺口，接进 audit-svc 每周告警
- `days_available` 一路透传到前端，不满 30 天就说不满
"""

import json
from datetime import datetime, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8))

# 顺风/逆风门槛。沿用原设计的 ±5% —— 它是这个信号唯一需要的精度。
TAILWIND_PCT = 5.0
HEADWIND_PCT = -5.0

# 动量窗口（交易日）。少于 MIN_DAYS_FOR_SIGNAL 只给「刚开始积累」的结论。
MOMENTUM_DAYS = 30
MIN_DAYS_FOR_SIGNAL = 5


# ── 数据源适配器：两套体系并行，各自独立 ────────────────────

_EM_HEADERS = {"User-Agent": "Mozilla/5.0"}
_EM_BASE = "https://push2.eastmoney.com/api/qt/clist/get"


def _em_get(params: str, tries: int = 3):
    """东财 push2 请求（带退避）。push2his 历史主机是被拒的，push2 可用。"""
    import time

    import requests
    for i in range(tries):
        try:
            r = requests.get(f"{_EM_BASE}?{params}", timeout=25, headers=_EM_HEADERS)
            r.raise_for_status()
            d = r.json()
            diff = (d.get("data") or {}).get("diff")
            items = list(diff.values()) if isinstance(diff, dict) else (diff or [])
            return items, (d.get("data") or {}).get("total")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))
    return [], None


def fetch_spot_em() -> list:
    """东财 100 个行业板块的当日表现。**1 次调用**。f3=涨跌幅(×100)，f62=主力净流入。"""
    try:
        items, _ = _em_get("pn=1&pz=200&fs=m:90+t:2&fields=f12,f14,f3,f62")
    except Exception as e:
        print(f"    ⚠️ 东财行业当日表现失败: {type(e).__name__}: {e}")
        return []
    out = []
    for b in items:
        try:
            out.append({
                "label": f"em:{b['f12']}",
                "name": str(b.get("f14", "")).strip(),
                "change_pct": round(float(b.get("f3", 0)) / 100.0, 4),
                "company_count": None,
                "avg_price": None,
            })
        except (TypeError, ValueError, KeyError):
            continue
    return [x for x in out if x["name"]]


def fetch_constituents_em(label: str) -> list:
    """东财板块成分股。**翻页拿完整列表**（单页上限 100）。"""
    bk = label.split(":", 1)[-1]
    codes, pn = [], 1
    while pn <= 10:                      # 单板块最多 1000 只，足够
        items, total = _em_get(f"pn={pn}&pz=100&fs=b:{bk}&fields=f12")
        codes.extend(str(i["f12"]) for i in items if i.get("f12"))
        if not items or (total and len(codes) >= total):
            break
        pn += 1
    return codes


def fetch_spot_sina() -> list:
    """新浪 49 个行业的当日表现。**1 次调用**。"""
    rows = _fetch_sector_spot_sina_raw()
    return [{**r, "label": f"sina:{r['label']}"} for r in rows]


def fetch_constituents_sina(label: str) -> list:
    import akshare as ak
    det = ak.stock_sector_detail(sector=label.split(":", 1)[-1])
    if det is None or det.empty or "code" not in det.columns:
        return []
    return [str(x) for x in det["code"]]


# 顺序即优先级：东财粒度更细（100 vs 49）且覆盖更全，新浪只补东财漏掉的。
#
# ⚠️ US-161：东财在 **GHA runner 上必然 502**（封数据中心 IP 段），所以在
# GHA 跑的 capture_daily / refresh_stock_industry_map 实际只有新浪会成功 ——
# 这是设计如此，不是 bug（多源降级）。东财那一半改由 Fly 上的 trigger-scan
# 搭车跑（capture_daily_em / refresh_map_em），先例见 insider_moves。
SOURCES = [
    ("em",   fetch_spot_em,   fetch_constituents_em),
    ("sina", fetch_spot_sina, fetch_constituents_sina),
]


# ── 捕获：每日每源 1 次调用 ────────────────────────────────

def _fetch_sector_spot_sina_raw() -> list:
    """拉全部行业当日表现。**一次调用拿全部 49 个行业**。

    返回 [{"label","name","change_pct","company_count","avg_price"}, ...]。
    失败返回 []，绝不抛 —— 调用方是每日 pipeline，不能被它拖垮。
    """
    try:
        import akshare as ak
        df = ak.stock_sector_spot(indicator="新浪行业")
    except Exception as e:
        print(f"    ⚠️ 行业当日表现拉取失败: {type(e).__name__}: {e}")
        return []
    if df is None or df.empty:
        print("    ⚠️ 行业当日表现返回空")
        return []

    out = []
    for _, r in df.iterrows():
        try:
            out.append({
                "label": str(r.get("label", "")).strip(),
                "name": str(r.get("板块", "")).strip(),
                "change_pct": round(float(r.get("涨跌幅")), 4),
                "company_count": int(float(r.get("公司家数") or 0)),
                "avg_price": float(r.get("平均价格") or 0) or None,
            })
        except (TypeError, ValueError):
            continue
    return [x for x in out if x["label"] and x["name"]]


def fetch_sector_spot() -> list:
    """全部数据源的当日表现合并（每源 1 次调用）。"""
    out = []
    for name, spot_fn, _ in SOURCES:
        try:
            rows = spot_fn()
            if rows:
                out.extend(rows)
            else:
                print(f"    ⚠️ 数据源 {name} 无数据（其余源继续）")
        except Exception as e:
            print(f"    ⚠️ 数据源 {name} 异常: {type(e).__name__}: {e}")
    return out


# ── 单源入口：东财只能在 Fly 上跑（US-161）────────────────────

def _capture_one_source(rows, date_str=None, force=False, tag=""):
    """把一个源的当日表现写进 industry_daily。守卫与 capture_daily 相同。"""
    import db

    date_str = date_str or datetime.now(CN_TZ).strftime("%Y-%m-%d")
    if not force:
        try:
            y, m, d = (int(x) for x in date_str.split("-"))
            if datetime(y, m, d).weekday() >= 5:
                return {"date": date_str, "captured": 0, "skipped": True,
                        "reason": "weekend", "source": tag}
        except (ValueError, TypeError):
            pass
    if not rows:
        return {"date": date_str, "captured": 0, "skipped": True,
                "reason": "fetch_failed", "source": tag}

    n = 0
    for r in rows:
        try:
            db.upsert_industry_daily(date_str, r["label"], r["name"],
                                     r["change_pct"], r["company_count"],
                                     r["avg_price"])
            n += 1
        except Exception as e:
            print(f"    ⚠️ 行业 {r['name']} 写入失败: {e}")
    return {"date": date_str, "captured": n, "skipped": False,
            "reason": "", "source": tag}


def capture_daily_em(date_str: str = None, force: bool = False) -> dict:
    """只捕获东财源。**必须在 Fly 上调用** —— 东财封数据中心 IP 段，
    从 GHA runner 打 push2 会 502（2026-08-22 实测：新西兰住宅 IP 五种参数
    组合全部 200，GHA 的 Azure IP 全部 502）。

    不做「重复数据」指纹比对：这里只有东财一个源的 100 个板块，
    与 capture_daily（两源合并 149 个）的指纹口径不同，混在一起比会互相误判。
    非交易日靠周末守卫挡，节假日会多写一天重复数据 —— 那点误差对 ±5% 的
    门槛判断无影响，比漏掉一天轻。
    """
    return _capture_one_source(fetch_spot_em(), date_str, force, tag="em")


def refresh_map_em(sleep_s: float = 0.6) -> dict:
    """只用东财刷映射。**必须在 Fly 上调用**（同上）。

    东财 100 个板块、成分股可翻页拿全，覆盖 A股全市场；新浪只有 49 个粗分类、
    覆盖约 55%（缺科创板/北交所）。所以东财跑成功后，映射会以它为准 ——
    save_stock_industry 是 upsert，同一只股票会被东财的记录覆盖掉新浪的。
    """
    import time

    import db

    boards = fetch_spot_em()
    if not boards:
        return {"source": "em", "boards": 0, "mapped": 0,
                "failed": ["<东财板块列表为空（IP 被封？）>"]}

    mapped, failed = 0, []
    for i, b in enumerate(boards, 1):
        try:
            codes = fetch_constituents_em(b["label"])
        except Exception as e:
            failed.append(f"{b['name']}({type(e).__name__})")
            time.sleep(sleep_s)
            continue
        payload = json.dumps({"label": b["label"], "name": b["name"],
                              "source": "em"}, ensure_ascii=False)
        for raw in codes:
            db.save_stock_industry(str(raw).split(".")[0].zfill(6), payload)
            mapped += 1
        if i % 25 == 0:
            print(f"    [em {i}/{len(boards)}] 累计 {mapped} 只")
        time.sleep(sleep_s)
    return {"source": "em", "boards": len(boards), "mapped": mapped,
            "failed": failed}


def _signature(rows: list) -> str:
    """全部行业涨跌幅的指纹。用来识别「非交易日返回上一交易日数据」。"""
    import hashlib

    payload = json.dumps(sorted((r["label"], r["change_pct"]) for r in rows),
                         ensure_ascii=False)
    return hashlib.md5(payload.encode()).hexdigest()


def capture_daily(date_str: str = None, force: bool = False) -> dict:
    """留存今天的行业表现。幂等——被多个服务重复调用是设计如此，不是浪费。

    **两道非交易日守卫**（缺了任何一道，动量都会被重复计数污染）：

    ① 周末直接跳过。
    ② 指纹比对：新浪在节假日返回的是**上一个交易日**的数据，日期上看不出来。
       若全部 49 个行业的涨跌幅与最近一次捕获完全相同，判定为同一交易日的
       重复数据，跳过。这是本仓已有的模式（CLAUDE_ROUTINE 的 Gate ②
       price_signature 就是这么识别「服务器空跑」的）。

    返回 {"date","captured","skipped","reason"}。
    """
    import db

    now = datetime.now(CN_TZ)
    date_str = date_str or now.strftime("%Y-%m-%d")

    if not force:
        try:
            y, m, d = (int(x) for x in date_str.split("-"))
            if datetime(y, m, d).weekday() >= 5:
                return {"date": date_str, "captured": 0, "skipped": True,
                        "reason": "weekend"}
        except (ValueError, TypeError):
            pass

    rows = fetch_sector_spot()
    if not rows:
        return {"date": date_str, "captured": 0, "skipped": True,
                "reason": "fetch_failed"}

    sig = _signature(rows)
    if not force:
        try:
            prev = db.get_latest_industry_signature(exclude_date=date_str)
            if prev and prev == sig:
                return {"date": date_str, "captured": 0, "skipped": True,
                        "reason": "duplicate_of_previous_trading_day"}
        except Exception:
            pass   # 签名比对失败不该挡住捕获——漏一天比多一天贵

    n = 0
    for r in rows:
        try:
            db.upsert_industry_daily(date_str, r["label"], r["name"],
                                     r["change_pct"], r["company_count"],
                                     r["avg_price"])
            n += 1
        except Exception as e:
            print(f"    ⚠️ 行业 {r['name']} 写入失败: {e}")
    return {"date": date_str, "captured": n, "skipped": False, "reason": ""}


# ── 动量：从我们自己的序列算 ────────────────────────────────

def compute_momentum(sector_label: str, days: int = MOMENTUM_DAYS) -> dict:
    """日收益连乘出区间涨跌。

    返回 {"change_pct","days_available","mature"}；无数据返回 {}。
    `days_available` 必须一路透传到前端——不满 30 天就说不满，
    这是整个设计里由代码保证「诚实」的地方。
    """
    import db

    series = db.get_industry_series(sector_label, limit=days)
    if not series:
        return {}

    cum, used = 1.0, 0
    for row in series:
        pct = row.get("change_pct")
        if pct is None:
            continue
        cum *= (1.0 + float(pct) / 100.0)
        used += 1
    if used == 0:
        return {}

    return {
        "change_pct": round((cum - 1.0) * 100.0, 2),
        "days_available": used,
        "mature": used >= days,
    }


def build_signal(sector_label: str, sector_name: str,
                 days: int = MOMENTUM_DAYS) -> dict:
    """给一个行业出信号卡片。数据不足时**降级但不沉默**。"""
    mom = compute_momentum(sector_label, days)
    if not mom:
        return {}

    change, avail = mom["change_pct"], mom["days_available"]

    if avail < MIN_DAYS_FOR_SIGNAL:
        return {
            "industry_key": sector_label,
            "label": sector_name,
            "signal": "中性",
            "change_30d": change,
            "days_available": avail,
            "mature": False,
            "description": f"{sector_name}数据刚开始积累（已{avail}个交易日），"
                           f"暂不足以判断趋势",
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }

    if change >= TAILWIND_PCT:
        signal = "顺风"
        desc = f"{sector_name}近{avail}个交易日上涨 {change:+.1f}%，板块处于上行态势"
    elif change <= HEADWIND_PCT:
        signal = "逆风"
        desc = f"{sector_name}近{avail}个交易日下跌 {change:+.1f}%，行业面临调整压力"
    else:
        signal = "中性"
        desc = f"{sector_name}近{avail}个交易日涨跌 {change:+.1f}%，板块震荡整理"

    if not mom["mature"]:
        desc += f"（数据积累中，目标{days}个交易日）"

    return {
        "industry_key": sector_label,
        "label": sector_name,
        "signal": signal,
        "change_30d": change,
        "days_available": avail,
        "mature": mom["mature"],
        "description": desc,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_signal_for_stock(code: str) -> dict:
    """个股 → 所属行业 → 信号卡片。查不到行业返回 {}。"""
    import db

    industry = db.get_stock_industry(code)
    if not industry:
        return {}

    label, name = "", ""
    if isinstance(industry, str) and industry.startswith("{"):
        try:
            payload = json.loads(industry)
            label, name = payload.get("label", ""), payload.get("name", "")
        except ValueError:
            pass

    # 兼容 label 加源前缀之前写入的记录（US-158 首版是裸 label，
    # 加东财源后统一成 "sina:xxx" / "em:BKxxxx"）。没前缀的一律当新浪。
    if label and ":" not in label:
        label = f"sina:{label}"
    if not label:
        # 旧格式：只存了行业名（东财口径）。用名字反查 label，查不到就放弃。
        name = industry
        label = _label_for_name(industry)
    if not label:
        return {}
    return build_signal(label, name)


def _label_for_name(name: str) -> str:
    """行业名 → 新浪 label。从已留存的数据里反查，不发请求。"""
    import db

    try:
        with db.get_conn() as c:
            row = c.execute(
                "SELECT sector_label FROM industry_daily WHERE sector_name=:n "
                "ORDER BY date DESC LIMIT 1", {"n": name},
            ).fetchone()
            return row["sector_label"] if row else ""
    except Exception:
        return ""


# ── 映射刷新：每周一次，49 次调用 ──────────────────────────

def refresh_stock_industry_map(sleep_s: float = 1.0) -> dict:
    """重建 个股→行业 映射。按 SOURCES 的优先级，先到先得。

    东财优先（100 个板块，粒度比新浪细一倍，且成分股可翻页拿全）；
    新浪只补东财漏掉的股票。**一只股票只归属一套体系**——动量也从同一套
    体系的序列算，所以永远不需要在两套分类之间做名称映射。

    断点续跑：今天已刷过的板块跳过。GHA 上单次 workflow 时限跑不完全部，
    与其无限加超时，不如让它分几次跑完（与 US-158 其余部分同一原则）。
    单个板块失败不影响其余——部分刷新好过完全不刷新。
    """
    import time

    import db

    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    seen: set = set()          # 已被更高优先级的源认领的股票
    stats = {"by_source": {}, "mapped": 0, "skipped": 0, "failed": []}

    for src_name, spot_fn, cons_fn in SOURCES:
        try:
            boards = spot_fn()
        except Exception as e:
            stats["failed"].append(f"<{src_name} 板块列表>({type(e).__name__})")
            continue
        if not boards:
            stats["failed"].append(f"<{src_name} 板块列表为空>")
            continue

        n_src = 0
        for i, b in enumerate(boards, 1):
            try:
                if db.sector_mapped_on(b["label"], today):
                    stats["skipped"] += 1
                    continue
            except Exception:
                pass

            try:
                codes = cons_fn(b["label"])
            except Exception as e:
                stats["failed"].append(f"{b['name']}({type(e).__name__})")
                time.sleep(sleep_s)
                continue

            payload = json.dumps({"label": b["label"], "name": b["name"],
                                  "source": src_name}, ensure_ascii=False)
            for raw in codes:
                pure = str(raw).split(".")[0].zfill(6)
                if pure in seen:
                    continue          # 更高优先级的源已经认领
                db.save_stock_industry(pure, payload)
                seen.add(pure)
                n_src += 1
                stats["mapped"] += 1

            if i % 20 == 0:
                print(f"    [{src_name} {i}/{len(boards)}] 累计 {stats['mapped']} 只")
            time.sleep(sleep_s)

        stats["by_source"][src_name] = n_src
        print(f"  ✔ {src_name}: 认领 {n_src} 只")

    return stats


# ── 缺口检测：让数据自己说话 ────────────────────────────────

def find_gaps(lookback_days: int = 30) -> dict:
    """最近 N 个自然日里，哪些工作日没有捕获到行业数据。

    不看「任务跑没跑」，看「该有的数据在不在」——这个系统所有的沉默失败
    （快照冻结 14 天、backfill 从没成功过、北向变 0 值 5 周、行业信号
    26 天没更新）都是「跑了、返回了、没报错、但没产出」。只有查数据才能发现。

    注：只按周末过滤，法定节假日会产生误报。宁可误报也不漏报——
    误报看一眼就知道，漏报会像前面那些一样沉默几个月。
    """
    import db

    today = datetime.now(CN_TZ).date()
    have = set(db.get_industry_capture_dates(limit=lookback_days * 2))

    expected, missing = [], []
    for i in range(lookback_days):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        s = d.strftime("%Y-%m-%d")
        expected.append(s)
        if s not in have:
            missing.append(s)

    # 今天可能还没到捕获时间，不算缺口
    today_s = today.strftime("%Y-%m-%d")
    missing = [m for m in missing if m != today_s]
    expected = [e for e in expected if e != today_s]

    return {
        "expected": len(expected),
        "captured": len(expected) - len(missing),
        "missing": sorted(missing, reverse=True),
        "coverage_pct": (round((len(expected) - len(missing)) * 100.0 / len(expected), 1)
                         if expected else 0.0),
    }
