"""Command handlers for the ``!letter`` domain.

Registered paths:
    - letter.list
    - letter.add
    - letter.send
    - letter.view
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.registry import command

# Side-effect imports to register handlers split into sub-modules
from lighterbird.server.command.handlers.letter_crud import (  # noqa: F401
    letter_list,
    letter_add,
    letter_view,
)
from lighterbird.server.command.handlers.letter_send import (  # noqa: F401
    letter_send,
    letter_pdf,
)
from lighterbird.server.command.handlers.letter_export_import import (  # noqa: F401
    letter_export,
    letter_export_md,
    letter_import_root,
    letter_import_md,
)


@command("letter")
def letter_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "status",
        "title": "Letter Commands",
        "data": {
            "_summary": (
                "Available !letter commands:\n"
                "  !letter list              — List letters\n"
                "  !letter view <uuid>       — View a letter\n"
                "  !letter add <object>      — Add a received letter\n"
                "  !letter send <recipient>  — Send a letter"
            ),
        },
    }
