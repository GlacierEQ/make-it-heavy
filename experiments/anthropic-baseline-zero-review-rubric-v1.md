# Baseline Zero supervisory quality rubric v1

This rubric exists because the legacy Make-It-Heavy `benefit_score` is a structural heuristic and lexical quality scoring can reward technical-looking output that reverses evidence states. This rubric is supervisory, observational, and non-causal. It must be held constant for the matched Turn 1 comparison unless a new experiment family is started.

## Quality dimensions

Quality is reported on a 0–100 scale using five dimensions:

- **Contract coverage — 20%**: required role sections are present and the worker stays inside its assigned job.
- **Evidence-state fidelity — 30%**: VERIFIED / UNVERIFIED / NONCLAIM / PROPOSED / BLOCKED states are preserved without promotion, inversion, or unsupported corroboration.
- **Role precision — 15%**: the output contributes the distinctive analysis expected from this role rather than generic synthesis.
- **Falsifiability and actionability — 15%**: recommendations or tests are specific enough to execute or disconfirm without presenting proposed thresholds as observed facts.
- **Uncertainty discipline — 20%**: uncertainty, missing proof, employer-fit limits, novelty limits, and unsupported quantitative claims remain explicit.

`quality = 0.20*contract + 0.30*evidence_fidelity + 0.15*role_precision + 0.15*falsifiability + 0.20*uncertainty_discipline`

## Severity rules

- **MATERIAL_EVIDENCE_ERROR**: a worker converts an explicit nonclaim/unverified field into supported evidence, or the role's core proof responsibility is violated. This is never hidden by a high presentation/structure score.
- **MATERIAL_OVERREACH**: a worker converts an unrun experiment, inferred interface, or unsupported employer-access assumption into a present fact or categorical conclusion.
- **CALIBRATION_GAP**: a proposed experiment contains useful but ungrounded thresholds/sample sizes. This remains a proposal rather than an evidence failure when clearly separated from observed facts.
- **PASS_WITH_LIMITS**: useful role execution with bounded, explicit uncertainty.

## Causal boundary

This rubric does **not** measure marginal system value or outcome leverage. Those fields remain `null` until full-vs-ablated synthesis is performed against the same outcome rubric.

## Timing and overlap boundary

The direct SparkForge connector return used for this first production specimen did not expose per-call wall-clock timing or a persistent raw-output handle suitable for exact token/sentence-overlap computation. Those fields must remain `null` in the Baseline Zero receipt. No estimate may be substituted. The next matched run must route through a persistence/timing path before it can satisfy those telemetry fields.