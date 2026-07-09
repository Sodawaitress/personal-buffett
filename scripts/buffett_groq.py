import time

import requests

from scripts.config import GROQ_API_KEY
from scripts.groq_ratelimit import throttle

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"


def _retry_after_seconds(resp) -> float:
    """从 429 响应头算等待秒数：优先 retry-after，其次 token/请求 reset。兜底 30s。"""
    for header in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        raw = resp.headers.get(header)
        if not raw:
            continue
        try:
            return max(float(raw), 1.0) + 2
        except (TypeError, ValueError):
            # 形如 "1m26.4s" / "185ms"
            secs, num = 0.0, ""
            for ch in raw:
                if ch.isdigit() or ch == ".":
                    num += ch
                elif ch == "m" and num:
                    secs += float(num) * 60; num = ""
                elif ch == "s" and num:
                    secs += float(num); num = ""
            if secs:
                return secs + 2
    return 30.0


def _call_groq(system: str, user_msg: str, max_tokens: int = 300) -> str:
    if not GROQ_API_KEY:
        return ""

    # 主动配速：按 TPM 12,000 精确投放，绝大多数情况下根本不会撞 429。
    waited = throttle(system, user_msg, max_tokens)
    if waited > 1:
        print(f"    ⏳ 配速等待 {waited:.1f}s（TPM 预算）")

    req_timeout = 90 if max_tokens > 500 else 45
    for attempt in range(3):
        try:
            resp = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.25,
                },
                timeout=req_timeout,
            )
            # 429 是配速兜底（估算偏差时才触发），按响应头精确等待，不再盲睡 65s。
            if resp.status_code == 429:
                if attempt >= 2:
                    print("    ⚠️ Groq 限流重试耗尽，切换备用方案")
                    return ""
                wait = _retry_after_seconds(resp)
                print(f"    ⏳ Groq 限流兜底，等待 {wait:.1f}s 后重试（第{attempt+1}次）...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage", {})
            if usage:
                print(
                    f"    📊 Groq token用量: 输入{usage.get('prompt_tokens','?')} + "
                    f"输出{usage.get('completion_tokens','?')} = {usage.get('total_tokens','?')}"
                )
            return data["choices"][0]["message"]["content"].strip()
        except requests.Timeout:
            wait = (attempt + 1) * 5
            print(f"    ⏳ Groq 超时，等待 {wait}s 后重试（第{attempt+1}次）...")
            time.sleep(wait)
        except Exception as e:
            print(f"    ⚠️ Groq 错误（不重试）: {e}")
            return ""
    print("    ⚠️ Groq 重试3次失败，切换备用方案")
    return ""
