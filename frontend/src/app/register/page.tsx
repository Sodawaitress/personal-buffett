"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AuthCard } from "@/components/auth/AuthCard";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrors({});
    if (password !== confirm) { setErrors({ confirm_password: "Passwords don't match." }); return; }
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password, confirm_password: confirm }),
      });
      const data = await res.json();
      if (data.ok) {
        router.push("/");
      } else {
        setErrors(data.errors ?? { email: "Registration failed." });
      }
    } catch {
      setErrors({ email: "Network error. Please try again." });
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthCard>
      <h2 className="text-lg font-semibold text-stone-800 mb-1">Create account</h2>
      <p className="text-sm text-stone-500 mb-6">Start your value investing journey</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-stone-700 mb-1">Email</label>
          <input
            type="email"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={`w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-2 focus:ring-stone-400 ${errors.email ? "border-red-400" : "border-stone-300"}`}
            placeholder="you@example.com"
          />
          {errors.email && <p className="mt-1 text-xs text-red-600">{errors.email}</p>}
        </div>

        <div>
          <label className="block text-sm font-medium text-stone-700 mb-1">Password</label>
          <div className="relative">
            <input
              type={showPw ? "text" : "password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={`w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-2 focus:ring-stone-400 pr-10 ${errors.password ? "border-red-400" : "border-stone-300"}`}
              placeholder="8+ characters"
            />
            <button type="button" onClick={() => setShowPw(!showPw)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-600 text-xs">
              {showPw ? "Hide" : "Show"}
            </button>
          </div>
          {errors.password && <p className="mt-1 text-xs text-red-600">{errors.password}</p>}
          <p className="mt-1 text-xs text-stone-400">Uppercase, lowercase, and a number required</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-stone-700 mb-1">Confirm password</label>
          <input
            type={showPw ? "text" : "password"}
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className={`w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-2 focus:ring-stone-400 ${errors.confirm_password ? "border-red-400" : "border-stone-300"}`}
          />
          {errors.confirm_password && <p className="mt-1 text-xs text-red-600">{errors.confirm_password}</p>}
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full py-2 bg-stone-900 text-white text-sm rounded hover:bg-stone-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-stone-500">
        Already have an account?{" "}
        <Link href="/login" className="text-stone-800 font-medium hover:underline">Sign in</Link>
      </p>
    </AuthCard>
  );
}
