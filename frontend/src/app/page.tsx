import { Navbar } from "@/components/Navbar";
import Link from "next/link";
import { PollGame } from "@/components/PollGame";
import { CompoundMini } from "@/components/CompoundMini";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5001";

interface Article {
  id: number;
  code: string;
  stock_name: string;
  market: string;
  grade: string;
  conclusion: string;
  reasoning: string;
  analysis_date: string;
}

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

async function getFeed(): Promise<Article[]> {
  try {
    const res = await fetch(`${API}/api/public/feed`, { next: { revalidate: 3600 } });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

async function getPoll(): Promise<Poll | null> {
  try {
    const res = await fetch(`${API}/api/public/poll/today`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function gradeColor(grade: string) {
  const g = (grade || "").toUpperCase();
  if (g.startsWith("A")) return "text-emerald-700 bg-emerald-50 border-emerald-200";
  if (g.startsWith("B")) return "text-sky-700 bg-sky-50 border-sky-200";
  if (g.startsWith("C")) return "text-amber-700 bg-amber-50 border-amber-200";
  return "text-rose-700 bg-rose-50 border-rose-200";
}

function today() {
  return new Date().toLocaleDateString("zh-CN", {
    year: "numeric", month: "long", day: "numeric", weekday: "long",
  });
}

export default async function HomePage() {
  const [articles, poll] = await Promise.all([getFeed(), getPoll()]);
  const featured = articles[0] ?? null;
  const rest = articles.slice(1);

  return (
    <div className="min-h-screen bg-stone-50">
      <Navbar />

      {/* 报头 */}
      <header className="border-b-2 border-stone-900 bg-white">
        <div className="max-w-4xl mx-auto px-4 py-6 text-center">
          <h1 className="font-serif text-4xl md:text-5xl text-stone-900 tracking-tight">
            预言家日报
          </h1>
          <p className="text-xs text-stone-400 mt-1 tracking-widest uppercase">
            SirenBuffet · 存活的风险 · {today()}
          </p>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">

        {/* 今日预言游戏 */}
        {poll && <PollGame poll={poll} apiBase={API} />}

        {/* 复利小游戏 */}
        <section className="mb-10">
          <div className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
            复利的奇迹
          </div>
          <CompoundMini />
        </section>

        {articles.length === 0 ? (
          /* 空态 */
          <div className="text-center py-20 text-stone-400">
            <p className="text-lg font-serif">暂无公开分析</p>
            <p className="text-sm mt-2">管理员发布后将显示在这里</p>
          </div>
        ) : (
          <>
            {/* 今日精选 */}
            {featured && (
              <section className="mb-10">
                <div className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
                  今日精选
                </div>
                <Link href={`/blog/${featured.code}`} className="block group">
                  <div className="bg-white border border-stone-200 rounded-lg p-6 hover:shadow-md transition-shadow">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <h2 className="font-serif text-2xl text-stone-900 group-hover:text-stone-600 transition-colors leading-snug">
                          {featured.stock_name}
                          <span className="text-stone-400 text-base font-sans ml-2">{featured.code}</span>
                        </h2>
                        <p className="text-stone-600 mt-2 text-sm leading-relaxed line-clamp-3">
                          {featured.reasoning || featured.conclusion}
                        </p>
                        <p className="text-xs text-stone-400 mt-3">{featured.analysis_date}</p>
                      </div>
                      <div className={`shrink-0 text-center px-3 py-2 border rounded-lg text-lg font-bold font-serif ${gradeColor(featured.grade)}`}>
                        {featured.grade || "—"}
                      </div>
                    </div>
                    <div className="mt-4 pt-4 border-t border-stone-100 text-sm text-stone-700 italic">
                      &ldquo;{featured.conclusion}&rdquo;
                    </div>
                  </div>
                </Link>
              </section>
            )}

            {/* 近期分析 */}
            {rest.length > 0 && (
              <section>
                <div className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
                  近期分析
                </div>
                <div className="divide-y divide-stone-100 bg-white border border-stone-200 rounded-lg overflow-hidden">
                  {rest.map((a) => (
                    <Link key={a.id} href={`/blog/${a.code}`}
                      className="flex items-center gap-4 px-5 py-4 hover:bg-stone-50 transition-colors group">
                      <span className={`shrink-0 w-8 text-center text-sm font-bold font-serif border rounded px-1 ${gradeColor(a.grade)}`}>
                        {a.grade || "—"}
                      </span>
                      <div className="flex-1 min-w-0">
                        <span className="font-medium text-stone-800 group-hover:text-stone-600">
                          {a.stock_name}
                        </span>
                        <span className="text-stone-400 text-xs ml-2">{a.code}</span>
                        <p className="text-xs text-stone-500 mt-0.5 truncate">{a.conclusion}</p>
                      </div>
                      <span className="shrink-0 text-xs text-stone-400">{a.analysis_date}</span>
                    </Link>
                  ))}
                </div>
              </section>
            )}
          </>
        )}

        {/* CTA */}
        <div className="mt-12 text-center border-t border-stone-200 pt-8">
          <p className="text-stone-500 text-sm mb-4">想分析你自己关注的股票？</p>
          <Link href="/register"
            className="inline-block px-6 py-2.5 bg-stone-900 text-white text-sm rounded hover:bg-stone-700 transition-colors">
            免费注册，开始分析
          </Link>
        </div>
      </main>

      {/* 页脚 */}
      <footer className="border-t border-stone-200 mt-12 py-6 text-center">
        <p className="text-xs text-stone-400">
          本站内容为教育用途，不构成投资建议。投资有风险，决策需谨慎。
        </p>
        <p className="text-xs text-stone-300 mt-1">
          SirenBuffet · 私人芭菲特工 · 2026
        </p>
      </footer>
    </div>
  );
}
