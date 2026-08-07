# SPDX-License-Identifier: Proprietary
"""Batch adapter for bounded semantic-support V2 worker claims."""

from __future__ import annotations

from typing import Dict, List, Mapping

from semantic_support import (
    OBSERVED_LINE_RE,
    SEMANTIC_RELATIONS,
    SOURCE_ENTAILS_CLAIM,
    SOURCE_INSUFFICIENT,
    SemanticSupportResult,
    sha256_text,
)
from semantic_support_v2 import evaluate_source_span_support_v2


def evaluate_observed_claims_v2(
    response: str,
    span_text_by_pointer: Mapping[str, str],
) -> Dict[str, object]:
    """Evaluate every worker OBSERVED claim with the V1-first V2 challenger.

    Promotion passes only when every observed claim is supported by its exact supplied
    span. Missing span text fails closed as SOURCE_INSUFFICIENT. This preserves the
    existing runtime gate shape while upgrading only its claim-to-span evaluator.
    """

    results: List[Dict[str, object]] = []
    missing_pointers: List[str] = []
    for raw_line in response.splitlines():
        match = OBSERVED_LINE_RE.match(raw_line.strip())
        if match is None:
            continue
        pointer = match.group("pointer").strip()
        claim = match.group("claim").strip()
        span_text = span_text_by_pointer.get(pointer)
        if span_text is None:
            missing_pointers.append(pointer)
            result = SemanticSupportResult(
                source_pointer=pointer,
                relation=SOURCE_INSUFFICIENT,
                reason="resolved source-span text was not supplied to the V2 semantic stage",
                claim_sha256=sha256_text(claim),
                span_sha256=sha256_text(""),
                token_coverage=0.0,
                unsupported_numbers=(),
                unsupported_identifiers=(),
            )
        else:
            result = evaluate_source_span_support_v2(claim, span_text, pointer)
        results.append(result.to_dict())

    counts = {relation: 0 for relation in sorted(SEMANTIC_RELATIONS)}
    for result in results:
        counts[str(result["relation"])] += 1
    return {
        "semantic_gate_pass": bool(results)
        and counts[SOURCE_ENTAILS_CLAIM] == len(results),
        "observed_claim_count": len(results),
        "missing_pointer_count": len(missing_pointers),
        "missing_pointers": sorted(set(missing_pointers)),
        "relation_counts": counts,
        "results": results,
        "evaluator": "semantic_support_v2",
        "truth_boundary": (
            "This stage evaluates only claim-to-cited-span support using the bounded V1-first "
            "V2 challenger. It does not establish external-world truth, repository-wide "
            "correctness, deployment, adoption, or employer relevance."
        ),
    }
