# XferAI-Bench user manual

Status (2026-10-19; public `main` updated 2026-10-18): the software runs locally end to end on synthetic data. **Real benchmark rankings are pending.** No rights-cleared real benchmark has been run, so synthetic results only test the interface and do not show which method is better. Every command below was checked against `xferbench <command> --help` and run on the synthetic tiny preset.

## 1. Install

Requires Python 3.11+ (checked with 3.11 and 3.13). Everything runs offline: there are no network or paid calls.

```sh
git clone https://github.com/raghavchalapathy/XferAI-Bench.git
cd XferAI-Bench
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/xferbench --help
.venv/bin/xferbench doctor --help     # checks a dependency profile without installing anything
```

Optional extras: LightGBM (needed for M4.lightgbm) and the foundation/neural extras (`foundation`, `timesfm`, `neural`; also `boosting`, `intermittent`; see `pyproject.toml`) are not part of the default install. When an extra is missing, the method is listed with the reason instead of running.

## 2. Quickest path

```sh
xferbench demo --out xb-demo            # generate -> validate -> split -> validation run -> select -> test run -> report
xferbench steps --benchmark synthetic-tiny@1.1.0 --out runs/benchmark/steps-1   # B0..M4 in order, per-scenario WMAPE/Bias
```

## 3. The full pipeline, step by step

```sh
xferbench synth generate --preset tiny --seed 42 --out local/data      # tiny | small | stress; --format parquet|csv|both
xferbench validate --metadata local/data/metadata.json --out local/data_quality.json
xferbench split    --metadata local/data/metadata.json --out local/splits.json
xferbench run      --local-data local/data/metadata.json --splits local/splits.json --stage validation --out runs/local/val-1
xferbench select   --validation-run runs/local/val-1 --out runs/local/selection.json
xferbench run      --local-data local/data/metadata.json --splits local/splits.json --stage test \
                   --selection runs/local/selection.json --out runs/local/test-1
xferbench report   --run runs/local/test-1 --out runs/local/test-1-report.html
```

Points to know:
- `select --out` is a **file** (the frozen selection JSON), not a directory. Pass that file to `run --selection`.
- Run directories are append-only. If a run fails, use a new `--out`, because a failed run can leave a partial directory behind.
- `split` reports the PAIR0-E and PAIR0-N counts and its leakage checks. A test run requires a frozen selection, and variants are chosen on validation only.
- `select --policy <file>` applies a preregistered selection policy. `xferbench init` creates the templates.
- `compare` refuses to rank runs whose data, split, stage, population or metrics differ.

## 4. Methods (retail)

`xferbench list-methods` shows what is implemented, and `--all` shows the whole registry.

| ID | Idea | State |
|---|---|---|
| B0 | households × national season-neutral item rate, flat | implemented |
| B1 | B0 × mean-one national product-type seasonality | implemented |
| B2 | households × the item's raw per-household rate in the k most similar FPGs (no shrinkage) | implemented |
| B3 | B2 shrunk toward the national rate (kappa grid); shown as an extra row, not a step | implemented |
| M1 | households × location propensity P, flat | implemented |
| M2 | M1 × mean-one seasonality S(i,f,w), with no anchor-week division | implemented |
| M3 | user ramp/blend/calibration rule | **config_required**: no recipe has been supplied and no substitute is invented |
| M4.lightgbm | gradient-boosted trees on origin-built features | implemented; needs the `lightgbm` extra |
| FM.chronos2, FM.chronos_bolt, FM.timesfm25, M6.deepar_count | donor-only foundation and neural adapters | experimental; need extras |
| FM.timesfm3, FM.moirai2, FM.tabpfn_ts, EXT.pop | research-only or non-commercial licences | licence_blocked; not in the default path |

Run specific methods with `--methods B0,B1,B2,M1,M2` (explicit list; nothing is silently substituted) or choose a profile with `--profile core|all`.

### Research-only methods

`--allow-research-only` on `xferbench run` opts in to methods whose licences are non-commercial or research-only (Moirai, TabPFN, POP, TimesFM 3). Their outputs are labelled *internal research only*, and these methods are never in the defaults. Blocked benchmark data (for example VISUELLE, or anything tagged `usage_tag=blocked`) is refused with exit 2.

## 5. Benchmark data vs your local data

| | Benchmark data | Local data (yours) |
|---|---|---|
| Flag | `--benchmark id@version` (see `xferbench benchmarks`: currently `synthetic-tiny@1.1.0`, `synthetic-small@1.1.0`), optionally `--benchmark-data <dir>` | `--local-data path/to/metadata.json` |
| Output | suggested `runs/benchmark/<id>@<version>/<run>/` | outside the repo, or a gitignored path such as `runs/local/<run>/`. A non-ignored path inside a git work tree is refused (exit 2) |
| Label | report names the benchmark | report banner **"LOCAL DATA: results on your own data. Not a benchmark result and not shareable as a leaderboard result"**; entity IDs are salted hashes |

The two are never mixed in one run, and `compare` will not rank across them. `runs/` is gitignored. Real data and runs must never be committed. The legacy `--metadata` flag is treated as local data (with a warning) when the path is outside `benchmarks/`.

## 6. Adding a domain (industry) plugin

The engine depends only on `xferbench.domains.base.DomainPlugin`. Retail is the built-in plugin (`xferbench.domains.retail`). To add one, expose it through the `xferbench.domains` entry-point group:

```toml
[project.entry-points."xferbench.domains"]
energy = "my_package.plugin:EnergyDomain"
```

and trust it explicitly: `export XFERBENCH_TRUSTED_PLUGINS=energy`. Installing a package never silently changes what runs. For adding a method, see `docs/EXTENDING.md`. A sample non-retail plugin is *planned* (Milestone D).

## 7. Publishing results

Nothing is published automatically. A result can appear on the XferAI website leaderboard only when:
1. it is a benchmark-data run (never `LOCAL DATA`) on a rights-cleared, versioned benchmark,
2. Reviewer has approved it, and
3. the owner has explicitly authorized publication.

Today no real benchmark exists, so the website leaderboard shows paper-reported results only, and the bench report heading says "real benchmark rankings pending".

## 8. Further reading

`docs/QUICKSTART.md`, `docs/DATA_CLASSES.md`, `docs/REAL_DATA.md`, `docs/METHODS.md`, `docs/EVALUATION.md`, `docs/EXTENDING.md`, `METHOD_SUPPORT.md`, `THIRD_PARTY_NOTICES.md`.
