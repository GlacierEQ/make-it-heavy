# Worker Turn 02 — Company Proof Compiler Proof Slice

**Run:** `mih-turn2-cpc-proof-slice-2026-08-06-sparkforge-v2`  
**Parent:** `mih-wbz-2026-08-05-sparkforge-v1`  
**Provider:** `henry-ships-sparkforge.smart_summarize`  
**Logical workers:** 7  
**Final provider concurrency width:** 1  
**Result SHA-256:** `54f24c6249c11b9c0cccbafcc7f23d0fa10773adbe3a508624ee174f2dcd7fad`

## Mission

Turn the Company Proof Compiler from an architecture idea into a minimum reproducible proof-slice contract before attempting all 48 company tracks.

The proof slice was bounded to six recruiter-safe repositories from the current flagship registry:

1. `GlacierEQ/job-app-helix`
2. `GlacierEQ/AKOS`
3. `GlacierEQ/Pro-DOCTOR-STRANGE`
4. `GlacierEQ/the-tower-of-babel`
5. `GlacierEQ/pro-code`
6. `GlacierEQ/job-application`

No source-code behavior, live job fit, employer adoption, production deployment, customer use, or affiliation was treated as established by the worker packet.

## Turn result

| Worker | Quality | Benefit | Provider-normalized benefit | Elapsed | Attempts | Baseline quality Δ | Next adjustment |
|---|---:|---:|---:|---:|---:|---:|---|
| `source_mapper` | 67.44 | 0.9023 | 0.9023 | 13.26 s | 1 | -28.56 | `TIGHTEN_EVIDENCE` |
| `adversarial_breaker` | 88.68 | 0.9660 | 0.9660 | 12.17 s | 1 | +2.63 | `EXPAND_OR_DUPLICATE`* |
| `proof_engineer` | 94.36 | 0.9831 | 0.9831 | 12.44 s | 1 | -2.44 | `EXPAND_OR_DUPLICATE` |
| `leverage_analyst` | 74.45 | 0.9233 | 0.9233 | 9.85 s | 1 | -17.63 | `KEEP`* |
| `presentation_strategist` | 89.90 | 0.9697 | 0.9697 | 14.16 s | 1 | -1.60 | `EXPAND_OR_DUPLICATE`* |
| `innovation_inventor` | 85.39 | 0.9141 | 0.9562 | 77.60 s | 2 | -4.81 | `EXPAND_OR_DUPLICATE`* |
| `bottleneck_cartographer` | 90.26 | 0.9708 | 0.9708 | 8.35 s | 1 | +0.66 | `EXPAND_OR_DUPLICATE`* |

**Average quality:** 84.35 / 100  
**Average marginal benefit:** 0.9470  
**Provider-normalized marginal benefit:** 0.9531  
**Adaptive topology decision:** hold at **7 workers** and tune templates before changing producer count.

`*` The deterministic score alone is no longer sufficient for promotion. Manual/raw-output review exposed unsupported quantitative and process-specific assertions in several otherwise high-scoring responses. Turn 3 therefore adds a claim-discipline gate before those actions can be accepted.

## Same-turn template learning

Three workers exposed genuine prompt defects and were tuned without lowering the acceptance gate.

### Proof Engineer

**Before:** valid response completed 4/6 required sections and omitted the two new decision-critical sections: `PASS FAIL CONTRACT` and `MINIMUM PROOF SLICE`.

**Adjustment:** put those two sections first and reduce the output budget to 550 words.

**After:** **6/6 sections, 100% coverage, 12.44 s, first attempt.**

### Adversarial Breaker

**Before:** two clean provider responses each completed 4/6 sections and omitted `RED TEAM DECISION GATES` and `STOP CONDITION`.

**Adjustment:** put the two decision-critical sections first and reduce the output budget to 500 words.

**After:** **6/6 sections, 100% coverage, 12.17 s, first attempt.**

### Leverage Analyst

**Before:** 5/6 sections after 75.26 s; the new `SCOPE CONSTRAINT` section was omitted.

**Adjustment:** move `SCOPE CONSTRAINT`, `PRIORITY`, and `NEXT BET` first and reduce the output budget to 450 words.

**After:** **6/6 sections, 100% coverage, 9.85 s, first attempt.**

### Reusable prompt rule discovered

> **Put the falsifiable/decision-critical output first; optional exposition comes last. Reduce scope before reducing the quality gate.**

That rule improved all three incomplete lanes immediately.

## What each worker actually added

### `source_mapper`

Useful contribution: surfaced the missing evidence boundaries—commit/ref pinning, content sampling depth, recruiter-safe scope definition, and the need for an explicit repository/source matrix.

Defect: it also inferred repository functions and interpreted the Baseline Zero averages as selection thresholds without precise source pointers. The structural score caught this partly (`evidence = 0`) but not all of the semantic overreach.

