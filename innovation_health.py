# SPDX-License-Identifier: Proprietary
"""Infrastructure-health isolation for adaptive worker learning."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Mapping, Optional, Sequence

MODEL_INFERENCE = "model_inference"
INFRA_FAILURE = "infra_failure"

_PROVIDER_MARKERS = (
    "openrouter returned http",
    "request failed",
    "transport failure",
    "api key",
    "api_key",
    "base_url",
    "unauthorized",
    "forbidden",
    "rate limit",
    "http 401",
    "http 403",
    "http 404",
    "http 410",
    "http 429",
    "http 5",
    "model not found",
    "provider",
    "llmcallerror",
    "circuit breaker",
)
_SECRET_RE = re.compile(
    r"(?i)(?:bearer\s+)[A-Za-z0-9._~+/=-]+|sk-[A-Za-z0-9_-]+"
)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


def _redact(value: str, limit: int = 600) -> str:
    text = _SECRET_RE.sub("[REDACTED_CREDENTIAL]", value or "")
    return text[:limit]


def _normalize_error(value: str) -> str:
    text = _redact(value, limit=1000).lower()
    text = _NUMBER_RE.sub("#", text)
    return " ".join(text.split())


def classify_shared_infrastructure_failure(
    results: Sequence[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return a shared-infrastructure incident only when template scoring is invalid.

    A turn is classified as infrastructure failure when every worker failed before
    producing reviewable model inference and the errors either share one normalized
    signature or are uniformly fast provider/transport failures. Mixed worker outcomes
    remain eligible for normal per-worker adaptation.
    """

    if not results:
        return None
    if any(str(item.get("status")) == MODEL_INFERENCE for item in results):
        return None
    if any(str(item.get("status")) != "error" for item in results):
        return None

    normalized = [
        _normalize_error(str(item.get("response") or item.get("error_message") or ""))
        for item in results
    ]
    signatures = {value for value in normalized if value}
    combined = "\n".join(normalized)
    has_provider_marker = any(marker in combined for marker in _PROVIDER_MARKERS)
    max_elapsed = max(float(item.get("execution_time") or 0.0) for item in results)
    same_signature = len(signatures) == 1
    uniformly_fast = max_elapsed <= 5.0

    if not has_provider_marker or not (same_signature or uniformly_fast):
        return None

    canonical = next(iter(signatures), "shared provider failure")
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "health_class": "INFRA_FAILURE",
        "failed_worker_count": len(results),
        "shared_error_fingerprint": fingerprint,
        "shared_error_excerpt": _redact(
            str(results[0].get("response") or results[0].get("error_message") or "")
        ),
        "max_execution_time": round(max_elapsed, 3),
        "template_learning_eligible": False,
    }


def build_infrastructure_report(
    mission_id: int,
    mission: str,
    results: Sequence[Mapping[str, Any]],
    innovation: Any,
    worker_profiles: Sequence[Mapping[str, Any]],
    incident: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build a persistent incident report without mutating worker templates."""

    profiles_by_role = {str(item["role"]): item for item in worker_profiles}
    scores = []
    adjustments = []

    for result in results:
        role = str(result.get("role") or "unknown")
        template = innovation.template_for_role(role)
        template_id = template.template_id if template is not None else f"{role}.unknown"
        template_version = template.version if template is not None else "unknown"
        response = str(result.get("response") or "")
        scorecard = {
            "worker_id": int(result.get("agent_id", -1)),
            "template_id": template_id,
            "template_version": template_version,
            "role": role,
            "model": str(result.get("model") or profiles_by_role.get(role, {}).get("model") or ""),
            "runtime_status": INFRA_FAILURE,
            "quality_score": 0.0,
            "benefit_score": 0.0,
            "execution_time": round(float(result.get("execution_time") or 0.0), 3),
            "dimensions": {
                "completion": 0.0,
                "evidence": 0.0,
                "specificity": 0.0,
                "novelty": 0.0,
                "actionability": 0.0,
                "truth": 0.0,
                "efficiency": 0.0,
            },
            "unique_contribution": 0.0,
            "response_chars": len(response),
            "template_learning_eligible": False,
            "error_class": "shared_inference_plane",
            "error_excerpt": _redact(response),
            "error_fingerprint": incident["shared_error_fingerprint"],
        }
        scores.append(scorecard)
        adjustments.append(
            {
                "role": role,
                "template_id": template_id,
                "action": "HOLD_TEMPLATE_INFRA",
                "instruction": (
                    "Do not mutate this worker template from this turn. Repair the shared "
                    "inference/runtime plane and rerun the same worker contract."
                ),
                "quality_before": None,
                "quality_after": 0.0,
                "benefit_before": None,
                "benefit_after": 0.0,
            }
        )

    next_roles = [str(profile["role"]) for profile in worker_profiles]
    reason = "hold topology; shared infrastructure failure invalidated template scoring"
    markdown = "\n".join(
        [
            "## WORKER INNOVATION REPORT",
            "",
            "**Turn health:** INFRA_FAILURE. Worker-template performance was **not scored**.",
            "The shared inference/runtime plane failed before any worker produced reviewable output.",
            "",
            "| Worker | Runtime | Template learning | Adjust next |",
            "|---|---:|---|---|",
            *[
                (
                    f"| {score['role']} | {score['execution_time']:.3f}s | excluded | "
                    "HOLD_TEMPLATE_INFRA |"
                )
                for score in scores
            ],
            "",
            f"**Infrastructure fingerprint:** `{incident['shared_error_fingerprint']}`",
            "",
            "**Topology decision:** hold worker count and roles; repair the provider plane, then rerun the same contracts.",
            "",
            "**Quality boundary:** zeroes are storage sentinels only. They are excluded from template learning and performance averages.",
        ]
    )
    return {
        "schema": "glaciereq.make-it-heavy.worker-turn-report.v2",
        "mission_id": int(mission_id),
        "mission": mission,
        "health_class": "INFRA_FAILURE",
        "performance_valid": False,
        "current_worker_count": len(results),
        "next_worker_count": len(next_roles),
        "next_roles": next_roles,
        "scores": scores,
        "adjustments": adjustments,
        "average_quality": None,
        "average_benefit": None,
        "silent_worker_omissions": 0,
        "topology_reason": reason,
        "infrastructure": dict(incident),
        "markdown": markdown,
    }
