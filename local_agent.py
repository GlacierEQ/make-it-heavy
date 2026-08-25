# SPDX-License-Identifier: Proprietary
# Copyright (c) 2026 Casey del Carpio Barton / GlacierEQ — All Rights Reserved
"""
local_agent.py — Local-model tier for Make-It-Heavy.

Adds a circuit-breaker-friendly local (Ollama) agent that mirrors the
OpenRouterAgent.run() contract. Used for the cheap, high-frequency roles
(decomposition, verification, synthesis) so long runs do not depend on
network round-trips for every worker call.

Falls back to None when the local model is unavailable so the orchestrator
can transparently drop a worker back to OpenRouter.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

import yaml

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_TIMEOUT = 60.0
MAX_TIMEOUT = 300.0


def _bounded_timeout(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_TIMEOUT
    return min(max(parsed, 1.0), MAX_TIMEOUT)


class LocalAgentError(Exception):
    """Raised when the local model cannot serve a request."""


class LocalAgent:
    """Bounded Ollama-backed agent with the same run() contract as OpenRouterAgent."""

    def __init__(
        self,
        config_path: str = "config.yaml",
        *,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_iterations: int = 1,
        request_timeout: float = DEFAULT_TIMEOUT,
    ):
        self.config_path = config_path
        self.config = self._load_config(config_path)
        local = self.config.get("local", {})

        self.model = model or local.get("model") or DEFAULT_MODEL
        self.system_prompt = system_prompt or local.get("system_prompt") or (
            "You are a local swarm worker. Separate sourced observations from "
            "allegations and inferences. Express every factual claim as "
            "OBSERVED[<source-id>]: <exact claim>."
        )
        self.base_url = (local.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        self.request_timeout = _bounded_timeout(
            request_timeout or local.get("request_timeout", DEFAULT_TIMEOUT)
        )
        self.max_iterations = max(1, int(max_iterations))
        self.enabled = bool(local.get("enabled", False))

    @staticmethod
    def _load_config(config_path: str) -> dict:
        with open(config_path, "r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
        return loaded if isinstance(loaded, dict) else {}

    def _available(self) -> bool:
        """Cheap liveness check against the Ollama /api/tags endpoint."""
        if not self.enabled:
            return False
        try:
            req = urlrequest.Request(
                f"{self.base_url}/api/tags",
                method="GET",
            )
            with urlrequest.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except (urlerror.URLError, OSError, TimeoutError):
            return False

    def _chat(self, messages: List[Dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.0},
        }
        req = urlrequest.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=self.request_timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        message = (body or {}).get("message") or {}
        return str(message.get("content", "")).strip()

    def run(self, user_input: str) -> str:
        """Execute one local-model turn. Raises LocalAgentError on failure."""
        if not self.enabled:
            raise LocalAgentError("local tier disabled in config")
        if not self._available():
            raise LocalAgentError(f"Ollama unavailable at {self.base_url}")

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]
        started = time.monotonic()
        last_error: Optional[Exception] = None
        for attempt in range(self.max_iterations):
            try:
                content = self._chat(messages)
                if content:
                    return content
                last_error = LocalAgentError("empty response from local model")
            except (urlerror.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                time.sleep(min(2 ** attempt, 5))
        elapsed = time.monotonic() - started
        logger.warning("LocalAgent failed after %.1fs: %s", elapsed, last_error)
        raise LocalAgentError(f"local model error: {last_error}")


def make_local_agent(
    config_path: str = "config.yaml",
    *,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> Optional[LocalAgent]:
    """Construct a local agent, or None if the local tier is not enabled."""
    try:
        agent = LocalAgent(
            config_path=config_path,
            model=model,
            system_prompt=system_prompt,
        )
    except Exception as exc:
        logger.warning("Could not construct LocalAgent: %s", exc)
        return None
    return agent if agent.enabled else None