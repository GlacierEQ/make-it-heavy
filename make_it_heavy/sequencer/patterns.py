"""
sequencer.patterns — the per-repo enhancement pattern catalog.

Each pattern declares *when it applies* (not just what it does). The
sequencer's plan builder reads the *profile* of a target repo and only
proposes patterns whose ``when_to_use`` matches. This is what keeps
the work from becoming a cookie-cutter template applied to every repo.

Adding a new pattern
--------------------
1. Subclass :class:`Pattern` and fill in every field.
2. Register it in :data:`PATTERNS` below.
3. The next call to :func:`make_it_heavy.sequencer.discover` will see it
   in the proposal table; the plan builder will score it against the
   profile and include it if it actually fits.

Do not write patterns that always fire — every pattern must declare the
profile signals that justify it. The sequencer's anti-cookie-cutter gate
penalises patterns that fire on too many distinct profiles.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional


@dataclass(frozen=True)
class Pattern:
    """A reusable enhancement pattern, tagged with the profile that justifies it."""

    id: str
    name: str
    summary: str
    # The profile signals that must be present for the pattern to be considered.
    # Each clause is a key into the repo profile dict; the pattern matches when
    # all clauses are satisfied (logical AND across the list).
    when_profile: tuple = ()
    # A short human description of what changes in the repo when this fires.
    actions: tuple = ()
    # What tests the pattern adds (so we can plan coverage).
    tests_added: tuple = ()
    # The anti-cookie-cutter signal: a short natural-language description of
    # what is *unique* to this pattern (used by the gate to detect templating).
    differentiator: str = ""
    # Rough cost. Used for budget hints, not hard limits.
    est_files_touched: int = 1
    est_loc_delta: int = 50


# ── The catalog. Start small; every pattern must earn its slot. ─────────────


PATTERNS: tuple = (
    Pattern(
        id="api-surface-completion",
        name="API surface completion",
        summary=(
            "When a module's public names are documented in __init__.py docstrings "
            "or skill SKILL.md but not actually importable, re-export the missing "
            "names (with backward-compat aliases for the old ones)."
        ),
        when_profile=(
            "has_python_src",
            "has_module_init",
        ),
        actions=(
            "compare docstring/skill names vs __all__ + live import",
            "add missing re-exports (keep old names as aliases)",
            "test that every documented name is importable",
        ),
        tests_added=("public_api_surface_match",),
        differentiator=(
            "only fires when docstring says X but __all__ has Y. "
            "Distinct from missing-CLI because the API already exists in spirit."
        ),
        est_files_touched=1,
        est_loc_delta=20,
    ),
    Pattern(
        id="shell-cli-bridge",
        name="Shell CLI bridge",
        summary=(
            "When a Python package has no `__main__.py` but the runtime cache "
            "or persistence layer is referenced from external tools, add a "
            "shell entry point that exposes the layer with argparse."
        ),
        when_profile=(
            "has_python_src",
            "has_persistent_state",
            "no_main_module",
        ),
        actions=(
            "design subcommand surface (save/load/compact/stats/...)",
            "implement __main__.py with argparse + per-user guards",
            "add subprocess-level integration test that exercises the log path",
        ),
        tests_added=("cli_subprocess_roundtrip", "cli_empty_user_guard"),
        differentiator=(
            "fires only when the package is referenced from outside Python "
            "(persistent state, MCP, or skill SKILL.md promises a CLI). "
            "Distinct from API surface — this is a new entry point, not a re-export."
        ),
        est_files_touched=2,
        est_loc_delta=200,
    ),
    Pattern(
        id="log-path-coverage",
        name="Log path coverage",
        summary=(
            "When a module declares a logging path but the log file is "
            "empty in the wild, add tests that exercise the writing code path "
            "so the log file becomes non-empty at test time."
        ),
        when_profile=(
            "has_python_src",
            "has_log_path",
            "log_file_present",
            "log_file_empty",
        ),
        actions=(
            "identify the code path that should have written the log",
            "add a test that calls that path and asserts the log grew",
            "fix the code path if the log write was being swallowed",
        ),
        tests_added=("log_writes_on_<event>",),
        differentiator=(
            "fires only when a log file is declared but empty. Distinct from "
            "observability work — we are wiring the existing log, not adding one."
        ),
        est_files_touched=1,
        est_loc_delta=30,
    ),
    Pattern(
        id="orphan-retirement",
        name="Orphan retirement",
        summary=(
            "When a sibling state file (e.g. a stale .db next to a current "
            ".json) is no longer read by the codebase, retire it by renaming "
            "to .legacy so the bytes are preserved but the live path is clean."
        ),
        when_profile=(
            "has_persistent_state",
            "has_sibling_orphan",
        ),
        actions=(
            "verify the orphan is not read or written by the current code",
            "rename orphan to .legacy in place",
            "document the retirement in the active code's docstring",
        ),
        tests_added=("orphan_not_in_live_path",),
        differentiator=(
            "fires only when the code no longer references the file. Distinct "
            "from migration — we are not converting the data, only acknowledging "
            "the legacy is dead."
        ),
        est_files_touched=1,
        est_loc_delta=5,
    ),
    Pattern(
        id="docs-refresh-and-guard",
        name="Docs refresh + consistency guardrail",
        summary=(
            "When the project's user-authored docs (STATUS, ROADMAP, "
            "PROOF_GATES, CANONICAL) have stale dates or counts, refresh the "
            "facts and add a test that asserts the docs stay honest."
        ),
        when_profile=(
            "has_user_docs",
            "docs_drift_detected",
        ),
        actions=(
            "audit every doc for dated facts and stale counts",
            "refresh dates/counts (preserving the user's prose framing)",
            "add a docs_consistency test that fails loudly on future drift",
        ),
        tests_added=("docs_consistency_guard",),
        differentiator=(
            "fires only when docs_drift_detected is true (dated facts found). "
            "Distinct from doc-writing — we are refreshing existing user prose, "
            "not authoring new docs."
        ),
        est_files_touched=4,
        est_loc_delta=80,
    ),
    Pattern(
        id="cross-repo-bridge",
        name="Cross-repo bridge",
        summary=(
            "When repo A has a runtime feature and repo B has a memory/lifecycle "
            "feature that the swarm would benefit from combining, add a thin "
            "bridge module in B that lazy-imports A and exposes one "
            "well-named function."
        ),
        when_profile=(
            "has_python_src",
            "has_sibling_repo_with_runtime",
            "runtime_state_overlap",
        ),
        actions=(
            "design the bridge's one public function",
            "lazy-import the sibling as an optional dep (BridgeDependencyError)",
            "add tests covering the happy path + the dependency-missing path",
        ),
        tests_added=("bridge_roundtrip", "bridge_dependency_missing"),
        differentiator=(
            "fires only when there is genuine runtime overlap with a sibling. "
            "Distinct from refactor — the bridge is a new file, not a rewrite."
        ),
        est_files_touched=2,
        est_loc_delta=120,
    ),
    Pattern(
        id="catalog-registration",
        name="Catalog registration",
        summary=(
            "When a repo's capabilities are not yet declared in the estate's "
            "meta-layer (monolith) catalog, register them with a clear state "
            "(PENDING_INITIAL_REGISTER is honest for not-yet-pushed work)."
        ),
        when_profile=(
            "sibling_has_meta_catalog",
            "not_in_catalog",
        ),
        actions=(
            "find the appropriate catalog file (core_mesh / mega_skills / etc.)",
            "add a well-formed entry with current head_commit + capabilities list",
            "add a test that fails if a future edit drops the entry",
        ),
        tests_added=("catalog_registration_pin",),
        differentiator=(
            "fires only when the repo is not in the catalog and the catalog is "
            "the right escalation surface. Distinct from the cross-repo bridge — "
            "this is metadata, not a runtime integration."
        ),
        est_files_touched=2,
        est_loc_delta=40,
    ),
    Pattern(
        id="swarm-integration-test",
        name="Swarm integration test",
        summary=(
            "When a repo has runtime state (cache, log, db) that should be "
            "exercised by a small in-process script, add a live smoke test "
            "that proves the end-to-end path works against the real filesystem."
        ),
        when_profile=(
            "has_persistent_state",
            "smoke_unproven",
        ),
        actions=(
            "design the minimal in-process script that proves the path",
            "either commit the script as a test or wire it into CI",
            "document the smoke in EVIDENCE.md so receipts are durable",
        ),
        tests_added=("live_<feature>_smoke",),
        differentiator=(
            "fires only when the persistent state has never been touched live. "
            "Distinct from log-path-coverage — this is end-to-end, not just a "
            "single log line."
        ),
        est_files_touched=1,
        est_loc_delta=40,
    ),
)


def all_patterns() -> List[Pattern]:
    """Return the full catalog as a list (deterministic order)."""
    return list(PATTERNS)


def get_pattern(pattern_id: str) -> Optional[Pattern]:
    for p in PATTERNS:
        if p.id == pattern_id:
            return p
    return None
