"""Context gatherers for LLM co-writing.

Each ``form_type`` can have a gatherer that fetches relevant user data
to provide helpful context.  For writing samples, we perform a semantic
vector search via sqlite-vec to find past user writing that matches the
current draft's style and topic.

If no embedding method is available (no API support, no local fastembed),
and no writing samples exist yet, the function signals ``_embed_required``
so the frontend can offer to install a local embedding model.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def gather_context(form_type: str, fields: dict[str, str]) -> dict[str, Any]:
    """Gather relevant context data for the given form type.

    Currently supports:
    - ``"email-send"`` — returns up to 5 semantically similar past
      writing samples + 3 most recent general samples.

    Returns:
        Dict with a ``"writing_samples"`` key containing a list of
        ``{title, body, source_domain, word_count}`` dicts, or empty
        dict if no samples are available.  If embedding is unavailable
        and no samples exist, returns ``{"_embed_required": True}``.
    """
    if form_type != "email-send":
        return {}

    body = fields.get("body", "").strip()
    if not body:
        return {}

    from lighterbird.email.db import get_db as get_email_db

    try:
        db = get_email_db()
    except Exception:
        logger.warning("Cannot open email DB for context gathering")
        return {}

    # ── 1. Try vector search (requires embed + vec0) ──────────────────────
    try:
        has_vec = db.execute_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_samples'"
        )
    except Exception:
        has_vec = None

    if has_vec:
        try:
            result = _vector_search(db, body)
            if result:
                return result
        except Exception:
            logger.debug("Vector search failed, falling back to recent")

    # ── 2. Fallback: most recent 5 samples ────────────────────────────────
    recent = _recent_samples_only(db)
    if recent:
        return recent

    # ── 3. No samples at all — check if local model weights can be
    #     downloaded.  If no API embed is available and the local model
    #     hasn't been cached yet, signal the frontend to offer download.
    from lighterbird.core.embedding import get_status as _embed_status

    status = _embed_status()
    if status["status"] == "model-needed":
        return {"_embed_required": True, "models": status["models"]}

    return {}


def _vector_search(db: Any, body: str) -> dict[str, Any] | None:
    """Try semantic vector search via embed() + vec0 k-NN."""
    import asyncio

    from lighterbird.core.embedding import embed as _embed

    embedding = asyncio.run(_embed([body]))
    if not embedding or not embedding[0]:
        return None

    query_vec = json.dumps(embedding[0])
    rows = db.execute(
        "SELECT ws.uuid, ws.title, ws.body, ws.source_domain, "
        "       ws.word_count, v.distance "
        "FROM vec_samples v "
        "JOIN writing_samples ws ON ws.rowid = v.rowid "
        "WHERE v.embedding MATCH ? AND v.k = 5",
        (query_vec,),
    )
    samples = [
        {
            "uuid": r["uuid"],
            "title": r["title"] or "",
            "body": r["body"],
            "source_domain": r["source_domain"],
            "word_count": r["word_count"],
            "distance": r["distance"],
        }
        for r in rows
    ]
    if samples:
        return {"writing_samples": samples}
    return None


def _recent_samples_only(db: Any) -> dict[str, Any]:
    """Return the 5 most recent writing samples (no vector search)."""
    try:
        rows = db.execute(
            "SELECT uuid, title, body, source_domain, word_count "
            "FROM writing_samples "
            "ORDER BY registered_at DESC LIMIT 5"
        )
        samples = [
            {
                "uuid": r["uuid"],
                "title": r["title"] or "",
                "body": r["body"],
                "source_domain": r["source_domain"],
                "word_count": r["word_count"],
            }
            for r in rows
        ]
        if samples:
            return {"writing_samples": samples}
    except Exception:
        pass
    return {}
