#!/usr/bin/env python3
"""One-shot hardening and Worker Baseline Zero execution helper."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"expected patch anchor missing: {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def harden_runtime() -> None:
    replace_once(
        "innovation_loop.py",
        'SPECIFICITY_RE = re.compile(\n    r"(?:\\b\\d+(?:\\.\\d+)?%?\\b|`[^`]+`|\\b[A-Z][A-Z0-9_ -]{3,}\\b|"\n    r"\\b[\\w.-]+/[\\w./-]+\\b)"\n)\n',
        'SPECIFICITY_RE = re.compile(\n    r"(?:\\b\\d+(?:\\.\\d+)?%?\\b|`[^`]+`|\\b[A-Z][A-Z0-9_ -]{3,}\\b|"\n    r"\\b[\\w.-]+/[\\w./-]+\\b)"\n)\nMANDATORY_ROLES = ("source_mapper", "adversarial_breaker", "proof_engineer")\n',
    )
    replace_once(
        "innovation_loop.py",
        '        max_workers: int = 12,\n',
        '        max_workers: int = 8,\n',
    )
    replace_once(
        "innovation_loop.py",
        '''        self.min_workers = int(min_workers)\n        self.max_workers = int(max_workers)\n        self.target_quality = float(target_quality)\n        self.target_benefit = float(target_benefit)\n        if not 1 <= self.min_workers <= self.max_workers <= 16:\n            raise InnovationConfigurationError(\n                "innovation worker bounds must satisfy 1 <= min <= max <= 16"\n            )\n        self.templates = self._load_templates(self.template_path)\n        self.templates_by_role = {template.role: template for template in self.templates}\n''',
        '''        requested_min = int(min_workers)\n        requested_max = int(max_workers)\n        self.target_quality = float(target_quality)\n        self.target_benefit = float(target_benefit)\n        if not 1 <= requested_min <= requested_max <= 16:\n            raise InnovationConfigurationError(\n                "innovation worker bounds must satisfy 1 <= min <= max <= 16"\n            )\n        self.templates = self._load_templates(self.template_path)\n        if not self.templates:\n            raise InnovationConfigurationError("no innovation worker templates configured")\n        self.max_workers = min(requested_max, len(self.templates))\n        self.min_workers = min(requested_min, self.max_workers)\n        if self.min_workers < len(MANDATORY_ROLES):\n            raise InnovationConfigurationError(\n                "min_workers must preserve source, adversarial, and proof coverage"\n            )\n        self.templates_by_role = {template.role: template for template in self.templates}\n''',
    )
    replace_once(
        "innovation_loop.py",
        '''            numeric_weights = {key: float(value) for key, value in weights.items()}\n            if not math.isclose(sum(numeric_weights.values()), 1.0, abs_tol=1e-6):\n                raise InnovationConfigurationError(f"{role}: weights must sum to 1.0")\n''',
        '''            numeric_weights = {key: float(value) for key, value in weights.items()}\n            if any(\n                not math.isfinite(value) or value < 0\n                for value in numeric_weights.values()\n            ):\n                raise InnovationConfigurationError(\n                    f"{role}: weights must be finite and non-negative"\n                )\n            if not math.isclose(sum(numeric_weights.values()), 1.0, abs_tol=1e-6):\n                raise InnovationConfigurationError(f"{role}: weights must sum to 1.0")\n''',
    )
    replace_once(
        "innovation_loop.py",
        '            and average_benefit >= 0.70\n',
        '            and average_benefit >= self.target_benefit\n',
    )
    replace_once(
        "innovation_loop.py",
        '''        active_roles = [str(score["role"]) for score in scores]\n        ranked = sorted(\n''',
        '''        ranked = sorted(\n''',
    )
    replace_once(
        "innovation_loop.py",
        '''        selected: List[str] = []\n        for role in mandatory_order:\n            if role in active_roles and role not in selected and len(selected) < next_count:\n                selected.append(role)\n''',
        '''        next_count = max(next_count, len(MANDATORY_ROLES))\n        selected: List[str] = []\n        for role in mandatory_order:\n            if role not in self.templates_by_role:\n                raise InnovationConfigurationError(\n                    f"mandatory innovation role is not configured: {role}"\n                )\n            if role not in selected and len(selected) < next_count:\n                selected.append(role)\n''',
    )
    replace_once(
        "innovation_loop.py",
        '''        templates = self.active_templates(\n            [{"role": str(result["role"])} for result in results]\n        )\n''',
        '''        if not results:\n            raise InnovationConfigurationError(\n                "evaluate_turn requires at least one worker result"\n            )\n        templates = self.active_templates(\n            [{"role": str(result["role"])} for result in results]\n        )\n''',
    )
    replace_once(
        "innovation_loop.py",
        '''        if self.memory is not None:\n            for score in scores:\n                if hasattr(self.memory, "log_worker_score"):\n                    self.memory.log_worker_score(mission_id, score)\n            for adjustment in adjustments:\n                if hasattr(self.memory, "log_template_adjustment"):\n                    self.memory.log_template_adjustment(mission_id, adjustment)\n            if hasattr(self.memory, "log_topology_adjustment"):\n                self.memory.log_topology_adjustment(\n                    mission_id,\n                    len(scores),\n                    next_count,\n                    topology_reason,\n                    report,\n                )\n''',
        '''        if self.memory is not None:\n            if hasattr(self.memory, "persist_adaptive_turn"):\n                self.memory.persist_adaptive_turn(\n                    mission_id,\n                    scores,\n                    adjustments,\n                    len(scores),\n                    next_count,\n                    topology_reason,\n                    report,\n                )\n            else:\n                for score in scores:\n                    if hasattr(self.memory, "log_worker_score"):\n                        self.memory.log_worker_score(mission_id, score)\n                for adjustment in adjustments:\n                    if hasattr(self.memory, "log_template_adjustment"):\n                        self.memory.log_template_adjustment(mission_id, adjustment)\n                if hasattr(self.memory, "log_topology_adjustment"):\n                    self.memory.log_topology_adjustment(\n                        mission_id,\n                        len(scores),\n                        next_count,\n                        topology_reason,\n                        report,\n                    )\n''',
    )

    memory_path = ROOT / "innovation_memory.py"
    memory_text = memory_path.read_text(encoding="utf-8")
    anchor = '''    def log_worker_score(\n        self,\n        mission_id: int,\n        scorecard: Dict[str, Any],\n    ) -> None:\n'''
    if anchor not in memory_text:
        raise RuntimeError("innovation_memory.py insertion anchor missing")
    persist_method = '''    @staticmethod\n    def _assert_mission_exists(conn: sqlite3.Connection, mission_id: int) -> None:\n        row = conn.execute(\n            "SELECT 1 FROM missions WHERE id = ?", (int(mission_id),)\n        ).fetchone()\n        if row is None:\n            raise ValueError(f"unknown mission_id: {mission_id}")\n\n    def persist_adaptive_turn(\n        self,\n        mission_id: int,\n        scores: List[Dict[str, Any]],\n        adjustments: List[Dict[str, Any]],\n        current_worker_count: int,\n        next_worker_count: int,\n        reason: str,\n        report: Dict[str, Any],\n    ) -> None:\n        """Persist the complete adaptive turn in one transaction."""\n\n        created_at = time.time()\n        with self._conn() as conn:\n            self._assert_mission_exists(conn, mission_id)\n            for scorecard in scores:\n                conn.execute(\n                    """\n                    INSERT INTO worker_scores (\n                        mission_id, worker_id, template_id, template_version,\n                        agent_role, model, runtime_status, quality_score,\n                        benefit_score, execution_time, scorecard_json, created_at\n                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n                    """,\n                    (\n                        mission_id, int(scorecard["worker_id"]),\n                        scorecard["template_id"], scorecard["template_version"],\n                        scorecard["role"], scorecard.get("model", ""),\n                        scorecard["runtime_status"],\n                        float(scorecard["quality_score"]),\n                        float(scorecard["benefit_score"]),\n                        float(scorecard["execution_time"]),\n                        json.dumps(scorecard, sort_keys=True), created_at,\n                    ),\n                )\n            for adjustment in adjustments:\n                conn.execute(\n                    """\n                    INSERT INTO template_adjustments (\n                        mission_id, agent_role, template_id, action, instruction,\n                        quality_before, quality_after, benefit_before,\n                        benefit_after, created_at\n                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n                    """,\n                    (\n                        mission_id, adjustment["role"], adjustment["template_id"],\n                        adjustment["action"], adjustment["instruction"],\n                        adjustment.get("quality_before"),\n                        float(adjustment["quality_after"]),\n                        adjustment.get("benefit_before"),\n                        float(adjustment["benefit_after"]), created_at,\n                    ),\n                )\n            conn.execute(\n                """\n                INSERT INTO topology_adjustments (\n                    mission_id, current_worker_count, next_worker_count,\n                    reason, report_json, created_at\n                ) VALUES (?, ?, ?, ?, ?, ?)\n                """,\n                (\n                    mission_id, int(current_worker_count), int(next_worker_count),\n                    reason, json.dumps(report, sort_keys=True), created_at,\n                ),\n            )\n\n'''
    memory_text = memory_text.replace(anchor, persist_method + anchor, 1)
    memory_text = memory_text.replace(
        'import json\nimport time\n',
        'import json\nimport sqlite3\nimport time\n',
        1,
    )
    memory_text = memory_text.replace(
        'ORDER BY created_at DESC\n                LIMIT ?',
        'ORDER BY id DESC\n                LIMIT ?',
        1,
    )
    memory_text = memory_text.replace(
        '''            adjustments = conn.execute(\n                "SELECT COUNT(*) AS count FROM template_adjustments"\n            ).fetchone()["count"]\n''',
        '''            adjustments = conn.execute(\n                "SELECT COUNT(*) AS count FROM template_adjustments"\n            ).fetchone()["count"]\n            topology_adjustments = conn.execute(\n                "SELECT COUNT(*) AS count FROM topology_adjustments"\n            ).fetchone()["count"]\n''',
        1,
    )
    memory_text = memory_text.replace(
        '''            "total_template_adjustments": adjustments,\n            "avg_worker_quality": round(average_quality, 2),\n''',
        '''            "total_template_adjustments": adjustments,\n            "total_topology_adjustments": topology_adjustments,\n            "avg_worker_quality": round(average_quality, 2),\n''',
        1,
    )
    memory_path.write_text(memory_text, encoding="utf-8")

    (ROOT / "adaptive_orchestrator.py").write_text(
        '''# SPDX-License-Identifier: Proprietary\n"""Innovation-stage orchestrator with per-turn worker scoring and adaptation."""\n\nfrom __future__ import annotations\n\nfrom pathlib import Path\nfrom typing import Any, Dict, List\n\nfrom innovation_loop import AdaptiveWorkerLoop, InnovationConfigurationError\nfrom innovation_memory import AdaptiveSwarmMemory\nfrom orchestrator import TaskOrchestrator\n\n\nclass AdaptiveTaskOrchestrator(TaskOrchestrator):\n    """Run Make-It-Heavy through versioned templates and a measured next-turn loop."""\n\n    def __init__(\n        self,\n        config_path: str = "innovation_config.yaml",\n        silent: bool = False,\n    ) -> None:\n        super().__init__(config_path=config_path, silent=silent)\n        innovation = self.config.get("innovation", {})\n        memory_path = self.config.get("memory", {}).get("db_path", ".swarm_memory.db")\n        self.memory = AdaptiveSwarmMemory(memory_path)\n        template_path = Path(config_path).resolve().parent / innovation.get(\n            "template_path",\n            "templates/innovation_workers.yaml",\n        )\n        self.innovation = AdaptiveWorkerLoop(\n            template_path,\n            self.memory,\n            min_workers=int(innovation.get("min_workers", 4)),\n            max_workers=int(innovation.get("max_workers", 8)),\n            target_quality=float(innovation.get("target_quality", 78.0)),\n            target_benefit=float(innovation.get("target_benefit", 0.60)),\n        )\n        self.all_worker_profiles: Dict[str, Dict[str, Any]] = {\n            str(profile["role"]): dict(profile)\n            for profile in self.config["apex_agents"]\n        }\n        profile_roles = set(self.all_worker_profiles)\n        template_roles = set(self.innovation.templates_by_role)\n        if profile_roles != template_roles:\n            missing_profiles = sorted(template_roles - profile_roles)\n            missing_templates = sorted(profile_roles - template_roles)\n            raise InnovationConfigurationError(\n                "profile/template role mismatch: "\n                f"missing_profiles={missing_profiles}, "\n                f"missing_templates={missing_templates}"\n            )\n        if not self.innovation.min_workers <= self.num_agents <= self.innovation.max_workers:\n            raise InnovationConfigurationError(\n                "initial parallel_agents is outside the adaptive worker bounds"\n            )\n        self.last_innovation_report: Dict[str, Any] = {}\n        persisted = self.memory.get_last_topology_adjustment()\n        if persisted:\n            roles = persisted.get("report", {}).get("next_roles")\n            if isinstance(roles, list) and roles:\n                self._activate_next_roles([str(role) for role in roles])\n\n    def decompose_task(self, user_input: str, num_agents: int) -> List[str]:\n        """Use exact worker templates instead of a generic decomposition model."""\n\n        profiles = self.worker_profiles[:num_agents]\n        return self.innovation.build_subtasks(user_input, profiles)\n\n    def _activate_next_roles(self, roles: List[str]) -> None:\n        if len(roles) != len(set(roles)):\n            raise InnovationConfigurationError("next topology contains duplicate roles")\n        if not self.innovation.min_workers <= len(roles) <= self.innovation.max_workers:\n            raise InnovationConfigurationError(\n                "next topology worker count is outside adaptive bounds"\n            )\n        unknown = [role for role in roles if role not in self.all_worker_profiles]\n        if unknown:\n            raise InnovationConfigurationError(\n                f"next topology contains unknown roles: {unknown}"\n            )\n        selected = [self.all_worker_profiles[role] for role in roles]\n        self.worker_profiles = selected\n        self.num_agents = len(selected)\n\n    def orchestrate(self, user_input: str) -> str:\n        """Execute, score, report, persist, and tune the next turn."""\n\n        self._current_mission_id = self.memory.start_mission(user_input)\n        try:\n            synthesis = super().orchestrate(user_input)\n            report = self.innovation.evaluate_turn(\n                self._current_mission_id,\n                user_input,\n                self.last_run_results,\n                synthesis,\n            )\n            self.last_innovation_report = report\n            final = f"{synthesis}\\n\\n{report['markdown']}"\n            self.memory.complete_mission(\n                self._current_mission_id,\n                final,\n                status="completed",\n            )\n            self._activate_next_roles(report["next_roles"])\n            return final\n        except Exception:\n            self.memory.complete_mission(\n                self._current_mission_id,\n                "Innovation turn failed before completion.",\n                status="failed",\n            )\n            raise\n''',
        encoding="utf-8",
    )

    (ROOT / "make_it_heavy_innovation.py").write_text(
        '''# SPDX-License-Identifier: Proprietary\n"""Interactive innovation-stage Make-It-Heavy runtime."""\n\nfrom __future__ import annotations\n\nimport argparse\nimport json\nimport logging\nimport sys\n\nfrom adaptive_orchestrator import AdaptiveTaskOrchestrator\n\nlogging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")\nEXIT_COMMANDS = frozenset({"quit", "exit", "bye"})\n\n\ndef emit_failure(exc: Exception) -> int:\n    print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)\n    return 1\n\n\ndef run_once(orchestrator: AdaptiveTaskOrchestrator, query: str) -> int:\n    try:\n        print(orchestrator.orchestrate(query))\n        return 0\n    except Exception as exc:\n        return emit_failure(exc)\n\n\ndef interactive(orchestrator: AdaptiveTaskOrchestrator) -> int:\n    print("Make-It-Heavy — Adaptive Worker Innovation Loop")\n    print(\n        f"Initial topology: {orchestrator.num_agents} workers; "\n        "every completed turn scores quality, benefit, and next topology."\n    )\n    while True:\n        try:\n            query = input("\\nMission: ").strip()\n        except (EOFError, KeyboardInterrupt):\n            print()\n            return 0\n        if not query:\n            continue\n        if query.lower() in EXIT_COMMANDS:\n            return 0\n        status = run_once(orchestrator, query)\n        if status:\n            print("The turn failed; the previous topology remains active.", file=sys.stderr)\n\n\ndef main() -> int:\n    parser = argparse.ArgumentParser(\n        description="Run the adaptive innovation-stage Make-It-Heavy worker loop."\n    )\n    parser.add_argument("query", nargs="*")\n    parser.add_argument("--config", default="innovation_config.yaml")\n    args = parser.parse_args()\n    try:\n        orchestrator = AdaptiveTaskOrchestrator(args.config)\n    except Exception as exc:\n        return emit_failure(exc)\n    if args.query:\n        return run_once(orchestrator, " ".join(args.query))\n    return interactive(orchestrator)\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n''',
        encoding="utf-8",
    )

    config_path = ROOT / "innovation_config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["tools"]["allowlist"] = [
        tool for tool in config["tools"]["allowlist"] if tool != "smithery_mcp"
    ]
    for profile in config["apex_agents"]:
        profile["allowed_tools"] = [
            tool for tool in profile["allowed_tools"] if tool != "smithery_mcp"
        ]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    workflow = ROOT / ".github/workflows/adaptive-worker-integrity.yml"
    workflow.write_text(
        '''name: Adaptive Worker Integrity\n\non:\n  push:\n    branches:\n      - main\n      - innovation/adaptive-worker-loop-2026-08-05\n  pull_request:\n\npermissions:\n  contents: read\n\njobs:\n  integrity:\n    runs-on: ubuntu-latest\n    timeout-minutes: 10\n    strategy:\n      fail-fast: false\n      matrix:\n        python-version: ['3.9', '3.10', '3.11', '3.12', '3.13']\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: ${{ matrix.python-version }}\n          cache: pip\n      - name: Install declared dependencies\n        run: python -m pip install -r requirements.txt\n      - name: Compile every Python module\n        run: python -m compileall -q .\n      - name: Run complete test suite\n        run: python -m unittest discover -s tests -v\n      - name: Verify innovation configuration boundaries\n        run: |\n          python - <<'PY'\n          from pathlib import Path\n          import yaml\n\n          with Path('innovation_config.yaml').open(encoding='utf-8') as handle:\n              config = yaml.safe_load(handle)\n          assert config['openrouter']['api_key'] == ''\n          assert config['smithery']['api_key'] == ''\n          assert config['orchestrator']['parallel_agents'] == 8\n          assert len(config['apex_agents']) == 8\n          assert all(\n              'smithery_mcp' not in profile['allowed_tools']\n              for profile in config['apex_agents']\n          )\n          PY\n''',
        encoding="utf-8",
    )

    docs = ROOT / "docs/ADAPTIVE_WORKER_INNOVATION_LOOP.md"
    if docs.exists():
        text = docs.read_text(encoding="utf-8").replace(
            "for every template", "for every active worker template"
        )
        docs.write_text(text, encoding="utf-8")

    templates = ROOT / "templates/innovation_workers.yaml"
    text = templates.read_text(encoding="utf-8").replace(
        "Attack assumptions, evidence, architecture, incentives, and execution.",
        "Run an independent pre-mortem against assumptions, evidence, architecture, incentives, and execution.",
        1,
    )
    templates.write_text(text, encoding="utf-8")

    hardening_tests = ROOT / "tests/test_adaptive_hardening.py"
    hardening_tests.write_text(
        '''"""Hardening regressions for the adaptive worker runtime."""\n\nimport tempfile\nimport unittest\nfrom pathlib import Path\n\nfrom adaptive_orchestrator import AdaptiveTaskOrchestrator\nfrom innovation_loop import AdaptiveWorkerLoop, InnovationConfigurationError, MANDATORY_ROLES\nfrom innovation_memory import AdaptiveSwarmMemory\n\nROOT = Path(__file__).resolve().parents[1]\n\n\nclass AdaptiveHardeningTests(unittest.TestCase):\n    def test_empty_results_fail_explicitly(self):\n        memory = AdaptiveSwarmMemory(":memory:")\n        loop = AdaptiveWorkerLoop(ROOT / "templates/innovation_workers.yaml", memory)\n        with self.assertRaisesRegex(InnovationConfigurationError, "at least one"):\n            loop.evaluate_turn(1, "mission", [], "")\n\n    def test_max_workers_clamps_to_template_count(self):\n        loop = AdaptiveWorkerLoop(\n            ROOT / "templates/innovation_workers.yaml",\n            max_workers=16,\n        )\n        self.assertEqual(loop.max_workers, len(loop.templates))\n\n    def test_mandatory_roles_are_restored(self):\n        loop = AdaptiveWorkerLoop(ROOT / "templates/innovation_workers.yaml")\n        scores = [\n            {\n                "role": "systems_architect",\n                "quality_score": 90.0,\n                "benefit_score": 0.9,\n                "runtime_status": "model_inference",\n            }\n        ]\n        roles = loop._next_roles(scores, 4)\n        for role in MANDATORY_ROLES:\n            self.assertIn(role, roles)\n\n    def test_atomic_turn_rejects_unknown_mission(self):\n        with tempfile.TemporaryDirectory() as directory:\n            memory = AdaptiveSwarmMemory(str(Path(directory) / "memory.db"))\n            with self.assertRaisesRegex(ValueError, "unknown mission_id"):\n                memory.persist_adaptive_turn(999, [], [], 0, 0, "none", {})\n            stats = memory.get_adaptive_stats()\n            self.assertEqual(stats["total_worker_scores"], 0)\n            self.assertEqual(stats["total_template_adjustments"], 0)\n            self.assertEqual(stats["total_topology_adjustments"], 0)\n\n    def test_persisted_topology_restores_across_processes(self):\n        with tempfile.TemporaryDirectory() as directory:\n            config = yaml.safe_load((ROOT / "innovation_config.yaml").read_text())\n            config["openrouter"]["api_key"] = "test"\n            config["memory"]["db_path"] = str(Path(directory) / "memory.db")\n            config_path = Path(directory) / "config.yaml"\n            config_path.write_text(yaml.safe_dump(config, sort_keys=False))\n            # Constructor validation is covered without making network calls.\n            first = AdaptiveTaskOrchestrator(str(config_path), silent=True)\n            mission_id = first.memory.start_mission("persist topology")\n            report = {"next_roles": list(MANDATORY_ROLES) + ["systems_architect"]}\n            first.memory.log_topology_adjustment(\n                mission_id, 8, 4, "test", report\n            )\n            second = AdaptiveTaskOrchestrator(str(config_path), silent=True)\n            self.assertEqual(second.num_agents, 4)\n            self.assertEqual(\n                [profile["role"] for profile in second.worker_profiles],\n                report["next_roles"],\n            )\n\n\nif __name__ == "__main__":\n    unittest.main()\n'''.replace(
            "import unittest\n", "import unittest\n\nimport yaml\n"
        ),
        encoding="utf-8",
    )


def build_baseline_config() -> Path:
    source = yaml.safe_load((ROOT / "innovation_config.yaml").read_text(encoding="utf-8"))
    source["openrouter"]["base_url"] = "https://models.github.ai/inference"
    source["openrouter"]["model"] = "openai/gpt-4.1"
    source["openrouter"]["request_timeout"] = 120
    source["tools"]["allowlist"] = []
    source["tools"]["mutation_enabled"] = False
    source["memory"]["db_path"] = str(ROOT / ".worker-baseline-zero.db")
    source["agent"]["max_iterations"] = 1
    source["agent"]["run_timeout"] = 180
    source["orchestrator"]["task_timeout"] = 240
    for profile in source["apex_agents"]:
        profile["model"] = "openai/gpt-4.1"
        profile["allowed_tools"] = []
    path = ROOT / ".worker-baseline-zero-config.yaml"
    path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    return path


def run_baseline() -> None:
    from adaptive_orchestrator import AdaptiveTaskOrchestrator

    output_dir = ROOT / "artifacts/worker-baseline-zero"
    output_dir.mkdir(parents=True, exist_ok=True)
    mission = '''WORKER BASELINE ZERO — JOB-APP HELIX COMPANY PROOF COMPILER

Verified source packet:
- Job-App Helix contains 48 source-backed company application tracks.
- The first-depth atlas maps company pressure, inferred bottlenecks, GlacierEQ systems, leverage, application moves, and next evidence gates.
- The unresolved second-depth gate is repository-by-repository code inspection plus current-role reconciliation.
- The system must prove that Casey builds connected systems, not isolated repositories.

Mission:
Design the next highest-leverage Job-App Helix innovation: a Company Proof Compiler that converts relevant GlacierEQ repositories and current role requirements into code-evidence sheets, reproducible proof artifacts, truth-bounded application claims, and a ranked APPLY_NOW / REPAIR_THEN_APPLY / WATCH / NO_MATCH decision.

Every worker must complete only its assigned template, preserve the distinction between verified packet facts and design inference, and produce a concrete contribution that can be measured against the other workers.'''
    config_path = build_baseline_config()
    orchestrator = AdaptiveTaskOrchestrator(str(config_path), silent=True)
    final = orchestrator.orchestrate(mission)
    report = orchestrator.last_innovation_report
    if len(report.get("scores", [])) != 8:
        raise RuntimeError("baseline did not produce exactly eight worker scorecards")
    if report.get("silent_worker_omissions") != 0:
        raise RuntimeError("baseline contains silent worker omissions")

    (output_dir / "mission.md").write_text(mission + "\n", encoding="utf-8")
    (output_dir / "raw-synthesis-and-report.md").write_text(final + "\n", encoding="utf-8")
    (output_dir / "worker-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    rows = []
    for score in report["scores"]:
        adjustment = next(
            item for item in report["adjustments"] if item["role"] == score["role"]
        )
        rows.append(
            "| {role} | {quality:.2f} | {benefit:.4f} | {action} |".format(
                role=score["role"],
                quality=score["quality_score"],
                benefit=score["benefit_score"],
                action=adjustment["action"],
            )
        )
    summary = "\n".join(
        [
            "# Worker Baseline Zero",
            "",
            f"- Workers executed: **{report['current_worker_count']}**",
            f"- Average quality: **{report['average_quality']:.2f}/100**",
            f"- Average marginal benefit: **{report['average_benefit']:.4f}**",
            f"- Next worker count: **{report['next_worker_count']}**",
            f"- Topology decision: {report['topology_reason']}",
            "",
            "| Worker | Quality | Benefit | Next adjustment |",
            "|---|---:|---:|---|",
            *rows,
            "",
            f"Next active roles: {', '.join(report['next_roles'])}",
            "",
            "Quality and benefit are output-contract metrics, not independent factual verification.",
        ]
    )
    (output_dir / "summary.md").write_text(summary + "\n", encoding="utf-8")

    hashes = {}
    for path in sorted(output_dir.iterdir()):
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = {
        "schema": "glaciereq.make-it-heavy.worker-baseline-zero.v1",
        "status": "PASS",
        "provider": "GitHub Models",
        "endpoint": "https://models.github.ai/inference/chat/completions",
        "model": "openai/gpt-4.1",
        "worker_count": report["current_worker_count"],
        "next_worker_count": report["next_worker_count"],
        "average_quality": report["average_quality"],
        "average_benefit": report["average_benefit"],
        "silent_worker_omissions": report["silent_worker_omissions"],
        "next_roles": report["next_roles"],
        "artifact_sha256": hashes,
        "truth_boundary": (
            "Live model execution is proven by the committed outputs. Scores measure "
            "template completion and marginal contribution, not factual correctness."
        ),
    }
    (ROOT / "receipts").mkdir(exist_ok=True)
    (ROOT / "receipts/worker-baseline-zero-2026-08-05.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    db_path = ROOT / ".worker-baseline-zero.db"
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            worker_scores = conn.execute("SELECT COUNT(*) FROM worker_scores").fetchone()[0]
            adjustments = conn.execute("SELECT COUNT(*) FROM template_adjustments").fetchone()[0]
            topologies = conn.execute("SELECT COUNT(*) FROM topology_adjustments").fetchone()[0]
        if (worker_scores, adjustments, topologies) != (8, 8, 1):
            raise RuntimeError(
                f"unexpected persisted counts: {(worker_scores, adjustments, topologies)}"
            )

    config_path.unlink(missing_ok=True)
    db_path.unlink(missing_ok=True)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in {"all", "harden"}:
        harden_runtime()
    if mode in {"all", "baseline"}:
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise RuntimeError("OPENROUTER_API_KEY/GitHub Models token is missing")
        run_baseline()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
