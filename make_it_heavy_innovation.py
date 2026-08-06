# SPDX-License-Identifier: Proprietary
"""Interactive innovation-stage Make-It-Heavy runtime."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from adaptive_orchestrator import AdaptiveTaskOrchestrator

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
EXIT_COMMANDS = frozenset({"quit", "exit", "bye"})


def emit_failure(exc: Exception) -> int:
    print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)
    return 1


def run_once(orchestrator: AdaptiveTaskOrchestrator, query: str) -> int:
    try:
        print(orchestrator.orchestrate(query))
        return 0
    except Exception as exc:
        return emit_failure(exc)


def interactive(orchestrator: AdaptiveTaskOrchestrator) -> int:
    print("Make-It-Heavy — Adaptive Worker Innovation Loop")
    print(
        f"Initial topology: {orchestrator.num_agents} workers; "
        "every completed turn scores quality, benefit, and next topology."
    )
    while True:
        try:
            query = input("\nMission: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not query:
            continue
        if query.lower() in EXIT_COMMANDS:
            return 0
        status = run_once(orchestrator, query)
        if status:
            print("The turn failed; the previous topology remains active.", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the adaptive innovation-stage Make-It-Heavy worker loop."
    )
    parser.add_argument("query", nargs="*")
    parser.add_argument("--config", default="innovation_config.yaml")
    args = parser.parse_args()
    try:
        orchestrator = AdaptiveTaskOrchestrator(args.config)
    except Exception as exc:
        return emit_failure(exc)
    if args.query:
        return run_once(orchestrator, " ".join(args.query))
    return interactive(orchestrator)


if __name__ == "__main__":
    raise SystemExit(main())
