"use client";

import { useState, useMemo, useEffect, useRef } from "react";
import Link from "next/link";

// ── utils ─────────────────────────────────────────────────────────────────────

function calcMinPayment(principal: number, annualRate: number, mult = 1) {
  const rm = annualRate / 100 / 12;
  let balance = principal;
  let totalPaid = 0;
  let months = 0;
  while (balance > 0.5 && months < 600) {
    balance *= (1 + rm);
    const minPay = Math.max(balance * 0.02 * mult, 10);
    const payment = Math.min(minPay, balance);
    balance -= payment;
    totalPaid += payment;
    months++;
  }
  return {
    months,
    years: months / 12,
    totalPaid: Math.max(totalPaid, principal),
    extraInterest: Math.max(0, totalPaid - principal),
  };
}

function calcFV(p: number, m: number, annualRate: number, years: number) {
  const rm = annualRate / 100 / 12;
  const n = years * 12;
  if (rm === 0) return p + m * n;
  return p * (1 + rm) ** n + m * ((1 + rm) ** n - 1) / rm;
}

function fmt(n: number) {
  if (n >= 1e8) return `${(n / 1e8).toFixed(1)}亿`;
  if (n >= 1e4) return `${(n / 1e4).toFixed(1)}万`;
  return `¥${Math.round(n).toLocaleString()}`;
}

