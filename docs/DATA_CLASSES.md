# Benchmark data and local data

xferbench keeps two classes of data apart.

| | Benchmark data | Local data |
|---|---|---|
| What | Shared synthetic data (built-in generator presets, later the user-supplied synthetic sample) or public data with recorded terms | Your own data |
| How it is loaded | `--benchmark id@version` (+ `--benchmark-data DIR`), or `xferbench demo` / `xferbench ladder --benchmark` | Only `--local-data PATH/metadata.json`. Legacy `--metadata` outside a `benchmarks/` directory is treated as local and prints a warning |
| Versioning | `BENCHMARK.json`: benchmark_id, version, kind (synthetic/public), licence, source, `dataset_hash`; the hash is verified before every run (mismatch: exit 2) | No manifest; the dataset hash is recorded in run outputs |
| Git | Manifests, metadata and small previews only | Never committed. `.gitignore` covers `local/`, `runs/`, `*.local.*` |
| Output | Any `--out`; suggested `runs/benchmark/<id>@<version>/<run>/` | `--out` outside the repository, or a gitignored path such as `runs/local/<run>/`. A non-ignored path inside a git work tree is refused (exit 2) |
| Labels | `run_manifest.json` `data` block: class, benchmark id, version, kind; report header names the benchmark | `data.data_class = local`; report banner "LOCAL DATA" |
| Reports | Aggregates, slices, failure reasons | Aggregates only. Item, FPG and launch IDs in report.html, summary.md and the CSV/JSON summaries are replaced by salted hashes (`id:xxxxxxxxxx`). `forecasts.parquet` and `artifacts/` keep per-row forecasts in your local output root for your own use |

`xferbench compare` refuses to compare runs from different data classes.

Built-in benchmarks: `xferbench benchmarks` lists them (`synthetic-tiny@1.0.0`, `synthetic-small@1.0.0`). Their
manifests ship inside the package (`src/xferbench/benchmarks/`) so an installed wheel can resolve them;
`benchmarks/` at the repository root holds externally supplied benchmark manifests such as the planned
user synthetic sample.

Synthetic benchmark results demonstrate software behavior only; they are not evidence about real data.
