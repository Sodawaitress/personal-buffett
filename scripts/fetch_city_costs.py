"""
城市生活成本数据抓取 / 维护脚本 (US-105)

数据策略：
  major 城市  — Numbeo 实时抓取，每年 6 月跑一次（NBS 2025 年报 5 月发布后 Numbeo 会更新）
  lifestyle 城市 — 手动维护参考值（云南统计公报 2025 + 用户调研），每年人工校核一次

更新方法：
  python3 scripts/fetch_city_costs.py            # 只刷新 30 天以上的城市
  python3 scripts/fetch_city_costs.py --force    # 全部重新抓取

Numbeo 解析说明（2026-06-07 验证）：
  薪资  → <span class="first_currency"> in "Average Monthly Net Salary" row
  房租  → <span class="first_currency"> in "1 Bedroom Apartment Outside of City Centre" row
  单人消费（不含租） → summary list 第二条 <span class="in_other_currency">
  月总成本 = 单人消费 + 市郊1居室房租
"""

import re
import time
import logging
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# ── Major cities（打工城市，Numbeo 抓取）────────────────────────────────────────
MAJOR_CITIES = [
    {"name": "上海",  "tier": "一线",   "slug": "Shanghai"},
    {"name": "北京",  "tier": "一线",   "slug": "Beijing"},
    {"name": "深圳",  "tier": "一线",   "slug": "Shenzhen"},
    {"name": "广州",  "tier": "一线",   "slug": "Guangzhou"},
    {"name": "杭州",  "tier": "新一线", "slug": "Hangzhou"},
    {"name": "南京",  "tier": "新一线", "slug": "Nanjing"},
    {"name": "苏州",  "tier": "新一线", "slug": "Suzhou"},
    {"name": "成都",  "tier": "新一线", "slug": "Chengdu"},
    {"name": "武汉",  "tier": "新一线", "slug": "Wuhan"},
    {"name": "重庆",  "tier": "新一线", "slug": "Chongqing"},
    {"name": "西安",  "tier": "二线",   "slug": "Xian"},
    {"name": "青岛",  "tier": "二线",   "slug": "Qingdao"},
    {"name": "长沙",  "tier": "二线",   "slug": "Changsha"},
    {"name": "昆明",  "tier": "二线",   "slug": "Kunming"},
    {"name": "厦门",  "tier": "二线",   "slug": "Xiamen"},
]

# ── Lifestyle cities（退休/躺平首选，手动维护）────────────────────────────────
# 数据来源：云南统计公报 2025 + 海南统计年鉴 2025 + 用户调研
# 每年 6 月人工核对一次，修改此处后重跑 --force
LIFESTYLE_CITIES = [
    {
        "name": "大理",    "tier": "躺平首选", "slug": "Dali-CN",
        "salary": 4000,   "cost": 3000,
        "source": "云南统计公报 2025 / 用户调研",
        # 薪资区间 ¥3,000-6,000；¥4,000 为中位数（本地就业）
        # 生活成本：市郊1居室 ¥1,200 + 单人餐饮交通 ¥1,800 = ¥3,000
    },
    {
        "name": "丽江",    "tier": "躺平首选", "slug": "Lijiang-CN",
        "salary": 3500,   "cost": 2800,
        "source": "云南统计公报 2025",
        # 旅游淡季消费低；¥2,800 为保守估计
    },
    {
        "name": "西双版纳", "tier": "躺平首选", "slug": "Xishuangbanna-CN",
        "salary": 3500,   "cost": 2500,
        "source": "云南统计公报 2025",
        # 热带气候，生活成本全国最低梯队之一
    },
    {
        "name": "三亚",    "tier": "躺平首选", "slug": "Sanya-CN",
        "salary": 5500,   "cost": 5500,
        "source": "海南统计年鉴 2025",
        # 旅游城市，消费偏高；退休选三亚的人通常有一定资产
    },
]

REPORT_YEAR = 2025  # 当前数据年份（NBS 2025 年报于 2026 年 5-6 月发布）

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


# ── Numbeo 解析 ────────────────────────────────────────────────────────────────

def _parse_cny(text: str) -> float | None:
    m = re.search(r"[\d,]+(?:\.\d+)?", text.replace(",", ""))
    try:
        return float(m.group().replace(",", "")) if m else None
    except ValueError:
        return None


def scrape_city(slug: str) -> dict | None:
    url = f"https://www.numbeo.com/cost-of-living/in/{slug}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        log.warning("Numbeo 抓取失败 %s: %s", slug, e)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    avg_salary       = None
    rent_outside     = None
    single_excl_rent = None

    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        label    = cells[0].get_text(strip=True)
        val_span = cells[1].find("span", class_="first_currency")
        if not val_span:
            continue
        raw = val_span.get_text(strip=True)
        if "Average Monthly Net Salary" in label:
            avg_salary = _parse_cny(raw)
        elif "1 Bedroom Apartment Outside of City Centre" in label:
            rent_outside = _parse_cny(raw)

    for li in soup.select("div.inside_box_summary_content li"):
        if "single person" in li.get_text(" ", strip=True).lower():
            cny_span = li.find("span", class_="in_other_currency")
            if cny_span:
                single_excl_rent = _parse_cny(cny_span.get_text(strip=True))
            break

    if avg_salary is None and rent_outside is None:
        log.warning("无法解析数据：%s", slug)
        return None

    avg_monthly_cost = None
    if single_excl_rent is not None and rent_outside is not None:
        avg_monthly_cost = round(single_excl_rent + rent_outside)
    elif rent_outside is not None:
        avg_monthly_cost = rent_outside

    return {"avg_monthly_salary": avg_salary, "avg_monthly_cost": avg_monthly_cost}


