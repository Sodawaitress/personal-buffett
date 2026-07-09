"use client";

import { useState, useMemo, useEffect, useRef } from "react";
import Link from "next/link";
import { useCityData, findCity, snapToStep } from "@/hooks/useCityData";

// ── data ──────────────────────────────────────────────────────────────────────
const PRESETS = [
  { label: "活期存款", sub: "0.35%",   rate: 0.35, bg: "#e7e5e4", fg: "#1c1917",
    src: "中国主要银行2025年挂牌利率" },
  { label: "A股指数",   sub: "~7.5%",   rate: 7.5,  bg: "#bfdbfe", fg: "#1e3a5f",
    src: "沪深300指数，2004年基点1000→2026年约4800，年化约7.5%（价格收益）" },
  { label: "标普500",  sub: "10.4% ★", rate: 10.4, bg: "#fde68a", fg: "#92400e",
    src: "标普500含股息再投资100年年化（Of Dollars & Data）" },
  { label: "纳指100",  sub: "~14%",    rate: 14,   bg: "#bbf7d0", fg: "#052e16",
    src: "纳斯达克100自1985年以来含分红年化约14%（Slickcharts / FRED）" },
  { label: "巴菲特",   sub: "19.7%",   rate: 19.7, bg: "#1c1917", fg: "#fbbf24",
    src: "伯克希尔哈撒韦1965-2025股价年化（2025年报）" },
];


const FREQ_OPTIONS = [
  { key: "monthly",  label: "月薪",   mult: 1 },
  { key: "biweekly", label: "双周薪", mult: 26 / 12 },
  { key: "weekly",   label: "周薪",   mult: 52 / 12 },
];

// FIRE years → milestone badge
const FIRE_MILESTONES = [
  { max: 0,  icon: "🎉", label: (_w: string, _r: string) => "财务独立！",                        color: "#15803d" },
  { max: 5,  icon: "🔥", label: (_w: string, _r: string) => "5年计划",                          color: "#b45309" },
  { max: 10, icon: "💎", label: (_w: string, _r: string) => "十年计划",                         color: "#4f46e5" },
  { max: 15, icon: "🚀", label: (_w: string, _r: string) => "快了！",                           color: "#0369a1" },
  { max: 20, icon: "✌️",  label: (_w: string, _r: string) => "进步中",                          color: "#374151" },
  { max: 30, icon: "🌱", label: (w: string,  _r: string) => `在${w}工作，学会复利`,              color: "#374151" },
  { max: 50, icon: "💡", label: (w: string,   r: string) => `在${w}赚，去${r}退`,               color: "#374151" },
];

// ── utils ─────────────────────────────────────────────────────────────────────

function calcFV(p: number, m: number, r: number, y: number) {
  const rm = r / 100 / 12, n = y * 12;
  if (rm === 0) return p + m * n;
  return p * (1 + rm) ** n + m * ((1 + rm) ** n - 1) / rm;
}

function fmtShort(n: number) {
  if (n >= 1e8) return `${(n / 1e8).toFixed(1)}亿`;
  if (n >= 1e4) return `${(n / 1e4).toFixed(1)}万`;
  return `¥${Math.round(n).toLocaleString()}`;
}

