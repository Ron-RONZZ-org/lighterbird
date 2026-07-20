"""Bayesian spam detection — tokenizer, classifier, training.

Uses a chi-squared combination of token probabilities (SpamBayes
algorithm) to classify email messages as spam or ham.  Ships with
a pre-baked seed table for immediate ~80% Day-1 accuracy; per-user
training overrides the seed as feedback accumulates.

Architecture:
    - ``SpamClassifier`` — scores a single message (tokenize → chi-squared)
    - ``SpamTrainer`` — updates per-user token counts from user feedback
    - A seed ``spam_tokens.json`` is shipped with the package for cold-start
"""

from __future__ import annotations

import json
import logging
import math
import re
import uuid
from collections.abc import Collection
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Seed data ────────────────────────────────────────────────────────────

_SEED_PATH = Path(__file__).resolve().parent / "spam_tokens.json"

# Regex patterns for tokenization
_RE_TOKEN = re.compile(r"[A-Za-z0-9]+|[^\w\s]")
_RE_URL = re.compile(r"https?://[^\s<>\"']+", re.I)
_RE_CAPS_WORD = re.compile(r"\b[A-Z]{4,}\b")
_RE_MONEY = re.compile(r"[\$\€\£\¥]\d+(?:[.,]\d+)?|\d+\s*(?:USD|EUR|GBP)")

# Minimum user reports before fully trusting per-user counts
_MIN_USER_COUNTS = 5

# Spam classification threshold
_SPAM_THRESHOLD = 0.9
_HAM_THRESHOLD = 0.15


def _load_seed() -> dict[str, dict[str, float]]:
    """Load the pre-baked seed token table.

    Returns:
        Dict mapping token → ``{"spam": prob, "ham": prob}``.
    """
    if _SEED_PATH.exists():
        try:
            with open(_SEED_PATH) as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to load spam seed tokens: %s", exc)
    return {}


def _tokenize(text: str) -> list[str]:
    """Tokenize email text into tokens suitable for Bayesian analysis.

    Splits words, punctuation, URLs, ALL-CAPS sequences, and money
    amounts.  Each token is lowercased for matching.

    Args:
        text: The email subject + body text (plaintext).

    Returns:
        List of token strings.
    """
    tokens: list[str] = []

    # Extract and tag URLs
    urls = _RE_URL.findall(text)
    for url in urls:
        tokens.append("http://")  # generic URL indicator
        # Extract domain from URL for domain-level token
        m = re.match(r"https?://([^/]+)", url)
        if m:
            tokens.append(f"dom:{m.group(1).lower()}")
        text = text.replace(url, "", 1)

    # Extract money amounts
    for m in _RE_MONEY.finditer(text):
        tokens.append("$")

    # Detect ALL-CAPS flag
    if _RE_CAPS_WORD.search(text):
        tokens.append("ALL-CAPS")

    # Split into individual tokens
    for match in _RE_TOKEN.finditer(text):
        tok = match.group(0).lower().strip()
        if len(tok) >= 2:  # skip single chars
            tokens.append(tok)

    return tokens


def _chi2_score(probabilities: list[float]) -> float:
    """Combine token probabilities using the chi-squared method.

    Implements the SpamBayes chi-squared combination algorithm.
    The result is a probability 0.0–1.0.

    Args:
        probabilities: List of token spam probabilities (0.0–1.0).

    Returns:
        Combined spam probability.
    """
    if not probabilities:
        return 0.5

    # Pick the N most extreme (farthest from 0.5) tokens
    N = min(15, len(probabilities))
    sorted_probs = sorted(probabilities, key=lambda p: abs(p - 0.5), reverse=True)
    selected = sorted_probs[:N]

    # Protect against extreme values causing log(0)
    eps = 1e-200
    H = -2.0 * sum(math.log(max(p, eps)) for p in selected)
    S = -2.0 * sum(math.log(max(1.0 - p, eps)) for p in selected)

    df = 2.0 * N
    try:
        # Use chi-squared CDF approximation (incomplete gamma function)
        from math import lgamma as _lgamma
        # Compute chi-squared CDF via series expansion
        # H = -2*sum(log(p))   — small if tokens are spammy (p near 1)
        # S = -2*sum(log(1-p)) — small if tokens are hammy (p near 0)
        # h_score = P(χ² < H)  — small if spammy (H small)
        # s_score = P(χ² < S)  — small if hammy (S small)
        # Combined = (s_score - h_score + 1) / 2 for correct polarity
        h_score = _gammainc(df / 2.0, H / 2.0)
        s_score = _gammainc(df / 2.0, S / 2.0)
        return (s_score - h_score + 1.0) / 2.0
    except Exception:
        # Fallback: simple average for edge cases
        return 0.5


def _gammainc(a: float, x: float) -> float:
    """Regularized lower incomplete gamma function P(a, x).

    Uses the series expansion: P(a, x) = exp(-x) * x**a / gamma(a) * sum(...)
    Converges quickly for small x; for large x uses continued fraction.

    Args:
        a: Shape parameter (positive).
        x: Upper limit (non-negative).

    Returns:
        Value in [0, 1].
    """
    if x <= 0 or a <= 0:
        return 0.0

    from math import exp, lgamma, log

    if x < a + 1:
        # Series expansion: P(a,x) = exp(-x + a*ln(x) - ln(Γ(a))) * S
        s = t = 1.0 / a
        for k in range(1, 200):
            t *= x / (a + k)
            s += t
            if abs(t) < 1e-15 * abs(s):
                break
        return s * exp(-x + a * log(x) - lgamma(a))
    else:
        # Continued fraction (Lentz's method)
        from math import fabs

        b = x + 1.0 - a
        c = 1.0 / 1e-30
        d = 1.0 / b
        h = d
        for i in range(1, 200):
            an = -i * (i - a)
            b += 2.0
            d = an * d + b
            if fabs(d) < 1e-30:
                d = 1e-30
            c = b + an / c
            if fabs(c) < 1e-30:
                c = 1e-30
            d = 1.0 / d
            delta = d * c
            h *= delta
            if fabs(delta - 1.0) < 1e-15:
                break
        return 1.0 - exp(-x + a * log(x) - lgamma(a)) * h


