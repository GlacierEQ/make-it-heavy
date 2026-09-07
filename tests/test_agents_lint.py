# SPDX-License-Identifier: Proprietary
"""Tests for AGENTS.md linting."""

import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from skill_lint import lint_agents_md, Severity


def _write(tmpdir: Path, name: str, body: str) -> Path:
    p = tmpdir / name
    p.write_text(textwrap.dedent(body).lstrip())
    return p


VALID_SUPPLEMENT = """\
# AGENTS.md — example-project

Quick rules and entry points for this project.

**See:** `@/root/.agents/skills/example-project/SKILL.md` for full operating guide.

## Quick rules

- **Test command:** `cd /root/projects/example && pytest`
- **Entry point:** `python -m example`
"""


class TestFrontmatterNotRequired(unittest.TestCase):
    """AGENTS.md is plain markdown, not YAML-frontmatter SKILL.md."""

    def test_no_frontmatter_is_fine(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write(Path(td), "AGENTS.md", VALID_SUPPLEMENT)
            report = lint_agents_md(p)
            self.assertFalse(
                any(f.severity == Severity.ERROR and "frontmatter" in f.message.lower()
                    for f in report.findings),
                f"AGENTS.md should not require YAML frontmatter, got: {report.findings}",
            )


class TestSupplementPattern(unittest.TestCase):
    def test_short_file_with_skill_pointer_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Create a stub skill so the pointer resolves.
            (root / "example-project" / "SKILL.md").mkdir(parents=True)
            (root / "example-project" / "SKILL.md" / "SKILL.md").write_text("---\nname: x\n---\n")
            # Note: lint_agents_md reads /root/.agents/skills directly; we can't
            # override it without changing the API. Instead, point at a skill
            # we know exists at /root/.agents/skills (any of them).
            p = _write(root, "AGENTS.md", """\
# AGENTS.md — example-project

**See:** `@/root/.agents/skills/clean-code/SKILL.md` for style guide.

## Quick rules

- **Test command:** `cd /root/projects/example && pytest`
""")
            report = lint_agents_md(p, skills_root=Path("/root/.agents/skills"))
            errors = [f for f in report.findings if f.severity == Severity.ERROR]
            self.assertEqual(errors, [], f"Valid supplement should pass, got: {errors}")

    def test_short_file_without_skill_pointer_warns(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write(Path(td), "AGENTS.md", """\
# AGENTS.md — example

Quick rules only, no skill pointer.
""")
            report = lint_agents_md(p)
            warnings = [f for f in report.findings if f.severity == Severity.WARNING]
            self.assertTrue(
                any("skill" in f.message.lower() and "pointer" in f.message.lower()
                    for f in warnings),
                f"Expected missing-skill-pointer warning, got: {warnings}",
            )

    def test_long_file_without_skill_pointer_warns(self):
        """A long AGENTS.md that doesn't point at a skill is probably
        duplicating doctrine that belongs in a skill."""
        with tempfile.TemporaryDirectory() as td:
            long_body = "# AGENTS.md — example\n\n" + ("rule line\n" * 80)
            p = _write(Path(td), "AGENTS.md", long_body)
            report = lint_agents_md(p)
            warnings = [f for f in report.findings if f.severity == Severity.WARNING]
            self.assertTrue(
                any("duplicate" in f.message.lower() or "doctrine" in f.message.lower()
                    for f in warnings),
                f"Expected doctrine-duplication warning, got: {warnings}",
            )


class TestTestCommand(unittest.TestCase):
    def test_supplement_without_test_command_warns(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write(Path(td), "AGENTS.md", """\
# AGENTS.md — example

**See:** `@/root/.agents/skills/example/SKILL.md` for full operating guide.

## Quick rules

- **Entry point:** `python -m example`
""")
            report = lint_agents_md(p)
            warnings = [f for f in report.findings if f.severity == Severity.WARNING]
            self.assertTrue(
                any("test command" in f.message.lower() for f in warnings),
                f"Expected test-command warning, got: {warnings}",
            )

    def test_supplement_with_test_command_passes(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write(Path(td), "AGENTS.md", VALID_SUPPLEMENT)
            report = lint_agents_md(p)
            cmd_warns = [f for f in report.findings
                         if f.severity == Severity.WARNING and "test command" in f.message.lower()]
            self.assertEqual(cmd_warns, [], f"Test command present, got: {cmd_warns}")


class TestSameRulesApply(unittest.TestCase):
    """AGENTS.md should not have the same bugs SKILL.md has."""

    def test_truncated_intro_detected(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write(Path(td), "AGENTS.md", """\
# AGENTS.md — example

This rule applies to chunking, embedding, and
""")
            report = lint_agents_md(p)
            warnings = [f for f in report.findings if f.severity == Severity.WARNING]
            self.assertTrue(
                any("truncat" in f.message.lower() for f in warnings),
                f"Expected truncation warning, got: {warnings}",
            )

    def test_broken_at_skill_ref_detected(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write(Path(td), "AGENTS.md", """\
# AGENTS.md — example

**See:** `@/root/.agents/skills/nonexistent/SKILL.md` for full operating guide.

## Quick rules

- **Test command:** `pytest`
""")
            report = lint_agents_md(p)
            errors = [f for f in report.findings if f.severity == Severity.ERROR]
            self.assertTrue(
                any("nonexistent" in f.message for f in errors),
                f"Expected broken-ref error, got: {errors}",
            )


class TestAgainstRealTree(unittest.TestCase):
    def test_lint_real_workspace_agents_md_files(self):
        """If the workspace AGENTS.md files exist, they should lint without crash."""
        candidates = [
            Path("/root/AGENTS.md"),
            Path("/root/projects/make-it-heavy/AGENTS.md"),
            Path("/root/projects/mastermind/AGENTS.md"),
            Path("/root/projects/monolith/AGENTS.md"),
            Path("/root/projects/GlacierEQ_Swarm/the-tower-of-babel/AGENTS.md"),
        ]
        existing = [p for p in candidates if p.exists()]
        if not existing:
            self.skipTest("No real AGENTS.md files present")
        for p in existing:
            report = lint_agents_md(p)
            for f in report.findings:
                self.assertIsNotNone(f.message)
                self.assertIsNotNone(f.file)


if __name__ == "__main__":
    unittest.main()
