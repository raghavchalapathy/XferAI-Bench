# Contributing

## Development setup

```bash
bash xferAI_setup.sh --no-demo             # or: uv sync --locked --extra dev (pip fallback: docs/GETTING_STARTED.md Step 0)
.venv/bin/python -m pytest                 # unit, integration and leakage tests (network tests excluded)
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/python -m mypy
```

The `.venv` stays inside the project; nothing is installed globally.

## Ground rules

- **No fake scores.** A method is scored only when its adapter actually executed on the run's population.
  Unimplemented, unlicensed or service-backed methods stay in the registry with a reason and remedy.
- **No leakage.** Methods receive only `TrainingContext` and `OriginContext`. Do not read files, evaluator
  targets or `_synthetic_truth/` from a method. Add a leakage test for any new feature source.
- **No silent substitution.** If a requested recipe cannot run, the run says so (exit code 3); it never swaps
  in a different method.
- **No network** on import, in tests (a session fixture blocks sockets) or in the default demo. Tests that
  truly need the network must be marked `@pytest.mark.network` and are never run by default.
- **No executable metadata.** Metadata stays declarative and strict (`extra="forbid"`).
- Escape every user-supplied label in reports (Jinja autoescape is on; SVG charts escape their text).
- Keep the core dependency set small; heavy libraries go in an optional extra and are imported lazily
  inside the adapter.

- **Evidence-only numbers.** Any benchmark number in docs or on the website is either paper-reported and has
  passed Scout research, Scientist verification and Reviewer review, or comes from a reproducible XferAI-Bench
  run. Never invent or convert results.
- **No proprietary Walmart data.** Public papers that mention Walmart may be cited; their data is not used.
- **Goals are not features.** Explainability and feature traceability are design goals; uncertainty intervals are
  not computed yet ([docs/EVALUATION.md](docs/EVALUATION.md)). Do not describe them as shipped.
- **Lean docs.** Short, scannable text. Site and harness rules: [docs/SITE_AND_HARNESS.md](docs/SITE_AND_HARNESS.md).

## Adding a method

See [docs/EXTENDING.md](docs/EXTENDING.md). A new adapter needs: a `CapabilitySpec` with honest rights
metadata, a declared variant grid, tests on a small synthetic fixture, a registry entry with the right
implementation state, and a regenerated `METHOD_SUPPORT.md`:

```bash
.venv/bin/xferbench list-methods --all --format markdown > METHOD_SUPPORT.md
```

## Releases

1. Update `src/xferbench/_version.py` and `PROGRESS.md`.
2. Run the full checks above and `bash xferAI_setup.sh` from a fresh clone.
3. `python -m build` and install the wheel into a clean environment outside the checkout; run
   `xferbench demo --out <tmp>`.
4. Tag the commit. v0.1.0 is published as a GitHub Release. Publishing to PyPI requires an explicit decision by
   the maintainers; until then do not document `pip install xfer-bench` from PyPI.
