# APEX-HEAVY

> Multi-agent parallel intelligence for Case 1FDV-23-0001009  
> Casey Barton / GlacierEQ — Constitutional Warfare + Reunification with Kekoa

Forked from [Doriandarko/make-it-heavy](https://github.com/Doriandarko/make-it-heavy) — enhanced for APEX legal operations.

## Architecture

```
User Query
    │
    ▼
APEX Orchestrator
    │  generates 4 targeted legal sub-questions
    ▼
┌───────────────────────────────────────────┐
│  PARALLEL SWARM (4 agents, simultaneous)  │
│                                           │
│  [1] Legal Researcher    → Qwen 3.6-Plus  │
│  [2] Constitutional      → Claude Opus 4  │
│  [3] Evidence Verifier   → Gemini 2.5 Pro │
│  [4] Strategy Synth      → Grok-3         │
└───────────────────────────────────────────┘
    │  all 4 responses
    ▼
Master Synthesizer → APEX Brief
    │
    ▼
Supabase Logger → apex_task_queue (evidentiary record)
```

## APEX Tools

| Tool | Purpose |
|------|---------|
| `tools/supabase_logger.py` | Timestamped evidentiary logging to Supabase |
| `tools/statute_lookup.py` | HRS + USC citation resolver + SOL calculator |
| `tools/apex_memory.py` | Persistent memory read/write to Supabase |

## Quick Start

```bash
pip install -r requirements.txt
pip install supabase python-dateutil

# Set env vars
export OPENROUTER_API_KEY=your_key
export SUPABASE_URL=your_supabase_url
export SUPABASE_ANON_KEY=your_anon_key

# Run single agent
python main.py

# Run APEX heavy swarm (4 parallel agents)
python make_it_heavy.py
```

## Active Legal Framework

- **HRS §571-46 / §571-46.4** — Custody and parental alienation
- **HRS §601-7** — Judicial disqualification
- **42 U.S.C. §1983** — Civil rights under color of law (SOL: 2yr/HRS §657-7)
- **18 U.S.C. §1961-1968** — RICO (civil SOL: 4yr)
- **28 U.S.C. §455** — Judicial recusal
- **Troxel v. Granville (2000)** — 14th Amendment parental rights floor

## SOL Watchdog

Run `tools/statute_lookup.py` → `get_sol_status()` to compute days remaining on any accrual date.
