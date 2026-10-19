# AGENTS.md

Coding assistants setting up or running XferAI-Bench on a user's own data: follow
[docs/DIY-GettingStarted.md](docs/DIY-GettingStarted.md) step by step.

Rules: Python >= 3.11; everything runs offline after install; never upload or commit the user's data or results
(`local/`, `runs/local/` are gitignored); no telemetry; stop and ask the user where the guide says STOP.

Developing XferAI-Bench itself: `python -m pip install -c constraints/core.txt -e ".[dev]"`, then
`ruff check src tests`, `ruff format --check src tests`, `python -m mypy`, `python -m pytest`. See CONTRIBUTING.md.
