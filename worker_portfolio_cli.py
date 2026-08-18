# SPDX-License-Identifier: Proprietary
"""CLI for evidence-weighted Make-It-Heavy worker portfolio selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from worker_portfolio_optimizer import select_worker_portfolio


def _history_provider(history: Mapping[str, Any]):
    def provider(role: str, limit: int):
        rows = history.get(role, [])
        if not isinstance(rows, list):
            raise ValueError(f"history[{role!r}] must be a list")
        return rows[:limit]

    return provider


def compile_worker_portfolio(payload: Mapping[str, Any]) -> Dict[str, Any]:
    scores = payload.get("scores")
    candidate_roles = payload.get("candidate_roles")
    mandatory_roles = payload.get("mandatory_roles")
    next_count = payload.get("next_count")
    history = payload.get("history", {})
    if not isinstance(scores, list) or not scores:
        raise ValueError("scores must be a non-empty list")
    if not isinstance(candidate_roles, list) or not candidate_roles:
        raise ValueError("candidate_roles must be a non-empty list")
    if not isinstance(mandatory_roles, list):
        raise ValueError("mandatory_roles must be a list")
    if not isinstance(next_count, int) or next_count <= 0:
        raise ValueError("next_count must be a positive integer")
    if not isinstance(history, dict):
        raise ValueError("history must be an object keyed by worker role")

    selected, signals = select_worker_portfolio(
        scores,
        next_count=next_count,
        candidate_roles=candidate_roles,
        mandatory_roles=mandatory_roles,
        history_provider=_history_provider(history),
    )
    return {
        "schema": "glaciereq.make-it-heavy.worker-portfolio.v1",
        "selected_roles": selected,
        "signals": {
            role: {
                "current_value": signal.current_value,
                "historical_value": signal.historical_value,
                "exploration_bonus": signal.exploration_bonus,
                "trend_bonus": signal.trend_bonus,
                "failure_penalty": signal.failure_penalty,
                "causal_bonus": signal.causal_bonus,
                "portfolio_score": signal.portfolio_score,
                "history_samples": signal.history_samples,
            }
            for role, signal in sorted(signals.items())
        },
        "decision_boundary": (
            "Observational quality/benefit evidence informs selection; causal bonus is "
            "zero unless explicit ablation/counterfactual metrics are supplied."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select the next Make-It-Heavy worker portfolio from longitudinal evidence"
    )
    parser.add_argument("input", type=Path, help="JSON worker portfolio input")
    parser.add_argument("--output", type=Path, help="Optional JSON decision receipt")
    args = parser.parse_args(argv)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input must contain a JSON object")
    result = compile_worker_portfolio(payload)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
