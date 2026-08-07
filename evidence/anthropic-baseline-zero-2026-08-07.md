# Anthropic Worker Baseline Zero — Evidence Snapshot

Snapshot date: 2026-08-07 HST.
Purpose: bounded evidence field for the first longitudinal Make-It-Heavy flagship-employer experiment. This file records source-derived observations; it does not assert Anthropic affiliation, adoption, or novelty.

## External Anthropic engineering evidence

E1. Anthropic, “Demystifying evals for AI agents” (2026-01-09): agent evaluations should measure final environment outcomes, use robust harnesses, isolate trials, and avoid shared-state/infrastructure confounders. Source: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
E2. Anthropic, “Quantifying infrastructure noise in agentic coding evals” (2026-02-05): resource configuration and infrastructure failures can shift agentic benchmark results enough to obscure small model differences; resource methodology should be treated as an experimental variable. Source: https://www.anthropic.com/engineering/infrastructure-noise
E3. Anthropic, “Harness design for long-running application development” (2026-03-24): separating generation from skeptical evaluation, decomposing work, and using structured handoff artifacts can improve long-running agent systems; self-evaluation is prone to leniency. Source: https://www.anthropic.com/engineering/harness-design-long-running-apps
E4. Anthropic, “Trustworthy agents in practice” (2026-04-09): greater agent autonomy creates risks from misunderstood intent, unintended actions, and prompt injection. Source: https://www.anthropic.com/research/trustworthy-agents
E5. Anthropic, “How we contain Claude across products” (2026-05-25): as agent capability and access increase, blast radius becomes an engineering constraint; containment boundaries complement or replace repeated human approval prompts. Source: https://www.anthropic.com/engineering/how-we-contain-claude

## GlacierEQ mapped repository evidence

R1. GlacierEQ/anthropic-agent-coordinator canonical head ac977563cfd59deb8e87177f53082184f6468aa8 implements a deterministic dependency-aware scheduler with explicit global budget, per-role capacity, stable-priority waves, dependency validation, cycle rejection, and explicit deferral states. Canonical implementation: src/anthropic_agent_coordinator/coordinator.py.
R2. anthropic-agent-coordinator receipt reports 62 collected/executed/passed tests on Python 3.13.5 with zero failures/errors/skips, while explicitly marking hosted Python 3.11–3.13 matrix verification, provider calls, production scale, and deployment as unverified/nonclaims. Receipt: receipts/wave-1-test-verification-2026-07-31.json.
R3. GlacierEQ/anthropic-safety-monitor canonical head a5c21172e32ce6054994402c38d86f7ef94bc56b implements structural review of proposed tool calls with ALLOW/CONFIRM/DENY decisions and explicit rules for destructive shell operations, forced Git pushes, Kubernetes deletion, Terraform destroy, database table deletion, dynamic shell expansion, and host availability changes. Canonical implementation: src/anthropic_safety_monitor/policy.py.
R4. anthropic-safety-monitor receipt reports a successful Python 3.11/3.12/3.13 workflow matrix with 51 tests per version and 153 total matrix executions, while explicitly disclaiming tool execution, semantic-safety completeness, automatic approval, production detection coverage, deployment verification, and Anthropic affiliation. Receipt: receipts/wave-1-test-verification-2026-07-31.json.
R5. GlacierEQ/anthropic-alignment-drift head ac39701f9d7a3b27991847a2b3332a6f406a654b contains one principal source file implementing windowed permission/risk trend comparisons and threshold-triggered drift/isolation state; its docstring asserts novelty but the inspected repository root contains no README, package metadata, tests, or verification receipt supporting that novelty claim.
R6. GlacierEQ/anthropic-byzantine-consensus head 4e142059ace9a13d84824cdb4c6fb6ac9c0d199f contains a single principal consensus implementation using 3f+1-derived thresholds, weighted approvals, heuristic suspicion scoring, trust decay, and manual isolation; the inspected root exposes no test or receipt surface, so fault-tolerance correctness and safety claims remain unverified.
R7. GlacierEQ/anthropic-cross-domain-fusion head 28d55f9bf4b38336bf209efa4161f7ba7715399c contains a small confidence/uncertainty-weighted state fusion prototype; its current executable example uses propulsion and orbital state rather than agent interpretability, and the inspected root exposes no test or receipt surface.

## Baseline truth boundary

T1. The evidence supports testing an intersection around reliable autonomous-agent harnesses: coordination, safety boundaries, evaluation discipline, and longitudinal behavior measurement. It does not establish that this is Anthropic’s single “hardest” engineering problem.
T2. The two promoted public repositories have materially stronger proof than the three private candidate repositories. The baseline must preserve that asymmetry rather than averaging repo names into false corroboration.
T3. The experiment must treat any claimed novel combined solution as PROPOSED until a new artifact and falsifiable proof differentiate it from existing harness, safety-policy, drift-detection, and consensus techniques.
