# AGENTS.md

## Using XferAI-Bench (assistants acting for a user)

Follow [docs/DIY-GettingStarted.md](docs/DIY-GettingStarted.md) step by step.

Rules: Python >= 3.11; everything runs offline after install by default (`XFERBENCH_ALLOW_WEIGHT_DOWNLOAD=1` enables
Hugging Face weight downloads for optional foundation adapters: never set it without the user's approval); never upload or commit the user's data or results
(`local/`, `runs/local/` are gitignored); no telemetry; stop and ask the user where the guide says STOP.

Experiments: `xferbench experiment list|new|run|run-all` (synthetic interface test, not rankings). Research-only
experiments (`exp03_visuelle_gtm`) need `--allow-research-only` and the user's own licence acceptance; never
download VISUELLE or install GTM for the user.

## Contributing to this repo (project agents)

Developing XferAI-Bench itself: install with `python -m pip install -c constraints/core.txt -e ".[dev]"` (or
`uv sync --extra dev`), then run `ruff check src tests`, `ruff format --check src tests`, `python -m mypy`,
`python -m pytest`. See CONTRIBUTING.md.

Project rules (details: [docs/SITE_AND_HARNESS.md](docs/SITE_AND_HARNESS.md)): keep docs lean; every benchmark
number is either paper-reported and has passed the project's research, verification and review roles (Scout,
Scientist, Reviewer), or comes from a reproducible XferAI-Bench run; no proprietary retailer data (public papers
may be cited); explainability and feature traceability are goals, not shipped features.

Repo layout: [configs/](configs/), `data/` (gitignored contents), [data_preparation/](data_preparation/README.md),
[models/](models/README.md), [harness/](harness/README.md), `scripts/` runbooks, [experiments/](experiments/README.md),
[eval/](eval/README.md), [results/](results/README.md). Code lives in `src/xferbench`. Also read
[COLDSTARTHARNESS.md](COLDSTARTHARNESS.md), [MEMORY.md](MEMORY.md), [DATASCIENTIST.md](DATASCIENTIST.md) and
[AIENGINEER.md](AIENGINEER.md).

Glossary: **Builder** writes code, **Scout** researches sources, **Scientist** verifies numbers, **Reviewer**
approves. Harness loop: `--log-lesson` on experiment runs, `xferbench harness triggers`, proposals in
`harness/proposals/`; `xferbench harness apply` adopts a proposal only after an approved Reviewer record.
