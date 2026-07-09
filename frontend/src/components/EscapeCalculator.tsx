"use client";

import { useState, useMemo } from "react";
import Link from "next/link";

// ── 汇率配置（更新这里 → 所有城市 CNY 数字自动重算）────────────────────────
// 最低工资/税率变了：改对应城市的 salaryLocal；汇率变了：改这里的 FX
const FX = {
  USD: 7.1,    // 美元
  NZD: 4.3,    // 新西兰元
  AUD: 4.6,    // 澳元
  JPY: 0.047,  // 日元（当前弱势，历史高点约 0.065）
  SGD: 5.4,    // 新加坡元
  AED: 2.0,    // 迪拜迪拉姆
  GBP: 9.0,    // 英镑
} as const;
type FxCurrency = keyof typeof FX;
const FX_DATE = "2025年Q4";  // 最后核对汇率的时间

function toCNY(local: number, cur: FxCurrency): number {
  return Math.round(local * FX[cur]);
}

type WorkAccess = "open" | "skilled" | "elite";

// ── 工作城市原始数据（本地货币）──────────────────────────────────────────────
// salaryLocal = 税后月薪（本地货币）  livingLocal = 节俭生活月支出（本地货币）
const _WORK_RAW: Array<{
  id: string; name: string; flag: string;
  currency: FxCurrency;
  salaryLocal: number;
  livingLocal: number;
  access: WorkAccess; visaNote: string; accessLabel?: string;
}> = [
  { id: "cruise",  name: "邮轮工作",   flag: "🚢",
    currency: "USD", salaryLocal: 1521, livingLocal: 101,
    access: "open",
    visaNote: "18-28岁，高中学历，基础英语（可培训），通过国内中介直接申请，食宿全包。合同6-10个月，结束后回家休假。薪资含小费，以服务员/客舱服务等中端岗位估算 USD $1,521/月税后。",
    accessLabel: "高中即可" },
  { id: "nz_min",  name: "新西兰最低", flag: "🇳🇿",
    currency: "NZD", salaryLocal: 3214, livingLocal: 1674,
    access: "open",
    visaNote: "打工假日签（IWP）35岁以下均可申请，无需雇主，无需学历。最多1-2年，之后需转技术签才能长期待。税后：最低时薪 NZD $23.15×40h，扣所得税+KiwiSaver 3%（锁到65岁）= NZD $3,214/月。",
    accessLabel: "35岁以下即可" },
  { id: "au",      name: "澳大利亚",   flag: "🇦🇺",
    currency: "AUD", salaryLocal: 3538, livingLocal: 2000,
    access: "open",
    visaNote: "打工假日签35岁以下可申，最多3年（后两年需农场工作）。WHV持有人没有个税免征额，从第一块钱按15%统一征税。税后：最低时薪 AUD $24.10×38h，15% WHV税率 = AUD $3,538/月。",
    accessLabel: "35岁以下即可" },
  { id: "nz",      name: "新西兰技术", flag: "🇳🇿",
    currency: "NZD", salaryLocal: 4186, livingLocal: 1651,
    access: "skilled",
    visaNote: "技术移民，需雇主担保+积分门槛，可长期居留。税后：NZD $5,500/月税前（护士/IT/工程师），扣所得税+ACC+KiwiSaver 3% = NZD $4,186/月。" },
  { id: "jp",      name: "日本东京",   flag: "🇯🇵",
    currency: "JPY", salaryLocal: 234043, livingLocal: 117021,
    access: "skilled",
    visaNote: "工签相对好拿，日语N3+有优势。税后：JPY ¥280,000/月税前（N3初级岗），扣所得税+健保+养老金 = JPY ¥234,000/月。日元弱：花钱便宜但挣来的换成人民币也打折。" },
  { id: "sg",      name: "新加坡",     flag: "🇸🇬",
    currency: "SGD", salaryLocal: 4259, livingLocal: 2000,
    access: "elite",
    visaNote: "EP需本科学历+雇主担保，竞争激烈。税后：EP最低门槛 SGD $5,000/月，非居民15%税率 = SGD $4,259/月。满183天转税务居民后实际税率更低，到手更多。" },
  { id: "ae",      name: "迪拜",       flag: "🇦🇪",
    currency: "AED", salaryLocal: 20000, livingLocal: 5000,
    access: "elite",
    visaNote: "UAE零个人所得税，AED 20,000/月是外派技术/金融岗的水平（需专业背景+雇主担保）。工签绑定雇主，失业即需离境。普通服务业（餐厅/贸易）工资根本覆盖不了当地生活费，这里不适用。" },
  { id: "uk",      name: "伦敦",       flag: "🇬🇧",
    currency: "GBP", salaryLocal: 2378, livingLocal: 1400,
    access: "elite",
    visaNote: "税后：中级专业岗 GBP £3,200/月税前，扣所得税20%+NI 8% = GBP £2,378/月。HSM签名额有限，zone 2合租租金持续涨（£1,100–1,500/月）。" },
];

