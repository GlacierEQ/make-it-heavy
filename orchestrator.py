# SPDX-License-Identifier: Proprietary
# Copyright (c) 2026 Casey del Carpio Barton / GlacierEQ — All Rights Reserved
"""
orchestrator.py — Multi-Agent Task Orchestrator

Coordinates parallel execution of specialized AI agents, dynamically decomposes
user queries into targeted sub-questions, and synthesizes results into a
comprehensive final answer using the configured aggregation strategy.

Part of the Pro-Make-It-Heavy / AEON-777 GlacierEQ framework.
"""

import json
import logging
import yaml
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from typing import List, Dict, Any, Optional

from agent import OpenRouterAgent

# ─── Module-level logger (replaces all bare print() calls) ───────────────────
logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────
DEFAULT_CONFIG_PATH: str = "config.yaml"
STATUS_QUEUED: str = "QUEUED"
STATUS_PROCESSING: str = "PROCESSING..."
STATUS_COMPLETED: str = "COMPLETED"
STATUS_FAILED_PREFIX: str = "FAILED"
STATUS_TIMEOUT: str = "TIMEOUT"
AGGREGATION_CONSENSUS: str = "consensus"
TOOL_MARK_TASK_COMPLETE: str = "mark_task_complete"

# Required config keys validated at startup
REQUIRED_CONFIG_KEYS: List[str] = [
    "openrouter",
    "orchestrator",
    "system_prompt",
]
REQUIRED_OPENROUTER_KEYS: List[str] = ["api_key", "base_url", "model"]
REQUIRED_ORCHESTRATOR_KEYS: List[str] = [
    "parallel_agents",
    "task_timeout",
    "aggregation_strategy",
    "question_generation_prompt",
    "synthesis_prompt",
]

# Fallback decomposition templates when AI question generation fails
FALLBACK_QUESTION_TEMPLATES: List[str] = [
    "Research comprehensive information about: {topic}",
    "Analyze and provide insights about: {topic}",
    "Find alternative perspectives on: {topic}",
    "Verify and cross-check facts about: {topic}",
    "Examine strategic implications of: {topic}",
    "Identify key risks and opportunities regarding: {topic}",
    "Provide a technical deep-dive on: {topic}",
    "Synthesize historical context and precedents for: {topic}",
]


class ConfigurationError(Exception):
    """Raised when required configuration keys are missing or invalid."""


class AgentExecutionError(Exception):
    """Raised when an individual agent fails to execute its subtask."""


class SynthesisError(Exception):
    """Raised when the synthesis agent fails to aggregate results."""


