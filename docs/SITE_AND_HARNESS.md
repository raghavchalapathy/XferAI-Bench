# Site and harness rules

Short rules for contributors and coding agents. Owner directives, 2026-10-19.

## Evidence
- Every benchmark number is either **paper-reported** and has passed Scout research, Scientist verification and
  Reviewer review, or comes from a **reproducible XferAI-Bench run**. Values are copied as printed; no conversion,
  no cross-paper ranking.
- **No proprietary Walmart data.** Public papers that mention Walmart may be cited.
- **Goals, not features:** explainability, interpretability and feature traceability are design goals.
  Uncertainty intervals are not computed yet ([EVALUATION.md](EVALUATION.md)).

## Scope
Cold-start time-series forecasting (zero or near-zero own history). Foundation-model / zero-shot approaches
(e.g. TimesFM) are tracked. Licence: Apache-2.0.

## Website (xferai.app)
- Built from the canonical store's `site/build_pages.py` and `factory/LEAN_SITE_RULES.md`, published to the
  `gh-pages` branch. Do not hand-edit gh-pages without updating the generator.
- Menu: Benchmark · News & Research · Getting started · Offers | Services, plus a "Send your request" button.
  No sub-menus. Lean, minimal text.
- Benchmark charts read `assets/benchmark.json` (reviewed rows only). News reads `assets/news-feed.json`
  (Reviewer-approved Scout feed).

## Docs
Lean and scannable. Start users at [DIY-GettingStarted.md](DIY-GettingStarted.md) or [GETTING_STARTED.md](GETTING_STARTED.md).
