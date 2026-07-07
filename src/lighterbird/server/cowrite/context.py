"""Context gatherers for LLM co-writing.

Each ``form_type`` can have a gatherer that fetches relevant user data
to provide helpful context.  For writing samples, we perform a semantic
vector search via sqlite-vec to find past user writing that matches the
current draft's style and topic.
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

    Args:
        form_type: Type of form (``"email-send"``, ``"todo-add"``, etc.).
        fields: Current form field values.

    Returns:
        Dict with a ``"writing_samples"`` key containing a list of
        ``{title, body, source_domain, word_count}`` dicts, or empty
        dict if no samples are available.
    """
    if form_type != "email-send":
        return {}

    body = fields.get("body", "").strip()
    if not body:
        return {}

    from lighterbird.core.ai import get_provider as get_core_provider
    from lighterbird.email.db import get_db as get_email_db
    from lighterbird.server.llm.provider import get_provider as get_wrapper

    try:
        db = get_email_db()
    except Exception:
        logger.warning("Cannot open email DB for context gathering")
        return {}

    # Check that vec_samples table exists and has data
    try:
        has_vec = db.execute_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_samples'"
        )
        if not has_vec:
            return _recent_samples_only(db)
    except Exception:
        return _recent_samples_only(db)

    # Try semantic retrieval via vector search
    try:
        wrapper = get_wrapper()
        if not wrapper.is_available():
            return _recent_samples_only(db)

        core = get_core_provider(wrapper.config)
        import asyncio

        embedding = asyncio.run(core.embed([body]))
        if not embedding or not embedding[0]:
            return _recent_samples_only(db)

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
    except Exception:
        logger.exception("Vector search failed, falling back to recent samples")

    return _recent_samples_only(db)


def _recent_samples_only(db: Any) -> dict[str, Any]:
    """Fallback: return the 5 most recent writing samples (no vector search)."""
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
