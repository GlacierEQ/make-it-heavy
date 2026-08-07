# SPDX-License-Identifier: Proprietary
"""Fail-closed resolution of immutable local Git evidence spans."""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, Mapping, Optional

LOCATOR_RE = re.compile(
    r"^(?P<path>[^@\s#]+)@(?P<revision>[0-9a-fA-F]{40})"
    r"#L(?P<start>\d+)(?:-L?(?P<end>\d+))?$"
)

SPAN_RESOLVED = "SPAN_RESOLVED"
SPAN_LOCATOR_INVALID = "SPAN_LOCATOR_INVALID"
SPAN_PATH_UNSAFE = "SPAN_PATH_UNSAFE"
SPAN_REVISION_UNAVAILABLE = "SPAN_REVISION_UNAVAILABLE"
SPAN_PATH_UNAVAILABLE = "SPAN_PATH_UNAVAILABLE"
SPAN_LINE_RANGE_INVALID = "SPAN_LINE_RANGE_INVALID"
SPAN_DECODE_FAILURE = "SPAN_DECODE_FAILURE"
SPAN_GIT_TIMEOUT = "SPAN_GIT_TIMEOUT"
GIT_TIMEOUT_RETURN_CODE = 124


@dataclass(frozen=True)
class ImmutableSpanResolution:
    """One bounded immutable source-span resolution receipt."""

    pointer: str
    locator: str
    state: str
    path: str = ""
    revision: str = ""
    start_line: int = 0
    end_line: int = 0
    span_text: str = ""
    span_sha256: str = ""
    error: str = ""

    @property
    def resolved(self) -> bool:
        return self.state == SPAN_RESOLVED

    def to_dict(self, include_text: bool = False) -> Dict[str, object]:
        value = asdict(self)
        if not include_text:
            value.pop("span_text", None)
        value["resolved"] = self.resolved
        return value


class LocalGitImmutableSpanResolver:
    """Resolve only exact `path@40hex#Lx-Ly` spans from a local Git object database."""

    def __init__(self, repo_root: Optional[Path] = None, timeout: float = 10.0) -> None:
        self.repo_root = Path(repo_root or Path.cwd()).resolve()
        self.timeout = max(0.5, min(float(timeout), 30.0))

    @staticmethod
    def _safe_path(raw_path: str) -> bool:
        candidate = PurePosixPath(raw_path)
        return (
            bool(raw_path)
            and not candidate.is_absolute()
            and ".." not in candidate.parts
            and raw_path not in {".", ".."}
            and not raw_path.startswith("-")
        )

    def _git(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        command = ["git", *args]
        try:
            return subprocess.run(
                command,
                cwd=str(self.repo_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                args=command,
                returncode=GIT_TIMEOUT_RETURN_CODE,
                stdout=b"",
                stderr=b"Git operation timed out",
            )

    def resolve(self, pointer: str, locator: str) -> ImmutableSpanResolution:
        match = LOCATOR_RE.fullmatch(str(locator).strip())
        if match is None:
            return ImmutableSpanResolution(
                pointer=pointer,
                locator=str(locator),
                state=SPAN_LOCATOR_INVALID,
                error="locator must use path@40-hex-commit#Lx-Ly",
            )

        path = match.group("path")
        revision = match.group("revision").lower()
        start_line = int(match.group("start"))
        end_line = int(match.group("end") or start_line)
        common = {
            "pointer": pointer,
            "locator": str(locator),
            "path": path,
            "revision": revision,
            "start_line": start_line,
            "end_line": end_line,
        }

        if not self._safe_path(path):
            return ImmutableSpanResolution(
                state=SPAN_PATH_UNSAFE,
                error="evidence path must be repository-relative and traversal-free",
                **common,
            )
        if start_line <= 0 or end_line < start_line:
            return ImmutableSpanResolution(
                state=SPAN_LINE_RANGE_INVALID,
                error="line range is invalid",
                **common,
            )

        commit_check = self._git("cat-file", "-e", f"{revision}^{{commit}}")
        if commit_check.returncode == GIT_TIMEOUT_RETURN_CODE:
            return ImmutableSpanResolution(
                state=SPAN_GIT_TIMEOUT,
                error="Git timed out while checking the immutable revision",
                **common,
            )
        if commit_check.returncode != 0:
            return ImmutableSpanResolution(
                state=SPAN_REVISION_UNAVAILABLE,
                error="immutable revision is not present in the local Git object database",
                **common,
            )

        blob = self._git("show", f"{revision}:{path}")
        if blob.returncode == GIT_TIMEOUT_RETURN_CODE:
            return ImmutableSpanResolution(
                state=SPAN_GIT_TIMEOUT,
                error="Git timed out while reading the immutable evidence blob",
                **common,
            )
        if blob.returncode != 0:
            return ImmutableSpanResolution(
                state=SPAN_PATH_UNAVAILABLE,
                error="path is not present at the immutable revision",
                **common,
            )
        try:
            text = blob.stdout.decode("utf-8")
        except UnicodeDecodeError:
            return ImmutableSpanResolution(
                state=SPAN_DECODE_FAILURE,
                error="evidence blob is not valid UTF-8 text",
                **common,
            )

        lines = text.splitlines()
        if end_line > len(lines):
            return ImmutableSpanResolution(
                state=SPAN_LINE_RANGE_INVALID,
                error=f"requested line {end_line} exceeds source length {len(lines)}",
                **common,
            )

        span_text = "\n".join(lines[start_line - 1 : end_line])
        return ImmutableSpanResolution(
            state=SPAN_RESOLVED,
            span_text=span_text,
            span_sha256=hashlib.sha256(span_text.encode("utf-8")).hexdigest(),
            **common,
        )


class StaticSpanResolver:
    """Deterministic in-memory resolver for unit tests and bounded fixtures."""

    def __init__(self, spans: Mapping[str, str]) -> None:
        self.spans = dict(spans)

    def resolve(self, pointer: str, locator: str) -> ImmutableSpanResolution:
        span_text = self.spans.get(pointer)
        if span_text is None:
            return ImmutableSpanResolution(
                pointer=pointer,
                locator=locator,
                state=SPAN_PATH_UNAVAILABLE,
                error="fixture contains no span for this pointer",
            )
        return ImmutableSpanResolution(
            pointer=pointer,
            locator=locator,
            state=SPAN_RESOLVED,
            span_text=span_text,
            span_sha256=hashlib.sha256(span_text.encode("utf-8")).hexdigest(),
        )
