# APEX_BLUEPRINT_V1

lane: JOB_RESTORE
verified_executable_capability_delta: YES

## Current source
- owning_repo: GlacierEQ/make-it-heavy
- source_sha_after_merge: 7a99aa65e80b768ef7cf47b61827ee9fb5aec93b
- production_runtime_file: semantic_claim_innovation.py
- production_runtime_blob: 5ceff13280ea89f9e0e43bfbe1021457091ebce7
- integration_test: tests/test_live_worker_portfolio_integration.py
- proof_workflow: .github/workflows/adaptive-worker-integrity.yml

## Donor SHAs / recovery lineage
- prior_main: 47d11a98a1c15c7be714a46877175d0efb34ec73
- longitudinal_optimizer_donor: 47d11a98a1c15c7be714a46877175d0efb34ec73
- optimizer_file: worker_portfolio_optimizer.py
- optimizer_blob: 46b490c30e60768c6287a0b9101b4af0d773ed03
- prior live topology implementation: innovation_loop.py blob 45c63b1ebc57e5ba9d004e22bd502815dc3399ed

## Selected priority
- tier: P2
- priority: Activate the already-proven longitudinal evidence-aware worker portfolio optimizer inside the real adaptive execution loop so persisted worker history changes next-turn topology instead of remaining CLI/library-only.

## Blocked higher candidates
- P1 real xAI `ready_for_human_submission=true` remains blocked on explicit applicant-controlled values for unresolved live Greenhouse fields. No applicant-controlled value was inferred.

## Displaced capability
`worker_portfolio_optimizer.py` was merged and independently executable, but production `AdaptiveWorkerLoop._next_roles()` still ranked only the current turn using benefit and quality. The runtime therefore ignored the richer longitudinal selector during real topology activation.

## Implemented delta
- `ReceiptLineageSemanticClaimAdaptiveWorkerLoop._next_roles()` now routes next-turn role selection through `select_worker_portfolio()`.
- Current worker-count logic remains authoritative for portfolio capacity.
- Mandatory `source_mapper`, `adversarial_breaker`, and `proof_engineer` roles remain non-displaceable.
- Persisted worker history is admitted through the existing `get_recent_worker_scores(role, limit=...)` memory contract.
- Sparse-history exploration, historical quality/benefit, and current-turn evidence now influence live challenger selection.
- When no memory provider exists, the optimizer's explicit no-history path preserves legacy current-turn ordering.
- The runtime exposes `worker_portfolio_selection` telemetry containing the mechanism, history source, selected roles, and deterministic per-role portfolio signals.

## Mechanisms compared
1. Keep the current-turn-only `_next_roles()` implementation: rejected because it leaves proven longitudinal capability stranded from production execution.
2. Replace adaptive topology control wholesale: rejected because it would unnecessarily displace proven worker-count, mandatory-role, semantic-claim, and evidence-gating behavior.
3. Selected nonlinear composition: preserve current count/gates and compose the proven longitudinal portfolio selector exactly at role-selection time, with a compatibility fallback when memory is absent.

## Preserved gains
- Existing adaptive worker-count decisions remain intact.
- Existing semantic claim firewall and immutable evidence-pointer gates remain intact.
- Existing provider-concurrency behavior remains intact.
- Mandatory source/adversarial/proof coverage remains intact.
- Existing worker templates and runtime profiles remain intact.
- No-memory selection remains backward compatible.
- Observational history is not promoted into a causal claim.

## Tests / runtime proof
- PR: #42
- exact proven PR head: 4597afe83f2474c77514cde2a8388010fcb6443e
- Adaptive Worker Integrity run: 32228139730 — PASS
- Python 3.9 job: 95992057323 — PASS
- Python 3.10 job: 95992057342 — PASS
- Python 3.11 job: 95992057530 — PASS
- Python 3.12 job: 95992057479 — PASS
- Python 3.13 job: 95992057487 — PASS
- Every matrix job completed repository-wide compileall, the complete unittest suite including live portfolio integration tests, and innovation/receipt-boundary verification.
- Exact-head squash merge: 7a99aa65e80b768ef7cf47b61827ee9fb5aec93b
- Post-merge readback confirmed `semantic_claim_innovation.py` blob 5ceff13280ea89f9e0e43bfbe1021457091ebce7 on `main`.

## Exact target files / functions
- semantic_claim_innovation.py: `ReceiptLineageSemanticClaimAdaptiveWorkerLoop._next_roles`, `evaluate_turn`
- worker_portfolio_optimizer.py: `select_worker_portfolio`, `build_worker_signal`
- innovation_loop.py: existing `_next_worker_count` and `evaluate_turn` call chain
- health_memory.py: existing `get_recent_worker_scores`
- tests/test_live_worker_portfolio_integration.py

## Top 3 remaining priorities
1. P1: bind explicit applicant-confirmed xAI values through the semantic-answer bridge and produce `ready_for_human_submission=true` without external submission.
2. P2: execute the first real stranded job-ecosystem repository-family restoration through the manifestless exact-SHA restoration stack and prove recovered behavior in that repository's native runtime.
3. P2: upgrade Make-It-Heavy's live history provider to consume longitudinal metric rows including invalid-turn failure evidence and explicit ablation/counterfactual fields, so failure penalties and causal bonuses can operate in production without conflating observational evidence with causality.

## Next sequence
1. Recheck the P1 applicant-value blocker only if explicit values become available; never infer them.
2. Otherwise select a real stranded repository family from current exact-SHA recovery evidence and execute target-native restoration.
3. If that path is blocked, extend the Make-It-Heavy history provider with explicit longitudinal/ablation evidence and adversarially prove live topology changes.

## Merge / deploy gate
- Exact-head five-version target-native proof passed.
- Exact-head merge passed.
- Post-merge runtime readback passed.
- No external application submission occurred.

## Rollback
Revert merge `7a99aa65e80b768ef7cf47b61827ee9fb5aec93b` to restore the prior current-turn-only production topology selector. The standalone longitudinal optimizer remains recoverable at prior main `47d11a98a1c15c7be714a46877175d0efb34ec73`.

## No-loss invariants
- Never displace mandatory source, adversarial, or proof roles.
- Never turn observational worker history into a causal performance claim.
- Never replace current worker-count control merely to use the portfolio selector.
- Never remove semantic/evidence gates to improve portfolio scores.
- Preserve the exact no-memory fallback.
- Preserve every stronger later runtime mechanism unless target-native proof shows a replacement is superior.
