# repro_visuelle_gtm: VISUELLE / GTM-Transformer reproduction

**RESEARCH ONLY. LICENCE-GATED. Excluded by default** (`xferbench experiment list` / `run-all` skip it unless
`--allow-research-only`). No data, weights or third-party code are included in this repository.

- **Paper:** Skenderi, Joppi, Denitto, Cristani (2021). *Well Googled is Half Done: Multimodal Forecasting of New
  Fashion Product Sales with Image-based Google Trends.* arXiv:2109.09824 <https://arxiv.org/abs/2109.09824>.
- **Paper-reported WAPE:** 55.2 % (Table 1, GTM-Transformer [T+I+G], 6 weeks, 52-week Google Trends; arXiv v6,
  accessed 2026-10-24). Our reproduced number is reported **separately** and is **pending** (never run here).
- **Models:** GTM-Transformer [T+I+G] (user-installed; not vendored, not run by us).
- **Code:** <https://github.com/HumaticsLAB/GTM-Transformer>, MIT License (verified 2026-10-24 from `LICENSE`).
  We do **not** vendor it; you install it yourself and point `gtm.install_path` at your checkout.
- **Data:** VISUELLE, obtained only through the official form linked from the GTM README
  (<https://forms.gle/cVGQAmxhHf7eRJ937>). Our licence audit found **no data licence text** (`not_found`), so
  using it is **blocked** for us until the terms are known. You must read and accept the terms yourself.

## Protocol (paper Sec. 5.2)
5080 training products, the 497 most recent products for test; trained on 12 weeks, evaluated on the first 6;
Google Trends window 52 weeks; WAPE = 100·Σ|y−ŷ|/Σy after the official rescaling. See `config.yaml`.

## How to run (on your machine, after accepting the terms)
1. Request VISUELLE through the official form and save the archive locally.
2. `bash experiments/repro_visuelle_gtm/scripts/download_visuelle.sh --archive /path/to/visuelle.zip`
   (interactive acceptance; extracts into git-ignored `data/visuelle/input/raw/`).
3. Install GTM-Transformer yourself per its README; set `gtm.install_path`, `gtm.python`, `gtm.ckpt_path`.
4. `xferbench experiment run repro_visuelle_gtm --allow-research-only` → `runs/<timestamp>/report.md`
   with the paper-reported and the reproduced WAPE side by side.

## What is blocked and why
- **Data:** VISUELLE licence text not found (audit 2026-10-24) → not downloaded, not used by us.
- **Running GTM:** not cloned, installed or run here (instruction); reproduced WAPE = PENDING.
- **Scout inventory:** no Reviewer approval file in `factory/inbox/scout/repro-inventory-20261024/` → not used.