function useSpring(target: number, k = 600) {
  const [val, setVal] = useState(target);
  const r = useRef({ from: target, t0: 0, raf: 0 });
  useEffect(() => {
    r.current.from = val;
    r.current.t0   = performance.now();
    cancelAnimationFrame(r.current.raf);
    const tick = (now: number) => {
      const t = Math.min(1, (now - r.current.t0) / k);
      setVal(r.current.from + (target - r.current.from) * (1 - (1 - t) ** 3));
      if (t < 1) r.current.raf = requestAnimationFrame(tick);
    };
    r.current.raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(r.current.raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);
  return val;
}

function Track({ value, min, max, step, onChange, accent = "#1c1917" }: {
  value: number; min: number; max: number; step: number;
  onChange: (v: number) => void; accent?: string;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="relative h-2 rounded-full bg-stone-100">
      <div className="absolute left-0 top-0 h-full rounded-full pointer-events-none"
        style={{ width: `${pct}%`, background: accent }} />
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
    </div>
  );
}

function GrowthChart({ p, m, r, y }: { p: number; m: number; r: number; y: number }) {
  const pts = useMemo(() =>
    Array.from({ length: y + 1 }, (_, i) => ({
      y: i, fv: calcFV(p, m, r, i), inv: p + m * 12 * i,
    })), [p, m, r, y]);
  const maxV = pts[pts.length - 1].fv;
  const W = 520, H = 110, PX = 2, PY = 6;
  const toX = (yr: number) => PX + (yr / y) * (W - PX * 2);
  const toY = (v: number)  => H - PY - (v / maxV) * (H - PY * 2 - 4);
  const fvD  = pts.map((d, i) => `${i ? "L" : "M"}${toX(d.y).toFixed(1)},${toY(d.fv).toFixed(1)}`).join("");
  const invD = pts.map((d, i) => `${i ? "L" : "M"}${toX(d.y).toFixed(1)},${toY(d.inv).toFixed(1)}`).join("");
  const aFV  = `${fvD}L${toX(y)},${H}L${toX(0)},${H}Z`;
  const aInv = `${invD}L${toX(y)},${toY(pts[pts.length - 1].inv).toFixed(1)}L${toX(0)},${toY(p).toFixed(1)}Z`;
  const step = y <= 10 ? 2 : y <= 20 ? 5 : 10;
  const ticks: number[] = [];
  for (let i = 0; i <= y; i += step) ticks.push(i);
  if (ticks[ticks.length - 1] !== y) ticks.push(y);
  return (
    <svg viewBox={`0 0 ${W} ${H + 16}`} className="w-full" style={{ height: 130 }} preserveAspectRatio="none">
      <defs>
        <linearGradient id="ccGrad2" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#15803d" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#15803d" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {[0.33, 0.66].map(f => (
        <line key={f} x1={PX} y1={toY(maxV * f)} x2={W - PX} y2={toY(maxV * f)} stroke="#f5f5f4" strokeWidth="1" />
      ))}
      <path d={aFV}  fill="url(#ccGrad2)" />
      <path d={aInv} fill="#fafaf9" />
      <path d={invD} fill="none" stroke="#d6d3d1" strokeWidth="1.5" strokeDasharray="4 3" />
      <path d={fvD}  fill="none" stroke="#15803d" strokeWidth="2" />
      <circle cx={toX(y)} cy={toY(pts[y].fv)} r="4" fill="#15803d" />
      {ticks.map(t => (
        <text key={t} x={toX(t)} y={H + 13} textAnchor="middle" fontSize="9" fill="#a8a29e">{t}年</text>
      ))}
    </svg>
  );
}

// ── Inline city grid (used inside the picker panel) ───────────────────────────
const TIER_ORDER = ["一线", "新一线", "二线", "躺平首选"];

