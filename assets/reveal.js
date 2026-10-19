// Progressive on-scroll reveal for home sections and news cards.
(() => {
  const io = 'IntersectionObserver' in window ? new IntersectionObserver((es) => { for (const e of es) if (e.isIntersecting) { e.target.classList.add('is-visible'); io.unobserve(e.target); } }, { threshold: 0.15 }) : null;
  const watch = (el, i) => { el.classList.add('reveal'); el.style.transitionDelay = (i * 120) + 'ms'; io ? io.observe(el) : el.classList.add('is-visible'); };
  document.querySelectorAll('.reveal-section .section-heading').forEach(watch);
  const grid = document.getElementById('home-news'); if (!grid) return;
  const scan = () => [...grid.children].filter((c) => !c.classList.contains('reveal') && !c.classList.contains('loading')).forEach(watch);
  new MutationObserver(scan).observe(grid, { childList: true }); scan();
})();
