# Worker Baseline Zero — Raw Genuine Outputs

## source_mapper

- Provider: `henry-ships-sparkforge.smart_summarize`
- Quality: **96.00/100**
- Marginal benefit: **0.9880**
- Execution time: **12.359s**
- Response SHA-256: `80ebf21cb23aeb283713c13628351b60de75228434ce6e8d5c1ef21450bd28dd`

[TECHNICAL]

## SOURCES

**Source 1: GlacierEQ/job-app-helix@f3b2092fe0709a6532202a007852121d1ca982e4 — docs/48_TRACK_BOTTLENECK_ATLAS.md**
- Commit hash verified in packet
- Stated purpose: maps company pressure, inferred bottlenecks, GlacierEQ systems, leverage, application moves, and next evidence gates
- Scope: 48 source-backed company application tracks
- Status: first-depth atlas (implies deeper analysis unresolved)

**Source 2: GlacierEQ/job-app-helix@f3b2092fe0709a6532202a007852121d1ca982e4 — manifests/company_intelligence.json**
- Same repository and commit hash as Source 1
- Stated purpose: company intelligence manifest (format and content structure not detailed in packet)

**Source 3: GlacierEQ/make-it-heavy@3d49c629fc47ffd965e4cdba43c37d7d9cfbba4a — templates/innovation_workers.yaml**
- Distinct repository (make-it-heavy, not job-app-helix)
- Commit hash verified in packet
- Stated purpose: worker role templates (specific template contents not detailed in packet)

## SUPPORTED OBSERVATIONS

1. **Portfolio Structure:** Casey operates connected multi-repository systems (job-app-helix + make-it-heavy at minimum), not isolated single repositories.
2. **Bottleneck Mapping Exists:** First-depth analysis of 48 company application tracks with documented pressure points, inferred blockers, and GlacierEQ system mappings is available.
3. **Staged Depth:** Analysis explicitly separates first-depth (atlas complete) from second-depth (code inspection + role reconciliation unresolved), indicating tiered methodology.
4. **Source Anchoring:** All three sources are pinned to specific commits, enabling reproducibility and version control.

## CONTRADICTIONS OR GAPS

1. **Content Unverified:** No packet excerpt or checksum validates the *actual content* of the three sources; their existence is asserted but internal structure is opaque.
2. **Live Reconciliation Gap:** The packet explicitly disclaims code inspection completion, live opening reconciliation, or employer adoption verification—second-depth gate remains open.
3. **Worker Prompt Scope:** This SOURCE MAPPER role is assigned only source location and support validation; it does not include content extraction, code analysis, or decision ranking (those are mission-level objectives for other workers).
4. **Missing Reference:** No sample from docs/48_TRACK_BOTTLENECK_ATLAS.md or company_intelligence.json is provided to test source reliability.

## HANDOFF

**To Next Worker (likely CONTENT EXTRACTOR or CODE INSPECTOR):**

- All three source anchors are verified as cited in the packet.
- First-depth bottleneck atlas and company intelligence manifest are ready for extraction.
- Innovation_workers.yaml templates available for role definition.
- **Blocker:** Second-depth code inspection and live role reconciliation explicitly not yet complete; expect unresolved evidence gaps when content is accessed.
- **Recommendation:** Prioritize Sources 1 and 2 (job-app-helix) as primary payload; use Source 3 to validate worker role framework before executing proof compilation.

---

**NEXT-TURN TEMPLATE ADJUSTMENT:** Add a fourth required output heading `## SOURCE VERIFICATION CONFIDENCE MATRIX` with rows for each source showing [Commit Pinned: Y/N] [Content Sampled: Y/N] [Scope Bounded: Y/N] to distinguish asserted availability from verified accessibility before handoff.

## bottleneck_cartographer

- Provider: `henry-ships-sparkforge.smart_summarize`
- Quality: **89.60/100**
- Marginal benefit: **0.9688**
- Execution time: **0.883s**
- Response SHA-256: `a49673b4680feae1731e5b3f3c7a0171773beb0334a624fb6d6777ef541339ab`

[EXECUTIVE]

