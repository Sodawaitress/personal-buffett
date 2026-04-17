"""Shared parsing helpers for Buffett analysis outputs."""

import json
import re

TRADE_KEYS = ("当前位置", "减仓区间", "买入区间1", "买入区间2", "止损位", "仓位策略", "关键监控")


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
