# AGENTS.md

Coding assistants setting up or running XferAI-Bench on a user's own data: follow
[docs/DIY-GettingStarted.md](docs/DIY-GettingStarted.md) step by step.

Rules: Python >= 3.11; everything runs offline after install by default (`XFERBENCH_ALLOW_WEIGHT_DOWNLOAD=1` enables
Hugging Face weight downloads for optional foundation adapters: never set it without the user's approval); never upload or commit the user's data or results
(`local/`, `runs/local/` are gitignored); no telemetry; stop and ask the user where the guide says STOP.

Developing XferAI-Bench itself: `python -m pip install -c constraints/core.txt -e ".[dev]"`, then
`ruff check src tests`, `ruff format --check src tests`, `python -m mypy`, `python -m pytest`. See CONTRIBUTING.md.

Project rules (details: [docs/SITE_AND_HARNESS.md](docs/SITE_AND_HARNESS.md)): keep docs lean; every benchmark
number is either paper-reported and passed Scout research, Scientist verification and Reviewer review, or comes
from a reproducible XferAI-Bench run; no proprietary Walmart data (public papers may be cited); explainability and
feature traceability are goals, not shipped features.

Repo layout: [configs/](configs/), `data/` (gitignored contents), [data_preparation/](data_preparation/README.md),
[models/](models/README.md), [harness/](harness/README.md), `scripts/` runbooks, [experiments/](experiments/README.md),
[eval/](eval/README.md), [results/](results/README.md). Code lives in `src/xferbench`. Also read
[COLDSTARTHARNESS.md](COLDSTARTHARNESS.md), [MEMORY.md](MEMORY.md), [DATASCIENTIST.md](DATASCIENTIST.md) and
[AIENGINEER.md](AIENGINEER.md). Experiments: `xferbench experiment --config experiments/<id>/config.yaml --out eval/<id>`
(synthetic interface test, not rankings).
Harness loop (Builder/Scout/Reviewer): `--log-lesson` on experiment runs, `xferbench harness triggers`,
proposals in `harness/proposals/`, adoption only via `xferbench harness apply` after an approved Reviewer record.
