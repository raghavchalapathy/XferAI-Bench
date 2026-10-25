# exp02_synthetic_chronos_zero_shot

**Synthetic interface test, not a ranking. NOT A DAY-ZERO RESULT.** Zero-shot foundation models are not day-zero
methods for XferAI; never present this experiment's output as a day-zero result.

- **Paper(s):** Ansari et al. (2024). *Chronos: Learning the Language of Time Series.* TMLR. <https://arxiv.org/abs/2403.07815>
- **Data:** synthetic preset `tiny`, seed 42 (`data.flavour: synthetic`); nothing downloaded.
- **Models:** B0, B2, B3. Optional: `FM.chronos2` needs the `foundation` extra **and** reviewed weights
  (`XFERBENCH_ALLOW_WEIGHT_DOWNLOAD=1` after review); otherwise it is listed as `config_required`.
- **Runtime:** `runtime.backend: polars` (default) or `spark`.
- **Run:** `xferbench experiment run exp02_synthetic_chronos_zero_shot` -> `experiments/exp02_synthetic_chronos_zero_shot/runs/<UTC timestamp>/`
