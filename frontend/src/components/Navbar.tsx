"use client";

import Link from "next/link";
import { useState, useEffect } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export function Navbar() {
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null);

  useEffect(() => {
    fetch(`${API}/api/me`, { credentials: "include" })
      .then((r) => r.json())
      .then((d) => setLoggedIn(!!d.user_id))
      .catch(() => setLoggedIn(false));
  }, []);

  return (
    <nav className="border-b border-stone-200 bg-white px-4 py-3 flex items-center justify-between">
      <Link href="/" className="font-serif text-lg text-stone-900 hover:opacity-80">
        SirenBuffet <span className="text-xs text-stone-400 font-sans">私人芭菲特工</span>
      </Link>
      <div className="flex items-center gap-3">
        {loggedIn === null ? null : loggedIn ? (
          <a href={`${API}/watchlist`} className="text-sm text-stone-600 hover:text-stone-900">
            我的选股 →
          </a>
        ) : (
          <>
            <Link href="/login" className="text-sm text-stone-500 hover:text-stone-800">
              登录
            </Link>
            <Link href="/register"
              className="text-sm px-3 py-1.5 bg-stone-900 text-white rounded hover:bg-stone-700 transition-colors">
              注册
            </Link>
          </>
        )}
      </div>
    </nav>
  );
}
