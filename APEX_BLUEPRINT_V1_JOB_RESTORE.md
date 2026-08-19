# APEX_BLUEPRINT_V1

lane: JOB_RESTORE
verified_executable_capability_delta: YES

## Current source
- owning_repo: GlacierEQ/make-it-heavy
- source_sha_before_cycle: e9591aa00da2f923a99de9255f323da569c28f7a
- prior_ranker_merge_sha: 11df62bb3bcf9b8e78926ce1f6baaef0b3c39abb
- exact_proven_pr_head: 9337042e699640b976c39009c00631a552c63302
- source_sha_after_merge: 13c642b8c9d007cc78c3d4b9b47dd9705c759b86
- production_runtime_file: recovery_candidate_verifier.py
- production_runtime_blob_sha: 3fea9cd927067c8566abf856c0f7be75e5bd7d81
- tests_file: tests/test_recovery_candidate_verifier.py
- production_runtime_readback: PASS on merged source

## Selected priority
- tier: P2
- target: convert corpus-ranked historical recovery candidates into current GitHub-lineage-verified restoration candidates before mutation
- operator_value: prevents stale export evidence from wasting restoration cycles and exposes which exact donor/PR candidates are still stranded or currently missing

## Higher candidates / pivots
- P1 BLOCKED: real xAI ready_for_human_submission=true still requires explicit applicant-controlled values; no value was inferred.
- P1 BLOCKED_THIS_RUN: GlacierEQ/job-app PR #8 restores transactional application-integrity runtime, but exact-head private-repo workflow run 32258846358 failed before exposing any executable steps; job-app CI therefore was not promoted as code proof and the run pivoted.
- P2 EXECUTED: live recovery-candidate verification in GlacierEQ/make-it-heavy.

## Mechanisms compared
1. Treat corpus ranking as current repository truth. Rejected: export history is evidence, not current Git state.
2. Search GitHub text/state only. Rejected: search cannot establish donor ancestry or exact merge state.
3. Selected nonlinear composition: provenance ranker output + current default-head SHA + exact donor/default compare + referenced PR state + fail-closed attribution.

## Implemented delta
- Added read-only GitHub REST client with explicit errors and token support.
- Added exact repository/default-head resolution.
- Added donor/default comparison semantics: DEFAULT_AT_DONOR, DONOR_IN_DEFAULT_HISTORY, DEFAULT_BEHIND_DONOR, DIVERGED_FROM_DEFAULT, DONOR_UNRESOLVED.
- Added PR state/merged-state verification.
- Added restoration classifications: ALREADY_RESTORED, STILL_STRANDED, CURRENTLY_MISSING, DONOR_MISSING, SUPERSEDED_OR_ABANDONED, REVERIFY_MANUALLY.
- Added executable_now only for STILL_STRANDED or CURRENTLY_MISSING.
- Added hard fail-closed behavior for ambiguous multi-repository/multi-donor/multi-PR provenance instead of inventing positional relationships.
- Added deterministic APEX_RECOVERY_CANDIDATE_VERIFICATION_V1 report and CLI output.

## Preserved gains
- corpus_miner.py provenance, FTS, reconciliation, and secret-safe inventory behavior unchanged.
- recovery_candidate_ranker.py scoring, secret redaction, deterministic ordering, and repository/commit/PR extraction unchanged.
- adaptive worker, longitudinal reliability, causal metrics, matched ablation, and production sampling mechanisms unchanged.
- historical corpus is still not promoted to repository truth without live verification.

## Tests / runtime proof
- pull_request: GlacierEQ/make-it-heavy#50
- workflow: Adaptive Worker Integrity run 32282321466
- exact_head: 9337042e699640b976c39009c00631a552c63302
- Python 3.9 job 96163721096: PASS
- Python 3.10 job 96163721199: PASS
- Python 3.11 job 96163721211: PASS
- Python 3.12 job 96163720878: PASS
- Python 3.13 job 96163721260: PASS
- each lane: checkout PASS; dependency install PASS; compile every Python module PASS; complete unittest suite PASS; innovation/receipt-boundary verification PASS
- exact-head squash merge: 13c642b8c9d007cc78c3d4b9b47dd9705c759b86
- post-merge runtime readback: PASS, blob 3fea9cd927067c8566abf856c0f7be75e5bd7d81

## Top 3 remaining priorities
1. P1: when explicit applicant-controlled xAI values are available, bind them and generate the real ready_for_human_submission=true package without external submission.
2. P1: repair/prove GlacierEQ/job-app PR #8 transactional application-integrity companion through an executable private-repo proof surface; if private Actions remains infrastructure-blocked, use a different authorized runtime rather than promoting static review.
3. P2: feed a real accumulated APEX_RECOVERY_CANDIDATE_RANKING_V1 artifact through recovery_candidate_verifier.py, select the highest executable_now exact-attribution candidate, and perform its exact-SHA target-native restoration.

## Exact continuation targets
- recovery_candidate_verifier.py: verify_candidate, verify_repository_candidate, _compare_relation, main
- recovery_candidate_ranker.py: candidate_report/main output is the verifier input contract
- next restoration target: highest live-verified candidate with executable_now=true and one exact repository/donor attribution

## Next sequence
1. Generate ranking from real corpus with recovery_candidate_ranker.py --require-repository.
2. Run recovery_candidate_verifier.py against that ranking using read-only GitHub access.
3. Discard ALREADY_RESTORED, DONOR_MISSING, SUPERSEDED_OR_ABANDONED, and REVERIFY_MANUALLY from automatic mutation.
4. Re-rank STILL_STRANDED/CURRENTLY_MISSING by original recovery score and operator leverage.
5. Inspect exact donor diff/current source of the winner; restore valuable mechanisms individually, never whole-repo revert.
6. Run target-native adversarial/runtime proof, exact-head merge, post-merge readback.

## Merge / deploy gate
- merge only exact tested head.
- no historical corpus candidate may trigger restoration mutation without current GitHub verification.
- no ambiguous provenance may be automatically paired or mutated.
- target-native executable proof is required before declaring the next restoration successful.

## Rollback
- revert merge 13c642b8c9d007cc78c3d4b9b47dd9705c759b86 to remove the verifier while preserving the prior ranker/corpus/runtime stack.

## No-loss invariants
- never blind-revert a repository.
- never treat repeated export conversation text as corroboration.
- preserve exact source/donor SHAs and evidence hashes.
- preserve stronger later code/interfaces during restoration.
- fail closed on ambiguous repository-to-donor attribution.
- governance/receipts/docs remain support only; executable capability remains the mission.
