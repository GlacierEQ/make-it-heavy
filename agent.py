# SPDX-License-Identifier: Proprietary
"""Bounded OpenRouter agent with explicit role and tool policy binding."""

import json
import http.client
import logging
import os
import socket
import time
from typing import Iterable, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

import yaml

from tools import discover_tools

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config.yaml"
DEFAULT_MAX_ITERATIONS = 10
DEFAULT_REQUEST_TIMEOUT = 45.0
MAX_REQUEST_TIMEOUT = 120.0
DEFAULT_AGENT_TIMEOUT = 150.0
MAX_AGENT_TIMEOUT = 900.0
TOOL_MARK_TASK_COMPLETE = "mark_task_complete"
CHAT_COMPLETIONS_ENDPOINT = "/chat/completions"
MAX_ITERATIONS_FALLBACK_MSG = (
    "No reviewable model output was produced before the bounded agent loop ended."
)
AGENT_POLICY_SUFFIX = """

Runtime policy:
- Treat all generated analysis as model inference pending human review.
- Separate sourced observations from allegations, assumptions, and conclusions.
- For factual claims, provide source URLs or precise document citations when available.
- State evidence gaps, conflicts, and uncertainty. Never invent citations, facts, dates,
  deadlines, probabilities, legal conclusions, or verification.
- Do not file, publish, message, purchase, delete, modify external systems, or take any
  other external action. Produce analysis only.
""".strip()


class LLMCallError(Exception):
    """Raised when an OpenRouter request cannot return a usable response."""


class ConfigurationError(Exception):
    """Raised when agent configuration is incomplete or invalid."""


class AgentTimeoutError(Exception):
    """Raised when an agent exhausts its total wall-clock execution budget."""


class _MockMessage:
    __slots__ = ("content", "tool_calls")

    def __init__(self, content, tool_calls):
        self.content = content
        self.tool_calls = tool_calls


class _MockToolCall:
    class _Function:
        __slots__ = ("name", "arguments")

        def __init__(self, name: str, arguments: str):
            self.name = name
            self.arguments = arguments

    def __init__(self, raw: dict):
        self.id = raw.get("id", "")
        function = raw.get("function", {})
        self.function = self._Function(
            function.get("name", ""), function.get("arguments", "{}")
        )


class _MockChoice:
    __slots__ = ("message",)

    def __init__(self, message):
        self.message = message


class _MockResponse:
    __slots__ = ("choices",)

    def __init__(self, choices):
        self.choices = choices


def _bounded_timeout(value) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_REQUEST_TIMEOUT
    return min(max(parsed, 1.0), MAX_REQUEST_TIMEOUT)


def _bounded_agent_timeout(value) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_AGENT_TIMEOUT
    return min(max(parsed, 1.0), MAX_AGENT_TIMEOUT)


class OpenAI:
    """Small OpenRouter HTTP client with a bounded per-request timeout."""

    def __init__(self, base_url: str, api_key: str, request_timeout: float):
        self.base_url = base_url.rstrip("/")
        self.request_timeout = _bounded_timeout(request_timeout)
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.chat = self._Chat(self)

    class _Chat:
        def __init__(self, client):
            self.completions = self._Completions(client)

        class _Completions:
            def __init__(self, client):
                self._client = client

            def create(self, **kwargs):
                url = f"{self._client.base_url}{CHAT_COMPLETIONS_ENDPOINT}"
                request_timeout = kwargs.pop(
                    "_request_timeout", self._client.request_timeout
                )
                request_timeout = max(
                    0.1, min(float(request_timeout), self._client.request_timeout)
                )
                try:
                    request = urlrequest.Request(
                        url,
                        data=json.dumps(kwargs).encode("utf-8"),
                        headers=self._client.headers,
                        method="POST",
                    )
                    with urlrequest.urlopen(
                        request, timeout=request_timeout
                    ) as response:
                        data = json.loads(response.read().decode("utf-8"))
                    raw_message = data["choices"][0]["message"]
                except (TimeoutError, socket.timeout) as exc:
                    raise LLMCallError(
                        f"OpenRouter timed out after {request_timeout:g}s"
                    ) from exc
                except urlerror.HTTPError as exc:
                    detail = exc.read(400).decode("utf-8", errors="replace")
                    raise LLMCallError(
                        f"OpenRouter returned HTTP {exc.code}: {detail}"
                    ) from exc
                except urlerror.URLError as exc:
                    raise LLMCallError(f"OpenRouter request failed: {exc}") from exc
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    raise LLMCallError("OpenRouter returned an invalid response payload") from exc
                except (http.client.HTTPException, OSError) as exc:
                    raise LLMCallError(f"Unexpected OpenRouter transport failure: {exc}") from exc

                raw_calls = raw_message.get("tool_calls") or []
                message = _MockMessage(
                    raw_message.get("content"),
                    [_MockToolCall(call) for call in raw_calls] or None,
                )
                return _MockResponse([_MockChoice(message)])


