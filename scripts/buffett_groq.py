import time

import requests

from scripts.config import GROQ_API_KEY

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"


def _call_groq(system: str, user_msg: str, max_tokens: int = 300) -> str:
    if not GROQ_API_KEY:
        return ""

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
            if resp.status_code == 429:
                if attempt >= 2:
                    print("    ⚠️ Groq 限流重试耗尽，切换备用方案")
                    return ""
                retry_after = resp.headers.get("retry-after") or resp.headers.get("x-ratelimit-reset-tokens")
                try:
                    wait = max(int(float(retry_after)), 10) + 5
                except (TypeError, ValueError):
                    wait = 65
                limit_type = ""
                remaining_tokens = resp.headers.get("x-ratelimit-remaining-tokens", "?")
                remaining_reqs = resp.headers.get("x-ratelimit-remaining-requests", "?")
                if remaining_tokens == "0" or remaining_tokens == 0:
                    limit_type = " (TPM 耗尽)"
                elif remaining_reqs == "0" or remaining_reqs == 0:
                    limit_type = " (RPM 耗尽)"
                print(f"    ⏳ Groq 限流{limit_type}，等待 {wait}s 后重试（第{attempt+1}次）...")
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
