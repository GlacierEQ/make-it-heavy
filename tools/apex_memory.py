"""APEX Memory Tool — reads/writes to Supabase memory stack for persistent context."""
import os
import json
from datetime import datetime, timezone
from typing import Optional

try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


def get_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if url and key and SUPABASE_AVAILABLE:
        return create_client(url, key)
    return None


def store_memory(content: str, category: str = "general", tags: list = None) -> dict:
    """Store a memory fragment to Supabase apex_memory table."""
    client = get_client()
    record = {
        "content": content,
        "category": category,
        "tags": tags or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case_id": "1FDV-23-0001009"
    }
    if client:
        try:
            result = client.table("apex_memory").insert(record).execute()
            return {"status": "stored", "id": result.data[0].get("id")}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "no_client", "record": record}


def recall_memories(query: str, category: str = None, limit: int = 10) -> list:
    """Retrieve relevant memories from Supabase."""
    client = get_client()
    if not client:
        return []
    try:
        q = client.table("apex_memory").select("*").eq("case_id", "1FDV-23-0001009").limit(limit)
        if category:
            q = q.eq("category", category)
        result = q.execute()
        return result.data
    except Exception as e:
        print(f"[APEX Memory] Recall failed: {e}")
        return []
