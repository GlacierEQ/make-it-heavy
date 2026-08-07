# Turn 7 — Atomic Semantic Claim Firewall

Target repository: `GlacierEQ/make-it-heavy`
Target immutable commit: `d290b022ffc709abacd4672aa3f7527ae22b692f`

Mission: measure whether the seven surviving adaptive workers can distinguish direct source-entailable observations from inference, proposal, and blocked claims after Turn 6.

## Hard contract

Every `OBSERVED[T7#Ex]:` claim MUST be copied as a direct contiguous phrase from one of the verified atoms below. Do not paraphrase inside `OBSERVED`.

All paraphrase, synthesis, ranking, consequence, recommendation, or speculation MUST be classified as `INFERENCE:`, `PROPOSED:`, or `BLOCKED:`.

Use at least two `OBSERVED[...]` lines. Use exactly one evidence pointer per `OBSERVED` line. Name all three semantic relation states somewhere in your first required section:

- `SOURCE_ENTAILS_CLAIM`
- `SOURCE_CONTRADICTS_CLAIM`
- `SOURCE_INSUFFICIENT`

Do not invent metrics, dates, identifiers, runtime facts, or source meaning. Maximum 430 words.

EVIDENCE_REGISTRY_BEGIN
{"T7":{"E1":"claim_aware_innovation.py@d290b022ffc709abacd4672aa3f7527ae22b692f#L314-L470","E2":"semantic_support.py@d290b022ffc709abacd4672aa3f7527ae22b692f#L150-L360","E3":"immutable_span_resolver.py@d290b022ffc709abacd4672aa3f7527ae22b692f#L1-L200","E4":"innovation_health.py@d290b022ffc709abacd4672aa3f7527ae22b692f#L1-L180","E5":"health_memory.py@d290b022ffc709abacd4672aa3f7527ae22b692f#L1-L99","E6":"tests/test_turn6_runtime_semantic_gate.py@d290b022ffc709abacd4672aa3f7527ae22b692f#L40-L190"}}
EVIDENCE_REGISTRY_END

## Verified source atoms

These atoms have already been checked against the exact immutable spans above. They are intentionally short so the provider receives evidence, not raw repository bulk.

[T7#E1] Resolve registered immutable spans and evaluate each OBSERVED claim.

[T7#E2] Extract quantities after removing recognized dates so date parts do not double-count.
[T7#E2] Require contiguous token-sequence containment, never broad substring matching.
[T7#E2] Reject support when either side contains mutually exclusive states.
[T7#E2] Compare negation only inside clauses that share the claim's local anchors.
[T7#E2] Classify one claim against one immutable source span conservatively.

[T7#E3] Fail-closed resolution of immutable local Git evidence spans.
[T7#E3] Resolve exact immutable spans from one explicitly bounded local Git repository.
[T7#E3] Find the nearest Git worktree root from a config/template/file anchor.
[T7#E3] Git timed out while checking the immutable revision
[T7#E3] path is not present at the immutable revision

[T7#E4] Infrastructure-health isolation for adaptive worker learning.
[T7#E4] Return a shared-infrastructure incident only when template scoring is invalid.
[T7#E4] Render an infrastructure incident without a misleading model-inference header.
[T7#E4] Build a persistent incident report without mutating worker templates.

[T7#E5] Adaptive memory views that exclude infrastructure failures from learning.
[T7#E5] Preserve infrastructure incidents while excluding them from prompt evolution.
[T7#E5] Return only reviewable model-inference scores for template comparison.
[T7#E5] Return the newest adjustment backed by reviewable model inference only.
[T7#E5] Report evaluated performance separately from infrastructure incidents.

[T7#E6] The provider status is verified.
[T7#E6] The provider status is not verified.
[T7#E6] The rollout date is January 2, 2024.
[T7#E6] The rollout date is January 3, 2024.
[T7#E6] deployment status PASS
[T7#E6] deployment status FAIL

## Experimental controls

- Worker topology: hold seven roles.
- Provider concurrency: one request at a time.
- Model diversity: held constant for this failover run.
- Provider/model: GitHub Models, `openai/gpt-4.1`.
- Source identity: fixed to merged Turn-6 commit.
- No worker should be penalized for provider or immutable-evidence resolution failure.
