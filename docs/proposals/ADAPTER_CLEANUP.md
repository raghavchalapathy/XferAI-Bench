# Proposal: adapter cleanup list (2026-10-19, Builder; for Reviewer)

Proposal only. It adds no methods and changes no code. Each item names the evidence and a suggested fix.

| # | Entry | Issue | Evidence | Suggested fix |
|---|---|---|---|---|
| 1 | `EXT.pop` | Still registered as a research-only, opt-in adapter, but the Reviewer rejected POP (`rejected_for_admission_leak_unresolvable`) | METHOD_SUPPORT.md row; pins.v5 `research_only_assets.POP` | Mark it rejected in the registry (or remove it) so it cannot be opted into with `--allow-research-only` |
| 2 | `FM.timesfm3` | Registry weight note predates the v4 pins and the Reviewer's TimesFM 3.0 ruling (internal only; publishing outputs blocked) | pins.v5 `v4_pins[timesfm-3.0].review` | Point the entry at the pinned revision `43046b85…` and the ruling; keep it unimplemented until approved |
| 3 | `FM.chronos2`, `FM.chronos_bolt`, `FM.timesfm25`, `M6.deepar_count` | Experimental; the real backends have never run (fake backends in tests only) | METHOD_SUPPORT.md; docs/METHODS.md | Before promoting: an opt-in integration test with locally cached weights, kept out of default CI |
| 4 | `M4.xgboost`, `M4.catboost` | Registered and unimplemented, not covered by the R3/R4 pins | pins.v3/v4 | Pin code and licences first, or drop them from the registry |
| 5 | `M5.hurdle` | METHOD_SUPPORT.md row has an extra `composite` cell, so its columns are shifted by one | METHOD_SUPPORT.md line 23 | Fix the markdown generator for composite entries |
| 6 | METHOD_SUPPORT.md generation | `xferbench list-methods --all --format markdown > METHOD_SUPPORT.md` (CONTRIBUTING.md) drops the hand-written "Research-only" and "Licence-pinned" sections | Seen when regenerating at registry 2026.10.16-e | Have the generator emit those sections, or tell contributors to regenerate only the table |
| 7 | Extras naming | `M4.lightgbm` docs mention both `lightgbm` and the wider `boosting` extra; README's `steps` paragraph says `boosting` | README.md, docs/METHODS.md | Name `lightgbm` as the single documented extra for M4.lightgbm |
| 8 | `REF.*` | Warm-reference methods cannot run on the cold C0 board (`unsupported_history`) | METHOD_SUPPORT.md | Keep them, but list them in a separate "reference only" section so they don't look like pending work |
| 9 | Scout candidates chronos-t5, lag-llama, moment, toto (Open-Base-1.0), sundial, ttm (r2), timegpt | Licence rulings done: the six models are PUBLIC-OK at licence level; TimeGPT BLOCKED (no use without owner authorization). This is not a rights audit and authorises no download or run | `factory/inbox/reviewer/pins-v5-review-20261019/review.json` (sha256 d9bf549f…1cfe), which also approves pins.v5 | Still no registry entries until an adapter is proposed and reviewed; TimeGPT stays out |