// CNY 值由 FX 自动推算，不要手工填
const WORK_REFS = _WORK_RAW.map(w => ({
  ...w,
  salaryCNY: toCNY(w.salaryLocal, w.currency),
  livingCNY: toCNY(w.livingLocal, w.currency),
}));

const FIRE_REFS = [
  { id: "dali",      name: "大理",     flag: "🏔️", monthlyCNY: 3000, note: "洱海边，气候好",       easter: false, japan: false },
  { id: "kunming",   name: "昆明",     flag: "🌸", monthlyCNY: 3500, note: "春城，四季如春",       easter: false, japan: false },
  { id: "chengdu",   name: "成都",     flag: "🐼", monthlyCNY: 4000, note: "慢生活，吃不贵",       easter: false, japan: false },
  { id: "guangzhou", name: "广州",     flag: "🌃", monthlyCNY: 5000, note: "一线舒适，比北上便宜",  easter: false, japan: false },
  { id: "danang",    name: "岘港",     flag: "🇻🇳", monthlyCNY: 4500, note: "90天电子签，最实惠",   easter: false, japan: false },
  { id: "chiangmai", name: "清迈",     flag: "🇹🇭", monthlyCNY: 5000, note: "60天旅游签可续",       easter: false, japan: false },
  { id: "penang",    name: "槟城",     flag: "🇲🇾", monthlyCNY: 6500, note: "华人多，英文通用",     easter: false, japan: false },
  { id: "bali",      name: "巴厘岛",   flag: "🇮🇩", monthlyCNY: 8000, note: "数字游民签",           easter: false, japan: false },
  { id: "fukuoka",   name: "福冈",     flag: "🇯🇵", monthlyCNY: 5500, note: "日元弱窗口期",         easter: false, japan: true  },
  { id: "osaka",     name: "大阪",     flag: "🇯🇵", monthlyCNY: 6500, note: "比东京便宜25%",        easter: false, japan: true  },
  { id: "kyoto_r",   name: "京都农村", flag: "🏯", monthlyCNY: 3500, note: "空置房极低租金",        easter: false, japan: true  },
  { id: "tbilisi",   name: "第比利斯", flag: "🇬🇪", monthlyCNY: 5000, note: "中国护照免签365天！",  easter: true,  japan: false },
];

const RATES = [
  { label: "A股 7.5%", rate: 7.5 },
  { label: "标普 10.4%", rate: 10.4 },
];

const SHANGHAI_MONTHLY = 1500;

// ── Utils ──────────────────────────────────────────────────────────────────────

function calcYTF(m: number, target: number, rate: number): number {
  if (m <= 0 || target <= 0) return Infinity;
  const rm = rate / 100 / 12;
  if (rm <= 0) return target / m / 12;
  const mratio = m / rm;
  const n = Math.log((target + mratio) / mratio) / Math.log(1 + rm) / 12;
  return n <= 0 ? 0 : n;
}

function fmtCNY(n: number) {
  if (n >= 1e8) return `¥${(n / 1e8).toFixed(1)}亿`;
  if (n >= 1e4) return `¥${(n / 1e4).toFixed(1)}万`;
  return `¥${Math.round(n).toLocaleString()}`;
}