function fmtWorkTime(months: number) {
  if (months < 1)  return "不到1个月";
  if (months < 24) return `${months.toFixed(1)} 个月`;
  const y = Math.floor(months / 12);
  const m = Math.round(months % 12);
  return m > 0 ? `${y}年${m}个月` : `${y}年`;
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

function Track({ value, min, max, step, onChange, accent = "#92400e" }: {
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

// ── constants ─────────────────────────────────────────────────────────────────

const DEBT_RATES = [
  { label: "花呗",   sub: "18.25%", rate: 18.25, note: "日利率 0.05% × 365" },
  { label: "信用卡", sub: "16%",    rate: 16,    note: "大多数银行标准利率" },
  { label: "网贷",   sub: "24%",    rate: 24,    note: "法定民间借贷上限" },
];

// ── component ─────────────────────────────────────────────────────────────────

export function DebtCalculator() {
  const [debtAmount, setDebtAmount] = useState(3000);
  const [salary,     setSalary]     = useState(6000);
  const [debtRate,   setDebtRate]   = useState(18.25);

  const base = useMemo(() => calcMinPayment(debtAmount, debtRate, 1), [debtAmount, debtRate]);
  const fast = useMemo(() => calcMinPayment(debtAmount, debtRate, 2), [debtAmount, debtRate]);

  const animYears = useSpring(Math.min(base.years, 50));
  const workMonths = salary > 0 ? base.extraInterest / salary : 0;

  const investFV = calcFV(base.extraInterest, 0, 7.5, 10);
  const yearsSaved = base.years - fast.years;
  const moneySaved = base.extraInterest - fast.extraInterest;

  return (
    <div className="space-y-4">

      {/* ── § 揭露区 ── */}
      <div className="border-2 border-stone-900 bg-stone-900 overflow-hidden">
        <div className="px-5 pt-5 pb-3">
          <p className="text-xs text-stone-400 tracking-widest uppercase mb-1">没人告诉你的事</p>
          <h2 className="font-serif font-black text-white text-2xl leading-tight">
            复利是把双刃刀
          </h2>
          <p className="text-stone-400 text-sm mt-1">
            银行用它割你，你也可以用它割回去
          </p>
        </div>

        <div className="divide-y divide-stone-800">

          {/* 陷阱1 */}
          <div className="px-5 py-4 flex gap-4">
            <div className="shrink-0 w-8 h-8 rounded-full bg-red-900 flex items-center justify-center text-red-300 font-bold text-sm">1</div>
            <div>
              <div className="text-white font-semibold text-sm">日利率 0.05% = 年利率 18.25%</div>
              <div className="text-stone-400 text-xs mt-1 leading-relaxed">
                故意写成日利率的。0.05% 看着小，× 365 = <span className="text-red-300 font-semibold">18.25%</span>。
                A股年化才 7.5%，花呗是它的 <span className="text-red-300 font-semibold">2.4 倍</span>。
              </div>
            </div>
          </div>

          {/* 陷阱2 */}
          <div className="px-5 py-4 flex gap-4">
            <div className="shrink-0 w-8 h-8 rounded-full bg-red-900 flex items-center justify-center text-red-300 font-bold text-sm">2</div>
            <div>
              <div className="text-white font-semibold text-sm">最低还款，还到死</div>
              <div className="text-stone-400 text-xs mt-1 leading-relaxed">
                ¥10,000 只还最低额（每月2%）——
                要还 <span className="text-red-300 font-semibold">17 年</span>，
                多付 <span className="text-red-300 font-semibold">¥12,000+</span> 利息。
                "最低还款"是给银行打工，不是给自己省钱。
              </div>
            </div>
          </div>

          {/* 征信 */}
          <div className="px-5 py-4 flex gap-4">
            <div className="shrink-0 w-8 h-8 rounded-full bg-amber-900 flex items-center justify-center text-amber-300 font-bold text-sm">!</div>
            <div>
              <div className="text-amber-300 font-semibold text-sm">花呗上征信了，买房会看这个</div>
              <div className="text-stone-400 text-xs mt-1 leading-relaxed">
                2021 年起花呗接入央行征信。你的花呗<span className="text-amber-300 font-semibold">额度</span>会被银行算作负债，
                额度越高，房贷能批的金额越少。不是欠款，是额度本身。
                准备买房前，先把花呗关掉。
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* ── § 计算器 ── */}
      <div className="border-2 border-stone-900 bg-white overflow-hidden">

        <div className="bg-stone-100 px-5 py-2.5">
          <span className="text-xs font-semibold text-stone-600 tracking-wide">算算你的情况</span>
        </div>

        <div className="px-5 py-4 space-y-4">

          {/* 欠款 */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-stone-500">花呗 / 信用卡欠款</span>
              <span className="font-semibold text-stone-900 tabular-nums text-sm">
                ¥{debtAmount.toLocaleString()}
              </span>
            </div>
            <Track value={debtAmount} min={500} max={100000} step={500} onChange={setDebtAmount} />
            <div className="flex justify-between text-xs text-stone-300 mt-1">
              <span>¥500</span><span>¥10万</span>
            </div>
          </div>

          {/* 月薪 */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-stone-500">税后月薪</span>
              <span className="font-semibold text-stone-900 tabular-nums text-sm">
                ¥{salary.toLocaleString()}
              </span>
            </div>
            <Track value={salary} min={1000} max={50000} step={500} onChange={setSalary} accent="#1c1917" />
            <div className="flex justify-between text-xs text-stone-300 mt-1">
              <span>¥1,000</span><span>¥5万</span>
            </div>
          </div>

          {/* 利率 */}
          <div>
            <div className="text-xs text-stone-500 mb-2">贷款利率</div>
            <div className="flex gap-2 flex-wrap">
              {DEBT_RATES.map(d => {
                const active = Math.abs(debtRate - d.rate) < 0.1;
                return (
                  <button key={d.label} onClick={() => setDebtRate(d.rate)}
                    title={d.note}
                    className={`text-xs px-3 py-1.5 rounded-full border font-semibold transition-all ${
                      active
                        ? "bg-amber-800 text-white border-amber-800"
                        : "bg-white text-stone-600 border-stone-200 hover:border-stone-400"
                    }`}>
                    {d.label} <span className="opacity-60">{d.sub}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* 核心结果 */}
        <div className="text-center py-6 border-y-2 border-stone-900 bg-amber-50">
          <div className="text-xs text-stone-400 tracking-widest mb-1">
            你多付的利息，银行拿去投资 20 年
          </div>
          <div className="flex items-end justify-center gap-1 leading-none">
            <span className="font-serif font-black text-red-700 tabular-nums"
              style={{ fontSize: "clamp(4rem, 18vw, 6.5rem)" }}>
              {fmt(calcFV(base.extraInterest, 0, 7.5, 20))}
            </span>
          </div>
          <div className="mt-3 text-sm text-stone-600">
            你多付{" "}
            <strong className="text-red-700">¥{Math.round(base.extraInterest).toLocaleString()}</strong>
            <span className="mx-2 text-stone-300">·</span>
            只还最低额要还{" "}
            <strong className="text-stone-700">{base.years > 49 ? "50+" : animYears.toFixed(1)} 年</strong>
          </div>
        </div>

        {/* 打工换算 */}
        <div className="border-b border-stone-100 divide-y divide-stone-100">

          {/* 每天利息 */}
          <div className="px-5 py-3 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-stone-800">
                每天醒来，银行自动拿走
              </div>
              <div className="text-xs text-stone-400 mt-0.5">现在，今天，每天</div>
            </div>
            <div className="text-right">
              <div className="font-serif font-black text-amber-900 text-2xl tabular-nums">
                ¥{(debtAmount * debtRate / 100 / 365).toFixed(1)}
              </div>
              <div className="text-xs text-stone-400">/ 天</div>
            </div>
          </div>

          {/* 白打工换算 */}
          <div className="px-5 py-3 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-stone-800">
                总共替银行白打
              </div>
              <div className="text-xs text-stone-400 mt-0.5">
                多付 ¥{Math.round(base.extraInterest).toLocaleString()} ÷ ¥{salary.toLocaleString()} 月薪
              </div>
            </div>
            <div className="text-right">
              <div className="font-serif font-black text-amber-900 text-2xl tabular-nums">
                {fmtWorkTime(workMonths)}
              </div>
              <div className="text-xs text-stone-400">的工</div>
            </div>
          </div>

          {/* 机会成本 */}
          <div className="px-5 py-3 flex items-center justify-between bg-stone-50">
            <div>
              <div className="text-sm font-semibold text-stone-800">
                银行拿走这笔钱去投资
              </div>
              <div className="text-xs text-stone-400 mt-0.5">
                ¥{Math.round(base.extraInterest).toLocaleString()} × A股指数 7.5%，20年
              </div>
            </div>
            <div className="text-right">
              <div className="font-serif font-black text-red-700 text-2xl tabular-nums">
                {fmt(calcFV(base.extraInterest, 0, 7.5, 20))}
              </div>
              <div className="text-xs text-stone-400">就没了</div>
            </div>
          </div>

        </div>
      </div>

      {/* ── § 逃生出口 ── */}
      <div className="border-2 border-stone-900 bg-white overflow-hidden">

        <div className="bg-stone-900 px-5 py-2.5">
          <span className="text-xs font-semibold text-stone-400 tracking-wide">三个逃生出口</span>
        </div>

        <div className="divide-y divide-stone-100">

          {/* 选项A */}
          <div className="px-5 py-4 flex gap-4 items-start">
            <div className="shrink-0 mt-0.5 w-7 h-7 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-700 font-bold text-xs">A</div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-stone-800">账单日前全额还清</div>
              <div className="text-xs text-stone-400 mt-0.5">利息 = ¥0，最优解，没有之一</div>
            </div>
            <div className="text-right shrink-0">
              <div className="text-sm font-semibold text-emerald-700">省 ¥{Math.round(base.extraInterest).toLocaleString()}</div>
              <div className="text-xs text-stone-300">全部利息</div>
            </div>
          </div>

          {/* 选项B */}
          <div className="px-5 py-4 flex gap-4 items-start">
            <div className="shrink-0 mt-0.5 w-7 h-7 rounded-full bg-sky-100 flex items-center justify-center text-sky-700 font-bold text-xs">B</div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-stone-800">每月多还一倍（最低额 × 2）</div>
              <div className="text-xs text-stone-400 mt-0.5">
                还清时间{" "}
                <span className="text-stone-600 font-semibold">{base.years.toFixed(1)} 年</span>
                {" → "}
                <span className="text-sky-700 font-semibold">{fast.years.toFixed(1)} 年</span>
                ，少还 {yearsSaved.toFixed(1)} 年
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="text-sm font-semibold text-sky-700">省 {fmt(moneySaved)}</div>
              <div className="text-xs text-stone-300">利息</div>
            </div>
          </div>

          {/* 选项C */}
          <div className="px-5 py-4 flex gap-4 items-start">
            <div className="shrink-0 mt-0.5 w-7 h-7 rounded-full bg-stone-100 flex items-center justify-center text-stone-700 font-bold text-xs">C</div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-stone-800">还清后，把这笔利息拿去投资</div>
              <div className="text-xs text-stone-400 mt-0.5">
                ¥{Math.round(base.extraInterest).toLocaleString()} 按 A股指数 7.5%，投 10 年
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="text-sm font-semibold text-stone-700">→ {fmt(investFV)}</div>
              <div className="text-xs text-stone-300">10年后</div>
            </div>
          </div>

        </div>
      </div>

      {/* ── CTA ── */}
      <div className="border-2 border-stone-900 bg-stone-900 px-5 py-4 flex items-center justify-between gap-4">
        <p className="text-sm text-stone-300 leading-relaxed">
          还清了，把这笔钱投进去<br />
          <span className="text-white font-semibold">算算还要打几年工</span>
        </p>
        <Link href="/tools/compound"
          className="shrink-0 px-5 py-2.5 bg-white text-stone-900 text-xs font-semibold rounded hover:bg-stone-100 transition-colors whitespace-nowrap">
          去算一算 →
        </Link>
      </div>

      {/* 数据来源 */}
      <p className="text-xs text-stone-300 leading-relaxed px-1">
        花呗日利率 0.05% 来自蚂蚁集团官网；信用卡利率参考央行相关规定；
        沪深300年化7.5%为价格收益，不含股息，历史均值不代表未来。
      </p>

    </div>
  );
}
