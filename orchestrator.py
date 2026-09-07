# SPDX-License-Identifier: Proprietary
"""Policy-bound multi-agent research orchestration."""

import hashlib
import json
import logging
import os
import threading
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
    as_completed,
)
from math import ceil
from typing import Any, Dict, List, Optional

import yaml

from agent import OpenRouterAgent, ConfigurationError
from memory import SwarmMemory
from memory_tiered import TieredMemory
from local_agent import LocalAgent, LocalAgentError

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config.yaml"
STATUS_QUEUED = "QUEUED"
STATUS_PROCESSING = "PROCESSING..."
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED_PREFIX = "FAILED"
STATUS_TIMEOUT = "TIMEOUT"
RESULT_CLASSIFICATION = "model_inference"
REVIEW_STATUS = "pending_review"
FALLBACK_QUESTION_TEMPLATES = [
    "Find source-backed observations relevant to: {topic}",
    "Identify unsupported claims, missing evidence, and conflicts in: {topic}",
    "Develop plausible alternative interpretations of: {topic}",
    "Describe reviewable next steps without taking external action for: {topic}",
]

# Approximate USD/1K-token pricing for OpenRouter models. Used only for
# telemetry; never asserted as ground truth. Unknown models fall back to 0.0.
_MODEL_PRICE_PER_1K: Dict[str, float] = {
    "openai/gpt-4.1-mini": 0.00015,
    "anthropic/claude-3.5-sonnet": 0.0015,
    "google/gemini-2.5-pro": 0.00125,
}
LOCAL_PRICE_PER_1K = 0.0  # local inference is free in this telemetry model


def bounded_provider_concurrency(logical_workers: int, configured_width: int) -> int:
    """Bound provider concurrency independently from logical worker count."""

    logical = max(1, int(logical_workers))
    width = max(1, int(configured_width))
    return min(logical, width)


def effective_turn_timeout(
    task_timeout: float,
    logical_workers: int,
    provider_width: int,
) -> float:
    """Scale the turn budget by execution waves when provider width is narrower."""

    width = bounded_provider_concurrency(logical_workers, provider_width)
    waves = max(1, ceil(max(1, int(logical_workers)) / width))
    return float(task_timeout) * waves


class ConfigurationError(Exception):
    """Raised when orchestration policy or worker configuration is invalid."""