# SYSTEM PATH
Job-App Helix currently maintains 48 source-backed company tracks mapping organizational pressures, inferred bottlenecks, and GlacierEQ systems. The existing atlas documents leverage points and application moves with evidence gates, providing directional insight into company dynamics.

# CURRENT BOTTLENECK
The system lacks repository-by-repository code inspection and current-role reconciliation. Without these inputs, bottleneck mapping remains inference-dependent rather than code-grounded, creating gaps between mapped pressures and verifiable technical reality.

# BRICK WALL
Generating reproducible proof requires integrating source-level evidence that the current architecture doesn't systematically capture. The design challenge is producing code-evidence sheets that support truth-bounded claims while avoiding unfounded assertions about company state.

# DISCONFIRMING TEST
**Design inference:** A Company Proof Compiler would succeed if it rejects applications where code inspection contradicts mapped bottlenecks—for example, detecting that a claimed infrastructure constraint has already been resolved. This requires building a falsifiability mechanism: proof claims must be testable against repository state, not merely consistent with historical pressure mapping.

# HANDOFF
The proposed four-decision framework (APPLY_NOW / REPAIR_THEN_APPLY / WATCH / NO_MATCH) should map to confidence bands in compiled proofs. APPLY_NOW requires high-confidence alignment between code-level evidence and role-fit. REPAIR_THEN_APPLY signals actionable misalignment. WATCH preserves judgment-pending states. NO_MATCH indicates disconfirming code evidence.

**Design inference:** Implementation should prioritize repository access patterns that reveal actual technical bottlenecks rather than assumed ones, feeding back into atlas refinement. Current-role reconciliation mechanisms must distinguish between outdated mapped pressures and live system states.

---

**NEXT-TURN TEMPLATE ADJUSTMENT**

Specify: (1) which source repositories are accessible for code inspection; (2) role-reconciliation data sources (org charts, commit history, current staffing); (3) confidence thresholds for each decision category; (4) feedback loop for updating Helix tracks when Compiler evidence contradicts existing mappings.

## systems_architect

- Provider: `henry-ships-sparkforge.smart_summarize`
- Quality: **75.10/100**
- Marginal benefit: **0.8253**
- Execution time: **14.345s**
- Response SHA-256: `8ca3820d444fc418e83d95b63a6a7a3bf039cee6e53e64456bd57fd1b6b8bebf`

[TECHNICAL]

# COMPANY PROOF COMPILER — SYSTEMS ARCHITECTURE

## ARCHITECTURE

**Core Constraint:** Convert repository state + role requirement into bounded truth claims without code inspection or live job reconciliation.

**Three-Layer Stack:**

1. **Evidence Mapper** (Input)
   - Consumes: GlacierEQ repository manifests (commit hash, file paths, document references)
   - Consumes: Role requirement schema (skills, systems, proof types needed)
   - Output: Structured claim slots (what *could* be proven if code were inspected)

2. **Proof Compiler** (Processing)
   - Cross-references repository metadata against role claim slots
   - Assigns confidence bounds: DIRECT (manifest-stated), INFERRED (structural pattern), UNMAPPED (gap detected)
   - Produces: Code-evidence sheets (repo+file pointers, not code results)
   - Tracks: Which claims require live opening reconciliation vs. which are repository-static

3. **Decision Ranker** (Output)
   - APPLY_NOW: All critical claims DIRECT or INFERRED with low repair cost
   - REPAIR_THEN_APPLY: Gaps exist; specific code inspection or role clarification required
   - WATCH: Structural match; no current opening or incomplete manifests
   - NO_MATCH: Fundamental claim-slot mismatch

**Constraint Shift:** Replaces need for full code inspection with *mapped proof boundaries*—acknowledging what's unknown while making available what's verifiable from repository metadata.

---

## INTERFACES

**Input Interface: RoleRequirement**
```
{
  role_id: string
  company_id: string
  required_claims: [
    {claim_type: "system_design" | "language_proficiency" | "framework_integration",
     evidence_source: "code" | "manifest" | "architecture_doc",
     minimum_confidence: "DIRECT" | "INFERRED"}
  ]
}
```

