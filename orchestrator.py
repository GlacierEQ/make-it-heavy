# SPDX-License-Identifier: Proprietary
"""Policy-bound multi-agent research orchestration."""

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
from typing import Any, Dict, List, Optional

import yaml

from agent import OpenRouterAgent

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


class ConfigurationError(Exception):
    """Raised when orchestration policy or worker configuration is invalid."""


class TaskOrchestrator:
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH, silent: bool = False):
        self.config_path = config_path
        self.silent = silent
        self.config = self._load_and_validate_config(config_path)
        orchestrator = self.config["orchestrator"]
        self.num_agents = int(orchestrator["parallel_agents"])
        self.task_timeout = float(orchestrator["task_timeout"])
        self.aggregation_strategy = orchestrator["aggregation_strategy"]
        self.worker_profiles = self.config["apex_agents"][: self.num_agents]
        self.agent_progress: Dict[int, str] = {}
        self.agent_results: Dict[int, str] = {}
        self.progress_lock = threading.Lock()
        self.last_run_results: List[Dict[str, Any]] = []

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
        if num_agents < 1 or num_agents > 16:
            raise ConfigurationError("orchestrator.parallel_agents must be between 1 and 16")
        timeout = float(orchestrator["task_timeout"])
        if timeout <= 0 or timeout > 900:
            raise ConfigurationError("orchestrator.task_timeout must be between 0 and 900 seconds")

        profiles = config["apex_agents"]
        if not isinstance(profiles, list) or len(profiles) < num_agents:
            raise ConfigurationError("apex_agents must define every configured worker")
        for index, profile in enumerate(profiles[:num_agents]):
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
            return questions
        except Exception as exc:
            logger.warning("Using deterministic task decomposition: %s", exc)
            return [
                FALLBACK_QUESTION_TEMPLATES[index % len(FALLBACK_QUESTION_TEMPLATES)].format(
                    topic=user_input
                )
                for index in range(num_agents)
            ]

    def run_agent_parallel(self, agent_id: int, subtask: str) -> Dict[str, Any]:
        self.update_agent_progress(agent_id, STATUS_PROCESSING)
        started = time.monotonic()
        profile = self.worker_profiles[agent_id]
        try:
            agent = OpenRouterAgent(
                self.config_path,
                silent=True,
                role=profile["role"],
                model=profile["model"],
                system_prompt=profile["system_prompt"],
                allowed_tools=profile["allowed_tools"],
            )
            response = agent.run(subtask)
            elapsed = time.monotonic() - started
            self.update_agent_progress(agent_id, STATUS_COMPLETED, response)
            return {
                "agent_id": agent_id,
                "role": profile["role"],
                "model": profile["model"],
                "status": RESULT_CLASSIFICATION,
                "result_classification": RESULT_CLASSIFICATION,
                "review_status": REVIEW_STATUS,
                "response": response,
                "execution_time": elapsed,
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
                "role": profile["role"],
                "model": profile["model"],
                "status": "error",
                "result_classification": RESULT_CLASSIFICATION,
                "review_status": REVIEW_STATUS,
                "response": f"Worker failed: {exc}",
                "execution_time": elapsed,
            }

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
        if len(reviewable) == 1:
            body = reviewable[0]["response"]
        else:
            body = self._aggregate_consensus(reviewable)
        return (
            "RESULT CLASSIFICATION: model_inference\n"
            "REVIEW STATUS: pending_review\n\n"
            f"{body}"
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
            )
            return agent.run(prompt)
        except Exception as exc:
            logger.warning("Synthesis unavailable; preserving worker outputs: %s", exc)
            return (
                "Synthesis unavailable. The following outputs remain separate, unreviewed "
                f"model inferences:\n\n{blocks}"
            )

    def orchestrate(self, user_input: str) -> str:
        with self.progress_lock:
            self.agent_progress = {}
            self.agent_results = {}
        subtasks = self.decompose_task(user_input, self.num_agents)
        for index in range(self.num_agents):
            self.update_agent_progress(index, STATUS_QUEUED)

        executor = ThreadPoolExecutor(max_workers=self.num_agents)
        futures = {
            executor.submit(self.run_agent_parallel, index, subtasks[index]): index
            for index in range(self.num_agents)
        }
        results: List[Dict[str, Any]] = []
        completed = set()
        try:
            for future in as_completed(futures, timeout=self.task_timeout):
                agent_id = futures[future]
                completed.add(agent_id)
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append(self._future_error(agent_id, exc))
        except FuturesTimeoutError:
            logger.warning("Bounded orchestration timeout reached after %.1fs", self.task_timeout)
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
                            f"Worker exceeded the {self.task_timeout:g}s orchestration timeout"
                        ),
                        "execution_time": self.task_timeout,
                        "cancelled_before_start": cancelled,
                    }
                )
            executor.shutdown(wait=False, cancel_futures=True)

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
