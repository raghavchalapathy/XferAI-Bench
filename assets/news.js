// News feed: reads ONE file, /assets/news-feed.json  {items:[{id,title,date,tag:"industry"|"research",summary,url}]}.
// To swap in Scout's reviewed feed, replace that file only. Sorted newest first. #feed-grid[data-limit] caps cards (0 = all).
(async () => {
  const grid = document.getElementById('feed-grid'); if (!grid) return;
  const el = (t, c, txt) => { const n = document.createElement(t); if (c) n.className = c; if (txt != null) n.textContent = txt; return n; };
  const fmt = (d) => { const p = String(d || '').split('-'); const m = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']; return p.length >= 2 ? (p[2] ? +p[2] + ' ' : '') + m[+p[1] - 1] + ' ' + p[0] : (d || ''); };
  function card(i) {
    const a = el('a', 'feed-card'); a.href = i.url; a.target = '_blank'; a.rel = 'noopener';
    const top = el('div', 'feed-top'); const tag = (i.tag || '').toLowerCase();
    top.append(el('span', 'tag-pill tag-' + tag, tag === 'industry' ? 'Industry' : 'Research'), el('time', '', fmt(i.date)));
    a.append(top, el('strong', '', i.title), el('span', 'feed-summary', i.summary), el('span', 'text-link', 'Source ↗'));
    a.dataset.search = [i.title, i.summary, i.tag].join(' ').toLowerCase(); return a;
  }
  try {
    const d = await (await fetch('/assets/news-feed.json', { cache: 'no-cache' })).json();
    let items = [...(d.items || [])].sort((x, y) => String(y.date).localeCompare(String(x.date)));
    const limit = +grid.dataset.limit || 0; if (limit) items = items.slice(0, limit);
    grid.replaceChildren(...items.map(card));
    const q = document.getElementById('feed-search'), empty = document.getElementById('feed-empty');
    if (q) q.addEventListener('input', () => { const s = q.value.trim().toLowerCase(); let n = 0; for (const c of grid.children) { const ok = !s || c.dataset.search.includes(s); c.hidden = !ok; if (ok) n++; } if (empty) empty.hidden = n > 0; });
  } catch (e) { grid.replaceChildren(el('p', 'fine-print', 'News is unavailable right now.')); }
})();
