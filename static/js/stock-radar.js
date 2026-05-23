/* stock-radar.js — 机构雷达 JS (A股专用)
 * Requires: window._stockCode, window._t, stock-common.js (for showKCard)
 */

const _SIGNAL_LABELS = {
  insider:       '高管增减持',
  northbound:    '北向资金',
  lhb:           '龙虎榜',
  block:         '大宗交易',
  shareholder:   '股东人数',
  fund_flow:     '资金流背离',
  repurchase:    '股票回购',
  survey:        '机构调研',
  short_selling: '融券余量',
  participation: '机构参与度',
};

const _BEHAVIORAL = ['insider','northbound','lhb','block','shareholder','fund_flow','repurchase'];
const _PRECURSOR  = ['survey','short_selling','participation'];

function _signalClass(dir) {
  if (dir > 0.15)  return 'positive';
  if (dir < -0.15) return 'negative';
  return 'neutral';
}

function _signalArrow(dir) {
  if (dir > 0.15)  return '<span style="color:#2e7d32">↑</span>';
  if (dir < -0.15) return '<span style="color:#c62828">↓</span>';
  return '<span style="color:#9e9e9e">→</span>';
}

function _miniBar(val, avg) {
  if (!avg) return '';
  const pct = Math.round(val / avg * 100);
  const color = val > avg + avg * 0.2 ? '#e65100' : val < avg - avg * 0.2 ? '#2e7d32' : '#9e9e9e';
  return `<span style="font-size:10px;color:${color}">(${pct > 100 ? '↑' : '↓'}均值${Math.abs(pct-100)}%)</span>`;
}

function _priorityBadge(weight) {
  if (weight >= 1.5) return '<span class="sig-pri sig-pri--high">高权重</span>';
  if (weight >= 1.0) return '<span class="sig-pri sig-pri--med">中权重</span>';
  return '<span class="sig-pri sig-pri--low">参考</span>';
}

function _conflictPanel(data) {
  const comps = data.components || {};
  const pos = [], neg = [];
  for (const [k, v] of Object.entries(comps)) {
    if (!v.valid || Math.abs(v.dir || 0) < 0.15) continue;
    const w = v.weight || 1.0;
    if ((v.dir || 0) > 0) pos.push({key: k, weight: w, dir: v.dir});
    else neg.push({key: k, weight: w, dir: v.dir});
  }
  if (!pos.length || !neg.length) return '';
  if (!pos.some(x => x.weight >= 1.0) || !neg.some(x => x.weight >= 1.0)) return '';
  pos.sort((a,b) => b.weight - a.weight);
  neg.sort((a,b) => b.weight - a.weight);
  const posScore = pos.reduce((s,x) => s + x.weight * Math.abs(x.dir), 0);
  const negScore = neg.reduce((s,x) => s + x.weight * Math.abs(x.dir), 0);
  const bullWins = posScore > negScore;
  const posNames = pos.slice(0,2).map(x => `${_SIGNAL_LABELS[x.key] || x.key}（权重×${x.weight}）`).join(' / ');
  const negNames = neg.slice(0,2).map(x => `${_SIGNAL_LABELS[x.key] || x.key}（权重×${x.weight}）`).join(' / ');
  return `<div class="conflict-panel">
    <div class="conflict-title">⚠ 存在矛盾信号 — 以权重高的为准</div>
    <div class="conflict-row"><span class="conflict-bull">↑</span> ${posNames}</div>
    <div class="conflict-row"><span class="conflict-bear">↓</span> ${negNames}</div>
    <div class="conflict-verdict">综合权重：<strong class="${bullWins ? 'conflict-win-buy' : 'conflict-win-sell'}">${bullWins ? '做多信号胜出' : '做空信号胜出'}</strong></div>
  </div>`;
}

function _rnsBlock(title, context, body, dir, slug, signalData) {
  const ind = dir > 0.15 ? '<span style="color:#2e7d32">↑</span>'
            : dir < -0.15 ? '<span style="color:#c62828">↓</span>'
            : '<span style="color:#bbb">→</span>';
  const qBtn = slug
    ? `<button class="kcard-trigger" onclick='showKCard("${slug}",${JSON.stringify(signalData||{})},this)' title="解读这个信号">?</button>`
    : '';
  return `<div class="rns-block">
    <div class="rns-head"><span class="rns-title">${title}</span>${ind}${qBtn}</div>
    <div class="rns-context">${context}</div>
    <div class="rns-body">${body}</div>
  </div>`;
}

