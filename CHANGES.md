# Changes

## 5.0.0 — Genius engine, local tier, telemetry, resumable runs

The history audit (Aug 20) found `genius_orchestration.py` present on disk but
imported by nothing — the "Genius Orchestration Engine" integration from commit
`5515645` was dead code. This release activates it and adds the three things
that cap long-run quality: a local-model tier, per-worker cost telemetry, and
resumable run-state checkpointing.

- **Activated the Genius Orchestration Engine.** `genius_orchestration.py`
  (now `make_it_heavy/genius_orchestration.py`) is a live pipeline: deterministic
  subtask decomposition → parallel swarm → fail-closed semantic claim firewall
  → immutable git-span receipts. Wired into the CLI via `--genius` and into the
  batch runner via `--genius --source-registry`.
- **Semantic firewall is fail-closed.** Every worker `OBSERVED[pointer]` claim
  must be entailed by its exact registered source span. Contradicted claims and
  missing pointers reject the iteration; the Genius engine never rewrites a
  failed claim into a verified one.
- **Local-model tier.** `local_agent.py` is an Ollama-backed agent that mirrors
  `OpenRouterAgent.run()`. `config.yaml` gains `local:` and `worker_tiers:`
  sections; `local_first` roles (review_planner, claim_auditor) try Ollama
  before OpenRouter and fall back transparently when the model is absent. This
  makes long runs cheap and resilient to network/API outages.
- **Per-worker token/cost telemetry.** `SwarmMemory.log_agent_run` now records
  `in_tokens`, `out_tokens`, and `cost_usd`; `get_stats()` returns totals plus a
  `cost_by_model` breakdown. Approximate OpenRouter pricing is inlined in
  `orchestrator.py` and is telemetry only, never asserted as ground truth.
- **Resumable run-state checkpointing.** `make_it_heavy/run_state.py` writes
  `RUN_STATE.json` per phase (`decompose` → `swarm` → `firewall` → `receipt` →
  `synthesis`). `make_it_heavy/batch.py` is a programmatic, resumable entry
  point: `python -m make_it_heavy.batch "<goal>"`, `--resume <run-id>`, `--runs`.
  Re-marking a phase is idempotent; resuming never re-runs completed phases.
- **Dependency hygiene.** `httpx` (imported by `tools/statute_lookup.py`) and
  the `scripts/` package (imported by `tests/test_turn6_semantic_recall.py`) are
  now declared in `requirements.txt` and `scripts/__init__.py` respectively.
- **Tests:** 200 passing (was 180), including 20 new tests in
  `tests/test_v5_additions.py` covering the firewall, Genius engine, local tier,
  run-state, and batch resume.

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
