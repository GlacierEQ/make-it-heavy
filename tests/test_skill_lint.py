# SPDX-License-Identifier: Proprietary
"""Tests for skill_lint — the SKILL.md convention linter."""

import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from skill_lint import LintReport, Severity, lint_file, lint_directory


def _write_skill(tmpdir: Path, name: str, body: str) -> Path:
    skill_dir = tmpdir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    p = skill_dir / "SKILL.md"
    p.write_text(textwrap.dedent(body).lstrip())
    return p


VALID_SKILL = """\
---
name: example
description: A test skill.
---

# Example

A clean skill body.

## Sharp Edges

| Issue | Severity | Solution |
|-------|----------|----------|
| Real issue | high | Real solution. |
"""


class TestFrontmatter(unittest.TestCase):
    def test_missing_name_field_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_skill(Path(td), "nofrontmatter", """\
---
description: missing name
---

body
""")
            report = lint_file(p)
            errors = [f for f in report.findings if f.severity == Severity.ERROR]
            self.assertTrue(any("name" in f.message.lower() for f in errors),
                            f"Expected missing-name error, got: {[f.message for f in errors]}")

    def test_present_name_field_passes(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_skill(Path(td), "good", VALID_SKILL)
            report = lint_file(p)
            self.assertFalse(any(f.severity == Severity.ERROR for f in report.findings),
                            f"Clean skill should have no errors, got: {report.findings}")


class TestBrokenCrossRefs(unittest.TestCase):
    def test_broken_at_skill_ref_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_skill(root, "exists", VALID_SKILL)
            p = _write_skill(root, "badref", """\
---
name: badref
description: Test.
---

See `@[skills/nonexistent]` for details.
""")
            report = lint_file(p, skills_root=root)
            errors = [f for f in report.findings if f.severity == Severity.ERROR]
            self.assertTrue(any("nonexistent" in f.message for f in errors),
                            f"Expected broken-ref error, got: {[f.message for f in errors]}")

    def test_clean_bare_ref_in_backticks_passes(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_skill(Path(td), "clean", """\
---
name: clean
description: Test.
---

Load `clean-code` for style.
""")
            report = lint_file(p)
            broken = [f for f in report.findings
                      if f.severity == Severity.ERROR and "cross-ref" in f.message.lower()]
            self.assertEqual(broken, [], f"Backticked bare names should pass, got: {broken}")


class TestSharpEdges(unittest.TestCase):
    def test_issue_placeholder_row_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_skill(Path(td), "placeholder", """\
---
name: placeholder
description: Test.
---

## Sharp Edges

| Issue | Severity | Solution |
|-------|----------|----------|
| Issue | high | ## Some heading-shaped thing |
""")
            report = lint_file(p)
            errors = [f for f in report.findings if f.severity == Severity.ERROR]
            self.assertTrue(any("placeholder" in f.message.lower() or "issue" in f.message.lower()
                                for f in errors),
                            f"Expected placeholder error, got: {[f.message for f in errors]}")

    def test_double_slash_comment_in_sharp_edges_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_skill(Path(td), "slashcomment", """\
---
name: slashcomment
description: Test.
---

## Sharp Edges

| Issue | Severity | Solution |
|-------|----------|----------|
| A real problem | high | // TODO: figure this out |
""")
            report = lint_file(p)
            errors = [f for f in report.findings if f.severity == Severity.ERROR]
            self.assertTrue(any("//" in f.message for f in errors),
                            f"Expected // comment error, got: {[f.message for f in errors]}")

    def test_real_sharp_edge_row_passes(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_skill(Path(td), "realrow", """\
---
name: realrow
description: Test.
---

## Sharp Edges

| Issue | Severity | Solution |
|-------|----------|----------|
| A real problem | high | **Do this** to fix it. |
""")
            report = lint_file(p)
            sharp_errors = [f for f in report.findings
                            if f.severity == Severity.ERROR and "sharp" in f.message.lower()]
            self.assertEqual(sharp_errors, [],
                             f"Real sharp-edge rows should pass, got: {sharp_errors}")


class TestTruncatedIntros(unittest.TestCase):
    def test_truncated_line_ending_with_conjunction_is_warning(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_skill(Path(td), "truncated", """\
---
name: truncated
description: Test.
---

You obsess over chunking strategies, embedding quality, and
""")
            report = lint_file(p)
            warnings = [f for f in report.findings if f.severity == Severity.WARNING]
            self.assertTrue(any("truncat" in f.message.lower() for f in warnings),
                            f"Expected truncation warning, got: {[f.message for f in warnings]}")

    def test_complete_sentence_passes(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_skill(Path(td), "complete", """\
---
name: complete
description: Test.
---

This is a complete sentence that ends with a period.
""")
            report = lint_file(p)
            trunc = [f for f in report.findings
                     if f.severity == Severity.WARNING and "truncat" in f.message.lower()]
            self.assertEqual(trunc, [], f"Complete sentences should pass, got: {trunc}")


class TestDirectoryLinting(unittest.TestCase):
    def test_lint_directory_returns_per_skill_reports(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_skill(root, "a", VALID_SKILL)
            _write_skill(root, "b", """\
---
description: missing name
---
body
""")
            reports = lint_directory(root)
            self.assertEqual(set(reports.keys()), {"a", "b"})
            self.assertFalse(any(f.severity == Severity.ERROR for f in reports["a"].findings))
            self.assertTrue(any(f.severity == Severity.ERROR for f in reports["b"].findings))


class TestReportShape(unittest.TestCase):
    def test_report_has_exit_code_helper(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_skill(Path(td), "x", """\
---
description: missing name
---
body
""")
            report = lint_file(p)
            self.assertEqual(report.exit_code(), 1)  # any error → non-zero

            p2 = _write_skill(Path(td), "y", VALID_SKILL)
            report2 = lint_file(p2)
            self.assertEqual(report2.exit_code(), 0)

    def test_finding_has_file_and_line(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_skill(Path(td), "lineno", """\
---
description: missing name
---
body line 5
""")
            report = lint_file(p)
            self.assertTrue(report.findings)
            f = report.findings[0]
            self.assertTrue(hasattr(f, "line"))
            self.assertTrue(hasattr(f, "file"))


class TestAgainstRealEcosystem(unittest.TestCase):
    """If the real skill tree is present, linting it should not crash.
    Any errors found are reported but the test only asserts the linter runs."""

    def test_real_skills_directory_lints_without_crash(self):
        real_path = Path("/root/.agents/skills")
        if not real_path.exists():
            self.skipTest("Real skill tree not available")
        reports = lint_directory(real_path)
        self.assertGreater(len(reports), 0, "Should find at least one skill")
        # Linter should never crash on any input.
        for name, report in reports.items():
            for f in report.findings:
                self.assertIsNotNone(f.message)
                self.assertIsNotNone(f.file)


if __name__ == "__main__":
    unittest.main()
