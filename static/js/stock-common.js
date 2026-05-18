/* stock-common.js — shared JS for all stock sub-pages.
 * Requires: window._t (translations), Bootstrap 5, Chart.js (fundamentals only)
 */

/* ── More menu ──────────────────────────────────────────────────────── */
function toggleMoreMenu(code) {
  const menu = document.getElementById('more-menu-' + code);
  if (!menu) return;
  const isOpen = menu.classList.contains('open');
  document.querySelectorAll('.more-menu.open').forEach(m => m.classList.remove('open'));
  if (!isOpen) menu.classList.add('open');
}

function closeMoreMenu(code) {
  const menu = document.getElementById('more-menu-' + code);
  if (menu) menu.classList.remove('open');
}

document.addEventListener('click', e => {
  if (!e.target.closest('.more-wrap')) {
    document.querySelectorAll('.more-menu.open').forEach(m => m.classList.remove('open'));
  }
});

/* ── Progress bar ───────────────────────────────────────────────────── */
const _STAGES = [
  { label: 'Price data…',   pct: 15, after: 0  },
  { label: 'Financials…',   pct: 35, after: 6  },
  { label: 'News…',         pct: 55, after: 14 },
  { label: 'Quant rating…', pct: 72, after: 26 },
  { label: 'AI analysis…',  pct: 88, after: 36 },
];

function _startProgress(suffix) {
  const fill  = document.getElementById('pfill-'  + suffix);
  const label = document.getElementById('plabel-' + suffix);
  if (!fill) return null;
  const start = Date.now();
  return setInterval(() => {
    const elapsed = (Date.now() - start) / 1000;
    let stage = _STAGES[0];
    for (const s of _STAGES) { if (elapsed >= s.after) stage = s; else break; }
    fill.style.width = stage.pct + '%';
    if (label) label.textContent = stage.label;
  }, 1500);
}

function _finishProgress(suffix, grade) {
  const fill  = document.getElementById('pfill-'  + suffix);
  const label = document.getElementById('plabel-' + suffix);
  if (fill)  { fill.style.transition = 'width .4s ease'; fill.style.width = '100%'; }
  if (label) label.textContent = grade ? `Grade: ${grade}` : 'Done';
}

function _showPending(msg, jobId) {
  const tab = document.getElementById('tab-brief') || document.querySelector('.stock-page-body');
  if (tab) {
    tab.innerHTML = `<div class="analysis-pending-block" id="pending-block" data-job="${jobId}">
      <div class="analysis-progress" id="progress-tab-${jobId}" style="max-width:220px">
        <div class="progress-track"><div class="progress-fill" id="pfill-tab-${jobId}"></div></div>
        <span class="progress-label" id="plabel-tab-${jobId}">${msg}</span>
      </div></div>`;
  }
  const hdrFill = document.getElementById('pfill-' + jobId);
  if (!hdrFill) {
    const actions = document.getElementById('stock-header-actions');
    if (actions) {
      const existing = actions.querySelector('.analysis-progress');
      if (!existing) {
        actions.insertAdjacentHTML('afterbegin',
          `<div class="analysis-progress" id="progress-${jobId}" style="max-width:160px">
            <div class="progress-track"><div class="progress-fill" id="pfill-${jobId}"></div></div>
            <span class="progress-label" id="plabel-${jobId}">${msg}</span>
          </div>`);
      }
    }
  }
}

function pollJob(jobId) {
  const pHdr = _startProgress(jobId);
  const pTab = _startProgress('tab-' + jobId);
  let pollCount = 0;
  const maxPolls = 60;
  const iv = setInterval(async () => {
    pollCount += 1;
    try {
      const d = await (await fetch(`/api/job/${jobId}`)).json();
      if (d.status === 'done') {
        clearInterval(iv);
        if (pHdr) clearInterval(pHdr);
        if (pTab) clearInterval(pTab);
        const grade = d.analysis && d.analysis.grade;
        _finishProgress(jobId, grade);
        _finishProgress('tab-' + jobId, grade);
        setTimeout(() => location.reload(), 1200);
      } else if (d.status === 'failed') {
        clearInterval(iv);
        if (pHdr) clearInterval(pHdr);
        if (pTab) clearInterval(pTab);
        const pb = document.getElementById('pending-block');
        if (pb) pb.innerHTML = '<span style="color:var(--red)">Analysis failed — please retry</span>';
      } else if (pollCount >= maxPolls) {
        clearInterval(iv);
        if (pHdr) clearInterval(pHdr);
        if (pTab) clearInterval(pTab);
        const pb = document.getElementById('pending-block');
        if (pb) pb.innerHTML = '<span style="color:var(--ink-muted)">Analysis is taking a while — refresh to check results</span>';
      }
    } catch(e) { clearInterval(iv); if (pHdr) clearInterval(pHdr); if (pTab) clearInterval(pTab); }
  }, 5000);
}

