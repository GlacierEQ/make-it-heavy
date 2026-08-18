# SPDX-License-Identifier: Proprietary
"""Longitudinal evidence-aware worker portfolio selection.

This module upgrades Make-It-Heavy's next-turn topology selection from a
single-turn ranking to an exploration/exploitation policy that can use recent
worker history without inventing causal claims. Historical quality and
heuristic benefit remain observational signals; explicit ablation metrics are
only used when supplied by the memory layer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence


HistoryProvider = Callable[[str, int], Sequence[Mapping[str, Any]]]


@dataclass(frozen=True)
class WorkerPortfolioSignal:
    role: str
    current_value: float
    historical_value: float
    exploration_bonus: float
    trend_bonus: float
    failure_penalty: float
    causal_bonus: float
    portfolio_score: float
    history_samples: int


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if math.isfinite(numeric) else default


def _normalized_observational_value(row: Mapping[str, Any]) -> float:
    quality = max(0.0, min(1.0, _finite(row.get("quality_score")) / 100.0))
    benefit = max(0.0, min(1.0, _finite(row.get("benefit_score"))))
    if "heuristic_benefit_score" in row:
        benefit = max(0.0, min(1.0, _finite(row.get("heuristic_benefit_score"))))
    unique = max(0.0, min(1.0, _finite(row.get("unique_contribution"), 0.5)))
    if "unique_contribution_score" in row:
        unique = max(0.0, min(1.0, _finite(row.get("unique_contribution_score"), 0.5)))
    return 0.45 * benefit + 0.40 * quality + 0.15 * unique


def _causal_signal(rows: Sequence[Mapping[str, Any]]) -> float:
    """Use causal evidence only when it explicitly exists.

    Missing ablation/counterfactual fields contribute zero. This prevents the
    selector from silently promoting heuristic scores into causal value.
    """

    values: List[float] = []
    for row in rows:
        marginal = row.get("marginal_system_value")
        leverage = row.get("outcome_leverage")
        if marginal is None and leverage is None:
            continue
        marginal_value = max(-1.0, min(1.0, _finite(marginal))) if marginal is not None else 0.0
        leverage_value = max(0.0, min(1.0, _finite(leverage))) if leverage is not None else 0.0
        values.append(0.65 * marginal_value + 0.35 * leverage_value)
    return mean(values) if values else 0.0


def _trend(rows: Sequence[Mapping[str, Any]]) -> float:
    values = [_normalized_observational_value(row) for row in rows]
    if len(values) < 2:
        return 0.0
    # Memory APIs return newest first. Positive means recent evidence improved.
    newest = mean(values[: min(2, len(values))])
    oldest = mean(values[-min(2, len(values)) :])
    return max(-0.20, min(0.20, newest - oldest))


def build_worker_signal(
    score: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    *,
    total_history_samples: int,
) -> WorkerPortfolioSignal:
    role = str(score["role"])
    current_value = _normalized_observational_value(score)
    valid_history = [
        row
        for row in history
        if str(row.get("runtime_status", "model_inference")) not in {"timeout", "error"}
        and bool(row.get("performance_valid", True))
    ]
    historical_values = [_normalized_observational_value(row) for row in valid_history]
    historical_value = mean(historical_values) if historical_values else current_value

    sample_count = len(valid_history)
    exploration_bonus = min(
        0.22,
        0.12 * math.sqrt(math.log(max(2, total_history_samples + 1)) / (sample_count + 1)),
    )
    trend_bonus = 0.35 * _trend(valid_history)

    failed = sum(
        1
        for row in history
        if str(row.get("runtime_status", "")) in {"timeout", "error"}
        or row.get("performance_valid") is False
    )
    failure_penalty = min(0.30, 0.08 * failed)
    causal_bonus = 0.18 * _causal_signal(valid_history)

    portfolio_score = (
        0.50 * current_value
        + 0.34 * historical_value
        + exploration_bonus
        + trend_bonus
        + causal_bonus
        - failure_penalty
    )
    return WorkerPortfolioSignal(
        role=role,
        current_value=round(current_value, 6),
        historical_value=round(historical_value, 6),
        exploration_bonus=round(exploration_bonus, 6),
        trend_bonus=round(trend_bonus, 6),
        failure_penalty=round(failure_penalty, 6),
        causal_bonus=round(causal_bonus, 6),
        portfolio_score=round(portfolio_score, 6),
        history_samples=sample_count,
    )


def select_worker_portfolio(
    scores: Sequence[Mapping[str, Any]],
    *,
    next_count: int,
    candidate_roles: Iterable[str],
    mandatory_roles: Sequence[str],
    history_provider: Optional[HistoryProvider] = None,
    history_limit: int = 8,
) -> tuple[List[str], Dict[str, WorkerPortfolioSignal]]:
    """Choose the next worker portfolio using current and longitudinal evidence.

    Without a history provider, this intentionally reproduces the legacy
    current-turn ordering. That makes the upgrade backwards-compatible while
    enabling smarter selection whenever longitudinal memory is available.
    """

    role_scores = {str(score["role"]): score for score in scores}
    candidates = list(dict.fromkeys(str(role) for role in candidate_roles))
    next_count = max(int(next_count), len(mandatory_roles))
    if next_count > len(candidates):
        raise ValueError("next_count exceeds configured candidate roles")

    selected: List[str] = []
    for role in mandatory_roles:
        if role not in candidates:
            raise ValueError(f"mandatory worker role is not configured: {role}")
        if role not in selected:
            selected.append(role)

    if history_provider is None:
        ranked = sorted(
            scores,
            key=lambda score: (
                0.65 * _finite(score.get("benefit_score"))
                + 0.35 * (_finite(score.get("quality_score")) / 100.0),
                str(score.get("role")),
            ),
            reverse=True,
        )
        signals: Dict[str, WorkerPortfolioSignal] = {}
        for score in ranked:
            role = str(score["role"])
            current = _normalized_observational_value(score)
            signals[role] = WorkerPortfolioSignal(
                role=role,
                current_value=round(current, 6),
                historical_value=round(current, 6),
                exploration_bonus=0.0,
                trend_bonus=0.0,
                failure_penalty=0.0,
                causal_bonus=0.0,
                portfolio_score=round(current, 6),
                history_samples=0,
            )
            if role not in selected and len(selected) < next_count:
                selected.append(role)
        for role in candidates:
            if role not in selected and len(selected) < next_count:
                selected.append(role)
        return selected, signals

    history_by_role: Dict[str, Sequence[Mapping[str, Any]]] = {
        role: tuple(history_provider(role, history_limit) or ()) for role in candidates
    }
    total_history = sum(len(rows) for rows in history_by_role.values())
    signals = {}
    for role in candidates:
        score = role_scores.get(role)
        if score is None:
            # A configured but inactive challenger receives a neutral current
            # observation and earns exploration pressure from sparse history.
            score = {
                "role": role,
                "quality_score": 50.0,
                "benefit_score": 0.50,
                "unique_contribution": 0.50,
            }
        signals[role] = build_worker_signal(
            score,
            history_by_role[role],
            total_history_samples=total_history,
        )

    ranked_roles = sorted(
        candidates,
        key=lambda role: (
            signals[role].portfolio_score,
            signals[role].causal_bonus,
            signals[role].exploration_bonus,
            role,
        ),
        reverse=True,
    )
    for role in ranked_roles:
        if role not in selected and len(selected) < next_count:
            selected.append(role)
    return selected, signals
