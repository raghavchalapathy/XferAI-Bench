# Benchmark data (shared, versioned, hashed)

Built-in benchmark manifests ship inside the package at `src/xferbench/benchmarks/<id>/<version>/BENCHMARK.json`
so an installed wheel can resolve `--benchmark synthetic-tiny@1.0.0`. A benchmark directory outside the package
(for example `benchmarks/user-synthetic-sample/1.0.0/`) can be passed as `--benchmark PATH/BENCHMARK.json`.

Benchmark data is synthetic or public data with recorded licence and `dataset_hash`. Large tables are regenerated
(synthetic) or fetched by the user; they are not committed. Your own data is **local data**: see
`docs/DATA_CLASSES.md` and use `--local-data`.
