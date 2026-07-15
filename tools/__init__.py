"""Explicit, policy-gated registry for built-in agent tools."""

import logging
from typing import Dict, Iterable, Optional, Type

from .base_tool import BaseTool
from .calculator_tool import CalculatorTool
from .read_file_tool import ReadFileTool
from .search_tool import SearchTool
from .task_done_tool import TaskDoneTool
from .write_file_tool import WriteFileTool

logger = logging.getLogger(__name__)

BUILTIN_TOOL_REGISTRY: Dict[str, Type[BaseTool]] = {
    "search_web": SearchTool,
    "calculate": CalculatorTool,
    "read_file": ReadFileTool,
    "write_file": WriteFileTool,
    "mark_task_complete": TaskDoneTool,
}
DEFAULT_TOOL_ALLOWLIST = frozenset(
    {"search_web", "calculate", "read_file", "mark_task_complete"}
)
MUTATING_TOOLS = frozenset({"write_file"})


def discover_tools(
    config: Optional[dict] = None,
    silent: bool = False,
    allowlist: Optional[Iterable[str]] = None,
) -> Dict[str, BaseTool]:
    """Load only explicitly registered and allowed tools.

    Tool modules are never discovered by scanning the directory. Mutating tools
    require an allowlist entry and tools.mutation_enabled set to true.
    """
    config = config or {}
    tool_config = config.get("tools", {})
    requested = set(
        allowlist
        if allowlist is not None
        else tool_config.get("allowlist", DEFAULT_TOOL_ALLOWLIST)
    )
    unknown = requested.difference(BUILTIN_TOOL_REGISTRY)
    if unknown:
        raise ValueError(f"Unknown tools in allowlist: {sorted(unknown)}")

    mutation_enabled = tool_config.get("mutation_enabled") is True
    loaded: Dict[str, BaseTool] = {}
    for name in BUILTIN_TOOL_REGISTRY:
        if name not in requested:
            continue
        if name in MUTATING_TOOLS and not mutation_enabled:
            logger.warning("Mutating tool %s denied: mutation opt-in is disabled", name)
            continue
        loaded[name] = BUILTIN_TOOL_REGISTRY[name](config)

    if not silent:
        logger.info("Loaded policy-approved tools: %s", sorted(loaded))
    return loaded
