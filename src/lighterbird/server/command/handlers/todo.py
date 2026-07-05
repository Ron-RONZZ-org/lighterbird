"""Command handlers for the ``!todo`` domain.

Registered paths:
    - todo.list / todo.tree
    - todo.add
    - todo.view
    - todo.done
    - todo.modify
    - todo.delete
    - todo.search
    - todo.template.*
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.registry import command

# Side-effect imports to register handlers split into sub-modules
from lighterbird.server.command.handlers.todo_list import (  # noqa: F401
    todo_list, todo_tree, todo_search,
)
from lighterbird.server.command.handlers.todo_crud import (  # noqa: F401
    todo_add, todo_view, todo_done, todo_modify, todo_delete,
)
from lighterbird.server.command.handlers.todo_template import (  # noqa: F401
    todo_template_root, todo_template_list, todo_template_add, todo_template_view,
    todo_template_modify, todo_template_delete,
)
from lighterbird.server.command.handlers.todo_export_import import (  # noqa: F401
    todo_export_root, todo_export_md, todo_import_root, todo_import_md,
)


@command("todo")
def todo_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo — Show available todo subcommands."""
    return {
        "type": "status",
        "title": "Todo Commands",
        "data": {
            "_summary": (
                "Available !todo commands:\n"
                "  !todo list                — List todos (flat)\n"
                "  !todo tree                — List todos (tree view)\n"
                "  !todo add <title>         — Add a todo\n"
                "  !todo view <uuid>         — View a todo\n"
                "  !todo done <uuid> [...]   — Mark todo(s) as done\n"
                "  !todo modify <uuid>       — Modify a todo\n"
                "  !todo delete <uuid> [...] — Delete a todo(s)\n"
                "  !todo search <query>      — Search todos\n"
                "  !todo draft               — List / recall todo drafts\n"
                "  !todo template            — Manage templates\n"
                "  !todo export md           — Export todo(s) to .md\n"
                "  !todo import md           — Import todo(s) from .md\n"
                "\nFlags for !todo add:\n"
                "  --parent <uuid>           — Set parent (subtask)\n"
                "  --dependency <uuid>       — Set dependency\n"
                "  --template <name>         — Use a template\n"
                "  --file <path|url>         — Attach a file\n"
                "  --due <DATE>, --priority N, --description TEXT\n"
                "  --text <name>:<value>     — Template field value\n"
            ),
        },
    }
