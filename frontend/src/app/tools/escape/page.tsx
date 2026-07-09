import { Navbar } from "@/components/Navbar";
import { EscapeCalculator } from "@/components/EscapeCalculator";
import Link from "next/link";

export const metadata = {
  title: "出逃路线：打份洋工，去哪躺平 · SirenBuffet",
  description: "在新加坡挣，去清迈躺——货币套利可以让 FIRE 快 20 年",
};

export default function EscapePage() {
  return (
    <div className="min-h-screen bg-stone-50">
      <Navbar />

      <main className="max-w-2xl mx-auto px-4 py-8">
        <Link href="/tools/compound" className="text-xs text-stone-400 hover:text-stone-600">
          ← 复利计算器
        </Link>

        <div className="mt-4">
          <EscapeCalculator />
        </div>
      </main>
    </div>
  );
}