function _surveyTimeline(sv) {
  const evts = (sv.events || []).filter(e => e.date);
  const W = 520, H = 56, PAD = 20;
  const inner = W - PAD * 2;
  const nowMs = Date.now();
  const day90 = 90 * 864e5;
  const todayX = PAD + inner;

  // Always render the axis; dots only if events exist
  function dotX(dateStr) {
    const age = nowMs - new Date(dateStr).getTime();
    if (age < 0 || age > day90) return null;
    return PAD + inner * (1 - age / day90);
  }
  function dotR(n) { return n >= 51 ? 10 : n >= 11 ? 7 : 4; }

  // Group events by date to stack same-day dots vertically
  const byDate = {};
  for (const e of evts) {
    const x = dotX(e.date);
    if (x === null) continue;
    if (!byDate[e.date]) byDate[e.date] = { x, items: [] };
    byDate[e.date].items.push(e);
  }

  let dots = '';
  let delay = 0;
  for (const { x, items } of Object.values(byDate)) {
    let cy = 28;
    for (const e of items) {
      const r = dotR(e.n_inst || 1);
      const fill = e.is_specific ? 'var(--prophet-ink)' : 'none';
      const method = e.method || (e.is_specific ? '专程拜访' : '开放日');
      const tip = `${e.date} · ${e.n_inst || '?'} 家机构 · ${method}`;
      dots += `<circle cx="${x.toFixed(1)}" cy="${cy}" r="${r}" fill="${fill}" stroke="var(--prophet-ink)" stroke-width="1.5" style="cursor:default;animation:svgFade 0.15s ${delay.toFixed(2)}s both"><title>${tip}</title></circle>`;
      cy += r * 2 + 4;
      delay += 0.04;
    }
  }

  const emptyNote = evts.length === 0
    ? `<div class="prophet-timeline-empty">近 90 天暂无调研记录</div>` : '';

  return `<div class="prophet-timeline">
    <div class="prophet-timeline-label">调研时间线（近90天）</div>
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" class="prophet-timeline-svg">
      <style>@keyframes svgFade{from{opacity:0}to{opacity:1}}</style>
      <line x1="${PAD}" y1="28" x2="${todayX}" y2="28" stroke="var(--prophet-rule)" stroke-width="1"/>
      <line x1="${todayX}" y1="10" x2="${todayX}" y2="46" stroke="var(--prophet-ink)" stroke-width="1" opacity="0.4"/>
      <text x="${PAD}" y="${H - 2}" font-size="8" fill="var(--prophet-muted)" text-anchor="start" font-family="monospace">90天前</text>
      ${dots}
    </svg>
    ${emptyNote}
    ${evts.length > 0 ? `<div class="prophet-timeline-legend">
      <span class="prophet-legend-item"><svg width="10" height="10"><circle cx="5" cy="5" r="4" fill="var(--prophet-ink)"/></svg>专程拜访</span>
      <span class="prophet-legend-item"><svg width="10" height="10"><circle cx="5" cy="5" r="4" fill="none" stroke="var(--prophet-ink)" stroke-width="1.5"/></svg>开放日</span>
      <span class="prophet-legend-item">点越大机构数越多</span>
    </div>` : ''}
  </div>`;
}

