#!/usr/bin/env python3
"""Materialize adaptive provider-capacity feedback into the Turn-9 worker-science lineage."""

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing patch anchor in {path}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_health() -> None:
    path = Path("innovation_health.py")
    text = path.read_text(encoding="utf-8")
    if 'CAPACITY_FAILURE = "capacity_failure"' not in text:
        text = text.replace(
            'MODEL_INFERENCE = "model_inference"\nINFRA_FAILURE = "infra_failure"\n',
            'MODEL_INFERENCE = "model_inference"\nINFRA_FAILURE = "infra_failure"\nCAPACITY_FAILURE = "capacity_failure"\n',
            1,
        )
    addition = '''


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

    canonical = "\\n".join(sorted(_normalize_error(value) for value in excerpts))
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
'''
    if "def classify_provider_capacity_contention(" not in text:
        text += addition
    path.write_text(text, encoding="utf-8")


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
                "Preserve this template unchanged. The worker lost provider execution "
                "capacity, so lower shared concurrency and rerun before judging the role."
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
                "hold logical count; provider-capacity failures require width repair, not role repair",
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
    insertion = '''    @staticmethod
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

'''
    if "def _next_provider_width(" not in text:
        if anchor not in text:
            raise SystemExit("missing _next_roles anchor")
        text = text.replace(anchor, insertion + anchor, 1)
    path.write_text(text, encoding="utf-8")

    replace_once(
        "innovation_loop.py",
        '''                f"**This turn:** {report['current_worker_count']} workers → "
                f"**next:** {report['next_worker_count']} workers. "
                f"Average quality **{report['average_quality']:.2f}/100**; "
                f"average marginal benefit **{report['average_benefit']:.4f}**."
''',
        '''                f"**This turn:** {report['current_worker_count']} logical workers → "
                f"**next:** {report['next_worker_count']} logical workers; "
                f"provider width {report['current_provider_concurrency_width']}→"
                f"{report['next_provider_concurrency_width']}. "
                f"Average reviewable-worker quality **{report['average_quality']:.2f}/100**; "
                f"average heuristic benefit **{report['average_benefit']:.4f}**."
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
                f"**Provider-width decision:** {report['provider_width_reason']}.",
                "",
                f"**Next active roles:** {', '.join(report['next_roles'])}.",
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
''',
    )


def patch_orchestrator() -> None:
    replace_once(
        "adaptive_orchestrator.py",
        '''from innovation_health import (
    build_infrastructure_report,
    classify_shared_infrastructure_failure,
    render_infrastructure_result,
)
''',
        '''from innovation_health import (
    build_infrastructure_report,
    classify_provider_capacity_contention,
    classify_shared_infrastructure_failure,
    mark_capacity_failures,
    render_infrastructure_result,
)
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
            next_provider_width = persisted_report.get(
                "next_provider_concurrency_width"
            )
            if next_provider_width is not None:
                self.provider_concurrency_width = max(
                    1, min(self.num_agents, int(next_provider_width))
                )
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
            report["provider_concurrency_width"] = bounded_provider_concurrency(
                self.num_agents,
                self.provider_concurrency_width,
            )
            report["claim_gate_pass_rate"] = round(
                sum(
                    1
                    for score in report["scores"]
                    if score.get("claim_gate", {}).get("pass")
                )
                / max(1, len(report["scores"])),
                4,
            )
''',
        '''            current_provider_width = bounded_provider_concurrency(
                self.num_agents,
                self.provider_concurrency_width,
            )
            capacity_incident = classify_provider_capacity_contention(
                self.last_run_results,
                base_url=self.config.get("openrouter", {}).get("base_url", ""),
                current_provider_width=current_provider_width,
            )
            effective_results = (
                mark_capacity_failures(self.last_run_results, capacity_incident)
                if capacity_incident is not None
                else self.last_run_results
            )
            self.innovation.current_provider_concurrency_width = current_provider_width
            report = self.innovation.evaluate_turn(
                self._current_mission_id,
                user_input,
                effective_results,
                synthesis,
            )
            report["provider_concurrency_width"] = current_provider_width
            if capacity_incident is not None:
                report["capacity_incident"] = capacity_incident
            claim_scores = [
                score
                for score in report["scores"]
                if score.get("runtime_status") == "model_inference"
            ]
            report["claim_gate_pass_rate"] = round(
                sum(
                    1
                    for score in claim_scores
                    if score.get("claim_gate", {}).get("pass")
                )
                / max(1, len(claim_scores)),
                4,
            )
            self.provider_concurrency_width = max(
                1,
                min(
                    self.num_agents,
                    int(
                        report.get(
                            "next_provider_concurrency_width",
                            current_provider_width,
                        )
                    ),
                ),
            )
''',
    )