/* ── Analysis triggers ──────────────────────────────────────────────── */
async function triggerAnalysis(code) {
  const resp = await fetch(`/api/analyze-only/${code}`, { method: 'POST' });
  const data = await resp.json();
  if (data.job_id) {
    _showPending(window._t.quant_only_msg, data.job_id);
    pollJob(data.job_id);
  }
}

async function triggerFullUpdate(code) {
  const resp = await fetch(`/api/analyze/${code}`, { method: 'POST' });
  const data = await resp.json();
  if (data.job_id) {
    _showPending(window._t.full_refresh_msg, data.job_id);
    pollJob(data.job_id);
  }
}

async function triggerNewsRefresh(code) {
  const resp = await fetch(`/api/refresh-news/${code}`, { method: 'POST' });
  const data = await resp.json();
  if (data.job_id) {
    _showPending((window._t.refresh_news || 'Refreshing news') + '…', data.job_id);
    pollJob(data.job_id);
  }
}

/* ── Letter generation ──────────────────────────────────────────────── */
function _resetLetterButton(btn) {
  if (!btn) return;
  btn.disabled = false;
  btn.textContent = window._t.gen_letter;
}

function _markLetterReady(code, btn) {
  const pendingBlock = document.getElementById('pending-block');
  if (pendingBlock) {
    pendingBlock.innerHTML = `<span style="color:var(--green)">${window._t.letter_ready}</span>`;
    pendingBlock.removeAttribute('data-job');
  }
  const actions = document.getElementById('stock-header-actions');
  if (actions && actions.textContent.includes('…')) {
    const adminMenu = window._t.is_admin
      ? `<hr style="margin:4px 0;border-color:var(--rule-light)"><button onclick="triggerFullUpdate('${code}');closeMoreMenu('${code}')">${window._t.full_update_lbl}</button>`
      : '';
    actions.innerHTML = `
      <button onclick="triggerAnalysis('${code}')" class="btn-ink btn-sm" title="${window._t.quant_only_msg}">${window._t.buffett_check}</button>
      <div class="more-wrap" id="more-wrap-${code}">
        <button class="btn-outline-ink btn-sm" onclick="toggleMoreMenu('${code}')" title="More">⋯</button>
        <div class="more-menu" id="more-menu-${code}">
          <button onclick="triggerNewsRefresh('${code}');closeMoreMenu('${code}')">${window._t.refresh_news}</button>
          <button onclick="exportBundle('${code}');closeMoreMenu('${code}')">📋 导出分析包</button>
          ${adminMenu}
        </div>
      </div>`;
  }
  const entry = btn ? btn.closest('.letter-entry') : document.querySelector('.letter-entry');
  if (entry) {
    entry.innerHTML = `
      <button onclick="showLetter()" class="btn-outline-ink btn-sm">${window._t.read_letter}</button>
      <span style="font-size:11px;color:var(--ink-faint);margin-left:8px">${window._t.letter_ready_lbl}</span>`;
  }
}

function _reloadOnLetterModalClose() {
  const modalEl = document.getElementById('letter-modal');
  if (!modalEl) return;
  modalEl.addEventListener('hidden.bs.modal', () => location.reload(), { once: true });
}

async function _fetchLatestLetter(code) {
  const resp = await fetch(`/api/letter/${code}`);
  if (!resp.ok) throw new Error(`letter fetch failed: ${resp.status}`);
  return await resp.json();
}

function _renderAndShowLetter(letterHtml) {
  const body = document.getElementById('letter-modal-body');
  if (!body) return;
  body.innerHTML = `
    <div class="letter-paper">
      <div class="letter-body-text">${letterHtml.replace(/\n/g,'<br>')}</div>
    </div>`;
  new bootstrap.Modal(document.getElementById('letter-modal')).show();
}

async function triggerLetterGeneration(code) {
  const btn = document.getElementById('letter-btn-' + code);
  if (btn) { btn.disabled = true; btn.textContent = window._t.generating; }
  try {
    const resp = await fetch(`/api/generate-letter/${code}`, { method: 'POST' });
    if (!resp.ok) throw new Error(`generate failed: ${resp.status}`);
    const data = await resp.json();
    if (!data.job_id) throw new Error('missing job_id');
    let pollCount = 0;
    const maxPolls = 50;
    const iv = setInterval(async () => {
      pollCount += 1;
      try {
        const jobResp = await fetch(`/api/job/${data.job_id}`);
        if (!jobResp.ok) throw new Error(`job fetch failed: ${jobResp.status}`);
        const d = await jobResp.json();
        if (d.status === 'done') {
          clearInterval(iv);
          try {
            const latest = await _fetchLatestLetter(code);
            if (latest && latest.letter) {
              _markLetterReady(code, btn);
              _renderAndShowLetter(latest.letter);
              _reloadOnLetterModalClose();
            } else if (d.analysis && d.analysis.letter) {
              _markLetterReady(code, btn);
              _renderAndShowLetter(d.analysis.letter);
              _reloadOnLetterModalClose();
            } else {
              _resetLetterButton(btn);
              alert('Letter job done but no content yet — please refresh.');
            }
          } catch (e) { _resetLetterButton(btn); alert('Letter generated, but could not read it. Please refresh.'); }
        } else if (d.status === 'failed') {
          clearInterval(iv);
          _resetLetterButton(btn);
          alert(d.error || 'Generation failed (Groq rate limit) — try again later.');
        } else if (pollCount >= maxPolls) {
          clearInterval(iv);
          _resetLetterButton(btn);
          alert('Letter is taking longer than usual — refresh later to check.');
        }
      } catch (e) {
        clearInterval(iv);
        _resetLetterButton(btn);
        alert('Error polling letter status — please refresh.');
      }
    }, 4000);
  } catch (e) {
    _resetLetterButton(btn);
    alert('Failed to start letter generation — please retry.');
  }
}

