"""APEX Supabase Logger — writes heavy-mode runs as case-scoped evidentiary records."""

import json
import os
from datetime import datetime, timezone
from typing import Optional

try:
    from supabase import create_client

    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


def get_supabase_client() -> Optional[object]:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key or not SUPABASE_AVAILABLE:
        return None
    return create_client(url, key)


def _resolve_case_id(case_id: Optional[str]) -> str:
    """Resolve case scope without silently binding unrelated runs to one matter."""
    resolved = case_id or os.getenv("APEX_CASE_ID")
    if not isinstance(resolved, str) or not resolved.strip():
        raise ValueError(
            "case_id is required; pass it explicitly or set APEX_CASE_ID"
        )
    return resolved.strip()


def log_apex_run(
    query: str,
    sub_questions: list[str],
    agent_responses: list[dict],
    synthesis: str,
    case_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """Write a complete APEX heavy-mode run as a case-scoped evidentiary record.

    Case scope is mandatory. The logger fails before any remote or local write if
    neither an explicit ``case_id`` nor ``APEX_CASE_ID`` is present.
    """
    resolved_case_id = _resolve_case_id(case_id)
    client = get_supabase_client()

    record = {
        "case_id": resolved_case_id,
        "query": query,
        "sub_questions": json.dumps(sub_questions),
        "agent_responses": json.dumps(agent_responses),
        "synthesis": synthesis,
        "tags": tags or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "apex-heavy",
        "status": "completed",
    }

    if client:
        try:
            result = client.table("apex_task_queue").insert(record).execute()
            print(f"[APEX] Logged to Supabase: {result.data[0].get('id', 'unknown')}")
            return result.data[0]
        except Exception as exc:
            # Remote exception text can contain request or provider detail. Keep the
            # public/local log diagnostic bounded to the failure class instead.
            print(f"[APEX] Supabase log failed: {type(exc).__name__}")

    # Fallback: write to local JSONL file.
    log_path = "apex_runs.jsonl"
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    print(f"[APEX] Logged locally to {log_path}")
    return record
