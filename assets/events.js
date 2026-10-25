// r6 2026-10-25 owner t279u: Events tabs, Upcoming/Past toggle, Discover search + topic filters (client-side, no network).
(() => {
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  $$('.ev-tab').forEach((b) => b.addEventListener('click', () => {
    $$('.ev-tab').forEach((x) => { x.classList.toggle('is-on', x === b); x.setAttribute('aria-selected', x === b); });
    $$('.ev-view').forEach((v) => { v.hidden = v.dataset.view !== b.dataset.view; });
  }));
  $$('.ev-seg-b').forEach((b) => b.addEventListener('click', () => {
    $$('.ev-seg-b').forEach((x) => x.classList.toggle('is-on', x === b));
    $$('.ev-view[data-view="list"] .ev-list').forEach((l) => { l.hidden = l.dataset.when !== b.dataset.when; });
  }));
  const res = document.querySelector('.ev-results'); if (!res) return;
  const rows = $$('.ev-view[data-view="list"] .ev-row');
  const input = document.getElementById('ev-search'); const empty = document.getElementById('ev-empty');
  const on = new Set();
  function run() {
    const q = (input.value || '').trim().toLowerCase();
    const hits = rows.filter((r) => (!q || r.dataset.text.includes(q)) && (!on.size || r.dataset.topics.split('|').some((t) => on.has(t))));
    res.replaceChildren(...hits.map((r) => r.cloneNode(true))); empty.hidden = hits.length > 0;
  }
  $$('.ev-chip').forEach((c) => c.addEventListener('click', () => { const t = c.dataset.topic; on.has(t) ? on.delete(t) : on.add(t); c.setAttribute('aria-pressed', on.has(t)); c.classList.toggle('is-on', on.has(t)); run(); }));
  input.addEventListener('input', run); run();
})();
