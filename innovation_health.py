# SPDX-License-Identifier: Proprietary
"""Infrastructure-health isolation for adaptive worker learning."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Mapping, Optional, Sequence

MODEL_INFERENCE = "model_inference"
INFRA_FAILURE = "infra_failure"
CAPACITY_FAILURE = "capacity_failure"

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


def _redact(value: str, limit: int = 600) -> str:
    text = _SECRET_RE.sub("[REDACTED_CREDENTIAL]", value or "")
    return text[:limit]


def _normalize_error(value: str) -> str:
    """Normalize spacing and secrets, but preserve status codes and distinguishing details."""

    return " ".join(_redact(value, limit=1000).lower().split())


def classify_shared_infrastructure_failure(
    results: Sequence[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return a shared-infrastructure incident only when template scoring is invalid."""

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
    if any(not value for value in normalized):
        return None
    signatures = set(normalized)
    same_signature = len(signatures) == 1
    shared_signature = normalized[0]
    has_provider_marker = any(
        marker in shared_signature for marker in _PROVIDER_MARKERS
    )
    max_elapsed = max(float(item.get("execution_time") or 0.0) for item in results)

    if not same_signature or not has_provider_marker:
        return None

    fingerprint = hashlib.sha256(shared_signature.encode("utf-8")).hexdigest()
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


def render_infrastructure_result(report: Mapping[str, Any]) -> str:
    """Render an infrastructure incident without a misleading model-inference header."""

    return (
        "RESULT CLASSIFICATION: infrastructure_failure\n"
        "REVIEW STATUS: execution_blocked\n\n"
        f"{report['markdown']}"
    )


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
            "model": str(
                result.get("model") or profiles_by_role.get(role, {}).get("model") or ""
            ),
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



def classify_provider_capacity_contention(
    results: Sequence[Mapping[str, Any]],
    *,
    base_url: str,
    current_provider_width: int,
) -> Optional[Dict[str, Any]]:
    """Detect partial timeout contention on a local shared inference plane.

    This is deliberately narrower than shared infrastructure-failure detection. At
    least one worker must have produced reviewable model inference, while at least one
    peer must have failed with a timeout-shaped transport result. Hosted-provider
    timeouts are not automatically classified as capacity contention because their
    cause is not observable from this runtime alone.
    """

    normalized_url = str(base_url or "").lower()
    local_plane = "127.0.0.1" in normalized_url or "localhost" in normalized_url
    if not local_plane or int(current_provider_width) <= 1 or not results:
        return None

    reviewable = [
        item for item in results if str(item.get("status") or "") == MODEL_INFERENCE
    ]
    if not reviewable:
        return None

    failed_ids: list[int] = []
    excerpts: list[str] = []
    for item in results:
        status = str(item.get("status") or "")
        response = str(item.get("response") or item.get("error_message") or "")
        lowered = response.lower()
        timeout_shaped = (
            status == "timeout"
            or "timed out" in lowered
            or "timeout" in lowered
            or ("exceeded" in lowered and "budget" in lowered)
        )
        if status in {"error", "timeout"} and timeout_shaped:
            failed_ids.append(int(item.get("agent_id", -1)))
            excerpts.append(_redact(response))

    if not failed_ids:
        return None

    canonical = "\n".join(sorted(_normalize_error(value) for value in excerpts))
    width = int(current_provider_width)
    return {
        "health_class": "CAPACITY_CONTENTION",
        "failed_worker_ids": failed_ids,
        "failed_worker_count": len(failed_ids),
        "reviewable_worker_count": len(reviewable),
        "current_provider_concurrency_width": width,
        "recommended_provider_concurrency_width": max(1, width // 2),
        "error_fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "error_excerpts": excerpts,
        "template_learning_eligible_for_failed_workers": False,
    }


def mark_capacity_failures(
    results: Sequence[Mapping[str, Any]],
    incident: Mapping[str, Any],
) -> list[Dict[str, Any]]:
    """Quarantine capacity-contended worker results from template learning."""

    failed = {int(value) for value in incident.get("failed_worker_ids", [])}
    marked: list[Dict[str, Any]] = []
    for raw in results:
        item = dict(raw)
        if int(item.get("agent_id", -1)) in failed:
            item["original_status"] = item.get("status")
            item["status"] = CAPACITY_FAILURE
            item["capacity_failure"] = True
            item["template_learning_eligible"] = False
        marked.append(item)
    return marked
