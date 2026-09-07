"""
sequencer.discover — per-repo profile builder.

The profile is the *input* to the plan builder. It is per-repo unique
because it is built from the repo's actual filesystem, git history, and
conventions — not from a fixed checklist. The whole anti-cookie-cutter
guarantee flows from this: a different profile yields a different plan.

Signals captured
----------------
- has_python_src / has_module_init / no_main_module / has_tests
- test_framework (pytest | unittest | none)
- has_persistent_state / has_log_path / log_file_empty / has_sibling_orphan
- has_user_docs / docs_drift_detected
- sibling_has_meta_catalog / not_in_catalog
- smoke_unproven
- runtime_state_overlap / has_sibling_repo_with_runtime
- recent_change_window (mtime of the most recent src file, in days)
- test_count_recent (pytest --collect-only)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


# A path inside a repo counts as a sibling when it is a known-flag dir name.
KNOWN_FLAGSHIP_DIRS = {
    "make-it-heavy", "monolith", "mastermind", "mermicorn",
    "tower-of-babel", "computer-user", "the-tower-of-babel",
}


@dataclass
class Profile:
    """A per-repo profile: signals that determine which patterns apply."""

    path: str
    name: str
    signals: Dict[str, Any] = field(default_factory=dict)

    def has(self, signal: str) -> bool:
        return bool(self.signals.get(signal, False))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "signals": self.signals,
        }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _git(path: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _file_exists(p: Path) -> bool:
    return p.exists() and p.is_file()


def _dir_exists(p: Path) -> bool:
    return p.exists() and p.is_dir()


def _collect_test_count(repo: Path) -> Optional[int]:
    if not _dir_exists(repo / "tests"):
        return None
    proc = subprocess.run(
        ["python3", "-m", "pytest", "tests/", "--collect-only", "-q"],
        capture_output=True, text=True, cwd=str(repo), timeout=60,
    )
    if proc.returncode != 0:
        return None
    total = 0
    saw_any = False
    for line in proc.stdout.splitlines():
        m = re.match(r"^.+?:\s+(\d+)\s*$", line)
        if m:
            total += int(m.group(1))
            saw_any = True
    if not saw_any:
        m = re.search(r"(\d+)\s+tests collected", proc.stdout)
        if m:
            return int(m.group(1))
    return total if saw_any else None


def _detect_test_framework(repo: Path) -> str:
    tests_dir = repo / "tests"
    if not _dir_exists(tests_dir):
        return "none"
    has_pytest_ini = (
        _file_exists(repo / "pytest.ini")
        or _file_exists(repo / "pyproject.toml")
    )
    for f in tests_dir.rglob("test_*.py"):
        text = _read_text(f)
        if "import unittest" in text or "from unittest" in text:
            return "unittest"
    if has_pytest_ini:
        return "pytest"
    # No unittest imports found, has tests dir; default is pytest in this estate.
    if any(tests_dir.glob("test_*.py")):
        return "pytest"
    return "none"


def _detect_user_docs(repo: Path) -> bool:
    candidates = ["STATUS.md", "ROADMAP.md", "CANONICAL.md", "docs/PROBLEM.md", "docs/PROOF_GATES.md"]
    return any(_file_exists(repo / c) for c in candidates)


def _detect_docs_drift(repo: Path) -> bool:
    """A drift signal: the user-authored docs reference a stale date OR a
    stale version string that no longer matches the code."""
    status = _read_text(repo / "STATUS.md")
    canonical = _read_text(repo / "CANONICAL.md")
    setup_py = _read_text(repo / "setup.py")
    pkg_init = _read_text(repo / "src" / "src" / "__init__.py")
    if not pkg_init:
        # try other common layouts
        for cand in repo.rglob("__init__.py"):
            if "src" in str(cand):
                pkg_init = _read_text(cand)
                break

    # Find today's date in YYYY-MM-DD form anywhere in the docs.
    drift_reasons: List[str] = []
    if status:
        m = re.search(r"Last updated:\*\*\s+(\d{4}-\d{2}-\d{2})", status)
        if m:
            # Anything older than 30 days is considered drifted.
            from datetime import date
            try:
                last = date.fromisoformat(m.group(1))
                if (date.today() - last).days > 30:
                    drift_reasons.append(f"STATUS.md last_updated {m.group(1)} > 30d ago")
            except ValueError:
                pass
    if canonical:
        m = re.search(r"Last Updated\*\*:\s+(\d{4}-\d{2}-\d{2})", canonical)
        if m:
            from datetime import date
            try:
                last = date.fromisoformat(m.group(1))
                if (date.today() - last).days > 60:
                    drift_reasons.append(f"CANONICAL.md last_updated {m.group(1)} > 60d ago")
            except ValueError:
                pass
    # Version drift: setup.py says 0.1.0 but the package says 0.2.0.
    setup_v = re.search(r'version\s*=\s*["\']([\d.]+)["\']', setup_py)
    pkg_v = re.search(r"__version__\s*=\s*[\"']([\d.]+)[\"']", pkg_init)
    if setup_v and pkg_v and setup_v.group(1) != pkg_v.group(1):
        drift_reasons.append(
            f"version drift: setup.py={setup_v.group(1)} package={pkg_v.group(1)}"
        )
    return bool(drift_reasons), drift_reasons


def _detect_sibling_repos(workspace: Path, self_path: Path) -> List[str]:
    """Top-level siblings under /root/projects that are known repos."""
    if not _dir_exists(workspace):
        return []
    return sorted(
        p.name for p in workspace.iterdir()
        if p.is_dir() and p != self_path and not p.name.startswith(".")
    )


def _detect_sibling_orphan(repo: Path) -> Optional[str]:
    """A `.db`, `.sqlite`, or similar file next to the canonical state file
    that the code no longer references."""
    candidates = []
    for ext in (".db", ".sqlite", ".sqlite3"):
        for p in repo.glob(f"**/*{ext}"):
            candidates.append(p)
    # Heuristic: if any .db file is older than the most-recent src change,
    # AND no src file imports sqlite3, treat it as orphan.
    src_files = []
    for root, _, files in os.walk(repo / "src"):
        for f in files:
            if f.endswith(".py"):
                src_files.append(Path(root) / f)
    if not src_files:
        return None
    most_recent_src = max(src_files, key=lambda p: p.stat().st_mtime, default=None)
    for db in candidates:
        if most_recent_src and db.stat().st_mtime < most_recent_src.stat().st_mtime:
            # Check no src file imports sqlite3
            for sf in src_files:
                if "sqlite3" in _read_text(sf):
                    return None
            return str(db.relative_to(repo))
    return None


def _detect_runtime_state_overlap(repo: Path) -> bool:
    """Does the repo share a state directory (/root/.token_saver etc) with a
    known flagship? Cheap heuristic: look for the canonical state dirs."""
    canonical_state = {
        "/root/.token_saver", "/root/.tower", "/root/.swarm",
        "/root/.tiered_memory", "/root/.swarm_memory",
    }
    for p in canonical_state:
        if _dir_exists(Path(p)):
            return True
    return False


def build_profile(repo_path: str) -> Profile:
    """Build a per-repo profile by reading the repo's actual state."""
    repo = Path(repo_path).resolve()
    if not _dir_exists(repo):
        raise FileNotFoundError(f"repo not found: {repo}")
    name = repo.name

    src_dir = repo / "src"
    has_python_src = (
        any(repo.glob("**/*.py"))
        and (src_dir.is_dir() or any(repo.glob("*.py")))
    )
    has_module_init = any(repo.glob("**/__init__.py"))

    # main module detection: walk src and look for a __main__.py
    no_main_module = has_module_init and not any(repo.glob("**/__main__.py"))

    # persistent state: look for canonical state paths near the repo
    has_persistent_state = False
    state_path = None
    for d in ("/root/.token_saver", f"/root/{name.replace('-', '_')}"):
        if _dir_exists(Path(d)):
            has_persistent_state = True
            state_path = d
            break

    # log path + empty log
    has_log_path = False
    log_file_empty = False
    if has_persistent_state and state_path:
        for cand in ("token_saver.log", f"{name.replace('-', '_')}.log"):
            log = Path(state_path) / cand
            if log.exists():
                has_log_path = True
                log_file_empty = log.stat().st_size == 0
                break

    # orphan
    sibling_orphan = _detect_sibling_orphan(repo)
    has_sibling_orphan = sibling_orphan is not None

    # docs
    has_user_docs = _detect_user_docs(repo)
    docs_drift = False
    drift_reasons: List[str] = []
    if has_user_docs:
        dd = _detect_docs_drift(repo)
        if isinstance(dd, tuple):
            docs_drift, drift_reasons = dd
        else:
            docs_drift = dd

    # test framework
    test_framework = _detect_test_framework(repo)
    test_count = _collect_test_count(repo)

    # siblings + catalog
    # The "workspace" is the top-level /root/projects dir when the repo
    # lives one or two levels under it. Walk up the path and take the
    # first ancestor whose name is "projects" — that's where the sibling
    # flagships (monolith, make-it-heavy, ...) actually live.
    workspace = repo.parent
    while workspace != workspace.parent and workspace.name != "projects":
        workspace = workspace.parent
    siblings = _detect_sibling_repos(workspace, repo)

    # A repo is "in the catalog" either when it appears by name in the
    # monolith core_mesh, OR when the repo IS monolith (which owns the
    # catalog and is the meta-layer).
    sibling_has_meta_catalog = "monolith" in siblings or name == "monolith"
    not_in_catalog = False
    if sibling_has_meta_catalog and name != "monolith":
        # Look for the repo name in monolith's core_mesh.json
        core_mesh = workspace / "monolith" / "catalog" / "core_mesh.json"
        if _file_exists(core_mesh):
            try:
                doc = json.loads(_read_text(core_mesh))
                names = [c.get("repository", "") for c in doc.get("verified_consumers", [])]
                names += [c.get("repository", "") for c in doc.get("pending_consumers", [])]
                not_in_catalog = not any(name in n for n in names)
            except json.JSONDecodeError:
                pass

    # smoke unproven: when the repo has a persistent state and that state is
    # the default-untouched size, we haven't proven the live path works.
    smoke_unproven = False
    if has_persistent_state and state_path:
        # The signal is "the canonical state file exists and is small but
        # there is no log evidence of recent live use".
        if has_log_path and log_file_empty:
            smoke_unproven = True

    # runtime overlap with a sibling
    runtime_state_overlap = _detect_runtime_state_overlap(repo)
    has_sibling_repo_with_runtime = any(
        s in KNOWN_FLAGSHIP_DIRS for s in siblings
    ) and runtime_state_overlap

    # recent change window — how stale is the repo's code?
    recent_change_window_days: Optional[int] = None
    src_files = []
    for ext in ("*.py", "*.ts", "*.rs", "*.js"):
        for p in repo.glob(f"**/{ext}"):
            if "/.git/" in str(p) or "/__pycache__/" in str(p):
                continue
            src_files.append(p)
    if src_files:
        import time
        most_recent = max(p.stat().st_mtime for p in src_files)
        recent_change_window_days = int((time.time() - most_recent) / 86400)

    signals: Dict[str, Any] = {
        "has_python_src": has_python_src,
        "has_module_init": has_module_init,
        "no_main_module": no_main_module,
        "has_tests": test_framework != "none",
        "test_framework": test_framework,
        "test_count": test_count,
        "has_persistent_state": has_persistent_state,
        "persistent_state_path": state_path,
        "has_log_path": has_log_path,
        "log_file_empty": log_file_empty,
        "has_sibling_orphan": has_sibling_orphan,
        "orphan_path": sibling_orphan,
        "has_user_docs": has_user_docs,
        "docs_drift_detected": docs_drift,
        "docs_drift_reasons": drift_reasons,
        "sibling_has_meta_catalog": sibling_has_meta_catalog,
        "not_in_catalog": not_in_catalog,
        "smoke_unproven": smoke_unproven,
        "runtime_state_overlap": runtime_state_overlap,
        "has_sibling_repo_with_runtime": has_sibling_repo_with_runtime,
        "recent_change_window_days": recent_change_window_days,
        "siblings": siblings,
    }
    return Profile(path=str(repo), name=name, signals=signals)
