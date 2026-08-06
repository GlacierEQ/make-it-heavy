#!/usr/bin/env python3
"""Materialize the genuine SparkForge Worker Baseline Zero receipt."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

ENDPOINT = (
    "https://kjebemdgvjvuutzvhbtp.supabase.co/functions/v1/"
    "mih-worker-baseline-zero"
)


def fetch_row() -> dict:
    request = urllib.request.Request(
        ENDPOINT,
        headers={"Accept": "application/json", "User-Agent": "Make-It-Heavy/Worker-Baseline-Zero"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError(f"receipt endpoint returned HTTP {response.status}")
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("receipt endpoint did not return an object")
    return value


def normalize_markdown(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines()).rstrip() + "\n"


def main() -> int:
    row = fetch_row()
    result = row.get("result") or {}
    assert row.get("status") == result.get("status") == "PASS"
    assert result.get("provider") == "henry-ships-sparkforge.smart_summarize"
    assert result.get("provider_count") == 1
    assert result.get("worker_count") == 8
    assert result.get("silent_worker_omissions") == 0
    assert len(result.get("scores", [])) == 8
    assert all(item.get("runtime_status") == "model_inference" for item in result["scores"])
    assert len(result.get("adjustments", [])) == 8
    assert len(result.get("next_roles", [])) == result.get("next_worker_count")

    output_dir = Path("artifacts/worker-baseline-zero")
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_dir = Path("receipts")
    receipt_dir.mkdir(exist_ok=True)

    (output_dir / "mission.md").write_text(
        normalize_markdown(str(result["mission"])), encoding="utf-8"
    )
    (output_dir / "worker-report.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    adjustment_by_role = {item["role"]: item for item in result["adjustments"]}
    blocks = ["# Worker Baseline Zero — Raw Genuine Outputs", ""]
    table_rows = []
    for score in result["scores"]:
        blocks.extend(
            [
                f"## {score['role']}",
                "",
                f"- Provider: `{score['model']}`",
                f"- Quality: **{score['quality_score']:.2f}/100**",
                f"- Marginal benefit: **{score['benefit_score']:.4f}**",
                f"- Execution time: **{score['execution_time']:.3f}s**",
                f"- Response SHA-256: `{score['response_sha256']}`",
                "",
                str(score["output"]).rstrip(),
                "",
            ]
        )
        action = adjustment_by_role[score["role"]]["action"]
        table_rows.append(
            f"| `{score['role']}` | {score['quality_score']:.2f} | "
            f"{score['benefit_score']:.4f} | `{action}` |"
        )
    (output_dir / "raw-worker-outputs.md").write_text(
        normalize_markdown("\n".join(blocks)), encoding="utf-8"
    )

    summary = "\n".join(
        [
            "# Worker Baseline Zero",
            "",
            f"- Genuine workers executed: **{result['worker_count']}**",
            f"- Provider: **{result['provider']}**",
            f"- Independent providers: **{result['provider_count']}**",
            f"- Average quality: **{result['average_quality']:.2f}/100**",
            f"- Average marginal benefit: **{result['average_benefit']:.4f}**",
            f"- Next worker count: **{result['next_worker_count']}**",
            f"- Topology decision: {result['topology_reason']}",
            "",
            "| Worker | Quality | Benefit | Next adjustment |",
            "|---|---:|---:|---|",
            *table_rows,
            "",
            "## Next active roles",
            "",
            ", ".join(f"`{role}`" for role in result["next_roles"]),
            "",
            "## Truth boundary",
            "",
            str(result["truth_boundary"]),
            "",
            f"Result SHA-256: `{row['result_sha256']}`",
        ]
    )
    (output_dir / "summary.md").write_text(
        normalize_markdown(summary), encoding="utf-8"
    )

    artifact_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output_dir.iterdir())
    }
    receipt = {
        "schema": "glaciereq.make-it-heavy.worker-baseline-zero-receipt.v1",
        "run_id": row["run_id"],
        "status": "PASS",
        "provider": result["provider"],
        "provider_count": 1,
        "worker_count": 8,
        "genuine_external_model_executions": 8,
        "silent_worker_omissions": 0,
        "average_quality": result["average_quality"],
        "average_benefit": result["average_benefit"],
        "next_worker_count": result["next_worker_count"],
        "next_roles": result["next_roles"],
        "result_sha256": row["result_sha256"],
        "artifact_sha256": artifact_hashes,
        "worker_response_sha256": {
            score["role"]: score["response_sha256"] for score in result["scores"]
        },
        "multi_provider_consensus": False,
        "truth_boundary": result["truth_boundary"],
    }
    (receipt_dir / "worker-baseline-zero-2026-08-05.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "workers": 8,
                "average_quality": result["average_quality"],
                "average_benefit": result["average_benefit"],
                "next_worker_count": result["next_worker_count"],
                "result_sha256": row["result_sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
