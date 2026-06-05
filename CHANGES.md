# CHANGES.md — Pro-Make-It-Heavy / AEON-777
## GlacierEQ Engineering Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2.0.0] — 2026-06-05 — GlacierEQ Humanized Engineering Pass

**Committed by:** Casey del Carpio Barton / GlacierEQ  
**Scope:** Full production-grade hardening of core runtime files  
**Files changed:** `orchestrator.py`, `agent.py`, `make_it_heavy.py`, `main.py`, `README.md`, `CHANGES.md`

### Added

#### Proprietary Headers (all .py files)
- `# SPDX-License-Identifier: Proprietary` header on every touched `.py` file
- Copyright notice: `Casey del Carpio Barton / GlacierEQ — All Rights Reserved`

#### Type Hints
- Full PEP 484 type annotations on **every** function and method signature
- Return types explicitly declared (`-> str`, `-> None`, `-> Dict[str, Any]`, etc.)
- Complex container types use `typing` imports (`List`, `Dict`, `Optional`)

#### Rich Docstrings (Google-style)
- Every class and function now has a multi-line docstring explaining:
  - **WHAT** it does
  - **WHY** it exists (design rationale)
  - **Args** and **Returns** sections
  - Error conditions and edge cases documented

#### Structured Logging (replaces all `print()`)
- `logging.getLogger(__name__)` at module level in all files
- All debug/info/warning/error events use `logger.*()` — zero bare `print()` in library code
- CLI-facing messages (user-visible output) remain as `print()` by design
- Log format includes timestamps in `main.py` for auditability

#### Custom Exception Types
- `ConfigurationError` — bad/missing config keys
- `LLMCallError` — OpenRouter API failures (timeout, HTTP error, connection error)
- `ToolExecutionError` — tool invocation failures
- `AgentExecutionError` — agent-level failures
- `SynthesisError` — aggregation failures

#### Configuration Validation at Startup
- `TaskOrchestrator._load_and_validate_config()` checks all required keys on init
- `REQUIRED_CONFIG_KEYS`, `REQUIRED_OPENROUTER_KEYS`, `REQUIRED_ORCHESTRATOR_KEYS` constants
- **Fail-fast** with a human-readable `ConfigurationError` instead of cryptic `KeyError` at runtime

#### Named Constants (zero magic strings/numbers)
- **orchestrator.py**: `STATUS_QUEUED`, `STATUS_PROCESSING`, `STATUS_COMPLETED`, `STATUS_FAILED_PREFIX`, `STATUS_TIMEOUT`, `AGGREGATION_CONSENSUS`, `TOOL_MARK_TASK_COMPLETE`, `DEFAULT_CONFIG_PATH`, `FALLBACK_QUESTION_TEMPLATES`
- **agent.py**: `DEFAULT_CONFIG_PATH`, `DEFAULT_MAX_ITERATIONS`, `TOOL_MARK_TASK_COMPLETE`, `ROLE_SYSTEM/USER/ASSISTANT/TOOL`, `CHAT_COMPLETIONS_ENDPOINT`, `MAX_ITERATIONS_FALLBACK_MSG`
- **make_it_heavy.py**: `ANSI_ORANGE`, `ANSI_RED`, `ANSI_RESET`, `BAR_WIDTH`, `BAR_ACTIVE_WIDTH`, `PROGRESS_UPDATE_INTERVAL`, `RESULT_SEPARATOR`, `EXIT_COMMANDS`
- **main.py**: `EXIT_COMMANDS`, `SEPARATOR`

#### Robust Error Handling
- `requests.exceptions.Timeout` — separate catch with clear 120s timeout message
- `requests.exceptions.ConnectionError` — network failure with URL in message
- `requests.exceptions.HTTPError` — includes status code + first 400 chars of response body
- `json.JSONDecodeError` on tool arguments — logs warning, passes empty dict instead of crashing
- `TypeError` on tool args mismatch — recoverable, reports available signature to LLM
- `FuturesTimeoutError` — global orchestration timeout handled gracefully with partial results
- All exceptions caught at appropriate specificity (no bare `except Exception` in library code)

#### Improved JSON Extraction
- `decompose_task()` now uses `str.find("[")` / `str.rfind("]")` to extract JSON even when
  the AI wraps it in markdown fences or explanatory text
- Validates list length matches `num_agents` exactly before accepting

#### Agent Mock SDK Hardening
- `_MockMessage`, `_MockChoice`, `_MockResponse`, `_MockToolCall` use `__slots__` for memory efficiency
- `_MockToolCall` wraps raw dicts into typed `_Function` objects with `.name` and `.arguments`
- Tool calls are now correctly serialized back into the message history (fixes a subtle bug where
  the `tool_calls` field was passed as mock objects instead of JSON-serializable dicts)

#### `__slots__` on Mock Objects
- Reduces per-instance memory overhead for mock response wrappers created in tight loops

#### EOFError Handling
- Both CLIs now catch `EOFError` to handle piped/non-interactive input gracefully

#### `sys.exit(1)` on Fatal Errors
- Both `main.py` and `make_it_heavy.py` exit with code 1 on unrecoverable startup errors
- Enables shell scripts and CI pipelines to detect failure

#### CHANGES.md (this file)
- Comprehensive changelog tracking all improvements

### Changed

- `OpenAI` inner class renamed to top-level `OpenAI` with private `_Chat`, `_Completions`, `_MockMessage`, etc.
- `progress_monitor()` thread renamed to `_progress_monitor()` (private convention)
- `run_agent_parallel()` uses `time.monotonic()` instead of `time.time()` for accurate elapsed timing
- Fallback decomposition now supports up to 8 templates (cycles for > 8 agents)
- `aggregate_results()` logs warning counts for failed agents rather than silently dropping them

### Fixed

- **Tool call history bug**: Previously, `_MockToolCall` objects were appended directly to
  `messages` — the OpenRouter API would reject these. Now serialized to plain dicts.
- **JSON extraction fragility**: Question-generation response is now robustly extracted even
  with surrounding markdown text.
- **Duplicate import**: `agent.py` had `import json` and `import yaml` each twice — removed.
- **Progress monitor thread not named**: Now named `"ProgressMonitor"` for easier debugging.

---

## [1.x] — Pre-GlacierEQ baseline

Original implementation by Pietro Schirano (Doriandarko/make-it-heavy).
See git history for pre-2.0.0 changes.