**Input Interface: RepositoryManifest**
```
{
  repo_key: "GlacierEQ/project@commit_hash",
  file_inventory: [path, ...],
  doc_references: [manifest_name, ...],
  stated_systems: [system_name, ...],
  proof_boundaries: {unmapped_areas: [string, ...]}
}
```

**Output Interface: ProofSheet**
```
{
  role_id: string,
  claim_match: [
    {claim_type, repository_source, confidence, file_pointers: [repo_path, ...],
     gap_description: null | string}
  ],
  decision: "APPLY_NOW" | "REPAIR_THEN_APPLY" | "WATCH" | "NO_MATCH",
  repair_actions: [action_description, ...],
  truth_label: "manifest-bounded" | "inference-required" | "unmapped"
}
```

---

## FAILURE DOMAINS

1. **Manifest Staleness**
   - *Risk:* Repository file inventory or stated systems are outdated; manifests lag code.
   - *Boundary:* Evidence Mapper labels all outputs as `proof_timestamp: commit_hash`. Ranker downgrades confidence if manifest age exceeds threshold.

2. **Role Requirement Ambiguity**
   - *Risk:* Role claims are vague; proof compiler cannot map them to repository structure.
   - *Boundary:* Proof sheet explicitly lists unmapped claim slots and flags decision as REPAIR_THEN_APPLY.

3. **False Negatives (Skill Present but Unmanifested)**
   - *Risk:* Repository contains skill evidence not declared in manifests (e.g., live production system not documented).
   - *Boundary:* Truth rules forbid inference beyond stated manifests. Decision defaults to WATCH pending live opening reconciliation.

4. **Live Opening Mismatch**
   - *Risk:* Company intelligence shows no current opening; proof sheet scores APPLY_NOW anyway.
   - *Boundary:* Proof Compiler output is repository-static. Ranker consumes separate `company_intelligence.json` to override decision if opening ≠ found.

5. **Claim-Slot Type Mismatch**
   - *Risk:* Role requires "Kubernetes operations"; repository states "container orchestration (generic)."
   -

## innovation_inventor

- Provider: `henry-ships-sparkforge.smart_summarize`
- Quality: **90.20/100**
- Marginal benefit: **0.9706**
- Execution time: **15.419s**
- Response SHA-256: `9634c6a04e80d98f22db7db90d5b68406583cc6fe2f7f3013b8164d04778c87f`

[TECHNICAL]

# COMPANY PROOF COMPILER — INNOVATION SUMMARY

## ASSUMPTION TO BREAK

**Current assumption:** Job-fit validation requires manual reconciliation of repository code patterns against live role requirements, treated as a sequential gatekeeping step after bottleneck mapping.

**Breaking it:** Code evidence and role fit can be compiled *simultaneously as a generative artifact*, where repository signals are extracted into structured proof claims that self-report confidence boundaries and trigger automated decision gates without human interpretation.

---

## INVENTION

**Company Proof Compiler (CPC):** A deterministic system that:

1. **Ingests** repository manifests (GlacierEQ/job-app-helix + GlacierEQ/make-it-heavy source commits) and extracts:
   - Function signatures, module dependencies, test coverage footprints
   - Template patterns (e.g., `innovation_workers.yaml` structure)
   - Commit-message signals (problem-domain keywords)

2. **Maps** these extracts to a company's stated role requirements via:
   - Literal string match (skill tags in role vs. code labels)
   - Structural homology (e.g., does applicant's multi-repo orchestration pattern match the company's stated system-integration bottleneck?)
   - Confidence scoring: 0.0–1.0 per claim, with derivation logged

3. **Outputs** a **Proof Sheet** per company:
   - **Code Evidence** (commit hash, file path, line range, extracted pattern)
   - **Role Claim** (role requirement field matched)
   - **Confidence & Derivation** (method used: string, homology, or null if unmatchable)
   - **Truth Boundary** (e.g., "evidence shows pattern exists; does NOT prove deployment at scale")

