# APEX_BLUEPRINT_V1

lane: JOB_RESTORE
verified_executable_capability_delta: YES

## Current source
- owning_repo: GlacierEQ/make-it-heavy
- source_sha_before_cycle: 8cb7251ae11d38b5d509236964a74539aef4becb
- source_sha_after_merge: 31395764dd843ea729d00638c2bacc5328ee3a10
- exact_proven_pr_head: af895b5f01f62dc44b774713ca6957f15c07f81e
- production_runtime_file: matched_ablation.py
- production_runtime_blob: b6633ffc3bc45f656cb03a8f33686e1dd80f2376
- live_history_runtime: health_memory.py
- live_selector_runtime: semantic_claim_innovation.py
- causal_storage_runtime: longitudinal_memory.py
- proof_workflow: .github/workflows/adaptive-worker-integrity.yml

## Donor SHAs / recovery lineage
- prior_main: 8cb7251ae11d38b5d509236964a74539aef4becb
- longitudinal_memory_blob: cfe8bbc671e5c239c5e7f5ef26a50ed4c4e402c0
- live_history_blob: 789ff0027c9b444714a96a540a171a6d91c764c5
- portfolio_optimizer_blob: 46b490c30e60768c6287a0b9101b4af0d773ed03
- live_semantic_selector_blob: a11438681b2f4e2e42e631e6e308cd408bf7c6f8

## Selected priority
- tier: P2
- priority: Bind causal worker value to a real persisted matched-ablation execution so live portfolio selection can consume measured marginal system value without relying on manual caller identity or observational inference.

## Blocked higher candidates
- P1 xAI `ready_for_human_submission=true` remains blocked on explicit applicant-controlled values for unresolved live Greenhouse fields. No applicant-controlled value was inferred.
- A real stranded repository-family restoration remained P2 but no stronger target with an immediately provable native execution surface was established before this unblocked live-runtime gap.

## Displaced capability
The repository already had three strong but disconnected pieces: matched longitudinal experiment storage, a manual `record_worker_ablation()` causal write path, and a production portfolio selector that consumes explicit `marginal_system_value` and `outcome_leverage`. What was missing was an executable bridge proving that the causal write came from an actual persisted parent/child matched topology execution. A caller could previously supply role identity and outcome scores manually without the runtime verifying that the cited ABLATION child actually removed that worker from the correct parent experiment.

## Implemented delta
- Added `matched_ablation.py` with `record_matched_worker_ablation()` and a CLI execution surface.
- The child must already exist as a persisted `ABLATION` experiment.
- Both parent and child must be performance-valid.
- Parent and child must share exact `mission_family` and `comparison_key`.
- The child must retain `freeze_topology=true` and equal the parent topology minus exactly one worker, with no additions or substitutions.
- The removed role is inferred from persisted topology rather than supplied by the caller.
- The parent must contain a valid longitudinal metric for that exact removed role.
- Only after those checks does the runtime reuse the existing `record_worker_ablation()` write path and promote measured marginal system value and outcome leverage into the parent worker metric consumed by live portfolio history.
- The receipt records parent/child mission identity, exact topologies, removed role, and the causal measurement boundary.

## Mechanisms compared
1. Continue manual `record_worker_ablation()` calls: rejected because role and experiment identity remain caller-controlled and can drift from the actual executed topology.
2. Infer causal contribution from observational quality/benefit history: rejected because it violates the repository's explicit causal truth boundary.
3. Selected nonlinear composition: validate two persisted executions, infer the sole removed role from topology, then reuse the proven causal storage path already consumed by production portfolio selection.

## Preserved gains
- Existing `worker_experiments`, `worker_longitudinal_metrics`, and `worker_ablations` schemas remain intact.
- Existing manual low-level causal write primitive remains available internally.
- Existing observational quality and heuristic benefit remain distinct from causal value.
- Existing live selector still awards zero causal bonus when explicit causal fields are absent.
- Existing infrastructure-failure isolation and role-local reliability penalties remain intact.
- Existing mandatory source/adversarial/proof role protection remains intact.
- No whole-repository revert or topology-controller replacement occurred.

