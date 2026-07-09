"""Groq 配速器。

实测限速（2026-07-09，llama-3.3-70b-versatile 免费档）：RPM 1000 / TPM 12,000。
瓶颈是 TPM。此模块按 token 精确配速，替掉旧的「撞 429 空睡 65s」。
线程安全，为未来微服务并发调用预留。
"""
import threading
import time

TPM_LIMIT = 12_000
RPM_LIMIT = 1_000
_SAFETY = 0.90  # 只用 90% 额度，留头寸给估算误差 + 其它并发调用


def estimate_tokens(system: str, user_msg: str, max_tokens: int) -> int:
    """粗估一次请求的 token 消耗。中英混合按 chars/3（偏高估——宁可略慢也别撞 429）。
    prompt = (system + user) 字符数 / 3；completion 按 max_tokens 满额预留。"""
    prompt_chars = len(system) + len(user_msg)
    prompt_tok = prompt_chars // 3 + 8  # +8：消息结构固定开销
    return prompt_tok + max_tokens


class _Bucket:
    """连续补充的令牌桶：容量 = 每分钟额度，补充速率 = 额度/60 每秒。"""

    def __init__(self, per_min: float):
        self.rate = per_min / 60.0
        self.capacity = float(per_min)
        self.tokens = float(per_min)
        self.updated = time.monotonic()
        self.lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now

    def acquire(self, n: float) -> float:
        """扣 n 个令牌，不够就 sleep 到够。返回实际等待秒数。n 超过容量则截到容量。"""
        n = min(float(n), self.capacity)
        waited = 0.0
        while True:
            with self.lock:
                self._refill()
                if self.tokens >= n:
                    self.tokens -= n
                    return waited
                wait = (n - self.tokens) / self.rate
            time.sleep(wait)
            waited += wait


_tpm = _Bucket(TPM_LIMIT * _SAFETY)
_rpm = _Bucket(RPM_LIMIT * _SAFETY)


def throttle(system: str, user_msg: str, max_tokens: int) -> float:
    """调用 Groq 前阻塞到配额允许。返回等待秒数（供日志）。"""
    est = estimate_tokens(system, user_msg, max_tokens)
    waited = _tpm.acquire(est)
    waited += _rpm.acquire(1)
    return waited
