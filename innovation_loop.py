# SPDX-License-Identifier: Proprietary
"""Adaptive worker-template scoring and topology control for Make-It-Heavy."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import yaml

URL_RE = re.compile(r"https?://[^\s)\]>]+", re.IGNORECASE)
TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]+")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
ACTION_WORDS = {
    "build",
    "test",
    "verify",
    "measure",
    "compare",
    "implement",
    "remove",
    "add",
    "repair",
    "deploy",
    "audit",
    "inspect",
    "prioritize",
    "next",
}
TRUTH_WORDS = {
    "uncertain",
    "unknown",
    "unverified",
    "inference",
    "assumption",
    "evidence",
    "source",
    "citation",
    "cannot confirm",
    "not proven",
    "gap",
    "contradiction",
}
SPECIFICITY_RE = re.compile(
    r"(?:\b\d+(?:\.\d+)?%?\b|`[^`]+`|\b[A-Z][A-Z0-9_ -]{3,}\b|"
    r"\b[\w.-]+/[\w./-]+\b)"
)
MANDATORY_ROLES = ("source_mapper", "adversarial_breaker", "proof_engineer")


class InnovationConfigurationError(ValueError):
    """Raised when the adaptive worker-template contract is invalid."""


@dataclass(frozen=True)
class WorkerTemplate:
    """One versioned innovation-worker contract."""

    template_id: str
    role: str
    objective: str
    task_template: str
    required_sections: Tuple[str, ...]
    source_target: int
    ideal_chars: Tuple[int, int]
    weights: Mapping[str, float]

    @property
    def version(self) -> str:
        """Return the version suffix encoded in the template identifier."""

        return self.template_id.rsplit(".", 1)[-1]


class AdaptiveWorkerLoop:
    """Build role-specific tasks, score each turn, and propose the next topology."""

    def __init__(
        self,
        template_path: Union[str, Path],
        memory: Any = None,
        *,
        min_workers: int = 4,
        max_workers: int = 8,
        target_quality: float = 78.0,
        target_benefit: float = 0.60,
    ) -> None:
        self.template_path = Path(template_path)
        self.memory = memory
        requested_min = int(min_workers)
        requested_max = int(max_workers)
        self.target_quality = float(target_quality)
        self.target_benefit = float(target_benefit)
        if not 1 <= requested_min <= requested_max <= 16:
            raise InnovationConfigurationError(
                "innovation worker bounds must satisfy 1 <= min <= max <= 16"
            )
        self.templates = self._load_templates(self.template_path)
        if not self.templates:
            raise InnovationConfigurationError("no innovation worker templates configured")
        self.max_workers = min(requested_max, len(self.templates))
        self.min_workers = min(requested_min, self.max_workers)
        if self.min_workers < len(MANDATORY_ROLES):
            raise InnovationConfigurationError(
                "min_workers must preserve source, adversarial, and proof coverage"
            )
        self.templates_by_role = {template.role: template for template in self.templates}
        self.last_report: Dict[str, Any] = {}

    @staticmethod
    def _load_templates(path: Path) -> Tuple[WorkerTemplate, ...]:
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise InnovationConfigurationError(f"template file not found: {path}") from exc
        except yaml.YAMLError as exc:
            raise InnovationConfigurationError(f"malformed template YAML: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("workers"), list):
            raise InnovationConfigurationError("worker templates must contain a workers array")

        templates: List[WorkerTemplate] = []
        seen_roles = set()
        seen_ids = set()
        dimensions = {
            "completion",
            "evidence",
            "specificity",
            "novelty",
            "actionability",
            "truth",
            "efficiency",
        }
        for index, raw in enumerate(payload["workers"]):
            if not isinstance(raw, dict):
                raise InnovationConfigurationError(f"workers[{index}] must be an object")
            required = {
                "template_id",
                "role",
                "objective",
                "task_template",
                "required_sections",
                "source_target",
                "ideal_chars",
                "weights",
            }
            missing = required.difference(raw)
            if missing:
                raise InnovationConfigurationError(
                    f"workers[{index}] missing {sorted(missing)}"
                )
            role = str(raw["role"])
            template_id = str(raw["template_id"])
            if role in seen_roles or template_id in seen_ids:
                raise InnovationConfigurationError(
                    f"duplicate role or template id: {role} / {template_id}"
                )
            seen_roles.add(role)
            seen_ids.add(template_id)

            weights = raw["weights"]
            if not isinstance(weights, dict) or set(weights) != dimensions:
                raise InnovationConfigurationError(
                    f"{role}: weights must define {sorted(dimensions)}"
                )
            numeric_weights = {key: float(value) for key, value in weights.items()}
            if any(
                not math.isfinite(value) or value < 0
                for value in numeric_weights.values()
            ):
                raise InnovationConfigurationError(
                    f"{role}: weights must be finite and non-negative"
                )
            if not math.isclose(sum(numeric_weights.values()), 1.0, abs_tol=1e-6):
                raise InnovationConfigurationError(f"{role}: weights must sum to 1.0")

            ideal_chars = tuple(int(value) for value in raw["ideal_chars"])
            if len(ideal_chars) != 2 or ideal_chars[0] <= 0 or ideal_chars[1] <= ideal_chars[0]:
                raise InnovationConfigurationError(f"{role}: invalid ideal_chars")

            sections = tuple(str(value) for value in raw["required_sections"])
            if not sections:
                raise InnovationConfigurationError(f"{role}: required_sections is empty")

            templates.append(
                WorkerTemplate(
                    template_id=template_id,
                    role=role,
                    objective=str(raw["objective"]),
                    task_template=str(raw["task_template"]),
                    required_sections=sections,
                    source_target=max(0, int(raw["source_target"])),
                    ideal_chars=(ideal_chars[0], ideal_chars[1]),
                    weights=numeric_weights,
                )
            )
        return tuple(templates)

    def template_for_role(self, role: str) -> Optional[WorkerTemplate]:
        """Return the configured template for a runtime worker role."""

        return self.templates_by_role.get(role)

    def active_templates(
        self, worker_profiles: Sequence[Mapping[str, Any]]
    ) -> Tuple[WorkerTemplate, ...]:
        """Bind runtime worker profiles to exact innovation templates."""

        templates: List[WorkerTemplate] = []
        for profile in worker_profiles:
            role = str(profile["role"])
            template = self.template_for_role(role)
            if template is None:
                raise InnovationConfigurationError(
                    f"runtime worker role has no innovation template: {role}"
                )
            templates.append(template)
        return tuple(templates)

    def build_subtasks(
        self,
        mission: str,
        worker_profiles: Sequence[Mapping[str, Any]],
    ) -> List[str]:
        """Build one distinct, versioned task from each active worker template."""

        tasks: List[str] = []
        adjustments = (
            self.memory.get_latest_template_adjustments()
            if self.memory is not None
            and hasattr(self.memory, "get_latest_template_adjustments")
            else {}
        )
        for template in self.active_templates(worker_profiles):
            adjustment = adjustments.get(template.role, {})
            instruction = str(adjustment.get("instruction") or "").strip()
            runtime_adjustment = (
                f"NEXT-TURN TEMPLATE ADJUSTMENT:\n{instruction}"
                if instruction
                else "NEXT-TURN TEMPLATE ADJUSTMENT:\nNone. Execute the base contract."
            )
            tasks.append(
                template.task_template.format(
                    mission=mission,
                    runtime_adjustment=runtime_adjustment,
                ).strip()
            )
        return tasks

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token.lower()
            for token in TOKEN_RE.findall(text)
            if len(token) > 2
        }

    @staticmethod
    def _section_score(response: str, sections: Sequence[str]) -> float:
        upper = response.upper()
        matches = sum(1 for section in sections if section.upper() in upper)
        return matches / len(sections)

    @staticmethod
    def _evidence_score(response: str, target: int) -> float:
        if target <= 0:
            evidence_terms = sum(
                1 for term in ("source", "evidence", "citation", "receipt")
                if term in response.lower()
            )
            return min(1.0, 0.55 + 0.15 * evidence_terms)
        urls = len(URL_RE.findall(response))
        citation_markers = response.lower().count("source:")
        return min(1.0, (urls + citation_markers) / target)

    @staticmethod
    def _specificity_score(response: str) -> float:
        matches = len(SPECIFICITY_RE.findall(response))
        return min(1.0, matches / 10.0)

    @staticmethod
    def _actionability_score(response: str) -> float:
        lower = response.lower()
        matches = sum(1 for word in ACTION_WORDS if word in lower)
        return min(1.0, matches / 6.0)

    @staticmethod
    def _truth_score(response: str) -> float:
        lower = response.lower()
        matches = sum(1 for word in TRUTH_WORDS if word in lower)
        absolute_penalty = sum(
            lower.count(phrase)
            for phrase in ("obviously", "guaranteed", "definitely proves", "always true")
        )
        return max(0.0, min(1.0, 0.2 + matches / 6.0 - absolute_penalty * 0.2))

    @staticmethod
    def _efficiency_score(response: str, ideal_chars: Tuple[int, int]) -> float:
        length = len(response)
        minimum, maximum = ideal_chars
        if minimum <= length <= maximum:
            return 1.0
        if length < minimum:
            return max(0.0, length / minimum)
        return max(0.0, maximum / length)

    @classmethod
    def _novelty_scores(cls, responses: Sequence[str]) -> List[float]:
        token_sets = [cls._tokens(response) for response in responses]
        if len(token_sets) <= 1:
            return [1.0]
        scores: List[float] = []
        for index, current in enumerate(token_sets):
            overlaps = []
            for other_index, other in enumerate(token_sets):
                if index == other_index:
                    continue
                union = current | other
                overlaps.append(len(current & other) / len(union) if union else 1.0)
            scores.append(max(0.0, 1.0 - max(overlaps, default=0.0)))
        return scores

    @staticmethod
    def _unique_sentence_ratio(response: str, peers: Sequence[str]) -> float:
        sentences = {
            " ".join(sentence.lower().split())
            for sentence in SENTENCE_RE.split(response)
            if len(sentence.split()) >= 5
        }
        if not sentences:
            return 0.0
        peer_sentences = {
            " ".join(sentence.lower().split())
            for peer in peers
            for sentence in SENTENCE_RE.split(peer)
            if len(sentence.split()) >= 5
        }
        return len(sentences - peer_sentences) / len(sentences)

    @staticmethod
    def _speed_score(elapsed: float, target: float = 45.0) -> float:
        return max(0.0, min(1.0, target / max(target, float(elapsed or 0.001))))

    def _score_one(
        self,
        template: WorkerTemplate,
        result: Mapping[str, Any],
        novelty: float,
        peers: Sequence[str],
    ) -> Dict[str, Any]:
        response = str(result.get("response") or "")
        runtime_status = str(result.get("status") or "error")
        reliable = runtime_status == "model_inference"
        completion = self._section_score(response, template.required_sections) if reliable else 0.0
        evidence = self._evidence_score(response, template.source_target) if reliable else 0.0
        specificity = self._specificity_score(response) if reliable else 0.0
        actionability = self._actionability_score(response) if reliable else 0.0
        truth = self._truth_score(response) if reliable else 0.0
        efficiency = self._efficiency_score(response, template.ideal_chars) if reliable else 0.0
        novelty = novelty if reliable else 0.0
        dimensions = {
            "completion": completion,
            "evidence": evidence,
            "specificity": specificity,
            "novelty": novelty,
            "actionability": actionability,
            "truth": truth,
            "efficiency": efficiency,
        }
        quality = 100.0 * sum(
            dimensions[name] * template.weights[name] for name in dimensions
        )
        unique_contribution = (
            self._unique_sentence_ratio(response, peers) if reliable else 0.0
        )
        speed = self._speed_score(float(result.get("execution_time") or 0.0)) if reliable else 0.0
        benefit = (
            0.35 * unique_contribution
            + 0.25 * completion
            + 0.30 * (quality / 100.0)
            + 0.10 * speed
        )
        return {
            "worker_id": int(result.get("agent_id", -1)),
            "template_id": template.template_id,
            "template_version": template.version,
            "role": template.role,
            "model": str(result.get("model") or ""),
            "runtime_status": runtime_status,
            "quality_score": round(quality, 2),
            "benefit_score": round(benefit, 4),
            "execution_time": round(float(result.get("execution_time") or 0.0), 3),
            "dimensions": {
                name: round(value, 4) for name, value in dimensions.items()
            },
            "unique_contribution": round(unique_contribution, 4),
            "response_chars": len(response),
        }

    def _previous_score(self, role: str) -> Optional[Dict[str, Any]]:
        if self.memory is None or not hasattr(self.memory, "get_recent_worker_scores"):
            return None
        rows = self.memory.get_recent_worker_scores(role, limit=1)
        return rows[0] if rows else None

    def _adjustment(self, score: Mapping[str, Any]) -> Dict[str, Any]:
        role = str(score["role"])
        quality = float(score["quality_score"])
        benefit = float(score["benefit_score"])
        dimensions = score["dimensions"]
        previous = self._previous_score(role)

        if score["runtime_status"] == "capacity_failure":
            action = "HOLD_TEMPLATE_CAPACITY"
            instruction = (
                "Preserve this template unchanged. The worker lost provider execution "
                "capacity, so lower shared concurrency and rerun before judging the role."
            )
        elif score["runtime_status"] in {"timeout", "error"}:
            action = "REPLACE_OR_NARROW"
            instruction = (
                "Cut the assignment to one bounded deliverable, preserve the required "
                "sections, and use the fastest reliable model/tool path."
            )
        elif previous and (
            quality < float(previous["quality_score"]) - 10.0
            and benefit < float(previous["benefit_score"]) - 0.10
        ):
            action = "ROLLBACK_PREVIOUS"
            instruction = (
                "Discard the last runtime adjustment and return to the base template; "
                "the previous change reduced both quality and marginal benefit."
            )
        elif float(dimensions["evidence"]) < 0.45:
            action = "TIGHTEN_EVIDENCE"
            instruction = (
                "Attach precise source pointers or executable receipts to every material "
                "claim and label unsupported statements as inference."
            )
        elif float(dimensions["completion"]) < 0.70:
            action = "NARROW_AND_COMPLETE"
            instruction = (
                "Answer every required section explicitly before adding optional detail; "
                "reduce scope rather than leaving sections incomplete."
            )
        elif quality >= 85.0 and benefit >= 0.70:
            action = "EXPAND_OR_DUPLICATE"
            instruction = (
                "Preserve this template and probe one adjacent failure mode or mechanism "
                "without repeating established findings."
            )
        elif quality >= 72.0 and benefit >= 0.50:
            action = "KEEP"
            instruction = "Preserve the current template; improve only evidence precision."
        elif quality >= 72.0 and benefit < 0.35:
            action = "MERGE_OR_REPURPOSE"
            instruction = (
                "Avoid overlap with peer workers; target the single unanswered question "
                "that only this role is positioned to resolve."
            )
        elif quality < 60.0 and benefit < 0.40:
            action = "RETIRE_OR_REPLACE"
            instruction = (
                "Replace this role or model unless the next run can demonstrate a distinct "
                "deliverable and complete its required sections."
            )
        else:
            action = "REPAIR"
            instruction = (
                "Keep the role but tighten specificity, actionability, and separation of "
                "evidence from inference."
            )
        return {
            "role": role,
            "template_id": score["template_id"],
            "action": action,
            "instruction": instruction,
            "quality_before": (
                round(float(previous["quality_score"]), 2) if previous else None
            ),
            "quality_after": quality,
            "benefit_before": (
                round(float(previous["benefit_score"]), 4) if previous else None
            ),
            "benefit_after": benefit,
        }

    def _next_worker_count(
        self,
        scores: Sequence[Mapping[str, Any]],
        current_count: int,
    ) -> Tuple[int, str]:
        capacity_failed = sum(
            1 for score in scores if score["runtime_status"] == "capacity_failure"
        )
        failed = sum(
            1 for score in scores if score["runtime_status"] in {"timeout", "error"}
        )
        redundant = sum(
            1
            for score in scores
            if float(score["quality_score"]) >= 72.0
            and float(score["benefit_score"]) < 0.35
        )
        high_value = sum(
            1
            for score in scores
            if float(score["quality_score"]) >= 82.0
            and float(score["benefit_score"]) >= 0.65
        )
        average_quality = mean(float(score["quality_score"]) for score in scores)
        average_benefit = mean(float(score["benefit_score"]) for score in scores)

        if capacity_failed:
            return (
                current_count,
                "hold logical count; provider-capacity failures require width repair, not role repair",
            )
        if failed:
            return current_count, "hold count; replace or narrow failed workers"
        if redundant >= 2:
            return (
                max(self.min_workers, current_count - 1),
                "reduce one worker because multiple outputs were high-quality but redundant",
            )
        if (
            average_quality < self.target_quality
            and high_value >= 2
            and current_count < self.max_workers
        ):
            return (
                current_count + 1,
                "add one challenger worker around the strongest high-benefit role",
            )
        if (
            average_quality >= 85.0
            and average_benefit >= self.target_benefit
            and current_count > self.min_workers
        ):
            return (
                current_count - 1,
                "compress the topology because quality and benefit exceed target",
            )
        return current_count, "keep count; tune templates before changing topology"

    @staticmethod
    def _next_provider_width(
        scores: Sequence[Mapping[str, Any]],
        current_width: int,
        logical_worker_count: int,
    ) -> Tuple[int, str]:
        """Adapt provider width separately from the logical specialist topology."""

        current_width = max(1, min(int(current_width), int(logical_worker_count)))
        capacity_failed = sum(
            1 for score in scores if score["runtime_status"] == "capacity_failure"
        )
        if capacity_failed:
            next_width = max(1, current_width // 2)
            return (
                next_width,
                f"reduce provider width {current_width}→{next_width}; "
                f"{capacity_failed} workers hit measured capacity contention",
            )
        if current_width < logical_worker_count:
            return (
                current_width,
                "hold reduced provider width until a matched clean turn proves spare capacity",
            )
        return (
            current_width,
            "provider width matched logical worker count without measured capacity contention",
        )

    def _next_roles(
        self,
        scores: Sequence[Mapping[str, Any]],
        next_count: int,
    ) -> List[str]:
        """Choose the next active roles while preserving proof and adversarial coverage."""

        mandatory_order = [
            "source_mapper",
            "adversarial_breaker",
            "proof_engineer",
        ]
        ranked = sorted(
            scores,
            key=lambda score: (
                0.65 * float(score["benefit_score"])
                + 0.35 * (float(score["quality_score"]) / 100.0)
            ),
            reverse=True,
        )
        next_count = max(next_count, len(MANDATORY_ROLES))
        selected: List[str] = []
        for role in mandatory_order:
            if role not in self.templates_by_role:
                raise InnovationConfigurationError(
                    f"mandatory innovation role is not configured: {role}"
                )
            if role not in selected and len(selected) < next_count:
                selected.append(role)
        for score in ranked:
            role = str(score["role"])
            if role not in selected and len(selected) < next_count:
                selected.append(role)
        if len(selected) < next_count:
            for template in self.templates:
                if template.role not in selected:
                    selected.append(template.role)
                if len(selected) >= next_count:
                    break
        return selected

    @staticmethod
    def _markdown_report(report: Mapping[str, Any]) -> str:
        lines = [
            "## WORKER INNOVATION REPORT",
            "",
            (
                f"**This turn:** {report['current_worker_count']} logical workers → "
                f"**next:** {report['next_worker_count']} logical workers; "
                f"provider width {report['current_provider_concurrency_width']}→"
                f"{report['next_provider_concurrency_width']}. "
                f"Average reviewable-worker quality **{report['average_quality']:.2f}/100**; "
                f"average heuristic benefit **{report['average_benefit']:.4f}**."
            ),
            "",
            "| Worker | Job | Quality | Benefit | Benefit delivered | Adjust next |",
            "|---|---|---:|---:|---|---|",
        ]
        by_role = {item["role"]: item for item in report["adjustments"]}
        for score in report["scores"]:
            adjustment = by_role[score["role"]]
            benefit_text = (
                f"{score['unique_contribution']:.0%} unique contribution; "
                f"{score['dimensions']['completion']:.0%} contract coverage"
            )
            lines.append(
                "| {role} | {template} | {quality:.2f} | {benefit:.4f} | "
                "{benefit_text} | {action} |".format(
                    role=score["role"],
                    template=score["template_id"],
                    quality=score["quality_score"],
                    benefit=score["benefit_score"],
                    benefit_text=benefit_text,
                    action=adjustment["action"],
                )
            )
        lines.extend(
            [
                "",
                f"**Logical-topology decision:** {report['topology_reason']}.",
                "",
                f"**Provider-width decision:** {report['provider_width_reason']}.",
                "",
                f"**Next active roles:** {', '.join(report['next_roles'])}.",
                "",
                (
                    "**Quality boundary:** these are deterministic output-contract and "
                    "marginal-contribution scores, not independent proof of factual correctness."
                ),
            ]
        )
        return "\n".join(lines)

    def evaluate_turn(
        self,
        mission_id: int,
        mission: str,
        results: Sequence[Mapping[str, Any]],
        synthesis: str,
    ) -> Dict[str, Any]:
        """Score one completed turn, persist it, and generate the next adjustment."""

        if not results:
            raise InnovationConfigurationError(
                "evaluate_turn requires at least one worker result"
            )
        templates = self.active_templates(
            [{"role": str(result["role"])} for result in results]
        )
        responses = [str(result.get("response") or "") for result in results]
        novelty_scores = self._novelty_scores(responses)
        scores: List[Dict[str, Any]] = []
        for index, (template, result) in enumerate(zip(templates, results)):
            peers = [
                response
                for peer_index, response in enumerate(responses)
                if peer_index != index
            ]
            scores.append(
                self._score_one(
                    template,
                    result,
                    novelty_scores[index],
                    peers,
                )
            )

        adjustments = [self._adjustment(score) for score in scores]
        next_count, topology_reason = self._next_worker_count(scores, len(scores))
        next_roles = self._next_roles(scores, next_count)
        current_provider_width = max(
            1,
            min(
                len(scores),
                int(getattr(self, "current_provider_concurrency_width", len(scores))),
            ),
        )
        next_provider_width, provider_width_reason = self._next_provider_width(
            scores,
            current_provider_width,
            next_count,
        )
        reviewable_scores = [
            score for score in scores if score["runtime_status"] == "model_inference"
        ]
        report: Dict[str, Any] = {
            "schema": "glaciereq.make-it-heavy.worker-turn-report.v1",
            "mission_id": mission_id,
            "mission": mission,
            "current_worker_count": len(scores),
            "next_worker_count": next_count,
            "next_roles": next_roles,
            "current_provider_concurrency_width": current_provider_width,
            "next_provider_concurrency_width": next_provider_width,
            "provider_width_reason": provider_width_reason,
            "performance_worker_count": len(reviewable_scores),
            "average_quality": (
                round(mean(score["quality_score"] for score in reviewable_scores), 2)
                if reviewable_scores
                else 0.0
            ),
            "average_benefit": (
                round(mean(score["benefit_score"] for score in reviewable_scores), 4)
                if reviewable_scores
                else 0.0
            ),
            "topology_reason": topology_reason,
            "scores": scores,
            "adjustments": adjustments,
            "synthesis_chars": len(synthesis),
            "silent_worker_omissions": 0,
        }
        report["markdown"] = self._markdown_report(report)

        if self.memory is not None:
            if hasattr(self.memory, "persist_adaptive_turn"):
                self.memory.persist_adaptive_turn(
                    mission_id,
                    scores,
                    adjustments,
                    len(scores),
                    next_count,
                    topology_reason,
                    report,
                )
            else:
                for score in scores:
                    if hasattr(self.memory, "log_worker_score"):
                        self.memory.log_worker_score(mission_id, score)
                for adjustment in adjustments:
                    if hasattr(self.memory, "log_template_adjustment"):
                        self.memory.log_template_adjustment(mission_id, adjustment)
                if hasattr(self.memory, "log_topology_adjustment"):
                    self.memory.log_topology_adjustment(
                        mission_id,
                        len(scores),
                        next_count,
                        topology_reason,
                        report,
                    )
        self.last_report = report
        return report
