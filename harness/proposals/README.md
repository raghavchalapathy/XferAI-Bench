# Proposals

Builder or Scout writes `<id>.yaml` (see `TEMPLATE.yaml.example`). A Reviewer adds the `review:` block. Then `xferbench harness apply --proposal harness/proposals/<id>.yaml` checks the guardrails, writes `BEST_PRACTICES.v<N+1>.yaml` and appends to `CHANGELOG.md`.