## Tests / runtime proof
- PR: #44
- first head: 8852fd2157e62587054d5225df341de31794475b
- first Adaptive Worker Integrity run: 32244903257 — FAILED
- first-run defect: the new positive-path test persisted only longitudinal rows, while real live execution persists ordinary `worker_scores` before longitudinal enrichment. The causal write succeeded, but the synthetic fixture therefore exposed no row to `get_recent_worker_portfolio_history()`.
- correction: test fixture now reproduces the live adaptive-score then longitudinal persistence sequence; the runtime causal gate was not weakened.
- exact proven PR head: af895b5f01f62dc44b774713ca6957f15c07f81e
- replacement Adaptive Worker Integrity run: 32245279054 — PASS
- Python 3.9 job: 96044346975 — PASS
- Python 3.10 job: 96044346839 — PASS
- Python 3.11 job: 96044346732 — PASS
- Python 3.12 job: 96044346927 — PASS
- Python 3.13 job: 96044346926 — PASS
- Every matrix job passed compileall, the complete unittest suite, and innovation/receipt-boundary verification.
- Adversarial proof covers successful causal promotion into live portfolio history, rejection of a no-op same-topology child, and rejection of an observational child masquerading as causal evidence.
- Exact-head squash merge: 31395764dd843ea729d00638c2bacc5328ee3a10
- Post-merge readback confirmed `matched_ablation.py` blob b6633ffc3bc45f656cb03a8f33686e1dd80f2376 on `main`.

## Exact target files / functions
- matched_ablation.py: `record_matched_worker_ablation`, `_load_experiment`, `_decode_topology`, CLI `main`
- longitudinal_memory.py: `persist_longitudinal_turn`, `record_worker_ablation`
- health_memory.py: `get_recent_worker_portfolio_history`
- worker_portfolio_optimizer.py: `_causal_signal`, `build_worker_signal`, `select_worker_portfolio`
- semantic_claim_innovation.py: `ReceiptLineageSemanticClaimAdaptiveWorkerLoop._next_roles`
- tests/test_matched_ablation.py

## Top 3 remaining priorities
1. P1: bind explicit applicant-confirmed xAI values and produce the real `ready_for_human_submission=true` package without external submission.
2. P2: execute the first independently provable stranded job-ecosystem repository-family restoration through exact-SHA recovery in that repository's native runtime.
3. P2: compose the matched-ablation recorder into an executable experiment runner that performs the full and one-worker-ablated runs under one explicit outcome rubric, while preserving the rule that causal metrics are promoted only from observed matched executions.

## Next sequence
1. Recheck the P1 applicant-value lane only if explicit values are actually available; never infer them.
2. Otherwise select the strongest real stranded repository family with an executable native proof surface and restore it from exact donor SHA without whole-repo rollback.
3. If no stronger recovery target is executable, compose the existing longitudinal experiment loop with the new matched-ablation recorder so a real full/ablated pair can generate causal portfolio evidence end to end.

## Merge / deploy gate
- Exact-head five-version target-native proof passed on replacement run 32245279054.
- Exact-head squash merge passed at 31395764dd843ea729d00638c2bacc5328ee3a10.
- Post-merge runtime readback passed.
- No external application submission occurred.

## Rollback
Revert merge `31395764dd843ea729d00638c2bacc5328ee3a10` to remove the matched-ablation bridge while preserving the prior reliability-aware portfolio selector and longitudinal memory stack at `8cb7251ae11d38b5d509236964a74539aef4becb`.

## No-loss invariants
- Never promote observational quality or heuristic benefit into causal worker value.
- Never accept an ABLATION child that adds/substitutes roles or removes anything other than exactly one parent worker.
- Never cross mission-family or comparison-key boundaries when recording causal value.
- Never record causal value from a performance-invalid parent or child execution.
- Never displace mandatory source, adversarial, or proof roles merely because causal ranking changes.
- Preserve role-local failure evidence while excluding shared infrastructure failures from worker penalties.
- Preserve stronger later runtime mechanisms and exact execution lineage during future recovery work.
