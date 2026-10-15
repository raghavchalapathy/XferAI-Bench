"""Domain plugin lookup: built-ins plus explicitly trusted ``xferbench.domains`` entry points."""

from __future__ import annotations

import os
from importlib.metadata import entry_points

from xferbench.domains.base import DomainPlugin

_REGISTERED: dict[str, DomainPlugin] = {}


def register_domain(plugin: DomainPlugin) -> None:
    _REGISTERED[plugin.id] = plugin


def trusted_entry_point_names() -> set[str]:
    """Third-party plugins load only when named in XFERBENCH_TRUSTED_PLUGINS (comma-separated)."""
    raw = os.environ.get("XFERBENCH_TRUSTED_PLUGINS", "")
    return {x.strip() for x in raw.split(",") if x.strip()}


def get_domain(domain_id: str) -> DomainPlugin:
    if domain_id in _REGISTERED:
        return _REGISTERED[domain_id]
    if domain_id == "retail":
        from xferbench.domains.retail.plugin import RetailDomain

        plugin: DomainPlugin = RetailDomain()
        register_domain(plugin)
        return plugin
    if domain_id in trusted_entry_point_names():
        for ep in entry_points(group="xferbench.domains"):
            if ep.name == domain_id:
                plugin = ep.load()()
                register_domain(plugin)
                return plugin
    raise KeyError(
        f"unknown domain plugin '{domain_id}'. Built-in: ['retail']. Third-party plugins must be installed and "
        f"listed in XFERBENCH_TRUSTED_PLUGINS."
    )
