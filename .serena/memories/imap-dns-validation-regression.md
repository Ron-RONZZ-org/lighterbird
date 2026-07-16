# IMAP DNS Validation Bug — Critical (2026-07-11)

## The Bug (plagued us for a long time)

When running `!email account modify test@ronzz.org --redetect`, the detected IMAP/SMTP servers were silently saved **without DNS validation**. If DNS resolution for MX records was temporarily unavailable (timeout, network blip, resolver latency), `detect_servers()` fell back to `imap.{domain}` / `smtp.{domain}` (e.g. `imap.ronzz.org`) and this WRONG value was persisted. The user saw "success" but the account had incorrect servers.

## Root Cause

Two problems:

1. **`account_modify --redetect` had NO DNS validation at all** — it called `detect_servers()` and saved blindly. The `account_add` handler had validation, but it was never replicated to `account_modify`.

2. **`account_add` validation was too narrow** — it only checked `method == "fallback"`. MX-based detections (like `ronzz.org → aspmx1.migadu.com` → `imap.migadu.com`) were NOT validated. Even correct-looking detection could return an unresolvable server.

## The Fix

Commit `a7b3539` introduced a shared `_validate_imap_dns()` helper in `email_account.py`:

```python
def _validate_imap_dns(detected: dict) -> str | None:
    host = detected.get("imap", "")
    port = detected.get("imap_port", 993)
    if not host:
        return "Auto-detection did not produce an IMAP server hostname."
    try:
        socket.getaddrinfo(host, port)
    except socket.gaierror:
        return f"The detected IMAP server '{host}' does not resolve in DNS. ..."
    return None
```

Applied to:
- **`account_add`**: returns `form-required` redirect with error message on failure
- **`account_modify --redetect`**: raises `CommandValidationError` on failure

Both validate ALL detection methods, not just "fallback".

## Always Ensure Visibility

**When modifying any IMAP/SMTP auto-detection logic, ALWAYS add DNS validation.** The pattern is:

1. Call `detect_servers()` to get the detected server
2. Call `_validate_imap_dns(detected)` to check it resolves
3. If validation fails, return an error (not silent fallback)

This applies to:
- Adding new commands that auto-detect IMAP/SMTP
- Modifying existing detection flows
- Creating new seed scripts or account creation paths

## Git Trail

- `5223d6a` — Introduced `--redetect` flag + DNS validation for `account_add` only (partial)
- `61d7801` — Changed `account_add` DNS validation from error to form redirect
- `a7b3539` — THIS FIX: extracted `_validate_imap_dns()`, applied to both handlers, covers all detection methods
