/* r8 (owner t283u): loop 'Zero sales' -> 'Early sales'; draw the line, pulse an end dot ~1.5 s, then switch.
   Illustrative synthetic data. Reduced motion or no JS: static 'Early sales'. Hover/focus pauses. */
(() => {
  const v = document.getElementById('history-visual'); if (!v) return;
  const r = v.querySelector('.fc-sweep-rect'); if (!r) return;
  if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) { v.dataset.scn = 'early'; v.classList.add('fc-done'); return; }
  v.classList.add('fc-js');
  const X0 = +(r.getAttribute('x') || 0), END = 508, NOW = 214, HOLD = 1500;
  let scn = 'zero', paused = false, timer = 0, raf = 0;
  const hold = (el) => { el.addEventListener('mouseenter', () => { paused = true; }); el.addEventListener('mouseleave', () => { paused = false; }); };
  hold(v); v.addEventListener('focusin', () => { paused = true; }); v.addEventListener('focusout', () => { paused = false; });
  function play() {
    v.dataset.scn = scn; v.classList.remove('fc-done');
    const from = scn === 'zero' ? NOW : X0, dur = scn === 'zero' ? 2600 : 4200; let el = 0, last = null;
    r.setAttribute('width', Math.max(0, from - X0));
    const step = () => { const t = performance.now();
      if (last !== null && !paused) el += t - last; last = t;
      const k = Math.min(1, el / dur); r.setAttribute('width', (from - X0) + (END - from) * k);
      if (k < 1) { raf = setTimeout(step, 16); return; }
      v.classList.add('fc-done');
      const wait = () => { if (paused) { timer = setTimeout(wait, 250); return; } scn = scn === 'zero' ? 'early' : 'zero'; play(); };
      timer = setTimeout(wait, HOLD);
    };
    raf = setTimeout(step, 16);
  }
  play();
})();
