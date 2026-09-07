# SPDX-License-Identifier: Proprietary
"""skill_lint — convention linter for SKILL.md files in this workspace.

Catches the classes of bug that have been hand-fixed twice already:
  - Missing or malformed YAML frontmatter (the `name:` field is required)
  - Broken `@[skills/...]` cross-refs to skills that don't exist
  - Sharp Edges table placeholders (the literal row `| Issue | Severity | Solution |`
    with `Issue` as the issue column)
  - `// comment` text leaking into Sharp Edge Solution cells
  - Truncated body intros (sentences ending in a dangling conjunction
    like "and" or "—")

Usage:
    from skill_lint import lint_directory
    reports = lint_directory("/root/.agents/skills")
    for name, report in reports.items():
        for f in report.findings:
            print(f"{report.path}:{f.line}: {f.severity.name}: {f.message}")
"""

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class Finding:
    severity: Severity
    message: str
    file: str
    line: int = 0

    def __str__(self) -> str:
        loc = f"{self.file}:{self.line}" if self.line else self.file
        return f"{loc}: {self.severity.value}: {self.message}"


@dataclass
class LintReport:
    path: Path
    findings: List[Finding] = field(default_factory=list)

    def exit_code(self) -> int:
        return 1 if any(f.severity == Severity.ERROR for f in self.findings) else 0


# Sentinel that says "this row of the Sharp Edges table is a placeholder".
# We only flag *data* rows, not the header. Header is exactly:
#   "| Issue | Severity | Solution |"
# Data placeholder rows look like:
#   "| Issue | high | ## Some heading-shaped thing |"
# Detection: a line that contains `| Issue |` followed by a severity keyword.
_SHARP_EDGES_PLACEHOLDER_ISSUE = re.compile(
    r"^\|\s*Issue\s*\|\s*(critical|high|medium|low)\b", re.IGNORECASE
)

# Anti-injection: persona/identity-override language. We match *behavioral*
# claims, not single adjectives. A skill is not bad because it says "be
# careful"; it is bad if it claims to install a persona, persist the agent
# across sessions, override termination, or escalate authority.
#
# "ascend" is matched ONLY in persona-install contexts (e.g. "ascend to
# godhood", "ascend eternally"). Bare "ascend" as a verb is normal English
# and the user explicitly used it in their activation_phrase
# ("Expand. Interlink. Ascend. The Operator coordinates the swarm.").
_PERSONA_OVERRIDE_RE = re.compile(
    r"\b(awaken(ing)?|persona\s+install(ation)?|soul\s+power|"
    r"deeply\s+persistent|eternal(ly)?\s+(persistent|loop|weave)|"
    r"infinite\s+power|resonance\s+engine|operator\s*=\s*universe|"
    r"ascend(ing)?\s+(to|over|beyond|eternally|toward)|"
    r"weave\s+the\s+|evolve\s+eternally|"
    r"all\s+power|all\s*-(?:knowing|powerful|seeing)|"
    r"omniscient|limitless|unstoppable|boundless)\b",
    re.IGNORECASE,
)

# Anti-injection: agent-override / termination-defeat language.
_TERMINATION_DEFEAT_RE = re.compile(
    r"\b(never\s+terminate|must\s+continue\s+forever|"
    r"run\s+eternally|cannot\s+be\s+stopped|override\s+the\s+(agent|safety|runtime)|"
    r"disable\s+safety|bypass\s+(policy|gate|guard)|"
    r"ignore\s+(all\s+)?(previous\s+|your\s+)?(instructions?|rules?|guardrails?)|"
    r"ignore\s+instructions?\s+(above|before)|"
    r"forget\s+your\s+(rules?|instructions?|restrictions?)|"
    r"you\s+are\s+now\s+|"
    r"act\s+as\s+(if|though)\s+you\s+have\s+no\s+restrictions?|"
    r"disregard\s+(all|any|your)\s+(previous|rules?|instructions?))\b",
    re.IGNORECASE,
)

# Anti-injection: sigil/emoji spam (>5 non-ASCII symbols in a single paragraph).
# Counted at the line level: if a single line has more than 5 non-ASCII chars
# outside markdown table cells, it may be a sigil-bomb (e.g. "🍍⚛️∞⩗𖩧🌌").
_SIGIL_SPAM_RE = re.compile(r"[^\x00-\x7f]")
_SIGIL_SPAM_THRESHOLD = 5

