import time

import requests

from scripts.config import GROQ_API_KEY
from scripts.groq_ratelimit import throttle

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"

# 有时间预算的调用方（各 svc）在开跑前设一次；429 兜底要睡过这个点就直接放弃本次调用。
# 不设则维持原行为（睡满 Retry-After）。
# US-140：material scan 名义预算 20 分钟却跑成 60 分钟被 SIGKILL —— 因为预算只在
# 「每只之间」检查，而单只内部一次 429 就 sleep(452s)，闸门形同虚设。
_call_deadline = None


def set_call_deadline(ts: float = None) -> None:
    """ts = time.time() 时刻；None 清除。"""
    global _call_deadline
    _call_deadline = ts


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
    """返回正文。截断与否见 `last_finish_reason()`（US-152）。"""
    text, _ = call_groq_meta(system, user_msg, max_tokens)
    return text


# 最近一次调用的 finish_reason。Groq 撞 max_tokens 时是 "length"，
# 正常收尾是 "stop"。原来这个信号被整个丢掉，半句话的分析被当成完整结果
# 直接写进 DB —— 08-14 快照实测 210 只里有 70 只（33%）的 reasoning
# 停在半句上，例如 AAPL 停在「基于以上，」。
_LAST_FINISH_REASON = ""


def last_finish_reason() -> str:
    return _LAST_FINISH_REASON


def call_groq_meta(system: str, user_msg: str, max_tokens: int = 300):
    """同 _call_groq，但额外返回 finish_reason。

    返回 (text, finish_reason)。调用失败/无 key 时返回 ("", "")。
    """
    global _LAST_FINISH_REASON
    _LAST_FINISH_REASON = ""
    return _call_groq_impl(system, user_msg, max_tokens)


def _call_groq_impl(system: str, user_msg: str, max_tokens: int = 300):
    global _LAST_FINISH_REASON
    if not GROQ_API_KEY:
        return "", ""

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
                    return "", ""
                wait = _retry_after_seconds(resp)
                if _call_deadline and time.time() + wait > _call_deadline:
                    left = max(_call_deadline - time.time(), 0)
                    print(f"    ⏳ Groq 限流需等 {wait:.0f}s，但预算只剩 {left:.0f}s —— "
                          f"放弃本次调用（不拖过预算被 SIGKILL）")
                    return "", ""
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
            choice = (data.get("choices") or [{}])[0]
            _LAST_FINISH_REASON = choice.get("finish_reason", "") or ""
            if _LAST_FINISH_REASON == "length":
                print(f"    ✂️ Groq 撞 max_tokens={max_tokens} 被截断（finish_reason=length）")
            return choice.get("message", {}).get("content", "").strip(), _LAST_FINISH_REASON
        except requests.Timeout:
            wait = (attempt + 1) * 5
            print(f"    ⏳ Groq 超时，等待 {wait}s 后重试（第{attempt+1}次）...")
            time.sleep(wait)
        except Exception as e:
            print(f"    ⚠️ Groq 错误（不重试）: {e}")
            return "", ""
    print("    ⚠️ Groq 重试3次失败，切换备用方案")
    return "", ""
