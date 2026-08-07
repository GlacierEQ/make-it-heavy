#!/usr/bin/env python3
"""Case-scoped OSINT lead monitor with a fail-closed docket truth boundary.

Public-web search results are leads only. This module never promotes snippets into
court-record milestones and never writes external memory unless explicitly enabled.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    from apex_memory import store_memory

    MEMORY_SUPPORT = True
except ImportError:
    MEMORY_SUPPORT = False


class DocketMonitorConfigurationError(ValueError):
    """Raised when a monitor would run without explicit case scope."""


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _enabled(value: Optional[str]) -> bool:
    return isinstance(value, str) and value.strip().lower() in {"1", "true", "yes"}


class DocketOSINTMonitor:
    """Collect unverified web leads without converting them into docket facts."""

    def __init__(
        self,
        *,
        case_id: Optional[str] = None,
        queries: Optional[Iterable[str]] = None,
        output_dir: Optional[str] = None,
        memory_write_enabled: Optional[bool] = None,
    ) -> None:
        resolved_case_id = case_id or os.getenv("APEX_CASE_ID")
        if not isinstance(resolved_case_id, str) or not resolved_case_id.strip():
            raise DocketMonitorConfigurationError(
                "case_id is required; pass it explicitly or set APEX_CASE_ID"
            )
        self.case_id = resolved_case_id.strip()

        supplied_queries = list(queries or [])
        env_queries = [
            value.strip()
            for value in os.getenv("APEX_DOCKET_QUERIES", "").split("||")
            if value.strip()
        ]
        self.queries = [
            str(value).strip()
            for value in (supplied_queries or env_queries or [f'"{self.case_id}"'])
            if str(value).strip()
        ]
        if not self.queries:
            raise DocketMonitorConfigurationError("at least one non-empty search query is required")

        resolved_output = (
            output_dir
            or os.getenv("APEX_DOCKET_OUTPUT_DIR")
            or "artifacts/docket-monitor"
        )
        self.output_dir = Path(resolved_output).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.json_path = self.output_dir / "DOCKET_MONITOR.json"
        self.md_path = self.output_dir / "DOCKET_OSINT_REPORT.md"
        self.memory_write_enabled = (
            bool(memory_write_enabled)
            if memory_write_enabled is not None
            else _enabled(os.getenv("APEX_DOCKET_MEMORY_WRITE_ENABLED"))
        )

    def search_ddg(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search the public web and label every returned item as unverified."""
        from ddgs import DDGS

        bounded = max(1, min(int(limit), 10))
        try:
            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=bounded))
        except Exception as exc:
            print(f"Search failed: {type(exc).__name__}")
            return []

        observed_at = _utc_now()
        results: list[dict[str, Any]] = []
        for item in raw_results:
            url = str(item.get("href") or "").strip()
            if not url:
                continue
            results.append(
                {
                    "query": query,
                    "title": str(item.get("title") or "").strip(),
                    "url": url,
                    "snippet": str(item.get("body") or "").strip(),
                    "observed_at": observed_at,
                    "verification_status": "unverified_source",
                    "promoted_to_docket": False,
                }
            )
        return results

    def harvest_docket_osint(self) -> list[dict[str, Any]]:
        """Run only explicitly scoped queries and deduplicate by URL."""
        aggregated: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for query in self.queries:
            for item in self.search_ddg(query, limit=3):
                url = str(item.get("url") or "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                aggregated.append(item)
        return aggregated

    def _empty_registry(self) -> dict[str, Any]:
        return {
            "schema": "glaciereq.make-it-heavy.docket-osint-registry.v2",
            "case_id": self.case_id,
            "last_updated": None,
            "docket_milestones": [],
            "osint_findings": [],
            "osint_promotion_policy": "never_auto_promote",
            "truth_boundary": (
                "Public-web results are unverified leads only. Docket milestones must be "
                "supplied from a separately verified court-record workflow."
            ),
        }

    def load_registry(self) -> dict[str, Any]:
        """Load a case-matching local registry; never manufacture baseline milestones."""
        if not self.json_path.exists():
            return self._empty_registry()
        try:
            registry = json.loads(self.json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DocketMonitorConfigurationError(
                f"existing docket registry is unreadable: {type(exc).__name__}"
            ) from exc
        if not isinstance(registry, dict):
            raise DocketMonitorConfigurationError("existing docket registry must be a JSON object")
        if registry.get("case_id") != self.case_id:
            raise DocketMonitorConfigurationError(
                "existing docket registry case_id does not match requested case scope"
            )
        if not isinstance(registry.get("docket_milestones", []), list):
            raise DocketMonitorConfigurationError("docket_milestones must be a list")
        registry.setdefault("docket_milestones", [])
        registry.setdefault("osint_findings", [])
        registry["osint_promotion_policy"] = "never_auto_promote"
        registry["truth_boundary"] = self._empty_registry()["truth_boundary"]
        return registry

    def save_registry(self, registry: dict[str, Any]) -> None:
        """Atomically save the local registry."""
        temporary = self.json_path.with_suffix(self.json_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.json_path)

    def _memory_status(self) -> str:
        if not self.memory_write_enabled:
            return "DISABLED"
        return "ENABLED" if MEMORY_SUPPORT else "BLOCKED_CONNECTOR_UNAVAILABLE"

    def _write_memory_leads(self, findings: list[dict[str, Any]]) -> int:
        """Optionally persist minimal lead metadata, never docket-fact assertions."""
        if not self.memory_write_enabled or not MEMORY_SUPPORT:
            return 0
        stored = 0
        for item in findings[:2]:
            content = (
                "UNVERIFIED OSINT LEAD — not a docket fact. "
                f"Title: {item.get('title', '')}. URL: {item.get('url', '')}."
            )
            try:
                result = store_memory(
                    content=content,
                    category="osint_docket_lead",
                    tags=["docket", "osint", "unverified_source", self.case_id],
                )
            except Exception as exc:
                print(f"Memory lead write failed: {type(exc).__name__}")
                continue
            if isinstance(result, dict) and result.get("status") in {"ok", "success", "stored"}:
                stored += 1
        return stored

    def generate_markdown_report(self, registry: dict[str, Any]) -> None:
        """Render a report that keeps verified docket data separate from OSINT leads."""
        milestones = registry.get("docket_milestones", [])
        if milestones:
            milestone_lines = []
            for item in milestones:
                date = str(item.get("date") or "UNKNOWN_DATE")
                event = str(item.get("event") or "UNSPECIFIED_EVENT")
                status = str(item.get("status") or "UNVERIFIED_LOCAL_ENTRY")
                milestone_lines.append(f"- **{date}**: {event} — `{status}`")
            milestones_md = "\n".join(milestone_lines)
        else:
            milestones_md = "*No verified docket milestones are stored by this monitor.*"

        findings = registry.get("osint_findings", [])
        if findings:
            lead_lines = []
            for index, item in enumerate(findings[:10], start=1):
                title = str(item.get("title") or "Untitled result")
                url = str(item.get("url") or "")
                snippet = str(item.get("snippet") or "")
                lead_lines.extend(
                    [
                        f"### {index}. {title}",
                        f"- URL: {url}",
                        "- Verification: `UNVERIFIED_SOURCE`",
                        f"- Snippet: {snippet}",
                        "",
                    ]
                )
            osint_md = "\n".join(lead_lines).rstrip()
        else:
            osint_md = "*No public-web leads were returned in this search run.*"

        report = f"""# Docket OSINT Lead Report

## Truth boundary

**Public-web search results are leads, not court-record facts.** This monitor never
promotes a search snippet into `docket_milestones`.

| Field | Value |
|---|---|
| Case scope | `{self.case_id}` |
| Last scan | `{registry.get('last_updated') or 'NOT_RUN'}` |
| OSINT promotion | `DISABLED` |
| External memory write | `{self._memory_status()}` |

## Verified docket milestones supplied by another workflow

{milestones_md}

## Unverified public-web leads

{osint_md}

## Promotion rule

A lead may be promoted only by a separate workflow that opens the controlling court
record, verifies identity and content, records provenance, and then explicitly updates
the docket registry. Repetition, search ranking, snippets, and inferred dates are not
verification.
"""
        self.md_path.write_text(report, encoding="utf-8")

    def run_monitor(self) -> dict[str, Any]:
        """Collect leads, preserve docket milestones unchanged, and write local receipts."""
        registry = self.load_registry()
        milestones_before = json.loads(json.dumps(registry.get("docket_milestones", [])))
        findings = self.harvest_docket_osint()
        registry["osint_findings"] = findings
        registry["last_updated"] = _utc_now()
        registry["osint_promotion_policy"] = "never_auto_promote"
        registry["docket_milestones"] = milestones_before
        registry["memory_leads_written"] = self._write_memory_leads(findings)
        self.save_registry(registry)
        self.generate_markdown_report(registry)
        return registry


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect case-scoped public-web leads without promoting them to docket facts."
    )
    parser.add_argument("--case-id", help="Required case scope; otherwise use APEX_CASE_ID")
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Search query; may be repeated. Defaults to the explicit case id only.",
    )
    parser.add_argument("--output-dir", help="Local output directory")
    parser.add_argument(
        "--enable-memory-write",
        action="store_true",
        help="Explicitly allow minimal UNVERIFIED OSINT lead writes to configured memory.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    monitor = DocketOSINTMonitor(
        case_id=args.case_id,
        queries=args.queries,
        output_dir=args.output_dir,
        memory_write_enabled=args.enable_memory_write or None,
    )
    monitor.run_monitor()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
