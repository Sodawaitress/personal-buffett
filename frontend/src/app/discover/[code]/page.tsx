import { Navbar } from "@/components/Navbar";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ClassifyStep } from "@/components/ClassifyStep";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5001";

export interface TypeCard {
  key: string;
  label: string;
  en: string;
  biz: string;
  how: string;
}

export interface CompanyClassify {
  code: string;
  name: string;
  market: string;
  suggested_type: string | null;
  suggested: TypeCard | null;
  options: TypeCard[];
}

async function getCompany(code: string): Promise<CompanyClassify | null> {
  try {
    const res = await fetch(`${API}/api/public/company/${code}`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function DiscoverPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  const data = await getCompany(code);
  if (!data) notFound();

  return (
    <div className="min-h-screen bg-stone-50">
      <Navbar />
      <main className="max-w-2xl mx-auto px-4 py-10">
        <Link href="/" className="text-xs text-stone-400 hover:text-stone-600">
          ← 首页
        </Link>
        <ClassifyStep initial={data} />
      </main>
    </div>
  );
}
