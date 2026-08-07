# Adaptive Worker Innovation Loop

Make-It-Heavy now has an innovation-stage runtime that answers five questions after every completed turn:

1. **How many workers ran?**
2. **What exact job did each worker own?**
3. **What output-contract quality did each worker achieve?**
4. **What marginal benefit did that worker add beyond its peers?**
5. **What changes on the next turn?**

## Initial topology: eight workers

| Worker | Job | Primary benefit |
|---|---|---|
| `source_mapper` | Locate sources and bound what they support | Prevents the rest of the swarm from building on unsourced premises |
| `bottleneck_cartographer` | Isolate the binding constraint and brick wall | Moves the mission from symptoms to system leverage |
| `systems_architect` | Design the smallest reusable intervention | Converts analysis into interfaces, failure domains, and acceptance tests |
| `innovation_inventor` | Break assumptions and propose testable mechanisms | Adds non-obvious options rather than polishing the current approach |
| `adversarial_breaker` | Attack evidence, architecture, incentives, and safety | Finds false positives and hardening needs before synthesis |
| `proof_engineer` | Convert claims into tests and receipts | Makes success falsifiable and reviewable |
| `leverage_analyst` | Compare effort, impact, reuse, and reversibility | Selects the next bet by marginal value |
| `presentation_strategist` | Build the clearest decision surface | Preserves proof and uncertainty while reducing reader confusion |

Run the persistent innovation session:

```bash
python make_it_heavy_innovation.py
```

Run one mission:

```bash
python make_it_heavy_innovation.py "Design the next Job-App Helix innovation"
```

## Per-turn scoring

Each worker receives a scorecard with seven normalized dimensions:

- required-section completion;
- evidence discipline;
- specificity;
- novelty relative to peer outputs;
- actionability;
- truth and uncertainty discipline;
- output efficiency.

The dimension weights are role-specific and stored in `templates/innovation_workers.yaml`.

The **quality score** is a weighted 0–100 output-contract score. It measures whether the worker completed its assigned contract with evidence discipline, specificity, novelty, actionability, and efficient presentation.

It is **not an independent factual-correctness verdict**.

The **benefit score** measures marginal contribution:

- 35% unique contribution relative to peers;
- 25% role-contract coverage;
- 30% quality;
- 10% execution speed.

This makes a polished but redundant worker visibly less valuable than a distinct worker that closes an important gap.

## Fine-tuning after every turn

The runtime chooses one bounded action for every active worker template:

| Condition | Next-turn action |
|---|---|
| Timeout or execution failure | `REPLACE_OR_NARROW` |
| Both quality and benefit regress materially | `ROLLBACK_PREVIOUS` |
| Weak source discipline | `TIGHTEN_EVIDENCE` |
| Missing required sections | `NARROW_AND_COMPLETE` |
| Exceptional quality and benefit | `EXPAND_OR_DUPLICATE` |
| Strong and useful | `KEEP` |
| Strong but redundant | `MERGE_OR_REPURPOSE` |
| Weak and low-value | `RETIRE_OR_REPLACE` |
| Mixed result | `REPAIR` |

The instruction is persisted in SQLite and injected into that worker's next task. Only one bounded instruction is introduced per role per turn, limiting oscillation.

## Topology adjustment

The controller also decides the next worker count:

- hold the count when a worker failed so the role can be repaired or replaced;
- remove one worker when multiple outputs are high-quality but redundant;
- add one challenger when average quality is below target but several workers show strong marginal benefit;
- compress the topology when both quality and benefit materially exceed target;
- otherwise keep the count and tune the templates first.

Proof coverage is preserved when reducing the topology: source mapping, adversarial review, and proof engineering remain mandatory while the remaining slots are selected by combined quality and benefit.

The current runtime supports **4–8 active workers**. The eight template identities remain available even when a smaller next-turn topology is selected.

## Persistent evidence

The adaptive memory layer stores:

- raw agent runs;
- per-worker scorecards;
- template adjustments;
- topology adjustments;
- historical quality and benefit;
- the full Markdown/JSON turn report.

The same persistent session therefore applies its previous adjustments on the next mission instead of starting from static prompts every time.

## Example turn footer

Every adaptive turn ends with:

```text
WORKER INNOVATION REPORT
This turn: 8 workers -> next: 7 workers
Average quality: 81.40/100
Average marginal benefit: 0.6280

worker | job | quality | benefit | benefit delivered | adjust next
...
```

The report preserves a critical boundary: measured output quality and marginal contribution guide template and topology improvement, but factual correctness still requires source review, executable proof, or human validation.
