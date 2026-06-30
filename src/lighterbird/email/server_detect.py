"""IMAP/SMTP server auto-detection from email domain.

Forked from A-lien's CLI auto-fill logic.

Detection strategy:
1. Check ``known_providers()`` by exact domain match
2. Look up DNS MX record, check if the MX hostname matches a known
   provider pattern (e.g. ``*.migadu.com`` → Migadu IMAP/SMTP config)
3. Fallback: ``imap.{domain}`` / ``smtp.{domain}``

Usage:
    from lighterbird.email.server_detect import detect_servers

    servers = detect_servers("user@example.com")
    # => {"imap": "...", "smtp": "...", "method": "known_provider"}
"""

from __future__ import annotations

from typing import Any


# ── Known provider patterns ────────────────────────────────────────────
# Each entry: (domain_exact | mx_substring) -> {imap, smtp}
# domain_exact matches the email domain directly.
# mx_substring matches against the MX hostname (e.g. "migadu.com"
# matches "aspmx1.migadu.com").

_PROVIDER_DB: list[tuple[tuple[str, ...], dict[str, str]]] = [
    (("migadu.com",), {
        "imap": "imap.migadu.com", "smtp": "smtp.migadu.com",
        "managesieve": "managesieve.migadu.com",
    }),
    (("gmail.com", "googlemail.com"), {
        "imap": "imap.gmail.com", "smtp": "smtp.gmail.com",
        "managesieve": "sieve.google.com",
    }),
    (("outlook.com", "hotmail.com", "live.com"), {
        "imap": "outlook.office365.com", "smtp": "smtp.office365.com",
        "managesieve": "sieve.office365.com",
    }),
    (("icloud.com", "me.com"), {"imap": "imap.mail.me.com", "smtp": "smtp.mail.me.com"}),
    (("yahoo.com",), {"imap": "imap.mail.yahoo.com", "smtp": "smtp.mail.yahoo.com"}),
    (("yandex.com",), {"imap": "imap.yandex.com", "smtp": "smtp.yandex.com"}),
    (("fastmail.com",), {"imap": "imap.fastmail.com", "smtp": "smtp.fastmail.com"}),
    (("zoho.com",), {"imap": "imap.zoho.com", "smtp": "smtp.zoho.com"}),
    # MX substring patterns — matched against MX hostname
    (("migadu.com",), {
        "imap": "imap.migadu.com", "smtp": "smtp.migadu.com",
        "managesieve": "managesieve.migadu.com",
    }),
    (("google.com", "googlemail.com"), {
        "imap": "imap.gmail.com", "smtp": "smtp.gmail.com",
        "managesieve": "sieve.google.com",
    }),
    (("outlook.com", "protection.outlook.com"), {
        "imap": "outlook.office365.com", "smtp": "smtp.office365.com",
        "managesieve": "sieve.office365.com",
    }),
    (("icloud.com",), {"imap": "imap.mail.me.com", "smtp": "smtp.mail.me.com"}),
    (("yahoodns.net",), {"imap": "imap.mail.yahoo.com", "smtp": "smtp.mail.yahoo.com"}),
    (("mx.zone.eu",), {"imap": "imap.zone.ee", "smtp": "smtp.zone.ee"}),
]


def _lookup_mx(domain: str) -> str | None:
    """Look up the MX record for a domain.

    Returns the hostname of the highest-priority MX server, or None.
    """
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "MX")
        if answers:
            sorted_records = sorted(answers, key=lambda r: r.preference)
            return str(sorted_records[0].exchange).rstrip(".")
    except Exception:
        pass
    return None


def _iter_providers():
    """Yield (match_key, config, is_exact) pairs from the provider DB.

    The first entry for each provider pattern is the exact domain match,
    subsequent entries with the same patterns are MX substring matches.
    """
    seen_patterns: set[str] = set()
    for patterns, config in _PROVIDER_DB:
        key = "|".join(sorted(patterns))
        is_exact = key not in seen_patterns
        seen_patterns.add(key)
        yield patterns, config, is_exact


def known_providers() -> dict[str, dict[str, str]]:
    """Return known provider configs keyed by domain (exact matches only)."""
    result: dict[str, dict[str, str]] = {}
    for patterns, config, is_exact in _iter_providers():
        if is_exact:
            for p in patterns:
                result[p] = config
    return result


def detect_servers(
    email: str,
    imap_server: str = "",
    smtp_server: str = "",
) -> dict[str, Any]:
    """Detect IMAP and SMTP servers from an email address.

    Args:
        email: Email address (e.g. ``user@example.com``)
        imap_server: Previously specified IMAP server (optional)
        smtp_server: Previously specified SMTP server (optional)

    Returns:
        Dict with keys ``imap``, ``smtp``, and ``method``.

    Raises:
        ValueError: If the email address has no ``@``.
    """
    if "@" not in email:
        raise ValueError(f"Invalid email address: {email}")

    domain = email.split("@", 1)[1].strip().lower()
    if not domain:
        raise ValueError(f"Invalid email address (empty domain): {email}")

    # If both services are explicitly provided, return immediately
    if imap_server and smtp_server:
        return {"imap": imap_server, "smtp": smtp_server, "method": "explicit"}

    # Resolve provider config
    provider = None
    method = "fallback"

    # 1. Exact domain match
    for patterns, config, is_exact in _iter_providers():
        if is_exact and domain in patterns:
            provider = config
            method = "known_provider"
            break

    # 2. MX lookup + provider pattern match
    if provider is None:
        mx = _lookup_mx(domain)
        if mx:
            for patterns, config, is_exact in _iter_providers():
                if not is_exact:  # MX patterns only
                    mx_lower = mx.lower()
                    if any(p in mx_lower for p in patterns):
                        provider = config
                        method = "mx_provider"
                        break
            if provider is None:
                # MX hostname but no provider match → use MX for SMTP
                method = "mx_hostname"

    # Build result
    result: dict[str, Any] = {}

    if imap_server:
        result["imap"] = imap_server
    elif provider:
        result["imap"] = provider["imap"]
    else:
        result["imap"] = f"imap.{domain}"

    if smtp_server:
        result["smtp"] = smtp_server
    elif provider:
        result["smtp"] = provider["smtp"]
    elif method == "mx_hostname":
        result["smtp"] = mx
    else:
        result["smtp"] = f"smtp.{domain}"

    if provider and "managesieve" in provider:
        result["managesieve"] = provider["managesieve"]

    result["method"] = method
    return result
