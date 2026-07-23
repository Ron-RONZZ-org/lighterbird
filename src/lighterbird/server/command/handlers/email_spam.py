"""Command handlers for the ``!email spam`` domain.

Only one command: ``!email spam stats`` — showing classifier statistics.
Reporting spam/fraud/ham is done via GUI (EmailHeaders buttons) or LLM,
not via CLI (UUIDs are not human-friendly).
"""

from __future__ import annotations

from typing import Any

from lightercore.permissions import PermissionLevel
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service


@command("email.spam.stats", permission_level=PermissionLevel.READ)
def spam_stats(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email spam stats — Show spam classifier statistics.

    Displays token counts, domain reputation, and classifier performance
    metrics from both the Bayesian and phishing detection systems.

    Usage::

        !email spam stats
        !email spam stats --detail    (show top tokens)
    """
    svc = get_email_service()
    detail = "detail" in flags

    # Bayesian token stats
    token_counts = svc.db.execute_one(
        "SELECT COUNT(*) AS total, "
        "SUM(spam_count) AS total_spam, "
        "SUM(ham_count) AS total_ham "
        "FROM spam_user_tokens"
    ) or {}
    total_tokens = token_counts.get("total", 0) or 0
    total_spam_counts = token_counts.get("total_spam", 0) or 0
    total_ham_counts = token_counts.get("total_ham", 0) or 0

    # Phishing feed stats
    feed_counts = svc.db.execute_one(
        "SELECT source, COUNT(*) AS cnt FROM phishing_feeds GROUP BY source"
    ) or {}
    total_feed_domains = (
        svc.db.execute_one("SELECT COUNT(*) AS cnt FROM phishing_feeds") or {}
    ).get("cnt", 0) or 0

    # Phishing watchlist stats
    watchlist_count = (
        svc.db.execute_one("SELECT COUNT(*) AS cnt FROM phishing_domains") or {}
    ).get("cnt", 0) or 0

    # Similarity detector stats
    similar = svc.similarity
    sim_stats = similar.get_stats()

    # Messages flagged
    spam_msg_count = (
        svc.db.execute_one("SELECT COUNT(*) AS cnt FROM messages WHERE is_spam = 1")
        or {}
    ).get("cnt", 0) or 0

    phishing_msg_count = (
        svc.db.execute_one(
            "SELECT COUNT(*) AS cnt FROM messages WHERE phishing_detected = 1"
        ) or {}
    ).get("cnt", 0) or 0

    lines = [
        "=== Spam Classifier Statistics ===",
        "",
        f"Bayesian tokens (per-user): {total_tokens}",
        f"  Spam token occurrences: {total_spam_counts}",
        f"  Ham token occurrences:  {total_ham_counts}",
        f"Messages flagged as spam: {spam_msg_count}",
        f"Messages flagged phishing: {phishing_msg_count}",
        "",
        f"Phishing feed domains:   {total_feed_domains}",
        f"Phishing watchlist size: {watchlist_count}",
        "",
        f"Similarity signatures:   {sim_stats.get('signatures', 0)}",
        f"Content hash entries:    {sim_stats.get('content_hashes', 0)}",
    ]

    if detail and total_tokens > 0:
        top_spammy = svc.db.execute(
            "SELECT token, spam_count, ham_count FROM spam_user_tokens "
            "ORDER BY CAST(spam_count AS REAL) / "
            "  MAX(CAST(spam_count + ham_count AS REAL), 1) DESC "
            "LIMIT 20"
        )
        lines.append("")
        lines.append("Top spammy tokens (per-user):")
        for row in top_spammy:
            total = row["spam_count"] + row["ham_count"]
            ratio = row["spam_count"] / max(total, 1) * 100
            lines.append(
                f"  {row['token']:<20} "
                f"spam={row['spam_count']} ham={row['ham_count']} "
                f"({ratio:.0f}% spam)"
            )

    return {
        "type": "status",
        "title": "Spam Classifier Statistics",
        "data": {"_summary": "\n".join(lines)},
    }
