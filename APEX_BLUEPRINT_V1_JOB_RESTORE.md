# APEX_BLUEPRINT_V1

lane: JOB_RESTORE
verified_executable_capability_delta: YES

## Current source
- owning_repo: GlacierEQ/make-it-heavy
- source_sha_before_cycle: 96368511ba2885910f79c90a2efffd6fcf708f6c
- exact_proven_pr_head: 9a6ecf19962a8ef49ceeba4927ab36617ebc3fa9
- source_sha_after_merge: 8ceac0a1c0cb9e73a36a1b1c1e108f40c78149c8
- production_runtime_file: causal_sampling_runner.py
- production_runtime_blob: becdb7e4f71a93fa725089bff6ba423f4a4ca7fd
- proof_workflow: Adaptive Worker Integrity
- proof_run: 32265461488

## Donor SHAs / recovery lineage
- prior_main: 96368511ba2885910f79c90a2efffd6fcf708f6c
- transactional_ablation_merge: d60aca36a8a9841974402f9b3c5b0f9db859129b
- transactional_runner_blob: 37bc91dacd3cc623c91976ac3f6e1c8c7ffbf1f4
- causal_recorder_merge: 31395764dd843ea729d00638c2bacc5328ee3a10
- reliability_selector_merge: 8cb7251ae11d38b5d509236964a74539aef4becb

## Selected priority
- tier: P2
- priority: Compose bounded matched-ablation sampling into live adaptive operation so real production turns periodically generate causal worker evidence without contaminating ordinary runtime topology.

## Blocked higher candidates
- P1 xAI ready_for_human_submission=true remains blocked on explicit applicant-controlled values for unresolved live Greenhouse fields. No applicant value was inferred.
- The independent stranded-repository restoration lane remained a strong P2, but no stronger target-native recovery candidate was established before this already named, fully executable continuation from the prior verified handoff.

## Displaced capability
The system had a proven matched-ablation runner and a live causal-aware topology selector, but causal experiment execution remained manually invoked. Ordinary adaptive operation did not have a bounded execution surface that could preserve normal single-turn behavior on most turns while automatically generating real matched causal measurements at selected intervals.

## Mechanisms compared
1. Keep matched ablation manual-only: rejected because production causal evidence generation remains operator-triggered and sparse.
2. Inject recursive sampling directly inside `AdaptiveTaskOrchestrator.orchestrate()`: rejected because the ablation runner itself calls the orchestrator and an in-method hook would create re-entrancy/recursion risk and couple experiment scheduling to core mission execution.
3. Selected nonlinear composition: add a production wrapper that executes exactly one ordinary mission on normal turns and delegates only due sample turns to the already-proven transactional matched-ablation runner. Deterministic optional-role rotation expands causal coverage while mandatory evidence/proof roles remain protected.

## Implemented delta
- Added `causal_sampling_runner.py` as a real production CLI/runtime surface around `AdaptiveTaskOrchestrator`.
- `should_sample()` validates positive 1-based cadence and selects only configured interval turns.
- `select_removal_role()` validates topology, never removes `source_mapper`, `adversarial_breaker`, or `proof_engineer`, and deterministically rotates across removable optional roles.
- `execute_bounded_causal_turn()` executes exactly one ordinary production mission when sampling is not due.
- A due turn with no optional removable role safely degrades to one ordinary mission rather than weakening mandatory coverage.
- A due turn with an optional role delegates to `execute_matched_worker_ablation()`, preserving exact full-vs-parent-minus-one causal execution and transactional topology restoration.
- CLI emits `glaciereq.make-it-heavy.causal-sampling-runner.v1` receipts distinguishing normal turns from bounded causal samples.

## Refinement / failure isolation
- Initial exact-head run 32265103136 failed two new normal-path tests across the Python matrix.
- The failure was isolated to the borrowed deterministic test fixture, whose `orchestrate()` intentionally required experiment metadata on every call.
- Production code was not weakened or changed to fake normal turns as experiments.
- The fixture was refined with `NormalCapableExperimentOrchestrator`, which handles plain normal missions independently while preserving the existing matched-ablation fixture for experiment-tagged sample turns.

