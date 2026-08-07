# SPDX-License-Identifier: Proprietary
"""Conservative source-span semantic support for adaptive worker claims.

This module is intentionally not a general truth or natural-language inference engine.
It evaluates only the relation between one claim and one already-resolved immutable source
span. Ambiguous relations abstain as SOURCE_INSUFFICIENT.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

SOURCE_ENTAILS_CLAIM = "SOURCE_ENTAILS_CLAIM"
SOURCE_CONTRADICTS_CLAIM = "SOURCE_CONTRADICTS_CLAIM"
SOURCE_INSUFFICIENT = "SOURCE_INSUFFICIENT"
SEMANTIC_RELATIONS = {
    SOURCE_ENTAILS_CLAIM,
    SOURCE_CONTRADICTS_CLAIM,
    SOURCE_INSUFFICIENT,
}

OBSERVED_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?OBSERVED\[(?P<pointer>[^\]]+)\]\s*:\s*(?P<claim>.+?)\s*$",
    re.IGNORECASE,
)
TOKEN_RE = re.compile(r"[A-Za-z0-9_./:{}^=<>+-]+")
NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?%?(?![A-Za-z])")
HEX_RE = re.compile(r"\b[0-9a-fA-F]{8,64}\b")
NEGATION_RE = re.compile(r"\b(?:not|never|no|cannot|can't|doesn't|isn't|without)\b", re.I)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}

SEMANTIC_EXPANSION_TERMS = {
    "always",
    "all",
    "guarantee",
    "guaranteed",
    "guarantees",
    "prove",
    "proved",
    "proves",
    "semantic",
    "behavioral",
    "production",
    "scalable",
    "optimal",
    "complete",
    "correct",
}

EXCLUSIVE_STATE_PAIRS = (
    ("resolved", "unresolved"),
    ("verified", "failed"),
    ("pass", "fail"),
    ("allowed", "blocked"),
    ("true", "false"),
    ("enabled", "disabled"),
)


@dataclass(frozen=True)
class SemanticSupportResult:
    """One content-addressed claim-to-source-span relation receipt."""

    source_pointer: str
    relation: str
    reason: str
    claim_sha256: str
    span_sha256: str
    token_coverage: float
    unsupported_numbers: Tuple[str, ...]
    unsupported_identifiers: Tuple[str, ...]
    semantic_boundary: str = (
        "This is a conservative span-local relation check, not an external-world truth "
        "verdict. SOURCE_INSUFFICIENT is the default when support is ambiguous."
    )

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_text(text: str) -> str:
    return " ".join(TOKEN_RE.findall(text.lower()))


def _content_tokens(text: str) -> Set[str]:
    return {
        token.lower()
        for token in TOKEN_RE.findall(text)
        if len(token) > 1 and token.lower() not in STOPWORDS
    }


def _numbers(text: str) -> Set[str]:
    return set(NUMBER_RE.findall(text))


def _identifiers(text: str) -> Set[str]:
    values = set(HEX_RE.findall(text))
    values.update(
        token
        for token in TOKEN_RE.findall(text)
        if any(marker in token for marker in ("HEAD^{commit}", "--verify", "exit_code"))
    )
    return values


def _opposite_state_contradiction(claim: str, span: str) -> bool:
    claim_tokens = _content_tokens(claim)
    span_tokens = _content_tokens(span)
    shared = claim_tokens & span_tokens
    denominator = max(1, len(claim_tokens))
    if len(shared) / denominator < 0.55:
        return False

    for left, right in EXCLUSIVE_STATE_PAIRS:
        claim_has_left = left in claim_tokens
        claim_has_right = right in claim_tokens
        span_has_left = left in span_tokens
        span_has_right = right in span_tokens
        if claim_has_left and not claim_has_right and span_has_right and not span_has_left:
            return True
        if claim_has_right and not claim_has_left and span_has_left and not span_has_right:
            return True
    return False


def _negation_contradiction(claim: str, span: str) -> bool:
    claim_tokens = _content_tokens(claim)
    span_tokens = _content_tokens(span)
    if not claim_tokens:
        return False
    overlap = len(claim_tokens & span_tokens) / len(claim_tokens)
    if overlap < 0.8:
        return False
    return bool(NEGATION_RE.search(claim)) != bool(NEGATION_RE.search(span))


def _semantic_expansion_terms(claim: str, span: str) -> Set[str]:
    claim_tokens = _content_tokens(claim)
    span_tokens = _content_tokens(span)
    return {
        term
        for term in SEMANTIC_EXPANSION_TERMS
        if term in claim_tokens and term not in span_tokens
    }


def evaluate_source_span_support(
    claim: str,
    span_text: str,
    source_pointer: str,
) -> SemanticSupportResult:
    """Classify one claim against one immutable source span conservatively.

    Entailment requires either canonical containment or near-complete lexical support with
    no new numeric/identifier precision and no unsupported semantic-expansion language.
    Contradiction requires an explicit local negation/state conflict. Everything else
    abstains as SOURCE_INSUFFICIENT.
    """

    claim = claim.strip()
    span_text = span_text.strip()
    if not claim or not span_text or not source_pointer.strip():
        return SemanticSupportResult(
            source_pointer=source_pointer.strip(),
            relation=SOURCE_INSUFFICIENT,
            reason="claim, source pointer, and source span text must all be non-empty",
            claim_sha256=sha256_text(claim),
            span_sha256=sha256_text(span_text),
            token_coverage=0.0,
            unsupported_numbers=(),
            unsupported_identifiers=(),
        )

    claim_tokens = _content_tokens(claim)
    span_tokens = _content_tokens(span_text)
    if not claim_tokens:
        coverage = 0.0
    else:
        coverage = len(claim_tokens & span_tokens) / len(claim_tokens)

    unsupported_numbers = tuple(sorted(_numbers(claim) - _numbers(span_text)))
    unsupported_identifiers = tuple(sorted(_identifiers(claim) - _identifiers(span_text)))
    expansion_terms = _semantic_expansion_terms(claim, span_text)

    common = dict(
        source_pointer=source_pointer.strip(),
        claim_sha256=sha256_text(claim),
        span_sha256=sha256_text(span_text),
        token_coverage=round(coverage, 4),
        unsupported_numbers=unsupported_numbers,
        unsupported_identifiers=unsupported_identifiers,
    )

    if unsupported_numbers or unsupported_identifiers:
        return SemanticSupportResult(
            relation=SOURCE_INSUFFICIENT,
            reason=(
                "claim introduces numeric or identifier precision absent from the source span"
            ),
            **common,
        )

    if _opposite_state_contradiction(claim, span_text) or _negation_contradiction(
        claim, span_text
    ):
        return SemanticSupportResult(
            relation=SOURCE_CONTRADICTS_CLAIM,
            reason="source span contains an explicit local state or negation conflict",
            **common,
        )

    canonical_claim = _canonical_text(claim)
    canonical_span = _canonical_text(span_text)
    exact_containment = bool(canonical_claim and canonical_claim in canonical_span)
    strong_lexical_support = (
        len(claim_tokens) >= 3
        and coverage >= 0.92
        and not expansion_terms
        and not NEGATION_RE.search(claim)
    )
    if exact_containment or strong_lexical_support:
        return SemanticSupportResult(
            relation=SOURCE_ENTAILS_CLAIM,
            reason=(
                "claim is contained in, or conservatively covered by, the source span "
                "without new precision or semantic-expansion terms"
            ),
            **common,
        )

    reasons: List[str] = []
    if coverage < 0.92:
        reasons.append("source span does not cover enough of the claim's content tokens")
    if expansion_terms:
        reasons.append(
            "claim adds semantic-expansion terms absent from the source span: "
            + ", ".join(sorted(expansion_terms))
        )
    if not reasons:
        reasons.append("support is ambiguous under the conservative span-local rules")
    return SemanticSupportResult(
        relation=SOURCE_INSUFFICIENT,
        reason="; ".join(reasons),
        **common,
    )


def evaluate_observed_claims(
    response: str,
    span_text_by_pointer: Mapping[str, str],
) -> Dict[str, object]:
    """Evaluate every OBSERVED[pointer] claim in a worker response.

    Semantic promotion passes only when every observed claim is SOURCE_ENTAILS_CLAIM.
    Contradictions and insufficient support remain separately visible.
    """

    results: List[Dict[str, object]] = []
    missing_pointers: List[str] = []
    for raw_line in response.splitlines():
        match = OBSERVED_LINE_RE.match(raw_line.strip())
        if not match:
            continue
        pointer = match.group("pointer").strip()
        claim = match.group("claim").strip()
        span_text = span_text_by_pointer.get(pointer)
        if span_text is None:
            missing_pointers.append(pointer)
            result = SemanticSupportResult(
                source_pointer=pointer,
                relation=SOURCE_INSUFFICIENT,
                reason="resolved source-span text was not supplied to the semantic stage",
                claim_sha256=sha256_text(claim),
                span_sha256=sha256_text(""),
                token_coverage=0.0,
                unsupported_numbers=(),
                unsupported_identifiers=(),
            )
        else:
            result = evaluate_source_span_support(claim, span_text, pointer)
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
        "truth_boundary": (
            "This stage evaluates only claim-to-cited-span support. It does not establish "
            "external-world truth, repository-wide correctness, or employer relevance."
        ),
    }
