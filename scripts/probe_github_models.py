#!/usr/bin/env python3
"""Probe a bounded GitHub Models candidate set and select one usable model."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

CANDIDATES = (
    "openai/gpt-4.1",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "microsoft/Phi-4",
    "meta/Llama-3.3-70B-Instruct",
)
ENDPOINT = "https://models.github.ai/inference/chat/completions"


def probe(model: str, token: str) -> Dict[str, Any]:
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "user", "content": "Reply exactly: turn7-provider-ok"}
            ],
            "temperature": 0,
            "max_tokens": 20,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "GlacierEQ-Make-It-Heavy-Turn7",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.load(response)
        content = str(body["choices"][0]["message"]["content"])
        return {
            "model": model,
            "status": "PASS" if "turn7-provider-ok" in content.lower() else "BAD_OUTPUT",
            "http_status": 200,
            "output_excerpt": content[:160],
        }
    except urllib.error.HTTPError as exc:
        raw = exc.read(1200).decode("utf-8", errors="replace")
        return {
            "model": model,
            "status": "HTTP_ERROR",
            "http_status": exc.code,
            "response_excerpt": raw[:1000],
        }
    except Exception as exc:
        return {
            "model": model,
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    token = os.environ.get("GITHUB_MODELS_TOKEN", "").strip()
    if not token:
        raise SystemExit("GITHUB_MODELS_TOKEN is empty")

    results: List[Dict[str, Any]] = []
    selected = None
    for model in CANDIDATES:
        result = probe(model, token)
        results.append(result)
        if result["status"] == "PASS":
            selected = model
            break

    receipt = {
        "schema": "glaciereq.make-it-heavy.github-models-probe.v1",
        "endpoint": ENDPOINT,
        "candidate_count": len(CANDIDATES),
        "attempted_count": len(results),
        "selected_model": selected,
        "status": "PASS" if selected else "BLOCKED_PROVIDER",
        "results": results,
        "truth_boundary": (
            "This receipt establishes only whether the current GitHub Actions identity "
            "can obtain one bounded inference response from a candidate model."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if selected:
        Path("/tmp/turn7-selected-model.txt").write_text(selected + "\n")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