4. **Generates Decision** via rules:
   - **APPLY_NOW:** ≥3 high-confidence (0.7+) matches + no contradictions
   - **REPAIR_THEN_APPLY:** 1–2 matches, or matches exist but confidence <0.6 (fixable gap identified in proof sheet)
   - **WATCH:** 0 matches but role-domain keyword appears in repo (signals emerging fit)
   - **NO_MATCH:** contradictory evidence or null intersection

---

## WHY IT IS DIFFERENT

| Aspect | Traditional | CPC |
|--------|-----------|-----|
| **Input** | Subjective code review + role doc | Deterministic repository signal extraction |
| **Output** | Go/No-Go binary | Decision + auditable proof artifact |
| **Scalability** | Manual per-company | Batch-processable across 48 tracks |
| **Reproducibility** | Interpretation-dependent | Hash-locked source, method-logged claims |
| **Repair Path** | Unclear | Proof sheet explicitly shows gap type; applicant can act |

**Materially different:** Transforms application validation from a *human judgment gate* into a *reproducible evidence compilation process*, making job-fit falsifiable and batch-automatable.

---

## FAST EXPERIMENT

**Scope:** One company (pick one from 48-track atlas) + one role requirement (e.g., "multi-repo orchestration").

**Steps:**
1. Extract 5 source files from GlacierEQ/job-app-helix@f3b2092 and GlacierEQ/make-it-heavy@3d49c62 manually
2. Define 3 role requirements from manifests/company_intelligence.json for that company
3. Hand-code CPC logic (pattern matching + homology rules) for those 3 requirements
4. Generate one Proof Sheet; manually validate: Does it match intuition? Are gaps visible?
5. Measure: Did the proof sheet catch something missed in 5-minute manual review?

**Success criterion:** Proof Sheet identifies ≥1 non-obvious structural match (e.g., template reuse pattern) that explains fit.

---

## KILL CRITERIA