# ── DB 操作 ────────────────────────────────────────────────────────────────────

def _ensure_table():
    from radar_app.data.core import get_conn
    with get_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS city_living_data (
                city_slug          TEXT PRIMARY KEY,
                city_name          TEXT NOT NULL,
                tier               TEXT NOT NULL,
                city_category      TEXT DEFAULT 'major',
                avg_monthly_salary REAL,
                avg_monthly_cost   REAL,
                source             TEXT DEFAULT 'numbeo',
                report_year        INTEGER,
                fetched_at         TEXT NOT NULL
            )
        """)


def _save(slug: str, name: str, tier: str, category: str,
          salary: float | None, cost: float | None,
          source: str, year: int):
    from radar_app.data.core import get_conn
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as c:
        c.execute("""
            INSERT INTO city_living_data
                (city_slug, city_name, tier, city_category,
                 avg_monthly_salary, avg_monthly_cost, source, report_year, fetched_at)
            VALUES (:slug, :name, :tier, :cat, :salary, :cost, :src, :yr, :ts)
            ON CONFLICT(city_slug) DO UPDATE SET
                city_name=excluded.city_name, tier=excluded.tier,
                city_category=excluded.city_category,
                avg_monthly_salary=excluded.avg_monthly_salary,
                avg_monthly_cost=excluded.avg_monthly_cost,
                source=excluded.source, report_year=excluded.report_year,
                fetched_at=excluded.fetched_at
        """, {"slug": slug, "name": name, "tier": tier, "cat": category,
              "salary": salary, "cost": cost, "src": source, "yr": year, "ts": now})


def get_all_cities() -> list[dict]:
    from radar_app.data.core import get_conn
    with get_conn() as c:
        # _ConnWrapper.execute() already returns MappingResult, so .all() directly
        rows = c.execute(
            "SELECT * FROM city_living_data ORDER BY city_category, tier, city_name"
        ).all()
    return [dict(r) for r in rows]


def is_stale(fetched_at_iso: str, days: int = 30) -> bool:
    try:
        ts = datetime.fromisoformat(fetched_at_iso.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - ts > timedelta(days=days)
    except Exception:
        return True


# ── 主刷新逻辑 ─────────────────────────────────────────────────────────────────

def _seed_lifestyle_cities():
    """把手动维护的生活城市写入 DB（每次都覆盖，因为 report_year 可能更新）。"""
    for c in LIFESTYLE_CITIES:
        _save(
            slug=c["slug"], name=c["name"], tier=c["tier"], category="lifestyle",
            salary=c["salary"], cost=c["cost"], source=c["source"], year=REPORT_YEAR,
        )
        log.info("  ✅ %s (手动维护): 月薪=¥%s 生活成本=¥%s", c["name"], c["salary"], c["cost"])


def refresh_all(force: bool = False) -> list[dict]:
    """
    刷新所有城市数据：
      - major 城市：Numbeo 抓取（30 天 TTL）
      - lifestyle 城市：每次都用 LIFESTYLE_CITIES 里的最新手动值覆盖
    """
    _ensure_table()
    existing = {r["city_slug"]: r for r in get_all_cities()}
    results  = []

    # 1. Lifestyle 城市（手动值，直接写入）
    log.info("── 写入生活城市手动数据 ──")
    _seed_lifestyle_cities()

    # 2. Major 城市（Numbeo 抓取）
    log.info("── 抓取大城市 Numbeo 数据 ──")
    for city in MAJOR_CITIES:
        slug   = city["slug"]
        cached = existing.get(slug)

        if cached and not force and not is_stale(cached.get("fetched_at", ""), days=30):
            log.info("  跳过 %s（数据新鲜）", city["name"])
            results.append(dict(cached))
            continue

        log.info("  抓取 %s …", city["name"])
        data = scrape_city(slug)
        if data:
            _save(
                slug=slug, name=city["name"], tier=city["tier"], category="major",
                salary=data["avg_monthly_salary"], cost=data["avg_monthly_cost"],
                source="Numbeo 2025", year=REPORT_YEAR,
            )
            results.append({
                "city_slug": slug, "city_name": city["name"],
                "tier": city["tier"], "city_category": "major",
                **data, "fetched_at": datetime.now(timezone.utc).isoformat(),
            })
            log.info("    月薪=¥%.0f 生活成本=¥%.0f",
                     data["avg_monthly_salary"] or 0, data["avg_monthly_cost"] or 0)
        else:
            if cached:
                results.append(dict(cached))
            log.warning("    ❌ 抓取失败，保留旧数据")

        time.sleep(1.5)

    return get_all_cities()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    force = "--force" in sys.argv
    data = refresh_all(force=force)
    print(f"\n共 {len(data)} 个城市")
    for d in data:
        sal  = f"¥{d['avg_monthly_salary']:,.0f}" if d.get('avg_monthly_salary') else "—"
        cost = f"¥{d['avg_monthly_cost']:,.0f}"   if d.get('avg_monthly_cost')   else "—"
        print(f"  [{d.get('city_category','?'):9s}] {d['city_name']:6s} ({d['tier']:5s})  "
              f"月薪={sal:>12}  生活={cost:>12}  来源={d.get('source','?')}")
