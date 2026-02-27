"""Plugin discovery and loading for autodev extensibility.

Scans a directory for ``.py`` files with a ``register()`` entry point.
Each plugin's ``register()`` function is called as a side effect, allowing
it to call ``register_validator()``, ``register_tool()``, or
``register_role()`` to extend the system.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("autodev")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PluginSpec:
    """Metadata for a discovered plugin."""

    name: str  # derived from filename stem
    path: str  # absolute path to .py file
    enabled: bool = True


@dataclass
class PluginLoadResult:
    """Outcome of loading a single plugin."""

    spec: PluginSpec
    ok: bool
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_plugins(
    plugin_dir: str,
    enabled_list: List[str] | None = None,
) -> List[PluginSpec]:
    """Scan *plugin_dir* for ``.py`` files that can serve as plugins.

    Args:
        plugin_dir: Absolute path to directory containing plugin ``.py`` files.
        enabled_list: If provided, only plugins whose name is in this list
            are marked enabled.  If ``None``, all discovered plugins are
            enabled.

    Returns:
        List of :class:`PluginSpec`, one per discovered ``.py`` file.
    """
    specs: List[PluginSpec] = []
    if not os.path.isdir(plugin_dir):
        return specs

    for entry in sorted(os.listdir(plugin_dir)):
        if not entry.endswith(".py") or entry.startswith("_"):
            continue
        name = entry[:-3]  # strip .py
        full_path = os.path.join(plugin_dir, entry)
        if not os.path.isfile(full_path):
            continue

        enabled = True if enabled_list is None else (name in enabled_list)
        specs.append(PluginSpec(name=name, path=full_path, enabled=enabled))

    return specs


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_plugin(plugin_spec: PluginSpec) -> PluginLoadResult:
    """Load and execute a single plugin's ``register()`` entry point.

    The ``register()`` function is called with no arguments.  It is expected
    to call registration functions (``register_validator``, ``register_tool``,
    ``register_role``) as side effects.

    Returns:
        :class:`PluginLoadResult` indicating success or failure.
    """
    if not plugin_spec.enabled:
        return PluginLoadResult(spec=plugin_spec, ok=True, error="disabled")

    try:
        mod_spec = importlib.util.spec_from_file_location(
            f"autodev_plugin_{plugin_spec.name}",
            plugin_spec.path,
        )
        if mod_spec is None or mod_spec.loader is None:
            return PluginLoadResult(
                spec=plugin_spec,
                ok=False,
                error="Could not create module spec",
            )

        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)  # type: ignore[union-attr]

        register_fn = getattr(module, "register", None)
        if not callable(register_fn):
            return PluginLoadResult(
                spec=plugin_spec,
                ok=False,
                error="No callable register() found",
            )

        register_fn()
        return PluginLoadResult(spec=plugin_spec, ok=True)

    except Exception as exc:
        return PluginLoadResult(
            spec=plugin_spec,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )


def load_all_plugins(
    plugin_dir: str,
    enabled_list: List[str] | None = None,
) -> List[PluginLoadResult]:
    """Discover and load all plugins from a directory.

    Convenience wrapper combining :func:`discover_plugins` and
    :func:`load_plugin`.
    """
    specs = discover_plugins(plugin_dir, enabled_list=enabled_list)
    return [load_plugin(ps) for ps in specs]
