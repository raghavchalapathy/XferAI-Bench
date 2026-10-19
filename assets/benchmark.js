// Renders /assets/benchmark.json. Numbers are shown ONLY when status === "reviewed".
// Schema: methods:[{method, value, source_url?}], datasets:[{dataset, results:[{method, value}]}]; value = WAPE % (lower is better).
(async () => {
  const $ = (id) => document.getElementById(id);
  const pending = () => { $('bench-status').hidden = false; for (const id of ['chart-methods', 'chart-datasets']) $(id).replaceChildren(skeleton()); };
  function skeleton() { const w = document.createElement('div'); w.className = 'bench-bars skeleton'; for (let i = 0; i < 4; i++) { const r = document.createElement('div'); r.className = 'bar-row'; r.innerHTML = '<span class="bar-label"></span><span class="bar-track"><span class="bar-fill" style="width:' + (80 - i * 14) + '%"></span></span><span class="bar-value"></span>'; w.append(r); } return w; }
  function bars(rows) {
    const w = document.createElement('div'); w.className = 'bench-bars';
    const max = Math.max(...rows.map((r) => r.value), 1);
    for (const r of [...rows].sort((a, b) => a.value - b.value)) {
      const row = document.createElement('div'); row.className = 'bar-row';
      const l = document.createElement('span'); l.className = 'bar-label'; l.textContent = r.method;
      const t = document.createElement('span'); t.className = 'bar-track';
      const f = document.createElement('span'); f.className = 'bar-fill'; f.style.width = (100 * r.value / max).toFixed(1) + '%'; t.append(f);
      const v = document.createElement('span'); v.className = 'bar-value'; v.textContent = (+r.value).toFixed(1) + '%';
      row.append(l, t, v); w.append(row);
    }
    return w;
  }
  try {
    const res = await fetch('/assets/benchmark.json', { cache: 'no-cache' }); const d = await res.json();
    if (d.status !== 'reviewed' || !(d.methods || []).length) return pending();
    $('chart-methods').replaceChildren(bars(d.methods));
    const host = $('chart-datasets'); host.replaceChildren();
    for (const ds of d.datasets || []) { const h = document.createElement('h3'); h.textContent = ds.dataset; host.append(h, bars(ds.results || [])); }
  } catch (e) { pending(); }
})();