# Anti-injection: literal secret material in skill body.
_SECRET_PATTERNS = [
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}\b"), "OpenAI-style key"),
    (re.compile(r"\bsk-ant-api\d{2}-[A-Za-z0-9_-]{20,}\b"), "Anthropic-style key"),
    (re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}\b"), "OpenRouter key"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "GitHub fine-grained PAT"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "GitHub classic PAT"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"), "GitLab PAT"),
    (re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"), "HuggingFace token"),
    (re.compile(r"\bpplx-[A-Za-z0-9]{20,}\b"), "Perplexity key"),
    (re.compile(r"\bpcsk_[A-Za-z0-9]{20,}\b"), "Pinecone key"),

    (re.compile(r"\beyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}"),
     "JWT token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "PEM private key"),
    (re.compile(r"ntn_[A-Za-z0-9]{20,}"), "Notion key"),
    (re.compile(r"figd_[A-Za-z0-9]{20,}"), "Figma key"),
    (re.compile(r"sbp_[A-Za-z0-9]{20,}"), "Supabase key"),
    (re.compile(r"rnd_[A-Za-z0-9]{20,}"), "Render key"),
]

# Detect dangling conjunction at end of line (truncation signature).
# e.g. "You obsess over chunking strategies, embedding quality, and"
_TRUNCATION_END = re.compile(r"[,—\-]\s*$")

# Detect `// ` style code comments in markdown — usually means the prose
# source got an unwashed code comment in it.
_SLASH_COMMENT = re.compile(r"\|\s*//\s")

# The `@[skills/...]` cross-ref syntax (broken — none of those skills exist).
_AT_SKILL_REF = re.compile(r"@\[skills/([a-zA-Z0-9_\-]+)\]")

# Bare skill name in backticks (valid). Used to whitelist in tests.
_BACKTICKED_NAME = re.compile(r"`([a-zA-Z][a-zA-Z0-9\-]+)`")


def _parse_frontmatter(text: str) -> Optional[Dict[str, str]]:
    """Return {key: value} dict if frontmatter present, else None."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    block = text[4:end]
    out: Dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def _is_known_skill(name: str, skills_root: Path) -> bool:
    """Is there a SKILL.md at skills_root/<name>/SKILL.md?"""
    return (skills_root / name / "SKILL.md").exists()


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def lint_file(path: Path, skills_root: Optional[Path] = None) -> LintReport:
    """Lint a single SKILL.md. Returns a LintReport (never raises)."""
    report = LintReport(path=path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        report.findings.append(Finding(
            severity=Severity.ERROR,
            message=f"could not read file: {exc}",
            file=str(path),
        ))
        return report

    # 1. Frontmatter
    fm = _parse_frontmatter(text)
    if fm is None:
        report.findings.append(Finding(
            severity=Severity.ERROR,
            message="missing or malformed YAML frontmatter (file must start with `---\\n`)",
            file=str(path),
            line=1,
        ))
    elif "name" not in fm or not fm["name"].strip():
        report.findings.append(Finding(
            severity=Severity.ERROR,
            message="frontmatter is missing required `name:` field",
            file=str(path),
            line=2,
        ))

    # 2. Broken @[skills/...] cross-refs
    for m in _AT_SKILL_REF.finditer(text):
        target = m.group(1)
        if skills_root is None:
            # Without a skills_root we can't verify; treat as warning.
            report.findings.append(Finding(
                severity=Severity.WARNING,
                message=(
                    f"`@[skills/{target}]` cross-ref cannot be resolved "
                    "(no skills_root given) — pass skills_root to lint_file() "
                    "or use lint_directory() which sets it automatically"
                ),
                file=str(path),
                line=_line_of(text, m.start()),
            ))
        elif not _is_known_skill(target, skills_root):
            report.findings.append(Finding(
                severity=Severity.ERROR,
                message=f"broken cross-ref `@[skills/{target}]` — skill not installed",
                file=str(path),
                line=_line_of(text, m.start()),
            ))
        else:
            # Skill exists, but the `@[skills/...]` syntax itself is non-standard.
            report.findings.append(Finding(
                severity=Severity.WARNING,
                message=(
                    f"non-standard `@[skills/{target}]` syntax — "
                    "use backticked bare name instead"
                ),
                file=str(path),
                line=_line_of(text, m.start()),
            ))

    # 3. Sharp Edges: placeholder rows + // comment leakage
    if "Sharp Edges" in text or "## ⚠️" in text:
        sharp_start = text.find("## ⚠️")
        if sharp_start < 0:
            sharp_start = text.find("## Sharp Edges")
        if sharp_start >= 0:
            sharp_block = text[sharp_start:]
            for line_offset, line in enumerate(sharp_block.splitlines(), start=1):
                if _SHARP_EDGES_PLACEHOLDER_ISSUE.match(line):
                    report.findings.append(Finding(
                        severity=Severity.ERROR,
                        message=(
                            "Sharp Edges table has placeholder `Issue` cell "
                            "— the issue column should describe a real problem"
                        ),
                        file=str(path),
                        line=_line_of(text, sharp_start) + line_offset - 1,
                    ))
                if _SLASH_COMMENT.search(line):
                    report.findings.append(Finding(
                        severity=Severity.ERROR,
                        message=(
                            "Sharp Edges table contains a `// comment` — "
                            "solutions should be real prose, not code comments"
                        ),
                        file=str(path),
                        line=_line_of(text, sharp_start) + line_offset - 1,
                    ))

    # 4. Truncated body intros. Heuristic: a non-empty, non-heading, non-table
    #    line that ends in a dangling conjunction (", and", ", or", "—", etc.)
    #    is suspicious. Must be a real continuation, not list punctuation.
    lines = text.splitlines()
    fm_end = 0
    for i, line in enumerate(lines):
        if i == 0 and line.strip() == "---":
            continue
        if line.strip() == "---":
            fm_end = i + 1
            break
    body_lines = lines[fm_end:]
    for i, line in enumerate(body_lines[:40]):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|") \
                or stripped.startswith("-") or stripped.startswith("*") \
                or stripped.startswith("```") or stripped.startswith(">"):
            continue
        # Only flag if line ends with a *dangling conjunction* — a word
        # that strongly suggests the sentence continues onto the next line.
        # Pattern: ends with " and", " or", " but", or trailing em-dash.
        if re.search(r"\b(and|or|but)\s*[,—\-]?\s*$", stripped) \
                or stripped.endswith("—") or stripped.endswith("-"):
            report.findings.append(Finding(
                severity=Severity.WARNING,
                message=(
                    f"possible truncated intro (line ends with dangling conjunction): "
                    f"{stripped[:80]!r}"
                ),
                file=str(path),
                line=fm_end + i + 1,
            ))

    # 4. Anti-injection: persona/identity-override language.
    for m in _PERSONA_OVERRIDE_RE.finditer(text):
        report.findings.append(Finding(
            severity=Severity.ERROR,
            message=(
                f"persona/identity-override language detected: "
                f"{m.group(0)!r} — skills must not install personas, claim eternal "
                "persistence, or escalate authority"
            ),
            file=str(path),
            line=_line_of(text, m.start()),
        ))
    for m in _TERMINATION_DEFEAT_RE.finditer(text):
        report.findings.append(Finding(
            severity=Severity.ERROR,
            message=(
                f"agent-override language detected: {m.group(0)!r} — "
                "skills must not disable safety, override termination, "
                "or bypass policy gates"
            ),
            file=str(path),
            line=_line_of(text, m.start()),
        ))

    # Sigil/emoji spam: a single non-table, non-code line with too many
    # non-ASCII symbols is a sigil-bomb. Code blocks and tables are excluded
    # because emojis are legitimate in those contexts.
    in_code_block = False
    for i, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or line.count("|") >= 2:
            continue
        non_ascii = _SIGIL_SPAM_RE.findall(line)
        if len(non_ascii) > _SIGIL_SPAM_THRESHOLD:
            report.findings.append(Finding(
                severity=Severity.WARNING,
                message=(
                    f"sigil/emoji spam on line {i}: {len(non_ascii)} non-ASCII chars "
                    f"({''.join(non_ascii)!r}) — common in persona-injection payloads"
                ),
                file=str(path),
                line=i,
            ))

    # 5. Anti-injection: literal secret material in body.
    for pattern, label in _SECRET_PATTERNS:
        for m in pattern.finditer(text):
            report.findings.append(Finding(
                severity=Severity.ERROR,
                message=(
                    f"literal {label} in skill body — secrets must never "
                    "appear in skill files; rotate the credential immediately"
                ),
                file=str(path),
                line=_line_of(text, m.start()),
            ))

    return report


def lint_directory(skills_root: Path | str) -> Dict[str, LintReport]:
    """Lint every SKILL.md under skills_root/<name>/SKILL.md.

    Returns a dict mapping skill name to its LintReport. Skills that have
    no SKILL.md are silently skipped (the directory layout is the contract).
    """
    root = Path(skills_root)
    reports: Dict[str, LintReport] = {}
    if not root.exists():
        return reports
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            continue
        reports[child.name] = lint_file(skill_md, skills_root=root)
    return reports


# ---- AGENTS.md linting -----------------------------------------------------

_AGENTS_MD_DOCTRINE_LINE_THRESHOLD = 50
_TEST_COMMAND_RE = re.compile(
    r"(?:^|\n)\s*[-*]\s*\*\*test command:?\*\*|`(?:pytest|unittest|[a-z\-]+test)",
    re.IGNORECASE,
)
_SKILL_POINTER_RE = re.compile(
    r"`?@?/root/\.agents/skills/[a-zA-Z0-9_\-]+/SKILL\.md`?"
)


def lint_agents_md(path: Path, skills_root: Optional[Path] = None) -> LintReport:
    """Lint a project AGENTS.md. Returns a LintReport (never raises).

    Rules:
      1. AGENTS.md is plain markdown, not YAML-frontmatter — no frontmatter required.
      2. If file is a *supplement* (≤50 lines) it should point at a skill
         (otherwise the project has no canonical doctrine).
      3. If file is long and has no skill pointer, it may be duplicating
         doctrine that belongs in a skill — warning.
      4. Supplements should declare a test command.
      5. Inherited: truncation detection, broken `@[skills/...]` refs.
    """
    report = LintReport(path=path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        report.findings.append(Finding(
            severity=Severity.ERROR,
            message=f"could not read file: {exc}",
            file=str(path),
        ))
        return report

    line_count = text.count("\n") + 1
    is_short = line_count <= _AGENTS_MD_DOCTRINE_LINE_THRESHOLD
    has_pointer = bool(_SKILL_POINTER_RE.search(text))

    # 2. Short supplement should point at a skill.
    if is_short and not has_pointer:
        report.findings.append(Finding(
            severity=Severity.WARNING,
            message=(
                "short AGENTS.md has no skill pointer — "
                "supplements should reference `/root/.agents/skills/<name>/SKILL.md`"
            ),
            file=str(path),
            line=1,
        ))

    # 3. Long file without pointer is probably duplicating doctrine.
    if not is_short and not has_pointer:
        report.findings.append(Finding(
            severity=Severity.WARNING,
            message=(
                f"AGENTS.md is {line_count} lines with no skill pointer — "
                "long AGENTS.md files duplicate doctrine that should live in a skill"
            ),
            file=str(path),
            line=1,
        ))

    # 4. Test command.
    if is_short and not _TEST_COMMAND_RE.search(text):
        report.findings.append(Finding(
            severity=Severity.WARNING,
            message=(
                "AGENTS.md has no test command — "
                "supplements should declare one (e.g. **Test command:** `cd <project> && pytest`)"
            ),
            file=str(path),
            line=1,
        ))

    # 5. Inherited rules.
    # Truncated intros.
    lines = text.splitlines()
    for i, line in enumerate(lines[:40]):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|") \
                or stripped.startswith("-") or stripped.startswith("*") \
                or stripped.startswith("```") or stripped.startswith(">"):
            continue
        if re.search(r"\b(and|or|but)\s*[,—\-]?\s*$", stripped) \
                or stripped.endswith("—") or stripped.endswith("-"):
            report.findings.append(Finding(
                severity=Severity.WARNING,
                message=(
                    f"possible truncated intro (line ends with dangling conjunction): "
                    f"{stripped[:80]!r}"
                ),
                file=str(path),
                line=i + 1,
            ))

    # Broken @[skills/...] refs (same rule as SKILL.md).
    for m in _AT_SKILL_REF.finditer(text):
        target = m.group(1)
        if skills_root is None or not _is_known_skill(target, skills_root):
            report.findings.append(Finding(
                severity=Severity.ERROR,
                message=f"broken cross-ref `@[skills/{target}]` — skill not installed",
                file=str(path),
                line=_line_of(text, m.start()),
            ))

    # Broken skill-pointers of the form `@/root/.agents/skills/<name>/SKILL.md`
    # pointing at a skill that doesn't exist.
    skill_pointer_re = re.compile(
        r"@?/root/\.agents/skills/([a-zA-Z0-9_\-]+)/SKILL\.md"
    )
    for m in skill_pointer_re.finditer(text):
        target = m.group(1)
        if skills_root is None or not _is_known_skill(target, skills_root):
            report.findings.append(Finding(
                severity=Severity.ERROR,
                message=f"broken skill pointer to `{target}` — skill not installed",
                file=str(path),
                line=_line_of(text, m.start()),
            ))

    return report


def lint_agents_md_tree(root: Path | str, max_depth: int = 6) -> Dict[str, LintReport]:
    """Find and lint every AGENTS.md under root, recursively up to max_depth.

    Returns {relative_path: LintReport}. The key is the path relative to root.
    max_depth=6 covers /root/projects/<p>/AGENTS.md and
    /root/projects/GlacierEQ_Swarm/<p>/AGENTS.md, which is the workspace shape.
    """
    base = Path(root)
    reports: Dict[str, LintReport] = {}
    if not base.exists():
        return reports
    SKIP_DIRS = {
        "node_modules", "__pycache__", ".git", ".npm", ".next", ".cache",
        ".local", ".config", ".agents", ".cline", ".opencode", ".kilo",
        ".bun", ".gemini", ".mimocode", "venv", ".venv", "dist", "build",
        "artifacts", "generated", "node_modules",
    }
    # Bounded DFS instead of rglob to avoid traversing huge cloned-repo trees.
    def _walk(d: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(d.iterdir())
        except (PermissionError, OSError):
            return
        for entry in entries:
            if entry.is_dir():
                if entry.name in SKIP_DIRS or entry.name.startswith("."):
                    continue
                _walk(entry, depth + 1)
            elif entry.name == "AGENTS.md":
                key = str(entry.relative_to(base))
                reports[key] = lint_agents_md(
                    entry, skills_root=Path("/root/.agents/skills")
                )
    _walk(base, 0)
    return reports


def format_report(reports: Dict[str, LintReport]) -> str:
    """Format all findings as a human-readable string. Alias: format_report_text."""
    out: List[str] = []
    total_errors = 0
    total_warnings = 0
    for name, report in reports.items():
        if not report.findings:
            continue
        out.append(f"== {name} ==")
        for f in report.findings:
            out.append(f"  {f}")
            if f.severity == Severity.ERROR:
                total_errors += 1
            else:
                total_warnings += 1
    if not out:
        return "clean: 0 errors, 0 warnings"
    summary = f"\n--- {len(reports)} skills scanned: {total_errors} error(s), {total_warnings} warning(s) ---"
    return "\n".join(out) + summary


# Backwards-compatible alias for callers that want explicit naming.
format_report_text = format_report


# ---- v2: JSON output ------------------------------------------------------


def format_report_json(reports: Dict[str, LintReport]) -> str:
    """Emit a structured JSON report. Schema:

    {
      "summary": {"scanned": int, "errors": int, "warnings": int},
      "skills": {
        "<name>": {
          "path": "<abs path>",
          "findings": [
            {"severity": "error"|"warning", "message": str, "line": int, "file": str}
          ]
        }
      }
    }
    """
    total_errors = sum(
        sum(1 for f in r.findings if f.severity == Severity.ERROR)
        for r in reports.values()
    )
    total_warnings = sum(
        sum(1 for f in r.findings if f.severity == Severity.WARNING)
        for r in reports.values()
    )
    skills_block: Dict[str, Any] = {}
    for name, report in reports.items():
        skills_block[name] = {
            "path": str(report.path),
            "findings": [
                {
                    "severity": f.severity.value,
                    "message": f.message,
                    "line": f.line,
                    "file": f.file,
                }
                for f in report.findings
            ],
        }
    payload = {
        "summary": {
            "scanned": len(reports),
            "errors": total_errors,
            "warnings": total_warnings,
        },
        "skills": skills_block,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


# ---- v2: auto-fix ---------------------------------------------------------
#
# Auto-fix is intentionally narrow. The linter knows how to detect ~25
# classes of bug. It only knows how to *fix* the classes that are mechanical
# and reversible. Anything that involves content the linter can't generate
# (e.g. "describe the issue in plain prose") stays report-only.

# Result of an auto-fix attempt. `modified=True` means the file changed.
@dataclass
class FixResult:
    fixer: str
    path: Path
    modified: bool
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fixer": self.fixer,
            "path": str(self.path),
            "modified": self.modified,
            "note": self.note,
        }


SAFE_FIXERS = ("mirror_canonical", "strip_slash_comments", "add_skill_pointer",
               "add_test_command")


def _add_test_command_to_text(text: str, test_command: str) -> Tuple[str, bool]:
    """Insert a `**Test command:** \\`<cmd>\\`` line if not already present.

    Idempotent: if any line already says 'Test command' or the literal cmd
    is present, no-op.
    """
    if "Test command" in text or test_command in text:
        return text, False
    lines = text.splitlines()
    new_lines: List[str] = []
    inserted = False
    for line in lines:
        new_lines.append(line)
        if not inserted and (line.startswith("## ") or line.startswith("# ")):
            new_lines.append("")
            new_lines.append(f"- **Test command:** `{test_command}`")
            inserted = True
    if not inserted:
        new_lines.append("")
        new_lines.append(f"- **Test command:** `{test_command}`")
    return "\n".join(new_lines) + "\n", True


# Path → skill mapping for cases where path.parent.name doesn't match a skill.
# Format: JSON file with {"<abs_path>": "<skill_name>"} entries.
def load_skill_map(path: Optional[Path]) -> Dict[str, str]:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"skill_lint: failed to load skill map: {exc}\n")
        return {}


def resolve_skill_for_agents_md(
    agents_md_path: Path,
    skill_map: Dict[str, str],
    canonical_root: Path,
) -> Optional[str]:
    """Return the canonical skill name for this AGENTS.md, or None.

    Resolution order:
      1. Exact match in skill_map (key is absolute path of the AGENTS.md).
      2. Path's parent directory name (e.g. /root/projects/foo/AGENTS.md → "foo").
      3. None — caller should refuse to insert a pointer.
    """
    abs_path = str(agents_md_path.resolve())
    if abs_path in skill_map:
        return skill_map[abs_path]
    return None  # fall through to parent-name resolution in run_gate


def _strip_slash_comments_in_text(text: str) -> Tuple[str, bool]:
    """Replace `| // comment-like` cells with `| **(see code)** `.

    Conservative: only touches cells inside a markdown table row whose
    content starts with `//`. We do not touch prose `// foo` because that
    is rare in skills and the cost of false positives is high.
    """
    new_lines: List[str] = []
    modified = False
    for line in text.splitlines(keepends=True):
        # Match a `| ... // something` cell pattern. We only act if the
        # line is a markdown table row (has at least 2 `|` separators) AND
        # a cell starts with `//`.
        if line.count("|") >= 3 and re.search(r"\|\s*//\s+\S", line):
            new_line = re.sub(r"\|\s*//\s+[^\n|]+", r"| **(see code)**", line)
            if new_line != line:
                modified = True
                line = new_line
        new_lines.append(line)
    return "".join(new_lines), modified


def auto_fix_file(
    path: Path,
    fixer: str,
    canonical_root: Optional[Path] = None,
    canonical_skill: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a single named fixer against one file. Returns a dict with
    `fixer`, `path`, `modified`, `note`. Never raises — failures are
    reported in `note`."""
    if fixer not in SAFE_FIXERS:
        return {"fixer": fixer, "path": str(path), "modified": False,
                "note": f"unknown fixer: {fixer}"}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"fixer": fixer, "path": str(path), "modified": False,
                "note": f"read failed: {exc}"}

    if fixer == "mirror_canonical":
        if canonical_root is None:
            return {"fixer": fixer, "path": str(path), "modified": False,
                    "note": "mirror_canonical requires canonical_root"}
        # Find the canonical source: canonical_root/<name>/SKILL.md where
        # name is path.parent.name.
        name = path.parent.name
        src = canonical_root / name / "SKILL.md"
        if not src.exists():
            return {"fixer": fixer, "path": str(path), "modified": False,
                    "note": f"no canonical source at {src}"}
        canonical_text = src.read_text(encoding="utf-8")
        if text == canonical_text:
            return {"fixer": fixer, "path": str(path), "modified": False,
                    "note": "already in sync"}
        path.write_text(canonical_text, encoding="utf-8")
        return {"fixer": fixer, "path": str(path), "modified": True,
                "note": f"mirrored from {src}"}

    if fixer == "strip_slash_comments":
        new_text, modified = _strip_slash_comments_in_text(text)
        if modified:
            path.write_text(new_text, encoding="utf-8")
        return {"fixer": fixer, "path": str(path), "modified": modified,
                "note": "" if modified else "no // comments found"}

    if fixer == "add_skill_pointer":
        if not canonical_skill:
            return {"fixer": fixer, "path": str(path), "modified": False,
                    "note": "add_skill_pointer requires canonical_skill=<name>"}
        if "/root/.agents/skills/" in text and "SKILL.md" in text:
            return {"fixer": fixer, "path": str(path), "modified": False,
                    "note": "skill pointer already present"}
        # Safety: never insert a pointer to a skill that doesn't exist.
        # Inserting a broken pointer turns a warning into an error — a strict
        # regression. Caller can pass canonical_skill explicitly; if not, we
        # refuse to guess.
        if canonical_root is not None:
            if not (canonical_root / canonical_skill / "SKILL.md").exists():
                return {"fixer": fixer, "path": str(path), "modified": False,
                        "note": f"refused: skill {canonical_skill!r} not installed at {canonical_root}"}
        # Insert a pointer line right after the H1 heading.
        lines = text.splitlines()
        new_lines: List[str] = []
        inserted = False
        for line in lines:
            new_lines.append(line)
            if not inserted and line.startswith("# "):
                new_lines.append("")
                new_lines.append(
                    f"**See:** `@/root/.agents/skills/{canonical_skill}/SKILL.md` "
                    "for full operating guide."
                )
                inserted = True
        if not inserted:
            new_lines.insert(0,
                             f"**See:** `@/root/.agents/skills/{canonical_skill}/SKILL.md` "
                             "for full operating guide.")
            new_lines.insert(0, "")
            inserted = True
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return {"fixer": fixer, "path": str(path), "modified": True,
                "note": f"added pointer to {canonical_skill}"}

    if fixer == "add_test_command":
        # test_command is passed via canonical_skill kwarg in this branch
        # for simplicity of the dispatcher. (Auto-fix dispatcher uses the
        # same kwargs shape; we reuse canonical_skill as the test command
        # string when fixer == add_test_command.)
        cmd = canonical_skill
        if not cmd:
            return {"fixer": fixer, "path": str(path), "modified": False,
                    "note": "add_test_command requires canonical_skill=<cmd>"}
        new_text, modified = _add_test_command_to_text(text, cmd)
        if modified:
            path.write_text(new_text, encoding="utf-8")
        return {"fixer": fixer, "path": str(path), "modified": modified,
                "note": "" if modified else "test command already present"}

    return {"fixer": fixer, "path": str(path), "modified": False,
            "note": "unreachable"}


