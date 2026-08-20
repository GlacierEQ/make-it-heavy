# make-it-heavy Thread Charter

## Mission

`make-it-heavy` turns a complex task into policy-bound, role-specific worker work while preserving uncertainty, limiting tool authority, and retaining evidence that distinguishes model inference from verified support.

## Runnable Proof Surface

Run the complete local suite with:

```bash
PYTHONPATH=. pytest -q
```

Run the deterministic standalone proof with:

```bash
PYTHONPATH=. python3 benchmarks/work_amplification_proof.py --output make_it_heavy_standalone_proof.json
```

The standalone proof exercises the actual tool-discovery and write-denial boundary plus the semantic claim firewall. It calls no model and makes no network request.

## Published Capability Surfaces

| Surface | Promise |
|---|---|
| `TaskOrchestrator` | Builds role-bound worker work with bounded request, agent, and orchestration timeouts; timeout results remain explicit rather than silently becoming success. |
| `discover_tools()` | Exposes only explicitly allowlisted tools and excludes mutation tools unless mutation is explicitly enabled. |
| `WriteFileTool` | Denies write execution when the mutation boundary is disabled. |
| `evaluate_semantic_claim_firewall()` | Requires each `OBSERVED[...]` worker claim to be supported by its exact registered source span; missing, contradictory, or insufficient support fails closed. |

## Truth Boundary

This thread demonstrates policy and evidence discipline for local fixtures. It does **not** demonstrate live-model quality, external research correctness, autonomous execution authority, production concurrency, or a claim about any employer, company, or real-world system.

## Next Capability

Consume a versioned Work Amplification manifest from `token_saver` that declares source pointers, byte budgets, and lossiness. The handoff must preserve source provenance and must not promote a byte reduction into a model-token or quality claim without separate evidence.
