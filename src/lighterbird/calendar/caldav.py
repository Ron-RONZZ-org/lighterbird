"""CalDAV client — read-only pull sync.

Forked from A-organizi's utils/sync.py, stripped of push, sync queue, and worker.
"""

from __future__ import annotations

import urllib.error
import urllib.request


def remote_http_url(url: str) -> str:
    """Convert caldav:// URL to https://."""
    low = url.strip().lower()
    if low.startswith("caldav://"):
        return "https://" + low[9:]
    if low.startswith("caldavs://"):
        return "https://" + low[10:]
    return url.strip()


def http_fetch_text(
    url: str,
    username: str,
    password: str,
    method: str = "GET",
    body: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Fetch URL with HTTP Basic auth.

    Returns:
        Tuple of (status_code, response_body).
    """
    import base64

    https_url = remote_http_url(url)
    req = urllib.request.Request(https_url, data=body.encode() if body else None)
    req.get_method = lambda: method
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    req.add_header("Authorization", f"Basic {encoded}")
    req.add_header("Content-Type", "text/plain; charset=utf-8")
    req.add_header("Accept", "application/xml, text/calendar, text/html, */*")
    req.add_header("User-Agent", "lighterbird/1.0")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8") if e.fp else ""
    except urllib.error.URLError as e:
        return 0, str(e.reason)


def fetch_remote_calendar_payloads(
    url: str,
    username: str,
    password: str,
) -> list[tuple[str, str]]:
    """Fetch calendar events via CalDAV REPORT.

    Returns:
        List of (href, calendar_data) tuples, one per event.
    """
    report_body = """<?xml version="1.0"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <c:calendar-data/>
  </d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT">
      </c:comp-filter>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>"""
    headers = {
        "Content-Type": 'application/xml; charset="utf-8"',
        "Depth": "1",
    }
    status, text = http_fetch_text(
        url, username, password, "REPORT", report_body, headers,
    )
    if status == 207:
        return _parse_multistatus(text)
    elif status == 404:
        return []
    else:
        raise RuntimeError(f"CalDAV fetch failed: {status} — {text[:200] if text else 'no body'}")


def _parse_multistatus(text: str) -> list[tuple[str, str]]:
    """Parse CalDAV multistatus response."""
    import xml.etree.ElementTree as ET

    ns = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    results: list[tuple[str, str]] = []
    for response in root.findall("d:response", ns):
        href_el = response.find("d:href", ns)
        href = href_el.text if href_el is not None else ""
        data_el = response.find(".//c:calendar-data", ns)
        data = data_el.text if data_el is not None else ""
        results.append((href.strip(), data.strip()))
    return results


def probe_calendar_config(
    url: str, username: str, password: str,
) -> dict[str, str]:
    """Probe remote calendar configuration.

    Returns:
        Dict with 'count' (event count) and 'description'.
    """
    if not username.strip():
        raise ValueError("Username is required for remote calendar.")
    if not password.strip():
        raise ValueError("Password is required for remote calendar.")
    https_url = remote_http_url(url)
    status, resp_body = http_fetch_text(https_url, username, password)
    if status == 401 or status == 403:
        msg = "Invalid username or password."
        if resp_body.strip():
            msg += f" Server: {resp_body.strip()[:120]}"
        raise ValueError(msg)
    if status == 404:
        raise ValueError("Calendar not found at URL.")
    if status not in (200, 207):
        raise RuntimeError(f"Calendar access failed: HTTP {status}")
    try:
        payloads = fetch_remote_calendar_payloads(https_url, username, password)
        count = len(payloads)
    except Exception:
        count = 0
    return {"count": str(count), "description": f"{count} event(s) found"}


# ──────────────────────────────────────────────────────────────────────────────
# CalDAV push / delete helpers
# ──────────────────────────────────────────────────────────────────────────────


_HTTP_DESCRIPTION: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized — check username and password",
    403: "Forbidden — check credentials or calendar permissions",
    404: "Not Found — check calendar URL",
    405: "Method Not Allowed",
    408: "Request Timeout",
    409: "Conflict",
    500: "Internal Server Error",
}


def _event_url(url: str, event_uuid: str, remote_href: str | None = None) -> str:
    """Build the PUT/DELETE URL for a remote event.

    Uses the server-provided ``remote_href`` when available, otherwise
    falls back to fabricating ``{url}/{event_uuid}.ics``.
    """
    if remote_href:
        if remote_href.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}{remote_href}"
        return remote_href
    return url.rstrip("/") + f"/{event_uuid}.ics"


def push_event(
    url: str,
    username: str,
    password: str,
    ics_payload: str,
    event_uuid: str,
    remote_href: str | None = None,
) -> int:
    """PUT an ICS event to the remote CalDAV server.

    Args:
        url: Base calendar URL.
        username: Username for Basic auth.
        password: Password for Basic auth.
        ics_payload: Full ICS text (VCALENDAR wrapper).
        event_uuid: Event UUID used as the resource name.
        remote_href: Server-provided resource path (from multistatus REPORT).

    Returns:
        HTTP status code (200, 201, or 204 on success).

    Raises:
        RuntimeError: If the server returns an unexpected status.
    """
    put_url = _event_url(url, event_uuid, remote_href)
    headers = {
        "Content-Type": "text/calendar; charset=utf-8",
    }
    status, resp_body = http_fetch_text(
        put_url, username, password, "PUT", ics_payload, headers,
    )
    if status not in (200, 201, 204):
        desc = _HTTP_DESCRIPTION.get(status, f"HTTP {status}")
        msg = f"CalDAV PUT failed: {desc} — URL: {put_url}"
        if resp_body:
            msg += f" — server: {resp_body.strip()[:120]}"
        raise RuntimeError(msg)
    return status


def delete_event(
    url: str,
    username: str,
    password: str,
    event_uuid: str,
    remote_href: str | None = None,
) -> int:
    """DELETE an event from the remote CalDAV server.

    Args:
        url: Base calendar URL.
        username: Username for Basic auth.
        password: Password for Basic auth.
        event_uuid: Event UUID used as the resource name.
        remote_href: Server-provided resource path (from multistatus REPORT).

    Returns:
        HTTP status code (200 or 204 on success; 404 is accepted).

    Raises:
        RuntimeError: If the server returns an unexpected status.
    """
    delete_url = _event_url(url, event_uuid, remote_href)
    status, resp_body = http_fetch_text(
        delete_url, username, password, "DELETE",
    )
    if status not in (200, 204, 404):
        desc = _HTTP_DESCRIPTION.get(status, f"HTTP {status}")
        msg = f"CalDAV DELETE failed: {desc} — URL: {delete_url}"
        if resp_body:
            msg += f" — server: {resp_body.strip()[:120]}"
        raise RuntimeError(msg)
    return status
