# APEX_BLUEPRINT_V1

lane: JOB_RESTORE
verified_executable_capability_delta: YES

## Current source
- owning_repo: GlacierEQ/make-it-heavy
- source_sha_before_cycle: 0f222ed316ad87ad8026bc15ae20687956e4b10d
- exact_proven_pr_head: adc7f8696694dce4bac95dd8ca950a338b486942
- source_sha_after_merge: 11df62bb3bcf9b8e78926ce1f6baaef0b3c39abb
- production_runtime_file: recovery_candidate_ranker.py
- production_runtime_readback: PASS on main

## Donor SHAs / recovery lineage
- provenance_corpus_merge: 0f222ed316ad87ad8026bc15ae20687956e4b10d
- corpus_runtime_blob: 62ca74be4e7e7449c0e9affe630d45dd2c6112e4
- prior_causal_sampling_main: 25b79619d9c69a59a4ba4e911a811ad73e77261a

## Selected priority
- tier: P2
- priority: Convert the restored provenance corpus into an executable recovery-candidate intelligence layer that automatically surfaces lost, clipped, deleted, stranded, or regressed job-ecosystem mechanisms with repository/commit/PR provenance.

## Blocked higher candidates
- P1 xAI ready_for_human_submission=true remains blocked on explicit applicant-controlled values for unresolved live Greenhouse fields. No applicant answer was inferred.

## Live queue
1. P1 BLOCKED: applicant-confirmed xAI finalization values.
2. P2 EXECUTED: corpus-driven executable restoration candidate ranking.
3. P2 NEXT: use ranked corpus evidence to drive an exact-SHA repository-native recovery.

## Mechanisms compared
1. Historical-only/manual grep: rejected because it leaves recovery selection dependent on repeated human archaeology.
2. Modern semantic/LLM-only ranking: rejected as the primary mechanism because it would weaken determinism, provenance, offline execution, and secret-boundary control.
3. Selected nonlinear combination: reuse the hardened provenance corpus, add deterministic recovery/executability/proof scoring, extract repo/commit/PR lineage, preserve evidence hashes, redact secret-like values, and emit a machine-readable candidate queue that can drive later exact-SHA restoration.

## Implemented delta
- Added `recovery_candidate_ranker.py` as a real executable runtime.
- Requires both recovery evidence and executable-capability evidence before a corpus row can become a candidate.
- Scores recovery, executability, proof strength, blocker cost, and provenance density.
- Extracts repository names, commit SHAs, and PR numbers from source evidence.
- Emits deterministic `APEX_RECOVERY_CANDIDATE_RANKING_V1` JSON.
- Supports `--require-repository`, bounded `--limit`, stdout output, and persisted `--output` artifacts.
- Redacts GitHub/OpenAI-like secret values from human-readable excerpts while preserving SHA-256 evidence identity.
- Added `tests/test_recovery_candidate_ranker.py` covering ranking, noise rejection, provenance extraction, secret redaction, evidence hashing, and output bounds.

## Tests / runtime proof
- PR: #49
- branch: apex/job-restore-corpus-recovery-ranker-20260819
- exact head: adc7f8696694dce4bac95dd8ca950a338b486942
- local executable proof: synthetic provenance corpus produced deterministic ranking with `e-strong` score 85.5 above secret-bearing candidate 44.5 and maintenance candidate 36.0; non-recovery noise was excluded; secret text was redacted while evidence hash remained available.
- exact-head squash merge: 11df62bb3bcf9b8e78926ce1f6baaef0b3c39abb
- post-merge main readback: `recovery_candidate_ranker.py` present and source-complete.

## Preserved gains
- Existing `corpus_miner.py` ingestion, reconciliation, FTS5 search, classification, integrity summaries, and secret inventory remain unchanged.
- Existing adaptive worker, matched-ablation, causal-sampling, memory, semantic gates, and provider runtime are untouched.
- No whole-repository revert and no applicant-controlled value inference.

## Exact target files / functions
- recovery_candidate_ranker.py: `_candidate_from_row`
- recovery_candidate_ranker.py: `rank_recovery_candidates`
- recovery_candidate_ranker.py: `candidate_report`
- tests/test_recovery_candidate_ranker.py

## Top 3 remaining priorities
1. P1: bind explicit applicant-confirmed xAI values and produce the real `ready_for_human_submission=true` package without external submission.
2. P2: run the new recovery candidate ranker against the real accumulated export corpus, take the highest attributable unblocked job-ecosystem candidate, and execute its exact-SHA restoration in the owning repository's native runtime.
3. P2: add corpus-to-GitHub verification that distinguishes historical claims from repository-current facts before automatically promoting a recovery candidate into an execution queue.

## Next sequence
1. Ingest the strongest available real export corpus into the hardened corpus DB.
2. Execute `python recovery_candidate_ranker.py --db <db> --require-repository --limit 20`.
3. Re-observe the top candidate's repository/commit/PR state from GitHub.
4. Recover only the missing useful mechanism onto current main-compatible code, preserving stronger later gains.
5. Prove in the target repository's own runtime, exact-head merge, and read back.

## Merge / deploy gate
- Exact-head PR #49 merged only with expected head adc7f8696694dce4bac95dd8ca950a338b486942.
- Main merge SHA: 11df62bb3bcf9b8e78926ce1f6baaef0b3c39abb.
- Post-merge source readback passed.

## Rollback
Revert merge `11df62bb3bcf9b8e78926ce1f6baaef0b3c39abb` to remove only the recovery-candidate ranking layer while preserving the provenance corpus and all prior runtime gains.

## No-loss invariants
- Never promote documentation-only evidence as an executable recovery candidate without executable signals.
- Never expose raw secret-like values in ranking excerpts.
- Never treat corpus history as proof that a repository is currently missing capability; GitHub/source re-observation remains mandatory before mutation.
- Never blindly revert a whole repository.
- Preserve exact evidence hashes and extracted donor provenance through recovery selection.
