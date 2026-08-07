# SPDX-License-Identifier: Proprietary
"""Pre-generation immutable evidence hydration for adaptive workers.

Workers should not be asked to write semantically bounded OBSERVED claims from opaque
locators alone.  This layer resolves the registered immutable spans once before worker
dispatch, injects the exact prompt-visible bytes with hashes, and reuses those same bytes
for post-generation semantic scoring.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Sequence

from claim_aware_innovation import (
    CLAIM_CONTRACT,
    OBSERVED_LINE_RE,
    ClaimAwareAdaptiveWorkerLoop,
)
from semantic_support_v2_batch import evaluate_observed_claims_v2

HYDRATED_EVIDENCE_BEGIN = "HYDRATED_EVIDENCE_BEGIN"
HYDRATED_EVIDENCE_END = "HYDRATED_EVIDENCE_END"

HYDRATION_CONTRACT = f"""
PRE-GENERATION EVIDENCE CONTRACT
When {HYDRATED_EVIDENCE_BEGIN}/{HYDRATED_EVIDENCE_END} is present:
1. OBSERVED[source-id#span-id] may use only a packet with prompt_available=true.
2. Keep each OBSERVED sentence atomic: one proposition supported by the exact packet text.
3. Move interpretation, implications, system diagnosis, prioritization, and generalization to INFERENCE.
4. Move designs, experiments, thresholds, and future mechanisms to PROPOSED.
5. If a pointer is unresolved or omitted by the prompt budget, use BLOCKED rather than guessing.
6. The span SHA identifies the exact prompt-visible bytes that will be reused by the semantic scorer.
7. Do not treat semantic entailment as external-world truth, repository-wide correctness, deployment, adoption, or employer fit.
""".strip()


class HydratedClaimAwareAdaptiveWorkerLoop(ClaimAwareAdaptiveWorkerLoop):
    """Resolve evidence before generation and score against the same prompt-visible bytes."""

    def __init__(
        self,
        *args: Any,
        prompt_evidence_budget_chars: int = 16000,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.prompt_evidence_budget_chars = max(
            1000,
            min(int(prompt_evidence_budget_chars), 100000),
        )
        self._hydrated_span_text_by_pointer: Dict[str, str] = {}
        self._hydration_receipts: List[Dict[str, Any]] = []
        self._hydration_packet_chars = 0

    def _hydrate_evidence(self) -> str:
        """Resolve registry spans once and build one bounded deterministic prompt packet."""

        self._hydrated_span_text_by_pointer = {}
        self._hydration_receipts = []
        self._hydration_packet_chars = 0
        if not self._evidence_registry:
            return ""

        remaining = self.prompt_evidence_budget_chars
        packet_rows: List[Dict[str, Any]] = []
        for source_id in sorted(self._evidence_registry):
            spans = self._evidence_registry[source_id]
            for span_id in sorted(spans):
                pointer = f"{source_id}#{span_id}"
                locator = spans[span_id]
                resolution = self.span_resolver.resolve(pointer, locator)
                receipt = resolution.to_dict(include_text=False)
                receipt["prompt_available"] = False
                receipt["prompt_omission_reason"] = ""

                if resolution.resolved:
                    span_text = resolution.span_text
                    row = {
                        "pointer": pointer,
                        "span_sha256": resolution.span_sha256,
                        "text": span_text,
                    }
                    serialized = json.dumps(
                        row,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    )
                    cost = len(serialized)
                    if cost <= remaining:
                        remaining -= cost
                        receipt["prompt_available"] = True
                        self._hydrated_span_text_by_pointer[pointer] = span_text
                        packet_rows.append(row)
                    else:
                        receipt["prompt_omission_reason"] = "PROMPT_EVIDENCE_BUDGET_EXCEEDED"
                else:
                    receipt["prompt_omission_reason"] = resolution.state
                self._hydration_receipts.append(receipt)

        packet = json.dumps(
            {
                "schema": "glaciereq.make-it-heavy.hydrated-evidence-packet.v1",
                "budget_chars": self.prompt_evidence_budget_chars,
                "prompt_available_count": len(packet_rows),
                "registered_pointer_count": sum(
                    len(spans) for spans in self._evidence_registry.values()
                ),
                "spans": packet_rows,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        self._hydration_packet_chars = len(packet)
        return (
            f"{HYDRATED_EVIDENCE_BEGIN}\n{packet}\n{HYDRATED_EVIDENCE_END}\n\n"
            f"{HYDRATION_CONTRACT}"
        )

    def build_subtasks(
        self,
        mission: str,
        worker_profiles: Sequence[Mapping[str, Any]],
    ) -> List[str]:
        """Inject exact immutable evidence after base claim/pointer contracts are bound."""

        tasks = super().build_subtasks(mission, worker_profiles)
        packet = self._hydrate_evidence()
        if not packet:
            return tasks
        return [f"{task}\n\n{packet}" for task in tasks]

    def evaluate_semantic_support(self, response: str) -> Dict[str, Any]:
        """Score claims against the exact prompt-visible bytes, never a later wider source set."""

        if not self._evidence_registry:
            return super().evaluate_semantic_support(response)

        matches = [
            match
            for raw_line in response.splitlines()
            if (match := OBSERVED_LINE_RE.match(raw_line.strip())) is not None
        ]
        if not matches:
            return {
                "pass": True,
                "semantic_support_status": "NOT_APPLICABLE",
                "failure_class": "NONE",
                "observed_claim_count": 0,
                "resolved_span_count": 0,
                "relation_counts": {},
                "resolutions": self._hydration_receipts,
                "results": [],
                "evidence_hydration_active": True,
                "hydration_packet_chars": self._hydration_packet_chars,
            }

        semantic = evaluate_observed_claims_v2(
            response,
            self._hydrated_span_text_by_pointer,
        )
        observed_count = int(semantic["observed_claim_count"])
        prompt_resolved_count = sum(
            1
            for match in matches
            if match.group("pointer").strip() in self._hydrated_span_text_by_pointer
        )
        resolution_complete = prompt_resolved_count == observed_count
        semantic_pass = bool(
            semantic["semantic_gate_pass"] and resolution_complete
        )
        if not resolution_complete:
            failure_class = "EVIDENCE_PROMPT_AVAILABILITY"
        elif not semantic_pass:
            failure_class = "CLAIM_SEMANTICS"
        else:
            failure_class = "NONE"
        semantic.update(
            {
                "pass": semantic_pass,
                "semantic_support_status": (
                    "SOURCE_SUPPORT_PASS"
                    if semantic_pass
                    else "SOURCE_SUPPORT_FAIL"
                ),
                "failure_class": failure_class,
                "resolved_span_count": prompt_resolved_count,
                "resolution_count": len(self._hydration_receipts),
                "resolutions": self._hydration_receipts,
                "evidence_hydration_active": True,
                "hydration_packet_chars": self._hydration_packet_chars,
                "prompt_available_span_count": len(
                    self._hydrated_span_text_by_pointer
                ),
                "registered_span_count": len(self._hydration_receipts),
                "same_bytes_generation_and_scoring": True,
            }
        )
        return semantic
