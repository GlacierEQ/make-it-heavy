# SPDX-License-Identifier: Proprietary
# Copyright (c) 2026 Casey del Carpio Barton / GlacierEQ — All Rights Reserved
"""
agent.py — OpenRouter AI Agent with Agentic Tool Loop

Provides a lightweight OpenAI-compatible HTTP client and a full agent
implementation that runs an agentic loop: call LLM → handle tool calls →
repeat until the task-completion tool fires or max iterations reached.

Part of the Pro-Make-It-Heavy / AEON-777 GlacierEQ framework.
"""

import json
import logging
import yaml
import requests

from tools import discover_tools

# ─── Module-level logger ──────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────
DEFAULT_CONFIG_PATH: str = "config.yaml"
DEFAULT_MAX_ITERATIONS: int = 10
TOOL_MARK_TASK_COMPLETE: str = "mark_task_complete"
ROLE_SYSTEM: str = "system"
ROLE_USER: str = "user"
ROLE_ASSISTANT: str = "assistant"
ROLE_TOOL: str = "tool"
CHAT_COMPLETIONS_ENDPOINT: str = "/chat/completions"
CONTENT_TYPE_JSON: str = "application/json"
MAX_ITERATIONS_FALLBACK_MSG: str = (
    "Maximum iterations reached. The agent may be stuck in a loop or the task "
    "requires a higher max_iterations setting in config.yaml."
)


class LLMCallError(Exception):
    """Raised when the OpenRouter API call fails after exhausting retries."""


class ToolExecutionError(Exception):
    """Raised when a tool invocation raises an unexpected exception."""


class ConfigurationError(Exception):
    """Raised when required configuration keys are missing or invalid."""


# ─── Lightweight OpenRouter HTTP Client ──────────────────────────────────────


class _MockMessage:
    """
    Minimal message object that mirrors the OpenAI SDK's response.choices[0].message.

    Why: We use a direct requests.Session rather than the openai package to avoid
    a heavy external dependency. This mock preserves the same attribute interface
    so the rest of the agent code needs no conditional branching.

    Attributes:
        content: The text content of the assistant's response (may be None).
        tool_calls: List of raw tool call dicts from the API (may be None).
    """

    __slots__ = ("content", "tool_calls")

    def __init__(self, content, tool_calls) -> None:  # noqa: ANN001
        self.content = content
        self.tool_calls = tool_calls


class _MockToolCall:
    """
    Minimal tool-call object that mirrors openai.types.chat.ChatCompletionMessageToolCall.

    Attributes:
        id: The unique tool call identifier string.
        function: An object with .name (str) and .arguments (str) attributes.
    """

    class _Function:
        __slots__ = ("name", "arguments")

        def __init__(self, name: str, arguments: str) -> None:
            self.name = name
            self.arguments = arguments

    def __init__(self, raw: dict) -> None:
        self.id: str = raw.get("id", "")
        fn = raw.get("function", {})
        self.function = self._Function(
            name=fn.get("name", ""),
            arguments=fn.get("arguments", "{}"),
        )


class _MockChoice:
    """Single choice wrapper aligning with openai.types.chat.ChatCompletion."""

    __slots__ = ("message",)

    def __init__(self, message: _MockMessage) -> None:
        self.message = message


class _MockResponse:
    """Top-level response wrapper aligning with openai.types.chat.ChatCompletion."""

    __slots__ = ("choices",)

    def __init__(self, choices) -> None:  # noqa: ANN001
        self.choices = choices


