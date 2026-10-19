# Changelog

## 0.1.0 (2026-10-19)

First public release, tagged `v0.1.0` on `17f8ddc`. Benchmark rankings are pending: no rights-cleared real
benchmark has been run. The bundled synthetic data only tests that the software works.

### Added
- Cold item-location pair (PAIR0) benchmark with PAIR0-E and PAIR0-N always scored separately (0.5/0.5).
- Baselines B0, B1, B2 (households x similar-FPG per-household rate, no shrinkage) and B3 (B2 shrunk toward the
  national rate, extra row); business rules M1, M2; M3 as config_required (never substituted).
- M4.lightgbm (optional `lightgbm` extra).
- Experimental, licence-pinned donor-prior adapters FM.chronos2, FM.chronos_bolt, FM.timesfm25 and M6.deepar_count,
  tested with fake backends only and not Reviewer-recommended for PAIR0.
- Shared retail hierarchy: rates item -> subcategory -> product type, seasonality category -> product type;
  levels recorded per forecast and in the run manifest.
- Origin-scoped contexts with leakage tests, chronological splits, validation-only selection, and an HTML report.
- Synthetic benchmarks `synthetic-tiny@1.1.0` and `synthetic-small@1.1.0`.
- Benchmark data and local data kept apart (LOCAL DATA banner, salted IDs, gitignored output paths).
- Licence gates: research-only entries need `--allow-research-only`; blocked datasets are refused.
- Run manifests record the git commit and dirty flag.
- Docs: GETTING_STARTED, DIY-GettingStarted (for coding assistants), AGENTS.md, llms.txt.

### Changed
- TimeGPT dropped before release (paid API; no use without owner authorization).

### Fixed
- Windows CI: mypy `resource` stub issue; explicit UTF-8 text I/O; posix git pathspecs; no symlinks in tests.
- `run --selection <dir>` gives a clear error with exit 2.

### Not included
- No PyPI package; install from a clone or a locally built wheel.
- No real-data rankings and no day-zero claims.