function CityGrid({ cities, value, onChange }: {
  cities: { city_slug: string; city_name: string; tier: string; city_category: string }[];
  value: string | null;
  onChange: (slug: string | null) => void;
}) {
  const grouped = cities.reduce((acc, c) => {
    (acc[c.tier] ??= []).push(c);
    return acc;
  }, {} as Record<string, typeof cities>);

  const tiers = TIER_ORDER.filter(t => grouped[t]?.length);

  return (
    <div className="space-y-3">
      {tiers.map(tier => (
        <div key={tier}>
          <div className="text-xs text-stone-400 mb-1.5">{tier}</div>
          <div className="flex flex-wrap gap-1.5">
            {grouped[tier].map(c => {
              const active = c.city_slug === value;
              const isLifestyle = c.city_category === "lifestyle";
              return (
                <button key={c.city_slug}
                  onClick={() => onChange(active ? null : c.city_slug)}
                  className={`text-xs px-3 py-1.5 rounded-full border transition-all font-medium ${
                    active
                      ? isLifestyle
                        ? "bg-emerald-700 text-white border-emerald-700"
                        : "bg-stone-900 text-white border-stone-900"
                      : "bg-white text-stone-600 border-stone-200 hover:border-stone-400"
                  }`}>
                  {c.city_name}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── main ──────────────────────────────────────────────────────────────────────
export function CompoundCalculator() {

  // ── income & budget ──────────────────────────────────────────────────────────
  const [freq,      setFreq]      = useState("monthly");
  const [income,    setIncome]    = useState(5000);
  const [investPct, setInvestPct] = useState(20);

  // ── investment params ────────────────────────────────────────────────────────
  const [rate,       setRate]       = useState(0.35);
  const [years,      setYears]      = useState(20);
  const [lump,       setLump]       = useState(0);
  const [livingCost, setLivingCost] = useState(6000);

  // ── UI state ─────────────────────────────────────────────────────────────────
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [openPicker,   setOpenPicker]   = useState<"work" | "retire" | null>(null);

  // ── cities (US-105) ──────────────────────────────────────────────────────────
  const { major, lifestyle, all: allCities, reportYear } = useCityData();
  const [workCitySlug,   setWorkCitySlug]   = useState<string | null>(null);
  const [retireCitySlug, setRetireCitySlug] = useState<string | null>(null);

  const workCity   = findCity(allCities, workCitySlug);
  const retireCity = findCity(allCities, retireCitySlug);

  function handleWorkCity(slug: string | null) {
    setWorkCitySlug(slug);
    if (!slug) return;
    const c = findCity(allCities, slug);
    const sal = snapToStep(c?.avg_monthly_salary ?? null);
    if (sal) setIncome(sal);
    // close picker after selection
    setOpenPicker(null);
  }

  function handleRetireCity(slug: string | null) {
    setRetireCitySlug(slug);
    if (!slug) return;
    const c = findCity(allCities, slug);
    const cost = snapToStep(c?.avg_monthly_cost ?? null);
    if (cost) setLivingCost(cost);
    setOpenPicker(null);
  }

  function togglePicker(side: "work" | "retire") {
    setOpenPicker(v => v === side ? null : side);
  }

  // ── calculations ─────────────────────────────────────────────────────────────
  const freqMult      = FREQ_OPTIONS.find(f => f.key === freq)?.mult ?? 1;
  const monthlyIncome = income * freqMult;
  const monthlyInvest = monthlyIncome * investPct / 100;

  const doubleYrs     = rate > 0 ? (72 / rate).toFixed(1) : null;

  const fireNumber     = livingCost * 300;

  const yearsToFIRE = useMemo(() => {
    if (monthlyInvest <= 0 || livingCost <= 0) return Infinity;
    const rm = rate / 100 / 12;
    if (rm <= 0) return Math.max(0, (fireNumber - lump) / monthlyInvest / 12);
    const mratio = monthlyInvest / rm;
    const base   = lump + mratio;
    if (base <= 0) return Infinity;
    const n = Math.log((fireNumber + mratio) / base) / Math.log(1 + rm) / 12;
    return n <= 0 ? 0 : n;
  }, [monthlyInvest, rate, fireNumber, lump, livingCost]);

  // 不投资只存钱，线性累积到 FIRE 目标需要多少年
  const yearsLinear = useMemo(() => {
    if (monthlyInvest <= 0) return Infinity;
    return (fireNumber - lump) / (monthlyInvest * 12);
  }, [monthlyInvest, fireNumber, lump]);

  // 图表年限：FIRE年数 > 用户设定年限时自动延伸，最多40年
  const chartYears    = yearsToFIRE < 50 && yearsToFIRE > years
    ? Math.min(Math.ceil(yearsToFIRE) + 2, 40)
    : years;
  // 所有统计数字都以 chartYears 为准，和图表保持一致
  const displayFV      = useMemo(() => calcFV(lump, monthlyInvest, rate, chartYears), [lump, monthlyInvest, rate, chartYears]);
  const totalInvested  = lump + monthlyInvest * 12 * chartYears;
  const interest       = displayFV - totalInvested;
  const mult           = totalInvested > 0 ? displayFV / totalInvested : 1;
  const interestPct    = displayFV > 0 ? (interest / displayFV) * 100 : 0;
  const passiveMonthly = displayFV * 0.04 / 12;

  // cap at 50 for animation; show "50+" text
  const ytfCapped  = yearsToFIRE === Infinity ? 50 : Math.min(yearsToFIRE, 50);
  const animYTF       = useSpring(ytfCapped);
  const animDisplayFV = useSpring(displayFV);


  const milestone = FIRE_MILESTONES.find(m => yearsToFIRE <= m.max) ?? null;

  // ── income slider params ──────────────────────────────────────────────────────
  const maxIncome  = freq === "weekly" ? 20000 : freq === "biweekly" ? 40000 : 80000;
  const stepIncome = freq === "weekly" ? 200   : 500;

  // ── city list for each picker ─────────────────────────────────────────────────
  const workCities   = major;
  const retireCities = [...major, ...lifestyle];

  // ── render ────────────────────────────────────────────────────────────────────
  return (
    <div className="border-2 border-stone-900 bg-white overflow-hidden font-sans">

      {/* ── 1. City Journey Bar ── */}
      <div className="bg-stone-900 px-5 py-3">
        <div className="flex items-stretch justify-center gap-3">

          {/* Work city button */}
          <button
            onClick={() => togglePicker("work")}
            className={`flex flex-col items-center px-4 py-2 rounded-lg border transition-all ${
              openPicker === "work"
                ? "bg-white border-white"
                : workCity
                  ? "bg-stone-800 border-stone-700 hover:border-stone-500"
                  : "bg-stone-800 border-dashed border-stone-600 hover:border-stone-400"
            }`}>
            <span className={`text-xs font-medium ${openPicker === "work" ? "text-stone-400" : "text-stone-400"}`}>
              打工城市
            </span>
            <span className={`text-sm font-semibold mt-0.5 ${
              openPicker === "work" ? "text-stone-900" : workCity ? "text-white" : "text-stone-500"
            }`}>
              {workCity ? workCity.city_name : "选城市 +"}
            </span>
          </button>

          {/* Arrow */}
          <div className="flex items-center text-stone-600 text-xs font-mono select-none px-1">
            投资 →
          </div>

          {/* Retire city button */}
          <button
            onClick={() => togglePicker("retire")}
            className={`flex flex-col items-center px-4 py-2 rounded-lg border transition-all ${
              openPicker === "retire"
                ? "bg-white border-white"
                : retireCity
                  ? "bg-emerald-900 border-emerald-700 hover:border-emerald-500"
                  : "bg-stone-800 border-dashed border-stone-600 hover:border-stone-400"
            }`}>
            <span className="text-xs font-medium text-stone-400">退休城市</span>
            <span className={`text-sm font-semibold mt-0.5 ${
              openPicker === "retire"
                ? "text-stone-900"
                : retireCity ? "text-emerald-300" : "text-stone-500"
            }`}>
              {retireCity ? retireCity.city_name : "选退休地 +"}
            </span>
          </button>

        </div>
      </div>

      {/* ── 2. City Picker Panel (conditionally shown) ── */}
      {openPicker && (
        <div className="border-b border-stone-200 bg-stone-50 px-5 py-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-stone-700">
              {openPicker === "work" ? "选打工城市（填入收入参考）" : "选退休城市（填入生活成本目标）"}
            </span>
            <span className="text-xs text-stone-400">
              国家统计局 · Numbeo · {reportYear} 年
            </span>
          </div>
          <CityGrid
            cities={openPicker === "work" ? workCities : retireCities}
            value={openPicker === "work" ? workCitySlug : retireCitySlug}
            onChange={openPicker === "work" ? handleWorkCity : handleRetireCity}
          />
          {/* city info after selection */}
          {(() => {
            const slug = openPicker === "work" ? workCitySlug : retireCitySlug;
            const c = findCity(allCities, slug);
            if (!c) return null;
            return (
              <p className="text-xs text-stone-500 mt-3 pt-3 border-t border-stone-200">
                {c.city_name}
                {c.avg_monthly_salary ? ` · 参考月薪 ¥${Math.round(c.avg_monthly_salary).toLocaleString()}` : ""}
                {c.avg_monthly_cost   ? ` · 生活成本约 ¥${Math.round(c.avg_monthly_cost).toLocaleString()}/月` : ""}
                <span className="text-stone-300 ml-1">（{c.source}）</span>
              </p>
            );
          })()}
        </div>
      )}

      {/* ── 3. Hero — FIRE Score ── */}
      <div className="px-5 pt-8 pb-6 text-center border-b border-stone-100">

        {yearsToFIRE <= 0 ? (
          /* 已达成财务独立 */
          <div>
            <div className="text-5xl mb-2">🎉</div>
            <div className="font-serif font-black text-green-700 text-3xl">财务独立达成！</div>
            <p className="text-stone-400 text-sm mt-2">被动收入已覆盖生活成本</p>
          </div>
        ) : (
          /* 主分支：显示还需多少年 */
          <div>
            <div className="text-xs text-stone-400 tracking-widest uppercase mb-1">坚持投资</div>

            <div className="flex items-end justify-center gap-1 leading-none">
              <span className="font-serif font-black text-stone-900 tabular-nums"
                style={{ fontSize: "clamp(4.5rem, 20vw, 7rem)" }}>
                {yearsToFIRE > 50 ? "50+" : animYTF.toFixed(1)}
              </span>
              <div className="flex flex-col items-start pb-2.5 gap-0.5">
                <span className="font-serif font-bold text-stone-400 text-2xl leading-none">年</span>
                <span className="text-sm text-stone-400 leading-none whitespace-nowrap">就够了</span>
              </div>
            </div>

            {/* 叙事句 */}
            <p className="text-stone-600 text-sm mt-3 font-medium">
              {workCity && retireCity && workCity.city_slug !== retireCity.city_slug
                ? <>在<strong className="text-stone-900">{workCity.city_name}</strong>投资
                  {" →"} 去<strong className="text-emerald-700">{retireCity.city_name}</strong>永远不工作</>
                : workCity
                  ? <>在<strong className="text-stone-900">{workCity.city_name}</strong>投资，直到财务独立</>
                  : <>每月投 <strong className="text-stone-900">¥{Math.round(monthlyInvest).toLocaleString()}</strong>，直到财务独立</>
              }
            </p>

            {/* 里程碑徽章 */}
            {milestone && (
              <div className="inline-flex items-center gap-1.5 mt-3 px-3 py-1 rounded-full border text-xs font-semibold"
                style={{ borderColor: milestone.color, color: milestone.color, background: `${milestone.color}15` }}>
                <span>{milestone.icon}</span>
                <span>{milestone.label(
                  workCity?.city_name ?? "某城市",
                  retireCity?.city_name ?? "躺平城市"
                )}</span>
              </div>
            )}

            {/* 高年数时的提示 */}
            {yearsToFIRE > 20 && yearsToFIRE <= 50 && (
              Math.abs(rate - 0.35) < 0.1 ? (
                <p className="text-xs text-stone-400 mt-2">
                  点 <strong className="text-stone-600">A股指数</strong>，从{" "}
                  {yearsToFIRE.toFixed(1)} 年变成{" "}
                  <strong className="text-stone-600">
                    {(() => {
                      const rm = 7.5 / 100 / 12;
                      const mratio = monthlyInvest / rm;
                      const base = lump + mratio;
                      if (base <= 0) return "—";
                      const n = Math.log((fireNumber + mratio) / base) / Math.log(1 + rm) / 12;
                      return Math.max(0, n).toFixed(1);
                    })()} 年
                  </strong>
                </p>
              ) : (
                <p className="text-xs text-stone-400 mt-2">
                  投资比例每 +5%，大约少{" "}
                  <strong className="text-stone-600">
                    {Math.max(1, Math.round(yearsToFIRE - (() => {
                      const m2 = monthlyIncome * (investPct + 5) / 100;
                      const rm = rate / 100 / 12;
                      if (rm <= 0 || m2 <= 0) return yearsToFIRE;
                      const n = Math.log((fireNumber + m2 / rm) / (lump + m2 / rm)) / Math.log(1 + rm) / 12;
                      return Math.max(0, n);
                    })()))} 年
                  </strong>
                </p>
              )
            )}
          </div>
        )}


        {/* 次级数据行 */}
        <div className="flex justify-center gap-5 mt-4 text-xs text-stone-400">
          <span>FIRE 目标 <strong className="text-stone-600">{fmtShort(fireNumber)}</strong></span>
          <span className="text-stone-200">·</span>
          <span>{chartYears}年后资产 <strong className="text-stone-600">{fmtShort(animDisplayFV)}</strong></span>
          <span className="text-stone-200">·</span>
          <span>{chartYears}年后被动收入 <strong className="text-stone-600">¥{Math.round(passiveMonthly).toLocaleString()}/月</strong></span>
        </div>

        {/* 两城市 FIRE 差额提示 */}
        {workCity && retireCity
          && workCity.city_slug !== retireCity.city_slug
          && retireCity.avg_monthly_cost && workCity.avg_monthly_cost
          && retireCity.avg_monthly_cost < workCity.avg_monthly_cost && (
          <p className="text-xs text-emerald-600 mt-2">
            比留在{workCity.city_name}退休，FIRE 目标少{" "}
            <strong>¥{fmtShort((workCity.avg_monthly_cost - retireCity.avg_monthly_cost) * 300)}</strong>
          </p>
        )}
      </div>

      {/* ── 4. Rate Presets ── */}
      <div className="px-5 pt-4 pb-3 border-b border-stone-100">
        <div className="flex items-center justify-between mb-2.5">
          <div>
            <span className="text-xs text-stone-400">投资策略</span>
            <span className="text-xs text-stone-300 ml-2">
              {Math.abs(rate - 0.35) < 0.1
                ? "← 点A股指数，看看投资后要几年"
                : "← 点活期存款，看看不投资要几年"}
            </span>
          </div>
          <span className="font-semibold text-stone-900 text-sm tabular-nums">{rate}% / 年</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map(p => {
            const active = Math.abs(rate - p.rate) < 0.15;
            return (
              <button key={p.label} onClick={() => setRate(p.rate)} title={p.src}
                className="text-xs px-3 py-1.5 rounded-full border font-semibold transition-all select-none"
                style={{
                  background:  active ? p.bg : "#fafaf9",
                  color:       active ? p.fg : "#78716c",
                  borderColor: active ? p.bg : "#e7e5e4",
                  transform:   active ? "translateY(-1px)" : "none",
                  boxShadow:   active ? "0 2px 6px rgba(0,0,0,0.1)" : "none",
                }}>
                {p.label} <span className="opacity-60">{p.sub}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── 5. Core Controls ── */}
      <div className="px-5 py-4 space-y-4 border-b border-stone-100">

        {/* Freq toggle + salary */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="flex gap-1 bg-stone-100 p-0.5 rounded">
              {FREQ_OPTIONS.map(f => (
                <button key={f.key}
                  onClick={() => { setFreq(f.key); setIncome(f.key === "weekly" ? 1250 : f.key === "biweekly" ? 2500 : 5000); }}
                  className={`text-xs px-2.5 py-1 rounded transition-colors font-medium ${
                    freq === f.key ? "bg-white text-stone-900 shadow-sm" : "text-stone-500 hover:text-stone-700"
                  }`}>
                  {f.label}
                </button>
              ))}
            </div>
            <span className="font-serif font-black text-stone-900 text-xl tabular-nums">
              ¥{income.toLocaleString()}
            </span>
          </div>
          <Track value={income} min={stepIncome} max={maxIncome} step={stepIncome} onChange={setIncome} />
          {freq !== "monthly" && (
            <p className="text-xs text-stone-400 mt-1">
              折算月收入 <strong className="text-stone-600">¥{Math.round(monthlyIncome).toLocaleString()}</strong>
            </p>
          )}
        </div>

        {/* Invest % */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-stone-500">每月投资</span>
            <span className="text-sm font-semibold text-stone-900 tabular-nums">
              {investPct}% = <span className="text-green-700">¥{Math.round(monthlyInvest).toLocaleString()}</span>
            </span>
          </div>
          <Track value={investPct} min={1} max={60} step={1} onChange={setInvestPct} accent="#15803d" />
          <div className="flex justify-between text-xs text-stone-300 mt-1">
            <span>1%</span><span>60%</span>
          </div>
          {investPct >= 40 && (
            <p className="text-xs text-amber-600 mt-1">超过 40% 很厉害，记得留够生活余裕</p>
          )}
        </div>

      </div>

      {/* ── 6. Advanced toggle ── */}
      <button
        onClick={() => setShowAdvanced(v => !v)}
        className="w-full px-5 py-2.5 flex items-center justify-between text-xs text-stone-400 hover:text-stone-600 hover:bg-stone-50 transition-colors border-b border-stone-100">
        <span>帮我算得更准</span>
        <span className="font-mono">{showAdvanced ? "↑ 收起" : "↓ 展开"}</span>
      </button>

      {/* ── 7. Advanced Panel ── */}
      {showAdvanced && (
        <div className="px-5 py-4 space-y-4 border-b border-stone-100 bg-stone-50">

          {/* 退休月消费 */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-stone-500">退休月消费</span>
              <span className="text-sm font-semibold text-stone-900 tabular-nums">
                ¥{livingCost.toLocaleString()}
                {retireCity?.city_name && (
                  <span className="text-xs font-normal text-stone-400 ml-1">（{retireCity.city_name}）</span>
                )}
              </span>
            </div>
            <Track value={livingCost} min={1000} max={20000} step={500} onChange={setLivingCost} accent="#0369a1" />
            <div className="flex justify-between text-xs text-stone-300 mt-1">
              <span>¥1,000</span><span>¥20,000</span>
            </div>
          </div>

          {/* 投资年限 */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-stone-500">投资年限（用于计算图表和终值）</span>
              <span className="text-sm font-semibold text-stone-900">{years} 年</span>
            </div>
            <Track value={years} min={1} max={40} step={1} onChange={setYears} accent="#7c3aed" />
            <div className="flex justify-between text-xs text-stone-300 mt-1">
              <span>1年</span><span>40年</span>
            </div>
          </div>

          {/* 一次性投入 */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-stone-500">额外一次性投入</span>
              <span className="text-sm font-semibold text-stone-900">
                {lump > 0 ? fmtShort(lump) : "无"}
              </span>
            </div>
            <Track value={lump} min={0} max={200000} step={5000} onChange={setLump} accent="#a78bfa" />
            <div className="flex justify-between text-xs text-stone-300 mt-1">
              <span>¥0</span><span>¥20万</span>
            </div>
          </div>

          {/* 自定义利率 */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-stone-500">自定义年化利率</span>
              <span className="text-sm font-semibold text-stone-900">{rate}%</span>
            </div>
            <Track value={rate} min={0.1} max={30} step={0.1} onChange={setRate} />
            <div className="flex justify-between text-xs text-stone-300 mt-1">
              <span>0.1%</span><span>30%</span>
            </div>
          </div>

          {/* 72 rule */}
          {doubleYrs && (
            <div className="flex items-center gap-4 border border-stone-200 rounded-lg px-4 py-3 bg-white">
              <div className="font-serif font-black text-3xl text-stone-900 leading-none">72</div>
              <div className="border-l border-stone-200 pl-4">
                <div className="text-sm font-semibold text-stone-800">
                  每 <span className="text-green-700">{doubleYrs} 年</span>翻一倍
                </div>
                <div className="text-xs text-stone-400 mt-0.5">
                  72 ÷ {rate}% = {doubleYrs} 年
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── 8. Growth Chart ── */}
      <div className="px-5 pt-4 pb-3 border-b border-stone-100">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-stone-400">
            资产增长曲线（{chartYears}年{chartYears > years ? `，含 FIRE 时点` : ""}）
          </span>
          <div className="flex items-center gap-3 text-xs text-stone-400">
            <span className="flex items-center gap-1">
              <span className="inline-block w-3 h-0.5 bg-green-700 rounded" />终值
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-3" style={{ borderTop: "1.5px dashed #d6d3d1" }} />本金
            </span>
          </div>
        </div>
        <GrowthChart p={lump} m={monthlyInvest} r={rate} y={chartYears} />
        <div className="flex justify-between text-xs text-stone-500 mt-2">
          <span>本金 <strong className="text-stone-700">{fmtShort(totalInvested)}</strong></span>
          <span>利息 <strong className="text-green-700">{fmtShort(interest)}</strong></span>
          <span className="font-serif font-bold text-stone-900">{(mult).toFixed(1)}×</span>
        </div>
        {/* Interest proportion bar */}
        <div className="mt-2 h-1.5 bg-stone-100 rounded-full overflow-hidden">
          <div className="h-full bg-green-700 rounded-full transition-all duration-700"
            style={{ width: `${interestPct.toFixed(1)}%` }} />
        </div>
      </div>

      {/* ── 9. Footnote ── */}
      <div className="px-5 py-3">
        <p className="text-xs text-stone-300 leading-relaxed">
          标普500含股息再投资百年年化 10.4%（Of Dollars &amp; Data）；
          巴菲特 19.7% 来自伯克希尔哈撒韦2025年报；
          城市数据来源国家统计局 · Numbeo · {reportYear} 年。历史均值不代表未来。
        </p>
      </div>

      {/* ── 10. Debt page entry ── */}
      <Link href="/tools/escape"
        className="flex items-center justify-between px-5 py-4 border-t border-stone-100 hover:bg-emerald-50 transition-colors group">
        <div>
          <div className="text-sm font-semibold text-stone-700 group-hover:text-emerald-900 transition-colors">
            出逃路线：打份洋工，去哪躺平？
          </div>
          <div className="text-xs text-stone-400 mt-0.5">
            新西兰最低工资 → 清迈 FIRE，只需 9.5 年
          </div>
        </div>
        <span className="text-stone-400 group-hover:text-emerald-900 transition-colors text-sm font-mono">→</span>
      </Link>

      <Link href="/tools/debt"
        className="flex items-center justify-between px-5 py-4 border-t-2 border-stone-100 hover:bg-amber-50 transition-colors group">
        <div>
          <div className="text-sm font-semibold text-stone-700 group-hover:text-amber-900 transition-colors">
            ⚠️ 你已经替银行打了多少工？
          </div>
          <div className="text-xs text-stone-400 mt-0.5">
            花呗 18.25% 年利率 · 最低还款陷阱 · 账单日还清技巧
          </div>
        </div>
        <span className="text-stone-400 group-hover:text-amber-900 transition-colors text-sm font-mono">→</span>
      </Link>

    </div>
  );
}
