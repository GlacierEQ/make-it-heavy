"""APEX Supabase Logger — writes every heavy-mode run as evidentiary record."""
import os
import json
from datetime import datetime, timezone
from typing import Optional

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


def get_supabase_client() -> Optional[object]:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key or not SUPABASE_AVAILABLE:
        return None
    return create_client(url, key)


def log_apex_run(
    query: str,
    sub_questions: list[str],
    agent_responses: list[dict],
    synthesis: str,
    case_id: str = "1FDV-23-0001009",
    tags: list[str] = None
) -> dict:
    """Write a complete APEX heavy-mode run to Supabase as timestamped evidence."""
    client = get_supabase_client()

    record = {
        "case_id": case_id,
        "query": query,
        "sub_questions": json.dumps(sub_questions),
        "agent_responses": json.dumps(agent_responses),
        "synthesis": synthesis,
        "tags": tags or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "apex-heavy",
        "status": "completed"
    }

    if client:
        try:
            result = client.table("apex_task_queue").insert(record).execute()
            print(f"[APEX] Logged to Supabase: {result.data[0].get('id', 'unknown')}")
            return result.data[0]
        except Exception as e:
            print(f"[APEX] Supabase log failed: {e}")

    # Fallback: write to local JSONL file
    log_path = "apex_runs.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")
    print(f"[APEX] Logged locally to {log_path}")
    return record