## Preserved gains
- Exact matched-ablation causal promotion remains the only path that earns causal credit.
- Transactional restoration of shared `worker_profiles` and `num_agents` remains intact.
- Mandatory `source_mapper`, `adversarial_breaker`, and `proof_engineer` roles are never selected for removal by the sampler.
- Ordinary non-sample turns remain ordinary production missions, not experiment-tagged simulations.
- Existing adaptive topology, provider execution, memory, semantic/claim gates, and reliability-aware portfolio learning are unchanged.
- No whole-repository revert and no applicant-controlled value inference.

## Tests / runtime proof
- PR: #47
- initial head: f788ad620e50f3bf70e62c66524ac8134799aa38
- initial Adaptive Worker Integrity run: 32265103136 — FAILED only in two new normal-path fixture tests after compile succeeded
- refined exact proven head: 9a6ecf19962a8ef49ceeba4927ab36617ebc3fa9
- replacement Adaptive Worker Integrity run: 32265461488 — PASS
- Python 3.9 job 96108731781: PASS
- Python 3.10 job 96108731780: PASS
- Python 3.11 job 96108732131: PASS
- Python 3.12 job 96108731889: PASS
- Python 3.13 job 96108731938: PASS
- every replacement matrix lane passed compileall, complete unittest discovery, and innovation/receipt boundary verification.
- exact-head squash merge: 8ceac0a1c0cb9e73a36a1b1c1e108f40c78149c8
- post-merge `main` readback confirms `causal_sampling_runner.py` blob becdb7e4f71a93fa725089bff6ba423f4a4ca7fd.

## Exact target files / functions
- causal_sampling_runner.py: `should_sample`
- causal_sampling_runner.py: `select_removal_role`
- causal_sampling_runner.py: `execute_bounded_causal_turn`
- tests/test_causal_sampling_runner.py: bounded cadence, mandatory-role protection, rotation, normal execution, matched sample execution/topology restoration, no-optional fallback, duplicate-topology refusal

## Top 3 remaining priorities
1. P1: bind explicit applicant-confirmed xAI values and produce the real `ready_for_human_submission=true` package without external submission.
2. P2: execute the first independently provable stranded job-ecosystem repository-family restoration through exact-SHA recovery and prove recovered behavior in that repository's native runtime.
3. P2: if still highest-value after the independent restoration check, derive sampling cadence from durable mission history/persistent sampler state so bounded causal sampling survives process restarts without a caller-supplied turn index.

## Next sequence
1. Prefer the P1 xAI completion immediately only when explicit applicant values are actually available; never infer them.
2. Otherwise force the next cycle toward an independent stranded repository-family restoration rather than extending this Make-It-Heavy micro-track by default.
3. Return to persistent cadence state only if that independent restoration lane is blocked or lower-value after fresh source inspection.

## Merge / deploy gate
- Exact-head target-native proof passed on run 32265461488 across Python 3.9-3.13.
- Exact-head squash merge completed at 8ceac0a1c0cb9e73a36a1b1c1e108f40c78149c8.
- Post-merge production source readback passed for blob becdb7e4f71a93fa725089bff6ba423f4a4ca7fd.
- No external application submission occurred.

## Rollback
Revert merge `8ceac0a1c0cb9e73a36a1b1c1e108f40c78149c8` to remove bounded causal sampling while preserving the previously proven matched-ablation, topology-restoration, causal-history, and reliability-aware selection infrastructure.

## No-loss invariants
- Never infer causal value from observational history alone.
- Never ablate mandatory source, adversarial, or proof roles through periodic sampling.
- Never execute more than one normal mission on a non-sample turn.
- Never accept a matched ablation whose child differs from the parent by anything other than exactly one removed worker.
- Never leave a shared production orchestrator in experimental topology after success or failure.
- Preserve exact mission-family/comparison-key causal lineage and the identical outcome rubric.
