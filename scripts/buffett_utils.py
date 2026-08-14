"""Shared parsing helpers for Buffett analysis outputs."""

import json
import re

TRADE_KEYS = ("当前位置", "减仓区间", "买入区间1", "买入区间2", "止损位", "仓位策略", "关键监控")

# 句末边界。中文标点直接算；英文句点必须后跟空白或结尾，否则
# 「PB倍数达到43.6x」里的小数点会被当成句末，把数字切成两半。
_SENTENCE_END_RE = re.compile(r"[。！？!?…]|\.(?=\s|$)")


def summarize_to_sentence(text: str, limit: int = 200) -> str:
    """把长文截成不超过 limit 字的摘要，且**只在句子边界断开**（US-152）。

    原来是 `letter_text[:200]` 硬切。08-14 快照实测：210 只里 44 只的
    reasoning 长度正好卡在 200 且停在半句上，例如 AAPL 的
    「…在技术行业中的竞争优势。\\n\\n基于以上，」——妈妈读到的就是这个半句。

    策略：在 limit 内找最后一个句末标点，从那里断。若 limit 内的句号太靠前
    （不到一半，说明后面是个长句），退回硬切并加省略号，至少显式表示没说完。
    """
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text

    window = text[:limit]
    ends = [m.end() for m in _SENTENCE_END_RE.finditer(window)]
    # 比的是「切完剩多长」，不是标点的下标——差一会把刚好半长的合法切点判掉
    if ends and ends[-1] >= limit // 2:
        return window[: ends[-1]].strip()
    return window.rstrip() + "…"


def parse_trade_block(raw: str):
    if not raw or "===TRADE===" not in raw or "===TRADE_END===" not in raw:
        return None
    try:
        trade_raw = raw.split("===TRADE===")[1].split("===TRADE_END===")[0].strip()
        trade_lines = {}
        for line in trade_raw.splitlines():
            line = line.strip()
            if not line:
                continue
            for key in TRADE_KEYS:
                if line.startswith(key + "：") or line.startswith(key + ":"):
                    trade_lines[key] = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                    break
        if trade_lines:
            return json.dumps(trade_lines, ensure_ascii=False)
    except Exception:
        return None
    return None


def split_dims_output(raw: str):
    if not raw:
        return "", ""
    dims_match = re.search(r"===DIMS===(.*?)(?:===END===|$)", raw, re.DOTALL)
    if dims_match:
        dims_text = dims_match.group(1).strip()
        letter_text = raw[: dims_match.start()].strip()
    else:
        dims_text = ""
        letter_text = raw.strip()

    letter_lines = [line for line in letter_text.splitlines() if not re.match(r"\s*评级[：:]\s*[A-Z]", line)]
    return "\n".join(letter_lines).strip(), dims_text


def strip_trade_block(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"===TRADE===.*?===TRADE_END===", "", raw, flags=re.DOTALL).strip()


def parse_dim(key: str, text: str) -> str:
    match = re.search(rf"{key}[：:]\s*(.+)", text)
    return match.group(1).strip()[:60] if match else ""