function Track({ value, min, max, step, onChange, accent = "#1c1917" }: {
  value: number; min: number; max: number; step: number;
  onChange: (v: number) => void; accent?: string;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="relative h-3 rounded-full bg-stone-100" style={{ touchAction: "none" }}>
      <div className="absolute left-0 top-0 h-full rounded-full pointer-events-none"
        style={{ width: `${pct}%`, background: accent }} />
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="absolute inset-0 w-full opacity-0 cursor-pointer"
        style={{ height: "100%", touchAction: "none" }} />
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function EscapeCalculator() {
  const [workId,   setWorkId]   = useState("nz_min");
  const [fireId,   setFireId]   = useState("chiangmai");
  const [rateIdx,  setRateIdx]  = useState(0);
  const defaultWork = WORK_REFS.find(c => c.id === "nz_min")!;
  const defaultFire = FIRE_REFS.find(c => c.id === "chiangmai")!;
  const [salary,     setSalary]     = useState<number>(defaultWork.salaryCNY);
  const [workLiving, setWorkLiving] = useState<number>(defaultWork.livingCNY);
  const [fireLiving, setFireLiving] = useState<number>(defaultFire.monthlyCNY);

  const rate = RATES[rateIdx].rate;
  const monthlySavings = Math.max(0, salary - workLiving);
  const fireNumber     = fireLiving * 300;

  const yearsToFIRE   = useMemo(() => calcYTF(monthlySavings, fireNumber, rate), [monthlySavings, fireNumber, rate]);
  const shanghaiYears = useMemo(() => calcYTF(SHANGHAI_MONTHLY, fireNumber, rate), [fireNumber, rate]);
  const yearsSaved    = shanghaiYears - yearsToFIRE;

  const workRef = WORK_REFS.find(c => c.id === workId);
  const fireRef = FIRE_REFS.find(c => c.id === fireId);

  function applyWork(id: string) {
    const ref = WORK_REFS.find(c => c.id === id);
    if (!ref) return;
    setWorkId(id);
    setSalary(ref.salaryCNY);
    setWorkLiving(ref.livingCNY);
  }

  function applyFire(id: string) {
    const ref = FIRE_REFS.find(c => c.id === id);
    if (!ref) return;
    setFireId(id);
    setFireLiving(ref.monthlyCNY);
  }

  return (
    <div className="border-2 border-stone-900 bg-white overflow-hidden font-sans">

      {/* ── 1. Header ── */}
      <div className="bg-stone-900 px-5 py-4 flex items-center justify-between">
        <div>
          <div className="text-white font-serif font-black text-lg">出逃路线</div>
          <div className="text-stone-400 text-xs mt-0.5">在哪挣，去哪躺</div>
        </div>
        <div className="flex gap-1 bg-stone-800 p-0.5 rounded-lg">
          {RATES.map((r, i) => (
            <button key={r.label} onClick={() => setRateIdx(i)}
              className={`text-xs px-2.5 py-1.5 rounded-md font-medium transition-colors ${
                rateIdx === i ? "bg-white text-stone-900" : "text-stone-400 hover:text-stone-200"
              }`}>
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── 2. Work city chips ── */}
      <div className="px-5 pt-4 pb-3 border-b border-stone-100">
        <div className="space-y-2.5">
          {(["open", "skilled", "elite"] as const).map(level => {
            const cities = WORK_REFS.filter(c => c.access === level);
            const label = level === "open" ? "✅ 现在就能申" : level === "skilled" ? "⚠️ 需要技能或雇主" : "🔒 高竞争高门槛";
            const labelColor = level === "open" ? "text-emerald-700" : level === "skilled" ? "text-amber-600" : "text-stone-400";
            return (
              <div key={level}>
                <div className={`text-xs font-medium mb-1.5 ${labelColor}`}>{label}</div>
                <div className="flex gap-1.5 overflow-x-auto pb-0.5 scrollbar-none">
                  {cities.map(c => {
                    const active = c.id === workId;
                    const savings = c.salaryCNY - c.livingCNY;
                    return (
                      <button key={c.id} onClick={() => applyWork(c.id)}
                        className={`flex-none flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium transition-all whitespace-nowrap ${
                          active
                            ? "bg-stone-900 border-stone-900 text-white"
                            : level === "open"
                              ? "bg-emerald-50 border-emerald-200 text-emerald-800 hover:border-emerald-400"
                              : level === "skilled"
                                ? "bg-white border-amber-200 text-stone-600 hover:border-amber-400"
                                : "bg-white border-stone-200 text-stone-400 hover:border-stone-400"
                        }`}>
                        <span>{c.flag}</span>
                        <span>{c.name}</span>
                        {!active && (
                          <span className={level === "open" ? "text-emerald-600" : "text-stone-400"}>
                            {fmtCNY(savings)}
                          </span>
                        )}
                        {"accessLabel" in c && !active && (
                          <span className="text-emerald-500 text-xs">·{c.accessLabel}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── 3. Hero ── */}
      <div className="px-5 pt-8 pb-6 text-center border-b border-stone-100">
        <div className="text-xs text-stone-400 tracking-widest uppercase mb-1">坚持投资</div>
        <div className="flex items-end justify-center gap-1 leading-none">
          <span className="font-serif font-black text-stone-900 tabular-nums"
            style={{ fontSize: "clamp(4.5rem, 20vw, 7rem)" }}>
            {yearsToFIRE > 50 ? "50+" : yearsToFIRE <= 0 ? "0" : yearsToFIRE.toFixed(1)}
          </span>
          <div className="flex flex-col items-start pb-2.5 gap-0.5">
            <span className="font-serif font-bold text-stone-400 text-2xl leading-none">年</span>
            <span className="text-sm text-stone-400 leading-none">就够了</span>
          </div>
        </div>
        <p className="text-stone-500 text-sm mt-3">
          每月存 <strong className="text-stone-800">{fmtCNY(monthlySavings)}</strong>
          ，去 <strong className="text-emerald-700">{fireRef?.name ?? "退休地"}</strong> 永远不工作
        </p>
        <div className="flex justify-center gap-5 mt-3 text-xs text-stone-400">
          <span>FIRE 目标 <strong className="text-stone-600">{fmtCNY(fireNumber)}</strong></span>
          <span className="text-stone-200">·</span>
          <span>月消费 × 300</span>
        </div>
      </div>

      {/* ── 4. Work sliders ── */}
      <div className="px-5 py-5 space-y-5 border-b border-stone-100">

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-stone-500">打工月薪（税后，折算人民币）</span>
            <span className="text-base font-black text-stone-900 tabular-nums">{fmtCNY(salary)}</span>
          </div>
          <Track value={salary} min={1000} max={80000} step={500} onChange={setSalary} accent="#1c1917" />
          <div className="flex justify-between text-xs text-stone-300 mt-1"><span>¥1,000</span><span>¥8万</span></div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-stone-500">在当地每月花掉</span>
            <span className="text-sm font-semibold text-stone-500 tabular-nums">− {fmtCNY(workLiving)}</span>
          </div>
          <Track value={workLiving} min={500} max={50000} step={500} onChange={setWorkLiving} accent="#a8a29e" />
          <div className="flex justify-between text-xs text-stone-300 mt-1"><span>¥500</span><span>¥5万</span></div>
        </div>

        <div className="flex items-center justify-between px-4 py-3 rounded-lg bg-stone-50 border border-stone-200">
          <span className="text-sm text-stone-600">每月可存 / 投资</span>
          <span className={`text-xl font-black tabular-nums ${monthlySavings > 0 ? "text-emerald-700" : "text-red-600"}`}>
            {monthlySavings > 0 ? `${fmtCNY(monthlySavings)}/月` : "入不敷出"}
          </span>
        </div>

        {workId === "cruise" && (
          <div className="text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2.5 border border-amber-200 leading-relaxed">
            🚢 邮轮合同每次6–10个月，结束后回家休假2–3个月。<br />
            休假期间没有收入，但也几乎没有硬性支出——这里显示的是在船期间的存钱速度。<br />
            年有效储蓄率约是显示数字的 75%。
          </div>
        )}

      </div>

      {/* ── 5. FIRE city chips ── */}
      <div className="px-5 pt-4 pb-3 border-b border-stone-100">
        <div className="text-xs text-stone-400 mb-2">退休城市参考 <span className="text-stone-300">· 点击填入月消费</span></div>
        <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-none">
          {FIRE_REFS.map(c => {
            const active = c.id === fireId;
            return (
              <button key={c.id} onClick={() => applyFire(c.id)}
                className={`flex-none flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium transition-all whitespace-nowrap ${
                  active
                    ? c.easter
                      ? "bg-emerald-700 border-emerald-700 text-white"
                      : "bg-stone-900 border-stone-900 text-white"
                    : "bg-white border-stone-200 text-stone-600 hover:border-stone-400"
                }`}>
                <span>{c.flag}</span>
                <span>{c.name}</span>
                {!active && <span className="text-stone-400">{fmtCNY(c.monthlyCNY)}</span>}
                {c.japan && !active && <span className="text-amber-500 text-xs">↓日元</span>}
                {c.easter && !active && <span className="text-emerald-600 text-xs">免签</span>}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── 6. FIRE slider ── */}
      <div className="px-5 py-5 border-b border-stone-100">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-stone-500">退休月消费（在 {fireRef?.name ?? "退休地"}）</span>
          <span className="text-base font-black text-stone-900 tabular-nums">{fmtCNY(fireLiving)}/月</span>
        </div>
        <Track value={fireLiving} min={1000} max={20000} step={500} onChange={setFireLiving} accent="#15803d" />
        <div className="flex justify-between text-xs text-stone-300 mt-1"><span>¥1,000</span><span>¥2万</span></div>
        {fireRef?.note && (
          <p className="text-xs text-stone-400 mt-2">{fireRef.note}</p>
        )}
        {fireRef?.easter && (
          <p className="text-xs text-emerald-700 mt-2">🎉 不是笔误——格鲁吉亚真的对中国护照免签365天。</p>
        )}
        {fireRef?.japan && (
          <p className="text-xs text-amber-600 mt-2">⏰ 日元弱势期间的价格，窗口不会一直开着。</p>
        )}
      </div>

      {/* ── 7. Math breakdown ── */}
      {yearsToFIRE < 50 && monthlySavings > 0 && (() => {
        const months       = yearsToFIRE * 12;
        const linearSaved  = monthlySavings * months;
        const compoundBonus = fireNumber - linearSaved;
        const annualGrowth  = fireNumber * rate / 100;
        const annualDraw    = fireLiving * 12;
        const netGrowth     = annualGrowth - annualDraw;
        return (
          <div className="px-5 py-5 border-b border-stone-100 space-y-4">
            <div className="text-xs font-semibold text-stone-400 tracking-widest uppercase">数学课</div>

            {/* Accumulation */}
            <div>
              <div className="text-xs text-stone-500 mb-2">
                <span className="font-semibold text-stone-700">积累期</span>
                {" · "}工作 {yearsToFIRE.toFixed(1)} 年（{Math.round(months)} 个月）
              </div>
              <div className="rounded-xl border border-stone-100 overflow-hidden text-xs">
                <div className="flex justify-between px-4 py-2.5 bg-stone-50">
                  <span className="text-stone-500">每月存入 × {Math.round(months)} 个月</span>
                  <span className="font-mono text-stone-700">{fmtCNY(linearSaved)}</span>
                </div>
                <div className="flex justify-between px-4 py-2.5 bg-emerald-50">
                  <span className="text-emerald-700">复利红利（{rate}% 年化）</span>
                  <span className="font-mono text-emerald-700">
                    {compoundBonus >= 0 ? "+" : ""}{fmtCNY(compoundBonus)}
                  </span>
                </div>
                <div className="flex justify-between px-4 py-3 bg-stone-900">
                  <span className="text-stone-300">存够 FIRE 目标</span>
                  <span className="font-mono font-bold text-white">{fmtCNY(fireNumber)}</span>
                </div>
              </div>
            </div>

            {/* Post-FIRE */}
            <div>
              <div className="text-xs text-stone-500 mb-2">
                <span className="font-semibold text-stone-700">停工后</span>
                {" · "}{fmtCNY(fireNumber)} 组合，{rate}% 增长 vs {fireLiving > 0 ? "4% 提取" : "—"}
              </div>
              <div className="rounded-xl border border-stone-100 overflow-hidden text-xs">
                <div className="flex justify-between px-4 py-2.5 bg-emerald-50">
                  <span className="text-emerald-700">组合每年增长 {rate}%</span>
                  <span className="font-mono text-emerald-700">+{fmtCNY(annualGrowth)}/年</span>
                </div>
                <div className="flex justify-between px-4 py-2.5 bg-red-50">
                  <span className="text-red-600">每年提取（4% 法则）</span>
                  <span className="font-mono text-red-600">−{fmtCNY(annualDraw)}/年</span>
                </div>
                <div className={`flex justify-between px-4 py-3 ${netGrowth >= 0 ? "bg-emerald-700" : "bg-amber-700"}`}>
                  <span className="text-white/80">净增长 / 年</span>
                  <span className="font-mono font-bold text-white">
                    {netGrowth >= 0 ? "+" : ""}{fmtCNY(netGrowth)} → 永远不会耗尽
                  </span>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── 8. Shanghai comparison ── */}
      <div className="px-5 py-4 border-b border-stone-100 bg-amber-50">
        <div className="text-xs text-stone-500 mb-2">
          对比：在上海原地打工（月薪¥8,000，拼命省也就存¥1,500），同样去{fireRef?.name ?? "这里"}
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-stone-600">
            需要 <strong className="text-stone-800">{shanghaiYears > 50 ? "50+ 年" : `${shanghaiYears.toFixed(1)} 年`}</strong>
          </span>
          {yearsSaved > 1 && yearsSaved < 100 && (
            <div className="text-right">
              <div className="text-xl font-black text-emerald-700">快 {Math.round(yearsSaved)} 年</div>
              <div className="text-xs text-stone-400">出逃的红利</div>
            </div>
          )}
          {yearsSaved <= 0 && (
            <span className="text-sm text-stone-400">跟在上海差不多</span>
          )}
        </div>
      </div>

      {/* ── 8. Visa note ── */}
      {workRef?.visaNote && (
        <div className="px-5 py-4 border-b border-stone-100">
          <div className="text-xs text-stone-400 mb-1">{workRef.flag} {workRef.name} 签证</div>
          <div className="text-xs text-stone-500 leading-relaxed">{workRef.visaNote}</div>
        </div>
      )}

      {/* ── 9. Footnote ── */}
      <div className="px-5 py-3">
        <p className="text-xs text-stone-300 leading-relaxed">
          薪资数据核对于 {FX_DATE}，汇率：NZD {FX.NZD} · AUD {FX.AUD} · JPY {FX.JPY} · SGD {FX.SGD} · AED {FX.AED} · GBP {FX.GBP}。汇率波动时数字会偏，仅供参考。4%法则来自Trinity Study。不构成签证或财务建议。
        </p>
      </div>

      {/* ── 10. CTA ── */}
      <Link href="/tools/compound"
        className="flex items-center justify-between px-5 py-4 border-t-2 border-stone-100 hover:bg-stone-50 transition-colors group">
        <div>
          <div className="text-sm font-semibold text-stone-700 group-hover:text-stone-900">精确算你的 FIRE 年数</div>
          <div className="text-xs text-stone-400 mt-0.5">调整收入、投资比例、退休消费</div>
        </div>
        <span className="text-stone-400 group-hover:text-stone-600 text-sm font-mono">→</span>
      </Link>

    </div>
  );
}
