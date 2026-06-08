# Export Validate Import

This runbook connects `make-it-heavy` to `mastermind`.

## Flow

```text
make-it-heavy query
-> export Mastermind lane config
-> validate lane config
-> copy into mastermind/config/parallel_coder_tasks.json
-> run STEALTH-MICROWAVE
```

## Commands

Export:

```bash
python scripts/export_mastermind_lanes.py "maximize Mastermind parallel coder lanes"
```

Validate:

```bash
python scripts/validate_mastermind_lanes.py outputs/mastermind_parallel_coder_tasks.json
```

Import target:

```text
mastermind/config/parallel_coder_tasks.json
```

Run in Mastermind:

```bash
python scripts/parallel_execution_engine.py
```

## Rule

Stability is king.

No code-producing lane promotes without diff, test or validator, recovery note, and report entry.
