# Reviewer regression tests

Copied verbatim from `factory/inbox/reviewer/xferbench-restructure-review-20261024/` (review.md sha256
c1767c9f42ac6de53a8c613b71be65bf2eceb5a12682fbb9b5f90af818e93de5). Do not edit; they are excluded from ruff.

| file | sha256 |
|---|---|
| test_review_harness.py | 07252b7d650b6716ff14beb263357ca34302f44d2d5fdadd342755a9c35cea64 |
| adv.py | f734c76739373b33bb5a5693f09e6c61635cc55830602799856017ff2b3a537e |

`test_review_adv.py` runs adv.py (Polars; Spark too when pyspark + Java are present) and asserts every case
matches the protected evaluator. `conftest.py` marks one Reviewer test xfail(strict, raises=ValidationError):
`test_self_approval` can only pass if self-approval is accepted; the fix rejects it at construction. Flagged
for the Reviewer rather than edited. `test_reviewer_files_unmodified` (tests/unit/test_harness.py) pins the hashes.
