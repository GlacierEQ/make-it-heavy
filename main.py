# SPDX-License-Identifier: Proprietary
# Copyright (c) 2026 Casey del Carpio Barton / GlacierEQ — All Rights Reserved
"""
main.py — Single-Agent CLI

Lightweight entry point for running a single OpenRouterAgent interactively.
Useful for quick queries without the overhead of the full multi-agent
orchestration pipeline.

Usage:
    python main.py
    uv run main.py

Part of the Pro-Make-It-Heavy / AEON-777 GlacierEQ framework.
"""

import logging
import sys

from agent import OpenRouterAgent, ConfigurationError

# ─── Logging: show INFO+ in single-agent mode (debug output useful here) ──────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────
EXIT_COMMANDS: frozenset = frozenset({"quit", "exit", "bye"})
SEPARATOR: str = "-" * 50


def main() -> None:
    """
    Run an interactive single-agent CLI session.

    Initialises one OpenRouterAgent with the default config.yaml, then
    enters a read-eval-print loop that sends each user query to the agent
    and prints the response. Exits cleanly on quit commands or Ctrl-C.

    Exits with code 1 if the agent cannot be initialised (e.g. missing API key).
    """
    print("OpenRouter Single Agent — GlacierEQ / AEON-777")
    print(f"Type {', '.join(repr(c) for c in EXIT_COMMANDS)} to exit")
    print(SEPARATOR)

    # Initialise agent — fail fast with a clear message on config errors
    try:
        agent = OpenRouterAgent()
        model: str = agent.config["openrouter"]["model"]
        print(f"Agent ready ✓  |  Model: {model}")
        print("Tip: Set your OpenRouter API key in config.yaml if not already done.")
        print(SEPARATOR)
    except ConfigurationError as exc:
        print(f"\n⚠️  Configuration error: {exc}")
        print("Steps to fix:")
        print("  1. Copy config.yaml.example → config.yaml")
        print("  2. Set openrouter.api_key to your OpenRouter API key")
        print("  3. Run: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as exc:
        logger.error("Unexpected agent init failure: %s", exc, exc_info=True)
        print(f"\n💥 Fatal error during agent init: {exc}")
        sys.exit(1)

    # REPL
    while True:
        try:
            user_input = input("\nUser: ").strip()

            if not user_input:
                print("Please enter a question or command.")
                continue

            if user_input.lower() in EXIT_COMMANDS:
                print("Goodbye — AEON-777 standing by.")
                break

            print("Agent: Thinking…")
            response: str = agent.run(user_input)
            print(f"Agent: {response}")

        except KeyboardInterrupt:
            print("\n\nKeyboard interrupt — exiting.")
            break
        except EOFError:
            # Non-interactive (piped) input exhausted
            break
        except Exception as exc:
            logger.error("Unexpected error during agent run: %s", exc, exc_info=True)
            print(f"Error: {exc}")
            print("Please try again or type 'quit' to exit.")


if __name__ == "__main__":
    main()