"""Human-readable financial metric explanations."""


def compute_metric_hints(lat, signals, pe_current, price, locale='zh'):
    """
    US-66: 为每个财务指标生成一句人话解读。
    返回 {metric: {'text': str, 'level': 'good'|'ok'|'warn'}}
    纯规则引擎，无 LLM，不报错。
    """
    hints = {}
    zh = (locale == 'zh')

    def _num(v):
        """解析 '18.2%' / '35.97x ⚠' / 数字 → float，失败返回 None"""
        if v is None or v == '—' or v == '':
            return None
        try:
            if isinstance(v, (int, float)):
                return float(v)
            cleaned = str(v).replace('%', '').replace('x', '').replace('⚠', '').strip()
            return float(cleaned)
        except Exception:
            return None

    pe_v = _num(pe_current) or _num((price or {}).get('pe_ratio'))
    if pe_v is not None:
        n = round(abs(pe_v))
        if pe_v < 0:
            hints['pe'] = {'text': '亏了！PE 这个数没意义' if zh else 'Losing money · PE meaningless', 'level': 'warn'}
        elif pe_v < 15:
            hints['pe'] = {'text': f'现在买入的话，大约 {n} 年能回本 · 不贵' if zh else f'At this price, ~{n} yrs to earn back · Cheap', 'level': 'good'}
        elif pe_v < 25:
            hints['pe'] = {'text': f'现在买入的话，大约 {n} 年能回本 · 价格合理' if zh else f'At this price, ~{n} yrs to earn back · Fair', 'level': 'ok'}
        elif pe_v < 40:
            hints['pe'] = {'text': f'现在买入的话，{n} 年回本 · 市场认为它还会继续增长' if zh else f'~{n} yrs to earn back · Market expects continued growth', 'level': 'ok'}
        else:
            hints['pe'] = {'text': f'现在买入的话，要 {n} 年才能回本 · 在赌它高速增长' if zh else f'~{n} yrs to earn back · Betting on fast growth ⚠', 'level': 'warn'}

    roe_v = _num((lat or {}).get('roe'))
    if roe_v is not None:
        n = round(abs(roe_v))
        if roe_v < 0:
            hints['roe'] = {'text': '亏了！' if zh else 'Losing money!', 'level': 'warn'}
        elif roe_v < 5:
            hints['roe'] = {'text': f'每100块本金才赚 {n} 块，还不如存银行' if zh else f'Earns just {n}¢ per $1 · Worse than savings', 'level': 'warn'}
        elif roe_v < 10:
            hints['roe'] = {'text': f'每100块本金每年赚 {n} 块 · 一般' if zh else f'Earns {n}¢ per $1 · Average', 'level': 'ok'}
        elif roe_v < 20:
            hints['roe'] = {'text': f'每100块本金每年赚 {n} 块 · 不错，很多公司到不了这个' if zh else f"Earns {n}¢ per $1 · Good, most companies don't reach this", 'level': 'ok'}
        else:
            hints['roe'] = {'text': f'每100块本金每年能赚 {n} 块 · 很能赚' if zh else f'Earns {n}¢ per $1 · Excellent', 'level': 'good'}

    nm_v = _num((lat or {}).get('net_margin'))
    if nm_v is not None:
        n = round(abs(nm_v))
        if nm_v < 0:
            hints['net_margin'] = {'text': '亏了！' if zh else 'Losing money!', 'level': 'warn'}
        elif nm_v < 5:
            hints['net_margin'] = {'text': f'卖100块东西才留 {n} 块，一出问题就垮' if zh else f'Keeps just {n}¢ per $1 · One bad quarter could break it', 'level': 'warn'}
        elif nm_v < 10:
            hints['net_margin'] = {'text': f'卖100块东西只留 {n} 块 · 辛苦钱，每笔赚得少' if zh else f'Keeps {n}¢ per $1 · Tight, every deal counts', 'level': 'ok'}
        elif nm_v < 20:
            hints['net_margin'] = {'text': f'卖100块东西能留 {n} 块 · 不错，大多数行业达不到' if zh else f'Keeps {n}¢ per $1 · Good, hard to reach in most industries', 'level': 'ok'}
        else:
            hints['net_margin'] = {'text': f'卖100块东西能留 {n} 块 · 挣钱轻松' if zh else f'Keeps {n}¢ per $1 · Very profitable', 'level': 'good'}

    dr = (lat or {}).get('debt_ratio')
    dr_note = (lat or {}).get('debt_ratio_note')
    dr_v = _num(dr)
    if dr_v is not None:
        is_de = bool(dr_note)
        if is_de:
            if dr_v <= 1:
                hints['debt_ratio'] = {'text': '借的钱比自己的少 · 稳健' if zh else 'Debt less than equity · Solid', 'level': 'good'}
            elif dr_v <= 3:
                hints['debt_ratio'] = {'text': '借了一些钱，还在可控范围内' if zh else 'Moderate borrowing · Manageable', 'level': 'ok'}
            else:
                hints['debt_ratio'] = {'text': '借的钱太多，一出问题就垮' if zh else 'Heavy debt · One crack and it collapses', 'level': 'warn'}
        else:
            if dr_v < 40:
                hints['debt_ratio'] = {'text': f'公司 {round(dr_v)}% 的钱是自己的，借来的少' if zh else f'{round(dr_v)}% debt-funded · Low borrowing', 'level': 'good'}
            elif dr_v < 70:
                hints['debt_ratio'] = {'text': 'A股上市公司里超过一半都这样' if zh else 'Over half of A-share listed companies are in this range', 'level': 'ok'}
            elif dr_v < 90:
                hints['debt_ratio'] = {'text': '借了很多钱，要看公司能不能按时还' if zh else 'Heavy debt · Watch if it can repay on time', 'level': 'warn'}
            else:
                hints['debt_ratio'] = {'text': '几乎全靠借钱撑着，一出问题就垮' if zh else 'Nearly all debt-funded · One crack and it collapses', 'level': 'warn'}

    roic_v = _num((signals or {}).get('roic_latest'))
    if roic_v is not None:
        n = round(roic_v)
        if roic_v < 8:
            hints['roic'] = {'text': f'每投入100块才赚 {n} 块，不如直接买沪深300' if zh else f'Returns only {n}¢ per $1 · Index fund beats this', 'level': 'warn'}
        elif roic_v < 15:
            hints['roic'] = {'text': f'每投入100块每年能赚回 {n} 块 · 还行' if zh else f'Returns {n}¢ per $1 · Acceptable', 'level': 'ok'}
        else:
            hints['roic'] = {'text': f'每投入100块每年能赚回 {n} 块 · 很划算' if zh else f'Returns {n}¢ per $1 · Great', 'level': 'good'}

    fcf_v = _num((signals or {}).get('fcf_quality_avg'))
    if fcf_v is not None:
        if fcf_v >= 0.8:
            hints['fcf'] = {'text': '账面利润是真的，钱真的进了口袋' if zh else 'Profits are real cash · Healthy', 'level': 'good'}
        elif fcf_v >= 0.3:
            hints['fcf'] = {'text': '利润基本有现金支撑 · 尚可' if zh else 'Profits mostly cash-backed · Acceptable', 'level': 'ok'}
        else:
            hints['fcf'] = {'text': '账面有利润，但钱还没进口袋，要留意' if zh else "Paper profits only · Cash hasn't arrived yet", 'level': 'warn'}

    return hints
