#!/usr/bin/env python3
"""Replay the exact Turn-5 live worker claims through semantic-support V2.

The source input is the persisted Turn-5 semantic-review response.  This replay
measures relation changes only.  It does not treat new entailments as verified
truth; every changed relation remains source-review pending.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from semantic_support import SOURCE_INSUFFICIENT, sha256_text
from semantic_support_v2 import evaluate_source_span_support_v2

ROOT = Path(__file__).resolve().parents[1]

COMPACT_SPANS = {
    "M1#E1": (
        "This module is intentionally not a general truth or natural-language inference "
        "engine. It evaluates only the relation between one claim and one already-resolved "
        "immutable source span. Ambiguous relations abstain as SOURCE_INSUFFICIENT. "
        "SOURCE_ENTAILS_CLAIM SOURCE_CONTRADICTS_CLAIM SOURCE_INSUFFICIENT. "
        "SemanticSupportResult fields: source_pointer, relation, reason, claim_sha256, "
        "span_sha256, token_coverage, unsupported_numbers, unsupported_identifiers, "
        "semantic_boundary."
    ),
    "M1#E2": (
        "Helpers extract canonical text, content tokens, numbers, identifiers, opposite "
        "state-pair contradictions, negation contradictions, and semantic expansion terms. "
        "Exclusive state pairs include resolved/unresolved, verified/failed, pass/fail, "
        "allowed/blocked, true/false, enabled/disabled."
    ),
    "M1#E3": (
        "evaluate_source_span_support classifies one claim against one immutable source span "
        "conservatively. Unsupported numeric or identifier precision returns "
        "SOURCE_INSUFFICIENT. Explicit local state or negation conflict returns "
        "SOURCE_CONTRADICTS_CLAIM. Canonical containment or strong lexical support without "
        "expansion can return SOURCE_ENTAILS_CLAIM. Everything else returns "
        "SOURCE_INSUFFICIENT."
    ),
    "M1#E4": (
        "evaluate_observed_claims evaluates every OBSERVED[pointer] claim independently. "
        "Missing source span text yields SOURCE_INSUFFICIENT. Semantic promotion passes only "
        "when every observed claim is SOURCE_ENTAILS_CLAIM. The stage does not establish "
        "external-world truth, repository-wide correctness, or employer relevance."
    ),
    "M2#E1": (
        "The benchmark is bound to GlacierEQ/job-app-helix commit "
        "b613a70766586511199266d63499bd31d2808b97. It contains 10 operator-reviewed "
        "claim-to-span cases. Positive controls cover direct implementation, workflow, and "
        "regression facts. Negative controls include fabricated 47 artifacts, timestamp "
        "1704067200, zero public API breaking changes, 18-24% degradation, unsupported "
        "truth-oracle complexity, unsupported production completion, and misdescription of "
        "a pytest collection regression span. Labels are bounded benchmark relations, not "
        "external-world truth."
    ),
    "M3#E1": (
        "Regression tests cover exact implementation phrase entailment, new numeric precision "
        "forcing SOURCE_INSUFFICIENT, semantic expansion forcing SOURCE_INSUFFICIENT, explicit "
        "negation conflict yielding SOURCE_CONTRADICTS_CLAIM, batch semantic promotion "
        "requiring every observed claim to entail, missing span text abstaining, and the "
        "10-case benchmark matching every operator-reviewed label."
    ),
}


def replay(payload: Dict[str, Any]) -> Dict[str, Any]:
    changes: List[Dict[str, Any]] = []
    lanes: List[Dict[str, Any]] = []
    before = Counter()
    after = Counter()
    total = 0

    for lane in payload.get("lanes", []):
        lane_before = Counter()
        lane_after = Counter()
        lane_changes = []
        for row in lane.get("results", []):
            pointer = str(row.get("pointer") or "")
            claim = str(row.get("claim") or "")
            previous = str(row.get("relation") or SOURCE_INSUFFICIENT)
            span = COMPACT_SPANS.get(pointer)
            if span is None:
                current = SOURCE_INSUFFICIENT
                reason = "Replay has no registered compact source span for this pointer."
                coverage = 0.0
            else:
                result = evaluate_source_span_support_v2(claim, span, pointer)
                current = result.relation
                reason = result.reason
                coverage = result.token_coverage

            before[previous] += 1
            after[current] += 1
            lane_before[previous] += 1
            lane_after[current] += 1
            total += 1

            if previous != current:
                change = {
                    "role": lane.get("role"),
                    "pointer": pointer,
                    "claim": claim,
                    "claim_sha256": sha256_text(claim),
                    "before": previous,
                    "after": current,
                    "v2_reason": reason,
                    "v2_token_coverage": coverage,
                    "review_state": "SOURCE_REVIEW_REQUIRED",
                }
                changes.append(change)
                lane_changes.append(change)

        lanes.append(
            {
                "role": lane.get("role"),
                "claim_count": sum(lane_before.values()),
                "v1_relation_counts": dict(sorted(lane_before.items())),
                "v2_relation_counts": dict(sorted(lane_after.items())),
                "changed_relation_count": len(lane_changes),
                "changed_claim_sha256": [item["claim_sha256"] for item in lane_changes],
            }
        )

    input_sha256 = sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    changed_to_entails = sum(1 for row in changes if row["after"] == "SOURCE_ENTAILS_CLAIM")
    changed_to_contradicts = sum(
        1 for row in changes if row["after"] == "SOURCE_CONTRADICTS_CLAIM"
    )

    return {
        "schema": "glaciereq.make-it-heavy.turn6-live-v2-replay.v1",
        "status": "PASS",
        "input_run_id": payload.get("run_id"),
        "input_evaluator": payload.get("evaluator"),
        "input_sha256": input_sha256,
        "claim_count": total,
        "v1_relation_counts": dict(sorted(before.items())),
        "v2_relation_counts": dict(sorted(after.items())),
        "changed_relation_count": len(changes),
        "changed_to_entails": changed_to_entails,
        "changed_to_contradicts": changed_to_contradicts,
        "unchanged_count": total - len(changes),
        "lanes": lanes,
        "changed_relations": changes,
        "review_contract": {
            "new_entailment_is_not_truth": True,
            "new_contradiction_is_not_truth": True,
            "every_changed_relation_requires_source_review": True,
            "promotion_from_replay_counts_alone": False,
        },
        "truth_boundary": (
            "This is a deterministic replay of previously generated live worker claims against "
            "the same compact Turn-5 source spans. A V2 relation change measures evaluator "
            "behavior, not factual correctness, external-world truth, or successful worker "
            "performance. Changed relations remain source-review pending."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    receipt = replay(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "claim_count": receipt["claim_count"],
                "v1_relation_counts": receipt["v1_relation_counts"],
                "v2_relation_counts": receipt["v2_relation_counts"],
                "changed_relation_count": receipt["changed_relation_count"],
                "changed_to_entails": receipt["changed_to_entails"],
                "changed_to_contradicts": receipt["changed_to_contradicts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
