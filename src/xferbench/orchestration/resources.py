"""Measured wall time and Python-heap peak memory (tracemalloc; includes NumPy buffers)."""

from __future__ import annotations

import platform
import sys
import time
import tracemalloc
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version


@dataclass
class Measurement:
    seconds: float = 0.0
    peak_bytes: int = 0


@contextmanager
def measure(enabled: bool = True) -> Iterator[Measurement]:
    m = Measurement()
    started_here = False
    if enabled and not tracemalloc.is_tracing():
        tracemalloc.start()
        started_here = True
    if enabled:
        tracemalloc.reset_peak()
    t0 = time.perf_counter()
    try:
        yield m
    finally:
        m.seconds = time.perf_counter() - t0
        if enabled:
            m.peak_bytes = tracemalloc.get_traced_memory()[1]
            if started_here:
                tracemalloc.stop()


def max_rss_mib() -> float | None:
    if sys.platform == "win32":  # no `resource` module on Windows (and none in its type stubs)
        return None
    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
    except (ImportError, OSError):
        return None


CORE_PACKAGES = ("numpy", "pandas", "pyarrow", "pydantic", "typer", "jinja2")


def package_versions(names: tuple[str, ...] = CORE_PACKAGES) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for n in names:
        try:
            out[n] = version(n)
        except PackageNotFoundError:
            out[n] = None
    return out


def hardware() -> dict:
    import os

    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "accelerator": "none used (CPU execution)",
    }