function _signalStrengthBars(sh, pa) {
  let rows = '';
  if (sh && sh.valid && sh.change_pct != null) {
    const raw = Math.max(-100, Math.min(100, sh.change_pct));
    const w = Math.abs(raw) / 2;
    const isInc = raw > 0;
    const fillStyle = isInc ? `right:50%;width:${w}%` : `left:50%;width:${w}%`;
    const cls = isInc ? 'prophet-bar-neg' : 'prophet-bar-pos';
    const hint = isInc ? '空头在加仓' : '空头在平仓';
    rows += `<div class="prophet-bar-row">
      <span class="prophet-bar-label">融券余量</span>
      <div class="prophet-bar-track">
        <div class="prophet-bar-center"></div>
        <div class="prophet-bar-fill ${cls}" style="${fillStyle}"></div>
      </div>
      <span class="prophet-bar-val">${raw > 0 ? '+' : ''}${raw.toFixed(0)}%</span>
      <span class="prophet-bar-hint">${hint}</span>
    </div>`;
  }
  if (pa && pa.valid && pa.latest != null && pa.avg_30d > 0) {
    const dev = (pa.latest - pa.avg_30d) / pa.avg_30d * 100;
    const capped = Math.max(-100, Math.min(100, dev));
    const w = Math.abs(capped) / 2;
    const isAbove = dev > 0;
    const fillStyle = isAbove ? `left:50%;width:${w}%` : `right:50%;width:${w}%`;
    const cls = isAbove ? 'prophet-bar-pos' : 'prophet-bar-neg';
    const hint = isAbove ? '高于均值' : '低于均值';
    rows += `<div class="prophet-bar-row">
      <span class="prophet-bar-label">机构参与度</span>
      <div class="prophet-bar-track">
        <div class="prophet-bar-center"></div>
        <div class="prophet-bar-fill ${cls}" style="${fillStyle}"></div>
      </div>
      <span class="prophet-bar-val">${dev > 0 ? '+' : ''}${dev.toFixed(0)}% vs均</span>
      <span class="prophet-bar-hint">${hint}</span>
    </div>`;
  }
  if (!rows) return '';
  return `<div class="prophet-bars"><div class="prophet-bars-title">信号相对强度</div>${rows}</div>`;
}

function _predictionAnchor(code) {
  return `<div class="prophet-anchor" id="prophet-anchor-${code}">
    <div class="prophet-anchor-title">你的预测</div>
    <div class="prophet-anchor-desc">根据以上信号，你认为接下来5天股价方向？记录下来，5天后系统会核对。</div>
    <div class="prophet-anchor-btns">
      <button class="prophet-pill prophet-pill-up"   onclick="_submitPrediction('${code}','up',this)">往上 ↑</button>
      <button class="prophet-pill prophet-pill-down" onclick="_submitPrediction('${code}','down',this)">往下 ↓</button>
      <button class="prophet-pill prophet-pill-flat" onclick="_submitPrediction('${code}','unsure',this)">不好说</button>
    </div>
    <input class="prophet-note-input" id="prophet-note-${code}" maxlength="80" placeholder="加一条备注（可选，80字内）">
    <div class="prophet-anchor-status" id="prophet-anchor-status-${code}"></div>
    <div class="prophet-history" id="prophet-history-${code}"></div>
  </div>`;
}

