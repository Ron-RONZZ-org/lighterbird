"""Command handlers for the ``!user info`` profile domain.

Registered paths:
    - user
    - user.info
    - user.info.list
    - user.info.add
    - user.info.view
    - user.info.modify
    - user.info.delete
"""

from __future__ import annotations

import json
from typing import Any

from lighterbird.profiles.services.profiles import ProfileError, ProfileService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_profiles_service


@command("user")
def _override_user_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!user — Show available user subcommands.

    Overrides the existing user_root from user_commands.py.
    The registry only keeps one handler per path, so the last @command("user")
    wins. This ensures the root prompt lists both ``saved-commands`` and ``info``.
    """
    return {
        "type": "status",
        "title": "User Commands",
        "data": {
            "_summary": (
                "Available !user commands:\n"
                "  !user saved-commands list              — List saved commands\n"
                "  !user saved-commands add               — Add a saved command\n"
                "  !user saved-commands modify <alias>    — Modify a saved command\n"
                "  !user saved-commands remove <alias>    — Remove saved command(s)\n"
                "  !user info list                        — List user profiles\n"
                "  !user info add                         — Add a user profile\n"
                "  !user info view <uuid>                 — View a profile\n"
                "  !user info modify <uuid>               — Modify a profile\n"
                "  !user info delete <uuid>               — Delete a profile"
            ),
        },
    }


@command("user.info")
def user_info_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!user info — Show available profile subcommands."""
    return {
        "type": "status",
        "title": "User Profiles",
        "data": {
            "_summary": (
                "Available !user info commands:\n"
                "  !user info list                 — List user profiles\n"
                "  !user info add <profile-name>   — Create a new profile\n"
                "  !user info view <uuid>          — View a profile's details\n"
                "  !user info modify <uuid>        — Modify a profile\n"
                "  !user info delete <uuid>        — Delete a profile"
            ),
        },
    }


# ── Flag parsing helpers ──────────────────────────────────────────────────


