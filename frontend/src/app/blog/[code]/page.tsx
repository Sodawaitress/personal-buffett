import { Navbar } from "@/components/Navbar";
import Link from "next/link";
import { notFound } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5001";

interface Article {
  code: string;
  stock_name: string;
  market: string;
  industry: string;
  grade: string;
  conclusion: string;
  reasoning: string;
  letter_html: string;
  analysis_date: string;
  framework_used: string;
}

async function getArticle(code: string): Promise<Article | null> {
  try {
    const res = await fetch(`${API}/api/public/article/${code}`, {
      next: { revalidate: 3600 },
    });
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

export default async function ArticlePage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const article = await getArticle(code);
  if (!article) notFound();

  return (
    <div className="min-h-screen bg-stone-50">
      <Navbar />

      <main className="max-w-2xl mx-auto px-4 py-10">
        {/* 面包屑 */}
        <Link href="/" className="text-xs text-stone-400 hover:text-stone-600">
          ← 预言家日报
        </Link>

        {/* 文章头 */}
        <div className="mt-4 mb-8">
          <div className="flex items-center gap-3 mb-2">
            <span className={`text-sm font-bold font-serif border px-2 py-0.5 rounded ${gradeColor(article.grade)}`}>
              {article.grade || "—"}
            </span>
            <span className="text-xs text-stone-400 uppercase tracking-wide">{article.market} · {article.industry}</span>
          </div>
          <h1 className="font-serif text-3xl text-stone-900 leading-tight">
            {article.stock_name}
            <span className="text-stone-400 text-xl font-sans ml-2">{article.code}</span>
          </h1>
          <p className="text-stone-500 text-sm mt-2">{article.analysis_date}</p>
        </div>

        {/* 结论 */}
        <div className="bg-stone-100 border-l-4 border-stone-400 px-5 py-4 mb-8 rounded-r">
          <p className="text-stone-700 font-medium italic">"{article.conclusion}"</p>
        </div>

        {/* 巴菲特信正文 */}
        {article.letter_html ? (
          <article className="prose prose-stone max-w-none font-serif leading-relaxed">
            <div
              className="text-stone-800 leading-8 text-[15px]"
              dangerouslySetInnerHTML={{
                __html: article.letter_html.replace(/\n/g, "<br>"),
              }}
            />
          </article>
        ) : (
          <p className="text-stone-600 leading-8 font-serif">{article.reasoning}</p>
        )}

        {/* 免责声明 */}
        <div className="mt-12 pt-6 border-t border-stone-200 text-xs text-stone-400 leading-relaxed">
          本文为教育用途，基于公开信息由 AI 生成，不构成任何投资建议。
          投资有风险，请独立判断。数据截至 {article.analysis_date}。
        </div>

        {/* CTA */}
        <div className="mt-8 text-center">
          <p className="text-sm text-stone-500 mb-3">想分析你自己关注的股票？</p>
          <Link href="/register"
            className="inline-block px-5 py-2 bg-stone-900 text-white text-sm rounded hover:bg-stone-700 transition-colors">
            免费注册
          </Link>
        </div>
      </main>
    </div>
  );
}
