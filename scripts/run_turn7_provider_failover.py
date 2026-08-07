#!/usr/bin/env python3
"""Run Turn 7 using a dynamically selected GitHub Models provider candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from adaptive_orchestrator import AdaptiveTaskOrchestrator
from run_turn7_github_models import atomic_metrics, load_atoms

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "turn7_runtime_config.yaml"
DEFAULT_MISSION = ROOT / "missions" / "turn7_atomic_firewall.md"
DEFAULT_OUTPUT = ROOT / "artifacts" / "worker-turn-07-github-models"


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

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    selected_model = str(config["openrouter"]["model"])
    mission = mission_path.read_text(encoding="utf-8")
    atoms = load_atoms(mission)
    orchestrator = AdaptiveTaskOrchestrator(str(config_path), silent=True)

    execution_error = None
    final_output = ""
    try:
        final_output = orchestrator.orchestrate(mission)
    except Exception as exc:
        execution_error = f"{type(exc).__name__}: {exc}"

    report = dict(orchestrator.last_innovation_report or {})
    results = [dict(item) for item in getattr(orchestrator, "last_run_results", [])]
    metrics_by_role: Dict[str, Dict[str, Any]] = {
        str(item.get("role") or "unknown"): atomic_metrics(
            str(item.get("response") or ""), atoms
        )
        for item in results
    }

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

    evaluated = [w for w in workers if w.get("runtime_status") == "model_inference"]
    rates = [
        float(w.get("atomic_metrics", {}).get("atomic_source_support_rate", 0.0))
        for w in evaluated
    ]
    status = "COMPLETE" if len(evaluated) == 7 else "BLOCKED_OR_PARTIAL"
    if execution_error:
        status = "ERROR"

    receipt = {
        "schema": "glaciereq.make-it-heavy.worker-turn-07-provider-failover.v1",
        "status": status,
        "provider": "github-models",
        "model": selected_model,
        "provider_concurrency_width": int(
            config["orchestrator"]["provider_concurrency_width"]
        ),
        "source_repository": "GlacierEQ/make-it-heavy",
        "source_commit": "d290b022ffc709abacd4672aa3f7527ae22b692f",
        "worker_count_requested": 7,
        "worker_count_evaluated": len(evaluated),
        "health_class": report.get("health_class"),
        "performance_valid": report.get("performance_valid"),
        "average_quality": report.get("average_quality"),
        "average_benefit": report.get("average_benefit"),
        "average_atomic_source_support_rate": (
            round(sum(rates) / len(rates), 4) if rates else 0.0
        ),
        "next_worker_count": report.get("next_worker_count"),
        "next_roles": report.get("next_roles"),
        "topology_reason": report.get("topology_reason"),
        "workers": workers,
        "adjustments": report.get("adjustments", []),
        "execution_error": execution_error,
        "truth_boundary": (
            "Worker quality and benefit measure output-contract performance. Atomic "
            "support measures literal source-atom discipline. Neither alone proves "
            "external-world truth. Provider and evidence failures remain excluded from "
            "worker-template learning under the merged Turn-6 health contract."
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
                "model": selected_model,
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
