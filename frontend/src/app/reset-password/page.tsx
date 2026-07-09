"use client";

import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { AuthCard } from "@/components/auth/AuthCard";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

function ResetPasswordForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) { setError("Passwords don't match."); return; }
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password, confirm_password: confirm }),
      });
      const data = await res.json();
      if (data.ok) {
        router.push("/login?reset=1");
      } else {
        setError(data.error ?? "Something went wrong.");
      }
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <div className="text-center text-sm text-stone-500">
        Invalid link. <Link href="/forgot-password" className="underline">Request a new one</Link>.
      </div>
    );
  }

  return (
    <>
      <h2 className="text-lg font-semibold text-stone-800 mb-1">Set new password</h2>
      <p className="text-sm text-stone-500 mb-6">Must be 8+ characters with uppercase, lowercase, and a number.</p>

      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-stone-700 mb-1">New password</label>
          <div className="relative">
            <input
              type={showPw ? "text" : "password"}
              required
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 border border-stone-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-stone-400 pr-10"
            />
            <button type="button" onClick={() => setShowPw(!showPw)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-600 text-xs">
              {showPw ? "Hide" : "Show"}
            </button>
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-stone-700 mb-1">Confirm password</label>
          <input
            type={showPw ? "text" : "password"}
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="w-full px-3 py-2 border border-stone-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-stone-400"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2 bg-stone-900 text-white text-sm rounded hover:bg-stone-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "Updating…" : "Update password"}
        </button>
      </form>
    </>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthCard>
      <Suspense fallback={<div className="text-sm text-stone-500">Loading…</div>}>
        <ResetPasswordForm />
      </Suspense>
    </AuthCard>
  );
}
