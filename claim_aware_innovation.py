# SPDX-License-Identifier: Proprietary
"""Claim-discipline and evidence-pointer hardening for adaptive workers."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Sequence

from innovation_loop import (
    AdaptiveWorkerLoop,
    InnovationConfigurationError,
    WorkerTemplate,
)

EVIDENCE_REGISTRY_BEGIN = "EVIDENCE_REGISTRY_BEGIN"
EVIDENCE_REGISTRY_END = "EVIDENCE_REGISTRY_END"
CLAIM_CONTRACT = f"""
CLAIM DISCIPLINE — HARD GATE
Classify every material claim with one of these prefixes:
- OBSERVED[source-id]: directly supported by a named source when no structured evidence registry is supplied.
- OBSERVED[source-id#span-id]: required when the mission supplies a structured evidence registry.
- INFERENCE: derived interpretation that is not itself established by a source.
- PROPOSED: design choice, experiment, threshold, timeline, estimate, or mechanism.
- BLOCKED: cannot be determined from the supplied evidence.

Structured evidence registry markers:
{EVIDENCE_REGISTRY_BEGIN}
{{"S1": {{"E1": "path/to/file.py@<immutable-revision>#L10-L20"}}}}
{EVIDENCE_REGISTRY_END}

Rules:
1. OBSERVED claims require a non-empty source id. If a structured registry is present,
   they also require a registered span id: OBSERVED[S1#E1].
2. A registered span must resolve to an immutable revision plus a line locator. A valid
   pointer proves source/span identity only; it does NOT by itself prove semantic entailment.
3. If the mission does not provide the required source/span, use INFERENCE or BLOCKED
   rather than inventing a source pointer.
4. Any quantitative threshold, percentage, confidence score, duration, scale claim, or
   estimate that is not explicitly supplied by a source must be PROPOSED.
5. Example decision cards use placeholders such as <VERIFIED_VALUE>; do not invent
   realistic-looking example metrics.
6. Do not convert repository existence, a repository name, repeated model output, or an
   inferred architecture into verified behavior, deployment, adoption, or role fit.
7. High specificity is not a substitute for evidence. Unsupported specificity fails this gate.
""".strip()

CLAIM_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?P<tag>OBSERVED\[(?P<source>[^\]]+)\]|INFERENCE|PROPOSED|BLOCKED)\s*:",
    re.IGNORECASE,
)
QUANTITATIVE_RE = re.compile(
    r"(?:"
    r"[<>]=?\s*\d+(?:\.\d+)?|"
    r"\b\d+(?:\.\d+)?\s*%|"
    r"\b0\.\d{2,}\b|"
    r"\b\d+(?:\.\d+)?\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?|users?|requests?|repos(?:itories)?|files?|lines?)\b"
    r")",
    re.IGNORECASE,
)
CERTAINTY_RE = re.compile(
    r"\b(?:confirmed|definitively|proven|verified|guaranteed|requires?|must|will|cannot)\b",
    re.IGNORECASE,
)
PLACEHOLDER_RE = re.compile(r"<[^>]+>")
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
IMMUTABLE_LOCATOR_RE = re.compile(
    r"^(?P<path>[^@\s#]+)@(?P<revision>[0-9a-fA-F]{40}|[0-9a-fA-F]{64})"
    r"#L(?P<start>\d+)(?:-L?(?P<end>\d+))?$"
)
GENERIC_SOURCE_IDS = {"source", "citation", "evidence", "unknown"}

EvidenceRegistry = Dict[str, Dict[str, str]]


class ClaimAwareAdaptiveWorkerLoop(AdaptiveWorkerLoop):
    """Adaptive loop with claim classification and optional immutable source spans.

    The original claim gate remains backward-compatible for missions that expose only
    source ids. When a mission contains an evidence registry, OBSERVED claims become
    fail-closed on exact source/span identity. Pointer resolution is intentionally kept
    separate from semantic entailment: a resolved locator is reported as
    SOURCE_SUPPORT_UNCHECKED until a later semantic verifier evaluates the cited span.
    """

    def __init__(
        self,
        *args: Any,
        claim_gate_min_score: float = 0.75,
        claim_gate_quality_cap: float = 69.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.claim_gate_min_score = float(claim_gate_min_score)
        self.claim_gate_quality_cap = float(claim_gate_quality_cap)
        self._evidence_registry: EvidenceRegistry = {}
        if not 0.0 <= self.claim_gate_min_score <= 1.0:
            raise ValueError("claim_gate_min_score must be between 0 and 1")
        if not 0.0 <= self.claim_gate_quality_cap <= 100.0:
            raise ValueError("claim_gate_quality_cap must be between 0 and 100")

    @staticmethod
    def parse_evidence_registry(mission: str) -> EvidenceRegistry:
        """Parse and validate one bounded immutable evidence registry in a mission."""

        begin_count = mission.count(EVIDENCE_REGISTRY_BEGIN)
        end_count = mission.count(EVIDENCE_REGISTRY_END)
        if begin_count == 0 and end_count == 0:
            return {}
        if begin_count != 1 or end_count != 1:
            raise InnovationConfigurationError(
                "evidence registry requires exactly one begin marker and one end marker"
            )

        start = mission.find(EVIDENCE_REGISTRY_BEGIN)
        end = mission.find(EVIDENCE_REGISTRY_END)
        if start < 0 or end < 0 or end <= start:
            raise InnovationConfigurationError("malformed evidence registry markers")

        payload_text = mission[start + len(EVIDENCE_REGISTRY_BEGIN) : end].strip()
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise InnovationConfigurationError(
                f"malformed evidence registry JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict) or not payload:
            raise InnovationConfigurationError("evidence registry must be a non-empty object")

        registry: EvidenceRegistry = {}
        for raw_source_id, raw_spans in payload.items():
            source_id = str(raw_source_id).strip()
            if (
                not source_id
                or SOURCE_ID_RE.fullmatch(source_id) is None
                or source_id.lower() in GENERIC_SOURCE_IDS
            ):
                raise InnovationConfigurationError(
                    f"invalid evidence registry source id: {source_id!r}"
                )
            if not isinstance(raw_spans, dict) or not raw_spans:
                raise InnovationConfigurationError(
                    f"evidence registry source {source_id} must contain spans"
                )
            spans: Dict[str, str] = {}
            for raw_span_id, raw_locator in raw_spans.items():
                span_id = str(raw_span_id).strip()
                locator = str(raw_locator).strip()
                if not span_id or SOURCE_ID_RE.fullmatch(span_id) is None:
                    raise InnovationConfigurationError(
                        f"invalid evidence span id for {source_id}: {span_id!r}"
                    )
                match = IMMUTABLE_LOCATOR_RE.fullmatch(locator)
                if match is None:
                    raise InnovationConfigurationError(
                        f"evidence span {source_id}#{span_id} is not immutable: {locator!r}"
                    )
                start_line = int(match.group("start"))
                end_line = int(match.group("end") or start_line)
                if start_line <= 0 or end_line < start_line:
                    raise InnovationConfigurationError(
                        f"evidence span {source_id}#{span_id} has invalid line bounds"
                    )
                spans[span_id] = locator
            registry[source_id] = spans
        return registry

    def build_subtasks(
        self,
        mission: str,
        worker_profiles: Sequence[Mapping[str, Any]],
    ) -> List[str]:
        """Bind the mission registry and append the same truth contract to every worker."""

        self._evidence_registry = self.parse_evidence_registry(mission)
        return [
            f"{task}\n\n{CLAIM_CONTRACT}"
            for task in super().build_subtasks(mission, worker_profiles)
        ]

    @staticmethod
    def _parse_observed_reference(reference: str) -> tuple[str, str | None]:
        value = reference.strip()
        source_id, separator, span_id = value.partition("#")
        return source_id.strip(), span_id.strip() if separator else None

    def evaluate_claim_discipline(
        self,
        response: str,
        evidence_registry: Mapping[str, Mapping[str, str]] | None = None,
    ) -> Dict[str, Any]:
        """Measure claim classification and, when available, exact source-span identity."""

        registry: Mapping[str, Mapping[str, str]] = (
            self._evidence_registry if evidence_registry is None else evidence_registry
        )
        registry_active = bool(registry)
        claim_lines: List[str] = []
        observed_sources: List[str] = []
        observed_pointers: List[str] = []
        resolved_pointers: List[str] = []
        invalid_observed_references: List[str] = []
        unclassified_quantitative: List[str] = []
        unclassified_certainty: List[str] = []

        for raw_line in response.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = CLAIM_LINE_RE.match(line)
            if match:
                claim_lines.append(line)
                reference = match.group("source")
                if reference is not None:
                    source_id, span_id = self._parse_observed_reference(reference)
                    observed_sources.append(source_id)
                    valid_source_id = bool(
                        source_id
                        and SOURCE_ID_RE.fullmatch(source_id)
                        and source_id.lower() not in GENERIC_SOURCE_IDS
                    )
                    if not valid_source_id:
                        invalid_observed_references.append(reference.strip())
                        continue
                    if span_id:
                        observed_pointers.append(f"{source_id}#{span_id}")
                    if registry_active:
                        spans = registry.get(source_id)
                        if (
                            not span_id
                            or not isinstance(spans, Mapping)
                            or span_id not in spans
                        ):
                            invalid_observed_references.append(reference.strip())
                            continue
                        resolved_pointers.append(f"{source_id}#{span_id}")
                continue
            if PLACEHOLDER_RE.search(line):
                continue
            if QUANTITATIVE_RE.search(line):
                unclassified_quantitative.append(line[:240])
            if CERTAINTY_RE.search(line):
                unclassified_certainty.append(line[:240])

        tag_score = min(1.0, len(claim_lines) / 4.0)
        source_score = 1.0
        if observed_sources:
            valid_source_count = len(observed_sources) - len(invalid_observed_references)
            source_score = max(0.0, valid_source_count / len(observed_sources))

        pointer_score = 1.0
        if registry_active and observed_sources:
            pointer_score = len(resolved_pointers) / len(observed_sources)

        quantitative_score = max(0.0, 1.0 - 0.35 * len(unclassified_quantitative))
        certainty_score = max(0.0, 1.0 - 0.15 * len(unclassified_certainty))
        score = (
            0.35 * tag_score
            + 0.15 * source_score
            + 0.10 * pointer_score
            + 0.25 * quantitative_score
            + 0.15 * certainty_score
        )
        source_gate_pass = not invalid_observed_references
        pointer_gate_pass = not registry_active or (
            source_gate_pass and len(resolved_pointers) == len(observed_sources)
        )
        passed = (
            score >= self.claim_gate_min_score
            and not unclassified_quantitative
            and source_gate_pass
            and pointer_gate_pass
        )

        if not registry_active:
            pointer_status = "LEGACY_SOURCE_ID_MODE"
        elif invalid_observed_references:
            pointer_status = "SOURCE_POINTER_INVALID"
        elif observed_sources:
            pointer_status = "SOURCE_POINTER_RESOLVED"
        else:
            pointer_status = "NO_OBSERVED_CLAIMS"

        semantic_status = (
            "SOURCE_SUPPORT_UNCHECKED" if resolved_pointers else "NOT_APPLICABLE"
        )
        return {
            "score": round(score, 4),
            "pass": passed,
            "claim_line_count": len(claim_lines),
            "observed_source_count": len(observed_sources),
            "observed_pointer_count": len(observed_pointers),
            "resolved_pointer_count": len(resolved_pointers),
            "evidence_registry_active": registry_active,
            "source_pointer_status": pointer_status,
            "semantic_support_status": semantic_status,
            "semantic_support_unchecked_count": len(resolved_pointers),
            "invalid_observed_reference_count": len(invalid_observed_references),
            "invalid_observed_references": invalid_observed_references[:5],
            "unclassified_quantitative_count": len(unclassified_quantitative),
            "unclassified_certainty_count": len(unclassified_certainty),
            "unclassified_quantitative_examples": unclassified_quantitative[:5],
            "unclassified_certainty_examples": unclassified_certainty[:5],
        }

    def _score_one(
        self,
        template: WorkerTemplate,
        result: Mapping[str, Any],
        novelty: float,
        peers: Sequence[str],
    ) -> Dict[str, Any]:
        score = super()._score_one(template, result, novelty, peers)
        response = str(result.get("response") or "")
        reliable = score["runtime_status"] == "model_inference"
        claim_gate = (
            self.evaluate_claim_discipline(response)
            if reliable
            else {
                "score": 0.0,
                "pass": False,
                "claim_line_count": 0,
                "observed_source_count": 0,
                "observed_pointer_count": 0,
                "resolved_pointer_count": 0,
                "evidence_registry_active": bool(self._evidence_registry),
                "source_pointer_status": "RUNTIME_FAILURE",
                "semantic_support_status": "NOT_APPLICABLE",
                "semantic_support_unchecked_count": 0,
                "invalid_observed_reference_count": 0,
                "invalid_observed_references": [],
                "unclassified_quantitative_count": 0,
                "unclassified_certainty_count": 0,
                "unclassified_quantitative_examples": [],
                "unclassified_certainty_examples": [],
            }
        )
        claim_gate["pass"] = bool(
            claim_gate["pass"]
            and float(claim_gate["score"]) >= self.claim_gate_min_score
        )
        score["claim_gate"] = claim_gate
        score["pre_claim_gate_quality_score"] = score["quality_score"]
        score["pre_claim_gate_benefit_score"] = score["benefit_score"]

        if reliable and not claim_gate["pass"]:
            capped_quality = min(
                float(score["quality_score"]),
                self.claim_gate_quality_cap,
            )
            score["quality_score"] = round(capped_quality, 2)
            completion = float(score["dimensions"]["completion"])
            unique_contribution = float(score["unique_contribution"])
            speed = self._speed_score(float(score["execution_time"]))
            benefit = (
                0.35 * unique_contribution
                + 0.25 * completion
                + 0.30 * (capped_quality / 100.0)
                + 0.10 * speed
            )
            score["benefit_score"] = round(benefit, 4)
        return score

    def _adjustment(self, score: Mapping[str, Any]) -> Dict[str, Any]:
        claim_gate = score.get("claim_gate")
        if (
            score.get("runtime_status") == "model_inference"
            and isinstance(claim_gate, Mapping)
            and not bool(claim_gate.get("pass"))
        ):
            previous = self._previous_score(str(score["role"]))
            if (
                claim_gate.get("evidence_registry_active")
                and int(claim_gate.get("invalid_observed_reference_count") or 0) > 0
            ):
                action = "TIGHTEN_SOURCE_POINTERS"
                instruction = (
                    "Use OBSERVED[source-id#span-id] only when that exact pair exists in "
                    "the mission EVIDENCE_REGISTRY. Otherwise classify the statement as "
                    "INFERENCE or BLOCKED. A resolved pointer is not semantic entailment."
                )
            else:
                action = "TIGHTEN_CLAIM_DISCIPLINE"
                instruction = (
                    "Classify material claims as OBSERVED[source-id], INFERENCE, "
                    "PROPOSED, or BLOCKED. Remove or explicitly mark every unsourced "
                    "threshold, timeline, confidence score, scale claim, and estimate."
                )
            return {
                "role": score["role"],
                "template_id": score["template_id"],
                "action": action,
                "instruction": instruction,
                "quality_before": (
                    round(float(previous["quality_score"]), 2) if previous else None
                ),
                "quality_after": score["quality_score"],
                "benefit_before": (
                    round(float(previous["benefit_score"]), 4) if previous else None
                ),
                "benefit_after": score["benefit_score"],
            }
        return super()._adjustment(score)

    @staticmethod
    def _markdown_report(report: Mapping[str, Any]) -> str:
        lines = [
            "## WORKER INNOVATION REPORT",
            "",
            (
                f"**This turn:** {report['current_worker_count']} workers → "
                f"**next:** {report['next_worker_count']} workers. "
                f"Average quality **{report['average_quality']:.2f}/100**; "
                f"average marginal benefit **{report['average_benefit']:.4f}**."
            ),
            "",
            "| Worker | Quality | Benefit | Claim gate | Source pointer | Benefit delivered | Adjust next |",
            "|---|---:|---:|---|---|---|---|",
        ]
        by_role = {item["role"]: item for item in report["adjustments"]}
        for score in report["scores"]:
            adjustment = by_role[score["role"]]
            gate = score.get("claim_gate", {})
            gate_text = "PASS" if gate.get("pass") else "FAIL"
            pointer_text = str(gate.get("source_pointer_status") or "N/A")
            benefit_text = (
                f"{score['unique_contribution']:.0%} unique; "
                f"{score['dimensions']['completion']:.0%} contract coverage"
            )
            lines.append(
                "| {role} | {quality:.2f} | {benefit:.4f} | {gate} | {pointer} | "
                "{benefit_text} | {action} |".format(
                    role=score["role"],
                    quality=score["quality_score"],
                    benefit=score["benefit_score"],
                    gate=gate_text,
                    pointer=pointer_text,
                    benefit_text=benefit_text,
                    action=adjustment["action"],
                )
            )
        lines.extend(
            [
                "",
                f"**Topology decision:** {report['topology_reason']}.",
                "",
                f"**Next active roles:** {', '.join(report['next_roles'])}.",
                "",
                (
                    "**Quality boundary:** structural quality and marginal contribution "
                    "cannot override the claim/source-pointer gate. A resolved evidence "
                    "pointer proves source identity, not semantic entailment; factual "
                    "correctness still requires source-span review or executable proof."
                ),
            ]
        )
        return "\n".join(lines)
