#!/usr/bin/env python3
"""One-shot materializer for capacity-aware adaptive worker control."""

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing patch anchor in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_health() -> None:
    path = Path("innovation_health.py")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        'MODEL_INFERENCE = "model_inference"\nINFRA_FAILURE = "infra_failure"\n',
        'MODEL_INFERENCE = "model_inference"\nINFRA_FAILURE = "infra_failure"\nCAPACITY_FAILURE = "capacity_failure"\n',
        1,
    )
    addition = '''


def classify_local_capacity_contention(
    results: Sequence[Mapping[str, Any]],
    *,
    base_url: str,
    current_parallel_width: int,
) -> Optional[Dict[str, Any]]:
    """Detect partial localhost timeouts caused by execution-width contention."""

    normalized_url = str(base_url or "").lower()
    if "127.0.0.1" not in normalized_url and "localhost" not in normalized_url:
        return None
    if int(current_parallel_width) <= 1 or not results:
        return None

    reviewable = [
        item for item in results if str(item.get("status")) == MODEL_INFERENCE
    ]
    if not reviewable:
        return None

    failed_ids = []
    excerpts = []
    for item in results:
        status = str(item.get("status") or "")
        response = str(item.get("response") or item.get("error_message") or "")
        lowered = response.lower()
        timeout_shaped = (
            status == "timeout"
            or "timed out" in lowered
            or "timeout" in lowered
            or ("exceeded its" in lowered and "budget" in lowered)
        )
        if status in {"error", "timeout"} and timeout_shaped:
            failed_ids.append(int(item.get("agent_id", -1)))
            excerpts.append(_redact(response))

    if not failed_ids:
        return None

    canonical = "\\n".join(sorted(_normalize_error(value) for value in excerpts))
    return {
        "health_class": "CAPACITY_CONTENTION",
        "failed_worker_ids": failed_ids,
        "failed_worker_count": len(failed_ids),
        "reviewable_worker_count": len(reviewable),
        "current_parallel_width": int(current_parallel_width),
        "recommended_parallel_width": max(1, int(current_parallel_width) // 2),
        "error_fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "error_excerpts": excerpts,
        "template_learning_eligible_for_failed_workers": False,
    }


def mark_capacity_failures(
    results: Sequence[Mapping[str, Any]],
    incident: Mapping[str, Any],
) -> list[Dict[str, Any]]:
    """Quarantine capacity-contended workers from template learning."""

    failed = {int(value) for value in incident.get("failed_worker_ids", [])}
    marked = []
    for raw in results:
        item = dict(raw)
        if int(item.get("agent_id", -1)) in failed:
            item["original_status"] = item.get("status")
            item["status"] = CAPACITY_FAILURE
            item["capacity_failure"] = True
            item["template_learning_eligible"] = False
        marked.append(item)
    return marked
'''
    if "def classify_local_capacity_contention(" not in text:
        text += addition
    path.write_text(text, encoding="utf-8")


def patch_orchestrator() -> None:
    replace_once(
        "orchestrator.py",
        "        executor = ThreadPoolExecutor(max_workers=self.num_agents)\n",
        '''        parallel_width = max(
            1,
            min(
                self.num_agents,
                int(getattr(self, "execution_parallelism", self.num_agents)),
            ),
        )
        executor = ThreadPoolExecutor(max_workers=parallel_width)
''',
    )


