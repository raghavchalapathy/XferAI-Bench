# harness/ - recursive self-improvement, as files plus code (`xferbench.harness`)

| file | role |
|---|---|
| `BEST_PRACTICES.v<N>.yaml` | Versioned rules. The highest N is current. Never edit by hand; adopt a proposal instead. |
| `CHANGELOG.md` | One entry per adopted version. |
| `lessons.jsonl` | Append-only, schema-validated lessons. Each has what changed, status, run-manifest path and sha256, evidence path, synthetic or real, and objective. |
| `proposals/` | Builder/Scout proposals. A Reviewer adds `review:`. |
| `watch.yaml` | Revisit sources: papers (`status: new` is due). |
| `PROTECTED_HASHES.json` | sha256 of the protected evaluator files. |

Loop:

1. Run with logging: `xferbench experiment ... --log-lesson "what changed"`.
2. Check what is due: `xferbench harness triggers`. This reports a new paper, a regression versus the last accepted lesson, a failed last run, or a stale review (more than `review_every_days`). It exits 1 when something is due.
3. Builder or Scout writes `proposals/<id>.yaml`. A Reviewer records `review: {decision: approved}`.
4. Check, then adopt: `xferbench harness check --proposal ...` and `xferbench harness apply --proposal ...`. Adopting writes `BEST_PRACTICES.v<N+1>.yaml` and a CHANGELOG entry.

Guardrails (tested in `tests/unit/test_harness.py` and the Reviewer's `tests/review/`). They are local checks that
make mistakes hard; they are not a security boundary against someone with write access to the repo:

- Protected paths: `src/xferbench/evaluation/`, `src/xferbench/scalable_eval/`, `harness/PROTECTED_HASHES.json`,
  `tests/unit/test_scalable_eval.py` and `tests/review/`. Paths are normalised (`..`, backslashes, case,
  symlinks) before the check. `PROTECTED_HASHES.json` pins the evaluator, scalable_eval and the parity test.
- `touches` is checked against the real change (git diff against `HEAD` plus untracked files) when the repo is a
  git checkout: protected or undeclared changed files are refused.
- Results need an existing run manifest whose sha256 matches, plus existing evidence.
- A synthetic result must carry an allow-listed label ("not a ranking") and make no ranking claim.
- Approval needs a Reviewer id (`reviewer` or `reviewer-<name>`) different from the author, a `review_file`
  and its `review_sha256`. Builder, Scout, Engineer and the author cannot approve. Nothing is adopted twice.