async function _submitPrediction(code, direction, btn) {
  btn.closest('.prophet-anchor-btns').querySelectorAll('.prophet-pill').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  const note  = (document.getElementById(`prophet-note-${code}`) || {}).value || '';
  const status = document.getElementById(`prophet-anchor-status-${code}`);
  try {
    const resp = await fetch(`/api/predict/${code}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({direction, note}),
    });
    const j = await resp.json();
    if (resp.ok) {
      if (status) status.innerHTML = `<span class="prophet-saved">✓ 已记录，5天后系统核对</span>`;
      _loadPredictionHistory(code);
    } else {
      if (status) status.textContent = j.error || '保存失败';
    }
  } catch(e) {
    if (status) status.textContent = '网络错误';
  }
}

async function _loadPredictionHistory(code) {
  const el = document.getElementById(`prophet-history-${code}`);
  if (!el) return;
  try {
    const resp = await fetch(`/api/predict/${code}`);
    const rows = await resp.json();
    const dirLabel = {
      up:     '<span class="prophet-hist-dir-up">往上↑</span>',
      down:   '<span class="prophet-hist-dir-down">往下↓</span>',
      unsure: '<span class="prophet-hist-dir-flat">不好说</span>'
    };

    // If latest prediction was made today, disable pill buttons
    if (rows.length) {
      const latestDate = (rows[0].created_at || '').slice(0, 10);
      const todayStr = new Date().toISOString().slice(0, 10);
      if (latestDate === todayStr) {
        const anchor = document.getElementById(`prophet-anchor-${code}`);
        if (anchor) {
          anchor.querySelectorAll('.prophet-pill').forEach(b => { b.disabled = true; });
          const noteInput = document.getElementById(`prophet-note-${code}`);
          if (noteInput) noteInput.disabled = true;
          const status = document.getElementById(`prophet-anchor-status-${code}`);
          if (status) {
            const dir = dirLabel[rows[0].direction] || rows[0].direction;
            status.innerHTML = `<span class="prophet-saved">已记录：${dir}，${rows[0].created_at.slice(0, 16)}</span>`;
          }
        }
      }
    }

    if (!rows.length) { el.innerHTML = ''; return; }
    let html = rows.slice(0, 3).map(r => {
      const dl = dirLabel[r.direction] || r.direction;
      const date = (r.created_at || '').slice(0, 10);
      let result = '';
      if (r.correct === 1) result = '<span class="prophet-hist-correct">✓ 对了</span>';
      else if (r.correct === 0) result = '<span class="prophet-hist-incorrect">✗ 错了</span>';
      else if (r.actual_return_5d != null) result = `5日收益 ${r.actual_return_5d > 0 ? '+' : ''}${r.actual_return_5d.toFixed(1)}%`;
      else result = '<span class="prophet-hist-pending">待核对</span>';
      return `<div class="prophet-history-row"><span>${date} ${dl}${r.note ? ' · ' + r.note : ''}</span><span>${result}</span></div>`;
    }).join('');
    el.innerHTML = html;
  } catch(e) {}
}

function _surveyBody(sv) {
  if (!sv) return '<span style="color:var(--ink-faint)">数据拉取中…</span>';
  const evts = sv.events || [];
  const specific = evts.filter(e => e.is_specific);
  if (!evts.length) return '近60天没有机构调研记录。';
  let s = `近60天共 <strong>${evts.length}</strong> 次调研`;
  if (specific.length) s += `，其中 <strong>${specific.length}</strong> 次是机构专程拜访`;
  const r = evts[0];
  if (r) s += `。<br>最近一次：${r.date}，${r.n_inst} 家机构参与`;
  return s + '。';
}

function _shortBody(s) {
  if (!s || !s.valid) return '这只股票暂无融券数据（可能不在融券标的范围内）。';
  const sign = s.change_pct >= 0 ? '+' : '';
  const col = s.change_pct >= 30 ? '#c62828' : s.change_pct <= -30 ? '#2e7d32' : 'var(--ink)';
  let body = `当前融券余量 <strong>${s.latest_short} 万股</strong>，近30天变化 <span style="color:${col}">${sign}${s.change_pct}%</span>。`;
  if (s.trend === '做空增加')  body += '<br>做空仓位在增加。';
  else if (s.trend === '做空减少') body += '<br>之前做空的资金在撤退（空头平仓），这有时出现在底部附近。';
  else body += '<br>做空仓位基本稳定，没有明显加仓动作。';
  return body;
}

function _participationBody(p) {
  if (!p || !p.valid) return '机构参与度数据暂缺。';
  let s = `当前 <strong>${p.latest}</strong>，30日均值 ${p.avg_30d}${_miniBar(p.latest, p.avg_30d)}。`;
  if (p.spike) s += '<br><span style="color:#e65100">今日参与度异常偏高，大资金非常活跃，结合价格方向判断含义。</span>';
  else if (p.trend === '上升') s += '<br>近5天机构参与度在上升，大资金的关注度在增加。';
  else if (p.trend === '下降') s += '<br>近5天机构参与度在下降，大资金的关注度有所减退。';
  else s += '<br>机构参与度平稳，无异常。';
  return s;
}

function _instHoldingsBlock(snap, instClass) {
  const inc = snap.inst_increased || 0;
  const dec = snap.inst_decreased || 0;
  const top = snap.inst_top || [];
  const etfS   = instClass.etf_sellers || [];
  const actS   = instClass.active_sellers || [];
  let body = `近季 <strong>↑${inc} 增持 / ↓${dec} 减持</strong>`;
  if (top.length) {
    body += '<br><br>';
    for (const inst of top.slice(0, 4)) {
      const isPassive = /ETF|指数|沪深300|中证|上证50|科创|创业板/.test(inst.name);
      const chg = inst.change != null ? inst.change.toFixed(2) : '—';
      const col = inst.change > 0 ? '#2e7d32' : inst.change < 0 ? '#c62828' : 'var(--ink-muted)';
      const badge = isPassive ? ' <span class="inst-passive-badge">指数基金</span>' : '';
      body += `· ${inst.name}${badge} <span style="color:${col}">${inst.change >= 0 ? '+' : ''}${chg}%</span><br>`;
    }
  }
  if (etfS.length && !actS.length && dec > 0) {
    body += '<br>减持的全部是指数基金——这类基金在指数权重调整时被动卖出，通常不代表主动判断改变。';
  } else if (actS.length) {
    const names = actS.slice(0, 2).map(s => s.name).join('、');
    body += `<br>其中 <strong>${names}</strong> 是主动管理基金——这代表基金经理主动决策卖出。`;
  }
  const ctx = '每季度机构必须公告持仓变化——这是我们能看到的最直接的"机构在买还是在卖"的记录。';
  return _rnsBlock('机构持仓增减（近季）', ctx, body, inc > dec ? 0.5 : dec > inc ? -0.5 : 0);
}

function _mainFlowBlock(snap, comp) {
  let body;
  if (snap.main_net != null) {
    const net = snap.main_net;
    const ratio = snap.main_ratio;
    const col = net >= 0 ? '#2e7d32' : '#c62828';
    const dir = net >= 0 ? '流入' : '流出';
    body = `今日净${dir} <span style="color:${col}"><strong>${net >= 0 ? '+' : ''}${net.toFixed(2)} 亿</strong></span>`;
    if (ratio != null) body += `，占当日成交额 <strong>${Math.abs(ratio).toFixed(1)}%</strong>`;
    body += '。';
  } else {
    body = comp?.desc || '今日主力资金数据暂缺。';
  }
  const ctx = '主力资金是指大额买卖单，通常来自机构或大户。它的流向代表有判断力的资金在做什么。';
  return _rnsBlock('主力资金', ctx, body, comp?.dir || 0);
}

function _marginBlock(snap) {
  const bal = snap.margin_balance;
  const chgPct = snap.margin_change_pct;
  const mdir = snap.margin_direction;
  if (!bal && chgPct == null) return _rnsBlock('融资余额（散户杠杆）',
    '散户用借来的钱买股票叫融资。余额减少说明散户在主动降低风险，情绪趋于保守。',
    '融资余额数据暂缺。', 0);
  let body = '';
  if (bal) body += `当前余额 <strong>${(bal / 1e8).toFixed(1)} 亿</strong>`;
  if (chgPct != null) {
    const sign = chgPct >= 0 ? '+' : '';
    const col = chgPct > 5 ? '#c62828' : chgPct < -5 ? '#2e7d32' : 'var(--ink)';
    body += `，近期变化 <span style="color:${col}">${sign}${chgPct.toFixed(1)}%</span>`;
  }
  if (mdir && mdir.includes('减')) body += '。<br>散户杠杆在下降，市场情绪趋于保守。';
  else if (mdir && mdir.includes('增')) body += '。<br>散户杠杆在增加，市场情绪趋于激进。';
  else body += '。';
  const ctx = '散户用借来的钱买股票叫融资。余额减少说明散户在主动降低风险，情绪趋于保守。';
  return _rnsBlock('融资余额（散户杠杆）', ctx, body, 0);
}

function _renderIntention(data) {
  const precRaw   = data.precursor_raw || {};
  const snap      = data.signals_snapshot || {};
  const instClass = data.inst_classification || {};
  const obs       = data.observations || [];
  const comps     = data.components || {};
  let html = '';

  html += `<div class="radar-section-head">
    <span class="radar-section-title">📡 前兆信号</span>
    <span class="radar-precursor-badge">比行为早 1-4 周</span>
  </div>`;
  const sv  = precRaw.survey        || {};
  const sh  = precRaw.short_selling || {};
  const pa  = precRaw.participation  || {};
  const priceChg = pa.price_change_pct ?? null;

  const svData = {
    has_specific: !!(sv.events||[]).some(e=>e.is_specific),
    n_inst:       ((sv.events||[])[0]||{}).n_inst || 0,
    days_ago:     ((sv.events||[])[0]?.date) ? Math.floor((Date.now()-new Date(sv.events[0].date))/864e5) : 999,
    score:        sv.score || 0,
    event_count:  (sv.events||[]).length,
  };
  const shData = {
    change_pct:       sh.change_pct ?? null,
    price_change_pct: priceChg,
    pa_spike:         pa.spike || false,
    has_survey:       svData.has_specific && svData.days_ago <= 30,
  };
  const paData = {
    spike:            pa.spike || false,
    trend:            pa.trend || '中性',
    price_change_pct: priceChg,
    short_increasing: sh.valid && (sh.change_pct||0) > 15,
    latest:           pa.latest ?? null,
    avg_30d:          pa.avg_30d ?? null,
  };

  html += _rnsBlock('机构调研热度',
    (comps.survey?.context || '机构不会无缘无故花时间调研——密度高说明他们在认真考虑，在做买入前的功课。'),
    _surveyBody(sv), comps.survey?.dir || 0, 'survey_activity', svData);
  html += _surveyTimeline(sv);
  html += _rnsBlock('融券做空动向',
    (comps.short_selling?.context || '融券就是借股票来卖，押注股价会跌。使用融券的主要是有判断力的专业资金。'),
    _shortBody(sh), comps.short_selling?.dir || 0, 'short_selling', shData);
  html += _rnsBlock('机构参与度',
    (comps.participation?.context || '机构参与度是当天机构交易占全市场成交的比例——越高说明今天大资金越活跃。'),
    _participationBody(pa), comps.participation?.dir || 0, 'inst_participation', paData);
  html += _signalStrengthBars(sh, pa);

  html += `<div class="radar-section-head" style="margin-top:24px">
    <span class="radar-section-title">已发生的行为</span>
    <span style="font-size:11px;color:var(--ink-faint)">这些已经在公开数据里可以看到</span>
  </div>`;
  html += _instHoldingsBlock(snap, instClass);
  html += _mainFlowBlock(snap, comps.fund_flow);
  html += _marginBlock(snap);
  html += _rnsBlock('北向资金',
    (comps.northbound?.context || '境外机构通过沪深港通买A股的资金——这些机构研究流程严格，被认为视野更长远。'),
    comps.northbound?.desc || '北向资金数据暂缺。', comps.northbound?.dir || 0);
  html += _rnsBlock('高管增减持',
    (comps.insider?.context || '高管是最了解公司内部情况的人。他们用自己的钱买卖自家股票，历来被认为参考价值最高。'),
    comps.insider?.desc || '高管增减持数据暂缺。', comps.insider?.dir || 0);

  if (obs.length) {
    html += `<div class="radar-section-head" style="margin-top:24px">
      <span class="radar-section-title">综合来看</span>
    </div>
    <div class="radar-observations">`;
    for (const o of obs) html += `<div class="radar-obs-item">· ${o}</div>`;
    html += `<div class="radar-obs-conf">有效信号 ${data.valid_signal_count || '—'} 个 · 置信度 ${data.confidence_label || '—'}</div>
    </div>`;
  }

  const _code = (window._stockCode || '').split('.')[0];
  if (window._t && window._t.in_watchlist) html += _predictionAnchor(_code);

  const cacheNote = data.precursor_from_cache
    ? `缓存于 ${data.precursor_fetched_at || '今日'}`
    : `${data.precursor_fetched_at || '刚刚'} 拉取`;
  html += `<div class="intention-freshness">
    <span>前兆信号 ${cacheNote}</span>
    <button class="radar-reload-btn" onclick="_reloadIntention()">↺ 强制刷新</button>
  </div>`;

  document.getElementById('intention-content').innerHTML = html;
  if (window._t && window._t.in_watchlist) _loadPredictionHistory(_code);
  document.getElementById('intention-loading').style.display = 'none';
  document.getElementById('intention-content').style.display = 'block';
}

let _intentionLoaded = false;

async function loadIntentionTab(force) {
  if (_intentionLoaded && !force) return;
  _intentionLoaded = true;

  document.getElementById('intention-loading').style.display = 'flex';
  document.getElementById('intention-empty').style.display = 'none';
  document.getElementById('intention-content').style.display = 'none';

  const url = '/api/intention/' + (window._stockCode || '') + (force ? '?force=1' : '');
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    _renderIntention(data);
  } catch (e) {
    document.getElementById('intention-loading').style.display = 'none';
    document.getElementById('intention-content').style.display = 'block';
    document.getElementById('intention-content').innerHTML =
      `<div class="intention-error">加载失败：${e.message} — 请稍后重试</div>`;
  }
}

function _reloadIntention() { _intentionLoaded = false; loadIntentionTab(true); }