def write_tests() -> None:
    Path("tests/test_turn10_capacity_feedback.py").write_text(
        '''"""Turn-10 adaptive provider-capacity feedback tests."""

from pathlib import Path
import unittest

from claim_aware_innovation import ClaimAwareAdaptiveWorkerLoop
from innovation_health import (
    classify_provider_capacity_contention,
    mark_capacity_failures,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "innovation_workers.yaml"


class CapacityClassificationTests(unittest.TestCase):
    @staticmethod
    def _results():
        return [
            {
                "agent_id": 0,
                "role": "source_mapper",
                "model": "qwen3:0.6b",
                "status": "model_inference",
                "response": "OBSERVED[S1]: bounded evidence.",
                "execution_time": 50.0,
            },
            {
                "agent_id": 1,
                "role": "bottleneck_cartographer",
                "model": "qwen3:0.6b",
                "status": "error",
                "response": "Worker failed: request timed out after 120s",
                "execution_time": 368.0,
            },
        ]

    def test_local_partial_timeout_is_capacity_contention(self) -> None:
        incident = classify_provider_capacity_contention(
            self._results(),
            base_url="http://127.0.0.1:11434/v1",
            current_provider_width=8,
        )
        self.assertIsNotNone(incident)
        assert incident is not None
        self.assertEqual(incident["failed_worker_ids"], [1])
        self.assertEqual(incident["recommended_provider_concurrency_width"], 4)

        marked = mark_capacity_failures(self._results(), incident)
        self.assertEqual(marked[0]["status"], "model_inference")
        self.assertEqual(marked[1]["status"], "capacity_failure")
        self.assertFalse(marked[1]["template_learning_eligible"])

    def test_hosted_partial_timeout_is_not_assumed_capacity(self) -> None:
        incident = classify_provider_capacity_contention(
            self._results(),
            base_url="https://api.openai.com/v1",
            current_provider_width=8,
        )
        self.assertIsNone(incident)


class CapacityLearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = ClaimAwareAdaptiveWorkerLoop(TEMPLATES, min_workers=4, max_workers=8)

    def _capacity_score(self):
        return {
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

    def test_capacity_failure_does_not_rewrite_template(self) -> None:
        adjustment = self.loop._adjustment(self._capacity_score())
        self.assertEqual(adjustment["action"], "HOLD_TEMPLATE_CAPACITY")
        self.assertIn("Preserve this template unchanged", adjustment["instruction"])

    def test_capacity_failure_halves_provider_width(self) -> None:
        width, reason = self.loop._next_provider_width(
            [self._capacity_score()],
            current_width=8,
            logical_worker_count=8,
        )
        self.assertEqual(width, 4)
        self.assertIn("measured capacity contention", reason)

    def test_clean_reduced_width_holds(self) -> None:
        score = dict(self._capacity_score())
        score["runtime_status"] = "model_inference"
        width, reason = self.loop._next_provider_width(
            [score],
            current_width=4,
            logical_worker_count=8,
        )
        self.assertEqual(width, 4)
        self.assertIn("matched clean turn", reason)


if __name__ == "__main__":
    unittest.main()
''',
        encoding="utf-8",
    )


def main() -> None:
    patch_health()
    patch_loop()
    patch_orchestrator()
    write_tests()


if __name__ == "__main__":
    main()
