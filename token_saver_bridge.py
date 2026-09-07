# SPDX-License-Identifier: Proprietary
# Copyright (c) 2026 Casey del Carpio Barton / GlacierEQ — All Rights Reserved
"""Bridge between :class:`memory_tiered.TieredMemory` and ``mermicorn_token_saver``.

The swarm keeps its own per-user STM/LTM/entity store. The token-saver keeps
an append-only per-user turn/receipt cache with a 10 KB cap. They speak the
same contract (per-user, append-only, auditable) but solve different problems:

* TieredMemory is the agent's working memory, FTS5-indexed for retrieval.
* mermicorn_token_saver is the context-compression service, with a hard cap
  and a per-session compaction receipt.

The bridge lets TieredMemory **delegate** compression to token-saver and
write the compacted text back as a single LTM record, so the swarm's LTM
remains the source of truth for retrieval while the receipt chain lives
in token-saver for audit.

User isolation
--------------
Both layers reject an empty ``user_id`` as a hard error. The bridge
re-checks at the entry point and re-raises on every delegation, so the
privacy boundary is enforced at every step.

Optional dependency
-------------------
``mermicorn_token_saver`` is treated as an optional dep (see commit
``c51dcee`` — gracefully handle optional token_saver dependency in the
handoff tests). The import is lazy; the bridge raises a clear
``BridgeDependencyError`` if the package is missing.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional


class BridgeDependencyError(ImportError):
    """Raised when ``mermicorn_token_saver`` is not importable in this env."""


def _load_token_saver():
    try:
        import mermicorn_token_saver  # type: ignore
    except ImportError as e:
        raise BridgeDependencyError(
            "mermicorn_token_saver is required for the bridge; install it via "
            "`pip install -e /root/projects/mermicorn/token-saver` or add it "
            "to the make-it-heavy requirements."
        ) from e
    return mermicorn_token_saver


def _require_user(user_id: str) -> str:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id is required for the token-saver bridge")
    return user_id.strip()


def compress_session(
    tiered_memory,
    user_id: str,
    session_id: str = "default",
    *,
    stm_limit: int = 20,
    strategy: str = "summarize",
    use_packs: bool = True,
    path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Read recent STM turns, compress via token-saver, write the result to LTM.

    Returns the token-saver receipt dict (with the compacted text under
    ``text``) or ``None`` when there are fewer than two live STM turns to
    compact. The receipt is the audit trail; the LTM record is the
    retrieval-friendly summary.

    The token-saver is invoked with its own per-user cache (``user_id`` and
    the supplied ``session_id``). The original STM turns are not deleted —
    this is a write, not a migration. Pass a custom ``path`` to redirect
    the token-saver cache during tests.
    """
    user_id = _require_user(user_id)
    turns = tiered_memory.get_recent_turns(user_id, limit=stm_limit)
    if not turns:
        return None
    turns_chrono = list(reversed(turns))
    if len(turns_chrono) < 2:
        return None

    ts = _load_token_saver()
    cache_kwargs: Dict[str, Any] = {"path": path} if path is not None else {}
    for t in turns_chrono:
        ts.save(
            user_id=user_id,
            turn_id=str(t.get("turn_id") or t.get("id") or ""),
            text=str(t.get("text") or ""),
            session_id=session_id,
            role=str(t.get("role") or "user"),
            **cache_kwargs,
        )
    receipt = ts.compact(
        user_id=user_id,
        session_id=session_id,
        strategy=strategy,
        use_packs=use_packs,
        **cache_kwargs,
    )
    if receipt is None:
        return None

    compacted_text = receipt.get("text", "")
    if compacted_text.strip():
        tiered_memory.store_long_term(
            user_id=user_id,
            text=compacted_text,
            source_tier="token_saver_bridge",
            turn_id=str(receipt.get("receipt_id") or f"tsbridge-{int(time.time())}"),
        )
    return receipt
