// Renders /assets/benchmark.json as SVG scatter charts. Numbers are shown ONLY when status === "reviewed".
// Values are displayed exactly as printed by each paper (value_as_printed); numeric "value" is used only for position.
// X = first-submission month encoded in each row's cited arXiv identifier (YYMM); rows without one are left out and listed.
(async () => {
  const $ = (id) => document.getElementById(id);
  const MOB = window.matchMedia('(max-width: 760px)').matches;
  const NS = 'http://www.w3.org/2000/svg';
  const el = (t, c, txt) => { const n = document.createElement(t); if (c) n.className = c; if (txt != null) n.textContent = txt; return n; };
  const sv = (t, a, txt) => { const n = document.createElementNS(NS, t); for (const k in a) n.setAttribute(k, a[k]); if (txt != null) n.textContent = txt; return n; };
  const css = (v, f) => (getComputedStyle(document.documentElement).getPropertyValue(v).trim() || f);
  const PALETTE = ['#b59cf8', '#e783bd', '#F5B754', css('--bench-teal', '#6fd3c1'), '#999be8', '#dd82bc'];
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const clean = (m) => m.replace(/\s*\(ours\)/gi, '').replace(/\*\*/g, '').trim(); /* r9 t288u: drop the paper's ** variant marker from display */
  const starPts = (cx, cy, R5) => { const p = []; for (let k = 0; k < 10; k++) { const a = -Math.PI / 2 + k * Math.PI / 5, rr = k % 2 ? R5 * 0.45 : R5; p.push(`${(cx + rr * Math.cos(a)).toFixed(1)},${(cy + rr * Math.sin(a)).toFixed(1)}`); } return p.join(' '); }; /* r10 t291u */
  const FOOTNOTE = '★ Lowest reported value; papers\u2019 setups differ (inputs, protocol), so values are not strictly comparable.';
  const KEY_NOTE = ' Paper-reported values, not XferAI results; Skenderi et al. = 2 papers (arXiv 2109.09824, 2204.06972).';
  const MUQ_NOTE = ' MuQAR\u2019s ★ value uses extra inputs [X, C]; MuQAR not admitted (extraction only).';
  /* r11 t294u: pause button removed (owner override of r10.1 H1); MuQAR mention in star yellow */
  function footnote(muq) { const p = el('p', 'chart-footnote', FOOTNOTE + KEY_NOTE); if (muq) { p.append(' '); p.append(el('span', 'muq-note', MUQ_NOTE.trim())); } return p; }
  const arxiv = (r) => { const m = /arXiv:(\d{2})(\d{2})\.\d{4,5}/.exec(r.source || ''); return m ? { y: 2000 + +m[1], m: +m[2], id: /arXiv:(\d{4}\.\d{4,5})/.exec(r.source)[1] } : null; };
  const paper = (r) => { const m = /\(([^,;)]+)/.exec(r.source || ''); const a = /arXiv:(\d{4}\.\d{4,5})/.exec(r.source || ''); const n = m ? m[1].trim() : 'source'; return a ? `${n} (arXiv ${a[1]})` : n; };
  const pending = () => { $('bench-status').hidden = false; for (const id of ['chart-methods', 'chart-datasets']) $(id).replaceChildren(el('div', 'scatter-skeleton')); };
  // 2026-10-25 owner t268u: minimal visible labels; details (arXiv id, venue, protocol, locator, notes, source link) in a tooltip
  // that opens on hover, keyboard focus (Enter/Space) and tap; the source link inside stays clickable. Esc or outside tap closes.
  const short = (p) => p.replace(/\s*\(arXiv [^)]*\)/, '');
  const TIP = el('div', 'bt-tip'); TIP.hidden = true; TIP.setAttribute('role', 'tooltip'); TIP.id = 'bt-tip'; document.body.append(TIP);
  let tipOwner = null, hideT = 0;
  function place(anchor) { const b = anchor.getBoundingClientRect(); const w = TIP.offsetWidth, h = TIP.offsetHeight; let x = b.left + b.width / 2 - w / 2 + scrollX, y = b.top + scrollY - h - 10; if (y < scrollY + 4) y = b.bottom + scrollY + 10; x = Math.max(scrollX + 8, Math.min(x, scrollX + document.documentElement.clientWidth - w - 8)); TIP.style.left = x + 'px'; TIP.style.top = y + 'px'; }
  function show(anchor, build) { clearTimeout(hideT); TIP.replaceChildren(...build()); TIP.hidden = false; tipOwner = anchor; anchor.setAttribute('aria-describedby', 'bt-tip'); place(anchor); }
  function hide() { TIP.hidden = true; if (tipOwner) tipOwner.removeAttribute('aria-describedby'); tipOwner = null; }
  const later = () => { hideT = setTimeout(hide, 250); };
  TIP.addEventListener('pointerenter', () => clearTimeout(hideT)); TIP.addEventListener('pointerleave', (e) => { if (e.pointerType === 'mouse') later(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && tipOwner) { const o = tipOwner; hide(); o.focus?.(); } });
  document.addEventListener('pointerdown', (e) => { if (tipOwner && !TIP.contains(e.target) && !tipOwner.contains(e.target)) hide(); });
  window.addEventListener('resize', () => tipOwner && place(tipOwner));
  function tipify(node, build, label) {
    node.setAttribute('tabindex', '0'); node.setAttribute('role', 'button'); if (label) node.setAttribute('aria-label', label);
    node.addEventListener('pointerenter', (e) => { if (e.pointerType === 'mouse') show(node, build); });
    node.addEventListener('pointerleave', (e) => { if (e.pointerType === 'mouse') later(); });
    node.addEventListener('focus', () => show(node, build)); node.addEventListener('blur', (e) => { if (!TIP.contains(e.relatedTarget)) later(); });
    node.addEventListener('click', (e) => { e.preventDefault(); show(node, build); });
    node.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); tipOwner === node ? hide() : show(node, build); } });
    return node;
  }
  TIP.addEventListener('focusout', (e) => { if (!TIP.contains(e.relatedTarget) && e.relatedTarget !== tipOwner) later(); });
  function pointTip(r, protocol) { return () => { const out = [el('strong', '', clean(r.method)), el('span', 'bt-wape', `${r.metric} ${r.value_as_printed} (as printed)`)]; const a = /arXiv:(\d{4}\.\d{4,5})/.exec(r.source || ''); if (r.row_index === 0 && a) out.push(el('span', 'bt-meta', `As reported in ${a[1]}; plotted at that paper's date.`)); out.push(el('span', 'bt-meta', (r.source || '').replace(/\s*https?:\S+/, ''))); if (protocol) out.push(el('span', 'bt-meta', protocol)); if (r.locator) out.push(el('span', 'bt-meta', r.locator)); if (r._lowest) out.push(el('span', 'bt-meta', /^MuQAR/.test(r.method) ? '★ Lowest reported. Uses extra inputs [X, C]; MuQAR not admitted (extraction only).' : '★ Lowest reported in this chart.'), el('span', 'bt-meta', FOOTNOTE)); /* r9.1 H1 */ if (r.note) out.push(el('span', 'bt-meta', r.note.replace(/\*\*/g, ''))); if (r.source_url) { const l = el('a', 'text-link', 'Source ↗'); l.href = r.source_url; l.target = '_blank'; l.rel = 'noopener'; out.push(l); } return out; }; }
  function info(texts) { const b = el('button', 'bt-info', 'i'); b.type = 'button'; tipify(b, () => texts.filter(Boolean).map((t) => el('span', 'bt-meta', t)), 'Chart details'); return b; }
  function link(node, r, protocol) { node.classList.add('bt-pt'); return tipify(node, pointTip(r, protocol), `${clean(r.method)}, ${r.metric} ${r.value_as_printed}. Details`); }

  function legend(groups) { const l = el('div', 'scatter-legend'); for (const [k, c] of groups) { const i = el('span', 'lg'); const s = el('i'); s.style.background = c; i.append(s, document.createTextNode(short(k))); l.append(i); } return l; }

  // Time scatter: x = arXiv month, y = WAPE (inverted: lower WAPE is higher on chart).
  function timeScatter(rows, colorOf) {
    const W = MOB ? 420 : 860, H = MOB ? 460 : 440, m = { l: 56, r: 24, t: 20, b: 44 };
    const t = (r) => r.d.y + (r.d.m - 1) / 12;
    const ts = rows.map(t), vs = rows.map((r) => r.value);
    const x0 = Math.floor(Math.min(...ts)) - (MOB ? 1.2 : 0.75), x1 = Math.ceil(Math.max(...ts)) + 0.25;
    const y0 = Math.floor(Math.min(...vs) - 1), y1 = Math.ceil(Math.max(...vs) + 1);
    const X = (v) => m.l + (v - x0) / (x1 - x0) * (W - m.l - m.r), Y = (v) => m.t + (v - y0) / (y1 - y0) * (H - m.t - m.b);
    const s = sv('svg', { viewBox: `0 0 ${W} ${H}`, class: 'scatter', role: 'img', 'aria-label': 'WAPE by publication month, lower is better' });
    // grid + axes
    for (let v = Math.ceil(y0); v <= y1; v += (y1 - y0 > 12 ? 2 : 1)) { s.append(sv('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), class: 'grid' }), sv('text', { x: m.l - 8, y: Y(v) + 4, class: 'tick', 'text-anchor': 'end' }, v)); }
    for (let y = Math.ceil(x0); y <= x1; y++) s.append(sv('line', { x1: X(y), x2: X(y), y1: m.t, y2: H - m.b, class: 'grid' }), sv('text', { x: X(y), y: H - m.b + 18, class: 'tick', 'text-anchor': 'middle' }, y));
    s.append(sv('text', { x: (m.l + W - m.r) / 2, y: H - 6, class: 'axis-title', 'text-anchor': 'middle' }, 'First arXiv submission (month from arXiv id)'));
    s.append(sv('text', { x: 14, y: (m.t + H - m.b) / 2, class: 'axis-title', 'text-anchor': 'middle', transform: `rotate(-90 14 ${(m.t + H - m.b) / 2})` }, 'WAPE (%), lower is better ↑'));
    // dodge points that share a month so they stay visible (visual offset only)
    const byMonth = {}; rows.forEach((r) => (byMonth[t(r)] = byMonth[t(r)] || []).push(r));
    const px = new Map();
    for (const k in byMonth) { const g = byMonth[k].sort((a, b) => a.value - b.value); g.forEach((r, i) => { const col = i % 4; px.set(r, X(+k) + (col - 1.5) * (MOB ? 6 : 9)); }); }
    // Pareto: best WAPE so far over time (step line)
    const months = Object.keys(byMonth).map(Number).sort((a, b) => a - b); let best = Infinity; const front = [];
    for (const k of months) { const b = Math.min(...byMonth[k].map((r) => r.value)); if (b < best) { best = b; front.push(byMonth[k].find((r) => r.value === b)); } }
    // points
    const lowV = Math.min(...rows.map((r) => r.value)); const lowest = rows.filter((r) => r.value === lowV); lowest.forEach((r) => { r._lowest = true; }); const labelled = new Set(front); const bestPer = {}; rows.forEach((r) => { const p = r.paper; if (!bestPer[p] || r.value < bestPer[p].value) bestPer[p] = r; }); Object.values(bestPer).forEach((r) => labelled.add(r));
    const used = [];
    for (const r of [...rows].sort((a, b) => a.value - b.value)) {
      const g = sv('g', { class: 'pt' });
      if (lowest.includes(r)) { const cx = px.get(r), cy = Y(r.value); g.append(sv('polygon', { points: starPts(cx, cy, 8.5), class: 'low-star', 'aria-hidden': 'true' })); const lt = sv('text', { x: cx, y: cy - 14, class: 'low-label', 'text-anchor': 'middle', 'aria-label': 'Star: lowest reported WAPE across papers; setups differ' }, 'lowest reported'); lt.append(sv('title', {}, FOOTNOTE)); s.append(lt); used.push({ x: cx, y: cy - 14 }); }
      else g.append(sv('circle', { cx: px.get(r), cy: Y(r.value), r: labelled.has(r) ? 6 : 4.5, fill: colorOf(r.paper) }));
      if (labelled.has(r)) { const first = t(r) === Math.min(...ts); const right = !first && px.get(r) < (m.l + W) / 2; let ly = Y(r.value) + 4; for (const u of used) if (Math.abs(u.y - ly) < 15 && Math.abs(u.x - px.get(r)) < 200) ly = u.y + 16; used.push({ x: px.get(r), y: ly }); g.append(sv('text', { x: px.get(r) + (right ? 12 : -12) + (/^MuQAR/.test(r.method) ? 5 : 0), y: ly, class: r._lowest && /^MuQAR/.test(r.method) ? 'pt-label pt-low' : 'pt-label', 'text-anchor': right ? 'start' : 'end' }, clean(r.method).split(' [')[0])); }
      s.append(link(g, r, 'VISUELLE · GTM protocol'));
    }
    return s;
  }

  // Dataset strip: x = WAPE (lower is better, left), one row per method.
  function strip(rows, colorOf, protocol) {
    const W = MOB ? 420 : 860, rowH = MOB ? 32 : 26, m = { l: 16, r: 70, t: 8, b: 30 }, H = m.t + m.b + rowH * rows.length;
    const vs = rows.map((r) => r.value), lo = Math.floor(Math.min(...vs) - 1), hi = Math.ceil(Math.max(...vs) + 1);
    const L = MOB ? 200 : 330, X = (v) => L + (v - lo) / (hi - lo || 1) * (W - L - m.r);
    const s = sv('svg', { viewBox: `0 0 ${W} ${H}`, class: 'scatter strip', role: 'img', 'aria-label': 'WAPE per method, lower is better' });
    const step = Math.max(1, Math.ceil((hi - lo) / 8));
    for (let v = lo; v <= hi; v += step) s.append(sv('line', { x1: X(v), x2: X(v), y1: m.t, y2: H - m.b, class: 'grid' }), sv('text', { x: X(v), y: H - m.b + 16, class: 'tick', 'text-anchor': 'middle' }, v));
    s.append(sv('text', { x: W - m.r, y: H - 2, class: 'axis-title', 'text-anchor': 'end' }, '← lower WAPE is better'));
    [...rows].sort((a, b) => a.value - b.value).forEach((r, i) => {
      const y = m.t + rowH * i + rowH / 2, g = sv('g', { class: 'pt' });
      const isLow = r.value === Math.min(...vs), len = X(r.value) - X(lo); if (isLow) r._lowest = true;
      const stem = sv('line', { x1: X(lo), x2: X(r.value), y1: y, y2: y, class: 'stem race-stem' }); stem.style.strokeDasharray = `${len} ${len + 1}`; stem.style.setProperty('--len', len);
      const bead = sv('g', { class: 'bead' }); bead.style.setProperty('--dx', `${-len}px`);
      bead.append(isLow ? sv('polygon', { points: starPts(X(r.value), y, 9), class: 'low-star', 'aria-hidden': 'true' }) : sv('circle', { cx: X(r.value), cy: y, r: 5.5, fill: colorOf(r.paper) }), sv('text', { x: X(r.value) + (isLow ? 12 : 10), y: y + 4, class: 'pt-value' }, r.value_as_printed));
      const nm = clean(r.method), cut = nm.indexOf(' ['); let lab; if (MOB && cut > 0) { lab = sv('text', { x: m.l, y: y - 2, class: isLow && /^MuQAR/.test(r.method) ? 'pt-label pt-low' : 'pt-label' }, nm.slice(0, cut)); lab.append(sv('tspan', { x: m.l, dy: 12, class: 'pt-sub' }, nm.slice(cut + 1))); } else lab = sv('text', { x: m.l, y: y + 4, class: isLow && /^MuQAR/.test(r.method) ? 'pt-label pt-low' : 'pt-label' }, nm); /* r10: wrap input tags on mobile to avoid stem overlap */ g.append(lab, stem, bead);
      s.append(link(g, r, protocol));
    });
    s.classList.add('racer'); const go = () => s.classList.add('go');
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) go();
    else { const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { io.disconnect(); requestAnimationFrame(() => requestAnimationFrame(go)); } }, { threshold: 0.35 }); io.observe(s); setTimeout(() => { if (!s.classList.contains('go') && s.getBoundingClientRect().top < innerHeight) go(); }, 4000); }
    return s;
  }

  try {
    const data = await (await fetch('/assets/benchmark.json', { cache: 'no-cache' })).json();
    if (data.status !== 'reviewed' || !(data.methods || []).length) return pending();
    const prep = (r) => Object.assign({}, r, { d: arxiv(r), paper: paper(r) });
    const all = [...data.methods, ...(data.datasets || []).flatMap((ds) => ds.results || [])].map(prep);
    const PAPER_COLOR = { 'Papadopoulos et al.': '#b59cf8', 'Skenderi et al.': '#e783bd', 'Dif4FF': '#F5B754', 'Avogaro et al.': css('--bench-teal', '#6fd3c1') }; const names = [...new Set(all.map((r) => short(r.paper)))]; const colorOf = (p) => PAPER_COLOR[short(p)] || PALETTE[(names.indexOf(short(p)) + 4) % PALETTE.length]; /* r11 t294u: duplicate paper-key box removed; its Skenderi 2-paper ids + 'not XferAI results' moved to KEY_NOTE footnote */
    const rows = data.methods.map(prep), dated = rows.filter((r) => r.d), undated = rows.filter((r) => !r.d);
    const host1 = $('chart-methods'); host1.className = 'scatter-host';
    host1.replaceChildren(legend([...new Set(dated.map((r) => r.paper))].map((p) => [p, colorOf(p)])), timeScatter(dated, colorOf), footnote(true));
    const card = host1.closest('.bench-card'); if (card) { card.querySelectorAll('.chart-note, .bench-label').forEach((n) => n.remove()); host1.prepend(el('p', 'bench-tags', '')); host1.firstChild.append(el('span', 'dataset-badge', 'Dataset: VISUELLE · GTM protocol')); const ib = info(['Paper-reported WAPE, not XferAI results; retrospective backtests · lower is better · same-month points offset for legibility · ★ lowest reported value (see footnote under the chart).', data.chart_label, 'VISUELLE · GTM protocol · WAPE by publication date · lower is better.', undated.length ? 'Not plotted (no date in cited source): ' + undated.map((r) => clean(r.method)).join(', ') : '']); ib.setAttribute('aria-label', 'Chart details: Paper-reported WAPE, not XferAI results; retrospective backtests · lower is better · same-month points offset for legibility · ★ lowest reported value (see footnote under the chart).'); card.querySelector('h2')?.append(ib); }
    const card2 = $('chart-datasets').closest('.bench-card'); if (card2) { const t = [...card2.querySelectorAll('.chart-note, .bench-label')].map((n) => n.textContent); card2.querySelectorAll('.chart-note, .bench-label').forEach((n) => n.remove()); card2.querySelector('h2')?.append(info([...t, data.chart_label])); }
    const host = $('chart-datasets'); host.replaceChildren();
    for (const ds of data.datasets || []) { const rs = (ds.results || []).map(prep); const b = el('div', 'bench-block'); const proto = ds.dataset + ' · ' + ds.note + (ds.shown ? ' · ' + ds.shown : ''); const h = el('h3', 'dataset-badge', 'Dataset: ' + ds.dataset.split(' · ').slice(0, 2).join(' · ')); h.append(info([proto])); b.append(h, legend([...new Set(rs.map((r) => r.paper))].map((p) => [p, colorOf(p)])), strip(rs, colorOf, proto), footnote(/^VISUELLE/i.test(ds.dataset) && rs.some((r) => /^MuQAR/.test(r.method)))); host.append(b); }
  } catch (e) { console.error(e); pending(); }
})();
