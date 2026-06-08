# Mastermind Integration

Purpose: align `make-it-heavy` with the Mastermind / STEALTH-MICROWAVE / OmniAgent architecture.

## Existing Pattern

`make-it-heavy` provides the heavy-analysis pattern:

```text
user query
-> question generation
-> 4 parallel agents
-> synthesis
-> final answer
```

## Mastermind Pattern

Mastermind extends the pattern with stability gates:

```text
task or query
-> OmniAgent coordination
-> STEALTH-MICROWAVE fanout
-> 4 parallel lanes
-> synthesis gate
-> promotion decision
```

## Current Mastermind Lanes

- `registry_guard`: validates the 12-piston registry.
- `stealth_claw`: precision patch lane.
- `apex_gemma4`: local coder lane.
- `omniagent`: coordination lane.

## Stability Rule

Stability is king.

A lane passing is not promotion-ready unless required proof exists.

For code-producing work, proof means:

- diff;
- test or validator;
- recovery note;
- report entry.

## Role Split

`make-it-heavy` is the conceptual heavy-analysis pattern.

`mastermind` is the stability-gated execution layer.

## Next Step

Add an adapter that can export a make-it-heavy four-agent plan into:

```text
mastermind/config/parallel_coder_tasks.json
```
