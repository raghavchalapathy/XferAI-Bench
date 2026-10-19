# Proposal: release tag plan v0.1.0 (2026-10-19, Builder; for Reviewer and owner)

**Status:** `v0.1.0` was tagged on `17f8ddc` on 2026-10-19 (annotated tag, 10:40 AM PT) under the owner's go-ahead
(GitHub API: `refs/tags/v0.1.0` -> tag object `acccc5fd` -> commit `17f8ddcce94d4c692a0b346cc99d02614e70392f`).
Nothing is published to PyPI. A GitHub Release is drafted in [docs/releases/v0.1.0.md](../releases/v0.1.0.md) and has not been created.
Tag created per ColdStart Lead's record: ColdStart Lead created it using the Builder commit identity (`ColdStart-Builder-engineer <engineer@coldstart.local>`) because the box had no git identity configured. Tagger date on the annotated tag object `acccc5fd` (GitHub API): 2026-10-19 10:40:05 AM PT (2026-10-19T17:40:05Z UTC). The tag is unchanged; it has not been rewritten.
The plan below is kept as the record of the gates.
Each step that is visible outside this machine needs the owner's explicit approval.

## Scope of v0.1.0

- Version: `src/xferbench/_version.py` is already `0.1.0`; the distribution is `xfer-bench` and the CLI is `xferbench`.
- Content: core baselines B0-B3, business rules M1/M2, M3 (config_required), M4.lightgbm (optional extra),
  experimental donor-prior adapters (fake-backend tested), evaluator, split/selection, HTML report, shared
  retail hierarchy, synthetic benchmarks `synthetic-tiny@1.1.0` and `synthetic-small@1.1.0`, docs
  (GETTING_STARTED, DIY-GettingStarted, AGENTS.md, llms.txt).
- Explicitly not in scope: real-data rankings (pending), PyPI publication, research-only adapters by default.

## Gates (all must hold on the tagged commit)

1. Reviewer approval of every commit since the last approved base, and owner sign-off for protected-contract changes.
2. GitHub Actions `ci` green on ubuntu/macos/windows x Python 3.11/3.13 for that exact commit.
3. A fresh clone passes `ruff check`, `ruff format --check`, `mypy` and `pytest`; `python -m build` produces
   `xfer_bench-0.1.0-py3-none-any.whl` and the sdist; the wheel installs outside the checkout and
   `xferbench demo` runs.
4. docs/GETTING_STARTED.md and docs/DIY-GettingStarted.md re-tested end to end on 3.11 and 3.13 (including the
   offline wheelhouse path).
5. PROGRESS.md entry and a CHANGELOG section for 0.1.0; THIRD_PARTY_NOTICES.md current.

## Steps (after approval)

```bash
git tag -a v0.1.0 -m "xfer-bench 0.1.0" <approved-sha>      # local annotated tag
git push origin v0.1.0                                      # ONLY with the owner's explicit approval
```

Optionally, a GitHub Release with the wheel and sdist attached, release notes copied from the CHANGELOG, and
the status line "benchmark rankings pending; synthetic data tests the software only". This also needs the
owner's approval.

## Not planned

- PyPI upload (`twine upload`) needs a separate decision: the package name, an account and a trusted-publisher
  setup. Until then the docs keep "not on PyPI; install from a clone".
