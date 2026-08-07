# SPDX-License-Identifier: Proprietary
"""Turn-6 bounded recall challenger for source-span semantic support.

V2 never overrides a V1 entailment or contradiction. It revisits only V1
SOURCE_INSUFFICIENT results. Recall improvements come from auditable code-evidence
atoms and citation normalization rather than from globally weakening thresholds.
"""

from __future__ import annotations

import re
from typing import Set, Tuple

from semantic_support import (
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

CONTEXT_WORDS = {
    "code",
    "implementation",
    "payload",
    "receipt",
    "regression",
    "resolver",
    "result",
    "test",
    "verifier",
    "verification",
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
    """Remove line-number citation decorations, not substantive numbers."""

    return " ".join(CITATION_METADATA_RE.sub(" ", text).split())


def _stem(token: str) -> str:
    token = token.lower()
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
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
    """Split prose and snake/path/code identifiers into comparable atoms."""

    tokens: Set[str] = set()
    for raw in WORD_RE.findall(_normalize_phrases(text)):
        candidates = [raw]
        candidates.extend(part for part in SPLIT_RE.split(raw) if part)
        for candidate in candidates:
            lowered = candidate.lower().strip(".,;:")
            if len(lowered) <= 1 or lowered in STOPWORDS or lowered in CONTEXT_WORDS:
                continue
            tokens.add(_stem(lowered))
    return tokens


def _unsupported_code_tokens(claim: str, span: str) -> Tuple[str, ...]:
    """Reject source-absent code-shaped precision without path/punctuation false positives."""

    span_raw = {token.lower().strip(".,;:") for token in WORD_RE.findall(span)}
    unsupported = []
    for raw in WORD_RE.findall(claim):
        token = raw.strip(".,;:")
        lowered = token.lower()
        code_shaped = (
            "_" in token
            or token.startswith("--")
            or "^{" in token
            or token.endswith(".py")
        )
        if not code_shaped or lowered in span_raw:
            continue
        if any(candidate.endswith("/" + lowered) for candidate in span_raw):
            continue
        parts = {
            part
            for part in SPLIT_RE.split(lowered)
            if len(part) > 1
        }
        span_parts = _expanded_tokens(span)
        if not parts or not parts.issubset(span_parts):
            unsupported.append(token)
    return tuple(sorted(set(unsupported)))


def _source_atoms(span: str) -> Set[str]:
    """Extract narrow executable facts from the bounded source span."""

    low = span.lower()
    atoms: Set[str] = set()

    if '"git"' in low and '"rev-parse"' in low:
        command = "git:rev-parse"
        if '"--verify"' in low:
            command += ":verify"
        if "head^{commit}" in low:
            command += ":head-commit"
        atoms.add(command)
    if "return none" in low and (
        "returncode != 0" in low or "fullmatch(resolved) is none" in low
    ):
        atoms.add("resolution-failure:return-none")

    if "collection_code != 0" in low:
        atoms.add("collection:success-required")
    if "collection_count <= 0" in low:
        atoms.add("collection:positive-required")
    if 'receipt.get("observed_test_count")' in low and "<= 0" in low:
        atoms.add("observed_test_count:positive-required")

    field_patterns = (
        r'\.get\("([a-zA-Z_][a-zA-Z0-9_]*)"\)',
        r'\["([a-zA-Z_][a-zA-Z0-9_]*)"\]',
        r'(?:^|[,{]\s*)"([a-zA-Z_][a-zA-Z0-9_]*)"\s*:',
    )
    for pattern in field_patterns:
        for field in re.findall(pattern, span):
            atoms.add(f"field:{field.lower()}")

    if "actions/checkout" in low and "github.event.pull_request.head.sha" in low:
        atoms.add("checkout:pr-head-sha")
    if (
        "run_featured_verification.py" in low
        and "--ref" in low
        and "git rev-parse head" in low
    ):
        atoms.add("verification:resolved-head-ref")
    if (
        'receipt.get("resolved_commit_sha") != expected' in low
        and "raise systemexit" in low
    ):
        atoms.add("mismatch:resolved_commit_sha:expected:exit")

    if re.search(r"resolve_commit_sha\(tmp_path\)\s*==\s*expected", low):
        atoms.add("resolve_commit_sha:git:expected")
    if re.search(r"resolve_commit_sha\(non_git_path\)\s+is\s+none", low):
        atoms.add("resolve_commit_sha:non-git:none")

    for match in re.finditer(
        r'(?:payload\["(?P<field>[a-zA-Z_][a-zA-Z0-9_]*)"\]|'
        r'(?P<name>\b(?:count|code)\b))\s*==\s*(?P<value>"[^"]+"|\d+)',
        span,
    ):
        key = (match.group("field") or match.group("name")).lower()
        value = match.group("value").strip('"').lower()
        atoms.add(f"eq:{key}:{value}")
    for field in re.findall(
        r'payload\["([a-zA-Z_][a-zA-Z0-9_]*)"\]\s+is\s+None',
        span,
        flags=re.I,
    ):
        atoms.add(f"none:{field.lower()}")

    return atoms


def _claim_atoms(claim: str) -> Set[str]:
    """Map bounded natural-language paraphrases onto executable source atoms."""

    low = claim.lower()
    atoms: Set[str] = set()

    if "git rev-parse" in low:
        command = "git:rev-parse"
        if "--verify" in low:
            command += ":verify"
        if "head^{commit}" in low:
            command += ":head-commit"
        atoms.add(command)
    if re.search(r"\bgit\s+show\b", low):
        command = "git:show"
        if "--verify" in low:
            command += ":verify"
        if "head^{commit}" in low:
            command += ":head-commit"
        atoms.add(command)
    if (
        "return" in low
        and "none" in low
        and ("fail" in low or "failure" in low)
        and ("resol" in low or "commit" in low)
    ):
        atoms.add("resolution-failure:return-none")

    if "collection" in low and ("must succeed" in low or "must be successful" in low):
        atoms.add("collection:success-required")
    if "collection" in low and ("at least one" in low or "one or more" in low):
        atoms.add("collection:positive-required")

    field_phrases = {
        "resolved_commit_sha": ("resolved commit sha",),
        "identity_status": ("identity status",),
        "observed_test_count": ("observed test count", "observed tests"),
        "status": (" status ",),
        "exit_code": ("exit code",),
    }
    padded = f" {low} "
    for field, phrases in field_phrases.items():
        if any(phrase in padded for phrase in phrases):
            atoms.add(f"field:{field}")

    if (
        ("zero observed tests" in low or "zero observed test" in low)
        and ("pass" in low or "succeed" in low)
    ):
        atoms.add("observed_test_count:zero-allowed")

    if "pull request head sha" in low and ("checkout" in low or "check" in low):
        atoms.add("checkout:pr-head-sha")
    if "run_featured_verification.py" in low and "--ref" in low and "head" in low:
        atoms.add("verification:resolved-head-ref")
    if (
        "resolved commit sha" in low
        and "expected" in low
        and (
            "does not equal" in low
            or "differs from" in low
            or "does not match" in low
            or "mismatch" in low
        )
        and ("exit" in low or "reject" in low)
    ):
        atoms.add("mismatch:resolved_commit_sha:expected:exit")

    if (
        "resolve_commit_sha" in low
        and "expected" in low
        and ("git" in low or "checkout" in low)
    ):
        atoms.add("resolve_commit_sha:git:expected")
    if (
        "resolve_commit_sha" in low
        and "none" in low
        and ("non-git" in low or "non git" in low)
    ):
        atoms.add("resolve_commit_sha:non-git:none")

    if "status blocked_identity" in low:
        atoms.add("eq:status:blocked_identity")
    if "identity" in low and "unresolved" in low:
        atoms.add("eq:identity_status:unresolved")
    if "no resolved commit sha" in low or "resolved commit sha is none" in low:
        atoms.add("none:resolved_commit_sha")

    count_match = re.search(r"\bcount\s+(\d+)", low)
    if count_match:
        atoms.add(f"eq:count:{count_match.group(1)}")
    exit_match = re.search(r"\bexit\s+code\s+(\d+)", low)
    if exit_match:
        atoms.add(f"eq:exit_code:{exit_match.group(1)}")
    else:
        code_match = re.search(r"\b(?:return\s+)?code\s+(\d+)", low)
        if code_match:
            atoms.add(f"eq:code:{code_match.group(1)}")
    status_match = re.search(r"\bstatus\s+([A-Z_]+)", claim)
    if status_match:
        atoms.add(f"eq:status:{status_match.group(1).lower()}")

    return atoms


def _recall_result(
    claim: str,
    span_text: str,
    source_pointer: str,
) -> SemanticSupportResult:
    stripped_claim = strip_citation_metadata(claim)
    stripped_span = strip_citation_metadata(span_text)

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
    unsupported_numbers = tuple(sorted(_numbers(stripped_claim) - _numbers(stripped_span)))
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
    if expansion_terms:
        return SemanticSupportResult(
            relation=SOURCE_INSUFFICIENT,
            reason=(
                "V2 abstains on unsupported semantic expansion: "
                + ", ".join(sorted(expansion_terms))
            ),
            **common,
        )

    claim_atoms = _claim_atoms(stripped_claim)
    source_atoms = _source_atoms(stripped_span)
    if claim_atoms and claim_atoms.issubset(source_atoms):
        return SemanticSupportResult(
            relation=SOURCE_ENTAILS_CLAIM,
            reason="V2 code-evidence atoms entail every bounded predicate in the paraphrase",
            **common,
        )

    if _opposite_state_contradiction(stripped_claim, stripped_span):
        return SemanticSupportResult(
            relation=SOURCE_CONTRADICTS_CLAIM,
            reason="V2 detected an explicit exclusive-state conflict",
            **common,
        )

    supported_atoms = len(claim_tokens & span_tokens)
    if (
        not claim_atoms
        and len(claim_tokens) >= 3
        and supported_atoms >= 3
        and coverage >= 0.78
    ):
        return SemanticSupportResult(
            relation=SOURCE_ENTAILS_CLAIM,
            reason=(
                "V2 bounded lexical fallback covers at least 78% of normalized claim atoms "
                "without new precision or semantic expansion"
            ),
            **common,
        )

    if claim_atoms:
        reason = "source lacks required code-evidence atoms: " + ", ".join(
            sorted(claim_atoms - source_atoms)
        )
    else:
        reason = f"normalized token coverage {coverage:.2%} is below the bounded recall gate"
    return SemanticSupportResult(
        relation=SOURCE_INSUFFICIENT,
        reason=reason,
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