def patch_adaptive_orchestrator() -> None:
    replace_once(
        "adaptive_orchestrator.py",
        '''from innovation_health import (
    build_infrastructure_report,
    classify_shared_infrastructure_failure,
)
''',
        '''from innovation_health import (
    build_infrastructure_report,
    classify_local_capacity_contention,
    classify_shared_infrastructure_failure,
    mark_capacity_failures,
)
''',
    )
    replace_once(
        "adaptive_orchestrator.py",
        '''        innovation = self.config.get("innovation", {})
        memory_path = self.config.get("memory", {}).get("db_path", ".swarm_memory.db")
''',
        '''        innovation = self.config.get("innovation", {})
        self.execution_parallelism = max(
            1,
            min(
                self.num_agents,
                int(innovation.get("execution_parallelism", self.num_agents)),
            ),
        )
        memory_path = self.config.get("memory", {}).get("db_path", ".swarm_memory.db")
''',
    )
    replace_once(
        "adaptive_orchestrator.py",
        '''        if persisted:
            roles = persisted.get("report", {}).get("next_roles")
            if isinstance(roles, list) and roles:
                self._activate_next_roles([str(role) for role in roles])
''',
        '''        if persisted:
            persisted_report = persisted.get("report", {})
            roles = persisted_report.get("next_roles")
            if isinstance(roles, list) and roles:
                self._activate_next_roles([str(role) for role in roles])
            next_parallel_width = persisted_report.get("next_parallel_width")
            if next_parallel_width is not None:
                self.execution_parallelism = max(
                    1, min(self.num_agents, int(next_parallel_width))
                )
''',
    )
    replace_once(
        "adaptive_orchestrator.py",
        '''        self.worker_profiles = selected
        self.num_agents = len(selected)
''',
        '''        self.worker_profiles = selected
        self.num_agents = len(selected)
        self.execution_parallelism = min(self.execution_parallelism, self.num_agents)
''',
    )
    replace_once(
        "adaptive_orchestrator.py",
        '''            report = self.innovation.evaluate_turn(
                self._current_mission_id,
                user_input,
                self.last_run_results,
                synthesis,
            )
            report["health_class"] = "HEALTHY_OR_MIXED"
            report["performance_valid"] = True
''',
        '''            capacity_incident = classify_local_capacity_contention(
                self.last_run_results,
                base_url=self.config.get("openrouter", {}).get("base_url", ""),
                current_parallel_width=self.execution_parallelism,
            )
            effective_results = (
                mark_capacity_failures(self.last_run_results, capacity_incident)
                if capacity_incident is not None
                else self.last_run_results
            )
            report = self.innovation.evaluate_turn(
                self._current_mission_id,
                user_input,
                effective_results,
                synthesis,
                current_parallel_width=self.execution_parallelism,
            )
            report["health_class"] = (
                "CAPACITY_CONTENTION"
                if capacity_incident is not None
                else "HEALTHY_OR_MIXED"
            )
            report["performance_valid"] = True
            if capacity_incident is not None:
                report["capacity"] = capacity_incident
''',
    )
    replace_once(
        "adaptive_orchestrator.py",
        '''            self._activate_next_roles(report["next_roles"])
            return final
        except Exception:
''',
        '''            self._activate_next_roles(report["next_roles"])
            self.execution_parallelism = max(
                1,
                min(
                    self.num_agents,
                    int(report.get("next_parallel_width", self.execution_parallelism)),
                ),
            )
            return final
        except Exception:
''',
    )