class TaskOrchestrator:
    """
    Multi-agent orchestration engine for the AEON-777 / Make-It-Heavy framework.

    Responsible for:
    1. Validating configuration at startup (fail-fast).
    2. Decomposing a user query into N specialized sub-questions via an AI agent.
    3. Running N parallel agents, each tackling one sub-question.
    4. Aggregating all agent responses into a single coherent final answer.
    5. Providing thread-safe progress tracking for live UI updates.

    Args:
        config_path: Path to the YAML configuration file.
        silent: If True, suppresses debug-level log output from sub-agents.
    """

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH, silent: bool = False) -> None:
        self.config_path = config_path
        self.silent = silent

        # Load and validate configuration
        self.config: Dict[str, Any] = self._load_and_validate_config(config_path)

        # Extract orchestrator settings
        orch_cfg = self.config["orchestrator"]
        self.num_agents: int = orch_cfg["parallel_agents"]
        self.task_timeout: int = orch_cfg["task_timeout"]
        self.aggregation_strategy: str = orch_cfg["aggregation_strategy"]

        # Thread-safe progress tracking
        self.agent_progress: Dict[int, str] = {}
        self.agent_results: Dict[int, str] = {}
        self.progress_lock: threading.Lock = threading.Lock()

        logger.info(
            "TaskOrchestrator initialized — %d parallel agents, timeout=%ds, strategy=%s",
            self.num_agents,
            self.task_timeout,
            self.aggregation_strategy,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Configuration
    # ──────────────────────────────────────────────────────────────────────────

    def _load_and_validate_config(self, config_path: str) -> Dict[str, Any]:
        """
        Load configuration from YAML and validate all required keys are present.

        Raises ConfigurationError with a clear message if any required key is
        absent, preventing cryptic KeyError crashes at runtime.

        Args:
            config_path: Filesystem path to the YAML config file.

        Returns:
            Validated configuration dictionary.

        Raises:
            ConfigurationError: If the file is missing or required keys absent.
            yaml.YAMLError: If the file is malformed YAML.
        """
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                config = yaml.safe_load(fh)
        except FileNotFoundError as exc:
            raise ConfigurationError(
                f"Configuration file not found: {config_path}. "
                "Create it from config.yaml.example and set your API keys."
            ) from exc
        except yaml.YAMLError as exc:
            raise ConfigurationError(f"Malformed YAML in {config_path}: {exc}") from exc

        # Validate top-level keys
        missing_top = [k for k in REQUIRED_CONFIG_KEYS if k not in config]
        if missing_top:
            raise ConfigurationError(
                f"Missing required top-level config keys: {missing_top}. "
                f"Check {config_path}."
            )

        # Validate openrouter sub-keys
        or_cfg = config.get("openrouter", {})
        missing_or = [k for k in REQUIRED_OPENROUTER_KEYS if not or_cfg.get(k)]
        if missing_or:
            raise ConfigurationError(
                f"Missing or empty openrouter config keys: {missing_or}. "
                "Set your OpenRouter API key in config.yaml."
            )

        # Validate orchestrator sub-keys
        orch = config.get("orchestrator", {})
        missing_orch = [k for k in REQUIRED_ORCHESTRATOR_KEYS if k not in orch]
        if missing_orch:
            raise ConfigurationError(
                f"Missing orchestrator config keys: {missing_orch}. "
                f"Check the 'orchestrator' section in {config_path}."
            )

        logger.debug("Configuration validated successfully from %s", config_path)
        return config

    # ──────────────────────────────────────────────────────────────────────────
    # Task Decomposition
    # ──────────────────────────────────────────────────────────────────────────

    def decompose_task(self, user_input: str, num_agents: int) -> List[str]:
        """
        Use an AI agent to dynamically generate N specialized research questions
        from the user's input, each targeting a different analytical angle.

        If the AI call fails or returns an unexpected format, a graceful fallback
        generates simple variation questions from predefined templates.

        Args:
            user_input: The raw user query to decompose.
            num_agents: How many sub-questions to generate (one per agent).

        Returns:
            List of N question strings ready for individual agents.
        """
        logger.info("Decomposing task into %d sub-questions for: %.80s…", num_agents, user_input)

        # Spin up a lightweight question-generation agent (no task-complete tool)
        try:
            question_agent = OpenRouterAgent(
                config_path=self.config_path, silent=True
            )
        except Exception as exc:
            logger.warning("Failed to initialize question agent: %s — using fallback", exc)
            return self._fallback_decomposition(user_input, num_agents)

        # Strip mark_task_complete so the agent just returns JSON
        question_agent.tools = [
            t for t in question_agent.tools
            if t.get("function", {}).get("name") != TOOL_MARK_TASK_COMPLETE
        ]
        question_agent.tool_mapping = {
            name: fn
            for name, fn in question_agent.tool_mapping.items()
            if name != TOOL_MARK_TASK_COMPLETE
        }

        prompt_template: str = self.config["orchestrator"]["question_generation_prompt"]
        generation_prompt = prompt_template.format(
            user_input=user_input,
            num_agents=num_agents,
        )

        try:
            response: str = question_agent.run(generation_prompt)

            # Extract JSON from response (may contain surrounding text)
            json_start = response.find("[")
            json_end = response.rfind("]") + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON array found in question-generation response")

            questions: List[str] = json.loads(response[json_start:json_end])

            if not isinstance(questions, list) or len(questions) != num_agents:
                raise ValueError(
                    f"Expected list of {num_agents} questions, "
                    f"got {type(questions).__name__} with length {len(questions) if isinstance(questions, list) else 'N/A'}"
                )

            logger.info("Successfully generated %d sub-questions via AI", len(questions))
            return questions

        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "AI question generation failed (%s) — activating fallback decomposition", exc
            )
            return self._fallback_decomposition(user_input, num_agents)
        except Exception as exc:
            logger.error(
                "Unexpected error during task decomposition: %s — activating fallback", exc,
                exc_info=True,
            )
            return self._fallback_decomposition(user_input, num_agents)

    def _fallback_decomposition(self, user_input: str, num_agents: int) -> List[str]:
        """
        Generate simple question variations when AI decomposition is unavailable.

        Uses the predefined FALLBACK_QUESTION_TEMPLATES, cycling through them
        if more agents are requested than templates exist.

        Args:
            user_input: The original user query.
            num_agents: How many questions to produce.

        Returns:
            List of N fallback question strings.
        """
        questions = []
        for i in range(num_agents):
            template = FALLBACK_QUESTION_TEMPLATES[i % len(FALLBACK_QUESTION_TEMPLATES)]
            questions.append(template.format(topic=user_input))
        logger.debug("Fallback decomposition produced %d questions", len(questions))
        return questions

    # ──────────────────────────────────────────────────────────────────────────
    # Progress Tracking
    # ──────────────────────────────────────────────────────────────────────────

    def update_agent_progress(
        self,
        agent_id: int,
        status: str,
        result: Optional[str] = None,
    ) -> None:
        """
        Thread-safe update of an individual agent's progress status and result.

        Args:
            agent_id: Zero-based index of the agent being updated.
            status: Human-readable status string (e.g. STATUS_PROCESSING).
            result: Optional result string to store when the agent completes.
        """
        with self.progress_lock:
            self.agent_progress[agent_id] = status
            if result is not None:
                self.agent_results[agent_id] = result

    def get_progress_status(self) -> Dict[int, str]:
        """
        Return a snapshot of all agent progress states, thread-safely.

        Returns:
            Dictionary mapping agent_id (int) → status string.
        """
        with self.progress_lock:
            return self.agent_progress.copy()

    # ──────────────────────────────────────────────────────────────────────────
    # Parallel Agent Execution
    # ──────────────────────────────────────────────────────────────────────────

    def run_agent_parallel(self, agent_id: int, subtask: str) -> Dict[str, Any]:
        """
        Execute a single agent on its assigned subtask in a thread-pool worker.

        Marks progress as PROCESSING on start, COMPLETED on success, or
        FAILED on error. Returns a structured result dictionary regardless of
        outcome, ensuring the aggregation step always receives valid data.

        Args:
            agent_id: Zero-based index of this agent.
            subtask: The specific research question assigned to this agent.

        Returns:
            Dictionary with keys:
                - agent_id (int)
                - status ("success" | "error")
                - response (str)
                - execution_time (float, seconds)
        """
        self.update_agent_progress(agent_id, STATUS_PROCESSING)
        logger.debug("Agent %d starting subtask: %.80s…", agent_id + 1, subtask)
        start_time = time.monotonic()

        try:
            agent = OpenRouterAgent(config_path=self.config_path, silent=True)
            response: str = agent.run(subtask)
            execution_time = time.monotonic() - start_time

            self.update_agent_progress(agent_id, STATUS_COMPLETED, response)
            logger.info(
                "Agent %d completed in %.1fs (%.0f chars)",
                agent_id + 1,
                execution_time,
                len(response),
            )

            return {
                "agent_id": agent_id,
                "status": "success",
                "response": response,
                "execution_time": execution_time,
            }

        except Exception as exc:
            execution_time = time.monotonic() - start_time
            error_msg = f"Agent {agent_id + 1} failed after {execution_time:.1f}s: {exc}"

            logger.error("Agent %d execution error: %s", agent_id + 1, exc, exc_info=True)
            self.update_agent_progress(
                agent_id, f"{STATUS_FAILED_PREFIX}: {type(exc).__name__}"
            )

            return {
                "agent_id": agent_id,
                "status": "error",
                "response": error_msg,
                "execution_time": execution_time,
            }

    # ──────────────────────────────────────────────────────────────────────────
    # Result Aggregation
    # ──────────────────────────────────────────────────────────────────────────

    def aggregate_results(self, agent_results: List[Dict[str, Any]]) -> str:
        """
        Combine results from all parallel agents into one comprehensive answer.

        Routes to the appropriate aggregation implementation based on the
        configured strategy. Only successful results are passed to synthesis;
        failed agents are logged and skipped gracefully.

        Args:
            agent_results: List of result dicts from run_agent_parallel().

        Returns:
            Final synthesized answer string.
        """
        successful = [r for r in agent_results if r["status"] == "success"]
        failed_count = len(agent_results) - len(successful)

        if failed_count > 0:
            logger.warning(
                "%d of %d agents failed — synthesizing from %d successful results",
                failed_count,
                len(agent_results),
                len(successful),
            )

        if not successful:
            logger.error("All %d agents failed — returning error message", len(agent_results))
            return (
                "⚠️ All agents failed to produce results. "
                "Check your OpenRouter API key and network connectivity, "
                "then try again."
            )

        responses: List[str] = [r["response"] for r in successful]

        if self.aggregation_strategy == AGGREGATION_CONSENSUS:
            return self._aggregate_consensus(responses, successful)

        # Default: consensus (extensible for future strategies)
        logger.debug(
            "Unknown aggregation strategy '%s' — defaulting to consensus",
            self.aggregation_strategy,
        )
        return self._aggregate_consensus(responses, successful)

    def _aggregate_consensus(
        self,
        responses: List[str],
        results: List[Dict[str, Any]],
    ) -> str:
        """
        Synthesize multiple agent responses into a single coherent answer using
        a dedicated synthesis AI agent.

        If only one response is available (e.g., all but one agent failed),
        returns it directly without an extra synthesis call.

        On synthesis failure, falls back to a clearly labelled concatenation of
        all individual responses rather than returning an error.

        Args:
            responses: List of successful agent response strings.
            results: Full result dicts (used for logging context).

        Returns:
            Synthesized or concatenated final answer string.
        """
        if len(responses) == 1:
            logger.debug("Single response available — skipping synthesis agent")
            return responses[0]

        logger.info("Launching synthesis agent for %d responses", len(responses))

        # Build the combined agent-responses block
        agent_responses_text = "".join(
            f"=== AGENT {i} RESPONSE ===\n{resp}\n\n"
            for i, resp in enumerate(responses, start=1)
        )

        synthesis_prompt_template: str = self.config["orchestrator"]["synthesis_prompt"]
        synthesis_prompt = synthesis_prompt_template.format(
            num_responses=len(responses),
            agent_responses=agent_responses_text,
        )

        try:
            synthesis_agent = OpenRouterAgent(config_path=self.config_path, silent=True)
            # Remove all tools so synthesis agent produces direct text output
            synthesis_agent.tools = []
            synthesis_agent.tool_mapping = {}

            final_answer: str = synthesis_agent.run(synthesis_prompt)
            logger.info(
                "Synthesis complete — final answer: %d chars", len(final_answer)
            )
            return final_answer

        except Exception as exc:
            logger.error(
                "Synthesis agent failed: %s — falling back to concatenated responses",
                exc,
                exc_info=True,
            )
            # Graceful fallback: return labelled concatenation
            combined = []
            for i, resp in enumerate(responses, start=1):
                combined.append(f"=== Agent {i} Response ===")
                combined.append(resp)
                combined.append("")
            return "\n".join(combined)

    # ──────────────────────────────────────────────────────────────────────────
    # Main Orchestration Entry Point
    # ──────────────────────────────────────────────────────────────────────────

    def orchestrate(self, user_input: str) -> str:
        """
        Full orchestration pipeline: decompose → parallel execute → aggregate.

        Steps:
        1. Reset progress tracking state.
        2. Decompose user_input into num_agents sub-questions.
        3. Initialize all agent slots as QUEUED.
        4. Execute all agents in parallel via ThreadPoolExecutor.
        5. Collect results (handling timeouts gracefully per-agent).
        6. Sort results by agent_id for deterministic output order.
        7. Aggregate and return the final answer.

        Args:
            user_input: The raw user query to process.

        Returns:
            Comprehensive synthesized answer string from all agents.
        """
        logger.info(
            "Orchestration START — %d agents, query: %.120s…",
            self.num_agents,
            user_input,
        )
        pipeline_start = time.monotonic()

        # Reset state for this run
        with self.progress_lock:
            self.agent_progress = {}
            self.agent_results = {}

        # Decompose task
        subtasks = self.decompose_task(user_input, self.num_agents)

        # Initialise progress slots
        for i in range(self.num_agents):
            self.update_agent_progress(i, STATUS_QUEUED)

        # Execute agents in parallel
        agent_results: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=self.num_agents) as executor:
            future_to_agent: Dict = {
                executor.submit(self.run_agent_parallel, i, subtasks[i]): i
                for i in range(self.num_agents)
            }

            try:
                for future in as_completed(future_to_agent, timeout=self.task_timeout):
                    agent_id = future_to_agent[future]
                    try:
                        result = future.result()
                        agent_results.append(result)
                    except Exception as exc:
                        logger.error(
                            "Agent %d future raised exception: %s",
                            agent_id + 1,
                            exc,
                            exc_info=True,
                        )
                        self.update_agent_progress(
                            agent_id, f"{STATUS_FAILED_PREFIX}: {type(exc).__name__}"
                        )
                        agent_results.append({
                            "agent_id": agent_id,
                            "status": "error",
                            "response": f"Agent {agent_id + 1} raised: {exc}",
                            "execution_time": 0,
                        })

            except FuturesTimeoutError:
                logger.warning(
                    "Global timeout (%ds) reached — collecting partial results",
                    self.task_timeout,
                )
                # Collect any futures that timed out
                for future, agent_id in future_to_agent.items():
                    if future not in [f for f in future_to_agent if f.done()]:
                        self.update_agent_progress(agent_id, STATUS_TIMEOUT)
                        agent_results.append({
                            "agent_id": agent_id,
                            "status": "error",
                            "response": (
                                f"Agent {agent_id + 1} timed out after {self.task_timeout}s"
                            ),
                            "execution_time": self.task_timeout,
                        })

        # Sort for consistent ordering
        agent_results.sort(key=lambda x: x["agent_id"])

        total_time = time.monotonic() - pipeline_start
        success_count = sum(1 for r in agent_results if r["status"] == "success")
        logger.info(
            "Orchestration complete in %.1fs — %d/%d agents succeeded",
            total_time,
            success_count,
            self.num_agents,
        )

        return self.aggregate_results(agent_results)