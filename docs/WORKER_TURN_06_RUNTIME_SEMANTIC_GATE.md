# Worker Innovation Turn 6 — Runtime Semantic Gate

## Mission

Make worker-template adaptation depend on what the cited immutable evidence actually supports, while preventing shared inference/runtime failures from being mislearned as weak worker performance.

## Why Turn 6 existed

Turns 4 and 5 established two separate contracts:

1. an immutable evidence-pointer identity gate; and
2. a bounded claim-to-source-span semantic evaluator.

The missing production link was that the live adaptive worker score still stopped at pointer identity. A worker could therefore cite the correct immutable span while making a claim that the span contradicted or did not support, and the template optimizer would not see the semantic defect.

A second failure mode was exposed by live worker execution: a uniform provider/runtime outage can make every worker return an error. Treating those error envelopes as eight independent zero-quality workers teaches the optimizer the wrong lesson.

Turn 6 closes both gaps.

## Runtime decision chain

```text
worker output
  -> OBSERVED[source#span] parse
  -> evidence-registry identity check
  -> immutable Git span resolution
  -> bounded semantic relation
       SOURCE_ENTAILS_CLAIM
       SOURCE_CONTRADICTS_CLAIM
       SOURCE_INSUFFICIENT
  -> worker quality/benefit cap
  -> next-turn adjustment
```

A shared provider/runtime failure takes a different path:

```text
all workers fail before reviewable model inference
  -> shared infrastructure classifier
  -> INFRA_FAILURE receipt
  -> preserve worker count and role set
  -> HOLD_TEMPLATE_INFRA
  -> exclude sentinel zeroes from performance history
  -> repair provider/runtime plane and rerun same contracts
```

## Semantic worker adjustments

- Resolved source span entails claim: semantic gate passes.
- Resolved source span contradicts or cannot support claim: worker quality is capped and the next instruction is `TIGHTEN_SEMANTIC_SUPPORT`.
- Immutable source span cannot be resolved: worker template is held and the next action is `HOLD_TEMPLATE_REPAIR_EVIDENCE`.

That distinction is deliberate. Evidence infrastructure failure is not worker-template failure.

## Semantic evaluator hardening

Turn 6 also narrows false positives and false contradictions:

- dates, quantities, and technical identifiers are evaluated separately from lexical coverage;
- sentence-case words are not automatically treated as identifiers;
- CLI flags, snake-case identifiers, all-caps identifiers, repository/path-like identifiers, hex values, and braced identifiers retain precision checks;
- broad substring matching is replaced with contiguous token-sequence containment plus conservative lexical coverage;
- punctuation at token boundaries is normalized without erasing internal identifier structure;
- negation contradiction is clause-local and requires substantial shared claim anchors;
- unsupported semantic-expansion terms fail closed.

## Immutable span resolver

`immutable_span_resolver.py` accepts only:

```text
path@40-character-commit-sha#Lx-Ly
```

It rejects path traversal, unavailable revisions, unavailable paths, invalid line ranges, and non-UTF-8 evidence. A successful resolution produces the exact span text and a SHA-256 receipt.

## Infrastructure-health isolation

A turn is classified as shared `INFRA_FAILURE` only when all workers fail before model inference and the failures share provider/runtime evidence. Mixed turns and unrelated role-specific failures remain ordinary worker results.

Infrastructure incidents remain auditable in adaptive memory, but:

- `get_recent_worker_scores()` excludes them from template comparison;
- `get_latest_template_adjustments()` excludes infrastructure-only adjustments from next-turn prompt evolution;
- quality/benefit averages use reviewable `model_inference` rows only.

The zero scores stored on an infrastructure incident are storage sentinels, not worker-performance measurements.

## Verification

The final Turn-6 materialization passed:

- 23 focused Turn-4/5/6 + infrastructure-health tests;
- bounded semantic benchmark: 10/10 exact matches, minimum accuracy 1.0;
- Python `compileall`;
- complete repository regression suite: 99 tests passed;
- self-removal of all temporary Turn-6 materializer workflows.

Semantic benchmark SHA-256:

`4ff72d086c242f86d610712469046028e3180be7817ac8f73884c6e1a8b7060d`

## Truth boundary

The semantic gate is a conservative relation between one claim and one resolved immutable source span. It is not a general natural-language inference engine, an external-world truth oracle, a repository-wide correctness proof, or evidence that a worker's proposed architecture will succeed.

Infrastructure classification likewise does not prove the provider's root cause. It establishes only that the observed worker errors are sufficiently uniform and provider/runtime-shaped that template-performance learning would be invalid for that turn.

## Next innovation gate

Turn 7 should use real worker-turn telemetry to tune **semantic recall versus precision** and **provider/runtime resilience** separately. Model/provider diversity should be treated as an experimental variable only after the shared execution plane is healthy, so topology and template effects remain attributable.
