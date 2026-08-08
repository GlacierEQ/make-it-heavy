"""Capacity-aware execution-width regression tests."""

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
            "response": "SOURCES\nsource: https://example.com\nBOUNDARY\nEvidence only.",
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
