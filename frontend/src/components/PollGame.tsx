"use client";

import { useState } from "react";

interface Poll {
  id: number;
  poll_date: string;
  question: string;
  up_votes: number;
  down_votes: number;
  outcome: string | null;
  clue_1: string | null;
  clue_2: string | null;
  clue_3: string | null;
}

interface Props {
  poll: Poll;
  apiBase: string;
}

export function PollGame({ poll, apiBase }: Props) {
  const [upVotes, setUpVotes] = useState(poll.up_votes);
  const [downVotes, setDownVotes] = useState(poll.down_votes);
  const [voted, setVoted] = useState<"up" | "down" | null>(null);
  const [loading, setLoading] = useState(false);
  const [alreadyVoted, setAlreadyVoted] = useState(false);

  const total = upVotes + downVotes;
  const upPct = total > 0 ? Math.round((upVotes / total) * 100) : 50;
  const downPct = total > 0 ? 100 - upPct : 50;

  const clues = [poll.clue_1, poll.clue_2, poll.clue_3].filter(Boolean);
  const hasOutcome = !!poll.outcome;

  async function vote(direction: "up" | "down") {
    if (voted || alreadyVoted || loading) return;
    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/api/public/poll/vote`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ direction }),
      });
      if (res.status === 400) {
        setAlreadyVoted(true);
        return;
      }
      if (res.ok) {
        const data = await res.json();
        setUpVotes(data.up_votes);
        setDownVotes(data.down_votes);
        setVoted(direction);
      }
    } finally {
      setLoading(false);
    }
  }

  const showResult = voted !== null || alreadyVoted || hasOutcome;

  return (
    <section className="mb-10">
      <div className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
        今日预言
      </div>
      <div className="bg-white border border-stone-200 rounded-lg p-6">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h2 className="font-serif text-xl text-stone-900">
              {poll.question}
            </h2>
            <p className="text-xs text-stone-400 mt-1">
              读三则线索，落笔押注，七日后见分晓
            </p>
          </div>
          {hasOutcome && (
            <span className={`shrink-0 text-xs font-semibold px-2 py-1 rounded-full border ${
              poll.outcome === "up"
                ? "text-emerald-700 bg-emerald-50 border-emerald-200"
                : "text-rose-700 bg-rose-50 border-rose-200"
            }`}>
              {poll.outcome === "up" ? "↑ 涨了" : "↓ 跌了"}
            </span>
          )}
        </div>

        {/* 线索 */}
        {clues.length > 0 && (
          <div className="space-y-2 mb-5">
            {clues.map((clue, i) => (
              <div key={i} className="flex items-start gap-2 text-sm text-stone-600">
                <span className="shrink-0 font-mono text-stone-300 text-xs mt-0.5">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span>{clue}</span>
              </div>
            ))}
          </div>
        )}

        {/* 无线索时的占位说明 */}
        {clues.length === 0 && (
          <div className="mb-5 text-sm text-stone-400 italic">
            今日线索尚未发布，凭直觉押注也是一种艺术。
          </div>
        )}

        {/* 投票区 */}
        {!showResult ? (
          <div className="flex gap-3">
            <button
              onClick={() => vote("up")}
              disabled={loading}
              className="flex-1 py-2.5 border border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded font-medium text-sm transition-colors disabled:opacity-50"
            >
              ↑ 涨
            </button>
            <button
              onClick={() => vote("down")}
              disabled={loading}
              className="flex-1 py-2.5 border border-rose-200 text-rose-700 bg-rose-50 hover:bg-rose-100 rounded font-medium text-sm transition-colors disabled:opacity-50"
            >
              ↓ 跌
            </button>
          </div>
        ) : (
          <div>
            {alreadyVoted && !voted && (
              <p className="text-xs text-stone-400 mb-2">你今天已经投过票了。</p>
            )}
            {voted && (
              <p className="text-xs text-stone-400 mb-2">
                你押注了{voted === "up" ? "↑ 涨" : "↓ 跌"}。
              </p>
            )}
            {/* 进度条 */}
            <div className="flex h-2 rounded-full overflow-hidden mb-2">
              <div
                className="bg-emerald-400 transition-all duration-500"
                style={{ width: `${upPct}%` }}
              />
              <div
                className="bg-rose-400 transition-all duration-500"
                style={{ width: `${downPct}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-stone-500">
              <span>↑ 涨 {upPct}% ({upVotes}票)</span>
              <span>↓ 跌 {downPct}% ({downVotes}票)</span>
            </div>
          </div>
        )}

        {total > 0 && !showResult && (
          <p className="text-xs text-stone-300 mt-3 text-center">
            已有 {total} 人押注
          </p>
        )}
      </div>
    </section>
  );
}
