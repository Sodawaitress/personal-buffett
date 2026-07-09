/**
 * useCityData — 城市生活成本数据 Custom Hook
 *
 * 重难点：Custom Hook 的三个核心价值
 *   1. 逻辑复用：CompoundCalculator 和 CompoundMini 共用同一份 fetch + 解析逻辑
 *   2. 关注点分离：组件只管 UI，Hook 负责数据
 *   3. 可测试性：Hook 可以单独 mock，不依赖组件渲染
 *
 * 调用方式：
 *   const { major, lifestyle, reportYear, loading } = useCityData();
 */

"use client";

import { useState, useEffect } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5001";

// ── Static fallback（后端不可用时使用，数据来自 NBS 2025 + Numbeo）────────────
// 薪资：该城市"活得还不错"的参考下限（税后），不是平均数
// 目的是教育导向——即使挣得不多，坚持投资也能 FIRE
// 生活成本：市郊1居室 + 单人餐饮交通的基础版
const FALLBACK_CITIES: CityEntry[] = [
  { city_slug:"Shanghai",        city_name:"上海",    tier:"一线",    city_category:"major",     avg_monthly_salary:6000,  avg_monthly_cost:6000,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Beijing",         city_name:"北京",    tier:"一线",    city_category:"major",     avg_monthly_salary:6000,  avg_monthly_cost:6000,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Shenzhen",        city_name:"深圳",    tier:"一线",    city_category:"major",     avg_monthly_salary:6000,  avg_monthly_cost:5500,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Guangzhou",       city_name:"广州",    tier:"一线",    city_category:"major",     avg_monthly_salary:5000,  avg_monthly_cost:5000,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Hangzhou",        city_name:"杭州",    tier:"新一线",  city_category:"major",     avg_monthly_salary:5500,  avg_monthly_cost:4500,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Nanjing",         city_name:"南京",    tier:"新一线",  city_category:"major",     avg_monthly_salary:5000,  avg_monthly_cost:4000,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Suzhou",          city_name:"苏州",    tier:"新一线",  city_category:"major",     avg_monthly_salary:5000,  avg_monthly_cost:4000,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Chengdu",         city_name:"成都",    tier:"新一线",  city_category:"major",     avg_monthly_salary:4500,  avg_monthly_cost:3500,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Wuhan",           city_name:"武汉",    tier:"新一线",  city_category:"major",     avg_monthly_salary:4500,  avg_monthly_cost:3500,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Chongqing",       city_name:"重庆",    tier:"新一线",  city_category:"major",     avg_monthly_salary:4000,  avg_monthly_cost:3000,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Xian",            city_name:"西安",    tier:"二线",    city_category:"major",     avg_monthly_salary:4000,  avg_monthly_cost:3000,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Qingdao",         city_name:"青岛",    tier:"二线",    city_category:"major",     avg_monthly_salary:4000,  avg_monthly_cost:3500,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Changsha",        city_name:"长沙",    tier:"二线",    city_category:"major",     avg_monthly_salary:4000,  avg_monthly_cost:3000,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Kunming",         city_name:"昆明",    tier:"二线",    city_category:"major",     avg_monthly_salary:4000,  avg_monthly_cost:3000,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Xiamen",          city_name:"厦门",    tier:"二线",    city_category:"major",     avg_monthly_salary:5000,  avg_monthly_cost:4000,  source:"参考下限（教育用途）", report_year:2025, fetched_at:"" },
  { city_slug:"Dali-CN",         city_name:"大理",    tier:"躺平首选", city_category:"lifestyle", avg_monthly_salary:4000,  avg_monthly_cost:3000,  source:"云南统计公报 2025", report_year:2025, fetched_at:"" },
  { city_slug:"Lijiang-CN",      city_name:"丽江",    tier:"躺平首选", city_category:"lifestyle", avg_monthly_salary:3500,  avg_monthly_cost:2800,  source:"云南统计公报 2025", report_year:2025, fetched_at:"" },
  { city_slug:"Xishuangbanna-CN",city_name:"西双版纳", tier:"躺平首选", city_category:"lifestyle", avg_monthly_salary:3500,  avg_monthly_cost:2500,  source:"云南统计公报 2025", report_year:2025, fetched_at:"" },
  { city_slug:"Sanya-CN",        city_name:"三亚",    tier:"躺平首选", city_category:"lifestyle", avg_monthly_salary:5500,  avg_monthly_cost:5500,  source:"海南统计年鉴 2025", report_year:2025, fetched_at:"" },
];

function buildState(cities: CityEntry[], reportYear: number): CityDataState {
  return {
    major:      cities.filter(c => c.city_category === "major"),
    lifestyle:  cities.filter(c => c.city_category === "lifestyle"),
    all:        cities,
    reportYear,
    loading:    false,
  };
}

// ── Types ──────────────────────────────────────────────────────────────────────

/**
 * 重难点：TypeScript Discriminated Union
 *
 * city_category 是 "discriminant"（区分字段）。
 * TypeScript 能根据它自动收窄其他字段的类型。
 *
 * 例如：
 *   if (city.city_category === 'lifestyle') {
 *     // TS 在这里知道 city 是 LifestyleCity，source 一定是手动维护的字符串
 *   }
 */
export interface CityEntry {
  city_slug:          string;
  city_name:          string;
  tier:               string;
  city_category:      "major" | "lifestyle";
  avg_monthly_salary: number | null;
  avg_monthly_cost:   number | null;
  source:             string;
  report_year:        number | null;
  fetched_at:         string;
}

export interface CityDataState {
  major:      CityEntry[];   // 一线/二线大城市（Numbeo 数据）
  lifestyle:  CityEntry[];   // 躺平首选小城市（手动维护）
  all:        CityEntry[];   // 全部，便于 lookup
  reportYear: number;
  loading:    boolean;
}

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useCityData(): CityDataState {
  // 立即用 fallback 初始化，城市选择器不依赖后端
  const [state, setState] = useState<CityDataState>(
    () => buildState(FALLBACK_CITIES, 2025)
  );

  useEffect(() => {
    let cancelled = false;

    fetch(`${API}/api/public/city-data`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (cancelled || !data?.cities?.length) return;
        // 后端数据更新后覆盖 fallback（含 Numbeo 实时数值）
        setState(buildState(data.cities as CityEntry[], data.report_year ?? 2025));
      })
      .catch(() => { /* fallback 已在 state 里，静默失败 */ });

    return () => { cancelled = true; };
  }, []);

  return state;
}

// ── Helper ─────────────────────────────────────────────────────────────────────

/** 根据 slug 从列表里找城市 */
export function findCity(cities: CityEntry[], slug: string | null): CityEntry | null {
  if (!slug) return null;
  return cities.find(c => c.city_slug === slug) ?? null;
}

/**
 * 把城市数值四舍五入到 500 步长，符合滑块 step
 * 例：¥11,317 → ¥11,500
 */
export function snapToStep(value: number | null, step = 500): number | null {
  if (value === null) return null;
  return Math.round(value / step) * step;
}
