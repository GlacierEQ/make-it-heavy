# SPDX-License-Identifier: Proprietary
"""Fail-closed semantic firewall for worker OBSERVED claims.

A source pointer proves identity.  This module decides whether the worker's exact
atomic OBSERVED claim is semantically supported by the exact registered source
span.  It never rewrites a failed claim into a verified one.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Mapping

from semantic_support import (
    SOURCE_CONTRADICTS_CLAIM,
    SOURCE_ENTAILS_CLAIM,
    SOURCE_INSUFFICIENT,
    SemanticSupportResult,
    sha256_text,
)
from semantic_support_v2 import evaluate_source_span_support_v2

OBSERVED_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?OBSERVED\[(?P<pointer>[^\]]+)\]\s*:\s*(?P<claim>.+?)\s*$",
    re.IGNORECASE,
)

Evaluator = Callable[[str, str, str], SemanticSupportResult]


def _relation_counts() -> Dict[str, int]:
    return {
        SOURCE_ENTAILS_CLAIM: 0,
        SOURCE_CONTRADICTS_CLAIM: 0,
        SOURCE_INSUFFICIENT: 0,
    }


def evaluate_semantic_claim_firewall(
    response: str,
    source_spans: Mapping[str, str],
    *,
    evaluator: Evaluator = evaluate_source_span_support_v2,
    require_observed: bool = True,
) -> Dict[str, Any]:
    """Evaluate every OBSERVED claim against its exact registered source span.

    The firewall is pass/fail, but it also returns the complete per-claim relation
    receipt so the adaptation layer can distinguish over-broad claims from true
    contradictions and missing source spans.
    """

    claims: List[Dict[str, Any]] = []
    counts = _relation_counts()
    missing_pointers: List[str] = []

    for raw_line in response.splitlines():
        match = OBSERVED_LINE_RE.match(raw_line.strip())
        if match is None:
            continue
        pointer = match.group("pointer").strip()
        claim = match.group("claim").strip()
        span = source_spans.get(pointer)
        if span is None:
            relation = SOURCE_INSUFFICIENT
            reason = "Semantic firewall has no exact source span for this pointer."
            token_coverage = 0.0
            unsupported_numbers: List[str] = []
            unsupported_identifiers: List[str] = []
            missing_pointers.append(pointer)
        else:
            result = evaluator(claim, span, pointer)
            relation = result.relation
            reason = result.reason
            token_coverage = result.token_coverage
            unsupported_numbers = list(result.unsupported_numbers)
            unsupported_identifiers = list(result.unsupported_identifiers)

        counts[relation] = counts.get(relation, 0) + 1
        claims.append(
            {
                "pointer": pointer,
                "claim": claim,
                "claim_sha256": sha256_text(claim),
                "span_sha256": sha256_text(span) if span is not None else None,
                "relation": relation,
                "reason": reason,
                "token_coverage": token_coverage,
                "unsupported_numbers": unsupported_numbers,
                "unsupported_identifiers": unsupported_identifiers,
            }
        )

    observed_count = len(claims)
    entails = counts[SOURCE_ENTAILS_CLAIM]
    contradicts = counts[SOURCE_CONTRADICTS_CLAIM]
    insufficient = counts[SOURCE_INSUFFICIENT]
    applicable = observed_count > 0
    semantic_score = entails / observed_count if observed_count else 0.0
    passed = (
        applicable
        and not missing_pointers
        and contradicts == 0
        and insufficient == 0
        and entails == observed_count
    )
    if not require_observed and not applicable:
        passed = True
        semantic_score = 1.0

    if missing_pointers:
        adjustment = "FIX_SEMANTIC_POINTER"
    elif contradicts:
        adjustment = "ESCALATE_CONTRADICTION"
    elif insufficient:
        adjustment = "NARROW_OBSERVED_TO_SPAN"
    elif not applicable and require_observed:
        adjustment = "ADD_ATOMIC_OBSERVED_CLAIM"
    else:
        adjustment = "KEEP_SEMANTIC_DISCIPLINE"

    return {
        "schema": "glaciereq.make-it-heavy.semantic-claim-firewall.v1",
        "applicable": applicable,
        "pass": passed,
        "score": round(semantic_score, 4),
        "observed_claim_count": observed_count,
        "relation_counts": counts,
        "missing_pointer_count": len(missing_pointers),
        "missing_pointers": sorted(set(missing_pointers)),
        "adjustment": adjustment,
        "claims": claims,
        "truth_boundary": (
            "SOURCE_ENTAILS_CLAIM means the exact registered span supports the exact "
            "worker claim under the bounded V2 evaluator. It does not establish external-"
            "world truth, repository-wide correctness, deployment, adoption, or employer fit."
        ),
    }
