"use client";

import { useState } from "react";
import Link from "next/link";
import { AuthCard } from "@/components/auth/AuthCard";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await fetch(`${API}/api/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
    } finally {
      setSent(true);
      setLoading(false);
    }
  }

  return (
    <AuthCard>
      <h2 className="text-lg font-semibold text-stone-800 mb-1">Forgot password?</h2>
      <p className="text-sm text-stone-500 mb-6">Enter your email and we'll send a reset link.</p>

      {sent ? (
        <div className="text-center">
          <div className="mb-4 p-4 bg-green-50 text-green-700 text-sm rounded">
            If that email is registered, a reset link is on its way.
          </div>
          <Link href="/login" className="text-sm text-stone-500 hover:text-stone-800">
            ← Back to login
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1">Email</label>
            <input
              type="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 border border-stone-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-stone-400"
              placeholder="you@example.com"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-stone-900 text-white text-sm rounded hover:bg-stone-700 disabled:opacity-50 transition-colors"
          >
            {loading ? "Sending…" : "Send reset link"}
          </button>
          <p className="text-center text-sm text-stone-500">
            <Link href="/login" className="hover:text-stone-800">← Back to login</Link>
          </p>
        </form>
      )}
    </AuthCard>
  );
}
