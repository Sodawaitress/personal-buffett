"use client";

import { useState, useMemo, useEffect, useRef } from "react";
import Link from "next/link";
import { useCityData, findCity, snapToStep } from "@/hooks/useCityData";
import { CityPicker } from "@/components/CityPicker";

const SAVE_RATE   = 0.20;
const YEARS       = 20;
const ANNUAL_RATE = 10.4;
// 国家统计局2024年城镇居民人均消费支出约¥2,897/月，家庭按2人算约¥6,000
// 用¥6,000作为"普通城市生活"基准，明确标注
const MONTHLY_LIVING_COST = 6000;

function calcFV(monthly: number) {
  const rm = ANNUAL_RATE / 100 / 12, n = YEARS * 12;
  return monthly * ((1 + rm) ** n - 1) / rm;
}

function useSpring(target: number, ms = 500) {
  const [v, setV] = useState(target);
  const s = useRef({ from: target, t0: 0, raf: 0 });
  useEffect(() => {
    s.current.from = v;
    s.current.t0   = performance.now();
    cancelAnimationFrame(s.current.raf);
    const tick = (now: number) => {
      const t = Math.min(1, (now - s.current.t0) / ms);
      setV(s.current.from + (target - s.current.from) * (1 - (1 - t) ** 3));
      if (t < 1) s.current.raf = requestAnimationFrame(tick);
    };
    s.current.raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(s.current.raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);
  return v;
}

export function CompoundMini() {
  const [freq,   setFreq]   = useState<"monthly" | "weekly">("monthly");
  const [income, setIncome] = useState(5000);

  // 首页用单城市：同时填收入 + 生活成本
  const { major, lifestyle, all: allCities, reportYear } = useCityData();
  const [citySlug, setCitySlug] = useState<string | null>(null);
  const selectedCity = findCity(allCities, citySlug);

  function handleCity(slug: string | null) {
    setCitySlug(slug);
    if (!slug) return;
    const c = findCity(allCities, slug);
    if (!c) return;
    const sal = snapToStep(c.avg_monthly_salary);
    if (sal) setIncome(sal);
  }

  const monthlyIncome  = freq === "weekly" ? income * 52 / 12 : income;
  const monthlyInvest  = monthlyIncome * SAVE_RATE;
  const fv             = useMemo(() => calcFV(monthlyInvest), [monthlyInvest]);
  const totalInvested  = monthlyInvest * 12 * YEARS;

  const animFV = useSpring(fv);

  // format the big number
  const wan  = animFV / 10000;
  const yi   = animFV / 100000000;
  const bigDisplay = animFV >= 1e8
    ? `${yi.toFixed(2)} 亿`
    : `${wan.toFixed(wan >= 100 ? 0 : 1)} 万`;

  const maxIncome  = freq === "weekly" ? 20000 : 80000;
  const stepIncome = freq === "weekly" ? 200 : 500;
  const trackPct   = ((income - stepIncome) / (maxIncome - stepIncome)) * 100;

  const multiplier = totalInvested > 0 ? fv / totalInvested : 0;

  // human meaning
  const passiveMonthly    = animFV * 0.04 / 12;
  const passiveCoversCost = passiveMonthly >= MONTHLY_LIVING_COST;
  const DRAWDOWN_RM = 0.04 / 12;
  const yearsOfFreedom = useMemo(() => {
    if (animFV <= 0) return 0;
    const threshold = animFV * DRAWDOWN_RM;
    if (MONTHLY_LIVING_COST <= threshold) return Infinity;
    return Math.log(MONTHLY_LIVING_COST / (MONTHLY_LIVING_COST - threshold)) / Math.log(1 + DRAWDOWN_RM) / 12;
  }, [animFV]);

  // FIRE crossover: minimum years to invest before passive income covers living cost
  const fireNumber  = MONTHLY_LIVING_COST * 300;
  const yearsToFIRE = useMemo(() => {
    if (monthlyInvest <= 0) return Infinity;
    const rm     = ANNUAL_RATE / 100 / 12;
    const mratio = monthlyInvest / rm;
    const n      = Math.log((fireNumber + mratio) / mratio) / Math.log(1 + rm) / 12;
    return n <= 0 ? 0 : n;
  }, [monthlyInvest, fireNumber]);

  return (
    <div className="border-2 border-stone-900 bg-white overflow-hidden">

      {/* top bar */}
      <div className="bg-stone-900 px-5 py-2.5 flex items-center justify-between">
        <span className="text-xs text-stone-400 tracking-wide">如果你投资 20%，{YEARS}年后</span>
        <div className="flex gap-1">
          {(["monthly", "weekly"] as const).map(f => (
            <button key={f}
              onClick={() => { setFreq(f); setIncome(f === "monthly" ? 5000 : 1250); }}
              className={`text-xs px-2.5 py-0.5 rounded transition-colors ${
                freq === f ? "bg-white text-stone-900 font-semibold" : "text-stone-500 hover:text-white"
              }`}>
              {f === "monthly" ? "月薪" : "周薪"}
            </button>
          ))}
        </div>
      </div>

      <div className="px-5 pt-5 pb-4">

        {/* salary slider */}
        <div className="mb-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-stone-400">
              {freq === "monthly" ? "税后月薪" : "税后周薪"}
            </span>
            <span className="font-mono font-semibold text-stone-700 tabular-nums text-sm">
              ¥{income.toLocaleString()}
            </span>
          </div>
          <div className="relative h-1.5 rounded-full bg-stone-100">
            <div className="absolute left-0 top-0 h-full bg-stone-900 rounded-full pointer-events-none"
              style={{ width: `${trackPct.toFixed(1)}%` }} />
            <input type="range"
              min={stepIncome} max={maxIncome} step={stepIncome} value={income}
              onChange={e => setIncome(Number(e.target.value))}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
          </div>
        </div>

        {/* 城市参考（单城市，同时填收入 + 生活成本）*/}
        {major.length > 0 && (
          <div className="mb-4">
            <CityPicker
              label="参考城市"
              value={citySlug}
              onChange={c => handleCity(c?.city_slug ?? null)}
              major={major}
              lifestyle={lifestyle}
              reportYear={reportYear}
              showLifestyle={true}
            />
          </div>
        )}

        {/* THE number — visual focal point */}
        <div className="text-center py-4 border-y border-stone-100 mb-4">
          <div className="font-serif font-black text-stone-900 tabular-nums leading-none"
            style={{ fontSize: "clamp(3rem, 14vw, 5.5rem)" }}>
            ¥{bigDisplay}
          </div>
          <div className="mt-2 text-sm text-stone-400">
            投入 <strong className="text-stone-600">¥{Math.round(totalInvested / 10000).toFixed(0)}万</strong>
            <span className="mx-2 text-stone-200">·</span>
            增值 <strong className="text-green-700">
              ¥{Math.round((animFV - totalInvested) / 10000).toFixed(0)}万
            </strong>
            <span className="mx-2 text-stone-200">·</span>
            <strong className="text-stone-700">{multiplier.toFixed(1)}×</strong>
          </div>
        </div>

        {/* human meaning */}
        <div className="mb-4 rounded-lg border border-stone-200 bg-stone-50 divide-y divide-stone-100">
          <div className="flex items-center gap-3 px-4 py-3">
            <span className="text-lg shrink-0">💸</span>
            <div>
              <div className="text-sm font-semibold text-stone-800">
                每月被动收入{" "}
                <span className="text-green-700">
                  ¥{Math.round(passiveMonthly).toLocaleString()}
                </span>
              </div>
              <div className="text-xs text-stone-400 mt-0.5">
                按4%提款法则——这笔钱可以永远取不完
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3 px-4 py-3 bg-stone-50">
            <span className="text-lg shrink-0">⏱️</span>
            <div>
              <div className="text-sm font-semibold text-stone-800">
                最少投资{" "}
                {yearsToFIRE === Infinity
                  ? "——"
                  : yearsToFIRE <= 0
                    ? <span className="text-green-700">已达到目标</span>
                    : <><span className="font-serif text-xl text-stone-900">{yearsToFIRE.toFixed(1)}</span> 年</>
                }
                {yearsToFIRE > 0 && yearsToFIRE !== Infinity && <>，就可以永远不工作</>}
              </div>
              <div className="text-xs text-stone-400 mt-0.5">
                财务独立目标 ¥{Math.round(fireNumber / 10000)}万
                （¥{MONTHLY_LIVING_COST.toLocaleString()}/月 × 300）
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 px-4 py-3">
            <span className="text-lg shrink-0">🗓️</span>
            <div>
              <div className="text-sm font-semibold text-stone-800">
                {passiveCoversCost || yearsOfFreedom === Infinity ? (
                  <>边投资边提款，<span className="text-green-700">可以永远不工作</span></>
                ) : yearsOfFreedom >= 1 ? (
                  <>边投资边提款，可以生活 <span className="text-stone-900">{yearsOfFreedom.toFixed(1)} 年</span></>
                ) : (
                  <>继续增加投资，目标超过1年</>
                )}
              </div>
              <div className="text-xs text-stone-400 mt-0.5">
                按 ¥{MONTHLY_LIVING_COST.toLocaleString()}/月提款，本金继续增值
                {yearsOfFreedom !== Infinity && yearsOfFreedom >= 1 &&
                  `，${yearsOfFreedom.toFixed(1)}年后本金花完`}
              </div>
            </div>
          </div>
        </div>

        {/* context note + CTA */}
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-stone-400 leading-relaxed">
            标普500历史均值 10.4%，{YEARS}年复利
          </p>
          <Link href="/tools/compound"
            className="shrink-0 px-4 py-2 bg-stone-900 text-white text-xs rounded hover:bg-stone-700 transition-colors whitespace-nowrap">
            算算你还有多少年不用打工喵 →
          </Link>
        </div>

      </div>
    </div>
  );
}
