import { Navbar } from "@/components/Navbar";
import { CompoundCalculator } from "@/components/CompoundCalculator";
import Link from "next/link";

export const metadata = {
  title: "复利计算器 · SirenBuffet",
  description: "用50/30/20法则规划月收入，看20年后的复利增值",
};

export default function CompoundPage() {
  return (
    <div className="min-h-screen bg-stone-50">
      <Navbar />

      <main className="max-w-2xl mx-auto px-4 py-8">
        {/* breadcrumb */}
        <Link href="/" className="text-xs text-stone-400 hover:text-stone-600">← 预言家日报</Link>

        <div className="mt-4">
          <CompoundCalculator />
        </div>
      </main>
    </div>
  );
}
