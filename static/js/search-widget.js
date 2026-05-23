/**
 * SearchWidget — unified stock typeahead
 *
 * Usage:
 *   SearchWidget.bind(inputId, dropId, getSearchType, onSelect, locale)
 *
 *   getSearchType : () => 'auto' | 'cn' | 'intl' | 'fund'
 *   onSelect      : (code, name, market, assetType) => void
 *   locale        : 'zh' | 'en'  (default 'zh')
 */
const SearchWidget = (() => {

  const _T = {
    zh: {
      loading:  '搜索中…',
      error:    '搜索出错，请检查网络',
      timeout:  '加载超时，请稍后重试',
      warming:  '⏳ 正在加载股票列表…',
      empty:    '未找到匹配结果',
    },
    en: {
      loading:  'Searching…',
      error:    'Search error, check your connection',
      timeout:  'Timed out, please retry',
      warming:  '⏳ Loading stock list…',
      empty:    'No results found',
    },
  };

  /**
   * @param {string}   inputId       id of the <input> element
   * @param {string}   dropId        id of the dropdown container
   * @param {Function} getSearchType () => search type string
   * @param {Function} onSelect      (code, name, market, assetType) => void
   * @param {string}   locale        'zh' | 'en'
   */
  function bind(inputId, dropId, getSearchType, onSelect, locale) {
    const inp  = document.getElementById(inputId);
    const drop = document.getElementById(dropId);
    if (!inp || !drop) return;

    const t = _T[(locale === 'en') ? 'en' : 'zh'];
    let _timer;
    let _composing = false;
    let _lastQuery = '';

    /* ── IME composition (Chinese / Japanese / Korean input) ── */
    inp.addEventListener('compositionstart', () => { _composing = true; });
    inp.addEventListener('compositionend', () => {
      _composing = false;
      // iOS Safari fires compositionend BEFORE updating input.value.
      // A zero-delay timeout lets the browser commit the composed text first.
      setTimeout(() => _schedule(inp.value.trim()), 0);
    });

    /* ── Normal typing ── */
    inp.addEventListener('input', () => {
      if (_composing) return;
      _schedule(inp.value.trim());
    });

    /* ── Enter key: fire immediately ── */
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !_composing) {
        e.preventDefault();
        clearTimeout(_timer);
        const q = inp.value.trim();
        if (q) _doSearch(q);
      }
    });

    /* ── Close dropdown when clicking outside ── */
    document.addEventListener('click', e => {
      if (!inp.contains(e.target) && !drop.contains(e.target))
        drop.classList.remove('open');
    }, { passive: true });

    /* ── Schedule a search with debounce ── */
    function _schedule(q) {
      clearTimeout(_timer);
      if (!q) {
        drop.innerHTML = '';
        drop.classList.remove('open');
        return;
      }
      if (q.length < 2) return;    // wait for at least 2 chars before searching
      _timer = setTimeout(() => _doSearch(q), 350);
    }

    /* ── Fetch and render ── */
    async function _doSearch(q, _retries) {
      _retries = _retries || 0;
      _lastQuery = q;

      drop.innerHTML = '<div class="search-loading"><span class="spinner-sm"></span> ' + t.loading + '</div>';
      drop.classList.add('open');

      let data;
      try {
        const type = (typeof getSearchType === 'function') ? getSearchType() : (getSearchType || 'auto');
        const resp = await fetch('/api/search?q=' + encodeURIComponent(q) + '&type=' + type);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        data = await resp.json();
      } catch (e) {
        if (inp.value.trim() !== q) return;
        drop.innerHTML = '<div class="search-empty">' + t.error + '</div>';
        return;
      }

      // Stale: user has already changed the input
      if (inp.value.trim() !== q) return;

      // CN cache still warming up — poll
      if (data && data.loading) {
        if (_retries >= 20) {
          drop.innerHTML = '<div class="search-empty">' + t.timeout + '</div>';
          return;
        }
        drop.innerHTML = '<div class="search-empty">' + t.warming + '</div>';
        setTimeout(() => { if (inp.value.trim() === q) _doSearch(q, _retries + 1); }, 1500);
        return;
      }

      const items = Array.isArray(data) ? data : [];
      if (!items.length) {
        drop.innerHTML = '<div class="search-empty">' + t.empty + '</div>';
        return;
      }

      drop.innerHTML = items.map(r => {
        const at = r.asset_type || '';
        const atBadge = at && at !== '股票' ? `<span class="asset-type-tag">${_esc(at)}</span>` : '';
        const mkt = `<span class="market-tag">${(r.market || '').toUpperCase()}</span>`;
        return `<div class="search-item"
                     data-code="${_esc(r.code)}"
                     data-name="${_esc(r.name)}"
                     data-market="${_esc(r.market)}"
                     data-at="${_esc(at)}">
          ${mkt}<span class="search-item-code">${r.code}</span
          ><span class="search-item-name">${r.name}</span>${atBadge}
        </div>`;
      }).join('');

      drop.querySelectorAll('.search-item').forEach(el => {
        el.addEventListener('click', () => {
          const { code, name, market, at } = el.dataset;
          drop.classList.remove('open');
          inp.value = '';
          onSelect(code, name, market, at || '');
        });
      });
    }
  }

  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;');
  }

  return { bind };
})();
