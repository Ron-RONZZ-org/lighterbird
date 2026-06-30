"""IMAP/SMTP/ManageSieve server auto-detection from email domain.

Forked from A-lien's CLI auto-fill logic.

Detection strategy (in order):
1. Check ``known_providers()`` by exact domain match
2. Look up DNS MX record, check if the MX hostname matches a known
   provider pattern (e.g. ``*.migadu.com`` → Migadu IMAP/SMTP config)
3. SRV record lookup: ``_sieve._tcp.{domain}`` (RFC 5804 standard)
4. Implicit sieve via IMAP hostname (most common pattern)
5. Fallback: ``imap.{domain}`` / ``smtp.{domain}`` / ``sieve.{domain}``

Usage:
    from lighterbird.email.server_detect import detect_servers

    servers = detect_servers("user@example.com")
    # => {"imap": "...", "smtp": "...",
    #     "managesieve_host": "...", "managesieve_port": 4190,
    #     "method": "known_provider"}
"""

from __future__ import annotations

from typing import Any

_SIEVE_PORT = 4190


# ── Known provider patterns ────────────────────────────────────────────
# Each entry: (domain_exact | mx_substring) -> {imap, smtp, ...}
# domain_exact matches the email domain directly.
# mx_substring matches against the MX hostname (e.g. "migadu.com"
# matches "aspmx1.migadu.com").
# Extra keys like "managesieve" set the ManageSieve server hostname.
# Omit "managesieve" to let the detection logic infer it from IMAP.

_PROVIDER_DB: list[tuple[tuple[str, ...], dict[str, str]]] = [
    (("migadu.com",), {
        "imap": "imap.migadu.com", "smtp": "smtp.migadu.com",
        "managesieve": "imap.migadu.com",
    }),
    (("gmail.com", "googlemail.com"), {
        "imap": "imap.gmail.com", "smtp": "smtp.gmail.com",
    }),
    (("outlook.com", "hotmail.com", "live.com"), {
        "imap": "outlook.office365.com", "smtp": "smtp.office365.com",
    }),
    (("icloud.com", "me.com"), {"imap": "imap.mail.me.com", "smtp": "smtp.mail.me.com"}),
    (("yahoo.com",), {"imap": "imap.mail.yahoo.com", "smtp": "smtp.mail.yahoo.com"}),
    (("yandex.com",), {"imap": "imap.yandex.com", "smtp": "smtp.yandex.com"}),
    (("fastmail.com",), {"imap": "imap.fastmail.com", "smtp": "smtp.fastmail.com"}),
    (("zoho.com",), {"imap": "imap.zoho.com", "smtp": "smtp.zoho.com"}),
    # MX substring patterns — matched against MX hostname
    (("migadu.com",), {
        "imap": "imap.migadu.com", "smtp": "smtp.migadu.com",
        "managesieve": "imap.migadu.com",
    }),
    (("google.com", "googlemail.com"), {
        "imap": "imap.gmail.com", "smtp": "smtp.gmail.com",
    }),
    (("outlook.com", "protection.outlook.com"), {
        "imap": "outlook.office365.com", "smtp": "smtp.office365.com",
    }),
    (("icloud.com",), {"imap": "imap.mail.me.com", "smtp": "smtp.mail.me.com"}),
    (("yahoodns.net",), {"imap": "imap.mail.yahoo.com", "smtp": "smtp.mail.yahoo.com"}),
    (("mx.zone.eu",), {"imap": "imap.zone.ee", "smtp": "smtp.zone.ee"}),
]

# Additional known ManageSieve hostnames for providers where auto-detection
# patterns won't produce the correct result (e.g. Google uses sieve.google.com
# not sieve.gmail.com).
_KNOWN_SIEVE_HOSTS: dict[str, str] = {
    "gmail.com": "sieve.google.com",
    "googlemail.com": "sieve.google.com",
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com",
    "fastmail.com": "sieve.fastmail.com",
    "zoho.com": "sieve.zoho.com",
    "yahoo.com": "sieve.yahoo.com",
    "yandex.com": "sieve.yandex.com",
}


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


# ── ManageSieve detection helpers ─────────────────────────────────────

_SIEVE_HOSTNAME_PATTERNS = [
    "sieve.{domain}",
    "managesieve.{domain}",
    "sieve.{mx}",
    "managesieve.{mx}",
    "{imap}",  # same as IMAP server (most common pattern)
]


