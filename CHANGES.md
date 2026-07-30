# Changes

## 4.0.0 — persistent memory, Smithery MCP, scheduler, resilience

- Added `memory.py`: SQLite-backed SwarmMemory with missions, agent runs, tool calls, and cache tables.
- Added `tools/memory_tool.py`: agents can recall similar missions, store key-value pairs, and check stats.
- Added `tools/smithery_mcp_tool.py`: agents can call any Smithery MCP server (GitHub, Notion, Drive, etc.) from inside the tool loop.
- Added `scheduler.py`: autonomous hourly mission runner with error recovery.
- Updated `agent.py`:
  - Exponential backoff retry (3 attempts) for transient OpenRouter failures.
  - Circuit breaker (threshold 5, reset 60s) to prevent cascading failures.
  - LLM response caching via SwarmMemory (30 min TTL).
  - Tool call latency logging.
- Updated `orchestrator.py`:
  - Added `run_mission()` method with full memory tracking.
  - Logs every agent run to SwarmMemory.
- Updated `tools/__init__.py`: registered `memory` and `smithery_mcp` tools.
- Updated `config.yaml`: added `memory`, `smithery`, and `scheduler` sections; expanded tool allowlists.
- Updated `requirements.txt`: added `schedule`.
- Added tests: `test_memory.py`, `test_scheduler.py`, `test_resilience.py`.

## 3.0.0 — read-only role-bound execution

- Replaced directory-wide hot tool discovery with an explicit built-in registry.
- Added per-worker tool allowlists and a separate, default-off mutation opt-in.
- Added an execution-time write denial inside write_file.
- Bound each configured worker's role, model, system prompt, and tools to its
  OpenRouterAgent.
- Removed case-specific facts, legal conclusions, probabilities, automatic
  escalation paths, and claimed deadlines from runtime defaults and documentation.
- Added bounded HTTP, per-agent, and orchestration timeouts plus cancellation of
  pending futures.
- Classified generated results as model_inference / pending_review with source
  expectations.
- Required synthesis to preserve uncertainty, disagreements, and evidence gaps.
- Added standard-library policy tests that make no external API calls.
