# SPDX-License-Identifier: Proprietary
"""Tests for skill_lint v2: CLI parsing, JSON output, fix mode, gate wrapper."""

import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import skill_lint
from skill_lint import (
    LintReport,
    Severity,
    Finding,
    auto_fix_file,
    auto_fix_directory,
    run_gate,
    main,
    format_report_json,
    format_report_text,
    SAFE_FIXERS,
    lint_file,
    lint_directory,
    lint_agents_md,
    lint_agents_md_tree,
)


def _write_skill(tmpdir: Path, name: str, body: str) -> Path:
    skill_dir = tmpdir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    p = skill_dir / "SKILL.md"
    p.write_text(textwrap.dedent(body).lstrip())
    return p


# ---------------------------------------------------------------------------
# CLI: argparse + format selection
# ---------------------------------------------------------------------------


class TestCLIArgs(unittest.TestCase):
    def test_help_flag_exits_zero(self):
        with mock.patch.object(sys, "argv", ["skill_lint", "--help"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)

    def test_format_json_emits_valid_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_skill(root, "good", "---\nname: g\n---\nbody\n")
            with mock.patch.object(sys, "argv",
                                   ["skill_lint", str(root), "--format", "json"]):
                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc = main()
            data = json.loads(buf.getvalue())
            self.assertIn("skills", data)
            self.assertIn("good", data["skills"])
            self.assertIn("findings", data["skills"]["good"])
            self.assertEqual(rc, 0)

    def test_severity_filter_warnings_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_skill(root, "broken", textwrap.dedent("""\
                ---
                description: missing name
                ---
                body
                """))
            with mock.patch.object(sys, "argv",
                                   ["skill_lint", str(root),
                                    "--format", "json", "--severity", "error"]):
                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc = main()
            data = json.loads(buf.getvalue())
            findings = data["skills"]["broken"]["findings"]
            for f in findings:
                self.assertEqual(f["severity"], "error")
            self.assertEqual(rc, 1)  # errors remain

    def test_exit_zero_flag_suppresses_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_skill(root, "broken", textwrap.dedent("""\
                ---
                description: missing name
                ---
                body
                """))
            with mock.patch.object(sys, "argv",
                                   ["skill_lint", str(root), "--exit-zero"]):
                rc = main()
                self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# JSON output shape
# ---------------------------------------------------------------------------


class TestJSONFormat(unittest.TestCase):
    def test_json_has_expected_keys(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_skill(root, "x", "---\nname: x\n---\nbody\n")
            reports = lint_directory(root)
            text = format_report_text(reports)
            data = json.loads(format_report_json(reports))
            self.assertIn("summary", data)
            self.assertIn("skills", data)
            self.assertIn("errors", data["summary"])
            self.assertIn("warnings", data["summary"])
            self.assertIn("scanned", data["summary"])
            self.assertEqual(data["summary"]["scanned"], 1)


# ---------------------------------------------------------------------------
# Auto-fix mode
# ---------------------------------------------------------------------------


class TestAutoFix(unittest.TestCase):
    def test_safe_fixer_list_nonempty(self):
        self.assertIn("mirror_canonical", SAFE_FIXERS)
        self.assertIn("strip_slash_comments", SAFE_FIXERS)
        self.assertIn("add_skill_pointer", SAFE_FIXERS)
        self.assertIn("add_test_command", SAFE_FIXERS)

    def test_mirror_canonical_copies_to_other_installs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical = root / "canonical"
            target = root / "target"
            (canonical / "shared").mkdir(parents=True)
            (canonical / "shared" / "SKILL.md").write_text(
                "---\nname: shared\n---\nclean body\n"
            )
            (target / "shared").mkdir(parents=True)
            (target / "shared" / "SKILL.md").write_text(
                textwrap.dedent("""\
                    ---
                    name: shared
                    description: Test.
                    ---

                    ## Sharp Edges

                    | Issue | Severity | Solution |
                    |-------|----------|----------|
                    | A real problem | high | // comment to strip |
                    """)
            )
            result = auto_fix_directory(
                target, fixer="mirror_canonical", canonical_root=canonical
            )
            self.assertEqual(len(result["fixed"]), 1)
            self.assertTrue(result["fixed"][0].endswith("shared/SKILL.md"))
            reports = lint_directory(target)
            errors = [f for f in reports["shared"].findings
                      if f.severity == Severity.ERROR]
            self.assertEqual(errors, [], f"After mirror, target should be clean, got: {errors}")

    def test_strip_slash_comments_in_sharp_edges(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = _write_skill(root, "leaky", textwrap.dedent("""\
                ---
                name: leaky
                description: Test.
                ---

                ## Sharp Edges

                | Issue | Severity | Solution |
                |-------|----------|----------|
                | A real problem | high | // this is a code comment leaked into prose |
                """))
            result = auto_fix_file(p, fixer="strip_slash_comments")
            self.assertTrue(result["modified"])
            new_text = p.read_text()
            self.assertNotIn("//", new_text,
                             f"// comments should be stripped, got: {new_text!r}")

    def test_add_skill_pointer_to_short_agents_md(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = (root / "AGENTS.md")
            p.write_text(textwrap.dedent("""\
                # AGENTS.md — example

                Quick rules only, no skill pointer.

                - **Test command:** `pytest`
                """))
            result = auto_fix_file(
                p, fixer="add_skill_pointer",
                canonical_skill="example",
            )
            self.assertTrue(result["modified"])
            new_text = p.read_text()
            self.assertIn("/root/.agents/skills/example/SKILL.md", new_text)

    def test_add_test_command_to_agents_md(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = (root / "AGENTS.md")
            p.write_text("# AGENTS.md — example\n\nNo test command here.\n")
            r = auto_fix_file(
                p, fixer="add_test_command",
                canonical_skill="cd /root/projects/example && pytest",
            )
            self.assertTrue(r["modified"])
            text = p.read_text()
            self.assertIn("Test command", text)
            self.assertIn("cd /root/projects/example", text)

    def test_add_test_command_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = (root / "AGENTS.md")
            p.write_text("# AGENTS.md — example\n\n- **Test command:** `pytest`\n")
            r = auto_fix_file(
                p, fixer="add_test_command",
                canonical_skill="cd /root/projects/example && pytest",
            )
            self.assertFalse(r["modified"], f"Already has test command, got: {r}")


class TestAutoFixIdempotency(unittest.TestCase):
    """Running --fix twice should not change the file the second time."""

    def test_strip_slash_comments_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = _write_skill(root, "x", textwrap.dedent("""\
                ---
                name: x
                description: Test.
                ---

                ## Sharp Edges

                | Issue | Severity | Solution |
                |-------|----------|----------|
                | Real problem | high | // strip me |
                """))
            r1 = auto_fix_file(p, fixer="strip_slash_comments")
            r2 = auto_fix_file(p, fixer="strip_slash_comments")
            self.assertTrue(r1["modified"])
            self.assertFalse(r2["modified"], "Second run should be a no-op")


class TestAutoFixSafety(unittest.TestCase):
    """The fixer must NEVER convert a warning into a broken-ref error."""

    def test_add_skill_pointer_refuses_unknown_skill(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = (root / "AGENTS.md")
            p.write_text("# AGENTS.md — example\n\nNo pointer here.\n")
            r = auto_fix_file(
                p, fixer="add_skill_pointer",
                canonical_skill="nonexistent-skill",
                canonical_root=root,  # no actual skill at this path
            )
            self.assertFalse(r["modified"],
                             f"Refused to insert a pointer to a non-existent skill, got: {r}")
            new_text = p.read_text()
            self.assertNotIn("/root/.agents/skills/", new_text,
                             f"Should not have written a broken pointer, got: {new_text!r}")

    def test_gate_does_not_create_broken_pointers(self):
        """End-to-end: gate on a tree with no real skills must not create errors."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical = root / "canonical"  # empty: no skills installed
            (root / "project1" / "AGENTS.md").parent.mkdir(parents=True)
            (root / "project1" / "AGENTS.md").write_text(
                "# AGENTS.md — project1\n\nQuick rules.\n\n- **Test command:** `pytest`\n"
            )
            # The gate should not introduce errors by inserting broken pointers.
            receipt = run_gate(
                target=root, fix=True, prove_cmd=None,
                canonical_root=canonical, agents_mode=True,
            )
            self.assertEqual(receipt["after"]["errors"], 0,
                             f"Gate must not create errors, got: {receipt}")
            # The fix should have been refused (skipped), not applied.
            skipped = [f for f in receipt["fixes_applied"] if not f.get("modified")]
            self.assertTrue(len(skipped) > 0,
                            f"Expected at least one skipped fix, got: {receipt['fixes_applied']}")


# ---------------------------------------------------------------------------
# Gate wrapper: detect → fix → prove
# ---------------------------------------------------------------------------


class TestGate(unittest.TestCase):
    def test_gate_returns_receipt_dict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "ok").mkdir()
            (root / "ok" / "SKILL.md").write_text("---\nname: ok\n---\nbody\n")
            receipt = run_gate(
                target=root, fix=False, prove_cmd=None,
            )
            self.assertIn("before", receipt)
            self.assertIn("after", receipt)
            self.assertIn("fixes_applied", receipt)
            self.assertIn("exit_code", receipt)
            self.assertEqual(receipt["before"]["errors"], 0)
            self.assertEqual(receipt["after"]["errors"], 0)
            self.assertEqual(receipt["fixes_applied"], [])

    def test_gate_runs_fix_then_proves(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = _write_skill(root, "leaky", textwrap.dedent("""\
                ---
                name: leaky
                description: Test.
                ---

                ## Sharp Edges

                | Issue | Severity | Solution |
                |-------|----------|----------|
                | Real problem | high | // strip me |
                """))
            before = lint_file(p)
            self.assertTrue(any(f.severity == Severity.ERROR for f in before.findings))

            receipt = run_gate(target=root, fix=True, prove_cmd=None)
            self.assertGreater(len(receipt["fixes_applied"]), 0)
            self.assertLess(receipt["after"]["errors"], receipt["before"]["errors"])

    def test_gate_prove_runs_command_and_records_passfail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "ok").mkdir()
            (root / "ok" / "SKILL.md").write_text("---\nname: ok\n---\nbody\n")
            receipt = run_gate(
                target=root, fix=False,
                prove_cmd=[sys.executable, "-c", "print('ok')"],
            )
            self.assertIn("prove", receipt)
            self.assertEqual(receipt["prove"]["returncode"], 0)


class TestEndToEndCLI(unittest.TestCase):
    """Run the linter as a real subprocess. Catches argparse wiring,
    stdout/stderr handling, and exit code bugs that mocked tests miss."""

    LINTER = "/root/projects/make-it-heavy/skill_lint.py"

    def test_help_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, self.LINTER, "--help"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("usage:", proc.stdout)

    def test_clean_tree_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "x").mkdir()
            (root / "x" / "SKILL.md").write_text("---\nname: x\n---\nbody\n")
            proc = subprocess.run(
                [sys.executable, self.LINTER, str(root)],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(proc.returncode, 0, f"clean should exit 0, got stderr: {proc.stderr}")
            self.assertIn("clean", proc.stdout)

    def test_broken_tree_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "broken").mkdir()
            (root / "broken" / "SKILL.md").write_text(
                textwrap.dedent("""\
                    ---
                    description: missing name
                    ---
                    body
                    """)
            )
            proc = subprocess.run(
                [sys.executable, self.LINTER, str(root)],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(proc.returncode, 1)
            self.assertIn("error", proc.stdout)

    def test_json_format_emits_valid_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "x").mkdir()
            (root / "x" / "SKILL.md").write_text("---\nname: x\n---\nbody\n")
            proc = subprocess.run(
                [sys.executable, self.LINTER, str(root), "--format", "json"],
                capture_output=True, text=True, timeout=10,
            )
            data = json.loads(proc.stdout)
            self.assertIn("summary", data)
            self.assertIn("skills", data)

    def test_gate_subcommand_emits_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "ok").mkdir()
            (root / "ok" / "SKILL.md").write_text("---\nname: ok\n---\nbody\n")
            proc = subprocess.run(
                [sys.executable, self.LINTER, str(root), "--gate"],
                capture_output=True, text=True, timeout=10,
            )
            data = json.loads(proc.stdout)
            self.assertIn("before", data)
            self.assertIn("after", data)
            self.assertIn("exit_code", data)
            self.assertEqual(data["after"]["errors"], 0)
            self.assertEqual(proc.returncode, 0)

    def test_receipt_flag_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "ok").mkdir()
            (root / "ok" / "SKILL.md").write_text("---\nname: ok\n---\nbody\n")
            receipt_path = Path(td) / "receipts.jsonl"
            proc = subprocess.run(
                [sys.executable, self.LINTER, str(root), "--gate",
                 "--receipt", str(receipt_path)],
                capture_output=True, text=True, timeout=10,
            )
            self.assertTrue(receipt_path.exists(),
                            f"Receipt file should exist, got: {proc.stderr}")
            lines = receipt_path.read_text().strip().split("\n")
            self.assertEqual(len(lines), 1)
            data = json.loads(lines[0])
            self.assertIn("before", data)
            self.assertIn("after", data)


if __name__ == "__main__":
    unittest.main()
