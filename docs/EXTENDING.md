# Extending Xfer Benchmark

## Adding a method

A method is any object with four calls (see `xferbench.models.base.Method`):

```text
capabilities() -> CapabilitySpec          # profiles, history needs, features, point statistic, rights
variants() -> list[dict]                  # declared config grid; chosen on validation only
fit(training, inner_validation, config) -> ModelArtifact
predict_batch(requests, origin_context, artifact) -> pandas.DataFrame   # 52 keyed rows per request
```

`training` holds only fit launches whose labels were available by the fit cutoff, plus `context_for(id)` to
build each training launch's own origin context. Outer validation/test labels are never passed.
`origin_context` is an `OriginContext` with origin-valid tables only.

A runnable example that registers a method at runtime, without editing core code:

```python
import numpy as np
from xferbench.models.base import RowResult, expand, stateless_artifact
from xferbench.models.baselines.rates import B0NationalRate
from xferbench.models.registry import RegistryEntry, register_method
from xferbench.orchestration import BenchmarkRunner, RunConfig
from pathlib import Path


class HalfB0:
    """Example: half of the B0 forecast."""

    def __init__(self):
        self.base = B0NationalRate()
        self.spec = self.base.spec.model_copy(
            update={"method_id": "EXT.half_b0", "display_name": "Half B0", "family": "example"}
        )

    def capabilities(self):
        return self.spec

    def variants(self):
        return [{}]

    def fit(self, training, inner_validation, config):
        return stateless_artifact(self.spec, training, config, "no learned parameters", self.variants())

    def predict_batch(self, requests, ctx, artifact):
        out = self.base.predict_batch(requests, ctx, artifact)
        out["point_units"] = out["point_units"] * 0.5
        return out


register_method(RegistryEntry(spec=HalfB0().spec, implementation_state="experimental", factory=HalfB0))
res = BenchmarkRunner(
    RunConfig(
        Path("xb-demo/data/metadata.json"),
        Path("xb-demo/splits.json"),
        "validation",
        Path("ext-run"),
        methods=["EXT.half_b0", "B0"],
    )
).run()
print(res.status, res.out)
```

Rules the runner enforces for every method, built-in or external:

- Exactly 52 rows per request with `request_id`, `horizon_week`, `point_units`, `status`
  (`success`/`fallback`/`failed`) and `reason`. Anything else becomes `failed` rows with a
  `contract_violation` reason; nothing is dropped.
- `success`/`fallback` values must be finite and nonnegative; `failed` values must be null.
- Exceptions in `fit` or `predict_batch` become visible failed rows for that method only.

To ship a method in a separate package, expose a `RegistryEntry` (or a zero-argument callable returning one)
through the `xferbench.methods` entry-point group. Like domain plugins, it is loaded only when its entry-point
name is listed in `XFERBENCH_TRUSTED_PLUGINS`:

```toml
[project.entry-points."xferbench.methods"]
half_b0 = "my_package.methods:half_b0_entry"
```

## Adding an industry (domain plugin)

The engine depends only on `xferbench.domains.base.DomainPlugin`: validation, split building, request and
target frames, origin-context building and a data profile. Retail is the built-in plugin
(`xferbench.domains.retail`). A third-party plugin is exposed through the `xferbench.domains` entry-point
group and is loaded only when its name appears in the environment variable `XFERBENCH_TRUSTED_PLUGINS`
(comma-separated), so installing a package never silently changes what runs.

```toml
[project.entry-points."xferbench.domains"]
energy = "my_package.plugin:EnergyDomain"
```

A small non-retail example plugin with its own tests is planned for Milestone D.