class SpamClassifier:
    """Bayesian spam classifier using chi-squared token combination.

    Combines a pre-baked seed table (from public corpus) with per-user
    token counts for personalized classification.

    Args:
        db: Database connection for per-user token queries.
    """

    def __init__(self, db: Any) -> None:
        self._db = db
        self._seed: dict[str, dict[str, float]] = _load_seed()

    def classify(self, subject: str, body: str,
                 account_email: str | None = None) -> dict[str, Any]:
        """Classify a single email message.

        Args:
            subject: Email subject line.
            body: Email body text (plaintext).
            account_email: Account email for per-user training lookup.
                If None, uses only the seed table (global baseline).

        Returns:
            Dict with ``is_spam`` (bool), ``score`` (float 0.0–1.0),
            and ``tokens`` (list of contributing tokens with probabilities).
        """
        text = f"{subject} {body}" if subject else (body or "")
        tokens = _tokenize(text)

        # Deduplicate tokens (each token contributes once per message)
        unique_tokens = list(set(tokens))

        probs: list[float] = []
        contributing: list[dict] = []

        for token in unique_tokens:
            prob = self._token_probability(token, account_email)
            if prob is not None:
                probs.append(prob)
                contributing.append({"token": token, "probability": round(prob, 4)})

        score = _chi2_score(probs) if probs else 0.5

        # Sort contributing tokens by extremity
        contributing.sort(key=lambda t: abs(t["probability"] - 0.5), reverse=True)

        return {
            "is_spam": score >= _SPAM_THRESHOLD,
            "score": round(score, 4),
            "tokens": contributing[:20],  # top 20 for debugging
        }

    def _token_probability(self, token: str,
                           account_email: str | None) -> float | None:
        """Compute combined probability for a single token.

        Blends seed and per-user counts: if user has < ``_MIN_USER_COUNTS``
        observations, blend seed + user; otherwise trust user exclusively.

        Returns:
            Probability in [0, 1], or None if token is unknown.
        """
        seed = self._seed.get(token)

        if account_email:
            row = self._db.execute_one(
                "SELECT spam_count, ham_count FROM spam_user_tokens "
                "WHERE token = ? AND account_email = ?",
                (token, account_email),
            )
        else:
            row = None

        if seed and not row:
            return seed["spam"]

        if row and not seed:
            total = row["spam_count"] + row["ham_count"]
            if total >= _MIN_USER_COUNTS:
                # Robinson's correction
                return (row["spam_count"] + 1.0) / (total + 2.0)
            # Too few observations — treat as neutral
            return 0.5

        if seed and row:
            total = row["spam_count"] + row["ham_count"]
            if total >= _MIN_USER_COUNTS:
                return (row["spam_count"] + 1.0) / (total + 2.0)
            else:
                # Blend: weight seed by (min - total) / min, user by total / min
                weight = total / _MIN_USER_COUNTS
                user_prob = (row["spam_count"] + 1.0) / (total + 2.0)
                return weight * user_prob + (1.0 - weight) * seed["spam"]

        return None


class SpamTrainer:
    """Updates per-user token counts from user feedback.

    When a user marks a message as spam or ham, this extracts tokens
    and updates the ``spam_user_tokens`` table.
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    def report(self, subject: str, body: str,
               account_email: str, is_spam: bool) -> None:
        """Train the classifier on a user's feedback.

        Extracts tokens from the message and increments either
        ``spam_count`` or ``ham_count`` for each.

        Args:
            subject: Email subject line.
            body: Email body text (plaintext).
            account_email: The account this feedback applies to.
            is_spam: True if user marked as spam, False for ham.
        """
        text = f"{subject} {body}" if subject else (body or "")
        tokens = set(_tokenize(text))  # deduplicate per message
        now = datetime.now(UTC).isoformat()
        col = "spam_count" if is_spam else "ham_count"

        for token in tokens:
            self._db.execute(
                f"""INSERT INTO spam_user_tokens
                    (token, account_email, spam_count, ham_count, last_seen_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(token, account_email) DO UPDATE SET
                        {col} = {col} + 1,
                        last_seen_at = excluded.last_seen_at""",
                (token, account_email,
                 1 if is_spam else 0,
                 0 if is_spam else 1,
                 now),
            )

    def log_feedback(self, message_uuid: str, account_email: str,
                     feedback: str) -> None:
        """Record user feedback in the audit log.

        Args:
            message_uuid: UUID of the message.
            account_email: Account email.
            feedback: One of ``"spam"``, ``"ham"``, ``"fraud"``.
        """
        now = datetime.now(UTC).isoformat()
        self._db.execute(
            "INSERT INTO spam_feedback (uuid, message_uuid, account_email, feedback, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), message_uuid, account_email, feedback, now),
        )


__all__ = [
    "SpamClassifier",
    "SpamTrainer",
    "_tokenize",
    "_chi2_score",
]