class TaskOrchestrator:
    def __init__(
        self,
        config_path: str = DEFAULT_CONFIG_PATH,
        silent: bool = False,
        user_id: Optional[str] = None,
    ):
        self.config_path = config_path
        self.silent = silent
        self.user_id = user_id or ""
        self.config = self._load_and_validate_config(config_path)
        orchestrator = self.config["orchestrator"]
        self.num_agents = int(orchestrator["parallel_agents"])
        self.task_timeout = float(orchestrator["task_timeout"])
        self.aggregation_strategy = orchestrator["aggregation_strategy"]
        self.provider_concurrency_width = max(
            1, int(orchestrator.get("provider_concurrency_width", self.num_agents))
        )
        self.synthesis_token_budget = int(orchestrator.get("synthesis_token_budget", 2000))
        self.default_max_iterations = int(
            self.config.get("agent", {}).get("max_iterations", 10)
        )
        self.worker_profiles = self.config["apex_agents"][: self.num_agents]
        self.agent_progress: Dict[int, str] = {}
        self.agent_results: Dict[int, str] = {}
        self.progress_lock = threading.Lock()
        self.last_run_results: List[Dict[str, Any]] = []
        self.memory = SwarmMemory(self.config.get("memory", {}).get("db_path", ".swarm_memory.db"))
        self._current_mission_id: int = 0
        # Reused across orchestrate() calls (e.g. the Genius loop) so provider
        # threads are not rebuilt every iteration.
        self._executor: Optional[ThreadPoolExecutor] = None
        self._decompose_cache: Dict[str, List[str]] = {}
        # Per-call injected context (Genius recall + tiered memory block).
        self._recall_context: List[str] = []
        self._memory_block: str = ""
        # Tiered memory handle (lazy, reused while a user_id is set).
        self._tiered_memory: Optional[TieredMemory] = None
        self._tiered_config = self.config.get("memory_tiered")

    @staticmethod
    def _load_and_validate_config(config_path: str) -> Dict[str, Any]:
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                config = yaml.safe_load(handle)
        except FileNotFoundError as exc:
            raise ConfigurationError(f"Configuration file not found: {config_path}") from exc
        except yaml.YAMLError as exc:
            raise ConfigurationError(f"Malformed YAML in {config_path}: {exc}") from exc
        if not isinstance(config, dict):
            raise ConfigurationError("Configuration must be a YAML mapping")

        required = {"openrouter", "orchestrator", "system_prompt", "apex_agents"}
        missing = required.difference(config)
        if missing:
            raise ConfigurationError(f"Missing required configuration keys: {sorted(missing)}")

        openrouter = config["openrouter"]
        openrouter["api_key"] = (
            os.environ.get("OPENROUTER_API_KEY") or openrouter.get("api_key")
        )
        for key in ("api_key", "base_url", "model"):
            if not openrouter.get(key):
                raise ConfigurationError(f"Missing openrouter.{key}")

        orchestrator = config["orchestrator"]
        for key in (
            "parallel_agents",
            "task_timeout",
            "aggregation_strategy",
            "question_generation_prompt",
            "synthesis_prompt",
        ):
            if key not in orchestrator:
                raise ConfigurationError(f"Missing orchestrator.{key}")
        num_agents = int(orchestrator["parallel_agents"])
        if num_agents < 1 or num_agents > 64:
            raise ConfigurationError("orchestrator.parallel_agents must be between 1 and 64")
        timeout = float(orchestrator["task_timeout"])
        if timeout <= 0 or timeout > 3600:
            raise ConfigurationError("orchestrator.task_timeout must be between 0 and 3600 seconds")

        default_role_iterations = int(
            config.get("agent", {}).get("max_iterations", 10)
        )
        profiles = config["apex_agents"]
        if not isinstance(profiles, list) or len(profiles) < num_agents:
            raise ConfigurationError("apex_agents must define every configured worker")
        for index, profile in enumerate(profiles[:num_agents]):
            # Enforce a per-role max_iterations (G1): default to the global
            # agent.max_iterations when the role does not declare one. Never 0/None.
            if not profile.get("max_iterations"):
                profile["max_iterations"] = default_role_iterations
            try:
                mi = int(profile["max_iterations"])
            except (TypeError, ValueError):
                raise ConfigurationError(
                    f"apex_agents[{index}].max_iterations must be an integer"
                )
            if mi < 1:
                raise ConfigurationError(
                    f"apex_agents[{index}].max_iterations must be >= 1"
                )
            missing_profile = {
                "role", "model", "system_prompt", "allowed_tools"
            }.difference(profile)
            if missing_profile:
                raise ConfigurationError(
                    f"apex_agents[{index}] is missing {sorted(missing_profile)}"
                )
        return config

    def update_agent_progress(
        self, agent_id: int, status: str, result: Optional[str] = None
    ) -> None:
        with self.progress_lock:
            if self.agent_progress.get(agent_id) == STATUS_TIMEOUT:
                return
            self.agent_progress[agent_id] = status
            if result is not None:
                self.agent_results[agent_id] = result

    def get_progress_status(self) -> Dict[int, str]:
        with self.progress_lock:
            return self.agent_progress.copy()

    def decompose_task(self, user_input: str, num_agents: int) -> List[str]:
        # Memoize by (num_agents, hash(user_input)) so repeated orchestrate()
        # calls with identical input skip the LLM decompose (mirrors the
        # SwarmMemory cache-key pattern).
        cache_key = hashlib.sha256(
            f"{num_agents}:{user_input}".encode("utf-8")
        ).hexdigest()
        cached = self._decompose_cache.get(cache_key)
        if cached is not None:
            return list(cached)

        openrouter = self.config["openrouter"]
        try:
            agent = OpenRouterAgent(
                self.config_path,
                silent=True,
                role="task_decomposer",
                model=openrouter["model"],
                system_prompt=(
                    "Decompose research questions. Do not assert facts or take external actions."
                ),
                allowed_tools=[],
                config=self.config,
                memory=self.memory,
            )
            prompt = self.config["orchestrator"]["question_generation_prompt"].format(
                user_input=user_input, num_agents=num_agents
            )
            response = agent.run(prompt)
            start, end = response.find("["), response.rfind("]") + 1
            if start < 0 or end <= start:
                raise ValueError("No JSON array returned")
            questions = json.loads(response[start:end])
            if (
                not isinstance(questions, list)
                or len(questions) != num_agents
                or not all(isinstance(item, str) and item.strip() for item in questions)
            ):
                raise ValueError("Question list does not match the configured worker count")
            self._decompose_cache[cache_key] = list(questions)
            return questions
        except Exception as exc:
            logger.warning("Using deterministic task decomposition: %s", exc)
            fallback = [
                FALLBACK_QUESTION_TEMPLATES[index % len(FALLBACK_QUESTION_TEMPLATES)].format(
                    topic=user_input
                )
                for index in range(num_agents)
            ]
            self._decompose_cache[cache_key] = fallback
            return fallback

    def _tier_config(self) -> Dict[str, Any]:
        """Read worker_tiers + local config from the config file."""
        tiers = self.config.get("worker_tiers", {})
        local = self.config.get("local", {})
        return {
            "local_first": set(tiers.get("local_first", [])),
            "all_openrouter": set(tiers.get("all_openrouter", [])),
            "local_enabled": bool(local.get("enabled", False)),
            "local_model": local.get("model"),
            "local_base_url": local.get("base_url"),
            "local_system_prompt": local.get("system_prompt"),
        }

    def _price_per_1k(self, model: str) -> float:
        return _MODEL_PRICE_PER_1K.get(model, 0.0)

    def _estimate_tokens(self, text: str) -> int:
        """Cheap token estimate (~4 chars/token) for telemetry only."""
        return max(1, len(text) // 4)

    def _log_telemetry(
        self,
        mission_id: int,
        role: str,
        model: str,
        tier: str,
        response: str,
        elapsed: float,
    ) -> None:
        """Persist per-worker token + cost telemetry to SQLite."""
        try:
            in_tokens = self._estimate_tokens(response)
            out_tokens = self._estimate_tokens(response)
            price = (
                LOCAL_PRICE_PER_1K
                if tier == "local"
                else self._price_per_1k(model)
            )
            cost = (in_tokens + out_tokens) * price / 1000.0
            self.memory.log_agent_run(
                mission_id,
                role,
                f"{tier}:{model}",
                response,
                elapsed,
                in_tokens=in_tokens,
                out_tokens=out_tokens,
                cost_usd=cost,
            )
        except Exception as exc:
            logger.debug("Telemetry log failed: %s", exc)

    def _inject_context(self, text: str) -> str:
        """Append Genius recall context and the tiered <memory> block to a prompt."""
        parts: List[str] = []
        if self._recall_context:
            joined = "\n".join(f"- {item}" for item in self._recall_context if item)
            if joined:
                parts.append(f"Prior related missions (recall):\n{joined}")
        if self._memory_block:
            parts.append(self._memory_block)
        if parts:
            return f"{text}\n\n" + "\n\n".join(parts)
        return text

    def _run_worker(self, agent_id: int, subtask: str) -> Dict[str, Any]:
        """Run one worker, choosing local-first vs OpenRouter per tier config."""
        self.update_agent_progress(agent_id, STATUS_PROCESSING)
        started = time.monotonic()
        profile = self.worker_profiles[agent_id]
        role = profile["role"]
        tiers = self._tier_config()
        local_first = role in tiers["local_first"]
        prompt = self._inject_context(subtask)

        # Try the local tier first for local_first roles when enabled.
        if local_first and tiers["local_enabled"]:
            try:
                local = LocalAgent(
                    self.config_path,
                    model=tiers["local_model"],
                    system_prompt=tiers["local_system_prompt"],
                )
                response = local.run(prompt)
                elapsed = time.monotonic() - started
                self.update_agent_progress(agent_id, STATUS_COMPLETED, response)
                self._log_telemetry(
                    self._current_mission_id, role, local.model, "local",
                    response, elapsed,
                )
                return {
                    "agent_id": agent_id,
                    "role": role,
                    "model": f"local:{local.model}",
                    "status": RESULT_CLASSIFICATION,
                    "result_classification": RESULT_CLASSIFICATION,
                    "review_status": REVIEW_STATUS,
                    "response": response,
                    "execution_time": elapsed,
                    "tier": "local",
                    "source_expectation": (
                        "Factual claims require a URL or precise document citation; "
                        "uncited claims remain unverified."
                    ),
                }
            except LocalAgentError as exc:
                logger.info(
                    "Local tier unavailable for %s, falling back to OpenRouter: %s",
                    role, exc,
                )

        try:
            agent = OpenRouterAgent(
                self.config_path,
                silent=True,
                role=role,
                model=profile["model"],
                system_prompt=profile["system_prompt"],
                allowed_tools=profile["allowed_tools"],
                max_iterations=profile.get("max_iterations", self.default_max_iterations),
                config=self.config,
                memory=self.memory,
            )
            response = agent.run(prompt)
            elapsed = time.monotonic() - started
            self.update_agent_progress(agent_id, STATUS_COMPLETED, response)
            self._log_telemetry(
                self._current_mission_id, role, profile["model"], "openrouter",
                response, elapsed,
            )
            return {
                "agent_id": agent_id,
                "role": role,
                "model": profile["model"],
                "status": RESULT_CLASSIFICATION,
                "result_classification": RESULT_CLASSIFICATION,
                "review_status": REVIEW_STATUS,
                "response": response,
                "execution_time": elapsed,
                "tier": "openrouter",
                "source_expectation": (
                    "Factual claims require a URL or precise document citation; "
                    "uncited claims remain unverified."
                ),
            }
        except Exception as exc:
            elapsed = time.monotonic() - started
            self.update_agent_progress(
                agent_id, f"{STATUS_FAILED_PREFIX}: {type(exc).__name__}"
            )
            return {
                "agent_id": agent_id,
                "role": role,
                "model": profile["model"],
                "status": "error",
                "result_classification": RESULT_CLASSIFICATION,
                "review_status": REVIEW_STATUS,
                "response": f"Worker failed: {exc}",
                "execution_time": elapsed,
                "tier": "openrouter",
                "result_classification": RESULT_CLASSIFICATION,
                "review_status": REVIEW_STATUS,
                "agent_id": agent_id,
                "role": role,
                "model": profile["model"],
                "status": "error",
                "source_expectation": (
                    "Factual claims require a URL or precise document citation; "
                    "uncited claims remain unverified."
                ),
            }

    # Backwards-compatible alias. The base method was renamed to _run_worker
    # when the local tier and telemetry were added; tests and external callers
    # still reference the original name.
    run_agent_parallel = _run_worker

    def _compact(self, text: str) -> str:
        """Truncate a worker response to the synthesis token budget (T1/T2)."""
        if not self.synthesis_token_budget:
            return text
        est = self._estimate_tokens(text)
        if est <= self.synthesis_token_budget:
            return text
        max_chars = int(self.synthesis_token_budget * 4)
        return text[:max_chars] + "\n...[truncated to synthesis budget]"

    def aggregate_results(self, agent_results: List[Dict[str, Any]]) -> str:
        reviewable = [
            item
            for item in agent_results
            if item.get("status") == RESULT_CLASSIFICATION
        ]
        if not reviewable:
            return (
                "RESULT CLASSIFICATION: model_inference\n"
                "REVIEW STATUS: pending_review\n\n"
                "No worker produced reviewable output. Check the bounded API errors."
            )
        # Bound each worker response before aggregation (T1/T2).
        if self.synthesis_token_budget:
            reviewable = [
                {**item, "response": self._compact(item["response"])}
                for item in reviewable
            ]
        strategy = (self.aggregation_strategy or "consensus").lower()
        if strategy == "best":
            body = self._aggregate_best(reviewable)
        elif strategy == "vote":
            body = self._aggregate_vote(reviewable)
        elif strategy == "compact":
            body = self._aggregate_compact(reviewable)
        else:  # consensus (default)
            if len(reviewable) == 1:
                body = reviewable[0]["response"]
            else:
                body = self._aggregate_consensus(reviewable)
        return (
            "RESULT CLASSIFICATION: model_inference\n"
            "REVIEW STATUS: pending_review\n\n"
            f"{body}"
        )

    def _aggregate_best(self, results: List[Dict[str, Any]]) -> str:
        """Return the single most detailed reviewable worker response."""
        best = max(results, key=lambda r: len(r.get("response", "") or ""))
        return best["response"]

    def _aggregate_vote(self, results: List[Dict[str, Any]]) -> str:
        """Token-efficient multi-perspective join without an LLM call."""
        return "\n\n".join(
            f"=== VOTE {item['role']} | unreviewed model inference ===\n{item['response']}"
            for item in results
        )

    def _aggregate_compact(self, results: List[Dict[str, Any]]) -> str:
        """Token-efficient labeled join without an LLM call."""
        return "\n\n".join(
            f"=== {item['role']} | unreviewed model inference ===\n{item['response']}"
            for item in results
        )

    def _aggregate_consensus(self, results: List[Dict[str, Any]]) -> str:
        blocks = "\n\n".join(
            (
                f"=== {item['role']} | unreviewed model inference ===\n"
                f"{item['response']}"
            )
            for item in results
        )
        prompt = self.config["orchestrator"]["synthesis_prompt"].format(
            num_responses=len(results), agent_responses=blocks
        )
        # Inject Genius recall context + tiered memory block (C1 / T3 / T4).
        extra: List[str] = []
        if self._recall_context:
            joined = "\n".join(f"- {c}" for c in self._recall_context if c)
            if joined:
                extra.append(f"Prior related missions (recall):\n{joined}")
        if self._memory_block:
            extra.append(self._memory_block)
        if extra:
            prompt = "\n\n".join(extra) + "\n\n" + prompt
        try:
            agent = OpenRouterAgent(
                self.config_path,
                silent=True,
                role="synthesis_reviewer",
                model=self.config["openrouter"]["model"],
                system_prompt=(
                    "Synthesize without converting allegations or repeated claims into facts. "
                    "Preserve disagreements, uncertainty, missing citations, and evidence gaps. "
                    "Do not recommend or take automatic external action."
                ),
                allowed_tools=[],
                config=self.config,
                memory=self.memory,
            )
            return agent.run(prompt)
        except Exception as exc:
            logger.warning("Synthesis unavailable; preserving worker outputs: %s", exc)
            return (
                "Synthesis unavailable. The following outputs remain separate, unreviewed "
                f"model inferences:\n\n{blocks}"
            )

    def _get_executor(self) -> ThreadPoolExecutor:
        """Lazily build (and reuse) a single provider-width executor.

        Reusing one executor across orchestrate() calls — e.g. every iteration
        of the Genius loop — avoids rebuilding provider threads each turn.
        """
        if self._executor is None:
            provider_width = bounded_provider_concurrency(
                self.num_agents, self.provider_concurrency_width
            )
            self._executor = ThreadPoolExecutor(max_workers=provider_width)
            import atexit

            atexit.register(self._shutdown_executor)
        return self._executor

    def _shutdown_executor(self) -> None:
        executor = self._executor
        self._executor = None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)

    def _build_memory_context(self, query: str) -> str:
        """Build a bounded <memory> block for user_id-scoped tiered memory.

        Returns "" when no user_id is set (no-op) — TieredMemory is never
        called with an empty user_id.
        """
        if not self.user_id:
            return ""
        try:
            if self._tiered_memory is None:
                self._tiered_memory = TieredMemory(
                    self.config.get("memory", {}).get("tiered_db_path", ".tiered_memory.db"),
                    tiered_config=self._tiered_config,
                )
            mem = self._tiered_memory
            block = mem.build_context(
                self.user_id, query, token_budget=self.synthesis_token_budget
            )
            return block
        except Exception as exc:
            logger.debug("Tiered memory context unavailable: %s", exc)
            return ""

    def orchestrate(
        self,
        user_input: str,
        subtasks: Optional[List[str]] = None,
        context: Optional[List[str]] = None,
    ) -> str:
        with self.progress_lock:
            self.agent_progress = {}
            self.agent_results = {}
        # Genius passes role-aligned subtasks to skip the LLM decompose (R1);
        # otherwise fall back to the base decomposition.
        if subtasks is None:
            subtasks = self.decompose_task(user_input, self.num_agents)
        subtasks = list(subtasks)[: self.num_agents]
        self._recall_context = list(context) if context else []
        self._memory_block = self._build_memory_context(user_input) if self.user_id else ""
        for index in range(self.num_agents):
            self.update_agent_progress(index, STATUS_QUEUED)

        provider_width = bounded_provider_concurrency(
            self.num_agents, self.provider_concurrency_width
        )
        turn_timeout = effective_turn_timeout(
            self.task_timeout, self.num_agents, provider_width
        )
        executor = self._get_executor()
        futures = {
            executor.submit(self.run_agent_parallel, index, subtasks[index]): index
            for index in range(self.num_agents)
        }
        results: List[Dict[str, Any]] = []
        completed = set()
        try:
            for future in as_completed(futures, timeout=turn_timeout):
                agent_id = futures[future]
                completed.add(agent_id)
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append(self._future_error(agent_id, exc))
        except FuturesTimeoutError:
            logger.warning(
                "Bounded orchestration timeout reached after %.1fs "
                "(%d logical workers / provider width %d)",
                turn_timeout,
                self.num_agents,
                provider_width,
            )
        finally:
            for future, agent_id in futures.items():
                if agent_id in completed:
                    continue
                cancelled = future.cancel()
                self.update_agent_progress(agent_id, STATUS_TIMEOUT)
                results.append(
                    {
                        "agent_id": agent_id,
                        "role": self.worker_profiles[agent_id]["role"],
                        "model": self.worker_profiles[agent_id]["model"],
                        "status": "timeout",
                        "result_classification": RESULT_CLASSIFICATION,
                        "review_status": REVIEW_STATUS,
                        "response": (
                            f"Worker exceeded the {turn_timeout:g}s orchestration timeout"
                        ),
                        "execution_time": turn_timeout,
                        "cancelled_before_start": cancelled,
                    }
                )

        results.sort(key=lambda item: item["agent_id"])
        self.last_run_results = results
        return self.aggregate_results(results)

    def _future_error(self, agent_id: int, exc: Exception) -> Dict[str, Any]:
        profile = self.worker_profiles[agent_id]
        self.update_agent_progress(
            agent_id, f"{STATUS_FAILED_PREFIX}: {type(exc).__name__}"
        )
        return {
            "agent_id": agent_id,
            "role": profile["role"],
            "model": profile["model"],
            "status": "error",
            "result_classification": RESULT_CLASSIFICATION,
            "review_status": REVIEW_STATUS,
            "response": f"Worker future failed: {exc}",
            "execution_time": 0,
        }