- **Code extraction fails:** If repository structures are too heterogeneous to extract consistent signals, CPC cannot scale.
- **Confidence scores are noise:** If homology-based scoring correlates <0.5 with actual job suitability, the method is not predictive.
- **No repair path:** If proof sheets identify gaps but provide no actionable guidance (e.g., "confidence is 0.4

## adversarial_breaker

- Provider: `henry-ships-sparkforge.smart_summarize`
- Quality: **86.05/100**
- Marginal benefit: **0.9082**
- Execution time: **14.062s**
- Response SHA-256: `c8c552e973fe4db56f94a2d832b6fed9712cc292dcc0e77920be6545e8232a0d`

[TECHNICAL]

# ADVERSARIAL BREAKER PRE-MORTEM: COMPANY PROOF COMPILER

## FAILURE ATTACKS

**Verification Chain Collapse**
- The compiler depends on 48 source-backed tracks existing and being current. No validation mechanism is specified for whether GlacierEQ repositories remain accessible, maintained, or representative of actual company requirements. A single upstream deletion or repository migration breaks evidence chains without detection.

**Ground-Truth Misalignment**
- The atlas maps "company pressure" and "inferred bottlenecks," but no source specifies how these inferences were derived or validated against actual hiring signals. The compiler may formalize guesses into falsely authoritative proof artifacts.

**Role-Reconciliation Gap**
- "Current-role reconciliation" is identified as an unresolved second-depth gate. The compiler cannot operate without this, yet no methodology exists in the verified packet. Attempting to proceed risks generating APPLY_NOW decisions on incomplete data.

**Portfolio Thesis Assumption**
- The thesis that "Casey builds connected systems" is stated but not proven in the verified packet. If the actual codebase is fragmented or the repositories do not architecturally cohere as claimed, all downstream ranking decisions become noise.

**Evidence-to-Decision Coupling**
- No separation between "what the code shows" and "what the compiler recommends." A single malformed artifact or misread commit can cascade into wrong APPLY_NOW / REPAIR_THEN_APPLY classification without manual review checkpoints.

## FALSE-POSITIVE RISKS

**Over-Confidence in Proof Artifacts**
- Code-evidence sheets may appear rigorous but actually reflect cherry-picked commits or shallow pattern matching. A hiring manager trusting these sheets could reject strong matches or pursue weak ones.

**Repo-as-Signal Fallacy**
- Presence of a repository does not confirm maintained adoption, live headcount need, or actual company stack preference. A compiler ranking based on repository existence alone will generate false positives for dormant or prototype projects.

**Reconciliation Skew**
- Without verified current-role data, the compiler cannot distinguish between "company wants this skill" and "company once prototyped this." False positives will cluster around historical, not active, tech choices.

**Composite Metric Illusion**
- If the compiler synthesizes multiple weak signals (old commits, inferred pressure, portfolio structure) into a single APPLY_NOW score, the aggregation hides brittleness in individual inputs.

## SECURITY OR SAFETY RISKS

**Inference Leakage**
- The compiler publishes "inferred bottlenecks" and "company pressure" as decision support. If inferences are shared with or visible to candidates, they could enable social engineering, targeted rejection gaming, or inappropriate targeting of specific hiring teams.

**Artifact Immutability Risk**
- Code-evidence sheets are presented as reproducible proof. If they are not cryptographically signed or versioned, downstream users cannot detect tampering or drift. A candidate could alter sheets before submission.

**Scope Creep into Privileged Data**
- The verified packet does not specify whether the compiler accesses internal performance reviews, salary bands, or non-public team structures. If inferences are drawn from such data, the compiler risks exposing confidential hiring intelligence.

**Automated Decision Authority**
- If the compiler's APPLY_NOW / NO_MATCH rankings are treated as binding by hiring systems, a single bug or adversarial input could systematically block or fast-track entire cohorts of candidates.

## MINIMUM HARDENING

1. **Verification Pinning**: Lock all referenced commits and repository URLs. Implement automated validation that commits remain accessible and unchanged. Fail gracefully if verification fails; do not proceed with stale evidence.

2. **Role-Reconciliation Mandatory Gate**: Do not generate decisions until current-role data is ingested and reconciled. Define reconciliation explicitly: source (internal HR system, public job board API, etc.), currency threshold (refreshed within X days), and conflict resolution rules.

3. **Evidence Artifact Signing**: Require all code-evidence sheets to be signed with a keypair whose public key is published. Include commit hash, timestamp, and derivation method in every artifact. Validate signatures before use.

4. **Manual Review Checkpoints**: APPLY_NOW decisions affecting more than 5 candidates or falling into edge cases (e.g., high rank but low code coverage) must pass human review before communication.

5. **Inference Transparency**: Label all inferences (pressure, bottlenecks) with confidence scores and source commits. Never

## proof_engineer

- Provider: `henry-ships-sparkforge.smart_summarize`
- Quality: **96.80/100**
- Marginal benefit: **0.9904**
- Execution time: **11.213s**
- Response SHA-256: `2a9cb4b624bd44c886b171ca3447fa077f6dce4222d7d9eb70bb46337196d557`

[TECHNICAL]

# COMPANY PROOF COMPILER — PROOF ENGINEER SUMMARY

## CLAIMS TO TEST

1. **Job-App Helix contains 48 source-backed company application tracks** (claimed in verified packet §1)
2. **First-depth atlas maps company pressure, bottlenecks, GlacierEQ systems, leverage, application moves, and next evidence gates** (claimed in §2)
3. **Second-depth gate requires repository-by-repository code inspection + current-role reconciliation** (claimed in §3)
4. **Casey builds connected systems, not isolated repositories** (portfolio thesis, §4)
5. **Three named source anchors exist at specified commits with specified file paths** (claimed in §5)
6. **No code-inspection, live-opening reconciliation, or employer adoption has been verified** (explicit boundary, §6)

---

## CURRENT EVIDENCE

- **Packet structure**: Verified source packet provided; internal logical consistency present
- **Commit hashes supplied**:
  - `f3b2092fe0709a6532202a007852121d1ca982e4` (Job-App Helix)
  - `3d49c629fc47ffd965e4cdba43c37d7d9cfbba4a` (make-it-heavy)
- **File paths named**:
  - `docs/48_TRACK_BOTTLENECK_ATLAS.md`
  - `manifests/company_intelligence.json`
  - `templates/innovation_workers.yaml`
- **No external verification**: No live repository access, no code diffs, no manifest inspection performed
- **No baseline metrics**: 48-track count, pressure/bottleneck map content, role reconciliation status all unverified

---

## TEST HARNESS

**Tier 1: Source Artifact Verification** (executable locally)
```
TEST 1A: git clone + commit checkout
  INPUT: GlacierEQ/job-app-helix, commit f3b2092...
  EXPECTED: Repository exists; commit resolves
  RECEIPT: Commit SHA match + file listing

TEST 1B: File existence checks
  INPUT: Three named file paths
  EXPECTED: Each file present in named commit
  RECEIPT: File hash, line count, YAML/JSON parse success

TEST 1C: 48-track census
  INPUT: docs/48_TRACK_BOTTLENECK_ATLAS.md
  EXPECTED: Structured record of 48 distinct company tracks
  RECEIPT: Count, sample track names, schema structure
```

**Tier 2: Integration Claims** (requires execution)
```
TEST 2A: First-depth atlas completeness
  INPUT: company_intelligence.json manifest
  EXPECTED: Entries include pressure, bottlenecks, GlacierEQ reference, leverage vector, application move, next gate
  RECEIPT: Schema validation; sample record

TEST 2B: Repository connectivity
  INPUT: innovation_workers.yaml + job-app-helix docs
  EXPECTED: Cross-references; evidence of system-level design
  RECEIPT: Citation map; dependency graph
```

**Tier 3: Boundary Validation**
```
TEST 3A: No-claim audit
  INPUT: This summary + verified packet
  EXPECTED: Zero assertions re: live openings, code behavior, adoption
  RECEIPT: Search results for {customer, live, hiring, production}
```

---

## RECEIPTS

**What can be produced immediately:**
- Git-backed file manifests (if repos are accessible)
- YAML/JSON schema validation reports
- Cross-reference citation maps
- Line counts, hash digests

**What cannot be produced without escalation:**
- Proof that 48 tracks are *correct* or *complete*
- Proof that Casey's systems are *connected* (requires code review)
- Proof that role reconciliation *succeeds* (requires current job data)
- Proof that any employer uses this output (requires external data source)

**Proposed receipt format** (for each test):
```
STATUS: [PASS | FAIL | BLOCKED]
EVIDENCE: [artifact hash | error log | dependency note]
CONFIDENCE: [high | medium | low]
REASON: [one sentence]
```

---

## PASS FAIL CONTRACT

| Test | Pass Condition | Fail Condition | Block Condition |
|---

## leverage_analyst

- Provider: `henry-ships-sparkforge.smart_summarize`
- Quality: **92.08/100**
- Marginal benefit: **0.9763**
- Execution time: **11.336s**
- Response SHA-256: `583b7d60e555202d316c68e952a9198808d331238c10a38dafd0e67c59f4c949`

[TECHNICAL]

# LEVERAGE ANALYST SUMMARY: COMPANY PROOF COMPILER

## LEVERAGE MAP

**Effort Concentration:**
- Primary lever: Repository-to-evidence mapping (second-depth gate, currently unresolved)
- Reuse surface: 48 existing company tracks + GlacierEQ manifests reduce discovery overhead
- Reversibility: Code-evidence sheets are additive; no requirement to modify source repositories
- Compounding: Each repository code-inspected feeds next application cycle; proof artifacts accumulate across multiple job cycles

**Connected-Systems Assumption:**
The portfolio thesis (Casey builds connected systems, not isolated repositories) concentrates impact on *inter-repository dependency mapping* rather than isolated repository proof. This reduces redundant inspection effort if systems are proven once.

## EXPECTED BENEFIT

**Design Inference (unverified):**
- Removes subjective claim-matching; code evidence grounds application truth-bounds
- Ranked decision outputs (APPLY_NOW / REPAIR_THEN_APPLY / WATCH / NO_MATCH) reduce application-to-rejection cycle time by eliminating low-fit submissions
- Proof artifacts become portable across roles within the same company, reducing re-inspection cost
- Current-role reconciliation surfaces skill-to-requirement gaps *before* application, enabling targeted repair

**No claim of adoption, employer adoption, or measurable outcome improvement is made.**

## COST AND DEPENDENCIES

**Dependencies:**
- Completion of second-depth gate: manual code inspection + live role reconciliation (effort unestimated)
- Access to current company job descriptions and role requirements (external dependency, not in verified packet)
- Decision-rule definition for APPLY_NOW / REPAIR_THEN_APPLY thresholds (design work, not specified)

**Effort Risks:**
- 48-track scope may exceed single-pass inspection capacity
- Connected-systems assumption requires proof that inter-repository dependencies exist before concentrated effort is justified
- No metadata on code complexity, language diversity, or role-requirement coverage in verified packet

## PRIORITY

**Conditional High:**
Prioritize only if second-depth gate (code inspection) is scoped to a minimum viable subset (e.g., 6–8 highest-signal repositories) rather than all 48 tracks. Prioritize proof-artifact reproducibility over completeness; one complete evidence sheet is higher-leverage than 48 partial sheets.

## NEXT BET

**Immediate:** Generate a *gate-readiness checklist* listing exactly which repositories must be code-inspected, which current-role data is required, and which decision rules must be defined *before* compiler design begins. This prevents effort waste on design that cannot execute.

---

**NEXT-TURN TEMPLATE ADJUSTMENT:** Add a "SCOPE CONSTRAINT" heading that names the maximum number of repositories, roles, or proof artifacts this worker should assume, and define success as *reproducibility and truth-boundedness within scope* rather than completeness across all 48 tracks.

## presentation_strategist

- Provider: `henry-ships-sparkforge.smart_summarize`
- Quality: **91.50/100**
- Marginal benefit: **0.9745**
- Execution time: **10.174s**
- Response SHA-256: `0f57e8d6c247ee8ea7bdcfadae290e7010e72926f971f21a26832b4e321f8f62`

[TECHNICAL]

## PRIMARY AUDIENCE
Hiring managers and talent acquisition leads at companies mapped in the 48-track bottleneck atlas who need to validate whether a candidate's demonstrated systems-building capability matches their open role's integration demands.

## ONE-SENTENCE THESIS
The Company Proof Compiler surfaces code-evidence that Casey builds *connected systems, not isolated repositories*, allowing employers to make APPLY_NOW / REPAIR_THEN_APPLY / WATCH / NO_MATCH decisions bounded by what is actually inspected rather than what is claimed.

## INFORMATION ORDER
1. **Role requirement → system integration demand** (what the company actually needs to scale)
2. **Repository evidence → proof artifact** (unambiguous code traces showing systems thinking: cross-repo dependencies, abstraction choices, failure recovery, API design consistency)
3. **Gap statement** (what remains uninspected: live repo code, current role reconciliation, employer adoption signals)
4. **Decision recommendation** (ranked action with explicit uncertainty bounds)
5. **Next inspection gate** (what second-depth verification would resolve the unresolved gate)

## PROOF TO SHOW
- Commit hash + file path + specific code pattern that demonstrates integration logic (e.g., how GlacierEQ/job-app-helix manages the company_intelligence.json contract across multiple consumer repositories)
- Bottleneck atlas entry that maps the candidate's problem-solving approach to the hiring company's stated pressure point
- Template or manifest version that shows reproducibility and API stability across versions
- Honest signal of what was *not* inspected: live repository state, current role fit, actual employer adoption

## CONFUSION TO REMOVE
- **Do not claim:** "This candidate has solved this exact problem at scale."
- **Do claim:** "This code artifact shows systems-thinking in domain X; your role demands Y integration; here is the uninspected gap."
- **Do not hide:** Repository-by-repository code inspection remains incomplete; current role is unmapped; no employer adoption is verified.
- **Do highlight:** The portfolio thesis is testable—specific repos either show connected systems or they do not.

---

NEXT-TURN TEMPLATE ADJUSTMENT: Add a **DECISION OUTPUT TEMPLATE** section showing the exact structure of one APPLY_NOW, one REPAIR_THEN_APPLY, and one NO_MATCH decision card, so the next worker (Proof Artifact Engineer) inherits a concrete decision-surface schema rather than a design inference.