def patch_loop() -> None:
    replace_once(
        "innovation_loop.py",
        '''        if score["runtime_status"] in {"timeout", "error"}:
            action = "REPLACE_OR_NARROW"
            instruction = (
                "Cut the assignment to one bounded deliverable, preserve the required "
                "sections, and use the fastest reliable model/tool path."
            )
''',
        '''        if score["runtime_status"] == "capacity_failure":
            action = "HOLD_TEMPLATE_CAPACITY"
            instruction = (
                "Preserve this worker template unchanged. The worker lost execution capacity, "
                "so reduce shared parallel pressure and rerun before judging the role."
            )
        elif score["runtime_status"] in {"timeout", "error"}:
            action = "REPLACE_OR_NARROW"
            instruction = (
                "Cut the assignment to one bounded deliverable, preserve the required "
                "sections, and use the fastest reliable model/tool path."
            )
''',
    )
    replace_once(
        "innovation_loop.py",
        '''        failed = sum(
            1 for score in scores if score["runtime_status"] in {"timeout", "error"}
        )
        redundant = sum(
''',
        '''        capacity_failed = sum(
            1 for score in scores if score["runtime_status"] == "capacity_failure"
        )
        failed = sum(
            1 for score in scores if score["runtime_status"] in {"timeout", "error"}
        )
        redundant = sum(
''',
    )
    replace_once(
        "innovation_loop.py",
        '''        if failed:
            return current_count, "hold count; replace or narrow failed workers"
''',
        '''        if capacity_failed:
            return (
                current_count,
                "hold logical worker count; capacity failures require execution-width repair",
            )
        if failed:
            return current_count, "hold count; replace or narrow failed workers"
''',
    )
    path = Path("innovation_loop.py")
    text = path.read_text(encoding="utf-8")
    anchor = '''    def _next_roles(
        self,
        scores: Sequence[Mapping[str, Any]],
        next_count: int,
    ) -> List[str]:
'''
    insertion = '''    def _next_parallel_width(
        self,
        scores: Sequence[Mapping[str, Any]],
        current_width: int,
        logical_worker_count: int,
    ) -> Tuple[int, str]:
        """Tune execution pressure independently from the logical specialist topology."""

        current_width = max(1, min(int(current_width), int(logical_worker_count)))
        capacity_failed = sum(
            1 for score in scores if score["runtime_status"] == "capacity_failure"
        )
        if capacity_failed:
            next_width = max(1, current_width // 2)
            return (
                next_width,
                f"reduce parallel width {current_width}→{next_width}; "
                f"{capacity_failed} workers hit local capacity contention",
            )
        if current_width < logical_worker_count:
            return (
                current_width,
                "hold reduced parallel width until a clean turn proves spare execution capacity",
            )
        return (
            current_width,
            "parallel width matched logical worker count without capacity evidence",
        )

'''
    if "def _next_parallel_width(" not in text:
        if anchor not in text:
            raise SystemExit("missing _next_roles anchor")
        text = text.replace(anchor, insertion + anchor, 1)
    path.write_text(text, encoding="utf-8")

    replace_once(
        "innovation_loop.py",
        '''                f"**This turn:** {report['current_worker_count']} workers → "
                f"**next:** {report['next_worker_count']} workers. "
                f"Average quality **{report['average_quality']:.2f}/100**; "
''',
        '''                f"**This turn:** {report['current_worker_count']} logical workers → "
                f"**next:** {report['next_worker_count']} logical workers; "
                f"parallel width {report['current_parallel_width']}→{report['next_parallel_width']}. "
                f"Average reviewable-worker quality **{report['average_quality']:.2f}/100**; "
''',
    )
    replace_once(
        "innovation_loop.py",
        '''                f"**Topology decision:** {report['topology_reason']}.",
                "",
                f"**Next active roles:** {', '.join(report['next_roles'])}.",
''',
        '''                f"**Logical-topology decision:** {report['topology_reason']}.",
                "",
                f"**Execution-width decision:** {report['parallel_reason']}.",
                "",
                f"**Next active roles:** {', '.join(report['next_roles'])}.",
''',
    )
    replace_once(
        "innovation_loop.py",
        '''        synthesis: str,
    ) -> Dict[str, Any]:
''',
        '''        synthesis: str,
        current_parallel_width: Optional[int] = None,
    ) -> Dict[str, Any]:
''',
    )
    replace_once(
        "innovation_loop.py",
        '''        adjustments = [self._adjustment(score) for score in scores]
        next_count, topology_reason = self._next_worker_count(scores, len(scores))
        next_roles = self._next_roles(scores, next_count)
        report: Dict[str, Any] = {
''',
        '''        adjustments = [self._adjustment(score) for score in scores]
        next_count, topology_reason = self._next_worker_count(scores, len(scores))
        next_roles = self._next_roles(scores, next_count)
        current_parallel_width = max(
            1, min(len(scores), int(current_parallel_width or len(scores)))
        )
        next_parallel_width, parallel_reason = self._next_parallel_width(
            scores, current_parallel_width, next_count
        )
        reviewable_scores = [
            score for score in scores if score["runtime_status"] == "model_inference"
        ]
        report: Dict[str, Any] = {
''',
    )
    replace_once(
        "innovation_loop.py",
        '''            "next_worker_count": next_count,
            "next_roles": next_roles,
            "average_quality": round(
                mean(score["quality_score"] for score in scores), 2
            ),
            "average_benefit": round(
                mean(score["benefit_score"] for score in scores), 4
            ),
            "topology_reason": topology_reason,
''',
        '''            "next_worker_count": next_count,
            "next_roles": next_roles,
            "current_parallel_width": current_parallel_width,
            "next_parallel_width": next_parallel_width,
            "parallel_reason": parallel_reason,
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
''',
    )