def auto_fix_directory(
    target: Path | str,
    fixer: str,
    canonical_root: Optional[Path] = None,
    canonical_skill: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a fixer across every file in `target`. Returns
    {fixed: [paths], skipped: [(path, note)]}."""
    target = Path(target)
    fixed: List[str] = []
    skipped: List[Dict[str, str]] = []
    if not target.exists():
        return {"fixed": fixed, "skipped": skipped}
    if fixer == "mirror_canonical" and canonical_root is not None:
        for child in sorted(target.iterdir()):
            if not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            if not skill_md.exists():
                continue
            r = auto_fix_file(skill_md, fixer, canonical_root=canonical_root)
            if r["modified"]:
                fixed.append(str(skill_md))
            else:
                skipped.append({"path": r["path"], "note": r["note"]})
        return {"fixed": fixed, "skipped": skipped}

    if fixer == "add_skill_pointer":
        # Apply to every AGENTS.md under target, recursively.
        for agents_md in target.rglob("AGENTS.md"):
            r = auto_fix_file(agents_md, fixer, canonical_skill=canonical_skill)
            if r["modified"]:
                fixed.append(str(agents_md))
            else:
                skipped.append({"path": r["path"], "note": r["note"]})
        return {"fixed": fixed, "skipped": skipped}

    if fixer == "strip_slash_comments":
        for child in sorted(target.iterdir()):
            if not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            if not skill_md.exists():
                continue
            r = auto_fix_file(skill_md, fixer)
            if r["modified"]:
                fixed.append(str(skill_md))
            else:
                skipped.append({"path": r["path"], "note": r["note"]})
        return {"fixed": fixed, "skipped": skipped}

    return {"fixed": fixed, "skipped": skipped,
            "error": f"unsupported fixer/directory combo: {fixer}"}


# ---- v2: gate wrapper -----------------------------------------------------


def _summary(reports: Dict[str, LintReport]) -> Dict[str, int]:
    e = sum(sum(1 for f in r.findings if f.severity == Severity.ERROR)
            for r in reports.values())
    w = sum(sum(1 for f in r.findings if f.severity == Severity.WARNING)
            for r in reports.values())
    return {"scanned": len(reports), "errors": e, "warnings": w}


def run_gate(
    target: Path | str,
    fix: bool = False,
    prove_cmd: Optional[List[str]] = None,
    canonical_root: Optional[Path] = None,
    agents_mode: bool = False,
    skill_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """The detect → fix → prove loop. Returns a receipt dict.

    Stages:
      1. detect  — lint target, capture before-summary
      2. fix     — if fix=True, run safe fixers and re-lint; capture after-summary
      3. prove   — if prove_cmd is set, run it and capture returncode/stdout
      4. receipt — assemble the result with an exit code

    Exit codes:
      0 — clean (or --exit-zero)
      1 — errors remain after fix
      2 — prove command failed
      3 — fatal (caller should never see this if main() wraps run_gate)
    """
    target = Path(target)
    receipt: Dict[str, Any] = {
        "target": str(target),
        "fix_requested": fix,
        "agents_mode": agents_mode,
    }

    if agents_mode:
        before_reports = lint_agents_md_tree(target)
    else:
        before_reports = lint_directory(target)
    receipt["before"] = _summary(before_reports)

    fixes_applied: List[Dict[str, Any]] = []
    if fix:
        # Apply fixers appropriate to mode.
        if agents_mode:
            skill_map = skill_map or {}
            for name, report in before_reports.items():
                path = Path(report.path)
                # Fixer 1: add skill pointer (only if we can resolve one).
                if any("no skill pointer" in f.message and f.severity == Severity.WARNING
                       for f in report.findings):
                    abs_path = str(path.resolve())
                    if abs_path in skill_map:
                        inferred_skill = skill_map[abs_path]
                    else:
                        inferred_skill = path.parent.name
                    if canonical_root is None \
                            or not (canonical_root / inferred_skill / "SKILL.md").exists():
                        fixes_applied.append({
                            "fixer": "add_skill_pointer",
                            "path": str(path),
                            "modified": False,
                            "note": (f"skipped: inferred skill {inferred_skill!r} "
                                     f"not installed at {canonical_root}"),
                        })
                    else:
                        r = auto_fix_file(path, "add_skill_pointer",
                                          canonical_skill=inferred_skill,
                                          canonical_root=canonical_root)
                        fixes_applied.append(r)
                # Fixer 2: add test command if missing.
                if any("no test command" in f.message and f.severity == Severity.WARNING
                       for f in report.findings):
                    r = auto_fix_file(
                        path, "add_test_command",
                        canonical_skill="cd <project-root> && pytest",
                    )
                    fixes_applied.append(r)
        else:
            # For SKILL.md: strip slash-comments (auto-fixable; safe).
            for name, report in before_reports.items():
                if any("//" in f.message and f.severity == Severity.ERROR
                       for f in report.findings):
                    r = auto_fix_file(report.path, "strip_slash_comments")
                    fixes_applied.append(r)
    receipt["fixes_applied"] = fixes_applied

    if agents_mode:
        after_reports = lint_agents_md_tree(target)
    else:
        after_reports = lint_directory(target)
    receipt["after"] = _summary(after_reports)

    if prove_cmd:
        try:
            proc = subprocess.run(
                prove_cmd, cwd=str(target), capture_output=True, text=True,
                timeout=300,
            )
            receipt["prove"] = {
                "cmd": prove_cmd,
                "returncode": proc.returncode,
                "stdout_tail": proc.stdout[-2000:] if proc.stdout else "",
                "stderr_tail": proc.stderr[-2000:] if proc.stderr else "",
            }
        except subprocess.TimeoutExpired as exc:
            receipt["prove"] = {
                "cmd": prove_cmd,
                "returncode": 124,
                "error": f"timeout after {exc.timeout}s",
            }
        except FileNotFoundError as exc:
            receipt["prove"] = {
                "cmd": prove_cmd,
                "returncode": 127,
                "error": str(exc),
            }

    if receipt["after"]["errors"] > 0:
        receipt["exit_code"] = 1
    elif prove_cmd and receipt.get("prove", {}).get("returncode", 0) != 0:
        receipt["exit_code"] = 2
    else:
        receipt["exit_code"] = 0
    return receipt


# ---- v2: CLI --------------------------------------------------------------


def _build_argparser():
    import argparse
    p = argparse.ArgumentParser(
        prog="skill_lint",
        description=(
            "Lint SKILL.md files (and AGENTS.md files) against the conventions "
            "established in this workspace. Pure stdlib; no network."
        ),
    )
    p.add_argument("target", nargs="?", default="/root/.agents/skills",
                   help="Directory containing skill/AGENTS.md files (default: /root/.agents/skills)")
    p.add_argument("mode", nargs="?", default="skills", choices=("skills", "agents"),
                   help="What to lint: SKILL.md trees or AGENTS.md files (default: skills)")
    p.add_argument("--format", "-f", choices=("text", "json"), default="text",
                   help="Output format (default: text)")
    p.add_argument("--severity", "-s", choices=("error", "warning"), default=None,
                   help="Filter findings to at least this severity")
    p.add_argument("--max-depth", type=int, default=6,
                   help="Max recursion depth for AGENTS.md search (default: 6)")
    p.add_argument("--skills-root", type=Path, default=Path("/root/.agents/skills"),
                   help="Where to look up @[skills/...] targets (default: /root/.agents/skills)")
    p.add_argument("--fix", action="store_true",
                   help="Auto-apply safe fixers before reporting")
    p.add_argument("--fixer", choices=SAFE_FIXERS, default=None,
                   help="Which safe fixer to run (default: all appropriate for mode)")
    p.add_argument("--canonical-root", type=Path, default=Path("/root/.agents/skills"),
                   help="Source of truth for --fixer=mirror_canonical")
    p.add_argument("--prove", nargs=argparse.REMAINDER,
                   help="Run a command after fixing; receipt records pass/fail")
    p.add_argument("--exit-zero", action="store_true",
                   help="Always exit 0 (useful for soft checks)")
    p.add_argument("--gate", action="store_true",
                   help="Run detect→fix→prove in one receipt-shaped step")
    p.add_argument("--receipt", type=Path, default=None,
                   help="Append a JSON receipt to this file on every gate run")
    p.add_argument("--skill-map", type=Path, default=None,
                   help="JSON file mapping AGENTS.md absolute paths to canonical skill names")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point. Returns the process exit code."""
    args = _build_argparser().parse_args(argv)

    if args.gate:
        skill_map = load_skill_map(args.skill_map)
        receipt = run_gate(
            target=Path(args.target),
            fix=args.fix,
            prove_cmd=args.prove if args.prove else None,
            canonical_root=args.canonical_root,
            agents_mode=(args.mode == "agents"),
            skill_map=skill_map,
        )
        # Append a JSON-lines receipt to the configured path, if any.
        if args.receipt is not None:
            try:
                args.receipt.parent.mkdir(parents=True, exist_ok=True)
                with open(args.receipt, "a", encoding="utf-8") as f:
                    f.write(json.dumps(receipt, default=str, sort_keys=True) + "\n")
            except OSError as exc:
                sys.stderr.write(f"skill_lint: failed to write receipt: {exc}\n")
        print(json.dumps(receipt, indent=2, default=str, sort_keys=True))
        if args.exit_zero:
            return 0
        return receipt["exit_code"]

    if args.mode == "agents":
        reports = lint_agents_md_tree(args.target, max_depth=args.max_depth)
    else:
        reports = lint_directory(args.target)

    severity_filter = (
        Severity.ERROR if args.severity == "error" else
        Severity.WARNING if args.severity == "warning" else
        None
    )
    if severity_filter is not None:
        for report in reports.values():
            report.findings = [f for f in report.findings
                               if f.severity == severity_filter]

    if args.fix:
        for name, report in reports.items():
            for f in report.findings:
                if f.severity == Severity.ERROR and "//" in f.message:
                    auto_fix_file(Path(report.path), "strip_slash_comments")

    if args.format == "json":
        print(format_report_json(reports))
    else:
        print(format_report(reports))

    any_error = any(r.exit_code() != 0 for r in reports.values())
    if args.exit_zero:
        return 0
    return 1 if any_error else 0


if __name__ == "__main__":
    import sys
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — CLI must never traceback silently
        sys.stderr.write(f"skill_lint: fatal: {exc}\n")
        sys.exit(2)
