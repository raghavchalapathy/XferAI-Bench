"""Method adapters grouped by model family, plus the versioned registry.

Families (cold-start only): ``stats``, ``analogs``, ``affinity_propensity``, ``machine_learning``,
``deep_learning``, ``graph_models``, ``foundation_models``. Every method implements
:class:`xferbench.models.base.Method` and is listed in :mod:`xferbench.models.registry`.
Heavy libraries are imported lazily so ``import xferbench.models`` stays core-only.
"""