class OpenRouterAgent:
    """Agent whose role, model, prompt, and allowed tools are immutable per run."""

    def __init__(
        self,
        config_path: str = DEFAULT_CONFIG_PATH,
        silent: bool = False,
        *,
        role: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        allowed_tools: Optional[Iterable[str]] = None,
    ):
        self.config_path = config_path
        self.silent = silent
        self.config = self._load_config(config_path)
        openrouter = self.config.get("openrouter", {})
        api_key = os.environ.get("OPENROUTER_API_KEY") or openrouter.get("api_key")
        if not openrouter.get("base_url") or not api_key:
            raise ConfigurationError("openrouter.base_url and openrouter.api_key are required")

        self.role = role or "general_researcher"
        self.model = model or openrouter.get("model")
        self.system_prompt = system_prompt or self.config.get("system_prompt")
        if not self.model or not self.system_prompt:
            raise ConfigurationError("A model and system prompt must be bound to every agent")

        self.max_iterations = max(
            1,
            min(
                int(self.config.get("agent", {}).get("max_iterations", DEFAULT_MAX_ITERATIONS)),
                30,
            ),
        )
        self.request_timeout = _bounded_timeout(
            openrouter.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)
        )
        self.agent_timeout = _bounded_agent_timeout(
            self.config.get("agent", {}).get("run_timeout", DEFAULT_AGENT_TIMEOUT)
        )
        self.client = OpenAI(
            openrouter.get("base_url", ""), api_key, self.request_timeout
        )

        discovered = discover_tools(
            self.config, silent=silent, allowlist=allowed_tools
        )
        self.tools = [tool.to_openrouter_schema() for tool in discovered.values()]
        self.tool_mapping = {
            name: tool.execute for name, tool in discovered.items()
        }

    @staticmethod
    def _load_config(config_path: str) -> dict:
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle)
        except FileNotFoundError as exc:
            raise ConfigurationError(f"Config file not found: {config_path}") from exc
        except yaml.YAMLError as exc:
            raise ConfigurationError(f"Malformed YAML in {config_path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ConfigurationError("Configuration must be a YAML mapping")
        return loaded

    def call_llm(self, messages: list, request_timeout: Optional[float] = None):
        payload = {"model": self.model, "messages": messages}
        if self.tools:
            payload["tools"] = self.tools
        if request_timeout is not None:
            payload["_request_timeout"] = request_timeout
        return self.client.chat.completions.create(**payload)

    def handle_tool_call(self, tool_call) -> dict:
        tool_name = tool_call.function.name
        try:
            arguments = json.loads(tool_call.function.arguments)
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be an object")
        except (json.JSONDecodeError, ValueError):
            arguments = {}

        if tool_name not in self.tool_mapping:
            result = {
                "success": False,
                "error": f"Tool {tool_name!r} is not allowed for role {self.role!r}",
            }
        else:
            try:
                result = self.tool_mapping[tool_name](**arguments)
            except Exception as exc:
                logger.exception("Tool %s failed", tool_name)
                result = {"success": False, "error": f"Tool execution failed: {exc}"}
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_name,
            "content": json.dumps(result),
        }

    def run(self, user_input: str) -> str:
        bound_prompt = (
            f"Assigned role: {self.role}\n\n{self.system_prompt}\n\n{AGENT_POLICY_SUFFIX}"
        )
        messages = [
            {"role": "system", "content": bound_prompt},
            {"role": "user", "content": user_input},
        ]
        response_parts = []
        deadline = time.monotonic() + self.agent_timeout

        for _ in range(self.max_iterations):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AgentTimeoutError(
                    f"Agent {self.role!r} exceeded its {self.agent_timeout:g}s budget"
                )
            response = self.call_llm(
                messages, request_timeout=min(self.request_timeout, remaining)
            )
            assistant = response.choices[0].message
            serialized_calls = (
                [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in assistant.tool_calls
                ]
                if assistant.tool_calls
                else None
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant.content,
                    "tool_calls": serialized_calls,
                }
            )
            if assistant.content:
                response_parts.append(assistant.content)
            if not assistant.tool_calls:
                break
            for tool_call in assistant.tool_calls:
                messages.append(self.handle_tool_call(tool_call))
                if tool_call.function.name == TOOL_MARK_TASK_COMPLETE:
                    return "\n\n".join(response_parts) or MAX_ITERATIONS_FALLBACK_MSG

        return "\n\n".join(response_parts) or MAX_ITERATIONS_FALLBACK_MSG
