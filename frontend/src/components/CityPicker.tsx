"use client";

/**
 * CityPicker — 可复用的城市选择器
 *
 * 重难点：Controlled Component 模式
 *   value 和 onChange 由父组件控制——组件本身不存状态。
 *   这是 React 里"单向数据流"的标准实现：
 *     父组件持有 workCitySlug 状态 → 传给 CityPicker value
 *     用户点击 → CityPicker 调用 onChange → 父组件更新状态 → 重新渲染
 *
 * 这样设计的好处：两个 CityPicker（打工 + 退休）可以共享同一个组件，
 * 父组件决定各自的行为，组件本身保持"无脑"状态。
 */

import { CityEntry } from "@/hooks/useCityData";

interface Props {
  label:      string;
  hint?:      string;
  value:      string | null;     // 当前选中的 slug
  onChange:   (city: CityEntry | null) => void;
  major:      CityEntry[];
  lifestyle:  CityEntry[];
  reportYear: number;
  showLifestyle?: boolean;       // 退休城市才显示生活城市分组
}

const TIER_ORDER = ["一线", "新一线", "二线", "躺平首选"];

function tierColor(tier: string, active: boolean) {
  if (!active) return "bg-white text-stone-600 border-stone-200 hover:border-stone-400";
  if (tier === "一线")    return "bg-stone-900  text-white  border-stone-900";
  if (tier === "新一线")  return "bg-sky-700    text-white  border-sky-700";
  if (tier === "躺平首选") return "bg-emerald-700 text-white border-emerald-700";
  return "bg-stone-500 text-white border-stone-500";
}

function groupByTier(cities: CityEntry[]): Record<string, CityEntry[]> {
  return cities.reduce((acc, c) => {
    (acc[c.tier] ??= []).push(c);
    return acc;
  }, {} as Record<string, CityEntry[]>);
}

export function CityPicker({
  label, hint, value, onChange,
  major, lifestyle, reportYear, showLifestyle = false,
}: Props) {
  const all = showLifestyle ? [...major, ...lifestyle] : major;
  const grouped = groupByTier(all);
  const tiers = TIER_ORDER.filter(t => grouped[t]?.length);

  const selected = all.find(c => c.city_slug === value) ?? null;

  return (
    <div className="bg-stone-50 border border-stone-200 rounded-lg px-4 py-3 space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-xs font-semibold text-stone-700">{label}</span>
          {hint && <span className="text-xs text-stone-400 ml-2">{hint}</span>}
        </div>
        <span className="text-xs text-stone-300">
          数据来源：国家统计局 · Numbeo · {reportYear} 年
        </span>
      </div>

      {/* 城市按钮网格 */}
      {tiers.map(tier => (
        <div key={tier}>
          <div className="text-xs text-stone-400 mb-1">{tier}</div>
          <div className="flex flex-wrap gap-1.5">
            {grouped[tier].map(city => {
              const active = city.city_slug === value;
              return (
                <button
                  key={city.city_slug}
                  onClick={() => onChange(active ? null : city)}
                  title={[
                    city.avg_monthly_salary ? `月薪约 ¥${Math.round(city.avg_monthly_salary).toLocaleString()}` : null,
                    city.avg_monthly_cost   ? `生活成本约 ¥${Math.round(city.avg_monthly_cost).toLocaleString()}/月` : null,
                    `来源：${city.source ?? ""}`,
                  ].filter(Boolean).join("  |  ")}
                  className={`text-xs px-2.5 py-1 rounded border transition-all ${tierColor(city.tier, active)}`}
                >
                  {city.city_name}
                </button>
              );
            })}
          </div>
        </div>
      ))}

      {/* 选中后显示参考数值 */}
      {selected && (
        <p className="text-xs text-stone-500 leading-relaxed pt-1 border-t border-stone-100">
          <strong className="text-stone-700">{selected.city_name}</strong>
          {selected.avg_monthly_salary
            ? ` · 参考月薪 ¥${Math.round(selected.avg_monthly_salary).toLocaleString()}`
            : ""}
          {selected.avg_monthly_cost
            ? ` · 生活成本约 ¥${Math.round(selected.avg_monthly_cost).toLocaleString()}/月`
            : ""}
          <span className="text-stone-300 ml-1">（{selected.source ?? ""}）</span>
        </p>
      )}
    </div>
  );
}
