# SPDX-License-Identifier: Proprietary
# Copyright (c) 2026 Casey del Carpio Barton / GlacierEQ — All Rights Reserved
# Original base: Doriandarko/make-it-heavy
# All modifications and additions by GlacierEQ are proprietary.
"""
agent.py — OpenRouter Agent Core
=================================
Provides ``OpenRouterAgent``: a self-contained agentic loop connecting to any
OpenRouter-compatible LLM. Discovers tools dynamically and executes a
multi-turn conversation until the task is marked complete or max iterations
is reached.
"""

import json
import logging
import yaml
import requests
from typing import Any, Dict, List, Optional

from tools import discover_tools

log = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS: int = 10
CHAT_COMPLETIONS_PATH: str = "/chat/completions"
MARK_TASK_COMPLETE_TOOL: str = "mark_task_complete"


class OpenAI:
    """Minimal HTTP client speaking the OpenAI Chat Completions API format, targeting OpenRouter."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    class _MockMessage:
        __slots__ = ("content", "tool_calls")
        def __init__(self, content: Optional[str], tool_calls: Optional[list]) -> None:
            self.content = content
            self.tool_calls = tool_calls

    class _MockChoice:
        __slots__ = ("message",)
        def __init__(self, message: Any) -> None:
            self.message = message

    class _MockResponse:
        __slots__ = ("choices",)
        def __init__(self, choices: list) -> None:
            self.choices = choices

    class Chat:
        """Namespace mirroring ``client.chat.completions.create()``."""
        def __init__(self, client: "OpenAI") -> None:
            self._client = client
            self.completions = self._Completions(client)

        class _Completions:
            def __init__(self, client: "OpenAI") -> None:
                self._client = client

            def create(self, **kwargs: Any) -> Any:
                """POST to /chat/completions and return a mock-response object.

                Args:
                    **kwargs: Passed verbatim as JSON request body.
                Returns:
                    _MockResponse with assistant message.
                Raises:
                    requests.HTTPError: On non-2xx responses.
                    ValueError: If response body is malformed.
                """
                url = f"{self._client.base_url}{CHAT_COMPLETIONS_PATH}"
                try:
                    resp = self._client.session.post(url, json=kwargs)
                    resp.raise_for_status()
                    data: Dict[str, Any] = resp.json()
                except requests.HTTPError as exc:
                    log.error("HTTP error from OpenRouter: %s", exc)
                    raise
                except ValueError as exc:
                    log.error("Malformed JSON from OpenRouter: %s", exc)
                    raise
                try:
                    msg = data["choices"][0]["message"]
                except (KeyError, IndexError) as exc:
                    raise ValueError(f"Unexpected OpenRouter response shape: {data}") from exc
                outer = self._client
                choice = outer._MockChoice(
                    outer._MockMessage(content=msg.get("content"), tool_calls=msg.get("tool_calls"))
                )
                return outer._MockResponse([choice])

    def chat(self) -> "OpenAI.Chat":
        """Return the Chat namespace."""
        return self.Chat(self)


class OpenRouterAgent:
    """
    Self-contained agentic loop backed by OpenRouter.

    Args:
        config_path: Path to config.yaml.
        silent: Suppresses log output when used inside an orchestrator.
    """

    def __init__(self, config_path: str = "config.yaml", silent: bool = False) -> None:
        self.silent = silent
        self.config = self._load_config(config_path)
        self.client = OpenAI(
            base_url=self.config["openrouter"]["base_url"],
            api_key=self.config["openrouter"]["api_key"],
        )
        self.discovered_tools = discover_tools(self.config, silent=self.silent)
        self.tools: List[Dict[str, Any]] = [t.to_openrouter_schema() for t in self.discovered_tools.values()]
        self.tool_mapping: Dict[str, Any] = {name: tool.execute for name, tool in self.discovered_tools.items()}

    @staticmethod
    def _load_config(path: str) -> Dict[str, Any]:
        """Load and validate YAML config.

        Args:
            path: Path to config.yaml.
        Returns:
            Parsed config dict.
        Raises:
            FileNotFoundError: If config file does not exist.
            KeyError: If required keys are missing.
        """
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cfg: Dict[str, Any] = yaml.safe_load(fh)
        except FileNotFoundError:
            log.critical("Config file not found: %s", path)
            raise
        for key in ("openrouter", "system_prompt"):
            if key not in cfg:
                raise KeyError(f"Missing required config key: '{key}'")
        return cfg

    def _call_llm(self, messages: List[Dict[str, Any]]) -> Any:
        """Send message history to LLM and return response.

        Args:
            messages: Full conversation history.
        Returns:
            MockResponse from HTTP client.
        Raises:
            Exception: Any HTTP or parsing error, with context logged.
        """
        try:
            return self.client.chat().completions.create(
                model=self.config["openrouter"]["model"],
                messages=messages,
                tools=self.tools,
            )
        except Exception as exc:
            log.error("LLM call failed: %s", exc)
            raise

    def _handle_tool_call(self, tool_call: Any) -> Dict[str, Any]:
        """Execute a single tool call and return result in message format.

        Args:
            tool_call: Tool call object from assistant message.
        Returns:
            role:tool message dict ready to append to history.
        """
        tool_name: str = tool_call.function.name
        try:
            tool_args: Dict[str, Any] = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as exc:
            log.warning("Failed to parse tool arguments for '%s': %s", tool_name, exc)
            tool_args = {}

        if tool_name in self.tool_mapping:
            try:
                result = self.tool_mapping[tool_name](**tool_args)
            except Exception as exc:
                log.error("Tool '%s' raised an exception: %s", tool_name, exc)
                result = {"error": f"Tool execution failed: {exc}"}
        else:
            log.warning("Unknown tool requested: '%s'", tool_name)
            result = {"error": f"Unknown tool: {tool_name}"}

        return {"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": json.dumps(result)}

    def run(self, user_input: str) -> str:
        """Run the agentic loop for a given user prompt.

        Runs until mark_task_complete is called or max_iterations is reached.

        Args:
            user_input: The task or question to send to the agent.
        Returns:
            Concatenated assistant response text from all iterations.
        """
        max_iter: int = self.config.get("agent", {}).get("max_iterations", DEFAULT_MAX_ITERATIONS)
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.config["system_prompt"]},
            {"role": "user", "content": user_input},
        ]
        collected: List[str] = []

        for iteration in range(1, max_iter + 1):
            if not self.silent:
                log.info("Agent iteration %d/%d", iteration, max_iter)

            response = self._call_llm(messages)
            assistant_msg = response.choices[0].message
            messages.append({"role": "assistant", "content": assistant_msg.content, "tool_calls": assistant_msg.tool_calls})

            if assistant_msg.content:
                collected.append(assistant_msg.content)

            if not assistant_msg.tool_calls:
                if not self.silent:
                    log.info("No tool calls — continuing.")
                continue

            if not self.silent:
                log.info("Making %d tool call(s).", len(assistant_msg.tool_calls))

            task_done = False
            for tool_call in assistant_msg.tool_calls:
                if not self.silent:
                    log.info("  → Calling: %s", tool_call.function.name)
                messages.append(self._handle_tool_call(tool_call))
                if tool_call.function.name == MARK_TASK_COMPLETE_TOOL:
                    if not self.silent:
                        log.info("Task marked complete. Exiting.")
                    task_done = True

            if task_done:
                break

        return "\n\n".join(collected) if collected else "Maximum iterations reached without a conclusive response."
