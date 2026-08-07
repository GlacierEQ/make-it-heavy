#!/usr/bin/env python3
"""Run Turn 7 on GitHub Models and emit worker-level atomic-evidence telemetry."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping

from adaptive_orchestrator import AdaptiveTaskOrchestrator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "turn7_github_models_config.yaml"
DEFAULT_MISSION = ROOT / "missions" / "turn7_atomic_firewall.md"
DEFAULT_OUTPUT = ROOT / "artifacts" / "worker-turn-07-github-models"

ATOM_RE = re.compile(r"^\[(T7#E\d+)\]\s+(.+?)\s*$")
OBSERVED_RE = re.compile(
    r"^\s*(?:[-*]\s*)?OBSERVED\[(T7#E\d+)\]\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)


def normalize_atomic(text: str) -> str:
    value = text.lower()
    value = re.sub(r"[`'\"“”‘’]", "", value)
    value = re.sub(r"[^a-z0-9_./:-]+", " ", value)
    return " ".join(value.split())


def load_atoms(mission: str) -> Dict[str, List[str]]:
    atoms: Dict[str, List[str]] = {}
    for raw_line in mission.splitlines():
        match = ATOM_RE.match(raw_line.strip())
        if not match:
            continue
        pointer = match.group(1).upper()
        atoms.setdefault(pointer, []).append(match.group(2).strip())
    if not atoms:
        raise ValueError("Turn-7 mission contains no source atoms")
    return atoms


def atomic_metrics(response: str, atoms: Mapping[str, List[str]]) -> Dict[str, Any]:
    observed: List[Dict[str, Any]] = []
    supported = 0
    invalid_pointer_count = 0
    for raw_line in response.splitlines():
        match = OBSERVED_RE.match(raw_line.strip())
        if not match:
            continue
        pointer = match.group(1).upper()
        claim = match.group(2).strip()
        claim_value = normalize_atomic(claim)
        candidates = [normalize_atomic(value) for value in atoms.get(pointer, [])]
        pointer_valid = bool(candidates)
        claim_supported = bool(
            pointer_valid
            and claim_value
            and len(claim_value.split()) >= 4
            and any(claim_value in candidate for candidate in candidates)
        )
        supported += int(claim_supported)
        invalid_pointer_count += int(not pointer_valid)
        observed.append(
            {
                "pointer": pointer,
                "claim": claim,
                "pointer_valid": pointer_valid,
                "atom_supported": claim_supported,
            }
        )
    count = len(observed)
    return {
        "observed_claim_count": count,
        "atom_supported_claim_count": supported,
        "invalid_pointer_count": invalid_pointer_count,
        "atomic_source_support_rate": round(supported / count, 4) if count else 0.0,
        "observed_claims": observed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--mission", type=Path, default=DEFAULT_MISSION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    config_path = args.config.resolve()
    mission_path = args.mission.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    mission = mission_path.read_text(encoding="utf-8")
    atoms = load_atoms(mission)
    orchestrator = AdaptiveTaskOrchestrator(str(config_path), silent=True)

    execution_error = None
    final_output = ""
    try:
        final_output = orchestrator.orchestrate(mission)
    except Exception as exc:  # preserve a receipt before propagating failure status
        execution_error = f"{type(exc).__name__}: {exc}"

    report = dict(orchestrator.last_innovation_report or {})
    results = [dict(item) for item in getattr(orchestrator, "last_run_results", [])]
    metrics_by_role: Dict[str, Dict[str, Any]] = {}
    for result in results:
        role = str(result.get("role") or "unknown")
        metrics_by_role[role] = atomic_metrics(
            str(result.get("response") or ""), atoms
        )

    workers: List[Dict[str, Any]] = []
    for score in report.get("scores", []):
        role = str(score.get("role") or "unknown")
        workers.append(
            {
                "role": role,
                "template_id": score.get("template_id"),
                "model": score.get("model"),
                "runtime_status": score.get("runtime_status"),
                "quality_score": score.get("quality_score"),
                "benefit_score": score.get("benefit_score"),
                "execution_time": score.get("execution_time"),
                "unique_contribution": score.get("unique_contribution"),
                "claim_gate": score.get("claim_gate"),
                "semantic_gate": score.get("semantic_gate"),
                "atomic_metrics": metrics_by_role.get(role, {}),
            }
        )

    evaluated = [
        worker for worker in workers if worker.get("runtime_status") == "model_inference"
    ]
    atomic_rates = [
        float(worker.get("atomic_metrics", {}).get("atomic_source_support_rate", 0.0))
        for worker in evaluated
    ]
    status = "COMPLETE" if len(evaluated) == 7 else "BLOCKED_OR_PARTIAL"
    if execution_error:
        status = "ERROR"

    receipt = {
        "schema": "glaciereq.make-it-heavy.worker-turn-07-github-models.v1",
        "status": status,
        "provider": "github-models",
        "model": "openai/gpt-4.1",
        "provider_concurrency_width": 1,
        "source_repository": "GlacierEQ/make-it-heavy",
        "source_commit": "d290b022ffc709abacd4672aa3f7527ae22b692f",
        "worker_count_requested": 7,
        "worker_count_evaluated": len(evaluated),
        "health_class": report.get("health_class"),
        "performance_valid": report.get("performance_valid"),
        "average_quality": report.get("average_quality"),
        "average_benefit": report.get("average_benefit"),
        "average_atomic_source_support_rate": (
            round(sum(atomic_rates) / len(atomic_rates), 4) if atomic_rates else 0.0
        ),
        "next_worker_count": report.get("next_worker_count"),
        "next_roles": report.get("next_roles"),
        "topology_reason": report.get("topology_reason"),
        "workers": workers,
        "adjustments": report.get("adjustments", []),
        "execution_error": execution_error,
        "truth_boundary": (
            "Native worker quality/benefit scores measure output-contract performance. "
            "Atomic support measures literal source-atom discipline. Neither alone is an "
            "external-world truth verdict. Provider/evidence failures are excluded from "
            "worker-template learning by the merged Turn-6 health contract."
        ),
    }

    (output_dir / "worker-report.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "final-output.md").write_text(final_output, encoding="utf-8")
    (output_dir / "native-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "raw-worker-results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": status,
                "evaluated_workers": len(evaluated),
                "average_quality": receipt["average_quality"],
                "average_benefit": receipt["average_benefit"],
                "average_atomic_source_support_rate": receipt[
                    "average_atomic_source_support_rate"
                ],
                "next_worker_count": receipt["next_worker_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