class OpenAI:
    """
    Lightweight OpenRouter HTTP client that mimics the openai.OpenAI interface.

    Uses a persistent requests.Session for connection pooling, significantly
    reducing overhead when the agent makes many sequential LLM calls.

    Args:
        base_url: Base URL for the OpenRouter API (e.g. https://openrouter.ai/api/v1).
        api_key: Bearer token for authentication.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url: str = base_url.rstrip("/")
        self.api_key: str = api_key

        self._session: requests.Session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": CONTENT_TYPE_JSON,
        })
        logger.debug("OpenAI client initialised — base_url=%s", self.base_url)

    def chat(self) -> "OpenAI._Chat":
        """Return a Chat interface object bound to this client."""
        return self._Chat(self)

    class _Chat:
        """Nested chat namespace — mirrors openai.OpenAI().chat."""

        def __init__(self, client: "OpenAI") -> None:
            self._client = client
            self.completions = self._Completions(client)

        class _Completions:
            """
            Completions endpoint wrapper — mirrors openai.OpenAI().chat.completions.

            Converts the raw OpenRouter JSON response into mock SDK objects so
            callers can use the same attribute-access pattern as the official SDK.
            """

            def __init__(self, client: "OpenAI") -> None:
                self._client = client

            def create(self, **kwargs) -> _MockResponse:  # noqa: ANN003
                """
                POST a chat-completion request to OpenRouter and return a mock response.

                Args:
                    **kwargs: Same keyword arguments as openai.chat.completions.create()
                              (model, messages, tools, etc.)

                Returns:
                    _MockResponse with .choices[0].message mirroring the SDK interface.

                Raises:
                    LLMCallError: If the HTTP request fails or returns a non-2xx status.
                """
                url = f"{self._client.base_url}{CHAT_COMPLETIONS_ENDPOINT}"
                try:
                    http_resp = self._client._session.post(url, json=kwargs, timeout=120)
                    http_resp.raise_for_status()
                except requests.exceptions.Timeout as exc:
                    raise LLMCallError(
                        f"OpenRouter API timed out after 120s at {url}"
                    ) from exc
                except requests.exceptions.ConnectionError as exc:
                    raise LLMCallError(
                        f"Network error connecting to OpenRouter at {url}: {exc}"
                    ) from exc
                except requests.exceptions.HTTPError as exc:
                    raise LLMCallError(
                        f"OpenRouter returned HTTP {exc.response.status_code}: "
                        f"{exc.response.text[:400]}"
                    ) from exc

                data: dict = http_resp.json()

                # Parse tool_calls into typed mock objects (or None)
                raw_msg = data["choices"][0]["message"]
                raw_tool_calls = raw_msg.get("tool_calls")
                tool_calls = (
                    [_MockToolCall(tc) for tc in raw_tool_calls]
                    if raw_tool_calls
                    else None
                )

                message = _MockMessage(
                    content=raw_msg.get("content"),
                    tool_calls=tool_calls,
                )
                return _MockResponse([_MockChoice(message)])


# ─── Agent ────────────────────────────────────────────────────────────────────


class OpenRouterAgent:
    """
    Stateful AI agent that runs an agentic loop via the OpenRouter API.

    On each call to .run(), the agent:
    1. Initialises a conversation with the system prompt + user message.
    2. Calls the LLM, which may respond with text and/or tool calls.
    3. Executes any requested tools and appends results to the conversation.
    4. Repeats until `mark_task_complete` is invoked or max_iterations reached.
    5. Returns all accumulated assistant text content as the final answer.

    Tools are auto-discovered from the `tools/` directory at init time, making
    the tool set hot-swappable without code changes.

    Args:
        config_path: Path to the YAML configuration file.
        silent: If True, only WARNING+ logs are emitted (suitable for parallel use).
    """

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH, silent: bool = False) -> None:
        self.config_path = config_path
        self.silent = silent

        self.config: dict = self._load_config(config_path)
        self.max_iterations: int = self.config.get("agent", {}).get(
            "max_iterations", DEFAULT_MAX_ITERATIONS
        )

        # Initialise OpenRouter HTTP client
        or_cfg = self.config.get("openrouter", {})
        self.client = OpenAI(
            base_url=or_cfg.get("base_url", ""),
            api_key=or_cfg.get("api_key", ""),
        )

        # Discover and register tools from the tools/ directory
        self.discovered_tools = discover_tools(self.config, silent=self.silent)
        self.tools: list = [t.to_openrouter_schema() for t in self.discovered_tools.values()]
        self.tool_mapping: dict = {
            name: tool.execute for name, tool in self.discovered_tools.items()
        }

        logger.debug(
            "OpenRouterAgent ready — model=%s, tools=%s, max_iter=%d",
            or_cfg.get("model", "unset"),
            list(self.tool_mapping.keys()),
            self.max_iterations,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _load_config(self, config_path: str) -> dict:
        """
        Load YAML configuration from disk.

        Args:
            config_path: Filesystem path to the config file.

        Returns:
            Parsed configuration dictionary.

        Raises:
            ConfigurationError: If the file is missing or YAML is malformed.
        """
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh)
        except FileNotFoundError as exc:
            raise ConfigurationError(
                f"Config file not found: {config_path}. "
                "Ensure config.yaml exists and your API keys are set."
            ) from exc
        except yaml.YAMLError as exc:
            raise ConfigurationError(f"Malformed YAML in {config_path}: {exc}") from exc

    def call_llm(self, messages: list) -> _MockResponse:
        """
        Make a single chat-completion call to the OpenRouter API.

        Args:
            messages: Full conversation history to send (role/content dicts).

        Returns:
            _MockResponse with the LLM's response.

        Raises:
            LLMCallError: If the API call fails for any reason.
        """
        model: str = self.config["openrouter"]["model"]
        logger.debug("LLM call — model=%s, messages=%d", model, len(messages))
        try:
            return self.client.chat().completions.create(
                model=model,
                messages=messages,
                tools=self.tools,
            )
        except LLMCallError:
            raise  # Already typed — re-raise as-is
        except Exception as exc:
            raise LLMCallError(
                f"Unexpected error calling OpenRouter ({model}): {exc}"
            ) from exc

    def handle_tool_call(self, tool_call: _MockToolCall) -> dict:
        """
        Execute a single tool call and return a properly formatted tool message.

        Looks up the tool by name in self.tool_mapping, parses the JSON
        arguments, calls the function, and wraps the result for the conversation.
        Unknown tools and execution errors are handled gracefully and reported
        back to the LLM so it can recover.

        Args:
            tool_call: A _MockToolCall object from the LLM response.

        Returns:
            Dict with role="tool", tool_call_id, name, and JSON-encoded content.
        """
        tool_name: str = tool_call.function.name
        tool_call_id: str = tool_call.id

        try:
            tool_args: dict = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in tool arguments for %s: %s", tool_name, exc)
            tool_args = {}

        logger.debug("Executing tool: %s(%s)", tool_name, list(tool_args.keys()))

        try:
            if tool_name in self.tool_mapping:
                tool_result = self.tool_mapping[tool_name](**tool_args)
            else:
                logger.warning("Unknown tool requested: %s", tool_name)
                tool_result = {
                    "error": f"Unknown tool '{tool_name}'. "
                    f"Available tools: {list(self.tool_mapping.keys())}"
                }
        except TypeError as exc:
            # Wrong args signature — recoverable
            logger.error("Tool %s called with wrong arguments: %s", tool_name, exc)
            tool_result = {
                "error": f"Tool '{tool_name}' received invalid arguments: {exc}"
            }
        except Exception as exc:
            logger.error("Tool %s raised an exception: %s", tool_name, exc, exc_info=True)
            tool_result = {
                "error": f"Tool '{tool_name}' execution failed: {type(exc).__name__}: {exc}"
            }

        return {
            "role": ROLE_TOOL,
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": json.dumps(tool_result),
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def run(self, user_input: str) -> str:
        """
        Run the full agentic loop for a given user query.

        Initialises the conversation, then iteratively calls the LLM and
        executes any tool calls until:
        - The `mark_task_complete` tool is invoked, OR
        - max_iterations is exhausted.

        Accumulates ALL assistant text content across iterations and returns
        it as the final answer, giving rich multi-step reasoning in the output.

        Args:
            user_input: The user's question or instruction.

        Returns:
            All accumulated assistant text content joined by double newlines.
            Returns a fallback message if the agent produces no content at all.
        """
        messages: list = [
            {"role": ROLE_SYSTEM, "content": self.config["system_prompt"]},
            {"role": ROLE_USER, "content": user_input},
        ]

        full_response_parts: list[str] = []

        for iteration in range(1, self.max_iterations + 1):
            logger.debug("Agent iteration %d/%d", iteration, self.max_iterations)

            # ── LLM call ──────────────────────────────────────────────────────
            try:
                response = self.call_llm(messages)
            except LLMCallError as exc:
                logger.error("LLM call failed on iteration %d: %s", iteration, exc)
                # Return whatever we have so far rather than crashing
                break

            assistant_message = response.choices[0].message

            # Append assistant turn to conversation history
            messages.append({
                "role": ROLE_ASSISTANT,
                "content": assistant_message.content,
                "tool_calls": (
                    [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_message.tool_calls
                    ]
                    if assistant_message.tool_calls
                    else None
                ),
            })

            # Capture text content
            if assistant_message.content:
                full_response_parts.append(assistant_message.content)

            # ── Tool calls ────────────────────────────────────────────────────
            if assistant_message.tool_calls:
                logger.debug(
                    "Iteration %d: %d tool call(s) requested",
                    iteration,
                    len(assistant_message.tool_calls),
                )

                for tool_call in assistant_message.tool_calls:
                    tool_result_msg = self.handle_tool_call(tool_call)
                    messages.append(tool_result_msg)

                    # Check for task completion signal
                    if tool_call.function.name == TOOL_MARK_TASK_COMPLETE:
                        logger.info(
                            "Task marked complete by agent on iteration %d/%d",
                            iteration,
                            self.max_iterations,
                        )
                        return "\n\n".join(full_response_parts)
            else:
                logger.debug("Iteration %d: no tool calls — continuing loop", iteration)

        # Max iterations reached
        if full_response_parts:
            logger.warning(
                "Max iterations (%d) reached — returning accumulated content (%d chars)",
                self.max_iterations,
                sum(len(p) for p in full_response_parts),
            )
            return "\n\n".join(full_response_parts)

        logger.error("Agent produced no content after %d iterations", self.max_iterations)
        return MAX_ITERATIONS_FALLBACK_MSG