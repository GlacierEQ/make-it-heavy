# AGENTS.md — make-it-heavy

Multi-agent swarm runner. Heavy analysis, repository improvement, README star-map.

**See:** `@/root/.agents/skills/make-it-heavy/SKILL.md` for full operating guide.

## Quick rules

- **Tool allowlist is policy.** Every tool must be in `config.yaml` before
  it can be invoked. Unlisted tools fail closed.
- **Every worker role must set `max_iterations`.** Default 10. Never 0, never None.
- **No tool merges without a test.** Create `tests/test_<tool>.py` in the same PR.
- **Memory is per-user.** `TieredMemory` requires a non-empty `user_id`. No
  anonymous memory writes. This is a privacy boundary, not a suggestion.
- **Test command:** `cd /root/projects/make-it-heavy && python -m unittest discover tests`

## Sub-systems

- Orchestration: `orchestrator.py`, `make_it_heavy.py`, `make_it_heavy/genius_orchestration.py`
- Memory: `memory.py` (SwarmMemory — flat) + `memory_tiered.py` (TieredMemory — STM/LTM/entity)
- Tools: `tools/` — calculator, file read/write, web search, Smithery MCP
- Workers: defined in `config.yaml` under `agents:`
