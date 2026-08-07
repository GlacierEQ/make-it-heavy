# SPDX-License-Identifier: Proprietary
"""Semantic evidence gating layered onto claim-aware adaptive workers."""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Sequence

from claim_aware_innovation import ClaimAwareAdaptiveWorkerLoop, WorkerTemplate
from innovation_loop import InnovationConfigurationError
from semantic_claim_firewall import evaluate_semantic_claim_firewall

SEMANTIC_SPAN_REGISTRY_BEGIN = "SEMANTIC_SPAN_REGISTRY_BEGIN"
SEMANTIC_SPAN_REGISTRY_END = "SEMANTIC_SPAN_REGISTRY_END"
SEMANTIC_CLAIM_CONTRACT = f"""
SEMANTIC CLAIM FIREWALL — HARD GATE WHEN SPAN TEXT IS REGISTERED
If the mission contains {SEMANTIC_SPAN_REGISTRY_BEGIN}/{SEMANTIC_SPAN_REGISTRY_END}:
1. Every OBSERVED[source#span] line must state one atomic proposition that the exact
   registered span itself supports.
2. Put interpretation, implications, generalization, risk, and system conclusions under
   INFERENCE rather than stretching an OBSERVED claim.
3. Put designs, experiments, thresholds, and future changes under PROPOSED.
4. Do not include line ranges, commit ids, counts, durations, or implementation details in
   an OBSERVED claim unless those exact details appear in the registered span text.
5. A valid pointer without semantic support earns no evidence credit.
6. SOURCE_INSUFFICIENT means narrow or reclassify the claim; do not pressure the evaluator
   to return SOURCE_ENTAILS_CLAIM.
7. SOURCE_CONTRADICTS_CLAIM is an adversarial escalation, not a prompt-repair target.
""".strip()