def _extract_domain(hostname: str) -> str:
    """Extract the registered domain from a hostname.

    Handles common patterns:
    - ``aspmx1.gmail.com`` → ``gmail.com``
    - ``mx1.example.co.uk`` → ``example.co.uk``
    - ``imap.migadu.com`` → ``migadu.com``

    Uses a simple heuristic: take the last 2 or 3 dot-separated parts
    depending on known 2-part TLDs.
    """
    import re
    # Known 2-part TLDs (co.uk, com.au, co.jp, etc.)
    two_part_tlds = {
        "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au",
        "co.jp", "ne.jp", "or.jp", "co.nz", "net.nz", "co.za",
        "com.br", "org.br", "com.ar",
    }
    parts = hostname.strip().lower().split(".")
    if len(parts) < 2:
        return hostname
    # Check for 2-part TLD
    if len(parts) >= 3 and ".".join(parts[-2:]) in two_part_tlds:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _lookup_srv(name: str) -> tuple[str, int] | None:
    """Look up an SRV record and return (hostname, port).

    Args:
        name: Full SRV name, e.g. ``_sieve._tcp.example.com``.

    Returns:
        ``(hostname, port)`` or ``None`` if not found or on error.
    """
    try:
        import dns.resolver
        try:
            answers = dns.resolver.resolve(name, "SRV")
            if answers:
                best = sorted(answers, key=lambda r: (r.priority, r.weight))[0]
                target = str(best.target).rstrip(".")
                return (target, best.port)
        except Exception:
            pass
    except ImportError:
        pass
    return None


def _probe_sieve_port(host: str, port: int = _SIEVE_PORT, timeout: float = 3.0) -> bool:
    """Quick TCP connectivity check to see if a host:port accepts connections.

    Returns True if the port is open (likely a ManageSieve server), False
    otherwise.
    """
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        result = s.connect_ex((host, port))
        s.close()
        return result == 0
    except Exception:
        return False


def _detect_managesieve(domain: str, imap_server: str, mx_hostname: str | None) -> dict[str, Any]:
    """Detect ManageSieve server hostname and port for *domain*.

    Tries in order:
    1. SRV ``_sieve._tcp.<domain>``
    2. SRV ``_sieve._tcp.<imap_server>`` (if different from domain)
    3. Common hostname patterns (sieve.<d>, managesieve.<d>, …)
    4. Fallback: same hostname as IMAP server, port 4190

    Returns:
        Dict with ``managesieve_host`` (str) and ``managesieve_port`` (int).
        Returns empty dict if nothing works.
    """
    result: dict[str, Any] = {}
    candidates: list[tuple[str, int]] = []

    # 1. SRV on domain
    srv = _lookup_srv(f"_sieve._tcp.{domain}")
    if srv:
        candidates.append(srv)

    # 2. SRV on IMAP hostname
    if imap_server and imap_server != domain:
        srv = _lookup_srv(f"_sieve._tcp.{imap_server}")
        if srv:
            candidates.append(srv)

    # 3. SRV on MX hostname
    if mx_hostname and mx_hostname != domain and mx_hostname != imap_server:
        srv = _lookup_srv(f"_sieve._tcp.{mx_hostname}")
        if srv:
            candidates.append(srv)

    # 4. Common hostname patterns
    for pattern in _SIEVE_HOSTNAME_PATTERNS:
        host = pattern.format(domain=domain, mx=mx_hostname or domain, imap=imap_server or f"imap.{domain}")
        if host:
            candidates.append((host, _SIEVE_PORT))

    # Deduplicate and probe
    seen: set[tuple[str, int]] = set()
    for host, port in candidates:
        key = (host.lower(), port)
        if key in seen:
            continue
        seen.add(key)
        if _probe_sieve_port(host, port):
            result["managesieve_host"] = host
            result["managesieve_port"] = port
            return result

    # No probe succeeded — return the most likely candidate anyway
    if candidates:
        best = candidates[0]
        result["managesieve_host"] = best[0]
        result["managesieve_port"] = best[1]
    elif imap_server:
        result["managesieve_host"] = imap_server
        result["managesieve_port"] = _SIEVE_PORT

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
    mx: str | None = None

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

    # Resolve IMAP
    if imap_server:
        result["imap"] = imap_server
    elif provider:
        result["imap"] = provider["imap"]
    else:
        result["imap"] = f"imap.{domain}"

    # Resolve SMTP
    if smtp_server:
        result["smtp"] = smtp_server
    elif provider:
        result["smtp"] = provider["smtp"]
    elif method == "mx_hostname":
        result["smtp"] = mx
    else:
        result["smtp"] = f"smtp.{domain}"

    # Resolve ManageSieve
    sieve_host = ""
    sieve_port = _SIEVE_PORT
    if provider and "managesieve" in provider:
        sieve_host = provider["managesieve"]
    elif domain in _KNOWN_SIEVE_HOSTS:
        sieve_host = _KNOWN_SIEVE_HOSTS[domain]
    elif mx:
        # Extract domain from MX hostname (e.g. aspmx1.gmail.com → gmail.com)
        mx_domain = _extract_domain(mx)
        if mx_domain in _KNOWN_SIEVE_HOSTS:
            sieve_host = _KNOWN_SIEVE_HOSTS[mx_domain]
    else:
        detected = _detect_managesieve(domain, result.get("imap", ""), mx)
        sieve_host = detected.get("managesieve_host", "")
        sieve_port = detected.get("managesieve_port", _SIEVE_PORT)
    if not sieve_host:
        # Last-resort fallback: use IMAP hostname (most common pattern)
        sieve_host = result.get("imap", f"imap.{domain}")

    result["managesieve_host"] = sieve_host
    result["managesieve_port"] = sieve_port
    result["method"] = method
    return result
