"use client";

import Link from "next/link";
import { useState } from "react";
import type { CompanyClassify, TypeCard } from "@/app/discover/[code]/page";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5001";

export function ClassifyStep({ initial }: { initial: CompanyClassify }) {
  const [picking, setPicking] = useState(false);
  const [chosen, setChosen] = useState<string | null>(initial.suggested_type);
  const [confirmed, setConfirmed] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const cardOf = (key: string | null): TypeCard | null =>
    key ? initial.options.find((o) => o.key === key) ?? initial.suggested : null;

  async function submit(type: string) {
    setSaving(true);
    try {
      await fetch(`${API}/api/public/company/${initial.code}/classify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type }),
      });
    } catch {
      /* 记录失败不阻塞体验 */
    }
    setConfirmed(type);
    setSaving(false);
  }

  const confirmedCard = confirmed ? cardOf(confirmed) : null;

  return (
    <div className="mt-4">
      {/* 步骤标题 */}
      <div className="text-xs font-medium text-amber-600 tracking-wide">
        第 1 步 · 看懂生意
      </div>
      <h1 className="mt-1 text-2xl font-bold text-stone-800">
        {initial.name}
        <span className="ml-2 text-sm font-normal text-stone-400">
          {initial.code} · {initial.market?.toUpperCase()}
        </span>
      </h1>
      <p className="mt-1 text-stone-500">这是一门什么生意？</p>

      {/* 已确认态 */}
      {confirmedCard ? (
        <div className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
          <div className="text-sm text-emerald-700">已记录 ✓ 你把它看作</div>
          <div className="mt-1 text-xl font-bold text-stone-800">
            {confirmedCard.label}
          </div>
          <div className="mt-2 text-stone-600">{confirmedCard.biz}</div>
          <div className="mt-3 rounded-lg bg-white/70 p-3 text-sm text-stone-700">
            <span className="font-medium">所以要这样看它：</span>
            {confirmedCard.how}
          </div>
          <Link
            href={`/discover/${initial.code}/business`}
            className="mt-5 inline-flex items-center gap-1 rounded-full bg-stone-800 px-5 py-2.5 text-sm font-medium text-white hover:bg-stone-700"
          >
            下一步：它靠什么赚钱 →
          </Link>
        </div>
      ) : (
        <>
          {/* 建议 + 确认/改选 */}
          {initial.suggested && !picking && (
            <div className="mt-6 rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
              <div className="text-sm text-stone-500">我们看它像</div>
              <div className="mt-1 text-xl font-bold text-stone-800">
                {initial.suggested.label}
              </div>
              <div className="mt-2 text-stone-600">{initial.suggested.biz}</div>
              <div className="mt-3 rounded-lg bg-stone-50 p-3 text-sm text-stone-600">
                {initial.suggested.how}
              </div>
              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  disabled={saving}
                  onClick={() => submit(initial.suggested_type!)}
                  className="rounded-full bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                >
                  对，就是这类
                </button>
                <button
                  onClick={() => setPicking(true)}
                  className="rounded-full border border-stone-300 px-5 py-2.5 text-sm text-stone-600 hover:border-stone-400"
                >
                  其实是别的…
                </button>
              </div>
            </div>
          )}

          {/* 选择态：没有建议、或用户点了"其实是别的" */}
          {(picking || !initial.suggested) && (
            <div className="mt-6">
              <div className="text-sm text-stone-500">
                {initial.suggested ? "那你觉得它是哪种生意？" : "帮我们判断一下——它是哪种生意？"}
              </div>
              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {initial.options.map((o) => (
                  <button
                    key={o.key}
                    onClick={() => setChosen(o.key)}
                    className={`rounded-xl border p-3 text-left transition ${
                      chosen === o.key
                        ? "border-emerald-400 bg-emerald-50"
                        : "border-stone-200 bg-white hover:border-stone-300"
                    }`}
                  >
                    <div className="font-medium text-stone-800">{o.label}</div>
                    <div className="mt-0.5 text-xs text-stone-500">{o.biz}</div>
                  </button>
                ))}
              </div>
              <button
                disabled={!chosen || saving}
                onClick={() => chosen && submit(chosen)}
                className="mt-4 rounded-full bg-stone-800 px-5 py-2.5 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40"
              >
                就选它
              </button>
            </div>
          )}
        </>
      )}

      {/* 教学脚注 */}
      <p className="mt-8 border-t border-stone-200 pt-4 text-sm text-stone-500">
        为什么先分类？不同生意，好坏的看法完全不同——银行看坏账、软件看增长、周期股别在利润高点追。
        先搞清是哪一种，后面才不会用错尺子。
      </p>
    </div>
  );
}
