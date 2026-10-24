# MEMORY.md

Durable project decisions (append-only, dated).

- 2026-10-24: Repo restructured into configs/, data/, data_preparation/, models/, harness/, scripts/, experiments/, eval/, results/. Code stays in `src/xferbench`. Old `xferbench.methods.*` and `xferbench.features.*` imports are aliased.
- 2026-10-24: Polars and PyYAML are core dependencies. PySpark stays an optional extra.
- 2026-10-24: Excluded methods: POP (rejected), VISUELLE (blocked), TimeGPT (dropped), Moirai and TimesFM 3.0 (non-commercial).
- Experiments run on synthetic data only. Their outputs are interface tests, not rankings.
- 2026-10-24: The harness is machine-checked. BEST_PRACTICES.v1.yaml is the seed. Rule changes go only through Reviewer-approved proposals (`xferbench harness apply`).
- PySpark/SynapseML stay optional extras; no weight downloads by default.
