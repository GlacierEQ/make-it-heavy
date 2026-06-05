# SPDX-License-Identifier: Proprietary
# Copyright (c) 2026 Casey del Carpio Barton / GlacierEQ — All Rights Reserved
"""
make_it_heavy.py — Multi-Agent Orchestrator CLI

Interactive command-line interface for the Make-It-Heavy multi-agent
orchestration system. Provides live, animated progress feedback while
parallel agents process complex queries.

Usage:
    python make_it_heavy.py
    uv run make_it_heavy.py

Part of the Pro-Make-It-Heavy / AEON-777 GlacierEQ framework.
"""

import logging
import os
import sys
import threading
import time
from typing import Optional

from orchestrator import TaskOrchestrator

# ─── Logging configuration (structured, replaces bare prints) ─────────────────
logging.basicConfig(
    level=logging.WARNING,   # CLI stays quiet; only warnings+ reach console
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── ANSI colour constants ────────────────────────────────────────────────────
ANSI_ORANGE: str = "\033[38;5;208m"
ANSI_RED: str = "\033[91m"
ANSI_RESET: str = "\033[0m"

# ─── Progress bar constants ───────────────────────────────────────────────────
BAR_WIDTH: int = 70
BAR_ACTIVE_WIDTH: int = 10
PROGRESS_UPDATE_INTERVAL: float = 1.0   # seconds between display refreshes

# ─── Status strings (must match orchestrator.py STATUS_* constants) ───────────
STATUS_QUEUED: str = "QUEUED"
STATUS_INITIALIZING: str = "INITIALIZING..."
STATUS_PROCESSING: str = "PROCESSING..."
STATUS_COMPLETED: str = "COMPLETED"
STATUS_FAILED_PREFIX: str = "FAILED"

# ─── Result display ───────────────────────────────────────────────────────────
RESULT_SEPARATOR: str = "=" * 80
EXIT_COMMANDS: frozenset = frozenset({"quit", "exit", "bye"})


class OrchestratorCLI:
    """
    Interactive CLI wrapper for TaskOrchestrator with live progress display.

    Spawns a background thread that redraws the terminal at PROGRESS_UPDATE_INTERVAL
    intervals showing per-agent animated progress bars. Results are printed in full
    after all agents complete.

    Args:
        None — reads all settings from config.yaml via TaskOrchestrator.
    """

    def __init__(self) -> None:
        self.orchestrator: TaskOrchestrator = TaskOrchestrator()
        self.start_time: Optional[float] = None
        self.running: bool = False
        self.model_display: str = self._build_model_display()

    # ──────────────────────────────────────────────────────────────────────────
    # Initialisation helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _build_model_display(self) -> str:
        """
        Derive a clean, human-readable model name for the CLI header.

        Strips the provider prefix (e.g. "google/") and shortens the slug to
        at most 3 hyphen-separated segments for display brevity.

        Returns:
            Uppercase model display string, e.g. "GEMINI-2.5-FLASH HEAVY".
        """
        model_full: str = self.orchestrator.config["openrouter"]["model"]
        model_slug = model_full.split("/")[-1] if "/" in model_full else model_full
        parts = model_slug.split("-")
        clean = "-".join(parts[:3]) if len(parts) >= 3 else model_slug
        return f"{clean.upper()} HEAVY"

    # ──────────────────────────────────────────────────────────────────────────
    # Display utilities
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def clear_screen() -> None:
        """Clear the terminal screen using the OS-appropriate command."""
        os.system("cls" if os.name == "nt" else "clear")

    @staticmethod
    def format_time(seconds: float) -> str:
        """
        Format an elapsed-seconds value into a compact human-readable string.

        Examples:
            format_time(45)    → "45S"
            format_time(125)   → "2M5S"
            format_time(3700)  → "1H1M"

        Args:
            seconds: Non-negative elapsed seconds.

        Returns:
            Compact time string.
        """
        seconds = max(0.0, seconds)
        if seconds < 60:
            return f"{int(seconds)}S"
        if seconds < 3600:
            return f"{int(seconds // 60)}M{int(seconds % 60)}S"
        return f"{int(seconds // 3600)}H{int((seconds % 3600) // 60)}M"

    def create_progress_bar(self, status: str) -> str:
        """
        Render a single-line progress bar string for a given agent status.

        Visual language:
            QUEUED       → empty dots
            INITIALIZING → half-filled orange
            PROCESSING   → pulsing orange fill
            COMPLETED    → full orange fill
            FAILED       → red X marks

        Args:
            status: Agent status string (one of the STATUS_* constants).

        Returns:
            ANSI-formatted progress bar string ready for print().
        """
        o, r, x = ANSI_ORANGE, ANSI_RESET, ANSI_RED

        if status == STATUS_QUEUED:
            return "○ " + "·" * BAR_WIDTH

        if status == STATUS_INITIALIZING:
            return f"{o}◐{r} " + "·" * BAR_WIDTH

        if status == STATUS_PROCESSING:
            active = f"{o}:" * BAR_ACTIVE_WIDTH + r
            rest = "·" * (BAR_WIDTH - BAR_ACTIVE_WIDTH)
            return f"{o}●{r} {active}{rest}"

        if status == STATUS_COMPLETED:
            return f"{o}●{r} " + f"{o}:" * BAR_WIDTH + r

        if status.startswith(STATUS_FAILED_PREFIX):
            return f"{x}✗{r} " + f"{x}×" * BAR_WIDTH + r

        # Unknown / transitional state
        return f"{o}◐{r} " + "·" * BAR_WIDTH

    def update_display(self) -> None:
        """
        Redraw the full CLI dashboard to the terminal.

        Shows the model name, elapsed time, and an animated progress bar for
        every registered agent. Flushes stdout so the update is immediately
        visible even without a newline.
        """
        if not self.running:
            return

        elapsed = time.monotonic() - self.start_time if self.start_time else 0.0
        time_str = self.format_time(elapsed)
        progress = self.orchestrator.get_progress_status()

        self.clear_screen()

        # Header
        print(self.model_display)
        state_label = "RUNNING" if self.running else "COMPLETED"
        print(f"● {state_label} • {time_str}")
        print()

        # Per-agent status rows
        for i in range(self.orchestrator.num_agents):
            status = progress.get(i, STATUS_QUEUED)
            bar = self.create_progress_bar(status)
            print(f"AGENT {i + 1:02d}  {bar}")

        print()
        sys.stdout.flush()

    # ──────────────────────────────────────────────────────────────────────────
    # Threading
    # ──────────────────────────────────────────────────────────────────────────

    def _progress_monitor(self) -> None:
        """
        Background thread target — refreshes the progress display on a timer.

        Runs until self.running is set to False by the main thread. Using a
        daemon thread ensures Python can exit cleanly even if this is still
        running when the process is interrupted.
        """
        while self.running:
            self.update_display()
            time.sleep(PROGRESS_UPDATE_INTERVAL)

    # ──────────────────────────────────────────────────────────────────────────
    # Task execution
    # ──────────────────────────────────────────────────────────────────────────

    def run_task(self, user_input: str) -> Optional[str]:
        """
        Execute a full orchestration run with live progress feedback.

        Starts the progress monitor thread, runs the orchestrator synchronously
        on the main thread (so stdout is always flushed after completion), then
        prints the final result with clear separators.

        Args:
            user_input: The user's query string.

        Returns:
            The final synthesised answer string, or None on critical failure.
        """
        self.start_time = time.monotonic()
        self.running = True

        progress_thread = threading.Thread(
            target=self._progress_monitor, daemon=True, name="ProgressMonitor"
        )
        progress_thread.start()

        try:
            result: str = self.orchestrator.orchestrate(user_input)

            self.running = False
            self.update_display()   # Final repaint in completed state

            # Print results
            print(RESULT_SEPARATOR)
            print("FINAL RESULTS")
            print(RESULT_SEPARATOR)
            print()
            print(result)
            print()
            print(RESULT_SEPARATOR)

            return result

        except Exception as exc:
            self.running = False
            self.update_display()
            logger.error("Orchestration run failed: %s", exc, exc_info=True)
            print(f"\n⚠️  Orchestration error: {exc}")
            print("Check your config.yaml API key and network connectivity.")
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # Interactive session
    # ──────────────────────────────────────────────────────────────────────────

    def interactive_mode(self) -> None:
        """
        Run a REPL-style interactive CLI session.

        Displays startup info, then loops accepting user queries until the user
        types an exit command or presses Ctrl-C. Each query is routed through
        run_task() with full progress visualisation.
        """
        print("Multi-Agent Orchestrator — GlacierEQ / AEON-777")
        print(f"Configured for {self.orchestrator.num_agents} parallel agents")
        print(f"Type {', '.join(repr(c) for c in EXIT_COMMANDS)} to exit")
        print("-" * 50)

        try:
            or_cfg = self.orchestrator.config["openrouter"]
            print(f"Model  : {or_cfg['model']}")
            print(f"Display: {self.model_display}")
            print("Status : Orchestrator ready ✓")
            print("-" * 50)
        except (KeyError, TypeError) as exc:
            print(f"⚠️  Config error: {exc}")
            print("Ensure config.yaml has a valid 'openrouter' section.")
            return

        while True:
            try:
                user_input = input("\nUser: ").strip()

                if not user_input:
                    print("Please enter a question or command.")
                    continue

                if user_input.lower() in EXIT_COMMANDS:
                    print("Goodbye — AEON-777 standing by.")
                    break

                print("\nOrchestrator: Starting multi-agent analysis…\n")
                result = self.run_task(user_input)

                if result is None:
                    print("⚠️  Task returned no result. Please try again.")

            except KeyboardInterrupt:
                print("\n\nKeyboard interrupt — exiting.")
                break
            except EOFError:
                # Non-interactive (piped) input exhausted
                break
            except Exception as exc:
                logger.error("Unexpected CLI error: %s", exc, exc_info=True)
                print(f"Unexpected error: {exc}")
                print("Please try again or type 'quit' to exit.")


# ─── Entry point ─────────────────────────────────────────────────────────────


def main() -> None:
    """
    Main entry point for the Make-It-Heavy multi-agent orchestrator CLI.

    Instantiates OrchestratorCLI and starts the interactive session.
    Exits with code 1 on fatal configuration errors so calling scripts
    can detect failure.
    """
    try:
        cli = OrchestratorCLI()
        cli.interactive_mode()
    except Exception as exc:
        # Only fatal initialisation errors reach here
        logger.critical("Fatal startup error: %s", exc, exc_info=True)
        print(f"\n💥 Fatal error: {exc}")
        print("Check config.yaml and ensure all dependencies are installed.")
        sys.exit(1)


if __name__ == "__main__":
    main()