class SemanticClaimAdaptiveWorkerLoop(ClaimAwareAdaptiveWorkerLoop):
    """Adaptive loop whose evidence credit requires pointer + semantic support."""

    def __init__(
        self,
        *args: Any,
        semantic_gate_quality_cap: float = 59.0,
        require_observed_with_semantic_registry: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.semantic_gate_quality_cap = float(semantic_gate_quality_cap)
        self.require_observed_with_semantic_registry = bool(
            require_observed_with_semantic_registry
        )
        self._semantic_spans: Dict[str, str] = {}
        if not 0.0 <= self.semantic_gate_quality_cap <= 100.0:
            raise ValueError("semantic_gate_quality_cap must be between 0 and 100")

    @staticmethod
    def parse_semantic_span_registry(mission: str) -> Dict[str, str]:
        """Parse one optional pointer->source-span JSON registry from the mission."""

        begin_count = mission.count(SEMANTIC_SPAN_REGISTRY_BEGIN)
        end_count = mission.count(SEMANTIC_SPAN_REGISTRY_END)
        if begin_count == 0 and end_count == 0:
            return {}
        if begin_count != 1 or end_count != 1:
            raise InnovationConfigurationError(
                "semantic span registry requires exactly one begin and end marker"
            )
        start = mission.find(SEMANTIC_SPAN_REGISTRY_BEGIN)
        end = mission.find(SEMANTIC_SPAN_REGISTRY_END)
        if start < 0 or end <= start:
            raise InnovationConfigurationError("malformed semantic span registry markers")

        payload_text = mission[
            start + len(SEMANTIC_SPAN_REGISTRY_BEGIN) : end
        ].strip()
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise InnovationConfigurationError(
                f"malformed semantic span registry JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict) or not payload:
            raise InnovationConfigurationError(
                "semantic span registry must be a non-empty object"
            )

        registry: Dict[str, str] = {}
        for raw_pointer, raw_span in payload.items():
            pointer = str(raw_pointer).strip()
            span = str(raw_span).strip()
            if "#" not in pointer or not pointer.split("#", 1)[0].strip():
                raise InnovationConfigurationError(
                    f"semantic span registry pointer must be source#span: {pointer!r}"
                )
            if not span:
                raise InnovationConfigurationError(
                    f"semantic span registry has empty source text: {pointer}"
                )
            registry[pointer] = span
        return registry

    def build_subtasks(
        self,
        mission: str,
        worker_profiles: Sequence[Mapping[str, Any]],
    ) -> list[str]:
        """Bind pointer identity and semantic span text before worker execution."""

        tasks = super().build_subtasks(mission, worker_profiles)
        self._semantic_spans = self.parse_semantic_span_registry(mission)
        if self._semantic_spans and self._evidence_registry:
            registered_pointers = {
                f"{source_id}#{span_id}"
                for source_id, spans in self._evidence_registry.items()
                for span_id in spans
            }
            unknown = sorted(set(self._semantic_spans) - registered_pointers)
            if unknown:
                raise InnovationConfigurationError(
                    "semantic spans must correspond to immutable evidence pointers: "
                    f"{unknown}"
                )
        if not self._semantic_spans:
            return tasks
        return [f"{task}\n\n{SEMANTIC_CLAIM_CONTRACT}" for task in tasks]

    def _score_one(
        self,
        template: WorkerTemplate,
        result: Mapping[str, Any],
        novelty: float,
        peers: Sequence[str],
    ) -> Dict[str, Any]:
        score = super()._score_one(template, result, novelty, peers)
        reliable = score["runtime_status"] == "model_inference"
        if not self._semantic_spans:
            score["semantic_claim_gate"] = {
                "applicable": False,
                "pass": True,
                "score": 1.0,
                "adjustment": "NOT_APPLICABLE",
            }
            return score

        response = str(result.get("response") or "")
        semantic_gate = (
            evaluate_semantic_claim_firewall(
                response,
                self._semantic_spans,
                require_observed=self.require_observed_with_semantic_registry,
            )
            if reliable
            else {
                "applicable": True,
                "pass": False,
                "score": 0.0,
                "adjustment": "RUNTIME_FAILURE",
                "observed_claim_count": 0,
                "relation_counts": {},
                "claims": [],
            }
        )
        score["semantic_claim_gate"] = semantic_gate
        score["pre_semantic_gate_quality_score"] = score["quality_score"]
        score["pre_semantic_gate_benefit_score"] = score["benefit_score"]

        if reliable and not semantic_gate["pass"]:
            capped_quality = min(
                float(score["quality_score"]),
                self.semantic_gate_quality_cap,
            )
            score["quality_score"] = round(capped_quality, 2)
            completion = float(score["dimensions"]["completion"])
            unique_contribution = float(score["unique_contribution"])
            speed = self._speed_score(float(score["execution_time"]))
            semantic_support = float(semantic_gate.get("score") or 0.0)
            benefit = (
                0.30 * unique_contribution
                + 0.20 * completion
                + 0.25 * (capped_quality / 100.0)
                + 0.10 * speed
                + 0.15 * semantic_support
            )
            score["benefit_score"] = round(benefit, 4)
        return score

    def _adjustment(self, score: Mapping[str, Any]) -> Dict[str, Any]:
        gate = score.get("semantic_claim_gate")
        if (
            score.get("runtime_status") == "model_inference"
            and isinstance(gate, Mapping)
            and bool(gate.get("applicable"))
            and not bool(gate.get("pass"))
        ):
            previous = self._previous_score(str(score["role"]))
            action = str(gate.get("adjustment") or "NARROW_OBSERVED_TO_SPAN")
            relation_counts = gate.get("relation_counts") or {}
            if action == "ESCALATE_CONTRADICTION":
                instruction = (
                    "Do not repair the cited claim toward agreement. Preserve the exact source "
                    "and worker claim, surface the contradiction, and hand it to the adversarial "
                    "or proof lane for review."
                )
            elif action == "FIX_SEMANTIC_POINTER":
                instruction = (
                    "Use only registered source#span pointers with exact source text. If the "
                    "required span is absent, classify the statement BLOCKED instead of OBSERVED."
                )
            elif action == "ADD_ATOMIC_OBSERVED_CLAIM":
                instruction = (
                    "Add at least one atomic OBSERVED[source#span] proposition copied or tightly "
                    "paraphrased from the registered span; keep implications under INFERENCE."
                )
            else:
                insufficient = int(relation_counts.get("SOURCE_INSUFFICIENT") or 0)
                instruction = (
                    "Narrow each OBSERVED claim to one proposition entailed by its exact source "
                    f"span. This turn had {insufficient} semantically insufficient OBSERVED "
                    "claim(s). Move implications/generalization to INFERENCE and design choices "
                    "to PROPOSED."
                )
            return {
                "role": score["role"],
                "template_id": score["template_id"],
                "action": action,
                "instruction": instruction,
                "quality_before": (
                    round(float(previous["quality_score"]), 2) if previous else None
                ),
                "quality_after": float(score["quality_score"]),
                "benefit_before": (
                    round(float(previous["benefit_score"]), 4) if previous else None
                ),
                "benefit_after": float(score["benefit_score"]),
            }
        return super()._adjustment(score)
