"""autodev — public API for extending the pipeline via plugins."""

from .validators import (
    register_validator,
    get_validator_definition,
    registered_validator_names,
    list_all_validators,
)
from .tools import register_tool, get_tool_definition, registered_tool_names
from .roles import register_role, get_role, registered_role_names, RoleSpec
from .plugin import (
    discover_plugins,
    load_plugin,
    load_all_plugins,
    PluginSpec,
    PluginLoadResult,
)
from .run_trace import RunTrace, EventType, TraceEvent, PhaseTimings
from .progress import ProgressEmitter
from .cli_progress import make_cli_progress_callback

__all__ = [
    # Validators
    "register_validator",
    "get_validator_definition",
    "registered_validator_names",
    "list_all_validators",
    # Tools
    "register_tool",
    "get_tool_definition",
    "registered_tool_names",
    # Roles
    "register_role",
    "get_role",
    "registered_role_names",
    "RoleSpec",
    # Plugins
    "discover_plugins",
    "load_plugin",
    "load_all_plugins",
    "PluginSpec",
    "PluginLoadResult",
    # Observability
    "RunTrace",
    "EventType",
    "TraceEvent",
    "PhaseTimings",
    # Progress
    "ProgressEmitter",
    "make_cli_progress_callback",
]