def patch_live_workflow() -> None:
    path = Path(".github/workflows/adaptive-innovation-live.yml")
    text = path.read_text(encoding="utf-8")
    if "config['innovation']['execution_parallelism'] = 4" not in text:
        anchor = "          config['orchestrator']['task_timeout'] = 900\n"
        if anchor not in text:
            raise SystemExit("missing local live-config anchor")
        text = text.replace(
            anchor,
            anchor + "          config['innovation']['execution_parallelism'] = 4\n",
            1,
        )
    text = text.replace(
        "          import json\n          import sqlite3\n          from pathlib import Path\n",
        "          import json\n          import os\n          import sqlite3\n          from pathlib import Path\n",
        1,
    )
    text = text.replace(
        "              'provider': os.environ.get('LIVE_PROVIDER') if False else None,\n",
        "              'provider': os.environ.get('LIVE_PROVIDER'),\n",
        1,
    )
    path.write_text(text, encoding="utf-8")


def write_tests() -> None:
    Path("tests/test_capacity_adaptation.py").write_text(
        '''"""Capacity-aware execution-width regression tests."""

from pathlib import Path

from innovation_health import (
    classify_local_capacity_contention,
    mark_capacity_failures,
)
from innovation_loop import AdaptiveWorkerLoop

ROOT = Path(__file__).resolve().parents[1]


def _results():
    return [
        {
            "agent_id": 0,
            "role": "source_mapper",
            "model": "qwen3:0.6b",
            "status": "model_inference",
            "response": "SOURCES\\nsource: https://example.com\\nBOUNDARY\\nEvidence only.",
            "execution_time": 50.0,
        },
        {
            "agent_id": 1,
            "role": "bottleneck_cartographer",
            "model": "qwen3:0.6b",
            "status": "error",
            "response": "Worker failed: OpenRouter timed out after 120s",
            "execution_time": 368.0,
        },
    ]


def test_local_partial_timeout_is_capacity_not_template_failure():
    incident = classify_local_capacity_contention(
        _results(),
        base_url="http://127.0.0.1:11434/v1",
        current_parallel_width=8,
    )
    assert incident is not None
    assert incident["failed_worker_ids"] == [1]
    marked = mark_capacity_failures(_results(), incident)
    assert marked[0]["status"] == "model_inference"
    assert marked[1]["status"] == "capacity_failure"


def test_hosted_timeout_is_not_automatically_capacity_contention():
    assert classify_local_capacity_contention(
        _results(),
        base_url="https://api.openai.com/v1",
        current_parallel_width=8,
    ) is None


def test_capacity_failure_preserves_template_and_reduces_width():
    loop = AdaptiveWorkerLoop(
        ROOT / "templates" / "innovation_workers.yaml",
        min_workers=4,
        max_workers=8,
    )
    score = {
        "role": "bottleneck_cartographer",
        "template_id": "bottleneck_cartographer.v1",
        "runtime_status": "capacity_failure",
        "quality_score": 0.0,
        "benefit_score": 0.0,
        "dimensions": {
            "completion": 0.0,
            "evidence": 0.0,
            "specificity": 0.0,
            "novelty": 0.0,
            "actionability": 0.0,
            "truth": 0.0,
            "efficiency": 0.0,
        },
    }
    adjustment = loop._adjustment(score)
    assert adjustment["action"] == "HOLD_TEMPLATE_CAPACITY"
    width, reason = loop._next_parallel_width([score], 8, 8)
    assert width == 4
    assert "capacity contention" in reason
''',
        encoding="utf-8",
    )


def main() -> None:
    patch_health()
    patch_orchestrator()
    patch_adaptive_orchestrator()
    patch_loop()
    patch_live_workflow()
    write_tests()


if __name__ == "__main__":
    main()