def _parse_tagged_values(raw: str) -> list[dict[str, str]]:
    """Parse ``tag:value`` pairs, possibly comma-separated.

    ``--email "work:a@b.com,home:c@d.com"`` → ``[{"tag":"work","value":"a@b.com"},{"tag":"home","value":"c@d.com"}]``
    ``--email work:a@b.com`` → ``[{"tag":"work","value":"a@b.com"}]``
    """
    results: list[dict[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            tag, _, value = part.partition(":")
            results.append({"tag": tag.strip(), "value": value.strip()})
        else:
            results.append({"tag": "", "value": part})
    return results


def _parse_custom_fields(raw: str) -> dict[str, str]:
    """Parse ``key:value`` pairs, comma-separated.

    ``--custom "key1:val1,key2:val2"`` → ``{"key1":"val1","key2":"val2"}``
    """
    result: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            key, _, value = part.partition(":")
            result[key.strip()] = value.strip()
        else:
            result[part] = ""
    return result


def _extract_profile_data(
    flags: dict[str, str],
    optional_name: str | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract profile fields from command flags into a data dict.

    Args:
        flags: The parsed flag dict from the command handler.
        optional_name: If set, use as profile_name (for add).
        existing: If set, use as base for updates (preserve existing values).

    Returns:
        Data dict ready for ProfileService.create() or .update().
    """
    data: dict[str, Any] = {}

    if optional_name is not None:
        data["profile_name"] = optional_name

    for key, flag_key in [
        ("given_name", "first-name"),
        ("middle_names", "middle-names"),
        ("family_name", "last-name"),
        ("date_of_birth", "dob"),
        ("place_of_birth", "place-of-birth"),
        ("address", "address"),
        ("post_code", "post-code"),
        ("organization", "organization"),
        ("position", "position"),
        ("notes", "notes"),
    ]:
        if flag_key in flags:
            data[key] = flags[flag_key]

    if "email" in flags:
        data["emails"] = json.dumps(_parse_tagged_values(flags["email"]), ensure_ascii=False)
    if "phone" in flags:
        data["phones"] = json.dumps(_parse_tagged_values(flags["phone"]), ensure_ascii=False)
    if "custom" in flags:
        data["custom_fields"] = json.dumps(_parse_custom_fields(flags["custom"]), ensure_ascii=False)

    return data


# ── Handlers ──────────────────────────────────────────────────────────────


@command("user.info.list")
def user_info_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!user info list — List all user profiles."""
    svc: ProfileService = get_profiles_service()
    profiles = svc.list()
    items = []
    for p in profiles:
        items.append({
            "uuid": p["uuid"][:8],
            "profile_name": p["profile_name"],
            "full_name": p["full_name"],
            "primary_email": p.get("_primary_email", ""),
            "organization": p["organization"],
            "updated_at": p["updated_at"],
        })
    return {
        "type": "status",
        "title": "User Profiles",
        "data": {"user_profiles": items, "total": len(items)},
    }


@command("user.info.add", interactive=True)
def user_info_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!user info add <profile-name> [--first-name ...] [--last-name ...] ...

    Create a new user identity profile.

    Example::

        !user info add work --first-name Alice --last-name Smith \\
            --email "work:alice@corp.com,personal:alice@gmail.com" \\
            --phone "mobile:+1234567890" \\
            --organization "ACME Corp" --position Engineer
    """
    if not remaining:
        raise CommandValidationError(
            "Missing profile name.",
            "Usage: !user info add <profile-name> [--first-name ...] [--last-name ...] ...",
        )
    profile_name = remaining[0]

    svc: ProfileService = get_profiles_service()
    data = _extract_profile_data(flags, optional_name=profile_name)

    try:
        result = svc.create(data)
    except ProfileError as e:
        raise CommandValidationError(str(e))
    except Exception as e:
        raise CommandValidationError(f"Failed to create profile: {e}")

    return {
        "type": "status",
        "title": "Profile Created",
        "data": {
            "uuid": result["uuid"][:8],
            "profile_name": result["profile_name"],
            "full_name": result["full_name"],
        },
    }


@command("user.info.view")
def user_info_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!user info view <uuid> — View profile details."""
    if not remaining:
        raise CommandValidationError(
            "Missing profile UUID.",
            "Usage: !user info view <uuid>",
        )

    svc: ProfileService = get_profiles_service()
    profile = svc.get(remaining[0])
    if not profile:
        raise CommandValidationError(f"Profile not found: '{remaining[0][:8]}'")

    # Pretty-print JSON fields for display
    display = dict(profile)
    for field in ("emails", "phones", "custom_fields"):
        try:
            display[field] = json.loads(display.get(field, "[]" if field != "custom_fields" else "{}"))
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "type": "status",
        "title": f"Profile: {profile['profile_name']}",
        "data": display,
    }


@command("user.info.modify", interactive=True)
def user_info_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!user info modify <uuid> [--first-name ...] [--last-name ...] ...

    Modify an existing user profile.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing profile UUID.",
            "Usage: !user info modify <uuid> [--first-name ...] [--last-name ...] ...",
        )
    uuid_str = remaining[0]

    svc: ProfileService = get_profiles_service()
    existing = svc.get(uuid_str)
    if not existing:
        raise CommandValidationError(f"Profile not found: '{uuid_str[:8]}'")

    data = _extract_profile_data(flags, existing=existing)
    if not data:
        raise CommandValidationError(
            "No fields to update.",
            "Specify at least one flag to modify, e.g. --first-name ...",
        )

    try:
        result = svc.update(uuid_str, data)
    except ProfileError as e:
        raise CommandValidationError(str(e))
    except Exception as e:
        raise CommandValidationError(f"Failed to modify profile: {e}")

    return {
        "type": "status",
        "title": "Profile Updated",
        "data": {
            "uuid": result["uuid"][:8],
            "profile_name": result["profile_name"],
            "full_name": result["full_name"],
        },
    }


def _resolve_uuid(svc: ProfileService, raw: str) -> str | None:
    """Resolve a profile identifier to its UUID.

    If *raw* looks like a UUID (hex of 6+ chars), try direct delete first.
    Otherwise, look up by profile_name.
    """
    import re
    # UUID-like: hex with optional hyphens, at least 6 chars
    is_uuid_like = bool(re.match(r'^[0-9a-fA-F-]{6,}$', raw))
    if is_uuid_like:
        profiles = svc.list()
        for p in profiles:
            puid = p.get("uuid", "")
            if puid.replace("-", "").startswith(raw.replace("-", "")):
                return puid
    # Fall back to profile name lookup
    profiles = svc.list()
    for p in profiles:
        if p.get("profile_name", "").lower() == raw.lower():
            return p["uuid"]
    return None


@command("user.info.delete")
def user_info_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!user info delete <uuid-or-name> [uuid-or-name...] — Delete one or more profiles.

    Accepts both UUID prefixes and profile names.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing profile UUID or name.",
            "Usage: !user info delete <uuid-or-name> [uuid-or-name...]",
        )

    svc: ProfileService = get_profiles_service()
    removed: list[str] = []
    not_found: list[str] = []

    for raw in remaining:
        resolved = _resolve_uuid(svc, raw)
        if resolved and svc.delete(resolved):
            removed.append(resolved[:8])
        else:
            # Show raw input truncated for non-found — no misleading truncation
            display = raw[:16] + "…" if len(raw) > 16 else raw
            not_found.append(display)

    return {
        "type": "status",
        "title": "Profile(s) Deleted",
        "data": {"removed": removed, "not_found": not_found},
    }
