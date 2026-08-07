# Make-It-Heavy Worker Turn 3 — Helix Proof Identity

Run: `mih-turn3-helix-proof-identity-2026-08-06-sparkforge-v1`

## Outcome

Seven logical SparkForge lanes completed with one-provider serialized execution and zero silent omissions. Mechanical lane PASS was treated only as a structural gate. Unsupported worker specifics were quarantined before any repository action.

The surviving source-reviewed defect was narrow: the Helix proof-weighted audit could execute against a mutable ref while its featured verification receipt did not independently bind the result to the exact checked-out commit.

## Repair chain

1. A first proof-identity branch was built and verified, but became stale after unrelated canonical CI debt had to be repaired.
2. Baseline cleanup stayed separate and merged through PR #44 as `4008d20be09401330059d07df0f90f6e9505fe21`.
3. Stale proof PR #43 was closed unmerged; its useful value was replayed onto fresh ancestry.
4. The fresh proof branch evolved under expected-head guards to add exact commit binding, pytest collection proof, source-derived root-truth counting, regression tests, and exact-head self-verification.
5. Exact head `5f922b53cba13ff7a7db401df0ecc02a6c1957bb` passed CI, Application Registry Validation, Portfolio Root Truth, Proof Identity Self Verification, and the full Proof-weighted portfolio audit.
6. Independent artifact readback showed `ref: main` and immutable `resolved_commit_sha` were preserved separately while a failing AKOS workload remained `FAILED`.
7. PR #45 was squash-merged with an expected-head guard as canonical Helix commit `b613a70766586511199266d63499bd31d2808b97`.

## Investigator lesson

Source IDs are necessary provenance, not factual proof. Turn 3 demonstrated that a worker can satisfy a mechanical citation/claim gate while still overstating what a source entails. Future turns therefore preserve two distinct gates:

- structural/source-anchor validity;
- semantic entailment before evidence promotion.

## Durable turn receipt

Authoritative execution-store result SHA256:

`37587e6ba3d59e0511e2c78041506c42c75eeac41ca30f75eb8a5307ff53acab`

Repository closeout receipt:

`receipts/worker-turn-03-2026-08-07.json`

The receipt explicitly preserves the semantic quarantine and does not advance Helix's older `verified_commit` checkpoint solely because the repair merged.
