# APEX_BLUEPRINT_V1

lane: JOB_RESTORE
verified_executable_capability_delta: YES

## Current source
- owning_repo: GlacierEQ/make-it-heavy
- source_sha_before_cycle: 8f70bb1d06c25d3da17ea991b4a5ead5732cbf2c
- source_sha_after_merge: d60aca36a8a9841974402f9b3c5b0f9db859129b
- exact_proven_pr_head: 6aa6bba07baab305d609424d1cefb87aaf4b05de
- production_runtime_file: matched_ablation_runner.py
- production_runtime_blob: 37bc91dacd3cc623c91976ac3f6e1c8c7ffbf1f4
- proof_workflow: Adaptive Worker Integrity
- proof_run: 32263673927

## Donor SHAs / recovery lineage
- prior_main: 8f70bb1d06c25d3da17ea991b4a5ead5732cbf2c
- prior_runner_blob: 2b426629c2c95da39e98b792c6cfb00fe755ce95
- causal_recorder_merge: 31395764dd843ea729d00638c2bacc5328ee3a10
- reliability_selector_merge: 8cb7251ae11d38b5d509236964a74539aef4becb

## Selected priority
- tier: P0
- priority: Eliminate production topology corruption after matched ablation execution. The runner permanently left the shared AdaptiveTaskOrchestrator in its one-worker-removed topology, causing later missions to inherit an experimental topology unintentionally.

## Blocked higher candidates
- P1 xAI ready_for_human_submission=true remains blocked on explicit applicant-controlled values for unresolved live Greenhouse fields. No applicant value was inferred.
- No stronger executable P0 was found before this live state-corruption defect.

## Displaced capability / defect
The matched-ablation runner correctly executed a baseline and exact one-worker-removed child, scored both under one rubric, and promoted causal value. However, it mutated `orchestrator.worker_profiles` and `orchestrator.num_agents` for the child run and never restored them. A successful experiment therefore contaminated subsequent production topology. Any exception during the ablated execution could also strand the shared orchestrator in the reduced topology.

## Mechanisms compared
1. Reconstruct topology from persisted next_roles after the experiment: rejected because persisted next topology is adaptive state, not necessarily the exact pre-experiment runtime object state.
2. Instantiate a second orchestrator for the ablated run: rejected because it weakens shared-memory/runtime continuity and creates extra provider/runtime state with different initialization behavior.
3. Selected transactional mutation: snapshot exact pre-ablation profiles and agent count, perform the child experiment inside try/finally, and restore exact runtime state on success and every exception path.

## Implemented delta
- `execute_matched_worker_ablation()` now snapshots the exact pre-ablation `worker_profiles` and `num_agents`.
- One-worker removal occurs only inside a transactional try/finally region.
- Exact original profile ordering and agent count are restored after successful causal promotion.
- Exact original topology is also restored if provider execution, report validation, topology validation, or causal recording raises.
- The success receipt now includes `orchestrator_topology_restored` for explicit runtime readback.
- Existing full-vs-ablated causal truth boundary, persisted experiment lineage, system-level rubric, and causal promotion path remain unchanged.

## Preserved gains
- No changes to worker experiment schemas or longitudinal metrics.
- No changes to causal scoring semantics.
- No changes to role-selection logic.
- No inference of applicant-controlled data.
- No whole-repository revert.
- Existing exact one-worker removal and mission-family/comparison-key lineage remain intact.

## Tests / runtime proof
- PR: #46
- exact proven head: 6aa6bba07baab305d609424d1cefb87aaf4b05de
- Adaptive Worker Integrity run: 32263673927 — PASS
- workflow status: completed
- workflow conclusion: success
- adversarial proof includes successful causal promotion with exact topology restoration and injected ablated-run provider failure with exact topology restoration.
- exact-head squash merge: d60aca36a8a9841974402f9b3c5b0f9db859129b
- post-merge readback confirmed `matched_ablation_runner.py` blob 37bc91dacd3cc623c91976ac3f6e1c8c7ffbf1f4 on `main`.

## Exact target files / functions
- matched_ablation_runner.py: `execute_matched_worker_ablation`
- tests/test_matched_ablation_runner.py: success-path topology restoration and exception-path topology restoration

## Top 3 remaining priorities
1. P1: bind explicit applicant-confirmed xAI values and produce the real `ready_for_human_submission=true` package without external submission.
2. P2: execute the first independently provable stranded job-ecosystem repository-family restoration through exact-SHA recovery in that repository's native runtime.
3. P2: compose bounded matched-ablation sampling into live adaptive operation so causal evidence is generated periodically without contaminating normal runtime topology.

## Next sequence
1. Recheck the P1 applicant-value lane only if explicit values are actually available; never infer them.
2. Otherwise inspect stranded job-ecosystem branches/repos for an exact-SHA recovery target with native proof.
3. If no stronger restoration is executable, add bounded causal sampling orchestration using the now-safe transactional ablation runner.

## Merge / deploy gate
- Exact-head target-native proof passed on run 32263673927.
- Exact-head squash merge passed at d60aca36a8a9841974402f9b3c5b0f9db859129b.
- Post-merge runtime readback passed.
- No external application submission occurred.

## Rollback
Revert merge `d60aca36a8a9841974402f9b3c5b0f9db859129b` to restore prior matched-ablation behavior while preserving all earlier causal-learning infrastructure.

## No-loss invariants
- Never leave a shared production orchestrator in an experimental ablated topology.
- Never infer causal value from observational history alone.
- Never accept an ABLATION child that differs from the parent by anything other than exactly one removed worker.
- Never cross mission-family or comparison-key boundaries when recording causal value.
- Never weaken mandatory source, adversarial, or proof role protection.
- Preserve exact pre-experiment runtime state across success and failure paths.