/* ── Export bundle ──────────────────────────────────────────────────── */
async function exportBundle(code) {
  const btn = document.querySelector(`button[onclick*="exportBundle('${code}')"]`);
  if (btn) btn.textContent = '⏳ 生成中…';
  try {
    const resp = await fetch(`/api/stock/${code}/bundle`);
    const data = await resp.json();
    if (data.error) { alert('导出失败：' + data.error); return; }
    await navigator.clipboard.writeText(data.markdown);
    if (btn) btn.textContent = '✅ 已复制！';
    setTimeout(() => { if (btn) btn.textContent = '📋 导出分析包'; }, 2500);
  } catch (e) {
    const resp = await fetch(`/api/stock/${code}/bundle`);
    const data = await resp.json();
    const ta = document.createElement('textarea');
    ta.value = data.markdown || '';
    ta.style.cssText = 'position:fixed;top:10%;left:5%;width:90%;height:80%;z-index:9999;font-size:12px;font-family:monospace;padding:12px';
    document.body.appendChild(ta);
    ta.select();
    const close = document.createElement('button');
    close.textContent = '✕ 关闭';
    close.style.cssText = 'position:fixed;top:8%;right:6%;z-index:10000;padding:6px 14px';
    close.onclick = () => { ta.remove(); close.remove(); };
    document.body.appendChild(close);
    if (btn) btn.textContent = '📋 导出分析包';
  }
}

/* ── Event form (admin) ─────────────────────────────────────────────── */
function submitEvent(code) {
  const type    = document.getElementById('evType').value;
  const date    = document.getElementById('evDate').value;
  const summary = document.getElementById('evSummary').value.trim();
  const msg     = document.getElementById('evMsg');
  if (!summary) { msg.textContent = 'Please fill in a summary.'; return; }
  fetch(`/api/stock/${code}/events`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({event_type: type, event_date: date, summary})
  }).then(r => r.json()).then(d => {
    if (d.ok) { msg.textContent = '✓ Recorded'; location.reload(); }
    else       msg.textContent = 'Error: ' + (d.error || 'unknown');
  });
}

/* ── Knowledge card ─────────────────────────────────────────────────── */
async function showKCard(slug, data, btn) {
  document.querySelectorAll('.kcard-popup').forEach(el => el.remove());
  const params = new URLSearchParams(
    Object.fromEntries(Object.entries(data).filter(([,v]) => v != null && v !== ''))
  );
  let card;
  try {
    const res = await fetch(`/api/knowledge/${slug}?${params}`);
    card = await res.json();
  } catch(e) { return; }
  if (card.error) return;
  const popup = document.createElement('div');
  popup.className = 'kcard-popup';
  popup.innerHTML = `
    <div class="kcard-header">
      <span class="kcard-name">${card.name}</span>
      <span class="kcard-situation">${card.situation}</span>
      <button class="kcard-close" onclick="this.closest('.kcard-popup').remove()">×</button>
    </div>
    <div class="kcard-one-liner">${card.one_liner}</div>
    <div class="kcard-body">${card.body.replace(/\n/g,'<br>')}</div>
    ${card.note ? `<div class="kcard-note">注意：${card.note.replace(/\n/g,'<br>')}</div>` : ''}
  `;
  const rect = btn.getBoundingClientRect();
  popup.style.top  = (rect.bottom + window.scrollY + 6) + 'px';
  popup.style.left = Math.max(8, rect.left + window.scrollX - 160) + 'px';
  document.body.appendChild(popup);
  setTimeout(() => {
    document.addEventListener('click', function close(e) {
      if (!popup.contains(e.target) && e.target !== btn) {
        popup.remove();
        document.removeEventListener('click', close);
      }
    });
  }, 50);
}

/* ── DOMContentLoaded: auto-resume pending job ──────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const pb = document.getElementById('pending-block');
  if (pb && pb.dataset.job) pollJob(pb.dataset.job);
});
