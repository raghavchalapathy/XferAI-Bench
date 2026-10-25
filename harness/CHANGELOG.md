# Best-practices changelog

## v1 - 2026-10-24

Seed from the owner brief (replaces harness/RULES.md).

## v2 - 2026-10-24

proposal `polars-asof-parity-20261024` by builder: Any pandas-to-Polars swap keeps the old code as a reference and ships a parity test plus a benchmark.. Approved by reviewer. Set: ['polars_swap_parity']; removed: [].

### Correction to v2 (2026-10-25, Reviewer A-1, A-2; no rule changed, BEST_PRACTICES.v2.yaml untouched)

- A-2: the v2 entry above should read "... plus a benchmark. Approved by reviewer." (one period). The entry is left as written because this log is append-only.
- A-1: per-rule sources are listed in `harness/RULE_SOURCES.md` (BEST_PRACTICES files are written only by `harness apply`, so no comments were added to them).

## v3 - 2026-10-25

proposal `installer-ux-20261025` by builder: First-run installer scripts (xferAI_setup.sh/.ps1) follow one safety and UX bar; every clause below is checked by tests/test_installer_rules.py (static checks of the scripts, the setup tests and ci.yml).. Approved by reviewer. Set: ['installer_checks', 'installer_env', 'installer_safety', 'installer_ux']; removed: [].

- H-A2: the v3 entry above should read "... the setup tests and ci.yml). Approved by reviewer." (one period). The "..", like A-2 for v2, comes from `harness apply` joining a summary that already ends in a period; the entry is left as written because this log is append-only. A generator fix will go through its own review.
- H-A1: the rule test is committed at tests/test_installer_rules.py; its two pre-apply checks (clash with v2, v3 preview diff) are dropped now that v3 is current; strict-skips core stays clean.
