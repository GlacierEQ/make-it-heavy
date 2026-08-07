# SPDX-License-Identifier: Proprietary
"""Claim-discipline hardening for the adaptive Make-It-Heavy worker loop."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Sequence

from innovation_loop import AdaptiveWorkerLoop, WorkerTemplate

CLAIM_CONTRACT = """
CLAIM DISCIPLINE — HARD GATE
Classify every material claim with one of these prefixes:
- OBSERVED[source-id]: directly supported by a source or receipt named in the mission.
- INFERENCE: derived interpretation that is not itself established by a source.
- PROPOSED: design choice, experiment, threshold, timeline, estimate, or mechanism.
- BLOCKED: cannot be determined from the supplied evidence.

Rules:
1. OBSERVED claims require a non-empty source-id. If the mission does not provide a source id, use BLOCKED rather than inventing one.
2. Any quantitative threshold, percentage, confidence score, duration, scale claim, or estimate that is not explicitly supplied by a source must be PROPOSED.
3. Example decision cards use placeholders such as <VERIFIED_VALUE>; do not invent realistic-looking example metrics.
4. Do not convert repository existence, a repository name, repeated model output, or an inferred architecture into verified behavior, deployment, adoption, or role fit.
5. High specificity is not a substitute for evidence. Unsupported specificity fails this gate.
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


class ClaimAwareAdaptiveWorkerLoop(AdaptiveWorkerLoop):
    """Adaptive worker loop with a hard claim-classification gate.

    The inherited quality dimensions remain useful for structure, novelty, and
    marginal contribution. This layer prevents those soft scores from masking
    unsupported quantitative or certainty-heavy claims.
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
        if not 0.0 <= self.claim_gate_min_score <= 1.0:
            raise ValueError("claim_gate_min_score must be between 0 and 1")
        if not 0.0 <= self.claim_gate_quality_cap <= 100.0:
            raise ValueError("claim_gate_quality_cap must be between 0 and 100")

    def build_subtasks(
        self,
        mission: str,
        worker_profiles: Sequence[Mapping[str, Any]],
    ) -> List[str]:
        """Append the same truth contract to every active worker assignment."""

        return [
            f"{task}\n\n{CLAIM_CONTRACT}"
            for task in super().build_subtasks(mission, worker_profiles)
        ]

    @staticmethod
    def evaluate_claim_discipline(response: str) -> Dict[str, Any]:
        """Measure whether material certainty and quantitative claims are classified."""

        claim_lines = []
        observed_sources = []
        unclassified_quantitative = []
        unclassified_certainty = []

        for raw_line in response.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = CLAIM_LINE_RE.match(line)
            if match:
                claim_lines.append(line)
                source = match.group("source")
                if source is not None:
                    observed_sources.append(source.strip())
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
            invalid_sources = [
                source
                for source in observed_sources
                if not source
                or source.lower() in {"source", "citation", "evidence", "unknown"}
            ]
            source_score = max(0.0, 1.0 - len(invalid_sources) / len(observed_sources))
        quantitative_score = max(0.0, 1.0 - 0.35 * len(unclassified_quantitative))
        certainty_score = max(0.0, 1.0 - 0.15 * len(unclassified_certainty))
        score = (
            0.35 * tag_score
            + 0.25 * source_score
            + 0.25 * quantitative_score
            + 0.15 * certainty_score
        )
        passed = score >= 0.75 and not unclassified_quantitative
        return {
            "score": round(score, 4),
            "pass": passed,
            "claim_line_count": len(claim_lines),
            "observed_source_count": len(observed_sources),
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
            return {
                "role": score["role"],
                "template_id": score["template_id"],
                "action": "TIGHTEN_CLAIM_DISCIPLINE",
                "instruction": (
                    "Classify material claims as OBSERVED[source-id], INFERENCE, "
                    "PROPOSED, or BLOCKED. Remove or explicitly mark every unsourced "
                    "threshold, timeline, confidence score, scale claim, and estimate."
                ),
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
            "| Worker | Quality | Benefit | Claim gate | Benefit delivered | Adjust next |",
            "|---|---:|---:|---|---|---|",
        ]
        by_role = {item["role"]: item for item in report["adjustments"]}
        for score in report["scores"]:
            adjustment = by_role[score["role"]]
            gate = score.get("claim_gate", {})
            gate_text = "PASS" if gate.get("pass") else "FAIL"
            benefit_text = (
                f"{score['unique_contribution']:.0%} unique; "
                f"{score['dimensions']['completion']:.0%} contract coverage"
            )
            lines.append(
                "| {role} | {quality:.2f} | {benefit:.4f} | {gate} | "
                "{benefit_text} | {action} |".format(
                    role=score["role"],
                    quality=score["quality_score"],
                    benefit=score["benefit_score"],
                    gate=gate_text,
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
                    "cannot override the claim-discipline gate; factual correctness still "
                    "requires source review or executable proof."
                ),
            ]
        )
        return "\n".join(lines)
