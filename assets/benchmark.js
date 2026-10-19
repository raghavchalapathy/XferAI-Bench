// Renders /assets/benchmark.json. Numbers are shown ONLY when status === "reviewed".
// Values are displayed exactly as printed by each paper (value_as_printed); "value" is used only for bar length/sort.
(async () => {
  const $ = (id) => document.getElementById(id);
  const el = (t, c, txt) => { const n = document.createElement(t); if (c) n.className = c; if (txt != null) n.textContent = txt; return n; };
  function skeleton() { const w = el('div', 'bench-bars skeleton'); for (let i = 0; i < 4; i++) { const r = el('div', 'bar-row'); r.innerHTML = '<span class="bar-label"></span><span class="bar-track"><span class="bar-fill" style="width:' + (80 - i * 14) + '%"></span></span><span class="bar-value"></span>'; w.append(r); } return w; }
  const pending = () => { $('bench-status').hidden = false; for (const id of ['chart-methods', 'chart-datasets']) $(id).replaceChildren(skeleton()); };
  function bars(rows) {
    const w = el('div', 'bench-bars'); const max = Math.max(...rows.map((r) => r.value), 1);
    for (const r of rows) {
      const tip = `${r.method} — ${r.metric} ${r.value_as_printed} (as printed). ${r.source}; ${r.locator}`;
      const row = el(r.source_url ? 'a' : 'div', 'bar-row'); row.title = tip; if (r.source_url) { row.href = r.source_url; row.target = '_blank'; row.rel = 'noopener'; }
      const t = el('span', 'bar-track'); const f = el('span', 'bar-fill'); f.style.width = (100 * r.value / max).toFixed(1) + '%'; t.append(f);
      row.append(el('span', 'bar-label', r.method), t, el('span', 'bar-value', r.value_as_printed)); w.append(row);
    }
    return w;
  }
  try {
    const d = await (await fetch('/assets/benchmark.json', { cache: 'no-cache' })).json();
    if (d.status !== 'reviewed' || !(d.methods || []).length) return pending();
    document.querySelectorAll('.bench-label').forEach((n) => { n.textContent = d.chart_label; n.hidden = false; });
    $('chart-methods').replaceChildren(el('p', 'bench-sub', 'VISUELLE · GTM protocol · lower is better'), bars(d.methods));
    const host = $('chart-datasets'); host.replaceChildren();
    for (const ds of d.datasets || []) { const b = el('div', 'bench-block'); b.append(el('h3', '', ds.dataset), el('p', 'bench-sub', ds.note + (ds.shown ? ' · ' + ds.shown : '')), bars(ds.results || [])); host.append(b); }
  } catch (e) { pending(); }
})();
