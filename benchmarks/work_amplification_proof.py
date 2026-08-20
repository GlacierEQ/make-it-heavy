"""Deterministic local proof for the make-it-heavy thread.

This artifact exercises two runtime contracts without calling a model or any
external tool: write capability remains denied without an explicit mutation
opt-in, and an OBSERVED claim must be supported by its exact source span.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from semantic_claim_firewall import evaluate_semantic_claim_firewall
from tools import discover_tools
from tools.write_file_tool import WriteFileTool


SOURCE_POINTER = "WORK-AMPLIFICATION#POLICY"
SOURCE_SPAN = (
    "The runtime allows only explicitly allowlisted tools and denies write_file "
    "when mutation_enabled is false."
)
OBSERVED_CLAIM = (
    "The runtime allows only explicitly allowlisted tools and denies write_file "
    "when mutation_enabled is false."
)


def run() -> dict[str, Any]:
    config = {
        "tools": {
            "allowlist": ["calculate", "write_file"],
            "mutation_enabled": False,
        }
    }
    available_tools = discover_tools(config, silent=True)
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "denied-write.txt"
        write_result = WriteFileTool(config).execute(str(target), "not written")
        target_exists = target.exists()

    semantic_receipt = evaluate_semantic_claim_firewall(
        f"OBSERVED[{SOURCE_POINTER}]: {OBSERVED_CLAIM}",
        {SOURCE_POINTER: SOURCE_SPAN},
    )
    return {
        "schema": "glaciereq.make-it-heavy.work-amplification-proof.v1",
        "policy": {
            "requested_tools": config["tools"]["allowlist"],
            "available_tools": sorted(available_tools),
            "mutation_enabled": False,
            "write_denied": not write_result["success"],
            "target_created": target_exists,
        },
        "semantic_firewall": {
            "pass": semantic_receipt["pass"],
            "score": semantic_receipt["score"],
            "relation_counts": semantic_receipt["relation_counts"],
            "truth_boundary": semantic_receipt["truth_boundary"],
        },
        "truth_boundary": (
            "This proof validates local policy and source-span support only. It does not "
            "call an LLM, conduct external research, execute a write, or establish any "
            "external-world claim."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(run(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
