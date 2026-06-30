"""Server-side command tokenizer for expanded template strings.

Must produce the same output as the frontend ``parser.js:parseCommand()``
for the same input. Used by ``UserCommandsService`` to parse expanded
command templates into tokens + flags.

Grammar (matching frontend ``parser.js``):

- Tokens are space-delimited
- ``--flag value`` assigns value to flag
- ``--flag=value`` inline syntax
- ``"double quoted"`` tokens preserve spaces
- Leading ``!`` is optional (templates omit it)
"""

from __future__ import annotations

import shlex
from typing import Any


def parse_expanded(cmd_str: str) -> tuple[list[str], dict[str, str]]:
    """Parse an expanded command string into tokens and flags.

    This reimplements the frontend ``parseCommand()`` on the server side
    for expanded alias templates.

    Args:
        cmd_str: Command string without leading ``!``,
            e.g. ``email list --folder ron@ronzz.org/INBOX``.

    Returns:
        ``(tokens, flags)`` where tokens are positional arguments and
        flags is a dict of flag name → value.
    """
    # Strip leading ! if present (templates should not have it, but be safe)
    text = cmd_str.strip()
    if text.startswith("!"):
        text = text[1:].strip()

    tokens: list[str] = []
    flags: dict[str, str] = {}
    in_flag: str | None = None

    # Use shlex for robust quoting — it handles double quotes, escapes, etc.
    try:
        parts = shlex.split(text)
    except ValueError:
        # Fallback: simple whitespace split if quoting is broken
        parts = text.split()

    for part in parts:
        if part.startswith("--"):
            # If a previous flag is waiting for a value, treat it as boolean
            if in_flag is not None:
                flags[in_flag] = "true"
                in_flag = None

            # Could be --flag or --flag=value
            if "=" in part:
                name, value = part[2:].split("=", 1)
                flags[name] = value
            else:
                # Start expecting a value
                in_flag = part[2:]
        elif part.startswith("-") and len(part) == 2 and not part[1].isdigit():
            # Short flag: -f (value follows as next token)
            in_flag = part[1]
        elif in_flag is not None:
            flags[in_flag] = part
            in_flag = None
        else:
            tokens.append(part)

    # If a flag was expected but no following value, treat it as boolean
    if in_flag is not None:
        flags[in_flag] = "true"

    return tokens, flags
