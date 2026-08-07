# SPDX-License-Identifier: Proprietary
"""Turn-6 bounded recall challenger for source-span semantic support.

V2 never overrides a V1 entailment or contradiction.  It only revisits V1
SOURCE_INSUFFICIENT results after removing citation-only metadata and applying a
small, auditable normalization layer for code identifiers and ordinary inflection.
The goal is recall on source-reviewed paraphrases without turning the checker into
a general semantic oracle.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, Set, Tuple

from semantic_support import (
    NEGATION_RE,
    SOURCE_CONTRADICTS_CLAIM,
    SOURCE_ENTAILS_CLAIM,
    SOURCE_INSUFFICIENT,
    SemanticSupportResult,
    _identifiers,
    _numbers,
    _opposite_state_contradiction,
    _semantic_expansion_terms,
    evaluate_source_span_support,
    sha256_text,
)

WORD_RE = re.compile(r"[A-Za-z0-9_./:{}^=<>+-]+")
SPLIT_RE = re.compile(r"[_./:{}^=<>+-]+")
CITATION_METADATA_RE = re.compile(
    r"(?ix)"
    r"(?:\(|\[)?\s*"
    r"(?:lines?\s+\d+(?:\s*[-–]\s*\d+)?|L\d+(?:\s*[-–]\s*L?\d+)?)"
    r"\s*(?:\)|\])?"
)

# These words describe the already-bound source context rather than adding a
# material predicate.  Removing them from coverage prevents harmless prose from
# defeating a claim that otherwise tracks the immutable source span.
CONTEXT_WORDS = {
    "code",
    "implementation",
    "payload",
    "receipt",
    "regression",
    "resolver",
    "test",
    "verifier",
    "workflow",
}

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

PHRASE_NORMALIZATIONS = (
    (re.compile(r"\bchecks?\s+out\b", re.I), "checkout"),
    (re.compile(r"\bchecked\s+out\b", re.I), "checkout"),
    (re.compile(r"\bchecking\s+out\b", re.I), "checkout"),
    (re.compile(r"\breturns?\s+none\b", re.I), "return none"),
)


def strip_citation_metadata(text: str) -> str:
    """Remove only line-number citation decorations from a claim."""

    return " ".join(CITATION_METADATA_RE.sub(" ", text).split())


def _stem(token: str) -> str:
    """Apply deliberately small English inflection normalization."""

    token = token.lower()
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        root = token[:-3]
        if len(root) >= 3:
            return root
    if len(token) > 4 and token.endswith("ed"):
        root = token[:-2]
        if len(root) >= 3:
            return root
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _normalize_phrases(text: str) -> str:
    value = text
    for pattern, replacement in PHRASE_NORMALIZATIONS:
        value = pattern.sub(replacement, value)
    return value


def _expanded_tokens(text: str) -> Set[str]:
    """Tokenize prose plus snake/path/code identifiers into comparable atoms."""

    value = _normalize_phrases(text)
    tokens: Set[str] = set()
    for raw in WORD_RE.findall(value):
        candidates = [raw]
        candidates.extend(part for part in SPLIT_RE.split(raw) if part)
        for candidate in candidates:
            lowered = candidate.lower()
            if len(lowered) <= 1 or lowered in STOPWORDS or lowered in CONTEXT_WORDS:
                continue
            tokens.add(_stem(lowered))
    return tokens


def _unsupported_code_tokens(claim: str, span: str) -> Tuple[str, ...]:
    """Reject new code-shaped precision that normalization must not explain away."""

    span_raw = set(WORD_RE.findall(span.lower()))
    unsupported = []
    for token in WORD_RE.findall(claim):
        lowered = token.lower()
        code_shaped = (
            "_" in token
            or token.startswith("--")
            or "^{" in token
            or token.endswith(".py")
        )
        if code_shaped and lowered not in span_raw:
            unsupported.append(token)
    return tuple(sorted(set(unsupported)))


def _recall_result(
    claim: str,
    span_text: str,
    source_pointer: str,
) -> SemanticSupportResult:
    stripped_claim = strip_citation_metadata(claim)
    stripped_span = strip_citation_metadata(span_text)

    # First retry the proven V1 gate after removing citation-only line numbers.
    stripped_v1 = evaluate_source_span_support(
        stripped_claim,
        stripped_span,
        source_pointer,
    )
    if stripped_v1.relation in {SOURCE_ENTAILS_CLAIM, SOURCE_CONTRADICTS_CLAIM}:
        return SemanticSupportResult(
            source_pointer=source_pointer.strip(),
            relation=stripped_v1.relation,
            reason="V2 citation-normalized replay: " + stripped_v1.reason,
            claim_sha256=sha256_text(claim.strip()),
            span_sha256=sha256_text(span_text.strip()),
            token_coverage=stripped_v1.token_coverage,
            unsupported_numbers=stripped_v1.unsupported_numbers,
            unsupported_identifiers=stripped_v1.unsupported_identifiers,
        )

    claim_tokens = _expanded_tokens(stripped_claim)
    span_tokens = _expanded_tokens(stripped_span)
    coverage = (
        len(claim_tokens & span_tokens) / len(claim_tokens)
        if claim_tokens
        else 0.0
    )

    unsupported_numbers = tuple(
        sorted(_numbers(stripped_claim) - _numbers(stripped_span))
    )
    unsupported_identifiers = tuple(
        sorted(_identifiers(stripped_claim) - _identifiers(stripped_span))
    )
    unsupported_code = _unsupported_code_tokens(stripped_claim, stripped_span)
    expansion_terms = _semantic_expansion_terms(stripped_claim, stripped_span)

    common = dict(
        source_pointer=source_pointer.strip(),
        claim_sha256=sha256_text(claim.strip()),
        span_sha256=sha256_text(span_text.strip()),
        token_coverage=round(coverage, 4),
        unsupported_numbers=unsupported_numbers,
        unsupported_identifiers=unsupported_identifiers,
    )

    if unsupported_numbers or unsupported_identifiers or unsupported_code:
        return SemanticSupportResult(
            relation=SOURCE_INSUFFICIENT,
            reason=(
                "V2 abstains because the claim introduces source-absent numeric, "
                "identifier, or code-shaped precision"
            ),
            **common,
        )

    if _opposite_state_contradiction(stripped_claim, stripped_span):
        return SemanticSupportResult(
            relation=SOURCE_CONTRADICTS_CLAIM,
            reason="V2 detected an explicit exclusive-state conflict",
            **common,
        )

    claim_negated = bool(NEGATION_RE.search(stripped_claim))
    span_negated = bool(NEGATION_RE.search(stripped_span))
    if claim_negated != span_negated and coverage >= 0.72:
        return SemanticSupportResult(
            relation=SOURCE_CONTRADICTS_CLAIM,
            reason="V2 detected a local negation conflict after normalized-token alignment",
            **common,
        )

    # The recall challenger is intentionally bounded.  It needs substantial
    # normalized overlap, at least three supported atoms, and no language that
    # expands the source into stronger system-level guarantees.
    supported_atoms = len(claim_tokens & span_tokens)
    if (
        len(claim_tokens) >= 3
        and supported_atoms >= 3
        and coverage >= 0.78
        and not expansion_terms
        and not claim_negated
    ):
        return SemanticSupportResult(
            relation=SOURCE_ENTAILS_CLAIM,
            reason=(
                "V2 bounded paraphrase support: normalized code/prose atoms cover at "
                "least 78% of the claim without new precision or semantic expansion"
            ),
            **common,
        )

    reasons = [
        f"normalized token coverage {coverage:.2%} is below the bounded recall gate"
        if coverage < 0.78
        else "support remains ambiguous after bounded normalization"
    ]
    if expansion_terms:
        reasons.append(
            "semantic-expansion terms remain unsupported: "
            + ", ".join(sorted(expansion_terms))
        )
    return SemanticSupportResult(
        relation=SOURCE_INSUFFICIENT,
        reason="; ".join(reasons),
        **common,
    )


def evaluate_source_span_support_v2(
    claim: str,
    span_text: str,
    source_pointer: str,
) -> SemanticSupportResult:
    """Run V1 first; use bounded V2 recall only for an insufficient V1 result."""

    v1 = evaluate_source_span_support(claim, span_text, source_pointer)
    if v1.relation != SOURCE_INSUFFICIENT:
        return v1
    return _recall_result(claim, span_text, source_pointer)