**Turn-3 change:** observed claims must use exact source IDs/receipts; no interpretation of a score as a threshold unless the controlling record says so.

### `adversarial_breaker`

Useful contribution: forced explicit blockers against repo-exists-is-proof reasoning, unsupported connected-system claims, stale evidence, and evidence-to-decision coupling.

Defect: it invented numeric freshness percentages/time windows and universal attestation/deployment requirements. Those are possible proposed gates, not verified requirements.

**Turn-3 change:** every threshold must be `PROPOSED` or backed by a source ID; unsourced quantitative gates cannot be emitted as requirements.

### `proof_engineer`

Highest-quality Turn-2 system contribution. It separated:

- repository existence;
- code behavior;
- connected-system evidence;
- future role-fit claims;

and defined `PASS / FAIL / DEFERRED` boundaries plus the minimum artifacts needed before the proof slice can expand.

**Turn-3 change:** preserve the proof-first ordering and add an explicit out-of-scope/deferred-claim ledger.

### `leverage_analyst`

Useful contribution: reinforced the central leverage rule—one complete, reusable proof sheet should be produced before breadth expansion.

Defect: it invented a 3–5-business-day estimate and confused its assigned worker lens with an employment/current-role record.

**Turn-3 change:** no unsourced time/cost estimates; explicitly state that the assigned worker role is an analysis lens, not a candidate employment role.

### `presentation_strategist`

Useful contribution: produced the right presentation shape—evidence state, unresolved gap, and one of `APPLY_NOW / REPAIR_THEN_APPLY / WATCH / NO_MATCH`.

Defect: its examples invented confidence scores, coverage thresholds, remediation timelines, recency windows, and scale claims. The structural scorer still rated this response highly.

**Turn-3 change:** presentation templates use placeholders such as `<VERIFIED_VALUE>` and may not generate example metrics unless the metric is present in a source receipt.

### `innovation_inventor`

Useful contribution: proposed replacing opaque repo-to-role confidence scores with a falsifiable tri-state mechanism:

- `ACCEPT`
- `DEFER`
- `REJECT`

plus a contradiction manifest explaining why a match fails.

Defect: the example experiment introduced arbitrary thresholds without consistently labeling them as hypothetical design values.

**Turn-3 change:** every experimental threshold must be explicitly tagged `PROPOSED` and cannot leak into evidence claims.

### `bottleneck_cartographer`

Useful contribution: the narrowed six-repository slice still points toward the same unresolved gate—actual code inspection plus current-role reconciliation.

Defect: it presented unobserved process mechanics (manual security review, external identity queries, constant per-repository latency) as if measured. No such execution evidence existed in the packet.

**Turn-3 change:** the bottleneck conclusion remains a provisional inference until repository inspection is executed; any velocity claim must be measured rather than narrated.

## Runtime learning

Turn 2 also changed the worker runtime itself.

### Seven-wide provider concurrency: rejected

Seven simultaneous logical workers saturated the single SparkForge plane near the gateway timeout ceiling and produced cross-lane contamination: one innovation lane returned a Source Mapper-shaped response.

### Width two: useful but not fair enough for scoring

Two simultaneous calls could succeed quickly, but one lane could complete while the peer consumed the timeout budget. It was not a stable basis for worker-to-worker comparison.

### Width one: selected measurement mode

Logical worker topology remains seven. Provider concurrency is a **separate control variable** and was fixed at one for comparable worker measurement.

### Capability allocator repaired

The `apex_tool_gateway_capabilities` identity sequence had fallen behind the table and could collide during concurrent allocation. The sequence was reconciled before continuing.

### Role-integrity gate repaired

A brittle `ROLE_ID` echo requirement falsely rejected structurally valid responses. Role acceptance now uses role-specific heading coverage; `ROLE_ID` is advisory.

## Evaluator defect discovered

The largest Turn-2 innovation is not another worker prompt. It is a scoring correction.

The old deterministic truth score rewarded the *presence of words* such as “source,” “evidence,” “uncertain,” and “inference.” It could therefore score a polished response highly even when that response invented a threshold, timeline, confidence score, or process mechanic.

Turn 3 must add a **claim-discipline plane**:

- `OBSERVED[source-id]`
- `INFERENCE`
- `PROPOSED`
- `BLOCKED`

Material `OBSERVED` claims require an exact source/receipt ID. Unsupported quantitative values cannot be presented as observed facts. High structure/novelty cannot override this gate.

## Turn 3

Producer topology remains **7**. The evaluation plane gains a non-voting claim adjudicator until the deterministic claim-discipline scorer is proven reliable.

Highest-value next execution: create the first actual repository proof sheet from pinned `GlacierEQ/job-app-helix` code, using the Turn-2 proof contract rather than another abstract architecture pass.
