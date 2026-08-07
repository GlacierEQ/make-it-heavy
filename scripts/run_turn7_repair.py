#!/usr/bin/env python3
"""Repair only failed Turn-7 workers, then rescore the combined seven-worker set."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import yaml

from adaptive_orchestrator import AdaptiveTaskOrchestrator
from claim_aware_innovation import ClaimAwareAdaptiveWorkerLoop
from health_memory import HealthAwareAdaptiveSwarmMemory
from run_turn7_github_models import atomic_metrics, load_atoms

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "worker-turn-07"
BASE_CONFIG = ROOT / "turn7_github_models_config.yaml"
BASE_TEMPLATES = ROOT / "templates" / "turn7_atomic_workers.yaml"
MISSION_PATH = ROOT / "missions" / "turn7_atomic_firewall.md"
COOLDOWN_SECONDS = 65
MIN_GROUP_SIZE = 3
MAX_FAILED_PER_GROUP = 3


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def chunks(values: List[str], size: int) -> List[List[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def build_group_roles(failed: List[str], successful: List[str]) -> List[List[str]]:
    groups: List[List[str]] = []
    controls = list(successful)
    for chunk in chunks(failed, MAX_FAILED_PER_GROUP):
        group = list(chunk)
        for role in controls:
            if len(group) >= MIN_GROUP_SIZE:
                break
            if role not in group:
                group.append(role)
        if len(group) < MIN_GROUP_SIZE:
            raise RuntimeError(f"cannot form a bounded repair group for {chunk}")
        groups.append(group)
    return groups


def write_group_files(
    directory: Path,
    roles: List[str],
    selected_model: str,
    group_number: int,
) -> Path:
    base_config = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    base_templates = yaml.safe_load(BASE_TEMPLATES.read_text(encoding="utf-8"))
    role_set = set(roles)

    templates = [
        item for item in base_templates["workers"] if item["role"] in role_set
    ]
    profiles = [
        item for item in base_config["apex_agents"] if item["role"] in role_set
    ]
    if {item["role"] for item in templates} != role_set:
        raise RuntimeError("repair templates do not exactly match requested roles")
    if {item["role"] for item in profiles} != role_set:
        raise RuntimeError("repair profiles do not exactly match requested roles")

    template_path = directory / f"turn7_repair_group_{group_number}_templates.yaml"
    config_path = directory / f"turn7_repair_group_{group_number}_config.yaml"
    template_path.write_text(
        yaml.safe_dump({"version": 1, "workers": templates}, sort_keys=False),
        encoding="utf-8",
    )

    base_config["openrouter"]["model"] = selected_model
    base_config["apex_agents"] = profiles
    for profile in base_config["apex_agents"]:
        profile["model"] = selected_model
    base_config["innovation"]["template_path"] = str(template_path)
    base_config["innovation"]["min_workers"] = MIN_GROUP_SIZE
    base_config["innovation"]["max_workers"] = len(roles)
    base_config["orchestrator"]["parallel_agents"] = len(roles)
    base_config["orchestrator"]["provider_concurrency_width"] = 1
    base_config["agent"]["max_iterations"] = 4
    base_config["memory"]["db_path"] = str(
        directory / f"turn7_repair_group_{group_number}_memory.db"
    )
    config_path.write_text(
        yaml.safe_dump(base_config, sort_keys=False), encoding="utf-8"
    )
    return config_path


def run_group(config_path: Path, mission: str) -> Dict[str, Any]:
    orchestrator = AdaptiveTaskOrchestrator(str(config_path), silent=True)
    error = None
    try:
        orchestrator.orchestrate(mission)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return {
        "error": error,
        "report": dict(orchestrator.last_innovation_report or {}),
        "results": [
            dict(item) for item in getattr(orchestrator, "last_run_results", [])
        ],
    }


def main() -> int:
    raw_path = ARTIFACT / "raw-worker-results.json"
    report_path = ARTIFACT / "worker-report.json"
    probe_path = ARTIFACT / "provider-probe.json"
    for path in (raw_path, report_path, probe_path):
        if not path.exists():
            raise SystemExit(f"required Turn-7 artifact is missing: {path}")

    original_results: List[Dict[str, Any]] = load_json(raw_path)
    original_report: Dict[str, Any] = load_json(report_path)
    provider_probe: Dict[str, Any] = load_json(probe_path)
    selected_model = str(provider_probe.get("selected_model") or "")
    if not selected_model:
        raise SystemExit("provider probe contains no selected model")

    successful_roles = [
        str(item.get("role"))
        for item in original_results
        if item.get("status") == "model_inference"
    ]
    failed_roles = [
        str(item.get("role"))
        for item in original_results
        if item.get("status") != "model_inference"
    ]
    if not failed_roles:
        shutil.copy2(report_path, ARTIFACT / "worker-report-repaired.json")
        print("No failed roles require repair.")
        return 0

    groups = build_group_roles(failed_roles, successful_roles)
    mission = MISSION_PATH.read_text(encoding="utf-8")
    repaired_by_role: Dict[str, Dict[str, Any]] = {}
    group_receipts: List[Dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="turn7-repair-") as temp_dir:
        directory = Path(temp_dir)
        for index, roles in enumerate(groups, start=1):
            config_path = write_group_files(directory, roles, selected_model, index)
            result = run_group(config_path, mission)
            group_receipts.append(
                {
                    "group": index,
                    "roles": roles,
                    "error": result["error"],
                    "health_class": result["report"].get("health_class"),
                    "performance_valid": result["report"].get("performance_valid"),
                    "result_statuses": {
                        str(item.get("role")): item.get("status")
                        for item in result["results"]
                    },
                }
            )
            for item in result["results"]:
                role = str(item.get("role"))
                if role in failed_roles and item.get("status") == "model_inference":
                    repaired_by_role[role] = item
            if index < len(groups):
                time.sleep(COOLDOWN_SECONDS)

    combined_results: List[Dict[str, Any]] = []
    for original in original_results:
        role = str(original.get("role"))
        combined_results.append(repaired_by_role.get(role, original))

    final_evaluated = [
        item for item in combined_results if item.get("status") == "model_inference"
    ]
    unrecovered = [
        str(item.get("role"))
        for item in combined_results
        if item.get("status") != "model_inference"
    ]

    full_config = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    full_profiles = list(full_config["apex_agents"])
    memory_path = ARTIFACT / "turn7_combined_rescore.db"
    if memory_path.exists():
        memory_path.unlink()
    memory = HealthAwareAdaptiveSwarmMemory(str(memory_path))
    loop = ClaimAwareAdaptiveWorkerLoop(
        BASE_TEMPLATES,
        memory,
        min_workers=4,
        max_workers=7,
        target_quality=float(full_config["innovation"]["target_quality"]),
        target_benefit=float(full_config["innovation"]["target_benefit"]),
        claim_gate_min_score=float(full_config["innovation"]["claim_gate_min_score"]),
        claim_gate_quality_cap=float(full_config["innovation"]["claim_gate_quality_cap"]),
    )
    loop.build_subtasks(mission, full_profiles)
    mission_id = memory.start_mission(mission)
    combined_report = loop.evaluate_turn(
        mission_id,
        mission,
        combined_results,
        "Turn 7 combined first-pass plus failed-role repair outputs.",
    )

    atoms = load_atoms(mission)
    atomic_by_role = {
        str(item.get("role")): atomic_metrics(str(item.get("response") or ""), atoms)
        for item in combined_results
    }
    workers: List[Dict[str, Any]] = []
    for score in combined_report.get("scores", []):
        role = str(score.get("role"))
        workers.append(
            {
                "role": role,
                "template_id": score.get("template_id"),
                "runtime_status": score.get("runtime_status"),
                "quality_score": score.get("quality_score"),
                "benefit_score": score.get("benefit_score"),
                "execution_time": score.get("execution_time"),
                "unique_contribution": score.get("unique_contribution"),
                "claim_gate": score.get("claim_gate"),
                "semantic_gate": score.get("semantic_gate"),
                "atomic_metrics": atomic_by_role.get(role, {}),
                "was_repaired": role in repaired_by_role,
            }
        )

    rates = [
        float(worker["atomic_metrics"].get("atomic_source_support_rate", 0.0))
        for worker in workers
        if worker.get("runtime_status") == "model_inference"
    ]
    repaired_receipt = {
        "schema": "glaciereq.make-it-heavy.worker-turn-07-repaired.v1",
        "status": "COMPLETE" if len(final_evaluated) == 7 else "PARTIAL",
        "provider": "github-models",
        "model": selected_model,
        "provider_concurrency_width": 1,
        "repair_cooldown_seconds": COOLDOWN_SECONDS,
        "first_pass_evaluated_workers": int(
            original_report.get("worker_count_evaluated") or 0
        ),
        "failed_roles_first_pass": failed_roles,
        "repair_groups": group_receipts,
        "repair_recovered_roles": sorted(repaired_by_role),
        "repair_unrecovered_roles": unrecovered,
        "worker_count_evaluated": len(final_evaluated),
        "average_quality": combined_report.get("average_quality"),
        "average_benefit": combined_report.get("average_benefit"),
        "average_atomic_source_support_rate": (
            round(sum(rates) / len(rates), 4) if rates else 0.0
        ),
        "next_worker_count": combined_report.get("next_worker_count"),
        "next_roles": combined_report.get("next_roles"),
        "topology_reason": combined_report.get("topology_reason"),
        "workers": workers,
        "adjustments": combined_report.get("adjustments", []),
        "truth_boundary": (
            "Successful first-pass workers were preserved. Only failed roles were eligible "
            "for provider-cooldown repair. Combined quality/benefit was recomputed across "
            "the final seven-role result set; provider/evidence failures remain separate "
            "from worker-template performance."
        ),
    }
    (ARTIFACT / "worker-report-repaired.json").write_text(
        json.dumps(repaired_receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (ARTIFACT / "raw-worker-results-repaired.json").write_text(
        json.dumps(combined_results, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (ARTIFACT / "repair-plan.json").write_text(
        json.dumps(
            {
                "failed_roles_first_pass": failed_roles,
                "groups": groups,
                "cooldown_seconds": COOLDOWN_SECONDS,
                "selected_model": selected_model,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": repaired_receipt["status"],
                "failed_roles_first_pass": failed_roles,
                "recovered_roles": sorted(repaired_by_role),
                "unrecovered_roles": unrecovered,
                "evaluated_workers": len(final_evaluated),
                "average_quality": repaired_receipt["average_quality"],
                "average_benefit": repaired_receipt["average_benefit"],
                "average_atomic_source_support_rate": repaired_receipt[
                    "average_atomic_source_support_rate"
                ],
                "next_worker_count": repaired_receipt["next_worker_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
