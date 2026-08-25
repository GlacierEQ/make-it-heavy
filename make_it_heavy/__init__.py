# SPDX-License-Identifier: Proprietary
"""Make-It-Heavy package — programmatic, resumable, checkpointed swarm orchestration.

The core swarm modules (agent, memory, orchestrator, innovation_loop, ...) live
at the repository root and use flat imports, matching the existing test suite.
This package groups the v5.0 additions (batch runner, Genius engine, run-state)
so they are importable as ``make_it_heavy.*``.

Imports are lazy (``__getattr__``) so that ``python -m make_it_heavy.batch`` does
not pre-import the batch module and emit a runpy RuntimeWarning.

Note: ``local_agent`` is kept at the repository root (not in this package)
because ``orchestrator.py`` imports it by flat name. It is re-exported here for
callers that prefer the dotted path.
"""

from __future__ import annotations

_LAZY = {
    "batch_main": ("make_it_heavy.batch", "main"),
    "batch_run": ("make_it_heavy.batch", "run"),
    "GeniusOrchestrator": ("make_it_heavy.genius_orchestration", "GeniusOrchestrator"),
    "GeniusOrchestrationConfig": (
        "make_it_heavy.genius_orchestration",
        "GeniusOrchestrationConfig",
    ),
    "RunStateStore": ("make_it_heavy.run_state", "RunStateStore"),
    "list_runs": ("make_it_heavy.run_state", "list_runs"),
}


def __getattr__(name: str):
    if name in _LAZY:
        module_name, attr = _LAZY[name]
        import importlib

        module = importlib.import_module(module_name)
        value = getattr(module, attr)
        globals()[name] = value
        return value
    # local_agent lives at the repo root; expose it lazily too.
    if name in ("LocalAgent", "LocalAgentError", "make_local_agent"):
        try:
            from local_agent import LocalAgent, LocalAgentError, make_local_agent  # noqa: F401
        except ImportError:  # pragma: no cover - only when local tier is unavailable
            raise AttributeError(name)
        value = {"LocalAgent": LocalAgent, "LocalAgentError": LocalAgentError,
                 "make_local_agent": make_local_agent}[name]
        globals()[name] = value
        return value
    raise AttributeError(f"module 'make_it_heavy' has no attribute {name!r}")


__all__ = [
    "batch_main",
    "batch_run",
    "GeniusOrchestrator",
    "GeniusOrchestrationConfig",
    "LocalAgent",
    "LocalAgentError",
    "make_local_agent",
    "RunStateStore",
    "list_runs",
]