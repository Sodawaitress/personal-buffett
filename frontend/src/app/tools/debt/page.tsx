import { Navbar } from "@/components/Navbar";
import { DebtCalculator } from "@/components/DebtCalculator";
import Link from "next/link";

export const metadata = {
  title: "你替银行打了多少工 · SirenBuffet",
  description: "花呗、信用卡最低还款的真实代价——复利是把双刃刀",
};

export default function DebtPage() {
  return (
    <div className="min-h-screen bg-stone-50">
      <Navbar />

      <main className="max-w-2xl mx-auto px-4 py-8">
        <Link href="/tools/compound" className="text-xs text-stone-400 hover:text-stone-600">
          ← 复利计算器
        </Link>

        <div className="mt-4">
          <DebtCalculator />
        </div>
      </main>
    </div>
  );
}
